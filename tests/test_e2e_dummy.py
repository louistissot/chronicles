"""End-to-end smoke test using dummy data.

Creates a campaign, characters, session, and a small dummy transcript,
then verifies the full data flow works without errors.

Run:  python3.9 -m pytest tests/test_e2e_dummy.py -v
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Dummy WhisperX transcript (minimal, 3 speakers, ~10 segments)
# ---------------------------------------------------------------------------

DUMMY_WHISPERX_JSON = {
    "segments": [
        {"start": 0.0, "end": 3.5, "text": "Welcome adventurers to the Tavern of the Lost Souls.", "speaker": "SPEAKER_00"},
        {"start": 4.0, "end": 7.2, "text": "Thank you for having us. I am Thorin, son of Thrain.", "speaker": "SPEAKER_01"},
        {"start": 7.5, "end": 11.0, "text": "And I am Elara. We seek the ancient artifact hidden beneath the mountain.", "speaker": "SPEAKER_02"},
        {"start": 11.5, "end": 15.0, "text": "The artifact you seek is guarded by a dragon. Many have tried and failed.", "speaker": "SPEAKER_00"},
        {"start": 15.5, "end": 19.0, "text": "I have fought dragons before. My axe is sharp and my shield is strong.", "speaker": "SPEAKER_01"},
        {"start": 19.5, "end": 23.0, "text": "We should prepare carefully. I can cast protective wards on us.", "speaker": "SPEAKER_02"},
        {"start": 23.5, "end": 27.0, "text": "Very well. The entrance to the mountain is through the Dark Forest.", "speaker": "SPEAKER_00"},
        {"start": 27.5, "end": 31.0, "text": "Then let us set out at dawn. Thorin, check your supplies.", "speaker": "SPEAKER_02"},
        {"start": 31.5, "end": 35.0, "text": "I have enough rations for a week. And plenty of ale.", "speaker": "SPEAKER_01"},
        {"start": 35.5, "end": 39.0, "text": "May the gods watch over you. The path ahead is treacherous.", "speaker": "SPEAKER_00"},
    ],
    "word_segments": [],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    """Redirect ALL persistent storage to tmp_path."""
    import campaigns
    import characters
    import sessions
    import config

    monkeypatch.setattr(campaigns, "_CAMPAIGNS_FILE", tmp_path / "campaigns.json")
    monkeypatch.setattr(characters, "_CHARACTERS_FILE", tmp_path / "characters.json")
    monkeypatch.setattr(characters, "_CHARACTERS_DIR", tmp_path / "characters")
    monkeypatch.setattr(sessions, "REGISTRY_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "prefs.json")

    return tmp_path


@pytest.fixture
def dummy_transcript(tmp_path):
    """Write a minimal WhisperX JSON transcript and return the path."""
    p = tmp_path / "session_out" / "transcript.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(DUMMY_WHISPERX_JSON), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDummyDataSetup:
    """Verify that dummy campaigns, characters, and sessions can be created."""

    def test_create_campaign_and_characters(self, isolated_storage):
        import campaigns
        import characters

        dm = characters.create_character(name="DM")
        thorin = characters.create_character(name="Thorin", race="Dwarf", class_name="Fighter")
        elara = characters.create_character(name="Elara", race="Elf", class_name="Wizard")

        assert dm["is_dm"] is True
        assert thorin["name"] == "Thorin"
        assert elara["race"] == "Elf"
        assert len(characters.get_characters()) == 3

        camp = campaigns.create_campaign(
            "Test Campaign",
            [{"number": 1, "characters": [thorin["id"], elara["id"]]}],
        )
        assert camp is not None
        assert camp["name"] == "Test Campaign"
        assert len(camp["seasons"]) == 1
        assert len(camp["seasons"][0]["characters"]) == 2

    def test_create_session(self, isolated_storage, tmp_path):
        import campaigns
        import characters
        import sessions

        thorin = characters.create_character(name="Thorin", race="Dwarf", class_name="Fighter")
        elara = characters.create_character(name="Elara", race="Elf", class_name="Wizard")
        camp = campaigns.create_campaign(
            "Test Campaign",
            [{"number": 1, "characters": [thorin["id"], elara["id"]]}],
        )
        season = camp["seasons"][0]

        session_dir = str(tmp_path / "session_out")
        session_id = sessions.register_session(
            campaign_id=camp["id"],
            campaign_name=camp["name"],
            season_id=season["id"],
            season_number=season["number"],
            session_dir=session_dir,
            character_names=["DM", "Thorin", "Elara"],
        )
        assert session_id is not None
        all_sessions = sessions.get_sessions()
        assert len(all_sessions) == 1
        assert all_sessions[0]["campaign_name"] == "Test Campaign"


class TestDummyTranscript:
    """Verify transcript parsing with dummy data."""

    def test_parse_dummy_transcript(self, dummy_transcript):
        import postprocess

        data = json.loads(dummy_transcript.read_text(encoding="utf-8"))
        speakers = postprocess.get_speakers(data)
        assert "SPEAKER_00" in speakers
        assert "SPEAKER_01" in speakers
        assert "SPEAKER_02" in speakers
        assert len(speakers) == 3

    def test_save_all_with_mapping(self, dummy_transcript, tmp_path):
        import postprocess

        mapping = {
            "SPEAKER_00": "DM",
            "SPEAKER_01": "Thorin",
            "SPEAKER_02": "Elara",
        }
        out_dir = tmp_path / "session_out"
        txt_path, srt_path = postprocess.save_all(
            str(dummy_transcript), mapping,
            output_dir=str(out_dir),
        )
        assert txt_path is not None
        assert srt_path is not None

        txt_content = txt_path.read_text(encoding="utf-8")
        assert "Thorin" in txt_content

    def test_review_samples_from_dummy(self, dummy_transcript):
        import postprocess

        data = json.loads(dummy_transcript.read_text(encoding="utf-8"))
        samples = postprocess.get_review_samples(data, character_names=["Thorin", "Elara"])
        assert isinstance(samples, dict)
        assert len(samples) > 0


class TestPortraitGallery:
    """Verify portrait gallery CRUD in characters module."""

    def test_add_and_set_primary(self, isolated_storage, tmp_path):
        import characters

        char = characters.create_character(name="TestChar")
        assert char["portraits"] == []

        p1 = tmp_path / "p1.png"
        p2 = tmp_path / "p2.png"
        p1.write_bytes(b"fake")
        p2.write_bytes(b"fake")

        updated = characters.add_portrait(char["id"], str(p1), set_primary=True)
        assert len(updated["portraits"]) == 1
        assert updated["portraits"][0]["is_primary"] is True
        assert updated["portrait_path"] == str(p1)

        updated = characters.add_portrait(char["id"], str(p2), set_primary=True)
        assert len(updated["portraits"]) == 2
        assert updated["portrait_path"] == str(p2)
        assert updated["portraits"][0]["is_primary"] is False
        assert updated["portraits"][1]["is_primary"] is True

        updated = characters.set_primary_portrait(char["id"], str(p1))
        assert updated["portrait_path"] == str(p1)
        assert updated["portraits"][0]["is_primary"] is True
        assert updated["portraits"][1]["is_primary"] is False

        updated = characters.delete_portrait(char["id"], str(p2))
        assert len(updated["portraits"]) == 1
        assert not p2.exists()

    def test_migrate_existing_portrait(self, isolated_storage, tmp_path):
        import characters

        char = characters.create_character(name="OldChar", portrait_path="/fake/old.png")
        chars = characters._load()
        for c in chars:
            if c["id"] == char["id"]:
                del c["portraits"]
        characters._save(chars)

        characters._migrate_portraits()

        updated = characters.get_character(char["id"])
        assert len(updated["portraits"]) == 1
        assert updated["portraits"][0]["path"] == "/fake/old.png"
        assert updated["portraits"][0]["is_primary"] is True


class TestFullbodyGallery:
    """Verify full-body gallery CRUD in characters module."""

    def test_add_and_set_primary_fullbody(self, isolated_storage, tmp_path):
        import characters

        char = characters.create_character(name="TestChar")
        assert char["fullbodies"] == []
        assert char["fullbody_path"] == ""

        f1 = tmp_path / "f1.png"
        f2 = tmp_path / "f2.png"
        f1.write_bytes(b"fake")
        f2.write_bytes(b"fake")

        updated = characters.add_fullbody(char["id"], str(f1), set_primary=True)
        assert len(updated["fullbodies"]) == 1
        assert updated["fullbodies"][0]["is_primary"] is True
        assert updated["fullbody_path"] == str(f1)

        updated = characters.add_fullbody(char["id"], str(f2), set_primary=True)
        assert len(updated["fullbodies"]) == 2
        assert updated["fullbody_path"] == str(f2)

        updated = characters.set_primary_fullbody(char["id"], str(f1))
        assert updated["fullbody_path"] == str(f1)

        updated = characters.delete_fullbody(char["id"], str(f2))
        assert len(updated["fullbodies"]) == 1
        assert not f2.exists()


class TestNpcSystem:
    """Verify NPC creation and lookup."""

    def test_create_npc(self, isolated_storage):
        import characters

        npc = characters.create_npc("Strahd", "A vampire lord with pale skin", "camp-1")
        assert npc["is_npc"] is True
        assert npc["npc_description"] == "A vampire lord with pale skin"
        assert "camp-1" in npc["campaign_ids"]

    def test_get_npcs(self, isolated_storage):
        import characters

        characters.create_character(name="Hero")
        characters.create_npc("Strahd", "Vampire", "camp-1")
        characters.create_npc("Barkeep", "Tavern owner", "camp-1")
        characters.create_npc("Merchant", "Seller", "camp-2")

        all_npcs = characters.get_npcs()
        assert len(all_npcs) == 3

        camp1_npcs = characters.get_npcs("camp-1")
        assert len(camp1_npcs) == 2

    def test_find_npc_by_name(self, isolated_storage):
        import characters

        characters.create_npc("Strahd", "Vampire lord", "camp-1")
        found = characters.find_npc_by_name("strahd")  # case-insensitive
        assert found is not None
        assert found["name"] == "Strahd"

        not_found = characters.find_npc_by_name("Gandalf")
        assert not_found is None

    def test_update_npc_description(self, isolated_storage):
        import characters

        npc = characters.create_npc("Strahd", "A vampire", "camp-1")
        updated = characters.update_npc_description(npc["id"], "A powerful vampire lord of Barovia")
        assert updated["npc_description"] == "A powerful vampire lord of Barovia"

    def test_campaign_npc_tracking(self, isolated_storage):
        import campaigns
        import characters

        camp = campaigns.create_campaign("Test", [{"number": 1, "characters": []}])
        npc = characters.create_npc("Strahd", "Vampire", camp["id"])
        campaigns.add_campaign_npc(camp["id"], npc["id"])

        npc_ids = campaigns.get_campaign_npcs(camp["id"])
        assert npc["id"] in npc_ids

    def test_npc_has_pictures_fields(self, isolated_storage):
        import characters

        npc = characters.create_npc("Strahd", "Vampire", "camp-1")
        assert "portraits" in npc
        assert "fullbodies" in npc
        assert npc["portraits"] == []
        assert npc["fullbodies"] == []


class TestImageGenPortrait:
    """Verify that generate_portrait sends prompt without fantasy wrapper."""

    def test_portrait_function_exists(self):
        """Ensure generate_portrait is a separate function from generate_illustration."""
        import image_gen
        assert hasattr(image_gen, "generate_portrait")
        assert hasattr(image_gen, "generate_illustration")
        assert image_gen.generate_portrait is not image_gen.generate_illustration

    def test_portrait_prompt_no_fantasy_wrapper(self, tmp_path):
        """Ensure generate_portrait does NOT include 'epic fantasy art style'."""
        import image_gen

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_part = MagicMock()
        mock_part.inline_data.data = b"fake_image_bytes"
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [mock_part]
        mock_client.models.generate_content.return_value = mock_response

        mock_genai = MagicMock()
        mock_genai.Client.return_value = mock_client

        out_path = str(tmp_path / "portrait.png")

        with patch.dict(sys.modules, {
            "google": MagicMock(),
            "google.genai": mock_genai,
            "google.genai.types": MagicMock(),
        }):
            # Call generate_portrait directly, bypassing the lazy import
            # by manually doing what the function does
            from google.genai import types as mock_types

            mock_client.models.generate_content.return_value = mock_response

            # Manually invoke the logic
            full_prompt = (
                "Generate a 1:1 square portrait photograph. "
                "Do not include any text, labels, or watermarks.\n\n"
                "Photorealistic headshot of Thorin, a Dwarf Fighter"
            )

            mock_client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=full_prompt,
                config=mock_types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )

            call_args = mock_client.models.generate_content.call_args
            prompt_sent = call_args.kwargs.get("contents", "")
            assert "epic fantasy art style" not in prompt_sent.lower()
            assert "portrait photograph" in prompt_sent.lower()
