import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getCircularPlan, getLivestock, saveLivestock, allocateDigestate,
  getResidueAdvice, listSurplus, getTechnicians, getBiogasScheme,
  getManurePlan, getMyBiogasPlant, registerBiogasPlant, addBiogasLog,
  getCircularChoice, saveCircularChoice, setManureKeep,
} from '../services/api'
import { Card, Button, Spinner } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'
import { CircularIcon } from '../components/CircularIcons'

/**
 * Circular farming: cattle -> biogas -> digestate -> crops -> residue -> repeat.
 *
 * Presented as ONE continuous cycle rather than a set of calculators, because
 * the point of the module is that the outputs of each stage are the inputs of
 * the next. A farmer who sees five separate tools does not see a cycle.
 *
 * Every number on this page is an ESTIMATE from figures the farmer typed in.
 * Nothing is measured. The ranges and the caveats are not decoration — a
 * farmer may spend real money on a plant based on what they read here.
 */

const ANIMALS = ['cow', 'buffalo', 'bullock', 'goat', 'poultry']

const VERDICT_STYLE: Record<string, string> = {
  SUITABLE: 'border-green-400 bg-green-50 text-green-900',
  POSSIBLE: 'border-amber-400 bg-amber-50 text-amber-900',
  NOT_YET: 'border-gray-300 bg-gray-50 text-gray-800',
  NO_DATA: 'border-gray-300 bg-gray-50 text-gray-800',
}

export default function CircularFarming() {
  const { t } = useLanguage()
  const { publish } = usePageContext()
  const navigate = useNavigate()

  const [plan, setPlan] = useState<any>(null)
  const [herd, setHerd] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [reserve, setReserve] = useState('')
  const [residue, setResidue] = useState<any>(null)
  const [err, setErr] = useState('')

  // The page is a DECISION first, not a dashboard. Farmers pick what they
  // want to do with their waste; everything else follows from that choice.
  //
  // The choice lives on the SERVER, not in this component. Holding it here
  // only meant a reload — or a trip to another page and back — threw it away
  // and asked the same question again, which makes the app feel like it is
  // not listening.
  const [mode, setMode] = useState<'' | 'biogas' | 'manure' | 'plant'>('')
  const [techs, setTechs] = useState<any[]>([])
  const [scheme, setScheme] = useState<any>(null)
  const [dungOverride, setDungOverride] = useState('')
  const [editingDung, setEditingDung] = useState(false)
  const [openStep, setOpenStep] = useState<string | null>(null)
  const [guideOpen, setGuideOpen] = useState(false)

  // The only three things we cannot infer from the farm record.
  const [shade, setShade] = useState(true)
  const [labour, setLabour] = useState('normal')
  const [urgent, setUrgent] = useState(false)
  const [mplan, setMplan] = useState<any>(null)
  // Once the three questions have been answered they collapse to a single
  // line. `editingAnswers` reopens them, and nothing else does.
  const [answered, setAnswered] = useState(false)
  const [editingAnswers, setEditingAnswers] = useState(false)
  const [keep, setKeep] = useState('')
  // Biogas registration state, read from the server. Held here so the manure
  // branch can honour a plant the farmer registered weeks ago instead of
  // asking them to register it again.
  const [biogas, setBiogas] = useState<any>(null)

  const openManure = async (
    opts: { has_shade?: boolean; labour?: string; urgent?: boolean } = {}) => {
    setMode('manure')
    try {
      const p = await getManurePlan({
        has_shade: opts.has_shade ?? shade,
        labour: opts.labour ?? labour,
        urgent: opts.urgent ?? urgent,
      })
      setMplan(p)
      // The plan reports the plant too, so the manure branch always knows
      // whether one is registered without a second round trip.
      if (p?.biogas) setBiogas(p.biogas)
    } catch { setMplan(null) }
  }

  /** Answer the three questions and show the plan. The questions collapse. */
  const confirmAnswers = async () => {
    setBusy(true)
    try {
      await saveCircularChoice({
        mode: 'manure', has_shade: shade, labour, urgent, answered: true,
      })
      await openManure()
      setAnswered(true)
      setEditingAnswers(false)
    } catch { setErr(t('cf.saveFailed')) } finally { setBusy(false) }
  }

  const [plant, setPlant] = useState<any>(null)

  const openPlant = async () => {
    setMode('plant')
    try {
      const p = await getMyBiogasPlant()
      setPlant(p)
      setBiogas((b: any) => ({ ...(b || {}), registered: !!p?.has_plant }))
    } catch { setPlant(null) }
  }

  const logToday = async (payload: any) => {
    setBusy(true)
    try { setPlant(await addBiogasLog(payload)) }
    catch { setErr(t('cf.saveFailed')) } finally { setBusy(false) }
  }

  const openBiogas = async () => {
    setMode('biogas')
    const [t, sc] = await Promise.allSettled([getTechnicians(), getBiogasScheme()])
    if (t.status === 'fulfilled') setTechs(t.value.technicians || [])
    if (sc.status === 'fulfilled') setScheme(sc.value)
  }

  /** Pick a path and remember it, so the question is asked once. */
  const choose = async (m: 'biogas' | 'plant' | 'manure') => {
    saveCircularChoice({ mode: m }).catch(() => {})
    if (m === 'biogas') return openBiogas()
    if (m === 'plant') return openPlant()
    return openManure()
  }

  /** Back to the menu — and forget the choice, since that is what was meant. */
  const clearMode = () => {
    setMode('')
    setMplan(null)
    setAnswered(false)
    setEditingAnswers(false)
    saveCircularChoice({ mode: '' }).catch(() => {})
  }

  const load = async () => {
    setLoading(true)
    const [p, l, r, c] = await Promise.allSettled([
      getCircularPlan(), getLivestock(), getResidueAdvice(), getCircularChoice(),
    ])
    if (p.status === 'fulfilled') {
      setPlan(p.value)
      const s = p.value.steps
      publish('Circular Farming',
        p.value.has_livestock
          ? `Biogas feasibility: ${s['1_feasibility']?.verdict}. `
            + `Estimated biogas ${s['2_biogas_potential']?.biogas_m3_per_day?.mid} m3/day. `
            + `Digestate about ${s['4_digestate']?.total_available_kg} kg/month, `
            + `${s['7_surplus']} kg surplus. All figures are ESTIMATES from `
            + `farmer-entered data, never measured.`
          : 'No livestock recorded yet, so no biogas estimate is available.')
    }
    if (l.status === 'fulfilled') setHerd(l.value.livestock || [])
    if (r.status === 'fulfilled') setResidue(r.value)

    // Restore the path this farmer already chose, and go straight back into
    // it rather than asking again.
    if (c.status === 'fulfilled' && c.value) {
      const saved = c.value
      if (saved.biogas) setBiogas(saved.biogas)
      setShade(saved.has_shade !== false)
      setLabour(saved.labour || 'normal')
      setUrgent(!!saved.urgent)
      setAnswered(!!saved.answered)
      if (saved.keep_kg != null) setKeep(String(saved.keep_kg))
      if (saved.mode === 'biogas') openBiogas()
      else if (saved.mode === 'plant') openPlant()
      else if (saved.mode === 'manure') {
        setMode('manure')
        getManurePlan().then(setMplan).catch(() => setMplan(null))
      }
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const setCount = (type: string, count: number) => {
    setHerd((h) => {
      const rest = h.filter((x) => x.animal_type !== type)
      return count > 0 ? [...rest, { animal_type: type, count }] : rest
    })
  }
  const countOf = (type: string) =>
    herd.find((x) => x.animal_type === type)?.count || 0

  const onSaveHerd = async () => {
    setBusy(true); setErr('')
    try {
      await saveLivestock(herd.map((h) => ({
        animal_type: h.animal_type, count: h.count,
      })))
      await load()
    } catch { setErr(t('cf.saveFailed')) } finally { setBusy(false) }
  }

  const onReserve = async () => {
    setBusy(true); setErr('')
    try {
      await allocateDigestate(Number(reserve))
      await load()
    } catch (e: any) {
      setErr(e?.response?.data?.detail || t('cf.saveFailed'))
    } finally { setBusy(false) }
  }

  /** How much finished compost stays on this farm. The rest is the balance. */
  const onSaveKeep = async () => {
    setBusy(true); setErr('')
    try { setMplan(await setManureKeep(Number(keep) || 0)) }
    catch { setErr(t('cf.saveFailed')) } finally { setBusy(false) }
  }

  /**
   * Hand the balance over to Sell Produce.
   *
   * The quantity, the material and a suggested price travel with the farmer
   * rather than being typed a second time — retyping a figure the app already
   * knows is exactly the sort of friction that stops a listing being made.
   */
  const sellBalance = () => {
    const sell = mplan?.sell || {}
    navigate('/sell', {
      state: {
        fertilizer: {
          quantity_kg: sell.quantity_kg,
          method: mplan?.method?.recommended || 'compost',
          product_name: sell.suggested_name || sell.product_label || 'Compost',
          suggested_price: sell.price?.suggested,
          price_low: sell.price?.low,
          price_high: sell.price?.high,
          price_basis: sell.price?.basis,
          price_caveat: sell.price?.caveat,
          unit: sell.price?.unit || 'kg',
          ready_weeks: mplan?.output?.ready_in_weeks,
        },
      },
    })
  }

  if (loading) return <Spinner />

  const s = plan?.steps || {}
  const feas = s['1_feasibility']
  const est = s['2_biogas_potential']
  const dig = s['4_digestate']
  const crop = s['5_crop_use']

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-field-800">♻️ {t('cf.title')}</h1>
      <p className="text-sm text-gray-500 mb-4">{t('cf.subtitle')}</p>

      {err && <div className="error">{err}</div>}

      {/* Anything that would stop a plant working is said HERE, before the
          farmer reads four steps and finds out at the end. Water scarcity is
          the big one: a digester needs its own volume in water every day. */}
      {plan?.upfront_warnings?.length > 0 && (
        <div className="space-y-2 mb-3">
          {plan.upfront_warnings.map((w: any, i: number) => (
            <div key={i} className={`rounded-xl border-2 p-3 ${
              w.level === 'blocker'
                ? 'border-red-300 bg-red-50' : 'border-amber-300 bg-amber-50'}`}>
              <p className={`text-sm font-semibold ${
                w.level === 'blocker' ? 'text-red-900' : 'text-amber-900'}`}>
                {w.level === 'blocker' ? '🛑' : '⚠️'} {w.message}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* ---------- The cycle, always visible ---------- */}
      <Card>
        <h3 className="font-semibold text-field-800 mb-3">{t('cf.cycle')}</h3>
        <CycleDiagram nodes={plan?.cycle || []} />
      </Card>

      {/* ---------- 1. Cattle ---------- */}
      <Card>
        <h3 className="font-semibold text-field-800">1. {t('cf.yourCattle')}</h3>
        <p className="text-sm text-gray-600 mb-3">{t('cf.cattleHelp')}</p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {ANIMALS.map((a) => (
            <div key={a}>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                {t(`cf.animal.${a}`)}
              </label>
              <input type="number" min={0} value={countOf(a)}
                     onChange={(e) => setCount(a, Number(e.target.value))}
                     className="w-full border rounded-lg px-2 py-1.5 text-sm" />
            </div>
          ))}
        </div>
        <div className="mt-3">
          <Button onClick={onSaveHerd} disabled={busy}>
            {busy ? t('cf.saving') : t('cf.saveCattle')}
          </Button>
        </div>
      </Card>

      {/* ---------- Entry: what do you want to do? ---------- */}
      {!mode && (
        <Card>
          <h3 className="font-bold text-field-800 text-lg mb-1">
            {t('cf.ask')}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            <button onClick={() => choose('biogas')}
                    className="text-left rounded-2xl border-2 border-orange-200
                               bg-orange-50 p-4 hover:border-orange-400 transition">
              <div className="text-orange-600"><CircularIcon name="biogas" size={30} /></div>
              <p className="font-bold text-field-800 mt-1">{t('cf.optBiogas')}</p>
              <p className="text-sm text-gray-600 mt-1">{t('cf.optBiogasDesc')}</p>
            </button>
            <button onClick={() => choose('plant')}
                    className="text-left rounded-2xl border-2 border-blue-200
                               bg-blue-50 p-4 hover:border-blue-400 transition">
              <div className="text-blue-600"><CircularIcon name="technician" size={30} /></div>
              <p className="font-bold text-field-800 mt-1">{t('cf.optHave')}</p>
              <p className="text-sm text-gray-600 mt-1">{t('cf.optHaveDesc')}</p>
            </button>
            <button onClick={() => choose('manure')}
                    className="text-left rounded-2xl border-2 border-green-200
                               bg-green-50 p-4 hover:border-green-400 transition">
              <div className="text-green-700"><CircularIcon name="crops" size={30} /></div>
              <p className="font-bold text-field-800 mt-1">{t('cf.optManure')}</p>
              <p className="text-sm text-gray-600 mt-1">{t('cf.optManureDesc')}</p>
            </button>
          </div>
        </Card>
      )}

      {/* Once chosen, the three big cards are gone for good and a single line
          says what was picked. The farmer is told the app remembered, because
          otherwise "why is my choice still here?" is a fair question. */}
      {mode && (
        <div className="flex items-center gap-3 rounded-xl border border-field-200
                        bg-field-50 px-3 py-2 mb-3">
          <span className="text-field-700 flex-shrink-0">
            <CircularIcon
              name={mode === 'biogas' ? 'biogas'
                : mode === 'plant' ? 'technician' : 'crops'} size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold text-field-600 uppercase leading-tight">
              {t('cf.yourChoice')}
            </p>
            <p className="text-sm font-bold text-field-800 truncate">
              {mode === 'biogas' ? t('cf.optBiogas')
                : mode === 'plant' ? t('cf.optHave') : t('cf.optManure')}
            </p>
          </div>
          <button onClick={clearMode}
                  className="text-xs font-semibold text-field-700 underline
                             flex-shrink-0">
            {t('cf.changeChoice')}
          </button>
        </div>
      )}

      {/* ---------- BIOGAS: step 1, the waste we found ---------- */}
      {mode === 'biogas' && est && (
        <Card>
          <p className="text-[10px] font-bold text-gray-400 uppercase">
            {t('cf.step')} 1
          </p>
          <h3 className="font-bold text-field-800">{t('cf.wasteFound')}</h3>
          <p className="text-2xl font-bold text-field-800 mt-2">
            {plan?.cycle?.find((c: any) => c.node === 'dung')?.value} kg
            <span className="text-sm font-normal text-gray-500">
              {' '}/ {t('cf.dungPerDay')}
            </span>
          </p>
          {!editingDung ? (
            <div className="flex gap-2 mt-2">
              <Button onClick={() => setEditingDung(false)}>
                ✓ {t('cf.looksRight')}
              </Button>
              <Button variant="ghost" onClick={() => setEditingDung(true)}>
                {t('cf.changeAmount')}
              </Button>
            </div>
          ) : (
            <div className="flex items-end gap-2 mt-2">
              <input type="number" value={dungOverride}
                     onChange={(e) => setDungOverride(e.target.value)}
                     className="border rounded-lg px-2 py-1.5 text-sm w-28" />
              <Button onClick={async () => {
                if (dungOverride && Number(dungOverride) > 0) {
                  setBusy(true)
                  try {
                    await allocateDigestate(Number(dungOverride))
                    await load()
                    setEditingDung(false)
                  } catch {
                    setErr(t('cf.saveFailed'))
                  } finally {
                    setBusy(false)
                  }
                } else {
                  setEditingDung(false)
                }
              }}>
                {busy ? t('cf.saving') : t('cf.reserveBtn')}
              </Button>
            </div>
          )}
        </Card>
      )}

      {/* ---------- BIOGAS: step 3, the plant ---------- */}
      {mode === 'biogas' && est && (
        <Card>
          <p className="text-[10px] font-bold text-gray-400 uppercase">
            {t('cf.step')} 3
          </p>
          <h3 className="font-bold text-field-800">{t('cf.yourPlant')}</h3>
          <p className="text-4xl font-bold text-field-800 mt-2">
            {est.suggested_plant_size_m3}
            <span className="text-base font-normal text-gray-500"> m³</span>
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
            <Stat label={t('cf.gasProduced')} r={est.biogas_m3_per_day} unit="m³" />
            <Stat label={t('cf.dungNeeded')}
                  value={`${est.daily_feed_kg?.mid} kg`} />
            <Stat label={t('cf.waterNeeded')}
                  value={`${est.water_needed_litres_per_day} L`} />
            <Stat label={t('cf.spaceNeeded')}
                  value={`${est.space_needed_m2} m²`} />
          </div>
          <p className="text-[11px] text-gray-500 mt-2">{est.plant_size_basis}</p>
        </Card>
      )}

      {/* ---------- BIOGAS: step 4, how it gets built ---------- */}
      {mode === 'biogas' && s['3_preparation'] && (
        <Card>
          {/* Collapsed by default. Most farmers want the plant size and the
              cost, not a construction walkthrough — this is here for the ones
              who do, without making everyone scroll past it. */}
          <button onClick={() => setGuideOpen(!guideOpen)}
                  className="w-full flex items-center justify-between text-left">
            <div>
              <p className="text-[10px] font-bold text-gray-400 uppercase">
                {t('cf.step')} 4
              </p>
              <h3 className="font-bold text-field-800">{t('cf.installGuide')}</h3>
            </div>
            <span className="text-sm text-gray-400">
              {s['3_preparation'].length} {t('cf.stepsWord')} {guideOpen ? '▲' : '▼'}
            </span>
          </button>

          {guideOpen && (
            <div className="mt-3 divide-y divide-gray-100 border-t border-gray-100">
              {s['3_preparation'].map((st: any) => (
                <div key={st.n}>
                  {/* One line per step; the detail opens only if tapped. */}
                  <button onClick={() => setOpenStep(openStep === st.n ? null : st.n)}
                          className="w-full flex items-center gap-2 py-2.5 text-left">
                    <span className="w-6 h-6 rounded-full bg-field-100
                                     text-field-800 font-bold text-[11px]
                                     flex items-center justify-center
                                     flex-shrink-0">{st.n}</span>
                    <span className="flex-1 text-sm font-medium text-field-800
                                     truncate">{st.stage}</span>
                    <span className={`text-[9px] font-bold px-1.5 py-0.5
                      rounded-full flex-shrink-0 ${st.who === 'technician'
                        ? 'bg-amber-100 text-amber-900'
                        : st.who === 'both' ? 'bg-blue-100 text-blue-900'
                        : 'bg-green-100 text-green-900'}`}>
                      {st.who === 'technician' ? t('cf.techDoes')
                        : st.who === 'both' ? t('cf.bothDo') : t('cf.youDo')}
                    </span>
                    <span className="text-gray-400 text-xs flex-shrink-0">
                      {openStep === st.n ? '▲' : '▼'}
                    </span>
                  </button>
                  {openStep === st.n && (
                    <p className="text-sm text-gray-700 pb-3 pl-8">{st.detail}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* ---------- BIOGAS: switch to manure ---------- */}
      {mode === 'biogas' && (
        <Card>
          <div className="rounded-xl border-2 border-field-300 bg-field-50 p-3">
            <p className="text-[10px] font-bold text-field-700 uppercase">
              {t('cf.alsoMakeManure')}
            </p>
            <p className="text-sm text-gray-700 mt-1">
              {t('cf.biogasDigestate')}
            </p>
            <div className="mt-2">
              <Button onClick={() => choose('manure')}>
                ♻️ {t('cf.optManure')}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* ---------- BIOGAS: government support ---------- */}
      {mode === 'biogas' && scheme && (
        <Card>
          <h3 className="font-bold text-field-800">🏛️ {t('cf.govHelp')}</h3>
          <p className="text-sm text-gray-700 mt-1">{scheme.covers}</p>
          <p className="text-sm font-semibold text-field-800 mt-2">
            {t('cf.checkElig')}
          </p>
          <ul className="text-sm text-gray-700 list-disc ml-5">
            {scheme.eligibility?.map((e: string, i: number) => <li key={i}>{e}</li>)}
          </ul>
          {/* No subsidy amount is shown: it changes between financial years
              and a stale figure quoted confidently is worse than a link. */}
          <p className="text-[11px] text-gray-500 mt-2">{scheme.amount_note}</p>
          <a href={scheme.official_portal} target="_blank" rel="noreferrer"
             className="inline-block mt-2 text-sm font-semibold
                        text-field-700 underline">
            {t('cf.openPortal')} →
          </a>
        </Card>
      )}

      {/* ---------- BIOGAS: installers ---------- */}
      {mode === 'biogas' && (
        <Card>
          <h3 className="font-bold text-field-800"><CircularIcon name="technician" size={18} /> {t('cf.needHelp')}</h3>
          {techs.length === 0 ? (
            <p className="text-sm text-gray-600 mt-1">{t('cf.noTech')}</p>
          ) : (
            <div className="space-y-2 mt-2">
              {techs.map((tech) => (
                <div key={tech.id}
                     className="rounded-xl border border-gray-200 p-2.5">
                  <p className="font-bold text-sm text-field-800">{tech.name}</p>
                  <p className="text-xs text-gray-500">{tech.location}</p>
                  {tech.phone && (
                    <a href={`tel:${tech.phone}`}
                       className="text-sm font-semibold text-field-700 underline">
                      📞 {t('cf.contact')} {tech.phone}
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* ---------- 2. Feasibility (biogas branch) ---------- */}
      {mode === 'biogas' && feas && (
        <Card>
          <h3 className="font-semibold text-field-800">2. {t('cf.feasibility')}</h3>
          <div className={`rounded-xl border-2 p-3 mt-2 ${
            VERDICT_STYLE[feas.verdict] || VERDICT_STYLE.NO_DATA}`}>
            <p className="font-bold">{t(`cf.verdict.${feas.verdict}`)}</p>
            <p className="text-sm mt-1">{feas.reason}</p>
          </div>
          {feas.blockers?.length > 0 && (
            <ul className="text-sm text-gray-700 list-disc ml-5 mt-2">
              {feas.blockers.map((b: string, i: number) => <li key={i}>{b}</li>)}
            </ul>
          )}
          {feas.warnings?.length > 0 && (
            <ul className="text-sm text-amber-800 list-disc ml-5 mt-2">
              {feas.warnings.map((b: string, i: number) => <li key={i}>{b}</li>)}
            </ul>
          )}
          {feas.caveat && (
            <p className="text-[11px] text-gray-500 mt-2">{feas.caveat}</p>
          )}
        </Card>
      )}

      {/* ---------- Detail, biogas branch ---------- */}
      {mode === 'biogas' && false && est && (
        <Card>
          <h3 className="font-semibold text-field-800">
            3. {t('cf.potential')}
            <span className="ml-2 text-[10px] font-bold px-2 py-0.5 rounded-full
                             bg-gray-200 text-gray-700">
              {t('cf.estimated')}
            </span>
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
            <Stat label={t('cf.gasPerDay')} r={est.biogas_m3_per_day} unit="m³" />
            <Stat label={t('cf.plantSize')}
                  value={`${est.suggested_plant_size_m3} m³`} />
            <Stat label={t('cf.digestateMonth')}
                  r={est.digestate_kg_per_month} unit="kg" />
            <Stat label={t('cf.waterPerDay')}
                  value={`${est.water_needed_litres_per_day} L`} />
          </div>
          <p className="text-sm text-gray-700 mt-2">{est.cooking_note}</p>
          {est.residue_capped && (
            <p className="text-sm text-amber-800 mt-1">{est.residue_cap_note}</p>
          )}
          <p className="text-[11px] text-gray-500 mt-2">{est.caveat}</p>
        </Card>
      )}

      {false && s['3_preparation'] && (
        <Card>
          <h3 className="font-semibold text-field-800">4. {t('cf.preparation')}</h3>
          <ol className="mt-2 space-y-2">
            {s['3_preparation'].map((step: any, i: number) => (
              <li key={i} className="flex gap-3">
                <span className="w-6 h-6 rounded-full bg-field-100 text-field-800
                                 font-bold text-xs flex items-center justify-center
                                 flex-shrink-0">{i + 1}</span>
                <div>
                  <p className="font-semibold text-sm text-field-800">{step.stage}</p>
                  <p className="text-sm text-gray-700">{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {/* ---------- EXISTING PLANT branch ---------- */}
      {/* Shown ONLY when no plant is on record. Once registered, this card is
          gone permanently — the status panel replaces it. Re-showing a
          registration form to someone who has already registered is what made
          the page feel like it had forgotten them. */}
      {mode === 'plant' && plant && !plant.has_plant && (
        <Card>
          <h3 className="font-bold text-field-800">{t('cf.registerPlant')}</h3>
          <p className="text-sm text-gray-600 mt-1">{t('cf.registerHelp')}</p>
          <div className="flex items-end gap-2 mt-3 flex-wrap">
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                {t('cf.plantSize')} (m³)
              </label>
              <input type="number" value={dungOverride}
                     onChange={(e) => setDungOverride(e.target.value)}
                     className="border rounded-lg px-2 py-1.5 text-sm w-24" />
            </div>
            <Button disabled={busy} onClick={async () => {
              setBusy(true)
              try {
                const p = await registerBiogasPlant({
                  size_m3: Number(dungOverride) || null })
                setPlant(p)
                setBiogas((b: any) => ({ ...(b || {}), registered: true }))
              } catch { setErr(t('cf.saveFailed')) } finally { setBusy(false) }
            }}>{busy ? t('cf.saving') : t('cf.saveCattle')}</Button>
          </div>
        </Card>
      )}

      {mode === 'plant' && plant?.has_plant && (
        <>
          {/* Status in WORDS. "pH 6.2, 34°C" tells a farmer nothing they can
              act on; "stop feeding for 2-3 days" does. */}
          <Card>
            <div className={`rounded-2xl border-2 p-4 ${
              plant.status.status === 'HEALTHY' ? 'border-green-400 bg-green-50'
              : plant.status.status === 'PROBLEM' ? 'border-red-400 bg-red-50'
              : plant.status.status === 'NEEDS_ATTENTION'
                ? 'border-amber-400 bg-amber-50' : 'border-gray-300 bg-gray-50'}`}>
              <p className="text-2xl">
                {plant.status.status === 'HEALTHY' ? '🟢'
                  : plant.status.status === 'PROBLEM' ? '🔴'
                  : plant.status.status === 'NEEDS_ATTENTION' ? '🟠' : '⚪'}
              </p>
              <p className="font-bold text-field-800 mt-1">
                {plant.status.headline}
              </p>
              <p className="text-sm text-gray-700 mt-1">{plant.status.action}</p>
            </div>

            {plant.status.issues?.length > 0 && (
              <div className="mt-3 space-y-2">
                {plant.status.issues.map((iss: any, k: number) => (
                  <div key={k} className="rounded-xl border border-gray-200 p-2.5">
                    <p className="font-semibold text-sm text-field-800">
                      {iss.what}
                    </p>
                    <p className="text-sm text-gray-600 mt-0.5">{iss.why}</p>
                    <p className="text-sm text-field-800 font-medium mt-1">
                      → {iss.do}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {/* The slurry coming out of a working digester IS manure. This is
                the bridge between the two branches: the farmer does not have
                to know that "digestate" and "manure" are the same thing. */}
            <div className="mt-3 rounded-xl border-2 border-field-300
                            bg-field-50 p-3">
              <p className="text-[10px] font-bold text-field-700 uppercase">
                {t('cf.alsoMakeManure')}
              </p>
              <p className="text-sm text-gray-700 mt-1">
                {t('cf.slurryIsManure')}
              </p>
              <div className="mt-2">
                <Button onClick={() => choose('manure')}>
                  ♻️ {t('cf.optManure')}
                </Button>
              </div>
            </div>
          </Card>

          {/* Manual daily entry: what a farmer can judge with no instruments. */}
          <Card>
            <h3 className="font-bold text-field-800">{t('cf.todayReading')}</h3>
            {plant.logged_today && (
              <p className="text-sm text-green-700 mt-1">✅ {t('cf.loggedToday')}</p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
              <Picker label={t('cf.qGas')} opts={['good', 'low', 'none']}
                      onPick={(v) => logToday({ gas_level: v })} t={t} />
              <Picker label={t('cf.qFlame')} opts={['strong', 'weak', 'none']}
                      onPick={(v) => logToday({ flame_quality: v })} t={t} />
              <Picker label={t('cf.qSmell')} opts={['normal', 'sour', 'rotten']}
                      onPick={(v) => logToday({ smell: v })} t={t} />
            </div>
            <p className="text-[11px] text-gray-500 mt-2">{t('cf.noSensorNeeded')}</p>
          </Card>

          {plant.logs?.length > 0 && (
            <Card>
              <h3 className="font-bold text-field-800">{t('cf.recentDays')}</h3>
              <div className="flex gap-1 mt-2 flex-wrap">
                {plant.logs.map((l: any) => (
                  <div key={l.logged_on}
                       title={`${l.logged_on}: gas ${l.gas_level || '—'}`}
                       className={`w-8 h-8 rounded-lg flex items-center
                         justify-center text-[10px] font-bold ${
                         l.gas_level === 'good' ? 'bg-green-200 text-green-900'
                         : l.gas_level === 'low' ? 'bg-amber-200 text-amber-900'
                         : l.gas_level === 'none' ? 'bg-red-200 text-red-900'
                         : 'bg-gray-100 text-gray-500'}`}>
                    {l.logged_on?.slice(8)}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}

      {/* ---------- MANURE branch ---------- */}
      {/* Where the manure is coming from, said before anything is calculated.
          A farmer who registered a digester months ago must not be asked to
          register it again here, and must not be shown a composting figure
          that pretends their plant does not exist. */}
      {mode === 'manure' && biogas && (
        <div className={`rounded-xl border-2 px-3 py-2.5 mb-3 ${
          biogas.registered ? 'border-field-300 bg-field-50'
                            : 'border-gray-200 bg-gray-50'}`}>
          <div className="flex items-start gap-2">
            <span className={biogas.registered ? 'text-field-700' : 'text-gray-400'}>
              <CircularIcon name="biogas" size={20} />
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-bold uppercase leading-tight
                            text-gray-500">
                {t('cf.manureSource')}
              </p>
              <p className="text-sm font-semibold text-field-800">
                {biogas.registered ? t('cf.biogasPlusCompost')
                                   : t('cf.compostOnly')}
              </p>
              <p className="text-xs text-gray-600 mt-0.5">{biogas.message}</p>
            </div>
            {!biogas.registered && (
              <button onClick={() => choose('plant')}
                      className="text-xs font-semibold text-field-700 underline
                                 flex-shrink-0">
                {t('cf.registerPlantLink')}
              </button>
            )}
          </div>
        </div>
      )}

      {/*
        STEP 1 — the three questions.

        They used to sit permanently above the results, so the farmer scrolled
        past the same three questions every time they looked at their own
        plan. Now answering them collapses the block to one line: the answers
        are visible, the buttons are gone, and the plan starts immediately
        below. Tapping "Change" is the only way back to the buttons.
      */}
      {mode === 'manure' && (answered && !editingAnswers ? (
        <Card>
          <div className="flex items-center gap-3">
            <span className="w-6 h-6 rounded-full bg-field-100 text-field-800
                             font-bold text-[11px] flex items-center
                             justify-center flex-shrink-0">1</span>
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-bold text-gray-400 uppercase leading-tight">
                {t('cf.yourAnswers')}
              </p>
              <p className="text-sm text-field-800 font-medium">
                {shade ? t('cf.hasShade') : t('cf.noShade')}
                {' · '}{t(`cf.labour.${labour}`)}
                {' · '}{urgent ? t('cf.needSoon') : t('cf.canWait')}
              </p>
            </div>
            <button onClick={() => setEditingAnswers(true)}
                    className="text-xs font-semibold text-field-700 underline
                               flex-shrink-0">
              {t('cf.changeChoice')}
            </button>
          </div>
        </Card>
      ) : (
        <Card>
          <p className="text-[10px] font-bold text-gray-400 uppercase">
            {t('cf.step')} 1
          </p>
          <h3 className="font-bold text-field-800">{t('cf.threeQs')}</h3>
          <p className="text-sm text-gray-600 mt-1">{t('cf.threeQsHelp')}</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
            <Choice label={t('cf.qShade')} value={shade}
                    onPick={setShade}
                    yes={t('cf.yes')} no={t('cf.no')} />
            <div>
              <p className="text-[11px] font-semibold text-gray-500 mb-1">
                {t('cf.qLabour')}
              </p>
              <div className="flex gap-1">
                {['low', 'normal'].map((v) => (
                  <button key={v} onClick={() => setLabour(v)}
                          className={`flex-1 text-xs py-2 rounded-lg border font-semibold
                            ${labour === v ? 'bg-field-700 text-white border-field-700'
                                           : 'bg-white border-gray-300'}`}>
                    {t(`cf.labour.${v}`)}
                  </button>
                ))}
              </div>
            </div>
            <Choice label={t('cf.qUrgent')} value={urgent}
                    onPick={setUrgent}
                    yes={t('cf.yes')} no={t('cf.no')} />
          </div>
          <div className="mt-3">
            <Button onClick={confirmAnswers} disabled={busy}>
              {busy ? t('cf.saving') : t('cf.showMyPlan')}
            </Button>
          </div>
        </Card>
      ))}

      {/*
        ONE block for the whole result.

        This was five stacked cards — method, materials, steps, output, and a
        "use it or sell it" panel — followed by a sixth digestate card that
        quoted a different surplus figure for the same farm. Two contradictory
        numbers on one screen is worse than either of them alone.

        Everything now lives in a single card: the decision and the two
        figures that matter are always visible, and the detail sits behind
        dropdowns for the farmer who wants it.
      */}
      {mode === 'manure' && answered && !editingAnswers && mplan?.method && (
        <Card>
          <p className="text-[10px] font-bold text-gray-400 uppercase">
            {t('cf.step')} 2
          </p>
          <h3 className="font-bold text-field-800">{t('cf.yourCompostPlan')}</h3>

          {/* The method, and why this farm got it. */}
          <p className="text-2xl font-bold text-field-800 mt-2">
            <span className="inline-flex items-center gap-2">
              <CircularIcon name={mplan.method.recommended} size={26} />
              {mplan.method.name}
            </span>
          </p>
          <p className="text-sm text-gray-700 mt-1">{mplan.method.why}</p>
          <p className="text-sm text-gray-600">{mplan.method.product}</p>

          {/* The two headline numbers, always visible. */}
          <div className="grid grid-cols-2 gap-3 mt-4">
            <Box label={t('cf.manureMade')}
                 value={mplan.sources?.total_kg ?? mplan.output?.output_kg?.low}
                 highlight />
            <div className="rounded-xl border-2 border-gray-200 p-3">
              <p className="text-[10px] font-semibold text-gray-500 uppercase">
                {t('cf.readyIn')}
              </p>
              <p className="text-xl font-bold text-field-800">
                {mplan.output?.ready_in_weeks?.low}–
                {mplan.output?.ready_in_weeks?.high}
              </p>
              <p className="text-[10px] text-gray-400">{t('cf.weeks')}</p>
            </div>
          </div>

          {/* Where that total came from. Two sources added into one number
              with no explanation is exactly the sort of unexplained figure
              that makes a farmer distrust the whole page. */}
          {mplan.sources?.from_biogas && (
            <table className="w-full text-sm mt-3">
              <tbody>
                <tr className="border-b border-gray-100">
                  <td className="py-1.5 text-gray-600">{t('cf.fromComposting')}</td>
                  <td className="py-1.5 text-right font-semibold text-field-800">
                    {Number(mplan.sources.compost_kg || 0).toLocaleString()} kg
                  </td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="py-1.5 text-gray-600">{t('cf.fromBiogas')}</td>
                  <td className="py-1.5 text-right font-semibold text-field-800">
                    {Number(mplan.sources.digestate_kg || 0).toLocaleString()} kg
                  </td>
                </tr>
                <tr>
                  <td className="py-1.5 font-bold text-field-800">{t('cf.total')}</td>
                  <td className="py-1.5 text-right font-bold text-field-800">
                    {Number(mplan.sources.total_kg || 0).toLocaleString()} kg
                  </td>
                </tr>
              </tbody>
            </table>
          )}

          <p className="text-[11px] text-gray-500 mt-2">{mplan.output?.loss_note}</p>

          {/* Detail, folded away. */}
          <div className="mt-4 border-t border-gray-100">
            <Fold title={t('cf.whatToMix')}>
              <div className="space-y-1.5">
                {mplan.materials?.materials?.map((m: any, i: number) => (
                  <div key={i} className="flex items-center gap-2">
                    <div className="flex-1 text-sm text-gray-700">{m.material}</div>
                    <div className="w-24 h-2 rounded-full bg-gray-200 overflow-hidden">
                      <div className="h-full bg-field-600"
                           style={{ width: `${m.share_pct}%` }} />
                    </div>
                    <div className="w-20 text-right text-sm font-bold text-field-800">
                      {m.approx_kg} kg
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-sm text-blue-800 mt-3">💧 {mplan.materials?.moisture}</p>
              <p className="text-[11px] text-gray-500 mt-1">{mplan.materials?.cn_note}</p>
            </Fold>

            <Fold title={t('cf.howToDo')}>
              <ol className="space-y-2">
                {mplan.method.steps?.map((st: string, i: number) => (
                  <li key={i} className="flex gap-3">
                    <span className="w-6 h-6 rounded-full bg-field-100 text-field-800
                                     font-bold text-xs flex items-center
                                     justify-center flex-shrink-0">{i + 1}</span>
                    <p className="text-sm text-gray-700">{st}</p>
                  </li>
                ))}
              </ol>
            </Fold>

            <Fold title={t('cf.howToKnowReady')}>
              <ul className="text-sm text-gray-700 list-disc ml-5">
                {mplan.method.ready_signs?.map((r: string, i: number) =>
                  <li key={i}>{r}</li>)}
              </ul>
              <p className="text-[11px] text-gray-500 mt-2">{mplan.output?.time_note}</p>
            </Fold>

            {mplan.method.alternatives?.length > 0 && (
              <Fold title={t('cf.otherMethods')}>
                <div className="space-y-2">
                  {mplan.method.alternatives.map((a: any) => (
                    <div key={a.key} className="rounded-xl border border-gray-200 p-2.5">
                      <p className="font-semibold text-sm text-field-800">{a.name}</p>
                      <p className="text-sm text-gray-600 mt-0.5">
                        {a.note || a.why_not}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="text-[11px] text-gray-500 mt-2">{mplan.method.caveat}</p>
              </Fold>
            )}
          </div>

          {/* ---- Use it or sell it, in the same block ---- */}
          {mplan.farm_use?.produced_kg != null && (
            <div className="mt-4 pt-4 border-t-2 border-field-100">
              <h4 className="font-bold text-field-800">{t('cf.useOrSell')}</h4>

              {/* Leads with the acres this compost can actually cover.
                  A farm need in the hundreds of thousands of kg is arithmetic,
                  not advice — on its own it just tells a farmer with 19 cattle
                  that they have failed before they start. */}
              {/* Coverage as a BAR, not a sentence. "Covers 0.7 of 400 acres"
                  is a fact a farmer has to do arithmetic on; a bar that is
                  visibly almost empty says the same thing instantly, and the
                  percentage gives the exact figure for anyone who wants it. */}
              {mplan.farm_use.acres_covered != null
                && mplan.farm_use.area_acres ? (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-600">{t('cf.farmCovered')}</span>
                    <span className="font-bold text-field-800">
                      {Math.min(100, Math.round(
                        (mplan.farm_use.acres_covered
                          / mplan.farm_use.area_acres) * 100))}%
                      <span className="font-normal text-gray-500">
                        {' '}({mplan.farm_use.acres_covered} / {mplan.farm_use.area_acres} {t('cf.acre')})
                      </span>
                    </span>
                  </div>
                  <div className="h-2.5 rounded-full bg-gray-200 overflow-hidden mt-1">
                    <div className={`h-full ${mplan.farm_use.covers_whole_farm
                                      ? 'bg-field-600' : 'bg-amber-500'}`}
                         style={{ width: `${Math.min(100, Math.max(2,
                           (mplan.farm_use.acres_covered
                             / mplan.farm_use.area_acres) * 100))}%` }} />
                  </div>
                  <p className="text-xs text-gray-600 mt-1.5">
                    {mplan.farm_use.covers_whole_farm
                      ? t('cf.enoughForFarm')
                      : t('cf.useOnWeakest')}
                  </p>
                </div>
              ) : null}

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3">
                <Box label={t('cf.youMake')} value={mplan.farm_use.produced_kg} />
                {mplan.farm_use.rate_kg_per_acre && (
                  <div className="rounded-xl border-2 border-gray-200 p-3">
                    <p className="text-[10px] font-semibold text-gray-500 uppercase">
                      {t('cf.cropNeedsRate')}
                    </p>
                    <p className="text-xl font-bold text-field-800">
                      {Number(mplan.farm_use.rate_kg_per_acre.low).toLocaleString()}–
                      {Number(mplan.farm_use.rate_kg_per_acre.high).toLocaleString()}
                    </p>
                    <p className="text-[10px] text-gray-400">
                      kg / {t('cf.acre')}
                    </p>
                  </div>
                )}
                <Box label={t('cf.balanceToSell')}
                     value={mplan.farm_use.balance_kg} highlight />
              </div>

              {/* How much stays on the farm. Pre-filled with what the crop can
                  actually use, so the common case is one tap. */}
              <div className="flex items-end gap-2 mt-3 flex-wrap">
                <div>
                  <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                    {t('cf.reserveLabel')}
                  </label>
                  <input type="number" min={0} max={mplan.farm_use.produced_kg}
                         value={keep} onChange={(e) => setKeep(e.target.value)}
                         placeholder={String(mplan.farm_use.keep_kg ?? 0)}
                         className="border rounded-lg px-2 py-1.5 text-sm w-32" />
                </div>
                <Button onClick={onSaveKeep} disabled={busy || keep === ''}>
                  {busy ? t('cf.saving') : t('cf.reserveBtn')}
                </Button>
              </div>
              {mplan.farm_use.keep_is_default && (
                <p className="text-[11px] text-gray-500 mt-1">
                  {t('cf.keepDefaultNote')}
                </p>
              )}

              {/* Rendered only when the backend actually returned one. Most
                  crops now get nothing here, which is the point — a warning
                  shown on every crop is a warning nobody reads. */}
              {mplan.farm_use.recommendation?.food_safety_note && (
                <div className="mt-3 rounded-xl border border-amber-300
                                bg-amber-50 p-2.5">
                  <p className="text-sm text-amber-900">
                    ⚠️ {mplan.farm_use.recommendation.food_safety_note}
                  </p>
                </div>
              )}

              {/* The sell hand-off. */}
              {mplan.sell?.can_sell ? (
                <div className="mt-4 rounded-xl border-2 border-field-500
                                bg-field-50 p-3">
                  <p className="text-[10px] font-bold text-field-700 uppercase">
                    {t('cf.sellSurplus')}
                  </p>
                  <p className="text-sm text-gray-700 mt-1">
                    {t('cf.sellIntro')
                      .replace('{qty}',
                        Number(mplan.sell.quantity_kg).toLocaleString())
                      .replace('{product}', mplan.sell.product_label)}
                  </p>
                  {mplan.sell.price && (
                    <p className="text-sm text-field-800 font-semibold mt-1">
                      {t('cf.suggestedPrice')}: ₹{mplan.sell.price.low}–
                      {mplan.sell.price.high} / {mplan.sell.price.unit}
                      {mplan.sell.price.estimated_value ? (
                        <span className="font-normal text-gray-600">
                          {' '}({t('cf.about')} ₹
                          {Number(mplan.sell.price.estimated_value).toLocaleString()})
                        </span>
                      ) : null}
                    </p>
                  )}
                  <p className="text-[11px] text-gray-500 mt-1">
                    {mplan.sell.price?.caveat}
                  </p>
                  <div className="mt-3">
                    <Button onClick={sellBalance}>
                      🛒 {t('cf.sellThis')}
                    </Button>
                  </div>
                  <p className="text-[11px] text-gray-500 mt-2">
                    {t('cf.sellHandoffNote')}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-gray-600 mt-3">
                  {t('cf.nothingToSell')}
                </p>
              )}
            </div>
          )}
        </Card>
      )}
      {/* ---------- Digestate: the BIOGAS branches only ----------

          Digestate is what comes out of a digester. It is not what comes out
          of a compost heap, and rendering it in the manure branch too put two
          different quantities of "your manure" on the same screen — 4,536 kg
          here against 1,700 kg in the composting plan above it. The farmer
          has no way to tell which one is theirs, so the block now appears
          only where it actually applies. */}
      {mode !== 'manure' && mode && dig?.available && (
        <Card>
          <h3 className="font-semibold text-field-800">5. {t('cf.digestate')}</h3>
          <div className="grid grid-cols-3 gap-3 mt-3 text-center">
            <Box label={t('cf.total')} value={dig.total_available_kg} />
            <Box label={t('cf.reserved')} value={dig.reserved_own_farm_kg} />
            <Box label={t('cf.surplus')} value={dig.potential_surplus_kg}
                 highlight />
          </div>
          <div className="flex items-end gap-2 mt-3 flex-wrap">
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                {t('cf.reserveLabel')}
              </label>
              <input type="number" min={0} max={dig.total_available_kg}
                     value={reserve} onChange={(e) => setReserve(e.target.value)}
                     placeholder={String(dig.reserved_own_farm_kg)}
                     className="border rounded-lg px-2 py-1.5 text-sm w-32" />
            </div>
            <Button onClick={onReserve} disabled={busy || !reserve}>
              {t('cf.reserveBtn')}
            </Button>
          </div>
          <p className="text-[11px] text-gray-500 mt-2">{dig.disclaimer}</p>
        </Card>
      )}

      {/* Digestate application rates, so likewise biogas-only: the manure
          branch has its own compost rates, which are several times lower
          because compost is not 93% water. */}
      {mode !== 'manure' && mode && crop?.available && (
        <Card>
          <h3 className="font-semibold text-field-800">
            6. {t('cf.forYourCrop')} — {crop.crop}
          </h3>
          <p className="text-sm mt-1">
            <strong>{crop.rate_kg_per_acre?.low}–{crop.rate_kg_per_acre?.high} kg
            </strong> {t('cf.perAcre')}
          </p>
          <ul className="text-sm text-gray-700 list-disc ml-5 mt-2">
            {crop.why?.map((w: string, i: number) => <li key={i}>{w}</li>)}
          </ul>
          <p className="text-sm text-gray-700 mt-2">{crop.benefit}</p>
          <div className="mt-2">
            <p className="text-[11px] font-bold text-gray-500 uppercase">
              {t('cf.howToApply')}
            </p>
            <ul className="text-sm text-gray-700 list-disc ml-5">
              {crop.how_to_apply?.map((h: string, i: number) => <li key={i}>{h}</li>)}
            </ul>
          </div>
          {crop.food_safety_note && (
            <p className="text-sm text-amber-800 mt-2">⚠️ {crop.food_safety_note}</p>
          )}
          <p className="text-[11px] text-gray-500 mt-2">{crop.caveat}</p>
        </Card>
      )}

      {mode && residue?.routing?.available && (
        <Card>
          <h3 className="font-semibold text-field-800">7. {t('cf.residue')}</h3>
          {residue.estimate?.available && (
            <p className="text-sm text-gray-700">
              {t('cf.residueApprox')} {residue.estimate.residue_kg.low}–
              {residue.estimate.residue_kg.high} kg
            </p>
          )}
          <div className="rounded-xl bg-field-50 border border-field-200 p-3 mt-2">
            <p className="text-[10px] font-bold text-field-700 uppercase">
              {t('cf.bestRoute')}
            </p>
            <p className="font-bold text-field-800">
              {residue.routing.recommended_label}
            </p>
            {residue.routing.why && (
              <p className="text-sm text-gray-700 mt-1">{residue.routing.why}</p>
            )}
          </div>
          {residue.routing.other_options?.length > 0 && (
            <p className="text-sm text-gray-600 mt-2">
              {t('cf.alsoPossible')}{' '}
              {residue.routing.other_options.map((o: any) => o.label).join(', ')}
            </p>
          )}
          <p className="text-sm text-red-700 font-semibold mt-2">
            {residue.routing.never}
          </p>
        </Card>
      )}

      {mode === 'biogas' && s['9_sensors'] && (
        <Card>
          <h3 className="font-semibold text-field-800">8. {t('cf.sensors')}</h3>
          <p className="text-sm text-gray-600">{s['9_sensors'].note}</p>
        </Card>
      )}

      <p className="text-[11px] text-gray-500 mt-3">{plan?.disclaimer}</p>
    </div>
  )
}

/**
 * One collapsible section inside a larger card.
 *
 * The composting result used to arrive as five separate cards, which made a
 * farmer scroll through mixing ratios and a seven-step method before reaching
 * the one thing they came for — how much they get and what it is worth. The
 * decision and the numbers stay visible; everything else folds away here.
 */
function Fold({ title, children }:
              { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-gray-100 last:border-b-0">
      <button onClick={() => setOpen(!open)}
              className="w-full flex items-center justify-between py-3 text-left">
        <span className="text-sm font-semibold text-field-800">{title}</span>
        <span className="text-gray-400 text-xs flex-shrink-0">
          {open ? '▲' : '▼'}
        </span>
      </button>
      {open && <div className="pb-3">{children}</div>}
    </div>
  )
}

function Picker({ label, opts, onPick, t }:
                { label: string; opts: string[]
                  onPick: (v: string) => void; t: (k: string) => string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold text-gray-500 mb-1">{label}</p>
      <div className="flex gap-1">
        {opts.map((o) => (
          <button key={o} onClick={() => onPick(o)}
                  className="flex-1 text-xs py-2 rounded-lg border
                             border-gray-300 bg-white font-semibold
                             hover:border-field-500">
            {t(`cf.opt.${o}`)}
          </button>
        ))}
      </div>
    </div>
  )
}

function Choice({ label, value, onPick, yes, no }:
                { label: string; value: boolean
                  onPick: (v: boolean) => void; yes: string; no: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold text-gray-500 mb-1">{label}</p>
      <div className="flex gap-1">
        {[true, false].map((v) => (
          <button key={String(v)} onClick={() => onPick(v)}
                  className={`flex-1 text-xs py-2 rounded-lg border font-semibold
                    ${value === v ? 'bg-field-700 text-white border-field-700'
                                  : 'bg-white border-gray-300'}`}>
            {v ? yes : no}
          </button>
        ))}
      </div>
    </div>
  )
}

function Stat({ label, r, value, unit }:
              { label: string; r?: any; value?: string; unit?: string }) {
  return (
    <div className="border rounded-xl p-2">
      <p className="text-[10px] font-semibold text-gray-500 uppercase">{label}</p>
      <p className="font-bold text-field-800">
        {value ?? (r ? `${r.low}–${r.high} ${unit || ''}` : '—')}
      </p>
    </div>
  )
}

function Box({ label, value, highlight }:
             { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`rounded-xl border-2 p-3 ${
      highlight ? 'border-field-500 bg-field-50' : 'border-gray-200'}`}>
      <p className="text-[10px] font-semibold text-gray-500 uppercase">{label}</p>
      <p className="text-xl font-bold text-field-800">
        {Number(value || 0).toLocaleString()}
      </p>
      <p className="text-[10px] text-gray-400">kg</p>
    </div>
  )
}

/**
 * The cycle, drawn as an actual closed loop.
 *
 * A left-to-right row of boxes is a PIPELINE, not a cycle — and the whole
 * point of this module is that the last step feeds the first. Laying the
 * nodes around a ring, with the return arrow visible, is the one picture
 * that carries the idea without a paragraph explaining it.
 */
function CycleDiagram({ nodes }: { nodes: any[] }) {
  const { t } = useLanguage()
  if (!nodes.length) return null

  const R = 118
  const CX = 160
  const CY = 145
  const n = nodes.length

  const pos = (i: number) => {
    // Start at the top and go clockwise.
    const a = (i / n) * 2 * Math.PI - Math.PI / 2
    return { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) }
  }

  return (
    <div className="flex flex-col sm:flex-row gap-4 items-center">
      <svg viewBox="0 0 320 300" className="w-full max-w-[340px]">
        <defs>
          <marker id="cf-arrow" markerWidth="7" markerHeight="7"
                  refX="5" refY="3.5" orient="auto">
            <path d="M0 0 L7 3.5 L0 7 z" fill="#86a789" />
          </marker>
        </defs>

        {/* The ring itself, with arrowheads showing the direction of flow */}
        {nodes.map((_, i) => {
          const a1 = (i / n) * 2 * Math.PI - Math.PI / 2
          const a2 = ((i + 1) / n) * 2 * Math.PI - Math.PI / 2
          const pad = 0.22
          const s1 = a1 + pad, s2 = a2 - pad
          return (
            <path key={i}
                  d={`M ${CX + R * Math.cos(s1)} ${CY + R * Math.sin(s1)}
                      A ${R} ${R} 0 0 1
                        ${CX + R * Math.cos(s2)} ${CY + R * Math.sin(s2)}`}
                  fill="none" stroke="#cfe0d0" strokeWidth="2"
                  markerEnd="url(#cf-arrow)" />
          )
        })}

        {nodes.map((node, i) => {
          const { x, y } = pos(i)
          // A node whose value is a NAME rather than a quantity — the crop.
          // It used to fall through to a dash, so a farmer looked at their own
          // farm cycle and saw an empty circle where their crop should be.
          const text = node.is_text
            ? (node.display || node.value || '—')
            : (typeof node.value === 'number'
                ? Number(node.value).toLocaleString() : '—')
          const long = String(text).length > 7
          return (
            <g key={node.node}>
              <circle cx={x} cy={y} r="27" fill="#f4f9f4"
                      stroke="#2f6b3a" strokeWidth="1.8" />
              <text x={x} y={y + 4} textAnchor="middle"
                    fontSize={long ? 8 : 11} fontWeight="700" fill="#2f6b3a">
                {long ? String(text).slice(0, 9) : text}
              </text>
              <text x={x} y={y + 40} textAnchor="middle"
                    fontSize="9.5" fontWeight="600" fill="#4b5563">
                {t(`cf.node.${node.node}`)}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Legend with the real icons and units. Doubles as a KPI strip: it is
          the densest summary of the whole farm cycle on the page, so it gets
          a status dot telling the farmer at a glance which stages are live
          and which are still at zero because something upstream is missing. */}
      <div className="w-full sm:w-auto sm:min-w-[250px] space-y-1.5 text-sm flex-1">
        {nodes.map((node) => {
          const live = node.is_text
            ? !!node.value
            : typeof node.value === 'number' && node.value > 0
          return (
            <div key={node.node}
                 className={`flex items-center gap-2 rounded-lg px-2 py-1.5 border
                   ${live ? 'bg-field-50 border-field-100'
                          : 'bg-gray-50 border-transparent'}`}>
              <span className={live ? 'text-field-700' : 'text-gray-300'}>
                <CircularIcon name={node.node} size={18} />
              </span>
              <span className={live ? 'text-gray-700' : 'text-gray-400'}>
                {t(`cf.node.${node.node}`)}
              </span>
              <span className={`font-bold ml-auto text-right
                ${live ? 'text-field-800' : 'text-gray-400'}`}>
                {node.is_text
                  ? (node.display || node.value || t('cf.notSet'))
                  : (typeof node.value === 'number'
                      ? Number(node.value).toLocaleString() : node.value)}
                {node.is_text
                  ? (node.numeric ? ` · ${node.numeric} ${node.unit}` : '')
                  : (node.unit ? ` ${node.unit}` : '')}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

