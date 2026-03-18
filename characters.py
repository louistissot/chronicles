"""Global character registry — persisted at ~/.config/dnd-whisperx/characters.json

Characters exist independently of campaigns. Campaigns reference characters by ID.
Each character optionally links to a D&D Beyond profile for auto-sync.
"""
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from log import get_logger

_log = get_logger("characters")
_CHARACTERS_FILE = Path.home() / ".config" / "dnd-whisperx" / "characters.json"
_CHARACTERS_DIR = Path.home() / ".config" / "dnd-whisperx" / "characters"


def _load() -> List[dict]:
    if _CHARACTERS_FILE.exists():
        try:
            data = json.loads(_CHARACTERS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("characters", [])
            if isinstance(data, list):
                return data
        except Exception as e:
            _log.error("Failed to load characters file: %s", e)
    return []


def _save(characters, force=False):
    # type: (List[dict], bool) -> None
    """Save characters list with atomic write and empty-data guard."""
    _CHARACTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Guard: refuse to wipe non-empty data
    if not characters and not force and _CHARACTERS_FILE.exists():
        try:
            existing = _CHARACTERS_FILE.read_text(encoding="utf-8").strip()
            if len(existing) > 20:  # more than '{"characters": []}'
                _log.error(
                    "BLOCKED: attempted to save empty characters over %d bytes of data",
                    len(existing),
                )
                return
        except Exception:
            pass
    # Backup existing file
    if _CHARACTERS_FILE.exists() and _CHARACTERS_FILE.stat().st_size > 0:
        bak = _CHARACTERS_FILE.with_suffix(".json.bak")
        try:
            shutil.copy2(str(_CHARACTERS_FILE), str(bak))
        except Exception:
            pass
    # Atomic write
    tmp = _CHARACTERS_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"characters": characters}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(str(tmp), str(_CHARACTERS_FILE))


def _char_dir(char_id: str) -> Path:
    """Return per-character storage directory (for avatar/portrait images)."""
    d = _CHARACTERS_DIR / char_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_characters() -> List[dict]:
    return _load()


def get_character(char_id: str) -> Optional[dict]:
    for c in _load():
        if c["id"] == char_id:
            return c
    return None


def get_characters_by_ids(char_ids: List[str]) -> List[dict]:
    """Return characters matching the given IDs, preserving order."""
    chars = {c["id"]: c for c in _load()}
    return [chars[cid] for cid in char_ids if cid in chars]


def character_names_from_ids(char_ids: List[str]) -> List[str]:
    """Resolve character IDs to names."""
    return [c["name"] for c in get_characters_by_ids(char_ids) if c.get("name")]


def create_character(
    name: str,
    race: str = "",
    class_name: str = "",
    subclass: str = "",
    level: int = 1,
    specialty: str = "",
    beyond_url: str = "",
    portrait_path: str = "",
) -> dict:
    """Create a new global character and return it."""
    char_id = str(uuid.uuid4())
    character = {
        "id": char_id,
        "name": name,
        "race": race,
        "class_name": class_name,
        "subclass": subclass,
        "level": level,
        "specialty": specialty,
        "beyond_url": beyond_url,
        "beyond_avatar_path": "",
        "portrait_path": portrait_path,
        "portraits": [],
        "fullbody_path": "",
        "fullbodies": [],
        "beyond_data": {},
        "beyond_last_synced": "",
        "history": [],
        "history_summary": "",
        "is_dm": name.lower() in ("dm", "dungeon master"),
        "is_npc": False,
        "npc_description": "",
        "campaign_ids": [],
    }
    characters = _load()
    characters.append(character)
    _save(characters)
    _log.info("Created character '%s' (id=%s)", name, char_id)
    return character


def update_character(char_id: str, **fields) -> Optional[dict]:
    """Update fields on a character. Returns updated character or None."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            c.update(fields)
            _save(characters)
            _log.info("Updated character '%s' fields=%s", c.get("name"), list(fields.keys()))
            return c
    _log.error("update_character: character %s not found", char_id)
    return None


def delete_character(char_id: str) -> bool:
    """Delete a character from the global registry."""
    characters = _load()
    before = len(characters)
    characters = [c for c in characters if c["id"] != char_id]
    if len(characters) < before:
        _save(characters, force=True)
        # Clean up character directory
        char_dir = _CHARACTERS_DIR / char_id
        if char_dir.exists():
            shutil.rmtree(char_dir, ignore_errors=True)
        _log.info("Deleted character %s", char_id)
        return True
    return False


def add_history_entry(
    char_id: str,
    session_id: str,
    session_date: str,
    campaign_name: str,
    season_number: int,
    auto_text: str,
    manual_text: str = "",
) -> bool:
    """Append a history entry for a character after a session."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            history = c.get("history", [])
            # Don't duplicate entries for the same session
            if any(h.get("session_id") == session_id for h in history):
                # Update existing entry
                for h in history:
                    if h["session_id"] == session_id:
                        h["auto_text"] = auto_text
                        if manual_text:
                            h["manual_text"] = manual_text
                        break
            else:
                history.append({
                    "session_id": session_id,
                    "session_date": session_date,
                    "campaign_name": campaign_name,
                    "season_number": season_number,
                    "auto_text": auto_text,
                    "manual_text": manual_text,
                })
            c["history"] = history
            _save(characters)
            _log.info("Added history entry for character '%s' session=%s", c.get("name"), session_id)
            return True
    return False


def update_history_manual_text(char_id: str, session_id: str, manual_text: str) -> bool:
    """Update the manual_text field of a specific history entry."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            for h in c.get("history", []):
                if h["session_id"] == session_id:
                    h["manual_text"] = manual_text
                    _save(characters)
                    return True
    return False


def update_history_auto_text(char_id: str, session_id: str, auto_text: str) -> bool:
    """Update the auto_text field of a specific history entry."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            for h in c.get("history", []):
                if h["session_id"] == session_id:
                    h["auto_text"] = auto_text
                    _save(characters)
                    return True
    return False


def set_history_summary(char_id: str, summary: str) -> bool:
    """Set the condensed history summary for a character."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            c["history_summary"] = summary
            _save(characters)
            return True
    return False


def set_beyond_data(
    char_id: str,
    beyond_data: Dict[str, Any],
    avatar_path: str = "",
    synced_at: str = "",
) -> Optional[dict]:
    """Update cached D&D Beyond data and optionally the avatar path."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            c["beyond_data"] = beyond_data
            if avatar_path:
                c["beyond_avatar_path"] = avatar_path
            if synced_at:
                c["beyond_last_synced"] = synced_at
            # Also update top-level fields from beyond_data if present
            if beyond_data.get("name"):
                c["name"] = beyond_data["name"]
            if beyond_data.get("race"):
                c["race"] = beyond_data["race"]
            if beyond_data.get("class_name"):
                c["class_name"] = beyond_data["class_name"]
            if beyond_data.get("subclass"):
                c["subclass"] = beyond_data["subclass"]
            if beyond_data.get("level") is not None:
                c["level"] = beyond_data["level"]
            _save(characters)
            _log.info("Updated beyond_data for character '%s'", c.get("name"))
            return c
    return None


def migrate_from_campaign_chars(chars: List[Any]) -> List[str]:
    """Migrate old campaign-embedded characters to global registry.

    Takes a list of old-format characters (strings or dicts with name/race/class_name/portrait)
    and creates global character entries for any that don't already exist.
    Returns a list of character IDs.
    """
    existing = _load()
    existing_names = {c["name"].lower(): c["id"] for c in existing if c.get("name")}
    char_ids = []

    for c in chars:
        if isinstance(c, str):
            name = c
            race = ""
            class_name = ""
            portrait = ""
        elif isinstance(c, dict):
            name = c.get("name", "")
            race = c.get("race", "")
            class_name = c.get("class_name", "")
            portrait = c.get("portrait", "")
        else:
            name = str(c)
            race = ""
            class_name = ""
            portrait = ""

        if not name:
            continue

        # Skip placeholder speaker names from WhisperX
        if re.match(r"^SPEAKER_\d+$", name):
            continue

        # Check if character already exists by name (case-insensitive)
        if name.lower() in existing_names:
            char_ids.append(existing_names[name.lower()])
        else:
            new_char = create_character(
                name=name,
                race=race,
                class_name=class_name,
                portrait_path=portrait,
            )
            existing_names[name.lower()] = new_char["id"]
            existing = _load()  # Reload after create
            char_ids.append(new_char["id"])

    return char_ids


def add_portrait(char_id, portrait_path, set_primary=True):
    # type: (str, str, bool) -> Optional[dict]
    """Add a portrait to a character's gallery. Optionally set as primary."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            portraits = c.get("portraits", [])
            # Don't add duplicate paths
            if any(p.get("path") == portrait_path for p in portraits):
                if set_primary:
                    for p in portraits:
                        p["is_primary"] = (p["path"] == portrait_path)
                    c["portrait_path"] = portrait_path
                    _save(characters)
                return c
            entry = {"path": portrait_path, "is_primary": set_primary}
            if set_primary:
                for p in portraits:
                    p["is_primary"] = False
                c["portrait_path"] = portrait_path
            portraits.append(entry)
            c["portraits"] = portraits
            _save(characters)
            _log.info("Added portrait for character '%s': %s (primary=%s)",
                       c.get("name"), portrait_path, set_primary)
            return c
    return None


def set_primary_portrait(char_id, portrait_path):
    # type: (str, str) -> Optional[dict]
    """Set a portrait as the primary for a character."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            portraits = c.get("portraits", [])
            found = False
            for p in portraits:
                if p["path"] == portrait_path:
                    p["is_primary"] = True
                    found = True
                else:
                    p["is_primary"] = False
            if found:
                c["portrait_path"] = portrait_path
                _save(characters)
                _log.info("Set primary portrait for '%s': %s", c.get("name"), portrait_path)
                return c
    return None


def delete_portrait(char_id, portrait_path):
    # type: (str, str) -> Optional[dict]
    """Remove a portrait from a character's gallery."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            portraits = c.get("portraits", [])
            was_primary = any(p.get("path") == portrait_path and p.get("is_primary") for p in portraits)
            portraits = [p for p in portraits if p.get("path") != portrait_path]
            c["portraits"] = portraits
            # If we deleted the primary, set the first remaining as primary
            if was_primary:
                if portraits:
                    portraits[0]["is_primary"] = True
                    c["portrait_path"] = portraits[0]["path"]
                else:
                    c["portrait_path"] = ""
            # Delete the file
            p = Path(portrait_path)
            if p.exists():
                p.unlink()
                _log.info("Deleted portrait file: %s", portrait_path)
            _save(characters)
            return c
    return None


def _migrate_portraits() -> None:
    """Ensure all characters have a portraits list. Migrate existing portrait_path."""
    characters = _load()
    changed = False
    for c in characters:
        if "portraits" not in c:
            c["portraits"] = []
            if c.get("portrait_path"):
                c["portraits"].append({"path": c["portrait_path"], "is_primary": True})
            changed = True
    if changed:
        _save(characters)
        _log.info("Migrated portraits list on characters")


def get_dm_character() -> Optional[dict]:
    """Return the first character with is_dm=True, or None."""
    for c in _load():
        if c.get("is_dm"):
            return c
    return None


# ---------------------------------------------------------------------------
# Full-body gallery CRUD (mirrors portrait gallery)
# ---------------------------------------------------------------------------

def add_fullbody(char_id, fullbody_path, set_primary=True):
    # type: (str, str, bool) -> Optional[dict]
    """Add a full-body image to a character's gallery. Optionally set as primary."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            fullbodies = c.get("fullbodies", [])
            if any(f.get("path") == fullbody_path for f in fullbodies):
                if set_primary:
                    for f in fullbodies:
                        f["is_primary"] = (f["path"] == fullbody_path)
                    c["fullbody_path"] = fullbody_path
                    _save(characters)
                return c
            entry = {"path": fullbody_path, "is_primary": set_primary}
            if set_primary:
                for f in fullbodies:
                    f["is_primary"] = False
                c["fullbody_path"] = fullbody_path
            fullbodies.append(entry)
            c["fullbodies"] = fullbodies
            _save(characters)
            _log.info("Added fullbody for character '%s': %s (primary=%s)",
                       c.get("name"), fullbody_path, set_primary)
            return c
    return None


def set_primary_fullbody(char_id, fullbody_path):
    # type: (str, str) -> Optional[dict]
    """Set a full-body image as the primary for a character."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            fullbodies = c.get("fullbodies", [])
            found = False
            for f in fullbodies:
                if f["path"] == fullbody_path:
                    f["is_primary"] = True
                    found = True
                else:
                    f["is_primary"] = False
            if found:
                c["fullbody_path"] = fullbody_path
                _save(characters)
                _log.info("Set primary fullbody for '%s': %s", c.get("name"), fullbody_path)
                return c
    return None


def delete_fullbody(char_id, fullbody_path):
    # type: (str, str) -> Optional[dict]
    """Remove a full-body image from a character's gallery."""
    characters = _load()
    for c in characters:
        if c["id"] == char_id:
            fullbodies = c.get("fullbodies", [])
            was_primary = any(f.get("path") == fullbody_path and f.get("is_primary") for f in fullbodies)
            fullbodies = [f for f in fullbodies if f.get("path") != fullbody_path]
            c["fullbodies"] = fullbodies
            if was_primary:
                if fullbodies:
                    fullbodies[0]["is_primary"] = True
                    c["fullbody_path"] = fullbodies[0]["path"]
                else:
                    c["fullbody_path"] = ""
            p = Path(fullbody_path)
            if p.exists():
                p.unlink()
                _log.info("Deleted fullbody file: %s", fullbody_path)
            _save(characters)
            return c
    return None


# ---------------------------------------------------------------------------
# NPC helpers
# ---------------------------------------------------------------------------

def create_npc(name, description="", campaign_id="", race="", role="",
               attitude="", current_status=""):
    # type: (str, str, str, str, str, str, str) -> dict
    """Create an NPC character with optional enriched fields. Returns the new character dict."""
    char = create_character(name=name)
    # Set NPC-specific fields
    characters = _load()
    for c in characters:
        if c["id"] == char["id"]:
            c["is_npc"] = True
            c["npc_description"] = description
            c["campaign_ids"] = [campaign_id] if campaign_id else []
            c["npc_race"] = race
            c["npc_role"] = role
            c["npc_attitude"] = attitude
            c["npc_current_status"] = current_status
            c["npc_session_history"] = []
            _save(characters)
            _log.info("Created NPC '%s' (id=%s)", name, char["id"])
            return c
    return char


def get_npcs(campaign_id=None):
    # type: (Optional[str]) -> List[dict]
    """Return all NPC characters, optionally filtered by campaign_id."""
    characters = _load()
    npcs = [c for c in characters if c.get("is_npc")]
    if campaign_id:
        npcs = [c for c in npcs if campaign_id in c.get("campaign_ids", [])]
    return npcs


def update_npc_description(char_id, description):
    # type: (str, str) -> Optional[dict]
    """Update an NPC's description. Returns updated character or None."""
    return update_character(char_id, npc_description=description)


def find_npc_by_name(name, campaign_id=None):
    # type: (str, Optional[str]) -> Optional[dict]
    """Find an NPC by name (case-insensitive). Returns character or None."""
    name_lower = name.lower().strip()
    for c in get_npcs(campaign_id):
        if c.get("name", "").lower().strip() == name_lower:
            return c
    return None


def enrich_npc(char_id, session_id="", session_date="", race="", role="",
               description="", attitude="", actions="", current_status="",
               campaign_id=""):
    # type: (str, str, str, str, str, str, str, str, str, str) -> Optional[dict]
    """Enrich an existing NPC with rich session data.

    - Keeps longest npc_description
    - Updates npc_race/npc_role if new value is longer
    - Always updates npc_attitude and npc_current_status (latest session wins)
    - Appends session snapshot to npc_session_history
    - Adds campaign_id to campaign_ids if not already there
    """
    characters = _load()
    for c in characters:
        if c["id"] != char_id:
            continue
        # Description: keep the longest
        if description and len(description) > len(c.get("npc_description", "")):
            c["npc_description"] = description
        # Race/role: keep the longest (richer)
        if race and len(race) > len(c.get("npc_race", "")):
            c["npc_race"] = race
        if role and len(role) > len(c.get("npc_role", "")):
            c["npc_role"] = role
        # Attitude + status: latest session always wins
        if attitude:
            c["npc_attitude"] = attitude
        if current_status:
            c["npc_current_status"] = current_status
        # Campaign linkage
        if campaign_id:
            cids = c.get("campaign_ids", [])
            if campaign_id not in cids:
                cids.append(campaign_id)
                c["campaign_ids"] = cids
        # Session history: append snapshot (avoid duplicates by session_id)
        history = c.get("npc_session_history", [])
        existing_ids = {h.get("session_id") for h in history}
        if session_id and session_id not in existing_ids:
            history.append({
                "session_id": session_id,
                "session_date": session_date,
                "actions": actions,
                "status": current_status,
                "attitude": attitude,
            })
            c["npc_session_history"] = history
        _save(characters)
        _log.info("Enriched NPC '%s' (id=%s) from session %s", c.get("name"), char_id, session_id)
        return c
    return None


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

def _migrate_dm_flag() -> None:
    """Ensure any character named 'DM' or 'Dungeon Master' has is_dm=True."""
    characters = _load()
    changed = False
    for c in characters:
        is_dm = c.get("name", "").lower() in ("dm", "dungeon master")
        if is_dm and not c.get("is_dm"):
            c["is_dm"] = is_dm
            changed = True
        elif "is_dm" not in c:
            c["is_dm"] = False
            changed = True
    if changed:
        _save(characters)
        _log.info("Migrated is_dm flag on characters")


def _migrate_fullbodies() -> None:
    """Ensure all characters have fullbodies list and fullbody_path."""
    characters = _load()
    changed = False
    for c in characters:
        if "fullbodies" not in c:
            c["fullbodies"] = []
            changed = True
        if "fullbody_path" not in c:
            c["fullbody_path"] = ""
            changed = True
    if changed:
        _save(characters)
        _log.info("Migrated fullbodies fields on characters")


def _migrate_npc_fields() -> None:
    """Ensure all characters have NPC-related fields."""
    characters = _load()
    changed = False
    for c in characters:
        if "is_npc" not in c:
            c["is_npc"] = False
            changed = True
        if "npc_description" not in c:
            c["npc_description"] = ""
            changed = True
        if "campaign_ids" not in c:
            c["campaign_ids"] = []
            changed = True
        # Enriched NPC fields (v2)
        if "npc_race" not in c:
            c["npc_race"] = ""
            changed = True
        if "npc_role" not in c:
            c["npc_role"] = ""
            changed = True
        if "npc_attitude" not in c:
            c["npc_attitude"] = ""
            changed = True
        if "npc_current_status" not in c:
            c["npc_current_status"] = ""
            changed = True
        if "npc_session_history" not in c:
            c["npc_session_history"] = []
            changed = True
    if changed:
        _save(characters)
        _log.info("Migrated NPC fields on characters")


# Run migrations on module load
_migrate_dm_flag()
_migrate_portraits()
_migrate_fullbodies()
_migrate_npc_fields()
