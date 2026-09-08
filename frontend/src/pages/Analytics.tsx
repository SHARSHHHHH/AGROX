import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { getAnalytics, addExpense, deleteExpense } from '../services/api'
import { Card, Spinner, Empty, Button } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

const EXPENSE_CATEGORIES = ['seeds', 'fertilizer', 'labor', 'machinery', 'other']

/** A tap-to-reveal section — collapsed by default, so the page opens as a
 * short list of dropdown boxes rather than a wall of charts at once. */
function Disclosure({ title, subtitle, defaultOpen = false, children }:
  { title: string; subtitle?: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card className="mb-4 !p-0 overflow-hidden">
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50 transition">
        <div>
          <h3 className="font-semibold text-field-800">{title}</h3>
          {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        </div>
        <span className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}>▼</span>
      </button>
      {open && <div className="px-5 pb-5">{children}</div>}
    </Card>
  )
}

export default function Analytics() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expForm, setExpForm] = useState({ category: 'seeds', amount: '', note: '', crop: '' })
  const [savingExpense, setSavingExpense] = useState(false)

  const load = () => {
    getAnalytics().then((res) => {
      setData(res)
      publish('Analytics', [
        res.series?.length ? `${res.series.length} recent sensor reading(s). ${res.insight}` : 'No sensor history yet.',
        `Crops: ${res.crops.sowed} sown, ${res.crops.grown} matured, ${res.crops.growing} still growing. ${res.crops.analysis}`,
        `Finance: earned ₹${res.finance.earned} from ${res.finance.sold_listings} sold listing(s), `
          + `spent ₹${res.finance.spent} across ${res.finance.expense_count} logged expense(s), net ₹${res.finance.net}.`,
      ].join(' '))
    }).finally(() => setLoading(false))
  }
  useEffect(load, [])

  const submitExpense = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!expForm.amount) return
    setSavingExpense(true)
    try {
      await addExpense(expForm.category, Number(expForm.amount), expForm.note, expForm.crop)
      setExpForm({ category: 'seeds', amount: '', note: '', crop: '' })
      load()
    } finally {
      setSavingExpense(false)
    }
  }

  const removeExpense = async (id: number) => { await deleteExpense(id); load() }

  if (loading) return <Spinner />
  if (!data) return <Empty msg="Could not load analytics." />

  const hasSensorData = data.series?.length > 0

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">📈 Analytics</h1>
      <p className="text-sm text-gray-500 mb-2">{t('analytics.subtitle')}</p>
      <p className="text-[11px] text-gray-400 mb-5">{data.data_note}</p>

      {/* Soil & Moisture */}
      <Disclosure title={`💧 ${t('analytics.moisture')}`}
        subtitle={hasSensorData ? `${data.series.length} recent reading(s) — tap to view the chart` : 'No sensor history yet'}>
        {hasSensorData ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data.series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="time" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="soil_moisture" stroke="#2f7d40" name="Soil Moisture %" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        ) : <Empty msg="Generate readings from the Dashboard to see this chart." />}
      </Disclosure>

      {/* Temperature & Humidity */}
      <Disclosure title={`🌡️ ${t('analytics.humidity')}`}
        subtitle={hasSensorData ? `${data.series.length} recent reading(s) — tap to view the chart` : 'No sensor history yet'}>
        {hasSensorData ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data.series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="time" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="temperature" stroke="#d97706" name="Temp °C" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="humidity" stroke="#0ea5e9" name="Humidity %" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        ) : <Empty msg="Generate readings from the Dashboard to see this chart." />}
      </Disclosure>

      {/* Crops sowed / grown */}
      <Disclosure title="🌱 Crops sown & grown"
        subtitle={`${data.crops.sowed} sown · ${data.crops.grown} matured · ${data.crops.growing} still growing`}>
        <p className="text-sm text-gray-700 mb-3">{data.crops.analysis}</p>
        {data.crops.by_crop.length > 0 ? (
          <div className="space-y-2">
            {data.crops.by_crop.map((c: any, i: number) => (
              <div key={i} className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
                <span className="text-sm font-medium">{tv(c.crop)}</span>
                <span className="text-sm text-gray-600">{c.sowed} sown · <b className="text-field-700">{c.grown} matured</b></span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-400">
            Log a crop on the <a href="/sell" className="text-field-600 font-semibold">Sell Produce</a> page to start tracking.
          </p>
        )}
      </Disclosure>

      {/* Spent vs earned */}
      <Disclosure title="💰 Spent & earned"
        subtitle={`Earned ₹${data.finance.earned} · Spent ₹${data.finance.spent} · Net ₹${data.finance.net}`}>
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-field-50 rounded-xl px-3 py-2 text-center">
            <div className="text-xs text-gray-500">Earned</div>
            <div className="text-lg font-bold text-field-700">₹{data.finance.earned}</div>
          </div>
          <div className="bg-red-50 rounded-xl px-3 py-2 text-center">
            <div className="text-xs text-gray-500">Spent</div>
            <div className="text-lg font-bold text-red-600">₹{data.finance.spent}</div>
          </div>
          <div className={`rounded-xl px-3 py-2 text-center ${data.finance.net >= 0 ? 'bg-field-50' : 'bg-amber-50'}`}>
            <div className="text-xs text-gray-500">Net</div>
            <div className={`text-lg font-bold ${data.finance.net >= 0 ? 'text-field-700' : 'text-amber-700'}`}>₹{data.finance.net}</div>
          </div>
        </div>
        <p className="text-xs text-gray-400 mb-4">{data.finance.note}</p>

        {data.finance.recent_expenses.length > 0 && (
          <div className="space-y-1.5 mb-4">
            {data.finance.recent_expenses.map((e: any) => (
              <div key={e.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-1.5 text-sm">
                <span className="capitalize">{e.category}{e.crop ? ` · ${tv(e.crop)}` : ''}{e.note ? ` — ${e.note}` : ''}</span>
                <div className="flex items-center gap-2">
                  <span className="font-semibold">₹{e.amount}</span>
                  <button onClick={() => removeExpense(e.id)} className="text-xs text-red-500 hover:text-red-700">✕</button>
                </div>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={submitExpense} className="grid grid-cols-2 sm:grid-cols-4 gap-2 items-end">
          <div>
            <label className="text-xs text-gray-500">Category</label>
            <select value={expForm.category} onChange={(e) => setExpForm({ ...expForm, category: e.target.value })}
              className="mt-1 w-full border rounded-lg px-2 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600">
              {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">Amount (₹)</label>
            <input type="number" min="0" value={expForm.amount}
              onChange={(e) => setExpForm({ ...expForm, amount: e.target.value })}
              className="mt-1 w-full border rounded-lg px-2 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
          </div>
          <div>
            <label className="text-xs text-gray-500">Note (optional)</label>
            <input value={expForm.note} onChange={(e) => setExpForm({ ...expForm, note: e.target.value })}
              className="mt-1 w-full border rounded-lg px-2 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
          </div>
          <Button type="submit" disabled={savingExpense || !expForm.amount}>
            {savingExpense ? 'Saving…' : 'Log expense'}
          </Button>
        </form>
      </Disclosure>

      <Card className="bg-field-50/40">
        <p className="text-sm text-gray-700">💡 {data.insight}</p>
      </Card>
    </div>
  )
}
