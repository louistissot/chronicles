"""
LLM-assisted speaker mapping.
Given speaker samples and character names, returns a suggested mapping dict.
Supports both Anthropic and OpenAI via llm.call_llm.
"""
import json
from typing import Callable, Dict, List, Optional, Tuple

from llm import stream_llm


def _build_prompt(speakers_block: str, names_list: str, strict: bool = False) -> str:
    strictness = (
        "\n\nIMPORTANT: Your entire response must be ONLY the JSON object. "
        "No analysis, no explanation, no markdown. Start with { and end with }."
        if strict else ""
    )
    return f"""You are helping identify speakers in a Dungeons & Dragons session transcript.

The audio was transcribed and diarized, producing these speaker IDs with sample lines:

{speakers_block}

The session participants are: {names_list}

Map each SPEAKER_XX to one of the participant names and provide a confidence score (0-100).
- The DM (Dungeon Master) typically describes scenes, plays NPCs, and guides the story.
- Players react, ask questions, announce actions, or speak in character.
- Multiple speaker IDs can map to the same participant (diarization sometimes splits one person).
- If there are many more speaker IDs than participants, most IDs share a person — that is expected and normal.
- Use "Unknown" only if you truly cannot tell, with confidence 0.

Respond with ONLY a valid JSON object mapping every speaker ID to an object with "name", "confidence", and "evidence". Example:
{{"SPEAKER_00": {{"name": "Dungeon Master", "confidence": 95, "evidence": "Describes scenes, plays NPCs, uses game mechanics language"}}, "SPEAKER_01": {{"name": "Alice", "confidence": 85, "evidence": "References backstory about being a ranger, mentions their wolf companion"}}}}

- "evidence" = brief explanation of WHY you mapped this speaker to this name (speaking style, content references, character-specific knowledge)

Use exactly the names provided: {names_list}{strictness}
"""


def _extract_json(raw: str) -> Optional[dict]:
    """Pull the first complete JSON object out of a string. Returns None on failure."""
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None


def _parse_mapping_response(raw_mapping):
    # type: (dict) -> Tuple[Dict[str, str], Dict[str, int], Dict[str, str]]
    """Parse a mapping response that may have confidence scores or flat strings.

    Returns (name_mapping, confidence_mapping, evidence_mapping).
    """
    names = {}  # type: Dict[str, str]
    confidences = {}  # type: Dict[str, int]
    evidence = {}  # type: Dict[str, str]
    for speaker_id, val in raw_mapping.items():
        if isinstance(val, dict):
            names[speaker_id] = val.get("name", "Unknown")
            confidences[speaker_id] = int(val.get("confidence", 50))
            evidence[speaker_id] = val.get("evidence", "")
        else:
            # Flat string format (backward compat)
            names[speaker_id] = str(val)
            confidences[speaker_id] = 100  # no confidence data, assume high
            evidence[speaker_id] = ""
    return names, confidences, evidence


def suggest_mapping(
    speaker_samples: Dict[str, List[str]],
    character_names: List[str],
    api_key: str,
    provider: str = "anthropic",
    model: Optional[str] = None,
    on_chunk: Optional[Callable[[str], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
    name_mentions: Optional[Dict[str, List[str]]] = None,
    confidence_threshold: int = 90,
    extra_samples: Optional[Dict[str, List[str]]] = None,
    character_details: Optional[Dict[str, Dict]] = None,
    glossary_context: Optional[str] = None,
) -> Tuple[Dict[str, str], Dict[str, int], Dict[str, str]]:
    """
    Ask the LLM to suggest which SPEAKER_XX corresponds to which character name.
    Returns a tuple of (name_mapping, confidence_mapping, evidence_mapping).
    name_mapping: {"SPEAKER_00": "Gandalf", ...}
    confidence_mapping: {"SPEAKER_00": 95, ...}
    evidence_mapping: {"SPEAKER_00": "Describes scenes, uses DM language", ...}

    If extra_samples is provided, those are merged into speaker_samples for
    speakers that need more context (retry with more data).
    """
    merged_samples = dict(speaker_samples)
    if extra_samples:
        for sp, lines in extra_samples.items():
            existing = merged_samples.get(sp, [])
            # Deduplicate and extend
            seen = set(existing)
            merged_samples[sp] = existing + [l for l in lines if l not in seen]

    speakers_block = "\n\n".join(
        f"**{speaker_id}** sample lines:\n"
        + "\n".join(f"  - {line}" for line in lines)
        for speaker_id, lines in merged_samples.items()
    )
    names_list = ", ".join(character_names)
    # Scale tokens: confidence format is larger
    max_tok = max(1024, len(merged_samples) * 60 + 256)

    cross_ref = ""
    if name_mentions:
        lines = []
        for sp, texts in name_mentions.items():
            for t in texts:
                lines.append(f"  {sp} says: \"{t}\"")
        if lines:
            cross_ref = (
                "\n\nCross-reference clues (segments where a character name is mentioned):\n"
                + "\n".join(lines)
            )

    char_context = ""
    if character_details:
        ctx_lines = []
        for name, details in character_details.items():
            parts = []
            if details.get("race"):
                parts.append(details["race"])
            if details.get("class_name"):
                parts.append(details["class_name"])
            if details.get("backstory"):
                # Truncate long backstories
                bs = details["backstory"]
                if len(bs) > 300:
                    bs = bs[:300] + "..."
                parts.append("Backstory: " + bs)
            if details.get("personality_traits"):
                parts.append("Personality: " + details["personality_traits"])
            if details.get("spells"):
                spell_list = details["spells"]
                if isinstance(spell_list, list):
                    parts.append("Spells: " + ", ".join(spell_list[:10]))
            if details.get("equipment"):
                equip_list = details["equipment"]
                if isinstance(equip_list, list):
                    parts.append("Equipment: " + ", ".join(equip_list[:8]))
            if details.get("history_summary"):
                hs = details["history_summary"]
                if len(hs) > 200:
                    hs = hs[:200] + "..."
                parts.append("Character arc: " + hs)
            if details.get("recent_events"):
                re_list = details["recent_events"]
                if isinstance(re_list, list) and re_list:
                    parts.append("Recent sessions: " + " | ".join(re_list[:3]))
            if parts:
                ctx_lines.append("  **{}**: {}".format(name, "; ".join(parts)))
        if ctx_lines:
            char_context = (
                "\n\nCharacter profiles (use these to identify who is speaking — "
                "match speech content to backstory, spells, equipment, and personality):\n"
                + "\n".join(ctx_lines)
            )

    glossary_block = ""
    if glossary_context:
        glossary_block = (
            "\n\nCampaign glossary (key terms from this campaign — "
            "speakers may reference these names, locations, or items):\n"
            + glossary_context
        )

    for attempt, strict in enumerate([False, True]):
        prompt = _build_prompt(speakers_block, names_list, strict=strict) + cross_ref + char_context + glossary_block
        raw = stream_llm(
            prompt, provider=provider, api_key=api_key, model=model, max_tokens=max_tok,
            on_chunk=on_chunk if attempt == 0 else None,
            stop_check=stop_check,
        ).strip()

        raw_mapping = _extract_json(raw)
        if raw_mapping is not None:
            return _parse_mapping_response(raw_mapping)

    raise ValueError(f"LLM returned unexpected response: {raw[:200]}")
