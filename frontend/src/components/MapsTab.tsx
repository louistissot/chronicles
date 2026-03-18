import { useState, useEffect, useMemo, lazy, Suspense } from 'react'
import {
  MapPin, Loader2, RefreshCw, X, Compass, Map, List, Search,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import type { CampaignMap, CampaignLocation, LocationSessionEvent } from '@/lib/api'

// Lazy-load React Flow canvas to prevent pywebview crashes if React Flow fails to initialize
const MapCanvas = lazy(() => import('@/components/MapCanvas'))

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
  // Load map + locations on mount
  useEffect(() => {
    if (!campaignId) return
    setLoaded(false)
    setMapData(null)
    setSelectedLocation(null)
    async function load() {
      try {
        const mapResult = await api('get_campaign_map', campaignId!) as { ok: boolean; map: CampaignMap | null } | null
        if (mapResult?.ok && mapResult.map) {
          setMapData(mapResult.map)
          setActivePlane(mapResult.map.planes?.[0] || 'Material Plane')
        }
      } catch {
        // Map not generated yet — that's fine
      }
      try {
        const locResult = await api('get_campaign_locations', campaignId!) as { ok: boolean; locations?: CampaignLocation[] } | null
        if (locResult?.ok && locResult.locations) {
          setLocations(locResult.locations)
        }
      } catch {
        // Locations may not exist yet
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

  // Memoize list view filtering
  const filteredListLocations = useMemo(() => {
    if (!listSearch) return locations
    const q = listSearch.toLowerCase()
    return locations.filter(loc =>
      loc.name.toLowerCase().includes(q) || loc.description?.toLowerCase().includes(q) ||
      loc.relative_position?.toLowerCase().includes(q) || loc.connections?.some(c => c.toLowerCase().includes(q))
    )
  }, [locations, listSearch])

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

          {mapData && campaignId && (
            <Suspense fallback={
              <div className="h-full flex items-center justify-center">
                <Loader2 className="w-6 h-6 animate-spin text-gold/30" />
              </div>
            }>
              <MapCanvas
                mapData={mapData}
                locations={locations}
                activePlane={activePlane}
                campaignId={campaignId}
                onNodeClick={handleNodeClick}
              />
            </Suspense>
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
            {filteredListLocations.length === 0 && locations.length > 0 && (
              <p className="text-xs text-parchment/25 font-body italic py-4 text-center">No locations match this search.</p>
            )}
            {filteredListLocations.length > 0 && (
              <div className="space-y-2">
                {filteredListLocations.map((loc, i) => (
                    <div key={i} className="rounded-md border border-white/5 bg-void/30 px-3 py-2 hover:border-white/10 transition-colors">
                      <div className="flex items-center gap-2">
                        {loc.global_order != null ? (
                          <span className="w-5 h-5 rounded-full bg-gold/15 border border-gold/25 flex items-center justify-center text-[10px] font-heading text-gold/80 flex-none">{loc.global_order}</span>
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
              )}
          </div>
        </>
      )}
    </div>
  )
}
