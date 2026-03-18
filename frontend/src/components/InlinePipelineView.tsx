/**
 * InlinePipelineView — shows pipeline processing progress with sidebar stages,
 * recording controls, speaker mapping review, and streaming LLM output.
 * Extracted from LibraryTab for reuse in SessionTab.
 */
import { useState, useEffect, useRef } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { api, type PipelineStage, type SpeakerReviewPayload, type EntityReviewPayload, type FactReviewPayload, type FactCard } from '@/lib/api'
import { EntityReviewPanel } from './EntityReviewPanel'
import {
  Loader2, RefreshCw, Mic, FileText,
  BookMarked, ScrollText, Clock, Check, X,
  ChevronDown, Square, AlertTriangle, CheckCircle2, XCircle, Circle, Wand2,
  Copy, BookOpen, Users, Mic2, SkipForward, Pause, Play, Image, SpellCheck,
  Trophy, Compass, Gem, Scroll, Pencil, Search, ClipboardCheck,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { PipelineStages, StageState } from '@/App'

// ── Helpers ──────────────────────────────────────────────────────────────────

export function classifyLine(text: string): string {
  const t = text.toLowerCase()
  if (t.includes('error') || t.includes('failed') || t.includes('traceback')) return 'error'
  if (t.includes('warning')) return 'warn'
  if (t.includes('100%') || t.includes('done') || t.includes('saved')) return 'success'
  if (t.includes('ffmpeg')) return 'ffmpeg'
  return 'default'
}

export const LINE_COLORS: Record<string, string> = {
  error: 'text-red-400', warn: 'text-amber-300', success: 'text-emerald-400',
  ffmpeg: 'text-sky-400', default: 'text-parchment/75',
}

export const STAGE_ORDER: { id: PipelineStage; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'transcription',         label: 'Transcription',         icon: Mic2 },
  { id: 'saving_transcript',    label: 'Save Transcript',       icon: FileText },
  { id: 'transcript_correction',label: 'Term Correction',       icon: SpellCheck },
  { id: 'speaker_mapping',      label: 'Speaker ID',            icon: Users },
  { id: 'updating_transcript',  label: 'Update Transcript',     icon: RefreshCw },
  { id: 'fact_extraction',    label: 'Extract Facts',          icon: Search },
  { id: 'fact_review',        label: 'Review Facts',           icon: ClipboardCheck },
  { id: 'timeline',           label: 'Timeline',           icon: Clock },
  { id: 'summary',            label: 'Summary',            icon: BookMarked },
  { id: 'dm_notes',           label: 'DM Notes',           icon: ScrollText },
  { id: 'character_updates',  label: 'Character Updates',  icon: Users },
  { id: 'glossary',           label: 'Glossary',           icon: BookOpen },
  { id: 'leaderboard',      label: 'Leaderboard',       icon: Trophy },
  { id: 'locations',        label: 'Locations',          icon: Compass },
  { id: 'npcs',             label: 'NPCs',              icon: Users },
  { id: 'loot',             label: 'Loot',              icon: Gem },
  { id: 'missions',         label: 'Missions',          icon: Scroll },
  { id: 'illustration',       label: 'Illustration',       icon: Image },
]

export function StageIcon({ status }: { status: string }) {
  if (status === 'running')      return <Loader2 className="w-4 h-4 text-gold animate-spin flex-none" />
  if (status === 'done')         return <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-none" />
  if (status === 'error')        return <XCircle className="w-4 h-4 text-red-400 flex-none" />
  if (status === 'needs_review') return <AlertTriangle className="w-4 h-4 text-amber-400 flex-none" />
  return <Circle className="w-4 h-4 text-parchment/15 flex-none" />
}

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button onClick={() => { navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }) }}
      className="p-1.5 rounded text-parchment/30 hover:text-gold hover:bg-gold/10 transition-colors">
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

export const SKIPPABLE_STAGES: PipelineStage[] = ['timeline', 'summary', 'dm_notes', 'character_updates', 'leaderboard', 'locations', 'npcs', 'loot', 'missions']

// ── Main Component ───────────────────────────────────────────────────────────

interface InlinePipelineViewProps {
  stages: PipelineStages
  speakerReview: SpeakerReviewPayload | null
  entityReview: EntityReviewPayload | null
  factReview: FactReviewPayload | null
  logLines: Array<{ text: string; isStderr: boolean }>
  logVersion: number
  streamingChunks: Record<PipelineStage, string>
  streamingVersion: number
  isTranscribing: boolean
  onStop: () => void
  onStopLLMStage: (stage: PipelineStage) => void
  onSkipStage: (stage: PipelineStage) => void
  onBack?: () => void
  onViewSession?: () => void
  recordingActive?: boolean
  recordingPaused?: boolean
  recordingSeconds?: number
  recordingAmplitude?: number
  recordingFileSize?: number
  amplitudeHistory?: number[]
  onPauseRecording?: () => void
  onResumeRecording?: () => void
  onStopRecording?: () => void
  onNavigateToLibrary?: () => void
}

export function InlinePipelineView({
  stages, speakerReview, entityReview, factReview, logLines, logVersion, streamingChunks, streamingVersion,
  isTranscribing, onStop, onStopLLMStage, onSkipStage, onBack, onViewSession,
  recordingActive, recordingPaused, recordingSeconds,
  recordingAmplitude, recordingFileSize, amplitudeHistory,
  onPauseRecording, onResumeRecording, onStopRecording,
  onNavigateToLibrary,
}: InlinePipelineViewProps) {
  const [activeStage, setActiveStage] = useState<PipelineStage | 'recording'>( recordingActive ? 'recording' : 'transcription')
  const [speakerMap, setSpeakerMap] = useState<Record<string, string>>({})
  const logEndRef = useRef<HTMLDivElement>(null)
  const displaySeconds = recordingSeconds ?? 0
  const [showStopConfirm, setShowStopConfirm] = useState(false)

  // Set active stage when recording starts
  useEffect(() => {
    if (recordingActive) { setActiveStage('recording') }
  }, [recordingActive])

  useEffect(() => {
    if (recordingActive) return // don't override during recording
    const running = STAGE_ORDER.find(s => stages[s.id].status === 'running')
    const needs   = STAGE_ORDER.find(s => stages[s.id].status === 'needs_review')
    if (needs) setActiveStage(needs.id)
    else if (running) setActiveStage(running.id)
  }, [stages, recordingActive])

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [logVersion])

  useEffect(() => {
    if (speakerReview) {
      const initial: Record<string, string> = {}
      speakerReview.unmappedSpeakers.forEach((sp, i) => { initial[sp] = speakerReview.characterNames[i] || '' })
      setSpeakerMap(p => ({ ...initial, ...p }))
    }
  }, [speakerReview])

  const activeState: StageState = activeStage === 'recording' ? { status: recordingActive ? 'running' : 'idle' } : stages[activeStage]
  const chunk = activeStage === 'recording' ? '' : streamingChunks[activeStage as PipelineStage]
  const LLM_STAGES: PipelineStage[] = ['speaker_mapping', 'fact_extraction', 'summary', 'dm_notes', 'timeline', 'illustration']

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-none flex items-center gap-3 px-5 py-3 border-b border-white/5">
        {onBack && (
          <button onClick={onBack} className="text-parchment/35 hover:text-gold/70 transition-colors p-1 rounded" title="Back">
            <ChevronDown className="w-4 h-4" />
          </button>
        )}
        <Wand2 className="w-3.5 h-3.5 text-gold/60" />
        <span className="text-xs font-heading text-parchment/70 uppercase tracking-widest">Processing</span>
        <div className="ml-auto flex items-center gap-2">
          {onViewSession && (
            <button onClick={onViewSession}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-gold/20 text-xs text-parchment/50 hover:text-gold hover:border-gold/40 transition-colors">
              <BookOpen className="w-3 h-3" />View Session
            </button>
          )}
          {Object.values(stages).some(s => s.status === 'running') && (
            <button onClick={onStop}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-red-500/30 text-xs text-red-400 hover:bg-red-500/8 transition-colors">
              <Square className="w-3 h-3 fill-current" />Stop
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <div className="flex-none w-36 border-r border-white/5 flex flex-col py-2 overflow-y-auto">
          {/* Recording pseudo-stage */}
          {(recordingActive || displaySeconds > 0) && (
            <button onClick={() => setActiveStage('recording')}
              className={cn(
                'flex items-center gap-2 px-3 py-2 text-left w-full transition-colors',
                activeStage === 'recording' ? 'bg-white/5 text-parchment/90' : 'text-parchment/30 hover:text-parchment/60 hover:bg-white/3'
              )}>
              {recordingActive ? (
                <span className="relative flex-none w-4 h-4 flex items-center justify-center">
                  <span className="w-2 h-2 rounded-full bg-red-500" />
                  <span className="absolute inset-0 w-2 h-2 m-auto rounded-full bg-red-500 animate-ping" />
                </span>
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-none" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1">
                  <Mic className="w-2.5 h-2.5 opacity-40 flex-none" />
                  <span className="text-[10px] font-body truncate">Recording</span>
                </div>
              </div>
            </button>
          )}
          {STAGE_ORDER.map(({ id, label, icon: Icon }) => {
            const state = stages[id]
            const isActive = activeStage === id
            return (
              <button key={id} onClick={() => setActiveStage(id)}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 text-left w-full transition-colors',
                  isActive ? 'bg-white/5 text-parchment/90' : 'text-parchment/30 hover:text-parchment/60 hover:bg-white/3'
                )}>
                <StageIcon status={state.status} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1">
                    <Icon className="w-2.5 h-2.5 opacity-40 flex-none" />
                    <span className="text-[10px] font-body truncate">{label}</span>
                  </div>
                </div>
              </button>
            )
          })}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="p-4 space-y-3">
              {/* Recording panel */}
              {activeStage === 'recording' && (
                <div className="flex flex-col items-center gap-6 py-8">
                  {/* Pulsing mic icon */}
                  <div className="relative">
                    <div className={cn(
                      'w-16 h-16 rounded-full flex items-center justify-center',
                      recordingActive && !recordingPaused ? 'bg-red-500/15 border border-red-500/30' : 'bg-white/5 border border-white/10'
                    )}>
                      <Mic className={cn('w-7 h-7', recordingActive && !recordingPaused ? 'text-red-400' : 'text-parchment/40')} />
                    </div>
                    {recordingActive && !recordingPaused && (
                      <span className="absolute inset-0 rounded-full border border-red-500/20 animate-ping" />
                    )}
                  </div>

                  {/* Waveform visualization */}
                  {recordingActive && amplitudeHistory && amplitudeHistory.length > 0 && (
                    <div className="flex items-end gap-0.5 h-12 w-48">
                      {amplitudeHistory.map((amp, i) => (
                        <div key={i} className="flex-1 bg-red-400/60 rounded-t transition-all duration-100"
                          style={{ height: `${Math.max(2, amp * 100)}%` }} />
                      ))}
                    </div>
                  )}

                  {/* Timer + file size */}
                  <div className="text-center">
                    <span className="text-3xl font-mono text-parchment/90 tabular-nums tracking-wider">
                      {String(Math.floor(displaySeconds / 60)).padStart(2, '0')}:{String(displaySeconds % 60).padStart(2, '0')}
                    </span>
                    {recordingActive && recordingFileSize != null && recordingFileSize > 0 && (
                      <p className="text-xs text-parchment/40 font-mono tabular-nums mt-1">
                        {recordingFileSize < 1024 ? `${recordingFileSize} B`
                          : recordingFileSize < 1024 * 1024 ? `${(recordingFileSize / 1024).toFixed(1)} KB`
                          : recordingFileSize < 1024 * 1024 * 1024 ? `${(recordingFileSize / (1024 * 1024)).toFixed(1)} MB`
                          : `${(recordingFileSize / (1024 * 1024 * 1024)).toFixed(2)} GB`}
                      </p>
                    )}
                    {recordingPaused && (
                      <p className="text-xs text-amber-400/70 font-body mt-2 uppercase tracking-widest">Paused</p>
                    )}
                    {!recordingActive && displaySeconds > 0 && (
                      <p className="text-xs text-emerald-400/70 font-body mt-2">Recording complete</p>
                    )}
                  </div>

                  {/* Controls */}
                  {recordingActive && (
                    <div className="flex items-center gap-3">
                      {recordingPaused ? (
                        <button onClick={onResumeRecording}
                          className="flex items-center gap-2 px-4 py-2 rounded-md bg-gold/15 border border-gold/25 text-sm font-heading text-gold/80 hover:bg-gold/20 transition-colors">
                          <Play className="w-4 h-4" />Resume
                        </button>
                      ) : (
                        <button onClick={onPauseRecording}
                          className="flex items-center gap-2 px-4 py-2 rounded-md bg-white/5 border border-white/15 text-sm font-heading text-parchment/60 hover:bg-white/8 transition-colors">
                          <Pause className="w-4 h-4" />Pause
                        </button>
                      )}
                      <button onClick={() => setShowStopConfirm(true)}
                        className="flex items-center gap-2 px-4 py-2 rounded-md bg-red-500/10 border border-red-500/25 text-sm font-heading text-red-400/80 hover:bg-red-500/15 transition-colors">
                        <Square className="w-4 h-4 fill-current" />Stop
                      </button>
                    </div>
                  )}

                  {/* Stop confirmation dialog */}
                  {showStopConfirm && (
                    <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-4 space-y-3 w-full max-w-xs">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                        <span className="text-xs font-heading text-amber-400/80 uppercase tracking-widest">Stop Recording?</span>
                      </div>
                      <p className="text-xs text-parchment/50 font-body">This will stop recording and begin transcription.</p>
                      <div className="flex items-center gap-2">
                        <button onClick={() => { setShowStopConfirm(false); if (!recordingPaused) onPauseRecording?.() }}
                          className="flex-1 py-1.5 rounded border border-white/10 text-xs text-parchment/50 hover:bg-white/5 transition-colors">
                          Pause Instead
                        </button>
                        <button onClick={() => { setShowStopConfirm(false); onStopRecording?.() }}
                          className="flex-1 py-1.5 rounded bg-red-500/15 border border-red-500/25 text-xs text-red-400 hover:bg-red-500/20 transition-colors">
                          Stop &amp; Transcribe
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Speaker review */}
              {activeStage === 'speaker_mapping' && activeState.status === 'needs_review' && speakerReview && (
                <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                    <span className="text-xs font-heading text-amber-400/80 uppercase tracking-widest">Map Speakers</span>
                  </div>
                  <div className="space-y-3">
                    {/* Sort speakers: low confidence first */}
                    {[...speakerReview.unmappedSpeakers]
                      .sort((a, b) => (speakerReview.confidences?.[a] ?? 50) - (speakerReview.confidences?.[b] ?? 50))
                      .map(sp => {
                        const conf = speakerReview.confidences?.[sp]
                        const ev = speakerReview.evidence?.[sp]
                        return (
                          <div key={sp} className="space-y-1.5">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-mono text-parchment/50 w-16 flex-none">{sp}</span>
                              <select value={speakerMap[sp] || ''} onChange={e => setSpeakerMap(p => ({ ...p, [sp]: e.target.value }))}
                                className="flex-1 bg-void/80 border border-white/10 rounded px-2 py-1 text-xs text-parchment/80 outline-none focus:border-gold/40" style={{ colorScheme: 'dark' }}>
                                <option value="">— skip —</option>
                                {speakerReview.characterNames.map(n => <option key={n} value={n}>{n}</option>)}
                              </select>
                              {conf !== undefined && (
                                <span className={cn(
                                  'text-[10px] font-mono px-1.5 py-0.5 rounded border',
                                  conf >= 90 ? 'text-emerald-400/70 border-emerald-400/20 bg-emerald-400/5' :
                                  conf >= 70 ? 'text-amber-400/70 border-amber-400/20 bg-amber-400/5' :
                                  'text-red-400/70 border-red-400/20 bg-red-400/5'
                                )}>
                                  {conf}%
                                </span>
                              )}
                            </div>
                            {ev && (
                              <p className="text-[10px] italic text-parchment/35 font-body leading-snug pl-[4.5rem]">{ev}</p>
                            )}
                            {speakerReview.sampleLines?.[sp]?.slice(0, 3).map((line, i) => (
                              <p key={i} className="text-[10px] italic text-parchment/25 font-body leading-snug pl-[4.5rem] line-clamp-2">"{line}"</p>
                            ))}
                          </div>
                        )
                      })}
                  </div>
                  <button onClick={() => api('complete_speaker_mapping', speakerReview.jsonPath, speakerMap)}
                    className="w-full flex items-center justify-center gap-1.5 py-2 rounded bg-gold/15 border border-gold/25 text-xs font-heading text-gold/80 hover:bg-gold/20 transition-colors">
                    <Check className="w-3.5 h-3.5" />Confirm Mapping
                  </button>
                </div>
              )}

              {/* Completed speaker mapping (read-only) */}
              {activeStage === 'speaker_mapping' && activeState.status === 'done' && activeState.data?.mapping && (
                <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-xs font-heading text-emerald-400/80 uppercase tracking-widest">Speaker Mapping Applied</span>
                  </div>
                  <div className="space-y-1.5">
                    {Object.entries(activeState.data.mapping as Record<string, string>).map(([sp, name]) => (
                      <div key={sp} className="flex items-center gap-2">
                        <span className="text-xs font-mono text-parchment/40 w-24 flex-none">{sp}</span>
                        <span className="text-xs text-parchment/30">→</span>
                        <span className="text-xs font-body text-gold/70">{name || '(skipped)'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Fact review */}
              {activeStage === 'fact_review' && activeState.status === 'needs_review' && factReview && (
                <FactReviewPanel
                  payload={factReview}
                  onSubmit={(decisions) => api('complete_fact_review', decisions)}
                />
              )}

              {/* Entity review */}
              {entityReview && activeState.status === 'needs_review' && entityReview.stage === activeStage && (
                <EntityReviewPanel
                  payload={entityReview}
                  onSubmit={(stage, decisions) => api('complete_entity_review', stage, decisions)}
                />
              )}

              {/* Error */}
              {activeState.status === 'error' && activeState.error && (
                <div className="flex items-start gap-2 rounded-md bg-red-500/8 border border-red-500/20 px-3 py-2.5">
                  <XCircle className="w-3.5 h-3.5 text-red-400 flex-none mt-0.5" />
                  <p className="text-xs text-red-400 font-body">{activeState.error}</p>
                </div>
              )}

              {/* LLM streaming output */}
              {activeStage !== 'recording' && LLM_STAGES.includes(activeStage) && chunk && (
                <div className="rounded-md border border-white/8 overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 bg-void/60 border-b border-white/5">
                    <span className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Output</span>
                    <div className="flex items-center gap-1">
                      {stages[activeStage].status === 'running' && (
                        <button onClick={() => onStopLLMStage(activeStage)}
                          className="flex items-center gap-1 px-2 py-0.5 rounded border border-white/10 text-[10px] text-parchment/35 hover:text-red-400 hover:border-red-400/30 transition-colors">
                          <Square className="w-2.5 h-2.5 fill-current" />Stop
                        </button>
                      )}
                      <CopyButton text={chunk} />
                    </div>
                  </div>
                  <pre className="px-3 py-2.5 text-[10px] text-parchment/65 font-mono leading-relaxed whitespace-pre-wrap break-words max-h-[60vh] overflow-y-auto">
                    {chunk}
                  </pre>
                </div>
              )}

              {/* Transcription log */}
              {activeStage === 'transcription' && (
                <div className="rounded-md border border-white/6 bg-void/40">
                  <div className="px-3 py-1.5 border-b border-white/5">
                    <span className="text-[10px] font-heading text-parchment/35 uppercase tracking-widest">Log</span>
                  </div>
                  <div className="max-h-[60vh] overflow-y-auto px-3 py-2 space-y-px">
                    {logLines.slice(-200).map((l, i) => (
                      <p key={i} className={cn('text-[10px] font-mono leading-relaxed', LINE_COLORS[classifyLine(l.text)])}>
                        {l.text}
                      </p>
                    ))}
                    <div ref={logEndRef} />
                  </div>
                </div>
              )}

              {/* Illustration preview when done */}
              {activeStage === 'illustration' && activeState.status === 'done' && activeState.data?.illustration && (
                <div className="rounded-md border border-white/8 overflow-hidden">
                  <div className="px-3 py-2 bg-void/60 border-b border-white/5">
                    <span className="text-[10px] font-heading text-parchment/40 uppercase tracking-widest">Generated Illustration</span>
                  </div>
                  <div className="p-2">
                    <img
                      src={`file://${activeState.data.illustration}`}
                      alt="Session illustration"
                      className="w-full rounded border border-white/5"
                    />
                  </div>
                </div>
              )}

              {activeState.status === 'done' && !chunk && !(activeStage === 'illustration' && activeState.data?.illustration) && (
                <StagePreview stage={activeStage} data={activeState.data} />
              )}
              {activeState.status === 'idle' && (
                <div className="flex items-center gap-3 py-4">
                  <p className="text-xs text-parchment/25 font-body">Waiting…</p>
                  {activeStage !== 'recording' && SKIPPABLE_STAGES.includes(activeStage) && (
                    <button onClick={() => onSkipStage(activeStage as PipelineStage)}
                      className="flex items-center gap-1 px-2 py-0.5 rounded border border-white/10 text-[10px] text-parchment/35 hover:text-gold hover:border-gold/30 transition-colors">
                      <SkipForward className="w-2.5 h-2.5" />Skip
                    </button>
                  )}
                </div>
              )}

              {/* Pipeline completion CTA */}
              {!recordingActive && onNavigateToLibrary && STAGE_ORDER.every(s => {
                const st = stages[s.id]?.status
                return st === 'done' || st === 'error'
              }) && (
                <div className="py-6 flex flex-col items-center gap-3">
                  <p className="text-xs text-emerald-400/60 font-body">Pipeline complete</p>
                  <button
                    onClick={onNavigateToLibrary}
                    className="flex items-center gap-2 px-4 py-2 rounded-md border border-gold/30 bg-gold/10 text-sm font-heading text-gold hover:bg-gold/20 hover:border-gold/50 transition-colors uppercase tracking-wider"
                  >
                    <BookOpen className="w-4 h-4" />
                    View in Library
                  </button>
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  )
}

// ── Stage Preview (completed stage data summaries) ──────────────────────

function StagePreview({ stage, data }: { stage: string; data?: any }) {
  const d = data || {}

  // Timeline: show first 3 events
  if (stage === 'timeline' && Array.isArray(d.timeline) && d.timeline.length > 0) {
    return (
      <div className="space-y-1 py-2">
        <p className="text-[9px] text-parchment/30 uppercase tracking-widest font-heading mb-1">{d.timeline.length} events</p>
        {d.timeline.slice(0, 3).map((ev: any, i: number) => (
          <div key={i} className="flex items-start gap-2">
            <span className="text-[9px] text-gold/40 font-mono shrink-0 w-12">{ev.time || '—'}</span>
            <span className="text-[10px] text-parchment/60 font-body">{ev.title}</span>
          </div>
        ))}
        {d.timeline.length > 3 && <p className="text-[9px] text-parchment/25 italic">+{d.timeline.length - 3} more</p>}
      </div>
    )
  }

  // Summary: show word count
  if (stage === 'summary' && d.summary) {
    const words = String(d.summary).split(/\s+/).length
    return (
      <div className="flex items-center gap-2 text-emerald-400/70 py-3">
        <CheckCircle2 className="w-4 h-4" />
        <span className="text-xs font-body">Summary generated ({words} words)</span>
      </div>
    )
  }

  // DM Notes
  if (stage === 'dm_notes' && d.notes) {
    const lines = String(d.notes).split('\n').filter((l: string) => l.trim()).length
    return (
      <div className="flex items-center gap-2 text-emerald-400/70 py-3">
        <CheckCircle2 className="w-4 h-4" />
        <span className="text-xs font-body">DM notes generated ({lines} lines)</span>
      </div>
    )
  }

  // Character updates
  if (stage === 'character_updates' && d.updates) {
    const count = typeof d.updates === 'object' ? Object.keys(d.updates).length : 0
    return (
      <div className="flex items-center gap-2 text-emerald-400/70 py-3">
        <CheckCircle2 className="w-4 h-4" />
        <span className="text-xs font-body">{count} character{count !== 1 ? 's' : ''} updated</span>
      </div>
    )
  }

  // Glossary
  if (stage === 'glossary' && d.glossary) {
    const terms = typeof d.glossary === 'object' ? Object.keys(d.glossary) : []
    const sample = terms.slice(0, 5).join(', ')
    return (
      <div className="py-2 space-y-1">
        <div className="flex items-center gap-2 text-emerald-400/70">
          <CheckCircle2 className="w-4 h-4" />
          <span className="text-xs font-body">{terms.length} term{terms.length !== 1 ? 's' : ''} extracted</span>
        </div>
        {sample && <p className="text-[10px] text-parchment/35 font-body pl-6 truncate">{sample}{terms.length > 5 ? '…' : ''}</p>}
      </div>
    )
  }

  // Leaderboard
  if (stage === 'leaderboard' && d.leaderboard) {
    const count = typeof d.leaderboard === 'object' ? Object.keys(d.leaderboard).length : 0
    return (
      <div className="flex items-center gap-2 text-emerald-400/70 py-3">
        <CheckCircle2 className="w-4 h-4" />
        <span className="text-xs font-body">Leaderboard — {count} hero{count !== 1 ? 'es' : ''}</span>
      </div>
    )
  }

  // Locations / NPCs / Loot / Missions — array or object counts
  if (['locations', 'npcs', 'missions'].includes(stage)) {
    const items = d[stage]
    const count = Array.isArray(items) ? items.length : typeof items === 'object' && items ? Object.keys(items).length : 0
    if (count > 0) {
      return (
        <div className="flex items-center gap-2 text-emerald-400/70 py-3">
          <CheckCircle2 className="w-4 h-4" />
          <span className="text-xs font-body">{count} {stage === 'npcs' ? 'NPC' : stage.replace(/s$/, '')}
            {count !== 1 ? 's' : ''} extracted</span>
        </div>
      )
    }
  }

  if (stage === 'loot' && d.loot) {
    const items = d.loot.items || d.loot
    const count = Array.isArray(items) ? items.length : typeof items === 'object' ? Object.keys(items).length : 0
    return (
      <div className="flex items-center gap-2 text-emerald-400/70 py-3">
        <CheckCircle2 className="w-4 h-4" />
        <span className="text-xs font-body">{count} loot entr{count !== 1 ? 'ies' : 'y'} extracted</span>
      </div>
    )
  }

  // Fact extraction
  if (stage === 'fact_extraction' && d.factCount !== undefined) {
    return (
      <div className="flex items-center gap-2 text-emerald-400/70 py-3">
        <CheckCircle2 className="w-4 h-4" />
        <span className="text-xs font-body">{d.factCount} facts extracted (threshold: {d.threshold}%{d.reviewCount ? `, ${d.reviewCount} for review` : ''})</span>
      </div>
    )
  }

  // Fact review
  if (stage === 'fact_review' && d.decisions !== undefined) {
    return (
      <div className="flex items-center gap-2 text-emerald-400/70 py-3">
        <CheckCircle2 className="w-4 h-4" />
        <span className="text-xs font-body">{d.decisions} fact{d.decisions !== 1 ? 's' : ''} reviewed</span>
      </div>
    )
  }

  // Speaker mapping — already has its own preview via the readonly mapping display
  if (stage === 'speaker_mapping' && d.mapping) {
    const entries = Object.entries(d.mapping as Record<string, string>)
    if (entries.length > 0) {
      return (
        <div className="py-2 space-y-0.5">
          <p className="text-[9px] text-parchment/30 uppercase tracking-widest font-heading mb-1">Speaker mapping</p>
          {entries.map(([spk, name]) => (
            <div key={spk} className="flex items-center gap-2">
              <span className="text-[9px] font-mono text-parchment/30 w-20 shrink-0">{spk}</span>
              <span className="text-[10px] text-gold/60 font-body">{name}</span>
            </div>
          ))}
        </div>
      )
    }
  }

  // Skipped stages
  if (d.skipped) {
    return (
      <div className="flex items-center gap-2 text-parchment/30 py-3">
        <SkipForward className="w-3.5 h-3.5" />
        <span className="text-xs font-body italic">Skipped</span>
      </div>
    )
  }

  // Default fallback
  return (
    <div className="flex items-center gap-2 text-emerald-400/70 py-3">
      <CheckCircle2 className="w-4 h-4" />
      <span className="text-xs font-body">Stage complete</span>
    </div>
  )
}

// ── Fact Review Panel ────────────────────────────────────────────────────

function FactReviewPanel({
  payload,
  onSubmit,
}: {
  payload: FactReviewPayload
  onSubmit: (decisions: Array<{ id: string; action: 'accept' | 'edit' | 'decline'; segment_indices?: number[]; speaker?: string; edited?: Record<string, any> }>) => void
}) {
  type Decision = 'accept' | 'edit' | 'decline'
  const [decisions, setDecisions] = useState<Record<string, { action: Decision; edited?: Record<string, any> }>>({})
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editState, setEditState] = useState<Record<string, any>>({})
  const [submitting, setSubmitting] = useState(false)
  const [showAutoApplied, setShowAutoApplied] = useState(false)

  const allDecided = payload.cards.length === 0 || payload.cards.every(c => decisions[c.id])
  const autoSubmitRef = useRef(false)

  // Auto-submit when all decisions are made
  useEffect(() => {
    if (allDecided && payload.cards.length > 0 && !autoSubmitRef.current && !submitting) {
      autoSubmitRef.current = true
      handleSubmit()
    }
  }, [allDecided])

  // If no cards to review (all auto-applied), auto-submit immediately
  useEffect(() => {
    if (payload.cards.length === 0 && !submitting) {
      handleSubmit()
    }
  }, [])

  function setDecision(id: string, action: Decision, card: FactCard) {
    setDecisions(prev => ({
      ...prev,
      [id]: { action, edited: action === 'edit' ? editState : undefined },
    }))
    if (action !== 'edit') setEditingId(null)
  }

  function startEdit(card: FactCard) {
    setEditingId(card.id)
    setEditState({
      who: card.who,
      what: card.what,
      why: card.why,
      when: card.when,
      speaker: card.speaker,
    })
  }

  function confirmEdit(card: FactCard) {
    setDecisions(prev => ({
      ...prev,
      [card.id]: { action: 'edit', edited: { ...editState } },
    }))
    setEditingId(null)
  }

  function batchAction(action: Decision) {
    const bulk: Record<string, { action: Decision }> = {}
    payload.cards.forEach(c => { bulk[c.id] = { action } })
    setDecisions(bulk)
  }

  async function handleSubmit() {
    setSubmitting(true)
    const result = payload.cards.map(c => {
      const d = decisions[c.id] || { action: 'accept' as Decision }
      return {
        id: c.id,
        action: d.action as 'accept' | 'edit' | 'decline',
        segment_indices: c.segment_indices,
        speaker: c.speaker,
        who: c.who,
        edited: d.edited,
      }
    })
    await onSubmit(result)
    setSubmitting(false)
  }

  const confColor = (conf: number) =>
    conf >= 90 ? 'text-emerald-400/70 border-emerald-400/20 bg-emerald-400/5' :
    conf >= 70 ? 'text-amber-400/70 border-amber-400/20 bg-amber-400/5' :
    'text-red-400/70 border-red-400/20 bg-red-400/5'

  const TYPE_COLORS: Record<string, string> = {
    action: 'text-blue-400/70 border-blue-400/20',
    dialogue: 'text-parchment/50 border-parchment/15',
    event: 'text-purple-400/70 border-purple-400/20',
    decision: 'text-gold/70 border-gold/20',
    discovery: 'text-emerald-400/70 border-emerald-400/20',
    combat: 'text-red-400/70 border-red-400/20',
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <ClipboardCheck className="w-4 h-4 text-gold/60" />
        <div className="flex-1">
          <h3 className="text-sm font-heading text-parchment/80 uppercase tracking-widest">
            Review Facts
          </h3>
          <p className="text-[10px] font-body text-parchment/40 mt-0.5">
            Review extracted facts. Edit speaker attributions or details if the AI got something wrong.
          </p>
        </div>
      </div>

      {/* Auto-applied summary */}
      {payload.auto_applied.length > 0 && (
        <div className="rounded-md border border-emerald-500/15 bg-emerald-500/5 px-3 py-2">
          <button onClick={() => setShowAutoApplied(!showAutoApplied)}
            className="flex items-center gap-2 w-full text-left">
            <CheckCircle2 className="w-3 h-3 text-emerald-400/60" />
            <span className="text-[10px] font-heading text-emerald-400/60 uppercase tracking-widest">
              {payload.auto_applied.length} facts auto-accepted (high confidence)
            </span>
            <ChevronDown className={cn('w-3 h-3 text-emerald-400/40 ml-auto transition-transform', showAutoApplied && 'rotate-180')} />
          </button>
          {showAutoApplied && (
            <div className="mt-2 space-y-1 pl-5">
              {payload.auto_applied.map(f => (
                <p key={f.id} className="text-[10px] text-parchment/35 font-body">
                  <span className="text-gold/50">{f.who}</span> — {f.what}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Batch actions */}
      {payload.cards.length > 1 && (
        <div className="flex items-center gap-2">
          <button onClick={() => batchAction('accept')}
            className="px-2 py-0.5 rounded border border-emerald-400/20 text-[10px] text-emerald-400/60 hover:bg-emerald-400/10 transition-colors">
            Accept All
          </button>
          <button onClick={() => batchAction('decline')}
            className="px-2 py-0.5 rounded border border-red-400/20 text-[10px] text-red-400/60 hover:bg-red-400/10 transition-colors">
            Decline All
          </button>
        </div>
      )}

      {/* Review cards */}
      <div className="space-y-2">
        {payload.cards.map(card => {
          const d = decisions[card.id]
          const isEditing = editingId === card.id
          const isDecided = !!d
          const isCollapsed = isDecided && !isEditing
          const displayWho = (isDecided && d.edited?.who) || card.who
          const displayWhat = (isDecided && d.edited?.what) || card.what

          return (
            <div key={card.id} className={cn(
              'rounded-md border transition-all',
              isCollapsed ? 'px-3 py-2' : 'p-3',
              isDecided && d.action === 'accept' ? 'border-emerald-400/15 bg-emerald-400/5' :
              isDecided && d.action === 'decline' ? 'border-red-400/15 bg-red-400/5' :
              isDecided && d.action === 'edit' ? 'border-gold/20 bg-gold/5' :
              'border-white/10 bg-void/40',
            )}>
              {/* Collapsed compact header */}
              {isCollapsed && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-heading text-gold/60 shrink-0">{displayWho}</span>
                  <span className={cn('text-[9px] font-mono px-1 py-0.5 rounded border shrink-0', TYPE_COLORS[card.type] || TYPE_COLORS.event)}>
                    {card.type}
                  </span>
                  <span className="text-[10px] text-parchment/40 font-body truncate flex-1">{displayWhat}</span>
                  <span className={cn('text-[9px] font-mono px-1 py-0.5 rounded shrink-0',
                    d.action === 'accept' ? 'text-emerald-400/80 bg-emerald-400/10' :
                    d.action === 'decline' ? 'text-red-400/80 bg-red-400/10' :
                    'text-gold/80 bg-gold/10',
                  )}>
                    {d.action}
                  </span>
                  <button onClick={() => setDecisions(prev => { const next = { ...prev }; delete next[card.id]; return next })}
                    className="text-[10px] text-parchment/25 hover:text-parchment/50 transition-colors shrink-0">
                    ↩
                  </button>
                </div>
              )}

              {/* Full card body — hidden when collapsed */}
              <div className={cn('transition-all duration-300 overflow-hidden',
                isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[2000px] opacity-100'
              )}>
                {/* Card header */}
                <div className="flex items-start gap-2 mb-2">
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-heading text-gold/80">{card.who}</span>
                      <span className={cn('text-[9px] font-mono px-1 py-0.5 rounded border', TYPE_COLORS[card.type] || TYPE_COLORS.event)}>
                        {card.type}
                      </span>
                      <span className={cn('text-[9px] font-mono px-1 py-0.5 rounded border', confColor(card.confidence))}>
                        {card.confidence}%
                      </span>
                    </div>
                    <p className="text-[11px] text-parchment/70 font-body leading-snug">{card.what}</p>
                    {card.why && (
                      <p className="text-[10px] text-parchment/40 font-body italic">Why: {card.why}</p>
                    )}
                    {card.when && (
                      <p className="text-[10px] text-parchment/35 font-body">When: {card.when}</p>
                    )}
                  </div>
                </div>

                {/* Speaker + original text */}
                <div className="mb-2 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] text-parchment/30 uppercase tracking-widest">Speaker:</span>
                    <span className="text-[10px] font-mono text-parchment/50">{card.speaker}</span>
                  </div>
                  {card.original_text && (
                    <pre className="text-[9px] text-parchment/30 font-mono leading-relaxed bg-void/60 rounded px-2 py-1.5 whitespace-pre-wrap max-h-32 overflow-y-auto">
                      {card.original_text}
                    </pre>
                  )}
                  {card.reasoning && (
                    <p className="text-[9px] italic text-parchment/25 font-body">{card.reasoning}</p>
                  )}
                </div>

                {/* Edit mode */}
                {isEditing && (
                  <div className="space-y-2 mb-2 p-2 rounded border border-gold/15 bg-gold/5">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-[9px] text-parchment/40 uppercase tracking-widest">Who</label>
                        <input value={editState.who || ''} onChange={e => setEditState(s => ({ ...s, who: e.target.value }))}
                          className="w-full bg-void/80 border border-white/10 rounded px-2 py-1 text-[10px] text-parchment/80 outline-none mt-0.5" />
                      </div>
                      <div>
                        <label className="text-[9px] text-parchment/40 uppercase tracking-widest">Speaker</label>
                        <select value={editState.speaker || ''} onChange={e => setEditState(s => ({ ...s, speaker: e.target.value }))}
                          className="w-full bg-void/80 border border-white/10 rounded px-2 py-1 text-[10px] text-parchment/80 outline-none mt-0.5" style={{ colorScheme: 'dark' }}>
                          {payload.character_names.map(n => <option key={n} value={n}>{n}</option>)}
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="text-[9px] text-parchment/40 uppercase tracking-widest">What</label>
                      <textarea value={editState.what || ''} onChange={e => setEditState(s => ({ ...s, what: e.target.value }))}
                        className="w-full bg-void/80 border border-white/10 rounded px-2 py-1 text-[10px] text-parchment/80 outline-none mt-0.5 resize-y min-h-[3rem]" />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-[9px] text-parchment/40 uppercase tracking-widest">Why</label>
                        <input value={editState.why || ''} onChange={e => setEditState(s => ({ ...s, why: e.target.value }))}
                          className="w-full bg-void/80 border border-white/10 rounded px-2 py-1 text-[10px] text-parchment/80 outline-none mt-0.5" />
                      </div>
                      <div>
                        <label className="text-[9px] text-parchment/40 uppercase tracking-widest">When</label>
                        <input value={editState.when || ''} onChange={e => setEditState(s => ({ ...s, when: e.target.value }))}
                          className="w-full bg-void/80 border border-white/10 rounded px-2 py-1 text-[10px] text-parchment/80 outline-none mt-0.5" />
                      </div>
                    </div>
                    <button onClick={() => confirmEdit(card)}
                      className="flex items-center gap-1 px-2 py-1 rounded bg-gold/15 border border-gold/25 text-[10px] text-gold/80 hover:bg-gold/25 transition-colors">
                      <Check className="w-3 h-3" />Confirm Edit
                    </button>
                  </div>
                )}

                {/* Action buttons */}
                {!isDecided && !isEditing && (
                  <div className="flex items-center gap-2">
                    <button onClick={() => setDecision(card.id, 'accept', card)}
                      className="px-2 py-0.5 rounded border border-emerald-400/20 text-[10px] text-emerald-400/60 hover:bg-emerald-400/10 transition-colors">
                      Accept
                    </button>
                    <button onClick={() => startEdit(card)}
                      className="px-2 py-0.5 rounded border border-gold/20 text-[10px] text-gold/60 hover:bg-gold/10 transition-colors">
                      Edit
                    </button>
                    <button onClick={() => setDecision(card.id, 'decline', card)}
                      className="px-2 py-0.5 rounded border border-red-400/20 text-[10px] text-red-400/60 hover:bg-red-400/10 transition-colors">
                      Decline
                    </button>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Submit */}
      {payload.cards.length > 0 && (
        <button
          onClick={handleSubmit}
          disabled={!allDecided || submitting}
          className={cn(
            'w-full flex items-center justify-center gap-2 py-2 rounded-md text-xs font-heading uppercase tracking-widest transition-all',
            !allDecided || submitting
              ? 'bg-white/5 text-parchment/30 border border-white/10 cursor-not-allowed'
              : 'bg-emerald-400/15 text-emerald-400 border border-emerald-400/25 hover:bg-emerald-400/25',
          )}
        >
          {submitting
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : <Check className="w-3.5 h-3.5" />
          }
          Approve & Continue
        </button>
      )}
    </div>
  )
}
