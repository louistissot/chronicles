# Chronicles — Frontend Guide

## Stack

- **React 18** + **TypeScript** (strict), **Vite** (port 5173, builds to `dist/`)
- **Tailwind CSS** (utility classes only), **shadcn/ui** (`src/components/ui/`), **Lucide React** icons

## Commands

```bash
npm install          # install deps
npm run dev          # dev server (limited — no Python backend)
npm run build        # production build (required before Python app)
npm run typecheck    # tsc --noEmit
```

## Component Map

```
src/
├── App.tsx                      Root. Global state: activeTab, pipeline stages, streaming chunks.
│                                Tabs: characters | library | glossary | chronicle
│                                "+ New Session" CTA → fullscreen SessionTab overlay.
├── components/
│   ├── TitleScreen.tsx          Splash screen. NEW CAMPAIGN / CONTINUE / OPTIONS.
│   ├── SessionTab.tsx           Campaign/season setup, recording/upload, transcript import.
│   │                            Shows InlinePipelineView during processing. Fullscreen overlay.
│   ├── InlinePipelineView.tsx   Pipeline progress: sidebar stages, recording controls,
│   │                            speaker mapping review, entity review, streaming output.
│   ├── EntityReviewPanel.tsx    Card-based DM review for low-confidence entities.
│   │                            Accept/Edit/Decline per card. Batch actions.
│   ├── HorizontalTimeline.tsx   Scrollable timeline rail. Used by SessionDetail + ChronicleTab.
│   ├── CampaignsTab.tsx         Campaign CRUD. Self-contained. Sub-components inline.
│   ├── CharactersTab.tsx        Character list + CharacterDetail with profile/history/portraits.
│   │                            NPCs show enriched data: race, role, attitude, status, session history.
│   ├── LibraryTab.tsx           Session list → SessionDetailScreen on click.
│   ├── MapsTab.tsx              Interactive campaign map (React Flow) + location list toggle.
│   │                            Custom LocationNode with golden icons per location_type.
│   │                            Plane tabs, draggable nodes, detail panel, edge styles per travel_type.
│   ├── GlossaryTab.tsx          Campaign glossary editor. Faction/Item/Spell/Other only (NPC/Location routed out).
│   ├── ChronicleTab.tsx         Season digest + timeline generator via LLM.
│   ├── SessionDetailScreen.tsx  Session detail: Info/Summary/Timeline/Transcript/DM Notes/
│   │                            Glossary/Locations/NPCs/Loot/Missions/Illustration.
│   ├── SettingsTab.tsx          API tokens, model/provider, theme.
│   ├── MarkdownRenderer.tsx     Custom markdown parser for LLM content. No external lib.
│   └── ui/                      shadcn primitives (do not edit).
├── lib/
│   ├── api.ts                   pywebview bridge. api() helper + Window augmentations.
│   └── utils.ts                 cn() tailwind class merge.
└── index.css                    Tailwind base + CSS vars + font-face.
```

## Design System

D&D parchment aesthetic, dark default + light mode.

| Token | Dark | Role |
|---|---|---|
| `text-gold` | `#D4AF37` | Primary accent |
| `text-parchment` | `#E8DFC0` | Body text |
| `bg-void` | `#080B14` | Deepest background |
| `bg-shadow` | `#0D1120` | Panel/card background |

Opacity modifiers (`/70`, `/40`, `/20`) for hierarchy. Never pure black/white.
Fonts: `font-display`/`font-heading` (Cinzel), `font-body` (Crimson Text), `font-mono` (system).
Light mode: boosted opacity, darker gold (`#8B7228`), glows disabled.

## Pipeline State Flow

`App.tsx` owns pipeline state, passes down as props:
- `appState.stages: Record<PipelineStage, { status, data, error }>`
- `streamingChunksRef` / `logLinesRef` — append-only refs, version counters trigger re-renders
- Stage order: `transcription → saving_transcript → transcript_correction → speaker_mapping → updating_transcript → transcript_review → timeline → summary → dm_notes → character_updates → glossary → leaderboard → locations → npcs → loot → missions → illustration`

Status values: `idle | running | done | error | needs_review`

## JS ↔ Python Events

Set on `window` in `App.tsx` useEffect: `_receiveLog`, `_onPipelineStage`, `_onLLMChunk`, `_pyDragDrop`.

## API Bridge

```ts
import { api } from '@/lib/api'
const result = await api('get_campaigns')  // Calls window.pywebview.api.*
```

Key types: `SessionEntry`, `Campaign`, `Season`, `CharacterInfo`, `TimelineEvent`, `PipelineStage`, `StageStatus`

## SessionDetailScreen

Tabs: **Info → Summary → Timeline → Transcript → DM Notes → Glossary → Locations → NPCs → Loot → Missions → Illustration**

All tabs lazy-load (no caching). Download buttons per tab. "Generate" button for missing artifacts. Streaming preview during generation. Auto-refresh after `run_single_stage` via `refreshCounter`.

Tab states: (1) gold/active, (2) normal parchment (data exists), (3) dimmed italic (no data). Tabs without transcript are disabled. Audio-only sessions show "Process Audio" button in Info tab.

Cross-tab navigation: `onNavigateToCharacter(charId)` → CharactersTab.

## LibraryTab

Session list with search, campaign/season filters, sort. Active session pinned at top with gold ring. Hero names as clickable tags via `character_map`. Clicking active session → SessionTab processing view.

## SessionTab — Fullscreen Overlay

Setup mode (campaign/season/audio) or InlinePipelineView (processing). Recording as pseudo-stage with pause/resume/stop. Skip buttons for LLM stages. Optional artifact checkboxes.

## Key Conventions

- All API calls via `await api('method', ...args)` — never `window.pywebview.api` directly.
- `cn()` from `@/lib/utils` for conditional Tailwind classes.
- Version-bump pattern: refs for data, `setXVersion(v => v + 1)` to trigger renders.
- `streamingVersion` must be passed as prop to `InlinePipelineView`.
- `async/await` in useEffect (named inner function) — avoid `.then()` pattern.

## Common Gotchas

- **`streamingVersion` prop**: must be in both InlinePipelineView's type declaration and destructuring.
- **`Tab` type**: `'characters' | 'library' | 'maps' | 'glossary' | 'chronicle'`. New tabs need: type + TABS array + render block. SessionTab is overlay, not tab.
- **`showNewSession` state**: controls fullscreen overlay. Pipeline continues in background when dismissed.
- **Light/dark mode**: `.light` class on `documentElement`. CSS vars in `index.css` under `:root` (dark) and `.light`.
- **`api()` stubs**: many calls return null in Vite dev mode. Full testing requires `python3.9 main.py`.
- **React hooks before early returns**: ALL hooks (`useState`, `useEffect`, `useMemo`, `useCallback`) MUST be called BEFORE any `if (...) return` statement in a component. Moving hooks after early returns causes React error #310 and crashes the tab.
- **TabErrorBoundary**: App.tsx wraps tab content in `TabErrorBoundary` to prevent component crashes from blanking the entire app. New tabs automatically benefit.
- **MapCanvas separation**: React Flow code is isolated in `MapCanvas.tsx` (separate from `MapsTab.tsx`) to contain any React Flow initialization failures.
