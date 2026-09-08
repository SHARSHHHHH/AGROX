import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from 'recharts'
import {
  getAdminOverview, getAdminKPIs, getAdminStates, getAdminDistricts, getAdminStateDetail,
  getAdminPriorityAlerts, getAdminPredictive, runScenarioPestAdvisory, runScenarioIrrigation,
  proposeAdminAction, listAdminActions, decideAdminAction,
} from '../services/api'
import { Card, Spinner, StatCard, StatusPill, Empty, Button } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'

type Tab = 'overview' | 'state' | 'alerts' | 'actions'

const SEVERITY_ICON: Record<string, string> = { CRITICAL: '🔴', WARNING: '🟠', INFO: '🟡' }
const WATER_ICON: Record<string, string> = { normal: '🟢', watch: '🟡', stressed: '🟠', critical: '🔴', unknown: '⚪' }

const KPI_LABELS: [string, string, string][] = [
  ['total_farmers', '👥', 'Total farmers'],
  ['active_farms', '🌾', 'Active farms'],
  ['active_crop_listings', '🛒', 'Active crop listings'],
  ['buyers', '🧑‍💼', 'Buyers'],
  ['active_crop_types', '🌱', 'Active crop types'],
  ['pest_disease_reports', '🐛', 'Pest/disease reports'],
  ['active_alerts', '🔔', 'Active alerts'],
  ['iot_monitored_devices', '📡', 'IoT-monitored farms'],
  ['scheme_engagement', '🏛️', 'Scheme engagement'],
  ['machinery_listings', '🚜', 'Machinery demand'],
]

/**
 * Government / agriculture command center.
 *
 * Everything here is either an observed number (a real row count), a
 * derived analytic (computed from observed numbers, formula shown), or a
 * clearly-labelled scenario simulation — never an invented figure. Where
 * data doesn't exist yet, the page says so instead of guessing.
 */
export default function Admin() {
  const { tv } = useLanguage()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'overview'

  const [data, setData] = useState<any>(null)
  const [kpis, setKpis] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    getAdminOverview().then(setData)
      .catch(() => setErr('Admin access required. Sign in as admin@agri.gov.'))
      .finally(() => setLoading(false))
    getAdminKPIs().then(setKpis).catch(() => {})
  }, [])

  const setTab = (t: Tab) => setParams((p) => { p.set('tab', t); return p })

  if (loading) return <Spinner />
  if (err) return <Card><p className="text-sm text-red-600">{err}</p></Card>

  const problems = Object.entries(data.major_problems.alerts || {})
    .map(([name, value]) => ({ name: name.replace(/_/g, ' ').toLowerCase(), value }))
  const diseases = Object.entries(data.major_problems.diseases_detected || {})
    .map(([name, value]) => ({ name, value }))
  const COLORS = ['#2f7d40', '#d97706', '#dc2626', '#6366f1', '#0ea5e9']

  return (
    <div className="max-w-6xl">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-field-800">🏛️ Agriculture Command Center</h1>
        <p className="text-sm text-gray-500">
          Live platform intelligence for agriculture officers — observed data, derived
          analytics, and clearly-labelled scenarios only.
        </p>
      </div>

      <div className="flex gap-2 mb-6 flex-wrap">
        {([['overview', '📊 Overview'], ['state', '📍 State Intelligence'],
          ['alerts', '🚨 Priority Alerts'], ['actions', '✅ Actions']] as [Tab, string][]).map(([tb, label]) => (
          <button key={tb} onClick={() => setTab(tb)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition
              ${tab === tb ? 'bg-field-600 text-white' : 'bg-white border text-gray-600 hover:bg-gray-50'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Top-level KPIs — shown on every tab, this IS the command-center pulse */}
      {kpis && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
          {KPI_LABELS.map(([key, icon, label]) => (
            <div key={key} className="bg-white rounded-xl border border-gray-100 shadow-sm px-3 py-2.5">
              <div className="text-[11px] text-gray-500">{icon} {label}</div>
              <div className="text-xl font-bold text-field-800">{kpis[key] ?? 0}</div>
            </div>
          ))}
        </div>
      )}

      {tab === 'overview' && <OverviewTab data={data} problems={problems} diseases={diseases} COLORS={COLORS} tv={tv} goState={(s: string) => { setParams((p) => { p.set('tab', 'state'); p.set('state', s); return p }) }} />}
      {tab === 'state' && <StateTab tv={tv} params={params} setParams={setParams} />}
      {tab === 'alerts' && <AlertsTab tv={tv} goState={(s: string) => { setParams((p) => { p.set('tab', 'state'); p.set('state', s); return p }) }} />}
      {tab === 'actions' && <ActionsTab />}
    </div>
  )
}

// ---------------------------------------------------------------- Overview

function OverviewTab({ data, problems, diseases, COLORS, tv, goState }: any) {
  return (
    <>
      <Card className="mb-6 bg-amber-50 border-amber-100">
        <h3 className="font-semibold text-amber-800 mb-2">📋 Recommended actions</h3>
        <ul className="space-y-1.5 text-sm text-gray-700 list-disc pl-4">
          {data.recommendation_for_government.map((r: string, i: number) => <li key={i}>{r}</li>)}
        </ul>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
        <Card>
          <h3 className="font-semibold text-field-800 mb-3">Major problems (observed)</h3>
          {problems.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={problems} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis type="number" fontSize={11} allowDecimals={false} />
                <YAxis type="category" dataKey="name" fontSize={10} width={110} />
                <Tooltip />
                <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                  {problems.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <Empty msg="No alerts recorded yet." />}
        </Card>

        <Card>
          <h3 className="font-semibold text-field-800 mb-3">Diseases detected (observed)</h3>
          {diseases.length > 0 ? (
            <div className="space-y-2">
              {diseases.map((d: any, i: number) => (
                <div key={i} className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
                  <span className="text-sm font-medium">{d.name}</span>
                  <span className="text-sm font-bold text-field-700">{d.value} case(s)</span>
                </div>
              ))}
            </div>
          ) : <Empty msg="No diagnoses recorded yet." />}
        </Card>
      </div>

      <Card className="mb-6">
        <h3 className="font-semibold text-field-800 mb-3">Soil fertility by location (observed + derived)</h3>
        {data.soil_fertility_by_location.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="py-2">Location</th><th>Samples</th><th>Dominant</th><th>Breakdown</th>
                </tr>
              </thead>
              <tbody>
                {data.soil_fertility_by_location.map((f: any, i: number) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-2 font-medium">{f.location}</td>
                    <td>{f.samples}</td>
                    <td><StatusPill status={f.dominant_health} /></td>
                    <td className="text-xs text-gray-500">
                      {Object.entries(f.breakdown).map(([k, v]) => `${k}: ${v}`).join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty msg="No soil test data yet." />}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card>
          <h3 className="font-semibold text-field-800 mb-3">Scheme demand by farmer category</h3>
          <div className="space-y-2">
            {Object.entries(data.scheme_demand.by_farmer_category || {}).map(([k, v]: any) => (
              <div key={k} className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
                <span className="text-sm capitalize">{k}</span>
                <span className="text-sm font-bold text-field-700">{v}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <h3 className="font-semibold text-field-800 mb-3">Users by state</h3>
          <div className="space-y-2">
            {Object.entries(data.scheme_demand.by_state || {}).map(([k, v]: any) => (
              <button key={k} onClick={() => goState(k)}
                className="w-full flex items-center justify-between bg-gray-50 hover:bg-field-50 rounded-xl px-3 py-2 transition">
                <span className="text-sm">{k}</span>
                <span className="text-sm font-bold text-field-700">{v} →</span>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- State Intelligence

function StateTab({ tv, params, setParams }: any) {
  const selectedState = params.get('state') || ''
  const selectedDistrict = params.get('district') || ''

  const [states, setStates] = useState<any[]>([])
  const [statesLoading, setStatesLoading] = useState(true)
  const [districts, setDistricts] = useState<any[]>([])
  const [detail, setDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [predictive, setPredictive] = useState<any>(null)
  const [scenario, setScenario] = useState<any>(null)
  const [scenarioBusy, setScenarioBusy] = useState(false)

  useEffect(() => {
    getAdminStates().then(setStates).catch(() => {}).finally(() => setStatesLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedState) return
    setDetailLoading(true)
    setDetail(null); setPredictive(null); setScenario(null)
    getAdminDistricts(selectedState).then(setDistricts).catch(() => setDistricts([]))
    getAdminStateDetail(selectedState, selectedDistrict).then(setDetail)
      .catch(() => {}).finally(() => setDetailLoading(false))
    getAdminPredictive(selectedState).then(setPredictive).catch(() => {})
  }, [selectedState, selectedDistrict])

  const openState = (state: string) => setParams((p: URLSearchParams) => {
    p.set('tab', 'state'); p.set('state', state); p.delete('district'); return p
  })
  const openDistrict = (district: string) => setParams((p: URLSearchParams) => {
    p.set('district', district); return p
  })
  const clearDistrict = () => setParams((p: URLSearchParams) => { p.delete('district'); return p })

  const runScenario = async (kind: 'pest' | 'irrigation') => {
    setScenarioBusy(true)
    try {
      const res = kind === 'pest'
        ? await runScenarioPestAdvisory(selectedState, selectedDistrict)
        : await runScenarioIrrigation(selectedState, selectedDistrict)
      setScenario({ kind, ...res })
    } finally {
      setScenarioBusy(false)
    }
  }

  const propose = async (kind: 'pest_advisory' | 'irrigation_support') => {
    await proposeAdminAction(kind, selectedState, selectedDistrict)
    alert('Action proposed — review it in the Actions tab.')
  }

  return (
    <>
      <Card className="mb-6">
        <h3 className="font-semibold text-field-800 mb-3">Choose a state</h3>
        {statesLoading ? <Spinner /> : states.length === 0 ? (
          <Empty msg="No states with registered farmers yet." />
        ) : (
          <div className="flex flex-wrap gap-2">
            {states.map((s: any) => (
              <button key={s.state} onClick={() => openState(s.state)}
                className={`px-4 py-2 rounded-xl text-sm font-semibold border transition
                  ${selectedState === s.state
                    ? 'bg-field-600 text-white border-field-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}>
                {s.state} <span className="opacity-70">({s.farmer_count})</span>
              </button>
            ))}
          </div>
        )}

        {selectedState && districts.length > 0 && (
          <div className="mt-3 pt-3 border-t">
            <div className="text-xs text-gray-400 mb-2">District (optional — narrows the view further)</div>
            <div className="flex flex-wrap gap-2">
              <button onClick={clearDistrict}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold border
                  ${!selectedDistrict ? 'bg-field-100 border-field-300 text-field-800' : 'bg-white border-gray-200 text-gray-500'}`}>
                All districts
              </button>
              {districts.map((d: any) => (
                <button key={d.district} onClick={() => openDistrict(d.district)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold border
                    ${selectedDistrict === d.district ? 'bg-field-100 border-field-300 text-field-800' : 'bg-white border-gray-200 text-gray-500'}`}>
                  {d.district} ({d.farmer_count})
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {!selectedState && !statesLoading && <Empty msg="Pick a state above to see its intelligence." />}
      {detailLoading && <Spinner />}

      {detail && !detailLoading && (
        <>
          <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
            <div>
              <h2 className="text-xl font-bold text-field-800">
                📍 {detail.state}{detail.district ? ` / ${detail.district}` : ''}
              </h2>
              <p className="text-sm text-gray-500">{detail.farmer_count} registered farmer(s)/grower(s) · {detail.note}</p>
            </div>
            <HealthScoreCard hs={detail.health_score} />
          </div>

          {/* Immediate problems */}
          <Card className="mb-6 bg-red-50 border-red-100">
            <h3 className="font-semibold text-red-800 mb-3">🚨 Immediate problems</h3>
            {detail.immediate_alerts.length === 0 ? (
              <p className="text-sm text-gray-500">No warning/critical alerts in the last 30 days.</p>
            ) : (
              <div className="space-y-2">
                {detail.immediate_alerts.map((a: any, i: number) => (
                  <div key={i} className="bg-white rounded-xl px-3 py-2 flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold">{a.title}</div>
                      <div className="text-xs text-gray-500">{a.message}</div>
                    </div>
                    <StatusPill status={a.severity} />
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Crops */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
            <Card>
              <h3 className="font-semibold text-field-800 mb-3">🌾 Dominant crops (observed)</h3>
              {detail.crops.dominant.length === 0 ? <Empty msg="No farm crop data yet." /> : (
                <div className="space-y-2">
                  {detail.crops.dominant.map((c: any, i: number) => (
                    <div key={i} className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
                      <span className="text-sm font-medium">{tv(c.crop)}</span>
                      <span className="text-sm text-field-700 font-bold">{c.farms} farm(s)</span>
                    </div>
                  ))}
                </div>
              )}
              {(detail.crops.increasing.length > 0 || detail.crops.declining.length > 0) && (
                <div className="mt-3 pt-3 border-t text-xs space-y-1">
                  {detail.crops.increasing.length > 0 && (
                    <p className="text-field-700">📈 Increasing: {detail.crops.increasing.map(tv).join(', ')}</p>
                  )}
                  {detail.crops.declining.length > 0 && (
                    <p className="text-red-600">📉 Declining: {detail.crops.declining.map(tv).join(', ')}</p>
                  )}
                  <p className="text-gray-400">{detail.crops.trend_basis}</p>
                </div>
              )}
            </Card>

            <Card>
              <h3 className="font-semibold text-field-800 mb-3">💰 Most sold crops (observed sales)</h3>
              {detail.most_sold_crops.length === 0 ? <Empty msg="No completed marketplace sales yet." /> : (
                <div className="space-y-2">
                  {detail.most_sold_crops.map((c: any, i: number) => (
                    <div key={i} className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
                      <span className="text-sm font-medium">{tv(c.crop)}</span>
                      <span className="text-sm text-field-700 font-bold">{c.listings_sold} sale(s) · {c.total_kg} kg</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {/* Pest & disease + water */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
            <Card>
              <h3 className="font-semibold text-field-800 mb-3">🐛 Pest & disease intelligence</h3>
              {detail.pest_disease.pest_reports.length === 0 && detail.pest_disease.disease_reports.length === 0 ? (
                <Empty msg="No pest or disease reports yet." />
              ) : (
                <div className="space-y-3">
                  {detail.pest_disease.pest_reports.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-gray-500 mb-1">Pests</p>
                      {detail.pest_disease.pest_reports.map((p: any, i: number) => (
                        <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-1.5 mb-1">
                          <span className="text-sm">{p.pest}</span>
                          <span className="text-sm font-bold text-field-700">{p.reports}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {detail.pest_disease.disease_reports.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-gray-500 mb-1">Diseases</p>
                      {detail.pest_disease.disease_reports.map((p: any, i: number) => (
                        <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-1.5 mb-1">
                          <span className="text-sm">{p.disease}</span>
                          <span className="text-sm font-bold text-field-700">{p.reports}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {Object.keys(detail.pest_disease.by_severity).length > 0 && (
                    <p className="text-xs text-gray-500">
                      By severity: {Object.entries(detail.pest_disease.by_severity).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                    </p>
                  )}
                </div>
              )}
            </Card>

            <Card>
              <h3 className="font-semibold text-field-800 mb-3">💧 Water stress intelligence</h3>
              {detail.water.monitored_farms === 0 ? (
                <Empty msg="No live sensor data available." />
              ) : (
                <div className="space-y-2">
                  {Object.entries(detail.water.by_status).map(([status, n]: any) => (
                    <div key={status} className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
                      <span className="text-sm capitalize">{WATER_ICON[status] || ''} {status}</span>
                      <span className="text-sm font-bold text-field-700">{n} farm(s)</span>
                    </div>
                  ))}
                  <p className="text-xs text-gray-400">{detail.water.note} ({detail.water.monitored_farms}/{detail.water.total_farms} farms monitored)</p>
                </div>
              )}
            </Card>
          </div>

          {/* Soil, schemes, machinery */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6">
            <Card>
              <h3 className="font-semibold text-field-800 mb-3">🧪 Soil conditions</h3>
              {detail.soil.samples === 0 ? <Empty msg="No soil tests yet." /> : (
                <div className="space-y-2">
                  {Object.entries(detail.soil.breakdown).map(([k, v]: any) => (
                    <div key={k} className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
                      <StatusPill status={k} />
                      <span className="text-sm font-bold text-field-700">{v}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <h3 className="font-semibold text-field-800 mb-3">🏛️ Scheme utilization</h3>
              <div className="text-3xl font-bold text-field-800">
                {detail.schemes.adoption_pct !== null ? `${detail.schemes.adoption_pct}%` : '—'}
              </div>
              <p className="text-xs text-gray-500 mb-2">
                {detail.schemes.engaged_farmers} of {detail.schemes.eligible_farmers} eligible farmer(s) engaged
              </p>
              {detail.schemes_chosen.length > 0 && (
                <div className="space-y-1 mt-2 pt-2 border-t">
                  {detail.schemes_chosen.slice(0, 3).map((s: any, i: number) => (
                    <div key={i} className="text-xs flex justify-between">
                      <span className="truncate pr-2">{s.scheme}</span>
                      <span className="font-bold text-field-700 shrink-0">{s.farmers}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <h3 className="font-semibold text-field-800 mb-3">🚜 Machinery demand</h3>
              {detail.machinery_demand.length === 0 ? <Empty msg="No machinery listings yet." /> : (
                <div className="space-y-2">
                  {detail.machinery_demand.map((m: any, i: number) => (
                    <div key={i} className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
                      <span className="text-sm capitalize">{m.machine.replace(/_/g, ' ')}</span>
                      <span className="text-sm font-bold text-field-700">{m.demand_score}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {/* Predictive */}
          {predictive && (
            <Card className="mb-6">
              <h3 className="font-semibold text-field-800 mb-3">🔮 Predictive intelligence (statistical, not LLM)</h3>
              {!predictive.available ? (
                <p className="text-sm text-gray-400">{predictive.reason}</p>
              ) : (
                <>
                  <p className="text-sm mb-2">
                    Marketplace listing activity is <b>{predictive.direction}</b> — next-period estimate:{' '}
                    <b>{predictive.forecast_next_period}</b>
                  </p>
                  <ResponsiveContainer width="100%" height={160}>
                    <LineChart data={predictive.history}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                      <XAxis dataKey="period" fontSize={11} />
                      <YAxis fontSize={11} />
                      <Tooltip />
                      <Line type="monotone" dataKey="value" stroke="#2f7d40" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                  <p className="text-[11px] text-gray-400 mt-1">{predictive.method}</p>
                </>
              )}
            </Card>
          )}

          {/* Scenario simulator + human-in-the-loop */}
          <Card>
            <h3 className="font-semibold text-field-800 mb-3">🧪 Scenario simulator</h3>
            <p className="text-xs text-gray-500 mb-3">
              Estimates based on current data — a scenario simulation, not a guaranteed real-world outcome.
            </p>
            <div className="flex gap-2 mb-3 flex-wrap">
              <Button variant="ghost" onClick={() => runScenario('pest')} disabled={scenarioBusy}>
                What if we send a pest advisory here?
              </Button>
              <Button variant="ghost" onClick={() => runScenario('irrigation')} disabled={scenarioBusy}>
                What if we allocate irrigation support?
              </Button>
            </div>
            {scenario && (
              <div className="bg-field-50 rounded-xl p-4 text-sm space-y-1">
                <p className="font-semibold text-field-800">SCENARIO SIMULATION</p>
                {scenario.kind === 'pest' ? (
                  <>
                    <p>Farmers targeted: <b>{scenario.farmers_targeted}</b></p>
                    <p>Districts affected: {scenario.districts_affected.join(', ') || '—'}</p>
                    <p className="text-xs text-gray-500">{scenario.expected_coverage}</p>
                    <button onClick={() => propose('pest_advisory')} className="text-xs font-semibold text-field-700 underline mt-2">
                      Propose this as an action →
                    </button>
                  </>
                ) : (
                  <>
                    <p>Farms targeted: <b>{scenario.farms_targeted}</b></p>
                    <p>Districts affected: {scenario.districts_affected.join(', ') || '—'}</p>
                    <p className="text-xs text-gray-500">{scenario.expected_coverage}</p>
                    <button onClick={() => propose('irrigation_support')} className="text-xs font-semibold text-field-700 underline mt-2">
                      Propose this as an action →
                    </button>
                  </>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </>
  )
}

function HealthScoreCard({ hs }: any) {
  const [open, setOpen] = useState(false)
  if (!hs) return null
  const color = hs.score === null ? 'text-gray-400' : hs.score >= 70 ? 'text-field-700' : hs.score >= 45 ? 'text-amber-600' : 'text-red-600'
  return (
    <div className="bg-white rounded-2xl border shadow-sm px-4 py-3 min-w-[180px]">
      <div className="text-xs text-gray-500">Agricultural Health Score</div>
      <div className={`text-3xl font-bold ${color}`}>{hs.score !== null ? `${hs.score}/100` : '—'}</div>
      <div className="text-xs font-semibold">{hs.label}</div>
      <button onClick={() => setOpen(!open)} className="text-[11px] text-field-600 underline mt-1">
        {open ? 'Hide' : 'Why is this the score?'}
      </button>
      {open && (
        <div className="mt-2 pt-2 border-t space-y-1.5">
          {hs.breakdown.map((b: any, i: number) => (
            <div key={i} className="text-[11px]">
              <div className="flex justify-between">
                <span className="font-medium">{b.factor.replace(/_/g, ' ')} ({b.weight_pct}%)</span>
                <span>{b.score !== null ? Math.round(b.score) : 'no data'}</span>
              </div>
              <div className="text-gray-400">{b.evidence}</div>
            </div>
          ))}
          <p className="text-gray-400 pt-1">{hs.methodology}</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- Priority Alerts

function AlertsTab({ tv, goState }: any) {
  const [alerts, setAlerts] = useState<any[] | null>(null)
  useEffect(() => { getAdminPriorityAlerts().then(setAlerts).catch(() => setAlerts([])) }, [])

  if (alerts === null) return <Spinner />
  if (alerts.length === 0) return <Card><Empty msg="No priority alerts right now — no monitored threshold has been crossed." /></Card>

  return (
    <div className="space-y-3">
      {alerts.map((a, i) => (
        <Card key={i}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-lg">{SEVERITY_ICON[a.severity]}</span>
                <h4 className="font-semibold text-field-800">{a.title}</h4>
              </div>
              <p className="text-sm text-gray-600 mt-1">{a.evidence}</p>
              <details className="mt-2 text-xs text-gray-500">
                <summary className="cursor-pointer font-medium">Why was this generated?</summary>
                <ul className="list-disc pl-4 mt-1 space-y-0.5">
                  {a.why.map((w: string, j: number) => <li key={j}>{w}</li>)}
                </ul>
              </details>
              <p className="text-xs text-field-700 font-medium mt-2">➡️ {a.recommended_action}</p>
            </div>
            <button onClick={() => goState(a.state)}
              className="text-xs font-semibold bg-field-600 text-white px-3 py-1.5 rounded-lg whitespace-nowrap">
              View details →
            </button>
          </div>
        </Card>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- Actions (human-in-the-loop)

function ActionsTab() {
  const [actions, setActions] = useState<any[] | null>(null)
  const load = () => getAdminActionsSafe().then(setActions)
  useEffect(() => { load() }, [])

  const decide = async (id: number, status: 'approved' | 'rejected') => {
    await decideAdminAction(id, status)
    load()
  }

  if (actions === null) return <Spinner />
  if (actions.length === 0) return <Card><Empty msg="No proposed actions yet — propose one from the State Intelligence tab's scenario simulator." /></Card>

  return (
    <div className="space-y-3">
      {actions.map((a) => (
        <Card key={a.id}>
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <h4 className="font-semibold text-field-800">{a.title}</h4>
              <p className="text-xs text-gray-500">{a.description}</p>
              <ul className="text-xs text-gray-600 list-disc pl-4 mt-1">
                {(a.reasoning || []).map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
              <p className="text-xs text-gray-400 mt-1">Affected: {a.affected_count}</p>
            </div>
            <div className="flex items-center gap-2">
              <StatusPill status={a.status === 'approved' ? 'OPTIMAL' : a.status === 'rejected' ? 'CRITICAL' : 'WARNING'} />
              {a.status === 'proposed' && (
                <>
                  <button onClick={() => decide(a.id, 'approved')} className="text-xs font-semibold bg-field-600 text-white px-3 py-1.5 rounded-lg">Approve</button>
                  <button onClick={() => decide(a.id, 'rejected')} className="text-xs font-semibold bg-white border px-3 py-1.5 rounded-lg">Reject</button>
                </>
              )}
            </div>
          </div>
        </Card>
      ))}
    </div>
  )
}

function getAdminActionsSafe() {
  return listAdminActions().catch(() => [])
}
