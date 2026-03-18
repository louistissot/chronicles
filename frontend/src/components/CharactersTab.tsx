import { useState, useEffect, useMemo, memo } from 'react'
import {
  ArrowLeft, Check, ChevronDown, ChevronRight, ExternalLink, ImageIcon,
  Loader2, Pencil, Plus, RefreshCw, Scroll, Search, Shield, Sparkles, Sword, Trash2,
  User, Users, Wand2, X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import type { Character, CharacterAppearance, CharacterBeyondData, CharacterHistoryEntry, PortraitEntry } from '@/lib/api'
import { RACES_5E, CLASSES_5E } from '@/lib/dnd-constants'
import { MarkdownRenderer } from '@/components/MarkdownRenderer'
import { RichTextEditor } from '@/components/RichTextEditor'

// ── Character Card (list view) ───────────────────────────────────────────────

const CharacterCard = memo(function CharacterCard({
  character,
  campaigns,
  onClick,
  isNpc,
}: {
  character: Character
  campaigns?: CampaignLink[]
  onClick: () => void
  isNpc?: boolean
}) {
  const portrait = character.portrait_path || character.beyond_avatar_path
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-md border border-white/8 bg-shadow/40 hover:border-gold/20 hover:bg-shadow/60 transition-all p-3 flex gap-3 items-start"
    >
      <div className="flex-none w-14 h-14 rounded-md border border-white/10 bg-void/60 flex items-center justify-center overflow-hidden">
        {portrait ? (
          <img src={`file://${portrait}`} alt="" className="w-full h-full object-cover" />
        ) : (
          <User className="w-6 h-6 text-parchment/15" />
        )}
      </div>
      <div className="flex-1 min-w-0 space-y-0.5">
        <p className="text-sm font-heading text-parchment/85 truncate">{character.name || 'Unnamed'}</p>
        {isNpc ? (
          <>
            {(character.npc_race || character.npc_role) && (
              <div className="flex flex-wrap gap-1 mb-0.5">
                {character.npc_race && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-parchment/40 border border-white/5">{character.npc_race}</span>
                )}
                {character.npc_role && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-parchment/40 border border-white/5">{character.npc_role}</span>
                )}
                {character.npc_attitude && (
                  <span className={cn(
                    'text-[9px] px-1.5 py-0.5 rounded-full border capitalize',
                    character.npc_attitude === 'friendly' ? 'text-emerald-400/70 bg-emerald-400/10 border-emerald-400/20' :
                    character.npc_attitude === 'hostile' ? 'text-red-400/70 bg-red-400/10 border-red-400/20' :
                    'text-parchment/40 bg-white/5 border-white/5'
                  )}>{character.npc_attitude}</span>
                )}
              </div>
            )}
            <p className="text-[11px] font-body text-parchment/40 truncate line-clamp-2">
              {character.npc_description || 'No description yet — process more sessions'}
            </p>
            {character.npc_current_status && (
              <p className="text-[10px] font-body text-parchment/25 truncate mt-0.5 italic">
                {character.npc_current_status}
              </p>
            )}
          </>
        ) : (
          <p className="text-[11px] font-body text-parchment/50 truncate">
            {[character.race, character.class_name].filter(Boolean).join(' · ') || 'No details'}
          </p>
        )}
        {character.specialty && (
          <p className="text-[10px] font-body text-gold/40 truncate">{character.specialty}</p>
        )}
        {character.level > 1 && (
          <span className="inline-block text-[10px] font-heading text-parchment/30 bg-white/5 rounded px-1.5 py-0.5 mt-0.5">
            Level {character.level}
          </span>
        )}
        {campaigns && campaigns.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {campaigns.map((cl, i) => (
              <span key={i} className="text-[9px] font-body text-parchment/30 bg-gold/5 border border-gold/10 rounded px-1.5 py-0.5">
                {cl.campaign_name} S{cl.season_number}
              </span>
            ))}
          </div>
        )}
      </div>
    </button>
  )
})

// ── Create Character Form ────────────────────────────────────────────────────

function CreateCharacterForm({ onCreated, onCancel }: {
  onCreated: (c: Character) => void
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  const [race, setRace] = useState('')
  const [className, setClassName] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [beyondUrl, setBeyondUrl] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate() {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    const result = await api('create_character', name.trim(), race, className, '', 1, specialty, beyondUrl.trim())
    setSaving(false)
    if (result?.ok && result.character) {
      onCreated(result.character)
    } else {
      setError(result?.error || 'Failed to create character')
    }
  }

  return (
    <div className="rounded-md border border-gold/20 bg-gold/3 p-4 space-y-3">
      <p className="text-xs font-heading text-gold/60 uppercase tracking-widest">New Character</p>

      <div className="space-y-1">
        <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Name</Label>
        <Input
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g. Aphelios"
          className="h-8 text-sm bg-void/60 border-white/10 text-parchment placeholder:text-parchment/25"
          onKeyDown={e => { if (e.key === 'Enter') handleCreate() }}
        />
      </div>

      <div className="flex gap-2">
        <div className="flex-1 space-y-1">
          <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Race</Label>
          <select
            value={race}
            onChange={e => setRace(e.target.value)}
            className="w-full h-7 bg-void/60 border border-white/10 rounded px-2 text-xs text-parchment/70 outline-none focus:border-gold/40"
            style={{ colorScheme: 'dark' }}
          >
            <option value="">Select…</option>
            {RACES_5E.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div className="flex-1 space-y-1">
          <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Class</Label>
          <select
            value={className}
            onChange={e => setClassName(e.target.value)}
            className="w-full h-7 bg-void/60 border border-white/10 rounded px-2 text-xs text-parchment/70 outline-none focus:border-gold/40"
            style={{ colorScheme: 'dark' }}
          >
            <option value="">Select…</option>
            {CLASSES_5E.map(cl => <option key={cl} value={cl}>{cl}</option>)}
          </select>
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Specialty</Label>
        <Input
          value={specialty}
          onChange={e => setSpecialty(e.target.value)}
          placeholder="e.g. Arcane warrior, Healer, etc."
          className="h-7 text-xs bg-void/60 border-white/10 text-parchment placeholder:text-parchment/25"
        />
      </div>

      <div className="space-y-1">
        <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest flex items-center gap-1.5">
          <ExternalLink className="w-3 h-3" />D&amp;D Beyond URL (optional)
        </Label>
        <Input
          value={beyondUrl}
          onChange={e => setBeyondUrl(e.target.value)}
          placeholder="https://www.dndbeyond.com/characters/..."
          className="h-7 text-xs bg-void/60 border-white/10 text-parchment placeholder:text-parchment/20"
        />
        <p className="text-[10px] text-parchment/25 font-body">If set, character details will auto-sync from D&amp;D Beyond</p>
      </div>

      {error && <p className="text-xs text-red-400/80 font-body">{error}</p>}

      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={onCancel} className="h-7 text-xs px-3">Cancel</Button>
        <Button size="sm" onClick={handleCreate} disabled={saving || !name.trim()} className="flex-1 gap-1.5">
          <Check className="w-3.5 h-3.5" />{saving ? 'Creating…' : 'Create Character'}
        </Button>
      </div>
    </div>
  )
}

// ── Stat Block ───────────────────────────────────────────────────────────────

function StatBlock({ scores }: { scores: Record<string, number> }) {
  const labels: Record<string, string> = { str: 'STR', dex: 'DEX', con: 'CON', int: 'INT', wis: 'WIS', cha: 'CHA' }
  const order = ['str', 'dex', 'con', 'int', 'wis', 'cha']
  return (
    <div className="flex gap-2 flex-wrap">
      {order.map(key => {
        const val = scores[key]
        if (val === undefined) return null
        const mod = Math.floor((val - 10) / 2)
        return (
          <div key={key} className="text-center bg-void/40 border border-white/8 rounded-md px-2.5 py-1.5 min-w-[48px]">
            <div className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">{labels[key]}</div>
            <div className="text-sm font-heading text-parchment/80">{val}</div>
            <div className="text-[10px] font-body text-gold/50">{mod >= 0 ? '+' : ''}{mod}</div>
          </div>
        )
      })}
    </div>
  )
}

// ── History Timeline ─────────────────────────────────────────────────────────

function HistoryTimeline({ history, charId, onManualUpdate, onAutoUpdate }: {
  history: CharacterHistoryEntry[]
  charId: string
  onManualUpdate: (sessionId: string, text: string) => void
  onAutoUpdate: (sessionId: string, text: string) => void
}) {
  const [editingSession, setEditingSession] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [editingAutoSession, setEditingAutoSession] = useState<string | null>(null)
  const [editAutoText, setEditAutoText] = useState('')

  return (
    <div className="space-y-3">
      {history.length === 0 && (
        <p className="text-xs font-body text-parchment/30 text-center py-4">No history entries yet. Process a session to generate character updates.</p>
      )}
      {history.map((entry, i) => (
        <div key={entry.session_id || i} className="border-l-2 border-gold/20 pl-3 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-heading text-gold/50">{entry.session_date}</span>
            <span className="text-[10px] font-body text-parchment/30">
              {entry.campaign_name} · Season {entry.season_number}
            </span>
          </div>
          {editingAutoSession === entry.session_id ? (
            <div className="space-y-1.5">
              <textarea
                value={editAutoText}
                onChange={e => setEditAutoText(e.target.value)}
                rows={3}
                className="w-full text-xs font-body text-parchment/70 bg-void/40 border border-gold/20 rounded px-2 py-1.5 resize-y focus:outline-none focus:border-gold/40"
                placeholder="Character update for this session..."
              />
              <div className="flex gap-1.5">
                <Button size="sm" variant="outline" onClick={() => setEditingAutoSession(null)} className="h-5 text-[10px] px-2">Cancel</Button>
                <Button size="sm" onClick={() => { onAutoUpdate(entry.session_id, editAutoText); setEditingAutoSession(null) }} className="h-5 text-[10px] px-2 gap-1">
                  <Check className="w-2.5 h-2.5" />Save
                </Button>
              </div>
            </div>
          ) : entry.auto_text ? (
            <div className="group relative">
              <p className="text-xs font-body text-parchment/60 leading-relaxed pr-5">{entry.auto_text}</p>
              <button
                onClick={() => { setEditAutoText(entry.auto_text); setEditingAutoSession(entry.session_id) }}
                className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 text-parchment/20 hover:text-gold/50 transition-all"
                title="Edit auto-generated text"
              >
                <Pencil className="w-2.5 h-2.5" />
              </button>
            </div>
          ) : null}
          {entry.manual_text && editingSession !== entry.session_id && (
            <div className="bg-gold/5 border border-gold/10 rounded px-2 py-1.5">
              <p className="text-[10px] font-heading text-gold/40 uppercase tracking-widest mb-0.5">Player Notes</p>
              <div
                className="text-xs font-body text-parchment/60 leading-relaxed rich-text-display"
                dangerouslySetInnerHTML={{ __html: entry.manual_text }}
              />
            </div>
          )}
          {editingSession === entry.session_id ? (
            <div className="space-y-1.5">
              <RichTextEditor
                content={editText}
                onChange={setEditText}
                placeholder="Add your own notes about this session..."
              />
              <div className="flex gap-1.5">
                <Button size="sm" variant="outline" onClick={() => setEditingSession(null)} className="h-5 text-[10px] px-2">Cancel</Button>
                <Button size="sm" onClick={() => { onManualUpdate(entry.session_id, editText); setEditingSession(null) }} className="h-5 text-[10px] px-2 gap-1">
                  <Check className="w-2.5 h-2.5" />Save
                </Button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => { setEditText(entry.manual_text || ''); setEditingSession(entry.session_id) }}
              className="text-[10px] font-body text-parchment/25 hover:text-gold/50 transition-colors flex items-center gap-1"
            >
              <Pencil className="w-2.5 h-2.5" /> {entry.manual_text ? 'Edit notes' : 'Add notes'}
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Character Detail Screen ──────────────────────────────────────────────────

function CharacterDetail({
  character: initialCharacter,
  campaigns,
  onBack,
  onUpdated,
  onDeleted,
}: {
  character: Character
  campaigns?: CampaignLink[]
  onBack: () => void
  onUpdated: (c: Character) => void
  onDeleted: (id: string) => void
}) {
  const [character, setCharacter] = useState(initialCharacter)
  const [activeTab, setActiveTab] = useState<'info' | 'beyond' | 'history'>('info')
  const [syncing, setSyncing] = useState(false)
  const [generatingPortrait, setGeneratingPortrait] = useState(false)
  const [generatingFullbody, setGeneratingFullbody] = useState(false)
  const [generatingSummary, setGeneratingSummary] = useState(false)
  const [editingSummary, setEditingSummary] = useState(false)
  const [summaryEditText, setSummaryEditText] = useState('')
  const [editing, setEditing] = useState(false)
  const [editFields, setEditFields] = useState({
    name: character.name,
    race: character.race,
    class_name: character.class_name,
    specialty: character.specialty,
    beyond_url: character.beyond_url,
  })
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const beyond: CharacterBeyondData = character.beyond_data || {}
  const appearance = beyond.appearance || {} as CharacterAppearance
  const portrait = character.portrait_path || character.beyond_avatar_path
  const headerAvatar = character.beyond_avatar_path

  async function syncBeyond() {
    setSyncing(true)
    const result = await api('sync_beyond_character', character.id)
    setSyncing(false)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
    }
  }

  async function pickPortrait() {
    const path = await api('pick_character_realistic_portrait')
    if (path) {
      // Copy file to character dir and add to gallery
      const result = await api('update_character', character.id, { portrait_path: path })
      if (result?.ok && result.character) {
        setCharacter(result.character)
        onUpdated(result.character)
      }
    }
  }

  async function generatePortrait() {
    setGeneratingPortrait(true)
    const method = character.is_npc ? 'generate_npc_portrait' : 'generate_character_portrait'
    const result = await api(method, character.id)
    setGeneratingPortrait(false)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
    } else if (result?.ok && result.portrait_path) {
      const updated = { ...character, portrait_path: result.portrait_path }
      setCharacter(updated)
      onUpdated(updated)
    }
  }

  async function handleSetPrimary(portraitPath: string) {
    const result = await api('set_primary_portrait', character.id, portraitPath)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
    }
  }

  async function handleDeletePortrait(portraitPath: string) {
    const result = await api('delete_portrait', character.id, portraitPath)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
    }
  }

  async function generateFullbody() {
    setGeneratingFullbody(true)
    const method = character.is_npc ? 'generate_npc_fullbody' : 'generate_character_fullbody'
    const result = await api(method, character.id)
    setGeneratingFullbody(false)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
    }
  }

  async function handleSetPrimaryFullbody(path: string) {
    const result = await api('set_primary_fullbody', character.id, path)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
    }
  }

  async function handleDeleteFullbody(path: string) {
    const result = await api('delete_fullbody', character.id, path)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
    }
  }

  async function saveEdit() {
    setSaving(true)
    const result = await api('update_character', character.id, editFields)
    setSaving(false)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
      setEditing(false)
    }
  }

  async function handleDelete() {
    const result = await api('delete_character', character.id)
    if (result?.ok) onDeleted(character.id)
  }

  async function handleAutoUpdate(sessionId: string, text: string) {
    await api('update_character_history_auto', character.id, sessionId, text)
    const result = await api('get_character', character.id)
    if (result?.ok && result.character) {
      setCharacter(result.character)
    }
  }

  async function handleManualUpdate(sessionId: string, text: string) {
    await api('update_character_history_manual', character.id, sessionId, text)
    // Refresh character
    const result = await api('get_character', character.id)
    if (result?.ok && result.character) {
      setCharacter(result.character)
      onUpdated(result.character)
    }
  }

  async function generateSummary() {
    setGeneratingSummary(true)
    const result = await api('generate_character_history_summary', character.id)
    setGeneratingSummary(false)
    if (result?.ok && result.summary) {
      const updated = { ...character, history_summary: result.summary }
      setCharacter(updated)
      onUpdated(updated)
    }
  }

  const tabs = [
    { id: 'info' as const, label: 'Info', icon: User },
    { id: 'beyond' as const, label: 'D&D Beyond', icon: Shield, show: !!character.beyond_url },
    { id: 'history' as const, label: 'History', icon: Scroll },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/8 flex-shrink-0 space-y-3">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-parchment/40 hover:text-gold/60 transition-colors">
            <ArrowLeft className="w-4 h-4" />
          </button>

          <div className="flex-none w-12 h-12 rounded-md border border-white/10 bg-void/60 flex items-center justify-center overflow-hidden">
            {headerAvatar ? (
              <img src={`file://${headerAvatar}`} alt="" className="w-full h-full object-cover" />
            ) : (
              <User className="w-5 h-5 text-parchment/15" />
            )}
          </div>

          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-heading text-parchment/85 truncate">{character.name}</h2>
            <p className="text-[11px] font-body text-parchment/50 truncate">
              {[character.race, character.class_name].filter(Boolean).join(' · ')}
              {character.level > 1 ? ` · Level ${character.level}` : ''}
            </p>
            {character.specialty && (
              <p className="text-[10px] font-body text-gold/40 truncate">{character.specialty}</p>
            )}
          </div>

          <div className="flex items-center gap-1 flex-shrink-0">
            {character.beyond_url && (
              <button onClick={syncBeyond} disabled={syncing} title="Sync from D&D Beyond"
                className={cn('text-parchment/30 hover:text-gold/60 transition-colors', syncing && 'animate-spin')}>
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              onClick={() => { setEditFields({ name: character.name, race: character.race, class_name: character.class_name, specialty: character.specialty, beyond_url: character.beyond_url }); setEditing(e => !e) }}
              className={cn('transition-colors', editing ? 'text-gold/60' : 'text-parchment/25 hover:text-gold/60')}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            {!confirmDelete ? (
              <button onClick={() => setConfirmDelete(true)} className="text-parchment/25 hover:text-red-400/70 transition-colors">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            ) : (
              <div className="flex items-center gap-1">
                <button onClick={() => setConfirmDelete(false)} className="text-parchment/30 hover:text-parchment/60"><X className="w-3.5 h-3.5" /></button>
                <button onClick={handleDelete} className="text-red-400/70 hover:text-red-400"><Check className="w-3.5 h-3.5" /></button>
              </div>
            )}
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex gap-1">
          {tabs.filter(t => t.show !== false).map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-heading uppercase tracking-widest transition-all',
                activeTab === t.id
                  ? 'bg-gold/10 text-gold/80 border border-gold/20'
                  : 'text-parchment/30 hover:text-parchment/50 border border-transparent',
              )}
            >
              <t.icon className="w-3 h-3" />{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Edit form */}
      {editing && (
        <div className="px-5 py-3 border-b border-white/8 space-y-2.5">
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Name</Label>
              <Input value={editFields.name} onChange={e => setEditFields(f => ({ ...f, name: e.target.value }))}
                className="h-7 text-xs bg-void/60 border-white/10 text-parchment" />
            </div>
            <div className="space-y-1">
              <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Specialty</Label>
              <Input value={editFields.specialty} onChange={e => setEditFields(f => ({ ...f, specialty: e.target.value }))}
                className="h-7 text-xs bg-void/60 border-white/10 text-parchment" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Race</Label>
              <select value={editFields.race} onChange={e => setEditFields(f => ({ ...f, race: e.target.value }))}
                className="w-full h-7 bg-void/60 border border-white/10 rounded px-2 text-xs text-parchment/70 outline-none focus:border-gold/40" style={{ colorScheme: 'dark' }}>
                <option value="">Select…</option>
                {RACES_5E.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Class</Label>
              <select value={editFields.class_name} onChange={e => setEditFields(f => ({ ...f, class_name: e.target.value }))}
                className="w-full h-7 bg-void/60 border border-white/10 rounded px-2 text-xs text-parchment/70 outline-none focus:border-gold/40" style={{ colorScheme: 'dark' }}>
                <option value="">Select…</option>
                {CLASSES_5E.map(cl => <option key={cl} value={cl}>{cl}</option>)}
              </select>
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest flex items-center gap-1.5">
              <ExternalLink className="w-3 h-3" />D&amp;D Beyond URL
            </Label>
            <Input value={editFields.beyond_url} onChange={e => setEditFields(f => ({ ...f, beyond_url: e.target.value }))}
              placeholder="https://www.dndbeyond.com/characters/..."
              className="h-7 text-xs bg-void/60 border-white/10 text-parchment placeholder:text-parchment/20" />
          </div>
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" onClick={() => setEditing(false)} className="h-6 text-[11px] px-2">Cancel</Button>
            <Button size="sm" onClick={saveEdit} disabled={saving || !editFields.name.trim()} className="h-6 text-[11px] px-2 gap-1">
              <Check className="w-3 h-3" />{saving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {activeTab === 'info' && (
          <>
            {/* NPC Details (for NPCs only) */}
            {character.is_npc && (
              <div className="space-y-3">
                {/* Quick info badges */}
                {(character.npc_race || character.npc_role || character.npc_attitude) && (
                  <div className="flex flex-wrap gap-1.5">
                    {character.npc_race && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-parchment/50 border border-white/8">{character.npc_race}</span>
                    )}
                    {character.npc_role && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-parchment/50 border border-white/8">{character.npc_role}</span>
                    )}
                    {character.npc_attitude && (
                      <span className={cn(
                        'text-[10px] px-2 py-0.5 rounded-full border capitalize',
                        character.npc_attitude === 'friendly' ? 'text-emerald-400/70 bg-emerald-400/10 border-emerald-400/20' :
                        character.npc_attitude === 'hostile' ? 'text-red-400/70 bg-red-400/10 border-red-400/20' :
                        'text-parchment/40 bg-white/5 border-white/5'
                      )}>{character.npc_attitude}</span>
                    )}
                  </div>
                )}

                {/* Description */}
                <div className="space-y-1.5">
                  <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Description</p>
                  <p className="text-xs font-body text-parchment/60 leading-relaxed bg-white/3 rounded-md p-3 border border-white/5">
                    {character.npc_description || 'No description yet — process more sessions to enrich this NPC.'}
                  </p>
                </div>

                {/* Current Status */}
                {character.npc_current_status && (
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Current Status</p>
                    <p className="text-xs font-body text-parchment/50 leading-relaxed bg-white/3 rounded-md p-3 border border-white/5 italic">
                      {character.npc_current_status}
                    </p>
                  </div>
                )}

                {/* Session History */}
                {character.npc_session_history && character.npc_session_history.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">
                      Session History ({character.npc_session_history.length})
                    </p>
                    <div className="space-y-1.5">
                      {character.npc_session_history.map((entry, i) => (
                        <div key={i} className="rounded-md border border-white/5 bg-void/30 px-3 py-2">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] font-heading text-gold/60">{entry.session_date || 'Unknown date'}</span>
                            {entry.attitude && (
                              <span className={cn(
                                'text-[8px] px-1.5 py-0.5 rounded-full border capitalize',
                                entry.attitude === 'friendly' ? 'text-emerald-400/60 bg-emerald-400/8 border-emerald-400/15' :
                                entry.attitude === 'hostile' ? 'text-red-400/60 bg-red-400/8 border-red-400/15' :
                                'text-parchment/30 bg-white/3 border-white/5'
                              )}>{entry.attitude}</span>
                            )}
                          </div>
                          {entry.actions && (
                            <p className="text-[11px] font-body text-parchment/50 leading-relaxed">{entry.actions}</p>
                          )}
                          {entry.status && (
                            <p className="text-[10px] font-body text-parchment/30 italic mt-1">{entry.status}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Pictures gallery (portraits + full-body) */}
            <div className="space-y-2">
              <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">
                Pictures
              </p>

              {/* Portrait thumbnails */}
              {character.portraits && character.portraits.length > 0 && (
                <div>
                  <p className="text-[9px] font-body text-parchment/30 mb-1">Portraits</p>
                  <div className="flex gap-2 flex-wrap">
                    {character.portraits.map((p) => (
                      <div
                        key={p.path}
                        className={cn(
                          'relative w-28 h-28 rounded-md border overflow-hidden group/portrait cursor-pointer transition-all',
                          p.is_primary ? 'border-gold/50 ring-1 ring-gold/20' : 'border-white/10 hover:border-gold/25'
                        )}
                        onClick={() => handleSetPrimary(p.path)}
                      >
                        <img src={`file://${p.path}`} alt="Portrait" className="w-full h-full object-cover" />
                        {p.is_primary && (
                          <div className="absolute top-1 left-1 bg-gold/80 text-void text-[8px] font-heading uppercase tracking-wider px-1.5 py-0.5 rounded">
                            Primary
                          </div>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDeletePortrait(p.path) }}
                          className="absolute top-1 right-1 opacity-0 group-hover/portrait:opacity-100 bg-void/70 text-red-400/70 hover:text-red-400 rounded p-0.5 transition-all"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Full-body thumbnails */}
              {character.fullbodies && character.fullbodies.length > 0 && (
                <div>
                  <p className="text-[9px] font-body text-parchment/30 mb-1">Full-Body</p>
                  <div className="flex gap-2 flex-wrap">
                    {character.fullbodies.map((f) => (
                      <div
                        key={f.path}
                        className={cn(
                          'relative w-20 h-28 rounded-md border overflow-hidden group/fullbody cursor-pointer transition-all',
                          f.is_primary ? 'border-gold/50 ring-1 ring-gold/20' : 'border-white/10 hover:border-gold/25'
                        )}
                        onClick={() => handleSetPrimaryFullbody(f.path)}
                      >
                        <img src={`file://${f.path}`} alt="Full-body" className="w-full h-full object-cover" />
                        {f.is_primary && (
                          <div className="absolute top-1 left-1 bg-gold/80 text-void text-[8px] font-heading uppercase tracking-wider px-1.5 py-0.5 rounded">
                            Primary
                          </div>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDeleteFullbody(f.path) }}
                          className="absolute top-1 right-1 opacity-0 group-hover/fullbody:opacity-100 bg-void/70 text-red-400/70 hover:text-red-400 rounded p-0.5 transition-all"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Legacy single portrait fallback */}
              {(!character.portraits || character.portraits.length === 0) && (!character.fullbodies || character.fullbodies.length === 0) && character.portrait_path ? (
                <div className="w-28 h-28 rounded-md border border-white/10 overflow-hidden">
                  <img src={`file://${character.portrait_path}`} alt="Portrait" className="w-full h-full object-cover" />
                </div>
              ) : null}

              <div className="flex gap-2 flex-wrap">
                <Button size="sm" variant="outline" onClick={pickPortrait} className="h-7 text-xs gap-1.5">
                  <ImageIcon className="w-3 h-3" />Upload Picture
                </Button>
                <Button size="sm" variant="outline" onClick={generatePortrait} disabled={generatingPortrait}
                  className={cn("h-7 text-xs gap-1.5", generatingPortrait && "border-parchment/20 text-parchment/40 shadow-none")}>
                  {generatingPortrait ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                  {generatingPortrait ? 'Generating…' : 'Generate Portrait'}
                </Button>
                <Button size="sm" variant="outline" onClick={generateFullbody} disabled={generatingFullbody}
                  className={cn("h-7 text-xs gap-1.5", generatingFullbody && "border-parchment/20 text-parchment/40 shadow-none")}>
                  {generatingFullbody ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                  {generatingFullbody ? 'Generating…' : 'Generate Full-Body'}
                </Button>
              </div>
            </div>

            {/* Campaign links */}
            {campaigns && campaigns.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Campaigns</p>
                <div className="flex flex-wrap gap-1.5">
                  {campaigns.map((cl, i) => (
                    <span key={i} className="text-[11px] font-body text-parchment/50 bg-gold/5 border border-gold/10 rounded-md px-2 py-1">
                      {cl.campaign_name} &middot; Season {cl.season_number}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Basic info from beyond_data */}
            {beyond.background && (
              <div className="space-y-1">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Background</p>
                <p className="text-xs font-body text-parchment/60">{beyond.background}</p>
              </div>
            )}
            {beyond.alignment && (
              <div className="space-y-1">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Alignment</p>
                <p className="text-xs font-body text-parchment/60">{beyond.alignment}</p>
              </div>
            )}

            {/* Appearance */}
            {Object.values(appearance).some(Boolean) && (
              <div className="space-y-1">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Appearance</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {appearance.hair && <p className="text-xs font-body text-parchment/50"><span className="text-parchment/30">Hair:</span> {appearance.hair}</p>}
                  {appearance.eyes && <p className="text-xs font-body text-parchment/50"><span className="text-parchment/30">Eyes:</span> {appearance.eyes}</p>}
                  {appearance.skin && <p className="text-xs font-body text-parchment/50"><span className="text-parchment/30">Skin:</span> {appearance.skin}</p>}
                  {appearance.height && <p className="text-xs font-body text-parchment/50"><span className="text-parchment/30">Height:</span> {appearance.height}</p>}
                  {appearance.weight && <p className="text-xs font-body text-parchment/50"><span className="text-parchment/30">Weight:</span> {appearance.weight}</p>}
                  {appearance.age && <p className="text-xs font-body text-parchment/50"><span className="text-parchment/30">Age:</span> {appearance.age}</p>}
                </div>
              </div>
            )}

            {/* Personality */}
            {(beyond.personality_traits || beyond.ideals || beyond.bonds || beyond.flaws) && (
              <div className="space-y-2">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Personality</p>
                {beyond.personality_traits && (
                  <div className="space-y-0.5">
                    <p className="text-[10px] font-body text-parchment/30">Traits</p>
                    <p className="text-xs font-body text-parchment/50">{beyond.personality_traits}</p>
                  </div>
                )}
                {beyond.ideals && (
                  <div className="space-y-0.5">
                    <p className="text-[10px] font-body text-parchment/30">Ideals</p>
                    <p className="text-xs font-body text-parchment/50">{beyond.ideals}</p>
                  </div>
                )}
                {beyond.bonds && (
                  <div className="space-y-0.5">
                    <p className="text-[10px] font-body text-parchment/30">Bonds</p>
                    <p className="text-xs font-body text-parchment/50">{beyond.bonds}</p>
                  </div>
                )}
                {beyond.flaws && (
                  <div className="space-y-0.5">
                    <p className="text-[10px] font-body text-parchment/30">Flaws</p>
                    <p className="text-xs font-body text-parchment/50">{beyond.flaws}</p>
                  </div>
                )}
              </div>
            )}

            {/* Backstory */}
            {beyond.backstory && (
              <div className="space-y-1">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Backstory</p>
                <p className="text-xs font-body text-parchment/50 leading-relaxed whitespace-pre-wrap">{beyond.backstory}</p>
              </div>
            )}

            {/* D&D Beyond link */}
            {character.beyond_url && (
              <div className="pt-2">
                <button
                  onClick={() => api('open_path', character.beyond_url)}
                  className="text-[11px] font-heading text-gold/50 hover:text-gold/80 transition-colors uppercase tracking-widest flex items-center gap-1.5"
                >
                  <ExternalLink className="w-3 h-3" /> View on D&amp;D Beyond
                </button>
                {character.beyond_last_synced && (
                  <p className="text-[10px] font-body text-parchment/20 mt-1">
                    Last synced: {new Date(character.beyond_last_synced).toLocaleString()}
                  </p>
                )}
              </div>
            )}
          </>
        )}

        {activeTab === 'beyond' && (
          <>
            {/* Ability Scores */}
            {beyond.ability_scores && Object.keys(beyond.ability_scores).length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Ability Scores</p>
                <StatBlock scores={beyond.ability_scores} />
              </div>
            )}

            {beyond.hp !== undefined && beyond.hp > 0 && (
              <div className="space-y-1">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Hit Points</p>
                <p className="text-sm font-heading text-parchment/70">{beyond.hp}</p>
              </div>
            )}

            {/* Spells */}
            {beyond.spells && beyond.spells.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest flex items-center gap-1.5">
                  <Wand2 className="w-3 h-3" />Spells ({beyond.spells.length})
                </p>
                <div className="flex flex-wrap gap-1">
                  {beyond.spells.map(spell => (
                    <span key={spell} className="text-[10px] font-body text-parchment/50 bg-white/5 rounded px-1.5 py-0.5">{spell}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Equipment */}
            {beyond.equipment && beyond.equipment.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest flex items-center gap-1.5">
                  <Sword className="w-3 h-3" />Equipment ({beyond.equipment.length})
                </p>
                <div className="flex flex-wrap gap-1">
                  {beyond.equipment.map(item => (
                    <span key={item} className="text-[10px] font-body text-parchment/50 bg-white/5 rounded px-1.5 py-0.5">{item}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Sync button */}
            <div className="pt-4">
              <Button size="sm" variant="outline" onClick={syncBeyond} disabled={syncing} className="gap-1.5">
                <RefreshCw className={cn('w-3 h-3', syncing && 'animate-spin')} />
                {syncing ? 'Syncing…' : 'Refresh from D&D Beyond'}
              </Button>
            </div>
          </>
        )}

        {activeTab === 'history' && (
          <>
            {/* History Summary */}
            {character.history_summary && !editingSummary && (
              <div className="space-y-1.5 bg-gold/3 border border-gold/10 rounded-md p-3 group relative">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-heading text-gold/50 uppercase tracking-widest">Character Arc Summary</p>
                  <button
                    onClick={() => { setSummaryEditText(character.history_summary); setEditingSummary(true) }}
                    className="opacity-0 group-hover:opacity-100 text-parchment/20 hover:text-gold/50 transition-all"
                    title="Edit summary"
                  >
                    <Pencil className="w-3 h-3" />
                  </button>
                </div>
                <MarkdownRenderer text={character.history_summary} />
              </div>
            )}
            {editingSummary && (
              <div className="space-y-2 bg-gold/3 border border-gold/10 rounded-md p-3">
                <p className="text-[10px] font-heading text-gold/50 uppercase tracking-widest">Edit Arc Summary</p>
                <textarea
                  value={summaryEditText}
                  onChange={e => setSummaryEditText(e.target.value)}
                  rows={6}
                  className="w-full text-xs font-body text-parchment/70 bg-void/40 border border-gold/20 rounded px-2 py-1.5 resize-y focus:outline-none focus:border-gold/40"
                />
                <div className="flex gap-1.5">
                  <Button size="sm" variant="outline" onClick={() => setEditingSummary(false)} className="h-6 text-[10px] px-2">Cancel</Button>
                  <Button size="sm" onClick={async () => {
                    await api('update_character_history_summary', character.id, summaryEditText)
                    const result = await api('get_character', character.id)
                    if (result?.ok && result.character) {
                      setCharacter(result.character)
                      onUpdated(result.character)
                    }
                    setEditingSummary(false)
                  }} className="h-6 text-[10px] px-2 gap-1">
                    <Check className="w-2.5 h-2.5" />Save
                  </Button>
                </div>
              </div>
            )}

            {/* Generate summary button */}
            {character.history.length > 0 && !editingSummary && (
              <Button size="sm" variant="outline" onClick={generateSummary} disabled={generatingSummary} className="gap-1.5">
                <Sparkles className={cn('w-3 h-3', generatingSummary && 'animate-pulse')} />
                {generatingSummary ? 'Generating…' : character.history_summary ? 'Regenerate Summary' : 'Generate Arc Summary'}
              </Button>
            )}

            {/* Timeline */}
            <HistoryTimeline
              history={character.history}
              charId={character.id}
              onManualUpdate={handleManualUpdate}
              onAutoUpdate={handleAutoUpdate}
            />
          </>
        )}
      </div>
    </div>
  )
}

// ── Main Tab ─────────────────────────────────────────────────────────────────

interface CampaignLink { campaign_name: string; season_number: number }

export function CharactersTab({ focusCharacterId, onFocusHandled }: { focusCharacterId?: string | null; onFocusHandled?: () => void } = {}) {
  const [characters, setCharacters] = useState<Character[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedChar, setSelectedChar] = useState<Character | null>(null)
  const [campaignLinks, setCampaignLinks] = useState<Record<string, CampaignLink[]>>({})
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<'all' | 'heroes' | 'npcs'>('all')
  const [sortOrder, setSortOrder] = useState<'name-asc' | 'name-desc' | 'level-asc' | 'level-desc'>('name-asc')

  useEffect(() => {
    async function load() {
      const allChars = await api('get_characters') as Character[] | null
      const chars = (allChars ?? []).filter(c => !c.is_dm)
      setCharacters(chars)
      setLoading(false)
      // Load campaign links for each character
      if (chars) {
        const links: Record<string, CampaignLink[]> = {}
        for (const c of chars) {
          const result = await api('get_character_campaigns', c.id) as CampaignLink[] | null
          if (result && result.length > 0) links[c.id] = result
        }
        setCampaignLinks(links)
      }
    }
    load()
  }, [])

  // Cross-tab navigation: auto-select a character when focusCharacterId changes
  useEffect(() => {
    if (!focusCharacterId || characters.length === 0) return
    const match = characters.find(c => c.id === focusCharacterId)
    if (match) {
      setSelectedChar(match)
      onFocusHandled?.()
    }
  }, [focusCharacterId, characters]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleCreated(c: Character) {
    setCharacters(prev => [...prev, c])
    setShowCreate(false)
    setSelectedChar(c)
  }

  function handleUpdated(updated: Character) {
    setCharacters(prev => prev.map(c => c.id === updated.id ? updated : c))
    setSelectedChar(prev => prev?.id === updated.id ? updated : prev)
  }

  function handleDeleted(id: string) {
    setCharacters(prev => prev.filter(c => c.id !== id))
    setSelectedChar(null)
  }

  // Filter + sort (memoized to avoid recomputing on unrelated re-renders)
  const { heroes, npcs } = useMemo(() => {
    const filtered = characters.filter(c => {
      if (typeFilter === 'heroes' && c.is_npc) return false
      if (typeFilter === 'npcs' && !c.is_npc) return false
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        return (
          c.name?.toLowerCase().includes(q) ||
          c.race?.toLowerCase().includes(q) ||
          c.class_name?.toLowerCase().includes(q) ||
          c.specialty?.toLowerCase().includes(q) ||
          c.npc_description?.toLowerCase().includes(q) ||
          false
        )
      }
      return true
    }).sort((a, b) => {
      switch (sortOrder) {
        case 'name-asc': return (a.name || '').localeCompare(b.name || '')
        case 'name-desc': return (b.name || '').localeCompare(a.name || '')
        case 'level-asc': return (a.level || 0) - (b.level || 0)
        case 'level-desc': return (b.level || 0) - (a.level || 0)
        default: return 0
      }
    })
    return {
      heroes: filtered.filter(c => !c.is_npc),
      npcs: filtered.filter(c => c.is_npc),
    }
  }, [characters, typeFilter, searchQuery, sortOrder])

  if (selectedChar) {
    return (
      <CharacterDetail
        character={selectedChar}
        campaigns={campaignLinks[selectedChar.id]}
        onBack={() => setSelectedChar(null)}
        onUpdated={handleUpdated}
        onDeleted={handleDeleted}
      />
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/8 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <Users className="w-4 h-4 text-gold/50" />
          <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">Characters</h2>
          {!loading && characters.length > 0 && (
            <span className="text-[10px] font-body text-parchment/30">{characters.length}</span>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setShowCreate(s => !s)}
          className="h-7 text-xs gap-1.5"
        >
          {showCreate ? <X className="w-3 h-3" /> : <Plus className="w-3.5 h-3.5" />}
          {showCreate ? 'Cancel' : 'New Character'}
        </Button>
      </div>

      {/* Filter bar */}
      {!loading && characters.length > 0 && (
        <div className="flex-none px-4 py-2.5 border-b border-white/5 flex items-center gap-2 flex-wrap">
          {/* Search */}
          <div className="relative flex-1 min-w-[140px]">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-parchment/25" />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search characters…"
              className="w-full h-7 bg-void/60 border border-white/8 rounded pl-7 pr-2 text-[11px] text-parchment/60 outline-none focus:border-gold/40 placeholder:text-parchment/20"
            />
          </div>
          {/* Type toggle */}
          <div className="flex rounded-md border border-white/8 overflow-hidden">
            {([['all', 'All'], ['heroes', 'Heroes'], ['npcs', 'NPCs']] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTypeFilter(key)}
                className={cn(
                  'px-2.5 py-1 text-[10px] font-heading uppercase tracking-wider transition-colors',
                  typeFilter === key ? 'bg-gold/20 text-gold' : 'bg-void/40 text-parchment/40 hover:text-parchment/60'
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {/* Sort */}
          <select
            value={sortOrder}
            onChange={e => setSortOrder(e.target.value as any)}
            className="h-7 bg-void/60 border border-white/8 rounded px-2 text-[10px] text-parchment/50 outline-none focus:border-gold/40"
            style={{ colorScheme: 'dark' }}
          >
            <option value="name-asc">Name A→Z</option>
            <option value="name-desc">Name Z→A</option>
            <option value="level-desc">Level ↓</option>
            <option value="level-asc">Level ↑</option>
          </select>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {showCreate && (
          <CreateCharacterForm onCreated={handleCreated} onCancel={() => setShowCreate(false)} />
        )}

        {loading && (
          <div className="flex items-center justify-center py-12">
            <p className="text-xs font-body text-parchment/30">Loading characters…</p>
          </div>
        )}

        {!loading && heroes.length === 0 && npcs.length === 0 && !showCreate && (
          <div className="flex flex-col items-center justify-center py-12 gap-3 text-center">
            <Users className="w-8 h-8 text-parchment/10" />
            <p className="text-sm font-heading text-parchment/30">No characters yet</p>
            <p className="text-xs font-body text-parchment/20">Create characters to manage your adventuring party</p>
            <Button size="sm" variant="outline" onClick={() => setShowCreate(true)} className="mt-2 gap-1.5">
              <Plus className="w-3.5 h-3.5" />New Character
            </Button>
          </div>
        )}

        {/* Heroes Section */}
        {!loading && heroes.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-3.5 h-3.5 text-gold/40" />
              <h3 className="text-xs font-heading text-parchment/50 uppercase tracking-widest">Heroes</h3>
              <span className="text-[10px] font-body text-parchment/25">{heroes.length}</span>
            </div>
            <div className="grid gap-2">
              {heroes.map(char => (
                <CharacterCard
                  key={char.id}
                  character={char}
                  campaigns={campaignLinks[char.id]}
                  onClick={() => setSelectedChar(char)}
                />
              ))}
            </div>
          </div>
        )}

        {/* NPCs Section */}
        {!loading && npcs.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Scroll className="w-3.5 h-3.5 text-parchment/30" />
              <h3 className="text-xs font-heading text-parchment/50 uppercase tracking-widest">NPCs</h3>
              <span className="text-[10px] font-body text-parchment/25">{npcs.length}</span>
            </div>
            <div className="grid gap-2">
              {npcs.map(char => (
                <CharacterCard
                  key={char.id}
                  character={char}
                  campaigns={campaignLinks[char.id]}
                  onClick={() => setSelectedChar(char)}
                  isNpc
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
