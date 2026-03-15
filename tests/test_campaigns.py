"""
Tests for campaigns.py — create, update, delete campaigns and seasons.

Runs entirely in a temp directory so it never touches the real
~/.config/dnd-whisperx/ files.
"""
import json
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_files(tmp_path: Path):
    """Return a combined context manager that redirects both campaigns.json
    and characters.json to files inside tmp_path."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        campaigns_file = tmp_path / "campaigns.json"
        characters_file = tmp_path / "characters.json"
        with patch("campaigns._CAMPAIGNS_FILE", campaigns_file), \
             patch("characters._CHARACTERS_FILE", characters_file):
            yield
    return _ctx()


def _patch_file(tmp_path: Path):
    """Legacy helper — patches both files for backward compat."""
    return _patch_files(tmp_path)


def _is_uuid(value):
    """Check if value looks like a UUID string."""
    import uuid
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# create_campaign
# ---------------------------------------------------------------------------

class TestCreateCampaign:
    def test_creates_campaign_with_season(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            result = campaigns.create_campaign(
                "Test Campaign",
                [{"number": 1, "characters": ["DM", "Elf"]}],
            )
        assert result["name"] == "Test Campaign"
        assert len(result["seasons"]) == 1
        # Characters are now UUIDs (migrated to global registry)
        chars = result["seasons"][0]["characters"]
        assert len(chars) == 2
        assert all(_is_uuid(c) for c in chars)
        assert "id" in result

    def test_persists_to_disk(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            campaigns.create_campaign("Persistent", [{"number": 1, "characters": ["DM"]}])
            loaded = campaigns.get_campaigns()
        assert any(c["name"] == "Persistent" for c in loaded)

    def test_multiple_campaigns_accumulate(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            campaigns.create_campaign("Alpha", [{"number": 1, "characters": ["A"]}])
            campaigns.create_campaign("Beta", [{"number": 1, "characters": ["B"]}])
            all_c = campaigns.get_campaigns()
        assert len(all_c) == 2
        names = {c["name"] for c in all_c}
        assert names == {"Alpha", "Beta"}

    def test_beyond_url_absent_on_new_campaign(self, tmp_path):
        """Newly created campaigns have no beyond_url key."""
        with _patch_file(tmp_path):
            import campaigns
            result = campaigns.create_campaign("No URL", [{"number": 1, "characters": ["DM"]}])
        assert "beyond_url" not in result


# ---------------------------------------------------------------------------
# update_campaign
# ---------------------------------------------------------------------------

class TestUpdateCampaign:
    def test_update_name(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Old Name", [{"number": 1, "characters": ["DM"]}])
            ok = campaigns.update_campaign(c["id"], "New Name", "")
            updated = next(x for x in campaigns.get_campaigns() if x["id"] == c["id"])
        assert ok is True
        assert updated["name"] == "New Name"

    def test_update_beyond_url(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            url = "https://www.dndbeyond.com/campaigns/12345"
            campaigns.update_campaign(c["id"], "Camp", url)
            updated = next(x for x in campaigns.get_campaigns() if x["id"] == c["id"])
        assert updated["beyond_url"] == url

    def test_clear_beyond_url(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            campaigns.update_campaign(c["id"], "Camp", "https://example.com")
            campaigns.update_campaign(c["id"], "Camp", "")
            updated = next(x for x in campaigns.get_campaigns() if x["id"] == c["id"])
        assert updated["beyond_url"] == ""

    def test_update_nonexistent_campaign_returns_false(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            ok = campaigns.update_campaign("nonexistent-id", "X", "")
        assert ok is False

    def test_empty_name_preserves_existing_name(self, tmp_path):
        """Passing empty string for name should NOT overwrite the existing name."""
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Keep Me", [{"number": 1, "characters": ["DM"]}])
            campaigns.update_campaign(c["id"], "", "https://example.com")
            updated = next(x for x in campaigns.get_campaigns() if x["id"] == c["id"])
        assert updated["name"] == "Keep Me"


# ---------------------------------------------------------------------------
# delete_campaign
# ---------------------------------------------------------------------------

class TestDeleteCampaign:
    def test_delete_removes_campaign(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("ToDelete", [{"number": 1, "characters": ["DM"]}])
            ok = campaigns.delete_campaign(c["id"])
            remaining = campaigns.get_campaigns()
        assert ok is True
        assert all(x["id"] != c["id"] for x in remaining)

    def test_delete_nonexistent_returns_false(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            ok = campaigns.delete_campaign("does-not-exist")
        assert ok is False

    def test_delete_does_not_affect_other_campaigns(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c1 = campaigns.create_campaign("A", [{"number": 1, "characters": ["DM"]}])
            c2 = campaigns.create_campaign("B", [{"number": 1, "characters": ["DM"]}])
            campaigns.delete_campaign(c1["id"])
            remaining = campaigns.get_campaigns()
        assert len(remaining) == 1
        assert remaining[0]["id"] == c2["id"]


# ---------------------------------------------------------------------------
# add_season / update_season
# ---------------------------------------------------------------------------

class TestSeasons:
    def test_add_season(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            season = campaigns.add_season(c["id"], 2, ["DM2", "Wizard"])
            updated = next(x for x in campaigns.get_campaigns() if x["id"] == c["id"])
        assert season is not None
        assert season["number"] == 2
        assert len(updated["seasons"]) == 2

    def test_add_season_nonexistent_campaign_returns_none(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            result = campaigns.add_season("ghost-id", 1, ["DM"])
        assert result is None

    def test_update_season_characters(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM", "Rogue"]}])
            s_id = c["seasons"][0]["id"]
            ok = campaigns.update_season(c["id"], s_id, ["DM", "Rogue", "Paladin"])
            updated = next(x for x in campaigns.get_campaigns() if x["id"] == c["id"])
        assert ok is True
        # Characters are now UUIDs
        chars = updated["seasons"][0]["characters"]
        assert len(chars) == 3
        assert all(_is_uuid(c) for c in chars)

    def test_update_season_nonexistent_returns_false(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            ok = campaigns.update_season(c["id"], "ghost-season-id", ["X"])
        assert ok is False


# ---------------------------------------------------------------------------
# JSON file integrity
# ---------------------------------------------------------------------------

class TestFileIntegrity:
    def test_campaigns_file_is_valid_json(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            raw = (tmp_path / "campaigns.json").read_text()
        data = json.loads(raw)
        assert "campaigns" in data

    def test_corrupted_file_returns_empty(self, tmp_path):
        bad_file = tmp_path / "campaigns.json"
        bad_file.write_text("NOT JSON {{{")
        with _patch_file(tmp_path):
            import campaigns
            result = campaigns.get_campaigns()
        assert result == []


# ---------------------------------------------------------------------------
# Character migration (old string/dict → global character IDs)
# ---------------------------------------------------------------------------

class TestCharacterMigration:
    def test_migrate_old_string_format_on_load(self, tmp_path):
        """Old campaigns.json with string characters auto-migrates to UUID refs."""
        old_data = {
            "campaigns": [{
                "id": "test-id",
                "name": "Old Campaign",
                "seasons": [{
                    "id": "season-id",
                    "number": 1,
                    "characters": ["DM", "Aragorn", "Gandalf"],
                }],
            }],
        }
        target = tmp_path / "campaigns.json"
        target.write_text(json.dumps(old_data))
        with _patch_file(tmp_path):
            import campaigns
            loaded = campaigns.get_campaigns()
            chars = loaded[0]["seasons"][0]["characters"]
            # Should now be UUIDs
            assert len(chars) == 3
            assert all(_is_uuid(c) for c in chars)
            # Names should resolve correctly
            names = campaigns.character_names(chars)
            assert set(names) == {"DM", "Aragorn", "Gandalf"}

    def test_migrate_preserves_existing_dict_fields(self, tmp_path):
        """Dict characters with race/class get migrated to global chars with those fields."""
        data = {
            "campaigns": [{
                "id": "test-id",
                "name": "Rich Campaign",
                "seasons": [{
                    "id": "season-id",
                    "number": 1,
                    "characters": [
                        {"name": "Aragorn", "race": "Human", "class_name": "Ranger", "portrait": "/img.png"},
                    ],
                }],
            }],
        }
        target = tmp_path / "campaigns.json"
        target.write_text(json.dumps(data))
        with _patch_file(tmp_path):
            import campaigns
            import characters
            loaded = campaigns.get_campaigns()
        chars = loaded[0]["seasons"][0]["characters"]
        assert len(chars) == 1
        assert _is_uuid(chars[0])
        # Verify global character has the right fields
        with _patch_file(tmp_path):
            char = characters.get_character(chars[0])
        assert char is not None
        assert char["name"] == "Aragorn"
        assert char["race"] == "Human"
        assert char["class_name"] == "Ranger"

    def test_character_names_helper(self, tmp_path):
        """character_names() extracts names from mixed list."""
        import campaigns
        mixed = ["DM", {"name": "Aragorn", "race": "Human", "class_name": "Ranger", "portrait": ""}]
        assert campaigns.character_names(mixed) == ["DM", "Aragorn"]

    def test_character_names_filters_empty(self, tmp_path):
        """character_names() filters out empty names."""
        import campaigns
        assert campaigns.character_names(["", {"name": "", "race": "Elf", "class_name": "", "portrait": ""}]) == []

    def test_create_campaign_with_dict_characters(self, tmp_path):
        """create_campaign accepts old dict format and migrates to UUIDs."""
        with _patch_file(tmp_path):
            import campaigns
            import characters
            result = campaigns.create_campaign("New", [{
                "number": 1,
                "characters": [
                    {"name": "DM", "race": "", "class_name": "", "portrait": ""},
                    {"name": "Elf", "race": "Wood Elf", "class_name": "Ranger", "portrait": "/p.png"},
                ],
            }])
            chars = result["seasons"][0]["characters"]
            assert len(chars) == 2
            assert all(_is_uuid(c) for c in chars)
            # Verify names resolve
            names = campaigns.character_names(chars)
            assert set(names) == {"DM", "Elf"}


# ---------------------------------------------------------------------------
# get_campaigns_for_character
# ---------------------------------------------------------------------------

class TestGetCampaignsForCharacter:
    def test_returns_matching_campaigns(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            result = campaigns.create_campaign(
                "Adventure", [{"number": 1, "characters": ["Hero"]}],
            )
            char_id = result["seasons"][0]["characters"][0]
            links = campaigns.get_campaigns_for_character(char_id)
            assert len(links) == 1
            assert links[0]["campaign_name"] == "Adventure"
            assert links[0]["season_number"] == 1

    def test_returns_empty_for_unknown(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            links = campaigns.get_campaigns_for_character("nonexistent-id")
            assert links == []

    def test_multiple_campaigns(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            import characters
            c = characters.create_character("Shared")
            campaigns.create_campaign("A", [{"number": 1, "characters": [c["id"]]}])
            campaigns.create_campaign("B", [{"number": 2, "characters": [c["id"]]}])
            links = campaigns.get_campaigns_for_character(c["id"])
            assert len(links) == 2
            names = {l["campaign_name"] for l in links}
            assert names == {"A", "B"}


# ---------------------------------------------------------------------------
# Glossary — merge_glossary and smart_merge_glossary
# ---------------------------------------------------------------------------

class TestGlossary:
    def test_merge_glossary_adds_new_terms(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            terms = {"Strahd": {"category": "NPC", "definition": "Vampire lord"}}
            ok = campaigns.merge_glossary(c["id"], terms)
            glossary = campaigns.get_glossary(c["id"])
        assert ok is True
        assert "Strahd" in glossary
        assert glossary["Strahd"]["category"] == "NPC"

    def test_merge_glossary_does_not_overwrite(self, tmp_path):
        """merge_glossary skips terms that already exist (additive only)."""
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            campaigns.merge_glossary(c["id"], {"X": {"category": "NPC", "definition": "Original"}})
            campaigns.merge_glossary(c["id"], {"X": {"category": "NPC", "definition": "Updated"}})
            glossary = campaigns.get_glossary(c["id"])
        assert glossary["X"]["definition"] == "Original"

    def test_smart_merge_adds_new_terms(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            terms = {
                "Vallaki": {"category": "Location", "definition": "Walled town"},
                "Strahd": {"category": "NPC", "definition": "Vampire lord"},
            }
            ok = campaigns.smart_merge_glossary(c["id"], terms)
            glossary = campaigns.get_glossary(c["id"])
        assert ok is True
        assert len(glossary) == 2
        assert glossary["Vallaki"]["definition"] == "Walled town"

    def test_smart_merge_updates_existing(self, tmp_path):
        """smart_merge_glossary overwrites existing terms with new definitions."""
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            campaigns.merge_glossary(c["id"], {"X": {"category": "NPC", "definition": "Old"}})
            campaigns.smart_merge_glossary(c["id"], {"X": {"category": "NPC", "definition": "Enriched"}})
            glossary = campaigns.get_glossary(c["id"])
        assert glossary["X"]["definition"] == "Enriched"

    def test_smart_merge_mixed_new_and_updated(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            campaigns.merge_glossary(c["id"], {"Existing": {"category": "NPC", "definition": "Old def"}})
            campaigns.smart_merge_glossary(c["id"], {
                "Existing": {"category": "NPC", "definition": "Better def"},
                "Brand New": {"category": "Location", "definition": "A new place"},
            })
            glossary = campaigns.get_glossary(c["id"])
        assert len(glossary) == 2
        assert glossary["Existing"]["definition"] == "Better def"
        assert glossary["Brand New"]["category"] == "Location"

    def test_smart_merge_nonexistent_campaign(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            ok = campaigns.smart_merge_glossary("ghost-id", {"X": {"category": "NPC", "definition": "Y"}})
        assert ok is False

    def test_smart_merge_empty_new_terms(self, tmp_path):
        with _patch_file(tmp_path):
            import campaigns
            c = campaigns.create_campaign("Camp", [{"number": 1, "characters": ["DM"]}])
            campaigns.merge_glossary(c["id"], {"Existing": {"category": "NPC", "definition": "Stays"}})
            ok = campaigns.smart_merge_glossary(c["id"], {})
            glossary = campaigns.get_glossary(c["id"])
        assert ok is True
        assert len(glossary) == 1
        assert glossary["Existing"]["definition"] == "Stays"
