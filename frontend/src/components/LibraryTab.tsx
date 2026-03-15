import { useState, useEffect, useCallback, useRef } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { api, type SessionEntry } from '@/lib/api'
import type { PipelineStages } from '@/App'
import {
  FolderOpen, Loader2, RefreshCw, Mic, FileText, FileJson,
  BookOpen, ScrollText, Film, Clock, Pencil, Check, X, Trash2,
  BookMarked, Image, Search,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { SessionDetailScreen } from '@/components/SessionDetailScreen'

// ── Props ─────────────────────────────────────────────────────────────────────

interface LibraryTabProps {
  pipelineActive: boolean
  pipelineSessionDir: string | null
  /** Navigate to Session tab to show the processing view */
  onNavigateToProcessing: () => void
  /** Callback to refresh sessions list externally */
  refreshTrigger?: number
  /** Global pipeline stages from App.tsx — passed to SessionDetailScreen for async generation tracking */
  stages?: PipelineStages
  /** Streaming LLM chunks keyed by stage — for live timeline preview */
  streamingChunks?: Record<string, string>
  /** Version counter that bumps on each new chunk */
  streamingVersion?: number
  /** Navigate to a character by ID (cross-tab) */
  onNavigateToCharacter?: (charId: string) => void
}

function formatDate(iso: string): { date: string; time: string } {
  const d = new Date(iso)
  return {
    date: d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }),
    time: d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
  }
}

function FileBadge({ available, label, icon: Icon }: { available: boolean; label: string; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <div className={cn(
      'flex items-center gap-1 px-2 py-0.5 rounded text-xs font-body',
      available ? 'bg-emerald-500/10 border border-emerald-500/25 text-emerald-400/80'
                : 'bg-white/4 border border-white/8 text-parchment/20'
    )}>
      <Icon className="w-3 h-3 flex-none" /><span>{label}</span>
    </div>
  )
}

function InlineNameEdit({ sessionId, currentName, onSaved }: { sessionId: string; currentName: string; onSaved: (name: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(currentName)
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => { if (editing) inputRef.current?.focus() }, [editing])
  async function save() {
    if (!value.trim() || value.trim() === currentName) { setEditing(false); return }
    setSaving(true); await api('rename_session', sessionId, value.trim()); onSaved(value.trim()); setSaving(false); setEditing(false)
  }
  if (editing) return (
    <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
      <input ref={inputRef} value={value} onChange={e => setValue(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setValue(currentName); setEditing(false) } }}
        className="bg-void/80 border border-gold/30 rounded px-2 py-0.5 text-sm font-heading text-parchment/85 outline-none focus:border-gold/60 min-w-0 w-40" />
      <button onClick={save} disabled={saving} className="text-emerald-400 p-0.5">
        {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
      </button>
      <button onClick={() => { setValue(currentName); setEditing(false) }} className="text-parchment/30 p-0.5"><X className="w-3.5 h-3.5" /></button>
    </div>
  )
  return (
    <div className="flex items-center gap-1.5 group/name">
      <span className="text-sm font-heading text-parchment/85">{currentName}</span>
      <button onClick={e => { e.stopPropagation(); setEditing(true) }} className="opacity-0 group-hover/name:opacity-100 text-parchment/25 hover:text-gold/60 transition-all p-0.5"><Pencil className="w-3 h-3" /></button>
    </div>
  )
}

function InlineDateEdit({ sessionId, currentDate, onSaved }: { sessionId: string; currentDate: string; onSaved: (isoDate: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(() => new Date(currentDate).toISOString().slice(0, 10))
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const { date, time } = formatDate(currentDate)
  useEffect(() => { if (editing) inputRef.current?.focus() }, [editing])
  async function save() {
    if (!value) { setEditing(false); return }
    setSaving(true); await api('update_session_date', sessionId, value); onSaved(new Date(value).toISOString()); setSaving(false); setEditing(false)
  }
  if (editing) return (
    <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
      <input ref={inputRef} type="date" value={value} onChange={e => setValue(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setValue(new Date(currentDate).toISOString().slice(0,10)); setEditing(false) } }}
        className="bg-void/80 border border-gold/30 rounded px-2 py-0.5 text-xs font-body text-parchment/70 outline-none focus:border-gold/60" style={{ colorScheme: 'dark' }} />
      <button onClick={save} disabled={saving} className="text-emerald-400 p-0.5">
        {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
      </button>
      <button onClick={() => { setValue(new Date(currentDate).toISOString().slice(0,10)); setEditing(false) }} className="text-parchment/30 p-0.5"><X className="w-3 h-3" /></button>
    </div>
  )
  return (
    <div className="flex items-center gap-1.5 group/date">
      <span className="text-xs text-parchment/35 font-body">{date}</span>
      <span className="text-xs text-parchment/20 font-body">{time}</span>
      <button onClick={e => { e.stopPropagation(); setEditing(true) }} className="opacity-0 group-hover/date:opacity-100 text-parchment/20 hover:text-gold/50 transition-all p-0.5"><Pencil className="w-3 h-3" /></button>
    </div>
  )
}

interface SessionCardProps {
  session: SessionEntry
  onOpen: (path: string) => void
  onUpdated: (id: string, fields: Partial<SessionEntry>) => void
  onDelete: (id: string) => void
  onSelect: (session: SessionEntry) => void
  isActive?: boolean
  onNavigateToCharacter?: (charId: string) => void
}

function SessionCard({ session, onOpen, onUpdated, onDelete, onSelect, isActive, onNavigateToCharacter }: SessionCardProps) {
  const displayName = session.display_name || `${session.campaign_name}${session.season_number ? ` · S${session.season_number}` : ''}`
  const names = session.character_names.filter(Boolean)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [generatingBanner, setGeneratingBanner] = useState(false)

  async function handleGenerateBanner(e: React.MouseEvent) {
    e.stopPropagation()
    setGeneratingBanner(true)
    try {
      await api('run_single_stage', session.id, 'illustration')
      // Refresh session data after generation
      const sessions = await api('get_sessions') as SessionEntry[] | null
      if (sessions) {
        const updated = sessions.find(s => s.id === session.id)
        if (updated?.illustration_path) {
          onUpdated(session.id, { illustration_path: updated.illustration_path })
        }
      }
    } catch { /* ignore */ }
    setGeneratingBanner(false)
  }

  return (
    <div
      className={cn(
        'relative rounded-md border overflow-hidden transition-colors group cursor-pointer aspect-video',
        isActive ? 'bg-gold/5 border-gold/30 ring-1 ring-gold/15' : 'bg-void/60 border-white/8 hover:border-gold/20'
      )}
      onClick={() => onSelect(session)}
    >
      {/* Background — illustration fills entire card */}
      {session.illustration_path ? (
        <img
          src={`file://${session.illustration_path}`}
          alt=""
          className="absolute inset-0 w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
        />
      ) : (
        <div className="absolute inset-0 bg-void/80 flex items-center justify-center">
          {session.files?.transcript && (
            <button
              onClick={handleGenerateBanner}
              disabled={generatingBanner}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-gold/20 text-xs text-parchment/40 hover:text-gold hover:border-gold/40 hover:bg-gold/5 transition-colors disabled:opacity-40"
            >
              {generatingBanner ? <Loader2 className="w-3 h-3 animate-spin" /> : <Image className="w-3 h-3" />}
              Generate Banner
            </button>
          )}
        </div>
      )}

      {/* Hover actions — top right */}
      <div className="absolute top-2 right-2 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        <button onClick={e => { e.stopPropagation(); onOpen(session.output_dir) }}
          className="flex items-center gap-1.5 px-2 py-1.5 rounded bg-black/50 backdrop-blur-sm border border-white/10 text-xs text-parchment/60 hover:text-gold hover:border-gold/30 transition-colors"
          title="Open in Finder"><FolderOpen className="w-3.5 h-3.5" /></button>
        {confirmDelete ? (
          <div className="flex items-center gap-1 bg-black/50 backdrop-blur-sm rounded px-2 py-1" onClick={e => e.stopPropagation()}>
            <span className="text-xs text-parchment/60 font-body">Delete?</span>
            <button onClick={async () => { setDeleting(true); await onDelete(session.id); setDeleting(false) }} disabled={deleting}
              className="px-2 py-0.5 rounded text-xs text-red-400 border border-red-500/30 hover:bg-red-500/10 transition-colors">
              {deleting ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Yes'}
            </button>
            <button onClick={() => setConfirmDelete(false)} className="px-2 py-0.5 rounded text-xs text-parchment/40 border border-white/10 hover:bg-white/5 transition-colors">No</button>
          </div>
        ) : (
          <button onClick={e => { e.stopPropagation(); setConfirmDelete(true) }}
            className="flex items-center gap-1.5 px-2 py-1.5 rounded bg-black/50 backdrop-blur-sm border border-white/10 text-xs text-parchment/30 hover:text-red-400 hover:border-red-500/30 transition-colors">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Info overlay — bottom with gradient */}
      <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 via-black/50 to-transparent px-3 pb-2.5 pt-10 z-10">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            {isActive && <span className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse flex-none" />}
            <InlineNameEdit sessionId={session.id} currentName={displayName} onSaved={name => onUpdated(session.id, { display_name: name })} />
          </div>
          <InlineDateEdit sessionId={session.id} currentDate={session.date} onSaved={date => onUpdated(session.id, { date })} />
        </div>
        {names.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {names.map((name, i) => {
              const charId = session.character_map?.[name]
              return (
                <button
                  key={i}
                  onClick={(e) => { e.stopPropagation(); if (charId && onNavigateToCharacter) onNavigateToCharacter(charId) }}
                  className={cn(
                    'px-2 py-0.5 rounded text-[10px] font-body transition-colors',
                    charId && onNavigateToCharacter
                      ? 'bg-gold/8 border border-gold/15 text-gold/70 hover:bg-gold/15 hover:text-gold cursor-pointer'
                      : 'bg-white/5 border border-white/8 text-parchment/50 cursor-default'
                  )}
                >
                  {name}
                </button>
              )
            })}
          </div>
        )}
        <div className="flex items-center gap-2 mt-1">
          {session.files.audio && <Mic className="w-2.5 h-2.5 text-parchment/25" />}
          {session.files.transcript && <FileText className="w-2.5 h-2.5 text-emerald-400/40" />}
          {session.files.summary && <BookMarked className="w-2.5 h-2.5 text-emerald-400/40" />}
        </div>
      </div>
    </div>
  )
}

// ── Main LibraryTab ───────────────────────────────────────────────────────────

export function LibraryTab({
  pipelineActive, pipelineSessionDir, onNavigateToProcessing, refreshTrigger, stages,
  streamingChunks, streamingVersion, onNavigateToCharacter,
}: LibraryTabProps) {
  const [sessions, setSessions] = useState<SessionEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedSession, setSelectedSession] = useState<SessionEntry | null>(null)
  const [filterCampaign, setFilterCampaign] = useState<string>('all')
  const [filterSeason, setFilterSeason] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortOrder, setSortOrder] = useState<'date-desc' | 'date-asc' | 'name-asc'>('date-desc')

  const load = useCallback(async () => {
    setLoading(true)
    const result = await api('get_sessions')
    setSessions(result || [])
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  // Reload when refreshTrigger changes (e.g. pipeline finished)
  useEffect(() => {
    if (refreshTrigger && refreshTrigger > 0) load()
  }, [refreshTrigger, load])

  // Filters
  const campaigns = Array.from(new Map(sessions.map(s => [s.campaign_id, s.campaign_name])).entries())
  const seasons = Array.from(new Set(
    sessions.filter(s => filterCampaign === 'all' || s.campaign_id === filterCampaign).map(s => s.season_number)
  )).sort((a, b) => a - b)

  const filtered = sessions.filter(s => {
    if (filterCampaign !== 'all' && s.campaign_id !== filterCampaign) return false
    if (filterSeason !== 'all' && String(s.season_number) !== filterSeason) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return (
        (s.display_name || '').toLowerCase().includes(q) ||
        s.campaign_name?.toLowerCase().includes(q) ||
        s.character_names?.some(n => n.toLowerCase().includes(q)) ||
        s.date?.toLowerCase().includes(q) ||
        false
      )
    }
    return true
  }).sort((a, b) => {
    switch (sortOrder) {
      case 'date-desc': return (b.date || '').localeCompare(a.date || '')
      case 'date-asc': return (a.date || '').localeCompare(b.date || '')
      case 'name-asc': return (a.display_name || a.date || '').localeCompare(b.display_name || b.date || '')
      default: return 0
    }
  })

  const activeSession = pipelineActive && pipelineSessionDir
    ? sessions.find(s => s.output_dir === pipelineSessionDir) ?? null
    : null

  function handleUpdated(id: string, fields: Partial<SessionEntry>) {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, ...fields } : s))
    if (selectedSession?.id === id) setSelectedSession(prev => prev ? { ...prev, ...fields } : null)
  }
  async function handleDelete(id: string) {
    await api('delete_session_folder', id)
    setSessions(prev => prev.filter(s => s.id !== id))
    if (selectedSession?.id === id) setSelectedSession(null)
  }
  function handleSelectSession(session: SessionEntry) {
    // If clicking the active processing session, navigate to Session tab's processing view
    if (pipelineActive && pipelineSessionDir && session.output_dir === pipelineSessionDir) {
      onNavigateToProcessing()
    } else {
      setSelectedSession(session)
    }
  }

  async function handleRefreshSelectedSession() {
    const result = await api('get_sessions')
    const all = result || []
    setSessions(all)
    if (selectedSession) {
      const updated = all.find(s => s.id === selectedSession.id)
      if (updated) setSelectedSession(updated)
    }
  }

  if (selectedSession) {
    return (
      <SessionDetailScreen
        session={selectedSession}
        onBack={() => setSelectedSession(null)}
        onUpdated={(fields) => handleUpdated(selectedSession.id, fields)}
        onViewPipeline={onNavigateToProcessing}
        onRefresh={handleRefreshSelectedSession}
        stages={stages}
        streamingChunks={streamingChunks}
        streamingVersion={streamingVersion}
        onNavigateToCharacter={onNavigateToCharacter}
      />
    )
  }

  return (
    <div className="h-full flex flex-col p-6 gap-3 overflow-hidden">
      <div className="flex items-center justify-between flex-none">
        <div className="flex items-center gap-3">
          <span className="text-xs font-heading text-parchment/60 uppercase tracking-widest">Past Sessions</span>
          {filtered.length > 0 && (
            <span className="text-xs text-parchment/30 font-body">{filtered.length} session{filtered.length !== 1 ? 's' : ''}</span>
          )}
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-white/10 text-xs text-parchment/40 hover:text-parchment/70 hover:border-white/20 transition-colors">
          <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />Refresh
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex-none flex items-center gap-2 flex-wrap">
        {/* Search */}
        <div className="relative flex-1 min-w-[140px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-parchment/25" />
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search sessions…"
            className="w-full h-7 bg-void/60 border border-white/8 rounded pl-7 pr-2 text-[11px] text-parchment/60 outline-none focus:border-gold/40 placeholder:text-parchment/20"
          />
        </div>
        {campaigns.length > 1 && (
          <select value={filterCampaign} onChange={e => { setFilterCampaign(e.target.value); setFilterSeason('all') }}
            className="h-7 bg-void/60 border border-white/10 rounded px-2.5 text-xs text-parchment/70 font-body outline-none focus:border-gold/30 hover:border-white/20 transition-colors"
            style={{ colorScheme: 'dark' }}>
            <option value="all">All Campaigns</option>
            {campaigns.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        )}
        {campaigns.length > 1 && seasons.length > 1 && (
          <select value={filterSeason} onChange={e => setFilterSeason(e.target.value)}
            className="h-7 bg-void/60 border border-white/10 rounded px-2.5 text-xs text-parchment/70 font-body outline-none focus:border-gold/30 hover:border-white/20 transition-colors"
            style={{ colorScheme: 'dark' }}>
            <option value="all">All Seasons</option>
            {seasons.map(n => <option key={n} value={String(n)}>Season {n}</option>)}
          </select>
        )}
        <select
          value={sortOrder}
          onChange={e => setSortOrder(e.target.value as any)}
          className="h-7 bg-void/60 border border-white/8 rounded px-2 text-[10px] text-parchment/50 outline-none focus:border-gold/40"
          style={{ colorScheme: 'dark' }}
        >
          <option value="date-desc">Newest first</option>
          <option value="date-asc">Oldest first</option>
          <option value="name-asc">Name A→Z</option>
        </select>
      </div>

      <ScrollArea className="flex-1">
        {/* Active processing card always at top */}
        {pipelineActive && activeSession && (
          <div className="mb-3 pr-3">
            <SessionCard session={activeSession} onOpen={p => api('open_path', p)}
              onUpdated={handleUpdated} onDelete={handleDelete} onSelect={handleSelectSession} isActive onNavigateToCharacter={onNavigateToCharacter} />
          </div>
        )}

        {loading && sessions.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-16">
            <Loader2 className="w-5 h-5 text-parchment/20 animate-spin" />
            <p className="text-xs text-parchment/25 font-body">Loading library…</p>
          </div>
        ) : filtered.length === 0 && !activeSession ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="w-12 h-12 rounded-full border border-white/8 flex items-center justify-center">
              <BookOpen className="w-5 h-5 text-parchment/15" />
            </div>
            <p className="text-sm font-heading text-parchment/30">No sessions yet</p>
            <p className="text-xs text-parchment/20 font-body">Your transcribed sessions will appear here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 pr-3">
            {filtered
              .filter(s => !activeSession || s.id !== activeSession.id)
              .map(s => (
                <SessionCard key={s.id} session={s} onOpen={p => api('open_path', p)}
                  onUpdated={handleUpdated} onDelete={handleDelete} onSelect={handleSelectSession} onNavigateToCharacter={onNavigateToCharacter} />
              ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
