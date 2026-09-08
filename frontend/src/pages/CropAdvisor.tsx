import { useEffect, useState } from 'react'
import {
  getCropList, getCropStage, getLifecycle, getSeason,
  recommendAdvisory, getMyCropStage, getSoil, getOnboardingStatus,
  getCropLifecycleFor, getFarmProfile,
} from '../services/api'
import { CropLifecycleTimeline } from '../components/CropLifecycleTimeline'
import { Card, Button, Spinner } from '../components/UI'
import { SpeakButton } from '../components/VoiceInput'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

const VERDICT_STYLE: Record<string, string> = {
  'HIGHLY SUITABLE': 'bg-green-100 text-green-800 border-green-300',
  'SUITABLE': 'bg-lime-100 text-lime-800 border-lime-300',
  'MARGINAL': 'bg-amber-100 text-amber-800 border-amber-300',
  'NOT RECOMMENDED': 'bg-red-100 text-red-700 border-red-300',
}

const CONFIDENCE_STYLE: Record<string, string> = {
  high: 'text-green-700',
  medium: 'text-amber-700',
  low: 'text-red-600',
}

function FactorBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100)
  const colour = value >= 0.8 ? 'bg-green-500' : value >= 0.5 ? 'bg-amber-500' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-20 text-gray-500 capitalize">{label}</span>
      <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${colour}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right text-gray-400">{pct}%</span>
    </div>
  )
}

export default function CropAdvisor() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const [tab, setTab] = useState<'suggest' | 'lifecycle'>('suggest')

  // --- suitability ---
  const [season, setSeason] = useState('')
  const [useMyData, setUseMyData] = useState(true)
  const [form, setForm] = useState({
    ph: '', nitrogen: '', phosphorus: '', potassium: '',
    moisture: '', temperature: '', soil_type: '',
  })
  const [result, setResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // Tracks which fields were auto-filled from the Farm Setup soil test, so
  // the "✓ filled from your farm setup" note only shows for those — and
  // disappears the moment the farmer edits a field themselves.
  const [prefilled, setPrefilled] = useState<Set<string>>(new Set())

  // --- lifecycle ---
  const [crops, setCrops] = useState<any[]>([])
  // Was hardcoded to 'soybean', which meant a farmer growing greengram opened
  // this tab and silently saw soybean with nothing telling them it was not
  // theirs. It now defaults to their actual crop once the profile loads.
  const [lcCrop, setLcCrop] = useState('')
  const [myCrop, setMyCrop] = useState('')
  const [openCrop, setOpenCrop] = useState('')
  const [lcData, setLcData] = useState<any>(null)


  const [lcBusy, setLcBusy] = useState(false)

  useEffect(() => {
    getSeason().then((d) => setSeason(d.season)).catch(() => {})
    getCropList().then(setCrops).catch(() => {})

    // Auto-fill NPK + pH from the soil test saved during Farm Setup, and
    // soil type from the farm profile itself — so a farmer who already did
    // that wizard never has to retype numbers they already gave once.
    // Only fills fields that are still empty; never overwrites something
    // the farmer has already typed here.
    getSoil().then((soil) => {
      if (!soil?.has_data) return
      setForm((f) => {
        const next = { ...f }
        const filled = new Set<string>()
        const maybeFill = (key: 'nitrogen' | 'phosphorus' | 'potassium' | 'ph', v: any) => {
          if (next[key] === '' && v !== undefined && v !== null) {
            next[key] = String(v)
            filled.add(key)
          }
        }
        maybeFill('nitrogen', soil.nitrogen?.value)
        maybeFill('phosphorus', soil.phosphorus?.value)
        maybeFill('potassium', soil.potassium?.value)
        maybeFill('ph', soil.ph?.value)
        if (filled.size) setPrefilled((p) => new Set([...p, ...filled]))
        return next
      })
    }).catch(() => {})

    getOnboardingStatus().then((s) => {
      const soilType = s?.farm?.soil_type
      if (!soilType) return
      setForm((f) => {
        if (f.soil_type !== '') return f
        setPrefilled((p) => new Set([...p, 'soil_type']))
        return { ...f, soil_type: soilType }
      })
    }).catch(() => {})
  }, [])

  const analyze = async () => {
    setBusy(true); setErr(''); setResult(null)
    try {
      const params: Record<string, any> = { use_my_data: useMyData }
      Object.entries(form).forEach(([k, v]) => {
        if (v !== '') params[k] = k === 'soil_type' ? v : Number(v)
      })
      if (season) params.season = season
      const res = await recommendAdvisory({
        state: params.state || '',
        season: params.season || season,
        previous_crop: params.previous_crop || '',
        soil_type: params.soil_type || '',
        irrigation_type: params.irrigation_type || '',
        water_source: params.water_source || '',
        nitrogen: params.nitrogen, phosphorus: params.phosphorus,
        potassium: params.potassium, ph: params.ph, moisture: params.moisture,
        include_market: true,
        use_my_data: useMyData,
      })
      setResult(res)
      publish('Crop Advisor', `Suggest tab: best crop is ${res.best?.display} `
        + `scoring ${res.best?.advisory_suitability_score}/100. `
        + `Other options: ${(res.recommendations || []).map((r: any) =>
            `${r.display} (${r.advisory_suitability_score}/100, ${r.verdict})`).join('; ')}. `
        + `${res.disclaimer || ''}`)
    } catch {
      setErr('Could not get recommendations. Is the backend running?')
    } finally {
      setBusy(false)
    }
  }

  /**
   * Load one crop's lifecycle via /api/farm/crop/{key}/lifecycle.
   *
   * That endpoint decides current-vs-explored server side, so the page cannot
   * accidentally present someone else's crop as the farmer's own — the
   * warning and the stage highlighting both come from the response.
   */
  const loadLifecycle = async (crop: string) => {
    if (!crop) return
    setLcBusy(true); setLcData(null)
    try {
      const data = await getCropLifecycleFor(crop)
      setLcData(data)

      const current = data.stages?.find((st: any) => st.is_current)
      publish('Crop Advisor',
        data.is_current_crop
          ? `Lifecycle tab: the farmer's CURRENT crop is ${data.display}, `
            + `day ${data.days_after_sowing} after sowing`
            + (current ? `, currently in the "${current.stage}" stage. ` : '. ')
            + (current?.tasks?.length ? `Tasks now: ${current.tasks.join('; ')}. ` : '')
            + (current?.risks?.length ? `Watch for: ${current.risks.join('; ')}.` : '')
          : `Lifecycle tab: the farmer is VIEWING ${data.display}, which is NOT `
            + `their current crop. ${data.warning?.message || ''} `
            + `Suitability for their land: ${data.suitability?.verdict || 'unknown'}. `
            + `Do not tell them they are growing ${data.display}.`)
    } catch {
      setErr(`No lifecycle data for ${crop}.`)
    } finally {
      setLcBusy(false)
    }
  }

  // Default the lifecycle tab to the farmer's OWN crop.
  useEffect(() => {
    (async () => {
      try {
        const profile = await getFarmProfile()
        const mine = profile?.current_crop?.crop || ''
        setMyCrop(mine)
        const start = mine || 'soybean'
        setLcCrop(start)
        loadLifecycle(start)
      } catch {
        setLcCrop('soybean')
        loadLifecycle('soybean')
      }
    })()
  }, []) // eslint-disable-line

  const field = (key: keyof typeof form, label: string, placeholder = '') => (
    <div>
      <label className="block text-[11px] font-semibold text-gray-500 mb-1">{label}</label>
      <input
        value={form[key]}
        onChange={(e) => {
          setForm({ ...form, [key]: e.target.value })
          // Once the farmer touches a prefilled field, it's their value now —
          // stop labelling it as auto-filled.
          if (prefilled.has(key)) {
            setPrefilled((p) => { const n = new Set(p); n.delete(key); return n })
          }
        }}
        placeholder={placeholder}
        className={`w-full border rounded-lg px-2.5 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600
          ${prefilled.has(key) ? 'bg-field-50 border-field-200' : ''}`}
      />
      {prefilled.has(key) && (
        <p className="text-[10px] text-field-700 mt-0.5">{t('crop.prefilled')}</p>
      )}
    </div>
  )

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">🌾 {t('crop.title')}</h1>
      <p className="text-sm text-gray-500 mb-4">
        {t('crop.subtitle')}
        {season && <span className="ml-1 font-semibold text-field-700">
          Current season: {season}
        </span>}
      </p>

      <div className="flex gap-2 mb-5">
        {(['suggest', 'lifecycle'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition
              ${tab === t ? 'bg-field-600 text-white shadow' : 'bg-white hover:bg-field-50 border'}`}
          >
            {t === 'suggest' ? 'What should I grow?' : 'Crop lifecycle'}
          </button>
        ))}
      </div>

      {err && <p className="text-sm text-red-600 mb-3">{err}</p>}

      {/* ---------------- SUGGEST ---------------- */}
      {tab === 'suggest' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card>
            <h3 className="font-semibold text-field-800 mb-3">{t('crop.yourconditions')}</h3>

            <label className="flex items-center gap-2 mb-3 text-sm">
              <input
                type="checkbox"
                checked={useMyData}
                onChange={(e) => setUseMyData(e.target.checked)}
              />
              <span>{t('crop.usemydata')}</span>
            </label>
            <p className="text-[11px] text-gray-400 mb-3">
              {t('crop.blanknote')}
            </p>

            <div className="grid grid-cols-2 gap-3">
              {field('ph', t('soil.ph'), '6.8')}
              {field('soil_type', 'Soil type', 'black')}
              {field('nitrogen', t('soil.nitrogen'), '30')}
              {field('phosphorus', t('soil.phosphorus'), '40')}
              {field('potassium', t('soil.potassium'), '70')}
              {field('moisture', 'Moisture %', '60')}
              {field('temperature', 'Temp °C', '28')}
              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">{t('common.season')}</label>
                <select
                  value={season}
                  onChange={(e) => setSeason(e.target.value)}
                  className="w-full border rounded-lg px-2.5 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600"
                >
                  <option value="kharif">{tv('kharif')}</option>
                  <option value="rabi">{tv('rabi')}</option>
                  <option value="zaid">{tv('zaid')}</option>
                </select>
              </div>
            </div>

            <Button onClick={analyze} disabled={busy}>
              {busy ? t('common.analysing') : t('crop.suggest')}
            </Button>
          </Card>

          <Card>
            <h3 className="font-semibold text-field-800 mb-2">{t('common.recommendations')}</h3>
            {busy && <Spinner />}
            {!busy && !result && (
              <p className="text-sm text-gray-400 py-8 text-center">{t('crop.noanalysis')}</p>
            )}

            {result && (
              <div className="space-y-3">
                <div className="text-xs">
                  {t('crop.confidence')}{' '}
                  <span className={`font-bold ${CONFIDENCE_STYLE[result.data_confidence]}`}>
                    {result.data_confidence.toUpperCase()}
                  </span>
                  <span className="text-gray-400">
                    {' '}· based on {result.data_used.length} measured value(s)
                  </span>
                </div>

                {result.provenance && (
                  <div className="text-[11px] bg-gray-50 rounded-lg p-2">
                    <p className="font-semibold text-gray-600 mb-1">
                      {t('adv.provenance')}
                    </p>
                    {Object.entries(result.provenance).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-gray-500 capitalize">{k}</span>
                        <span className={String(v) === 'MISSING'
                          ? 'text-gray-400' : 'text-green-700 font-medium'}>
                          {t('src.' + v)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {result.data_missing?.length > 0 && (
                  <p className="text-[11px] text-amber-700 bg-amber-50 rounded-lg p-2">
                    Not measured: {result.data_missing.join(', ')}. Adding these
                    improves accuracy.
                  </p>
                )}

                {result.recommendations.map((r: any, rank: number) => (
                  <div key={r.crop} className="border rounded-xl p-3">
                    {/* Collapsed by default: rank + name is the whole answer
                        most farmers want. The reasoning is one tap away for
                        anyone who wants to check our working. */}
                    <button
                      onClick={() => setOpenCrop(openCrop === r.crop ? '' : r.crop)}
                      className="w-full flex items-center justify-between gap-2 text-left"
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <span className="text-sm font-bold text-field-700 flex-shrink-0">
                          #{rank + 1}
                        </span>
                        <span className="font-bold text-field-800 truncate">
                          {tv(r.display)}
                        </span>
                        {r.crop === myCrop && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded-full
                                           bg-field-100 text-field-800 font-bold flex-shrink-0">
                            {t('crop.yours')}
                          </span>
                        )}
                      </span>
                      <span className="flex items-center gap-2 flex-shrink-0">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold
                          ${VERDICT_STYLE[r.verdict] || ''}`}>
                          {tv(r.verdict)}
                        </span>
                        <span className="text-gray-400 text-xs">
                          {openCrop === r.crop ? '▲' : '▼'}
                        </span>
                      </span>
                    </button>

                    {openCrop === r.crop && (<>
                    <p className="text-[11px] font-semibold text-field-800 mt-3 mb-1">
                      {t('crop.whyRecommended')}
                    </p>
                    <div className="text-xs text-gray-500 mb-2">
                      {t('adv.score')} {r.advisory_suitability_score}/100 · {r.duration_days} days · {r.water_need} water
                    </div>

                    <div className="space-y-1 mb-2">
                      <FactorBar label={t('adv.soilfit')} value={(r.soil_fit?.score ?? 50) / 100} />
                      <FactorBar label={t('adv.weatherfit')} value={(r.weather_fit?.score ?? 50) / 100} />
                      <FactorBar label={t('adv.water')} value={(r.water_requirement?.score ?? 50) / 100} />
                      <FactorBar label={t('adv.rotationfit')} value={(r.rotation_fit?.score ?? 50) / 100} />
                    </div>

                    {/* Live mandi price, straight from data.gov.in */}
                    <div className="bg-amber-50 rounded-lg p-2 mb-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-amber-800 uppercase">
                          💰 {t('adv.market')}
                        </span>
                        {r.market_information?.status === 'ok' && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-green-100
                                           text-green-800 border border-green-300 font-bold">
                            {t('mandi.live')}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-gray-700 mt-1">
                        {r.market_information?.note}
                      </p>
                    </div>

                    {r.risks?.length > 0 && (
                      <div className="mb-2">
                        <p className="text-[10px] font-semibold text-red-700 uppercase mb-0.5">
                          ⚠️ {t('adv.risks')}
                        </p>
                        <ul className="text-[11px] text-red-700 list-disc ml-4">
                          {r.risks.slice(0, 3).map((x: string, i: number) => <li key={i}>{x}</li>)}
                        </ul>
                      </div>
                    )}

                    {r.reasons?.length > 0 && (
                      <ul className="text-[11px] text-green-700 list-disc ml-4">
                        {r.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}
                      </ul>
                    )}
                    {(r.soil_fit?.limitations?.length || 0) > 0 && (
                      <ul className="text-[11px] text-amber-700 list-disc ml-4 mt-1">
                        {(r.soil_fit?.limitations || []).map((x: string, i: number) => <li key={i}>{x}</li>)}
                      </ul>
                    )}
                    <p className="text-[11px] text-gray-500 mt-2">{r.notes}</p>
                    </>)}
                  </div>
                ))}

                <div className="border-t pt-2 flex items-start justify-between gap-2">
                  <p className="text-[10px] text-gray-400">{result.disclaimer}</p>
                  <SpeakButton
                    text={`Best crop is ${result.best?.display}, scoring ${result.best?.advisory_suitability_score} out of 100.`}
                  />
                </div>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ---------------- LIFECYCLE ---------------- */}
      {tab === 'lifecycle' && (
        <div>
          <Card>
            <h3 className="font-semibold text-field-800 mb-3">{t('crop.wherenow')}</h3>
            {/* Defaults to the crop the farmer is ACTUALLY growing, not a
                hardcoded one. Picking anything else is still allowed — it
                just gets clearly labelled as explored, not current. */}
            <label className="block text-[11px] font-semibold text-gray-500 mb-1">
              {t('common.crop')}
            </label>
            <select
              value={lcCrop}
              onChange={(e) => { setLcCrop(e.target.value); loadLifecycle(e.target.value) }}
              className="w-full max-w-xs border rounded-lg px-2.5 py-2 text-sm
                         outline-none focus:ring-2 focus:ring-field-600"
            >
              {crops.map((c) => (
                <option key={c.key} value={c.key}>
                  {tv(c.display)}{c.key === myCrop ? ` — ${t('crop.yours')}` : ''}
                </option>
              ))}
            </select>
          </Card>

          {lcBusy && <Spinner />}
          {lcData && (
            <div className="mt-4">
              <CropLifecycleTimeline data={lcData} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
