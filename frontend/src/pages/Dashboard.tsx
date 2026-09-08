import { useEffect, useState } from 'react'
import { getLatestSensor, getIrrigation, getSoil, getWeather,
         simulateSensor, setScenario, getUser } from '../services/api'
import { StatCard, Card, Spinner, Button, StatusPill } from '../components/UI'
import { CurrentCropPanel } from '../components/CurrentCropPanel'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

const SCENARIOS = [
  ['normal', 'Normal'], ['dry_soil', 'Dry soil'], ['heavy_rain', 'Heavy rain'],
  ['low_water', 'Low water'], ['high_temp', 'High temp'],
]

function soilSummaryLine(so: any): string {
  if (!so?.has_data) return 'No soil test recorded yet'
  return `Soil health overall: ${so.overall} (N ${so.nitrogen.status}, `
    + `P ${so.phosphorus.status}, K ${so.potassium.status}, pH ${so.ph.value} ${so.ph.status})`
}

export default function Dashboard() {
  const { t, tv } = useLanguage()
  const user = getUser()
  const { publish } = usePageContext()
  const [sensor, setSensor] = useState<any>(null)
  const [irr, setIrr] = useState<any>(null)
  const [soil, setSoil] = useState<any>(null)
  const [weather, setWeather] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [scenario, setScen] = useState('normal')

  const load = async () => {
    setLoading(true)
    try {
      const [s, i, so, w] = await Promise.all([
        getLatestSensor().catch(() => null),
        getIrrigation().catch(() => null),
        getSoil().catch(() => null),
        getWeather().catch(() => null),
      ])
      setSensor(s); setIrr(i); setSoil(so); setWeather(w)

      // Tell the floating AI advisor exactly what's on screen, so "what is
      // happening here?" answers from the SAME numbers the farmer sees.
      const bits = [
        s ? `Soil moisture ${s.soil_moisture}%, temperature ${s.temperature}°C, `
            + `humidity ${s.humidity}%, water tank ${s.water_level}%` : 'No sensor reading yet',
        i?.irrigate !== undefined
          ? `Irrigation recommendation: ${i.irrigate ? `irrigate ~${i.duration_min} min` : 'no irrigation needed'} `
            + `(priority ${i.priority}) — reason: ${i.reason}`
          : 'No irrigation recommendation yet',
        w ? `Weather: ${w.condition}, ${w.temperature}°C, rain probability ${w.rain_probability}% — ${w.interpretation}`
          : 'No weather data yet',
        soilSummaryLine(so),
      ]
      publish('Dashboard', bits.join('. '))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const runScenario = async (name: string) => {
    setScen(name)
    await setScenario(name)
    // generate a few readings so trends & recommendation update
    await simulateSensor(); await simulateSensor(); await simulateSensor()
    await load()
  }

  if (loading) return <Spinner />

  const moisture = sensor?.soil_moisture
  const isBalcony = user?.mode === 'balcony'

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-bold text-field-800">
          Namaste, {user?.name?.split(' ')[0]} 🌱
        </h1>
        
      <CurrentCropPanel />
<Button variant="ghost" onClick={load}>↻ Refresh</Button>
      </div>
      <p className="text-sm text-gray-500 mb-5">
        Here's the current status of your {isBalcony ? 'garden' : 'farm'}.
      </p>

      {/* Demo scenario controls */}
      <Card className="mb-5 bg-field-50/50">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-field-700 mr-1">🎬 Demo scenario:</span>
          {SCENARIOS.map(([v, l]) => (
            <button key={v} onClick={() => runScenario(v)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition
                ${scenario === v ? 'bg-field-600 text-white border-field-600'
                                  : 'bg-white text-field-700 border-field-200 hover:bg-field-100'}`}>
              {l}
            </button>
          ))}
          <span className="text-xs text-gray-400 ml-1">
            {t('admin.simulator')}
          </span>
        </div>
      </Card>

      {/* Environment cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label={t('dash.soilmoisture')} icon="💧" value={moisture ?? '—'} unit="%"
          status={irr?.status}
          recommendation={irr?.reason?.slice(0, 90)} />
        <StatCard label={t('dash.temperature')} icon="🌡️" value={sensor?.temperature ?? '—'} unit="°C" />
        <StatCard label={t('dash.humidity')} icon="💨" value={sensor?.humidity ?? '—'} unit="%" />
        <StatCard label={t('dash.watertank')} icon="🪣" value={sensor?.water_level ?? '—'} unit="%"
          status={sensor?.water_level < 20 ? 'CRITICAL' : undefined} />
      </div>

      {/* Irrigation + Weather + Soil summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-field-800">💧 Irrigation</h3>
            {irr?.priority && <StatusPill status={irr.priority} />}
          </div>
          {irr?.irrigate !== undefined ? (
            <>
              <p className="text-lg font-bold mb-1" style={{ color: irr.irrigate ? '#b45309' : '#256232' }}>
                {irr.irrigate ? `Irrigate ~${irr.duration_min} min` : 'No irrigation needed'}
              </p>
              <p className="text-sm text-gray-600">{irr.reason}</p>
            </>
          ) : <p className="text-sm text-gray-400">{t('dash.norec')}</p>}
        </Card>

        <Card>
          <h3 className="font-semibold text-field-800 mb-2">🌤️ Weather</h3>
          {weather ? (
            <>
              <p className="text-lg font-bold text-field-800">{weather.condition}</p>
              <p className="text-sm text-gray-600">
                {weather.temperature}°C · Rain {weather.rain_probability}%
              </p>
              <p className="text-sm text-gray-500 mt-1">{weather.interpretation}</p>
              <p className="text-[11px] text-gray-400 mt-2">Source: {weather.source}</p>
            </>
          ) : <p className="text-sm text-gray-400">{t('dash.noweather')}</p>}
        </Card>

        <Card>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-field-800">🧪 Soil Health</h3>
            {soil?.overall && <StatusPill status={soil.overall} />}
          </div>
          {soil?.has_data ? (
            <div className="space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">{t('soil.nitrogen')}</span>
                <StatusPill status={soil.nitrogen.status} /></div>
              <div className="flex justify-between"><span className="text-gray-500">{t('soil.phosphorus')}</span>
                <StatusPill status={soil.phosphorus.status} /></div>
              <div className="flex justify-between"><span className="text-gray-500">{t('soil.potassium')}</span>
                <StatusPill status={soil.potassium.status} /></div>
              <div className="flex justify-between"><span className="text-gray-500">pH</span>
                <span className="font-semibold">{soil.ph.value} ({soil.ph.status})</span></div>
            </div>
          ) : <p className="text-sm text-gray-400">{t('dash.nosoil')}</p>}
        </Card>
      </div>
    </div>
  )
}
