# Chronicles — Codebase Guide

## What This Is

A macOS desktop app for DnD players. Records/imports session audio, runs WhisperX (speech-to-text + speaker diarization), maps speakers to characters, then generates structured artifacts (summary, DM notes, timeline, etc.) via an LLM pipeline. React frontend inside a pywebview window.

## How to Run / Package

```bash
# Dev
cd frontend && npm install && npm run build && cd ..
/Library/Developer/CommandLineTools/usr/bin/python3.9 main.py

# Frontend hot-reload (no Python backend, limited stubs)
cd frontend && npm run dev

# Package
/Users/louistissot/Library/Python/3.9/bin/pyinstaller DnDWhisperX.spec --clean --noconfirm
cp -R "dist/Chronicles.app" /Applications/
```

## Python Version Constraint — CRITICAL

**Python 3.9 only.** WhisperX is installed against this specific interpreter.

- Binary: `/Library/Developer/CommandLineTools/usr/bin/python3.9`
- PyInstaller: `/Users/louistissot/Library/Python/3.9/bin/pyinstaller`
- **Never use `str | None`** — use `Optional[str]` from `typing`. Same for `list[str]` → `List[str]`, `dict` → `Dict`.

## File Structure

```
main.py          Entry point. pywebview window + native macOS drag-drop via ObjC.
backend.py       API class exposed to JS. Full pipeline: transcription → speaker mapping → LLM stages → illustration.
image_gen.py     Gemini image generation (gemini-2.5-flash-image). Three functions:
                 generate_illustration() (16:9, fantasy wrapper), generate_portrait() (1:1), generate_fullbody() (2:3).
characters.py    Global character registry (~/.config/dnd-whisperx/characters.json). CRUD, history, D&D Beyond sync.
                 is_dm=True chars hidden from UI, auto-included in speaker mapping. NPC support (is_npc, campaign_ids).
beyond.py        D&D Beyond data fetching. Parses classes/races/stats/spells/equipment. ValueError on 403 (private).
sessions.py      Session registry (~/.config/dnd-whisperx/sessions.json). Atomic writes + backup + empty-write guard.
campaigns.py     Campaign + season registry. Seasons store character UUIDs referencing characters.json.
config.py        Token + prefs storage (prefs.json). Thread-safe with lock + atomic writes.
runner.py        Runs ffmpeg + whisperx CLI as subprocesses with streaming output.
postprocess.py   Parses WhisperX JSON. Speaker label replacement, .txt/.srt generation.
                 Fuzzy transcript correction: 0.70 threshold for character names, 0.80 for glossary terms.
llm.py           LLM abstraction. Routes to Anthropic (claude-sonnet-4-6) or OpenAI (gpt-4o). Blocking + streaming.
llm_mapper.py    LLM speaker→character mapping with confidence scores + evidence.
entities.py      Per-campaign entity registry (~/.config/dnd-whisperx/entities/<id>.json).
                 Tracks locations, items, missions, factions, spells, lore with history + relationships.
log.py           Rotating file logger → ~/.config/dnd-whisperx/app.log.
tests/           pytest suite. Run: python3.9 -m pytest tests/ -v
```

## Pipeline Stages

All run in a background thread. `_notify_stage(stage, status, data)` pushes events to JS.

```
[1]  transcription ────────── ffmpeg → whisperx CLI → .json
[2]  saving_transcript ────── saves raw JSON path to session registry
[3]  transcript_correction ── fuzzy-match glossary+character names (dual threshold: 0.70 chars, 0.80 glossary)
[4]  speaker_mapping ──────── LLM maps SPEAKER_XX → names (retries if <90% confidence → needs_review)
[5]  updating_transcript ──── postprocess applies mapping → labeled .txt + .srt
[6]  transcript_review ────── human-in-the-loop: user reviews/edits transcript (pipeline blocks)
[7]  timeline ─────────────── LLM: event timeline (JSON array, 8–15 key moments)
[8]  summary ──────────────── LLM: prose narrative recap
[9]  dm_notes ─────────────── LLM: structured DM notes
[10] character_updates ────── LLM: per-character + NPC development updates
[11] glossary ─────────────── LLM: extracts terms → smart-merges into campaign glossary → NPC sync
[12] leaderboard ──────────── LLM: per-hero combat stats
[13] locations ────────────── LLM: locations with descriptions, connections
[14] npcs ─────────────────── LLM: session NPC list with attitudes
[15] loot ─────────────────── LLM: items looted + gold transactions
[16] missions ─────────────── LLM: quests started/continued/completed
[17] illustration ─────────── LLM prompt → Gemini image generation
```

Status values: `idle | running | done | error | needs_review`

### LLM Stage Architecture

Each stage has `_generate_*_streaming()` (builds prompt, calls `_llm_stream()`) and `_save_*()` (writes file, updates registry). Stages skippable via `set_skipped_stages()` or `skip_llm_stage()`.

**Context injection into all LLM stages:**
- **Glossary context**: `_build_glossary_context()` cached at pipeline start, refreshed after glossary stage
- **Entity context**: `get_entity_context_for_llm()` provides cross-session knowledge (locations, NPCs, items, etc.)
- **Facts-as-context**: high-confidence facts (≥70%) formatted and injected after fact review
- **Session date anchoring**: prevents cross-session data leakage in prompts

### Speaker Mapping

`llm_mapper.suggest_mapping()` returns `(name_mapping, confidence_mapping, evidence_mapping)`. Enriched with character history, recent events, glossary context. DM auto-included. `_parse_mapping_response()` handles both confidence and flat string formats.

Review UI: confidence %, evidence text, sample lines per speaker. Color-coded: green (≥90), amber (70-89), red (<70).

### Entity Review (Human-in-the-Loop)

Entity stages include confidence scoring. Threshold: 95% for entity stages, 90% for glossary/character_updates. High-confidence auto-applied; low-confidence triggers `needs_review` pause with `EntityReviewPanel`. DM reviews each card: Accept/Edit/Decline. `complete_entity_review(stage, decisions)` resumes pipeline. `stop_pipeline()` sets all pending events to prevent zombie threads.

### Campaign Glossary

Stored on each campaign: `{term: {category, definition, description}}`. CRUD: `get_glossary()`, `update_glossary()`, `smart_merge_glossary()`, `apply_glossary_merges()`. NPC sync: `_sync_npcs_from_glossary()` auto-creates NPC characters from NPC glossary entries.

### Optional Artifacts & Single-Stage Generation

Users uncheck artifacts in SessionTab setup. Glossary always runs. `run_single_stage(session_id, stage)` generates on-demand from SessionDetailScreen. `retry_transcription(session_id, model, language)` re-triggers full pipeline for sessions with audio but no transcript.

## Entity Registry

`entities.py` — per-campaign at `~/.config/dnd-whisperx/entities/<campaign_id>.json`. Types: `location`, `item`, `mission`, `faction`, `spell`, `lore`. NPCs in `characters.json` linked via relationships. Features: history tracking, relationship versioning, alias fuzzy matching, auto-migration from glossary+artifacts.

API: `get_entities`, `get_entity_detail`, `get_entity_relationships`, `get_entity_timeline`, `migrate_campaign_entities`.

## Recording

`_Recorder` class: pause/resume, auto-save every 20min, crash-safe via atexit. Frontend shows as pseudo-stage in pipeline sidebar.

## JS ↔ Python Bridge

- Python `API` class methods callable as `window.pywebview.api.method_name()`
- Frontend wraps via `api()` in `frontend/src/lib/api.ts`
- Python→JS events: `_receiveLog`, `_onPipelineStage`, `_onLLMChunk`, `_pyDragDrop`
- Additional: `generate_session_title()`, `download_file()`, `download_session_zip()`

## Persistent Storage

All under `~/.config/dnd-whisperx/`: `prefs.json`, `sessions.json`, `campaigns.json`, `characters.json`, `characters/<id>/`, `entities/<id>.json`, `digests/<cid>_<sid>.json`, `app.log`.

Session outputs: `~/Documents/Chronicles/<Campaign>/Season N/<YYYY-MM-DD_HH-MM>/`.

### Data Loss Prevention

`sessions.py`, `campaigns.py`, `characters.py` all use:
- **Atomic writes**: write to `.tmp` then `os.replace()` for crash safety
- **Backup**: `.json.bak` created before each save
- **Empty-write guard**: refuses to overwrite non-empty file with empty data unless `force=True`
- `update_session()` skips `_save()` when no matching session ID found (prevents ghost writes from background threads)

## Running Tests

```bash
cd "/Users/louistissot/DnD WhisperX"
python3.9 -m pytest tests/ -v
```

### Test Isolation

`tests/conftest.py` has an autouse `_guard_real_config_files` fixture that snapshots mtime/size of real config files before each test and fails if any are modified. All test files use `_isolate_storage` fixtures redirecting registry paths to `tmp_path`. Always use `patch.object(backend, "method", ...)` not `patch("backend.method", ...)` — the module isn't in `sys.modules` after the import context exits.

### Repackaging Checklist

```bash
python3.9 -m pytest tests/ -v
cd frontend && npm run build && cd ..
/Users/louistissot/Library/Python/3.9/bin/pyinstaller DnDWhisperX.spec --clean --noconfirm
cp -R "dist/Chronicles.app" /Applications/
```

## Campaigns & D&D Beyond

Campaigns have `beyond_url` (optional). Seasons store character UUIDs. `_migrate_to_global_chars()` auto-converts old formats. `open_path()` handles both filesystem paths and URLs.

## Common Gotchas

- **App not opening**: check `~/.config/dnd-whisperx/app.log` first.
- **Python 3.9 syntax**: `X | Y` type hints crash on startup. Use `Optional[X]`, `Union[X, Y]`.
- **Frontend not found**: run `cd frontend && npm run build` before `python3.9 main.py`.
- **Session dir must exist before writing**: always `mkdir(parents=True, exist_ok=True)` before file writes.
- **`updating_transcript` vs `saving_transcript`**: `saving_transcript` saves raw JSON; `updating_transcript` applies speaker mapping → labeled .txt/.srt.
- **prefs.json race condition**: frontend MUST `await` sequential `set_pref` calls — never fire in parallel.
- **Portrait vs Illustration**: `generate_portrait()` for character headshots, `generate_illustration()` for session art (wraps with fantasy style).
- **DM handling**: `is_dm=True` chars hidden from UI but auto-included in speaker mapping.
- **NSFilenamesPboardType deprecated**: use `"public.file-url"` with `readObjectsForClasses_options_`.
- **pywebview**: `background_color` not `background` in `create_window`. `evaluate_js` must be called from background threads.
- **Gemini model names**: `gemini-2.5-flash-image` — Google preview model, name may change.
