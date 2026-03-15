# Chronicles — Codebase Guide

## What This Is

A macOS desktop app for DnD players. It records or imports audio from sessions, runs WhisperX (speech-to-text + speaker diarization), does automatic speaker-to-character mapping, then generates a structured session summary, DM notes, scene prompts, and a timeline — all via an LLM pipeline. The UI is a React frontend loaded inside a pywebview window.

## How to Run (Development)

```bash
# 1. Build the frontend first (required before starting Python)
cd frontend && npm install && npm run build && cd ..

# 2. Run the app
/Library/Developer/CommandLineTools/usr/bin/python3.9 main.py
```

Dev frontend with hot-reload (no Python backend, limited API stubs):
```bash
cd frontend && npm run dev   # http://localhost:5173
```

## How to Package

```bash
/Users/louistissot/Library/Python/3.9/bin/pyinstaller Chronicles.spec --clean --noconfirm
cp -R "dist/Chronicles.app" /Applications/
```

## Python Version Constraint — CRITICAL

**Python 3.9 only.** WhisperX is installed against this specific interpreter.

- Binary: `/Library/Developer/CommandLineTools/usr/bin/python3.9`
- PyInstaller: `/Users/louistissot/Library/Python/3.9/bin/pyinstaller`
- **Never use `str | None` union syntax** — that's Python 3.10+. Always use `Optional[str]` from `typing`.
- Same for `list[str]`, `dict[str, Any]` etc. — use `List[str]`, `Dict[str, Any]` from `typing`.

## File Structure

```
main.py          Entry point. Creates pywebview window, registers native macOS drag-drop via ObjC.
backend.py       The API class exposed to JS via window.pywebview.api. All JS→Python calls go here.
                 Contains the full pipeline: transcription → speaker mapping → LLM stages → illustration.
image_gen.py     Gemini image generation via google-genai SDK (gemini-2.5-flash-image).
                 Generates session illustrations via generate_content() with response_modalities=["TEXT", "IMAGE"].
                 Three functions: generate_illustration() (16:9, fantasy art wrapper),
                 generate_portrait() (1:1, no wrapper), generate_fullbody() (2:3, no wrapper).
characters.py    Global character registry at ~/.config/dnd-whisperx/characters.json.
                 Full CRUD: create, get, update, delete. Per-character storage dirs
                 under characters/<char_id>/. History tracking and D&D Beyond data sync.
                 Characters with is_dm=True are hidden from the UI but auto-included
                 in speaker mapping. Migration auto-sets is_dm on "DM"/"Dungeon Master".
                 NPC support: is_npc flag, npc_description, campaign_ids. NPCs auto-created
                 from glossary extraction. Full-body gallery: fullbody_path, fullbodies list.
beyond.py        D&D Beyond character data fetching. Extracts character ID from URL,
                 fetches from public API, parses classes/races/stats/spells/equipment/
                 backpack/currency/proficiencies/languages/features/feats/notes/defenses.
                 Downloads avatar images. Raises ValueError on 403 (private characters).
sessions.py      Session registry. Reads/writes ~/.config/dnd-whisperx/sessions.json.
campaigns.py     Campaign + season registry. Reads/writes ~/.config/dnd-whisperx/campaigns.json.
                 Seasons store character IDs (UUIDs) referencing the global characters.json.
                 _migrate_to_global_chars() auto-converts old formats on load.
                 get_campaigns_for_character(char_id) returns campaigns/seasons referencing a character.
config.py        Token + prefs storage. All stored flat in ~/.config/dnd-whisperx/prefs.json.
runner.py        Runs ffmpeg (audio conversion) and whisperx CLI as subprocesses with streaming output.
postprocess.py   Parses WhisperX JSON output. Replaces SPEAKER_00 etc. with character names.
                 Writes transcript.txt and transcript.srt. Glossary-aware transcript correction
                 via correct_transcript_terms() (fuzzy matching with difflib.SequenceMatcher).
llm.py           LLM abstraction. Routes to Anthropic (claude-sonnet-4-6) or OpenAI (gpt-4o).
                 Supports both blocking (call_llm) and streaming (stream_llm) modes.
llm_mapper.py    Uses LLM to suggest speaker→character name mapping from transcript samples.
                 Returns (name_mapping, confidence_mapping, evidence_mapping) 3-tuple.
                 Evidence field explains WHY the LLM mapped each speaker to a name.
entities.py      Unified entity registry. Per-campaign storage at ~/.config/dnd-whisperx/entities/<id>.json.
                 Tracks locations, items, missions, factions, spells, lore with full history.
                 Relationships between entities (and characters) with status tracking and versioning.
                 Auto-migrates from campaign glossary + session artifacts on first access.
log.py           Rotating file logger. Log file at ~/.config/dnd-whisperx/app.log.
deps.py          Background dependency check/auto-upgrade (skipped in bundled .app).
app.py           Legacy: older CustomTkinter UI, no longer used.
Chronicles.spec PyInstaller spec. Bundles Python + frontend/dist into Chronicles.app.
tests/           pytest test suite. Run with: python3.9 -m pytest tests/ -v
```

## Pipeline Stages (in order)

All stages run in a background thread. Each stage calls `_notify_stage(stage, status, data)` which pushes events to JS via `window.evaluate_js()`.

```
Audio file (.m4a/.mp3/etc.)
       │
       ▼
  [1] transcription ──────── ffmpeg → whisperx CLI → .json
       │
       ▼
  [2] saving_transcript ──── saves raw JSON path to session registry
       │
       ▼
  [3] transcript_correction ── fuzzy-matches glossary terms + character names against WhisperX
       │                        output to fix misspelled proper nouns (uses difflib.SequenceMatcher,
       │                        threshold 0.80, min 4 chars, common word filter). Non-fatal.
       ▼
  [4] speaker_mapping ────── LLM maps SPEAKER_XX → character names (with confidence scores)
       │                      └─► retries with extra samples if any speaker < 90% confidence
       │                      └─► needs_review if still low confidence after retry
       ▼
  [5] updating_transcript ── postprocess.py applies mapping → labeled .txt + .srt
       │
       ▼
  [6] timeline ──────────── LLM: event timeline (JSON array, 8–15 key moments)
       │
       ▼
  [7] summary ───────────── LLM: prose narrative recap
       │
       ▼
  [8] dm_notes ──────────── LLM: structured DM notes (hooks, NPCs, loose ends)
       │
       ▼
  [9] character_updates ─── LLM: per-character + NPC development updates (JSON object)
       │                      └─► skipped if no character IDs in session
       │                      └─► also generates history entries for campaign NPCs that appear in transcript
       ▼
 [10] glossary ─────────── LLM: extracts NPCs, locations, factions, items, spells from transcript
       │                      └─► smart-merges into campaign glossary (adds new + updates enriched definitions/descriptions)
       │                      └─► LLM deduplication via _merges directives (merge variant terms)
       │                      └─► _sync_npcs_from_glossary: auto-creates/updates NPC characters from NPC glossary entries
       ▼
 [11] leaderboard ────────── LLM: per-hero combat stats (kills, assists, damage, d20 avg, nat 20s/1s)
       ▼
 [12] locations ──────────── LLM: locations visited with descriptions, connections, relative positions
       ▼
 [13] npcs ───────────────── LLM: session-level NPC list (name, race, role, attitude, actions, status)
       ▼
 [14] loot ───────────────── LLM: items looted + gold transactions (who, what, when, where, how)
       ▼
 [15] missions ──────────── LLM: quests started/continued/completed with objectives and rewards
       ▼
 [16] scenes ────────────── LLM: cinematic scene prompts (JSON array)
       │
       ▼
 [17] illustration ──────── LLM: generates image prompt → Gemini Imagen generates PNG
                             Skipped automatically if no Gemini API key is configured.

```

Stage status values: `idle | running | done | error | needs_review`

### LLM Stage Architecture

`_run_llm_stages()` runs 11 sequential streaming calls: timeline → summary → dm_notes → character_updates → glossary → leaderboard → locations → npcs → loot → missions → scenes, followed by `_run_illustration_stage()` which generates an illustration prompt via LLM then calls Gemini image generation. Each stage has its own `_generate_*_streaming()` method (builds the prompt, calls `_llm_stream()`) and `_save_*()` method (writes file, updates session registry, notifies frontend). Stages can be skipped via `skip_llm_stage(stage)` or pre-populated via `set_skipped_stages(stages)`. Skipped stages are tracked in `_skipped_stages` set and marked as `done` with `{"skipped": True}`.

**Glossary context injection:** `_build_glossary_context()` loads the campaign glossary once at pipeline start and caches it in `self._glossary_context`. This formatted block is injected into downstream LLM stage prompts (timeline, dm_notes, scenes) for accurate proper-noun usage. After the glossary stage saves and smart-merges new terms, the context is refreshed for subsequent stages (scenes, illustration).

**Session date anchoring:** `_run_llm_stages()` looks up the session date and stores it in `self._session_date`. All 11 `_generate_*_streaming` methods inject this date into prompts ("This session took place on {date}. Extract information ONLY from THIS session's transcript.") to prevent cross-session data leakage.

### Optional Artifacts

Users can uncheck artifacts (timeline, summary, dm_notes, character_updates, leaderboard, locations, npcs, loot, missions, scenes, illustration) in SessionTab before starting the pipeline. Glossary always runs (not optional — it feeds accuracy into all stages). `set_skipped_stages(stages)` pre-populates `_skipped_stages` before the pipeline runs. `run_single_stage(session_id, stage)` allows generating a single artifact on-demand for an existing session from the SessionDetailScreen.

### Retry Transcription

`retry_transcription(session_id, model=None, language=None)` re-triggers the full pipeline for a session that has audio but no transcript (e.g. failed/interrupted transcription). It restores session context (`_current_session_id`, `_current_campaign_id`, character names from season) and calls `start_job()` internally. Model/language can be passed directly or fall back to saved prefs (tries `whisperx_model`/`whisperx_language` first, then `model`/`language`).

In the frontend, `SessionDetailScreen` shows a "Process Audio" button in the Info tab when `session.files.audio && !session.files.transcript`. Clicking it opens a settings modal (model + language selectors) before triggering the transcription. After starting, `onViewPipeline()` navigates to the Session tab's pipeline processing view.

**Important**: `start_job()` calls `_notify_stage("transcription", "running")` to notify the frontend. This is essential for the retry flow since it doesn't go through `App.tsx`'s `handleRun` which normally sets the stage status on the frontend side.

### Illustration Generation

`_run_illustration_stage()` first generates a detailed image prompt via LLM streaming (`_generate_illustration_prompt_streaming()`), then calls `image_gen.generate_illustration()` which uses the google-genai SDK. The resulting PNG is saved to `out_dir/illustration.png`. Requires a Gemini API key configured in Settings.

### JSON Repair

`_repair_json_array(text)` is a cascading repair helper for LLM-produced JSON arrays. Handles: markdown fences, trailing commas, surrounding prose. Used by `_save_timeline` and `_save_scenes`.

### Speaker Mapping with Confidence

`llm_mapper.suggest_mapping()` returns `(name_mapping, confidence_mapping, evidence_mapping)`. Confidence is 0–100 per speaker. Evidence is a brief explanation of WHY the LLM mapped each speaker. If any speaker has < 90% confidence, the pipeline retries with 15 extra samples. If still low after retry → `needs_review` with pre-filled high-confidence assignments.

The mapping prompt is enriched with: character `history_summary`, last 3 session `recent_events`, and campaign glossary context (top 50 terms). This helps the LLM distinguish speakers who reference known NPCs, locations, etc.

**DM auto-inclusion**: `backend.py` always injects "DM" into `character_names` if not already present. The DM is an implicit participant in every session — it does not need to be added as a character in the Characters tab or season character list. Characters with `is_dm=True` are hidden from CharactersTab and CampaignsTab pickers but still appear in transcripts, DM notes, and speaker mapping review.

`_parse_mapping_response(raw_dict)` handles both confidence format `{"SPEAKER_00": {"name": "DM", "confidence": 95}}` and flat string format `{"SPEAKER_00": "DM"}` for backward compatibility.

### Speaker Mapping Review

When speaker mapping is partial or fails, `needs_review` is fired with:
- `jsonPath`, `partialMapping`, `unmappedSpeakers`, `characterNames`
- `sampleLines: Record<speakerId, string[]>` — up to 5 transcript lines per speaker for identification
- `confidences: Record<speakerId, number>` — LLM confidence score per speaker
- `evidence: Record<speakerId, string>` — LLM reasoning per speaker mapping

Sample lines are filtered by `postprocess.get_review_samples()`: only lines with >=5 words OR containing a character name/glossary term. Falls back to all lines if no qualifying lines exist. Sorted by length.

The frontend shows confidence %, evidence text, and sample lines in the speaker review UI. Speakers are sorted by confidence (lowest first = needs most attention). Confidence is color-coded: green (>=90), amber (70-89), red (<70).

### Entity Review (Human-in-the-Loop)

Entity stages (locations, npcs, loot, missions — NOT glossary) now include confidence scoring in their LLM prompts. Each extracted entity has a `confidence` (0-100) and `reasoning` field.

**Confidence threshold**: 95%. Entities with confidence >= 95% are auto-applied to the entity registry. Entities below 95% trigger a `needs_review` pause.

**Review flow**:
1. `_save_*` methods split entities by confidence threshold
2. High-confidence entities auto-applied to entity registry immediately
3. Low-confidence entities sent to `_request_entity_review(stage, items, auto_applied)`
4. Pipeline thread blocks via `threading.Event.wait()` (indefinite, no timeout)
5. Frontend shows `EntityReviewPanel` inline in the pipeline view
6. DM reviews each card: Accept / Edit / Decline
7. Frontend calls `complete_entity_review(stage, decisions)` which sets the event
8. Pipeline resumes, applying accepted/edited entities to the registry

**Glossary is excluded** from entity review — it has its own editing tab (GlossaryTab) for manual term management.

**Safety**: `stop_pipeline()` sets all pending entity review events to prevent zombie threads. Confidence/reasoning fields are stripped from saved artifact files (backward compat).

**API**: `complete_entity_review(stage, decisions)` — decisions is a list of `{id, action: accept|edit|decline, edited?: {...}}`.

### Campaign Glossary

`campaigns.py` stores a `glossary` dict on each campaign: `{term: {"category": "NPC|Location|Faction|Item|Spell|Other", "definition": "...", "description": "..."}}`. `definition` = concise factual summary (1-2 sentences). `description` = richer cumulative context that grows over sessions. CRUD via `get_glossary()`, `update_glossary()` (full replace), `merge_glossary()` (additive-only, legacy), `smart_merge_glossary()` (case-insensitive matching, adds new terms + updates existing definitions/descriptions when the LLM provides richer context), `apply_glossary_merges()` (processes deduplication directives: `{"keep": "full name", "remove": "variant"}`).

The `glossary` pipeline stage always runs — it receives existing glossary terms WITH their current definitions and descriptions in the prompt, decides what to add or enrich, detects near-duplicates and reports them via `_merges` directives. The result is smart-merged into the campaign glossary, then merge directives are applied to deduplicate.

The `transcript_correction` stage runs BEFORE speaker mapping — it uses glossary terms + character names to fix misspelled proper nouns in the WhisperX JSON via fuzzy matching (`difflib.SequenceMatcher`, threshold 0.80, min 4 chars). A common word filter prevents false positives. Non-fatal — pipeline continues even if correction fails.

The glossary context (with truncated descriptions) is also injected into speaker mapping prompts (top 50 terms) and all downstream LLM stages for accurate naming. Frontend has a `GlossarySection` editor with category filter pills, search, and description editing inside `CampaignsTab.tsx`. `SessionDetailScreen` has a dedicated Glossary tab showing session-specific extracted terms.

## Recording

The `_Recorder` class in `backend.py` supports:
- **Pause/resume**: `pause()` / `resume()` — stream keeps reading to prevent buffer overflow, but data is discarded while paused. Duration excludes paused time.
- **Auto-save**: checkpoint WAV saved every 20 minutes without stopping the recording.
- **Crash-safe**: `atexit` handler converts raw PCM to WAV if the app exits mid-recording.
- **API methods**: `pause_recording()`, `resume_recording()`, `is_recording_paused()`, `stop_recording()`

The frontend shows recording as a display-only pseudo-stage in the pipeline sidebar (not a real backend `PipelineStage`). When recording stops, the pipeline auto-starts transcription.

## Window

The app uses a pywebview window (`frameless=False` in `main.py`) with native macOS window controls. The header has `padding-left: 78px` to accommodate the traffic light buttons.

## JS ↔ Python Bridge

- Python methods on the `API` class in `backend.py` are callable from JS as `window.pywebview.api.method_name()`
- The frontend wraps all calls through `api()` helper in `frontend/src/lib/api.ts`
- Python pushes events to JS via `self._window.evaluate_js("window._handler && window._handler(...)")`:
  - `window._receiveLog(line, isStderr)` — pipeline stdout/stderr lines
  - `window._onPipelineStage(stage, status, data)` — stage status changes
  - `window._onLLMChunk(stage, chunk)` — streaming LLM text tokens
  - `window._pyDragDrop({type, path})` — native macOS file drop events

### Additional API Methods

- `generate_session_title(session_id)` — Uses LLM to generate a short evocative session title from the transcript. Updates `display_name` on the session. Returns `{ok, title}` or `{ok: false, error}`.
- `download_file(path)` — Copies a file to `~/Downloads/`, adding timestamp suffix on name collision. Returns `{ok, dest}`.
- `download_session_zip(session_id)` — Zips all files in the session's `output_dir` to `~/Downloads/Chronicles_<name>.zip`. Returns `{ok, dest}`.

## Native Drag-and-Drop

Implemented in `main.py` via PyObjC (`objc`, `AppKit`, `Foundation.NSURL`). A transparent `NSView` overlay is attached above the webview content (`NSWindowAbove`) with `hitTest_withEvent_` returning `None` so mouse clicks pass through to the webview while drag events are intercepted. Uses modern `"public.file-url"` pasteboard type with `readObjectsForClasses_options_([NSURL], ...)` for file path extraction (the deprecated `NSFilenamesPboardType` no longer works on modern macOS). Accepts `.m4a .mp3 .wav .ogg .flac .aac .wma` (audio) and `.json .txt .srt` (transcript) files. On drop it calls `window._pyDragDrop()`. This only works inside the packaged `.app` — not in browser dev mode.

## Persistent Storage

All under `~/.config/dnd-whisperx/`:
- `prefs.json` — API tokens (HF, Claude, OpenAI, Gemini) + UI preferences (model, theme, etc.)
- `sessions.json` — list of all past sessions with paths to output files
- `campaigns.json` — campaigns and seasons with character ID lists
- `characters.json` — global character registry (independent of campaigns)
- `characters/<char_id>/` — per-character storage (portrait.png, avatar.jpg)
- `entities/<campaign_id>.json` — per-campaign entity registry (locations, items, missions, factions, spells, lore) with relationships and history
- `digests/<campaign_id>_<season_id>.json` — season digest (narrative summary, character arcs, unresolved threads)
- `app.log` — rotating log file (first place to look when the app misbehaves)

Session output files are written to `~/Documents/Chronicles/<CampaignName>/Season N/<YYYY-MM-DD_HH-MM>/`.

## LLM Provider

Configured via Settings tab. Supports:
- **Anthropic** — `claude-sonnet-4-6` (default)
- **OpenAI** — `gpt-4o` (configurable model in config.py `_DEFAULTS`)

The `stream_llm()` function in `llm.py` accepts a `stop_check` callback; `backend.py` uses a threading `Event` per stage so the user can cancel mid-stream. The `stop_pipeline()` API method stops both the transcription job and all LLM stages at once.

## Entity Registry (Graph-Ready Data Model)

`entities.py` provides a unified registry for all campaign entities with full relationship tracking and history. Stored per-campaign at `~/.config/dnd-whisperx/entities/<campaign_id>.json`.

**Entity types:** `location`, `item`, `mission`, `faction`, `spell`, `lore`. NPCs remain in `characters.json` but are linked to entities via relationships.

**Key features:**
- **History tracking:** Every update snapshots the previous state. Entity timeline shows all changes across sessions (e.g., a mission going from "active" → "completed").
- **Relationship versioning:** Relationships have `current` state + `history` array. A romance that ends later is preserved: `active` (session 1) → `ended` (session 3), with both states visible.
- **Aliases:** Fuzzy matching via `difflib.SequenceMatcher` (threshold 0.80) handles misspellings.
- **Auto-migration:** On first access per campaign, glossary terms + session artifacts (locations.json, loot.json, missions.json) are migrated into the entity registry. The glossary in `campaigns.py` stays in sync via `project_to_glossary()`.
- **Pipeline integration:** `_save_locations()`, `_save_loot()`, `_save_missions()`, and `_save_glossary()` in `backend.py` feed into the entity registry automatically.

**API endpoints (on `backend.API`):**
- `get_entities(campaign_id, entity_type)` — list entities with optional type filter
- `get_entity_detail(campaign_id, entity_id)` — entity + relationships + timeline
- `get_entity_relationships(campaign_id, entity_id)` — relationships for an entity
- `get_entity_timeline(campaign_id, entity_id)` — merged timeline of changes
- `migrate_campaign_entities(campaign_id)` — trigger migration manually

**LLM context:** `get_entity_context_for_llm(campaign_id)` builds a formatted context block of all entities + active relationships for injection into LLM prompts.

## Campaigns & D&D Beyond

`campaigns.py` persists to `~/.config/dnd-whisperx/campaigns.json`. Each campaign object looks like:

```json
{
  "id": "<uuid>",
  "name": "The Lost Mines",
  "beyond_url": "https://www.dndbeyond.com/campaigns/...",
  "seasons": [
    { "id": "<uuid>", "number": 1, "characters": ["<char-uuid>", "<char-uuid>"] }
  ]
}
```

Seasons store character IDs (UUIDs) referencing the global `characters.json` registry. `_migrate_to_global_chars()` auto-converts old embedded formats (plain strings or dicts) to character IDs on load.

`beyond_url` is optional and defaults to absent (old campaigns) or `""` (after first edit). The `update_campaign(campaign_id, name, beyond_url)` function sets both fields atomically.

`open_path(path)` in `backend.py` handles both filesystem paths and `http://`/`https://` URLs — URLs are passed directly to macOS `open`, filesystem paths resolve parent directory.

## Running Tests

```bash
cd "/Users/louistissot/DnD WhisperX"
python3.9 -m pytest tests/ -v
```

See `tests/` for the full suite. Tests cover: campaign CRUD (including glossary), `update_campaign`, `open_path` URL routing, frontend TypeScript build, Python import/syntax checks, `postprocess.py` (speaker extraction, `save_all` directory creation, `get_review_samples`), `test_pipeline.py` (pipeline stage ordering and error routing in `_continue_pipeline`), `characters.py` (full CRUD, history, beyond data sync, migration, portrait gallery), `beyond.py` (URL parsing, API response parsing, avatar download), `video_gen.py` (image encoding, video generation polling, error handling), and `test_e2e_dummy.py` (end-to-end flow with dummy transcript data).

### E2E Dummy Data Tests

`tests/test_e2e_dummy.py` contains a minimal WhisperX transcript (3 speakers, 10 segments) and tests the full data creation flow: campaigns, characters, sessions, transcript parsing, speaker mapping, portrait gallery CRUD, and portrait generation prompt verification. **Always run these tests when modifying the pipeline flow.**

### Repackaging Checklist

After making changes, always follow this sequence:

```bash
# 1. Run tests
python3.9 -m pytest tests/ -v

# 2. Build frontend (includes TypeScript check)
cd frontend && npm run build && cd ..

# 3. Package and install
/Users/louistissot/Library/Python/3.9/bin/pyinstaller DnDWhisperX.spec --clean --noconfirm
cp -R "dist/Chronicles.app" /Applications/
```

### Patching `backend` in tests

`backend` is not registered in `sys.modules` after the module-level `with patch.dict(sys.modules, {...}): import backend` context exits — `patch.dict` restores `sys.modules` on exit, removing `backend` since it wasn't there before. As a result, `patch("backend.save_all", ...)` silently fails (no module lookup). Always use `patch.object(backend, "save_all", ...)` instead, where `backend` is the module object imported at the top of the test file.

## Cross-Tab Character Navigation

`App.tsx` manages `focusCharacterId` state. When set (e.g. from `onNavigateToCharacter` callback), it switches to the Characters tab. `CharactersTab` accepts `focusCharacterId` and auto-selects the matching character, then calls `onFocusHandled()` to clear the state. This pattern is used by: hero tags in library session cards, NPC cards in SessionDetailScreen.

Sessions store `character_ids` (list of UUIDs from the campaign season) alongside `character_names`. This enables cross-referencing sessions to the global character registry. The IDs are populated at registration time and resolved dynamically in `get_sessions()` for older sessions.

## Common Gotchas

- **App not opening**: check `~/.config/dnd-whisperx/app.log` — it's always the first place to look.
- **Python 3.9 union syntax crash**: any `X | Y` type hint in Python code will crash on startup. Use `Optional[X]`, `Union[X, Y]`.
- **Frontend not found**: if running from source without building frontend, the app crashes with `FileNotFoundError`. Run `cd frontend && npm run build` first.
- **WhisperX not found**: whisperx is installed for Python 3.9 only. Running with any other Python will fail.
- **evaluate_js from threads**: pywebview's `evaluate_js` must be called on a background thread (not the main thread) when triggered from pipeline stages. It's already handled correctly in `backend.py`.
- **`api()` stubs in browser**: many backend calls (campaign creation, session creation, file reads) return null or stub values in the Vite dev server. Full functionality requires running via `python3.9 main.py`.
- **Session directory must exist before writing**: `postprocess.save_all()` and `_run_llm_stages()` both call `out_dir.mkdir(parents=True, exist_ok=True)` before writing. Any new code that writes files to the session dir must do the same — never assume the dir exists just because it's in the sessions registry.
- **"Failed to save transcript" error**: if this appears, the session output directory doesn't exist on disk. `save_all()` now creates it automatically, but if the error reappears in a new code path, add `mkdir(parents=True, exist_ok=True)` before the write.
- **CONTINUE flow must reset `showNewCampaign`**: `SessionTab.tsx` `load()` sets `showNewCampaign(false)` when `autoNewCampaign` is false (CONTINUE path). If you add another entry point that bypasses `autoNewCampaign`, make sure to reset this state explicitly.
- **`updating_transcript` stage ordering**: `updating_transcript` is the stage that applies speaker mapping and writes labeled `.txt`/`.srt`. `speaker_mapping:done` fires first, then `updating_transcript:running`, then `save_all()`, then `updating_transcript:done`. Any failure during `save_all()` fires `updating_transcript:error`. `saving_transcript` is a separate earlier stage that just saves the raw WhisperX JSON path.
- **prefs.json race condition**: `config.py` uses a threading lock (`_prefs_lock`) and atomic writes (write to `.tmp` then rename) to prevent concurrent `set_pref`/`set_token` calls from corrupting the file. The frontend MUST `await` sequential `set_pref` calls — never fire multiple `api('set_pref', ...)` in parallel without awaiting each one. Corrupted prefs.json causes all API tokens to be lost (falls back to defaults with empty tokens), silently breaking transcription and LLM calls.
- **JSON existence check before `save_all`**: `_continue_pipeline` checks `json_path.exists()` before calling `save_all()`. If the JSON is missing, it fires `updating_transcript:error` with a clear "Re-import" message and returns.
- **D&D Beyond private characters**: `beyond.py` raises `ValueError` on 403 Forbidden responses. `backend.py:sync_beyond_character` catches this separately and returns the user-friendly error message. The character must be set to public in D&D Beyond settings.
- **Gemini model names**: `image_gen.py` uses `gemini-2.5-flash-image` (via `generate_content` API with `response_modalities=["TEXT", "IMAGE"]`). This is a Google preview model — name may change.
- **Portrait vs Illustration generation**: `image_gen.py` has TWO functions: `generate_illustration()` wraps prompts with "epic fantasy art style" for session illustrations, while `generate_portrait()` sends the prompt as-is for photorealistic character headshots. **Always use `generate_portrait()` for character portraits** — using `generate_illustration()` will override photorealistic prompts with fantasy art style.
- **Portrait gallery**: Characters have a `portraits: List[Dict]` field with `{path, is_primary}` entries. `portrait_path` stays in sync with the primary portrait. Generated portraits are saved with timestamps (`portrait_<ts>.png`) to avoid overwriting. `characters.py` has `add_portrait()`, `set_primary_portrait()`, `delete_portrait()` helpers. `_migrate_portraits()` runs on module load to backfill the list from old `portrait_path` data.
- **DM handling**: Characters with `is_dm=True` (auto-detected from name "DM" or "Dungeon Master") are hidden from the Characters tab and campaign character pickers. DM is auto-included in speaker mapping. The `is_dm` flag is set on creation and migrated on module load via `_migrate_dm_flag()`.
- **NSFilenamesPboardType is deprecated**: macOS no longer returns file paths via `propertyListForType_(NSFilenamesPboardType)` during drag-drop. Use `"public.file-url"` pasteboard type with `readObjectsForClasses_options_([NSURL], ...)` instead.
- **SPEAKER_XX migration**: `characters.py:migrate_from_campaign_chars()` filters out placeholder names matching `SPEAKER_\d+` to prevent creating junk characters from unmapped WhisperX speakers.
- **`create_window` background parameter**: pywebview uses `background_color`, not `background`. See `main.py` for the canonical call pattern.

