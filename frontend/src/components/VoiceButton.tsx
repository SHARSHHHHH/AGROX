import { useEffect } from 'react'
import { useVoice } from '../hooks/useVoice'

/**
 * Microphone button available to BOTH farmers and balcony growers on the AI
 * Advisor. Streams speech to text (browser or Whisper), then hands the final
 * transcript to the parent via onResult.
 */
export function VoiceButton({
  language, onResult, onInterim,
}: {
  language: string
  onResult: (text: string) => void
  onInterim?: (text: string) => void
}) {
  const { recording, transcript, busy, error, start, stop, engine } = useVoice(language)

  useEffect(() => {
    if (transcript && onInterim) onInterim(transcript)
  }, [transcript]) // eslint-disable-line

  const handleClick = () => {
    if (recording) {
      stop()
      // Give the recognizer a tick to finalize, then emit
      setTimeout(() => transcript && onResult(transcript), 300)
    } else {
      start()
    }
  }

  return (
    <div className="flex flex-col items-center">
      <button
        onClick={handleClick}
        disabled={busy}
        title={`Voice input (${engine})`}
        className={`w-12 h-12 rounded-full flex items-center justify-center transition shadow
          ${recording ? 'bg-red-500 animate-pulse' : 'bg-field-600 hover:bg-field-700'}
          ${busy ? 'opacity-50' : ''} text-white`}
      >
        {busy ? '…' : recording ? '■' : '🎤'}
      </button>
      <span className="mt-1 text-[10px] text-gray-400">
        {busy ? 'transcribing' : recording ? 'listening…' : engine}
      </span>
      {error && <span className="text-[10px] text-red-500 max-w-[120px] text-center">{error}</span>}
    </div>
  )
}
