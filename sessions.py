"""
Session registry — tracks all past sessions in ~/.config/dnd-whisperx/sessions.json
Each entry records paths to all generated outputs and session metadata.
"""
import json
import logging
import os
import pathlib
import shutil
from datetime import datetime
from typing import Optional

_log = logging.getLogger("dnd.sessions")

REGISTRY_FILE = pathlib.Path.home() / ".config" / "dnd-whisperx" / "sessions.json"


def _load() -> list:
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(sessions, force=False):
    # type: (list, bool) -> None
    """Save sessions list. Refuses to overwrite non-empty file with empty list
    unless force=True (used by delete_session). Creates .bak backup and uses
    atomic write (write to .tmp then os.replace)."""
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Guard: refuse to wipe non-empty data
    if not sessions and not force and REGISTRY_FILE.exists():
        try:
            existing = REGISTRY_FILE.read_text(encoding="utf-8").strip()
            if len(existing) > 2:  # more than "[]"
                _log.error(
                    "BLOCKED: attempted to save empty sessions list over %d bytes of data",
                    len(existing),
                )
                return
        except Exception:
            pass
    # Backup existing file before overwrite
    if REGISTRY_FILE.exists() and REGISTRY_FILE.stat().st_size > 0:
        bak = REGISTRY_FILE.with_suffix(".json.bak")
        try:
            shutil.copy2(str(REGISTRY_FILE), str(bak))
        except Exception:
            pass
    # Atomic write: write to .tmp then rename
    tmp = REGISTRY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sessions, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(REGISTRY_FILE))


def create_session_folder(
    campaign_name: str,
    season_number: int,
    date_override: Optional[str] = None,
) -> pathlib.Path:
    """Create and return a timestamped session folder under ~/Documents/DnD WhisperX.

    date_override — optional YYYY-MM-DD string; used when importing a past transcript
                    so the folder reflects the actual session date.
    """
    base = pathlib.Path.home() / "Documents" / "DnD WhisperX"
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in campaign_name).strip()
    safe = safe or "Campaign"
    ts = date_override if date_override else datetime.now().strftime("%Y-%m-%d_%H-%M")
    folder = base / safe / f"Season {season_number}" / ts
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def register_session(
    campaign_id: str,
    campaign_name: str,
    season_id: str,
    season_number: int,
    session_dir: str,
    character_names: list,
    audio_path: Optional[str] = None,
    date_override: Optional[str] = None,
) -> str:
    """Create a new session entry and return its ID."""
    sessions = _load()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    if date_override:
        try:
            entry_date = datetime.strptime(date_override, "%Y-%m-%d").isoformat()
        except ValueError:
            entry_date = datetime.now().isoformat()
    else:
        entry_date = datetime.now().isoformat()
    entry = {
        "id": session_id,
        "date": entry_date,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "season_id": season_id,
        "season_number": season_number,
        "character_names": character_names,
        "character_ids": [],
        "output_dir": session_dir,
        "audio_path": audio_path,
        "json_path": None,
        "txt_path": None,
        "srt_path": None,
        "summary_path": None,
        "dm_notes_path": None,
        "scenes_path": None,
        "timeline_path": None,
        "illustration_path": None,
        "glossary_path": None,
        "character_updates_path": None,
        "leaderboard_path": None,
        "locations_path": None,
        "npcs_path": None,
        "loot_path": None,
        "missions_path": None,
    }
    sessions.append(entry)
    _save(sessions)
    return session_id


def update_session(session_id: str, **fields) -> None:
    """Update fields on an existing session by ID."""
    sessions = _load()
    found = False
    for entry in sessions:
        if entry["id"] == session_id:
            entry.update(fields)
            found = True
            break
    if found:
        _save(sessions)


def delete_session(session_id: str) -> Optional[str]:
    """Remove session from registry. Returns the output_dir of the deleted entry."""
    sessions = _load()
    for i, s in enumerate(sessions):
        if s["id"] == session_id:
            output_dir = s.get("output_dir")
            sessions.pop(i)
            _save(sessions, force=True)
            return output_dir
    return None


def get_sessions() -> list:
    """Return all sessions newest-first."""
    return list(reversed(_load()))


def get_session_by_id(session_id):
    # type: (str) -> Optional[dict]
    """Return a single session by ID, or None if not found. Single disk read."""
    for s in _load():
        if s.get("id") == session_id:
            return s
    return None


def get_campaign_session_count(campaign_id: str) -> int:
    """Count completed sessions for a campaign (those with a txt_path)."""
    sessions = _load()
    return sum(
        1 for s in sessions
        if s.get("campaign_id") == campaign_id and s.get("txt_path")
    )
