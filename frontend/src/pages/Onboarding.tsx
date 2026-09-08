import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getOnboardingStatus, saveOnboarding, reverseGeocode, getUser } from '../services/api'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'
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
 * - The NPK values entered in Step 5 are also what pre-fills the Crop
 *   Advisor's soil fields, so a farmer who has done this wizard never has to
 *   retype their soil test there.
 */

const CATEGORIES = ['marginal', 'small', 'medium', 'large']
const SOIL_TYPES = ['black', 'red', 'alluvial', 'sandy', 'clay', 'loam']
const IRRIGATION = ['drip', 'sprinkler', 'flood', 'furrow', 'rainfed']
const WATER_SOURCES = ['borewell', 'canal', 'tank', 'river', 'rainfed']
const SEASONS = ['kharif', 'rabi', 'zaid']
const CROPS = ['soybean', 'wheat', 'chickpea', 'maize', 'cotton',
               'rice', 'tomato', 'onion', 'potato', 'chilli']

const TOTAL_STEPS = 5

export default function Onboarding() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
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
    nitrogen: '', phosphorus: '', potassium: '', ph: '',
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

  /** Only send fields the farmer actually filled in — never blanks. */
  const payload = () => {
    const out: any = {}
    Object.entries(form).forEach(([k, v]) => {
      if (v === '' || v === null || v === undefined) return
      if (['land_size_acres', 'nitrogen', 'phosphorus', 'potassium', 'ph',
           'previous_yield_qtl', 'crop_area_acres'].includes(k)) {
        const n = Number(v)
        if (!Number.isNaN(n)) out[k] = n
      } else {
        out[k] = v
      }
    })
    return out
  }

  const save = async (advance = true) => {
    setSaving(true)
    try {
      const s = await saveOnboarding(payload())
      setStatus(s)
      if (advance && step < TOTAL_STEPS) setStep(step + 1)
      else if (advance) nav('/crop-advisor')
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
                with no history for its harvest date is just noise. */}
            {form.previous_crop && form.previous_crop !== 'none' && (
              <>
                <VoiceField label={t('ob.s3.prevvariety')}
                            value={form.previous_variety}
                            onChange={(v) => set('previous_variety', v)} />
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">
                      {t('ob.s3.prevsowing')}
                    </label>
                    <input type="date" value={form.previous_sowing_date}
                           onChange={(e) => set('previous_sowing_date', e.target.value)}
                           className="w-full border rounded-xl px-3 py-2.5 text-sm
                                      outline-none focus:ring-2 focus:ring-field-600" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">
                      {t('ob.s3.prevharvest')}
                    </label>
                    <input type="date" value={form.previous_harvest_date}
                           onChange={(e) => set('previous_harvest_date', e.target.value)}
                           className="w-full border rounded-xl px-3 py-2.5 text-sm
                                      outline-none focus:ring-2 focus:ring-field-600" />
                  </div>
                </div>
                <VoiceField label={t('ob.s3.prevyield')}
                            value={String(form.previous_yield_qtl)}
                            onChange={(v) => set('previous_yield_qtl',
                                                 v.replace(/[^\d.]/g, ''))} />
                {/* Last season's outbreak is the best predictor of this
                    season's, so it feeds the pest advice later. */}
                <VoiceField label={t('ob.s3.prevproblems')}
                            value={form.previous_problems}
                            onChange={(v) => set('previous_problems', v)} />
              </>
            )}
          </div>
        )}

        {/* ---------------- STEP 4: CURRENT CROP ---------------- */}
        {step === 4 && (
          <div className="space-y-4">
            <h3 className="font-semibold text-field-800">{t('ob.s4.title')}</h3>
            <p className="text-xs text-gray-500 bg-field-50 rounded-lg p-2">
              💡 {t('ob.s4.why')}
            </p>

            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5">
                {t('ob.s4.crop')}
              </label>
              {pill('crop', form.crop, CROPS)}
            </div>

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

            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">
                {t('ob.s4.harvest')}
              </label>
              <input type="date" value={form.expected_harvest_date}
                     onChange={(e) => set('expected_harvest_date', e.target.value)}
                     className="w-full border rounded-xl px-3 py-2.5 text-sm
                                outline-none focus:ring-2 focus:ring-field-600" />
              <p className="text-[11px] text-gray-500 mt-1">
                {t('ob.s4.harvesthint')}
              </p>
            </div>
          </div>
        )}

        {/* ---------------- STEP 5: SOIL TEST ---------------- */}
        {step === 5 && (
          <div className="space-y-4">
            <h3 className="font-semibold text-field-800">{t('ob.s5.title')}</h3>
            <p className="text-xs text-gray-500">{t('ob.s5.optional')}</p>

            <div className="grid grid-cols-2 gap-3">
              <VoiceField label={t('soil.nitrogenN')} value={String(form.nitrogen)}
                          onChange={(v) => set('nitrogen', v.replace(/[^\d.]/g, ''))}
                          placeholder="38" />
              <VoiceField label={t('soil.phosphorusP')} value={String(form.phosphorus)}
                          onChange={(v) => set('phosphorus', v.replace(/[^\d.]/g, ''))}
                          placeholder="22" />
              <VoiceField label={t('soil.potassiumK')} value={String(form.potassium)}
                          onChange={(v) => set('potassium', v.replace(/[^\d.]/g, ''))}
                          placeholder="145" />
              <VoiceField label={t('soil.ph')} value={String(form.ph)}
                          onChange={(v) => set('ph', v.replace(/[^\d.]/g, ''))}
                          placeholder="6.2" />
            </div>

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
