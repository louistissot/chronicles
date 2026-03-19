/**
 * TerrainPatterns — SVG terrain pattern definitions and terrain overlay layer
 * for the campaign map. Each region_type gets a hand-drawn-style tileable pattern.
 */
import { memo } from 'react'
import { useViewport } from '@xyflow/react'
import type { MapNode } from '@/lib/api'

// ── Pattern IDs ─────────────────────────────────────────────────────────────

const PATTERN_PREFIX = 'terrain-'

export const TERRAIN_PATTERN_IDS: Record<string, string> = {
  sea: `${PATTERN_PREFIX}sea`,
  coast: `${PATTERN_PREFIX}coast`,
  plains: `${PATTERN_PREFIX}plains`,
  forest: `${PATTERN_PREFIX}forest`,
  jungle: `${PATTERN_PREFIX}jungle`,
  mountains: `${PATTERN_PREFIX}mountains`,
  desert: `${PATTERN_PREFIX}desert`,
  swamp: `${PATTERN_PREFIX}swamp`,
  underground: `${PATTERN_PREFIX}underground`,
  urban: `${PATTERN_PREFIX}urban`,
  ruins: `${PATTERN_PREFIX}ruins`,
  arctic: `${PATTERN_PREFIX}arctic`,
}

// ── Terrain radii per region type (node-space units) ────────────────────────

const TERRAIN_RADIUS: Record<string, number> = {
  sea: 220,
  coast: 180,
  plains: 160,
  forest: 170,
  jungle: 170,
  mountains: 190,
  desert: 200,
  swamp: 160,
  underground: 150,
  urban: 140,
  ruins: 150,
  arctic: 190,
}

// ── SVG Pattern Definitions ─────────────────────────────────────────────────

export const TerrainDefs = memo(function TerrainDefs() {
  return (
    <defs>
      {/* Radial fade mask */}
      <radialGradient id="terrain-fade">
        <stop offset="0%" stopColor="white" stopOpacity="0.7" />
        <stop offset="50%" stopColor="white" stopOpacity="0.45" />
        <stop offset="80%" stopColor="white" stopOpacity="0.15" />
        <stop offset="100%" stopColor="white" stopOpacity="0" />
      </radialGradient>

      {/* SEA — horizontal wavy lines */}
      <pattern id={TERRAIN_PATTERN_IDS.sea} patternUnits="userSpaceOnUse" width="60" height="30">
        <path d="M0,10 Q15,4 30,10 Q45,16 60,10" fill="none" stroke="rgba(96,165,250,0.18)" strokeWidth="1.5" />
        <path d="M0,22 Q15,16 30,22 Q45,28 60,22" fill="none" stroke="rgba(96,165,250,0.12)" strokeWidth="1" />
      </pattern>

      {/* COAST — sand dots + thin wave */}
      <pattern id={TERRAIN_PATTERN_IDS.coast} patternUnits="userSpaceOnUse" width="50" height="40">
        <circle cx="8" cy="12" r="1" fill="rgba(234,179,8,0.12)" />
        <circle cx="25" cy="8" r="0.8" fill="rgba(234,179,8,0.10)" />
        <circle cx="40" cy="15" r="1.2" fill="rgba(234,179,8,0.11)" />
        <circle cx="15" cy="28" r="0.7" fill="rgba(234,179,8,0.09)" />
        <circle cx="35" cy="32" r="1" fill="rgba(234,179,8,0.10)" />
        <path d="M0,35 Q12,31 25,35 Q38,39 50,35" fill="none" stroke="rgba(96,165,250,0.10)" strokeWidth="0.8" />
      </pattern>

      {/* PLAINS — sparse grass strokes */}
      <pattern id={TERRAIN_PATTERN_IDS.plains} patternUnits="userSpaceOnUse" width="50" height="50">
        <path d="M10,40 Q11,32 12,28" fill="none" stroke="rgba(212,175,55,0.08)" strokeWidth="1" strokeLinecap="round" />
        <path d="M13,40 Q13,34 11,30" fill="none" stroke="rgba(212,175,55,0.06)" strokeWidth="0.8" strokeLinecap="round" />
        <path d="M35,42 Q36,35 37,30" fill="none" stroke="rgba(212,175,55,0.07)" strokeWidth="1" strokeLinecap="round" />
        <path d="M38,42 Q37,36 36,32" fill="none" stroke="rgba(212,175,55,0.06)" strokeWidth="0.8" strokeLinecap="round" />
        <path d="M22,18 Q23,12 24,8" fill="none" stroke="rgba(212,175,55,0.06)" strokeWidth="0.8" strokeLinecap="round" />
      </pattern>

      {/* FOREST — small evergreen tree silhouettes */}
      <pattern id={TERRAIN_PATTERN_IDS.forest} patternUnits="userSpaceOnUse" width="50" height="50">
        {/* Tree 1 */}
        <path d="M15,38 L12,30 L15,32 L10,22 L15,25 L13,16 L17,16 L15,25 L20,22 L15,32 L18,30 Z" fill="rgba(34,197,94,0.10)" />
        <line x1="15" y1="38" x2="15" y2="42" stroke="rgba(120,80,40,0.12)" strokeWidth="1.5" />
        {/* Tree 2 */}
        <path d="M38,36 L36,30 L38,31 L34,24 L38,26 L37,20 L39,20 L38,26 L42,24 L38,31 L40,30 Z" fill="rgba(34,197,94,0.08)" />
        <line x1="38" y1="36" x2="38" y2="39" stroke="rgba(120,80,40,0.10)" strokeWidth="1" />
        {/* Small bush */}
        <circle cx="28" cy="44" r="3" fill="rgba(34,197,94,0.06)" />
      </pattern>

      {/* JUNGLE — dense leaf/fern shapes */}
      <pattern id={TERRAIN_PATTERN_IDS.jungle} patternUnits="userSpaceOnUse" width="45" height="45">
        <path d="M10,35 L8,25 L12,28 L7,18 L13,22 L11,12 L15,12 L13,22 L18,18 L13,28 L17,25 Z" fill="rgba(22,163,74,0.12)" />
        <path d="M30,40 L28,32 L32,34 L27,26 L33,30 L31,22 L34,22 L33,30 L37,26 L33,34 L36,32 Z" fill="rgba(22,163,74,0.10)" />
        <path d="M20,20 Q25,15 22,10" fill="none" stroke="rgba(22,163,74,0.10)" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="38" cy="12" r="4" fill="rgba(22,163,74,0.06)" />
        <circle cx="5" cy="40" r="3" fill="rgba(22,163,74,0.07)" />
      </pattern>

      {/* MOUNTAINS — triangle peaks */}
      <pattern id={TERRAIN_PATTERN_IDS.mountains} patternUnits="userSpaceOnUse" width="60" height="50">
        <path d="M15,40 L22,15 L29,40 Z" fill="none" stroke="rgba(148,163,184,0.12)" strokeWidth="1.2" />
        <path d="M22,15 L25,22 L19,22 Z" fill="rgba(186,230,253,0.06)" />
        <path d="M35,40 L42,20 L49,40 Z" fill="none" stroke="rgba(148,163,184,0.10)" strokeWidth="1" />
        <path d="M42,20 L44,26 L40,26 Z" fill="rgba(186,230,253,0.05)" />
        <path d="M5,42 L10,28 L15,42" fill="none" stroke="rgba(148,163,184,0.07)" strokeWidth="0.8" />
      </pattern>

      {/* DESERT — stippled dots + dune curves */}
      <pattern id={TERRAIN_PATTERN_IDS.desert} patternUnits="userSpaceOnUse" width="55" height="45">
        <path d="M0,35 Q14,28 27,35 Q41,42 55,35" fill="none" stroke="rgba(234,179,8,0.10)" strokeWidth="1" />
        <path d="M5,20 Q16,14 27,20 Q38,26 50,20" fill="none" stroke="rgba(234,179,8,0.07)" strokeWidth="0.8" />
        <circle cx="10" cy="10" r="0.8" fill="rgba(234,179,8,0.10)" />
        <circle cx="30" cy="14" r="0.6" fill="rgba(234,179,8,0.08)" />
        <circle cx="45" cy="8" r="0.7" fill="rgba(234,179,8,0.09)" />
        <circle cx="20" cy="30" r="0.9" fill="rgba(234,179,8,0.08)" />
        <circle cx="42" cy="28" r="0.7" fill="rgba(234,179,8,0.07)" />
      </pattern>

      {/* SWAMP — wavy lines + reed shapes */}
      <pattern id={TERRAIN_PATTERN_IDS.swamp} patternUnits="userSpaceOnUse" width="50" height="50">
        <path d="M0,40 Q12,36 25,40 Q38,44 50,40" fill="none" stroke="rgba(101,163,13,0.10)" strokeWidth="1" />
        <path d="M0,30 Q12,26 25,30 Q38,34 50,30" fill="none" stroke="rgba(101,163,13,0.07)" strokeWidth="0.8" />
        {/* Reeds */}
        <line x1="12" y1="45" x2="11" y2="20" stroke="rgba(101,163,13,0.10)" strokeWidth="0.8" />
        <line x1="14" y1="45" x2="15" y2="22" stroke="rgba(101,163,13,0.08)" strokeWidth="0.6" />
        <circle cx="11" cy="19" r="1.5" fill="rgba(101,163,13,0.06)" />
        <line x1="38" y1="44" x2="37" y2="25" stroke="rgba(101,163,13,0.09)" strokeWidth="0.7" />
        <circle cx="37" cy="24" r="1.2" fill="rgba(101,163,13,0.05)" />
      </pattern>

      {/* UNDERGROUND — crystal/stalactite shapes + rock dots */}
      <pattern id={TERRAIN_PATTERN_IDS.underground} patternUnits="userSpaceOnUse" width="50" height="50">
        {/* Stalactites */}
        <path d="M15,0 L13,12 L15,10 L17,12 Z" fill="rgba(148,130,200,0.10)" />
        <path d="M35,0 L34,8 L35,7 L36,8 Z" fill="rgba(148,130,200,0.08)" />
        {/* Crystals */}
        <path d="M25,30 L23,22 L25,20 L27,22 Z" fill="rgba(168,130,255,0.08)" />
        <path d="M40,35 L39,30 L40,29 L41,30 Z" fill="rgba(168,130,255,0.06)" />
        {/* Rock dots */}
        <circle cx="8" cy="35" r="1.2" fill="rgba(100,100,130,0.10)" />
        <circle cx="45" cy="20" r="0.9" fill="rgba(100,100,130,0.08)" />
        <circle cx="20" cy="45" r="1" fill="rgba(100,100,130,0.07)" />
      </pattern>

      {/* URBAN — cobblestone grid */}
      <pattern id={TERRAIN_PATTERN_IDS.urban} patternUnits="userSpaceOnUse" width="40" height="40">
        <rect x="2" y="2" width="16" height="16" fill="none" stroke="rgba(212,175,55,0.06)" strokeWidth="0.6" rx="1" />
        <rect x="22" y="2" width="16" height="16" fill="none" stroke="rgba(212,175,55,0.05)" strokeWidth="0.6" rx="1" />
        <rect x="12" y="22" width="16" height="16" fill="none" stroke="rgba(212,175,55,0.06)" strokeWidth="0.6" rx="1" />
        <rect x="32" y="22" width="8" height="16" fill="none" stroke="rgba(212,175,55,0.04)" strokeWidth="0.5" rx="1" />
        <rect x="0" y="22" width="8" height="16" fill="none" stroke="rgba(212,175,55,0.04)" strokeWidth="0.5" rx="1" />
      </pattern>

      {/* RUINS — broken grid + crack marks */}
      <pattern id={TERRAIN_PATTERN_IDS.ruins} patternUnits="userSpaceOnUse" width="50" height="50">
        <rect x="5" y="5" width="15" height="12" fill="none" stroke="rgba(148,163,184,0.08)" strokeWidth="0.6" strokeDasharray="3 2" />
        <rect x="30" y="8" width="12" height="15" fill="none" stroke="rgba(148,163,184,0.06)" strokeWidth="0.5" strokeDasharray="4 3" />
        {/* Cracks */}
        <path d="M25,0 L27,15 L24,20 L28,30" fill="none" stroke="rgba(148,163,184,0.07)" strokeWidth="0.5" />
        <path d="M10,30 L15,35 L12,45" fill="none" stroke="rgba(148,163,184,0.06)" strokeWidth="0.4" />
        <circle cx="35" cy="40" r="2" fill="rgba(148,163,184,0.04)" />
      </pattern>

      {/* ARCTIC — snowflake dots + crystalline shapes */}
      <pattern id={TERRAIN_PATTERN_IDS.arctic} patternUnits="userSpaceOnUse" width="50" height="50">
        {/* Snowflakes (simple 6-arm stars) */}
        <g transform="translate(15,15)" stroke="rgba(186,230,253,0.12)" strokeWidth="0.6" fill="none">
          <line x1="0" y1="-4" x2="0" y2="4" />
          <line x1="-3.5" y1="-2" x2="3.5" y2="2" />
          <line x1="-3.5" y1="2" x2="3.5" y2="-2" />
        </g>
        <g transform="translate(40,38)" stroke="rgba(186,230,253,0.09)" strokeWidth="0.5" fill="none">
          <line x1="0" y1="-3" x2="0" y2="3" />
          <line x1="-2.6" y1="-1.5" x2="2.6" y2="1.5" />
          <line x1="-2.6" y1="1.5" x2="2.6" y2="-1.5" />
        </g>
        {/* Ice dots */}
        <circle cx="35" cy="12" r="1" fill="rgba(186,230,253,0.08)" />
        <circle cx="8" cy="40" r="0.8" fill="rgba(186,230,253,0.07)" />
        <circle cx="28" cy="45" r="1.2" fill="rgba(186,230,253,0.06)" />
      </pattern>
    </defs>
  )
})

// ── Terrain Layer ───────────────────────────────────────────────────────────

interface TerrainLayerProps {
  nodes: MapNode[]
}

export const TerrainLayer = memo(function TerrainLayer({ nodes }: TerrainLayerProps) {
  const { x, y, zoom } = useViewport()

  if (!nodes.length) return null

  return (
    <svg
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    >
      <TerrainDefs />
      <g transform={`translate(${x}, ${y}) scale(${zoom})`}>
        {nodes.map(node => {
          const patternId = TERRAIN_PATTERN_IDS[node.region_type] || TERRAIN_PATTERN_IDS.plains
          const radius = TERRAIN_RADIUS[node.region_type] || 160
          // Offset by half the node width (20px / zoom) to center on the node icon
          const cx = node.x + 20 / zoom
          const cy = node.y + 20 / zoom
          return (
            <g key={node.name}>
              {/* Pattern-filled circle */}
              <circle
                cx={cx}
                cy={cy}
                r={radius}
                fill={`url(#${patternId})`}
                opacity="0.8"
              />
              {/* Radial fade mask overlay — dark edges blend into background */}
              <circle
                cx={cx}
                cy={cy}
                r={radius}
                fill="url(#terrain-fade)"
                style={{ mixBlendMode: 'multiply' }}
              />
            </g>
          )
        })}
      </g>
    </svg>
  )
})
