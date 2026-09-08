import { useEffect, useState } from 'react'
import {
  getMachineTypes, getMachineTypeDetail,
  getMachineryCatalog, getMachineryGuide, getMachineryStates,
  searchMachinery, machineryNearby, revealMachineryContact,
  createMachineryListing, getMyMachineryListings,
  deleteMachineryListing, setMachineryAvailability,
} from '../services/api'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'
import { VoiceField } from '../components/VoiceInput'
import { MachineryImage } from '../components/MachineryImage'
import { Card, Button, Spinner } from '../components/UI'

type Tab = 'rent' | 'give' | 'guide'

const RADII = [25, 50, 100, 250, 500]

export default function Machinery() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const [tab, setTab] = useState<Tab>('rent')

  // shared
  const [catalog, setCatalog] = useState<any>(null)
  const [states, setStates] = useState<string[]>([])

  // ---- browse ----
  const [items, setItems] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const [filters, setFilters] = useState({
    machine_key: '', state: '', district: '', category: '', max_rate: '', sort: 'distance',
  })
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null)
  const [place, setPlace] = useState<any>(null)
  const [radius, setRadius] = useState(100)
  const [gpsBusy, setGpsBusy] = useState(false)
  const [gpsError, setGpsError] = useState('')
  const [contact, setContact] = useState<any>(null)

  // ---- give for rent ----
  const [form, setForm] = useState<any>({
    machine_key: 'tractor', title: '', brand: '', model_year: '',
    description: '', condition: 'good', daily_rate: '', hourly_rate: '',
    fuel_included: false, operator_included: false, min_days: '1',
    owner_name: '', contact_phone: '', state: '', district: '', village: '',
  })
  const [photo, setPhoto] = useState<File | null>(null)

  // TYPE-FIRST BROWSING
  // The grid used to list individual offers, each with a price and a
  // "Get contact number" button. That showed one stranger's commercial terms
  // to a farmer who had not yet decided what KIND of machine they needed.
  // Now: pick a machine type, then compare offers for it.
  const [types, setTypes] = useState<any[]>([])
  const [typesBusy, setTypesBusy] = useState(false)
  const [detail, setDetail] = useState<any>(null)
  const [detailBusy, setDetailBusy] = useState(false)
  const [gallery, setGallery] = useState(0)

  /** Reveal an owner's phone number. Audited server-side, hence a POST. */
  const revealContact = async (id: number) => {
    try {
      const res = await revealMachineryContact(id)
      setContact(res)
    } catch { /* the modal simply does not open */ }
  }

  const loadTypes = async () => {
    setTypesBusy(true)
    try {
      const res = await getMachineTypes({ state: filters.state || '',
                                          district: filters.district || '' })
      setTypes(res.types || [])
    } catch { setTypes([]) } finally { setTypesBusy(false) }
  }

  const openType = async (key: string) => {
    setDetailBusy(true); setGallery(0)
    try {
      const res = await getMachineTypeDetail(key, {
        state: filters.state || '', district: filters.district || '',
        max_rate: filters.max_rate || undefined,
        ...(coords ? { lat: coords.lat, lon: coords.lon, sort: 'distance' } : {}),
      })
      setDetail(res)
    } catch { setDetail(null) } finally { setDetailBusy(false) }
  }

  useEffect(() => { if (tab === 'rent' && !detail) loadTypes() },
           [tab, filters.state, filters.district])
  const [preview, setPreview] = useState('')
  const [errors, setErrors] = useState<string[]>([])
  const [posted, setPosted] = useState(false)
  const [mine, setMine] = useState<any[]>([])

  // ---- guide ----
  const [guide, setGuide] = useState<any>(null)

  useEffect(() => {
    getMachineryCatalog().then(setCatalog).catch(() => {})
    getMachineryStates().then((d) => setStates(d.states)).catch(() => {})
    runSearch()
    getMyMachineryListings().then((d) => setMine(d.items)).catch(() => {})
    getMachineryGuide({}).then(setGuide).catch(() => {})
  }, []) // eslint-disable-line

  const runSearch = async (override: any = {}) => {
    setBusy(true)
    try {
      const params: any = {
        machine_key: filters.machine_key || undefined,
        state: filters.state || undefined,
        category: filters.category || undefined,
        max_rate: filters.max_rate || undefined,
        sort: filters.sort,
        ...override,
      }
      if (coords && !override.ignoreLocation) {
        params.lat = coords.lat
        params.lon = coords.lon
        params.radius_km = radius
      }
      delete params.ignoreLocation
      const res = await searchMachinery(params)
      setItems(res.items)
      publish('Machinery Rental', res.items.length
        ? `${res.items.length} machine(s) available to rent: `
          + res.items.slice(0, 8).map((m: any) => `${m.title} — ₹${m.daily_rate}/day in ${m.district || m.state}`).join('; ')
        : 'No machinery matches the current search filters.')
    } catch {
      setItems([])
    } finally {
      setBusy(false)
    }
  }

  const useLocation = () => {
    if (!navigator.geolocation) {
      setGpsError(t('ob.gpserror'))
      return
    }
    setGpsBusy(true); setGpsError('')
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude: lat, longitude: lon } = pos.coords
        setCoords({ lat, lon })
        try {
          const res = await machineryNearby(lat, lon, radius)
          setItems(res.items)
          setPlace(res.location)
          // Pre-fill the listing form too, so an owner does not retype it.
          if (res.location?.status === 'ok') {
            setForm((f: any) => ({
              ...f,
              state: f.state || res.location.state,
              district: f.district || res.location.district,
              latitude: lat, longitude: lon,
            }))
          }
        } catch {
          setGpsError(t('mach.searchfail'))
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

  const submit = async () => {
    setErrors([]); setPosted(false)
    const fd = new FormData()
    Object.entries(form).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) fd.append(k, String(v))
    })
    if (photo) fd.append('photo', photo)

    try {
      await createMachineryListing(fd)
      setPosted(true)
      setPhoto(null); setPreview('')
      setForm((f: any) => ({ ...f, title: '', daily_rate: '', description: '' }))
      getMyMachineryListings().then((d) => setMine(d.items))
      runSearch()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setErrors(detail?.errors || [t('mach.postfail')])
    }
  }

  const tabBtn = (id: Tab, label: string) => (
    <button
      key={id}
      onClick={() => setTab(id)}
      className={`px-4 py-2 rounded-xl text-sm font-medium transition
        ${tab === id ? 'bg-field-600 text-white shadow'
                     : 'bg-white hover:bg-field-50 border'}`}
    >
      {label}
    </button>
  )

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">
        🚜 {t('mach.title')}
      </h1>
      <p className="text-sm text-gray-500 mb-4">{t('mach.subtitle')}</p>

      <div className="flex flex-wrap gap-2 mb-5">
        {tabBtn('rent', t('mach.tab.rent'))}
        {tabBtn('give', t('mach.tab.give'))}
        {tabBtn('guide', t('mach.tab.guide'))}
      </div>

      {/* ================= RENT ================= */}
      {tab === 'rent' && (
        <>
          <Card>
            <div className="flex flex-wrap items-end gap-3">
              <button
                type="button"
                onClick={useLocation}
                disabled={gpsBusy}
                className="px-3 py-2 rounded-xl text-sm border-2 border-dashed
                           border-field-300 text-field-700 hover:bg-field-50
                           disabled:opacity-50"
              >
                📍 {gpsBusy ? t('ob.s1.gpsbusy') : t('mach.usemylocation')}
              </button>

              {place && (
                <span className="text-xs text-green-700 font-medium">
                  ✓ {place.district || place.state}
                </span>
              )}

              {coords && (
                <div>
                  <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                    {t('mach.within')}
                  </label>
                  <select
                    value={radius}
                    onChange={(e) => {
                      const r = Number(e.target.value)
                      setRadius(r)
                      if (coords) machineryNearby(coords.lat, coords.lon, r)
                        .then((res) => setItems(res.items)).catch(() => {})
                    }}
                    className="border rounded-lg px-2 py-1.5 text-sm"
                  >
                    {RADII.map((r) => <option key={r} value={r}>{r} km</option>)}
                  </select>
                </div>
              )}
            </div>

            {gpsError && (
              <p className="text-xs text-amber-700 mt-2">{gpsError}</p>
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                  {t('mach.machine')}
                </label>
                <select value={filters.machine_key}
                        onChange={(e) => setFilters({ ...filters, machine_key: e.target.value })}
                        className="w-full border rounded-lg px-2 py-1.5 text-sm">
                  <option value="">{t('mach.all')}</option>
                  {catalog?.machines?.map((m: any) => (
                    <option key={m.key} value={m.key}>{m.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                  {t('common.state')}
                </label>
                <select value={filters.state}
                        onChange={(e) => setFilters({ ...filters, state: e.target.value })}
                        className="w-full border rounded-lg px-2 py-1.5 text-sm">
                  <option value="">{t('mach.allindia')}</option>
                  {states.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                  {t('mach.maxrate')}
                </label>
                <input value={filters.max_rate}
                       onChange={(e) => setFilters({ ...filters, max_rate: e.target.value.replace(/[^\d]/g, '') })}
                       placeholder="2000"
                       className="w-full border rounded-lg px-2 py-1.5 text-sm" />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                  {t('mach.sort')}
                </label>
                <select value={filters.sort}
                        onChange={(e) => setFilters({ ...filters, sort: e.target.value })}
                        className="w-full border rounded-lg px-2 py-1.5 text-sm">
                  <option value="distance">{t('mach.sort.near')}</option>
                  <option value="price_low">{t('mach.sort.cheap')}</option>
                  <option value="price_high">{t('mach.sort.costly')}</option>
                  <option value="newest">{t('mach.sort.new')}</option>
                </select>
              </div>
            </div>

            <Button onClick={() => runSearch()} disabled={busy}>
              {busy ? t('common.loading') : t('mach.search')}
            </Button>
          </Card>

          {busy && <Spinner />}

          {!busy && items.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-10">
              {t('mach.noresults')}
            </p>
          )}

          {/* ---------- STEP 1: choose a machine TYPE ---------- */}
          {!detail && (
            <>
              {typesBusy && <Spinner />}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-4">
                {types.map((ty) => (
                  <button key={ty.machine_key} onClick={() => openType(ty.machine_key)}
                          className="bg-white rounded-2xl shadow-sm border overflow-hidden
                                     text-left hover:shadow-md transition">
                    {/* Real photo when one has been added, else the drawing.
                        Never a broken image icon. */}
                    {ty.cover_photo
                      ? <img src={ty.cover_photo} alt={ty.name}
                             className="w-full h-28 object-cover" />
                      : <MachineryImage type={ty.icon} className="h-28" />}
                    <div className="p-3">
                      <h3 className="font-bold text-field-800 text-sm leading-tight">
                        {ty.name}
                      </h3>
                      {/* Availability only. No rate, no contact — those belong
                          on the next screen, once a machine is chosen. */}
                      <p className="text-[11px] text-gray-500 mt-1">
                        {ty.available_count > 0
                          ? `${ty.available_count} ${t('mach.availableCount')}`
                          : t('mach.noneListed')}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}

          {/* ---------- STEP 2: offers for the chosen type ---------- */}
          {detail && (
            <div className="mt-4">
              <button onClick={() => { setDetail(null); loadTypes() }}
                      className="text-sm text-field-700 mb-3">
                ← {t('mach.backToTypes')}
              </button>

              {detailBusy && <Spinner />}

              <Card>
                {/* Photo gallery for this machine type. */}
                {detail.photos?.length > 0 ? (
                  <div>
                    <img src={detail.photos[gallery]} alt={detail.name}
                         className="w-full h-56 object-cover rounded-xl" />
                    {detail.photos.length > 1 && (
                      <div className="flex gap-2 mt-2 overflow-x-auto">
                        {detail.photos.map((ph: string, idx: number) => (
                          <img key={ph} src={ph} alt="" onClick={() => setGallery(idx)}
                               className={`w-16 h-14 object-cover rounded-lg cursor-pointer
                                 ${idx === gallery ? 'ring-2 ring-field-600' : 'opacity-70'}`} />
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <MachineryImage type={detail.icon} className="h-40" />
                )}

                <h2 className="font-bold text-field-800 text-lg mt-3">{detail.name}</h2>
                <p className="text-sm text-gray-700 mt-1">{detail.what_it_does}</p>
                {detail.when_needed && (
                  <p className="text-sm text-gray-600 mt-2">
                    <strong>{t('mach.whenNeeded')}:</strong> {detail.when_needed}
                  </p>
                )}
                {detail.suits_land && (
                  <p className="text-sm text-gray-600 mt-1">
                    <strong>{t('mach.suitsLand')}:</strong> {detail.suits_land}
                  </p>
                )}
                {detail.tip && (
                  <p className="text-[12px] bg-amber-50 text-amber-900 rounded-lg p-2 mt-3">
                    💡 {detail.tip}
                  </p>
                )}
              </Card>

              <h3 className="font-bold text-field-800 mt-5 mb-2">
                {detail.offer_count > 0
                  ? `${detail.offer_count} ${t('mach.offersAvailable')}`
                  : t('mach.noOffers')}
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {detail.offers?.map((m: any) => (
                  <div key={m.id}
                       className="bg-white rounded-2xl shadow-sm border overflow-hidden flex flex-col">
                    {m.image_path
                      ? <img src={m.image_path} alt={m.machine_name}
                             className="w-full h-32 object-cover" />
                      : <MachineryImage type={m.icon} className="h-32" />}
                    <div className="p-3 flex-1 flex flex-col">
                      <div className="flex items-start justify-between gap-2">
                        <h4 className="font-bold text-field-800 text-sm leading-tight">
                          {m.title || m.machine_name}
                        </h4>
                        {m.distance_km !== null && m.distance_km !== undefined && (
                          <span className="text-[10px] whitespace-nowrap px-1.5 py-0.5
                                           rounded-full bg-field-100 text-field-800">
                            {m.distance_km} km{m.distance_exact ? '' : '~'}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-gray-500 mt-0.5">
                        {m.brand} {m.model_year ? `· ${m.model_year}` : ''}
                      </p>
                      <div className="mt-2">
                        <span className="text-xl font-bold text-field-800">
                          ₹{m.daily_rate?.toLocaleString()}
                        </span>
                        <span className="text-xs text-gray-500"> {t('mach.perday')}</span>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {m.fuel_included && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full
                                           bg-green-100 text-green-800">
                            ⛽ {t('mach.fuelinc')}
                          </span>
                        )}
                        {m.operator_included && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full
                                           bg-blue-100 text-blue-800">
                            👨‍🌾 {t('mach.opinc')}
                          </span>
                        )}
                      </div>
                      {m.notes && (
                        <p className="text-[12px] text-gray-600 mt-2">{m.notes}</p>
                      )}
                      <p className="text-[11px] text-gray-500 mt-2">
                        📍 {[m.village, m.district, m.state].filter(Boolean).join(', ')}
                      </p>
                      <button onClick={() => revealContact(m.id)}
                              className="mt-3 w-full bg-field-700 text-white rounded-xl
                                         py-2 text-sm font-semibold">
                        📞 {t('mach.getcontact')}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* contact modal */}
          {contact && (
            <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50"
                 onClick={() => setContact(null)}>
              <div className="bg-white rounded-2xl p-5 max-w-sm w-full"
                   onClick={(e) => e.stopPropagation()}>
                <h3 className="font-bold text-field-800">{contact.machine_name}</h3>
                <p className="text-sm text-gray-600 mt-1">{contact.owner_name}</p>
                <a href={`tel:${contact.contact_phone}`}
                   className="block text-2xl font-bold text-field-700 my-3">
                  📞 {contact.contact_phone}
                </a>
                <p className="text-sm">
                  ₹{contact.daily_rate?.toLocaleString()} {t('mach.perday')}
                </p>
                <p className="text-[11px] text-amber-800 bg-amber-50 rounded-lg p-2 mt-3">
                  ⚠ {contact.safety_note}
                </p>
                <button onClick={() => setContact(null)}
                        className="mt-3 w-full border rounded-xl py-2 text-sm">
                  {t('mach.close')}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ================= GIVE FOR RENT ================= */}
      {tab === 'give' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card>
            <h3 className="font-semibold text-field-800 mb-3">{t('mach.listyours')}</h3>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                  {t('mach.machine')} *
                </label>
                <select value={form.machine_key}
                        onChange={(e) => setForm({ ...form, machine_key: e.target.value })}
                        className="w-full border rounded-xl px-3 py-2.5 text-sm">
                  {catalog?.machines?.map((m: any) => (
                    <option key={m.key} value={m.key}>{m.name}</option>
                  ))}
                </select>
              </div>

              {/* Photo. A real photo builds far more trust than an illustration. */}
              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                  {t('mach.photo')}
                </label>
                <label className="block border-2 border-dashed rounded-xl p-4
                                  text-center cursor-pointer hover:bg-field-50">
                  {preview
                    ? <img src={preview} alt="" className="h-28 mx-auto rounded-lg object-cover" />
                    : <span className="text-xs text-gray-500">📷 {t('mach.addphoto')}</span>}
                  <input type="file" accept="image/*" className="hidden"
                         onChange={(e) => {
                           const f = e.target.files?.[0] || null
                           setPhoto(f)
                           setPreview(f ? URL.createObjectURL(f) : '')
                         }} />
                </label>
              </div>

              <VoiceField label={t('mach.listingtitle')} value={form.title}
                          onChange={(v) => setForm({ ...form, title: v })}
                          placeholder="Mahindra 575 DI, 47 HP" />

              <div className="grid grid-cols-2 gap-3">
                <VoiceField label={t('mach.brand')} value={form.brand}
                            onChange={(v) => setForm({ ...form, brand: v })} />
                <div>
                  <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                    {t('mach.year')}
                  </label>
                  <input value={form.model_year}
                         onChange={(e) => setForm({ ...form, model_year: e.target.value.replace(/[^\d]/g, '') })}
                         placeholder="2021"
                         className="w-full border rounded-xl px-3 py-2.5 text-sm" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                    {t('mach.dailyrate')} *
                  </label>
                  <input value={form.daily_rate}
                         onChange={(e) => setForm({ ...form, daily_rate: e.target.value.replace(/[^\d.]/g, '') })}
                         placeholder="1500"
                         className="w-full border rounded-xl px-3 py-2.5 text-sm" />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                    {t('mach.condition')}
                  </label>
                  <select value={form.condition}
                          onChange={(e) => setForm({ ...form, condition: e.target.value })}
                          className="w-full border rounded-xl px-3 py-2.5 text-sm">
                    <option value="excellent">{t('mach.cond.excellent')}</option>
                    <option value="good">{t('mach.cond.good')}</option>
                    <option value="fair">{t('mach.cond.fair')}</option>
                  </select>
                </div>
              </div>

              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.fuel_included}
                         onChange={(e) => setForm({ ...form, fuel_included: e.target.checked })} />
                  {t('mach.fuelinc')}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.operator_included}
                         onChange={(e) => setForm({ ...form, operator_included: e.target.checked })} />
                  {t('mach.operatorinc')}
                </label>
              </div>

              <VoiceField label={t('mach.yourname')} value={form.owner_name}
                          onChange={(v) => setForm({ ...form, owner_name: v })} />

              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                  {t('mach.phone')} *
                </label>
                <input value={form.contact_phone}
                       onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
                       placeholder="9876543210" inputMode="tel"
                       className="w-full border rounded-xl px-3 py-2.5 text-sm" />
                <p className="text-[10px] text-gray-400 mt-1">{t('mach.phonenote')}</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-gray-500 mb-1">
                    {t('common.state')} *
                  </label>
                  <select value={form.state}
                          onChange={(e) => setForm({ ...form, state: e.target.value })}
                          className="w-full border rounded-xl px-3 py-2.5 text-sm">
                    <option value="">—</option>
                    {states.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <VoiceField label={t('common.district')} value={form.district}
                            onChange={(v) => setForm({ ...form, district: v })} />
              </div>

              <VoiceField label={t('mach.description')} value={form.description}
                          onChange={(v) => setForm({ ...form, description: v })}
                          multiline rows={2} />

              {errors.length > 0 && (
                <ul className="text-xs text-red-700 bg-red-50 rounded-lg p-2 list-disc ml-4">
                  {errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
              {posted && (
                <p className="text-sm text-green-700 bg-green-50 rounded-lg p-2">
                  ✓ {t('mach.posted')}
                </p>
              )}

              <Button onClick={submit}>{t('mach.publish')}</Button>
            </div>
          </Card>

          <Card>
            <h3 className="font-semibold text-field-800 mb-3">
              {t('mach.mylistings')} ({mine.length})
            </h3>
            {mine.length === 0 && (
              <p className="text-sm text-gray-400 py-6 text-center">
                {t('mach.nolistings')}
              </p>
            )}
            <div className="space-y-3">
              {mine.map((m) => (
                <div key={m.id} className="border rounded-xl p-3 flex gap-3">
                  <div className="w-20 shrink-0">
                    {m.image_path
                      ? <img src={m.image_path} alt="" className="w-20 h-16 object-cover rounded-lg" />
                      : <MachineryImage type={m.icon} className="h-16 rounded-lg" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm text-field-800 truncate">
                      {m.title || m.machine_name}
                    </p>
                    <p className="text-xs text-gray-500">
                      ₹{m.daily_rate.toLocaleString()} {t('mach.perday')} ·{' '}
                      👁 {m.views} · 📞 {m.contact_requests}
                    </p>
                    <div className="flex gap-2 mt-1.5">
                      <button
                        onClick={() => setMachineryAvailability(m.id, !m.available)
                          .then(() => getMyMachineryListings().then((d) => setMine(d.items)))}
                        className={`text-[11px] px-2 py-0.5 rounded-full border
                          ${m.available ? 'bg-green-100 text-green-800'
                                        : 'bg-gray-100 text-gray-600'}`}>
                        {m.available ? t('mach.availableCount') : t('mach.paused')}
                      </button>
                      <button
                        onClick={() => deleteMachineryListing(m.id)
                          .then(() => getMyMachineryListings().then((d) => setMine(d.items)))}
                        className="text-[11px] text-red-600 hover:underline">
                        {t('mach.delete')}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ================= GUIDE ================= */}
      {tab === 'guide' && guide && (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            {t('mach.guideintro')}
            {guide.crop && <b> {tv(guide.crop)}</b>}
            {guide.land_size_acres && <> · {guide.land_size_acres} {t('ob.s2.acres')}</>}
          </p>

          {catalog && guide.recommended.map((m: any) => (
            <Card key={m.key}>
              <div className="flex gap-4">
                <div className="w-28 shrink-0">
                  <MachineryImage type={m.icon} className="h-20 rounded-lg" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-bold text-field-800">{m.name}</h3>
                    <span className="text-[10px] px-2 py-0.5 rounded-full
                                     bg-field-100 text-field-800">
                      {catalog.stages[m.stage]}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 mt-1">{m.what_it_does}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    <b>{t('mach.whenneeded')}:</b> {m.when_needed}
                  </p>
                  <p className="text-xs text-gray-500">
                    <b>{t('mach.suitsland')}:</b> {m.suits_land}
                  </p>
                  <p className="text-xs text-field-700 mt-1">
                    <b>{t('mach.typicalrate')}:</b> ₹{m.typical_daily_rate[0].toLocaleString()}
                    –₹{m.typical_daily_rate[1].toLocaleString()} {m.unit}
                  </p>
                  <p className="text-[11px] text-amber-800 bg-amber-50 rounded-lg p-2 mt-2">
                    💡 {m.tip}
                  </p>
                  <button
                    onClick={() => {
                      setFilters({ ...filters, machine_key: m.key })
                      setTab('rent')
                      runSearch({ machine_key: m.key })
                    }}
                    className="mt-2 text-xs font-semibold text-field-700 hover:underline">
                    {t('mach.findnearby')} →
                  </button>
                </div>
              </div>
            </Card>
          ))}

          {guide.not_suitable?.length > 0 && (
            <Card>
              <h3 className="font-semibold text-gray-600 text-sm mb-2">
                {t('mach.notsuitable')}
              </h3>
              {guide.not_suitable.map((m: any) => (
                <p key={m.key} className="text-xs text-gray-500 mb-1">
                  <b>{m.name}</b> — {m.note}
                </p>
              ))}
            </Card>
          )}

          <p className="text-[11px] text-gray-400">{guide.disclaimer}</p>
        </div>
      )}
    </div>
  )
}
