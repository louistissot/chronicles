"""
Post-process WhisperX JSON output:
  - Replace SPEAKER_XX labels with character names
  - Write a human-readable .txt transcript
  - Write a .srt subtitle file
  - Extract speaker samples for the review UI
  - Correct misspelled proper nouns using glossary terms
"""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


def load_json(json_path: Union[str, Path]) -> dict:
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def get_speakers(data: dict) -> List[str]:
    """Return sorted list of unique speaker IDs found in the JSON."""
    seen = set()
    for seg in data.get("segments", []):
        sp = seg.get("speaker")
        if sp:
            seen.add(sp)
    return sorted(seen)


def get_speaker_samples(data: dict, n_samples: int = 5) -> Dict[str, List[str]]:
    """Return up to n_samples transcript lines per speaker.

    Selects the longest lines (filtered to >= 4 words) to give the LLM
    the most identifying content. Falls back to all lines if a speaker
    only has very short utterances.
    """
    all_segs: Dict[str, List[str]] = {}
    for seg in data.get("segments", []):
        sp = seg.get("speaker")
        text = seg.get("text", "").strip()
        if not sp or not text:
            continue
        all_segs.setdefault(sp, []).append(text)

    result: Dict[str, List[str]] = {}
    for sp, texts in all_segs.items():
        meaningful = [t for t in texts if len(t.split()) >= 4]
        if not meaningful:
            meaningful = texts  # fallback: speaker only has short lines
        meaningful.sort(key=len, reverse=True)
        result[sp] = meaningful[:n_samples]
    return result


def get_name_mention_segments(
    data: dict,
    character_names: List[str],
    max_per_speaker: int = 3,
) -> Dict[str, List[str]]:
    """Return segments where the speaker mentions a character name.

    These 'naming events' (e.g. 'Your turn Aphelios', 'Nice work Khuzz!')
    give the LLM strong cross-reference clues: the speaker is likely the DM
    or a player addressing a named participant.
    """
    name_tokens = [n.split()[0].lower() for n in character_names if n.strip()]
    mentions: Dict[str, List[str]] = {}
    for seg in data.get("segments", []):
        sp = seg.get("speaker")
        text = seg.get("text", "").strip()
        if not sp or not text:
            continue
        text_lower = text.lower()
        if any(tok in text_lower for tok in name_tokens):
            bucket = mentions.setdefault(sp, [])
            if len(bucket) < max_per_speaker:
                bucket.append(text)
    return mentions


def get_review_samples(
    data,           # type: dict
    character_names,  # type: List[str]
    glossary_terms=None,  # type: Optional[List[str]]
    n_samples=5,    # type: int
):
    # type: (...) -> Dict[str, List[str]]
    """Return review-quality samples per speaker for manual identification.

    Filters to lines with >= 5 words, UNLESS the line contains a character
    name or glossary term (case-insensitive). Falls back to all lines if a
    speaker has no qualifying lines.
    """
    # Build lowercase match tokens
    name_tokens = [n.split()[0].lower() for n in character_names if n.strip()]
    glossary_tokens = []  # type: List[str]
    if glossary_terms:
        glossary_tokens = [t.lower() for t in glossary_terms if t.strip()]

    all_segs = {}  # type: Dict[str, List[str]]
    for seg in data.get("segments", []):
        sp = seg.get("speaker")
        text = seg.get("text", "").strip()
        if not sp or not text:
            continue
        all_segs.setdefault(sp, []).append(text)

    result = {}  # type: Dict[str, List[str]]
    for sp, texts in all_segs.items():
        qualifying = []  # type: List[str]
        for t in texts:
            word_count = len(t.split())
            if word_count >= 5:
                qualifying.append(t)
            else:
                # Short line — keep only if it contains a name or glossary term
                t_lower = t.lower()
                if any(tok in t_lower for tok in name_tokens):
                    qualifying.append(t)
                elif any(tok in t_lower for tok in glossary_tokens):
                    qualifying.append(t)
        if not qualifying:
            qualifying = texts  # fallback
        qualifying.sort(key=len, reverse=True)
        result[sp] = qualifying[:n_samples]
    return result


def apply_mapping(data: dict, mapping: Dict[str, str]) -> dict:
    """Replace speaker IDs with character names in a copy of the data."""
    import copy
    out = copy.deepcopy(data)
    for seg in out.get("segments", []):
        sp = seg.get("speaker")
        if sp and sp in mapping:
            seg["speaker"] = mapping[sp]
    return out


def _format_mm_ss(seconds: float) -> str:
    """Format seconds as MM:SS for transcript timestamps."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def write_transcript(data: dict, out_path: Union[str, Path]) -> None:
    """Write a plain-text transcript grouped by speaker turns with timestamps.

    Handles non-diarized transcripts: segments without a 'speaker' key
    are emitted as plain text without speaker headers.
    """
    out_path = Path(out_path)
    lines = []  # type: List[str]
    prev_speaker = None
    for seg in data.get("segments", []):
        sp = seg.get("speaker")  # May be None for non-diarized
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = seg.get("start")
        if sp is None:
            # Non-diarized: emit plain text without speaker header
            lines.append(text)
            prev_speaker = None
        elif sp != prev_speaker:
            ts = f" ({_format_mm_ss(start)})" if start is not None else ""
            lines.append(f"\n[{sp}]{ts}")
            lines.append(text)
            prev_speaker = sp
        else:
            lines.append(text)
    out_path.write_text("\n".join(lines).lstrip("\n"), encoding="utf-8")


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(data: dict, out_path: Union[str, Path]) -> None:
    """Write an SRT subtitle file with optional speaker labels.

    Non-diarized segments (no 'speaker' key) are written without a label prefix.
    """
    out_path = Path(out_path)
    entries = []  # type: List[str]
    idx = 1
    for seg in data.get("segments", []):
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)
        sp = seg.get("speaker")  # May be None for non-diarized
        text = seg.get("text", "").strip()
        if not text:
            continue
        label = "[{}] ".format(sp) if sp else ""
        entries.append(
            f"{idx}\n"
            f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n"
            f"{label}{text}\n"
        )
        idx += 1
    out_path.write_text("\n".join(entries), encoding="utf-8")


def save_all(
    json_path: Union[str, Path],
    mapping: Dict[str, str],
    output_dir: Optional[Union[str, Path]] = None,
    write_txt: bool = True,
    do_srt: bool = True,
) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Load JSON, apply mapping, write transcript files.
    Returns (txt_path, srt_path) — each may be None if not written.
    """
    json_path = Path(json_path)
    if output_dir is None:
        output_dir = json_path.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_json(json_path)
    mapped = apply_mapping(data, mapping)

    stem = json_path.stem
    txt_path = None
    srt_path = None

    if write_txt:
        txt_path = output_dir / f"{stem}_transcript.txt"
        write_transcript(mapped, txt_path)

    if do_srt:
        srt_path = output_dir / f"{stem}_transcript.srt"
        write_srt(mapped, srt_path)

    return txt_path, srt_path


def correct_transcript_terms(data, glossary_terms, character_names):
    # type: (dict, List[str], List[str]) -> Tuple[dict, Dict[str, str]]
    """Correct misspelled proper nouns in WhisperX transcript using glossary + character names.

    Uses fuzzy matching (difflib.SequenceMatcher) to find and fix words that are
    close to known terms. Only corrects when there's exactly one close match
    (no ambiguity) and the term is at least 4 characters long.

    Args:
        data: WhisperX JSON dict with 'segments' list.
        glossary_terms: List of known glossary term strings.
        character_names: List of character name strings.

    Returns:
        (corrected_data, corrections_log) where corrections_log maps
        original_word -> corrected_term for all corrections applied.
    """
    import copy

    # Build the combined term list (unique, case-preserved)
    all_terms = []  # type: List[str]
    seen_lower = set()  # type: set
    for t in list(glossary_terms) + list(character_names):
        t = t.strip()
        if t and t.lower() not in seen_lower:
            all_terms.append(t)
            seen_lower.add(t.lower())

    if not all_terms:
        return data, {}

    # Pre-build lowercase lookup for exact match check
    term_lower_map = {t.lower(): t for t in all_terms}

    # Common English words that should never be "corrected" to a glossary term
    _COMMON_WORDS = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
        "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
        "how", "its", "may", "old", "see", "way", "who", "did", "let", "say",
        "she", "too", "use", "that", "this", "with", "have", "from", "they",
        "been", "said", "each", "make", "like", "long", "look", "many", "some",
        "them", "than", "will", "into", "just", "over", "such", "take", "come",
        "could", "would", "about", "after", "other", "their", "there", "these",
        "which", "being", "where", "first", "found", "going", "great", "house",
        "right", "still", "think", "those", "under", "water", "world", "never",
        "sword", "spell", "magic", "staff", "armor", "arrow", "blade", "cloak",
        "demon", "dwarf", "flame", "ghost", "giant", "guard", "horse", "human",
        "knife", "mount", "night", "oaken", "potion", "power", "queen", "river",
        "rogue", "royal", "scout", "shade", "shield", "skull", "snake", "spear",
        "stone", "storm", "tower", "torch", "troll", "tribe", "woods", "beast",
        "blood", "chest", "creek", "crown", "death", "earth", "feast", "fight",
        "frost", "grave", "guild", "heart", "light", "north", "ocean", "party",
        "south", "steel", "sworn", "thief", "trail", "wrath", "taken", "thing",
        "three", "until", "while", "again", "along", "below", "every", "large",
        "place", "small", "above", "might", "point", "given", "group", "young",
        "goblin", "dragon", "attack", "damage", "castle", "temple", "forest",
        "tavern", "weapon", "battle", "archer", "bandit", "cleric", "druid",
        "ranger", "wizard", "kobold", "priest", "spirit",
    }

    # Build n-gram sets for multi-word terms (bigrams, trigrams)
    multi_word_terms = [t for t in all_terms if len(t.split()) > 1]
    single_word_terms = [t for t in all_terms if len(t.split()) == 1]

    MIN_TERM_LEN = 4
    THRESHOLD = 0.80

    corrections = {}  # type: Dict[str, str]
    out = copy.deepcopy(data)

    for seg in out.get("segments", []):
        text = seg.get("text", "")
        if not text:
            continue

        # Phase 1: Multi-word term correction (bigrams/trigrams)
        for term in multi_word_terms:
            if len(term) < MIN_TERM_LEN:
                continue
            # Use regex to find approximate matches for multi-word terms
            words = text.split()
            term_words = term.split()
            n = len(term_words)
            if len(words) < n:
                continue
            for i in range(len(words) - n + 1):
                candidate = " ".join(words[i:i + n])
                # Skip if already exact match
                if candidate.lower() == term.lower():
                    continue
                ratio = SequenceMatcher(None, candidate.lower(), term.lower()).ratio()
                if ratio >= THRESHOLD:
                    # Replace in text preserving surrounding context
                    text = text.replace(candidate, term, 1)
                    corrections[candidate] = term

        # Phase 2: Single-word term correction
        words = text.split()
        corrected_words = []  # type: List[str]
        for word in words:
            # Strip punctuation for matching but preserve it
            stripped = re.sub(r'[^\w]', '', word)
            if len(stripped) < MIN_TERM_LEN:
                corrected_words.append(word)
                continue

            # Skip if it's already an exact match
            if stripped.lower() in term_lower_map:
                corrected_words.append(word)
                continue

            # Skip common English / D&D generic words
            if stripped.lower() in _COMMON_WORDS:
                corrected_words.append(word)
                continue

            # Find fuzzy matches
            best_match = None  # type: Optional[str]
            best_ratio = 0.0
            match_count = 0
            for term in single_word_terms:
                if len(term) < MIN_TERM_LEN:
                    continue
                ratio = SequenceMatcher(None, stripped.lower(), term.lower()).ratio()
                if ratio >= THRESHOLD:
                    match_count += 1
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = term

            # Only correct if exactly one close match (no ambiguity)
            if match_count == 1 and best_match is not None:
                # Preserve original punctuation
                corrected = word.replace(stripped, best_match)
                if corrected != word:
                    corrections[stripped] = best_match
                    corrected_words.append(corrected)
                else:
                    corrected_words.append(word)
            else:
                corrected_words.append(word)

        seg["text"] = " ".join(corrected_words)

    return out, corrections
