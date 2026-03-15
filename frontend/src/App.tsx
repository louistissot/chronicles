import { useState, useCallback, useRef, useEffect } from 'react'
import { SessionTab } from '@/components/SessionTab'
import { LibraryTab } from '@/components/LibraryTab'
import { SettingsTab } from '@/components/SettingsTab'
import { CampaignsTab, CreateCampaignForm } from '@/components/CampaignsTab'
import { CharactersTab } from '@/components/CharactersTab'
import { GlossaryTab } from '@/components/GlossaryTab'
import { ChronicleTab } from '@/components/ChronicleTab'
import { TitleScreen, type TitleChoice } from '@/components/TitleScreen'
import { api, type PipelineStage, type StageStatus, type SpeakerReviewPayload, type EntityReviewPayload } from '@/lib/api'
import type { Campaign, Character } from '@/lib/api'
import { Scroll, Archive, Sun, Moon, Users, Settings, Shield, ChevronDown, BookOpen, Plus, ArrowLeft } from 'lucide-react'
import { cn } from '@/lib/utils'

const EMPTY_CHUNKS: Record<PipelineStage, string> = {
  transcription: '', saving_transcript: '', transcript_correction: '', speaker_mapping: '', updating_transcript: '', timeline: '', summary: '', dm_notes: '', character_updates: '', glossary: '', leaderboard: '', locations: '', npcs: '', loot: '', missions: '', scenes: '', illustration: '',
}

type Tab = 'characters' | 'library' | 'glossary' | 'chronicle'

export interface StageState {
  status: StageStatus
  data?: any
  error?: string
}

export type PipelineStages = Record<PipelineStage, StageState>

const IDLE_STAGES: PipelineStages = {
  transcription:      { status: 'idle' },
  saving_transcript:  { status: 'idle' },
  transcript_correction: { status: 'idle' },
  speaker_mapping:    { status: 'idle' },
  updating_transcript:{ status: 'idle' },
  timeline:           { status: 'idle' },
  summary:            { status: 'idle' },
  dm_notes:           { status: 'idle' },
  character_updates:  { status: 'idle' },
  glossary:           { status: 'idle' },
  leaderboard:        { status: 'idle' },
  locations:          { status: 'idle' },
  npcs:               { status: 'idle' },
  loot:               { status: 'idle' },
  missions:           { status: 'idle' },
  scenes:             { status: 'idle' },
  illustration:       { status: 'idle' },
}

export type AppState = {
  sessionStarted: boolean
  sessionDir: string | null
  characterNames: string[]
  stages: PipelineStages
  speakerReview: SpeakerReviewPayload | null
  entityReview: EntityReviewPayload | null
  logLines: Array<{ text: string; isStderr: boolean }>
}

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'characters', label: 'Characters', icon: Users },
  { id: 'library',    label: 'Library',    icon: Archive },
  { id: 'glossary',   label: 'Glossary',   icon: BookOpen },
  { id: 'chronicle',  label: 'Chronicles', icon: Scroll },
]

export default function App() {
  const [activeTab, setActiveTab]       = useState<Tab>('library')
  const [showNewSession, setShowNewSession] = useState(false)
  const [showTitle, setShowTitle]       = useState(true)
  const [autoNewCampaign, setAutoNew]   = useState(false)
  const [isNewGameFunnel, setIsNewGameFunnel] = useState(false)
  const [theme, setTheme]               = useState<'dark' | 'light'>('dark')
  const [pendingDrop, setPendingDrop]   = useState<{ type: 'audio' | 'transcript'; path: string } | null>(null)
  const [dragOver, setDragOver]         = useState<'audio' | 'transcript' | null>(null)
  const [npcNotification, setNpcNotification] = useState<string | null>(null)
  const [prefillCampaignId, setPrefillCampaignId] = useState<string | undefined>(undefined)
  const [prefillSeasonId, setPrefillSeasonId]     = useState<string | undefined>(undefined)
  const [recordingState, setRecordingState] = useState<{ active: boolean; paused: boolean }>({ active: false, paused: false })
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [recordingInfo, setRecordingInfo] = useState<{ amplitude: number; file_size: number }>({ amplitude: 0, file_size: 0 })
  const amplitudeHistory = useRef<number[]>([])
  const [showProcessing, setShowProcessing] = useState(false)
  const [libraryRefreshTrigger, setLibraryRefreshTrigger] = useState(0)

  // Campaign-first navigation state
  const [activeCampaignId, setActiveCampaignId] = useState<string | null>(null)
  const [activeCampaignName, setActiveCampaignName] = useState<string>('')
  const [showCampaignSelector, setShowCampaignSelector] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showManageCampaigns, setShowManageCampaigns] = useState(false)
  const [campaignDropdownOpen, setCampaignDropdownOpen] = useState(false)
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [showCreateCampaign, setShowCreateCampaign] = useState(false)
  const [focusCharacterId, setFocusCharacterId] = useState<string | null>(null)

  const handleNavigateToCharacter = useCallback((charId: string) => {
    setFocusCharacterId(charId)
    setActiveTab('characters')
  }, [])

  const [appState, setAppState] = useState<AppState>({
    sessionStarted: false,
    sessionDir: null,
    characterNames: [],
    stages: IDLE_STAGES,
    speakerReview: null,
    entityReview: null,
    logLines: [],
  })
  const logLinesRef = useRef<Array<{ text: string; isStderr: boolean }>>([])
  const streamingChunksRef = useRef<Record<PipelineStage, string>>({ ...EMPTY_CHUNKS })
  const [streamingVersion, setStreamingVersion] = useState(0)
  const [logVersion, setLogVersion] = useState(0)

  useEffect(() => {
    window._receiveLog = (line: string, isStderr: boolean) => {
      logLinesRef.current = [...logLinesRef.current, { text: line, isStderr }]
      setLogVersion(v => v + 1)
    }

    window._pyDragDrop = (payload) => {
      setDragOver(null)
      setShowNewSession(true)
      setShowProcessing(false)
      setPendingDrop(payload)
    }

    window._pyDragOver = (dtype: string) => {
      setDragOver(dtype as 'audio' | 'transcript')
    }

    window._pyDragLeave = () => {
      setDragOver(null)
    }

    window._onLLMChunk = (stage: PipelineStage, chunk: string) => {
      streamingChunksRef.current = {
        ...streamingChunksRef.current,
        [stage]: streamingChunksRef.current[stage] + chunk,
      }
      setStreamingVersion(v => v + 1)
    }

    const ENTITY_REVIEW_STAGES = ['locations', 'npcs', 'loot', 'missions']
    window._onPipelineStage = (stage: PipelineStage, status: StageStatus, data: any) => {
      setAppState(s => {
        const next = { ...s, stages: { ...s.stages, [stage]: { status, data, error: data?.error } } }
        if (stage === 'speaker_mapping' && status === 'needs_review') {
          next.speakerReview = data as SpeakerReviewPayload
        }
        if (stage === 'speaker_mapping' && status === 'done') {
          next.speakerReview = null
        }
        // Entity review for low-confidence extractions
        if (ENTITY_REVIEW_STAGES.includes(stage) && status === 'needs_review') {
          next.entityReview = data as EntityReviewPayload
        }
        if (ENTITY_REVIEW_STAGES.includes(stage) && (status === 'done' || status === 'error')) {
          if (s.entityReview?.stage === stage) next.entityReview = null
        }
        return next
      })
    }

    window._onNpcSync = (data: { new: string[]; updated: string[] }) => {
      const parts: string[] = []
      if (data.new.length) parts.push(`${data.new.length} new NPC${data.new.length > 1 ? 's' : ''}`)
      if (data.updated.length) parts.push(`${data.updated.length} updated`)
      if (parts.length) {
        setNpcNotification(parts.join(', '))
        setTimeout(() => setNpcNotification(null), 6000)
      }
    }

    return () => {
      window._receiveLog = undefined
      window._onPipelineStage = undefined
      window._onLLMChunk = undefined
      window._pyDragDrop = undefined
      window._pyDragOver = undefined
      window._pyDragLeave = undefined
      window._onNpcSync = undefined
    }
  }, [])

  // Recording polling — 200ms for waveform visualization + duration + file size
  useEffect(() => {
    if (!recordingState.active) {
      amplitudeHistory.current = []
      setRecordingInfo({ amplitude: 0, file_size: 0 })
      return
    }
    const iv = setInterval(async () => {
      const info = await api('get_recording_info')
      if (info) {
        setRecordingSeconds(Math.floor(info.duration ?? 0))
        setRecordingInfo({ amplitude: info.amplitude ?? 0, file_size: info.file_size ?? 0 })
        amplitudeHistory.current = [...amplitudeHistory.current.slice(-39), info.amplitude ?? 0]
      }
    }, 200)
    return () => clearInterval(iv)
  }, [recordingState.active])

  // Auto-refresh library when pipeline finishes
  const prevStagesRef = useRef(appState.stages)
  useEffect(() => {
    const wasRunning = Object.values(prevStagesRef.current).some(s => s.status === 'running')
    const nowDone    = Object.values(appState.stages).every(s => s.status !== 'running' && s.status !== 'needs_review')
    if (wasRunning && nowDone && appState.sessionStarted) {
      setTimeout(() => setLibraryRefreshTrigger(v => v + 1), 1500)
      setAppState(s => ({ ...s, sessionStarted: false }))
    }
    prevStagesRef.current = appState.stages
  }, [appState.stages, appState.sessionStarted])

  useEffect(() => {
    api('get_pref', 'theme', 'dark').then((saved: any) => {
      const t = saved === 'light' ? 'light' : 'dark'
      setTheme(t)
      document.documentElement.classList.toggle('light', t === 'light')
    })
  }, [])

  // Load campaigns for selector
  const loadCampaigns = useCallback(async () => {
    const cs = await api('get_campaigns')
    if (cs) setCampaigns(cs)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark'
      document.documentElement.classList.toggle('light', next === 'light')
      api('set_pref', 'theme', next)
      return next
    })
  }, [])

  const selectCampaign = useCallback((campaign: Campaign) => {
    setActiveCampaignId(campaign.id)
    setActiveCampaignName(campaign.name)
    setPrefillCampaignId(campaign.id)
    // Pick the latest season
    if (campaign.seasons.length > 0) {
      const latest = campaign.seasons[campaign.seasons.length - 1]
      setPrefillSeasonId(latest.id)
    }
    setShowCampaignSelector(false)
  }, [])

  const handleSessionStarted = useCallback((
    sessionDir: string,
    characterNames: string[],
  ) => {
    logLinesRef.current = []
    streamingChunksRef.current = { ...EMPTY_CHUNKS }
    setLogVersion(v => v + 1)
    setStreamingVersion(v => v + 1)
    setAppState({
      sessionStarted: true,
      sessionDir,
      characterNames,
      stages: IDLE_STAGES,
      speakerReview: null,
      entityReview: null,
      logLines: [],
    })
    // Show processing in fullscreen session view
    setShowNewSession(true)
    setShowProcessing(true)
  }, [])

  const handleRun = useCallback(async (
    audioPath: string,
    model: string,
    numSpeakers: number,
    characterNames: string[],
    language: string,
  ) => {
    setAppState(s => ({
      ...s,
      stages: { ...s.stages, transcription: { status: 'running' } },
    }))
    const result = await api('start_job', audioPath, model, numSpeakers, characterNames, language)
    if (!result?.ok) {
      setAppState(s => ({
        ...s,
        stages: {
          ...s.stages,
          transcription: { status: 'error', error: result?.error || 'Failed to start job' },
        },
      }))
      logLinesRef.current = [...logLinesRef.current, {
        text: `[Error] ${result?.error || 'Failed to start job'}`,
        isStderr: true,
      }]
      setLogVersion(v => v + 1)
    }
  }, [])

  const handleStop = useCallback(async () => {
    await api('stop_pipeline')
    setAppState(s => {
      const updated = { ...s.stages }
      for (const key of Object.keys(updated) as PipelineStage[]) {
        if (updated[key].status === 'running') {
          updated[key] = { status: 'error', error: 'Stopped by user' }
        }
      }
      return { ...s, sessionStarted: false, stages: updated }
    })
  }, [])

  const handleStopLLMStage = useCallback(async (stage: PipelineStage) => {
    await api('stop_llm_stage', stage)
  }, [])

  const handleSkipStage = useCallback(async (stage: PipelineStage) => {
    await api('skip_llm_stage', stage)
  }, [])

  const handleRecordingStarted = useCallback((sessionDir: string, characterNames: string[]) => {
    logLinesRef.current = []
    streamingChunksRef.current = { ...EMPTY_CHUNKS }
    setLogVersion(v => v + 1)
    setStreamingVersion(v => v + 1)
    setAppState({
      sessionStarted: true,
      sessionDir,
      characterNames,
      stages: IDLE_STAGES,
      speakerReview: null,
      entityReview: null,
      logLines: [],
    })
    setRecordingState({ active: true, paused: false })
    setRecordingSeconds(0)
    // Show processing in fullscreen session view
    setShowNewSession(true)
    setShowProcessing(true)
  }, [])

  const handlePauseRecording = useCallback(async () => {
    await api('pause_recording')
    setRecordingState(s => ({ ...s, paused: true }))
  }, [])

  const handleResumeRecording = useCallback(async () => {
    await api('resume_recording')
    setRecordingState(s => ({ ...s, paused: false }))
  }, [])

  const handleStopRecording = useCallback(async () => {
    const result = await api('stop_recording')
    setRecordingState({ active: false, paused: false })
    if (result?.ok && result.path) {
      // Auto-start transcription pipeline
      const model = await api('get_pref', 'whisperx_model', 'large-v3')
      const numSpeakers = appState.characterNames.length || 4
      const language = await api('get_pref', 'whisperx_language', 'auto')
      handleRun(result.path, model, numSpeakers, appState.characterNames, language)
    }
  }, [appState.characterNames, handleRun])

  const handleTitleSelect = useCallback((choice: TitleChoice) => {
    if (choice === 'options') {
      setShowSettings(true)
      setShowTitle(false)
      return
    }

    if (choice === 'start') {
      // New Campaign — standalone create campaign view
      setShowCreateCampaign(true)
      setShowTitle(false)
      return
    }

    // Continue — show campaign selector
    setShowTitle(false)
    setShowCampaignSelector(true)
    loadCampaigns()
  }, [loadCampaigns])

  const handleCancelToTitle = useCallback(() => {
    setShowTitle(true)
    setIsNewGameFunnel(false)
    setAutoNew(false)
    setActiveCampaignId(null)
    setActiveCampaignName('')
    setShowCampaignSelector(false)
    setShowSettings(false)
    setShowManageCampaigns(false)
    setShowCreateCampaign(false)
    setShowNewSession(false)
  }, [])

  const handleFunnelComplete = useCallback(() => {
    setIsNewGameFunnel(false)
    // After creating a campaign in the funnel, update campaign info
    loadCampaigns()
  }, [loadCampaigns])

  const isTranscribing = appState.stages.transcription.status === 'running'
  const pipelineActive = appState.sessionStarted
  const pipelineInProgress = pipelineActive && (
    isTranscribing ||
    recordingState.active ||
    Object.values(appState.stages).some(s => s.status === 'running' || s.status === 'needs_review')
  )

  function isTabDisabled(_id: Tab) {
    return false
  }

  // Determine which top-level view to show
  const showMainTabs = !showCampaignSelector && !showSettings && !showManageCampaigns && !showCreateCampaign && !showNewSession

  return (
    <>
    {showTitle && <TitleScreen onSelect={handleTitleSelect} theme={theme} />}
    {!showTitle && <div className="flex flex-col h-screen bg-void overflow-hidden" style={{
      background: theme === 'light'
        ? 'radial-gradient(ellipse at top, #E4DECA 0%, #F5F0E1 70%)'
        : 'radial-gradient(ellipse at top, #12172A 0%, #080B14 70%)',
    }}>
      {/* Header — draggable titlebar region */}
      <header className="flex-none px-8 pt-6 pb-3 app-drag" style={{ paddingLeft: '78px' }}>
        <div className="flex items-center gap-4">
          <div className="relative flex-none">
            <svg width="44" height="44" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="22" cy="22" r="21" fill="#0D1120" stroke="rgba(212,175,55,0.3)" strokeWidth="1"/>
              <polygon points="22,4 37,13 37,31 22,40 7,31 7,13" fill="#12172A" stroke="#D4AF37" strokeWidth="1.5" strokeLinejoin="round"/>
              <line x1="22" y1="4" x2="22" y2="22" stroke="rgba(212,175,55,0.4)" strokeWidth="0.8"/>
              <line x1="37" y1="13" x2="22" y2="22" stroke="rgba(212,175,55,0.4)" strokeWidth="0.8"/>
              <line x1="37" y1="31" x2="22" y2="22" stroke="rgba(212,175,55,0.4)" strokeWidth="0.8"/>
              <line x1="22" y1="40" x2="22" y2="22" stroke="rgba(212,175,55,0.4)" strokeWidth="0.8"/>
              <line x1="7" y1="31" x2="22" y2="22" stroke="rgba(212,175,55,0.4)" strokeWidth="0.8"/>
              <line x1="7" y1="13" x2="22" y2="22" stroke="rgba(212,175,55,0.4)" strokeWidth="0.8"/>
              <text x="22" y="27" textAnchor="middle" fill="#D4AF37" fontSize="12" fontFamily="Impact, serif" fontWeight="bold">20</text>
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-display text-gold animate-glow-pulse leading-none"
              style={{ fontFamily: "'Cinzel Decorative', serif" }}>
              Chronicles
            </h1>
            <p className="text-xs text-parchment/40 font-body tracking-widest uppercase mt-0.5">
              D&D Unofficial LoreKeeper
            </p>
          </div>

          {/* Right side: new session CTA + campaign indicator + settings + theme */}
          <div className="ml-auto flex items-center gap-2 app-no-drag">
            {/* + New Session CTA */}
            {!showNewSession && activeCampaignId && showMainTabs && (
              <button
                onClick={() => {
                  setShowNewSession(true)
                  setShowProcessing(false)
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-gold/10 border border-gold/25 text-xs font-heading text-gold hover:bg-gold/20 hover:border-gold/40 transition-colors"
              >
                <Plus className="w-3 h-3" />
                New Session
              </button>
            )}

            {/* Campaign indicator */}
            {activeCampaignId && showMainTabs && (
              <div className="relative">
                <button
                  onClick={() => setCampaignDropdownOpen(v => !v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gold/20 text-xs font-heading text-gold/80 hover:bg-gold/5 hover:border-gold/30 transition-colors"
                >
                  <Shield className="w-3 h-3 text-gold/50" />
                  <span className="max-w-[140px] truncate">{activeCampaignName}</span>
                  <ChevronDown className="w-3 h-3 text-gold/40" />
                </button>
                {campaignDropdownOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setCampaignDropdownOpen(false)} />
                    <div className="absolute right-0 top-full mt-1 z-50 w-56 rounded-md border border-white/10 bg-shadow shadow-lg overflow-hidden">
                      {campaigns.map(c => (
                        <button
                          key={c.id}
                          onClick={() => {
                            selectCampaign(c)
                            setCampaignDropdownOpen(false)
                          }}
                          className={cn(
                            'w-full text-left px-3 py-2 text-xs font-body hover:bg-white/5 transition-colors',
                            c.id === activeCampaignId ? 'text-gold bg-gold/5' : 'text-parchment/60',
                          )}
                        >
                          {c.name}
                        </button>
                      ))}
                      <div className="border-t border-white/8">
                        <button
                          onClick={() => {
                            setCampaignDropdownOpen(false)
                            setShowManageCampaigns(true)
                            loadCampaigns()
                          }}
                          className="w-full text-left px-3 py-2 text-xs font-heading text-parchment/40 hover:text-gold hover:bg-white/5 transition-colors uppercase tracking-widest"
                        >
                          Manage Campaigns
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Settings gear */}
            <button
              onClick={() => {
                setShowSettings(true)
                setShowCampaignSelector(false)
                setShowManageCampaigns(false)
              }}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                showSettings ? 'text-gold bg-gold/10' : 'text-parchment/35 hover:text-gold/70',
              )}
              title="Settings"
            >
              <Settings className="w-4 h-4" />
            </button>

            {/* Theme toggle */}
            <button
              onClick={toggleTheme}
              className="p-1.5 rounded-md text-parchment/35 hover:text-gold/70 transition-colors"
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </div>

      </header>

      {/* Tab bar — only show when in main tab view */}
      {showMainTabs && (
        <nav className="flex-none flex px-8 gap-1 mt-2">
          {TABS.map(({ id, label, icon: Icon }) => {
            const isActive = activeTab === id
            const disabled = isTabDisabled(id)

            return (
              <button
                key={id}
                onClick={() => !disabled && setActiveTab(id)}
                disabled={disabled}
                className={cn(
                  'flex items-center gap-2 px-4 py-2.5 rounded-t-md text-xs font-body font-medium tracking-wide transition-all select-none relative',
                  isActive
                    ? 'bg-shadow text-gold border-t border-x border-gold/25 tab-active-glow'
                    : disabled
                    ? 'text-parchment/20 cursor-not-allowed'
                    : 'text-parchment/50 hover:text-parchment/80 hover:bg-white/5 cursor-pointer border-t border-x border-transparent'
                )}
              >
                <Icon className={cn('w-3.5 h-3.5', isActive ? 'text-gold' : 'opacity-50')} />
                {label}
              </button>
            )
          })}
        </nav>
      )}

      {/* New Session header bar (back arrow) */}
      {showNewSession && (
        <div className="flex-none flex items-center gap-2 px-8 mt-2">
          <button
            onClick={() => {
              if (!pipelineInProgress) {
                setShowNewSession(false)
                setShowProcessing(false)
              } else {
                // Pipeline running — just go back, it continues in background
                setShowNewSession(false)
              }
            }}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-body text-parchment/50 hover:text-gold hover:bg-white/5 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back
          </button>
          {pipelineInProgress && (
            <span className="flex items-center gap-1.5 text-[10px] font-body text-gold/50">
              <span className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse" />
              Processing…
            </span>
          )}
        </div>
      )}

      {/* Main content */}
      <main className={cn(
        'flex-1 overflow-hidden bg-shadow/60 border-t border-gold/20 mx-8 mb-6',
        showMainTabs ? 'rounded-b-sm' : 'rounded-sm mt-2',
      )} style={{ backdropFilter: 'blur(4px)' }}>

        {/* Campaign selector */}
        {showCampaignSelector && (
          <CampaignSelector
            campaigns={campaigns}
            onSelect={selectCampaign}
            onBack={handleCancelToTitle}
            onRefresh={loadCampaigns}
          />
        )}

        {/* Settings full view */}
        {showSettings && (
          <div className="h-full flex flex-col">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-white/8 flex-shrink-0">
              <button onClick={() => {
                setShowSettings(false)
                if (!activeCampaignId) setShowTitle(true)
              }} className="p-1.5 rounded hover:bg-white/5 text-parchment/50 hover:text-gold transition-colors">
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>
              </button>
              <Settings className="w-4 h-4 text-gold/50" />
              <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">Settings</h2>
            </div>
            <div className="flex-1 overflow-hidden">
              <SettingsTab theme={theme} onThemeChange={toggleTheme} />
            </div>
          </div>
        )}

        {/* Manage Campaigns full view */}
        {showManageCampaigns && (
          <div className="h-full flex flex-col">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-white/8 flex-shrink-0">
              <button onClick={() => setShowManageCampaigns(false)} className="p-1.5 rounded hover:bg-white/5 text-parchment/50 hover:text-gold transition-colors">
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>
              </button>
              <Shield className="w-4 h-4 text-gold/50" />
              <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">Manage Campaigns</h2>
            </div>
            <div className="flex-1 overflow-hidden">
              <CampaignsTab />
            </div>
          </div>
        )}

        {/* Standalone Create Campaign view */}
        {showCreateCampaign && (
          <CreateCampaignView
            onCreated={(campaign) => {
              setShowCreateCampaign(false)
              selectCampaign(campaign)
              setActiveTab('library')
            }}
            onCancel={handleCancelToTitle}
          />
        )}

        {/* Fullscreen New Session view */}
        {showNewSession && (
          <SessionTab
            onSessionStarted={handleSessionStarted}
            onRecordingStarted={handleRecordingStarted}
            onRun={handleRun}
            isRunning={isTranscribing}
            autoNewCampaign={autoNewCampaign}
            prefillCampaignId={prefillCampaignId}
            prefillSeasonId={prefillSeasonId}
            pendingDrop={pendingDrop}
            onDropHandled={() => setPendingDrop(null)}
            dragOver={dragOver}
            onCancelToTitle={isNewGameFunnel ? handleCancelToTitle : undefined}
            onFunnelComplete={isNewGameFunnel ? handleFunnelComplete : undefined}
            // Pipeline state
            pipelineActive={pipelineActive}
            pipelineStages={appState.stages}
            speakerReview={appState.speakerReview}
            entityReview={appState.entityReview}
            logLines={logLinesRef.current}
            logVersion={logVersion}
            streamingChunks={streamingChunksRef.current}
            streamingVersion={streamingVersion}
            onStop={handleStop}
            onStopLLMStage={handleStopLLMStage}
            onSkipStage={handleSkipStage}
            recordingActive={recordingState.active}
            recordingPaused={recordingState.paused}
            recordingSeconds={recordingSeconds}
            recordingAmplitude={recordingInfo.amplitude}
            recordingFileSize={recordingInfo.file_size}
            amplitudeHistory={amplitudeHistory.current}
            onPauseRecording={handlePauseRecording}
            onResumeRecording={handleResumeRecording}
            onStopRecording={handleStopRecording}
            showProcessing={showProcessing}
            onBackToSetup={() => setShowProcessing(false)}
          />
        )}

        {/* Main 4-tab content */}
        {showMainTabs && (
          <>
            {activeTab === 'characters' && <CharactersTab focusCharacterId={focusCharacterId} onFocusHandled={() => setFocusCharacterId(null)} />}
            {activeTab === 'library' && (
              <LibraryTab
                pipelineActive={pipelineActive}
                pipelineSessionDir={appState.sessionDir}
                onNavigateToProcessing={() => { setShowNewSession(true); setShowProcessing(true) }}
                refreshTrigger={libraryRefreshTrigger}
                stages={appState.stages}
                streamingChunks={streamingChunksRef.current}
                streamingVersion={streamingVersion}
                onNavigateToCharacter={handleNavigateToCharacter}
              />
            )}
            {activeTab === 'glossary' && (
              <GlossaryTab campaignId={activeCampaignId} campaignName={activeCampaignName} />
            )}
            {activeTab === 'chronicle' && (
              <ChronicleTab campaignId={activeCampaignId} campaignName={activeCampaignName} />
            )}
          </>
        )}
      </main>

      {/* NPC sync toast notification */}
      {npcNotification && (
        <div className="fixed bottom-4 right-4 z-50 animate-in fade-in slide-in-from-bottom-4 duration-300">
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-void/90 border border-gold/30 shadow-lg shadow-gold/10 backdrop-blur-sm">
            <Users className="w-4 h-4 text-gold flex-none" />
            <span className="text-sm font-body text-parchment/80">NPCs: {npcNotification}</span>
            <button onClick={() => setNpcNotification(null)} className="ml-2 text-parchment/30 hover:text-parchment/60 transition-colors">✕</button>
          </div>
        </div>
      )}
    </div>}
    </>
  )
}

// ── Standalone Create Campaign ───────────────────────────────────────────────

function CreateCampaignView({
  onCreated,
  onCancel,
}: {
  onCreated: (campaign: Campaign) => void
  onCancel: () => void
}) {
  const [allCharacters, setAllCharacters] = useState<Character[]>([])

  useEffect(() => {
    async function load() {
      const chars = await api('get_characters')
      setAllCharacters(chars ?? [])
    }
    load()
  }, [])

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-white/8 flex-shrink-0">
        <button onClick={onCancel} className="p-1.5 rounded hover:bg-white/5 text-parchment/50 hover:text-gold transition-colors">
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>
        </button>
        <Shield className="w-4 h-4 text-gold/50" />
        <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">New Campaign</h2>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6 flex justify-center">
        <div className="w-full max-w-md">
          <CreateCampaignForm
            onCreated={onCreated}
            onCancel={onCancel}
            allCharacters={allCharacters}
            onCharactersChanged={setAllCharacters}
          />
        </div>
      </div>
    </div>
  )
}

// ── Campaign Selector ────────────────────────────────────────────────────────

function CampaignSelector({
  campaigns,
  onSelect,
  onBack,
  onRefresh,
}: {
  campaigns: Campaign[]
  onSelect: (campaign: Campaign) => void
  onBack: () => void
  onRefresh: () => void
}) {
  const [loading, setLoading] = useState(campaigns.length === 0)

  useEffect(() => {
    if (campaigns.length > 0) setLoading(false)
  }, [campaigns])

  // Reload campaigns if we come in with empty list
  useEffect(() => {
    if (campaigns.length === 0) {
      onRefresh()
      const t = setTimeout(() => setLoading(false), 2000)
      return () => clearTimeout(t)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-white/8 flex-shrink-0">
        <button onClick={onBack} className="p-1.5 rounded hover:bg-white/5 text-parchment/50 hover:text-gold transition-colors">
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>
        </button>
        <Shield className="w-4 h-4 text-gold/50" />
        <h2 className="text-sm font-heading text-parchment/70 uppercase tracking-widest">Select Campaign</h2>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {loading && (
          <div className="flex items-center justify-center py-16">
            <p className="text-xs font-body text-parchment/30">Loading campaigns...</p>
          </div>
        )}

        {!loading && campaigns.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <Shield className="w-10 h-10 text-parchment/10" />
            <p className="text-sm font-heading text-parchment/30">No campaigns yet</p>
            <p className="text-xs font-body text-parchment/20">Go back and create a new campaign to get started</p>
            <button
              onClick={onBack}
              className="mt-3 flex items-center gap-2 px-4 py-2 rounded-md border border-gold/25 text-xs font-heading text-gold hover:bg-gold/10 transition-colors uppercase tracking-widest"
            >
              Back to Title
            </button>
          </div>
        )}

        {!loading && campaigns.length > 0 && (
          <div className="max-w-2xl mx-auto space-y-3">
            <p className="text-xs text-parchment/30 font-body mb-4">Choose a campaign to continue your adventure.</p>
            {campaigns.map(campaign => {
              const seasonCount = campaign.seasons.length
              const latestSeason = campaign.seasons[campaign.seasons.length - 1]
              const charCount = latestSeason ? latestSeason.characters?.length || 0 : 0
              return (
                <button
                  key={campaign.id}
                  onClick={() => onSelect(campaign)}
                  className="w-full text-left rounded-md border border-white/8 hover:border-gold/25 bg-white/3 hover:bg-gold/5 px-5 py-4 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <Shield className="w-5 h-5 text-gold/40 group-hover:text-gold/70 transition-colors flex-none" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-heading text-parchment/85 group-hover:text-gold transition-colors">{campaign.name}</p>
                      <p className="text-xs text-parchment/35 font-body mt-0.5">
                        {seasonCount} season{seasonCount !== 1 ? 's' : ''}
                        {charCount > 0 && ` · ${charCount} character${charCount !== 1 ? 's' : ''}`}
                      </p>
                    </div>
                    <ChevronDown className="w-4 h-4 text-parchment/20 -rotate-90 group-hover:text-gold/50 transition-colors" />
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
