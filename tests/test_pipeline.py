"""
Tests for backend.py _continue_pipeline stage ordering and error routing.

Key invariants (updated for new pipeline stage order):
- speaker_mapping:done fires at the start of _continue_pipeline
- updating_transcript:running fires after speaker_mapping:done
- updating_transcript:done fires AFTER save_all() succeeds, never before
- Missing JSON → updating_transcript:error (early exit, no LLM stages)
- save_all() I/O failure → updating_transcript:error (no LLM stages)
- LLM stages do not fire after any updating_transcript error
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import backend once at module level, with heavy deps mocked
# ---------------------------------------------------------------------------

with patch.dict(sys.modules, {"webview": MagicMock(), "sounddevice": MagicMock()}):
    import backend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api() -> backend.API:
    """Return a backend.API instance wired to a mock window."""
    win = MagicMock()
    return backend.API([win])


def _make_whisperx_json(tmp_path: Path) -> Path:
    data = {
        "segments": [
            {
                "start": 0.0, "end": 2.0,
                "text": "Hello from speaker zero.",
                "speaker": "SPEAKER_00",
                "words": [],
            },
            {
                "start": 2.5, "end": 5.0,
                "text": "And I am speaker one.",
                "speaker": "SPEAKER_01",
                "words": [],
            },
        ]
    }
    p = tmp_path / "transcript.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


MAPPING = {"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"}


def _run_continue_pipeline(api: backend.API, json_path: Path, mapping: dict):
    """
    Call _continue_pipeline synchronously and return a list of (stage, status)
    tuples emitted via _notify_stage. _run_llm_stages is patched to a no-op.
    """
    events = []
    original_notify = api._notify_stage

    def capturing_notify(stage, status, data=None):
        events.append((stage, status))
        original_notify(stage, status, data)

    api._notify_stage = capturing_notify

    with patch.object(api, "_run_llm_stages", return_value=None):
        api._continue_pipeline(json_path, mapping)

    return events


# ---------------------------------------------------------------------------
# Happy path: stage ordering
# ---------------------------------------------------------------------------

class TestContinuePipelineStageOrder:
    def test_updating_transcript_done_is_emitted(self, tmp_path):
        json_path = _make_whisperx_json(tmp_path)
        events = _run_continue_pipeline(_make_api(), json_path, MAPPING)
        assert ("updating_transcript", "done") in events

    def test_speaker_mapping_done_is_emitted(self, tmp_path):
        json_path = _make_whisperx_json(tmp_path)
        events = _run_continue_pipeline(_make_api(), json_path, MAPPING)
        assert ("speaker_mapping", "done") in events

    def test_speaker_mapping_done_precedes_updating_transcript(self, tmp_path):
        """speaker_mapping:done must fire before updating_transcript:done."""
        json_path = _make_whisperx_json(tmp_path)
        events = _run_continue_pipeline(_make_api(), json_path, MAPPING)
        done_stages = [s for s, st in events if st == "done"]
        assert "speaker_mapping" in done_stages
        assert "updating_transcript" in done_stages
        assert done_stages.index("speaker_mapping") < done_stages.index("updating_transcript")

    def test_updating_transcript_done_fires_after_save_all(self, tmp_path):
        """save_all() must complete before updating_transcript:done is emitted."""
        import postprocess
        json_path = _make_whisperx_json(tmp_path)
        api = _make_api()
        order = []

        original_notify = api._notify_stage
        def tracking_notify(stage, status, data=None):
            if stage == "updating_transcript" and status == "done":
                order.append("notify_done")
            original_notify(stage, status, data)
        api._notify_stage = tracking_notify

        real_save_all = postprocess.save_all

        def save_and_track(*args, **kwargs):
            result = real_save_all(*args, **kwargs)
            order.append("save_all_returned")
            return result

        with patch.object(backend, "save_all", side_effect=save_and_track):
            with patch.object(api, "_run_llm_stages", return_value=None):
                api._continue_pipeline(json_path, MAPPING)

        assert "save_all_returned" in order, "save_all was never called"
        assert "notify_done" in order, "updating_transcript:done was never emitted"
        assert order.index("save_all_returned") < order.index("notify_done"), \
            "save_all must complete before updating_transcript:done fires"

    def test_no_error_events_on_happy_path(self, tmp_path):
        json_path = _make_whisperx_json(tmp_path)
        events = _run_continue_pipeline(_make_api(), json_path, MAPPING)
        errors = [(s, st) for s, st in events if st == "error"]
        assert not errors, f"Unexpected errors on happy path: {errors}"


# ---------------------------------------------------------------------------
# Missing JSON file
# ---------------------------------------------------------------------------

class TestContinuePipelineMissingJSON:
    def test_fires_updating_transcript_error(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        events = _run_continue_pipeline(_make_api(), missing, MAPPING)
        assert ("updating_transcript", "error") in events

    def test_error_message_mentions_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        api = _make_api()
        error_data = []
        original = api._notify_stage

        def cap(stage, status, data=None):
            if stage == "updating_transcript" and status == "error":
                error_data.append(data or {})
            original(stage, status, data)

        api._notify_stage = cap
        with patch.object(api, "_run_llm_stages", return_value=None):
            api._continue_pipeline(missing, MAPPING)

        assert error_data, "No updating_transcript:error was emitted"
        msg = error_data[0].get("error", "")
        assert "nonexistent.json" in msg or "not found" in msg.lower() or "Transcript" in msg

    def test_llm_stages_do_not_fire(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        events = _run_continue_pipeline(_make_api(), missing, MAPPING)
        llm_stages = {"summary", "dm_notes", "scenes", "timeline",
                       "leaderboard", "locations", "npcs", "loot", "missions"}
        fired = {s for s, _ in events}
        assert not fired & llm_stages, f"LLM stages must not fire: {fired & llm_stages}"

    def test_updating_transcript_not_done(self, tmp_path):
        """updating_transcript must not be marked done when JSON is missing."""
        missing = tmp_path / "nonexistent.json"
        events = _run_continue_pipeline(_make_api(), missing, MAPPING)
        assert ("updating_transcript", "done") not in events


# ---------------------------------------------------------------------------
# save_all I/O failure
# ---------------------------------------------------------------------------

class TestContinuePipelineSaveAllFailure:
    def _collect_events(self, json_path, exc):
        api = _make_api()
        events = []
        original = api._notify_stage

        def cap(stage, status, data=None):
            events.append((stage, status))
            original(stage, status, data)

        api._notify_stage = cap
        with patch.object(backend, "save_all", side_effect=exc):
            with patch.object(api, "_run_llm_stages", return_value=None):
                api._continue_pipeline(json_path, MAPPING)
        return events

    def test_fires_updating_transcript_error(self, tmp_path):
        json_path = _make_whisperx_json(tmp_path)
        events = self._collect_events(json_path, OSError("disk full"))
        assert ("updating_transcript", "error") in events

    def test_speaker_mapping_still_marked_done(self, tmp_path):
        """speaker_mapping:done fires before save_all, so it should still be done."""
        json_path = _make_whisperx_json(tmp_path)
        events = self._collect_events(json_path, OSError("disk full"))
        assert ("speaker_mapping", "done") in events

    def test_llm_stages_do_not_fire(self, tmp_path):
        json_path = _make_whisperx_json(tmp_path)
        events = self._collect_events(json_path, OSError("disk full"))
        llm_stages = {"summary", "dm_notes", "scenes", "timeline",
                       "leaderboard", "locations", "npcs", "loot", "missions"}
        assert not {s for s, _ in events} & llm_stages

    def test_updating_transcript_not_done(self, tmp_path):
        json_path = _make_whisperx_json(tmp_path)
        events = self._collect_events(json_path, OSError("disk full"))
        assert ("updating_transcript", "done") not in events


# ---------------------------------------------------------------------------
# postprocess.save_all — missing source JSON raises clearly
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# run_single_stage — context setup and restoration
# ---------------------------------------------------------------------------

class TestRunSingleStage:
    def _make_session(self, tmp_path):
        """Create a session with transcript file and campaign context."""
        txt_path = tmp_path / "transcript.txt"
        txt_path.write_text("DM: Welcome to the session.", encoding="utf-8")
        return {
            "id": "test-session-123",
            "campaign_id": "test-campaign-456",
            "season_id": "test-season-789",
            "txt_path": str(txt_path),
            "output_dir": str(tmp_path),
            "character_names": ["DM", "Aragorn"],
        }

    def test_invalid_stage_returns_error(self, tmp_path):
        api = _make_api()
        session = self._make_session(tmp_path)
        with patch.object(backend, "get_sessions", return_value=[session]):
            result = api.run_single_stage("test-session-123", "nonexistent_stage")
        assert result["ok"] is False
        assert "Invalid stage" in result["error"]

    def test_new_stages_are_valid(self, tmp_path):
        """All 5 new extraction stages should be accepted by run_single_stage."""
        api = _make_api()
        session = self._make_session(tmp_path)
        new_stages = ["leaderboard", "locations", "npcs", "loot", "missions"]
        for stage in new_stages:
            with patch.object(backend, "get_sessions", return_value=[session]):
                result = api.run_single_stage("test-session-123", stage)
            assert result["ok"] is True, f"Stage '{stage}' should be valid but got: {result}"

    def test_missing_session_returns_error(self):
        api = _make_api()
        with patch.object(backend, "get_sessions", return_value=[]):
            result = api.run_single_stage("ghost-id", "summary")
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_missing_transcript_returns_error(self, tmp_path):
        api = _make_api()
        session = self._make_session(tmp_path)
        session["txt_path"] = str(tmp_path / "nonexistent.txt")
        with patch.object(backend, "get_sessions", return_value=[session]):
            result = api.run_single_stage("test-session-123", "summary")
        assert result["ok"] is False
        assert "transcript" in result["error"].lower()

    def test_sets_campaign_context(self, tmp_path):
        api = _make_api()
        session = self._make_session(tmp_path)
        campaigns_data = [{
            "id": "test-campaign-456",
            "name": "Test Campaign",
            "seasons": [{"id": "test-season-789", "number": 1, "characters": ["char-1", "char-2"]}],
        }]
        with patch.object(backend, "get_sessions", return_value=[session]), \
             patch.object(backend, "_get_campaigns", return_value=campaigns_data):
            result = api.run_single_stage("test-session-123", "summary")
        assert result["ok"] is True
        assert api._current_campaign_id == "test-campaign-456"
        assert api._current_character_ids == ["char-1", "char-2"]

    def test_restores_context_after_completion(self, tmp_path):
        """After thread completes, context should be restored."""
        import time as _time
        api = _make_api()
        api._current_session_id = "original-session"
        api._current_campaign_id = "original-campaign"
        api._current_character_ids = ["original-char"]
        session = self._make_session(tmp_path)
        with patch.object(backend, "get_sessions", return_value=[session]), \
             patch.object(backend, "_get_campaigns", return_value=[]), \
             patch.object(api, "_generate_summary_streaming", return_value="Test summary"), \
             patch.object(api, "_save_summary"):
            api.run_single_stage("test-session-123", "summary")
            # Wait for thread to finish
            _time.sleep(0.5)
        assert api._current_session_id == "original-session"
        assert api._current_campaign_id == "original-campaign"
        assert api._current_character_ids == ["original-char"]


class TestSaveAllMissingSource:
    def test_raises_when_json_path_missing(self, tmp_path):
        """save_all() raises when the source JSON doesn't exist.
        The backend guards against this upstream with json_path.exists(),
        but the contract must stay explicit so callers can't silently skip it."""
        from postprocess import save_all
        missing = tmp_path / "ghost.json"
        with pytest.raises((FileNotFoundError, OSError, ValueError)):
            save_all(str(missing), {"SPEAKER_00": "Alice"}, tmp_path)
