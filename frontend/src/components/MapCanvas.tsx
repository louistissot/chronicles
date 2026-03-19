/**
 * MapCanvas — lazy-loaded React Flow canvas for the Maps tab.
 * Separated to avoid crashing the app if React Flow fails to load in pywebview.
 *
 * Features:
 * - Terrain region illustrations (SVG patterns per region_type)
 * - Compass rose with drag-to-rotate map rotation
 * - Edit mode toggle (nodes locked by default, draggable in edit mode)
 */
import { memo, useCallback, useRef, useState } from 'react'
import {
  ReactFlow, ReactFlowProvider, Background, Controls, MiniMap, Panel,
  type Node, type Edge, type NodeProps, type OnNodeDrag,
  Handle, Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  MapPin, Pencil,
  Castle, Home, Beer, Church, Ship, Anchor, Wheat, Tent,
  Mountain, Landmark, Shield, TreePine, Signpost, Crown, Store,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import type { CampaignMap, CampaignLocation } from '@/lib/api'
import CompassRose from './CompassRose'
import { TerrainLayer } from './TerrainPatterns'

// ── Icon mapping for location_type ──────────────────────────────────────────

const LOCATION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  city: Castle, town: Home, village: Home, inn: Beer,
  temple: Church, shrine: Church, ship: Ship, dock: Anchor,
  farm: Wheat, camp: Tent, cave: Mountain, dungeon: Mountain,
  ruins: Landmark, fortress: Shield, tower: Shield,
  clearing: TreePine, bridge: Signpost, crossroads: Signpost,
  manor: Crown, market: Store, shop: Store, other: MapPin,
}

// ── Region colors ───────────────────────────────────────────────────────────

const REGION_COLORS: Record<string, string> = {
  sea: 'rgba(59, 130, 246, 0.15)',
  coast: 'rgba(59, 130, 246, 0.08)',
  plains: 'rgba(212, 175, 55, 0.06)',
  forest: 'rgba(34, 197, 94, 0.10)',
  jungle: 'rgba(22, 163, 74, 0.12)',
  mountains: 'rgba(148, 163, 184, 0.10)',
  desert: 'rgba(234, 179, 8, 0.10)',
  swamp: 'rgba(101, 163, 13, 0.08)',
  underground: 'rgba(30, 30, 50, 0.20)',
  urban: 'rgba(212, 175, 55, 0.06)',
  ruins: 'rgba(148, 163, 184, 0.08)',
  arctic: 'rgba(186, 230, 253, 0.12)',
}

// ── Edge styles by travel_type ──────────────────────────────────────────────

const EDGE_STYLES: Record<string, { stroke: string; strokeWidth: number; strokeDasharray?: string }> = {
  walk:        { stroke: 'rgba(232, 223, 192, 0.25)', strokeWidth: 2 },
  ride:        { stroke: 'rgba(232, 223, 192, 0.30)', strokeWidth: 2.5 },
  sail:        { stroke: 'rgba(96, 165, 250, 0.40)', strokeWidth: 2, strokeDasharray: '8 4' },
  fly:         { stroke: 'rgba(148, 163, 184, 0.30)', strokeWidth: 1.5, strokeDasharray: '3 3' },
  teleport:    { stroke: 'rgba(168, 85, 247, 0.40)', strokeWidth: 1.5, strokeDasharray: '4 4' },
  portal:      { stroke: 'rgba(239, 68, 68, 0.40)', strokeWidth: 2.5, strokeDasharray: '6 3' },
  underground: { stroke: 'rgba(120, 80, 40, 0.30)', strokeWidth: 1.5, strokeDasharray: '3 6' },
  swim:        { stroke: 'rgba(45, 212, 191, 0.35)', strokeWidth: 2, strokeDasharray: '6 4' },
  climb:       { stroke: 'rgba(148, 163, 184, 0.25)', strokeWidth: 1.5, strokeDasharray: '2 2' },
  other:       { stroke: 'rgba(148, 163, 184, 0.20)', strokeWidth: 1, strokeDasharray: '4 4' },
}

// ── Custom Location Node ────────────────────────────────────────────────────

const LocationNode = memo(function LocationNode({ data }: NodeProps) {
  const Icon = LOCATION_ICONS[data.location_type as string] || MapPin
  const bgColor = REGION_COLORS[data.region_type as string] || REGION_COLORS.plains
  const visited = data.visited as boolean
  const rotation = (data.rotation as number) || 0
  const editMode = data.editMode as boolean

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-0 !h-0" />
      <div
        className={cn('flex flex-col items-center gap-1 cursor-pointer transition-all hover:scale-110')}
        style={{ transform: rotation ? `rotate(${-rotation}deg)` : undefined }}
      >
        <div
          className={cn(
            'w-10 h-10 rounded-full flex items-center justify-center transition-all',
            visited ? 'border-2 border-gold/60 shadow-[0_0_12px_rgba(212,175,55,0.25)]' : 'border border-white/15',
            editMode && 'border-dashed !border-gold/40',
          )}
          style={{ backgroundColor: bgColor }}
        >
          <Icon className="w-4.5 h-4.5 text-gold/80" />
        </div>
        <span className="text-[10px] font-heading text-parchment/70 text-center max-w-[100px] leading-tight whitespace-nowrap overflow-hidden text-ellipsis">
          {data.label as string}
        </span>
        {(data.session_count as number) > 1 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-gold/20 border border-gold/30 flex items-center justify-center text-[8px] font-heading text-gold/80">
            {data.session_count as number}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />
    </>
  )
})

const nodeTypes = { location: LocationNode }

// ── Props ───────────────────────────────────────────────────────────────────

interface MapCanvasProps {
  mapData: CampaignMap
  locations: CampaignLocation[]
  activePlane: string
  campaignId: string
  onNodeClick: (locationName: string) => void
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function MapCanvas({ mapData, locations, activePlane, campaignId, onNodeClick }: MapCanvasProps) {
  const [rotation, setRotation] = useState(() => mapData.rotation ?? 0)
  const [editMode, setEditMode] = useState(false)
  const dragTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const rotationTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleNodeDragStop: OnNodeDrag = useCallback((_event, node) => {
    if (!campaignId) return
    if (dragTimer.current) clearTimeout(dragTimer.current)
    dragTimer.current = setTimeout(() => {
      api('update_map_positions', campaignId, {
        [node.data.label as string]: { x: node.position.x, y: node.position.y },
      })
    }, 500)
  }, [campaignId])

  const handleRotate = useCallback((degrees: number) => {
    setRotation(degrees)
    // Debounce persistence
    if (rotationTimer.current) clearTimeout(rotationTimer.current)
    rotationTimer.current = setTimeout(() => {
      if (campaignId) {
        api('update_map_rotation', campaignId, degrees)
      }
    }, 500)
  }, [campaignId])

  // Build React Flow nodes/edges from map data, filtered by plane
  const locLookup: Record<string, CampaignLocation> = {}
  for (const loc of locations) {
    locLookup[loc.name.toLowerCase()] = loc
  }

  const planeNodes = mapData.nodes.filter(n => n.plane === activePlane)
  const planeNodeNames = new Set(planeNodes.map(n => n.name.toLowerCase()))

  const flowNodes: Node[] = planeNodes.map(n => {
    const locMeta = locLookup[n.name.toLowerCase()]
    return {
      id: n.name,
      type: 'location',
      position: { x: n.x, y: n.y },
      data: {
        label: n.name,
        region_type: n.region_type,
        location_type: n.location_type,
        visited: locMeta?.visited ?? false,
        session_count: locMeta?.session_count ?? 1,
        rotation,
        editMode,
      },
    }
  })

  const flowEdges: Edge[] = mapData.edges
    .filter(e => planeNodeNames.has(e.from.toLowerCase()) && planeNodeNames.has(e.to.toLowerCase()))
    .map((e, i) => {
      const style = EDGE_STYLES[e.travel_type] || EDGE_STYLES.other
      return {
        id: `edge-${i}`,
        source: e.from,
        target: e.to,
        label: e.label,
        type: 'default',
        style,
        labelStyle: {
          fill: 'rgba(232, 223, 192, 0.35)',
          fontSize: 9,
          fontFamily: 'Crimson Text, serif',
          transform: rotation ? `rotate(${-rotation}deg)` : undefined,
        },
        labelBgStyle: { fill: 'rgba(8, 11, 20, 0.7)', fillOpacity: 0.7 },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 3,
      }
    })

  return (
    <ReactFlowProvider>
      <div className="relative w-full h-full overflow-hidden">
        {/* Rotated map container */}
        <div
          className="w-full h-full transition-transform duration-150"
          style={{
            transform: rotation ? `rotate(${rotation}deg)` : undefined,
            transformOrigin: 'center center',
          }}
        >
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            nodesDraggable={editMode}
            onNodeClick={(_e, node) => onNodeClick(node.data.label as string)}
            onNodeDragStop={handleNodeDragStop}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.2}
            maxZoom={3}
            proOptions={{ hideAttribution: true }}
            style={{ background: '#080B14' }}
          >
            <TerrainLayer nodes={planeNodes} />
            <Background color="rgba(212, 175, 55, 0.03)" gap={40} size={1} />
            <MiniMap
              nodeColor={() => 'rgba(212, 175, 55, 0.3)'}
              maskColor="rgba(8, 11, 20, 0.8)"
              className="!bg-shadow !border-white/10"
            />
          </ReactFlow>
        </div>

        {/* Controls — outside rotation so they stay axis-aligned */}
        <div className="absolute bottom-2 left-2 z-10 flex flex-col items-center gap-2">
          <CompassRose rotation={rotation} onRotate={handleRotate} />
        </div>

        {/* Edit mode toggle */}
        <div className="absolute top-2 right-2 z-10 flex items-center gap-2">
          {editMode && (
            <span className="text-[10px] font-heading text-gold/60 bg-void/80 px-2 py-1 rounded border border-gold/20">
              Edit Mode — drag nodes to reposition
            </span>
          )}
          <button
            onClick={() => setEditMode(m => !m)}
            className={cn(
              'w-8 h-8 rounded flex items-center justify-center transition-all border',
              editMode
                ? 'bg-gold/20 border-gold/40 text-gold'
                : 'bg-shadow/80 border-white/10 text-parchment/50 hover:bg-white/5',
            )}
            title={editMode ? 'Exit edit mode' : 'Edit mode — drag to reposition nodes'}
          >
            <Pencil className="w-4 h-4" />
          </button>
        </div>
      </div>
    </ReactFlowProvider>
  )
}
