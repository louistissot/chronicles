/**
 * SessionDetailScreen — full-screen detail view for a library session.
 * Shows Info, Timeline, Transcript, and DM Notes tabs.
 */
import { useState, useEffect, useRef } from 'react'
import { api, type SessionEntry, type TimelineEvent, type GlossaryEntry, type PipelineStage } from '@/lib/api'
import type { PipelineStages } from '@/App'
import {
  ArrowLeft, Loader2, ChevronDown, ChevronUp, Copy, Check,
  Mic, FileText, FileJson, ScrollText, Clock, Clapperboard,
  FolderOpen, AlertCircle, BookOpen, Wand2, Image, Users,
  Search, Compass, Sparkles, Gem, Trophy,
  Settings2, Download, Scroll, RefreshCw,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { MarkdownRenderer } from '@/components/MarkdownRenderer'
import { HorizontalTimeline, TimelineIcon, importanceColor } from './HorizontalTimeline'


// ── Transcription Settings Constants ─────────────────────────────────────────

const WHISPERX_MODELS = [
  { value: 'large-v3', label: 'large-v3 — Best accuracy' },
  { value: 'large-v2', label: 'large-v2 — Recommended' },
  { value: 'medium',   label: 'medium — Balanced' },
  { value: 'small',    label: 'small — Fast' },
  { value: 'base',     label: 'base — Fastest' },
  { value: 'tiny',     label: 'tiny — Minimal' },
]

const WHISPERX_LANGUAGES = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'en',   label: 'English' },
  { value: 'fr',   label: 'French' },
  { value: 'de',   label: 'German' },
  { value: 'es',   label: 'Spanish' },
  { value: 'it',   label: 'Italian' },
  { value: 'pt',   label: 'Portuguese' },
  { value: 'nl',   label: 'Dutch' },
  { value: 'ru',   label: 'Russian' },
  { value: 'zh',   label: 'Chinese' },
  { value: 'ja',   label: 'Japanese' },
  { value: 'ko',   label: 'Korean' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string): { date: string; time: string } {
  const d = new Date(iso)
  return {
    date: d.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }),
    time: d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
  }
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        })
      }}
      className="flex-none p-1.5 rounded text-parchment/30 hover:text-gold hover:bg-gold/10 transition-colors"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

// ── File status badge ─────────────────────────────────────────────────────────

function StatusBadge({ available, label, icon: Icon }: { available: boolean; label: string; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <div className={cn(
      'flex items-center gap-1.5 px-3 py-2 rounded-md border text-sm font-body',
      available
        ? 'bg-emerald-500/8 border-emerald-500/20 text-emerald-400/80'
        : 'bg-white/3 border-white/8 text-parchment/25'
    )}>
      <Icon className="w-3.5 h-3.5 flex-none" />
      {label}
    </div>
  )
}

// ── Generate button for missing artifacts ─────────────────────────────────────

function GenerateArtifactButton({
  stage, label, generating, onGenerate,
}: { stage: string; label: string; generating: Set<string>; onGenerate: (stage: string) => void }) {
  const isGen = generating.has(stage)
  return (
    <div className="flex flex-col items-center gap-3 py-8">
      <p className="text-sm text-parchment/30 font-body">
        No {label.toLowerCase()} has been generated for this session yet.
      </p>
      <button
        onClick={() => onGenerate(stage)}
        disabled={isGen}
        className={cn(
          'flex items-center gap-2 px-4 py-2 rounded-md border text-sm font-heading uppercase tracking-widest transition-all',
          isGen
            ? 'border-gold/30 bg-gold/10 text-gold cursor-wait'
            : 'border-gold/30 text-gold hover:bg-gold/10 hover:border-gold/50',
        )}
      >
        {isGen ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
        {isGen ? `Generating ${label}…` : `Generate ${label}`}
      </button>
    </div>
  )
}

// ── DM Notes Table of Contents ────────────────────────────────────────────────

function extractHeadings(content: string) {
  const lines = content.split('\n')
  const headings: { level: number; text: string; id: string }[] = []
  let counter = 0
  for (const line of lines) {
    const m = line.match(/^(#{1,3})\s+(.+)$/)
    if (m) {
      headings.push({
        level: m[1].length,
        text: m[2].replace(/\*\*/g, '').replace(/\*/g, ''),
        id: `md-heading-${counter}`,
      })
      counter++
    }
  }
  return headings
}

function DmNotesToc({ headings }: { headings: { level: number; text: string; id: string }[] }) {
  return (
    <nav className="flex-none w-52 hidden lg:block self-start sticky top-4">
      <div className="max-h-[80vh] overflow-y-auto py-1">
        <p className="text-[10px] font-heading text-parchment/30 uppercase tracking-widest mb-3">Contents</p>
        <ul className="space-y-1">
          {headings.map((h, i) => (
            <li key={i}>
              <a
                href={`#${h.id}`}
                onClick={(e) => {
                  e.preventDefault()
                  document.getElementById(h.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }}
                className={cn(
                  'block text-xs font-body text-parchment/40 hover:text-gold transition-colors leading-snug py-0.5',
                  h.level === 1 && 'font-heading text-parchment/55',
                  h.level === 2 && 'pl-3',
                  h.level === 3 && 'pl-6 text-parchment/30',
                )}
              >
                {h.text}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  )
}

// ── Timeline Streaming Preview ────────────────────────────────────────────────

function TimelineStreamingPreview({ text }: { text: string }) {
  // Try to parse partial JSON — find last complete object in array
  const parsed = (() => {
    try {
      // Try full parse first
      const arr = JSON.parse(text)
      if (Array.isArray(arr)) return arr as TimelineEvent[]
    } catch { /* partial */ }
    try {
      // Strip markdown fences
      let cleaned = text.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim()
      // Find last } and try to close the array
      const lastBrace = cleaned.lastIndexOf('}')
      if (lastBrace > 0) {
        const truncated = cleaned.slice(0, lastBrace + 1)
        // Ensure it starts with [
        const arrStart = truncated.indexOf('[')
        if (arrStart >= 0) {
          const candidate = truncated.slice(arrStart) + ']'
          const arr = JSON.parse(candidate)
          if (Array.isArray(arr)) return arr as TimelineEvent[]
        }
      }
    } catch { /* can't parse yet */ }
    return null
  })()

  if (parsed && parsed.length > 0) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Loader2 className="w-4 h-4 text-gold animate-spin" />
          <span className="text-xs text-gold/60 font-body">Generating timeline… {parsed.length} events so far</span>
        </div>
        <HorizontalTimeline events={parsed} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Loader2 className="w-4 h-4 text-gold animate-spin" />
        <span className="text-xs text-gold/60 font-body">Generating timeline…</span>
      </div>
      <pre className="text-xs text-parchment/40 font-mono leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto bg-white/3 rounded-md p-3 border border-white/5">
        {text.slice(-500) || 'Starting…'}
      </pre>
    </div>
  )
}

// ── Error banner ───────────────────────────────────────────────────────────────

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-red-500/8 border border-red-500/20 px-4 py-3">
      <AlertCircle className="w-3.5 h-3.5 text-red-400 flex-none mt-0.5" />
      <p className="text-sm text-red-400 font-body">{message}</p>
    </div>
  )
}

// ── Loading spinner ────────────────────────────────────────────────────────────

function LoadingSpinner({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16">
      <Loader2 className="w-5 h-5 text-parchment/20 animate-spin" />
      <p className="text-xs text-parchment/25 font-body">{label}</p>
    </div>
  )
}

// ── Download button ──────────────────────────────────────────────────────────

function DownloadButton({ path, label }: { path: string; label?: string }) {
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  return (
    <button
      onClick={async () => {
        setBusy(true)
        await api('download_file', path)
        setBusy(false)
        setDone(true)
        setTimeout(() => setDone(false), 2000)
      }}
      disabled={busy}
      className="flex items-center gap-1 px-2 py-1 rounded border border-white/8 text-[10px] text-parchment/40 hover:text-gold hover:border-gold/30 transition-colors disabled:opacity-30"
      title={label || 'Download'}
    >
      {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : done ? <Check className="w-3 h-3 text-emerald-400" /> : <Download className="w-3 h-3" />}
    </button>
  )
}

// ── Glossary tab content (session read-only view) ───────────────────────────

function GlossaryTabContent({ entries, categories, catCounts }: {
  entries: [string, GlossaryEntry][]
  categories: string[]
  catCounts: Record<string, number>
}) {
  const [activeCat, setActiveCat] = useState('All')
  const [search, setSearch] = useState('')

  const filtered = entries
    .filter(([term, info]) => {
      if (activeCat !== 'All' && info.category !== activeCat) return false
      if (search) {
        const q = search.toLowerCase()
        return term.toLowerCase().includes(q) ||
          info.definition?.toLowerCase().includes(q) ||
          info.description?.toLowerCase().includes(q)
      }
      return true
    })
    .sort(([a], [b]) => a.localeCompare(b))

  return (
    <div className="space-y-3">
      {/* Category pills */}
      <div className="flex flex-wrap gap-1.5">
        {categories.map(cat => {
          const count = catCounts[cat] || 0
          const isActive = activeCat === cat
          return (
            <button
              key={cat}
              onClick={() => setActiveCat(cat)}
              className={cn(
                'px-2.5 py-1 rounded-full text-[10px] font-heading uppercase tracking-wider transition-colors',
                isActive
                  ? 'bg-gold/20 text-gold border border-gold/30'
                  : 'bg-void/40 text-parchment/40 border border-white/6 hover:border-gold/20 hover:text-parchment/60'
              )}
            >
              {cat} {count > 0 && <span className="text-[9px] opacity-60">({count})</span>}
            </button>
          )
        })}
      </div>

      {/* Search */}
      <input
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Search terms…"
        className="w-full h-7 bg-void/60 border border-white/8 rounded px-3 text-xs text-parchment/60 outline-none focus:border-gold/40 placeholder:text-parchment/20"
      />

      {/* Term list */}
      <p className="text-xs text-parchment/30 uppercase tracking-widest font-body">
        {filtered.length} term{filtered.length !== 1 ? 's' : ''}
      </p>
      <div className="space-y-2">
        {filtered.map(([term, info]) => (
          <div key={term} className="rounded-md border border-white/5 bg-void/30 px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-body text-parchment/80 font-semibold">{term}</span>
              <span className="text-[9px] font-heading uppercase tracking-wider text-gold/50 bg-gold/8 px-1.5 py-0.5 rounded-full">
                {info.category}
              </span>
            </div>
            {info.definition && (
              <p className="mt-1 text-xs text-parchment/55 font-body leading-relaxed">{info.definition}</p>
            )}
            {info.description && (
              <p className="mt-1 text-[11px] text-parchment/35 font-body leading-relaxed italic">{info.description}</p>
            )}
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <p className="text-xs text-parchment/25 font-body italic py-2">No terms match this filter.</p>
      )}
    </div>
  )
}

// ── Tab definitions ────────────────────────────────────────────────────────────

type DetailTab = 'info' | 'summary' | 'timeline' | 'transcript' | 'notes' | 'glossary' | 'locations' | 'npcs' | 'loot' | 'missions'

// ── Props ─────────────────────────────────────────────────────────────────────

interface SessionDetailScreenProps {
  session: SessionEntry
  onBack: () => void
  onUpdated: (fields: Partial<SessionEntry>) => void
  onViewPipeline?: () => void
  onRefresh?: () => void
  /** Global pipeline stages from App.tsx — used to track async generation progress */
  stages?: PipelineStages
  /** Streaming LLM chunks keyed by stage — for live timeline preview */
  streamingChunks?: Record<string, string>
  /** Version counter that bumps on each new chunk */
  streamingVersion?: number
  /** Navigate to a character by ID (cross-tab) */
  onNavigateToCharacter?: (charId: string) => void
}

// ── Main component ────────────────────────────────────────────────────────────

export function SessionDetailScreen({ session, onBack, onViewPipeline, onRefresh, stages, streamingChunks, streamingVersion, onNavigateToCharacter }: SessionDetailScreenProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>('info')
  const [transcriptContent, setTranscriptContent] = useState<string | null>(null)
  const [summaryContent, setSummaryContent] = useState<string | null>(null)
  const [dmNotesContent, setDmNotesContent] = useState<string | null>(null)
  const [timelineData, setTimelineData] = useState<TimelineEvent[] | null>(null)
  // scenesData removed — scenes stage no longer exists
  const [glossaryData, setGlossaryData] = useState<Record<string, GlossaryEntry> | null>(null)
  const [locationsData, setLocationsData] = useState<any[] | null>(null)
  const [npcsData, setNpcsData] = useState<any[] | null>(null)
  const [lootData, setLootData] = useState<any | null>(null)
  const [missionsData, setMissionsData] = useState<any[] | null>(null)
  const [leaderboardData, setLeaderboardData] = useState<any | null>(null)
  const [generatingSet, setGeneratingSet] = useState<Set<string>>(new Set())
  const [refreshCounter, setRefreshCounter] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [showProcessModal, setShowProcessModal] = useState(false)
  const [wxModel, setWxModel] = useState('large-v2')
  const [wxLanguage, setWxLanguage] = useState('auto')
  const [generatingTitle, setGeneratingTitle] = useState(false)

  const displayName = session.display_name ||
    `${session.campaign_name}${session.season_number ? ` · S${session.season_number}` : ''}`
  const { date, time } = formatDate(session.date)
  const names = session.character_names.filter(Boolean)

  async function loadSummary() {
    if (!session.summary_path || !session.files.summary) return
    setLoading(true)
    setLoadError(null)
    const result = await api('read_file', session.summary_path)
    if (result?.ok) setSummaryContent(result.content)
    else setLoadError(result?.error || 'Failed to load summary')
    setLoading(false)
  }

  async function loadTranscript() {
    if (!session.txt_path || !session.files.transcript) {
      setLoadError('No transcript file available for this session.')
      return
    }
    setLoading(true)
    setLoadError(null)
    const result = await api('read_file', session.txt_path)
    if (result?.ok) setTranscriptContent(result.content)
    else setLoadError(result?.error || 'Failed to load transcript')
    setLoading(false)
  }

  async function loadDmNotes() {
    if (!session.dm_notes_path || !session.files.dm_notes) return
    setLoading(true)
    setLoadError(null)
    const result = await api('read_file', session.dm_notes_path)
    if (result?.ok) setDmNotesContent(result.content)
    else setLoadError(result?.error || 'Failed to load DM notes')
    setLoading(false)
  }

  async function loadTimeline() {
    if (!session.timeline_path || !session.files.timeline) return
    setLoading(true)
    setLoadError(null)
    const result = await api('read_file', session.timeline_path)
    if (result?.ok) {
      try {
        setTimelineData(JSON.parse(result.content))
      } catch {
        setLoadError('Failed to parse timeline data.')
      }
    } else {
      setLoadError(result?.error || 'Failed to load timeline')
    }
    setLoading(false)
  }

  async function loadGlossary() {
    if (!session.glossary_path || !session.files.glossary) return
    setLoading(true)
    setLoadError(null)
    const result = await api('read_file', session.glossary_path)
    if (result?.ok) {
      try {
        setGlossaryData(JSON.parse(result.content))
      } catch {
        setLoadError('Failed to parse glossary data.')
      }
    } else {
      setLoadError(result?.error || 'Failed to load glossary')
    }
    setLoading(false)
  }

  async function loadLocations() {
    if (!session.locations_path || !session.files.locations) return
    setLoading(true); setLoadError(null)
    const result = await api('read_file', session.locations_path)
    if (result?.ok) { try { setLocationsData(JSON.parse(result.content)) } catch { setLoadError('Failed to parse locations.') } }
    else { setLoadError(result?.error || 'Failed to load locations') }
    setLoading(false)
  }

  async function loadNpcs() {
    if (!session.npcs_path || !session.files.npcs) return
    setLoading(true); setLoadError(null)
    const result = await api('read_file', session.npcs_path)
    if (result?.ok) { try { setNpcsData(JSON.parse(result.content)) } catch { setLoadError('Failed to parse NPCs.') } }
    else { setLoadError(result?.error || 'Failed to load NPCs') }
    setLoading(false)
  }

  async function loadLoot() {
    if (!session.loot_path || !session.files.loot) return
    setLoading(true); setLoadError(null)
    const result = await api('read_file', session.loot_path)
    if (result?.ok) { try { setLootData(JSON.parse(result.content)) } catch { setLoadError('Failed to parse loot.') } }
    else { setLoadError(result?.error || 'Failed to load loot') }
    setLoading(false)
  }

  async function loadMissions() {
    if (!session.missions_path || !session.files.missions) return
    setLoading(true); setLoadError(null)
    const result = await api('read_file', session.missions_path)
    if (result?.ok) { try { setMissionsData(JSON.parse(result.content)) } catch { setLoadError('Failed to parse missions.') } }
    else { setLoadError(result?.error || 'Failed to load missions') }
    setLoading(false)
  }

  async function loadLeaderboard() {
    if (!session.leaderboard_path || !session.files.leaderboard) return
    setLoading(true); setLoadError(null)
    const result = await api('read_file', session.leaderboard_path)
    if (result?.ok) { try { setLeaderboardData(JSON.parse(result.content)) } catch { setLoadError('Failed to parse leaderboard.') } }
    else { setLoadError(result?.error || 'Failed to load leaderboard') }
    setLoading(false)
  }

  useEffect(() => {
    setLoadError(null)
    if (activeTab === 'summary') { loadSummary(); loadLeaderboard() }
    if (activeTab === 'transcript') loadTranscript()
    if (activeTab === 'notes') loadDmNotes()
    if (activeTab === 'timeline') loadTimeline()
    if (activeTab === 'glossary') loadGlossary()
    if (activeTab === 'locations') loadLocations()
    if (activeTab === 'npcs') loadNpcs()
    if (activeTab === 'loot') loadLoot()
    if (activeTab === 'missions') loadMissions()
  }, [activeTab, refreshCounter, session]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate(stage: string) {
    setGeneratingSet(prev => new Set(prev).add(stage))
    setLoadError(null)
    try {
      const result = await api('run_single_stage', session.id, stage)
      if (!result?.ok) {
        setLoadError(result?.error || 'Generation failed')
        setGeneratingSet(prev => { const next = new Set(prev); next.delete(stage); return next })
      }
      // result.ok means the background thread started — stage completion
      // will be detected via the stages prop from App.tsx (see useEffect below)
    } catch (e: any) {
      setLoadError(e?.message || 'Generation failed')
      setGeneratingSet(prev => { const next = new Set(prev); next.delete(stage); return next })
    }
  }

  // Watch global stages for async generation completion
  useEffect(() => {
    if (generatingSet.size === 0 || !stages) return
    for (const gen of generatingSet) {
      const stageState = stages[gen as PipelineStage]
      if (!stageState) continue
      if (stageState.status === 'done') {
        setGeneratingSet(prev => { const next = new Set(prev); next.delete(gen); return next })
        onRefresh?.()
        setRefreshCounter(c => c + 1)
      } else if (stageState.status === 'error') {
        setLoadError(stageState.error || 'Generation failed')
        setGeneratingSet(prev => { const next = new Set(prev); next.delete(gen); return next })
      }
    }
  }, [stages, generatingSet]) // eslint-disable-line react-hooks/exhaustive-deps

  const hasTranscript = session.files.transcript
  const tabs: { id: DetailTab; label: string; available: boolean; hasData: boolean }[] = [
    { id: 'info',          label: 'Info',          available: true,           hasData: true },
    { id: 'summary',       label: 'Summary',       available: hasTranscript,  hasData: !!session.files.summary },
    { id: 'timeline',      label: 'Timeline',      available: hasTranscript,  hasData: !!session.files.timeline },
    { id: 'transcript',    label: 'Transcript',    available: session.files.transcript, hasData: session.files.transcript },
    { id: 'notes',         label: 'DM Notes',      available: hasTranscript,  hasData: !!session.files.dm_notes },
    { id: 'glossary',      label: 'Glossary',      available: hasTranscript,  hasData: !!session.files.glossary },
    { id: 'locations',     label: 'Locations',     available: hasTranscript,  hasData: !!session.files.locations },
    { id: 'npcs',          label: 'NPCs',          available: hasTranscript,  hasData: !!session.files.npcs },
    { id: 'loot',          label: 'Loot',          available: hasTranscript,  hasData: !!session.files.loot },
    { id: 'missions',      label: 'Missions',      available: hasTranscript,  hasData: !!session.files.missions },
  ]

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-none px-6 pt-5 pb-3 border-b border-white/5">
        <div className="flex items-start gap-3">
          <button
            onClick={onBack}
            className="flex-none mt-0.5 p-1.5 rounded-md text-parchment/35 hover:text-gold/70 hover:bg-white/5 transition-colors"
            title="Back to library"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <h2 className={cn(
                "text-base font-heading leading-tight truncate",
                generatingTitle ? "text-gold/50 animate-pulse" : "text-parchment/90"
              )}>
                {generatingTitle ? 'Channeling the muse…' : displayName}
              </h2>
              {hasTranscript && (
                <button
                  disabled={generatingTitle}
                  onClick={async () => {
                    setGeneratingTitle(true)
                    try {
                      const result = await api('generate_session_title', session.id)
                      if (result?.ok) onRefresh?.()
                    } finally {
                      setGeneratingTitle(false)
                    }
                  }}
                  className={cn(
                    "p-1 rounded transition-colors",
                    generatingTitle
                      ? "text-gold/50 animate-spin"
                      : "text-parchment/25 hover:text-gold/70 hover:bg-white/5"
                  )}
                  title="Generate session title"
                >
                  <Sparkles className="w-3 h-3" />
                </button>
              )}
            </div>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              <span className="text-xs text-parchment/35 font-body">{date}</span>
              <span className="text-xs text-parchment/20 font-body">{time}</span>
              {names.length > 0 && (
                <>
                  <span className="text-parchment/15 text-xs">·</span>
                  <span className="text-xs text-parchment/30 font-body truncate">{names.join(' · ')}</span>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-none">
            {onViewPipeline && (
              <button
                onClick={onViewPipeline}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-gold/20 text-xs text-parchment/40
                  hover:text-gold hover:border-gold/40 transition-colors"
                title="Back to processing view"
              >
                <ArrowLeft className="w-3 h-3" />Pipeline
              </button>
            )}
            <button
              onClick={() => api('open_path', session.output_dir)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-white/10 text-xs text-parchment/35
                hover:text-gold hover:border-gold/30 hover:bg-gold/5 transition-colors"
              title="Open in Finder"
            >
              <FolderOpen className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex gap-1 mt-4">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'px-3 py-1.5 rounded text-xs font-body transition-colors',
                activeTab === tab.id
                  ? 'bg-gold/10 text-gold border border-gold/25'
                  : tab.available && tab.hasData
                  ? 'text-parchment/50 hover:text-parchment/80 hover:bg-white/5 border border-transparent'
                  : tab.available && !tab.hasData
                  ? 'text-parchment/25 hover:text-parchment/40 hover:bg-white/3 border border-transparent italic'
                  : 'text-parchment/20 cursor-not-allowed border border-transparent'
              )}
              disabled={!tab.available && tab.id !== 'info'}
            >
              {tab.label}
              {!tab.available && tab.id !== 'info' && (
                <span className="ml-1.5 text-[9px] text-parchment/15">—</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-6 max-w-6xl mx-auto space-y-4">
          {loadError && <ErrorBanner message={loadError} />}

          {/* Info Tab */}
          {activeTab === 'info' && (
            <div className="space-y-5">
              {/* Header illustration / Generate Banner */}
              {session.illustration_path && session.files.illustration ? (
                <div className="relative group/illust">
                  <button
                    onClick={() => api('open_path', session.illustration_path!)}
                    className="w-full rounded-md border border-white/8 overflow-hidden hover:border-gold/30 transition-colors"
                    title="Open illustration in Finder"
                  >
                    <img
                      src={`file://${session.illustration_path}`}
                      alt="Session illustration"
                      className="w-full aspect-video object-cover group-hover/illust:brightness-110 transition-all"
                    />
                  </button>
                  <button
                    onClick={() => handleGenerate('illustration')}
                    disabled={generatingSet.has('illustration')}
                    className="absolute bottom-2 right-2 flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-shadow/80 backdrop-blur-sm border border-gold/25 text-[10px] font-heading text-parchment/60 uppercase tracking-wider opacity-0 group-hover/illust:opacity-100 hover:text-gold hover:border-gold/40 transition-all disabled:opacity-30"
                  >
                    {generatingSet.has('illustration') ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                    Regenerate
                  </button>
                </div>
              ) : hasTranscript && (
                <div className="w-full aspect-video rounded-md border border-dashed border-gold/20 bg-white/2 flex items-center justify-center">
                  <button
                    onClick={() => handleGenerate('illustration')}
                    disabled={generatingSet.has('illustration')}
                    className="flex items-center gap-2 px-4 py-2 rounded border border-gold/25 text-sm text-parchment/50 hover:text-gold hover:border-gold/40 hover:bg-gold/5 transition-colors font-body disabled:opacity-40"
                  >
                    {generatingSet.has('illustration') ? <Loader2 className="w-4 h-4 animate-spin" /> : <Image className="w-4 h-4" />}
                    Generate Banner
                  </button>
                </div>
              )}

              {/* Session metadata */}
              <div className="rounded-md border border-white/8 overflow-hidden">
                <div className="px-4 py-2.5 bg-white/3 border-b border-white/5">
                  <span className="text-xs font-heading text-parchment/50 uppercase tracking-widest">Session Info</span>
                </div>
                <div className="px-4 py-3 space-y-2.5">
                  <MetaRow label="Campaign" value={session.campaign_name} />
                  {session.season_number && <MetaRow label="Season" value={`Season ${session.season_number}`} />}
                  <MetaRow label="Date" value={`${date} at ${time}`} />
                  {names.length > 0 && <MetaRow label="Adventurers" value={names.join(', ')} />}
                  <MetaRow label="Output Folder" value={session.output_dir} mono truncate />
                </div>
              </div>

              {/* Available files */}
              <div>
                <p className="text-xs font-heading text-parchment/40 uppercase tracking-widest mb-3">Available Files</p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  <StatusBadge available={session.files.audio}      label="Audio Recording" icon={Mic} />
                  <StatusBadge available={session.files.transcript} label="Transcript"       icon={FileText} />
                  <StatusBadge available={session.files.srt}        label="SRT Subtitles"   icon={FileJson} />
                  <StatusBadge available={session.files.summary}    label="Summary"         icon={BookOpen} />
                  <StatusBadge available={session.files.dm_notes}   label="DM Notes"        icon={ScrollText} />
                  <StatusBadge available={session.files.timeline}   label="Timeline"        icon={Clock} />
                  <StatusBadge available={session.files.glossary}            label="Glossary"            icon={Search} />
                  <StatusBadge available={session.files.character_updates} label="Character Updates"  icon={Users} />
                  <StatusBadge available={session.files.illustration}  label="Illustration"      icon={Image} />
                  <StatusBadge available={session.files.leaderboard}   label="Leaderboard"       icon={Trophy} />
                  <StatusBadge available={session.files.locations}     label="Locations"          icon={Compass} />
                  <StatusBadge available={session.files.npcs}          label="NPCs"               icon={Users} />
                  <StatusBadge available={session.files.loot}          label="Loot"               icon={Gem} />
                  <StatusBadge available={session.files.missions}      label="Missions"           icon={Scroll} />
                </div>
                {/* Download All */}
                {hasTranscript && (
                  <div className="mt-3">
                    <button
                      onClick={async () => { await api('download_session_zip', session.id) }}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-gold/20 text-xs text-parchment/50 hover:text-gold hover:border-gold/40 transition-colors"
                    >
                      <Download className="w-3 h-3" /> Download All Files
                    </button>
                  </div>
                )}

                {/* Process audio — full pipeline trigger when audio exists but no transcript */}
                {session.files.audio && !session.files.transcript && (
                  <div className="mt-4 rounded-md border border-gold/20 bg-gold/3 p-4 space-y-3">
                    <p className="text-xs text-parchment/50 font-body leading-relaxed">
                      Audio file is ready but hasn't been transcribed yet. Click below to configure and start the full pipeline
                      (transcription, speaker mapping, and all artifact generation).
                    </p>
                    <button
                      disabled={generatingSet.has('transcription')}
                      onClick={async () => {
                        // Load saved prefs into modal state
                        const [savedModel, savedLang] = await Promise.all([
                          api('get_pref', 'model', 'large-v2'),
                          api('get_pref', 'language', 'auto'),
                        ])
                        if (savedModel) setWxModel(savedModel as string)
                        if (savedLang) setWxLanguage(savedLang as string)
                        setShowProcessModal(true)
                      }}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md bg-gold/10 border border-gold/30 text-sm font-heading text-gold uppercase tracking-widest hover:bg-gold/15 hover:border-gold/40 transition-colors disabled:opacity-30"
                    >
                      {generatingSet.has('transcription') ? <Loader2 className="w-4 h-4 animate-spin" /> : <Settings2 className="w-4 h-4" />}
                      {generatingSet.has('transcription') ? 'Starting…' : 'Process Audio'}
                    </button>
                  </div>
                )}
                {/* Re-generate buttons for missing artifacts */}
                {hasTranscript && (
                  <div className="flex flex-wrap gap-2 mt-3">
                    {!session.files.glossary && (
                      <button
                        disabled={generatingSet.has('glossary')}
                        onClick={() => handleGenerate('glossary')}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-gold/20 text-xs text-parchment/50 hover:text-gold hover:border-gold/40 transition-colors disabled:opacity-30"
                      >
                        {generatingSet.has('glossary') ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                        Generate Glossary
                      </button>
                    )}
                    {!session.files.illustration && (
                      <button
                        disabled={generatingSet.has('illustration')}
                        onClick={() => handleGenerate('illustration')}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-gold/20 text-xs text-parchment/50 hover:text-gold hover:border-gold/40 transition-colors disabled:opacity-30"
                      >
                        {generatingSet.has('illustration') ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                        Generate Illustration
                      </button>
                    )}
                    {!session.files.character_updates && (
                      <button
                        disabled={generatingSet.has('character_updates')}
                        onClick={() => handleGenerate('character_updates')}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-gold/20 text-xs text-parchment/50 hover:text-gold hover:border-gold/40 transition-colors disabled:opacity-30"
                      >
                        {generatingSet.has('character_updates') ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                        Generate Character Updates
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Quick tips */}
              {!session.files.timeline && !session.files.dm_notes && (
                <div className="rounded-md border border-gold/10 bg-gold/3 px-4 py-3">
                  <p className="text-xs text-parchment/45 font-body leading-relaxed">
                    Run a session through the pipeline to generate DM Notes, Timeline, and more.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Summary Tab */}
          {activeTab === 'summary' && (
            <div className="space-y-3">
              {/* Leaderboard stats table */}
              {leaderboardData && Object.keys(leaderboardData).length > 0 && (
                <div className="rounded-md border border-gold/15 bg-void/40 overflow-hidden mb-4">
                  <div className="px-3 py-2 bg-gold/5 border-b border-gold/10 flex items-center gap-2">
                    <Trophy className="w-3.5 h-3.5 text-gold/60" />
                    <span className="text-[11px] font-heading text-gold/70 uppercase tracking-widest">Session Leaderboard</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-[10px] font-body">
                      <thead>
                        <tr className="border-b border-white/5">
                          <th className="px-3 py-1.5 text-left text-parchment/40 font-heading uppercase tracking-wider">Hero</th>
                          <th className="px-2 py-1.5 text-center text-parchment/40">Kills</th>
                          <th className="px-2 py-1.5 text-center text-parchment/40">Assists</th>
                          <th className="px-2 py-1.5 text-center text-parchment/40">Damage</th>
                          <th className="px-2 py-1.5 text-center text-parchment/40">Avg d20</th>
                          <th className="px-2 py-1.5 text-center text-parchment/40">Nat 20</th>
                          <th className="px-2 py-1.5 text-center text-parchment/40">Nat 1</th>
                          <th className="px-2 py-1.5 text-center text-parchment/40">Conf.</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(leaderboardData).map(([name, stats]: [string, any]) => (
                          <tr key={name} className="border-b border-white/3 hover:bg-white/2">
                            <td className="px-3 py-1.5 text-parchment/70 font-semibold">{name}</td>
                            <td className="px-2 py-1.5 text-center text-parchment/50">{stats.kills ?? '-'}</td>
                            <td className="px-2 py-1.5 text-center text-parchment/50">{stats.assists ?? '-'}</td>
                            <td className="px-2 py-1.5 text-center text-parchment/50">{stats.total_damage ?? '-'}</td>
                            <td className="px-2 py-1.5 text-center text-parchment/50">{stats.avg_d20 != null ? stats.avg_d20.toFixed(1) : '-'}</td>
                            <td className="px-2 py-1.5 text-center text-gold/60 font-semibold">{stats.nat_20s ?? '-'}</td>
                            <td className="px-2 py-1.5 text-center text-red-400/60 font-semibold">{stats.nat_1s ?? '-'}</td>
                            <td className="px-2 py-1.5 text-center">
                              {stats.confidence != null ? (
                                <span className={cn('text-[10px]',
                                  stats.confidence >= 80 ? 'text-emerald-400/60' :
                                  stats.confidence >= 50 ? 'text-amber-400/60' : 'text-red-400/60'
                                )}>{stats.confidence}%</span>
                              ) : <span className="text-parchment/20">—</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              {!leaderboardData && session.files.transcript && !session.files.leaderboard && (
                <div className="mb-4">
                  <button
                    onClick={() => handleGenerate('leaderboard')}
                    disabled={generatingSet.has('leaderboard')}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-gold/20 text-xs text-parchment/50 hover:text-gold hover:border-gold/40 transition-colors disabled:opacity-30"
                  >
                    {generatingSet.has('leaderboard') ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trophy className="w-3 h-3" />}
                    Generate Leaderboard
                  </button>
                </div>
              )}
              {loading && <LoadingSpinner label="Loading summary…" />}
              {!loading && summaryContent && (
                <div className="rounded-md border border-white/8 overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-2 bg-void/60 border-b border-white/5">
                    <span className="text-xs font-heading text-parchment/50 uppercase tracking-widest">Adventure Summary</span>
                    <div className="flex items-center gap-1.5">
                      {session.summary_path && <DownloadButton path={session.summary_path} />}
                      <CopyButton text={summaryContent} />
                    </div>
                  </div>
                  <div className="px-4 py-4">
                    <MarkdownRenderer text={summaryContent} />
                  </div>
                </div>
              )}
              {generatingSet.has('summary') && streamingChunks?.summary && (
                <div className="rounded-md border border-gold/15 bg-void/30 px-4 py-4 animate-pulse-subtle">
                  <MarkdownRenderer text={streamingChunks.summary} />
                </div>
              )}
              {!loading && !summaryContent && !loadError && !session.files.summary && hasTranscript && !generatingSet.has('summary') && (
                <GenerateArtifactButton stage="summary" label="Summary" generating={generatingSet} onGenerate={handleGenerate} />
              )}
              {!loading && !summaryContent && !loadError && !hasTranscript && (
                <p className="text-sm text-parchment/30 font-body py-4">No transcript available — transcribe a session first.</p>
              )}
            </div>
          )}

          {/* Timeline Tab */}
          {activeTab === 'timeline' && (() => {
            const isStreaming = stages?.timeline?.status === 'running' && streamingChunks?.timeline
            return (
              <div className="space-y-2">
                {loading && !isStreaming && <LoadingSpinner label="Loading timeline…" />}
                {isStreaming && (
                  <TimelineStreamingPreview text={streamingChunks!.timeline} />
                )}
                {!loading && !isStreaming && timelineData && timelineData.length > 0 && (
                  <>
                    <div className="flex items-center justify-between mb-4">
                      <p className="text-xs text-parchment/30 uppercase tracking-widest font-body">
                        {timelineData.length} events
                      </p>
                      {session.timeline_path && <DownloadButton path={session.timeline_path} />}
                    </div>
                    <HorizontalTimeline events={timelineData} />
                  </>
                )}
                {!loading && !isStreaming && timelineData && timelineData.length === 0 && (
                  <p className="text-sm text-parchment/30 font-body py-4">No timeline events found.</p>
                )}
                {!loading && !isStreaming && !timelineData && !loadError && !session.files.timeline && hasTranscript && (
                  <GenerateArtifactButton stage="timeline" label="Timeline" generating={generatingSet} onGenerate={handleGenerate} />
                )}
              </div>
            )
          })()}

          {/* Transcript Tab */}
          {activeTab === 'transcript' && (
            <div className="space-y-3">
              {loading && <LoadingSpinner label="Loading transcript…" />}
              {!loading && transcriptContent && (
                <div className="rounded-md border border-white/8 overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-2 bg-void/60 border-b border-white/5">
                    <span className="text-xs font-heading text-parchment/50 uppercase tracking-widest">Transcript</span>
                    <div className="flex items-center gap-1.5">
                      {session.txt_path && <DownloadButton path={session.txt_path} />}
                      <CopyButton text={transcriptContent} />
                    </div>
                  </div>
                  <div className="px-4 py-3 max-h-[60vh] overflow-y-auto"
                    style={{ fontFamily: "'Menlo', 'Consolas', monospace" }}>
                    <pre className="text-xs text-parchment/65 leading-relaxed whitespace-pre-wrap break-words">
                      {transcriptContent}
                    </pre>
                  </div>
                </div>
              )}
              {!loading && !transcriptContent && !loadError && (
                <p className="text-sm text-parchment/30 font-body py-4">No transcript available.</p>
              )}
            </div>
          )}

          {/* DM Notes Tab */}
          {activeTab === 'notes' && (() => {
            const headings = dmNotesContent ? extractHeadings(dmNotesContent) : []
            const showToc = headings.length >= 3
            return (
              <div className="space-y-3">
                {loading && <LoadingSpinner label="Loading DM notes…" />}
                {!loading && dmNotesContent && (
                  <div className={cn('flex gap-6', !showToc && 'flex-col')}>
                    {showToc && <DmNotesToc headings={headings} />}
                    <div className="flex-1 min-w-0">
                      <div className="rounded-md border border-white/8 overflow-hidden">
                        <div className="flex items-center justify-between px-4 py-2 bg-void/60 border-b border-white/5">
                          <span className="text-xs font-heading text-parchment/50 uppercase tracking-widest">DM Notes</span>
                          <div className="flex items-center gap-1.5">
                            {session.dm_notes_path && <DownloadButton path={session.dm_notes_path} />}
                            <CopyButton text={dmNotesContent} />
                          </div>
                        </div>
                        <div className="px-5 py-5">
                          <MarkdownRenderer text={dmNotesContent} headingIds />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                {generatingSet.has('dm_notes') && streamingChunks?.dm_notes && (
                  <div className="rounded-md border border-gold/15 bg-void/30 px-4 py-4 animate-pulse-subtle">
                    <MarkdownRenderer text={streamingChunks.dm_notes} />
                  </div>
                )}
                {!loading && !dmNotesContent && !loadError && !session.files.dm_notes && hasTranscript && !generatingSet.has('dm_notes') && (
                  <GenerateArtifactButton stage="dm_notes" label="DM Notes" generating={generatingSet} onGenerate={handleGenerate} />
                )}
              </div>
            )
          })()}

          {/* Glossary Tab */}
          {activeTab === 'glossary' && (
            <div className="space-y-3">
              {session.glossary_path && <div className="flex justify-end"><DownloadButton path={session.glossary_path} /></div>}
              {loading && <LoadingSpinner label="Loading glossary…" />}
              {!loading && glossaryData && Object.keys(glossaryData).length > 0 && (() => {
                const CATS = ['All', 'NPC', 'Location', 'Faction', 'Item', 'Spell', 'Other']
                const entries = Object.entries(glossaryData)
                const catCounts: Record<string, number> = { All: entries.length }
                for (const [, info] of entries) {
                  const cat = (info as any).category || 'Other'
                  catCounts[cat] = (catCounts[cat] || 0) + 1
                }
                return <GlossaryTabContent entries={entries} categories={CATS} catCounts={catCounts} />
              })()}
              {!loading && glossaryData && Object.keys(glossaryData).length === 0 && (
                <p className="text-sm text-parchment/30 font-body py-4">No glossary terms extracted this session.</p>
              )}
              {!loading && !glossaryData && !loadError && !session.files.glossary && hasTranscript && (
                <GenerateArtifactButton stage="glossary" label="Glossary" generating={generatingSet} onGenerate={handleGenerate} />
              )}
            </div>
          )}

          {/* Locations Tab */}
          {activeTab === 'locations' && (
            <div className="space-y-3">
              {session.locations_path && <div className="flex justify-end"><DownloadButton path={session.locations_path} /></div>}
              {loading && <LoadingSpinner label="Loading locations..." />}
              {!loading && locationsData && locationsData.length > 0 && (
                <>
                  <p className="text-xs text-parchment/30 uppercase tracking-widest font-body">{locationsData.length} location{locationsData.length !== 1 ? 's' : ''}</p>
                  <div className="space-y-2">
                    {locationsData.map((loc: any, i: number) => (
                      <div key={i} className="rounded-md border border-white/5 bg-void/30 px-3 py-2">
                        <div className="flex items-center gap-2">
                          {loc.visit_order != null ? (
                            <span className="w-5 h-5 rounded-full bg-gold/15 border border-gold/25 flex items-center justify-center text-[10px] font-heading text-gold/80 flex-none">{loc.visit_order}</span>
                          ) : (
                            <Compass className="w-3.5 h-3.5 text-gold/50 flex-none" />
                          )}
                          <span className="text-sm font-body text-parchment/80 font-semibold">{loc.name}</span>
                          {loc.visited && <span className="text-[8px] uppercase tracking-wider text-emerald-400/70 bg-emerald-400/10 px-1.5 py-0.5 rounded-full">Visited</span>}
                        </div>
                        {loc.description && <p className="mt-1 text-xs text-parchment/55 font-body">{loc.description}</p>}
                        {loc.relative_position && <p className="mt-1 text-[11px] text-parchment/35 font-body italic">{loc.relative_position}</p>}
                        {loc.connections?.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {loc.connections.map((c: string, j: number) => (
                              <span key={j} className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-parchment/40 border border-white/5">{c}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
              {generatingSet.has('locations') && streamingChunks?.locations && (
                <div className="rounded-md border border-gold/15 bg-void/30 px-4 py-3">
                  <div className="flex items-center gap-2 mb-2"><Loader2 className="w-3 h-3 animate-spin text-gold/50" /><span className="text-[10px] text-gold/50 uppercase tracking-wider">Generating…</span></div>
                  <pre className="text-[10px] text-parchment/50 whitespace-pre-wrap font-mono">{streamingChunks.locations}</pre>
                </div>
              )}
              {!loading && (!locationsData || locationsData.length === 0) && !loadError && !session.files.locations && hasTranscript && !generatingSet.has('locations') && (
                <GenerateArtifactButton stage="locations" label="Locations" generating={generatingSet} onGenerate={handleGenerate} />
              )}
              {!loading && locationsData && locationsData.length > 0 && hasTranscript && !generatingSet.has('locations') && (
                <div className="flex justify-center pt-2 pb-1">
                  <button
                    onClick={() => handleGenerate('locations')}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-white/8 text-[10px] font-heading text-parchment/40 uppercase tracking-wider hover:border-gold/20 hover:text-gold/60 transition-colors"
                  >
                    <RefreshCw className="w-3 h-3" />Reprocess Locations
                  </button>
                </div>
              )}
            </div>
          )}

          {/* NPCs Tab */}
          {activeTab === 'npcs' && (
            <div className="space-y-3">
              {session.npcs_path && <div className="flex justify-end"><DownloadButton path={session.npcs_path} /></div>}
              {loading && <LoadingSpinner label="Loading NPCs..." />}
              {!loading && npcsData && npcsData.length > 0 && (
                <>
                  <p className="text-xs text-parchment/30 uppercase tracking-widest font-body">{npcsData.length} NPC{npcsData.length !== 1 ? 's' : ''}</p>
                  <div className="space-y-2">
                    {npcsData.map((npc: any, i: number) => (
                      <div key={i} className="rounded-md border border-white/5 bg-void/30 px-3 py-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Users className="w-3.5 h-3.5 text-gold/50 flex-none" />
                          <span className="text-sm font-body text-parchment/80 font-semibold">{npc.name}</span>
                          {npc.race && (
                            <span className="text-[9px] font-heading uppercase tracking-wider text-parchment/40 bg-white/5 px-1.5 py-0.5 rounded-full border border-white/5">{npc.race}</span>
                          )}
                          {npc.role && (
                            <span className="text-[9px] font-heading uppercase tracking-wider text-gold/50 bg-gold/8 px-1.5 py-0.5 rounded-full">{npc.role}</span>
                          )}
                        </div>
                        {npc.description && <p className="mt-1 text-xs text-parchment/55 font-body">{npc.description}</p>}
                        {npc.attitude && (
                          <p className={cn(
                            'mt-1 text-[11px] font-body italic',
                            npc.attitude === 'friendly' && 'text-emerald-400/60',
                            npc.attitude === 'hostile' && 'text-red-400/60',
                            npc.attitude === 'neutral' && 'text-parchment/35',
                            !['friendly', 'hostile', 'neutral'].includes(npc.attitude) && 'text-parchment/35',
                          )}>
                            Attitude: {npc.attitude}
                          </p>
                        )}
                        {(() => {
                          const actionsList = Array.isArray(npc.actions) ? npc.actions : npc.actions ? [npc.actions] : []
                          return actionsList.length > 0 ? (
                            <div className="mt-1.5">
                              <p className="text-[10px] text-parchment/30 uppercase tracking-wider mb-0.5">Actions</p>
                              <ul className="space-y-0.5">
                                {actionsList.map((action: string, j: number) => (
                                  <li key={j} className="text-xs text-parchment/50 font-body pl-2 border-l border-white/5">{action}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null
                        })()}
                        {npc.current_status && (
                          <p className="mt-1.5 text-[11px] text-parchment/40 font-body">Status: {npc.current_status}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
              {generatingSet.has('npcs') && streamingChunks?.npcs && (
                <div className="rounded-md border border-gold/15 bg-void/30 px-4 py-3">
                  <div className="flex items-center gap-2 mb-2"><Loader2 className="w-3 h-3 animate-spin text-gold/50" /><span className="text-[10px] text-gold/50 uppercase tracking-wider">Generating…</span></div>
                  <pre className="text-[10px] text-parchment/50 whitespace-pre-wrap font-mono">{streamingChunks.npcs}</pre>
                </div>
              )}
              {!loading && (!npcsData || npcsData.length === 0) && !loadError && !session.files.npcs && hasTranscript && !generatingSet.has('npcs') && (
                <GenerateArtifactButton stage="npcs" label="NPCs" generating={generatingSet} onGenerate={handleGenerate} />
              )}
            </div>
          )}

          {/* Loot Tab */}
          {activeTab === 'loot' && (
            <div className="space-y-3">
              {session.loot_path && <div className="flex justify-end"><DownloadButton path={session.loot_path} /></div>}
              {loading && <LoadingSpinner label="Loading loot..." />}
              {!loading && lootData && (
                <>
                  {/* Items table */}
                  {lootData.items && lootData.items.length > 0 && (
                    <div className="rounded-md border border-gold/15 bg-void/40 overflow-hidden">
                      <div className="px-3 py-2 bg-gold/5 border-b border-gold/10 flex items-center gap-2">
                        <Gem className="w-3.5 h-3.5 text-gold/60" />
                        <span className="text-[11px] font-heading text-gold/70 uppercase tracking-widest">Items Looted</span>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-[10px] font-body">
                          <thead>
                            <tr className="border-b border-white/5">
                              <th className="px-3 py-1.5 text-left text-parchment/40 font-heading uppercase tracking-wider">Item</th>
                              <th className="px-2 py-1.5 text-left text-parchment/40">Type</th>
                              <th className="px-2 py-1.5 text-center text-parchment/40">Magical</th>
                              <th className="px-2 py-1.5 text-left text-parchment/40">Looted By</th>
                              <th className="px-2 py-1.5 text-left text-parchment/40">From</th>
                            </tr>
                          </thead>
                          <tbody>
                            {lootData.items.map((item: any, i: number) => (
                              <tr key={i} className="border-b border-white/3 hover:bg-white/2">
                                <td className="px-3 py-1.5 text-parchment/70 font-semibold">{item.name}</td>
                                <td className="px-2 py-1.5">
                                  {item.type && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-parchment/40 border border-white/5">{item.type}</span>}
                                </td>
                                <td className="px-2 py-1.5 text-center">{item.magical ? <Sparkles className="w-3 h-3 text-gold/50 inline" /> : '-'}</td>
                                <td className="px-2 py-1.5 text-parchment/50">{item.looted_by || '-'}</td>
                                <td className="px-2 py-1.5 text-parchment/50">{item.looted_from || '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Gold transactions */}
                  {lootData.gold && lootData.gold.length > 0 && (
                    <div className="rounded-md border border-gold/15 bg-void/40 overflow-hidden">
                      <div className="px-3 py-2 bg-gold/5 border-b border-gold/10 flex items-center gap-2">
                        <Trophy className="w-3.5 h-3.5 text-gold/60" />
                        <span className="text-[11px] font-heading text-gold/70 uppercase tracking-widest">Gold & Currency</span>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-[10px] font-body">
                          <thead>
                            <tr className="border-b border-white/5">
                              <th className="px-3 py-1.5 text-left text-parchment/40 font-heading uppercase tracking-wider">Amount</th>
                              <th className="px-2 py-1.5 text-left text-parchment/40">Currency</th>
                              <th className="px-2 py-1.5 text-left text-parchment/40">Source</th>
                              <th className="px-2 py-1.5 text-left text-parchment/40">Gained By</th>
                            </tr>
                          </thead>
                          <tbody>
                            {lootData.gold.map((g: any, i: number) => (
                              <tr key={i} className="border-b border-white/3 hover:bg-white/2">
                                <td className="px-3 py-1.5 text-gold/70 font-semibold">{g.amount}</td>
                                <td className="px-2 py-1.5 text-parchment/50">{g.currency || 'gp'}</td>
                                <td className="px-2 py-1.5 text-parchment/50">{g.source || '-'}</td>
                                <td className="px-2 py-1.5 text-parchment/50">{g.gained_by || '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {(!lootData.items || lootData.items.length === 0) && (!lootData.gold || lootData.gold.length === 0) && (
                    <p className="text-sm text-parchment/30 font-body py-4">No loot found this session.</p>
                  )}
                </>
              )}
              {generatingSet.has('loot') && streamingChunks?.loot && (
                <div className="rounded-md border border-gold/15 bg-void/30 px-4 py-3">
                  <div className="flex items-center gap-2 mb-2"><Loader2 className="w-3 h-3 animate-spin text-gold/50" /><span className="text-[10px] text-gold/50 uppercase tracking-wider">Generating…</span></div>
                  <pre className="text-[10px] text-parchment/50 whitespace-pre-wrap font-mono">{streamingChunks.loot}</pre>
                </div>
              )}
              {!loading && !lootData && !loadError && !session.files.loot && hasTranscript && !generatingSet.has('loot') && (
                <GenerateArtifactButton stage="loot" label="Loot" generating={generatingSet} onGenerate={handleGenerate} />
              )}
              {!loading && lootData && hasTranscript && !generatingSet.has('loot') && (
                <div className="flex justify-center pt-2 pb-1">
                  <button
                    onClick={() => handleGenerate('loot')}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-white/8 text-[10px] font-heading text-parchment/40 uppercase tracking-wider hover:border-gold/20 hover:text-gold/60 transition-colors"
                  >
                    <RefreshCw className="w-3 h-3" />Reprocess Loot
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Missions Tab */}
          {activeTab === 'missions' && (
            <div className="space-y-3">
              {session.missions_path && <div className="flex justify-end"><DownloadButton path={session.missions_path} /></div>}
              {loading && <LoadingSpinner label="Loading missions..." />}
              {!loading && missionsData && missionsData.length > 0 && (
                <>
                  <p className="text-xs text-parchment/30 uppercase tracking-widest font-body">{missionsData.length} mission{missionsData.length !== 1 ? 's' : ''}</p>
                  <div className="space-y-2">
                    {missionsData.map((mission: any, i: number) => (
                      <div key={i} className="rounded-md border border-white/5 bg-void/30 px-3 py-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Scroll className="w-3.5 h-3.5 text-gold/50 flex-none" />
                          <span className="text-sm font-body text-parchment/80 font-semibold">{mission.name}</span>
                          {mission.status && (
                            <span className={cn(
                              'text-[8px] uppercase tracking-wider px-1.5 py-0.5 rounded-full',
                              mission.status === 'started' && 'text-amber-400/70 bg-amber-400/10',
                              mission.status === 'continued' && 'text-blue-400/70 bg-blue-400/10',
                              mission.status === 'completed' && 'text-emerald-400/70 bg-emerald-400/10',
                              !['started', 'continued', 'completed'].includes(mission.status) && 'text-parchment/40 bg-white/5',
                            )}>
                              {mission.status}
                            </span>
                          )}
                        </div>
                        {mission.description && <p className="mt-1 text-xs text-parchment/55 font-body">{mission.description}</p>}
                        {mission.objectives && mission.objectives.length > 0 && (
                          <div className="mt-1.5">
                            <p className="text-[10px] text-parchment/30 uppercase tracking-wider mb-0.5">Objectives</p>
                            <ul className="space-y-0.5">
                              {mission.objectives.map((obj: string, j: number) => (
                                <li key={j} className="text-xs text-parchment/50 font-body pl-2 border-l border-white/5">{obj}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {mission.givers && mission.givers.length > 0 && (
                          <p className="mt-1.5 text-[11px] text-parchment/35 font-body">Given by: {mission.givers.join(', ')}</p>
                        )}
                        {mission.rewards && mission.rewards.length > 0 && (
                          <p className="mt-1 text-[11px] text-gold/40 font-body">Rewards: {mission.rewards.join(', ')}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
              {generatingSet.has('missions') && streamingChunks?.missions && (
                <div className="rounded-md border border-gold/15 bg-void/30 px-4 py-3">
                  <div className="flex items-center gap-2 mb-2"><Loader2 className="w-3 h-3 animate-spin text-gold/50" /><span className="text-[10px] text-gold/50 uppercase tracking-wider">Generating…</span></div>
                  <pre className="text-[10px] text-parchment/50 whitespace-pre-wrap font-mono">{streamingChunks.missions}</pre>
                </div>
              )}
              {!loading && (!missionsData || missionsData.length === 0) && !loadError && !session.files.missions && hasTranscript && !generatingSet.has('missions') && (
                <GenerateArtifactButton stage="missions" label="Missions" generating={generatingSet} onGenerate={handleGenerate} />
              )}
            </div>
          )}



        </div>
      </div>

      {/* ── Process Audio Settings Modal ── */}
      {showProcessModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-lg border border-gold/20 bg-shadow p-6 space-y-5 shadow-2xl">
            <h3 className="text-sm font-heading text-gold uppercase tracking-widest text-center">
              Transcription Settings
            </h3>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-heading text-parchment/50 uppercase tracking-wider">Model</label>
                <Select value={wxModel} onValueChange={v => setWxModel(v)}>
                  <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {WHISPERX_MODELS.map(m => (
                      <SelectItem key={m.value} value={m.value} className="text-xs">{m.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-heading text-parchment/50 uppercase tracking-wider">Language</label>
                <Select value={wxLanguage} onValueChange={v => setWxLanguage(v)}>
                  <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {WHISPERX_LANGUAGES.map(l => (
                      <SelectItem key={l.value} value={l.value} className="text-xs">{l.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setShowProcessModal(false)}
                className="flex-1 px-4 py-2 rounded-md border border-white/10 text-sm font-heading text-parchment/50 uppercase tracking-widest hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={generatingSet.has('transcription')}
                onClick={async () => {
                  setShowProcessModal(false)
                  setGeneratingSet(prev => new Set([...prev, 'transcription']))
                  // Save prefs sequentially to avoid race condition on prefs.json
                  await api('set_pref', 'model', wxModel)
                  await api('set_pref', 'language', wxLanguage)
                  const result = await api('retry_transcription', session.id, wxModel, wxLanguage)
                  if (result?.ok) {
                    onViewPipeline?.()
                  } else {
                    const errMsg = (result as any)?.error || 'Failed to start transcription'
                    alert(errMsg)
                    setGeneratingSet(prev => { const s = new Set(prev); s.delete('transcription'); return s })
                  }
                }}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md bg-gold/10 border border-gold/30 text-sm font-heading text-gold uppercase tracking-widest hover:bg-gold/15 hover:border-gold/40 transition-colors disabled:opacity-30"
              >
                <Mic className="w-4 h-4" />
                Start
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── MetaRow helper ────────────────────────────────────────────────────────────

function MetaRow({ label, value, mono, truncate }: { label: string; value: string; mono?: boolean; truncate?: boolean }) {
  return (
    <div className="flex gap-3 items-baseline">
      <span className="text-sm text-parchment/35 font-body w-28 flex-none">{label}</span>
      <span className={cn(
        'text-sm text-parchment/70 font-body flex-1',
        mono && 'font-mono text-xs',
        truncate && 'truncate',
      )}>
        {value}
      </span>
    </div>
  )
}
