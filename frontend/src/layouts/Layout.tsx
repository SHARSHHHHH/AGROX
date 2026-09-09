import { ReactNode, useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { getHarvestMessageNotifications, getUser, logout } from '../services/api'
import { LanguagePicker } from '../components/VoiceInput'
import { FloatingAdvisor } from '../components/FloatingAdvisor'
import { WeatherWidget } from '../components/WeatherWidget'
import { useLanguage } from '../contexts/LanguageContext'

const FARMER_NAV = [
  { to: '/dashboard', key: 'nav.dashboard', icon: '🏠' },
  // "My Farm" and "Farm Setup" are merged into one wizard (see
  // Onboarding.tsx) that both a first-time and a returning farmer use,
  // so there's a single /farm route now. /onboarding redirects here to
  // keep any old bookmark or link working.
  { to: '/farm', key: 'nav.farm', icon: '🌱' },
  { to: '/soil', key: 'nav.soil', icon: '🧪' },
  { to: '/water', key: 'nav.water', icon: '💧' },
  { to: '/plant-health', key: 'nav.plant', icon: '🍃' },
  { to: '/crop-advisor', key: 'nav.crop', icon: '🌾' },
  { to: '/satellite', key: 'nav.satellite', icon: '🛰️' },
  { to: '/circular', key: 'nav.circular', icon: '♻️' },
  { to: '/market', key: 'nav.market', icon: '💰' },
  { to: '/sell', key: 'nav.sell', icon: '🛒' },
  { to: '/harvest-calendar', key: 'nav.harvestCalendar', icon: '📅' },
  { to: '/notifications', key: 'nav.notifications', icon: '🔔' },
  { to: '/land-contractors', key: 'nav.landcontractors', icon: '🏡' },
  { to: '/machinery', key: 'nav.machinery', icon: '🚜' },
  { to: '/weather', key: 'nav.weather', icon: '🌤️' },
  // The AI Advisor and the old Voice Assistant page are merged into one
  // agentic panel (chat + full app navigation with permission), reached
  // from the single floating crop icon pinned bottom-right on every page
  // (see <FloatingAdvisor /> below) — that's the one entry point now,
  // rather than splitting it across two sidebar items. The full-page
  // version still exists at /ai-advisor for a larger view, linked from
  // inside the floating panel itself.
  { to: '/schemes', key: 'nav.schemes', icon: '🏛️' },
  { to: '/alerts', key: 'nav.alerts', icon: '🔔' },
  { to: '/analytics', key: 'nav.analytics', icon: '📈' },
]

// A buyer never grows anything — their sidebar is just the marketplace and
// their own order history, not the farmer's operational toolset.
const BUYER_NAV = [
  { to: '/marketplace', key: 'nav.marketplace', icon: '🛒' },
  { to: '/pre-booking', key: 'nav.prebooking', icon: '📅' },
  { to: '/notifications', key: 'nav.notifications', icon: '🔔' },
  { to: '/land-contractors', key: 'nav.landcontractors', icon: '🏡' },
]

// An admin is a state/central agriculture officer, not a farmer — Farm
// Setup, Soil, Water, Weather and the rest of the day-to-day farming tools
// have no place in their view. Their entire job is the analytics dashboard,
// which they reach through the amber "Govt Dashboard" link below.
const ADMIN_NAV: typeof FARMER_NAV = []

export function Layout({ children }: { children: ReactNode }) {
  const user = getUser()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const [unreadNotifications, setUnreadNotifications] = useState(0)
  const isAdmin = user?.role === 'admin'
  const isBuyer = user?.role === 'buyer'
  const { t } = useLanguage()
  const modeKey = user?.mode === 'balcony' ? 'common.mode.balcony' : 'common.mode.farm'
  const NAV = isAdmin ? ADMIN_NAV : isBuyer ? BUYER_NAV : FARMER_NAV

  useEffect(() => {
    if (isAdmin) return
    const loadUnreadNotifications = () => {
      getHarvestMessageNotifications()
        .then(items => setUnreadNotifications(items.filter((item: any) => !item.read).length))
        .catch(() => {})
    }
    loadUnreadNotifications()
    const timer = window.setInterval(loadUnreadNotifications, 10000)
    return () => window.clearInterval(timer)
  }, [isAdmin])

  return (
    <div className="min-h-screen flex bg-[#f6f8f6]">
      {/* Sidebar */}
      <aside
        className={`fixed lg:static z-30 h-full w-64 bg-field-800 text-white flex flex-col
          transition-transform ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
      >
        <div className="p-5 border-b border-field-700">
          <div className="font-display font-bold text-lg leading-tight">🌾 {t('app.name')}</div>
          <div className="text-xs text-field-100 mt-1">
            {isAdmin ? t('nav.admin') : isBuyer ? t('nav.marketplace') : t(modeKey)}
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto py-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm font-medium transition
                 ${isActive ? 'bg-field-700 border-l-4 border-white' : 'hover:bg-field-700/50 border-l-4 border-transparent'}`
              }
            >
              <span>{n.icon}</span>
              <span className="flex items-center gap-2">
                {t(n.key)}
                {n.to === '/notifications' && unreadNotifications > 0 && (
                  <span className="inline-flex min-w-5 h-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[11px] font-bold text-white">
                    {unreadNotifications > 9 ? '9+' : unreadNotifications}
                  </span>
                )}
              </span>
            </NavLink>
          ))}
          {isAdmin && (
            <NavLink
              to="/admin"
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm font-semibold transition
                 ${isActive ? 'bg-amber-600' : 'bg-amber-700/40 hover:bg-amber-700/60'}`
              }
            >
              <span>🏛️</span> {t('nav.admin')}
            </NavLink>
          )}
        </nav>
        <div className="p-4 border-t border-field-700">
          {/* Language selector lives in the shared Layout, so it is present on
              every authenticated page rather than only on Login. */}
          <div className="mb-3">
            <div className="text-[11px] uppercase tracking-wide text-field-100 mb-1">
              {t('common.language')}
            </div>
            <LanguagePicker compact />
          </div>
          <div className="text-sm font-medium">{user?.name}</div>
          <div className="text-xs text-field-100 mb-2">{user?.email}</div>
          <button onClick={logout} className="text-xs bg-field-700 hover:bg-field-600 px-3 py-1.5 rounded-lg w-full">
            {t('common.signout')}
          </button>
        </div>
      </aside>

      {open && <div className="fixed inset-0 bg-black/40 z-20 lg:hidden" onClick={() => setOpen(false)} />}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="lg:hidden flex items-center justify-between p-4 bg-white border-b">
          <button onClick={() => setOpen(true)} className="text-2xl">☰</button>
          <span className="font-display font-bold text-field-800">🌾 Agri Advisor</span>
          <span className="w-6" />
        </header>
        {/* Weather chip — top-right, farmer/balcony only. Replaces the old
            standalone Weather sidebar tab with a glanceable widget that is
            always visible instead of a whole page you have to navigate to. */}
        {!isAdmin && !isBuyer && (
          <div className="hidden sm:flex justify-end px-4 sm:px-6 pt-4">
            <WeatherWidget />
          </div>
        )}

        <main className="flex-1 p-4 sm:p-6 overflow-y-auto">{children}</main>
      </div>

      {/* The AI advisor answers farming questions and can open farming
          pages for farmers/balcony growers; admins get a different agent
          branch (real-data Q&A + dashboard navigation, see the admin
          branch in AdvisorChatPanel). Only buyers, who have no farming or
          admin context for it to act on, don't see it. */}
      {!isBuyer && <FloatingAdvisor />}
    </div>
  )
}

export function Settings() {
  const { t } = useLanguage()
  const { tv } = useLanguage()
  const user = getUser()
  const nav = useNavigate()
  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-bold text-field-800 mb-4">{t('nav.settings')}</h1>
      <div className="bg-white rounded-2xl border p-5 space-y-2 text-sm">
        <div><span className="text-gray-500">{t('register.name')}:</span> {user?.name}</div>
        <div><span className="text-gray-500">{t('login.email')}:</span> {user?.email}</div>
        <div><span className="text-gray-500">{t('schemes.category')}:</span> {tv(user?.role || '')}</div>
        <div><span className="text-gray-500">{t('register.choosemode')}:</span> {tv(user?.mode || '')}</div>
        <div><span className="text-gray-500">{t('common.language')}:</span> {user?.language}</div>
        <div><span className="text-gray-500">{t('common.state')}:</span> {user?.state}</div>
        <button onClick={logout} className="mt-3 bg-red-500 text-white px-4 py-2 rounded-xl text-sm">
          {t('common.signout')}
        </button>
      </div>
    </div>
  )
}
