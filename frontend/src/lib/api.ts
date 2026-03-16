/**
 * pywebview API bridge types and helpers.
 * The Python backend exposes methods via window.pywebview.api
 */

/** @deprecated Old embedded character format — use Character for global characters */
export interface CharacterInfo {
  name: string
  race: string
  class_name: string
  portrait: string
}

export interface CharacterHistoryEntry {
  session_id: string
  session_date: string
  campaign_name: string
  season_number: number
  auto_text: string
  manual_text: string
}

export interface CharacterAppearance {
  hair: string
  eyes: string
  skin: string
  height: string
  weight: string
  age: string
  gender: string
}

export interface CharacterBeyondData {
  name?: string
  race?: string
  class_name?: string
  subclass?: string
  level?: number
  background?: string
  alignment?: string
  backstory?: string
  appearance?: CharacterAppearance
  personality_traits?: string
  ideals?: string
  bonds?: string
  flaws?: string
  ability_scores?: Record<string, number>
  hp?: number
  spells?: string[]
  equipment?: string[]
  notes?: Record<string, string>
  backpack?: Array<{ name: string; quantity: number; equipped: boolean; magic: boolean }>
  currency?: Record<string, number>
  proficiencies?: string[]
  languages?: string[]
  features?: string[]
  feats?: string[]
  base_speed?: number
  resistances?: string[]
  immunities?: string[]
  vulnerabilities?: string[]
  condition_immunities?: string[]
  faith?: string
}

export interface PortraitEntry {
  path: string
  is_primary: boolean
}

export interface Character {
  id: string
  name: string
  race: string
  class_name: string
  subclass: string
  level: number
  specialty: string
  beyond_url: string
  beyond_avatar_path: string
  portrait_path: string
  portraits: PortraitEntry[]
  fullbody_path: string
  fullbodies: PortraitEntry[]
  beyond_data: CharacterBeyondData
  beyond_last_synced: string
  history: CharacterHistoryEntry[]
  history_summary: string
  is_dm?: boolean
  is_npc?: boolean
  npc_description?: string
  campaign_ids?: string[]
}

export interface Season {
  id: string
  number: number
  characters: string[]  // character IDs (global registry)
}

export interface Campaign {
  id: string
  name: string
  beyond_url?: string
  seasons: Season[]
}

export interface Scene {
  title: string
  description: string
  videoPrompt: string
}

export interface TimelineEvent {
  time: string | null
  title: string
  summary: string
  details: string
  importance: 'high' | 'medium' | 'low'
  type?: string
}

export interface SessionEntry {
  id: string
  date: string
  display_name?: string
  campaign_id: string
  campaign_name: string
  season_id: string
  season_number: number
  character_names: string[]
  character_ids?: string[]
  character_map?: Record<string, string>
  output_dir: string
  audio_path: string | null
  json_path: string | null
  txt_path: string | null
  srt_path: string | null
  summary_path: string | null
  dm_notes_path: string | null
  scenes_path: string | null
  timeline_path: string | null
  illustration_path: string | null
  glossary_path: string | null
  character_updates_path: string | null
  leaderboard_path: string | null
  locations_path: string | null
  npcs_path: string | null
  loot_path: string | null
  missions_path: string | null
  files: {
    audio: boolean
    transcript: boolean
    srt: boolean
    summary: boolean
    dm_notes: boolean
    scenes: boolean
    timeline: boolean
    illustration: boolean
    glossary: boolean
    character_updates: boolean
    leaderboard: boolean
    locations: boolean
    npcs: boolean
    loot: boolean
    missions: boolean
  }
}

export interface GlossaryEntry {
  category: string
  definition: string
  description: string
}

export type PipelineStage = 'transcription' | 'saving_transcript' | 'transcript_correction' | 'speaker_mapping' | 'updating_transcript' | 'transcript_review' | 'timeline' | 'summary' | 'dm_notes' | 'character_updates' | 'glossary' | 'leaderboard' | 'locations' | 'npcs' | 'loot' | 'missions' | 'scenes' | 'illustration'
export type StageStatus = 'idle' | 'running' | 'done' | 'error' | 'needs_review'

export interface SpeakerReviewPayload {
  jsonPath: string
  partialMapping: Record<string, string>
  unmappedSpeakers: string[]
  characterNames: string[]
  sampleLines?: Record<string, string[]>
  confidences?: Record<string, number>
  evidence?: Record<string, string>
  error?: string
}

export interface EntityReviewCard {
  id: string
  action: 'create' | 'update'
  entity_type: string
  name: string
  confidence: number
  reasoning: string
  current_state: any | null
  proposed: Record<string, any>
  diff?: Record<string, { old: any; new: any }>
}

export interface EntityReviewPayload {
  stage: string
  campaign_id: string
  session_id: string
  cards: EntityReviewCard[]
  auto_applied: Array<{ name: string; action: string; confidence: number }>
}

export interface TranscriptReviewPayload {
  transcript: string
  txtPath: string
}

declare global {
  interface Window {
    pywebview?: { api: PyWebViewAPI }
    _receiveLog?: (line: string, isStderr: boolean) => void
    _onPipelineStage?: (stage: PipelineStage, status: StageStatus, data: any) => void
    _onLLMChunk?: (stage: PipelineStage, chunk: string) => void
    _pyDragDrop?: (payload: { type: 'audio' | 'transcript'; path: string }) => void
    _pyDragOver?: (dtype: string) => void
    _pyDragLeave?: () => void
    _onNpcSync?: (data: { new: string[]; updated: string[] }) => void
  }
}

interface PyWebViewAPI {
  // Dialogs
  pick_audio_file(): Promise<string | null>
  pick_transcript_file(): Promise<string | null>
  pick_character_portrait(): Promise<string | null>

  // Tokens / settings
  get_hf_token(): Promise<string>
  set_hf_token(token: string): Promise<void>
  get_claude_token(): Promise<string>
  set_claude_token(token: string): Promise<void>
  get_openai_token(): Promise<string>
  set_openai_token(token: string): Promise<void>
  get_gemini_token(): Promise<string>
  set_gemini_token(token: string): Promise<void>
  get_pref(key: string, fallback: string): Promise<string>
  set_pref(key: string, value: string): Promise<void>

  // Session lifecycle
  create_session(
    campaignId: string,
    seasonId: string,
    dateOverride?: string
  ): Promise<{ ok: boolean; session_dir?: string; session_id?: string; error?: string }>
  copy_audio_to_session(
    audioPath: string,
    sessionDir: string
  ): Promise<{ ok: boolean; path?: string; error?: string }>

  // Audio recording
  start_recording(sessionDir: string): Promise<{ ok: boolean; path?: string; error?: string }>
  stop_recording(): Promise<{ ok: boolean; path?: string; error?: string }>
  get_recording_duration(): Promise<number>
  get_recording_info(): Promise<{ duration: number; amplitude: number; file_size: number; paused: boolean }>
  pause_recording(): Promise<{ ok: boolean; error?: string }>
  resume_recording(): Promise<{ ok: boolean; error?: string }>
  is_recording_paused(): Promise<boolean>

  // Job control
  start_job(
    audioPath: string,
    model: string,
    numSpeakers: number,
    characterNames: string[],
    language: string
  ): Promise<{ ok: boolean; error?: string }>
  stop_job(): Promise<void>
  stop_pipeline(): Promise<void>

  // Transcript import
  start_pipeline_from_transcript(
    transcriptPath: string,
    diarized?: boolean
  ): Promise<{ ok: boolean; error?: string }>

  // Speaker mapping completion (manual review fallback)
  complete_speaker_mapping(
    jsonPath: string,
    mapping: Record<string, string>
  ): Promise<{ ok: boolean; error?: string }>

  complete_entity_review(
    stage: string,
    decisions: Array<{ id: string; action: 'accept' | 'edit' | 'decline'; name?: string; proposed?: Record<string, any>; edited?: Record<string, any> }>
  ): Promise<{ ok: boolean }>

  complete_transcript_review(corrected_text: string | null): Promise<{ ok: boolean }>

  // Campaign management
  get_campaigns(): Promise<Campaign[]>
  create_campaign(
    name: string,
    seasons: Array<{ number: number; characters: string[] }>
  ): Promise<{ ok: boolean; campaign?: Campaign; error?: string }>
  add_season(
    campaignId: string,
    number: number,
    characters: string[]
  ): Promise<{ ok: boolean; season?: Season; error?: string }>
  update_season(
    campaignId: string,
    seasonId: string,
    characters: string[]
  ): Promise<{ ok: boolean; error?: string }>
  update_campaign(
    campaignId: string,
    name: string,
    beyondUrl: string
  ): Promise<{ ok: boolean; error?: string }>
  delete_campaign(campaignId: string): Promise<{ ok: boolean; error?: string }>

  // Glossary
  get_campaign_glossary(campaignId: string): Promise<Record<string, GlossaryEntry>>
  update_campaign_glossary(campaignId: string, glossary: Record<string, GlossaryEntry>): Promise<{ ok: boolean; error?: string }>

  // Character management
  get_characters(): Promise<Character[]>
  get_character(charId: string): Promise<{ ok: boolean; character?: Character; error?: string }>
  get_characters_by_ids(charIds: string[]): Promise<Character[]>
  get_character_campaigns(charId: string): Promise<{ campaign_id: string; campaign_name: string; season_number: number }[]>
  create_character(
    name: string,
    race?: string,
    class_name?: string,
    subclass?: string,
    level?: number,
    specialty?: string,
    beyond_url?: string,
    portrait_path?: string
  ): Promise<{ ok: boolean; character?: Character; error?: string }>
  update_character(
    charId: string,
    fields: Partial<Character>
  ): Promise<{ ok: boolean; character?: Character; error?: string }>
  delete_character(charId: string): Promise<{ ok: boolean; error?: string }>
  sync_beyond_character(charId: string): Promise<{ ok: boolean; character?: Character; error?: string }>
  pick_character_realistic_portrait(): Promise<string | null>
  generate_character_portrait(charId: string): Promise<{ ok: boolean; portrait_path?: string; character?: Character; error?: string }>
  set_primary_portrait(charId: string, portraitPath: string): Promise<{ ok: boolean; character?: Character; error?: string }>
  delete_portrait(charId: string, portraitPath: string): Promise<{ ok: boolean; character?: Character; error?: string }>
  // Full-body
  generate_character_fullbody(charId: string): Promise<{ ok: boolean; fullbody_path?: string; character?: Character; error?: string }>
  set_primary_fullbody(charId: string, fullbodyPath: string): Promise<{ ok: boolean; character?: Character; error?: string }>
  delete_fullbody(charId: string, fullbodyPath: string): Promise<{ ok: boolean; character?: Character; error?: string }>
  // NPC management
  get_npcs(campaignId?: string): Promise<Character[]>
  generate_npc_portrait(charId: string): Promise<{ ok: boolean; portrait_path?: string; character?: Character; error?: string }>
  generate_npc_fullbody(charId: string): Promise<{ ok: boolean; fullbody_path?: string; character?: Character; error?: string }>
  update_npc_description(charId: string, description: string): Promise<{ ok: boolean; character?: Character; error?: string }>
  update_character_history_manual(
    charId: string,
    sessionId: string,
    manualText: string
  ): Promise<{ ok: boolean; error?: string }>
  generate_character_history_summary(
    charId: string
  ): Promise<{ ok: boolean; summary?: string; error?: string }>
  update_character_history_auto(
    charId: string,
    sessionId: string,
    autoText: string
  ): Promise<{ ok: boolean; error?: string }>
  update_character_history_summary(
    charId: string,
    summary: string
  ): Promise<{ ok: boolean; error?: string }>

  // LLM streaming control
  stop_llm_stage(stage: PipelineStage): Promise<void>
  skip_llm_stage(stage: PipelineStage): Promise<void>
  set_skipped_stages(stages: string[]): Promise<{ ok: boolean }>
  run_single_stage(sessionId: string, stage: string): Promise<{ ok: boolean; error?: string }>
  retry_transcription(sessionId: string, model?: string, language?: string): Promise<{ ok: boolean; error?: string }>

  // Session Library
  get_sessions(): Promise<SessionEntry[]>
  open_path(path: string): Promise<{ ok: boolean; error?: string }>
  rename_session(id: string, displayName: string): Promise<{ ok: boolean; error?: string }>
  update_session_date(id: string, date: string): Promise<{ ok: boolean; error?: string }>
  delete_session_folder(id: string): Promise<{ ok: boolean; error?: string }>
  read_file(path: string): Promise<{ ok: boolean; content: string; error?: string }>
  generate_session_title(sessionId: string): Promise<{ ok: boolean; title?: string; error?: string }>
  get_season_digest(campaignId: string, seasonId: string): Promise<{ ok: boolean; digest?: any; error?: string }>
  generate_season_digest(campaignId: string, seasonId: string): Promise<{ ok: boolean; digest?: any; error?: string }>
  download_file(path: string): Promise<{ ok: boolean; dest?: string; error?: string }>
  download_session_zip(sessionId: string): Promise<{ ok: boolean; dest?: string; error?: string }>
}

/** Call a pywebview API method safely (no-op stub in browser preview) */
export async function api<K extends keyof PyWebViewAPI>(
  method: K,
  ...args: Parameters<PyWebViewAPI[K]>
): Promise<ReturnType<PyWebViewAPI[K]>> {
  if (!window.pywebview) {
    console.warn(`[api] pywebview not available — called: ${method}`, args)
    if (method === 'get_hf_token' || method === 'get_claude_token' || method === 'get_openai_token' || method === 'get_gemini_token') return '' as any
    if (method === 'get_pref') return args[1] as any
    if (method === 'get_recording_duration') return 0 as any
    if (method === 'get_recording_info') return { duration: 0, amplitude: 0, file_size: 0, paused: false } as any
    if (method === 'get_sessions') return [] as any
    if (method === 'get_campaigns') return [] as any
    if (method === 'get_characters') return [] as any
    if (method === 'get_characters_by_ids') return [] as any
    if (method === 'get_campaign_glossary') return {} as any
    if (method === 'create_session') return { ok: true, session_dir: '/tmp/demo_session', session_id: 'demo' } as any
    if (method === 'copy_audio_to_session') return { ok: true, path: args[0] } as any
    if (method === 'start_pipeline_from_transcript') return { ok: true } as any
    if (method === 'rename_session' || method === 'update_session_date') return { ok: true } as any
    if (method === 'delete_session_folder') return { ok: true } as any
    if (method === 'read_file') return { ok: false, content: '', error: 'Not available in browser' } as any
    return null as any
  }
  const fn = window.pywebview.api[method] as (...a: any[]) => Promise<any>
  return fn(...args)
}

export {}
