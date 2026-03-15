import { useState, useEffect, useCallback } from 'react'
import {
  Scroll, Loader2, RefreshCw, ChevronDown,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import type { Campaign, Season, TimelineEvent } from '@/lib/api'
import { MarkdownRenderer } from '@/components/MarkdownRenderer'
import { HorizontalTimeline } from './HorizontalTimeline'

interface SeasonDigest {
  title: string
  narrative: string
  character_arcs: Array<{ name: string; arc: string }>
  unresolved: string[]
  timeline?: TimelineEvent[]
}

export function ChronicleTab({ campaignId, campaignName }: { campaignId: string | null; campaignName: string }) {
  const [seasons, setSeasons] = useState<Season[]>([])
  const [selectedSeasonId, setSelectedSeasonId] = useState<string | null>(null)
  const [digest, setDigest] = useState<SeasonDigest | null>(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [streamingText, setStreamingText] = useState('')

  // Load seasons when campaign changes
  useEffect(() => {
    if (!campaignId) {
      setSeasons([])
      setSelectedSeasonId(null)
      return
    }
    async function load() {
      const campaigns = await api('get_campaigns')
      const campaign = campaigns?.find((c: Campaign) => c.id === campaignId)
      if (campaign?.seasons?.length) {
        setSeasons(campaign.seasons)
        setSelectedSeasonId(campaign.seasons[campaign.seasons.length - 1].id)
      } else {
        setSeasons([])
        setSelectedSeasonId(null)
      }
    }
    load()
  }, [campaignId])

  // Load existing digest
  const loadDigest = useCallback(async () => {
    if (!campaignId || !selectedSeasonId) return
    setLoading(true)
    setDigest(null)
    setError(null)
    try {
      const result = await api('get_season_digest', campaignId, selectedSeasonId)
      if (result?.ok && result.digest) {
        setDigest(result.digest)
      }
    } catch {
      // No digest yet
    }
    setLoading(false)
  }, [campaignId, selectedSeasonId])

  useEffect(() => {
    loadDigest()
  }, [loadDigest])

  const handleGenerate = useCallback(async () => {
    if (!campaignId || !selectedSeasonId) return
    setGenerating(true)
    setError(null)
    setStreamingText('')
    setDigest(null)

    try {
      const result = await api('generate_season_digest', campaignId, selectedSeasonId)
      if (result?.ok && result.digest) {
        setDigest(result.digest)
        setStreamingText('')
      } else {
        setError(result?.error || 'Failed to generate digest')
      }
    } catch (e: any) {
      setError(e?.message || 'An error occurred')
    }
    setGenerating(false)
  }, [campaignId, selectedSeasonId])

  if (!campaignId) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-center px-6">
        <Scroll className="w-10 h-10 text-parchment/10" />
        <p className="text-sm font-heading text-parchment/30">No campaign selected</p>
        <p className="text-xs font-body text-parchment/20">Select a campaign from the dropdown to view its chronicle</p>
      </div>
    )
  }

  if (seasons.length === 0 && !loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-center px-6">
        <Scroll className="w-10 h-10 text-parchment/10" />
        <p className="text-sm font-heading text-parchment/30">No seasons yet</p>
        <p className="text-xs font-body text-parchment/20">Add seasons to your campaign to generate chronicles</p>
      </div>
    )
  }

  const selectedSeason = seasons.find(s => s.id === selectedSeasonId)

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-none px-5 py-3 border-b border-white/8 flex items-center gap-3">
        <Scroll className="w-4 h-4 text-gold/50" />
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">Chronicles</h2>
          <p className="text-[10px] font-body text-parchment/30 truncate mt-0.5">{campaignName}</p>
        </div>

        {/* Season selector */}
        {seasons.length > 1 && (
          <div className="flex items-center gap-1.5">
            {seasons.map(s => (
              <button
                key={s.id}
                onClick={() => setSelectedSeasonId(s.id)}
                className={cn(
                  'px-2.5 py-1 rounded-md text-[10px] font-heading uppercase tracking-wider transition-colors',
                  s.id === selectedSeasonId
                    ? 'bg-gold/20 text-gold border border-gold/30'
                    : 'bg-void/40 text-parchment/40 border border-white/6 hover:border-gold/20'
                )}
              >
                S{s.number}
              </button>
            ))}
          </div>
        )}

        {/* Generate / Regenerate */}
        <Button
          size="sm"
          variant={digest ? 'outline' : 'default'}
          onClick={handleGenerate}
          disabled={generating || !selectedSeasonId}
          className="h-7 text-[10px] px-3 gap-1.5"
        >
          {generating ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : digest ? (
            <RefreshCw className="w-3 h-3" />
          ) : (
            <Scroll className="w-3 h-3" />
          )}
          {generating ? 'Generating…' : digest ? 'Regenerate' : 'Generate Digest'}
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 text-gold/40 animate-spin" />
          </div>
        )}

        {error && (
          <div className="rounded-md border border-red-400/20 bg-red-400/5 px-4 py-3 text-xs text-red-400/80 font-body">
            {error}
          </div>
        )}

        {generating && !digest && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 text-gold/50 animate-spin" />
              <p className="text-xs font-body text-gold/50 animate-pulse">Weaving the chronicle…</p>
            </div>
            {streamingText && (
              <div className="rounded-md border border-white/6 bg-void/30 p-4">
                <MarkdownRenderer text={streamingText} />
              </div>
            )}
          </div>
        )}

        {!loading && !generating && !digest && !error && (
          <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
            <Scroll className="w-12 h-12 text-parchment/8" />
            <div>
              <p className="text-sm font-heading text-parchment/30">
                Season {selectedSeason?.number ?? '?'} Chronicles
              </p>
              <p className="text-xs font-body text-parchment/20 mt-1">
                Generate a digest to weave your sessions into an epic narrative
              </p>
            </div>
          </div>
        )}

        {digest && (
          <div className="space-y-6 max-w-3xl mx-auto">
            {/* Title */}
            <div className="text-center">
              <h3 className="text-xl font-display text-gold" style={{ fontFamily: "'Cinzel Decorative', serif" }}>
                {digest.title}
              </h3>
              <p className="text-[10px] text-parchment/30 font-heading uppercase tracking-widest mt-1">
                Season {selectedSeason?.number ?? '?'}
              </p>
            </div>

            {/* Season Timeline */}
            {digest.timeline && digest.timeline.length > 0 && (
              <div>
                <h4 className="text-xs font-heading text-parchment/50 uppercase tracking-widest mb-3">Season Timeline</h4>
                <HorizontalTimeline events={digest.timeline} />
              </div>
            )}

            {/* Narrative */}
            <div className="rounded-md border border-white/6 bg-void/20 p-5">
              <MarkdownRenderer text={digest.narrative} />
            </div>

            {/* Character Arcs */}
            {digest.character_arcs?.length > 0 && (
              <div>
                <h4 className="text-xs font-heading text-parchment/50 uppercase tracking-widest mb-3">Character Arcs</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {digest.character_arcs.map((ca, i) => (
                    <div key={i} className="rounded-md border border-white/6 bg-void/20 px-3 py-2">
                      <p className="text-xs font-heading text-gold/70 mb-0.5">{ca.name}</p>
                      <p className="text-[11px] font-body text-parchment/50 leading-relaxed">{ca.arc}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Unresolved Threads */}
            {digest.unresolved?.length > 0 && (
              <div>
                <h4 className="text-xs font-heading text-parchment/50 uppercase tracking-widest mb-3">Unresolved Threads</h4>
                <ul className="space-y-1.5">
                  {digest.unresolved.map((thread, i) => (
                    <li key={i} className="flex items-start gap-2 text-[11px] font-body text-parchment/50">
                      <span className="text-gold/40 mt-0.5">•</span>
                      <span>{thread}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
