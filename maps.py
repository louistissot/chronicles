"""Campaign map persistence.

Stores LLM-generated map layouts (node positions, edges, planes) per campaign.
Storage: ~/.config/dnd-whisperx/maps/<campaign_id>.json
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

_log = logging.getLogger("dnd.maps")

_MAPS_DIR = Path.home() / ".config" / "dnd-whisperx" / "maps"
_MAPS_DIR.mkdir(parents=True, exist_ok=True)


def _map_file(campaign_id):
    # type: (str) -> Path
    return _MAPS_DIR / "{}.json".format(campaign_id)


def load_map(campaign_id):
    # type: (str) -> Optional[dict]
    """Load saved map data for a campaign, or None if not generated yet."""
    path = _map_file(campaign_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        _log.error("Failed to load map for campaign %s: %s", campaign_id, e)
        return None


def save_map(campaign_id, data):
    # type: (str, dict) -> None
    """Atomically save map data for a campaign."""
    path = _map_file(campaign_id)
    # Backup existing
    if path.exists():
        bak = path.with_suffix(".json.bak")
        try:
            bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    # Atomic write
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(path))
    _log.info("Saved map for campaign %s (%d nodes, %d edges)",
              campaign_id, len(data.get("nodes", [])), len(data.get("edges", [])))


def update_node_positions(campaign_id, positions):
    # type: (str, Dict[str, Dict[str, float]]) -> bool
    """Update specific node positions without regenerating. Returns True on success."""
    data = load_map(campaign_id)
    if not data:
        _log.warning("update_node_positions: no map found for campaign %s", campaign_id)
        return False
    nodes = data.get("nodes", [])
    name_to_idx = {n["name"]: i for i, n in enumerate(nodes)}
    updated = 0
    for name, pos in positions.items():
        idx = name_to_idx.get(name)
        if idx is not None:
            nodes[idx]["x"] = pos.get("x", nodes[idx]["x"])
            nodes[idx]["y"] = pos.get("y", nodes[idx]["y"])
            updated += 1
    if updated:
        save_map(campaign_id, data)
        _log.info("Updated %d node positions for campaign %s", updated, campaign_id)
    return True


def update_map_rotation(campaign_id, rotation):
    # type: (str, float) -> bool
    """Persist map rotation angle (degrees). Returns True on success."""
    data = load_map(campaign_id)
    if not data:
        _log.warning("update_map_rotation: no map found for campaign %s", campaign_id)
        return False
    data["rotation"] = rotation
    save_map(campaign_id, data)
    _log.info("Updated rotation to %.1f° for campaign %s", rotation, campaign_id)
    return True
