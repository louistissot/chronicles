"""
Tests for characters.py — global character registry CRUD, history, and migration.

Runs in a temp directory via the characters_file fixture so it never touches
the real ~/.config/dnd-whisperx/ files.
"""
import json


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestCreateCharacter:
    def test_returns_dict_with_expected_fields(self, characters_file):
        import characters
        c = characters.create_character("DM")
        assert isinstance(c, dict)
        assert c["name"] == "DM"
        assert "id" in c
        assert c["race"] == ""
        assert c["class_name"] == ""
        assert c["history"] == []
        assert c["history_summary"] == ""

    def test_persists_to_disk(self, characters_file):
        import characters
        characters.create_character("Gandalf", race="Maia", class_name="Wizard")
        assert characters_file.exists()
        data = json.loads(characters_file.read_text())
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "Gandalf"

    def test_multiple_creates_accumulate(self, characters_file):
        import characters
        characters.create_character("A")
        characters.create_character("B")
        characters.create_character("C")
        assert len(characters.get_characters()) == 3

    def test_all_fields_stored(self, characters_file):
        import characters
        c = characters.create_character(
            name="Aragorn",
            race="Human",
            class_name="Ranger",
            subclass="Hunter",
            level=5,
            specialty="Tracking",
            beyond_url="https://dndbeyond.com/characters/123",
            portrait_path="/img/aragorn.png",
        )
        assert c["race"] == "Human"
        assert c["class_name"] == "Ranger"
        assert c["subclass"] == "Hunter"
        assert c["level"] == 5
        assert c["specialty"] == "Tracking"
        assert c["beyond_url"] == "https://dndbeyond.com/characters/123"
        assert c["portrait_path"] == "/img/aragorn.png"


class TestGetCharacter:
    def test_returns_character_by_id(self, characters_file):
        import characters
        created = characters.create_character("Legolas", race="Elf")
        fetched = characters.get_character(created["id"])
        assert fetched is not None
        assert fetched["name"] == "Legolas"
        assert fetched["race"] == "Elf"

    def test_returns_none_for_unknown_id(self, characters_file):
        import characters
        assert characters.get_character("nonexistent-uuid") is None


class TestGetCharactersByIds:
    def test_returns_matching_in_order(self, characters_file):
        import characters
        a = characters.create_character("Alpha")
        b = characters.create_character("Beta")
        c = characters.create_character("Gamma")
        result = characters.get_characters_by_ids([c["id"], a["id"]])
        assert [r["name"] for r in result] == ["Gamma", "Alpha"]

    def test_ignores_unknown_ids(self, characters_file):
        import characters
        a = characters.create_character("Solo")
        result = characters.get_characters_by_ids([a["id"], "unknown-id"])
        assert len(result) == 1
        assert result[0]["name"] == "Solo"


class TestCharacterNamesFromIds:
    def test_resolves_ids_to_names(self, characters_file):
        import characters
        a = characters.create_character("DM")
        b = characters.create_character("Frodo")
        names = characters.character_names_from_ids([a["id"], b["id"]])
        assert names == ["DM", "Frodo"]

    def test_skips_missing_ids(self, characters_file):
        import characters
        a = characters.create_character("Only")
        names = characters.character_names_from_ids([a["id"], "ghost-id"])
        assert names == ["Only"]


class TestUpdateCharacter:
    def test_updates_fields(self, characters_file):
        import characters
        c = characters.create_character("Gimli", race="Dwarf")
        updated = characters.update_character(c["id"], level=8, specialty="Axes")
        assert updated is not None
        assert updated["level"] == 8
        assert updated["specialty"] == "Axes"
        # Original fields preserved
        assert updated["race"] == "Dwarf"

    def test_returns_none_for_unknown(self, characters_file):
        import characters
        assert characters.update_character("bad-id", name="X") is None

    def test_persists_update_to_disk(self, characters_file):
        import characters
        c = characters.create_character("Temp")
        characters.update_character(c["id"], name="Updated")
        reloaded = characters.get_character(c["id"])
        assert reloaded["name"] == "Updated"


class TestDeleteCharacter:
    def test_removes_character(self, characters_file):
        import characters
        c = characters.create_character("ToDelete")
        assert characters.delete_character(c["id"]) is True
        assert characters.get_character(c["id"]) is None

    def test_returns_false_for_unknown(self, characters_file):
        import characters
        assert characters.delete_character("no-such-id") is False

    def test_does_not_affect_others(self, characters_file):
        import characters
        a = characters.create_character("Keep")
        b = characters.create_character("Remove")
        characters.delete_character(b["id"])
        assert len(characters.get_characters()) == 1
        assert characters.get_characters()[0]["name"] == "Keep"


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestAddHistoryEntry:
    def test_appends_entry(self, characters_file):
        import characters
        c = characters.create_character("Hero")
        ok = characters.add_history_entry(
            c["id"], "sess-1", "2026-03-01", "Campaign", 1, "Fought a dragon"
        )
        assert ok is True
        updated = characters.get_character(c["id"])
        assert len(updated["history"]) == 1
        assert updated["history"][0]["auto_text"] == "Fought a dragon"
        assert updated["history"][0]["session_id"] == "sess-1"

    def test_deduplicates_by_session_id(self, characters_file):
        import characters
        c = characters.create_character("Hero")
        characters.add_history_entry(c["id"], "sess-1", "2026-03-01", "C", 1, "V1")
        characters.add_history_entry(c["id"], "sess-1", "2026-03-01", "C", 1, "V2")
        updated = characters.get_character(c["id"])
        assert len(updated["history"]) == 1
        assert updated["history"][0]["auto_text"] == "V2"

    def test_returns_false_for_unknown_char(self, characters_file):
        import characters
        ok = characters.add_history_entry("bad", "s", "d", "c", 1, "t")
        assert ok is False


class TestUpdateHistoryManualText:
    def test_updates_manual_text(self, characters_file):
        import characters
        c = characters.create_character("Hero")
        characters.add_history_entry(c["id"], "sess-1", "2026-03-01", "C", 1, "Auto")
        ok = characters.update_history_manual_text(c["id"], "sess-1", "My notes")
        assert ok is True
        h = characters.get_character(c["id"])["history"][0]
        assert h["manual_text"] == "My notes"

    def test_returns_false_for_unknown(self, characters_file):
        import characters
        assert characters.update_history_manual_text("bad", "s", "t") is False


class TestUpdateHistoryAutoText:
    def test_updates_auto_text(self, characters_file):
        import characters
        c = characters.create_character("Hero")
        characters.add_history_entry(c["id"], "sess-1", "2026-03-01", "C", 1, "Original auto text")
        ok = characters.update_history_auto_text(c["id"], "sess-1", "Corrected auto text")
        assert ok is True
        h = characters.get_character(c["id"])["history"][0]
        assert h["auto_text"] == "Corrected auto text"

    def test_returns_false_for_unknown_char(self, characters_file):
        import characters
        assert characters.update_history_auto_text("bad", "s", "t") is False

    def test_returns_false_for_unknown_session(self, characters_file):
        import characters
        c = characters.create_character("Hero")
        characters.add_history_entry(c["id"], "sess-1", "2026-03-01", "C", 1, "Auto")
        assert characters.update_history_auto_text(c["id"], "sess-999", "t") is False


class TestSetHistorySummary:
    def test_sets_summary(self, characters_file):
        import characters
        c = characters.create_character("Hero")
        ok = characters.set_history_summary(c["id"], "A brave warrior's tale")
        assert ok is True
        assert characters.get_character(c["id"])["history_summary"] == "A brave warrior's tale"

    def test_returns_false_for_unknown(self, characters_file):
        import characters
        assert characters.set_history_summary("bad", "text") is False


# ---------------------------------------------------------------------------
# Beyond data sync
# ---------------------------------------------------------------------------

class TestSetBeyondData:
    def test_stores_beyond_data(self, characters_file):
        import characters
        c = characters.create_character("Raw")
        beyond = {"name": "Aragorn", "race": "Human", "class_name": "Ranger", "level": 10}
        result = characters.set_beyond_data(
            c["id"], beyond, avatar_path="/av.jpg", synced_at="2026-03-13"
        )
        assert result is not None
        assert result["beyond_data"] == beyond
        assert result["beyond_avatar_path"] == "/av.jpg"
        assert result["beyond_last_synced"] == "2026-03-13"

    def test_propagates_top_level_fields(self, characters_file):
        import characters
        c = characters.create_character("Raw", race="Unknown")
        beyond = {"name": "Legolas", "race": "Elf", "class_name": "Fighter", "subclass": "Champion", "level": 5}
        result = characters.set_beyond_data(c["id"], beyond)
        assert result["name"] == "Legolas"
        assert result["race"] == "Elf"
        assert result["class_name"] == "Fighter"
        assert result["subclass"] == "Champion"
        assert result["level"] == 5

    def test_returns_none_for_unknown(self, characters_file):
        import characters
        assert characters.set_beyond_data("bad", {}) is None


# ---------------------------------------------------------------------------
# Migration from campaign characters
# ---------------------------------------------------------------------------

class TestMigrateFromCampaignChars:
    def test_migrates_strings(self, characters_file):
        import characters
        ids = characters.migrate_from_campaign_chars(["DM", "Rogue"])
        assert len(ids) == 2
        # IDs should be valid UUIDs
        import uuid
        for cid in ids:
            uuid.UUID(cid)  # should not raise
        # Characters should exist in registry
        assert characters.get_character(ids[0])["name"] == "DM"
        assert characters.get_character(ids[1])["name"] == "Rogue"

    def test_migrates_dicts(self, characters_file):
        import characters
        ids = characters.migrate_from_campaign_chars([
            {"name": "Elf", "race": "Wood Elf", "class_name": "Ranger", "portrait": ""},
        ])
        assert len(ids) == 1
        c = characters.get_character(ids[0])
        assert c["name"] == "Elf"
        assert c["race"] == "Wood Elf"
        assert c["class_name"] == "Ranger"

    def test_deduplicates_by_name(self, characters_file):
        import characters
        characters.create_character("DM")
        ids = characters.migrate_from_campaign_chars(["DM", "DM"])
        assert len(ids) == 2
        assert ids[0] == ids[1]  # Same character referenced twice
        # Only 1 character in registry (the original + no duplicates)
        assert len(characters.get_characters()) == 1

    def test_skips_empty_names(self, characters_file):
        import characters
        ids = characters.migrate_from_campaign_chars(["", {"name": ""}, "Valid"])
        assert len(ids) == 1
        assert characters.get_character(ids[0])["name"] == "Valid"

    def test_skips_speaker_placeholders(self, characters_file):
        import characters
        ids = characters.migrate_from_campaign_chars(["SPEAKER_00", "SPEAKER_01", "DM"])
        assert len(ids) == 1
        assert characters.get_character(ids[0])["name"] == "DM"
