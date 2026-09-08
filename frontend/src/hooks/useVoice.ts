import { useRef, useState, useCallback } from 'react'
import { transcribeVoice } from '../services/api'

/**
 * Voice input hook. Two engines:
 *  1) Browser Web Speech API (instant, no server) — used when available.
 *  2) MediaRecorder -> backend Whisper (multilingual, higher accuracy) — fallback
 *     for browsers without Web Speech support.
 *
 * Language codes map to BCP-47 for the browser engine.
 */
const BCP47: Record<string, string> = {
  en: 'en-IN', ta: 'ta-IN', te: 'te-IN', kn: 'kn-IN', ml: 'ml-IN', hi: 'hi-IN',
}

export function useVoice(language = 'en') {
  const [recording, setRecording] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const recogRef = useRef<any>(null)
  const shouldListenRef = useRef(false)

  const hasBrowserSpeech =
    typeof window !== 'undefined' &&
    ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)

  // ---- Engine 1: Browser Web Speech ----
  const startBrowser = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    const recog = new SR()
    recog.lang = BCP47[language] || 'en-IN'
    recog.interimResults = true
    recog.continuous = true
    recogRef.current = recog
    shouldListenRef.current = true
    setTranscript('')
    setError('')
    recog.onresult = (e: any) => {
      let text = ''
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript
      setTranscript(text)
    }
    recog.onerror = (e: any) => {
      if (e.error === 'no-speech' && shouldListenRef.current) return
      setError(`Voice error: ${e.error}`)
    }
    recog.onend = () => {
      if (!shouldListenRef.current) {
        setRecording(false)
        return
      }
      try {
        recog.start()
      } catch {
        setRecording(false)
      }
    }
    recog.start()
    setRecording(true)
  }, [language])

  const stopBrowser = useCallback(() => {
    shouldListenRef.current = false
    recogRef.current?.stop()
    setRecording(false)
  }, [])

  // ---- Engine 2: MediaRecorder -> Whisper ----
  const startRecorder = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      chunksRef.current = []
      mr.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setBusy(true)
        try {
          const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
          const res = await transcribeVoice(blob)
          if (res.error) setError(res.error)
          else setTranscript(res.transcript || '')
        } catch {
          setError('Could not transcribe audio. Please try again.')
        } finally {
          setBusy(false)
        }
      }
      mediaRef.current = mr
      mr.start()
      setRecording(true)
      setError('')
    } catch {
      setError('Microphone permission denied.')
    }
  }, [])

  const stopRecorder = useCallback(() => {
    mediaRef.current?.stop()
    setRecording(false)
  }, [])

  // Prefer browser speech for every supported language. Backend Whisper is
  // optional and only used when the browser has no speech recognition API.
  const useWhisper = !hasBrowserSpeech

  const start = useWhisper ? startRecorder : startBrowser
  const stop = useWhisper ? stopRecorder : stopBrowser

  return { recording, transcript, setTranscript, busy, error, start, stop,
           engine: useWhisper ? 'whisper' : 'browser' }
}
