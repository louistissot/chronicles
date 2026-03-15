"""
Tests for beyond.py — D&D Beyond URL parsing, API response parsing, avatar download.

Network calls are mocked so tests run without internet access.
"""
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# extract_character_id
# ---------------------------------------------------------------------------

class TestExtractCharacterId:
    def test_standard_url(self):
        import beyond
        assert beyond.extract_character_id(
            "https://www.dndbeyond.com/characters/129265475"
        ) == "129265475"

    def test_url_with_builder_suffix(self):
        import beyond
        assert beyond.extract_character_id(
            "https://www.dndbeyond.com/characters/129265475/builder"
        ) == "129265475"

    def test_url_without_www(self):
        import beyond
        assert beyond.extract_character_id(
            "https://dndbeyond.com/characters/99999"
        ) == "99999"

    def test_non_dndbeyond_url_returns_none(self):
        import beyond
        assert beyond.extract_character_id("https://example.com/characters/123") is None

    def test_invalid_url_returns_none(self):
        import beyond
        assert beyond.extract_character_id("not-a-url") is None

    def test_empty_string_returns_none(self):
        import beyond
        assert beyond.extract_character_id("") is None


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

class TestParseClasses:
    def test_single_class(self):
        import beyond
        data = {
            "classes": [{
                "definition": {"name": "Fighter"},
                "level": 5,
                "subclassDefinition": None,
            }]
        }
        name, sub, level = beyond._parse_classes(data)
        assert "Fighter" in name
        assert level == 5

    def test_multiclass(self):
        import beyond
        data = {
            "classes": [
                {"definition": {"name": "Fighter"}, "level": 3, "subclassDefinition": None},
                {"definition": {"name": "Rogue"}, "level": 2, "subclassDefinition": None},
            ]
        }
        name, sub, level = beyond._parse_classes(data)
        assert "Fighter" in name
        assert "Rogue" in name
        assert level == 5

    def test_with_subclass(self):
        import beyond
        data = {
            "classes": [{
                "definition": {"name": "Wizard"},
                "level": 7,
                "subclassDefinition": {"name": "Evocation"},
            }]
        }
        name, sub, level = beyond._parse_classes(data)
        assert "Evocation" in name
        assert sub == "Evocation"

    def test_empty_classes(self):
        import beyond
        name, sub, level = beyond._parse_classes({"classes": []})
        assert name == ""
        assert level == 1


class TestParseStats:
    def test_base_stats(self):
        import beyond
        data = {
            "stats": [
                {"id": 1, "value": 16},  # str
                {"id": 2, "value": 14},  # dex
            ],
            "bonusStats": [],
            "overrideStats": [],
        }
        result = beyond._parse_stats(data)
        assert result["str"] == 16
        assert result["dex"] == 14

    def test_bonus_stats_add(self):
        import beyond
        data = {
            "stats": [{"id": 1, "value": 10}],
            "bonusStats": [{"id": 1, "value": 2}],
            "overrideStats": [],
        }
        result = beyond._parse_stats(data)
        assert result["str"] == 12

    def test_override_stats_replace(self):
        import beyond
        data = {
            "stats": [{"id": 1, "value": 10}],
            "bonusStats": [{"id": 1, "value": 5}],
            "overrideStats": [{"id": 1, "value": 20}],
        }
        result = beyond._parse_stats(data)
        assert result["str"] == 20


class TestParseSpells:
    def test_class_spells(self):
        import beyond
        data = {
            "classSpells": [{
                "spells": [
                    {"definition": {"name": "Fireball"}},
                    {"definition": {"name": "Shield"}},
                ]
            }],
            "spells": {"race": []},
        }
        result = beyond._parse_spells(data)
        assert "Fireball" in result
        assert "Shield" in result

    def test_deduplicates(self):
        import beyond
        data = {
            "classSpells": [{
                "spells": [
                    {"definition": {"name": "Fireball"}},
                    {"definition": {"name": "Fireball"}},
                ]
            }],
            "spells": {"race": []},
        }
        result = beyond._parse_spells(data)
        assert result.count("Fireball") == 1


class TestParseEquipment:
    def test_equipped_items(self):
        import beyond
        data = {
            "inventory": [
                {"definition": {"name": "Longsword", "magic": False}, "equipped": True, "quantity": 1},
                {"definition": {"name": "Shield", "magic": False}, "equipped": False, "quantity": 1},
            ]
        }
        result = beyond._parse_equipment(data)
        assert "Longsword" in result
        assert "Shield" not in result

    def test_magic_items_always_included(self):
        import beyond
        data = {
            "inventory": [
                {"definition": {"name": "Ring of Power", "magic": True}, "equipped": False, "quantity": 1},
            ]
        }
        result = beyond._parse_equipment(data)
        assert "Ring of Power" in result


# ---------------------------------------------------------------------------
# fetch_beyond_character (mocked network)
# ---------------------------------------------------------------------------

class TestFetchBeyondCharacter:
    def _mock_response(self, json_data, status_code=200):
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.status_code = status_code
        resp.raise_for_status = MagicMock()
        return resp

    @patch("beyond.requests.get")
    def test_happy_path(self, mock_get):
        import beyond
        mock_get.return_value = self._mock_response({
            "success": True,
            "data": {
                "name": "Gandalf",
                "race": {"fullName": "Maia", "baseName": "Maia"},
                "classes": [{"definition": {"name": "Wizard"}, "level": 20, "subclassDefinition": None}],
                "stats": [{"id": 4, "value": 20}],
                "bonusStats": [],
                "overrideStats": [],
                "classSpells": [],
                "spells": {"race": []},
                "inventory": [],
                "notes": {"backstory": "A wandering wizard"},
                "traits": {"personalityTraits": "Wise"},
                "baseHitPoints": 150,
                "decorations": {"avatarUrl": "https://img.example.com/gandalf.jpg"},
            },
        })
        result = beyond.fetch_beyond_character("https://dndbeyond.com/characters/123")
        assert result is not None
        assert result["name"] == "Gandalf"
        assert result["race"] == "Maia"
        assert "Wizard" in result["class_name"]
        assert result["backstory"] == "A wandering wizard"
        assert result["hp"] == 150

    @patch("beyond.requests.get")
    def test_bad_url_returns_none(self, mock_get):
        import beyond
        result = beyond.fetch_beyond_character("not-a-valid-url")
        assert result is None
        mock_get.assert_not_called()

    @patch("beyond.requests.get")
    def test_http_error_returns_none(self, mock_get):
        import beyond
        import requests as req
        mock_get.side_effect = req.RequestException("Server error")
        result = beyond.fetch_beyond_character("https://dndbeyond.com/characters/999")
        assert result is None

    @patch("beyond.requests.get")
    def test_success_false_returns_none(self, mock_get):
        import beyond
        mock_get.return_value = self._mock_response({"success": False, "message": "Not found"})
        result = beyond.fetch_beyond_character("https://dndbeyond.com/characters/999")
        assert result is None

    @patch("beyond.requests.get")
    def test_403_raises_value_error(self, mock_get):
        import beyond
        import pytest
        resp = MagicMock()
        resp.status_code = 403
        mock_get.return_value = resp
        with pytest.raises(ValueError, match="private or restricted"):
            beyond.fetch_beyond_character("https://dndbeyond.com/characters/999")


# ---------------------------------------------------------------------------
# download_avatar (mocked network)
# ---------------------------------------------------------------------------

class TestDownloadAvatar:
    @patch("beyond.requests.get")
    def test_downloads_and_saves(self, mock_get, tmp_path):
        import beyond
        mock_get.return_value = MagicMock(
            content=b"FAKE_IMAGE_DATA",
            status_code=200,
        )
        mock_get.return_value.raise_for_status = MagicMock()
        path = str(tmp_path / "avatar.jpg")
        ok = beyond.download_avatar("https://img.example.com/av.jpg", path)
        assert ok is True
        assert (tmp_path / "avatar.jpg").read_bytes() == b"FAKE_IMAGE_DATA"

    def test_empty_url_returns_false(self):
        import beyond
        assert beyond.download_avatar("", "/tmp/nope.jpg") is False

    @patch("beyond.requests.get")
    def test_http_error_returns_false(self, mock_get):
        import beyond
        import requests as req
        mock_get.side_effect = req.RequestException("timeout")
        ok = beyond.download_avatar("https://img.example.com/av.jpg", "/tmp/nope.jpg")
        assert ok is False
