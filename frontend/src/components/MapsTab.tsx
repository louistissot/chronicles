import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  ReactFlow, Background, Controls, MiniMap,
  type Node, type Edge, type NodeProps, type OnNodeDrag,
  Handle, Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  MapPin, Loader2, RefreshCw, X, Compass, Map, List, Search,
  Castle, Home, Beer, Church, Ship, Anchor, Wheat, Tent,
  Mountain, Landmark, Shield, TreePine, Signpost, Crown, Store,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import type { CampaignMap, CampaignLocation, MapNode, MapEdge, LocationSessionEvent } from '@/lib/api'

// ── Icon mapping for location_type ──────────────────────────────────────────

const LOCATION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  city: Castle, town: Home, village: Home, inn: Beer,
  temple: Church, shrine: Church, ship: Ship, dock: Anchor,
  farm: Wheat, camp: Tent, cave: Mountain, dungeon: Mountain,
  ruins: Landmark, fortress: Shield, tower: Shield,
  clearing: TreePine, bridge: Signpost, crossroads: Signpost,
  manor: Crown, market: Store, other: MapPin,
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

function LocationNode({ data }: NodeProps) {
  const Icon = LOCATION_ICONS[data.location_type as string] || MapPin
  const bgColor = REGION_COLORS[data.region_type as string] || REGION_COLORS.plains
  const visited = data.visited as boolean

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-0 !h-0" />
      <div
        className={cn(
          'flex flex-col items-center gap-1 cursor-pointer transition-all hover:scale-110',
        )}
      >
        {/* Node circle */}
        <div
          className={cn(
            'w-10 h-10 rounded-full flex items-center justify-center transition-all',
            visited ? 'border-2 border-gold/60 shadow-[0_0_12px_rgba(212,175,55,0.25)]' : 'border border-white/15',
          )}
          style={{ backgroundColor: bgColor }}
        >
          <Icon className="w-4.5 h-4.5 text-gold/80" />
        </div>
        {/* Label */}
        <span className="text-[10px] font-heading text-parchment/70 text-center max-w-[100px] leading-tight whitespace-nowrap overflow-hidden text-ellipsis">
          {data.label as string}
        </span>
        {/* Session count badge */}
        {(data.session_count as number) > 1 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-gold/20 border border-gold/30 flex items-center justify-center text-[8px] font-heading text-gold/80">
            {data.session_count as number}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />
    </>
  )
}

const nodeTypes = { location: LocationNode }

// ── Detail Panel ────────────────────────────────────────────────────────────

function DetailPanel({
  locationName, location, events, loadingEvents, onClose,
}: {
  locationName: string
  location: CampaignLocation | undefined
  events: LocationSessionEvent[] | null
  loadingEvents: boolean
  onClose: () => void
}) {
  return (
    <div className="absolute right-0 top-0 bottom-0 w-[340px] bg-shadow border-l border-white/8 overflow-y-auto z-10">
      {/* Header */}
      <div className="sticky top-0 bg-shadow/95 backdrop-blur-sm px-4 py-3 border-b border-white/8 flex items-center gap-2">
        <Compass className="w-4 h-4 text-gold/50 flex-none" />
        <h3 className="text-sm font-heading text-parchment/80 flex-1 truncate">{locationName}</h3>
        <button onClick={onClose} className="p-1 rounded hover:bg-white/5 text-parchment/40 hover:text-parchment/70 transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="px-4 py-3 space-y-4">
        {/* Location info */}
        {location && (
          <>
            {location.description && (
              <div>
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest mb-1">Description</p>
                <p className="text-xs font-body text-parchment/55 leading-relaxed">{location.description}</p>
              </div>
            )}
            {location.connections && location.connections.length > 0 && (
              <div>
                <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest mb-1">Connections</p>
                <div className="flex flex-wrap gap-1">
                  {location.connections.map((c, i) => (
                    <span key={i} className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-parchment/40 border border-white/5">{c}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* Session events */}
        <div>
          <p className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest mb-1.5">
            What happened here
          </p>
          {loadingEvents && (
            <div className="flex items-center gap-2 py-4">
              <Loader2 className="w-3 h-3 animate-spin text-gold/40" />
              <span className="text-[10px] text-parchment/30">Loading events...</span>
            </div>
          )}
          {!loadingEvents && events && events.length === 0 && (
            <p className="text-[10px] text-parchment/20 italic py-2">No events recorded at this location.</p>
          )}
          {!loadingEvents && events && events.length > 0 && (
            <div className="space-y-2">
              {events.map((evt, i) => (
                <div key={i} className="rounded-md border border-white/5 bg-void/30 px-3 py-2">
                  <p className="text-[10px] font-heading text-gold/60 mb-1">
                    {evt.session_date}{evt.session_name ? ` — ${evt.session_name}` : ''}
                  </p>
                  {evt.description && (
                    <p className="text-[11px] font-body text-parchment/50 leading-relaxed">{evt.description}</p>
                  )}
                  {evt.npcs.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {evt.npcs.map((npc, j) => (
                        <span key={j} className="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-400/10 text-purple-300/60 border border-purple-400/15">{npc}</span>
                      ))}
                    </div>
                  )}
                  {evt.events.length > 0 && (
                    <div className="mt-1.5 space-y-1">
                      {evt.events.map((e, j) => (
                        <p key={j} className="text-[10px] font-body text-parchment/35 italic pl-2 border-l border-gold/15">{e}</p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main Component ──────────────────────────────────────────────────────────

export function MapsTab({ campaignId, campaignName }: { campaignId: string | null; campaignName: string }) {
  const [mapData, setMapData] = useState<CampaignMap | null>(null)
  const [locations, setLocations] = useState<CampaignLocation[]>([])
  const [loaded, setLoaded] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [activePlane, setActivePlane] = useState('Material Plane')
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null)
  const [locationEvents, setLocationEvents] = useState<LocationSessionEvent[] | null>(null)
  const [loadingEvents, setLoadingEvents] = useState(false)
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map')
  const [listSearch, setListSearch] = useState('')
  const dragTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load map + locations on mount
  useEffect(() => {
    if (!campaignId) return
    setLoaded(false)
    setMapData(null)
    setSelectedLocation(null)
    async function load() {
      const mapResult = await api('get_campaign_map', campaignId!) as { ok: boolean; map: CampaignMap | null } | null
      const locResult = await api('get_campaign_locations', campaignId!) as { ok: boolean; locations?: CampaignLocation[] } | null
      if (mapResult?.ok && mapResult.map) {
        setMapData(mapResult.map)
        setActivePlane(mapResult.map.planes?.[0] || 'Material Plane')
      }
      if (locResult?.ok && locResult.locations) {
        setLocations(locResult.locations)
      }
      setLoaded(true)
    }
    load()
  }, [campaignId])

  // Generate map
  async function handleGenerate() {
    if (!campaignId) return
    setGenerating(true)
    const result = await api('generate_campaign_map', campaignId) as { ok: boolean; map?: CampaignMap; error?: string } | null
    if (result?.ok && result.map) {
      setMapData(result.map)
      setActivePlane(result.map.planes?.[0] || 'Material Plane')
    }
    setGenerating(false)
  }

  // Node click → load events
  async function handleNodeClick(locationName: string) {
    if (!campaignId) return
    setSelectedLocation(locationName)
    setLoadingEvents(true)
    setLocationEvents(null)
    const result = await api('get_location_events', campaignId, locationName) as { ok: boolean; sessions?: LocationSessionEvent[] } | null
    setLocationEvents(result?.sessions || [])
    setLoadingEvents(false)
  }

  // Node drag → persist position
  const handleNodeDragStop: OnNodeDrag = useCallback((_event, node) => {
    if (!campaignId) return
    if (dragTimer.current) clearTimeout(dragTimer.current)
    dragTimer.current = setTimeout(() => {
      api('update_map_positions', campaignId, {
        [node.data.label as string]: { x: node.position.x, y: node.position.y },
      })
    }, 500)
  }, [campaignId])

  // Convert map data to React Flow nodes/edges, filtered by plane
  const { flowNodes, flowEdges } = useMemo(() => {
    if (!mapData) return { flowNodes: [], flowEdges: [] }

    // Build location lookup for metadata
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
          labelStyle: { fill: 'rgba(232, 223, 192, 0.35)', fontSize: 9, fontFamily: 'Crimson Text, serif' },
          labelBgStyle: { fill: 'rgba(8, 11, 20, 0.7)', fillOpacity: 0.7 },
          labelBgPadding: [4, 2] as [number, number],
          labelBgBorderRadius: 3,
        }
      })

    return { flowNodes, flowEdges }
  }, [mapData, activePlane, locations])

  // ── Renders ─────────────────────────────────────────────────────────────

  if (!campaignId) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-center px-6">
        <MapPin className="w-10 h-10 text-parchment/10" />
        <p className="text-sm font-heading text-parchment/30">No campaign selected</p>
        <p className="text-xs font-body text-parchment/20">Select a campaign from the dropdown to view its map</p>
      </div>
    )
  }

  if (!loaded) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-xs font-body text-parchment/30">Loading map...</p>
      </div>
    )
  }

  const selectedLoc = selectedLocation
    ? locations.find(l => l.name.toLowerCase() === selectedLocation.toLowerCase())
    : undefined

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-none px-5 py-3 border-b border-white/8 flex items-center gap-3">
        <MapPin className="w-4 h-4 text-gold/50" />
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">Maps</h2>
          <p className="text-[10px] font-body text-parchment/30 truncate mt-0.5">
            {campaignName} · {locations.length} location{locations.length !== 1 ? 's' : ''}
          </p>
        </div>
        {/* View toggle */}
        <div className="flex rounded-md border border-white/8 overflow-hidden">
          <button
            onClick={() => setViewMode('map')}
            className={cn(
              'px-2 py-1.5 transition-colors',
              viewMode === 'map' ? 'bg-gold/20 text-gold' : 'bg-void/40 text-parchment/40 hover:text-parchment/60'
            )}
            title="Map view"
          >
            <Map className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={cn(
              'px-2 py-1.5 transition-colors',
              viewMode === 'list' ? 'bg-gold/20 text-gold' : 'bg-void/40 text-parchment/40 hover:text-parchment/60'
            )}
            title="List view"
          >
            <List className="w-3.5 h-3.5" />
          </button>
        </div>
        {viewMode === 'map' && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleGenerate}
            disabled={generating || locations.length === 0}
            className="h-7 text-[10px] px-3 gap-1.5"
          >
            {generating ? (
              <><Loader2 className="w-3 h-3 animate-spin" />Generating...</>
            ) : mapData ? (
              <><RefreshCw className="w-3 h-3" />Regenerate Map</>
            ) : (
              <><Compass className="w-3 h-3" />Generate Map</>
            )}
          </Button>
        )}
      </div>

      {/* Plane tabs (map view only) */}
      {viewMode === 'map' && mapData && mapData.planes.length > 1 && (
        <div className="flex-none px-5 py-2 border-b border-white/5 flex gap-1.5">
          {mapData.planes.map(plane => (
            <button
              key={plane}
              onClick={() => setActivePlane(plane)}
              className={cn(
                'px-2.5 py-1 rounded-full text-[10px] font-heading uppercase tracking-wider transition-colors',
                activePlane === plane
                  ? 'bg-gold/20 text-gold border border-gold/30'
                  : 'bg-void/40 text-parchment/40 border border-white/6 hover:border-gold/20 hover:text-parchment/60'
              )}
            >
              {plane}
            </button>
          ))}
        </div>
      )}

      {/* ── Map View ── */}
      {viewMode === 'map' && (
        <div className="flex-1 relative">
          {!mapData && !generating && (
            <div className="h-full flex flex-col items-center justify-center gap-3 text-center px-6">
              <Compass className="w-12 h-12 text-parchment/8" />
              <p className="text-sm font-heading text-parchment/30">No map generated yet</p>
              <p className="text-xs font-body text-parchment/20 max-w-[280px]">
                {locations.length > 0
                  ? 'Click "Generate Map" to create an interactive map from your campaign locations.'
                  : 'Process sessions first to discover locations, then generate a map.'}
              </p>
            </div>
          )}

          {generating && !mapData && (
            <div className="h-full flex flex-col items-center justify-center gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-gold/30" />
              <p className="text-xs font-body text-parchment/30">Generating campaign map...</p>
            </div>
          )}

          {mapData && (
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              onNodeClick={(_e, node) => handleNodeClick(node.data.label as string)}
              onNodeDragStop={handleNodeDragStop}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              minZoom={0.2}
              maxZoom={3}
              proOptions={{ hideAttribution: true }}
              style={{ background: '#080B14' }}
            >
              <Background color="rgba(212, 175, 55, 0.03)" gap={40} size={1} />
              <Controls
                showInteractive={false}
                className="!bg-shadow !border-white/10 !shadow-none [&>button]:!bg-shadow [&>button]:!border-white/10 [&>button]:!text-parchment/50 [&>button:hover]:!bg-white/5"
              />
              <MiniMap
                nodeColor={() => 'rgba(212, 175, 55, 0.3)'}
                maskColor="rgba(8, 11, 20, 0.8)"
                className="!bg-shadow !border-white/10"
              />
            </ReactFlow>
          )}

          {/* Detail panel */}
          {selectedLocation && (
            <DetailPanel
              locationName={selectedLocation}
              location={selectedLoc}
              events={locationEvents}
              loadingEvents={loadingEvents}
              onClose={() => { setSelectedLocation(null); setLocationEvents(null) }}
            />
          )}
        </div>
      )}

      {/* ── List View ── */}
      {viewMode === 'list' && (
        <>
          {/* Search */}
          {locations.length > 0 && (
            <div className="flex-none px-5 py-2.5 border-b border-white/5">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-parchment/25" />
                <input
                  value={listSearch}
                  onChange={e => setListSearch(e.target.value)}
                  placeholder="Search locations..."
                  className="w-full h-7 bg-void/60 border border-white/8 rounded pl-7 pr-2 text-[11px] text-parchment/60 outline-none focus:border-gold/40 placeholder:text-parchment/20"
                />
              </div>
            </div>
          )}
          <div className="flex-1 overflow-y-auto px-5 py-3">
            {locations.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
                <MapPin className="w-10 h-10 text-parchment/10" />
                <p className="text-sm font-heading text-parchment/30">No locations yet</p>
                <p className="text-xs font-body text-parchment/20">Process sessions to discover locations.</p>
              </div>
            )}
            {(() => {
              const filtered = listSearch
                ? locations.filter(loc => {
                    const q = listSearch.toLowerCase()
                    return loc.name.toLowerCase().includes(q) || loc.description?.toLowerCase().includes(q) ||
                      loc.relative_position?.toLowerCase().includes(q) || loc.connections?.some(c => c.toLowerCase().includes(q))
                  })
                : locations
              if (filtered.length === 0 && locations.length > 0) {
                return <p className="text-xs text-parchment/25 font-body italic py-4 text-center">No locations match this search.</p>
              }
              return (
                <div className="space-y-2">
                  {filtered.map((loc, i) => (
                    <div key={i} className="rounded-md border border-white/5 bg-void/30 px-3 py-2 hover:border-white/10 transition-colors">
                      <div className="flex items-center gap-2">
                        {loc.visit_order != null ? (
                          <span className="w-5 h-5 rounded-full bg-gold/15 border border-gold/25 flex items-center justify-center text-[10px] font-heading text-gold/80 flex-none">{loc.visit_order}</span>
                        ) : (
                          <Compass className="w-3.5 h-3.5 text-gold/50 flex-none" />
                        )}
                        <span className="text-sm font-body text-parchment/80 font-semibold">{loc.name}</span>
                        {loc.visited && (
                          <span className="text-[8px] uppercase tracking-wider text-emerald-400/70 bg-emerald-400/10 px-1.5 py-0.5 rounded-full">Visited</span>
                        )}
                        {loc.session_count > 1 && (
                          <span className="text-[8px] uppercase tracking-wider text-gold/50 bg-gold/8 px-1.5 py-0.5 rounded-full">{loc.session_count} sessions</span>
                        )}
                        {loc.region_type && (
                          <span className="text-[8px] px-1.5 py-0.5 rounded-full bg-white/5 text-parchment/30 border border-white/5">{loc.region_type}</span>
                        )}
                        {loc.location_type && (
                          <span className="text-[8px] px-1.5 py-0.5 rounded-full bg-white/5 text-parchment/30 border border-white/5">{loc.location_type}</span>
                        )}
                      </div>
                      {loc.description && <p className="mt-1 text-xs text-parchment/55 font-body">{loc.description}</p>}
                      {loc.relative_position && <p className="mt-1 text-[11px] text-parchment/35 font-body italic">{loc.relative_position}</p>}
                      {loc.connections && loc.connections.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {loc.connections.map((c, j) => (
                            <span key={j} className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-parchment/40 border border-white/5">{c}</span>
                          ))}
                        </div>
                      )}
                      {(loc.first_session_date || loc.last_session_date) && (
                        <p className="mt-1.5 text-[9px] text-parchment/25 font-body">
                          {loc.first_session_date === loc.last_session_date
                            ? `Session: ${loc.first_session_date}`
                            : `First: ${loc.first_session_date} · Last: ${loc.last_session_date}`}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )
            })()}
          </div>
        </>
      )}
    </div>
  )
}
