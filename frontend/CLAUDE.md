# Chronicles — Frontend Guide

## Stack

- **React 18** + **TypeScript** (strict)
- **Vite** — dev server on port 5173, builds to `dist/`
- **Tailwind CSS** — utility classes only, no CSS modules
- **shadcn/ui** — base primitives in `src/components/ui/` (Button, Input, Select, ScrollArea, etc.)
- **Lucide React** — icons

## Commands

```bash
npm install          # install deps
npm run dev          # dev server at http://localhost:5173 (limited — no Python backend)
npm run build        # production build to dist/ (required before running the Python app)
npm run typecheck    # tsc --noEmit
```

## Component Map

```
src/
├── App.tsx                      Root. Manages global state: activeTab, pipeline stages, streaming chunks.
│                                Four tabs: characters | library | glossary | chronicle
│                                "+ New Session" CTA opens fullscreen SessionTab.
│                                Campaign management via dropdown → Manage Campaigns overlay.
├── components/
│   ├── TitleScreen.tsx          Splash screen shown on app open. NEW CAMPAIGN / CONTINUE / OPTIONS choices.
│   │                            Uses Cinzel Decorative + gold accents matching app aesthetic. Theme-aware.
│   ├── SessionTab.tsx           Campaign/season setup, audio recording/upload, transcript import.
│   │                            Also shows InlinePipelineView during processing.
│   │                            Opens as fullscreen overlay via "+ New Session" CTA (not a tab).
│   │                            Has optional artifact checkboxes + campaignError state.
│   ├── InlinePipelineView.tsx   Pipeline processing progress: sidebar stages, recording controls,
│   │                            speaker mapping review (with confidence % + evidence), entity review,
│   │                            streaming LLM output, illustration preview.
│   │                            Extracted from LibraryTab for reuse in SessionTab.
│   ├── EntityReviewPanel.tsx    Card-based DM review for low-confidence entity extractions.
│   │                            Shows proposed changes with Accept/Edit/Decline per card.
│   │                            Batch actions (Accept All / Decline All). Auto-applied summary.
│   ├── HorizontalTimeline.tsx   Shared timeline component used by SessionDetailScreen and ChronicleTab.
│   │                            Scrollable rail of event nodes with hover/pin detail cards.
│   │                            Exports: TIMELINE_ICONS, inferEventType, TimelineIcon, importanceColor.
│   ├── CampaignsTab.tsx         Campaign management: list, expand/collapse cards, edit name + D&D Beyond
│   │                            URL, manage seasons + characters (race/class/portrait), delete.
│   │                            Accessed via "Manage Campaigns" in campaign dropdown (not a tab).
│   ├── CharactersTab.tsx        Character list with search, type filter (Heroes/NPCs/All), sort.
│   │                            Click to open CharacterDetail with full profile, history, portraits.
│   ├── LibraryTab.tsx           Session list with search, campaign/season filters, sort.
│   │                            Click session to open SessionDetailScreen.
│   ├── GlossaryTab.tsx          Standalone campaign glossary editor. Category pills, search, sort.
│   │                            Requires active campaign selection. Full CRUD on glossary terms.
│   ├── ChronicleTab.tsx         Season digest: generates narrative summary + timeline of a full season.
│   │                            Season selector tabs, "Generate Digest" button, HorizontalTimeline,
│   │                            character arcs, unresolved threads. Uses LLM to weave epic narrative.
│   ├── SessionDetailScreen.tsx  Full detail for a past session: Info / Summary / Timeline /
│   │                            Transcript / DM Notes / Scenes / Illustration.
│   │                            "Generate" buttons for missing artifacts (on-demand generation).
│   ├── SettingsTab.tsx          API tokens (HF, Claude, OpenAI, Gemini), model/provider, theme.
│   ├── MarkdownRenderer.tsx     Custom block + inline markdown renderer for LLM-generated content.
│   └── ui/                      shadcn primitives (do not edit).
├── lib/
│   ├── api.ts                   pywebview bridge. All JS→Python calls go through api() helper.
│   │                            Also declares global Window augmentations (_receiveLog, _onLLMChunk, etc.)
│   └── utils.ts                 cn() tailwind class merge helper.
└── index.css                    Tailwind base + custom CSS vars + font-face declarations.
```

## Color Palette & Design System

The app uses a D&D / parchment aesthetic with two modes (dark default, light available).

| Token | Dark value | Role |
|---|---|---|
| `text-gold` | `#D4AF37` | Primary accent — headings, active states, icons |
| `text-parchment` | `#E8DFC0` | Body text base |
| `bg-void` | `#080B14` | Deepest background |
| `bg-shadow` | `#0D1120` | Panel/card background |

Opacity modifiers (`/70`, `/40`, `/20`) are used heavily for hierarchy. Never use pure black or pure white.

Fonts (loaded via Google Fonts + @font-face):
- `font-display` / `font-heading` — Cinzel Decorative (display), Cinzel (headings)
- `font-body` — Crimson Text (body text)
- `font-mono` — system mono fallback

## Pipeline State Flow

`App.tsx` owns all pipeline state and passes it down as props:

```
App.tsx
  appState.stages: Record<PipelineStage, { status, data, error }>
  streamingChunksRef: Record<PipelineStage, string>   ← append-only, reset on new session
  logLinesRef: Array<{ text, isStderr }>              ← append-only, reset on new session
       │
       ├─► SessionTab.tsx
       │       └─► InlinePipelineView  (when showProcessing=true)
       └─► LibraryTab.tsx
               └─► SessionDetailScreen (when selectedSession != null)
```

Pipeline stage order: `transcription → saving_transcript → transcript_correction → speaker_mapping → updating_transcript → timeline → summary → dm_notes → character_updates → glossary → leaderboard → locations → npcs → loot → missions → scenes → illustration`

Processing now shows in the **Session tab** (not Library). Library tab is simplified to session list only; clicking an active/processing session navigates to the Session tab.

Recording is a display-only pseudo-stage (not in `PipelineStage` type). It appears in the sidebar when `recordingActive` is true.

Status values: `idle | running | done | error | needs_review`

The `summary` stage (before `dm_notes`) generates a prose narrative recap of the session. It produces `summary.md` in the session output folder.

## Python ↔ JS Event Handlers

These are set on `window` in `App.tsx`'s first `useEffect`:

| Handler | When called | What it does |
|---|---|---|
| `window._receiveLog(line, isStderr)` | Each subprocess output line | Appends to `logLinesRef`, bumps `logVersion` |
| `window._onPipelineStage(stage, status, data)` | Stage status change | Updates `appState.stages` |
| `window._onLLMChunk(stage, chunk)` | Each streaming token | Appends to `streamingChunksRef[stage]`, bumps `streamingVersion` |
| `window._pyDragDrop({type, path})` | Native file drop | Routes to SessionTab via `pendingDrop` state |

## API Bridge (`src/lib/api.ts`)

```ts
import { api } from '@/lib/api'

// Calls window.pywebview.api.method_name(...args)
// In browser dev mode: returns safe stubs (empty strings, empty arrays, null)
const result = await api('get_campaigns')
const result = await api('create_session', campaignId, seasonId)
const result = await api('read_file', path)
```

Key types: `SessionEntry`, `Campaign`, `Season`, `CharacterInfo`, `Scene`, `TimelineEvent`, `PipelineStage`, `StageStatus`, `SpeakerReviewPayload`

**Important**: many API calls return null in browser dev mode (no pywebview). Always test full functionality by running via `python3.9 main.py`.

## MarkdownRenderer

`src/components/MarkdownRenderer.tsx` — custom line-by-line parser. No external markdown library.

Handles: `# H1`, `## H2`, `### H3`, `---` dividers, `**bold**`, `*italic*`, `` `code` ``, `- bullet` lists (with indent), `1. numbered` lists, `> blockquotes`, plain paragraphs.

Used for: LLM streaming output in `InlinePipelineView`, DM Notes tab, Summary tab in `SessionDetailScreen`.

## SessionDetailScreen Tabs

Order: **Info → Summary → Timeline → Transcript → DM Notes → Glossary → Locations → NPCs → Loot → Missions → Scenes → Illustration**

- Summary: reads `session.summary_path` → renders with `MarkdownRenderer`. Also shows Leaderboard table (from `session.leaderboard_path`) above the prose summary with per-hero combat stats.
- Timeline: reads `session.timeline_path` → parses JSON array of `TimelineEvent`
- Transcript: reads `session.txt_path` → renders as `<pre>` monospace
- DM Notes: reads `session.dm_notes_path` → renders with `MarkdownRenderer`
- Glossary: reads `session.glossary_path` → parses JSON object, shows terms with category filter pills and search
- Locations: reads `session.locations_path` → parses JSON array, shows cards with visited badge, connections pills, relative positions
- NPCs: reads `session.npcs_path` → parses JSON array, shows cards with race/role badges, attitude color-coding
- Loot: reads `session.loot_path` → parses JSON object with items table + gold transactions
- Missions: reads `session.missions_path` → parses JSON array, shows cards with status badges (started=amber, continued=blue, completed=green)
- Scenes: reads `session.scenes_path` → parses JSON array of `Scene`, shows expandable cards
- Illustration: displays `session.illustration_path` as an image, with "Open in Finder" and "Regenerate" buttons

All content tabs include a download button that copies the file to `~/Downloads/`. Info tab has a "Download All" button that zips the entire session. Session title can be regenerated via LLM from the Info tab header.

All tabs lazy-load on each activation (no caching — ensures fresh data after generation). Files are read via `api('read_file', path)`.

**Tab visual states:** Tabs have three visual states: (1) gold/active when selected, (2) normal parchment when data exists, (3) dimmed italic when tab is accessible but has no data yet. Tabs without a transcript are fully disabled.

**Auto-refresh after generation:** When `run_single_stage` completes, a `refreshCounter` state increments alongside `onRefresh?.()`, triggering the data-loading useEffect to reload the current tab's content automatically — no tab-switch needed.

**Streaming preview:** While generating an artifact, each tab shows a live streaming preview of the LLM output (MarkdownRenderer for prose stages, `<pre>` for JSON stages) with a pulsing indicator.

For missing artifacts (when transcript exists), each tab shows a "Generate" button that calls `api('run_single_stage', sessionId, stage)` to generate that artifact on-demand.

**Cross-tab character navigation:** `onNavigateToCharacter(charId)` prop navigates to CharactersTab and auto-selects the character. Used by NPC cards and hero tags in library session cards.

When a session has audio but no transcript (`session.files.audio && !session.files.transcript`), only the Info tab is available. The Info tab shows a "Process Audio" button that opens a settings modal (WhisperX model + language selectors, pre-filled from saved prefs). On confirm, it calls `api('retry_transcription', sessionId, model, language)` and navigates to the Session tab's pipeline view via `onViewPipeline()`.

## LibraryTab

```
selectedSession != null    → SessionDetailScreen
default                    → session list with search + campaign/season filters + sort
```

The active session (currently processing) is pinned at top with a gold ring + pulsing dot. Clicking it opens the fullscreen SessionTab's processing view via `onNavigateToProcessing()`. After the pipeline completes, the library auto-refreshes.

**Session cards** display hero names as clickable gold-tinted tags (instead of artifact badges). Clicking a hero tag navigates to CharactersTab via `onNavigateToCharacter(charId)`. Hero tag linking uses `session.character_map` (name→ID lookup) instead of index-based matching. Minimal status icons (audio/transcript/summary) show below the tags.

**Filters:** Search input (matches display_name, campaign_name, character_names, date). Campaign/season dropdowns appear when >1 campaign. Sort: newest first (default), oldest first, name A→Z.

## GlossaryTab

Standalone top-level tab showing the active campaign's glossary. Props: `{ campaignId, campaignName }`. Shows "No campaign selected" if no `campaignId`.

Features: category filter pills (All, NPC, Location, Faction, Item, Spell, Other), search, sort (Name A→Z, Name Z→A, Category), inline editing of terms/definitions/descriptions, add/delete terms, save button.

## ChronicleTab

Season digest + timeline generator. Props: `{ campaignId, campaignName }`. Shows "No campaign selected" if no `campaignId`. Tab label is "Chronicles".

Features: season selector tabs, "Generate Digest" / "Regenerate" button. LLM generates a JSON digest with: title, narrative (markdown), character_arcs, unresolved threads, and a `timeline` (array of TimelineEvent). The timeline is displayed via the shared `HorizontalTimeline` component (same UI as session detail timeline) with events referencing session names instead of timestamps. The digest narrative is displayed with MarkdownRenderer. Backend: `generate_season_digest(campaign_id, season_id)`, `get_season_digest(campaign_id, season_id)`. Digests saved at `~/.config/dnd-whisperx/digests/<campaign_id>_<season_id>.json`. Existing digests without a `timeline` key still render (backward compat).

## SessionTab — Fullscreen Mode

SessionTab is no longer a tab — it's opened via the `+ New Session` CTA button in the header.

```
showProcessing=true        → InlinePipelineView (processing/recording in progress)
default                    → setup mode (campaign/season/audio selection)
```

### Recording in Pipeline View

Recording is displayed as a pseudo-stage in `InlinePipelineView` with:
- Pulsing red dot in sidebar, timer (MM:SS), Pause/Resume/Stop buttons
- Stop confirmation dialog offering "Pause Instead" or "Stop & Transcribe"
- Auto-transitions to transcription pipeline after stopping
- Props flow: `App.tsx` → `SessionTab` → `InlinePipelineView`

### Skip Buttons

LLM stages (timeline, summary, dm_notes, scenes, illustration) have skip buttons visible when the stage is idle. Skipping marks the stage as done with `{"skipped": true}` and prevents execution when its turn comes.

### Optional Artifacts

SessionTab setup mode shows checkboxes for: Timeline, Summary, DM Notes, Scenes, Illustration (all checked by default). Unchecked artifacts are passed to `set_skipped_stages()` before the pipeline starts.

## Key Conventions

- All API calls are `await api('method_name', ...args)` — never call `window.pywebview.api` directly.
- Use `cn()` from `@/lib/utils` for conditional Tailwind class merging.
- Version-bump pattern: `setLogVersion(v => v + 1)` / `setStreamingVersion(v => v + 1)` forces re-renders when ref values change.
- Refs (`logLinesRef`, `streamingChunksRef`) are used for append-only data that shouldn't trigger renders on every push — only the version counter triggers renders.
- `streamingVersion` must be passed through to `InlinePipelineView` as a prop so it re-renders on new chunks. The prop exists in the interface but was added after initial implementation — check that the type declaration includes it if the component is refactored.

## CampaignsTab Architecture

`CampaignsTab.tsx` is fully self-contained — it loads campaigns on mount and manages all state internally. No pipeline state needed.

Sub-components (all defined in the same file):
- `CharacterList` — reusable character input list with add/remove
- `SeasonRow` — single season with inline edit mode
- `CampaignCard` — collapsible card with header actions (edit pencil, trash, D&D Beyond link), edit form, and season management
- `CreateCampaignForm` — standalone create form used when "New Campaign" is clicked

**D&D Beyond URL handling:** stored as `beyond_url` on the campaign object. Empty string `""` = no link. `api('open_path', url)` sends it to backend which calls macOS `open` — this works for both URLs and filesystem paths (backend detects `http://`/`https://` prefix).

**`Campaign` type** (in `api.ts`):
```ts
interface Campaign {
  id: string
  name: string
  beyond_url?: string   // optional — absent on old campaigns, "" after first edit
  seasons: Season[]
}
```

**`update_campaign` API call:**
```ts
await api('update_campaign', campaignId, name, beyondUrl)
// beyondUrl is always a string — pass "" to clear the link
```

## Common Gotchas

- **`streamingVersion` prop**: `InlinePipelineView` takes `streamingVersion: number` in its props type. If you add new props to this component, make sure to add them to both the destructuring and the inline type.
- **`summary` in `SessionEntry`**: `files.summary: boolean` and `summary_path: string | null` must be present in both `api.ts` types and `backend.py`'s `get_sessions()` response. They were added together.
- **Light/dark mode**: toggled by adding/removing the `light` class on `document.documentElement`. CSS vars are defined in `index.css` under `:root` (dark) and `.light` (light). The theme toggle button is in the header in `App.tsx`. Light mode has boosted opacity overrides for `text-parchment/*` classes (e.g. `/35` maps to alpha 0.50 in light mode, not 0.35) and darker gold (`#8B7228`) for contrast on cream backgrounds. Glows are disabled in light mode.
- **TitleScreen z-index**: rendered absolutely on top of the main app. When visible, clicking any option dismisses it. The main app behind it is still mounted but hidden.
- **`Tab` type in App.tsx**: currently `'characters' | 'library' | 'glossary' | 'chronicle'`. If you add a new tab, add it here AND to the `TABS` array AND add the render block in the `<main>` section. SessionTab is NOT a tab — it's a fullscreen overlay controlled by `showNewSession` state.
- **`showNewSession` state**: Controls the fullscreen SessionTab overlay. When true, tab bar is hidden and SessionTab renders fullscreen. Back arrow returns to main tabs. If pipeline is running, it continues in background. Library shows active session card for re-entry.
- **`api()` async pattern**: always use `async/await` inside `useEffect` (wrap in a named inner async function). The `.then()` pattern can cause TypeScript inference issues with the generic return type.
