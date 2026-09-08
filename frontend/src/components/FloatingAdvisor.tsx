import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AdvisorChatPanel } from './AdvisorChatPanel'
import { useLanguage } from '../contexts/LanguageContext'

const SEEN_KEY = 'agri_advisor_seen'

/**
 * Floating "AI Advisor" launcher — a cute crop icon pinned to the bottom-right
 * corner of every page. Replaces the old full-page-only entry: the advisor is
 * now always one tap away, without leaving whatever screen the farmer is on.
 *
 * The full /ai-advisor page still exists (linked from inside the panel) for
 * anyone who wants a larger, dedicated view — this widget just makes the
 * common case (a quick question) instant from anywhere in the app.
 */
export function FloatingAdvisor() {
  const [open, setOpen] = useState(false)
  const [everOpened, setEverOpened] = useState(() =>
    typeof window !== 'undefined' && localStorage.getItem(SEEN_KEY) === '1')
  const { t } = useLanguage()
  const nav = useNavigate()

  const toggle = () => {
    setOpen((o) => !o)
    if (!everOpened) {
      setEverOpened(true)
      localStorage.setItem(SEEN_KEY, '1')
    }
  }

  // Close on Escape for keyboard users.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <>
      {/* Launcher bubble */}
      <button
        onClick={toggle}
        aria-label={t('nav.ai')}
        title={t('nav.ai')}
        className={`fixed z-40 bottom-5 right-5 sm:bottom-6 sm:right-6 w-14 h-14 rounded-full
          bg-gradient-to-br from-field-600 to-field-800 text-white shadow-lg
          flex items-center justify-center text-2xl
          transition-transform hover:scale-110 active:scale-95
          ${open ? 'rotate-0' : ''}`}
      >
        {open ? (
          <span className="text-xl">✕</span>
        ) : (
          <span className="relative">
            <span className="drop-shadow-sm">🌱</span>
            {!everOpened && (
              <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-amber-400
                               border-2 border-white animate-pulse" />
            )}
          </span>
        )}
      </button>
      {!open && !everOpened && (
        <div className="fixed z-40 bottom-[4.6rem] right-5 sm:bottom-[5rem] sm:right-6
                        bg-white text-field-800 text-xs font-medium px-3 py-1.5
                        rounded-full shadow border border-field-100 animate-bounce
                        pointer-events-none">
          {t('ai.subtitle')}
        </div>
      )}

      {/* Panel */}
      {open && (
        <div
          className="fixed z-40 inset-0 sm:inset-auto sm:bottom-24 sm:right-6
                     sm:w-[380px] sm:h-[560px] bg-white sm:rounded-2xl shadow-2xl
                     border border-gray-100 flex flex-col overflow-hidden"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b
                          bg-gradient-to-r from-field-700 to-field-800 text-white shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xl">🌱</span>
              <div className="min-w-0">
                <div className="font-display font-bold text-sm leading-tight truncate">
                  {t('nav.ai')}
                </div>
                <div className="text-[11px] text-field-100 truncate">{t('ai.subtitle')}</div>
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => { setOpen(false); nav('/ai-advisor') }}
                title="Open full page"
                className="w-8 h-8 rounded-lg hover:bg-white/10 flex items-center justify-center text-sm"
              >
                ⤢
              </button>
              <button
                onClick={() => setOpen(false)}
                title="Close"
                className="w-8 h-8 rounded-lg hover:bg-white/10 flex items-center justify-center text-sm"
              >
                ✕
              </button>
            </div>
          </div>
          <div className="flex-1 min-h-0">
            <AdvisorChatPanel variant="widget" />
          </div>
        </div>
      )}
    </>
  )
}
