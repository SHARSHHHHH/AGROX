import { useEffect, useState } from 'react'
import { api } from '../services/api'
import { useLanguage } from '../contexts/LanguageContext'

/**
 * Shows a clear banner when the backend cannot be reached.
 *
 * WHY THIS EXISTS
 * ---------------
 * When uvicorn is not running, or is running on a port the dev proxy is not
 * pointed at, every request fails with ECONNREFUSED and the dashboard renders
 * empty cards — no numbers, no error, no clue. That looks exactly like a
 * database problem or lost data, and sends you hunting in the wrong place.
 *
 * A blank screen is the worst possible failure message. This turns it into an
 * actionable one.
 */
export function ConnectionBanner() {
  const { t } = useLanguage()
  const [state, setState] = useState<'checking' | 'ok' | 'down'>('checking')
  const [detail, setDetail] = useState('')

  const check = async () => {
    try {
      const r = await api.get('/api/health', { timeout: 5000 })
      setState('ok')
      setDetail(`${r.data.llm_provider} · ${r.data.vision_provider}`)
    } catch (err: any) {
      // A 401 still proves the backend answered — that is not "down".
      if (err?.response?.status) {
        setState('ok')
        return
      }
      setState('down')
    }
  }

  useEffect(() => {
    check()
    // Re-check periodically so the banner clears itself once you start the
    // backend, without needing a page reload.
    const id = setInterval(check, 15000)
    return () => clearInterval(id)
  }, [])

  if (state !== 'down') return null

  return (
    <div className="bg-red-50 border-b-2 border-red-300 px-4 py-3">
      <div className="max-w-5xl mx-auto">
        <p className="text-sm font-bold text-red-800">
          ⚠ {t('conn.title')}
        </p>
        <p className="text-xs text-red-700 mt-1">{t('conn.body')}</p>
        <pre className="text-[11px] bg-white/70 rounded-lg p-2 mt-2 overflow-x-auto
                        text-gray-700 border border-red-200">
{`cd backend
uvicorn app.main:app --reload`}
        </pre>
        <p className="text-[11px] text-red-700 mt-1.5">{t('conn.port')}</p>
        <button onClick={check}
                className="mt-2 text-xs font-semibold text-red-800 underline">
          {t('conn.retry')}
        </button>
      </div>
    </div>
  )
}
