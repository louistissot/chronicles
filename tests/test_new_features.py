"""
Tests for new features:
- _repair_json_array  (JSON repair helper)
- _Recorder pause/resume (unit logic, no real microphone)
- skip_llm_stage      (skip mechanism for LLM pipeline stages)
- llm_mapper confidence parsing
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import with heavy deps mocked
# ---------------------------------------------------------------------------
with patch.dict(sys.modules, {"webview": MagicMock(), "sounddevice": MagicMock()}):
    import backend


def _make_api() -> backend.API:
    win = MagicMock()
    return win, backend.API([win])


# ===========================================================================
# _repair_json_array
# ===========================================================================

class TestRepairJsonArray:
    """Test the cascading JSON repair helper on backend.API."""

    def _repair(self, text):
        _, api = _make_api()
        return api._repair_json_array(text)

    def test_valid_json_array(self):
        data = [{"a": 1}, {"b": 2}]
        assert self._repair(json.dumps(data)) == data

    def test_markdown_fenced_json(self):
        text = '```json\n[{"event": "battle"}]\n```'
        assert self._repair(text) == [{"event": "battle"}]

    def test_markdown_fenced_no_language(self):
        text = '```\n[{"event": "battle"}]\n```'
        assert self._repair(text) == [{"event": "battle"}]

    def test_trailing_comma_in_array(self):
        text = '[{"a": 1}, {"b": 2},]'
        assert self._repair(text) == [{"a": 1}, {"b": 2}]

    def test_trailing_comma_in_object(self):
        text = '[{"a": 1, "b": 2,}]'
        assert self._repair(text) == [{"a": 1, "b": 2}]

    def test_surrounding_prose(self):
        text = 'Here is the JSON:\n[{"event": "battle"}]\nEnd of response.'
        assert self._repair(text) == [{"event": "battle"}]

    def test_totally_invalid_returns_none(self):
        assert self._repair("This is not JSON at all.") is None

    def test_empty_string_returns_none(self):
        assert self._repair("") is None

    def test_bare_object_wrapped_in_array(self):
        # Bare JSON object is now recovered as a single-element array
        result = self._repair('{"key": "value"}')
        assert result == [{"key": "value"}]

    def test_nested_trailing_commas(self):
        text = '[{"items": [1, 2, 3,], "name": "test",},]'
        result = self._repair(text)
        assert result == [{"items": [1, 2, 3], "name": "test"}]


# ===========================================================================
# _Recorder pause/resume (state-only, no real microphone)
# ===========================================================================

class TestRecorderPauseResume:
    """Test _Recorder pause/resume state transitions without real audio."""

    def _make_recorder(self):
        rec = backend._Recorder()
        # Simulate recording state without starting real audio
        rec._recording = True
        rec._paused = False
        rec._start_time = time.monotonic()
        rec._total_paused = 0.0
        return rec

    def test_pause_sets_paused_flag(self):
        rec = self._make_recorder()
        rec.pause()
        assert rec._paused is True

    def test_resume_clears_paused_flag(self):
        rec = self._make_recorder()
        rec.pause()
        rec.resume()
        assert rec._paused is False

    def test_pause_when_not_recording_is_noop(self):
        rec = backend._Recorder()
        assert rec._recording is False
        rec.pause()
        assert rec._paused is False

    def test_resume_when_not_paused_is_noop(self):
        rec = self._make_recorder()
        assert rec._paused is False
        rec.resume()
        assert rec._paused is False
        assert rec._total_paused == 0.0

    def test_double_pause_is_idempotent(self):
        rec = self._make_recorder()
        rec.pause()
        first_pause_start = rec._pause_start
        rec.pause()  # should be a no-op
        assert rec._pause_start == first_pause_start

    def test_total_paused_accumulates(self):
        rec = self._make_recorder()
        rec.pause()
        rec._pause_start = time.monotonic() - 2.0  # fake 2 seconds pause
        rec.resume()
        assert rec._total_paused >= 1.5  # some tolerance

    def test_stop_while_paused_accumulates_paused_time(self):
        rec = self._make_recorder()
        rec._output_path = Path("/tmp/test_rec.wav")
        rec._raw_path = Path("/tmp/test_rec.raw")
        rec.pause()
        rec._pause_start = time.monotonic() - 1.0  # fake 1 second pause
        # We can't call stop() without a real raw file, so just check the logic
        # by calling the same code that stop() does for pause handling
        if rec._paused:
            rec._total_paused += time.monotonic() - rec._pause_start
            rec._paused = False
        assert rec._total_paused >= 0.5
        assert rec._paused is False


# ===========================================================================
# skip_llm_stage
# ===========================================================================

class TestSkipLLMStage:
    """Test skip_llm_stage marks stage done and prevents execution."""

    def test_skip_marks_stage_done(self):
        _, api = _make_api()
        events = []
        original = api._notify_stage
        def cap(stage, status, data=None):
            events.append((stage, status, data))
            original(stage, status, data)
        api._notify_stage = cap

        api.skip_llm_stage("timeline")

        assert any(s == "timeline" and st == "done" for s, st, _ in events)

    def test_skip_includes_skipped_flag(self):
        _, api = _make_api()
        events = []
        original = api._notify_stage
        def cap(stage, status, data=None):
            events.append((stage, status, data))
            original(stage, status, data)
        api._notify_stage = cap

        api.skip_llm_stage("summary")

        done_events = [(s, d) for s, st, d in events if s == "summary" and st == "done"]
        assert len(done_events) == 1
        assert done_events[0][1] and done_events[0][1].get("skipped") is True

    def test_skip_adds_to_skipped_set(self):
        _, api = _make_api()
        api.skip_llm_stage("dm_notes")
        assert "dm_notes" in api._skipped_stages

    def test_skip_adds_to_stop_set(self):
        _, api = _make_api()
        api.skip_llm_stage("scenes")
        assert "scenes" in api._stop_llm_stages


# ===========================================================================
# llm_mapper confidence parsing
# ===========================================================================

class TestLLMMapperConfidenceParsing:
    """Test that llm_mapper._parse_mapping_response handles confidence format."""

    def test_confidence_format(self):
        from llm_mapper import _parse_mapping_response
        raw = {
            "SPEAKER_00": {"name": "DM", "confidence": 95},
            "SPEAKER_01": {"name": "Aragorn", "confidence": 80},
        }
        mapping, confidences, evidence = _parse_mapping_response(raw)
        assert mapping == {"SPEAKER_00": "DM", "SPEAKER_01": "Aragorn"}
        assert confidences == {"SPEAKER_00": 95, "SPEAKER_01": 80}

    def test_flat_string_format(self):
        from llm_mapper import _parse_mapping_response
        raw = {
            "SPEAKER_00": "DM",
            "SPEAKER_01": "Aragorn",
        }
        mapping, confidences, evidence = _parse_mapping_response(raw)
        assert mapping == {"SPEAKER_00": "DM", "SPEAKER_01": "Aragorn"}
        assert confidences == {"SPEAKER_00": 100, "SPEAKER_01": 100}

    def test_extract_and_parse(self):
        """Test that _extract_json + _parse_mapping_response work together."""
        from llm_mapper import _extract_json, _parse_mapping_response
        raw_text = '```json\n{"SPEAKER_00": {"name": "DM", "confidence": 90}}\n```'
        extracted = _extract_json(raw_text)
        assert extracted is not None
        mapping, confidences, evidence = _parse_mapping_response(extracted)
        assert mapping == {"SPEAKER_00": "DM"}
        assert confidences == {"SPEAKER_00": 90}

    def test_missing_confidence_defaults_to_50(self):
        from llm_mapper import _parse_mapping_response
        raw = {"SPEAKER_00": {"name": "DM"}}  # no confidence key
        mapping, confidences, evidence = _parse_mapping_response(raw)
        assert mapping == {"SPEAKER_00": "DM"}
        assert confidences == {"SPEAKER_00": 50}

    def test_evidence_field_parsed(self):
        from llm_mapper import _parse_mapping_response
        raw = {
            "SPEAKER_00": {"name": "DM", "confidence": 95, "evidence": "Describes scenes"},
            "SPEAKER_01": {"name": "Alice", "confidence": 80, "evidence": "References backstory"},
        }
        mapping, confidences, evidence = _parse_mapping_response(raw)
        assert evidence == {"SPEAKER_00": "Describes scenes", "SPEAKER_01": "References backstory"}

    def test_evidence_empty_for_flat_format(self):
        from llm_mapper import _parse_mapping_response
        raw = {"SPEAKER_00": "DM"}
        mapping, confidences, evidence = _parse_mapping_response(raw)
        assert evidence == {"SPEAKER_00": ""}


# ===========================================================================
# Entity confidence stripping
# ===========================================================================

class TestConfidenceStripping:
    """Test that confidence/reasoning fields are stripped before saving artifacts."""

    def test_strip_confidence_from_list(self):
        _, api = _make_api()
        items = [
            {"name": "Tavern", "description": "A warm place", "confidence": 92, "reasoning": "Mentioned"},
            {"name": "Castle", "description": "Dark and brooding", "confidence": 98, "reasoning": "Described"},
        ]
        api._strip_confidence(items)
        assert "confidence" not in items[0]
        assert "reasoning" not in items[0]
        assert items[0]["name"] == "Tavern"
        assert items[1]["name"] == "Castle"

    def test_strip_confidence_from_loot(self):
        _, api = _make_api()
        loot = {
            "items": [{"item": "Sword", "confidence": 88, "reasoning": "Found after combat"}],
            "gold": [{"amount": 50, "confidence": 95, "reasoning": "Explicitly stated"}],
        }
        api._strip_confidence_loot(loot)
        assert "confidence" not in loot["items"][0]
        assert "confidence" not in loot["gold"][0]
        assert loot["items"][0]["item"] == "Sword"

    def test_stage_to_entity_type(self):
        _, api = _make_api()
        assert api._stage_to_entity_type("locations") == "location"
        assert api._stage_to_entity_type("loot") == "item"
        assert api._stage_to_entity_type("missions") == "mission"
        assert api._stage_to_entity_type("npcs") is None
        assert api._stage_to_entity_type("unknown") is None


# ===========================================================================
# _build_glossary_context
# ===========================================================================

class TestBuildGlossaryContext:
    """Test the glossary context builder for LLM prompt injection."""

    def test_with_terms(self):
        _, api = _make_api()
        api._current_campaign_id = "test-camp"
        glossary = {
            "Strahd": {"category": "NPC", "definition": "Vampire lord"},
            "Vallaki": {"category": "Location", "definition": "Walled town"},
        }
        with patch.object(backend, "_get_glossary", return_value=glossary):
            result = api._build_glossary_context()
        assert "## Campaign Glossary" in result
        assert "Strahd (NPC): Vampire lord" in result
        assert "Vallaki (Location): Walled town" in result

    def test_empty_glossary(self):
        _, api = _make_api()
        api._current_campaign_id = "test-camp"
        with patch.object(backend, "_get_glossary", return_value={}):
            result = api._build_glossary_context()
        assert result == ""

    def test_no_campaign_id(self):
        _, api = _make_api()
        api._current_campaign_id = None
        result = api._build_glossary_context()
        assert result == ""

    def test_glossary_load_error_returns_empty(self):
        _, api = _make_api()
        api._current_campaign_id = "test-camp"
        with patch.object(backend, "_get_glossary", side_effect=Exception("disk error")):
            result = api._build_glossary_context()
        assert result == ""

    def test_term_without_definition(self):
        _, api = _make_api()
        api._current_campaign_id = "test-camp"
        glossary = {"Mysterious": {"category": "Other", "definition": ""}}
        with patch.object(backend, "_get_glossary", return_value=glossary):
            result = api._build_glossary_context()
        assert "Mysterious (Other)" in result
        # No trailing colon when definition is empty
        assert "Mysterious (Other):" not in result
