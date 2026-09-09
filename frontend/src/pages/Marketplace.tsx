import { useEffect, useState } from 'react'
import { getAvailableCrops, browseListings, revealListingContact, expressInterest } from '../services/api'
import { Card, Spinner, StatusPill, Empty } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

const STATUS_PILL: Record<string, string> = { growing: 'INFO', available: 'OPTIMAL' }

const CROP_ICONS: Record<string, string> = {
  soybean: '🌱', wheat: '🌾', chickpea: '🫘', maize: '🌽', cotton: '☁️',
  rice: '🍚', tomato: '🍅', onion: '🧅', potato: '🥔', chilli: '🌶️',
}

/**
 * Buyer-facing marketplace. Buyers pick a crop by its icon rather than
 * typing a search — tapping a crop expands to show it grouped by STATE
 * (the same crop is often listed by farmers in several states), and within
 * each state, by variety (Local/Hybrid/Organic/...), with the farmer's own
 * photo where they've uploaded one.
 */
export default function Marketplace() {
  const { tv } = useLanguage()
  const { publish } = usePageContext()
  const [crops, setCrops] = useState<any[] | null>(null)
  const [openCrop, setOpenCrop] = useState<string | null>(null)
  const [listings, setListings] = useState<any[]>([])
  const [loadingListings, setLoadingListings] = useState(false)
  const [contact, setContact] = useState<any>(null)
  const [interested, setInterested] = useState<Record<number, boolean>>({})
  const [qty, setQty] = useState<Record<number, string>>({})
  const [showSearch, setShowSearch] = useState(false)
  const [filters, setFilters] = useState({ crop: '', state: '', district: '', max_price: '' })
  const [searchResults, setSearchResults] = useState<any[] | null>(null)

  useEffect(() => {
    getAvailableCrops().then((cs) => {
      setCrops(cs)
      publish('Marketplace', cs.length
        ? `Crops currently available to buy: ${cs.map((c: any) => `${c.crop} (${c.listings} listing(s))`).join(', ')}.`
        : 'No crops currently listed for sale.')
    }).catch(() => setCrops([]))
  }, [])

  const openCropBox = async (crop: string) => {
    if (openCrop === crop) { setOpenCrop(null); return }
    setOpenCrop(crop)
    setLoadingListings(true)
    try {
      const res = await browseListings({ crop })
      setListings(res)
    } finally {
      setLoadingListings(false)
    }
  }

  const doContact = async (id: number) => {
    const res = await revealListingContact(id)
    setContact({ id, ...res })
  }
  const doInterest = async (id: number) => {
    await expressInterest(id, { quantity_kg: qty[id] ? Number(qty[id]) : null })
    setInterested((m) => ({ ...m, [id]: true }))
  }

  const runSearch = () => {
    const params: any = {}
    if (filters.crop) params.crop = filters.crop
    if (filters.state) params.state = filters.state
    if (filters.district) params.district = filters.district
    if (filters.max_price) params.max_price = Number(filters.max_price)
    browseListings(params).then(setSearchResults).catch(() => setSearchResults([]))
  }

  // Group the open crop's listings by state, then by variety within state —
  // this is the "same crop, different states, different types" view.
  const byState: Record<string, Record<string, any[]>> = {}
  for (const l of listings) {
    const state = l.state || 'Unknown state'
    const variety = l.variety || 'Unspecified'
    byState[state] = byState[state] || {}
    byState[state][variety] = byState[state][variety] || []
    byState[state][variety].push(l)
  }

  const ListingCard = ({ l }: { l: any }) => (
    <Card className="!p-3">
      <div className="flex gap-3">
        {l.image_url ? (
          <img src={l.image_url} alt={l.crop} className="w-16 h-16 object-cover rounded-lg border shrink-0" />
        ) : (
          <div className="w-16 h-16 rounded-lg border bg-gray-50 flex items-center justify-center text-2xl shrink-0">
            {CROP_ICONS[l.crop] || '🥬'}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="font-semibold text-sm text-field-800 truncate">
              {tv(l.crop)} {l.variety && <span className="text-gray-400 font-normal">· {l.variety}</span>}
            </div>
            <StatusPill status={STATUS_PILL[l.status] || 'INFO'} />
          </div>
          <div className="text-xs text-gray-500">{l.district || l.state} · Farmer: {l.farmer_name}</div>
          <div className="text-sm mt-0.5">
            {l.quantity_kg && <span>📦 {l.quantity_kg} kg</span>}
            {l.price_per_kg && <span className="font-bold text-field-700"> · ₹{l.price_per_kg}/kg</span>}
          </div>
          {l.predicted_maturity_date && (
            <div className="text-xs text-gray-400">
              {l.status === 'available' ? 'Ready now' : `Ready ~${l.predicted_maturity_date}`}
            </div>
          )}
        </div>
      </div>

      <div className="mt-2 flex gap-2">
        <input type="number" min="0" placeholder="kg needed"
          value={qty[l.id] || ''}
          onChange={(e) => setQty((m) => ({ ...m, [l.id]: e.target.value }))}
          className="flex-1 border rounded-lg px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-field-600" />
        <button onClick={() => doInterest(l.id)} disabled={!!interested[l.id]}
          className="text-xs font-semibold bg-field-600 text-white px-2.5 py-1.5 rounded-lg disabled:opacity-50">
          {interested[l.id] ? '✓ Sent' : "I'm interested"}
        </button>
      </div>
      <button onClick={() => doContact(l.id)}
        className="mt-1.5 text-xs font-semibold bg-white border w-full py-1.5 rounded-lg hover:bg-gray-50">
        📞 Show farmer's contact
      </button>
      {contact?.id === l.id && (
        <div className="mt-2 bg-field-50 rounded-lg p-2 text-xs">
          <div className="font-semibold">{contact.farmer_name}</div>
          <div>{contact.contact_phone}</div>
          <p className="text-gray-500 mt-1">{contact.safety_note}</p>
        </div>
      )}
    </Card>
  )

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">🛒 Buy Crops</h1>
      <p className="text-sm text-gray-500 mb-5">
        Tap a crop to see what's available, in which states, and from which farmers — no mandi trip, no middleman.
      </p>

      {crops === null ? <Spinner /> : crops.length === 0 ? (
        <Card><Empty msg="No crops are listed for sale right now — check back soon." /></Card>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-3 mb-6">
          {crops.map((c: any) => (
            <button key={c.crop} onClick={() => openCropBox(c.crop)}
              className={`aspect-square rounded-2xl border-2 flex flex-col items-center justify-center gap-1 transition
                ${openCrop === c.crop ? 'border-field-600 bg-field-50' : 'border-gray-200 bg-white hover:border-field-300'}`}>
              <span className="text-3xl">{CROP_ICONS[c.crop] || '🥬'}</span>
              <span className="text-xs font-semibold text-field-800 capitalize">{tv(c.crop)}</span>
              <span className="text-[10px] text-gray-400">{c.listings} listing(s)</span>
            </button>
          ))}
        </div>
      )}

      {openCrop && (
        <Card className="mb-6">
          <h3 className="font-semibold text-field-800 mb-3">
            {CROP_ICONS[openCrop] || '🥬'} {tv(openCrop)} — available by state
          </h3>
          {loadingListings ? <Spinner /> : Object.keys(byState).length === 0 ? (
            <Empty msg="No current listings for this crop." />
          ) : (
            <div className="space-y-5">
              {Object.entries(byState).map(([state, varieties]) => (
                <div key={state}>
                  <div className="text-sm font-semibold text-gray-600 mb-2">📍 {state}</div>
                  {Object.entries(varieties).map(([variety, items]) => (
                    <div key={variety} className="mb-3">
                      <div className="text-xs text-gray-400 mb-1.5 pl-1">Type: {variety}</div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {items.map((l) => <ListingCard key={l.id} l={l} />)}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Optional broader search, for a buyer who wants to filter across
          crops/states/price rather than browse crop-by-crop. */}
      <button onClick={() => setShowSearch(!showSearch)}
        className="text-xs text-field-600 font-semibold underline underline-offset-2 mb-3">
        {showSearch ? 'Hide' : 'Or search all listings by filters'}
      </button>
      {showSearch && (
        <Card>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <input placeholder="Crop" value={filters.crop}
              onChange={(e) => setFilters({ ...filters, crop: e.target.value })}
              className="border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            <input placeholder="State" value={filters.state}
              onChange={(e) => setFilters({ ...filters, state: e.target.value })}
              className="border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            <input placeholder="District" value={filters.district}
              onChange={(e) => setFilters({ ...filters, district: e.target.value })}
              className="border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            <input placeholder="Max ₹/kg" type="number" value={filters.max_price}
              onChange={(e) => setFilters({ ...filters, max_price: e.target.value })}
              className="border rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600" />
          </div>
          <button onClick={runSearch}
            className="mt-3 text-xs font-semibold bg-field-600 text-white px-4 py-2 rounded-xl">
            Search
          </button>
          {searchResults !== null && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-4">
              {searchResults.length === 0 ? <Empty msg="No listings match those filters." /> :
                searchResults.map((l) => <ListingCard key={l.id} l={l} />)}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
