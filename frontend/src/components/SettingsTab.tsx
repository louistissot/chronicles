import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { api } from '@/lib/api'
import { Key, Save, Eye, EyeOff, Shield, Sun, Moon } from 'lucide-react'

interface TokenFieldProps {
  label: string
  description: string
  value: string
  onChange: (v: string) => void
  onSave: () => void
  status: 'saved' | 'unsaved' | 'saving'
  placeholder?: string
}

function TokenField({ label, description, value, onChange, onSave, status, placeholder }: TokenFieldProps) {
  const [show, setShow] = useState(false)

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-parchment/70 uppercase tracking-widest text-xs font-heading">
          {label}
        </Label>
        {status === 'saved' && (
          <Badge variant="success" className="gap-1">
            <Shield className="w-3 h-3" />
            Stored in Keychain
          </Badge>
        )}
        {status === 'unsaved' && value && (
          <Badge variant="secondary">Unsaved</Badge>
        )}
      </div>
      <p className="text-xs text-parchment/35 font-body">{description}</p>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gold/30 pointer-events-none" />
          <Input
            type={show ? 'text' : 'password'}
            value={value}
            onChange={e => onChange(e.target.value)}
            placeholder={placeholder || 'Paste token here…'}
            className="pl-9 pr-10 font-mono text-xs"
          />
          <button
            className="absolute right-3 top-1/2 -translate-y-1/2 text-parchment/30 hover:text-parchment/60 transition-colors"
            onClick={() => setShow(s => !s)}
            type="button"
            tabIndex={-1}
          >
            {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          </button>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onSave}
          disabled={!value || status === 'saving'}
          className="gap-1.5 shrink-0"
        >
          <Save className="w-3.5 h-3.5" />
          Save
        </Button>
      </div>
    </div>
  )
}

interface SettingsTabProps {
  theme: 'dark' | 'light'
  onThemeChange: () => void
}

export function SettingsTab({ theme, onThemeChange }: SettingsTabProps) {
  const [hfToken, setHfToken] = useState('')
  const [claudeToken, setClaudeToken] = useState('')
  const [openaiToken, setOpenaiToken] = useState('')
  const [geminiToken, setGeminiToken] = useState('')
  const [hfStatus, setHfStatus] = useState<'saved' | 'unsaved' | 'saving'>('unsaved')
  const [claudeStatus, setClaudeStatus] = useState<'saved' | 'unsaved' | 'saving'>('unsaved')
  const [openaiStatus, setOpenaiStatus] = useState<'saved' | 'unsaved' | 'saving'>('unsaved')
  const [geminiStatus, setGeminiStatus] = useState<'saved' | 'unsaved' | 'saving'>('unsaved')

  const [provider, setProvider] = useState<'anthropic' | 'openai'>('anthropic')
  const [openaiModel, setOpenaiModel] = useState('gpt-4.5')

  useEffect(() => {
    async function load() {
      const [hf, cl, oa, gem, prov, model] = await Promise.all([
        api('get_hf_token'),
        api('get_claude_token'),
        api('get_openai_token'),
        api('get_gemini_token'),
        api('get_pref', 'llm_provider', 'anthropic'),
        api('get_pref', 'openai_model', 'gpt-4.5'),
      ])
      if (hf) { setHfToken(hf); setHfStatus('saved') }
      if (cl) { setClaudeToken(cl); setClaudeStatus('saved') }
      if (oa) { setOpenaiToken(oa); setOpenaiStatus('saved') }
      if (gem) { setGeminiToken(gem); setGeminiStatus('saved') }
      if (prov === 'openai') setProvider('openai')
      if (model) setOpenaiModel(model)
    }
    load()
  }, [])

  async function saveHf() {
    setHfStatus('saving')
    await api('set_hf_token', hfToken)
    setHfStatus('saved')
  }

  async function saveClaude() {
    setClaudeStatus('saving')
    await api('set_claude_token', claudeToken)
    setClaudeStatus('saved')
  }

  async function saveOpenAI() {
    setOpenaiStatus('saving')
    await api('set_openai_token', openaiToken)
    setOpenaiStatus('saved')
  }

  async function saveGemini() {
    setGeminiStatus('saving')
    await api('set_gemini_token', geminiToken)
    setGeminiStatus('saved')
  }

  function handleProviderChange(p: string) {
    const prov = p as 'anthropic' | 'openai'
    setProvider(prov)
    api('set_pref', 'llm_provider', prov)
  }

  function handleModelChange(m: string) {
    setOpenaiModel(m)
    api('set_pref', 'openai_model', m)
  }

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="max-w-xl mx-auto space-y-8">
        {/* Header */}
        <div className="space-y-1">
          <h2
            className="text-sm font-heading text-gold/80 uppercase tracking-widest"
            style={{ fontFamily: "'Cinzel', serif" }}
          >
            Arcane Configuration
          </h2>
          <p className="text-xs text-parchment/40 font-body">
            Tokens are stored securely in the macOS Keychain — never in plain text.
          </p>
        </div>

        <Separator />

        {/* Appearance */}
        <div className="space-y-3">
          <Label className="text-parchment/70 uppercase tracking-widest text-xs font-heading">
            Appearance
          </Label>
          <div className="flex items-center gap-3">
            <button
              onClick={onThemeChange}
              className={`flex items-center gap-2 px-4 py-2 rounded-md border text-xs font-body transition-all ${
                theme === 'dark'
                  ? 'border-gold/40 bg-gold/10 text-gold'
                  : 'border-parchment/20 text-parchment/40 hover:border-parchment/40'
              }`}
            >
              <Moon className="w-3.5 h-3.5" /> Dark
            </button>
            <button
              onClick={onThemeChange}
              className={`flex items-center gap-2 px-4 py-2 rounded-md border text-xs font-body transition-all ${
                theme === 'light'
                  ? 'border-gold/40 bg-gold/10 text-gold'
                  : 'border-parchment/20 text-parchment/40 hover:border-parchment/40'
              }`}
            >
              <Sun className="w-3.5 h-3.5" /> Light
            </button>
          </div>
        </div>

        <Separator />

        {/* HF Token — always needed */}
        <TokenField
          label="HuggingFace Token"
          description="Required for speaker diarization via pyannote.audio. Get yours at huggingface.co/settings/tokens"
          value={hfToken}
          onChange={v => { setHfToken(v); setHfStatus('unsaved') }}
          onSave={saveHf}
          status={hfStatus}
          placeholder="hf_…"
        />

        <Separator />

        {/* AI Provider — dropdown */}
        <div className="space-y-3">
          <div>
            <Label className="text-parchment/70 uppercase tracking-widest text-xs font-heading">
              AI Provider
            </Label>
            <p className="text-xs text-parchment/35 font-body mt-1">
              Used for Speaker Auto-suggest, Adventure Summary, Scene Extracts, and DM Notes.
            </p>
          </div>
          <Select value={provider} onValueChange={handleProviderChange}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="anthropic">Anthropic — Claude sonnet-4-6</SelectItem>
              <SelectItem value="openai">OpenAI — ChatGPT</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Claude key — only when anthropic */}
        {provider === 'anthropic' && (
          <TokenField
            label="Claude API Key"
            description="claude-sonnet-4-6 · Get yours at console.anthropic.com"
            value={claudeToken}
            onChange={v => { setClaudeToken(v); setClaudeStatus('unsaved') }}
            onSave={saveClaude}
            status={claudeStatus}
            placeholder="sk-ant-…"
          />
        )}

        {/* OpenAI key + model — only when openai */}
        {provider === 'openai' && (
          <>
            <TokenField
              label="OpenAI API Key"
              description="Get yours at platform.openai.com/api-keys"
              value={openaiToken}
              onChange={v => { setOpenaiToken(v); setOpenaiStatus('unsaved') }}
              onSave={saveOpenAI}
              status={openaiStatus}
              placeholder="sk-…"
            />

            <div className="space-y-2">
              <Label className="text-parchment/70 uppercase tracking-widest text-xs font-heading">
                Model
              </Label>
              <Input
                value={openaiModel}
                onChange={e => handleModelChange(e.target.value)}
                placeholder="gpt-4.5"
                className="font-mono text-xs"
              />
              <p className="text-xs text-parchment/30 font-body">
                Default: gpt-4.5. You can use any chat-compatible model (e.g. gpt-4o, o3, o4-mini).
              </p>
            </div>
          </>
        )}

        <Separator />

        {/* Gemini — Image Generation */}
        <div className="space-y-3">
          <div>
            <Label className="text-parchment/70 uppercase tracking-widest text-xs font-heading">
              Google Gemini (Image Generation)
            </Label>
            <p className="text-xs text-parchment/35 font-body mt-1">
              Optional. Used for generating session illustrations via Imagen 3. Without this key, the illustration step is skipped.
            </p>
          </div>
          <TokenField
            label="Gemini API Key"
            description="Get yours at aistudio.google.com/apikey"
            value={geminiToken}
            onChange={v => { setGeminiToken(v); setGeminiStatus('unsaved') }}
            onSave={saveGemini}
            status={geminiStatus}
            placeholder="AIza…"
          />
        </div>

        <Separator />

        {/* Info */}
        <div className="rounded-md parchment-scroll p-4 space-y-2">
          <p className="text-xs font-heading text-gold/50 uppercase tracking-widest">About</p>
          <p className="text-xs text-parchment/40 font-body leading-relaxed">
            Chronicles uses WhisperX with pyannote speaker diarization to transcribe your session recordings.
            The HuggingFace token must be associated with an account that has accepted the pyannote speaker
            diarization model license at huggingface.co/pyannote/speaker-diarization-3.1
          </p>
          <p className="text-xs text-parchment/30 font-body pt-1">
            v1.4.0 · whisperx 3.7.4
          </p>
        </div>
      </div>
    </div>
  )
}
