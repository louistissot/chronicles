"""Campaign, season, and character persistence.

Seasons store character IDs referencing the global character registry
(characters.py). Old formats (plain strings, embedded dicts) are
auto-migrated on load.
"""
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from log import get_logger

_log = get_logger("campaigns")
_CAMPAIGNS_FILE = Path.home() / ".config" / "dnd-whisperx" / "campaigns.json"


def _is_uuid(value: str) -> bool:
    """Check if a string looks like a UUID (character ID)."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _migrate_to_global_chars(chars: List[Any]) -> List[str]:
    """Migrate old character formats to global character IDs.

    Old format 1: ["DM", "Aragorn"]  (plain strings)
    Old format 2: [{"name": "DM", "race": "", ...}]  (embedded dicts)
    New format:   ["<uuid>", "<uuid>"]  (character IDs)

    Creates global character entries for any non-UUID entries.
    """
    # If already all UUIDs, nothing to do
    if chars and all(isinstance(c, str) and _is_uuid(c) for c in chars):
        return chars

    # Lazy import to avoid circular dependency at module level
    from characters import migrate_from_campaign_chars
    return migrate_from_campaign_chars(chars)


def character_names(chars: List[Any]) -> List[str]:
    """Extract character names from a (possibly mixed) character list.

    Handles: UUID strings (resolved from global registry), plain name strings,
    or old-format dicts.
    """
    result = []
    # Collect UUIDs to resolve in batch
    uuid_ids = []
    non_uuid = []
    for c in chars:
        if isinstance(c, str):
            if _is_uuid(c):
                uuid_ids.append(c)
            else:
                non_uuid.append(c)
        elif isinstance(c, dict):
            name = c.get("name", "")
            if name:
                non_uuid.append(name)
        else:
            non_uuid.append(str(c))

    if uuid_ids:
        from characters import character_names_from_ids
        result.extend(character_names_from_ids(uuid_ids))

    result.extend(non_uuid)
    return [n for n in result if n]


def _load() -> dict:
    if _CAMPAIGNS_FILE.exists():
        try:
            data = json.loads(_CAMPAIGNS_FILE.read_text(encoding="utf-8"))
            # Auto-migrate old character formats to global character IDs
            migrated = False
            for c in data.get("campaigns", []):
                for s in c.get("seasons", []):
                    chars = s.get("characters", [])
                    if not chars:
                        continue
                    # Check if migration needed (non-UUID entries)
                    needs_migration = False
                    for ch in chars:
                        if isinstance(ch, dict):
                            needs_migration = True
                            break
                        if isinstance(ch, str) and not _is_uuid(ch):
                            needs_migration = True
                            break
                    if needs_migration:
                        s["characters"] = _migrate_to_global_chars(chars)
                        migrated = True
            if migrated:
                _save(data)
                _log.info("Migrated campaign characters to global character IDs")
            return data
        except Exception as e:
            _log.error("Failed to load campaigns file: %s", e)
    return {"campaigns": []}


def _save(data: dict) -> None:
    _CAMPAIGNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CAMPAIGNS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_campaigns() -> List[dict]:
    return _load()["campaigns"]


def get_campaigns_for_character(char_id: str) -> List[Dict[str, Any]]:
    """Return campaigns/seasons that reference a character ID."""
    result = []  # type: List[Dict[str, Any]]
    for c in _load()["campaigns"]:
        for s in c.get("seasons", []):
            if char_id in s.get("characters", []):
                result.append({
                    "campaign_id": c["id"],
                    "campaign_name": c["name"],
                    "season_number": s.get("number", 1),
                })
    return result


def create_campaign(name: str, seasons: List[dict]) -> dict:
    """Create a campaign. seasons[].characters can be character IDs or old formats."""
    campaign = {
        "id": str(uuid.uuid4()),
        "name": name,
        "seasons": [
            {
                "id": str(uuid.uuid4()),
                "number": s.get("number", 1),
                "characters": _ensure_char_ids(s.get("characters", [])),
            }
            for s in seasons
        ],
    }
    data = _load()
    data["campaigns"].append(campaign)
    _save(data)
    _log.info("Created campaign '%s' with %d season(s)", name, len(seasons))
    return campaign


def _ensure_char_ids(chars: List[Any]) -> List[str]:
    """Ensure a character list contains only character IDs."""
    if not chars:
        return []
    # If already all UUIDs, return as-is
    if all(isinstance(c, str) and _is_uuid(c) for c in chars):
        return chars
    return _migrate_to_global_chars(chars)


def add_season(campaign_id: str, number: int, characters: List[Any]) -> Optional[dict]:
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            season = {
                "id": str(uuid.uuid4()),
                "number": number,
                "characters": _ensure_char_ids(characters),
            }
            c["seasons"].append(season)
            _save(data)
            _log.info("Added season %d to campaign '%s'", number, c["name"])
            return season
    _log.error("add_season: campaign %s not found", campaign_id)
    return None


def update_season(campaign_id: str, season_id: str, characters: List[Any]) -> bool:
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            for s in c["seasons"]:
                if s["id"] == season_id:
                    s["characters"] = _ensure_char_ids(characters)
                    _save(data)
                    _log.info(
                        "Updated season %d in campaign '%s' with %d characters",
                        s["number"], c["name"], len(characters),
                    )
                    return True
    return False


def update_campaign(campaign_id: str, name: str, beyond_url: str) -> bool:
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            if name:
                c["name"] = name
            c["beyond_url"] = beyond_url
            _save(data)
            _log.info("Updated campaign '%s' beyond_url=%r", c["name"], beyond_url)
            return True
    _log.error("update_campaign: campaign %s not found", campaign_id)
    return False


def delete_campaign(campaign_id: str) -> bool:
    data = _load()
    before = len(data["campaigns"])
    data["campaigns"] = [c for c in data["campaigns"] if c["id"] != campaign_id]
    if len(data["campaigns"]) < before:
        _save(data)
        _log.info("Deleted campaign %s", campaign_id)
        return True
    return False


# ── Glossary ──────────────────────────────────────────────────────────────────

def get_glossary(campaign_id):
    # type: (str) -> Dict[str, Dict[str, str]]
    """Return the glossary for a campaign. {term: {category, definition}}"""
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            return c.get("glossary", {})
    return {}


def update_glossary(campaign_id, glossary):
    # type: (str, Dict[str, Dict[str, str]]) -> bool
    """Full-replace the glossary for a campaign."""
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            c["glossary"] = glossary
            _save(data)
            _log.info("Updated glossary for campaign '%s' (%d terms)", c["name"], len(glossary))
            return True
    _log.error("update_glossary: campaign %s not found", campaign_id)
    return False


def merge_glossary(campaign_id, new_terms):
    # type: (str, Dict[str, Dict[str, str]]) -> bool
    """Merge new terms into the glossary without overwriting existing ones."""
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            existing = c.get("glossary", {})
            added = 0
            for term, info in new_terms.items():
                if term not in existing:
                    existing[term] = info
                    added += 1
            c["glossary"] = existing
            _save(data)
            _log.info("Merged glossary for campaign '%s': %d new of %d total",
                      c["name"], added, len(existing))
            return True
    _log.error("merge_glossary: campaign %s not found", campaign_id)
    return False


def smart_merge_glossary(campaign_id, new_terms):
    # type: (str, Dict[str, Dict[str, str]]) -> bool
    """Smart merge: adds new terms AND updates existing terms with enriched definitions.

    Case-insensitive matching: if a term matches an existing one (ignoring case),
    the existing entry is updated rather than creating a duplicate.
    Description field is merged cumulatively (keeps the longer/richer version).
    """
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            existing = c.get("glossary", {})
            # Build case-insensitive lookup
            lower_to_key = {k.lower(): k for k in existing}
            added = 0
            updated = 0
            for term, info in list(new_terms.items()):
                # Normalise: LLM sometimes returns strings instead of dicts
                if not isinstance(info, dict):
                    info = {"category": "Other", "definition": str(info), "description": ""}
                    new_terms[term] = info
                if "description" not in info:
                    info["description"] = ""
                canonical = lower_to_key.get(term.lower())
                if canonical:
                    # Update existing: enrich definition and description
                    old = existing[canonical]
                    if info.get("definition") and len(info["definition"]) > len(old.get("definition", "")):
                        old["definition"] = info["definition"]
                    if info.get("description") and len(info["description"]) > len(old.get("description", "")):
                        old["description"] = info["description"]
                    if info.get("category"):
                        old["category"] = info["category"]
                    if "description" not in old:
                        old["description"] = ""
                    updated += 1
                else:
                    existing[term] = info
                    lower_to_key[term.lower()] = term
                    added += 1
            c["glossary"] = existing
            _save(data)
            _log.info("Smart-merged glossary for campaign '%s': %d new, %d updated, %d total",
                      c["name"], added, updated, len(existing))
            return True
    _log.error("smart_merge_glossary: campaign %s not found", campaign_id)
    return False


def apply_glossary_merges(campaign_id, merges):
    # type: (str, List[Dict[str, str]]) -> int
    """Apply merge directives: keep one term, remove the duplicate, combine content.

    Each merge is {"keep": "full name", "remove": "variant name"}.
    Returns count of merges applied.
    """
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            existing = c.get("glossary", {})
            count = 0
            for merge in merges:
                keep = merge.get("keep", "")
                remove = merge.get("remove", "")
                if not keep or not remove:
                    continue
                # Find both terms (case-insensitive)
                keep_key = None
                remove_key = None
                for k in existing:
                    if k.lower() == keep.lower():
                        keep_key = k
                    if k.lower() == remove.lower():
                        remove_key = k
                if keep_key and remove_key and keep_key != remove_key:
                    # Combine: keep the richer definition/description
                    keep_entry = existing[keep_key]
                    remove_entry = existing[remove_key]
                    if len(remove_entry.get("definition", "")) > len(keep_entry.get("definition", "")):
                        keep_entry["definition"] = remove_entry["definition"]
                    if len(remove_entry.get("description", "")) > len(keep_entry.get("description", "")):
                        keep_entry["description"] = remove_entry["description"]
                    del existing[remove_key]
                    count += 1
                    _log.info("Merged glossary term '%s' into '%s'", remove_key, keep_key)
            if count:
                c["glossary"] = existing
                _save(data)
            return count
    return 0


# ---------------------------------------------------------------------------
# Campaign NPC tracking
# ---------------------------------------------------------------------------

def add_campaign_npc(campaign_id, npc_char_id):
    # type: (str, str) -> bool
    """Add an NPC character ID to a campaign's npc_ids list."""
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            npc_ids = c.get("npc_ids", [])
            if npc_char_id not in npc_ids:
                npc_ids.append(npc_char_id)
                c["npc_ids"] = npc_ids
                _save(data)
                _log.info("Added NPC %s to campaign '%s'", npc_char_id, c["name"])
            return True
    return False


def get_campaign_npcs(campaign_id):
    # type: (str) -> List[str]
    """Return NPC character IDs for a campaign."""
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            return c.get("npc_ids", [])
    return []


def _migrate_npc_ids():
    # type: () -> None
    """Ensure all campaigns have an npc_ids list."""
    data = _load()
    changed = False
    for c in data["campaigns"]:
        if "npc_ids" not in c:
            c["npc_ids"] = []
            changed = True
    if changed:
        _save(data)
        _log.info("Migrated npc_ids on campaigns")


def _migrate_glossary_descriptions():
    # type: () -> None
    """Ensure all glossary entries have a description field."""
    data = _load()
    changed = False
    for c in data["campaigns"]:
        for term, info in c.get("glossary", {}).items():
            if isinstance(info, dict) and "description" not in info:
                info["description"] = ""
                changed = True
    if changed:
        _save(data)
        _log.info("Migrated glossary entries: added description field")


_migrate_npc_ids()
_migrate_glossary_descriptions()
