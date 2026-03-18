"""
Tests for retry_transcription and start_job transcription notification.

Covers:
- retry_transcription with valid session + audio → calls start_job correctly
- retry_transcription with explicit model/language params
- retry_transcription with nonexistent session → error
- retry_transcription with session missing audio → error
- start_job emits _notify_stage("transcription", "running") before starting
"""
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Import backend with heavy deps mocked
# ---------------------------------------------------------------------------

with patch.dict(sys.modules, {"webview": MagicMock(), "sounddevice": MagicMock()}):
    import backend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api():
    # type: () -> backend.API
    win = MagicMock()
    return backend.API([win])


def _make_session(tmp_path, audio=True):
    # type: (Path, bool) -> dict
    """Create a fake session dict. If audio=True, create an actual audio file."""
    audio_path = ""
    if audio:
        audio_file = tmp_path / "recording.m4a"
        audio_file.write_bytes(b"fake audio data")
        audio_path = str(audio_file)

    return {
        "id": "sess-001",
        "campaign_id": "camp-001",
        "season_id": "season-001",
        "output_dir": str(tmp_path / "output"),
        "audio_path": audio_path,
        "character_names": ["DM", "Thorin", "Elara"],
    }


# ---------------------------------------------------------------------------
# retry_transcription — valid session with audio
# ---------------------------------------------------------------------------

class TestRetryTranscriptionValidSession:
    def test_calls_start_job_with_correct_audio_path(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path)
        with patch.object(backend, "_get_session_by_id", return_value=session), \
             patch.object(backend, "_get_campaigns", return_value=[]), \
             patch.object(backend, "get_pref", return_value="large-v2"), \
             patch.object(api, "start_job", return_value={"ok": True}) as mock_start:
            result = api.retry_transcription("sess-001")

        assert result["ok"] is True
        mock_start.assert_called_once()
        args = mock_start.call_args
        assert args[0][0] == session["audio_path"]

    def test_passes_character_names_to_start_job(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path)
        with patch.object(backend, "_get_session_by_id", return_value=session), \
             patch.object(backend, "_get_campaigns", return_value=[]), \
             patch.object(backend, "get_pref", return_value="large-v2"), \
             patch.object(api, "start_job", return_value={"ok": True}) as mock_start:
            api.retry_transcription("sess-001")

        # character_names is the 4th positional arg
        char_names = mock_start.call_args[0][3]
        assert "DM" in char_names
        assert "Thorin" in char_names
        assert "Elara" in char_names

    def test_num_speakers_matches_character_count(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path)
        with patch.object(backend, "_get_session_by_id", return_value=session), \
             patch.object(backend, "_get_campaigns", return_value=[]), \
             patch.object(backend, "get_pref", return_value="large-v2"), \
             patch.object(api, "start_job", return_value={"ok": True}) as mock_start:
            api.retry_transcription("sess-001")

        # num_speakers is the 3rd positional arg
        num_speakers = mock_start.call_args[0][2]
        assert num_speakers == 3  # DM, Thorin, Elara

    def test_restores_session_context(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path)
        with patch.object(backend, "_get_session_by_id", return_value=session), \
             patch.object(backend, "_get_campaigns", return_value=[]), \
             patch.object(backend, "get_pref", return_value="large-v2"), \
             patch.object(api, "start_job", return_value={"ok": True}):
            api.retry_transcription("sess-001")

        assert api._current_session_id == "sess-001"
        assert api._current_campaign_id == "camp-001"
        assert str(api._current_session_dir) == str(tmp_path / "output")


# ---------------------------------------------------------------------------
# retry_transcription — explicit model/language params
# ---------------------------------------------------------------------------

class TestRetryTranscriptionWithParams:
    def test_uses_explicit_model(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path)
        with patch.object(backend, "_get_session_by_id", return_value=session), \
             patch.object(backend, "_get_campaigns", return_value=[]), \
             patch.object(backend, "get_pref", return_value="large-v2"), \
             patch.object(api, "start_job", return_value={"ok": True}) as mock_start:
            api.retry_transcription("sess-001", model="small")

        # model is the 2nd positional arg
        model = mock_start.call_args[0][1]
        assert model == "small"

    def test_uses_explicit_language(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path)
        with patch.object(backend, "_get_session_by_id", return_value=session), \
             patch.object(backend, "_get_campaigns", return_value=[]), \
             patch.object(backend, "get_pref", return_value="large-v2"), \
             patch.object(api, "start_job", return_value={"ok": True}) as mock_start:
            api.retry_transcription("sess-001", language="fr")

        # language is the 5th positional arg
        language = mock_start.call_args[0][4]
        assert language == "fr"

    def test_falls_back_to_prefs_when_no_params(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path)

        def mock_get_pref(key, fallback=""):
            if key == "whisperx_model":
                return "medium"
            if key == "whisperx_language":
                return "en"
            return fallback

        with patch.object(backend, "_get_session_by_id", return_value=session), \
             patch.object(backend, "_get_campaigns", return_value=[]), \
             patch.object(backend, "get_pref", side_effect=mock_get_pref), \
             patch.object(api, "start_job", return_value={"ok": True}) as mock_start:
            api.retry_transcription("sess-001")

        model = mock_start.call_args[0][1]
        language = mock_start.call_args[0][4]
        assert model == "medium"
        assert language == "en"


# ---------------------------------------------------------------------------
# retry_transcription — nonexistent session
# ---------------------------------------------------------------------------

class TestRetryTranscriptionNonexistentSession:
    def test_returns_error(self):
        api = _make_api()
        with patch.object(backend, "_get_session_by_id", return_value=None):
            result = api.retry_transcription("ghost-session-id")

        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_does_not_call_start_job(self):
        api = _make_api()
        with patch.object(backend, "_get_session_by_id", return_value=None), \
             patch.object(api, "start_job") as mock_start:
            api.retry_transcription("ghost-session-id")

        mock_start.assert_not_called()


# ---------------------------------------------------------------------------
# retry_transcription — session with no audio file
# ---------------------------------------------------------------------------

class TestRetryTranscriptionNoAudio:
    def test_missing_audio_path_returns_error(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path, audio=False)
        with patch.object(backend, "_get_session_by_id", return_value=session):
            result = api.retry_transcription("sess-001")

        assert result["ok"] is False
        assert "audio" in result["error"].lower()

    def test_nonexistent_audio_file_returns_error(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path, audio=False)
        session["audio_path"] = str(tmp_path / "deleted_recording.m4a")
        with patch.object(backend, "_get_session_by_id", return_value=session):
            result = api.retry_transcription("sess-001")

        assert result["ok"] is False
        assert "audio" in result["error"].lower()

    def test_does_not_call_start_job(self, tmp_path):
        api = _make_api()
        session = _make_session(tmp_path, audio=False)
        with patch.object(backend, "_get_session_by_id", return_value=session), \
             patch.object(api, "start_job") as mock_start:
            api.retry_transcription("sess-001")

        mock_start.assert_not_called()


# ---------------------------------------------------------------------------
# start_job — emits _notify_stage("transcription", "running") before starting
# ---------------------------------------------------------------------------

class TestStartJobNotifiesTranscriptionRunning:
    def test_notify_stage_called_with_transcription_running(self, tmp_path):
        api = _make_api()
        api._current_session_dir = tmp_path

        events = []
        original_notify = api._notify_stage

        def capturing_notify(stage, status, data=None):
            events.append((stage, status))
            original_notify(stage, status, data)

        api._notify_stage = capturing_notify

        with patch.object(backend, "get_hf_token", return_value="hf_fake_token"), \
             patch.object(backend, "TranscriptionJob") as MockJob:
            mock_job = MagicMock()
            mock_job.is_running.return_value = False
            MockJob.return_value = mock_job
            api._job = None

            api.start_job(
                str(tmp_path / "audio.m4a"), "large-v2", 3,
                ["DM", "Thorin", "Elara"], "auto",
            )

        assert ("transcription", "running") in events

    def test_notify_running_fires_before_job_start(self, tmp_path):
        api = _make_api()
        api._current_session_dir = tmp_path

        order = []

        original_notify = api._notify_stage

        def tracking_notify(stage, status, data=None):
            if stage == "transcription" and status == "running":
                order.append("notify_running")
            original_notify(stage, status, data)

        api._notify_stage = tracking_notify

        with patch.object(backend, "get_hf_token", return_value="hf_fake_token"), \
             patch.object(backend, "TranscriptionJob") as MockJob:
            mock_job = MagicMock()
            mock_job.is_running.return_value = False

            def track_start():
                order.append("job_started")

            mock_job.start = track_start
            MockJob.return_value = mock_job
            api._job = None

            api.start_job(
                str(tmp_path / "audio.m4a"), "large-v2", 3,
                ["DM", "Thorin", "Elara"], "auto",
            )

        assert "notify_running" in order
        assert "job_started" in order
        assert order.index("notify_running") < order.index("job_started")
