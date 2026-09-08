import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  predictMaturity, createListing, getMyListings, withdrawListing,
  getReceivedOrders, respondToOrder, uploadListingPhoto,
  createFertilizerListing, getFertilizerPriceSuggestion,
} from '../services/api'
import { Card, Button, Spinner, StatusPill } from '../components/UI'
import { VoiceField } from '../components/VoiceInput'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

const CROPS = ['soybean', 'wheat', 'chickpea', 'maize', 'cotton',
               'rice', 'tomato', 'onion', 'potato', 'chilli']

const FERTILIZER_METHODS = [
  { key: 'compost', label: 'Compost' },
  { key: 'vermicompost', label: 'Vermicompost' },
  { key: 'fym', label: 'Farmyard manure (FYM)' },
  { key: 'liquid', label: 'Liquid manure' },
]

const ORDER_STATUS_LABEL: Record<string, string> = {
  requested: 'WARNING', confirmed: 'OPTIMAL', declined: 'CRITICAL', completed: 'OPTIMAL',
}

const todayPlusWeeks = (weeks: number) => {
  const d = new Date()
  d.setDate(d.getDate() + Math.round(weeks * 7))
  return d.toISOString().slice(0, 10)
}

/**
 * "Sell Produce" — a farmer sows a crop, the app predicts when it will be
 * ready (from the same crop-lifecycle data used on Crop Advisor), and the
 * farmer decides whether and at what price to offer it to buyers directly
 * through the marketplace. No middleman, no mandi trip required.
 *
 * The page also sells FERTILISER. A farmer composting their dung on the
 * Circular Farming page ends up with a surplus that is worth money, and
 * making them retype a quantity the app already calculated is the surest way
 * to make sure the listing never gets made. Tapping "Sell this" over there
 * lands here with the tab switched, the quantity filled in and a suggested
 * price — the farmer still names it and sets their own price.
 */
export default function Sell() {
  const { tv } = useLanguage()
  const { publish } = usePageContext()
  const location = useLocation()
  const handoff = (location.state as any)?.fertilizer

  const [tab, setTab] = useState<'produce' | 'fertilizer'>(
    handoff ? 'fertilizer' : 'produce')

  const [form, setForm] = useState<any>({
    crop: 'tomato', variety: '', sowing_date: '', maturity_date: '',
    intends_to_sell: false, quantity_kg: '', price_per_kg: '', contact_phone: '',
  })

  // Fertiliser listing, pre-filled from the Circular Farming hand-off when
  // there is one.
  const [fert, setFert] = useState<any>({
    product_name: handoff?.product_name || '',
    method: handoff?.method || 'compost',
    variety: '',
    quantity_kg: handoff?.quantity_kg != null ? String(handoff.quantity_kg) : '',
    price_per_kg: handoff?.suggested_price != null
      ? String(handoff.suggested_price) : '',
    contact_phone: '',
    ready_date: handoff?.ready_weeks?.low
      ? todayPlusWeeks(handoff.ready_weeks.low) : '',
  })
  const [priceHint, setPriceHint] = useState<any>(handoff ? {
    low: handoff.price_low, high: handoff.price_high,
    suggested: handoff.suggested_price, unit: handoff.unit || 'kg',
    basis: handoff.price_basis, caveat: handoff.price_caveat,
  } : null)
  const [fertSaving, setFertSaving] = useState(false)
  const [fertError, setFertError] = useState('')
  const [fertSaved, setFertSaved] = useState(false)

  const [prediction, setPrediction] = useState<any>(null)
  const [predicting, setPredicting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  const [mine, setMine] = useState<any[]>([])
  const [loadingMine, setLoadingMine] = useState(true)
  const [orders, setOrders] = useState<any[]>([])
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [photoPreview, setPhotoPreview] = useState('')
  const [uploadingPhotoFor, setUploadingPhotoFor] = useState<number | null>(null)
  const photoInputRef = useRef<HTMLInputElement>(null)

  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }))

  const loadMine = () => {
    getMyListings().then((m) => {
      setMine(m)
      publish('Sell Produce', m.length
        ? `${m.length} listing(s): ` + m.map((l: any) =>
            `${l.crop}${l.variety ? ` (${l.variety})` : ''} — ${l.status}`
              + (l.price_per_kg ? ` at ₹${l.price_per_kg}/kg` : '')).join('; ')
        : 'No produce listed for sale yet.')
    }).catch(() => {}).finally(() => setLoadingMine(false))
    getReceivedOrders().then(setOrders).catch(() => {})
  }
  useEffect(loadMine, [])

  // Recompute the predicted maturity date whenever crop or sowing date
  // changes — this is what makes the date feel automatic rather than
  // something the farmer has to work out themselves.
  useEffect(() => {
    if (!form.crop || !form.sowing_date) { setPrediction(null); return }
    setPredicting(true)
    predictMaturity(form.crop, form.sowing_date)
      .then(setPrediction)
      .catch(() => setPrediction(null))
      .finally(() => setPredicting(false))
  }, [form.crop, form.sowing_date])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true); setError(''); setSaved(false)
    try {
      const created = await createListing({
        crop: form.crop, variety: form.variety,
        sowing_date: form.sowing_date || null,
        maturity_date: form.maturity_date || null,
        intends_to_sell: form.intends_to_sell,
        quantity_kg: form.quantity_kg ? Number(form.quantity_kg) : null,
        price_per_kg: form.price_per_kg ? Number(form.price_per_kg) : null,
        contact_phone: form.contact_phone,
      })
      if (photoFile && created?.id) {
        await uploadListingPhoto(created.id, photoFile).catch(() => {})
      }
      setSaved(true)
      setForm((f: any) => ({ ...f, quantity_kg: '', price_per_kg: '' }))
      setPhotoFile(null); setPhotoPreview('')
      if (photoInputRef.current) photoInputRef.current.value = ''
      loadMine()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not save this listing.')
    } finally {
      setSaving(false)
    }
  }

  const pickPhoto = (f: File) => {
    setPhotoFile(f)
    setPhotoPreview(URL.createObjectURL(f))
  }

  const setF = (k: string, v: any) => setFert((f: any) => ({ ...f, [k]: v }))

  // Re-fetch the suggested band when the material changes — vermicompost and
  // plain FYM are not worth remotely the same per kg, and leaving a stale
  // suggestion on screen would be worse than showing none.
  useEffect(() => {
    if (tab !== 'fertilizer' || !fert.method) return
    getFertilizerPriceSuggestion(
      fert.method,
      fert.quantity_kg ? Number(fert.quantity_kg) : undefined)
      .then(setPriceHint)
      .catch(() => {})
  }, [tab, fert.method, fert.quantity_kg])

  const submitFertilizer = async (e: React.FormEvent) => {
    e.preventDefault()
    setFertSaving(true); setFertError(''); setFertSaved(false)
    try {
      await createFertilizerListing({
        product_name: fert.product_name,
        method: fert.method,
        variety: fert.variety,
        quantity_kg: fert.quantity_kg ? Number(fert.quantity_kg) : null,
        price_per_kg: fert.price_per_kg ? Number(fert.price_per_kg) : null,
        contact_phone: fert.contact_phone,
        ready_date: fert.ready_date || null,
        source: handoff ? 'circular_farming' : '',
      })
      setFertSaved(true)
      loadMine()
    } catch (e: any) {
      setFertError(e.response?.data?.detail || 'Could not save this listing.')
    } finally {
      setFertSaving(false)
    }
  }

  const addPhotoToExisting = async (id: number, f: File) => {
    setUploadingPhotoFor(id)
    try { await uploadListingPhoto(id, f); loadMine() } finally { setUploadingPhotoFor(null) }
  }

  const respond = async (id: number, status: string) => {
    await respondToOrder(id, status)
    loadMine()
  }

  const needsManualDate = form.sowing_date && prediction && !prediction.supported

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">🛒 Sell Produce</h1>
      <p className="text-sm text-gray-500 mb-4">
        Tell us what you sowed and when — we'll work out roughly when it will
        be ready, and you decide if and at what price to offer it to buyers.
      </p>

      {/* Two things a farm has to sell: what it grew, and what it composted.
          Same buyers, same listing management, different form. */}
      <div className="flex gap-2 mb-5">
        {([['produce', '🌾 Crop produce'],
           ['fertilizer', '♻️ Compost / fertiliser']] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`text-sm font-semibold px-4 py-2 rounded-xl border-2 transition
              ${tab === k ? 'border-field-600 bg-field-50 text-field-800'
                          : 'border-gray-200 bg-white text-gray-500 hover:border-field-300'}`}>
            {label}
          </button>
        ))}
      </div>

      {handoff && tab === 'fertilizer' && (
        <div className="rounded-xl border-2 border-field-300 bg-field-50 px-4 py-3 mb-4">
          <p className="text-sm font-semibold text-field-800">
            ♻️ Brought over from Circular Farming
          </p>
          <p className="text-xs text-gray-600 mt-0.5">
            Quantity and a suggested price are filled in from your composting
            plan. Give it a name, set your own price, and it goes to buyers.
          </p>
        </div>
      )}

      {tab === 'fertilizer' && (
        <Card className="mb-6">
          <form onSubmit={submitFertilizer} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-600">
                  Fertiliser name
                </label>
                <p className="text-xs text-gray-400 mb-1">
                  What buyers will see. Your own name for it is fine.
                </p>
                <input value={fert.product_name}
                  onChange={(e) => setF('product_name', e.target.value)}
                  placeholder="e.g. Vermicompost"
                  className="w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600">Material</label>
                <p className="text-xs text-gray-400 mb-1">
                  Buyers browse by material, so this decides where it shows up.
                </p>
                <select value={fert.method}
                  onChange={(e) => setF('method', e.target.value)}
                  className="w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600">
                  {FERTILIZER_METHODS.map((m) => (
                    <option key={m.key} value={m.key}>{m.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-600">
                  Quantity ({priceHint?.unit === 'litre' ? 'litres' : 'kg'})
                </label>
                <input type="number" min="0" value={fert.quantity_kg}
                  onChange={(e) => setF('quantity_kg', e.target.value)}
                  className="mt-1 w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600">
                  Your price (₹/{priceHint?.unit || 'kg'})
                </label>
                <input type="number" min="0" step="0.5" value={fert.price_per_kg}
                  onChange={(e) => setF('price_per_kg', e.target.value)}
                  className="mt-1 w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
              </div>
              <VoiceField label="Contact phone" value={fert.contact_phone}
                onChange={(v) => setF('contact_phone', v)} placeholder="10-digit mobile" />
            </div>

            {/* The suggestion sits BESIDE the input, never inside it. There is
                no daily price for farm compost the way there is for grain, so
                a figure typed into the box for them would look like a rate
                the app is standing behind. */}
            {priceHint?.low != null && (
              <div className="bg-field-50 rounded-xl p-4">
                <p className="text-sm font-semibold text-field-800">
                  💡 Farmers near you usually get ₹{priceHint.low}–{priceHint.high} per {priceHint.unit}
                  {priceHint.estimated_value ? (
                    <span className="font-normal text-gray-600">
                      {' '}— about ₹{Number(priceHint.estimated_value).toLocaleString()} for this lot
                    </span>
                  ) : null}
                </p>
                {priceHint.suggested != null && (
                  <button type="button"
                    onClick={() => setF('price_per_kg', String(priceHint.suggested))}
                    className="text-xs font-semibold text-field-700 underline mt-1">
                    Use ₹{priceHint.suggested}/{priceHint.unit}
                  </button>
                )}
                <p className="text-xs text-gray-500 mt-1">{priceHint.caveat}</p>
              </div>
            )}

            <div>
              <label className="text-sm font-medium text-gray-600">
                Ready on
              </label>
              <p className="text-xs text-gray-400 mb-1">
                Leave blank if you have it now. Buyers see it as "ready ~date"
                until then, so nobody orders a heap that is still rotting.
              </p>
              <input type="date" value={fert.ready_date}
                onChange={(e) => setF('ready_date', e.target.value)}
                className="w-full sm:w-64 border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            </div>

            {fertError && <p className="text-sm text-red-600">{fertError}</p>}
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={fertSaving}>
                {fertSaving ? 'Saving…' : 'List this fertiliser'}
              </Button>
              {fertSaved && (
                <span className="text-sm text-field-600">
                  ✓ Listed — buyers can now see it under your name
                </span>
              )}
            </div>
          </form>
        </Card>
      )}

      {tab === 'produce' && (
      <Card className="mb-6">
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-600">Crop</label>
              <select value={form.crop} onChange={(e) => set('crop', e.target.value)}
                className="mt-1 w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600">
                {CROPS.map((c) => <option key={c} value={c}>{tv(c)}</option>)}
              </select>
            </div>
            <VoiceField label="Variety (optional)" value={form.variety}
              onChange={(v) => set('variety', v)} placeholder="e.g. Local, Hybrid" />
          </div>

          <div>
            <label className="text-sm font-medium text-gray-600">Sowing date</label>
            <input type="date" value={form.sowing_date}
              onChange={(e) => set('sowing_date', e.target.value)}
              max={new Date().toISOString().slice(0, 10)}
              className="mt-1 w-full sm:w-64 border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
          </div>

          {predicting && <p className="text-sm text-gray-400">Working out the maturity date…</p>}

          {prediction?.supported && (
            <div className="bg-field-50 rounded-xl p-4">
              <p className="text-sm font-semibold text-field-800">
                📅 Predicted ready-to-harvest date:{' '}
                {new Date(prediction.predicted_maturity_date).toLocaleDateString('en-IN',
                  { day: 'numeric', month: 'long', year: 'numeric' })}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Based on a typical {prediction.total_duration_days}-day cycle for {tv(form.crop)}.
                {' '}{prediction.disclaimer}
              </p>
            </div>
          )}

          {needsManualDate && (
            <div>
              <label className="text-sm font-medium text-gray-600">
                We don't have a standard cycle for {tv(form.crop)} yet — enter your own expected harvest date
              </label>
              <input type="date" value={form.maturity_date}
                onChange={(e) => set('maturity_date', e.target.value)}
                className="mt-1 w-full sm:w-64 border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            </div>
          )}

          <label className="flex items-center gap-3 bg-gray-50 rounded-xl px-4 py-3 cursor-pointer">
            <input type="checkbox" checked={form.intends_to_sell}
              onChange={(e) => set('intends_to_sell', e.target.checked)}
              className="w-5 h-5 accent-field-600" />
            <span className="text-sm font-medium text-gray-700">
              Do you plan to sell this crop through the marketplace?
            </span>
          </label>

          {form.intends_to_sell && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-600">Quantity (kg)</label>
                <input type="number" min="0" value={form.quantity_kg}
                  onChange={(e) => set('quantity_kg', e.target.value)}
                  className="mt-1 w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600">Price (₹/kg)</label>
                <input type="number" min="0" step="0.5" value={form.price_per_kg}
                  onChange={(e) => set('price_per_kg', e.target.value)}
                  className="mt-1 w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
              </div>
              <VoiceField label="Contact phone" value={form.contact_phone}
                onChange={(v) => set('contact_phone', v)} placeholder="10-digit mobile" />
            </div>
          )}

          {form.intends_to_sell && (
            <div>
              <label className="text-sm font-medium text-gray-600">Photo of your produce (optional)</label>
              <p className="text-xs text-gray-400 mb-1.5">Buyers browsing this crop will see it — a real photo builds trust.</p>
              <div className="flex items-center gap-3">
                <input ref={photoInputRef} type="file" accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => e.target.files?.[0] && pickPhoto(e.target.files[0])}
                  className="text-sm" />
                {photoPreview && (
                  <img src={photoPreview} alt="preview" className="w-16 h-16 object-cover rounded-lg border" />
                )}
              </div>
            </div>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'List this crop'}
            </Button>
            {saved && <span className="text-sm text-field-600">✓ Saved</span>}
          </div>
        </form>
      </Card>
      )}

      {/* Received buyer requests */}
      {orders.length > 0 && (
        <Card className="mb-6">
          <h3 className="font-semibold text-field-800 mb-3">📥 Buyer requests</h3>
          <div className="space-y-2">
            {orders.map((o) => (
              <div key={o.id} className="bg-gray-50 rounded-xl px-4 py-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm">
                    <span className="font-semibold">{o.buyer_name}</span> wants{' '}
                    {o.quantity_kg ? `${o.quantity_kg} kg of ` : ''}
                    {o.listing?.crop ? tv(o.listing.crop) : 'this crop'}
                  </div>
                  <StatusPill status={ORDER_STATUS_LABEL[o.status] || 'INFO'} />
                </div>
                {o.message && <p className="text-xs text-gray-500 mt-1">"{o.message}"</p>}
                {o.status === 'requested' && (
                  <div className="flex gap-2 mt-2">
                    <button onClick={() => respond(o.id, 'confirmed')}
                      className="text-xs font-semibold bg-field-600 text-white px-3 py-1.5 rounded-lg">
                      Accept
                    </button>
                    <button onClick={() => respond(o.id, 'declined')}
                      className="text-xs font-semibold bg-white border px-3 py-1.5 rounded-lg">
                      Decline
                    </button>
                  </div>
                )}
                {o.status === 'confirmed' && (
                  <button onClick={() => respond(o.id, 'completed')}
                    className="text-xs font-semibold bg-field-600 text-white px-3 py-1.5 rounded-lg mt-2">
                    Mark sold / completed
                  </button>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* My listings */}
      <Card>
        <h3 className="font-semibold text-field-800 mb-3">My listings</h3>
        {loadingMine ? <Spinner /> : mine.length === 0 ? (
          <p className="text-sm text-gray-400">No listings yet.</p>
        ) : (
          <div className="space-y-2">
            {mine.map((l) => (
              <div key={l.id} className="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-3">
                <div className="flex items-center gap-3">
                  {l.image_url ? (
                    <img src={l.image_url} alt={l.crop} className="w-12 h-12 object-cover rounded-lg border" />
                  ) : (
                    <label className="w-12 h-12 rounded-lg border border-dashed flex items-center justify-center text-[10px] text-gray-400 cursor-pointer hover:bg-gray-100 text-center">
                      {uploadingPhotoFor === l.id ? '…' : '+ photo'}
                      <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                        onChange={(e) => e.target.files?.[0] && addPhotoToExisting(l.id, e.target.files[0])} />
                    </label>
                  )}
                  <div>
                    <div className="text-sm font-semibold">
                      {l.product_type === 'fertilizer'
                        ? <>♻️ {l.product_name || tv(l.crop)}</>
                        : <>{tv(l.crop)} {l.variety && `(${l.variety})`}</>}
                    </div>
                    <div className="text-xs text-gray-500">
                      {l.quantity_kg ? `${l.quantity_kg} kg` : ''}
                      {l.price_per_kg ? ` · ₹${l.price_per_kg}/kg` : ''}
                      {l.predicted_maturity_date ? ` · ready ${l.predicted_maturity_date}` : ''}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill status={l.status === 'available' ? 'OPTIMAL'
                    : l.status === 'growing' ? 'INFO'
                    : l.status === 'sold' ? 'Good' : 'WARNING'} />
                  {l.status !== 'withdrawn' && l.status !== 'sold' && (
                    <button
                      onClick={async () => { await withdrawListing(l.id); loadMine() }}
                      className="text-xs text-red-600 hover:text-red-700">
                      Withdraw
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
