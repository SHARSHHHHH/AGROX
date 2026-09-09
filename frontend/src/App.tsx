import { Routes, Route, Navigate } from 'react-router-dom'
import { getUser } from './services/api'
import { Layout, Settings } from './layouts/Layout'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Water from './pages/Water'
import PlantAndPestHealth from './pages/PlantAndPestHealth'
import CropAdvisor from './pages/CropAdvisor'
import Satellite from './pages/Satellite'
import CircularFarming from './pages/CircularFarming'
import Onboarding from './pages/Onboarding'
import Machinery from './pages/Machinery'
import { ConnectionBanner } from './components/ConnectionBanner'
import { FarmSetupProvider, RequireFarmSetup } from './components/FarmSetupGuard'
import Market from './pages/Market'
import Weather from './pages/Weather'
import AIAdvisor from './pages/AIAdvisor'
import Schemes from './pages/Schemes'
import Alerts from './pages/Alerts'
import Analytics from './pages/Analytics'
import Admin from './pages/Admin'
import Sell from './pages/Sell'
import Marketplace from './pages/Marketplace'
import LandContractors from './pages/LandContractors'
import FarmerLand from './pages/FarmerLand'
import HarvestCalendar from './pages/HarvestCalendar'
import PreBooking from './pages/PreBooking'
import Notifications from './pages/Notifications'
import GovernmentBrief from './pages/GovernmentBrief'
import PestOutbreakReport from './pages/PestOutbreakReport'

function Protected({ children }: { children: JSX.Element }) {
  return getUser() ? <Layout>{children}</Layout> : <Navigate to="/login" />
}

/**
 * Signed in AND farm setup completed.
 *
 * Used for every module whose output depends on the farmer's own land. A
 * dashboard with no farm behind it is a page of empty cards, and a crop
 * ranking with no soil or location is a list of generic crops — showing
 * either is worse than explaining what is missing.
 *
 * Deliberately NOT applied to Weather, Machinery, Market, Marketplace or
 * Settings: those are useful on day one, before any setup exists, and gating
 * them would be hostile for no benefit.
 */
function Personalized({ children }: { children: JSX.Element }) {
  return (
    <Protected>
      <RequireFarmSetup>{children}</RequireFarmSetup>
    </Protected>
  )
}

/** Where "/" and any unknown path should land, based on who is signed in. */
function landingFor(user: any) {
  if (!user) return '/login'
  if (user.role === 'admin') return '/admin'
  if (user.role === 'buyer') return '/marketplace'
  return '/dashboard'
}

export default function App() {
  const user = getUser()
  return (
    <>
      <ConnectionBanner />
      <FarmSetupProvider>
      <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/dashboard" element={<Personalized><Dashboard /></Personalized>} />
      {/* "My Farm" and "Farm Setup" are merged into one wizard (see
          Onboarding.tsx) that both a first-time and a returning farmer use,
          so there's a single /farm route now. /onboarding redirects here to
          keep any old bookmark or link working. */}
      <Route path="/farm" element={<Protected><Onboarding /></Protected>} />
      <Route path="/onboarding" element={<Navigate to="/farm" />} />
      <Route path="/farm-setup" element={<Navigate to="/farm" />} />
      <Route path="/water" element={<Personalized><Water /></Personalized>} />
      <Route path="/plant-health" element={<Personalized><PlantAndPestHealth /></Personalized>} />
      {/* Pest Management is now a tab inside PlantAndPestHealth; the old
          route is kept so existing links and bookmarks still work. */}
      <Route path="/pest-management" element={<Navigate to="/plant-health" replace />} />
      <Route path="/crop-advisor" element={<Personalized><CropAdvisor /></Personalized>} />
      <Route path="/satellite" element={<Personalized><Satellite /></Personalized>} />
      <Route path="/circular" element={<Personalized><CircularFarming /></Personalized>} />
      <Route path="/machinery" element={<Protected><Machinery /></Protected>} />
      <Route path="/market" element={<Protected><Market /></Protected>} />
      <Route path="/weather" element={<Protected><Weather /></Protected>} />
      <Route path="/ai-advisor" element={<Personalized><AIAdvisor /></Personalized>} />
      {/* AI Advisor and the old Voice Assistant page are merged into one
          agentic panel (see AdvisorChatPanel), reached from the floating
          icon on every page. This redirect keeps any old bookmark working. */}
      <Route path="/assistant" element={<Navigate to="/ai-advisor" />} />
      <Route path="/schemes" element={<Personalized><Schemes /></Personalized>} />
      <Route path="/alerts" element={<Personalized><Alerts /></Personalized>} />
      <Route path="/analytics" element={<Personalized><Analytics /></Personalized>} />
      <Route path="/farmer-land" element={<Protected><FarmerLand /></Protected>} />
      {/* Sell produce direct to buyers (farmer side) and the buyer-facing
          marketplace + their own order history — see the "buyer" role. */}
      <Route path="/sell" element={<Protected><Sell /></Protected>} />
      <Route path="/marketplace" element={<Protected><Marketplace /></Protected>} />
      <Route path="/harvest-calendar" element={<Protected><HarvestCalendar /></Protected>} />
      <Route path="/pre-booking" element={<Protected><PreBooking /></Protected>} />
      <Route path="/notifications" element={<Protected><Notifications /></Protected>} />
      <Route path="/land-contractors" element={<Protected><LandContractors /></Protected>} />
      <Route path="/settings" element={<Protected><Settings /></Protected>} />
      <Route path="/admin" element={<Protected><Admin /></Protected>} />
      <Route path="/admin/brief" element={<Protected><GovernmentBrief /></Protected>} />
      <Route path="/admin/pest-report" element={<Protected><PestOutbreakReport /></Protected>} />
      <Route path="/" element={<Navigate to={landingFor(user)} />} />
      <Route path="*" element={<Navigate to={landingFor(user)} />} />
      </Routes>
      </FarmSetupProvider>
    </>
  )
}
