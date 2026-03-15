"""D&D Beyond character data fetching.

Pulls character info from the public D&D Beyond API (no auth required).
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests  # type: ignore

from log import get_logger

_log = get_logger("beyond")

_API_BASE = "https://character-service.dndbeyond.com/character/v5/character"

_ALIGNMENT_MAP = {
    1: "Lawful Good",
    2: "Neutral Good",
    3: "Chaotic Good",
    4: "Lawful Neutral",
    5: "True Neutral",
    6: "Chaotic Neutral",
    7: "Lawful Evil",
    8: "Neutral Evil",
    9: "Chaotic Evil",
}


def extract_character_id(url: str) -> Optional[str]:
    """Extract the numeric character ID from a D&D Beyond URL.

    Handles formats like:
      https://www.dndbeyond.com/characters/129265475
      https://www.dndbeyond.com/characters/129265475/builder
      https://dndbeyond.com/characters/129265475
    """
    m = re.search(r"dndbeyond\.com/characters/(\d+)", url)
    return m.group(1) if m else None


def _parse_classes(data: Dict[str, Any]) -> Tuple[str, str, int]:
    """Parse class info. Returns (class_name, subclass, total_level)."""
    classes = data.get("classes", [])
    if not classes:
        return ("", "", 1)

    total_level = 0
    class_parts = []
    subclass = ""

    for cls in classes:
        defn = cls.get("definition", {})
        name = defn.get("name", "")
        lvl = cls.get("level", 0)
        total_level += lvl

        sub_defn = cls.get("subclassDefinition")
        if sub_defn:
            sub_name = sub_defn.get("name", "")
            if sub_name:
                subclass = sub_name
                class_parts.append("{} ({}) {}".format(name, sub_name, lvl))
            else:
                class_parts.append("{} {}".format(name, lvl))
        else:
            class_parts.append("{} {}".format(name, lvl))

    class_name = " / ".join(class_parts) if class_parts else ""
    return (class_name, subclass, total_level or 1)


def _parse_stats(data: Dict[str, Any]) -> Dict[str, int]:
    """Parse ability scores from stats array."""
    stat_names = {1: "str", 2: "dex", 3: "con", 4: "int", 5: "wis", 6: "cha"}
    result = {}
    for stat in data.get("stats", []):
        stat_id = stat.get("id")
        value = stat.get("value")
        if stat_id in stat_names and value is not None:
            result[stat_names[stat_id]] = value

    # Apply bonus stats
    for stat in data.get("bonusStats", []):
        stat_id = stat.get("id")
        value = stat.get("value")
        if stat_id in stat_names and value:
            key = stat_names[stat_id]
            result[key] = result.get(key, 10) + value

    # Apply override stats
    for stat in data.get("overrideStats", []):
        stat_id = stat.get("id")
        value = stat.get("value")
        if stat_id in stat_names and value is not None:
            result[stat_names[stat_id]] = value

    return result


def _parse_spells(data: Dict[str, Any]) -> List[str]:
    """Extract spell names from classSpells and other sources."""
    spells = set()

    for class_spells in data.get("classSpells", []):
        for spell in class_spells.get("spells", []):
            defn = spell.get("definition", {})
            name = defn.get("name", "")
            if name:
                spells.add(name)

    # Also check race spells
    for spell in data.get("spells", {}).get("race", []):
        defn = spell.get("definition", {})
        name = defn.get("name", "")
        if name:
            spells.add(name)

    return sorted(spells)


def _parse_equipment(data: Dict[str, Any]) -> List[str]:
    """Extract equipped/notable equipment names."""
    items = []
    for item in data.get("inventory", []):
        defn = item.get("definition", {})
        name = defn.get("name", "")
        if not name:
            continue
        qty = item.get("quantity", 1)
        equipped = item.get("equipped", False)
        magic = defn.get("magic", False)
        # Include equipped items and magic items
        if equipped or magic:
            if qty > 1:
                items.append("{} (x{})".format(name, qty))
            else:
                items.append(name)
    return items


def _parse_backpack(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract full inventory with quantities and status."""
    items = []
    for item in data.get("inventory", []):
        defn = item.get("definition", {})
        name = defn.get("name", "")
        if not name:
            continue
        items.append({
            "name": name,
            "quantity": item.get("quantity", 1),
            "equipped": item.get("equipped", False),
            "magic": defn.get("magic", False),
        })
    return items


def _parse_currency(data: Dict[str, Any]) -> Dict[str, int]:
    """Extract currency (cp, sp, ep, gp, pp)."""
    currencies = data.get("currencies", {}) or {}
    return {
        "cp": currencies.get("cp", 0) or 0,
        "sp": currencies.get("sp", 0) or 0,
        "ep": currencies.get("ep", 0) or 0,
        "gp": currencies.get("gp", 0) or 0,
        "pp": currencies.get("pp", 0) or 0,
    }


def _parse_modifiers(data: Dict[str, Any], mod_type: str) -> List[str]:
    """Extract modifier names of a given type (proficiency, language, etc.)."""
    result = []  # type: List[str]
    modifiers = data.get("modifiers", {}) or {}
    for source in ("class", "race", "background", "item", "feat"):
        for mod in modifiers.get(source, []):
            if mod.get("type") == mod_type:
                friendly = mod.get("friendlySubtypeName", "") or mod.get("subType", "")
                if friendly and friendly not in result:
                    result.append(friendly)
    return result


def _parse_features(data: Dict[str, Any]) -> List[str]:
    """Extract class features and racial traits."""
    features = []  # type: List[str]
    modifiers = data.get("modifiers", {}) or {}
    for source in ("class", "race", "feat", "background"):
        for mod in modifiers.get(source, []):
            name = mod.get("friendlyTypeName", "")
            if not name:
                continue
            # Only include granted features, not simple bonuses
            if mod.get("type") in ("proficiency", "language", "resistance",
                                   "immunity", "vulnerability", "size",
                                   "bonus", "set"):
                continue
            if name not in features:
                features.append(name)
    # Also check explicit feats
    for feat in data.get("feats", []) or []:
        defn = feat.get("definition", {}) or {}
        name = defn.get("name", "")
        if name and name not in features:
            features.append(name)
    return features


def _parse_feats(data: Dict[str, Any]) -> List[str]:
    """Extract feat names."""
    feats = []  # type: List[str]
    for feat in data.get("feats", []) or []:
        defn = feat.get("definition", {}) or {}
        name = defn.get("name", "")
        if name and name not in feats:
            feats.append(name)
    return feats


def _parse_notes(data: Dict[str, Any]) -> Dict[str, str]:
    """Extract all character notes."""
    notes = data.get("notes", {}) or {}
    return {
        "backstory": notes.get("backstory", "") or "",
        "allies": notes.get("allies", "") or "",
        "enemies": notes.get("enemies", "") or "",
        "organizations": notes.get("organizations", "") or "",
        "other_notes": notes.get("otherNotes", "") or "",
        "personal_possessions": notes.get("personalPossessions", "") or "",
    }


def _parse_defenses(data: Dict[str, Any], key: str) -> List[str]:
    """Extract defense type names (resistances, immunities, etc.)."""
    return [str(d) for d in (data.get(key, []) or []) if d]


def fetch_beyond_character(beyond_url: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse character data from D&D Beyond.

    Returns a dict with parsed fields, or None on failure.
    The returned dict includes:
      name, race, class_name, subclass, level, background, alignment,
      backstory, appearance, personality_traits, ideals, bonds, flaws,
      ability_scores, hp, spells, equipment, avatar_url
    """
    char_id = extract_character_id(beyond_url)
    if not char_id:
        _log.error("Could not extract character ID from URL: %s", beyond_url)
        return None

    url = "{}/{}".format(_API_BASE, char_id)
    _log.info("Fetching D&D Beyond character %s", char_id)

    try:
        resp = requests.get(url, timeout=15, headers={
            "Accept": "application/json",
            "User-Agent": "Chronicles/1.0",
        })
        if resp.status_code == 403:
            msg = "Character is private or restricted on D&D Beyond. Make it public in your D&D Beyond settings."
            _log.error("D&D Beyond 403 Forbidden for %s: %s", char_id, msg)
            raise ValueError(msg)
        resp.raise_for_status()
    except requests.RequestException as e:
        _log.error("D&D Beyond API error: %s", e)
        return None

    body = resp.json()
    if not body.get("success"):
        _log.error("D&D Beyond API returned success=false: %s", body.get("message"))
        return None

    data = body.get("data", {})
    if not data:
        _log.error("D&D Beyond API returned empty data")
        return None

    class_name, subclass, level = _parse_classes(data)

    # Race
    race_obj = data.get("race", {})
    race = ""
    if isinstance(race_obj, dict):
        race = race_obj.get("fullName", "") or race_obj.get("baseName", "")
    elif isinstance(race_obj, str):
        race = race_obj

    # Background
    bg = data.get("background", {})
    background = ""
    if isinstance(bg, dict):
        defn = bg.get("definition", {})
        if isinstance(defn, dict):
            background = defn.get("name", "")

    # Alignment
    alignment = _ALIGNMENT_MAP.get(data.get("alignmentId", 0), "")

    # Notes (all categories)
    all_notes = _parse_notes(data)
    backstory = all_notes.get("backstory", "")

    # Traits
    traits = data.get("traits", {}) or {}
    personality_traits = traits.get("personalityTraits", "") or ""
    ideals = traits.get("ideals", "") or ""
    bonds = traits.get("bonds", "") or ""
    flaws = traits.get("flaws", "") or ""

    # Appearance
    appearance = {
        "hair": data.get("hair", "") or "",
        "eyes": data.get("eyes", "") or "",
        "skin": data.get("skin", "") or "",
        "height": data.get("height", "") or "",
        "weight": str(data.get("weight", "")) if data.get("weight") else "",
        "age": str(data.get("age", "")) if data.get("age") else "",
        "gender": data.get("gender", "") or "",
    }

    # Avatar URL
    decorations = data.get("decorations", {}) or {}
    avatar_url = decorations.get("avatarUrl", "") or data.get("avatarUrl", "") or ""

    # HP
    hp = data.get("baseHitPoints", 0) or 0

    # Speed
    base_speed = 30
    if isinstance(race_obj, dict):
        weight_speeds = race_obj.get("weightSpeeds", {}) or {}
        normal = weight_speeds.get("normal", {}) or {}
        base_speed = normal.get("walk", 30) or 30

    # Faith/Deity
    faith = data.get("faith", "") or ""

    result = {
        "name": data.get("name", ""),
        "race": race,
        "class_name": class_name,
        "subclass": subclass,
        "level": level,
        "background": background,
        "alignment": alignment,
        "backstory": backstory,
        "appearance": appearance,
        "personality_traits": personality_traits,
        "ideals": ideals,
        "bonds": bonds,
        "flaws": flaws,
        "ability_scores": _parse_stats(data),
        "hp": hp,
        "spells": _parse_spells(data),
        "equipment": _parse_equipment(data),
        "avatar_url": avatar_url,
        # New fields
        "notes": all_notes,
        "backpack": _parse_backpack(data),
        "currency": _parse_currency(data),
        "proficiencies": _parse_modifiers(data, "proficiency"),
        "languages": _parse_modifiers(data, "language"),
        "features": _parse_features(data),
        "feats": _parse_feats(data),
        "base_speed": base_speed,
        "resistances": _parse_defenses(data, "resistances"),
        "immunities": _parse_defenses(data, "immunities"),
        "vulnerabilities": _parse_defenses(data, "vulnerabilities"),
        "condition_immunities": _parse_defenses(data, "conditionImmunities"),
        "faith": faith,
    }

    _log.info(
        "Fetched D&D Beyond character: %s (%s %s, level %d)",
        result["name"], result["race"], result["class_name"], result["level"],
    )
    return result


def download_avatar(avatar_url: str, save_path: str) -> bool:
    """Download a character avatar image and save it locally."""
    if not avatar_url:
        return False
    try:
        resp = requests.get(avatar_url, timeout=15)
        resp.raise_for_status()
        out = Path(save_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.content)
        _log.info("Downloaded avatar to %s (%d bytes)", save_path, len(resp.content))
        return True
    except requests.RequestException as e:
        _log.error("Failed to download avatar: %s", e)
        return False
