/**
 * HorizontalTimeline — shared timeline component used by SessionDetailScreen and ChronicleTab.
 * Displays a scrollable rail of event nodes with a detail card below.
 */
import { useState, useRef } from 'react'
import type { TimelineEvent } from '@/lib/api'
import {
  Swords, Search, MessageCircle, Compass, Sparkles, Moon, Skull,
  Gem, Puzzle, UserCheck, Crown, Eye, Flame, ShieldAlert, Trophy, Star,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Fantasy Timeline Icons ────────────────────────────────────────────────────

export const TIMELINE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  combat: Swords,
  discovery: Search,
  dialogue: MessageCircle,
  travel: Compass,
  magic: Sparkles,
  rest: Moon,
  death: Skull,
  treasure: Gem,
  puzzle: Puzzle,
  npc: UserCheck,
  boss: Crown,
  stealth: Eye,
  ritual: Flame,
  betrayal: ShieldAlert,
  victory: Trophy,
}

export function inferEventType(event: TimelineEvent): string | undefined {
  if (event.type) return event.type
  const text = `${event.title} ${event.summary}`.toLowerCase()
  if (/\b(fight|combat|attack|battle|ambush|clash|slay|kill|struck|swing|arrow|sword|weapon)\b/.test(text)) return 'combat'
  if (/\b(boss|villain|dragon|demon lord|final boss|lich|necromancer)\b/.test(text)) return 'boss'
  if (/\b(discover|find|reveal|uncover|learn|secret|hidden|clue)\b/.test(text)) return 'discovery'
  if (/\b(talk|speak|conversation|negotiat|persuad|diplomac|ask|told|said|plea)\b/.test(text)) return 'dialogue'
  if (/\b(travel|journey|arrive|depart|cross|enter|leave|march|ride|set out|head|path)\b/.test(text)) return 'travel'
  if (/\b(spell|magic|enchant|arcane|mystic|conjur|summon|cast|portal|teleport)\b/.test(text)) return 'magic'
  if (/\b(rest|camp|sleep|heal|recover|downtime|inn|tavern)\b/.test(text)) return 'rest'
  if (/\b(death|die|dead|fell|resurrect|perish|slain|corpse)\b/.test(text)) return 'death'
  if (/\b(treasure|loot|gold|reward|chest|gem|artifact|coin|potion|scroll)\b/.test(text)) return 'treasure'
  if (/\b(puzzle|riddle|trap|enigma|cipher|mechanism|lock|solve)\b/.test(text)) return 'puzzle'
  if (/\b(meet|npc|stranger|merchant|villager|introduc|encounter|greet)\b/.test(text)) return 'npc'
  if (/\b(sneak|stealth|infiltrat|spy|shadow|hide|creep|scout)\b/.test(text)) return 'stealth'
  if (/\b(ritual|ceremony|pact|oath|transform|rite|blessing|curse)\b/.test(text)) return 'ritual'
  if (/\b(betray|decei|trick|traitor|twist|doublecross|lie|false)\b/.test(text)) return 'betrayal'
  if (/\b(victory|triumph|succeed|win|complet|celebrat|safe|escap)\b/.test(text)) return 'victory'
  return undefined
}

export function TimelineIcon({ type, event, className }: { type?: string; event?: TimelineEvent; className?: string }) {
  const resolvedType = type || (event ? inferEventType(event) : undefined)
  const Icon = (resolvedType && TIMELINE_ICONS[resolvedType]) || Star
  return <Icon className={className || 'w-5 h-5'} />
}

export function importanceColor(imp: string) {
  if (imp === 'high') return 'text-gold'
  if (imp === 'medium') return 'text-blue-400'
  return 'text-parchment/40'
}

// ── Horizontal Timeline ────────────────────────────────────────────────────────

export function HorizontalTimeline({ events }: { events: TimelineEvent[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const [pinnedIndex, setPinnedIndex] = useState<number | null>(null)
  const railRef = useRef<HTMLDivElement>(null)

  const activeIndex = pinnedIndex ?? hoveredIndex

  return (
    <div className="space-y-4">
      {/* Scrollable rail */}
      <div ref={railRef} className="overflow-x-auto pb-2 scrollbar-none">
        <div className="flex items-start gap-0 min-w-max px-4">
          {events.map((event, i) => {
            const color = importanceColor(event.importance)
            const isActive = activeIndex === i
            return (
              <div
                key={i}
                className="flex flex-col items-center cursor-pointer group"
                style={{ minWidth: '90px', maxWidth: '130px' }}
                onMouseEnter={() => { if (pinnedIndex === null) setHoveredIndex(i) }}
                onMouseLeave={() => { if (pinnedIndex === null) setHoveredIndex(null) }}
                onClick={() => setPinnedIndex(pinnedIndex === i ? null : i)}
              >
                {/* Icon + connector line */}
                <div className="flex items-center w-full">
                  {i > 0 && <div className="flex-1 h-[2px] bg-gradient-to-r from-gold/10 via-gold/30 to-gold/10" />}
                  {i === 0 && <div className="flex-1" />}
                  <div className={cn(
                    'flex-none w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 bg-shadow border',
                    isActive
                      ? 'scale-125 border-gold/40 shadow-[0_0_12px_rgba(212,175,55,0.3)]'
                      : 'border-white/10 group-hover:scale-110 group-hover:border-gold/25',
                    color,
                  )}>
                    <TimelineIcon type={event.type} event={event} className={cn('w-4 h-4 transition-all duration-200', isActive && 'w-[18px] h-[18px]')} />
                  </div>
                  {i < events.length - 1 && <div className="flex-1 h-[2px] bg-gradient-to-r from-gold/10 via-gold/30 to-gold/10" />}
                  {i === events.length - 1 && <div className="flex-1" />}
                </div>
                {/* Label */}
                <div className="mt-2 px-1 text-center">
                  {event.time && (
                    <p className="text-[10px] font-mono text-parchment/25 leading-tight">{event.time}</p>
                  )}
                  <p className={cn(
                    'text-xs font-body leading-tight mt-0.5 transition-colors',
                    isActive ? 'text-parchment/80' : 'text-parchment/40',
                  )}>
                    {event.title.length > 25 ? event.title.slice(0, 23) + '…' : event.title}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Detail card for hovered/pinned event */}
      {activeIndex !== null && activeIndex < events.length && (() => {
        const event = events[activeIndex]
        return (
          <div className="rounded-md border border-white/8 bg-white/3 px-5 py-4 animate-in fade-in duration-200">
            <div className="flex items-center gap-2 mb-2">
              <span className={cn('w-5 h-5', importanceColor(event.importance))}>
                <TimelineIcon type={event.type} event={event} className="w-5 h-5" />
              </span>
              {event.time && (
                <span className="text-xs font-mono text-parchment/30">{event.time}</span>
              )}
              <span className={cn('text-[10px] font-body px-1.5 py-0.5 rounded border', {
                'text-gold/80 border-gold/25 bg-gold/5': event.importance === 'high',
                'text-blue-300/80 border-blue-400/20 bg-blue-400/5': event.importance === 'medium',
                'text-parchment/35 border-white/10 bg-white/3': event.importance === 'low',
              })}>
                {event.importance}
              </span>
              {event.type && (
                <span className="text-[10px] font-body text-parchment/25 italic">{event.type}</span>
              )}
            </div>
            <h4 className="text-sm font-heading text-parchment/90 leading-snug">{event.title}</h4>
            <p className="text-sm text-parchment/55 font-body leading-relaxed mt-1 italic">{event.summary}</p>
            {event.details && (
              <p className="text-sm text-parchment/65 font-body leading-relaxed mt-2">{event.details}</p>
            )}
          </div>
        )
      })()}

    </div>
  )
}
