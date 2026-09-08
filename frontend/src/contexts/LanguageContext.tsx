import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { SPEECH_LANGS, SpeechLang } from '../hooks/useSpeech'
import { Lang, translate, translateValue } from '../i18n/translations'

/**
 * App-wide language, available BEFORE login.
 *
 * The user's language lives in the database once they register, but Login and
 * Register render before any token exists. Storing the choice in localStorage
 * means a Tamil-speaking farmer can pick their language on the login screen and
 * have it persist through registration and into the app.
 */

interface LanguageContextValue {
  language: SpeechLang
  setLanguage: (lang: SpeechLang) => void
  /** UI string by key. */
  t: (key: string) => string
  /** Data value from the backend (crop, disease, severity, tier...). */
  tv: (value: string) => string
}

const LanguageContext = createContext<LanguageContextValue>({
  language: 'en',
  setLanguage: () => {},
  t: (k) => k,
  tv: (v) => v,
})

const STORAGE_KEY = 'agri_language'

/**
 * UI strings for screens that render before login, where the backend
 * translation endpoint is unreachable. In-app content is still translated
 * server-side by the existing NLP pipeline.
 */
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<SpeechLang>(() => {
    if (typeof window === 'undefined') return 'en'
    const saved = localStorage.getItem(STORAGE_KEY) as SpeechLang | null
    if (saved && saved in SPEECH_LANGS) return saved

    // Follow the browser locale when we fully support it. Otherwise default
    // to Hindi, the primary language for this deployment, rather than English.
    const browser = navigator.language?.split('-')[0]
    return (browser && browser in SPEECH_LANGS) ? (browser as SpeechLang) : 'hi'
  })

  const setLanguage = (lang: SpeechLang) => {
    setLanguageState(lang)
    localStorage.setItem(STORAGE_KEY, lang)
  }

  // Adopt the language stored on the user record once they log in.
  useEffect(() => {
    const raw = localStorage.getItem('user')
    if (!raw) return
    try {
      const user = JSON.parse(raw)
      if (user?.language && user.language in SPEECH_LANGS
          && !localStorage.getItem(STORAGE_KEY)) {
        setLanguage(user.language)
      }
    } catch { /* ignore malformed */ }
  }, [])

  const t = (key: string): string => translate(language as Lang, key)
  const tv = (value: string): string => translateValue(language as Lang, value)

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t, tv }}>
      {children}
    </LanguageContext.Provider>
  )
}

export const useLanguage = () => useContext(LanguageContext)
