import { useEffect, useState } from 'react'
import { checkEligibility, getUser, getOnboardingStatus, markSchemeInterest, getMySchemeInterests } from '../services/api'
import { Card, Button, Spinner } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

/**
 * Government schemes.
 *
 * The eligibility check now runs at the TOP of the page, and only schemes
 * the farmer likely qualifies for are shown — no "possibly eligible" /
 * "not eligible" / "missing information" clutter to sift through. The old
 * page had a second, separately-loaded "Recommended for you" list above
 * this that used the same underlying engine but was never filtered the same
 * way; that duplication is gone, this is the one list.
 *
 * The form is pre-filled from the farmer's saved profile (Farm Setup) and
 * the check runs automatically on load, so a farmer sees real matches
 * immediately without having to fill in a form first. Every field stays
 * editable — e.g. to check eligibility for a different crop than what's
 * currently planted.
 */
export default function Schemes() {
  const { t } = useLanguage()
  const { publish } = usePageContext()
  const user = getUser()

  const [form, setForm] = useState({
    state: user?.state || '', farmer_category: 'small',
    land_size_acres: '1', crop: '',
  })
  const [eligible, setEligible] = useState<any[] | null>(null)
  const [checking, setChecking] = useState(true)
  const [autofilled, setAutofilled] = useState(false)
  const [chosen, setChosen] = useState<number[]>([])

  const set = (k: string, v: string) => setForm({ ...form, [k]: v })

  const chooseScheme = async (id: number) => {
    setChosen((c) => [...c, id])          // optimistic — this is what powers
    try { await markSchemeInterest(id) }  // the state-wise "schemes chosen"
    catch { setChosen((c) => c.filter((x) => x !== id)) }  // admin view
  }

  const runCheck = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setChecking(true)
    try {
      const res = await checkEligibility({ ...form, land_size_acres: +form.land_size_acres || 0 })
      const likelyEligible = (res || []).filter((r: any) => r.verdict === 'Likely eligible')
      setEligible(likelyEligible)
      publish('Government Schemes', likelyEligible.length
        ? `Checked eligibility for state ${form.state}, category ${form.farmer_category}, `
          + `${form.land_size_acres} acre(s)${form.crop ? `, crop ${form.crop}` : ''}. `
          + `Eligible for: ${likelyEligible.map((r: any) => r.scheme_name).join(', ')}.`
        : `Checked eligibility for state ${form.state}, category ${form.farmer_category}, `
          + `${form.land_size_acres} acre(s)${form.crop ? `, crop ${form.crop}` : ''} — no schemes matched.`)
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => {
    // Pre-fill from the farmer's saved profile (Farm Setup), then run the
    // check immediately — a farmer should see real matches without having
    // to touch the form first.
    getOnboardingStatus().then((s) => {
      const farm = s?.farm
      if (farm) {
        setForm((f) => ({
          state: f.state || farm.state || '',
          farmer_category: farm.farmer_category || f.farmer_category,
          land_size_acres: farm.land_size_acres ? String(farm.land_size_acres) : f.land_size_acres,
          crop: farm.crop || f.crop,
        }))
        setAutofilled(true)
      }
    }).catch(() => {}).finally(() => { runCheck() })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (user?.role === 'farmer' || user?.role === 'balcony') {
      getMySchemeInterests().then(setChosen).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">{t('schemes.title')}</h1>
      <p className="text-sm text-gray-500 mb-5">{t('schemes.subtitle')}</p>

      <Card className="bg-field-50/40 mb-6">
        <h3 className="font-semibold text-field-800 mb-1">{t('schemes.check')}</h3>
        {autofilled && <p className="text-[11px] text-field-700 mb-3">✓ {t('schemes.autofilled')}</p>}
        <form onSubmit={runCheck} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input placeholder={t('common.state')} value={form.state} onChange={(e) => set('state', e.target.value)}
            className="border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
          <select value={form.farmer_category} onChange={(e) => set('farmer_category', e.target.value)}
            className="border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600">
            {['marginal', 'small', 'medium', 'large'].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input type="number" step="0.1" placeholder={t('schemes.landsize')} value={form.land_size_acres}
            onChange={(e) => set('land_size_acres', e.target.value)}
            className="border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
          <input placeholder={t('crop.cropoptional')} value={form.crop} onChange={(e) => set('crop', e.target.value)}
            className="border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
          <div className="sm:col-span-2">
            <Button type="submit" disabled={checking}>
              {checking ? t('schemes.checking') : t('schemes.recheck')}
            </Button>
          </div>
        </form>
      </Card>

      <h3 className="font-semibold text-field-800 mb-3">{t('schemes.recommended')}</h3>
      {checking && !eligible && <Spinner />}

      {eligible && eligible.length === 0 && (
        <Card><p className="text-sm text-gray-500 py-4 text-center">{t('schemes.none')}</p></Card>
      )}

      {eligible && eligible.length > 0 && (
        <div className="space-y-3">
          {eligible.map((r) => (
            <Card key={r.scheme_id}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-semibold text-field-800">{r.scheme_name}</h4>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-100 text-green-800
                                     border border-green-300 font-bold uppercase">
                      {r.verdict}
                    </span>
                  </div>
                  {r.why?.length > 0 && (
                    <ul className="text-sm text-gray-600 mt-2 list-disc pl-4 space-y-0.5">
                      {r.why.slice(0, 3).map((w: string, i: number) => <li key={i}>{w}</li>)}
                    </ul>
                  )}
                  {r.note && <p className="text-[11px] text-amber-600 mt-2">⚠️ {r.note}</p>}
                  {chosen.includes(r.scheme_id) ? (
                    <p className="text-xs text-field-700 font-semibold mt-2">✓ Marked as applying</p>
                  ) : (
                    <button onClick={() => chooseScheme(r.scheme_id)}
                      className="text-xs text-field-700 font-semibold mt-2 underline underline-offset-2 hover:text-field-900">
                      I'm applying for this
                    </button>
                  )}
                </div>
                <a href={r.url} target="_blank" rel="noreferrer"
                   className="text-xs bg-field-600 text-white px-3 py-1.5 rounded-lg whitespace-nowrap hover:bg-field-700">
                  {t('schemes.apply')}
                </a>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
