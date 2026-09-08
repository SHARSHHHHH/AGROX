import { useEffect, useRef, useState } from 'react'
import { useLanguage } from '../contexts/LanguageContext'
import { SPEECH_LANGS, SpeechLang, useSpeech } from '../hooks/useSpeech'

/**
 * Reusable voice components. These work on EVERY page, including Login and
 * Register, because they use the browser's speech engine and never call the
 * backend.
 */

// ---------------------------------------------------------------------------
// VoiceMic — a microphone button that pushes recognised text to a callback.
// ---------------------------------------------------------------------------

export function VoiceMic({
  onResult,
  onInterim,
  language,
  size = 'md',
  className = '',
}: {
  onResult: (text: string) => void
  onInterim?: (text: string) => void
  language?: SpeechLang
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  const { language: ctxLang, t } = useLanguage()
  const lang = language || ctxLang

  const { supported, listening, error, toggle, interim } = useSpeech(lang, {
    onFinal: onResult,
    onInterim,
  })

  const dims = { sm: 'w-9 h-9 text-sm', md: 'w-12 h-12 text-base', lg: 'w-16 h-16 text-xl' }[size]

  if (!supported) {
    return (
      <span className="text-[10px] text-gray-400 max-w-[110px] text-center leading-tight">
        {t('voice.unsupported')}
      </span>
    )
  }

  return (
    <div className={`flex flex-col items-center ${className}`}>
      <button
        type="button"
        onClick={toggle}
        aria-label={listening ? t('voice.listening') : t('voice.tap')}
        aria-pressed={listening}
        title={`${SPEECH_LANGS[lang].label} — ${listening ? t('voice.listening') : t('voice.tap')}`}
        className={`${dims} rounded-full flex items-center justify-center transition shadow text-white
          ${listening ? 'bg-red-500 animate-pulse ring-4 ring-red-200' : 'bg-field-600 hover:bg-field-700'}`}
      >
        {listening ? '■' : '🎤'}
      </button>

      <span className="mt-1 text-[10px] text-gray-400">
        {listening ? t('voice.listening') : SPEECH_LANGS[lang].native}
      </span>

      {listening && interim && (
        <span className="mt-0.5 text-[10px] text-gray-500 italic max-w-[160px] text-center truncate">
          {interim}
        </span>
      )}

      {error && (
        <span className="mt-0.5 text-[10px] text-red-500 max-w-[150px] text-center leading-tight">
          {error}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// VoiceField — a text input or textarea with a built-in microphone.
// Live speech fills the field as the user talks, so they can see and correct it
// before submitting. This is the component to use on forms.
// ---------------------------------------------------------------------------

export function VoiceField({
  value,
  onChange,
  placeholder = '',
  label,
  type = 'text',
  multiline = false,
  rows = 3,
  language,
  className = '',
  inputClassName = '',
  disabled = false,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  label?: string
  type?: string
  multiline?: boolean
  rows?: number
  language?: SpeechLang
  className?: string
  inputClassName?: string
  disabled?: boolean
}) {
  const { language: ctxLang, t } = useLanguage()
  const lang = language || ctxLang

  // Text already in the field when recording started, so dictation appends
  // instead of wiping what the user typed.
  const baseRef = useRef('')
  // Guards against a stale-closure race: the hook restarts recognition on a
  // language change, and without this flag the restart re-applied the OLD
  // base text over freshly dictated words, producing doubled or scrambled
  // input. This was the "voice text box filling is not good" bug.
  const dictatingRef = useRef(false)

  const compose = (spoken: string) => {
    const base = baseRef.current.trim()
    const said = spoken.trim()
    if (!base) return said
    if (!said) return base
    // Never re-append text the field already ends with.
    if (base.endsWith(said)) return base
    return `${base} ${said}`
  }

  const { supported, listening, toggle, error } = useSpeech(lang, {
    onInterim: (text) => {
      if (!dictatingRef.current) return
      onChange(compose(text))
    },
    onFinal: (text) => {
      if (!dictatingRef.current) return
      dictatingRef.current = false
      const finalValue = compose(text)
      onChange(finalValue)
      // Committed text becomes the new base, so a second dictation appends
      // to it rather than overwriting it.
      baseRef.current = finalValue
    },
  })

  const handleMic = () => {
    if (!listening) {
      baseRef.current = value.trim()
      dictatingRef.current = true
    } else {
      dictatingRef.current = false
    }
    toggle()
  }

  const base =
    'w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600 ' +
    (supported ? 'pr-12 ' : '') +
    (listening ? 'ring-2 ring-red-300 ' : '') +
    inputClassName

  return (
    <div className={className}>
      {label && (
        <label className="block text-xs font-semibold text-gray-600 mb-1">{label}</label>
      )}

      <div className="relative">
        {multiline ? (
          <textarea
            value={value}
            rows={rows}
            disabled={disabled}
            onChange={(e) => {
              if (!listening) baseRef.current = e.target.value
              onChange(e.target.value)
            }}
            placeholder={placeholder}
            className={base}
          />
        ) : (
          <input
            type={type}
            value={value}
            disabled={disabled}
            onChange={(e) => {
              if (!listening) baseRef.current = e.target.value
              onChange(e.target.value)
            }}
            placeholder={placeholder}
            className={base}
          />
        )}

        {supported && !disabled && (
          <button
            type="button"
            onClick={handleMic}
            aria-label={t('voice.input')}
            className={`absolute right-2 ${multiline ? 'top-2' : 'top-1/2 -translate-y-1/2'}
              w-8 h-8 rounded-full flex items-center justify-center text-sm transition
              ${listening ? 'bg-red-500 text-white animate-pulse' : 'bg-field-100 hover:bg-field-200'}`}
          >
            {listening ? '■' : '🎤'}
          </button>
        )}
      </div>

      {listening && (
        <p className="mt-1 text-[10px] text-red-600 flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          {SPEECH_LANGS[lang]?.native} — speak now
        </p>
      )}
      {error && <p className="mt-1 text-[10px] text-red-500">{error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// LanguagePicker — language selector usable before login.
// ---------------------------------------------------------------------------

export function LanguagePicker({ compact = false }: { compact?: boolean }) {
  const { language, setLanguage, t } = useLanguage()

  if (compact) {
    return (
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value as SpeechLang)}
        aria-label={t('login.language')}
        className="text-sm border rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-field-600 bg-white"
      >
        {Object.entries(SPEECH_LANGS).map(([code, info]) => (
          <option key={code} value={code}>{info.native}</option>
        ))}
      </select>
    )
  }

  return (
    <div>
      <label className="block text-xs font-semibold text-gray-600 mb-1.5">
        {t('login.language')}
      </label>
      <div className="grid grid-cols-3 gap-2">
        {Object.entries(SPEECH_LANGS).map(([code, info]) => (
          <button
            key={code}
            type="button"
            onClick={() => setLanguage(code as SpeechLang)}
            className={`px-2 py-2 rounded-xl text-sm border transition
              ${language === code
                ? 'bg-field-600 text-white border-field-600 shadow'
                : 'bg-white hover:bg-field-50 border-gray-200'}`}
          >
            {info.native}
          </button>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SpeakButton — reads text aloud. Pairs with any AI answer.
// ---------------------------------------------------------------------------

export function SpeakButton({ text, language }: { text: string; language?: SpeechLang }) {
  const { language: ctxLang } = useLanguage()
  const { speak, stopSpeaking, speaking } = useSpeech(language || ctxLang)
  const [mounted, setMounted] = useState(false)

  useEffect(() => { setMounted(true) }, [])
  if (!mounted || !text?.trim()) return null

  return (
    <button
      type="button"
      onClick={() => (speaking ? stopSpeaking() : speak(text))}
      className="text-xs text-field-700 hover:text-field-900 flex items-center gap-1"
      aria-label={speaking ? 'Stop reading' : 'Read aloud'}
    >
      {speaking ? '⏹ Stop' : '🔊 Listen'}
    </button>
  )
}
