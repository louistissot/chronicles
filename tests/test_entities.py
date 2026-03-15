"""Tests for entities.py — unified entity registry with relationships and history."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entities


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_entity_dir(tmp_path, monkeypatch):
    """Redirect entity storage to a temp directory for each test."""
    monkeypatch.setattr(entities, "_ENTITIES_DIR", tmp_path / "entities")


CAMPAIGN_ID = "test-campaign-001"


# ---------------------------------------------------------------------------
# Entity CRUD
# ---------------------------------------------------------------------------

class TestEntityCRUD:
    def test_create_entity(self):
        ent = entities.create_entity(
            campaign_id=CAMPAIGN_ID,
            entity_type="location",
            name="Thundertop Mountain",
            session_id="sess-001",
            session_date="2026-01-15",
            definition="A volcanic peak east of Phandalin.",
            description="Tall mountain with smoke rising from the summit.",
            properties={"status": "visited", "visit_order": 1},
        )
        assert ent["id"]
        assert ent["name"] == "Thundertop Mountain"
        assert ent["type"] == "location"
        assert ent["current"]["definition"] == "A volcanic peak east of Phandalin."
        assert ent["current"]["properties"]["status"] == "visited"
        assert len(ent["history"]) == 1
        assert ent["history"][0]["change_type"] == "created"

    def test_get_entity(self):
        ent = entities.create_entity(CAMPAIGN_ID, "item", "Flame Tongue")
        fetched = entities.get_entity(CAMPAIGN_ID, ent["id"])
        assert fetched is not None
        assert fetched["name"] == "Flame Tongue"

    def test_get_entity_missing(self):
        assert entities.get_entity(CAMPAIGN_ID, "nonexistent") is None

    def test_get_entities_filters_by_type(self):
        entities.create_entity(CAMPAIGN_ID, "location", "Town Square")
        entities.create_entity(CAMPAIGN_ID, "item", "Potion of Healing")
        entities.create_entity(CAMPAIGN_ID, "location", "Dark Forest")

        all_ents = entities.get_entities(CAMPAIGN_ID)
        assert len(all_ents) == 3

        locations = entities.get_entities(CAMPAIGN_ID, entity_type="location")
        assert len(locations) == 2
        assert all(e["type"] == "location" for e in locations)

    def test_find_entity_by_name(self):
        entities.create_entity(CAMPAIGN_ID, "faction", "Order of the Gauntlet")
        found = entities.find_entity_by_name(CAMPAIGN_ID, "order of the gauntlet")
        assert found is not None
        assert found["name"] == "Order of the Gauntlet"

    def test_find_entity_by_alias(self):
        entities.create_entity(
            CAMPAIGN_ID, "location", "Phandalin",
            aliases=["Fandolin", "Phandolin"],
        )
        found = entities.find_entity_by_name(CAMPAIGN_ID, "Fandolin")
        assert found is not None
        assert found["name"] == "Phandalin"

    def test_find_entity_fuzzy(self):
        entities.create_entity(CAMPAIGN_ID, "location", "Thundertop Mountain")
        # Close misspelling
        found = entities.find_entity_fuzzy(CAMPAIGN_ID, "Thundertop Mountian")
        assert found is not None
        assert found["name"] == "Thundertop Mountain"

    def test_delete_entity(self):
        ent = entities.create_entity(CAMPAIGN_ID, "item", "Shield of Faith")
        assert entities.delete_entity(CAMPAIGN_ID, ent["id"]) is True
        assert entities.get_entity(CAMPAIGN_ID, ent["id"]) is None

    def test_delete_removes_relationships(self):
        e1 = entities.create_entity(CAMPAIGN_ID, "location", "Castle")
        e2 = entities.create_entity(CAMPAIGN_ID, "location", "Village")
        entities.create_relationship(
            CAMPAIGN_ID, e1["id"], "entity", e2["id"], "entity", "connected_to",
        )
        assert len(entities.get_relationships(CAMPAIGN_ID, e1["id"])) == 1
        entities.delete_entity(CAMPAIGN_ID, e1["id"])
        assert len(entities.get_relationships(CAMPAIGN_ID, e2["id"])) == 0


# ---------------------------------------------------------------------------
# Entity Update with History
# ---------------------------------------------------------------------------

class TestEntityHistory:
    def test_update_snapshots_previous_state(self):
        ent = entities.create_entity(
            CAMPAIGN_ID, "mission", "Rescue the Princess",
            session_id="sess-001", session_date="2026-01-15",
            definition="Save Princess Aria from the tower.",
            properties={"status": "active"},
        )

        updated = entities.update_entity(
            CAMPAIGN_ID, ent["id"], "sess-002",
            session_date="2026-01-22",
            properties={"status": "completed"},
            change_summary="Princess rescued successfully",
        )

        assert updated is not None
        assert updated["current"]["properties"]["status"] == "completed"
        assert len(updated["history"]) == 2  # created + updated

        # The second history entry should have the previous state
        hist = updated["history"][1]
        assert hist["change_type"] == "updated"
        assert hist["summary"] == "Princess rescued successfully"
        assert hist["previous_state"]["properties"]["status"] == "active"

    def test_update_merges_properties(self):
        ent = entities.create_entity(
            CAMPAIGN_ID, "item", "Sword",
            properties={"magical": True, "owner_name": "Alice"},
        )
        updated = entities.update_entity(
            CAMPAIGN_ID, ent["id"], "sess-002",
            properties={"owner_name": "Bob"},
        )
        # magical should be preserved, owner_name updated
        assert updated["current"]["properties"]["magical"] is True
        assert updated["current"]["properties"]["owner_name"] == "Bob"

    def test_update_adds_aliases(self):
        ent = entities.create_entity(CAMPAIGN_ID, "location", "Neverwinter")
        updated = entities.update_entity(
            CAMPAIGN_ID, ent["id"], "sess-002",
            aliases=["The Jewel of the North"],
        )
        assert "The Jewel of the North" in updated["aliases"]

    def test_multiple_updates_build_history(self):
        ent = entities.create_entity(
            CAMPAIGN_ID, "location", "Tavern",
            session_id="sess-001", session_date="2026-01-01",
            definition="A cozy tavern.",
        )

        for i in range(5):
            entities.update_entity(
                CAMPAIGN_ID, ent["id"], "sess-{:03d}".format(i + 2),
                session_date="2026-01-{:02d}".format(i + 8),
                change_summary="Visit {}".format(i + 2),
            )

        final = entities.get_entity(CAMPAIGN_ID, ent["id"])
        assert len(final["history"]) == 6  # 1 created + 5 updates


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

class TestRelationships:
    def test_create_relationship(self):
        e1 = entities.create_entity(CAMPAIGN_ID, "location", "Castle")
        e2 = entities.create_entity(CAMPAIGN_ID, "location", "Village")

        rel = entities.create_relationship(
            CAMPAIGN_ID, e1["id"], "entity", e2["id"], "entity",
            "connected_to",
            session_id="sess-001", session_date="2026-01-15",
            description="Castle overlooks the village",
        )
        assert rel["type"] == "connected_to"
        assert rel["current"]["status"] == "active"
        assert len(rel["history"]) == 1

    def test_update_relationship_tracks_history(self):
        """Test the romance → breakup scenario."""
        # Two characters fall in love
        e1 = entities.create_entity(CAMPAIGN_ID, "lore", "Alice's Romance")
        e2 = entities.create_entity(CAMPAIGN_ID, "lore", "Bob's Romance")

        rel = entities.create_relationship(
            CAMPAIGN_ID, e1["id"], "entity", e2["id"], "entity",
            "loves",
            session_id="sess-001", session_date="2026-01-15",
            description="Alice and Bob fell in love",
        )

        # Session 3: they break up
        updated = entities.update_relationship(
            CAMPAIGN_ID, rel["id"], "sess-003",
            session_date="2026-01-29",
            new_status="ended",
            new_description="Alice and Bob broke up after a bitter argument",
            change_summary="Romance ended — bitter argument",
        )

        assert updated["current"]["status"] == "ended"
        assert len(updated["history"]) == 2

        # History shows both states
        assert updated["history"][0]["status"] == "active"
        assert updated["history"][1]["status"] == "ended"
        assert updated["history"][1]["change_summary"] == "Romance ended — bitter argument"

    def test_find_relationship(self):
        e1 = entities.create_entity(CAMPAIGN_ID, "location", "A")
        e2 = entities.create_entity(CAMPAIGN_ID, "location", "B")
        entities.create_relationship(
            CAMPAIGN_ID, e1["id"], "entity", e2["id"], "entity", "connected_to",
        )
        # Forward lookup
        found = entities.find_relationship(CAMPAIGN_ID, e1["id"], e2["id"])
        assert found is not None
        # Reverse lookup
        found_rev = entities.find_relationship(CAMPAIGN_ID, e2["id"], e1["id"])
        assert found_rev is not None
        assert found["id"] == found_rev["id"]

    def test_get_relationships_filtered(self):
        e1 = entities.create_entity(CAMPAIGN_ID, "location", "X")
        e2 = entities.create_entity(CAMPAIGN_ID, "location", "Y")
        e3 = entities.create_entity(CAMPAIGN_ID, "faction", "Z")

        entities.create_relationship(
            CAMPAIGN_ID, e1["id"], "entity", e2["id"], "entity", "connected_to",
        )
        entities.create_relationship(
            CAMPAIGN_ID, e1["id"], "entity", e3["id"], "entity", "allied_with",
        )

        all_rels = entities.get_relationships(CAMPAIGN_ID, e1["id"])
        assert len(all_rels) == 2

        typed = entities.get_relationships(CAMPAIGN_ID, e1["id"], rel_type="connected_to")
        assert len(typed) == 1


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

class TestEntityTimeline:
    def test_timeline_merges_entity_and_relationship_events(self):
        e1 = entities.create_entity(
            CAMPAIGN_ID, "location", "Tavern",
            session_id="sess-001", session_date="2026-01-01",
        )
        e2 = entities.create_entity(
            CAMPAIGN_ID, "location", "Market",
            session_id="sess-001", session_date="2026-01-01",
        )

        entities.create_relationship(
            CAMPAIGN_ID, e1["id"], "entity", e2["id"], "entity",
            "connected_to",
            session_id="sess-001", session_date="2026-01-01",
        )

        entities.update_entity(
            CAMPAIGN_ID, e1["id"], "sess-002",
            session_date="2026-01-08",
            change_summary="Tavern burned down",
        )

        timeline = entities.get_entity_timeline(CAMPAIGN_ID, e1["id"])
        assert len(timeline) == 3  # created + relationship + updated
        assert timeline[0]["type"] == "entity_change"
        # All events for same date should be present
        dates = [t["session_date"] for t in timeline]
        assert "2026-01-01" in dates
        assert "2026-01-08" in dates


# ---------------------------------------------------------------------------
# Glossary Migration
# ---------------------------------------------------------------------------

class TestGlossaryMigration:
    def test_migrate_glossary_creates_entities(self):
        glossary = {
            "Phandalin": {
                "category": "Location",
                "definition": "A small frontier town.",
                "description": "Mining town in the Sword Coast.",
            },
            "Flame Tongue": {
                "category": "Item",
                "definition": "A magical flaming sword.",
                "description": "",
            },
            "Boblin": {
                "category": "NPC",
                "definition": "A friendly goblin.",
                "description": "Met in session 1.",
            },
        }
        count = entities.migrate_glossary_to_entities(CAMPAIGN_ID, glossary)
        # NPCs should be skipped (they live in characters.json)
        assert count == 2

        all_ents = entities.get_entities(CAMPAIGN_ID)
        assert len(all_ents) == 2
        names = {e["name"] for e in all_ents}
        assert "Phandalin" in names
        assert "Flame Tongue" in names
        assert "Boblin" not in names

    def test_migrate_idempotent(self):
        glossary = {
            "Phandalin": {
                "category": "Location",
                "definition": "A small town.",
                "description": "",
            },
        }
        entities.migrate_glossary_to_entities(CAMPAIGN_ID, glossary)
        count = entities.migrate_glossary_to_entities(CAMPAIGN_ID, glossary)
        assert count == 0  # No duplicates
        assert len(entities.get_entities(CAMPAIGN_ID)) == 1


# ---------------------------------------------------------------------------
# Session Artifact Migration
# ---------------------------------------------------------------------------

class TestSessionArtifactMigration:
    def test_migrate_locations(self, tmp_path):
        loc_data = [
            {"name": "Dark Forest", "description": "Spooky woods.", "visit_order": 1,
             "connections": ["north of town"], "relative_position": "north"},
        ]
        (tmp_path / "locations.json").write_text(json.dumps(loc_data), encoding="utf-8")

        count = entities.migrate_session_artifacts(CAMPAIGN_ID, "sess-001", "2026-01-15", str(tmp_path))
        assert count == 1

        ent = entities.find_entity_by_name(CAMPAIGN_ID, "Dark Forest")
        assert ent is not None
        assert ent["type"] == "location"
        assert ent["current"]["properties"]["visit_order"] == 1

    def test_migrate_loot(self, tmp_path):
        loot_data = {
            "items": [
                {"item": "Healing Potion", "type": "potion", "magical": False,
                 "looted_by": "Alice", "how": "found"},
            ],
            "gold": [],
        }
        (tmp_path / "loot.json").write_text(json.dumps(loot_data), encoding="utf-8")

        count = entities.migrate_session_artifacts(CAMPAIGN_ID, "sess-001", "2026-01-15", str(tmp_path))
        assert count == 1

        ent = entities.find_entity_by_name(CAMPAIGN_ID, "Healing Potion")
        assert ent is not None
        assert ent["type"] == "item"

    def test_migrate_missions(self, tmp_path):
        missions_data = [
            {"name": "Rescue the Princess", "status": "started",
             "description": "Save Aria.", "givers": ["King"],
             "objectives": ["Find the tower"], "rewards_mentioned": "Gold"},
        ]
        (tmp_path / "missions.json").write_text(json.dumps(missions_data), encoding="utf-8")

        count = entities.migrate_session_artifacts(CAMPAIGN_ID, "sess-001", "2026-01-15", str(tmp_path))
        assert count == 1

        ent = entities.find_entity_by_name(CAMPAIGN_ID, "Rescue the Princess")
        assert ent is not None
        assert ent["type"] == "mission"
        assert ent["current"]["properties"]["status"] == "started"


# ---------------------------------------------------------------------------
# Entity Enrichment (LLM output processing)
# ---------------------------------------------------------------------------

class TestEntityEnrichment:
    def test_process_creates_new_entities(self):
        stats = entities.process_extracted_entities(
            campaign_id=CAMPAIGN_ID,
            session_id="sess-001",
            session_date="2026-01-15",
            extracted_entities=[
                {"name": "Waterdeep", "type": "location",
                 "definition": "City of Splendors", "change_type": "new"},
                {"name": "Shield of Heroes", "type": "item",
                 "definition": "Magical shield", "change_type": "new"},
            ],
            extracted_relationships=[],
        )
        assert stats["created"] == 2
        assert len(entities.get_entities(CAMPAIGN_ID)) == 2

    def test_process_updates_existing_entities(self):
        ent = entities.create_entity(
            CAMPAIGN_ID, "location", "Waterdeep",
            session_id="sess-001",
            definition="A large city.",
        )

        stats = entities.process_extracted_entities(
            campaign_id=CAMPAIGN_ID,
            session_id="sess-002",
            session_date="2026-01-22",
            extracted_entities=[
                {"name": "Waterdeep", "type": "location", "match_id": ent["id"],
                 "definition": "The City of Splendors, largest city on the Sword Coast.",
                 "change_type": "updated", "change_summary": "More detail learned"},
            ],
            extracted_relationships=[],
        )
        assert stats["updated"] == 1
        updated = entities.get_entity(CAMPAIGN_ID, ent["id"])
        assert "City of Splendors" in updated["current"]["definition"]

    def test_process_creates_relationships(self):
        entities.create_entity(CAMPAIGN_ID, "location", "Castle")
        entities.create_entity(CAMPAIGN_ID, "location", "Village")

        stats = entities.process_extracted_entities(
            campaign_id=CAMPAIGN_ID,
            session_id="sess-001",
            session_date="2026-01-15",
            extracted_entities=[],
            extracted_relationships=[
                {"source_name": "Castle", "target_name": "Village",
                 "type": "connected_to", "status": "active",
                 "description": "Castle overlooks village", "is_new": True},
            ],
        )
        assert stats["rels_created"] == 1


# ---------------------------------------------------------------------------
# Glossary Projection
# ---------------------------------------------------------------------------

class TestGlossaryProjection:
    def test_project_to_glossary(self):
        entities.create_entity(
            CAMPAIGN_ID, "location", "Phandalin",
            definition="A small town.", description="Mining town.",
        )
        entities.create_entity(
            CAMPAIGN_ID, "item", "Flame Tongue",
            definition="Flaming sword.", description="",
        )

        glossary = entities.project_to_glossary(CAMPAIGN_ID)
        assert "Phandalin" in glossary
        assert glossary["Phandalin"]["category"] == "Location"
        assert glossary["Phandalin"]["definition"] == "A small town."
        assert "Flame Tongue" in glossary
        assert glossary["Flame Tongue"]["category"] == "Item"


# ---------------------------------------------------------------------------
# LLM Context Generation
# ---------------------------------------------------------------------------

class TestLLMContext:
    def test_entity_context_for_llm(self):
        entities.create_entity(
            CAMPAIGN_ID, "location", "Phandalin",
            definition="A small frontier town.",
        )
        entities.create_entity(
            CAMPAIGN_ID, "faction", "Zhentarim",
            definition="A shadowy mercantile network.",
        )

        context = entities.get_entity_context_for_llm(CAMPAIGN_ID)
        assert "Phandalin" in context
        assert "Zhentarim" in context
        assert "## Campaign Entity Registry" in context

    def test_empty_campaign_returns_empty(self):
        context = entities.get_entity_context_for_llm("nonexistent-campaign")
        assert context == ""
