import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { getFarmSetupStatus } from '../services/api'
import { useLanguage } from '../contexts/LanguageContext'
import { Card, Button, Spinner } from './UI'

/**
 * Farm setup gating.
 *
 * WHY A CONTEXT AND NOT A CHECK PER PAGE
 * --------------------------------------
 * Twelve pages need this rule. Copying the check into each one guarantees they
 * drift: someone adds a thirteenth page and forgets, or fixes a bug in one
 * copy and not the other eleven. Worse, twelve pages each firing their own
 * /setup/status request on every navigation is twelve round trips for one
 * boolean.
 *
 * So the status is fetched ONCE into a context and every guarded route reads
 * it from there.
 *
 * WHAT IS DELIBERATELY NOT GUARDED
 * --------------------------------
 * Only modules that need personal farm data are gated. Weather, the machinery
 * catalogue, market prices and government scheme listings are useful to a
 * farmer who has not set anything up yet, and blocking them would be hostile
 * for no benefit.
 */

type SetupStatus = {
  completed: boolean
  has_farm: boolean
  completeness: number
  missing_required: string[]
  missing_recommended: string[]
  message: string
  next_step: string | null
}

type Ctx = {
  status: SetupStatus | null
  loading: boolean
  refresh: () => Promise<void>
}

const FarmSetupContext = createContext<Ctx>({
  status: null, loading: true, refresh: async () => {},
})

export const useFarmSetup = () => useContext(FarmSetupContext)

export function FarmSetupProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    setLoading(true)
    try {
      setStatus(await getFarmSetupStatus())
    } catch {
      // A failed status check must not lock the farmer out of their own app.
      // Failing OPEN is the right call here: the backend re-checks anything
      // that actually depends on farm data, so the worst case is an empty
      // dashboard rather than an unreachable one.
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [])

  return (
    <FarmSetupContext.Provider value={{ status, loading, refresh }}>
      {children}
    </FarmSetupContext.Provider>
  )
}

/** Wrap any route that needs a completed farm profile. */
export function RequireFarmSetup({ children }: { children: ReactNode }) {
  const { status, loading } = useFarmSetup()
  const { t } = useLanguage()
  const location = useLocation()

  if (loading) return <Spinner />

  // Status unavailable -> let them through (see refresh() above).
  if (status === null) return <>{children}</>

  if (status.completed) return <>{children}</>

  // Already on the setup page: never redirect to where we already are.
  if (location.pathname === '/farm-setup') return <>{children}</>

  return <FarmSetupRequired status={status} />
}

/** Explains exactly what is missing rather than bouncing the farmer silently. */
function FarmSetupRequired({ status }: { status: SetupStatus }) {
  const { t } = useLanguage()
  const [go, setGo] = useState(false)

  if (go) return <Navigate to="/farm-setup" replace />

  return (
    <Card>
      <h2 className="font-bold text-field-800 text-lg">
        {t('setup.requiredTitle')}
      </h2>
      <p className="text-sm text-gray-700 mt-2">{t('setup.requiredBody')}</p>

      {status.missing_required.length > 0 && (
        <div className="mt-3">
          <p className="text-sm font-semibold">{t('setup.stillNeeded')}</p>
          <ul className="text-sm text-gray-700 list-disc ml-5 mt-1">
            {status.missing_required.map((f) => (
              <li key={f}>{t(`setup.field.${f}`)}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3">
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div className="h-full bg-field-600"
               style={{ width: `${status.completeness}%` }} />
        </div>
        <p className="text-xs text-gray-500 mt-1">
          {status.completeness}% {t('setup.complete')}
        </p>
      </div>

      <div className="mt-4">
        <Button onClick={() => setGo(true)}>{t('setup.completeButton')}</Button>
      </div>
    </Card>
  )
}
