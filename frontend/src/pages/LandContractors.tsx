import { useEffect, useState } from 'react'
import {
  browseLandListings, getLandListingContact, requestLandContract,
  getMyLandContracts, cancelLandContract, getLandStats, getContractMessages, sendContractMessage
} from '../services/api'
import { Card, Spinner, Empty, Button } from '../components/UI'

// ─── Types ────────────────────────────────────────────────────────────────────
interface LandListing {
  id: number
  farmer_name: string
  title: string
  description: string
  state: string
  district: string
  village: string
  area_acres: number
  soil_type: string
  water_source: string
  irrigation_available: boolean
  suitable_crops: string[]
  price_per_acre_per_season: number
  min_season_months: number
  max_season_months: number
  available_from: string | null
  status: string
  views: number
}

interface LandContract {
  id: number
  listing_id: number
  start_date: string
  end_date: string
  agreed_crop: string
  price_per_acre: number
  total_price: number
  status: string
  terms_accepted: boolean
  farmer_notes: string
  buyer_notes: string
  listing_title: string
  listing_area_acres: number
  listing_state: string
  listing_district: string
  listing_village: string
  listing_suitable_crops: string[]
  farmer_name: string
  created_at: string
}

// ─── Constants ─────────────────────────────────────────────────────────────────
const SOIL_ICONS: Record<string, string> = {
  Red: '🟥', Black: '⬛', Alluvial: '🟫', Loamy: '🟤', Sandy: '🟨',
  Clay: '🪨', Laterite: '🟧',
}
const WATER_ICONS: Record<string, string> = {
  borewell: '🕳️', canal: '🌊', rainfed: '🌧️', tank: '🪣', river: '💧',
}
const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800 border-amber-200',
  active: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  completed: 'bg-blue-100 text-blue-800 border-blue-200',
  cancelled: 'bg-red-100 text-red-800 border-red-200',
}
const STATUS_ICONS: Record<string, string> = {
  pending: '⏳', active: '✅', completed: '🏁', cancelled: '❌',
}
const TABS = ['Browse Land', 'My Contracts'] as const
type Tab = typeof TABS[number]

// ─── Sub-components ──────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: any }) {
  return (
    <div className="grid grid-cols-2 gap-4 mb-6">
      <div className="rounded-2xl p-4 text-white flex flex-col gap-1"
        style={{ background: 'linear-gradient(135deg, #2d6a4f 0%, #52b788 100%)' }}>
        <div className="text-3xl font-bold">{stats.available_plots ?? '—'}</div>
        <div className="text-sm font-medium opacity-90">🏡 Plots Available for Rent</div>
      </div>
      <div className="rounded-2xl p-4 text-white flex flex-col gap-1"
        style={{ background: 'linear-gradient(135deg, #774936 0%, #b5838d 100%)' }}>
        <div className="text-3xl font-bold">{stats.rented_plots ?? '—'}</div>
        <div className="text-sm font-medium opacity-90">🤝 Plots Under Contract</div>
      </div>
    </div>
  )
}

function FilterBar({ onSearch }: { onSearch: (f: any) => void }) {
  const [f, setF] = useState({ state: '', district: '', soil_type: '', min_acres: '', max_price: '', crop: '' })
  return (
    <Card className="mb-5">
      <div className="font-semibold text-field-800 mb-3 text-sm">🔍 Filter Land Listings</div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {[
          { key: 'state', ph: 'State' },
          { key: 'district', ph: 'District' },
          { key: 'soil_type', ph: 'Soil type' },
          { key: 'crop', ph: 'Suitable crop' },
          { key: 'min_acres', ph: 'Min acres', type: 'number' },
          { key: 'max_price', ph: 'Max ₹/acre/season', type: 'number' },
        ].map(({ key, ph, type }) => (
          <input key={key} type={type || 'text'} placeholder={ph}
            value={(f as any)[key]}
            onChange={(e) => setF({ ...f, [key]: e.target.value })}
            className="border rounded-xl px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-field-600 bg-white" />
        ))}
      </div>
      <button onClick={() => onSearch(f)}
        className="mt-3 bg-field-700 hover:bg-field-600 text-white text-xs font-bold px-5 py-2 rounded-xl transition">
        Search
      </button>
      <button onClick={() => { setF({ state: '', district: '', soil_type: '', min_acres: '', max_price: '', crop: '' }); onSearch({}) }}
        className="mt-3 ml-2 text-xs text-gray-500 underline">Clear</button>
    </Card>
  )
}

function ListingCard({
  listing, onRent, onReveal, contactInfo,
}: {
  listing: LandListing
  onRent: (l: LandListing) => void
  onReveal: (id: number) => void
  contactInfo: Record<number, any>
}) {
  const ci = contactInfo[listing.id]
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-all duration-200 overflow-hidden flex flex-col">
      {/* Header stripe */}
      <div className="h-1.5 w-full"
        style={{ background: listing.irrigation_available
          ? 'linear-gradient(90deg, #2d6a4f, #52b788)'
          : 'linear-gradient(90deg, #774936, #b5838d)' }} />

      <div className="p-4 flex-1 flex flex-col gap-3">
        {/* Title row */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-bold text-field-800 text-sm leading-tight">{listing.title || 'Farm Land for Rent'}</div>
            <div className="text-xs text-gray-500 mt-0.5">
              📍 {listing.village ? `${listing.village}, ` : ''}{listing.district}, {listing.state}
            </div>
          </div>
          <span className={`shrink-0 text-xs font-bold px-2 py-1 rounded-full border ${
            listing.status === 'available' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-gray-100 text-gray-500'
          }`}>
            {listing.status === 'available' ? '✅ Available' : listing.status}
          </span>
        </div>

        {/* Key stats row */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-field-50 rounded-xl p-2 text-center">
            <div className="text-lg font-bold text-field-800">{listing.area_acres}</div>
            <div className="text-[10px] text-gray-500">Acres</div>
          </div>
          <div className="bg-amber-50 rounded-xl p-2 text-center">
            <div className="text-lg font-bold text-amber-800">₹{listing.price_per_acre_per_season.toLocaleString()}</div>
            <div className="text-[10px] text-gray-500">per acre/season</div>
          </div>
        </div>

        {/* Details */}
        <div className="space-y-1 text-xs text-gray-600">
          <div className="flex gap-3 flex-wrap">
            {listing.soil_type && (
              <span>{SOIL_ICONS[listing.soil_type] || '🌱'} {listing.soil_type} soil</span>
            )}
            {listing.water_source && (
              <span>{WATER_ICONS[listing.water_source] || '💧'} {listing.water_source}</span>
            )}
            {listing.irrigation_available && <span className="text-emerald-600 font-medium">💦 Irrigation</span>}
          </div>
          <div>⏳ {listing.min_season_months}–{listing.max_season_months} months</div>
          {listing.available_from && (
            <div>📅 Available from: {new Date(listing.available_from).toLocaleDateString('en-IN')}</div>
          )}
        </div>

        {/* Suitable crops */}
        {listing.suitable_crops?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {listing.suitable_crops.map((c) => (
              <span key={c} className="text-[10px] bg-field-100 text-field-800 px-2 py-0.5 rounded-full font-medium">
                {c}
              </span>
            ))}
          </div>
        )}

        {/* Description */}
        {listing.description && (
          <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">{listing.description}</p>
        )}

        {/* Farmer contact (revealed) */}
        {ci && (
          <div className="bg-field-50 rounded-xl p-2 text-xs border border-field-200">
            <div className="font-semibold text-field-800">{ci.farmer_name}</div>
            <div className="text-field-700">📞 {ci.contact_phone}</div>
            <p className="text-gray-400 mt-1 text-[10px]">{ci.safety_note}</p>
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="px-4 pb-4 flex gap-2">
        <button
          onClick={() => onRent(listing)}
          disabled={listing.status !== 'available'}
          className="flex-1 bg-field-700 hover:bg-field-600 disabled:opacity-40 text-white text-xs font-bold py-2 rounded-xl transition">
          🤝 Request Contract
        </button>
        <button
          onClick={() => onReveal(listing.id)}
          className="bg-white border border-gray-200 hover:bg-gray-50 text-xs font-semibold py-2 px-3 rounded-xl transition">
          📞
        </button>
      </div>
    </div>
  )
}

function ContractRequestModal({
  listing, onClose, onSubmit,
}: {
  listing: LandListing
  onClose: () => void
  onSubmit: (payload: any) => Promise<void>
}) {
  const today = new Date().toISOString().split('T')[0]
  const [form, setForm] = useState({
    start_date: today,
    end_date: '',
    agreed_crop: listing.suitable_crops?.[0] || '',
    buyer_notes: '',
    terms_accepted: false,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const months = form.start_date && form.end_date
    ? Math.max(1, Math.round((new Date(form.end_date).getTime() - new Date(form.start_date).getTime()) / (30 * 86400000)))
    : 0
  const estimatedTotal = months > 0
    ? (listing.price_per_acre_per_season * listing.area_acres * months / 6).toFixed(0)
    : '—'

  const submit = async () => {
    if (!form.end_date) { setError('Please select an end date'); return }
    if (!form.terms_accepted) { setError('Please accept the terms'); return }
    setLoading(true); setError('')
    try {
      await onSubmit({ listing_id: listing.id, ...form })
      onClose()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)' }}>
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="p-5 text-white"
          style={{ background: 'linear-gradient(135deg, #2d6a4f 0%, #52b788 100%)' }}>
          <div className="font-bold text-lg">🤝 Request Land Contract</div>
          <div className="text-sm opacity-90 mt-0.5">{listing.title || 'Farm Land'} · {listing.area_acres} acres · {listing.district}</div>
        </div>

        <div className="p-5 space-y-4">
          {/* Price info */}
          <div className="bg-amber-50 rounded-2xl p-3 flex justify-between items-center">
            <div className="text-xs text-gray-500">Rate</div>
            <div className="font-bold text-amber-800">₹{listing.price_per_acre_per_season.toLocaleString()}/acre/season</div>
          </div>

          {/* Date pickers */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Start Date</label>
              <input type="date" value={form.start_date} min={today}
                onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                className="w-full border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">End Date</label>
              <input type="date" value={form.end_date} min={form.start_date || today}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                className="w-full border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            </div>
          </div>

          {/* Estimated total */}
          {months > 0 && (
            <div className="bg-field-50 rounded-xl p-3 text-center">
              <div className="text-xs text-gray-500 mb-0.5">Estimated Total ({months} month{months !== 1 ? 's' : ''})</div>
              <div className="text-2xl font-bold text-field-800">₹{Number(estimatedTotal).toLocaleString()}</div>
              <div className="text-[10px] text-gray-400">rate × {listing.area_acres} acres × {months}/6 seasons</div>
            </div>
          )}

          {/* Crop selection */}
          <div>
            <label className="text-xs text-gray-500 block mb-1">Planned Crop</label>
            {listing.suitable_crops?.length > 0 ? (
              <select value={form.agreed_crop}
                onChange={(e) => setForm({ ...form, agreed_crop: e.target.value })}
                className="w-full border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600">
                <option value="">— Select crop —</option>
                {listing.suitable_crops.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
                <option value="other">Other</option>
              </select>
            ) : (
              <input placeholder="e.g. Rice, Wheat" value={form.agreed_crop}
                onChange={(e) => setForm({ ...form, agreed_crop: e.target.value })}
                className="w-full border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            )}
          </div>

          {/* Notes */}
          <div>
            <label className="text-xs text-gray-500 block mb-1">Message to Farmer (optional)</label>
            <textarea rows={2} placeholder="Your plans, questions, or requirements..."
              value={form.buyer_notes}
              onChange={(e) => setForm({ ...form, buyer_notes: e.target.value })}
              className="w-full border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600 resize-none" />
          </div>

          {/* Terms */}
          <label className="flex items-start gap-2 cursor-pointer">
            <input type="checkbox" checked={form.terms_accepted}
              onChange={(e) => setForm({ ...form, terms_accepted: e.target.checked })}
              className="mt-0.5 accent-field-700" />
            <span className="text-xs text-gray-600">
              I understand that all produce grown on this land during the contract period belongs to me (the buyer/contractor), and I agree to the rental terms.
            </span>
          </label>

          {error && <div className="text-xs text-red-600 bg-red-50 rounded-xl px-3 py-2">{error}</div>}

          <div className="flex gap-2">
            <button onClick={onClose}
              className="flex-1 border rounded-xl py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50">
              Cancel
            </button>
            <button onClick={submit} disabled={loading}
              className="flex-1 bg-field-700 hover:bg-field-600 text-white text-sm font-bold py-2.5 rounded-xl disabled:opacity-50 transition">
              {loading ? '⏳ Sending…' : '✅ Send Request'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function ContractCard({ c, onCancel, onOpenChat }: { c: LandContract; onCancel?: (id: number) => void; onOpenChat?: (id: number) => void }) {
  const start = c.start_date ? new Date(c.start_date).toLocaleDateString('en-IN') : '—'
  const end = c.end_date ? new Date(c.end_date).toLocaleDateString('en-IN') : '—'
  const months = c.start_date && c.end_date
    ? Math.max(1, Math.round((new Date(c.end_date).getTime() - new Date(c.start_date).getTime()) / (30 * 86400000)))
    : 0

  return (
    <div className={`bg-white rounded-2xl border shadow-sm overflow-hidden ${
      c.status === 'active' ? 'border-emerald-200 ring-1 ring-emerald-100' : 'border-gray-100'
    }`}>
      {/* Status bar */}
      <div className={`flex items-center justify-between px-4 py-2 text-xs font-bold ${STATUS_COLORS[c.status] || 'bg-gray-50 text-gray-600'}`}>
        <span>{STATUS_ICONS[c.status]} {c.status.toUpperCase()}</span>
        <span>#{c.id}</span>
      </div>

      <div className="p-4 space-y-3">
        <div>
          <div className="font-bold text-field-800 text-sm">{c.listing_title || 'Farm Land'}</div>
          <div className="text-xs text-gray-500">
            📍 {c.listing_village ? `${c.listing_village}, ` : ''}{c.listing_district}, {c.listing_state}
          </div>
          <div className="text-xs text-gray-500">👨‍🌾 Farmer: {c.farmer_name}</div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div className="bg-field-50 rounded-xl p-2 text-center">
            <div className="font-bold text-field-800 text-sm">{c.listing_area_acres}</div>
            <div className="text-[10px] text-gray-500">Acres</div>
          </div>
          <div className="bg-amber-50 rounded-xl p-2 text-center">
            <div className="font-bold text-amber-800 text-sm">{months}m</div>
            <div className="text-[10px] text-gray-500">Duration</div>
          </div>
          <div className="bg-purple-50 rounded-xl p-2 text-center">
            <div className="font-bold text-purple-800 text-sm">₹{c.total_price ? Math.round(c.total_price).toLocaleString() : '—'}</div>
            <div className="text-[10px] text-gray-500">Total</div>
          </div>
        </div>

        <div className="text-xs text-gray-600 flex flex-wrap gap-x-4 gap-y-1">
          <span>📅 {start} → {end}</span>
          {c.agreed_crop && <span>🌱 Crop: <strong>{c.agreed_crop}</strong></span>}
        </div>

        {c.status === 'active' && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs">
            <div className="font-bold text-emerald-800 mb-1">🌾 Your Active Contract</div>
            <p className="text-emerald-700">
              All produce grown on this land between <strong>{start}</strong> and <strong>{end}</strong> belongs to you.
              Coordinate directly with the farmer for sowing and harvesting schedules.
            </p>
          </div>
        )}

        {c.farmer_notes && (
          <div className="text-xs bg-gray-50 rounded-xl px-3 py-2">
            <span className="text-gray-400">Farmer note: </span>{c.farmer_notes}
          </div>
        )}

        <div className="flex gap-2 mt-2">
          {c.status === 'pending' && onCancel && (
            <button onClick={() => onCancel(c.id)}
              className="flex-1 text-xs text-red-600 border border-red-200 hover:bg-red-50 py-2 rounded-xl font-medium transition">
              Cancel Request
            </button>
          )}
          {onOpenChat && (
            <button onClick={() => onOpenChat(c.id)}
              className="flex-1 text-xs border py-2 rounded-xl font-medium hover:bg-gray-50 transition">
              💬 Message Farmer
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function LandContractors() {
  const [tab, setTab] = useState<Tab>('Browse Land')
  const [stats, setStats] = useState<any>({})
  const [listings, setListings] = useState<LandListing[] | null>(null)
  const [contracts, setContracts] = useState<LandContract[] | null>(null)
  const [contactInfo, setContactInfo] = useState<Record<number, any>>({})
  const [selectedListing, setSelectedListing] = useState<LandListing | null>(null)
  const [toastMsg, setToastMsg] = useState('')

  // Messaging State
  const [activeChat, setActiveChat] = useState<number | null>(null)
  const [messages, setMessages] = useState<any[]>([])
  const [msgInput, setMsgInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)

  const loadChat = (contractId: number) => {
    setChatLoading(true)
    getContractMessages(contractId)
      .then(setMessages)
      .catch(() => {})
      .finally(() => setChatLoading(false))
  }

  const handleOpenChat = (contractId: number) => {
    setActiveChat(contractId)
    loadChat(contractId)
  }

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!msgInput.trim() || !activeChat) return
    const txt = msgInput
    setMsgInput('')
    try {
      const newMsg = await sendContractMessage(activeChat, txt)
      setMessages(prev => [...prev, newMsg])
    } catch (err) {
      console.error(err)
    }
  }

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setTimeout(() => setToastMsg(''), 3500)
  }

  useEffect(() => {
    getLandStats().then(setStats).catch(() => {})
    loadListings({})
  }, [])

  useEffect(() => {
    if (tab === 'My Contracts') loadContracts()
  }, [tab])

  const loadListings = (params: any) => {
    setListings(null)
    const clean: any = {}
    if (params.state) clean.state = params.state
    if (params.district) clean.district = params.district
    if (params.soil_type) clean.soil_type = params.soil_type
    if (params.min_acres) clean.min_acres = Number(params.min_acres)
    if (params.max_price) clean.max_price = Number(params.max_price)
    if (params.crop) clean.crop = params.crop
    browseLandListings(clean)
      .then(setListings)
      .catch(() => setListings([]))
  }

  const loadContracts = () => {
    setContracts(null)
    getMyLandContracts().then(setContracts).catch(() => setContracts([]))
  }

  const handleReveal = async (id: number) => {
    if (contactInfo[id]) return
    try {
      const info = await getLandListingContact(id)
      setContactInfo((prev) => ({ ...prev, [id]: info }))
    } catch {
      showToast('Could not retrieve contact info')
    }
  }

  const handleRequestContract = async (payload: any) => {
    await requestLandContract(payload)
    showToast('✅ Contract request sent! The farmer will respond shortly.')
    loadContracts()
  }

  const handleCancelContract = async (id: number) => {
    await cancelLandContract(id)
    showToast('Contract request cancelled.')
    loadContracts()
  }

  const activeContracts = (contracts || []).filter((c) => c.status === 'active')
  const otherContracts = (contracts || []).filter((c) => c.status !== 'active')

  return (
    <div className="max-w-5xl relative">
      {/* Toast */}
      {toastMsg && (
        <div className="fixed top-4 right-4 z-50 bg-field-800 text-white text-sm font-medium px-5 py-3 rounded-2xl shadow-xl animate-bounce-in">
          {toastMsg}
        </div>
      )}

      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-field-800 flex items-center gap-2">
          🏡 Land Contractors
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Rent farmland directly from farmers. For the contract period, everything grown on that land is yours.
        </p>
      </div>

      {/* Stats bar */}
      <StatsBar stats={stats} />

      {/* Tab nav */}
      <div className="flex gap-2 mb-5 bg-gray-100 p-1 rounded-2xl w-fit">
        {TABS.map((t) => (
          <button key={t} onClick={() => { setTab(t); setActiveChat(null) }}
            className={`px-5 py-2 text-sm font-semibold rounded-xl transition-all duration-150 ${
              tab === t
                ? 'bg-white text-field-800 shadow-sm'
                : 'text-gray-500 hover:text-field-700'
            }`}>
            {t === 'Browse Land' ? '🔍 Browse Land' : `📋 My Contracts${contracts ? ` (${contracts.length})` : ''}`}
          </button>
        ))}
      </div>

      {/* ── BROWSE TAB ─────────────────────────────────────────────────────── */}
      {tab === 'Browse Land' && (
        <div>
          <FilterBar onSearch={loadListings} />

          {listings === null ? (
            <div className="flex justify-center py-12"><Spinner /></div>
          ) : listings.length === 0 ? (
            <Card>
              <Empty msg="No land listings match your filters. Try broadening the search or check back later." />
            </Card>
          ) : (
            <>
              <div className="text-xs text-gray-400 mb-3">{listings.length} plot{listings.length !== 1 ? 's' : ''} found</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {listings.map((l) => (
                  <ListingCard
                    key={l.id}
                    listing={l}
                    onRent={setSelectedListing}
                    onReveal={handleReveal}
                    contactInfo={contactInfo}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── CONTRACTS TAB ──────────────────────────────────────────────────── */}
      {tab === 'My Contracts' && (
        <div>
          {activeChat ? (
            <Card className="flex flex-col h-[500px]">
              <div className="flex justify-between items-center mb-4 pb-4 border-b">
                <h3 className="font-bold text-lg">Chat with Farmer</h3>
                <Button variant="outline" onClick={() => setActiveChat(null)}>Back</Button>
              </div>
              <div className="flex-1 overflow-y-auto mb-4 space-y-4 pr-2">
                {chatLoading ? <Spinner /> : messages.length === 0 ? (
                  <p className="text-gray-400 text-center text-sm italic mt-10">No messages yet. Say hello!</p>
                ) : (
                  messages.map(m => (
                    <div key={m.id} className={`flex ${m.is_mine ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[75%] p-3 rounded-2xl ${
                        m.is_mine ? 'bg-field-600 text-white rounded-br-none' : 'bg-gray-100 text-gray-800 rounded-bl-none'
                      }`}>
                        <div className="text-xs opacity-70 mb-1">{m.sender_name}</div>
                        <div className="text-sm whitespace-pre-wrap">{m.content}</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <form onSubmit={handleSendMessage} className="flex gap-2">
                <input
                  type="text"
                  value={msgInput}
                  onChange={e => setMsgInput(e.target.value)}
                  className="flex-1 border rounded-lg px-4 py-2"
                  placeholder="Type a message..."
                />
                <Button type="submit">Send</Button>
              </form>
            </Card>
          ) : contracts === null ? (
            <div className="flex justify-center py-12"><Spinner /></div>
          ) : contracts.length === 0 ? (
            <Card>
              <Empty msg="You haven't requested any land contracts yet. Browse available land and tap 'Request Contract'." />
            </Card>
          ) : (
            <div className="space-y-6">
              {activeContracts.length > 0 && (
                <div>
                  <div className="text-sm font-bold text-emerald-800 mb-3 flex items-center gap-2">
                    <span className="w-2 h-2 bg-emerald-500 rounded-full inline-block animate-pulse" />
                    Active Contracts — Produce is Yours
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {activeContracts.map((c) => (
                      <ContractCard key={c.id} c={c} onOpenChat={handleOpenChat} />
                    ))}
                  </div>
                </div>
              )}

              {otherContracts.length > 0 && (
                <div>
                  <div className="text-sm font-semibold text-gray-600 mb-3">
                    All Contracts
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {otherContracts.map((c) => (
                      <ContractCard key={c.id} c={c} onCancel={handleCancelContract} onOpenChat={handleOpenChat} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Contract request modal */}
      {selectedListing && (
        <ContractRequestModal
          listing={selectedListing}
          onClose={() => setSelectedListing(null)}
          onSubmit={handleRequestContract}
        />
      )}
    </div>
  )
}
