import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { chat, askAdmin, getUser } from '../services/api'
import { VoiceMic } from './VoiceInput'
import { useLanguage } from '../contexts/LanguageContext'
import { useSpeech, SPEECH_LANGS } from '../hooks/useSpeech'
import { matchPageCommand, routeForIntent, PageMatch } from '../utils/agentRouter'
import { Lang } from '../i18n/translations'
import { usePageContext } from '../contexts/PageContext'

// Phrases that ask about the CURRENT SCREEN rather than a farming question —
// answered instantly from the live page context, no backend round trip.
const PAGE_QUESTION_RE =
  /what('?s| is) happening (here|on this page)|what am i (looking|seeing)|what does this (page|screen) show|explain this (page|screen)/i

// Phrases that ask about the PREVIOUS answer's reasoning — answered from
// that message's own transparency data (data_used/tools_called/intent),
// which the app already collected when it gave that answer.
const WHY_QUESTION_RE =
  /^why( is)? this( answer)?\??$|^why\??$|how did (you|the ai|it) (get|give|come up with|generate)|how (was|is) this (answer|calculated|worked out)/i

// Only the three fully-translated languages are offered here. This list is
// derived from SPEECH_LANGS (not hardcoded) so the picker can never drift
// out of sync with what voice input/output and the UI actually support.
const LANGS = Object.entries(SPEECH_LANGS).map(([code, info]) => [code, info.native])

const SUGGESTIONS: Record<string, string[]> = {
  en: ['Should I water my crop today?', 'Which government scheme can I apply for?',
       'My tomato leaves have brown spots with rings, what should I do?',
       'Open the market page'],
  ta: ['இன்று என் பயிருக்கு தண்ணீர் ஊற்ற வேண்டுமா?', 'எந்த அரசு திட்டத்திற்கு விண்ணப்பிக்கலாம்?',
       'சந்தை பக்கத்தைத் திற'],
  hi: ['क्या मुझे आज फसल को पानी देना चाहिए?', 'मैं किस सरकारी योजना के लिए आवेदन कर सकता हूँ?',
       'बाज़ार पेज खोलो'],
}

const ADMIN_SUGGESTIONS = [
  'Which states have the highest pest activity?',
  'Which districts have water stress?',
  'What are the top crops in Tamil Nadu?',
  'Which alerts should I prioritize?',
]
const QUICK_LINKS: { icon: string; navKey: string; route: string }[] = [
  { icon: '💧', navKey: 'nav.water', route: '/water' },
  { icon: '🌤️', navKey: 'nav.weather', route: '/weather' },
  { icon: '🍃', navKey: 'nav.plant', route: '/plant-health' },
  { icon: '🏛️', navKey: 'nav.schemes', route: '/schemes' },
  { icon: '💰', navKey: 'nav.market', route: '/market' },
  { icon: '🌾', navKey: 'nav.crop', route: '/crop-advisor' },
]

const PERMISSION_KEY = 'agri_assistant_permission'
const NAV_DELAY_MS = 2200
type Permission = 'granted' | 'denied' | null

type Msg = {
  role: 'user' | 'assistant'
  content: string
  meta?: any
  pageMatch?: PageMatch | null
  offerPermission?: boolean
  adminNavTo?: string | null
  adminEvidence?: string[]
}

/**
 * Unified advisor + agentic assistant.
 *
 * This used to be two separate surfaces — a plain Q&A chat bubble ("AI
 * Advisor") and a full-page voice-first navigator ("Voice Assistant") that
 * duplicated a lot of the same chat plumbing. They're merged here into one
 * panel that both answers questions AND can act on the farmer's behalf
 * (opening the right page), reached from a single floating icon.
 *
 * NAVIGATION AND PERMISSION
 * --------------------------
 * The assistant can open app pages for the farmer, but only automatically
 * once they've said yes (see the permission banner below). Until then, it
 * still tells them exactly where to go and gives a one-tap link — it never
 * jumps there on its own without consent. The choice is remembered in
 * localStorage and can be flipped anytime from the header toggle (full
 * variant) or stays as a link-only fallback in the compact widget.
 *
 * variant="full"   — used on the standalone /ai-advisor page: taller, shows
 *                     the "why this answer" detail panel and permission toggle.
 * variant="widget" — used inside the floating crop-icon bubble: compact,
 *                     denser spacing, identical capabilities.
 */
export function AdvisorChatPanel({
  variant = 'full',
}: {
  variant?: 'full' | 'widget'
}) {
  // Language lives in the shared app-wide context, not local state, so every
  // picker (sidebar, this panel) stays in sync and survives a refresh.
  const { language, setLanguage, t } = useLanguage()
  const nav = useNavigate()
  const { speak, stopSpeaking, speaking } = useSpeech(language)
  const isAdmin = getUser()?.role === 'admin'
  const { pageName, summary: pageSummary } = usePageContext()

  const [permission, setPermission] = useState<Permission>(() => {
    if (typeof window === 'undefined') return null
    const v = localStorage.getItem(PERMISSION_KEY)
    return v === 'granted' || v === 'denied' ? v : null
  })
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingNav, setPendingNav] = useState<PageMatch | null>(null)

  const endRef = useRef<HTMLDivElement>(null)
  const navTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy, pendingNav])
  useEffect(() => () => { if (navTimer.current) clearTimeout(navTimer.current) }, [])

  const setPermissionChoice = (choice: 'granted' | 'denied') => {
    setPermission(choice)
    localStorage.setItem(PERMISSION_KEY, choice)
  }

  // Tapping a link always navigates immediately — this is the farmer acting
  // directly, not the assistant acting "on its own", so it's never gated
  // behind the auto-open permission.
  const goNow = (route: string) => {
    if (navTimer.current) { clearTimeout(navTimer.current); navTimer.current = null }
    setPendingNav(null)
    stopSpeaking()
    nav(route)
  }

  const offerNavigation = (match: PageMatch) => {
    if (navTimer.current) { clearTimeout(navTimer.current); navTimer.current = null }
    if (permission === 'granted') {
      setPendingNav(match)
      navTimer.current = setTimeout(() => goNow(match.route), NAV_DELAY_MS)
    }
    // 'denied' or undecided: the page stays one tap away on the message
    // itself — nothing happens without the farmer's tap.
  }

  const send = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: trimmed }])

    // Admins get a different agent entirely: it answers from real backend
    // queries (pest activity, water stress, top crops, priority alerts —
    // never a guess) and, where a relevant dashboard view exists, offers a
    // direct link into it. No page-open permission dance here — this is the
    // admin's own dashboard, not "taking over the app" on a farmer's behalf.
    if (isAdmin) {
      setBusy(true)
      try {
        const res = await askAdmin(trimmed)
        setMessages((m) => [...m, {
          role: 'assistant', content: res.answer,
          adminNavTo: res.navigate_to || null, adminEvidence: res.evidence,
        }])
        speak(res.answer)
      } catch {
        const failMsg = 'Sorry, I could not process that. Please try again.'
        setMessages((m) => [...m, { role: 'assistant', content: failMsg }])
        speak(failMsg)
      } finally {
        setBusy(false)
      }
      return
    }

    // Live page awareness: "what is happening here?" is answered directly
    // from the SAME summary the current page just published — instant, and
    // provably grounded in what's actually on screen right now, not a
    // generic guess.
    if (PAGE_QUESTION_RE.test(trimmed)) {
      const reply = pageSummary
        ? `On the ${pageName} page right now: ${pageSummary}`
        : `I don't see any live data published from this page yet — try asking again in a moment, or ask me a specific question instead.`
      setMessages((m) => [...m, { role: 'assistant', content: reply }])
      speak(reply)
      return
    }

    // "Why this answer?" / "How did the AI give me this?" — explained from
    // the PREVIOUS assistant message's own transparency data, which is the
    // real intent/data/tools that produced it — never re-guessed.
    if (WHY_QUESTION_RE.test(trimmed)) {
      const prevAssistant = [...messages].reverse().find((m) => m.role === 'assistant' && m.meta)
      let reply: string
      if (prevAssistant?.meta) {
        const meta = prevAssistant.meta
        const parts = [`I answered based on intent "${meta.intent}"`]
        if (meta.data_used?.length) parts.push(`using this data: ${meta.data_used.join('; ')}`)
        if (meta.tools_called?.length) parts.push(`via these tools: ${meta.tools_called.join(', ')}`)
        reply = parts.join(' — ') + '.'
      } else if (pageSummary) {
        reply = `That answer isn't available to explain — but here's what's currently on the ${pageName} page, which may be what you're asking about: ${pageSummary}`
      } else {
        reply = "I don't have a previous answer to explain yet — ask me something first, then ask why."
      }
      setMessages((m) => [...m, { role: 'assistant', content: reply }])
      speak(reply)
      return
    }

    // 1. Offline "open <page>" commands resolve instantly, no backend needed.
    const direct = matchPageCommand(trimmed, language as Lang)
    if (direct) {
      const reply = `${t('assistant.opening')} ${t(direct.navKey)}…`
      const offerPermission = permission === null
      setMessages((m) => [...m, { role: 'assistant', content: reply, pageMatch: direct, offerPermission }])
      speak(reply)
      offerNavigation(direct)
      return
    }

    // 2. Otherwise ask the real chat agent, and offer whatever page its
    // detected intent maps to.
    setBusy(true)
    try {
      const res = await chat(trimmed, language, pageSummary)
      const match = routeForIntent(res.intent)
      const offerPermission = !!match && permission === null
      setMessages((m) => [...m, { role: 'assistant', content: res.answer, meta: res, pageMatch: match, offerPermission }])
      speak(res.answer)
      if (match) offerNavigation(match)
    } catch {
      const failMsg = 'Sorry, I could not process that. Please try again.'
      setMessages((m) => [...m, { role: 'assistant', content: failMsg }])
      speak(failMsg)
    } finally {
      setBusy(false)
    }
  }

  const suggestions = isAdmin ? ADMIN_SUGGESTIONS : (SUGGESTIONS[language] || SUGGESTIONS.en)
  const compact = variant === 'widget'

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header — full page only; the widget's own header (in FloatingAdvisor)
          covers title/subtitle, but the permission toggle still needs a home. */}
      {!compact && (
        <div className="flex items-center justify-between mb-3 shrink-0 gap-2">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-field-800">🌱 {t('nav.ai')}</h1>
            <p className="text-sm text-gray-500">{t('assistant.subtitle')}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {permission !== null && (
              <button
                onClick={() => setPermissionChoice(permission === 'granted' ? 'denied' : 'granted')}
                className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition
                  ${permission === 'granted'
                    ? 'bg-field-600 text-white border-field-600'
                    : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'}`}
              >
                {permission === 'granted' ? t('assistant.permission.on') : t('assistant.permission.off')}
              </button>
            )}
            <select value={language} onChange={(e) => setLanguage(e.target.value as typeof language)}
              className="border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600">
              {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>
      )}

      {/* Conversation */}
      <div className={`flex-1 min-h-0 overflow-y-auto space-y-3 ${compact ? 'px-3 py-3' : 'pb-3'}`}>
        {messages.length === 0 && (
          <div className={`bg-field-50/60 rounded-2xl ${compact ? 'p-3' : 'p-5 border border-gray-100 shadow-sm'}`}>
            <p className="text-sm text-gray-600 mb-2">👋 {t('assistant.welcome')}</p>
            <div className="flex flex-wrap gap-2">
              {suggestions.slice(0, compact ? 2 : 4).map((s) => (
                <button key={s} onClick={() => send(s)}
                  className="text-left text-xs sm:text-sm bg-white border border-field-200 rounded-xl px-2.5 py-1.5 hover:bg-field-100 transition">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`${compact ? 'max-w-[90%] rounded-xl px-3 py-2' : 'max-w-[85%] rounded-2xl px-4 py-3'} ${
              m.role === 'user' ? 'bg-field-600 text-white' : 'bg-white border border-gray-100 shadow-sm'}`}>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</p>

              {/* Listen option — every answer is spoken AND shown as text,
                  never text-only, so a semi-literate farmer can rely on
                  either. */}
              {m.role === 'assistant' && (
                <button
                  onClick={() => (speaking ? stopSpeaking() : speak(m.content))}
                  className="mt-2 text-xs text-field-700 hover:text-field-900 flex items-center gap-1"
                >
                  {speaking ? `⏹ ${t('voice.stop')}` : `🔊 ${t('voice.listen')}`}
                </button>
              )}

              {/* Admin agent: evidence + a direct link into the dashboard
                  view the answer came from — real backend data, not a guess. */}
              {m.adminEvidence && m.adminEvidence.length > 0 && (
                <ul className="mt-2 text-xs text-gray-500 list-disc pl-4 space-y-0.5">
                  {m.adminEvidence.map((e, j) => <li key={j}>{e}</li>)}
                </ul>
              )}
              {m.adminNavTo && (
                <div className="mt-2 pt-2 border-t border-gray-100">
                  <button
                    onClick={() => nav(m.adminNavTo!)}
                    className="text-sm font-semibold text-field-700 hover:text-field-900 underline underline-offset-2"
                  >
                    Open in dashboard →
                  </button>
                </div>
              )}

              {/* Full app control: a one-tap link to the page the assistant
                  thinks the farmer needs. */}
              {m.pageMatch && (
                <div className="mt-2 pt-2 border-t border-gray-100">
                  <button
                    onClick={() => goNow(m.pageMatch!.route)}
                    className="text-sm font-semibold text-field-700 hover:text-field-900 underline underline-offset-2"
                  >
                    {t('assistant.openpage')} {t(m.pageMatch.navKey)} →
                  </button>
                </div>
              )}

              {m.offerPermission && m.pageMatch && (
                <div className="mt-3 bg-field-50/70 rounded-xl p-3">
                  <p className="text-xs font-semibold text-field-800 mb-1">{t('assistant.permission.title')}</p>
                  <p className="text-xs text-gray-600 mb-2">{t('assistant.permission.desc')}</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPermissionChoice('granted')}
                      className="text-xs font-semibold bg-field-600 text-white px-3 py-1.5 rounded-lg hover:bg-field-700"
                    >
                      {t('assistant.permission.allow')}
                    </button>
                    <button
                      onClick={() => setPermissionChoice('denied')}
                      className="text-xs font-semibold bg-white border border-gray-200 px-3 py-1.5 rounded-lg hover:bg-gray-50"
                    >
                      {t('assistant.permission.deny')}
                    </button>
                  </div>
                </div>
              )}

              {/* "Why this answer" detail — full page only, keeps the
                  compact widget uncluttered. */}
              {m.meta && !compact && (
                <details className="mt-2 text-[11px] opacity-70">
                  <summary className="cursor-pointer">{t('ai.why')}</summary>
                  <div className="mt-1 space-y-1">
                    <p><b>{t('ai.intent')}</b> {m.meta.intent} · <b>Language:</b> {m.meta.language_name}</p>
                    {m.meta.data_used?.length > 0 && (
                      <p><b>Data used:</b> {m.meta.data_used.join('; ')}</p>)}
                    {m.meta.tools_called?.length > 0 && (
                      <p><b>{t('ai.tools')}</b> {m.meta.tools_called.join(', ')}</p>)}
                  </div>
                </details>
              )}
            </div>
          </div>
        ))}

        {pendingNav && (
          <div className="flex justify-start">
            <div className="bg-field-50 border border-field-200 rounded-2xl px-4 py-3 flex items-center gap-3">
              <span className="text-sm text-field-800">
                {t('assistant.opening')} {t(pendingNav.navKey)}…
              </span>
              <button
                onClick={() => { if (navTimer.current) clearTimeout(navTimer.current); setPendingNav(null) }}
                className="text-xs font-semibold text-red-600 hover:text-red-700"
              >
                {t('assistant.cancel')}
              </button>
            </div>
          </div>
        )}

        {busy && (
          <div className="flex justify-start">
            <div className="bg-white border rounded-2xl px-4 py-3 shadow-sm">
              <span className="inline-flex gap-1">
                <span className="w-2 h-2 bg-field-400 rounded-full animate-bounce" />
                <span className="w-2 h-2 bg-field-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                <span className="w-2 h-2 bg-field-400 rounded-full animate-bounce [animation-delay:0.2s]" />
              </span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Quick links — tapping works identically to saying "open water". */}
      <div className={`shrink-0 border-t ${compact ? 'px-2 pt-2' : 'pt-2'}`}>
        <div className={`flex flex-wrap gap-1.5 ${compact ? 'mb-2' : 'mb-2.5'}`}>
          {(compact ? QUICK_LINKS.slice(0, 4) : QUICK_LINKS).map((q) => (
            <button
              key={q.route}
              onClick={() => goNow(q.route)}
              className="text-xs bg-white border border-field-200 rounded-xl px-2 py-1 hover:bg-field-100 transition flex items-center gap-1"
            >
              <span>{q.icon}</span> {t(q.navKey)}
            </button>
          ))}
        </div>

        {/* Input row with voice */}
        <div className={`flex items-end gap-2 ${compact ? 'pb-2' : ''}`}>
          <VoiceMic
            language={language}
            size={compact ? 'md' : 'lg'}
            onInterim={(txt) => setInput(txt)}
            onResult={(txt) => send(txt)}
          />
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
            placeholder={t('assistant.placeholder')}
            rows={1}
            className={`flex-1 border rounded-2xl outline-none focus:ring-2 focus:ring-field-600 resize-none ${
              compact ? 'px-3 py-2 text-sm' : 'px-4 py-3 text-sm'}`}
          />
          <button onClick={() => send(input)} disabled={busy || !input.trim()}
            className="px-4 py-2 rounded-xl font-semibold text-sm transition disabled:opacity-50 bg-field-600 text-white hover:bg-field-700">
            {t('common.send')}
          </button>
        </div>
      </div>
    </div>
  )
}
