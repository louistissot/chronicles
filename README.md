# Chronicles

A macOS desktop app for Dungeons & Dragons players that turns session recordings into rich, structured campaign archives.

Record your session (or import audio/transcripts), and Chronicles will transcribe it with speaker diarization, identify who said what, then generate a full suite of artifacts — narrative summaries, DM notes, timelines, character updates, NPC profiles, loot tracking, quest logs, location maps, scene illustrations, and a living campaign glossary.

## What it does

1. **Record or import** — Built-in audio recording with pause/resume, or drag-and-drop audio files (`.m4a`, `.mp3`, `.wav`, etc.) and transcripts (`.json`, `.txt`, `.srt`)
2. **Transcribe** — WhisperX speech-to-text with speaker diarization, glossary-aware proper noun correction
3. **Identify speakers** — LLM maps speaker IDs to character names using transcript content, character backstories, and campaign context. Shows confidence scores and evidence for DM review
4. **Generate artifacts** — Streaming LLM pipeline produces 11+ structured outputs per session:

| Artifact | Description |
|---|---|
| **Timeline** | 8-15 key events with fantasy icons, hover/pin details |
| **Summary** | Narrative prose recap for reading aloud next session |
| **DM Notes** | Structured hooks, loose ends, NPC notes, loot tracking |
| **Character Updates** | Per-character development notes and history entries |
| **Glossary** | Auto-extracted NPCs, locations, factions, items, spells — smart-merged into campaign glossary |
| **Leaderboard** | Per-hero combat stats (kills, damage, nat 20s) |
| **Locations** | Visited locations with descriptions, connections, spatial relationships |
| **NPCs** | Every NPC encountered with race, role, attitude, actions, status |
| **Loot** | Items acquired + gold transactions with full provenance |
| **Missions** | Quests started/continued/completed with objectives and rewards |
| **Scenes** | Cinematic scene prompts for illustration |
| **Illustration** | AI-generated session artwork via Gemini |

5. **Review & refine** — Human-in-the-loop review system pauses the pipeline when the LLM's confidence is below 95%, letting the DM accept, edit, or decline proposed entity changes
6. **Chronicles** — Season-level digests weave multiple sessions into epic narrative arcs with timelines, character arcs, and unresolved threads

## Screenshots

*Coming soon*

## Tech Stack

- **Frontend**: React 18 + TypeScript + Tailwind CSS + shadcn/ui + Lucide icons
- **Backend**: Python 3.9 + pywebview (native macOS window)
- **Transcription**: WhisperX (speech-to-text + speaker diarization)
- **LLM**: Anthropic Claude (default) or OpenAI GPT-4o
- **Image Generation**: Google Gemini
- **D&D Beyond**: Character data sync (public characters)

## Requirements

- **macOS** (uses pywebview + native ObjC for drag-and-drop)
- **Python 3.9** — WhisperX requires this specific version
- **Node.js 18+** — for building the frontend
- **API Keys** (configured in Settings tab):
  - **Anthropic** or **OpenAI** — for LLM pipeline
  - **Hugging Face** — for WhisperX speaker diarization models
  - **Google Gemini** (optional) — for illustration generation

## Installation

### From source

```bash
# Clone
git clone https://github.com/louistissot/chronicles.git
cd chronicles

# Install Python dependencies
pip3.9 install -r requirements.txt

# Install WhisperX (heavy — requires PyTorch)
pip3.9 install whisperx

# Build the frontend
cd frontend && npm install && npm run build && cd ..

# Run
python3.9 main.py
```

### As a macOS app

```bash
# Build frontend first
cd frontend && npm install && npm run build && cd ..

# Package with PyInstaller
pip3.9 install pyinstaller
pyinstaller DnDWhisperX.spec --clean --noconfirm

# Install
cp -R dist/Chronicles.app /Applications/
```

## Development

```bash
# Frontend dev server (hot reload, limited — no Python backend)
cd frontend && npm run dev

# Run full app (requires built frontend)
python3.9 main.py

# TypeScript check
cd frontend && npm run typecheck

# Run tests
python3.9 -m pytest tests/ -v
```

## Project Structure

```
chronicles/
├── main.py                 Entry point — creates pywebview window, native drag-and-drop
├── backend.py              API class exposed to JS — full pipeline orchestration
├── llm.py                  LLM abstraction (Anthropic / OpenAI, blocking + streaming)
├── llm_mapper.py           Speaker-to-character mapping with confidence + evidence
├── postprocess.py          WhisperX output parsing, speaker labeling, glossary correction
├── runner.py               ffmpeg + WhisperX subprocess runner
├── image_gen.py            Gemini image generation (illustrations + portraits)
├── characters.py           Global character registry with history tracking
├── campaigns.py            Campaign + season management with glossary
├── sessions.py             Session registry
├── entities.py             Per-campaign entity registry (locations, items, missions, etc.)
├── beyond.py               D&D Beyond character data fetching
├── config.py               API token + preferences storage
├── log.py                  Rotating file logger
├── DnDWhisperX.spec        PyInstaller packaging spec
├── requirements.txt        Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.tsx                  Root — global state, tab navigation, pipeline events
│   │   ├── components/
│   │   │   ├── SessionTab.tsx       Campaign setup, audio recording, transcript import
│   │   │   ├── InlinePipelineView   Pipeline progress, speaker review, entity review
│   │   │   ├── LibraryTab.tsx       Session list with search, filters, sort
│   │   │   ├── SessionDetailScreen  Full session detail (12 tabs of artifacts)
│   │   │   ├── CharactersTab.tsx    Character gallery with search, filter, sort
│   │   │   ├── GlossaryTab.tsx      Campaign glossary editor
│   │   │   ├── ChronicleTab.tsx     Season digests with timeline + narrative
│   │   │   ├── EntityReviewPanel    Human-in-the-loop entity review cards
│   │   │   ├── HorizontalTimeline   Shared scrollable event timeline
│   │   │   ├── CampaignsTab.tsx     Campaign + season management
│   │   │   ├── TitleScreen.tsx      Splash screen
│   │   │   ├── SettingsTab.tsx      API keys, model selection, theme
│   │   │   └── ui/                  shadcn/ui primitives
│   │   └── lib/
│   │       ├── api.ts               pywebview bridge types + helpers
│   │       └── utils.ts             Tailwind class merge utility
│   └── package.json
└── tests/                  pytest suite (300+ tests)
```

## Data Storage

All persistent data is stored in `~/.config/dnd-whisperx/`:

| File | Contents |
|---|---|
| `prefs.json` | API tokens + UI preferences |
| `sessions.json` | Session registry with file paths |
| `campaigns.json` | Campaigns, seasons, glossary |
| `characters.json` | Global character registry |
| `entities/<id>.json` | Per-campaign entity registry |
| `digests/<id>.json` | Season digest + timeline |
| `characters/<id>/` | Character portraits and avatars |
| `app.log` | Rotating application log |

Session output files are written to `~/Documents/Chronicles/<Campaign>/Season N/<date>/`.

## Pipeline Architecture

The pipeline runs in a background thread. Each stage notifies the frontend via `evaluate_js()`:

```
Audio → [transcription] → [transcript_correction] → [speaker_mapping] →
[updating_transcript] → [timeline] → [summary] → [dm_notes] →
[character_updates] → [glossary] → [leaderboard] → [locations] →
[npcs] → [loot] → [missions] → [scenes] → [illustration]
```

- **Glossary always runs** — it feeds accuracy into all downstream stages
- **Other artifacts are optional** — users can uncheck them before starting
- **Entity stages have confidence scoring** — the LLM rates each extraction 0-100, and low-confidence items (<95%) pause for DM review
- **Speaker mapping retries** — if any speaker is below 90% confidence, the pipeline retries with more transcript samples before asking for manual review

## License

*TBD*

## Acknowledgments

Built with [Claude](https://claude.ai) by Anthropic. Uses [WhisperX](https://github.com/m-bain/whisperX) for transcription, [Gemini](https://ai.google.dev/) for image generation, and [shadcn/ui](https://ui.shadcn.com/) for UI components.
