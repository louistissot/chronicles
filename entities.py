"""Unified entity registry — graph-ready data model with relationships and history.

Stores all campaign entities (locations, items, missions, factions, spells, lore)
in per-campaign JSON files at ~/.config/dnd-whisperx/entities/<campaign_id>.json.

Each entity has:
- A current state (definition, description, type-specific properties)
- A full history of state changes (snapshots before each update)
- Aliases for fuzzy matching

Relationships between entities (and between entities and characters) are first-class
objects with their own history, enabling timeline tracking (e.g., romance -> breakup).

Python 3.9 compatible — no X|Y union syntax.
"""
import copy
import json
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from log import get_logger

_log = get_logger("entities")
_ENTITIES_DIR = Path.home() / ".config" / "dnd-whisperx" / "entities"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def _entity_file(campaign_id):
    # type: (str) -> Path
    return _ENTITIES_DIR / "{}.json".format(campaign_id)


def _load(campaign_id):
    # type: (str) -> Dict[str, Any]
    path = _entity_file(campaign_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            _log.error("Failed to load entities for campaign %s: %s", campaign_id, e)
    return {"version": 2, "entities": {}, "relationships": {}}


def _save(campaign_id, data):
    # type: (str, Dict[str, Any]) -> None
    _ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
    path = _entity_file(campaign_id)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entity CRUD
# ---------------------------------------------------------------------------

def get_entities(campaign_id, entity_type=None):
    # type: (str, Optional[str]) -> List[Dict[str, Any]]
    """Return all entities for a campaign, optionally filtered by type."""
    data = _load(campaign_id)
    entities = list(data.get("entities", {}).values())
    if entity_type:
        entities = [e for e in entities if e.get("type") == entity_type]
    return entities


def get_entity(campaign_id, entity_id):
    # type: (str, str) -> Optional[Dict[str, Any]]
    """Return a single entity by ID."""
    data = _load(campaign_id)
    return data.get("entities", {}).get(entity_id)


def find_entity_by_name(campaign_id, name, entity_type=None):
    # type: (str, str, Optional[str]) -> Optional[Dict[str, Any]]
    """Find an entity by name or alias (case-insensitive). Returns best match or None."""
    name_lower = name.lower().strip()
    if not name_lower:
        return None
    data = _load(campaign_id)
    for ent in data.get("entities", {}).values():
        if entity_type and ent.get("type") != entity_type:
            continue
        if ent.get("name", "").lower().strip() == name_lower:
            return ent
        for alias in ent.get("aliases", []):
            if alias.lower().strip() == name_lower:
                return ent
    return None


def find_entity_fuzzy(campaign_id, name, entity_type=None, threshold=0.80):
    # type: (str, str, Optional[str], float) -> Optional[Dict[str, Any]]
    """Find an entity by fuzzy name matching. Returns best match above threshold."""
    name_lower = name.lower().strip()
    if not name_lower or len(name_lower) < 3:
        return None

    # Try exact match first
    exact = find_entity_by_name(campaign_id, name, entity_type)
    if exact:
        return exact

    data = _load(campaign_id)
    best_match = None  # type: Optional[Dict[str, Any]]
    best_score = threshold

    for ent in data.get("entities", {}).values():
        if entity_type and ent.get("type") != entity_type:
            continue
        candidates = [ent.get("name", "")] + ent.get("aliases", [])
        for candidate in candidates:
            score = SequenceMatcher(None, name_lower, candidate.lower().strip()).ratio()
            if score > best_score:
                best_score = score
                best_match = ent

    return best_match


def create_entity(
    campaign_id,        # type: str
    entity_type,        # type: str
    name,               # type: str
    session_id="",      # type: str
    session_date="",    # type: str
    definition="",      # type: str
    description="",     # type: str
    category="",        # type: str
    aliases=None,       # type: Optional[List[str]]
    properties=None,    # type: Optional[Dict[str, Any]]
):
    # type: (...) -> Dict[str, Any]
    """Create a new entity in the campaign registry. Returns the created entity."""
    entity_id = str(uuid.uuid4())
    entity = {
        "id": entity_id,
        "type": entity_type,
        "name": name,
        "aliases": aliases or [],
        "campaign_id": campaign_id,
        "category": category,
        "created_session_id": session_id,
        "last_updated_session_id": session_id,
        "current": {
            "definition": definition,
            "description": description,
            "properties": properties or {},
            "as_of_session": session_id,
        },
        "history": [
            {
                "session_id": session_id,
                "session_date": session_date,
                "change_type": "created",
                "summary": "First appearance",
                "previous_state": {},
            }
        ] if session_id else [],
    }
    data = _load(campaign_id)
    data["entities"][entity_id] = entity
    _save(campaign_id, data)
    _log.info("Created entity '%s' (%s) in campaign %s", name, entity_type, campaign_id)
    return entity


def update_entity(
    campaign_id,     # type: str
    entity_id,       # type: str
    session_id,      # type: str
    session_date="", # type: str
    definition=None, # type: Optional[str]
    description=None,  # type: Optional[str]
    properties=None, # type: Optional[Dict[str, Any]]
    change_summary="",  # type: str
    aliases=None,    # type: Optional[List[str]]
):
    # type: (...) -> Optional[Dict[str, Any]]
    """Update an entity, automatically snapshotting the previous state to history."""
    data = _load(campaign_id)
    entity = data.get("entities", {}).get(entity_id)
    if not entity:
        _log.error("update_entity: entity %s not found in campaign %s", entity_id, campaign_id)
        return None

    # Snapshot current state before updating (deep copy to preserve nested dicts)
    previous_state = copy.deepcopy(entity.get("current", {}))

    current = entity.get("current", {})

    # Apply updates (only non-None values)
    if definition is not None:
        current["definition"] = definition
    if description is not None:
        current["description"] = description
    if properties is not None:
        # Merge properties rather than replace
        existing_props = current.get("properties", {})
        existing_props.update(properties)
        current["properties"] = existing_props
    current["as_of_session"] = session_id
    entity["current"] = current

    # Add aliases if provided
    if aliases:
        existing_aliases = set(entity.get("aliases", []))
        for alias in aliases:
            existing_aliases.add(alias)
        entity["aliases"] = list(existing_aliases)

    # Append history entry
    history = entity.get("history", [])
    history.append({
        "session_id": session_id,
        "session_date": session_date,
        "change_type": "updated",
        "summary": change_summary or "Updated",
        "previous_state": previous_state,
    })
    entity["history"] = history
    entity["last_updated_session_id"] = session_id

    data["entities"][entity_id] = entity
    _save(campaign_id, data)
    _log.info("Updated entity '%s' in session %s", entity.get("name"), session_id)
    return entity


def delete_entity(campaign_id, entity_id):
    # type: (str, str) -> bool
    """Delete an entity and all its relationships."""
    data = _load(campaign_id)
    if entity_id not in data.get("entities", {}):
        return False

    # Remove entity
    del data["entities"][entity_id]

    # Remove relationships involving this entity
    rels = data.get("relationships", {})
    to_remove = [
        rid for rid, rel in rels.items()
        if rel.get("source_id") == entity_id or rel.get("target_id") == entity_id
    ]
    for rid in to_remove:
        del rels[rid]

    _save(campaign_id, data)
    _log.info("Deleted entity %s and %d relationships", entity_id, len(to_remove))
    return True


# ---------------------------------------------------------------------------
# Relationship CRUD
# ---------------------------------------------------------------------------

def create_relationship(
    campaign_id,     # type: str
    source_id,       # type: str
    source_type,     # type: str
    target_id,       # type: str
    target_type,     # type: str
    rel_type,        # type: str
    session_id="",   # type: str
    session_date="", # type: str
    status="active", # type: str
    description="",  # type: str
):
    # type: (...) -> Dict[str, Any]
    """Create a new relationship between two entities/characters."""
    rel_id = str(uuid.uuid4())
    relationship = {
        "id": rel_id,
        "type": rel_type,
        "source_id": source_id,
        "source_type": source_type,
        "target_id": target_id,
        "target_type": target_type,
        "campaign_id": campaign_id,
        "current": {
            "status": status,
            "description": description,
            "as_of_session": session_id,
        },
        "history": [
            {
                "session_id": session_id,
                "session_date": session_date,
                "status": status,
                "description": description,
                "change_summary": "Relationship established",
            }
        ] if session_id else [],
    }
    data = _load(campaign_id)
    data["relationships"][rel_id] = relationship
    _save(campaign_id, data)
    _log.info("Created relationship %s: %s -> %s (%s)", rel_type, source_id, target_id, status)
    return relationship


def update_relationship(
    campaign_id,         # type: str
    rel_id,              # type: str
    session_id,          # type: str
    session_date="",     # type: str
    new_status=None,     # type: Optional[str]
    new_description=None,  # type: Optional[str]
    change_summary="",   # type: str
):
    # type: (...) -> Optional[Dict[str, Any]]
    """Update a relationship, snapshotting the previous state to history."""
    data = _load(campaign_id)
    rel = data.get("relationships", {}).get(rel_id)
    if not rel:
        _log.error("update_relationship: relationship %s not found", rel_id)
        return None

    current = rel.get("current", {})
    old_status = current.get("status", "active")
    old_description = current.get("description", "")

    if new_status is not None:
        current["status"] = new_status
    if new_description is not None:
        current["description"] = new_description
    current["as_of_session"] = session_id
    rel["current"] = current

    # Append history
    history = rel.get("history", [])
    history.append({
        "session_id": session_id,
        "session_date": session_date,
        "status": current.get("status", old_status),
        "description": current.get("description", old_description),
        "change_summary": change_summary or "Updated",
    })
    rel["history"] = history

    data["relationships"][rel_id] = rel
    _save(campaign_id, data)
    _log.info("Updated relationship %s: status=%s", rel_id, current.get("status"))
    return rel


def get_relationships(campaign_id, entity_id=None, rel_type=None):
    # type: (str, Optional[str], Optional[str]) -> List[Dict[str, Any]]
    """Return relationships, optionally filtered by entity or type."""
    data = _load(campaign_id)
    rels = list(data.get("relationships", {}).values())
    if entity_id:
        rels = [
            r for r in rels
            if r.get("source_id") == entity_id or r.get("target_id") == entity_id
        ]
    if rel_type:
        rels = [r for r in rels if r.get("type") == rel_type]
    return rels


def find_relationship(campaign_id, source_id, target_id, rel_type=None):
    # type: (str, str, str, Optional[str]) -> Optional[Dict[str, Any]]
    """Find an existing relationship between two specific entities."""
    data = _load(campaign_id)
    for rel in data.get("relationships", {}).values():
        src_match = rel.get("source_id") == source_id and rel.get("target_id") == target_id
        rev_match = rel.get("source_id") == target_id and rel.get("target_id") == source_id
        if src_match or rev_match:
            if rel_type is None or rel.get("type") == rel_type:
                return rel
    return None


# ---------------------------------------------------------------------------
# Timeline / Query Helpers
# ---------------------------------------------------------------------------

def get_entity_timeline(campaign_id, entity_id):
    # type: (str, str) -> List[Dict[str, Any]]
    """Return merged timeline of entity changes + relationship changes, sorted by session date."""
    data = _load(campaign_id)
    entity = data.get("entities", {}).get(entity_id)
    if not entity:
        return []

    timeline = []  # type: List[Dict[str, Any]]

    # Entity's own history
    for entry in entity.get("history", []):
        timeline.append({
            "type": "entity_change",
            "entity_name": entity.get("name", ""),
            "session_id": entry.get("session_id", ""),
            "session_date": entry.get("session_date", ""),
            "change_type": entry.get("change_type", ""),
            "summary": entry.get("summary", ""),
        })

    # Relationships involving this entity
    for rel in data.get("relationships", {}).values():
        if rel.get("source_id") != entity_id and rel.get("target_id") != entity_id:
            continue
        for entry in rel.get("history", []):
            # Resolve the other side's name
            other_id = rel.get("target_id") if rel.get("source_id") == entity_id else rel.get("source_id")
            other_entity = data.get("entities", {}).get(other_id, {})
            other_name = other_entity.get("name", other_id)
            timeline.append({
                "type": "relationship_change",
                "relationship_type": rel.get("type", ""),
                "other_name": other_name,
                "other_id": other_id,
                "session_id": entry.get("session_id", ""),
                "session_date": entry.get("session_date", ""),
                "status": entry.get("status", ""),
                "summary": entry.get("change_summary", ""),
            })

    # Sort by session_date
    timeline.sort(key=lambda x: x.get("session_date", ""))
    return timeline


def get_entity_context_for_llm(campaign_id, max_entities=100):
    # type: (str, int) -> str
    """Build a formatted context string of all entities + relationships for LLM injection."""
    data = _load(campaign_id)
    entities = data.get("entities", {})
    relationships = data.get("relationships", {})

    if not entities:
        return ""

    lines = ["## Campaign Entity Registry"]

    # Group by type
    by_type = {}  # type: Dict[str, List[Dict[str, Any]]]
    for ent in entities.values():
        etype = ent.get("type", "other")
        by_type.setdefault(etype, []).append(ent)

    count = 0
    for etype in ["location", "faction", "item", "mission", "spell", "lore"]:
        type_entities = by_type.get(etype, [])
        if not type_entities:
            continue
        lines.append("\n### {}s".format(etype.title()))
        for ent in type_entities:
            if count >= max_entities:
                break
            current = ent.get("current", {})
            name = ent.get("name", "")
            defn = current.get("definition", "")
            props = current.get("properties", {})
            line = "- **{}** [{}]: {}".format(name, ent.get("id", ""), defn)
            if props.get("status"):
                line += " (Status: {})".format(props["status"])
            lines.append(line)
            count += 1

    # Active relationships summary
    active_rels = [r for r in relationships.values()
                   if r.get("current", {}).get("status") == "active"]
    if active_rels:
        lines.append("\n### Active Relationships")
        for rel in active_rels[:50]:
            src = entities.get(rel.get("source_id", ""), {}).get("name", rel.get("source_id", "?"))
            tgt = entities.get(rel.get("target_id", ""), {}).get("name", rel.get("target_id", "?"))
            desc = rel.get("current", {}).get("description", "")
            lines.append("- {} --[{}]--> {}: {}".format(
                src, rel.get("type", "?"), tgt, desc
            ))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Migration from Glossary
# ---------------------------------------------------------------------------

_CATEGORY_TO_TYPE = {
    "NPC": "npc",          # NPCs stay in characters.json, but get entity links
    "Location": "location",
    "Faction": "faction",
    "Item": "item",
    "Spell": "spell",
    "Other": "lore",
}


def migrate_glossary_to_entities(campaign_id, glossary):
    # type: (str, Dict[str, Dict[str, str]]) -> int
    """Migrate a campaign glossary into the entity registry.

    Returns count of entities created. Skips NPC-category entries (they live in characters.json).
    Idempotent — skips terms that already exist as entities.
    """
    if not glossary:
        return 0

    data = _load(campaign_id)
    created = 0

    for term, info in glossary.items():
        category = info.get("category", "Other")
        entity_type = _CATEGORY_TO_TYPE.get(category, "lore")

        # Skip NPCs — they're tracked in characters.json
        if entity_type == "npc":
            continue

        # Check if entity already exists by name
        existing = find_entity_by_name(campaign_id, term, entity_type)
        if existing:
            continue

        create_entity(
            campaign_id=campaign_id,
            entity_type=entity_type,
            name=term,
            definition=info.get("definition", ""),
            description=info.get("description", ""),
            category=category,
        )
        created += 1

    _log.info("Migrated %d glossary terms to entities for campaign %s", created, campaign_id)
    return created


def migrate_session_artifacts(campaign_id, session_id, session_date, output_dir):
    # type: (str, str, str, str) -> int
    """Migrate per-session artifact JSONs (locations, loot, missions) into entity registry.

    Reads locations.json, loot.json, missions.json from the session output directory
    and creates/updates entities. Returns count of entities created or updated.
    """
    out_path = Path(output_dir)
    count = 0

    # --- Locations ---
    loc_file = out_path / "locations.json"
    if loc_file.exists():
        try:
            locations = json.loads(loc_file.read_text(encoding="utf-8"))
            if isinstance(locations, list):
                for loc in locations:
                    name = loc.get("name", "")
                    if not name:
                        continue
                    existing = find_entity_by_name(campaign_id, name, "location")
                    if existing:
                        update_entity(
                            campaign_id, existing["id"], session_id,
                            session_date=session_date,
                            description=loc.get("description", ""),
                            properties={
                                "visit_order": loc.get("visit_order"),
                                "connections": loc.get("connections", []),
                                "relative_position": loc.get("relative_position", ""),
                                "status": "visited",
                            },
                            change_summary="Updated from session artifact",
                        )
                    else:
                        create_entity(
                            campaign_id=campaign_id,
                            entity_type="location",
                            name=name,
                            session_id=session_id,
                            session_date=session_date,
                            definition=loc.get("description", "")[:200],
                            description=loc.get("description", ""),
                            properties={
                                "visit_order": loc.get("visit_order"),
                                "connections": loc.get("connections", []),
                                "relative_position": loc.get("relative_position", ""),
                                "status": "visited",
                            },
                        )
                    count += 1
        except Exception as e:
            _log.error("Failed to migrate locations from %s: %s", loc_file, e)

    # --- Loot (items) ---
    loot_file = out_path / "loot.json"
    if loot_file.exists():
        try:
            loot_data = json.loads(loot_file.read_text(encoding="utf-8"))
            items = loot_data.get("items", []) if isinstance(loot_data, dict) else []
            for item in items:
                name = item.get("item", "")
                if not name:
                    continue
                existing = find_entity_by_name(campaign_id, name, "item")
                if existing:
                    update_entity(
                        campaign_id, existing["id"], session_id,
                        session_date=session_date,
                        properties={
                            "item_type": item.get("type", ""),
                            "magical": item.get("magical", False),
                            "owner_id": "",
                            "owner_name": item.get("looted_by", ""),
                            "status": "owned",
                        },
                        change_summary="Acquired by {}".format(item.get("looted_by", "unknown")),
                    )
                else:
                    create_entity(
                        campaign_id=campaign_id,
                        entity_type="item",
                        name=name,
                        session_id=session_id,
                        session_date=session_date,
                        definition="{} {} ({})".format(
                            "Magical" if item.get("magical") else "",
                            item.get("type", "item"),
                            item.get("how", "found"),
                        ).strip(),
                        properties={
                            "item_type": item.get("type", ""),
                            "magical": item.get("magical", False),
                            "owner_id": "",
                            "owner_name": item.get("looted_by", ""),
                            "status": "owned",
                        },
                    )
                count += 1
        except Exception as e:
            _log.error("Failed to migrate loot from %s: %s", loot_file, e)

    # --- Missions ---
    missions_file = out_path / "missions.json"
    if missions_file.exists():
        try:
            missions = json.loads(missions_file.read_text(encoding="utf-8"))
            if isinstance(missions, list):
                for mission in missions:
                    name = mission.get("name", "")
                    if not name:
                        continue
                    existing = find_entity_by_name(campaign_id, name, "mission")
                    if existing:
                        update_entity(
                            campaign_id, existing["id"], session_id,
                            session_date=session_date,
                            description=mission.get("description", ""),
                            properties={
                                "status": mission.get("status", "active"),
                                "givers": mission.get("givers", []),
                                "objectives": [
                                    {"text": obj, "completed": False}
                                    for obj in mission.get("objectives", [])
                                ],
                                "rewards_mentioned": mission.get("rewards_mentioned", ""),
                            },
                            change_summary="Status: {}".format(mission.get("status", "continued")),
                        )
                    else:
                        create_entity(
                            campaign_id=campaign_id,
                            entity_type="mission",
                            name=name,
                            session_id=session_id,
                            session_date=session_date,
                            definition=mission.get("description", "")[:200],
                            description=mission.get("description", ""),
                            properties={
                                "status": mission.get("status", "active"),
                                "givers": mission.get("givers", []),
                                "objectives": [
                                    {"text": obj, "completed": False}
                                    for obj in mission.get("objectives", [])
                                ],
                                "rewards_mentioned": mission.get("rewards_mentioned", ""),
                            },
                        )
                    count += 1
        except Exception as e:
            _log.error("Failed to migrate missions from %s: %s", missions_file, e)

    if count:
        _log.info("Migrated %d session artifacts to entities for session %s", count, session_id)
    return count


def ensure_migrated(campaign_id, glossary=None, sessions=None):
    # type: (str, Optional[Dict[str, Dict[str, str]]], Optional[List[Dict[str, Any]]]) -> bool
    """Ensure a campaign has been migrated to the entity registry.

    Performs migration if the entity file doesn't exist yet.
    Returns True if migration was performed, False if already done.
    """
    path = _entity_file(campaign_id)
    if path.exists():
        data = _load(campaign_id)
        if data.get("entities"):
            return False  # Already migrated with data

    _log.info("Starting entity migration for campaign %s", campaign_id)

    # Migrate glossary
    if glossary:
        migrate_glossary_to_entities(campaign_id, glossary)

    # Migrate session artifacts
    if sessions:
        for session in sessions:
            if session.get("campaign_id") != campaign_id:
                continue
            output_dir = session.get("output_dir", "")
            if output_dir:
                migrate_session_artifacts(
                    campaign_id,
                    session.get("id", ""),
                    session.get("date", ""),
                    output_dir,
                )

    _log.info("Entity migration complete for campaign %s", campaign_id)
    return True


# ---------------------------------------------------------------------------
# Enrichment — process LLM entity extraction output
# ---------------------------------------------------------------------------

def process_extracted_entities(
    campaign_id,            # type: str
    session_id,             # type: str
    session_date,           # type: str
    extracted_entities,     # type: List[Dict[str, Any]]
    extracted_relationships,  # type: List[Dict[str, Any]]
    character_relationships=None,  # type: Optional[List[Dict[str, Any]]]
):
    # type: (...) -> Dict[str, Any]
    """Process LLM-extracted entities and relationships into the registry.

    Returns summary of changes: {created: int, updated: int, relationships_created: int, relationships_updated: int}
    """
    stats = {"created": 0, "updated": 0, "rels_created": 0, "rels_updated": 0}

    # --- Process entities ---
    for ext in extracted_entities:
        name = ext.get("name", "")
        if not name:
            continue

        entity_type = ext.get("type", "lore")
        change_type = ext.get("change_type", "new")
        match_id = ext.get("match_id")

        # Try to find existing entity
        existing = None  # type: Optional[Dict[str, Any]]
        if match_id:
            existing = get_entity(campaign_id, match_id)
        if not existing:
            existing = find_entity_fuzzy(campaign_id, name, entity_type)

        if existing and change_type != "new":
            # Update existing
            update_entity(
                campaign_id=campaign_id,
                entity_id=existing["id"],
                session_id=session_id,
                session_date=session_date,
                definition=ext.get("definition"),
                description=ext.get("description"),
                properties=ext.get("properties"),
                change_summary=ext.get("change_summary", "Updated from session"),
                aliases=[name] if name.lower() != existing.get("name", "").lower() else None,
            )
            stats["updated"] += 1
        else:
            # Create new
            create_entity(
                campaign_id=campaign_id,
                entity_type=entity_type,
                name=name,
                session_id=session_id,
                session_date=session_date,
                definition=ext.get("definition", ""),
                description=ext.get("description", ""),
                category=ext.get("category", ""),
                properties=ext.get("properties"),
            )
            stats["created"] += 1

    # --- Process entity-to-entity relationships ---
    for rel in extracted_relationships:
        source_name = rel.get("source_name", "")
        target_name = rel.get("target_name", "")
        if not source_name or not target_name:
            continue

        source = find_entity_fuzzy(campaign_id, source_name)
        target = find_entity_fuzzy(campaign_id, target_name)
        if not source or not target:
            continue

        existing_rel = find_relationship(campaign_id, source["id"], target["id"], rel.get("type"))
        if existing_rel:
            update_relationship(
                campaign_id=campaign_id,
                rel_id=existing_rel["id"],
                session_id=session_id,
                session_date=session_date,
                new_status=rel.get("status"),
                new_description=rel.get("description"),
                change_summary=rel.get("change_summary", ""),
            )
            stats["rels_updated"] += 1
        else:
            create_relationship(
                campaign_id=campaign_id,
                source_id=source["id"],
                source_type="entity",
                target_id=target["id"],
                target_type="entity",
                rel_type=rel.get("type", "related_to"),
                session_id=session_id,
                session_date=session_date,
                status=rel.get("status", "active"),
                description=rel.get("description", ""),
            )
            stats["rels_created"] += 1

    # --- Process character-to-entity relationships ---
    if character_relationships:
        for crel in character_relationships:
            char_name = crel.get("character_name", "")
            target_name = crel.get("target_name", "")
            if not char_name or not target_name:
                continue

            # Resolve character ID
            from characters import get_characters
            char_id = None  # type: Optional[str]
            for ch in get_characters():
                if ch.get("name", "").lower() == char_name.lower():
                    char_id = ch["id"]
                    break
            if not char_id:
                continue

            # Resolve target entity
            target = find_entity_fuzzy(campaign_id, target_name)
            if not target:
                continue

            existing_rel = find_relationship(campaign_id, char_id, target["id"], crel.get("type"))
            if existing_rel:
                update_relationship(
                    campaign_id=campaign_id,
                    rel_id=existing_rel["id"],
                    session_id=session_id,
                    session_date=session_date,
                    new_status=crel.get("status"),
                    new_description=crel.get("description"),
                    change_summary=crel.get("change_summary", ""),
                )
                stats["rels_updated"] += 1
            else:
                create_relationship(
                    campaign_id=campaign_id,
                    source_id=char_id,
                    source_type="character",
                    target_id=target["id"],
                    target_type="entity",
                    rel_type=crel.get("type", "interacts_with"),
                    session_id=session_id,
                    session_date=session_date,
                    status=crel.get("status", "active"),
                    description=crel.get("description", ""),
                )
                stats["rels_created"] += 1

    _log.info(
        "Processed entities for session %s: %d created, %d updated, %d rels created, %d rels updated",
        session_id, stats["created"], stats["updated"], stats["rels_created"], stats["rels_updated"],
    )
    return stats


# ---------------------------------------------------------------------------
# Glossary projection (backward compat)
# ---------------------------------------------------------------------------

def project_to_glossary(campaign_id):
    # type: (str) -> Dict[str, Dict[str, str]]
    """Project entity registry back to a glossary dict for backward compatibility.

    Returns {term: {category, definition, description}} matching the existing glossary format.
    """
    data = _load(campaign_id)
    glossary = {}  # type: Dict[str, Dict[str, str]]

    type_to_category = {
        "location": "Location",
        "faction": "Faction",
        "item": "Item",
        "spell": "Spell",
        "lore": "Other",
        "mission": "Other",
    }

    for ent in data.get("entities", {}).values():
        current = ent.get("current", {})
        glossary[ent.get("name", "")] = {
            "category": type_to_category.get(ent.get("type", ""), "Other"),
            "definition": current.get("definition", ""),
            "description": current.get("description", ""),
        }

    return glossary
