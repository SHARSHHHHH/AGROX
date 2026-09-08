import { useEffect, useState } from 'react'
import { getLatestSensor, getIrrigation, controlPump, logIrrigation,
         getSensorHistory } from '../services/api'
import { Card, Button, Spinner, StatusPill, StatCard } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

export default function Water() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const [sensor, setSensor] = useState<any>(null)
  const [irr, setIrr] = useState<any>(null)
  const [history, setHistory] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [pumpState, setPumpState] = useState('OFF')
  const [msg, setMsg] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [s, i, h] = await Promise.all([
        getLatestSensor().catch(() => null),
        getIrrigation().catch(() => null),
        getSensorHistory().catch(() => []),
      ])
      setSensor(s); setIrr(i); setHistory(h)
      publish('Water & Irrigation', [
        s ? `Soil moisture ${s.soil_moisture}%, water tank ${s.water_level}%, flow ${s.water_flow} L/min` : 'No sensor reading yet',
        i?.irrigate !== undefined
          ? `Recommendation: ${i.irrigate ? `irrigate ~${i.duration_min} min (priority ${i.priority})` : 'no irrigation needed'} — ${i.reason}`
          : 'No irrigation recommendation yet',
        `${h.length} recent moisture reading(s) in history`,
      ].join('. '))
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const togglePump = async (state: string) => {
    const res = await controlPump(state)
    setPumpState(state)
    setMsg(res.note || `Pump ${state}`)
  }

  const logRun = async () => {
    if (!irr?.duration_min) return
    await logIrrigation(irr.duration_min)
    setMsg(`Logged irrigation of ${irr.duration_min} min.`)
  }

  if (loading) return <Spinner />

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">💧 Water & Irrigation</h1>
      <p className="text-sm text-gray-500 mb-5">{t('water.subtitle')}</p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
        <StatCard label={t('dash.soilmoisture')} icon="💧" value={sensor?.soil_moisture ?? '—'} unit="%"
          status={irr?.status} />
        <StatCard label={t('dash.watertank')} icon="🪣" value={sensor?.water_level ?? '—'} unit="%"
          status={sensor?.water_level < 20 ? 'CRITICAL' : undefined} />
        <StatCard label={t('dash.waterflow')} icon="🚿" value={sensor?.water_flow ?? '—'} unit="L/min" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-field-800">{t('common.recommendation')}</h3>
            {irr?.priority && <StatusPill status={irr.priority} />}
          </div>
          {irr?.irrigate !== undefined ? (
            <>
              <p className="text-lg font-bold mb-1"
                 style={{ color: irr.irrigate ? '#b45309' : '#256232' }}>
                {irr.irrigate ? `Irrigate ~${irr.duration_min} minutes` : 'No irrigation needed'}
              </p>
              <p className="text-sm text-gray-600 mb-3">{irr.reason}</p>
              {irr.irrigate && <Button onClick={logRun}>{t('water.log')}</Button>}
            </>
          ) : <p className="text-sm text-gray-400">{t('water.norec')}</p>}
        </Card>

        <Card>
          <h3 className="font-semibold text-field-800 mb-2">{t('water.pump')}</h3>
          <p className="text-xs text-gray-500 mb-3">
            Manual control only. Automated pump control is intentionally gated behind
            a safety layer (never triggered by the AI directly).
          </p>
          <div className="flex gap-2">
            <Button variant={pumpState === 'ON' ? 'primary' : 'ghost'} onClick={() => togglePump('ON')}>
              {t('water.turnon')}
            </Button>
            <Button variant={pumpState === 'OFF' ? 'danger' : 'ghost'} onClick={() => togglePump('OFF')}>
              {t('water.turnoff')}
            </Button>
          </div>
          {msg && <p className="text-xs text-gray-500 mt-3">{msg}</p>}
        </Card>
      </div>

      {history.length > 0 && (
        <Card className="mt-5">
          <h3 className="font-semibold text-field-800 mb-2">{t('water.recent')}</h3>
          <div className="flex items-end gap-1 h-24">
            {history.slice(-24).map((h, i) => (
              <div key={i} className="flex-1 bg-field-500 rounded-t"
                   style={{ height: `${Math.min(100, h.soil_moisture)}%` }}
                   title={`${h.soil_moisture}% @ ${h.timestamp?.slice(11,16)}`} />
            ))}
          </div>
          <p className="text-[11px] text-gray-400 mt-2">
            Last {Math.min(24, history.length)} readings. Source: {history[history.length-1]?.source}.
          </p>
        </Card>
      )}
    </div>
  )
}
