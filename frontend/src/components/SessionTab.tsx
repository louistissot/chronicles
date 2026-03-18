import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api, Campaign, Season, Character, type PipelineStage, type SpeakerReviewPayload, type EntityReviewPayload } from '@/lib/api'
import {
  FileAudio, Sword, Mic, Square, Circle, Loader2,
  Plus, Trash2, BookOpen, ChevronDown, ChevronUp, Pencil, Check, X, FileUp,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { CharacterPicker } from '@/components/CampaignsTab'
import { InlinePipelineView } from '@/components/InlinePipelineView'
import type { PipelineStages } from '@/App'

// ── Constants ──────────────────────────────────────────────────────────────

const MODELS = [
  { value: 'large-v3', label: 'large-v3 — Best accuracy' },
  { value: 'large-v2', label: 'large-v2 — Recommended' },
  { value: 'medium',   label: 'medium — Balanced' },
  { value: 'small',    label: 'small — Fast' },
  { value: 'base',     label: 'base — Fastest' },
  { value: 'tiny',     label: 'tiny — Minimal' },
]

const LANGUAGES = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'en',   label: 'English' },
  { value: 'fr',   label: 'French' },
  { value: 'de',   label: 'German' },
  { value: 'es',   label: 'Spanish' },
  { value: 'it',   label: 'Italian' },
  { value: 'pt',   label: 'Portuguese' },
  { value: 'nl',   label: 'Dutch' },
  { value: 'ru',   label: 'Russian' },
  { value: 'zh',   label: 'Chinese' },
  { value: 'ja',   label: 'Japanese' },
  { value: 'ko',   label: 'Korean' },
]


function formatDuration(secs: number): string {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60).toString().padStart(2, '0')
  const s = Math.floor(secs % 60).toString().padStart(2, '0')
  return h > 0 ? `${h}:${m}:${s}` : `${m}:${s}`
}

// ── Props ─────────────────────────────────────────────────────────────────

interface SessionTabProps {
  onSessionStarted: (sessionDir: string, characterNames: string[]) => void
  onRecordingStarted: (sessionDir: string, characterNames: string[]) => void
  onRun: (
    audioPath: string,
    model: string,
    numSpeakers: number,
    characterNames: string[],
    language: string
  ) => void
  isRunning: boolean
  autoNewCampaign?: boolean
  prefillCampaignId?: string
  prefillSeasonId?: string
  pendingDrop?: { type: 'audio' | 'transcript'; path: string } | null
  onDropHandled?: () => void
  dragOver?: 'audio' | 'transcript' | null
  /** Called when user cancels campaign creation during the NEW GAME funnel */
  onCancelToTitle?: () => void
  /** Called when a campaign is successfully created during the NEW GAME funnel */
  onFunnelComplete?: () => void
  // Pipeline state — for processing mode
  pipelineActive: boolean
  pipelineStages: PipelineStages
  speakerReview: SpeakerReviewPayload | null
  entityReview: EntityReviewPayload | null
  factReview: import('@/lib/api').FactReviewPayload | null
  logLines: Array<{ text: string; isStderr: boolean }>
  logVersion: number
  streamingChunks: Record<PipelineStage, string>
  streamingVersion: number
  onStop: () => void
  onStopLLMStage: (stage: PipelineStage) => void
  onSkipStage: (stage: PipelineStage) => void
  recordingActive: boolean
  recordingPaused: boolean
  recordingSeconds: number
  recordingAmplitude?: number
  recordingFileSize?: number
  amplitudeHistory?: number[]
  onPauseRecording: () => void
  onResumeRecording: () => void
  onStopRecording: () => void
  /** Show processing view */
  showProcessing: boolean
  /** Navigate back to setup from processing */
  onBackToSetup: () => void
  /** Navigate to library after pipeline completes */
  onNavigateToLibrary?: () => void
}

// ── Main component ────────────────────────────────────────────────────────

export function SessionTab({
  onSessionStarted, onRecordingStarted, onRun, isRunning, autoNewCampaign, prefillCampaignId, prefillSeasonId,
  pendingDrop, onDropHandled, dragOver, onCancelToTitle, onFunnelComplete,
  pipelineActive, pipelineStages, speakerReview, entityReview, factReview,
  logLines, logVersion, streamingChunks, streamingVersion,
  onStop, onStopLLMStage, onSkipStage,
  recordingActive, recordingPaused, recordingSeconds,
  recordingAmplitude, recordingFileSize, amplitudeHistory,
  onPauseRecording, onResumeRecording, onStopRecording,
  showProcessing, onBackToSetup, onNavigateToLibrary,
}: SessionTabProps) {
  // Initial loading
  const [initialLoading, setInitialLoading] = useState(true)

  // Campaign / season
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [selectedCampaignId, setSelectedCampaignId] = useState('')
  const [selectedSeasonId, setSelectedSeasonId] = useState('')

  // All global characters (for CharacterPicker)
  const [allCharacters, setAllCharacters] = useState<Character[]>([])

  // Create campaign form
  const [showNewCampaign, setShowNewCampaign] = useState(false)
  const [newCampaignName, setNewCampaignName] = useState('')
  const [newSeasonNum, setNewSeasonNum] = useState(1)
  const [newCharIds, setNewCharIds] = useState<string[]>([])
  const [campaignError, setCampaignError] = useState<string | null>(null)

  // Add season form
  const [showNewSeason, setShowNewSeason] = useState(false)
  const [addSeasonNum, setAddSeasonNum] = useState(2)
  const [addSeasonCharIds, setAddSeasonCharIds] = useState<string[]>([])

  // Edit season
  const [editingSeasonId, setEditingSeasonId] = useState<string | null>(null)
  const [editCharIds, setEditCharIds] = useState<string[]>([])

  // Transcription settings
  const [model, setModel] = useState('large-v2')
  const [language, setLanguage] = useState('auto')

  // Optional artifact selection (illustration + glossary always run — not listed here)
  const [selectedArtifacts, setSelectedArtifacts] = useState<Record<string, boolean>>({
    timeline: true, summary: true, dm_notes: true, character_updates: true,
    leaderboard: true, locations: true, npcs: true, loot: true, missions: true,
  })

  // Session state — reset when campaign/season changes
  const [sessionDir, setSessionDir] = useState<string | null>(null)
  const [audioPath, setAudioPath] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [recordDuration, setRecordDuration] = useState(0)
  const [recordError, setRecordError] = useState<string | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Import transcript state
  const [importTranscriptPath, setImportTranscriptPath] = useState('')
  const [importDate, setImportDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [isImporting, setIsImporting] = useState(false)
  const [importDiarized, setImportDiarized] = useState(true)

  // Collapsible sections
  const [audioExpanded, setAudioExpanded] = useState(false)
  const [transcriptExpanded, setTranscriptExpanded] = useState(false)

  // ── Derived ──────────────────────────────────────────────────────────────

  const selectedCampaign = campaigns.find(c => c.id === selectedCampaignId)
  const selectedSeason = selectedCampaign?.seasons.find(s => s.id === selectedSeasonId)
  const characterNames = (selectedSeason?.characters ?? [])
    .map(id => allCharacters.find(c => c.id === id)?.name || '')
    .filter(Boolean)
  const numSpeakers = Math.max(1, characterNames.length)
  const canProceed = !!selectedSeason

  const isTranscribing = pipelineStages.transcription.status === 'running'

  // ── Load on mount ─────────────────────────────────────────────────────────

  useEffect(() => {
    async function load() {
      const [camps, chars, savedCampId, savedSeasonId, savedModel, savedLang] = await Promise.all([
        api('get_campaigns'),
        api('get_characters'),
        api('get_pref', 'selected_campaign_id', ''),
        api('get_pref', 'selected_season_id', ''),
        api('get_pref', 'model', 'large-v2'),
        api('get_pref', 'language', 'auto'),
      ])
      const campaignList = (camps as Campaign[]) ?? []
      setCampaigns(campaignList)
      setAllCharacters((chars as Character[]) ?? [])

      // Prefill from "Continue" takes priority over saved prefs
      const campId  = prefillCampaignId || savedCampId
      const seasonId = prefillSeasonId  || savedSeasonId

      if (campId) setSelectedCampaignId(campId)
      if (seasonId) setSelectedSeasonId(seasonId)
      setModel(savedModel)
      setLanguage(savedLang)

      if (!campId && campaignList.length === 1) {
        const c = campaignList[0]
        setSelectedCampaignId(c.id)
        api('set_pref', 'selected_campaign_id', c.id)
        if (c.seasons.length === 1) {
          setSelectedSeasonId(c.seasons[0].id)
          api('set_pref', 'selected_season_id', c.seasons[0].id)
        }
      }

      // If launched from "NEW GAME", open the new campaign form (unless campaigns exist and user should pick)
      if (autoNewCampaign) {
        setShowNewCampaign(true)
      } else {
        setShowNewCampaign(false)
      }

      setInitialLoading(false)
    }
    load()
  }, [autoNewCampaign, prefillCampaignId, prefillSeasonId])

  // Handle files dropped via native macOS drag-and-drop
  useEffect(() => {
    if (!pendingDrop) return
    if (pendingDrop.type === 'audio') {
      setAudioPath(pendingDrop.path)
      setAudioExpanded(true)
    } else {
      setImportTranscriptPath(pendingDrop.path)
      setTranscriptExpanded(true)
    }
    onDropHandled?.()
  }, [pendingDrop, onDropHandled])

  useEffect(() => {
    if (!selectedCampaign) return
    const valid = selectedCampaign.seasons.some(s => s.id === selectedSeasonId)
    if (!valid) {
      const id = selectedCampaign.seasons.length === 1 ? selectedCampaign.seasons[0].id : ''
      setSelectedSeasonId(id)
      api('set_pref', 'selected_season_id', id)
    }
  }, [selectedCampaignId, campaigns]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  // ── Campaign / season handlers ────────────────────────────────────────────

  function handleSelectCampaign(id: string) {
    setSelectedCampaignId(id); setSelectedSeasonId('')
    setSessionDir(null); setAudioPath(''); setImportTranscriptPath('')
    setShowNewCampaign(false); setShowNewSeason(false); setEditingSeasonId(null)
    api('set_pref', 'selected_campaign_id', id)
    api('set_pref', 'selected_season_id', '')
  }

  function handleSelectSeason(id: string) {
    setSelectedSeasonId(id)
    setSessionDir(null); setAudioPath(''); setImportTranscriptPath('')
    setEditingSeasonId(null)
    api('set_pref', 'selected_season_id', id)
  }

  async function handleCreateCampaign() {
    const name = newCampaignName.trim()
    if (!name || newCharIds.length === 0) return
    const result = await api('create_campaign', name, [{ number: newSeasonNum, characters: newCharIds }])
    if (result?.ok && result.campaign) {
      setCampaignError(null)
      const campaign = result.campaign as Campaign
      setCampaigns(prev => [...prev, campaign])
      const season = campaign.seasons[0]
      setSelectedCampaignId(campaign.id); setSelectedSeasonId(season.id)
      api('set_pref', 'selected_campaign_id', campaign.id)
      api('set_pref', 'selected_season_id', season.id)
      setShowNewCampaign(false); setNewCampaignName(''); setNewSeasonNum(1); setNewCharIds([])
      onFunnelComplete?.()
    } else {
      setCampaignError(result?.error || 'Failed to save campaign. Check that the app has write access to ~/.config/dnd-whisperx/ (Chronicles config directory)')
    }
  }

  async function handleDeleteCampaign() {
    if (!selectedCampaignId) return
    const result = await api('delete_campaign', selectedCampaignId)
    if (result?.ok) {
      setCampaigns(prev => prev.filter(c => c.id !== selectedCampaignId))
      setSelectedCampaignId(''); setSelectedSeasonId('')
      api('set_pref', 'selected_campaign_id', ''); api('set_pref', 'selected_season_id', '')
    }
  }

  function openAddSeason() {
    const maxNum = selectedCampaign ? Math.max(0, ...selectedCampaign.seasons.map(s => s.number)) : 1
    setAddSeasonNum(maxNum + 1); setAddSeasonCharIds([]); setShowNewSeason(true)
  }

  async function handleAddSeason() {
    if (!selectedCampaignId || !addSeasonCharIds.length) return
    const result = await api('add_season', selectedCampaignId, addSeasonNum, addSeasonCharIds)
    if (result?.ok && result.season) {
      const season = result.season as Season
      setCampaigns(prev => prev.map(c =>
        c.id === selectedCampaignId ? { ...c, seasons: [...c.seasons, season] } : c
      ))
      setSelectedSeasonId(season.id)
      api('set_pref', 'selected_season_id', season.id)
      setShowNewSeason(false)
    }
  }

  function startEditSeason(season: Season) { setEditingSeasonId(season.id); setEditCharIds([...season.characters]) }

  async function handleSaveSeasonEdit() {
    if (!selectedCampaignId || !editingSeasonId || !editCharIds.length) return
    const result = await api('update_season', selectedCampaignId, editingSeasonId, editCharIds)
    if (result?.ok) {
      setCampaigns(prev => prev.map(c =>
        c.id === selectedCampaignId
          ? { ...c, seasons: c.seasons.map(s => s.id === editingSeasonId ? { ...s, characters: editCharIds } : s) }
          : c
      ))
      setEditingSeasonId(null)
    }
  }

  // ── Session creation helper ───────────────────────────────────────────────

  async function ensureSession(dateOverride?: string): Promise<string | null> {
    if (sessionDir && !dateOverride) return sessionDir
    if (!selectedCampaignId || !selectedSeasonId) {
      setErrors(['Select a campaign and season first'])
      return null
    }
    const result = await api('create_session', selectedCampaignId, selectedSeasonId, dateOverride)
    if (!result?.ok) {
      setErrors([result?.error || 'Failed to create session folder'])
      return null
    }
    const dir = result.session_dir!
    setSessionDir(dir)
    onSessionStarted(dir, characterNames)
    return dir
  }

  // ── Audio handlers ────────────────────────────────────────────────────────

  async function handlePickAudio() {
    const path = await api('pick_audio_file')
    if (!path) return
    setErrors([])
    const dir = await ensureSession()
    if (!dir) return
    const result = await api('copy_audio_to_session', path, dir)
    if (result?.ok && result.path) {
      setAudioPath(result.path)
    } else {
      setErrors([result?.error || 'Failed to copy audio'])
    }
  }

  async function handleStartRecording() {
    setRecordError(null)
    setErrors([])
    const dir = await ensureSession()
    if (!dir) return
    const result = await api('start_recording', dir)
    if (!result?.ok) {
      setRecordError(result?.error || 'Failed to start recording')
      return
    }
    if (result.path) setAudioPath(result.path)
    // Redirect to pipeline view with recording state
    onRecordingStarted(dir, characterNames)
  }

  async function handleStopRecording() {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    const result = await api('stop_recording')
    setIsRecording(false)
    if (!result?.ok) {
      setRecordError(result?.error || 'Failed to stop recording')
      return
    }
    const path = result.path!
    setAudioPath(path)
    // Auto-start transcription
    doRun(path)
  }

  const doRun = useCallback(async (path: string) => {
    const errs: string[] = []
    if (!path) errs.push('Select or record an audio file')
    setErrors(errs)
    if (errs.length) return
    await api('set_pref', 'model', model)
    await api('set_pref', 'language', language)
    // Pre-populate skipped stages for optional artifacts
    const skipped = Object.entries(selectedArtifacts).filter(([, v]) => !v).map(([k]) => k)
    if (skipped.length > 0) await api('set_skipped_stages', skipped)
    onRun(path, model, numSpeakers, characterNames, language)
  }, [characterNames, model, language, numSpeakers, onRun, selectedArtifacts])

  // ── Transcript import handlers ────────────────────────────────────────────

  async function handlePickTranscript() {
    const path = await api('pick_transcript_file')
    if (path) setImportTranscriptPath(path)
  }

  async function handleImportTranscript() {
    if (!importTranscriptPath) {
      setErrors(['Select a transcript file first'])
      return
    }
    setErrors([])
    setIsImporting(true)
    const dir = await ensureSession(importDate)
    if (!dir) { setIsImporting(false); return }
    // Pre-populate skipped stages for optional artifacts
    const skipped = Object.entries(selectedArtifacts).filter(([, v]) => !v).map(([k]) => k)
    if (skipped.length > 0) await api('set_skipped_stages', skipped)
    const result = await api('start_pipeline_from_transcript', importTranscriptPath, importDiarized)
    setIsImporting(false)
    if (!result?.ok) setErrors([result?.error || 'Failed to start pipeline'])
  }

  // ── Section label ─────────────────────────────────────────────────────────

  function SectionLabel({ children }: { children: React.ReactNode }) {
    return <Label className="text-parchment/70 uppercase tracking-widest text-xs font-heading">{children}</Label>
  }

  // ── Processing mode ─────────────────────────────────────────────────────

  if (showProcessing) {
    return (
      <InlinePipelineView
        stages={pipelineStages}
        speakerReview={speakerReview}
        entityReview={entityReview}
        factReview={factReview}
        logLines={logLines}
        logVersion={logVersion}
        streamingChunks={streamingChunks}
        streamingVersion={streamingVersion}
        isTranscribing={isTranscribing}
        onStop={onStop}
        onStopLLMStage={onStopLLMStage}
        onSkipStage={onSkipStage}
        onBack={onBackToSetup}
        recordingActive={recordingActive}
        recordingPaused={recordingPaused}
        recordingSeconds={recordingSeconds}
        recordingAmplitude={recordingAmplitude}
        recordingFileSize={recordingFileSize}
        amplitudeHistory={amplitudeHistory}
        onPauseRecording={onPauseRecording}
        onResumeRecording={onResumeRecording}
        onStopRecording={onStopRecording}
        onNavigateToLibrary={onNavigateToLibrary}
      />
    )
  }

  // ── Loading state ────────────────────────────────────────────────────────

  if (initialLoading && !showProcessing) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 text-gold/40 animate-spin" />
          <p className="text-sm text-parchment/30 font-body">Loading session data…</p>
        </div>
      </div>
    )
  }

  // ── Setup mode (default) ─────────────────────────────────────────────────

  return (
    <div className="h-full overflow-y-auto p-8 relative">
      {/* Drag-over visual overlay */}
      {dragOver && !showProcessing && (
        <div className="absolute inset-0 z-50 pointer-events-none flex items-center justify-center">
          <div className="absolute inset-3 rounded-lg border-2 border-dashed border-gold/40 bg-gold/5" />
          <div className="relative flex flex-col items-center gap-2 text-gold/70">
            {dragOver === 'audio'
              ? <FileAudio className="w-8 h-8" />
              : <FileUp className="w-8 h-8" />
            }
            <span className="text-sm font-heading uppercase tracking-widest">
              Drop {dragOver === 'audio' ? 'audio file' : 'transcript'} here
            </span>
          </div>
        </div>
      )}

      <div className="max-w-xl mx-auto space-y-7">

        {/* ── No campaigns prompt ── */}
        {campaigns.length === 0 && !showNewCampaign && (
          <div className="text-center py-6 text-parchment/30">
            <BookOpen className="w-5 h-5 mx-auto mb-2" />
            <p className="text-xs font-body">No campaigns yet — create one from the Campaigns tab</p>
          </div>
        )}

        {!selectedCampaign && campaigns.length > 0 && !showNewCampaign && (
          <div className="text-center py-4 text-parchment/30">
            <p className="text-xs font-body">Select a campaign from the header dropdown</p>
          </div>
        )}

        {showNewCampaign && (
          <div className="rounded-md border border-gold/20 bg-gold/3 p-4 space-y-4">
            <div className="space-y-1.5">
              <Label className="text-parchment/50 text-xs font-heading uppercase tracking-widest">Campaign Name</Label>
              <Input value={newCampaignName} onChange={e => setNewCampaignName(e.target.value)} placeholder="e.g. The Lost Mines" autoFocus />
            </div>
            <div className="flex items-center gap-3">
              <Label className="text-parchment/50 text-xs font-heading uppercase tracking-widest flex-none">First Season</Label>
              <div className="flex items-center gap-1.5">
                <button className="w-6 h-6 rounded border border-white/10 flex items-center justify-center text-parchment/40 hover:text-gold hover:border-gold/30 transition-colors" onClick={() => setNewSeasonNum(n => Math.max(1, n - 1))} type="button"><ChevronDown className="w-3 h-3" /></button>
                <span className="w-5 text-center text-sm font-body text-parchment">{newSeasonNum}</span>
                <button className="w-6 h-6 rounded border border-white/10 flex items-center justify-center text-parchment/40 hover:text-gold hover:border-gold/30 transition-colors" onClick={() => setNewSeasonNum(n => n + 1)} type="button"><ChevronUp className="w-3 h-3" /></button>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-parchment/50 text-xs font-heading uppercase tracking-widest">Adventurers</Label>
              <CharacterPicker selectedIds={newCharIds} onChange={setNewCharIds} allCharacters={allCharacters} onCharactersChanged={setAllCharacters} />
            </div>
            {campaignError && (
              <p className="text-xs text-red-400/80 font-body px-1">{campaignError}</p>
            )}
            <div className="flex gap-2 pt-1">
              <Button size="sm" variant="outline" onClick={() => {
                if (autoNewCampaign && onCancelToTitle) {
                  onCancelToTitle()
                } else {
                  setShowNewCampaign(false); setNewCampaignName(''); setNewCharIds([]); setCampaignError(null)
                }
              }} className="flex-1">Cancel</Button>
              <Button size="sm" onClick={handleCreateCampaign} disabled={!newCampaignName.trim() || newCharIds.length === 0} className="flex-1 gap-1.5">
                <Check className="w-3.5 h-3.5" />Create Campaign
              </Button>
            </div>
          </div>
        )}

        {/* ── Season ── */}
        {selectedCampaign && !showNewCampaign && (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <SectionLabel>Season</SectionLabel>
              <button
                onClick={() => { openAddSeason(); setShowNewCampaign(false) }}
                className={cn('flex items-center gap-1 text-xs font-body transition-colors px-2 py-1 rounded', showNewSeason ? 'text-gold border border-gold/30 bg-gold/5' : 'text-parchment/40 hover:text-gold hover:border-gold/20 border border-transparent')}
              >
                <Plus className="w-3 h-3" />New Season
              </button>
            </div>
            <Select value={selectedSeasonId} onValueChange={handleSelectSeason}>
              <SelectTrigger><SelectValue placeholder="Select a season…" /></SelectTrigger>
              <SelectContent>
                {selectedCampaign.seasons.map(s => (
                  <SelectItem key={s.id} value={s.id}>Season {s.number} · {s.characters.length} adventurer{s.characters.length !== 1 ? 's' : ''}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {showNewSeason && (
              <div className="rounded-md border border-gold/20 bg-gold/3 p-4 space-y-4">
                <div className="flex items-center gap-3">
                  <Label className="text-parchment/50 text-xs font-heading uppercase tracking-widest flex-none">Season</Label>
                  <div className="flex items-center gap-1.5">
                    <button className="w-6 h-6 rounded border border-white/10 flex items-center justify-center text-parchment/40 hover:text-gold transition-colors" onClick={() => setAddSeasonNum(n => Math.max(1, n - 1))} type="button"><ChevronDown className="w-3 h-3" /></button>
                    <span className="w-5 text-center text-sm font-body text-parchment">{addSeasonNum}</span>
                    <button className="w-6 h-6 rounded border border-white/10 flex items-center justify-center text-parchment/40 hover:text-gold transition-colors" onClick={() => setAddSeasonNum(n => n + 1)} type="button"><ChevronUp className="w-3 h-3" /></button>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-parchment/50 text-xs font-heading uppercase tracking-widest">Adventurers</Label>
                  <CharacterPicker selectedIds={addSeasonCharIds} onChange={setAddSeasonCharIds} allCharacters={allCharacters} onCharactersChanged={setAllCharacters} />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setShowNewSeason(false)} className="flex-1">Cancel</Button>
                  <Button size="sm" onClick={handleAddSeason} disabled={addSeasonCharIds.length === 0} className="flex-1 gap-1.5">
                    <Check className="w-3.5 h-3.5" />Add Season
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Adventurers (read-only / editable) ── */}
        {selectedSeason && !showNewCampaign && !showNewSeason && (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <SectionLabel>Adventurers</SectionLabel>
              {editingSeasonId !== selectedSeason.id && (
                <button onClick={() => startEditSeason(selectedSeason)} className="flex items-center gap-1 text-xs text-parchment/30 hover:text-gold/60 transition-colors">
                  <Pencil className="w-3 h-3" />Edit
                </button>
              )}
            </div>
            {editingSeasonId === selectedSeason.id ? (
              <div className="space-y-3">
                <CharacterPicker selectedIds={editCharIds} onChange={setEditCharIds} allCharacters={allCharacters} onCharactersChanged={setAllCharacters} />
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setEditingSeasonId(null)} className="flex-1">Cancel</Button>
                  <Button size="sm" onClick={handleSaveSeasonEdit} disabled={editCharIds.length === 0} className="flex-1 gap-1.5">
                    <Check className="w-3.5 h-3.5" />Save
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {characterNames.map((name, i) => (
                  <div key={i} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gold/8 border border-gold/15 text-xs text-parchment/70 font-body">
                    <span className="w-3.5 h-3.5 rounded-full bg-gold/20 flex items-center justify-center text-[9px] text-gold/80 font-heading flex-none">{i + 1}</span>
                    {name}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Session Settings (only when campaign+season selected) ── */}
        {canProceed && !showNewCampaign && !showNewSeason && editingSeasonId !== selectedSeasonId && (
          <>
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-gold/20 to-transparent"/>
              <span className="text-gold/30 text-xs tracking-widest font-heading uppercase">Session Settings</span>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-gold/20 to-transparent"/>
            </div>

            {/* ── Transcription Settings ── */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <SectionLabel>Model</SectionLabel>
                <Select value={model} onValueChange={v => setModel(v)}>
                  <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>{MODELS.map(m => <SelectItem key={m.value} value={m.value} className="text-xs">{m.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <SectionLabel>Language</SectionLabel>
                <Select value={language} onValueChange={v => setLanguage(v)}>
                  <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>{LANGUAGES.map(l => <SelectItem key={l.value} value={l.value} className="text-xs">{l.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>

            {/* ── Artifacts to generate ── */}
            <div className="space-y-2">
              <SectionLabel>Artifacts to generate</SectionLabel>
              <div className="grid grid-cols-3 gap-x-4 gap-y-1.5">
                {([
                  ['timeline', 'Timeline'],
                  ['summary', 'Summary'],
                  ['dm_notes', 'DM Notes'],
                  ['character_updates', 'Character Updates'],
                  ['leaderboard', 'Leaderboard'],
                  ['locations', 'Locations'],
                  ['npcs', 'NPCs'],
                  ['loot', 'Loot'],
                  ['missions', 'Missions'],
                ] as const).map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={selectedArtifacts[key]}
                      onChange={e => setSelectedArtifacts(prev => ({ ...prev, [key]: e.target.checked }))}
                      className="w-3.5 h-3.5 rounded border-white/20 bg-white/5 text-gold accent-gold cursor-pointer"
                    />
                    <span className="text-xs font-body text-parchment/50 group-hover:text-parchment/70 transition-colors select-none">
                      {label}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            {/* ── Record Session (primary action) ── */}
            <div>
              <Button
                variant="default" size="lg"
                className="w-full gap-3 font-heading tracking-widest uppercase text-sm"
                onClick={handleStartRecording}
                disabled={isRunning || isRecording}
              >
                <Mic className="w-4 h-4" />
                Record Session
              </Button>
            </div>

            {/* ── OR separator ── */}
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-parchment/15 to-transparent"/>
              <span className="text-parchment/30 text-xs tracking-widest font-heading uppercase">Or</span>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-parchment/15 to-transparent"/>
            </div>

            {/* ── Import Audio (collapsible) ── */}
            <div>
              <div className="rounded-md border border-white/8 overflow-hidden">
                <button
                  onClick={() => setAudioExpanded(v => !v)}
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-white/2 hover:bg-white/4 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <FileAudio className="w-3.5 h-3.5 text-parchment/40 flex-none" />
                    <span className="text-xs font-heading text-parchment/50 uppercase tracking-widest">Import Audio</span>
                    {audioPath && !audioExpanded && (
                      <span className="text-[10px] font-body text-gold/50 truncate max-w-[180px]">{audioPath.split('/').pop()}</span>
                    )}
                  </div>
                  <ChevronDown className={cn('w-3.5 h-3.5 text-parchment/30 transition-transform', audioExpanded && 'rotate-180')} />
                </button>
                {audioExpanded && (
                  <div className="p-4 space-y-3">
                    <button
                      onClick={handlePickAudio}
                      disabled={isRunning}
                      className={cn(
                        'w-full flex flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed py-8 transition-all',
                        audioPath
                          ? 'border-gold/30 bg-gold/5'
                          : 'border-white/12 hover:border-gold/30 hover:bg-gold/3',
                      )}
                    >
                      <FileAudio className={cn('w-5 h-5', audioPath ? 'text-gold/60' : 'text-parchment/25')} />
                      {audioPath ? (
                        <div className="text-center space-y-0.5">
                          <p className="text-xs font-body text-gold/70 font-medium">{audioPath.split('/').pop()}</p>
                          <p className="text-[10px] text-parchment/30 font-body">Click to change file</p>
                        </div>
                      ) : (
                        <div className="text-center space-y-1">
                          <p className="text-xs font-body text-parchment/45">Drop audio here or click to browse</p>
                          <p className="text-[10px] text-parchment/25 font-body">m4a · mp3 · wav · ogg · flac</p>
                        </div>
                      )}
                    </button>
                    {recordError && <p className="text-xs text-red-400 font-body pl-1">{recordError}</p>}

                    {/* Run button (only when audio ready) */}
                    {audioPath && (
                      <Button
                        variant="default" size="sm"
                        className="w-full gap-2 font-heading tracking-widest uppercase text-xs"
                        onClick={() => doRun(audioPath)}
                        disabled={isRunning}
                      >
                        <Sword className={cn("w-3.5 h-3.5", isRunning && "animate-spin")} />
                        {isRunning ? 'Running Pipeline…' : 'Import Audio & Process'}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* ── Import Transcript (collapsible) ── */}
            <div>
              <div className="rounded-md border border-white/8 overflow-hidden">
                <button
                  onClick={() => setTranscriptExpanded(v => !v)}
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-white/2 hover:bg-white/4 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <FileUp className="w-3.5 h-3.5 text-parchment/40 flex-none" />
                    <span className="text-xs font-heading text-parchment/50 uppercase tracking-widest">Import Transcript</span>
                    {importTranscriptPath && !transcriptExpanded && (
                      <span className="text-[10px] font-body text-blue-300/50 truncate max-w-[180px]">{importTranscriptPath.split('/').pop()}</span>
                    )}
                  </div>
                  <ChevronDown className={cn('w-3.5 h-3.5 text-parchment/30 transition-transform', transcriptExpanded && 'rotate-180')} />
                </button>
                {transcriptExpanded && (
                  <div className="p-4 space-y-3">
                    <p className="text-xs text-parchment/30 font-body leading-relaxed">
                      Upload a WhisperX <span className="text-parchment/50">.json</span> to run speaker ID + full pipeline, or a labeled <span className="text-parchment/50">.txt</span> to generate DM notes &amp; video prompts directly.
                    </p>

                    {/* File picker */}
                    <button
                      onClick={handlePickTranscript}
                      disabled={isImporting}
                      className={cn(
                        'w-full flex flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed py-8 transition-all',
                        importTranscriptPath
                          ? 'border-blue-400/30 bg-blue-400/5'
                          : 'border-white/10 hover:border-blue-400/25 hover:bg-white/3',
                      )}
                    >
                      <FileUp className={cn('w-5 h-5', importTranscriptPath ? 'text-blue-400/60' : 'text-parchment/20')} />
                      {importTranscriptPath ? (
                        <div className="text-center space-y-0.5">
                          <p className="text-xs font-body text-blue-300/70 font-medium">{importTranscriptPath.split('/').pop()}</p>
                          <p className="text-[10px] text-parchment/30 font-body">Click to change file</p>
                        </div>
                      ) : (
                        <div className="text-center space-y-1">
                          <p className="text-xs font-body text-parchment/35">Drop transcript here or click to browse</p>
                          <p className="text-[10px] text-parchment/20 font-body">.json · .txt</p>
                        </div>
                      )}
                    </button>

                    {/* Diarization checkbox */}
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={importDiarized}
                        onChange={e => setImportDiarized(e.target.checked)}
                        className="w-3.5 h-3.5 rounded border-gold/30 accent-gold cursor-pointer"
                      />
                      <span className="text-xs text-parchment/50 font-body">Transcript includes speaker diarization</span>
                    </label>

                    {/* Session date */}
                    <div className="flex items-center gap-3">
                      <Label className="text-parchment/40 text-xs font-heading uppercase tracking-widest flex-none">Session Date</Label>
                      <Input
                        type="date"
                        value={importDate}
                        onChange={e => setImportDate(e.target.value)}
                        className="h-8 text-xs flex-1"
                        max={new Date().toISOString().slice(0, 10)}
                      />
                    </div>

                    <Button
                      variant="default" size="sm"
                      className="w-full gap-2 font-heading tracking-widest uppercase text-xs"
                      onClick={handleImportTranscript}
                      disabled={!importTranscriptPath || isImporting || isRunning}
                    >
                      <FileUp className={cn("w-3.5 h-3.5", isImporting && "animate-pulse")} />
                      {isImporting ? 'Importing…' : 'Import & Process'}
                    </Button>
                  </div>
                )}
              </div>
            </div>

            {/* ── Errors ── */}
            {errors.length > 0 && (
              <div className="rounded-md bg-destructive/10 border border-destructive/30 px-4 py-3 space-y-1">
                {errors.map((e, i) => <p key={i} className="text-xs text-red-400 font-body">• {e}</p>)}
              </div>
            )}
          </>
        )}

      </div>
    </div>
  )
}
