import { useState, useEffect } from 'react'
import {
  ChevronDown, ChevronRight, Pencil, Trash2, Plus, Check, X,
  ExternalLink, Link, Shield, Users, User, BookOpen, Save,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import type { Campaign, Season, Character, GlossaryEntry } from '@/lib/api'
import { RACES_5E, CLASSES_5E } from '@/lib/dnd-constants'

// ── Character Picker ─────────────────────────────────────────────────────────

export function CharacterPicker({
  selectedIds,
  onChange,
  allCharacters,
  onCharactersChanged,
}: {
  selectedIds: string[]
  onChange: (ids: string[]) => void
  allCharacters: Character[]
  onCharactersChanged: (chars: Character[]) => void
}) {
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newRace, setNewRace] = useState('')
  const [newClass, setNewClass] = useState('')
  const [creating, setCreating] = useState(false)

  const available = allCharacters.filter(c => !selectedIds.includes(c.id))
  const selected = selectedIds.map(id => allCharacters.find(c => c.id === id)).filter(Boolean) as Character[]

  async function handleCreate() {
    if (!newName.trim()) return
    setCreating(true)
    const result = await api('create_character', newName.trim(), newRace, newClass)
    setCreating(false)
    if (result?.ok && result.character) {
      onCharactersChanged([...allCharacters, result.character])
      onChange([...selectedIds, result.character.id])
      setShowCreate(false)
      setNewName('')
      setNewRace('')
      setNewClass('')
    }
  }

  return (
    <div className="space-y-2">
      {selected.map(c => {
        const portrait = c.portrait_path || c.beyond_avatar_path
        return (
          <div key={c.id} className="flex items-center gap-2 rounded-md border border-white/6 bg-void/30 px-2 py-1.5">
            <div className="flex-none w-6 h-6 rounded border border-white/10 bg-void/60 flex items-center justify-center overflow-hidden">
              {portrait ? (
                <img src={`file://${portrait}`} alt="" className="w-full h-full object-cover" />
              ) : (
                <User className="w-3 h-3 text-parchment/20" />
              )}
            </div>
            <span className="text-xs font-body text-parchment/70 flex-1 truncate">
              {c.name}
              {(c.race || c.class_name) && (
                <span className="text-parchment/30 ml-1">
                  {[c.race, c.class_name].filter(Boolean).join(' ')}
                </span>
              )}
            </span>
            <button
              onClick={() => onChange(selectedIds.filter(id => id !== c.id))}
              className="text-parchment/30 hover:text-red-400/70 transition-colors flex-shrink-0"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )
      })}

      {available.length > 0 && (
        <select
          value=""
          onChange={e => {
            if (e.target.value) onChange([...selectedIds, e.target.value])
          }}
          className="w-full h-7 bg-void/60 border border-white/10 rounded px-2 text-xs text-parchment/50 outline-none focus:border-gold/40"
          style={{ colorScheme: 'dark' }}
        >
          <option value="">Add existing character…</option>
          {available.map(c => (
            <option key={c.id} value={c.id}>
              {c.name}{c.race ? ` (${c.race})` : ''}{c.class_name ? ` — ${c.class_name}` : ''}
            </option>
          ))}
        </select>
      )}

      {showCreate ? (
        <div className="space-y-1.5 rounded-md border border-gold/15 bg-gold/3 p-2">
          <Input
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder="Character name"
            className="h-7 text-xs bg-void/60 border-white/10 text-parchment placeholder:text-parchment/25"
            onKeyDown={e => { if (e.key === 'Enter') handleCreate() }}
            autoFocus
          />
          <div className="flex gap-1.5">
            <select value={newRace} onChange={e => setNewRace(e.target.value)}
              className="flex-1 h-6 bg-void/60 border border-white/10 rounded px-1.5 text-[10px] text-parchment/70 outline-none focus:border-gold/40" style={{ colorScheme: 'dark' }}>
              <option value="">Race…</option>
              {RACES_5E.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <select value={newClass} onChange={e => setNewClass(e.target.value)}
              className="flex-1 h-6 bg-void/60 border border-white/10 rounded px-1.5 text-[10px] text-parchment/70 outline-none focus:border-gold/40" style={{ colorScheme: 'dark' }}>
              <option value="">Class…</option>
              {CLASSES_5E.map(cl => <option key={cl} value={cl}>{cl}</option>)}
            </select>
          </div>
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" onClick={() => setShowCreate(false)} className="h-5 text-[10px] px-2">Cancel</Button>
            <Button size="sm" onClick={handleCreate} disabled={creating || !newName.trim()} className="h-5 text-[10px] px-2 gap-1">
              <Check className="w-2.5 h-2.5" />{creating ? 'Creating…' : 'Create & Add'}
            </Button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowCreate(true)}
          className="text-[11px] text-parchment/35 hover:text-gold/60 transition-colors font-body flex items-center gap-1"
        >
          <Plus className="w-3 h-3" /> Create new character
        </button>
      )}
    </div>
  )
}

// ── Season row ────────────────────────────────────────────────────────────────

function SeasonRow({
  campaign,
  season,
  allCharacters,
  onUpdated,
  onCharactersChanged,
}: {
  campaign: Campaign
  season: Season
  allCharacters: Character[]
  onUpdated: (updated: Campaign) => void
  onCharactersChanged: (chars: Character[]) => void
}) {
  const [editing, setEditing] = useState(false)
  const [editIds, setEditIds] = useState<string[]>(season.characters)
  const [saving, setSaving] = useState(false)

  const selectedChars = season.characters
    .map(id => allCharacters.find(c => c.id === id))
    .filter(Boolean) as Character[]

  async function save() {
    setSaving(true)
    const result = await api('update_season', campaign.id, season.id, editIds)
    setSaving(false)
    if (result?.ok) {
      const updated: Campaign = {
        ...campaign,
        seasons: campaign.seasons.map(s =>
          s.id === season.id ? { ...s, characters: editIds } : s
        ),
      }
      onUpdated(updated)
      setEditing(false)
    }
  }

  return (
    <div className="pl-4 py-2 border-l border-white/8 ml-1 space-y-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Users className="w-3 h-3 text-parchment/30" />
          <span className="text-xs font-heading text-parchment/60 uppercase tracking-widest">
            Season {season.number}
          </span>
          {!editing && (
            <span className="text-[10px] text-parchment/30 font-body ml-1">
              {selectedChars.length} adventurer{selectedChars.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        {!editing && (
          <button
            onClick={() => { setEditIds(season.characters); setEditing(true) }}
            className="text-parchment/25 hover:text-gold/60 transition-colors"
          >
            <Pencil className="w-3 h-3" />
          </button>
        )}
      </div>

      {!editing && selectedChars.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-1">
          {selectedChars.map(c => {
            const portrait = c.portrait_path || c.beyond_avatar_path
            return (
              <span key={c.id} className="text-[10px] font-body text-parchment/50 bg-white/5 rounded px-1.5 py-0.5 flex items-center gap-1">
                {portrait && (
                  <img src={`file://${portrait}`} alt="" className="w-3.5 h-3.5 rounded-full object-cover inline-block" />
                )}
                {c.name}
                {(c.race || c.class_name) && (
                  <span className="text-parchment/30">
                    {[c.race, c.class_name].filter(Boolean).join(' ')}
                  </span>
                )}
              </span>
            )
          })}
        </div>
      )}

      {editing && (
        <div className="space-y-2">
          <CharacterPicker
            selectedIds={editIds}
            onChange={setEditIds}
            allCharacters={allCharacters}
            onCharactersChanged={onCharactersChanged}
          />
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" onClick={() => setEditing(false)} className="h-6 text-[11px] px-2">Cancel</Button>
            <Button size="sm" onClick={save} disabled={saving || editIds.length === 0} className="h-6 text-[11px] px-2 gap-1">
              <Check className="w-3 h-3" />{saving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Campaign card ─────────────────────────────────────────────────────────────

function CampaignCard({
  campaign,
  allCharacters,
  onUpdated,
  onDeleted,
  onCharactersChanged,
}: {
  campaign: Campaign
  allCharacters: Character[]
  onUpdated: (updated: Campaign) => void
  onDeleted: (id: string) => void
  onCharactersChanged: (chars: Character[]) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState(campaign.name)
  const [editUrl, setEditUrl] = useState(campaign.beyond_url ?? '')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const [showAddSeason, setShowAddSeason] = useState(false)
  const [newSeasonCharIds, setNewSeasonCharIds] = useState<string[]>([])
  const [addingSeasonNum, setAddingSeasonNum] = useState(
    Math.max(0, ...campaign.seasons.map(s => s.number)) + 1
  )

  async function saveCampaign() {
    if (!editName.trim()) return
    setSaving(true)
    const result = await api('update_campaign', campaign.id, editName.trim(), editUrl.trim())
    setSaving(false)
    if (result?.ok) {
      onUpdated({ ...campaign, name: editName.trim(), beyond_url: editUrl.trim() })
      setEditing(false)
    }
  }

  async function handleDelete() {
    const result = await api('delete_campaign', campaign.id)
    if (result?.ok) onDeleted(campaign.id)
  }

  async function handleAddSeason() {
    if (!newSeasonCharIds.length) return
    const result = await api('add_season', campaign.id, addingSeasonNum, newSeasonCharIds)
    if (result?.ok && result.season) {
      onUpdated({ ...campaign, seasons: [...campaign.seasons, result.season] })
      setShowAddSeason(false)
      setNewSeasonCharIds([])
      setAddingSeasonNum(addingSeasonNum + 1)
    }
  }

  function openBeyond() {
    const url = campaign.beyond_url?.trim()
    if (url) api('open_path', url)
  }

  const hasBeyondUrl = !!(campaign.beyond_url?.trim())

  return (
    <div className={cn(
      'rounded-md border transition-colors',
      expanded ? 'border-white/12 bg-shadow/80' : 'border-white/8 bg-shadow/40 hover:border-white/10',
    )}>
      <div className="flex items-center gap-2 px-3 py-2.5">
        <button onClick={() => setExpanded(e => !e)} className="flex items-center gap-2 flex-1 min-w-0 text-left">
          {expanded ? <ChevronDown className="w-3.5 h-3.5 text-gold/50 flex-shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-parchment/30 flex-shrink-0" />}
          <Shield className="w-3.5 h-3.5 text-gold/40 flex-shrink-0" />
          <span className="text-sm font-heading text-parchment/85 truncate">{campaign.name}</span>
          <span className="text-[10px] text-parchment/30 font-body ml-1 flex-shrink-0">
            {campaign.seasons.length} season{campaign.seasons.length !== 1 ? 's' : ''}
          </span>
        </button>
        <div className="flex items-center gap-1 flex-shrink-0">
          {hasBeyondUrl && (
            <button onClick={openBeyond} title="Open in D&D Beyond" className="text-parchment/25 hover:text-gold/60 transition-colors">
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={() => { setEditName(campaign.name); setEditUrl(campaign.beyond_url ?? ''); setEditing(e => !e); setExpanded(true) }}
            className={cn('transition-colors', editing ? 'text-gold/60' : 'text-parchment/25 hover:text-gold/60')}
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          {!confirmDelete ? (
            <button onClick={() => setConfirmDelete(true)} className="text-parchment/25 hover:text-red-400/70 transition-colors"><Trash2 className="w-3.5 h-3.5" /></button>
          ) : (
            <div className="flex items-center gap-1">
              <button onClick={() => setConfirmDelete(false)} className="text-parchment/30 hover:text-parchment/60"><X className="w-3.5 h-3.5" /></button>
              <button onClick={handleDelete} className="text-red-400/70 hover:text-red-400"><Check className="w-3.5 h-3.5" /></button>
            </div>
          )}
        </div>
      </div>

      {editing && (
        <div className="px-4 pb-3 pt-1 space-y-2.5 border-t border-white/6">
          <div className="space-y-1">
            <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Campaign name</Label>
            <Input value={editName} onChange={e => setEditName(e.target.value)} className="h-7 text-xs bg-void/60 border-white/10 text-parchment" />
          </div>
          <div className="space-y-1">
            <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest flex items-center gap-1.5">
              <Link className="w-3 h-3" />D&amp;D Beyond URL
            </Label>
            <Input value={editUrl} onChange={e => setEditUrl(e.target.value)} placeholder="https://www.dndbeyond.com/campaigns/..." className="h-7 text-xs bg-void/60 border-white/10 text-parchment placeholder:text-parchment/20" />
          </div>
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" onClick={() => setEditing(false)} className="h-6 text-[11px] px-2">Cancel</Button>
            <Button size="sm" onClick={saveCampaign} disabled={saving || !editName.trim()} className="h-6 text-[11px] px-2 gap-1">
              <Check className="w-3 h-3" />{saving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      )}

      {expanded && !editing && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-white/6">
          {hasBeyondUrl && (
            <div className="flex items-center gap-2 py-1">
              <Link className="w-3 h-3 text-parchment/30 flex-shrink-0" />
              <span className="text-[11px] text-parchment/40 font-body truncate flex-1">{campaign.beyond_url}</span>
              <button onClick={openBeyond} className="text-[10px] font-heading text-gold/50 hover:text-gold/80 transition-colors uppercase tracking-widest flex items-center gap-1 flex-shrink-0">
                Open <ExternalLink className="w-2.5 h-2.5" />
              </button>
            </div>
          )}
          {!hasBeyondUrl && (
            <button onClick={() => { setEditName(campaign.name); setEditUrl(''); setEditing(true) }} className="text-[11px] font-body text-parchment/25 hover:text-gold/50 transition-colors flex items-center gap-1.5 py-0.5">
              <Link className="w-3 h-3" /> Add D&amp;D Beyond link
            </button>
          )}

          {campaign.seasons.length > 0 && (
            <div className="space-y-1">
              {campaign.seasons.map(s => (
                <SeasonRow key={s.id} campaign={campaign} season={s} allCharacters={allCharacters} onUpdated={onUpdated} onCharactersChanged={onCharactersChanged} />
              ))}
            </div>
          )}

          {showAddSeason ? (
            <div className="pl-4 border-l border-white/8 ml-1 space-y-2 py-1.5">
              <span className="text-[10px] font-heading text-parchment/50 uppercase tracking-widest">Season {addingSeasonNum}</span>
              <CharacterPicker selectedIds={newSeasonCharIds} onChange={setNewSeasonCharIds} allCharacters={allCharacters} onCharactersChanged={onCharactersChanged} />
              <div className="flex gap-1.5">
                <Button size="sm" variant="outline" onClick={() => { setShowAddSeason(false); setNewSeasonCharIds([]) }} className="h-6 text-[11px] px-2">Cancel</Button>
                <Button size="sm" onClick={handleAddSeason} disabled={newSeasonCharIds.length === 0} className="h-6 text-[11px] px-2 gap-1">
                  <Check className="w-3 h-3" />Add Season
                </Button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => { setAddingSeasonNum(Math.max(0, ...campaign.seasons.map(s => s.number)) + 1); setShowAddSeason(true) }}
              className="text-[11px] font-body text-parchment/25 hover:text-gold/50 transition-colors flex items-center gap-1.5 py-0.5"
            >
              <Plus className="w-3 h-3" /> Add season
            </button>
          )}

          <GlossarySection campaignId={campaign.id} />
        </div>
      )}
    </div>
  )
}

// ── Glossary Section ─────────────────────────────────────────────────────────

const GLOSSARY_CATEGORIES = ['Faction', 'Item', 'Spell', 'Other']

function GlossarySection({ campaignId }: { campaignId: string }) {
  const [expanded, setExpanded] = useState(false)
  const [glossary, setGlossary] = useState<Record<string, GlossaryEntry>>({})
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [newTerm, setNewTerm] = useState('')
  const [activeCategory, setActiveCategory] = useState<string>('All')
  const [search, setSearch] = useState('')
  const [expandedDesc, setExpandedDesc] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!expanded || loaded) return
    async function load() {
      const data = await api('get_campaign_glossary', campaignId)
      setGlossary(data ?? {})
      setLoaded(true)
    }
    load()
  }, [expanded, loaded, campaignId])

  async function handleSave() {
    setSaving(true)
    await api('update_campaign_glossary', campaignId, glossary)
    setSaving(false)
    setDirty(false)
  }

  function updateEntry(term: string, field: 'category' | 'definition' | 'description', value: string) {
    setGlossary(prev => ({
      ...prev,
      [term]: { ...prev[term], [field]: value },
    }))
    setDirty(true)
  }

  function deleteTerm(term: string) {
    setGlossary(prev => {
      const next = { ...prev }
      delete next[term]
      return next
    })
    setDirty(true)
  }

  function addTerm() {
    const t = newTerm.trim()
    if (!t || t in glossary) return
    const cat = activeCategory !== 'All' ? activeCategory : 'Other'
    setGlossary(prev => ({
      ...prev,
      [t]: { category: cat, definition: '', description: '' },
    }))
    setNewTerm('')
    setDirty(true)
  }

  const termCount = Object.keys(glossary).length

  // Category counts
  const categoryCounts: Record<string, number> = { All: termCount }
  for (const entry of Object.values(glossary)) {
    const cat = entry.category || 'Other'
    categoryCounts[cat] = (categoryCounts[cat] || 0) + 1
  }

  // Filter terms by category + search
  const filteredTerms = Object.keys(glossary)
    .filter(term => {
      if (activeCategory !== 'All' && glossary[term].category !== activeCategory) return false
      if (search) {
        const q = search.toLowerCase()
        return term.toLowerCase().includes(q) ||
          glossary[term].definition?.toLowerCase().includes(q) ||
          glossary[term].description?.toLowerCase().includes(q)
      }
      return true
    })
    .sort((a, b) => a.localeCompare(b))

  return (
    <div className="border-t border-white/6 pt-2 mt-1">
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex items-center gap-1.5 w-full text-left py-0.5"
      >
        {expanded ? <ChevronDown className="w-3 h-3 text-gold/50" /> : <ChevronRight className="w-3 h-3 text-parchment/30" />}
        <BookOpen className="w-3 h-3 text-gold/40" />
        <span className="text-[11px] font-heading text-parchment/50 uppercase tracking-widest">
          Glossary
        </span>
        {termCount > 0 && (
          <span className="text-[10px] text-parchment/30 font-body ml-1">{termCount} term{termCount !== 1 ? 's' : ''}</span>
        )}
      </button>

      {expanded && (
        <div className="mt-2 space-y-2 pl-1">
          {!loaded && (
            <p className="text-[10px] text-parchment/25 font-body">Loading…</p>
          )}

          {loaded && (
            <>
              {/* Category filter pills */}
              <div className="flex flex-wrap gap-1">
                {['All', ...GLOSSARY_CATEGORIES].map(cat => {
                  const count = categoryCounts[cat] || 0
                  const isActive = activeCategory === cat
                  return (
                    <button
                      key={cat}
                      onClick={() => setActiveCategory(cat)}
                      className={cn(
                        'px-2 py-0.5 rounded-full text-[9px] font-heading uppercase tracking-wider transition-colors',
                        isActive
                          ? 'bg-gold/20 text-gold border border-gold/30'
                          : 'bg-void/40 text-parchment/40 border border-white/6 hover:border-gold/20 hover:text-parchment/60'
                      )}
                    >
                      {cat} {count > 0 && <span className="text-[8px] opacity-60">({count})</span>}
                    </button>
                  )
                })}
              </div>

              {/* Search */}
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search terms…"
                className="w-full h-6 bg-void/60 border border-white/8 rounded px-2 text-[10px] text-parchment/50 outline-none focus:border-gold/40 placeholder:text-parchment/20"
              />

              {termCount === 0 && (
                <p className="text-[10px] text-parchment/25 font-body italic">
                  No glossary terms yet. Process a session to auto-populate, or add manually.
                </p>
              )}

              {filteredTerms.length > 0 && (
                <div className="space-y-1.5 max-h-80 overflow-y-auto pr-1">
                  {filteredTerms.map(term => {
                    const entry = glossary[term]
                    const hasDesc = !!entry.description
                    const isDescExpanded = expandedDesc[term]
                    return (
                      <div key={term} className="rounded border border-white/5 bg-void/30 px-2 py-1.5 group">
                        {/* Row 1: name, category, delete */}
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] font-body text-parchment/80 font-semibold truncate flex-1" title={term}>
                            {term}
                          </span>
                          <select
                            value={entry.category}
                            onChange={e => updateEntry(term, 'category', e.target.value)}
                            className="h-5 bg-void/60 border border-white/8 rounded px-1 text-[9px] text-parchment/50 outline-none focus:border-gold/40 flex-shrink-0"
                            style={{ colorScheme: 'dark' }}
                          >
                            {GLOSSARY_CATEGORIES.map(c => (
                              <option key={c} value={c}>{c}</option>
                            ))}
                          </select>
                          <button
                            onClick={() => deleteTerm(term)}
                            className="text-parchment/20 hover:text-red-400/70 transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                        {/* Row 2: definition */}
                        <input
                          value={entry.definition}
                          onChange={e => updateEntry(term, 'definition', e.target.value)}
                          className="w-full mt-1 h-5 bg-void/40 border border-white/5 rounded px-1.5 text-[10px] text-parchment/60 outline-none focus:border-gold/40 placeholder:text-parchment/20"
                          placeholder="Definition (brief factual summary)…"
                        />
                        {/* Row 3: description (expandable) */}
                        <button
                          onClick={() => setExpandedDesc(prev => ({ ...prev, [term]: !prev[term] }))}
                          className="mt-1 text-[9px] text-parchment/30 hover:text-parchment/50 transition-colors"
                        >
                          {isDescExpanded ? '▾ Hide description' : hasDesc ? '▸ Show description' : '▸ Add description'}
                        </button>
                        {isDescExpanded && (
                          <textarea
                            value={entry.description || ''}
                            onChange={e => updateEntry(term, 'description', e.target.value)}
                            className="w-full mt-1 bg-void/40 border border-white/5 rounded px-1.5 py-1 text-[10px] text-parchment/50 outline-none focus:border-gold/40 placeholder:text-parchment/20 resize-y min-h-[40px]"
                            rows={3}
                            placeholder="Richer description (context, relationships, events)…"
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {filteredTerms.length === 0 && termCount > 0 && (
                <p className="text-[10px] text-parchment/25 font-body italic">No terms match this filter.</p>
              )}

              {/* Add term + Save */}
              <div className="flex items-center gap-1.5">
                <input
                  value={newTerm}
                  onChange={e => setNewTerm(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') addTerm() }}
                  placeholder="Add term…"
                  className="flex-1 h-6 bg-void/60 border border-white/8 rounded px-2 text-[10px] text-parchment/50 outline-none focus:border-gold/40 placeholder:text-parchment/20"
                />
                <Button size="sm" variant="outline" onClick={addTerm} disabled={!newTerm.trim()} className="h-6 text-[10px] px-2 gap-1">
                  <Plus className="w-2.5 h-2.5" />Add
                </Button>
                {dirty && (
                  <Button size="sm" onClick={handleSave} disabled={saving} className="h-6 text-[10px] px-2 gap-1">
                    <Save className="w-2.5 h-2.5" />{saving ? 'Saving…' : 'Save'}
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Create campaign form ──────────────────────────────────────────────────────

export function CreateCampaignForm({ onCreated, onCancel, allCharacters, onCharactersChanged }: {
  onCreated: (c: Campaign) => void
  onCancel?: () => void
  allCharacters: Character[]
  onCharactersChanged: (chars: Character[]) => void
}) {
  const [name, setName] = useState('')
  const [charIds, setCharIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleCreate() {
    const trimName = name.trim()
    if (!trimName || !charIds.length) return
    setSaving(true)
    const result = await api('create_campaign', trimName, [{ number: 1, characters: charIds }])
    setSaving(false)
    if (result?.ok && result.campaign) {
      setError(null)
      onCreated(result.campaign as Campaign)
      setName('')
      setCharIds([])
    } else {
      setError(result?.error || 'Failed to save campaign.')
    }
  }

  return (
    <div className="rounded-md border border-gold/20 bg-gold/3 p-4 space-y-3">
      <p className="text-xs font-heading text-gold/60 uppercase tracking-widest">New Campaign</p>
      <div className="space-y-1">
        <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Campaign name</Label>
        <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. The Lost Mines"
          className="h-8 text-sm bg-void/60 border-white/10 text-parchment placeholder:text-parchment/25"
          onKeyDown={e => { if (e.key === 'Enter') handleCreate() }} />
      </div>
      <div className="space-y-1">
        <Label className="text-parchment/40 text-[10px] font-heading uppercase tracking-widest">Season 1 — Adventurers</Label>
        <CharacterPicker selectedIds={charIds} onChange={setCharIds} allCharacters={allCharacters} onCharactersChanged={onCharactersChanged} />
      </div>
      {error && <p className="text-xs text-red-400/80 font-body">{error}</p>}
      <Button size="sm" onClick={handleCreate} disabled={saving || !name.trim() || charIds.length === 0} className="w-full gap-1.5">
        <Check className="w-3.5 h-3.5" />{saving ? 'Creating…' : 'Create Campaign'}
      </Button>
    </div>
  )
}

// ── Main tab ──────────────────────────────────────────────────────────────────

export function CampaignsTab() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [allCharacters, setAllCharacters] = useState<Character[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)

  useEffect(() => {
    async function load() {
      const [cs, chars] = await Promise.all([api('get_campaigns'), api('get_characters')])
      setCampaigns(cs ?? [])
      setAllCharacters(((chars ?? []) as Character[]).filter(c => !c.is_dm))
      setLoading(false)
    }
    load()
  }, [])

  function handleUpdated(updated: Campaign) {
    setCampaigns(prev => prev.map(c => c.id === updated.id ? updated : c))
  }

  function handleDeleted(id: string) {
    setCampaigns(prev => prev.filter(c => c.id !== id))
  }

  function handleCreated(campaign: Campaign) {
    setCampaigns(prev => [...prev, campaign])
    setShowCreate(false)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/8 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <Shield className="w-4 h-4 text-gold/50" />
          <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">Campaigns</h2>
        </div>
        <Button size="sm" variant="outline" onClick={() => setShowCreate(s => !s)} className="h-7 text-xs gap-1.5">
          {showCreate ? <X className="w-3 h-3" /> : <Plus className="w-3.5 h-3.5" />}
          {showCreate ? 'Cancel' : 'New Campaign'}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {showCreate && <CreateCampaignForm onCreated={handleCreated} allCharacters={allCharacters} onCharactersChanged={setAllCharacters} />}

        {loading && (
          <div className="flex items-center justify-center py-12">
            <p className="text-xs font-body text-parchment/30">Loading campaigns…</p>
          </div>
        )}

        {!loading && campaigns.length === 0 && !showCreate && (
          <div className="flex flex-col items-center justify-center py-12 gap-3 text-center">
            <Shield className="w-8 h-8 text-parchment/10" />
            <p className="text-sm font-heading text-parchment/30">No campaigns yet</p>
            <p className="text-xs font-body text-parchment/20">Create a campaign to begin your adventure</p>
            <Button size="sm" variant="outline" onClick={() => setShowCreate(true)} className="mt-2 gap-1.5">
              <Plus className="w-3.5 h-3.5" />New Campaign
            </Button>
          </div>
        )}

        {!loading && campaigns.map(campaign => (
          <CampaignCard key={campaign.id} campaign={campaign} allCharacters={allCharacters} onUpdated={handleUpdated} onDeleted={handleDeleted} onCharactersChanged={setAllCharacters} />
        ))}
      </div>
    </div>
  )
}
