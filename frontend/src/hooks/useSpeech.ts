import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Browser-native speech recognition, usable on ANY page — including Login and
 * Register, where the user is not authenticated and no backend call is possible.
 *
 * WHY BROWSER-FIRST
 * -----------------
 * The previous voice flow recorded audio, uploaded it, and waited for Whisper
 * on the server. That has three problems for a farmer-facing app:
 *
 *   1. It cannot work before login — there is no token to call the API with.
 *   2. Round-trip latency on a rural connection is seconds, not milliseconds.
 *   3. It needs the backend and the model to be up.
 *
 * The Web Speech API runs entirely in the browser, streams interim results as
 * the user speaks, and costs nothing. Chrome, Edge and Android WebView support
 * it well; Firefox does not, and `supported` is false there so callers can
 * fall back to typing.
 *
 * ACCURACY NOTES
 * --------------
 * - `lang` must be a full BCP-47 tag ('ta-IN', not 'ta'). Passing a bare
 *   language code is the most common cause of poor recognition on Indian
 *   languages.
 * - `continuous` plus a manual restart in `onend` is required because Chrome
 *   silently stops after a few seconds of silence.
 * - Interim results are kept separate from finalised text so the caller can
 *   show live feedback without corrupting the committed transcript.
 */

export const SPEECH_LANGS: Record<string, { tag: string; label: string; native: string }> = {
  // Hindi first: it is the primary language for this deployment (Madhya
  // Pradesh) and has the best Web Speech recognition support of the three.
  hi: { tag: 'hi-IN', label: 'Hindi', native: 'हिन्दी' },
  en: { tag: 'en-IN', label: 'English', native: 'English' },
  ta: { tag: 'ta-IN', label: 'Tamil', native: 'தமிழ்' },
}

/**
 * Languages the UI is FULLY translated into. The picker only offers these,
 * because showing a language that falls back to English on most screens is
 * worse than not offering it at all.
 */
export const SUPPORTED_UI_LANGS = ['hi', 'en', 'ta'] as const

export type SpeechLang = keyof typeof SPEECH_LANGS

function getRecognition(): any | null {
  if (typeof window === 'undefined') return null
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  return SR ? new SR() : null
}

export function isSpeechSupported(): boolean {
  if (typeof window === 'undefined') return false
  return !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
}

interface UseSpeechOptions {
  /** Called once with the finalised transcript when the user stops. */
  onFinal?: (text: string) => void
  /** Called continuously with committed + interim text while speaking. */
  onInterim?: (text: string) => void
  /** Stop automatically after this many ms of silence. 0 disables. */
  silenceTimeoutMs?: number
}

export function useSpeech(language: SpeechLang = 'en', options: UseSpeechOptions = {}) {
  const { onFinal, onInterim, silenceTimeoutMs = 6000 } = options

  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const [speaking, setSpeaking] = useState(false)

  const recogRef = useRef<any>(null)
  const finalRef = useRef('')
  const silenceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const stoppingRef = useRef(false)

  // Keep callbacks in refs so restarting recognition never uses a stale closure.
  // This was the bug in the previous implementation: the transcript captured at
  // click time was empty, so the parent never received the result.
  const onFinalRef = useRef(onFinal)
  const onInterimRef = useRef(onInterim)
  useEffect(() => { onFinalRef.current = onFinal }, [onFinal])
  useEffect(() => { onInterimRef.current = onInterim }, [onInterim])

  const supported = isSpeechSupported()

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimer.current) {
      clearTimeout(silenceTimer.current)
      silenceTimer.current = null
    }
  }, [])

  const stop = useCallback(() => {
    clearSilenceTimer()
    stoppingRef.current = true

    const recog = recogRef.current
    recogRef.current = null // cleared FIRST so onend does not restart

    if (recog) {
      try { recog.stop() } catch { /* already stopped */ }
    }

    setListening(false)
    setInterim('')

    const finalText = finalRef.current.trim()
    if (finalText && onFinalRef.current) onFinalRef.current(finalText)
    return finalText
  }, [clearSilenceTimer])

  const start = useCallback(() => {
    if (!supported) {
      setError('Voice input is not supported in this browser. Please use Chrome or Edge, or type instead.')
      return
    }
    if (recogRef.current) return // already listening

    const recog = getRecognition()
    if (!recog) return

    recog.lang = SPEECH_LANGS[language]?.tag || 'en-IN'
    recog.interimResults = true
    recog.continuous = true
    // Ask for several candidates. Indian-language recognition frequently puts
    // the correct transcript second; we take the highest-confidence final.
    recog.maxAlternatives = 3

    finalRef.current = ''
    stoppingRef.current = false
    setTranscript('')
    setInterim('')
    setError('')
    setListening(true)

    recog.onresult = (event: any) => {
      let interimText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i]
        if (res.isFinal) {
          // Choose the alternative with the highest confidence, not just [0].
          let best = res[0]
          for (let a = 1; a < res.length; a++) {
            if ((res[a].confidence ?? 0) > (best.confidence ?? 0)) best = res[a]
          }
          finalRef.current += best.transcript + ' '
        } else {
          interimText += res[0].transcript
        }
      }

      const committed = finalRef.current.trim()
      setTranscript(committed)
      setInterim(interimText)

      const combined = (committed + ' ' + interimText).trim()
      if (onInterimRef.current) onInterimRef.current(combined)

      // Reset the silence countdown on every result.
      clearSilenceTimer()
      if (silenceTimeoutMs > 0) {
        silenceTimer.current = setTimeout(() => { stop() }, silenceTimeoutMs)
      }
    }

    recog.onerror = (event: any) => {
      // 'no-speech' and 'aborted' fire routinely in continuous mode.
      if (event.error === 'no-speech' || event.error === 'aborted') return

      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        setError('Microphone permission denied. Allow microphone access in your browser settings.')
        recogRef.current = null
        setListening(false)
        return
      }
      if (event.error === 'network') {
        setError('Voice recognition needs an internet connection.')
        return
      }
      setError(`Voice error: ${event.error}`)
    }

    recog.onend = () => {
      // Chrome stops on its own after a pause. Restart unless the user stopped.
      if (recogRef.current === recog && !stoppingRef.current) {
        try { recog.start() } catch { /* restart race, safe to ignore */ }
      }
    }

    recogRef.current = recog
    try {
      recog.start()
    } catch {
      recogRef.current = null
      setListening(false)
      setError('Could not start voice input. Please try again.')
    }
  }, [language, supported, silenceTimeoutMs, stop, clearSilenceTimer])

  const toggle = useCallback(() => {
    if (listening) stop()
    else start()
  }, [listening, start, stop])

  // ---- Text to speech (reads answers back to the farmer) ----
  //
  // WHY THIS IS MORE THAN `utter.lang = 'ta-IN'`
  // -------------------------------------------
  // Setting `lang` alone is a REQUEST, not an instruction. If the engine has
  // no voice installed for that tag it silently falls back to the system
  // default — which on almost every Indian phone and on desktop Chrome is a
  // US English voice. It then reads Tamil or Devanagari text with English
  // phonetics, producing the "it only speaks English" symptom.
  //
  // The fix is to pick a real voice object from getVoices() and assign it.
  //
  // Second trap: getVoices() returns an EMPTY array on first call in Chrome
  // and Android WebView, because the list loads asynchronously. Code that
  // reads it once at module load always finds nothing. `voiceschanged` is the
  // event that says the list is ready, so we keep a live cache.
  const voicesRef = useRef<SpeechSynthesisVoice[]>([])
  const [voiceReady, setVoiceReady] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return

    const load = () => {
      const list = window.speechSynthesis.getVoices()
      if (list.length) {
        voicesRef.current = list
        setVoiceReady(true)
      }
    }
    load()
    window.speechSynthesis.addEventListener('voiceschanged', load)
    return () => window.speechSynthesis.removeEventListener('voiceschanged', load)
  }, [])

  /**
   * Best available voice for a BCP-47 tag, most specific match first.
   *   1. exact tag        ta-IN
   *   2. same language    ta-LK, or any ta-*
   *   3. null             caller decides what to do about it
   *
   * Never falls through to an English voice: reading Tamil text aloud with an
   * English voice is worse than staying silent, because it sounds broken and
   * teaches the farmer the feature does not work.
   */
  const pickVoice = useCallback((tag: string): SpeechSynthesisVoice | null => {
    const voices = voicesRef.current
    if (!voices.length) return null

    const lower = tag.toLowerCase()
    const base = lower.split('-')[0]

    const exact = voices.find((v) => v.lang?.toLowerCase() === lower)
    if (exact) return exact

    const sameLang = voices.find(
      (v) => v.lang?.toLowerCase().split('-')[0] === base)
    return sameLang || null
  }, [])

  /** Is a voice actually installed for the current language? */
  const voiceAvailable = useCallback((lang: SpeechLang = language) => {
    const tag = SPEECH_LANGS[lang]?.tag || 'en-IN'
    return !!pickVoice(tag)
  }, [language, pickVoice])

  const audioRef = useRef<HTMLAudioElement | null>(null)

  /** Stop any server audio that is currently playing. */
  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ''
      audioRef.current = null
    }
  }, [])

  /**
   * Speak text in the farmer's language.
   *
   * STRATEGY: SERVER FIRST FOR TAMIL AND HINDI
   * ------------------------------------------
   * The browser can only speak a language the DEVICE has a voice pack for.
   * Tamil and Hindi packs are missing on most phones and on nearly every
   * desktop Chrome, and when they are missing speechSynthesis does not fail —
   * it quietly reads the text with a US English voice. That is why voice
   * "only came out in English".
   *
   * So for ta/hi we ask the backend for an MP3 first. Server synthesis works
   * regardless of what the device has installed. Browser speech is used only
   * as a fallback, and for English, where a voice is essentially always
   * present and the local path is faster.
   */
  const speak = useCallback(async (text: string) => {
    if (!text?.trim()) return
    setError('')

    const clean = text.trim()
    const needsServer = language === 'ta' || language === 'hi'
    const localVoice = pickVoice(SPEECH_LANGS[language]?.tag || 'en-IN')

    if (needsServer || !localVoice) {
      try {
        stopAudio()
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
          window.speechSynthesis.cancel()
        }
        setSpeaking(true)

        const res = await fetch('/api/tts/speak', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(localStorage.getItem('token')
              ? { Authorization: `Bearer ${localStorage.getItem('token')}` }
              : {}),
          },
          body: JSON.stringify({ text: clean, language }),
        })

        if (res.ok) {
          const blob = await res.blob()
          const audio = new Audio(URL.createObjectURL(blob))
          audioRef.current = audio
          audio.onended = () => { setSpeaking(false); audioRef.current = null }
          audio.onerror = () => { setSpeaking(false); audioRef.current = null }
          await audio.play()
          return
        }
        // 503 means the server cannot synthesise. Fall through to the browser,
        // which may still work if the device happens to have the voice.
        setSpeaking(false)
      } catch {
        setSpeaking(false)
      }
    }

    speakWithBrowser(clean)
  }, [language, pickVoice, stopAudio])

  /** Device speech synthesis. Used for English, and as the fallback path. */
  const speakWithBrowser = useCallback((text: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return

    const tag = SPEECH_LANGS[language]?.tag || 'en-IN'
    const voice = pickVoice(tag)

    if (!voice && language !== 'en') {
      // Say so rather than mispronouncing in English.
      setError(
        `No ${SPEECH_LANGS[language]?.native || language} voice is available. ` +
        `Server speech is offline and this device has no ${language} voice ` +
        `pack installed.`)
      setSpeaking(false)
      return
    }

    window.speechSynthesis.cancel()
    const utter = new SpeechSynthesisUtterance(text)
    if (voice) utter.voice = voice
    utter.lang = voice?.lang || tag
    utter.rate = 0.9
    utter.pitch = 1
    utter.onstart = () => setSpeaking(true)
    utter.onend = () => setSpeaking(false)
    utter.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(utter)
  }, [language, pickVoice])

  const stopSpeaking = useCallback(() => {
    // Two independent playback paths now exist, so stopping must cover both.
    // Cancelling only speechSynthesis would leave server audio playing on.
    stopAudio()
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    setSpeaking(false)
  }, [stopAudio])

  // Restart recognition when the language changes.
  //
  // recog.lang is read only when start() is called. Without this, switching
  // to Tamil or Hindi while a field was already mounted left the recogniser
  // listening in the previous language — the "voice only understands English"
  // bug. Recreating it picks up the new BCP-47 tag.
  useEffect(() => {
    if (!recogRef.current) return
    const wasListening = listening
    stop()
    if (wasListening) {
      // Let the old recogniser release the mic before claiming it again.
      const id = setTimeout(() => start(), 250)
      return () => clearTimeout(id)
    }
  }, [language]) // eslint-disable-line react-hooks/exhaustive-deps

  // Release the microphone if the component unmounts mid-recording.
  useEffect(() => {
    return () => {
      clearSilenceTimer()
      const recog = recogRef.current
      recogRef.current = null
      if (recog) { try { recog.stop() } catch { /* noop */ } }
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel()
      }
    }
  }, [clearSilenceTimer])

  return {
    supported,
    listening,
    transcript,
    interim,
    /** Committed text plus whatever is being spoken right now. */
    live: (transcript + ' ' + interim).trim(),
    error,
    speaking,
    /** True once the browser has finished loading its voice list. */
    voiceReady,
    /** Is a speech voice installed for the current (or given) language? */
    voiceAvailable,
    start,
    stop,
    toggle,
    speak,
    stopSpeaking,
  }
}
