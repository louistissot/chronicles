---
name: feature-development
description: Use when building a new feature, implementing a user request, adding functionality, or making significant code changes. This skill enforces the development process that prevents regressions like missing ENTITY_REVIEW_STAGES entries, broken type unions, or untested code paths. Triggers on phrases like "add feature", "implement", "build", "create new", "extend", or any multi-file change.
---

# Feature Development Process

## Why This Exists

Past regressions happened because we skipped steps:
- `ENTITY_REVIEW_STAGES` missing `character_updates`/`glossary` → pipeline hung with no review UI
- `sessions.json` wiped by tests → data loss from missing test isolation
- Entity context not injected into fact extraction → LLM couldn't learn across sessions

This process prevents those failures.

## Phase 1: Understand

Before writing any code:

- [ ] **Read the related code** — don't assume you know the codebase. Open the actual files.
- [ ] **Identify ALL files that need changes** — backend + frontend + tests + types. Use this checklist:

| Area | Files to Check |
|------|---------------|
| Backend logic | `backend.py`, relevant module (`sessions.py`, `characters.py`, `entities.py`, etc.) |
| Frontend types | `frontend/src/lib/api.ts` — `PipelineStage`, `SessionEntry`, etc. |
| Frontend UI | `InlinePipelineView.tsx`, `SessionDetailScreen.tsx`, `MapsTab.tsx`, `App.tsx` |
| Stage lists | `ENTITY_REVIEW_STAGES` in `App.tsx`, sidebar stages in `InlinePipelineView.tsx` |
| Data dedup | Glossary only stores Faction/Item/Spell/Other. NPCs → `characters.json`, Locations → entity registry |
| Maps | `maps.py` for map persistence, `MapsTab.tsx` for React Flow rendering |
| Tests | `test_pipeline.py`, `test_save_stages.py`, `test_new_features.py`, `test_sessions.py` |

- [ ] **Check for existing patterns** — search for similar implementations in the codebase. Don't reinvent.

## Phase 2: Plan

- [ ] **List every file to modify** with the specific change for each
- [ ] **Check cross-cutting concerns** — these are the things that get missed:
  1. `ENTITY_REVIEW_STAGES` in `App.tsx` — any stage with confidence review MUST be here
  2. `PipelineStage` type union in `api.ts` — any new stage MUST be in the type
  3. `LLM_STAGES` in `test_pipeline.py` — test must know about new stages
  4. Context injection — glossary, entity, facts, session date in LLM prompts
  5. Test isolation — new tests MUST use `_isolate_storage` fixture
  6. Python 3.9 syntax — `Optional[X]` not `X | None`, `List[str]` not `list[str]`
  7. NPC/Location dedup — glossary must NOT contain NPC/Location entries; they route to characters.json and entity registry
  8. Maps module — map data in `maps.py`, not in campaigns.json or entities
  9. React hooks order — ALL hooks MUST be called BEFORE any early `return` in components (error #310 crash)
  10. PyInstaller local modules — new `.py` files must be added to `datas` in `DnDWhisperX.spec` AND imported at module level

## Phase 3: Test First

- [ ] **Run baseline**: `python3.9 -m pytest tests/ -v` — confirm all tests pass BEFORE changes
- [ ] **Write a failing test** for the new behavior
  - Pipeline stages → `test_save_stages.py` or `test_pipeline.py`
  - Registry changes → `test_sessions.py`, `test_characters.py`, `test_campaigns.py`
  - Frontend → `npm run build` (TypeScript is the test)
- [ ] **Verify the test fails** for the right reason — not a setup error

## Phase 4: Implement

- [ ] **Follow the plan checklist** — one file at a time
- [ ] **One logical change per step** — don't bundle unrelated changes
- [ ] **After each backend change**: `python3.9 -m pytest tests/ -v`
- [ ] **After each frontend change**: `cd frontend && npm run build`

## Phase 5: Verify (MANDATORY)

**Never claim "done" without fresh evidence from ALL of these:**

- [ ] `python3.9 -m pytest tests/ -v` → all pass (run it fresh, not from cache)
- [ ] `cd frontend && npm run build` → TypeScript compiles clean
- [ ] **Cross-cutting review** (read the actual code, not from memory):
  - If new stage: is it in `ENTITY_REVIEW_STAGES`? In `PipelineStage` type? In sidebar?
  - If new test: does it use `_isolate_storage`? Does it use `patch.object(backend, ...)`?
  - If new registry field: is it in `SessionEntry` type? In `get_sessions()` response?
- [ ] **Package + install** (if deploying):
  ```bash
  /Users/louistissot/Library/Python/3.9/bin/pyinstaller DnDWhisperX.spec --clean --noconfirm
  cp -R "dist/Chronicles.app" /Applications/
  ```
- [ ] **Manual test** — open the app, verify the specific feature works

## Red Flags (Stop and Reassess)

- Modifying more than 5 files without a plan → stop, write the plan first
- Test suite was not green before you started → fix existing failures first
- You're guessing at a fix without reading the code → go back to Phase 1
- A "simple" change touches backend + frontend + types + tests → it's not simple, follow the full process
