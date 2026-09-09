import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getOnboardingStatus, saveOnboarding, promotePreviousCrop,
         getNextCropsForPrevious, reverseGeocode, getUser } from '../services/api'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'
import { useFarmSetup } from '../components/FarmSetupGuard'
import { VoiceField } from '../components/VoiceInput'
import { Card, Button, Spinner } from '../components/UI'

/**
 * Unified farm/garden profile + setup wizard.
 *
 * This used to be two separate pages — a single-page "My Farm" profile form
 * and a multi-step "Farm Setup" onboarding wizard — that both wrote to the
 * same underlying farm record through two different endpoints, so a change
 * on one page silently didn't show up on the other. They're merged here into
 * one wizard, reachable only at /farm.
 *
 * DESIGN NOTES
 * ------------
 * - Every free-text field is voice-enabled. A farmer who cannot type
 *   comfortably can speak every answer in Tamil, Hindi or English.
 * - Each step SAVES as you go, so a dropped connection or a closed tab does
 *   not lose the answers already given. The backend accepts partial saves.
 * - Nothing is defaulted to a plausible-looking value. An unanswered land size
 *   stays empty rather than becoming "1 acre", because an invented figure
 *   silently corrupts every recommendation downstream.
 * - GPS is offered but never required — manual entry always works.
 * - Step 2 branches on the farmer's registered mode: land/soil/irrigation
 *   questions for "farm" mode, container/sunlight/growing-medium questions
 *   for "balcony" (home garden) mode — the two very different farmer
 *   profiles the old separate pages used to split across.
 * - There is deliberately no "enter your soil test" step. Almost nobody
 *   running this wizard owns an NPK sensor or lab kit, so a required field
 *   for it would either block them forever or invite a guessed number —
 *   and a guessed N/P/K is worse than none, per the no-invented-data rule
 *   above. A real lab or Soil Health Card result can still be logged any
 *   time from the Soil page; it just isn't asked for here. The crop
 *   suitability scorer (see crop_suitability.py) already treats a missing
 *   NPK/pH reading as neutral rather than penalised, and leans on signals
 *   this wizard DOES collect instead: season (30% of the score), the
 *   farmer's own soil-type answer in Step 2 (8%, a reasonable proxy —
 *   black/alluvial soils skew fertile and neutral-to-alkaline, red/sandy
 *   soils skew leaner and more acidic), and live soil-moisture/temperature
 *   sensor readings (30% combined) where a sensor exists. Previous crop
 *   (Step 3) adds a fertility signal too — a heavy feeder like chilli or
 *   cotton is flagged as having likely drawn down nitrogen. Together that
 *   covers most of the score without ever asking for a number the farmer
 *   doesn't have.
 * - After the final step, the app-wide farm-setup gate is refreshed
 *   immediately (see useFarmSetup().refresh below). Without this, the
 *   gate's cached "not set up yet" status stuck around after finishing the
 *   wizard until a hard page reload, which is why farmers kept getting
 *   bounced back to Farm Setup right after completing it.
 * - Step 3 (previous crop) no longer asks for a harvest date. Given a
 *   sowing date, the crop's typical duration tells us when it was due to
 *   be harvested, so we compute it (see previous_crop_check in the
 *   onboarding status response) instead of asking a second date question.
 *   That computation also decides where the wizard goes next:
 *     - harvest date still in the future -> the farmer described their
 *       CURRENT crop under the wrong question (it hasn't come off the
 *       field yet). We correct that automatically (promotePreviousCrop)
 *       and skip straight to the crop lifecycle view — there is no
 *       "current crop" left to ask about, we already have it.
 *     - harvest date in the past -> genuinely a previous crop. Step 4
 *       becomes a ranked "what to plant next" suggestion list (rotation +
 *       agronomy scored against that previous crop) instead of a bare
 *       crop dropdown, with manual pick still available as a fallback.
 *   A crop with no reviewed duration data (previous_crop_check.
 *   needs_manual_harvest_date) falls back to asking the harvest date
 *   directly rather than guessing — same no-invented-data rule as
 *   everywhere else in this file.
 */

const CATEGORIES = ['marginal', 'small', 'medium', 'large']
const SOIL_TYPES = ['black', 'red', 'alluvial', 'sandy', 'clay', 'loam']
const IRRIGATION = ['drip', 'sprinkler', 'flood', 'furrow', 'rainfed']
const WATER_SOURCES = ['borewell', 'canal', 'tank', 'river', 'rainfed']
const SEASONS = ['kharif', 'rabi', 'zaid']
const CROPS = ['soybean', 'wheat', 'chickpea', 'maize', 'cotton',
               'rice', 'tomato', 'onion', 'potato', 'chilli']

// Typical days sowing-to-harvest, mirroring MP_CROPS in
// backend/app/services/crop_suitability.py — kept here too so a picked
// suggestion (which already carries its own duration_days) and a manually
// picked crop can both show an estimated harvest date without a round
// trip. "chilli" is deliberately absent: this app holds no reviewed
// duration data for it (see the NOTE in MP_CROPS), so its harvest date is
// simply not estimated rather than guessed.
const CROP_DURATIONS: Record<string, number> = {
  soybean: 95, wheat: 130, chickpea: 110, maize: 100, cotton: 165,
  rice: 130, tomato: 120, onion: 120, potato: 100,
}

const todayISO = () => new Date().toISOString().slice(0, 10)
const addDaysISO = (iso: string, days: number) => {
  const d = new Date(iso)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

const TOTAL_STEPS = 4

export default function Onboarding() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const { refresh: refreshFarmSetup } = useFarmSetup()
  const nav = useNavigate()
  const user = getUser()
  const isBalcony = user?.mode === 'balcony'

  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<any>(null)
  const [gpsBusy, setGpsBusy] = useState(false)
  const [gpsError, setGpsError] = useState('')
  const [gpsPlace, setGpsPlace] = useState<any>(null)
  // Step 4's "what to plant next" ranking, fetched once the previous crop
  // is confirmed genuinely harvested. Null while unfetched/unavailable —
  // that is also the signal to fall back to plain manual crop selection.
  const [suggestions, setSuggestions] = useState<any>(null)
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const [showOtherCrops, setShowOtherCrops] = useState(false)

  const [form, setForm] = useState<any>({
    name: '', state: user?.state || '', district: user?.district || '', village: '',
    latitude: null, longitude: null,
    land_size_acres: '', farmer_category: 'small', soil_type: '',
    irrigation_type: '', water_source: '',
    area: '', sunlight: '', growing_medium: '', watering_method: '',
    previous_crop: '', previous_season: '',
    previous_variety: '', previous_sowing_date: '', previous_harvest_date: '',
    previous_yield_qtl: '', previous_problems: '',
    crop: '', variety: '', growth_stage: '', sowing_date: '',
    expected_harvest_date: '', crop_area_acres: '',
    area_unit: 'acre', water_availability: '',
    device_id: '',
  })

  useEffect(() => {
    getOnboardingStatus()
      .then((s) => {
        setStatus(s)
        if (s.farm) {
          setForm((f: any) => ({
            ...f,
            ...Object.fromEntries(
              Object.entries(s.farm).filter(([, v]) => v !== null && v !== '')),
          }))
          const f = s.farm
          publish('Farm Setup', `Farm "${f.name || 'unnamed'}" in ${f.village ? f.village + ', ' : ''}`
            + `${f.district || ''}, ${f.state || ''}. `
            + (isBalcony
                ? `${f.area ? `Space: ${f.area}. ` : ''}${f.growing_medium ? `Medium: ${f.growing_medium}. ` : ''}`
                : `${f.land_size_acres ? `${f.land_size_acres} acres, ` : ''}${f.farmer_category || ''} farmer, `
                  + `soil ${f.soil_type || 'not set'}, irrigation ${f.irrigation_type || 'not set'}. `)
            + `Current crop: ${f.crop || 'none set'}${f.variety ? ` (${f.variety})` : ''}`
            + (f.sowing_date ? `, sown ${f.sowing_date}` : '') + '.')
        } else {
          publish('Farm Setup', 'No farm profile saved yet — this is a new setup.')
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }))

  /** Tapping a suggestion (or a manual crop pill) picks the current crop
   * and, if the farmer hasn't already typed a sowing date, assumes sowing
   * starts today — the natural default for "what am I planting now". */
  const selectCurrentCrop = (cropKey: string) => {
    setForm((f: any) => ({
      ...f,
      crop: cropKey,
      sowing_date: f.sowing_date || todayISO(),
    }))
  }

  /** Duration for the estimated-harvest line: prefer the figure the ranked
   * suggestion already carries (it came straight from the backend's
   * MP_CROPS), falling back to the local mirror for a manually-picked crop
   * that never appeared in the suggestion list. */
  const durationFor = (cropKey: string): number | null => {
    const fromSuggestion = suggestions?.recommendations
      ?.find((r: any) => r.crop === cropKey)?.duration_days
    return fromSuggestion ?? CROP_DURATIONS[cropKey] ?? null
  }

  /** Only send fields the farmer actually filled in — never blanks. */
  const payload = () => {
    const out: any = {}
    Object.entries(form).forEach(([k, v]) => {
      if (v === '' || v === null || v === undefined) return
      if (['land_size_acres', 'previous_yield_qtl', 'crop_area_acres'].includes(k)) {
        const n = Number(v)
        if (!Number.isNaN(n)) out[k] = n
      } else {
        out[k] = v
      }
    })
    return out
  }

  // Step 3: keep previous_crop_check current as the farmer types, so the
  // "estimated harvest" line below updates live instead of only after
  // clicking Next. Debounced and silent — it's the same background save
  // the wizard already does on every step, just not tied to a button.
  useEffect(() => {
    if (step !== 3) return
    if (!form.previous_crop || form.previous_crop === 'none') return
    if (!form.previous_sowing_date) return
    const timer = setTimeout(() => {
      saveOnboarding(payload()).then((s) => {
        setStatus(s)
        refreshFarmSetup()
      }).catch(() => {})
    }, 600)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, form.previous_crop, form.previous_sowing_date])

  // Step 4: once it's established the previous crop is genuinely off the
  // field, fetch what suits the land next. Re-fetches each time the
  // farmer arrives at step 4, so going back and changing the previous
  // crop produces a fresh ranking rather than a stale one.
  useEffect(() => {
    if (step !== 4) return
    if (!form.previous_crop || form.previous_crop === 'none') { setSuggestions(null); return }
    setSuggestionsLoading(true)
    setShowOtherCrops(false)
    getNextCropsForPrevious(5)
      .then(setSuggestions)
      .catch(() => setSuggestions(null))
      .finally(() => setSuggestionsLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  const save = async (advance = true) => {
    setSaving(true)
    try {
      const s = await saveOnboarding(payload())
      setStatus(s)
      // The app-wide farm-setup gate (FarmSetupProvider) fetched its status
      // once at app load and never again, so as soon as state/district are
      // saved it is stale. Refresh it on every save — not just the final
      // one — so leaving this page early (including the "skip to dashboard"
      // link below) never bounces the farmer back to a setup screen they
      // already got past.
      refreshFarmSetup()

      if (!advance) return

      // Step 3 is the one step whose "Next" does not simply move to the
      // next step — see the design note at the top of this file. Every
      // other step keeps the plain advance-or-finish behaviour below.
      if (step === 3) {
        const check = s.previous_crop_check
        if (check?.still_growing) {
          const promoted = await promotePreviousCrop()
          setStatus(promoted)
          refreshFarmSetup()
          // There is no "current crop" left to ask about — we already
          // have it — so land directly on its lifecycle instead of a
          // step 4 that would just be asking the same question twice.
          nav('/crop-advisor?tab=lifecycle')
          return
        }
        setStep(4)
        return
      }

      if (step < TOTAL_STEPS) {
        setStep(step + 1)
      } else {
        // Whatever was picked in Step 4 — a ranked suggestion or a manual
        // pick — is now the farm's current crop. The dashboard, crop
        // advisor and lifecycle view all read it fresh from the farm
        // profile on their own next load, so landing on the dashboard is
        // enough to show it reflected everywhere.
        nav('/dashboard')
      }
    } catch {
      /* keep the user's answers on screen if the save fails */
    } finally {
      setSaving(false)
    }
  }

  const useGps = () => {
    if (!navigator.geolocation) {
      setGpsError(t('ob.gpserror'))
      return
    }
    setGpsBusy(true); setGpsError('')
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords
        set('latitude', latitude)
        set('longitude', longitude)

        // Coordinates alone are useless to a farmer. Resolve them to a state
        // and district and fill the fields in, which is what the button
        // appeared to promise but previously never did.
        try {
          const place = await reverseGeocode(latitude, longitude)
          if (place.status === 'ok') {
            setForm((f: any) => ({
              ...f,
              latitude, longitude,
              state: place.state || f.state,
              district: place.district || f.district,
              village: place.village || f.village,
            }))
            setGpsPlace(place)
          } else {
            setGpsError(place.message || t('ob.gpserror'))
          }
        } catch {
          setGpsError(t('ob.gpserror'))
        } finally {
          setGpsBusy(false)
        }
      },
      (err) => {
        setGpsError(err.code === err.PERMISSION_DENIED
          ? t('ob.gpsdenied') : t('ob.gpserror'))
        setGpsBusy(false)
      },
      { timeout: 15000, enableHighAccuracy: true, maximumAge: 0 },
    )
  }

  if (loading) return <Spinner />

  const pill = (key: string, value: string, options: string[]) => (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          onClick={() => set(key, o)}
          className={`px-3 py-2 rounded-xl text-sm border transition
            ${value === o ? 'bg-field-600 text-white border-field-600 shadow'
                          : 'bg-white hover:bg-field-50 border-gray-200'}`}
        >
          {tv(o)}
        </button>
      ))}
    </div>
  )

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">
        {isBalcony ? '🪴' : '🌾'} {t('ob.title')}
      </h1>
      <p className="text-sm text-gray-500 mb-4">{t('ob.subtitle')}</p>

      {/* progress */}
      <div className="flex items-center gap-2 mb-5">
        {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map((n) => (
          <div key={n} className={`h-1.5 flex-1 rounded-full transition
            ${n <= step ? 'bg-field-600' : 'bg-gray-200'}`} />
        ))}
        <span className="text-xs text-gray-500 ml-2 whitespace-nowrap">
          {t('ob.step')} {step} {t('ob.of')} {TOTAL_STEPS}
        </span>
      </div>

      <Card>
        {/* ---------------- STEP 1: LOCATION ---------------- */}
        {step === 1 && (
          <div className="space-y-4">
            <h3 className="font-semibold text-field-800">{t('ob.s1.title')}</h3>

            <button
              type="button"
              onClick={useGps}
              disabled={gpsBusy}
              className="w-full border-2 border-dashed border-field-300 rounded-xl py-3
                         text-sm text-field-700 hover:bg-field-50 disabled:opacity-50"
            >
              📍 {gpsBusy ? t('ob.s1.gpsbusy') : t('ob.s1.gps')}
            </button>

            {gpsPlace && (
              <div className="bg-green-50 border border-green-200 rounded-xl p-2.5">
                <p className="text-sm font-semibold text-green-800">
                  ✓ {gpsPlace.district}, {gpsPlace.state}
                </p>
                <p className="text-[11px] text-green-700 mt-0.5">
                  {t('ob.gpsfilled')}
                </p>
                <p className="text-[10px] text-gray-500 mt-1">
                  {Number(form.latitude).toFixed(4)}, {Number(form.longitude).toFixed(4)}
                  {gpsPlace.distance_km !== undefined &&
                    ` · ~${gpsPlace.distance_km} km ${t('ob.gpsfrom')}`}
                </p>
              </div>
            )}
            {gpsError && <p className="text-xs text-amber-700">{gpsError}</p>}

            <p className="text-xs text-gray-400">{t('ob.s1.manual')}</p>
            <VoiceField label={t('common.state')} value={form.state}
                        onChange={(v) => set('state', v)} placeholder="Madhya Pradesh" />
            <VoiceField label={t('common.district')} value={form.district}
                        onChange={(v) => set('district', v)} placeholder="Indore" />
            <VoiceField label={t('ob.village')} value={form.village}
                        onChange={(v) => set('village', v)} />
            <VoiceField label={t('ob.s1.name')} value={form.name}
                        onChange={(v) => set('name', v)}
                        placeholder={isBalcony ? 'Terrace garden' : 'Green Valley Farm'} />
          </div>
        )}

        {/* ---------------- STEP 2: LAND (farm) or GARDEN (balcony) ---------------- */}
        {step === 2 && !isBalcony && (
          <div className="space-y-4">
            <h3 className="font-semibold text-field-800">{t('ob.s2.title')}</h3>

            <VoiceField label={t('ob.s2.acres')} value={String(form.land_size_acres)}
                        onChange={(v) => set('land_size_acres', v.replace(/[^\d.]/g, ''))}
                        placeholder="2.5" />

            {/* Stored alongside the number so the farmer is always shown back
                the unit they typed, rather than a silent conversion. */}
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s2.areaunit')}
              </label>
              {pill('area_unit', form.area_unit, ['acre', 'hectare'])}
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s2.wateravail')}
              </label>
              {pill('water_availability', form.water_availability,
                    ['abundant', 'adequate', 'limited', 'scarce'])}
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s2.category')}
              </label>
              {pill('farmer_category', form.farmer_category, CATEGORIES)}
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s2.soiltype')}
              </label>
              {pill('soil_type', form.soil_type, SOIL_TYPES)}
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s2.irrigation')}
              </label>
              {pill('irrigation_type', form.irrigation_type, IRRIGATION)}
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s2.water')}
              </label>
              {pill('water_source', form.water_source, WATER_SOURCES)}
            </div>
            <VoiceField label={t('ob.s2.device')} value={form.device_id}
                        onChange={(v) => set('device_id', v)} placeholder="ESP32-001" />
          </div>
        )}

        {step === 2 && isBalcony && (
          <div className="space-y-4">
            <h3 className="font-semibold text-field-800">{t('ob.s2.title.balcony')}</h3>

            <VoiceField label={t('ob.s2.container')} value={form.area}
                        onChange={(v) => set('area', v)} placeholder="12 inch pot" />
            <VoiceField label={t('ob.s2.sunlight')} value={form.sunlight}
                        onChange={(v) => set('sunlight', v.replace(/[^\d.]/g, ''))}
                        placeholder="6" />
            <VoiceField label={t('ob.s2.medium')} value={form.growing_medium}
                        onChange={(v) => set('growing_medium', v)} placeholder="Potting mix" />
            <VoiceField label={t('ob.s2.watering')} value={form.watering_method}
                        onChange={(v) => set('watering_method', v)} placeholder="Hand watering" />
            <VoiceField label={t('ob.s2.device')} value={form.device_id}
                        onChange={(v) => set('device_id', v)} placeholder="ESP32-001" />
          </div>
        )}

        {/* ---------------- STEP 3: PREVIOUS CROP ---------------- */}
        {step === 3 && (
          <div className="space-y-4">
            <h3 className="font-semibold text-field-800">{t('ob.s3.title')}</h3>
            <p className="text-xs text-gray-500 bg-field-50 rounded-lg p-2">
              💡 {t('ob.s3.why')}
            </p>

            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s3.prevcrop')}
              </label>
              {pill('previous_crop', form.previous_crop, [...CROPS, 'none'])}
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s3.prevseason')}
              </label>
              {pill('previous_season', form.previous_season, SEASONS)}
            </div>

            {/* Shown only once a previous crop is chosen — asking a farmer
                with no history for it is just noise. */}
            {form.previous_crop && form.previous_crop !== 'none' && (() => {
              const check = status?.previous_crop_check
              // Ignore a check left over from a crop the farmer has since
              // changed away from — the debounce effect above will refresh
              // it shortly, but the display must not show stale numbers
              // for the wrong crop in the meantime.
              const fresh = check && check.crop === form.previous_crop.trim().toLowerCase()
              const knowsHarvest = fresh && !!check.computed_harvest_date
              const needsManual = fresh && check.needs_manual_harvest_date
                && !!form.previous_sowing_date

              return (
                <>
                  <VoiceField label={t('ob.s3.prevvariety')}
                              value={form.previous_variety}
                              onChange={(v) => set('previous_variety', v)} />

                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">
                      {t('ob.s3.prevsowing')}
                    </label>
                    <input type="date" value={form.previous_sowing_date}
                           onChange={(e) => set('previous_sowing_date', e.target.value)}
                           className="w-full border rounded-xl px-3 py-2.5 text-sm
                                      outline-none focus:ring-2 focus:ring-field-600" />
                  </div>

                  {/* No manual "harvest date" question in the normal case —
                      it's computed from the sowing date above plus this
                      crop's typical duration. See the design note at the
                      top of this file. */}
                  {knowsHarvest && (
                    <div className={`rounded-xl border p-2.5 text-sm ${
                      check.still_growing
                        ? 'border-amber-300 bg-amber-50 text-amber-900'
                        : 'border-field-200 bg-field-50 text-field-800'}`}>
                      <p className="font-semibold">
                        {(check.still_growing ? '🌱 ' : '✓ ')
                          + `Estimated harvest: ${check.computed_harvest_date} `
                          + `(based on the typical ${check.duration_days}-day `
                          + `${check.display} cycle)`}
                      </p>
                      <p className="text-xs mt-1 opacity-90">
                        {check.still_growing
                          ? "That's still ahead of today, so this crop is "
                            + "probably still in the ground. We'll keep it "
                            + 'as your current crop instead of asking again.'
                          : "That's already behind us, so we'll ask what "
                            + "you're planting next instead of a harvest date."}
                      </p>
                    </div>
                  )}

                  {/* Fallback: only reached when we hold no duration data
                      for this crop (see CROP_DURATIONS / MP_CROPS) and so
                      genuinely cannot compute anything — asking directly
                      beats guessing. */}
                  {needsManual && (
                    <div>
                      <label className="block text-xs font-semibold text-gray-600 mb-1">
                        {t('ob.s3.prevharvest')}
                      </label>
                      <input type="date" value={form.previous_harvest_date}
                             onChange={(e) => set('previous_harvest_date', e.target.value)}
                             className="w-full border rounded-xl px-3 py-2.5 text-sm
                                        outline-none focus:ring-2 focus:ring-field-600" />
                      <p className="text-[11px] text-gray-500 mt-1">
                        We don't have typical-duration data for {check.display} yet,
                        so please let us know when it was (or will be) harvested.
                      </p>
                    </div>
                  )}

                  {/* Yield and problems only make sense for a crop that has
                      actually been harvested — pointless (and a little
                      strange) to ask about a crop we've just worked out is
                      still standing in the field. */}
                  {!(knowsHarvest && check.still_growing) && (
                    <>
                      <VoiceField label={t('ob.s3.prevyield')}
                                  value={String(form.previous_yield_qtl)}
                                  onChange={(v) => set('previous_yield_qtl',
                                                       v.replace(/[^\d.]/g, ''))} />
                      {/* Last season's outbreak is the best predictor of
                          this season's, so it feeds the pest advice later. */}
                      <VoiceField label={t('ob.s3.prevproblems')}
                                  value={form.previous_problems}
                                  onChange={(v) => set('previous_problems', v)} />
                    </>
                  )}
                </>
              )
            })()}
          </div>
        )}

        {/* ---------------- STEP 4: CURRENT / NEXT CROP ---------------- */}
        {step === 4 && (
          <div className="space-y-4">
            <h3 className="font-semibold text-field-800">
              {suggestions?.available ? 'What are you planting now?' : t('ob.s4.title')}
            </h3>
            <p className="text-xs text-gray-500 bg-field-50 rounded-lg p-2">
              💡 {suggestions?.available ? suggestions.headline : t('ob.s4.why')}
            </p>

            {suggestionsLoading && (
              <div className="py-4"><Spinner /></div>
            )}

            {!suggestionsLoading && suggestions?.available && (
              <div className="space-y-2">
                {suggestions.recommendations.map((r: any, i: number) => (
                  <button key={r.crop} type="button"
                          onClick={() => selectCurrentCrop(r.crop)}
                          className={`w-full text-left border rounded-xl p-2.5 transition
                            ${form.crop === r.crop
                              ? 'border-field-600 bg-field-50 shadow-sm'
                              : 'border-gray-200 hover:border-field-300 bg-white'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-field-800 text-sm">
                        #{i + 1} {r.display}
                      </span>
                      {/* Same score-bar + verdict pattern as the "Recommended
                          next crops" panel on the dashboard, so a ranking
                          reads the same way wherever it appears. */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {typeof r.score === 'number' && (
                          <div className="w-16 h-2 rounded-full bg-gray-200 overflow-hidden">
                            <div className="h-full bg-field-600"
                                 style={{ width: `${Math.max(4, Math.min(100,
                                   r.score <= 1 ? r.score * 100 : r.score))}%` }} />
                          </div>
                        )}
                        <span className="text-[10px] text-gray-500">{r.verdict}</span>
                      </div>
                    </div>
                    {r.why?.length > 0 && (
                      <ul className="text-xs text-gray-600 list-disc ml-4 mt-1">
                        {r.why.slice(0, 2).map((w: string, k: number) => <li key={k}>{w}</li>)}
                      </ul>
                    )}
                  </button>
                ))}

                {!showOtherCrops ? (
                  <button type="button" onClick={() => setShowOtherCrops(true)}
                          className="text-xs text-field-700 font-semibold underline">
                    Choose a different crop instead
                  </button>
                ) : (
                  <div className="pt-1">
                    <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                      {t('ob.s4.crop')}
                    </label>
                    {pill('crop', form.crop, CROPS)}
                  </div>
                )}
              </div>
            )}

            {!suggestionsLoading && !suggestions?.available && (
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                  {t('ob.s4.crop')}
                </label>
                {pill('crop', form.crop, CROPS)}
              </div>
            )}

            <VoiceField label={t('ob.s4.variety')} value={form.variety}
                        onChange={(v) => set('variety', v)} />

            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">
                {t('ob.s4.sowing')}
              </label>
              <input type="date" value={form.sowing_date}
                     onChange={(e) => set('sowing_date', e.target.value)}
                     className="w-full border rounded-xl px-3 py-2.5 text-sm
                                outline-none focus:ring-2 focus:ring-field-600" />
            </div>

            {/* Separate from total holding. A farmer with 4 acres may have
                sown 1.5, and fertiliser computed on 4 would be far too much. */}
            <VoiceField label={t('ob.s4.croparea')}
                        value={String(form.crop_area_acres)}
                        onChange={(v) => set('crop_area_acres',
                                             v.replace(/[^\d.]/g, ''))} />

            {/* No manual "expected harvest date" question here either, for
                the same reason as Step 3: it's computed from the sowing
                date plus this crop's typical duration rather than asked
                for and stored as a second, possibly-conflicting date. */}
            {form.crop && form.sowing_date && (() => {
              const duration = durationFor(form.crop)
              if (duration == null) return null
              return (
                <div className="rounded-xl border border-field-200 bg-field-50 p-2.5 text-sm text-field-800">
                  <p className="font-semibold">
                    {`🌾 Estimated harvest: ${addDaysISO(form.sowing_date, duration)} `
                      + `(based on the typical ${duration}-day cycle)`}
                  </p>
                </div>
              )
            })()}

            {/* No "enter your soil test" step: see the design note at the
                top of this file for why NPK/pH is deliberately never asked
                for here. A real lab or Soil Health Card result can still be
                logged later from the Soil page — this wizard just never
                blocks on a number the farmer doesn't have. */}
            {status && (
              <div className="border-t pt-3 text-xs">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-gray-500">{t('ob.complete')}</span>
                  <span className="font-bold text-field-700">
                    {status.completeness}%
                  </span>
                </div>
                <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-field-600"
                       style={{ width: `${status.completeness}%` }} />
                </div>
                {status.missing?.length > 0 && (
                  <p className="text-[11px] text-gray-400 mt-2">
                    {t('ob.missing')}: {status.missing.join(', ')}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* ---------------- NAV ---------------- */}
        <div className="flex items-center gap-2 mt-6 pt-4 border-t">
          {step > 1 && (
            <button type="button" onClick={() => setStep(step - 1)}
                    className="px-4 py-2 rounded-xl text-sm border hover:bg-gray-50">
              {t('ob.back')}
            </button>
          )}
          <div className="flex-1" />
          <button type="button" onClick={() => save(false)} disabled={saving}
                  className="px-4 py-2 rounded-xl text-sm text-gray-500 hover:bg-gray-50">
            {saving ? t('ob.saving') : t('ob.saved')}
          </button>
          <Button onClick={() => save(true)} disabled={saving}>
            {step === TOTAL_STEPS ? t('ob.finish') : t('ob.next')}
          </Button>
        </div>
      </Card>

      <p className="text-[11px] text-gray-400 mt-3 text-center">
        {t('ob.skip')} — <button onClick={() => nav('/dashboard')}
          className="underline">{t('nav.dashboard')}</button>
      </p>
    </div>
  )
}
