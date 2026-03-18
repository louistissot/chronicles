import { useState, useEffect } from 'react'
import {
  BookOpen, Plus, Save, Search, X, RefreshCw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import type { GlossaryEntry } from '@/lib/api'

const GLOSSARY_CATEGORIES = ['Faction', 'Item', 'Spell', 'Other']

type SortOrder = 'name-asc' | 'name-desc' | 'category'

export function GlossaryTab({ campaignId, campaignName }: { campaignId: string | null; campaignName: string }) {
  const [glossary, setGlossary] = useState<Record<string, GlossaryEntry>>({})
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [newTerm, setNewTerm] = useState('')
  const [activeCategory, setActiveCategory] = useState<string>('All')
  const [search, setSearch] = useState('')
  const [expandedDesc, setExpandedDesc] = useState<Record<string, boolean>>({})
  const [sortOrder, setSortOrder] = useState<SortOrder>('name-asc')
  const [rebuilding, setRebuilding] = useState(false)

  useEffect(() => {
    if (!campaignId) return
    setLoaded(false)
    async function load() {
      const data = await api('get_campaign_glossary', campaignId!)
      setGlossary(data ?? {})
      setLoaded(true)
      setDirty(false)
    }
    load()
  }, [campaignId])

  async function handleSave() {
    if (!campaignId) return
    setSaving(true)
    await api('update_campaign_glossary', campaignId, glossary)
    setSaving(false)
    setDirty(false)
  }

  async function handleRebuild() {
    if (!campaignId) return
    setRebuilding(true)
    const result = await api('rebuild_campaign_glossary', campaignId) as { ok: boolean; terms?: number; npcs_created?: number; error?: string } | null
    if (result?.ok) {
      const data = await api('get_campaign_glossary', campaignId)
      setGlossary(data ?? {})
      setDirty(false)
    }
    setRebuilding(false)
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

  if (!campaignId) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-center px-6">
        <BookOpen className="w-10 h-10 text-parchment/10" />
        <p className="text-sm font-heading text-parchment/30">No campaign selected</p>
        <p className="text-xs font-body text-parchment/20">Select a campaign from the dropdown to view its glossary</p>
      </div>
    )
  }

  const termCount = Object.keys(glossary).length

  // Category counts
  const categoryCounts: Record<string, number> = { All: termCount }
  for (const entry of Object.values(glossary)) {
    const cat = entry.category || 'Other'
    categoryCounts[cat] = (categoryCounts[cat] || 0) + 1
  }

  // Filter + sort
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
    .sort((a, b) => {
      if (sortOrder === 'name-asc') return a.localeCompare(b)
      if (sortOrder === 'name-desc') return b.localeCompare(a)
      // category sort
      const catA = glossary[a].category || 'Other'
      const catB = glossary[b].category || 'Other'
      if (catA !== catB) return catA.localeCompare(catB)
      return a.localeCompare(b)
    })

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-none px-5 py-3 border-b border-white/8 flex items-center gap-3">
        <BookOpen className="w-4 h-4 text-gold/50" />
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">Glossary</h2>
          <p className="text-[10px] font-body text-parchment/30 truncate mt-0.5">
            {campaignName} · {termCount} term{termCount !== 1 ? 's' : ''}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={handleRebuild} disabled={rebuilding} className="h-7 text-[10px] px-3 gap-1.5">
          <RefreshCw className={cn('w-3 h-3', rebuilding && 'animate-spin')} />{rebuilding ? 'Rebuilding…' : 'Rebuild from Sessions'}
        </Button>
        {dirty && (
          <Button size="sm" onClick={handleSave} disabled={saving} className="h-7 text-[10px] px-3 gap-1.5">
            <Save className="w-3 h-3" />{saving ? 'Saving…' : 'Save Changes'}
          </Button>
        )}
      </div>

      {/* Filters bar */}
      <div className="flex-none px-5 py-3 space-y-2 border-b border-white/5">
        {/* Category pills */}
        <div className="flex flex-wrap gap-1.5">
          {['All', ...GLOSSARY_CATEGORIES].map(cat => {
            const count = categoryCounts[cat] || 0
            const isActive = activeCategory === cat
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
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

        {/* Search + sort + add */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-parchment/25" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search terms…"
              className="w-full h-7 bg-void/60 border border-white/8 rounded pl-7 pr-2 text-[11px] text-parchment/60 outline-none focus:border-gold/40 placeholder:text-parchment/20"
            />
          </div>
          <select
            value={sortOrder}
            onChange={e => setSortOrder(e.target.value as SortOrder)}
            className="h-7 bg-void/60 border border-white/8 rounded px-2 text-[10px] text-parchment/50 outline-none focus:border-gold/40"
            style={{ colorScheme: 'dark' }}
          >
            <option value="name-asc">Name A→Z</option>
            <option value="name-desc">Name Z→A</option>
            <option value="category">Category</option>
          </select>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-3">
        {!loaded && (
          <div className="flex items-center justify-center py-16">
            <p className="text-xs font-body text-parchment/30">Loading glossary…</p>
          </div>
        )}

        {loaded && termCount === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <BookOpen className="w-10 h-10 text-parchment/10" />
            <p className="text-sm font-heading text-parchment/30">No glossary terms yet</p>
            <p className="text-xs font-body text-parchment/20">
              Process a session to auto-populate, or add terms manually below.
            </p>
          </div>
        )}

        {loaded && filteredTerms.length === 0 && termCount > 0 && (
          <p className="text-xs text-parchment/25 font-body italic py-4 text-center">No terms match this filter.</p>
        )}

        {loaded && filteredTerms.length > 0 && (
          <div className="space-y-2">
            {filteredTerms.map(term => {
              const entry = glossary[term]
              const hasDesc = !!entry.description
              const isDescExpanded = expandedDesc[term]
              return (
                <div key={term} className="rounded-md border border-white/6 bg-void/30 px-3 py-2 group hover:border-white/10 transition-colors">
                  {/* Row 1: name, category, delete */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-body text-parchment/80 font-semibold truncate flex-1" title={term}>
                      {term}
                    </span>
                    <select
                      value={entry.category}
                      onChange={e => updateEntry(term, 'category', e.target.value)}
                      className="h-5 bg-void/60 border border-white/8 rounded px-1.5 text-[9px] text-parchment/50 outline-none focus:border-gold/40 flex-shrink-0"
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
                    className="w-full mt-1.5 h-6 bg-void/40 border border-white/5 rounded px-2 text-[11px] text-parchment/60 outline-none focus:border-gold/40 placeholder:text-parchment/20"
                    placeholder="Definition (brief factual summary)…"
                  />
                  {/* Row 3: description (expandable) */}
                  <button
                    onClick={() => setExpandedDesc(prev => ({ ...prev, [term]: !prev[term] }))}
                    className="mt-1.5 text-[9px] text-parchment/30 hover:text-parchment/50 transition-colors"
                  >
                    {isDescExpanded ? '▾ Hide description' : hasDesc ? '▸ Show description' : '▸ Add description'}
                  </button>
                  {isDescExpanded && (
                    <textarea
                      value={entry.description || ''}
                      onChange={e => updateEntry(term, 'description', e.target.value)}
                      className="w-full mt-1 bg-void/40 border border-white/5 rounded px-2 py-1.5 text-[11px] text-parchment/50 outline-none focus:border-gold/40 placeholder:text-parchment/20 resize-y min-h-[40px]"
                      rows={3}
                      placeholder="Richer description (context, relationships, events)…"
                    />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Bottom bar: add term */}
      {loaded && (
        <div className="flex-none px-5 py-3 border-t border-white/8 flex items-center gap-2">
          <input
            value={newTerm}
            onChange={e => setNewTerm(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') addTerm() }}
            placeholder="Add new term…"
            className="flex-1 h-7 bg-void/60 border border-white/8 rounded px-3 text-[11px] text-parchment/50 outline-none focus:border-gold/40 placeholder:text-parchment/20"
          />
          <Button size="sm" variant="outline" onClick={addTerm} disabled={!newTerm.trim()} className="h-7 text-[10px] px-3 gap-1">
            <Plus className="w-3 h-3" />Add
          </Button>
        </div>
      )}
    </div>
  )
}
