import { useState, useEffect, useCallback } from 'react'
import { cn } from '@/lib/utils'

export type TitleChoice = 'start' | 'continue' | 'options'

const MENU: { id: TitleChoice; label: string }[] = [
  { id: 'start',    label: 'New Campaign' },
  { id: 'continue', label: 'Continue' },
  { id: 'options',  label: 'Options'  },
]

// ── Title screen ───────────────────────────────────────────────────────────
interface TitleScreenProps {
  onSelect: (choice: TitleChoice) => void
  theme?: 'dark' | 'light'
}

export function TitleScreen({ onSelect, theme = 'dark' }: TitleScreenProps) {
  const [cursor, setCursor]         = useState(0)
  const [visible, setVisible]       = useState(false)
  const [exiting, setExiting]       = useState(false)
  const [menuVisible, setMenuVisible] = useState(false)
  const light = theme === 'light'

  useEffect(() => {
    const t1 = setTimeout(() => setVisible(true), 80)
    const t2 = setTimeout(() => setMenuVisible(true), 1000)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [])

  const choose = useCallback((index: number) => {
    if (exiting) return
    setExiting(true)
    setTimeout(() => onSelect(MENU[index].id), 700)
  }, [exiting, onSelect])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (exiting) return
      if (e.key === 'ArrowUp'   || e.key === 'w') { e.preventDefault(); setCursor(c => (c - 1 + MENU.length) % MENU.length) }
      if (e.key === 'ArrowDown' || e.key === 's') { e.preventDefault(); setCursor(c => (c + 1) % MENU.length) }
      if (e.key === 'Enter'     || e.key === ' ') { e.preventDefault(); choose(cursor) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cursor, exiting, choose])

  const gold = light ? '#8B7228' : '#D4AF37'
  const goldGlow = light ? 'none' : '0 0 8px rgba(212,175,55,0.6), 0 0 22px rgba(212,175,55,0.3)'
  const goldFaint = light ? 'rgba(139,114,40,0.35)' : 'rgba(212,175,55,0.3)'
  const bgColor = light ? '#F5F0E1' : '#080B14'
  const subtitleColor = light ? 'rgba(139,114,40,0.50)' : 'rgba(212,175,55,0.40)'
  const hintColor = light ? 'rgba(139,114,40,0.30)' : 'rgba(212,175,55,0.18)'
  const copyrightColor = light ? 'rgba(139,114,40,0.20)' : 'rgba(212,175,55,0.12)'
  const sigil_bg = light ? '#EEE8D7' : '#08031A'
  const sigil_inner = light ? '#F5F0E1' : '#0E0728'
  const sigil_stroke_faint = light ? 'rgba(139,114,40,0.35)' : 'rgba(212,175,55,0.35)'
  const sigil_ring_stroke = light ? 'rgba(139,114,40,0.4)' : 'rgba(212,175,55,0.4)'
  const sigil_filter = light
    ? 'drop-shadow(0 0 8px rgba(139,114,40,0.25))'
    : 'drop-shadow(0 0 10px rgba(212,175,55,0.55)) drop-shadow(0 0 28px rgba(212,175,55,0.22))'

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex flex-col items-center justify-center transition-opacity duration-700 app-drag',
        visible && !exiting ? 'opacity-100' : 'opacity-0',
      )}
      style={{ backgroundColor: bgColor }}
    >
      {/* Subtle radial gradient for depth */}
      <div className="absolute inset-0" aria-hidden style={{
        background: light
          ? 'radial-gradient(ellipse at 50% 40%, rgba(212,175,55,0.06) 0%, transparent 70%)'
          : 'radial-gradient(ellipse at 50% 40%, rgba(212,175,55,0.04) 0%, transparent 70%)',
      }} />

      {/* UI content */}
      <div className="relative z-10 flex flex-col items-center">

        {/* D20 sigil */}
        <div className={cn(
          'mb-10 transition-all duration-1000',
          visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4',
        )}>
          <svg width="80" height="80" viewBox="0 0 44 44" fill="none"
            className="animate-glow-pulse"
            style={{ filter: sigil_filter }}>
            <circle cx="22" cy="22" r="21" fill={sigil_bg} stroke={sigil_ring_stroke} strokeWidth="1"/>
            <polygon points="22,4 37,13 37,31 22,40 7,31 7,13" fill={sigil_inner} stroke={gold} strokeWidth="1.5" strokeLinejoin="round"/>
            <line x1="22" y1="4"  x2="22" y2="22" stroke={sigil_stroke_faint} strokeWidth="0.8"/>
            <line x1="37" y1="13" x2="22" y2="22" stroke={sigil_stroke_faint} strokeWidth="0.8"/>
            <line x1="37" y1="31" x2="22" y2="22" stroke={sigil_stroke_faint} strokeWidth="0.8"/>
            <line x1="22" y1="40" x2="22" y2="22" stroke={sigil_stroke_faint} strokeWidth="0.8"/>
            <line x1="7"  y1="31" x2="22" y2="22" stroke={sigil_stroke_faint} strokeWidth="0.8"/>
            <line x1="7"  y1="13" x2="22" y2="22" stroke={sigil_stroke_faint} strokeWidth="0.8"/>
            <text x="22" y="27" textAnchor="middle" fill={gold} fontSize="12" fontFamily="Impact, serif" fontWeight="bold">20</text>
          </svg>
        </div>

        {/* Title */}
        <div className={cn(
          'text-center transition-all duration-1000 delay-200',
          visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6',
        )}>
          <h1 className="font-display" style={{
            fontSize: '28px',
            letterSpacing: '0.06em',
            color: gold,
            textShadow: goldGlow,
            lineHeight: 1,
          }}>
            Chronicles
          </h1>
          <p className="font-heading mt-4 uppercase" style={{
            fontSize: '10px',
            letterSpacing: '0.3em',
            color: subtitleColor,
          }}>
            D&D Unofficial LoreKeeper
          </p>
        </div>

        {/* Ornament */}
        <div className={cn(
          'flex items-center gap-3 my-12 w-64 transition-all duration-1000 delay-300',
          visible ? 'opacity-100' : 'opacity-0',
        )}>
          <div className="h-px flex-1" style={{ background: `linear-gradient(90deg, transparent, ${goldFaint})` }} />
          <span style={{ color: goldFaint, fontSize: '8px' }}>✦</span>
          <div className="h-px flex-1" style={{ background: `linear-gradient(90deg, ${goldFaint}, transparent)` }} />
        </div>

        {/* Menu items */}
        <div className={cn(
          'flex flex-col items-center gap-6 transition-all duration-700 app-no-drag',
          menuVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3',
        )}>
          {MENU.map((item, i) => {
            const isActive = cursor === i
            return (
              <button
                key={item.id}
                className="outline-none font-heading uppercase tracking-[0.25em] transition-all duration-200"
                onClick={() => { setCursor(i); choose(i) }}
                onMouseEnter={() => setCursor(i)}
                style={{
                  fontSize: '13px',
                  color: gold,
                  opacity: isActive ? 1 : 0.3,
                  textShadow: isActive ? goldGlow : 'none',
                  borderBottom: isActive ? `1.5px solid ${goldFaint}` : '1.5px solid transparent',
                  paddingBottom: '4px',
                }}
              >
                {item.label}
              </button>
            )
          })}
        </div>

        {/* Keyboard hint */}
        <p className={cn(
          'font-heading uppercase mt-14 transition-all duration-700 delay-300',
          menuVisible ? 'opacity-100' : 'opacity-0',
        )} style={{ fontSize: '8px', color: hintColor, letterSpacing: '0.2em' }}>
          ↑ ↓ Navigate &nbsp;&nbsp; Enter Select
        </p>
      </div>

      {/* Bottom copyright */}
      <p className="font-heading absolute bottom-5 z-10 uppercase"
        style={{ fontSize: '8px', color: copyrightColor, letterSpacing: '0.15em' }}>
        © 2025 Chronicles
      </p>
    </div>
  )
}
