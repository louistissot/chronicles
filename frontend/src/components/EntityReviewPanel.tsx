/**
 * EntityReviewPanel — card-based DM review for low-confidence entity extractions.
 * Shows proposed entity changes/creations with accept/edit/decline per card.
 */
import { useState, useEffect, useRef } from 'react'
import {
  Check, X, Pencil, ChevronDown, ChevronUp, Loader2,
  MapPin, Sword, ScrollText, Users, Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { EntityReviewPayload, EntityReviewCard } from '@/lib/api'

const ENTITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  location: MapPin,
  item: Sword,
  mission: ScrollText,
  npcs: Users,
  loot: Sparkles,
}

function confidenceColor(conf: number): string {
  if (conf < 70) return 'text-red-400'
  if (conf < 85) return 'text-amber-400'
  return 'text-yellow-400'
}

function confidenceBg(conf: number): string {
  if (conf < 70) return 'bg-red-400/10 border-red-400/25'
  if (conf < 85) return 'bg-amber-400/10 border-amber-400/25'
  return 'bg-yellow-400/10 border-yellow-400/25'
}

type Decision = 'accept' | 'edit' | 'decline' | null

interface CardState {
  decision: Decision
  editing: boolean
  editedData: Record<string, any>
}

export function EntityReviewPanel({
  payload,
  onSubmit,
}: {
  payload: EntityReviewPayload
  onSubmit: (stage: string, decisions: Array<{
    id: string
    action: 'accept' | 'edit' | 'decline'
    name?: string
    proposed?: Record<string, any>
    edited?: Record<string, any>
  }>) => void
}) {
  const [cardStates, setCardStates] = useState<Record<string, CardState>>(() => {
    const init: Record<string, CardState> = {}
    for (const card of payload.cards) {
      init[card.id] = { decision: null, editing: false, editedData: { ...card.proposed } }
    }
    return init
  })
  const [submitting, setSubmitting] = useState(false)
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({})

  const allDecided = payload.cards.every(c => cardStates[c.id]?.decision !== null)
  const autoSubmitRef = useRef(false)

  // Auto-submit when all cards have decisions
  useEffect(() => {
    if (allDecided && !submitting && !autoSubmitRef.current && payload.cards.length > 0) {
      autoSubmitRef.current = true
      handleSubmit()
    }
  }, [allDecided]) // eslint-disable-line react-hooks/exhaustive-deps

  function setDecision(cardId: string, decision: Decision) {
    setCardStates(prev => ({
      ...prev,
      [cardId]: { ...prev[cardId], decision, editing: decision === 'edit' },
    }))
  }

  function updateEditField(cardId: string, field: string, value: any) {
    setCardStates(prev => ({
      ...prev,
      [cardId]: {
        ...prev[cardId],
        editedData: { ...prev[cardId].editedData, [field]: value },
      },
    }))
  }

  function acceptAll() {
    setCardStates(prev => {
      const next = { ...prev }
      for (const card of payload.cards) {
        next[card.id] = { ...next[card.id], decision: 'accept', editing: false }
      }
      return next
    })
  }

  function declineAll() {
    setCardStates(prev => {
      const next = { ...prev }
      for (const card of payload.cards) {
        next[card.id] = { ...next[card.id], decision: 'decline', editing: false }
      }
      return next
    })
  }

  async function handleSubmit() {
    setSubmitting(true)
    const decisions = payload.cards.map(card => {
      const state = cardStates[card.id]
      return {
        id: card.id,
        action: state.decision || 'decline' as const,
        name: card.name,
        proposed: card.proposed,
        ...(state.decision === 'edit' ? { edited: state.editedData } : {}),
      }
    })
    await onSubmit(payload.stage, decisions)
    setSubmitting(false)
  }

  const Icon = ENTITY_ICONS[payload.stage] || ScrollText

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Icon className="w-5 h-5 text-gold/60" />
        <div className="flex-1">
          <h3 className="text-sm font-heading text-parchment/80 uppercase tracking-widest">
            Entity Review — {payload.stage}
          </h3>
          <p className="text-[10px] font-body text-parchment/40 mt-0.5">
            {payload.auto_applied.length > 0 && (
              <span className="text-emerald-400/70">
                {payload.auto_applied.length} auto-applied (high confidence)
              </span>
            )}
            {payload.auto_applied.length > 0 && payload.cards.length > 0 && ' · '}
            {payload.cards.length > 0 && (
              <span className="text-amber-400/70">
                {payload.cards.length} need{payload.cards.length === 1 ? 's' : ''} review
              </span>
            )}
          </p>
        </div>

        {/* Batch actions */}
        <button
          onClick={acceptAll}
          className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-heading text-emerald-400/70 border border-emerald-400/20 hover:bg-emerald-400/10 transition-colors"
        >
          <Check className="w-3 h-3" /> Accept All
        </button>
        <button
          onClick={declineAll}
          className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-heading text-red-400/70 border border-red-400/20 hover:bg-red-400/10 transition-colors"
        >
          <X className="w-3 h-3" /> Decline All
        </button>
      </div>

      {/* Auto-applied summary */}
      {payload.auto_applied.length > 0 && (
        <div className="rounded-md border border-emerald-400/15 bg-emerald-400/5 px-3 py-2">
          <button
            onClick={() => setExpandedCards(prev => ({ ...prev, __auto: !prev.__auto }))}
            className="flex items-center gap-2 w-full text-left"
          >
            <Check className="w-3 h-3 text-emerald-400/60" />
            <span className="text-[11px] font-body text-emerald-400/60 flex-1">
              {payload.auto_applied.length} entities auto-applied (confidence {'\u2265'} 95%)
            </span>
            {expandedCards.__auto
              ? <ChevronUp className="w-3 h-3 text-parchment/30" />
              : <ChevronDown className="w-3 h-3 text-parchment/30" />
            }
          </button>
          {expandedCards.__auto && (
            <div className="mt-2 space-y-1 pl-5">
              {payload.auto_applied.map((item, i) => (
                <p key={i} className="text-[10px] font-body text-parchment/40">
                  <span className="text-parchment/60">{item.name}</span>
                  <span className="text-parchment/25 mx-1">·</span>
                  <span className="text-emerald-400/50">{item.action}</span>
                  <span className="text-parchment/25 mx-1">·</span>
                  <span className="text-emerald-400/40">{item.confidence}%</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Review cards */}
      <div className="space-y-3">
        {payload.cards.map(card => {
          const state = cardStates[card.id]
          return (
            <ReviewCard
              key={card.id}
              card={card}
              state={state}
              onDecision={(d) => setDecision(card.id, d)}
              onEditField={(field, value) => updateEditField(card.id, field, value)}
              onConfirmEdit={() => {
                setCardStates(prev => ({
                  ...prev,
                  [card.id]: { ...prev[card.id], editing: false },
                }))
              }}
            />
          )
        })}
      </div>

      {/* Submit */}
      <div className="flex justify-end pt-2">
        <button
          onClick={handleSubmit}
          disabled={!allDecided || submitting}
          className={cn(
            'flex items-center gap-2 px-5 py-2 rounded-md text-sm font-heading uppercase tracking-widest transition-all',
            allDecided && !submitting
              ? 'bg-gold/20 text-gold border border-gold/30 hover:bg-gold/30'
              : 'bg-white/5 text-parchment/30 border border-white/10 cursor-not-allowed',
          )}
        >
          {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          {submitting ? 'Submitting...' : 'Submit Review'}
        </button>
      </div>
    </div>
  )
}

function ReviewCard({
  card,
  state,
  onDecision,
  onEditField,
  onConfirmEdit,
}: {
  card: EntityReviewCard
  state: CardState
  onDecision: (d: Decision) => void
  onEditField: (field: string, value: any) => void
  onConfirmEdit: () => void
}) {
  const hasDecision = state.decision !== null
  const isCollapsed = hasDecision && !state.editing

  return (
    <div className={cn(
      'rounded-md border transition-all duration-300',
      state.decision === 'accept' && 'border-emerald-400/25 bg-emerald-400/5',
      state.decision === 'decline' && 'border-red-400/20 bg-red-400/5 opacity-60',
      state.decision === 'edit' && 'border-gold/30 bg-gold/5',
      state.decision === null && 'border-white/10 bg-void/30',
      isCollapsed ? 'px-4 py-2' : 'px-4 py-3',
    )}>
      {/* Card header */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-heading text-parchment/80">{card.name}</span>
        <span className={cn(
          'text-[10px] font-body px-1.5 py-0.5 rounded border',
          card.action === 'create'
            ? 'text-blue-300/80 border-blue-400/20 bg-blue-400/5'
            : 'text-amber-300/80 border-amber-400/20 bg-amber-400/5'
        )}>
          {card.action}
        </span>
        <span className={cn('text-[10px] font-heading px-1.5 py-0.5 rounded border', confidenceBg(card.confidence))}>
          <span className={confidenceColor(card.confidence)}>{card.confidence}%</span>
        </span>
        {isCollapsed && (
          <span className="text-[9px] font-body ml-auto italic flex items-center gap-1">
            {state.decision === 'accept' && <><Check className="w-3 h-3 text-emerald-400" /><span className="text-emerald-400/60">Accepted</span></>}
            {state.decision === 'edit' && <><Pencil className="w-3 h-3 text-gold" /><span className="text-gold/60">Edited</span></>}
            {state.decision === 'decline' && <><X className="w-3 h-3 text-red-400" /><span className="text-red-400/60">Declined</span></>}
            <button
              onClick={() => onDecision(null)}
              className="text-parchment/25 hover:text-parchment/50 ml-1 transition-colors"
              title="Undo"
            >
              ↩
            </button>
          </span>
        )}
        {!isCollapsed && (
          <span className="text-[10px] font-body text-parchment/30 italic">{card.entity_type}</span>
        )}
      </div>

      {/* Collapsible body */}
      <div className={cn(
        'transition-all duration-300 overflow-hidden',
        isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[2000px] opacity-100 mt-2',
      )}>
        {/* Reasoning */}
        {card.reasoning && (
          <p className="text-[11px] font-body text-parchment/40 italic mb-2 leading-relaxed">
            {card.reasoning}
          </p>
        )}

        {/* Diff for updates */}
        {card.action === 'update' && card.diff && Object.keys(card.diff).length > 0 && (
          <div className="space-y-1.5 mb-3">
            {Object.entries(card.diff).map(([field, { old: oldVal, new: newVal }]) => (
              <div key={field} className="text-[11px] font-body">
                <span className="text-parchment/40 font-heading uppercase text-[9px] tracking-wider">{field}:</span>
                <div className="flex gap-2 mt-0.5">
                  <span className="text-red-400/50 line-through flex-1">{String(oldVal || '(empty)')}</span>
                  <span className="text-parchment/20">→</span>
                  <span className="text-emerald-400/60 flex-1">{String(newVal)}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Proposed data for creates */}
        {card.action === 'create' && !state.editing && (
          <div className="space-y-1 mb-3">
            {Object.entries(card.proposed)
              .filter(([k]) => !['confidence', 'reasoning'].includes(k))
              .map(([field, value]) => (
                <div key={field} className="text-[11px] font-body">
                  <span className="text-parchment/40 font-heading uppercase text-[9px] tracking-wider">{field}: </span>
                  <span className="text-parchment/60">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
          </div>
        )}

        {/* Edit mode */}
        {state.editing && (
          <div className="space-y-2 mb-3 rounded border border-gold/15 bg-gold/5 p-3">
            {Object.entries(state.editedData)
              .filter(([k]) => !['confidence', 'reasoning'].includes(k))
              .map(([field, value]) => (
                <div key={field}>
                  <label className="text-[9px] font-heading text-parchment/40 uppercase tracking-wider block mb-0.5">
                    {field}
                  </label>
                  {typeof value === 'string' && value.length > 80 ? (
                    <textarea
                      value={String(value)}
                      onChange={e => onEditField(field, e.target.value)}
                      className="w-full bg-void/60 border border-white/10 rounded px-2 py-1.5 text-[11px] text-parchment/60 outline-none focus:border-gold/40 resize-y min-h-[40px]"
                      rows={2}
                    />
                  ) : typeof value === 'boolean' ? (
                    <button
                      onClick={() => onEditField(field, !value)}
                      className={cn(
                        'px-2 py-0.5 rounded text-[10px] border',
                        value ? 'text-emerald-400/70 border-emerald-400/20 bg-emerald-400/5' : 'text-parchment/40 border-white/10 bg-void/40'
                      )}
                    >
                      {String(value)}
                    </button>
                  ) : typeof value === 'object' ? (
                    <textarea
                      value={JSON.stringify(value, null, 2)}
                      onChange={e => {
                        try { onEditField(field, JSON.parse(e.target.value)) } catch { /* invalid JSON, keep text */ }
                      }}
                      className="w-full bg-void/60 border border-white/10 rounded px-2 py-1.5 text-[11px] text-parchment/60 font-mono outline-none focus:border-gold/40 resize-y min-h-[40px]"
                      rows={2}
                    />
                  ) : (
                    <input
                      value={String(value ?? '')}
                      onChange={e => onEditField(field, e.target.value)}
                      className="w-full bg-void/60 border border-white/10 rounded px-2 py-1 text-[11px] text-parchment/60 outline-none focus:border-gold/40"
                    />
                  )}
                </div>
              ))}
            {/* Confirm Edit button */}
            <button
              onClick={onConfirmEdit}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-[10px] font-heading bg-gold/20 text-gold border border-gold/30 hover:bg-gold/30 transition-colors mt-2"
            >
              <Check className="w-3 h-3" /> Confirm Edit
            </button>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onDecision(state.decision === 'accept' ? null : 'accept')}
            className={cn(
              'flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-heading transition-colors',
              state.decision === 'accept'
                ? 'bg-emerald-400/20 text-emerald-400 border border-emerald-400/30'
                : 'text-emerald-400/60 border border-white/10 hover:border-emerald-400/20 hover:bg-emerald-400/5',
            )}
          >
            <Check className="w-3 h-3" /> Accept
          </button>
          <button
            onClick={() => onDecision(state.decision === 'edit' ? null : 'edit')}
            className={cn(
              'flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-heading transition-colors',
              state.decision === 'edit'
                ? 'bg-gold/20 text-gold border border-gold/30'
                : 'text-gold/60 border border-white/10 hover:border-gold/20 hover:bg-gold/5',
            )}
          >
            <Pencil className="w-3 h-3" /> Edit
          </button>
          <button
            onClick={() => onDecision(state.decision === 'decline' ? null : 'decline')}
            className={cn(
              'flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-heading transition-colors',
              state.decision === 'decline'
                ? 'bg-red-400/20 text-red-400 border border-red-400/30'
                : 'text-red-400/60 border border-white/10 hover:border-red-400/20 hover:bg-red-400/5',
            )}
          >
            <X className="w-3 h-3" /> Decline
          </button>
        </div>
      </div>
    </div>
  )
}
