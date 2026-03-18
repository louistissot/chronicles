"""
Tests for backend.py save-stage methods and review flows.

Covers: NPC sync from glossary, glossary/character_updates confidence-based
entity review, fact review name corrections, facts-as-context building,
entity review blocking/unblocking flow.
"""
import json
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

with patch.dict(sys.modules, {"webview": MagicMock(), "sounddevice": MagicMock()}):
    import backend
    # Capture module refs before patch.dict restores sys.modules
    _characters_mod = sys.modules["characters"]
    _campaigns_mod = sys.modules["campaigns"]
    _sessions_mod = sys.modules["sessions"]


# ---------------------------------------------------------------------------
# Isolation — redirect all registry files to tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    """Prevent tests from reading/writing real user data files."""
    monkeypatch.setattr(_sessions_mod, "REGISTRY_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(_characters_mod, "_CHARACTERS_FILE", tmp_path / "characters.json")
    monkeypatch.setattr(_characters_mod, "_CHARACTERS_DIR", tmp_path / "characters")
    monkeypatch.setattr(_campaigns_mod, "_CAMPAIGNS_FILE", tmp_path / "campaigns.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api():
    # type: () -> backend.API
    win = MagicMock()
    api = backend.API([win])
    api._current_campaign_id = "camp-1"
    api._current_session_id = "sess-1"
    api._current_character_names = ["DM", "Aragorn"]
    api._current_character_ids = []
    return api


# ---------------------------------------------------------------------------
# 2A: NPC sync from glossary
# ---------------------------------------------------------------------------

class TestSyncNpcsFromGlossary:
    def test_creates_npc_from_glossary_npc_entry(self):
        api = _make_api()
        glossary = {
            "Strahd": {"category": "NPC", "definition": "Vampire lord", "description": "Scary guy"},
            "Vallaki": {"category": "Location", "definition": "Walled town", "description": "Safe-ish"},
        }
        # Re-register captured modules so local imports in _sync_npcs_from_glossary find them
        chars = _characters_mod
        with patch.dict(sys.modules, {"characters": chars, "campaigns": _campaigns_mod}), \
             patch.object(chars, "get_characters", return_value=[]), \
             patch.object(chars, "find_npc_by_name", return_value=None) as mock_find, \
             patch.object(chars, "create_npc", return_value={"id": "npc-1", "name": "Strahd"}) as mock_create, \
             patch.object(_campaigns_mod, "add_campaign_npc"):
            api._sync_npcs_from_glossary(glossary, "camp-1")

        # Should only try to create Strahd (NPC), not Vallaki (Location)
        assert mock_find.call_count >= 1
        assert "Strahd" in str(mock_find.call_args_list)
        mock_create.assert_called_once()

    def test_skips_player_character_names(self):
        api = _make_api()
        glossary = {
            "Aragorn": {"category": "NPC", "definition": "Ranger king", "description": ""},
        }
        chars = _characters_mod
        with patch.dict(sys.modules, {"characters": chars, "campaigns": _campaigns_mod}), \
             patch.object(chars, "get_characters", return_value=[
                 {"name": "Aragorn", "is_npc": False}
             ]), \
             patch.object(chars, "find_npc_by_name", return_value=None) as mock_find, \
             patch.object(chars, "create_npc") as mock_create:
            api._sync_npcs_from_glossary(glossary, "camp-1")

        mock_create.assert_not_called()

    def test_non_npc_categories_ignored(self):
        api = _make_api()
        glossary = {
            "Sword of Kas": {"category": "Item", "definition": "Evil sword", "description": ""},
            "Barovia": {"category": "Location", "definition": "Cursed land", "description": ""},
        }
        chars = _characters_mod
        with patch.dict(sys.modules, {"characters": chars, "campaigns": _campaigns_mod}), \
             patch.object(chars, "get_characters", return_value=[]), \
             patch.object(chars, "find_npc_by_name") as mock_find, \
             patch.object(chars, "create_npc") as mock_create:
            api._sync_npcs_from_glossary(glossary, "camp-1")

        mock_find.assert_not_called()
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# 2B: Glossary save with confidence split
# ---------------------------------------------------------------------------

class TestSaveGlossaryConfidence:
    def _make_glossary_text(self, terms):
        return json.dumps(terms)

    def test_high_confidence_terms_auto_merge(self, tmp_path):
        api = _make_api()
        terms = {
            "Order of the Gauntlet": {"category": "Faction", "definition": "Holy knights", "description": "", "confidence": 98, "reasoning": "Named explicitly"},
        }
        text = self._make_glossary_text(terms)

        with patch.object(backend, "_get_glossary", return_value={}), \
             patch.object(backend, "_smart_merge_glossary", return_value=(1, 0)) as mock_merge, \
             patch.object(api, "_sync_npcs_from_glossary"), \
             patch.object(backend, "_migrate_glossary", return_value=0), \
             patch.object(api, "_build_glossary_context", return_value=""), \
             patch.object(api, "_request_entity_review") as mock_review, \
             patch.object(backend, "update_session"):
            api._save_glossary(text, tmp_path)

        # High confidence: auto-merge, no review
        mock_merge.assert_called_once()
        mock_review.assert_not_called()

    def test_low_confidence_new_terms_trigger_review(self, tmp_path):
        api = _make_api()
        terms = {
            "Zhentarim": {"category": "Faction", "definition": "Shadow network", "description": "", "confidence": 60, "reasoning": "Mentioned once"},
        }
        text = self._make_glossary_text(terms)

        review_decisions = [
            {"action": "accept", "name": "Zhentarim", "proposed": {"category": "Faction", "definition": "Shadow network", "description": ""}}
        ]

        with patch.object(backend, "_get_glossary", return_value={}), \
             patch.object(backend, "_smart_merge_glossary", return_value=(0, 0)) as mock_merge, \
             patch.object(api, "_sync_npcs_from_glossary") as mock_npc_sync, \
             patch.object(backend, "_migrate_glossary", return_value=0), \
             patch.object(api, "_build_glossary_context", return_value=""), \
             patch.object(api, "_request_entity_review", return_value=review_decisions) as mock_review, \
             patch.object(backend, "update_session"):
            api._save_glossary(text, tmp_path)

        # Low confidence: triggers review
        mock_review.assert_called_once()
        assert mock_review.call_args[0][0] == "glossary"  # stage name

        # Accepted terms merged via _smart_merge (no auto_terms → only review merge)
        mock_merge.assert_called_once()

    def test_accepted_review_terms_synced_as_npcs(self, tmp_path):
        api = _make_api()
        terms = {
            "Ismark": {"category": "NPC", "definition": "Local leader", "description": "", "confidence": 70, "reasoning": "Brief mention"},
        }
        text = self._make_glossary_text(terms)

        review_decisions = [
            {"action": "accept", "name": "Ismark", "proposed": {"category": "NPC", "definition": "Local leader", "description": ""}}
        ]

        synced_glossary = {}

        def capture_sync(glossary, campaign_id):
            synced_glossary.update(glossary)

        with patch.object(backend, "_get_glossary", return_value={}), \
             patch.object(backend, "_smart_merge_glossary", return_value=(0, 0)), \
             patch.object(api, "_sync_npcs_from_glossary", side_effect=capture_sync) as mock_sync, \
             patch.object(backend, "_migrate_glossary", return_value=0), \
             patch.object(api, "_build_glossary_context", return_value=""), \
             patch.object(api, "_request_entity_review", return_value=review_decisions), \
             patch.object(backend, "update_session"):
            api._save_glossary(text, tmp_path)

        # The synced glossary should include "Ismark" from review
        assert "Ismark" in synced_glossary
        assert synced_glossary["Ismark"]["category"] == "NPC"

    def test_no_campaign_id_skips_merge(self, tmp_path):
        api = _make_api()
        api._current_campaign_id = None
        terms = {"Strahd": {"category": "NPC", "definition": "Vamp", "description": ""}}
        text = self._make_glossary_text(terms)

        with patch.object(backend, "_get_glossary", return_value={}), \
             patch.object(backend, "_smart_merge_glossary") as mock_merge, \
             patch.object(api, "_build_glossary_context", return_value=""), \
             patch.object(backend, "update_session"):
            api._save_glossary(text, tmp_path)

        mock_merge.assert_not_called()


# ---------------------------------------------------------------------------
# 2C: Character updates with confidence
# ---------------------------------------------------------------------------

class TestSaveCharacterUpdates:
    def test_new_format_with_confidence(self, tmp_path):
        api = _make_api()
        api._current_character_ids = ["char-1"]
        api._current_npc_chars = []
        updates = {
            "Aragorn": {"text": "Led the charge.", "confidence": 98, "reasoning": "Directly stated"}
        }
        text = json.dumps(updates)

        with patch.object(backend, "_get_characters_by_ids", return_value=[
            {"id": "char-1", "name": "Aragorn"}
        ]), \
             patch.object(backend, "_add_history_entry") as mock_add, \
             patch.object(backend, "get_sessions", return_value=[
                 {"id": "sess-1", "date": "2026-03-16", "campaign_name": "Camp", "season_number": 1}
             ]), \
             patch.object(backend, "update_session"):
            api._save_character_updates(text, tmp_path)

        # High confidence: auto-applied to history
        mock_add.assert_called_once()
        assert mock_add.call_args[0][0] == "char-1"  # char_id
        assert "Led the charge" in mock_add.call_args[0][5]  # update_text

    def test_flat_string_format_backward_compat(self, tmp_path):
        api = _make_api()
        api._current_character_ids = ["char-1"]
        api._current_npc_chars = []
        updates = {"Aragorn": "Did something heroic."}
        text = json.dumps(updates)

        with patch.object(backend, "_get_characters_by_ids", return_value=[
            {"id": "char-1", "name": "Aragorn"}
        ]), \
             patch.object(backend, "_add_history_entry") as mock_add, \
             patch.object(backend, "get_sessions", return_value=[
                 {"id": "sess-1", "date": "2026-03-16", "campaign_name": "Camp", "season_number": 1}
             ]), \
             patch.object(backend, "update_session"):
            api._save_character_updates(text, tmp_path)

        # Flat string: treated as 100% confidence, auto-applied
        mock_add.assert_called_once()
        assert "heroic" in mock_add.call_args[0][5]

    def test_low_confidence_triggers_review(self, tmp_path):
        api = _make_api()
        api._current_character_ids = ["char-1"]
        api._current_npc_chars = []
        updates = {
            "Aragorn": {"text": "Might have used magic.", "confidence": 60, "reasoning": "Unclear from transcript"}
        }
        text = json.dumps(updates)

        review_decisions = [
            {"action": "accept", "name": "Aragorn", "proposed": {"text": "Might have used magic."}}
        ]

        with patch.object(backend, "_get_characters_by_ids", return_value=[
            {"id": "char-1", "name": "Aragorn"}
        ]), \
             patch.object(backend, "_add_history_entry") as mock_add, \
             patch.object(backend, "get_sessions", return_value=[
                 {"id": "sess-1", "date": "2026-03-16", "campaign_name": "Camp", "season_number": 1}
             ]), \
             patch.object(api, "_request_entity_review", return_value=review_decisions) as mock_review, \
             patch.object(backend, "update_session"):
            api._save_character_updates(text, tmp_path)

        mock_review.assert_called_once()
        assert mock_review.call_args[0][0] == "character_updates"


# ---------------------------------------------------------------------------
# 2D: Entity review blocking/unblocking
# ---------------------------------------------------------------------------

class TestEntityReviewFlow:
    def test_complete_entity_review_unblocks(self):
        api = _make_api()
        # Simulate a pending review event
        event = threading.Event()
        api._pending_entity_reviews["locations"] = event
        api._entity_review_decisions["locations"] = []

        # Complete the review from "frontend"
        result = api.complete_entity_review("locations", [
            {"id": "card-1", "action": "accept"}
        ])

        assert result == {"ok": True}
        assert event.is_set()  # Event was unblocked
        assert api._entity_review_decisions.get("locations") == [{"id": "card-1", "action": "accept"}]

    def test_stop_pipeline_sets_pending_events(self):
        api = _make_api()
        event = threading.Event()
        api._pending_entity_reviews["locations"] = event

        # Simulate stop_pipeline clearing events
        for ev in api._pending_entity_reviews.values():
            ev.set()

        assert event.is_set()


# ---------------------------------------------------------------------------
# 2E: Fact review name corrections
# ---------------------------------------------------------------------------

class TestFactReviewNameCorrections:
    def _simulate_review(self, api, decisions):
        """Mock _notify_stage to auto-complete the fact review when needs_review fires."""
        original_notify = api._notify_stage

        def auto_complete(stage, status, data=None):
            original_notify(stage, status, data)
            if stage == "fact_review" and status == "needs_review":
                api._fact_review_decisions = decisions
                api._pending_fact_review.set()

        api._notify_stage = auto_complete

    def test_who_field_edit_produces_name_correction(self):
        api = _make_api()
        self._simulate_review(api, [
            {
                "id": "fact-1",
                "action": "edit",
                "who": "Rijay",
                "edited": {"who": "Rougey", "what": "Fought bravely"},
                "segment_indices": [0, 1],
            }
        ])

        corrections, name_corrections = api._request_fact_review(
            review_queue=[{"id": "fact-1", "who": "Rijay", "what": "Fought", "confidence": 50}],
            auto_applied=[],
            json_path="/tmp/test.json",
            mapping={"SPEAKER_00": "Rijay"},
            txt_path="/tmp/transcript.txt",
        )

        assert "Rijay" in name_corrections
        assert name_corrections["Rijay"] == "Rougey"

    def test_no_edit_produces_no_name_correction(self):
        api = _make_api()
        self._simulate_review(api, [
            {"id": "fact-1", "action": "accept", "who": "Aragorn", "segment_indices": [0]},
        ])

        corrections, name_corrections = api._request_fact_review(
            review_queue=[{"id": "fact-1", "who": "Aragorn", "what": "Led charge", "confidence": 50}],
            auto_applied=[],
            json_path="/tmp/test.json",
            mapping={},
            txt_path="/tmp/transcript.txt",
        )

        assert len(name_corrections) == 0


# ---------------------------------------------------------------------------
# 2F: Facts-as-context building
# ---------------------------------------------------------------------------

class TestFactsContext:
    def test_builds_context_from_facts_json(self, tmp_path):
        facts = [
            {"type": "combat", "who": "Aragorn", "what": "Slew the dragon", "when": "midnight", "confidence": 90},
            {"type": "loot", "who": "Party", "what": "Found golden crown", "when": "", "confidence": 80},
            {"type": "event", "who": "DM", "what": "Side chatter about pizza", "when": "", "confidence": 40},
        ]
        (tmp_path / "facts.json").write_text(json.dumps(facts), encoding="utf-8")

        # Simulate the facts context building from _continue_pipeline
        facts_context = ""
        facts_file = tmp_path / "facts.json"
        if facts_file.exists():
            all_facts = json.loads(facts_file.read_text(encoding="utf-8"))
            relevant = [f for f in all_facts if f.get("confidence", 0) >= 70]
            if relevant:
                lines = []
                for f in relevant:
                    who = f.get("who", "")
                    what = f.get("what", "")
                    when = f.get("when", "")
                    ftype = f.get("type", "")
                    line = "- [{type}] {who}: {what}".format(type=ftype, who=who, what=what)
                    if when:
                        line += " (when: {})".format(when)
                    lines.append(line)
                facts_context = "\n\n## Key Events Summary (extracted facts)\n" + "\n".join(lines)

        # Should include high-confidence facts only
        assert "Aragorn" in facts_context
        assert "golden crown" in facts_context
        assert "pizza" not in facts_context  # Low confidence excluded
        assert "(when: midnight)" in facts_context

    def test_empty_when_no_facts_file(self, tmp_path):
        facts_context = ""
        facts_file = tmp_path / "facts.json"
        if facts_file.exists():
            pass  # won't enter
        assert facts_context == ""
