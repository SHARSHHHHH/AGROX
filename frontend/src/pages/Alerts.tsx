import { useEffect, useState } from 'react'
import {
  getAlertsFiltered, getAlertSummary, dismissAlert, markAlertRead,
  markAllAlertsRead,
} from '../services/api'
import { Card, Spinner, Empty, Button } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'
import { usePushNotifications } from '../hooks/usePushNotifications'
import { useNavigate } from 'react-router-dom'

/**
 * Where each alert category sends the farmer when tapped.
 *
 * An alert that says "your field needs water" and then does nothing when
 * tapped is a dead end — the farmer has to find the irrigation page
 * themselves. Tapping should land them where they can act on it.
 */
const CATEGORY_ROUTE: Record<string, string> = {
  irrigation: '/water',
  water_tank: '/water',
  weather: '/weather',
  pest_nearby: '/plant-health',
  scheme: '/schemes',
  disaster: '/schemes',
  compensation: '/schemes',
  supplies: '/circular',
  machinery: '/machinery',
  lifecycle: '/crop-advisor?tab=lifecycle',
  satellite: '/satellite',
  soil: '/soil',
}

/**
 * Alerts.
 *
 * Ordering is by PRIORITY first, recency second. A critical tank alert from
 * this morning must sit above an informational one from a minute ago —
 * strict reverse-chronological buries exactly the alerts that matter.
 *
 * Read and dismissed are deliberately different actions. Read means "I saw
 * it" and dims the card. Dismissed means "stop showing me this" and removes
 * it, and the backend's dedup respects that so it does not come straight back.
 */

const PRIORITY_STYLE: Record<string, string> = {
  CRITICAL: 'border-red-400 bg-red-50',
  HIGH: 'border-amber-400 bg-amber-50',
  MEDIUM: 'border-blue-300 bg-blue-50',
  LOW: 'border-gray-200 bg-white',
}

const PRIORITY_DOT: Record<string, string> = {
  CRITICAL: 'bg-red-600', HIGH: 'bg-amber-500',
  MEDIUM: 'bg-blue-500', LOW: 'bg-gray-400',
}

const CATEGORY_ICON: Record<string, string> = {
  irrigation: '💧', water_tank: '🪣', weather: '🌦️', pest_nearby: '🐛',
  scheme: '🏛️', disaster: '🚨', compensation: '💰', supplies: '🧪',
  machinery: '🚜', lifecycle: '🌱', satellite: '🛰️', soil: '🧱',
  general: '🔔',
}

export default function Alerts() {
  const { t } = useLanguage()
  const { publish } = usePageContext()
  const push = usePushNotifications()
  const navigate = useNavigate()

  const [alerts, setAlerts] = useState<any[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState('')
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [open, setOpen] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    // Independent: a failed summary must not blank the alert list.
    const [rows, sum] = await Promise.allSettled([
      getAlertsFiltered({ category, unread_only: unreadOnly }),
      getAlertSummary(),
    ])
    if (rows.status === 'fulfilled') {
      setAlerts(rows.value)
      publish('Alerts', rows.value.length
        ? `${rows.value.length} active alert(s): ` + rows.value
            .map((a: any) => `[${a.priority}/${a.category}] ${a.title} — ${a.message}`
                             + (a.action ? ` Action: ${a.action}` : ''))
            .join(' | ')
        : 'No active alerts right now.')
    }
    if (sum.status === 'fulfilled') setSummary(sum.value)
    setLoading(false)
  }

  useEffect(() => { load() }, [category, unreadOnly])

  const onRead = async (id: number) => {
    await markAlertRead(id)
    setAlerts((a) => a.map((x) => (x.id === id ? { ...x, read: true } : x)))
    getAlertSummary().then(setSummary).catch(() => {})
  }

  const onDismiss = async (id: number) => {
    await dismissAlert(id)
    setAlerts((a) => a.filter((x) => x.id !== id))
    getAlertSummary().then(setSummary).catch(() => {})
  }

  const onReadAll = async () => {
    await markAllAlertsRead()
    setAlerts((a) => a.map((x) => ({ ...x, read: true })))
    getAlertSummary().then(setSummary).catch(() => {})
  }

  const categories = Object.keys(summary?.by_category || {})

  return (
    <div className="max-w-3xl">
      <div className="flex items-start justify-between gap-3 mb-1">
        <h1 className="text-2xl font-bold text-field-800">
          🔔 {t('alerts.title')}
          {summary?.unread > 0 && (
            <span className="ml-2 text-xs align-middle px-2 py-0.5 rounded-full
                             bg-red-600 text-white font-bold">
              {summary.unread}
            </span>
          )}
        </h1>
        {summary?.unread > 0 && (
          <Button variant="ghost" onClick={onReadAll}>
            {t('alerts.readAll')}
          </Button>
        )}
      </div>
      <p className="text-sm text-gray-500 mb-4">{t('alerts.subtitle')}</p>

      {/* Urgent count first — the number that should change behaviour. */}
      {summary?.needs_attention > 0 && (
        <div className="rounded-xl border-2 border-red-300 bg-red-50 p-3 mb-4">
          <p className="font-bold text-red-800">
            {summary.needs_attention} {t('alerts.needAttention')}
          </p>
        </div>
      )}

      {/* Push opt-in. Never blocks anything — alerts show here regardless. */}
      {push.supported && push.serverReady && !push.subscribed && (
        <Card>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold text-field-800">
                {t('alerts.pushTitle')}
              </h3>
              <p className="text-sm text-gray-600 mt-1">{t('alerts.pushBody')}</p>
            </div>
            <Button onClick={push.enable} disabled={push.busy}>
              {push.busy ? t('alerts.pushBusy') : t('alerts.pushEnable')}
            </Button>
          </div>
          {push.reason && (
            <p className="text-[11px] text-gray-500 mt-2">{push.reason}</p>
          )}
        </Card>
      )}
      {push.subscribed && (
        <p className="text-[11px] text-gray-500 mb-3">
          ✅ {t('alerts.pushOn')}{' '}
          <button onClick={push.disable} className="underline">
            {t('alerts.pushOff')}
          </button>
        </p>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <FilterChip active={!category} onClick={() => setCategory('')}
                    label={t('alerts.all')}
                    count={summary?.unread} />
        {categories.map((c) => (
          <FilterChip key={c} active={category === c}
                      onClick={() => setCategory(c)}
                      label={`${CATEGORY_ICON[c] || '🔔'} ${t(`alerts.cat.${c}`)}`}
                      count={summary?.by_category?.[c]} />
        ))}
        <FilterChip active={unreadOnly} onClick={() => setUnreadOnly(!unreadOnly)}
                    label={t('alerts.unreadOnly')} />
      </div>

      {loading ? <Spinner /> : alerts.length === 0 ? (
        <Empty msg={t('alerts.none')} />
      ) : (
        <div className="space-y-3">
          {alerts.map((a) => (
            <div key={a.id}
                 className={`rounded-2xl border-2 p-3 transition
                   ${PRIORITY_STYLE[a.priority] || PRIORITY_STYLE.LOW}
                   ${a.read ? 'opacity-60' : ''}`}>

              {/* ONE LINE by default: icon, title, priority. The message and
                  action only appear when the farmer opens it, so a screen of
                  alerts can be scanned rather than read. */}
              <button onClick={() => { setOpen(open === a.id ? null : a.id)
                                       if (!a.read) onRead(a.id) }}
                      className="w-full text-left flex items-center gap-2 min-w-0">
                <span className={`w-2 h-2 rounded-full flex-shrink-0
                                  ${PRIORITY_DOT[a.priority] || ''}`} />
                <span className="text-base flex-shrink-0">
                  {CATEGORY_ICON[a.category] || '🔔'}
                </span>
                <span className="font-semibold text-field-800 truncate flex-1">
                  {a.title}
                </span>
                {!a.read && (
                  <span className="w-1.5 h-1.5 rounded-full bg-red-600 flex-shrink-0" />
                )}
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full
                                 bg-white/70 border flex-shrink-0">
                  {t(`alerts.p.${a.priority}`)}
                </span>
                <span className="text-gray-400 text-xs flex-shrink-0">
                  {open === a.id ? '▲' : '▼'}
                </span>
              </button>

              {open === a.id && (
                <div className="mt-2">
                  <p className="text-sm text-gray-700 whitespace-pre-line">
                    {a.message}
                  </p>

                  {a.action && (
                    <div className="mt-2 rounded-xl bg-white/70 border p-2">
                      <p className="text-[10px] font-bold text-gray-500 uppercase">
                        {t('alerts.whatToDo')}
                      </p>
                      <p className="text-sm text-gray-800">{a.action}</p>
                    </div>
                  )}

                  {a.payload?.amount != null && (
                    <p className="text-sm font-bold text-field-800 mt-2">
                      ₹{Number(a.payload.amount).toLocaleString()}{' '}
                      {a.payload.amount_unit || ''}
                    </p>
                  )}
                  {a.payload?.is_your_field === false && (
                    <p className="text-[11px] text-amber-800 font-semibold mt-1">
                      {t('alerts.nearbyOnly')}
                    </p>
                  )}
                  {a.payload?.estimated && (
                    <p className="text-[11px] text-gray-500 mt-1">
                      {t('alerts.estimated')}
                    </p>
                  )}

                  {CATEGORY_ROUTE[a.category] && (
                    <button
                      onClick={() => navigate(CATEGORY_ROUTE[a.category])}
                      className="mt-2 text-sm font-semibold text-field-700 underline">
                      {t('alerts.openPage')} →
                    </button>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between gap-2 mt-2">
                <p className="text-[11px] text-gray-400">
                  {new Date(a.date).toLocaleString()}
                </p>
                <div className="flex items-center gap-3">
                  {a.source?.url && (
                    <a href={a.source.url} target="_blank" rel="noreferrer"
                       className="text-xs text-field-700 font-semibold underline">
                      {t('alerts.viewSource')}
                      {a.source.name ? ` (${a.source.name})` : ''}
                    </a>
                  )}
                  <button onClick={() => onDismiss(a.id)}
                          className="text-xs text-gray-500 hover:underline">
                    {t('alerts.dismiss')}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function FilterChip({ active, onClick, label, count }:
                    { active: boolean; onClick: () => void
                      label: string; count?: number }) {
  return (
    <button onClick={onClick}
            className={`text-xs px-3 py-1.5 rounded-full border font-semibold
              ${active ? 'bg-field-700 text-white border-field-700'
                       : 'bg-white text-gray-700 border-gray-300'}`}>
      {label}
      {count ? ` (${count})` : ''}
    </button>
  )
}
