import { useEffect, useState } from 'react'
import { getSoil, addSoilTest } from '../services/api'
import { Card, Button, Spinner, StatusPill, StatCard } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

export default function Soil() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const [soil, setSoil] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ nitrogen: '', phosphorus: '', potassium: '', ph: '', ec: '' })
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true)
    getSoil().then((res) => {
      setSoil(res)
      publish('Soil Health', res?.has_data
        ? `Overall soil health: ${res.overall}. Nitrogen ${res.nitrogen.value} (${res.nitrogen.status}), `
          + `Phosphorus ${res.phosphorus.value} (${res.phosphorus.status}), `
          + `Potassium ${res.potassium.value} (${res.potassium.status}), pH ${res.ph.value} (${res.ph.status}). `
          + `Suggestions: ${res.suggestions?.join('; ')}`
          + (res.warnings?.length ? `. Warnings: ${res.warnings.join('; ')}` : '')
        : `No soil test recorded yet. ${res?.message || ''}`)
    }).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const set = (k: string, v: string) => setForm({ ...form, [k]: v })

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { nitrogen: +form.nitrogen, phosphorus: +form.phosphorus,
        potassium: +form.potassium, ph: +form.ph, ec: +form.ec || 0 }
      const res = await addSoilTest(payload)
      setSoil({ ...res, has_data: true })
      setForm({ nitrogen: '', phosphorus: '', potassium: '', ph: '', ec: '' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">🧪 Soil Health</h1>
      <p className="text-sm text-gray-500 mb-5">{t('soil.subtitle')}</p>

      {loading ? <Spinner /> : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div>
            {soil?.has_data ? (
              <>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-sm text-gray-500">Overall:</span>
                  <StatusPill status={soil.overall} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <StatCard label={t('soil.nitrogenN')} value={soil.nitrogen.value} status={soil.nitrogen.status} />
                  <StatCard label={t('soil.phosphorusP')} value={soil.phosphorus.value} status={soil.phosphorus.status} />
                  <StatCard label={t('soil.potassiumK')} value={soil.potassium.value} status={soil.potassium.status} />
                  <StatCard label={t('soil.ph')} value={soil.ph.value} status={soil.ph.status} />
                </div>
                {soil.warnings?.length > 0 && (
                  <Card className="mt-3 bg-orange-50 border-orange-100">
                    <p className="text-xs font-semibold text-orange-700 uppercase mb-1">{t('common.warnings')}</p>
                    <ul className="text-sm text-gray-700 list-disc pl-4 space-y-1">
                      {soil.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
                    </ul>
                  </Card>
                )}
                <Card className="mt-3 bg-field-50 border-field-100">
                  <p className="text-xs font-semibold text-field-700 uppercase mb-1">{t('common.suggestions')}</p>
                  <ul className="text-sm text-gray-700 list-disc pl-4 space-y-1">
                    {soil.suggestions.map((s: string, i: number) => <li key={i}>{s}</li>)}
                  </ul>
                </Card>
              </>
            ) : (
              <Card><p className="text-sm text-gray-500">{soil?.message || 'No soil test yet.'}</p></Card>
            )}
          </div>

          <Card>
            <h3 className="font-semibold text-field-800 mb-3">{t('soil.enter')}</h3>
            <form onSubmit={submit} className="space-y-3">
              {[['nitrogen','Nitrogen (kg/ha)'],['phosphorus','Phosphorus (kg/ha)'],
                ['potassium','Potassium (kg/ha)'],['ph','pH (0–14)'],['ec','EC (optional)']].map(([k, label]) => (
                <div key={k}>
                  <label className="text-sm font-medium text-gray-600">{label}</label>
                  <input type="number" step="0.1" required={k !== 'ec'}
                    value={(form as any)[k]} onChange={(e) => set(k, e.target.value)}
                    className="mt-1 w-full border rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-field-600" />
                </div>
              ))}
              <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Analyze soil'}</Button>
            </form>
            <p className="text-[11px] text-gray-400 mt-3">
              Don't have a lab test? Request a free Soil Health Card (see Govt Schemes).
            </p>
          </Card>
        </div>
      )}
    </div>
  )
}
