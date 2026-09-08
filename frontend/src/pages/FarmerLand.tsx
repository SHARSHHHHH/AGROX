import { useEffect, useState } from 'react'
import {
  createLandListing, getMyLandListings, getIncomingLandContracts,
  respondToLandContract, getContractMessages, sendContractMessage
} from '../services/api'
import { Card, Button, Spinner, StatusPill } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800 border-amber-200',
  active: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  completed: 'bg-blue-100 text-blue-800 border-blue-200',
  cancelled: 'bg-red-100 text-red-800 border-red-200',
  available: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  rented: 'bg-blue-100 text-blue-800 border-blue-200',
  withdrawn: 'bg-gray-100 text-gray-800 border-gray-200',
}

export default function FarmerLand() {
  const { t } = useLanguage()
  const [tab, setTab] = useState<'upload' | 'myland' | 'requests'>('upload')
  const [listings, setListings] = useState<any[]>([])
  const [requests, setRequests] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // Upload Form State
  const [form, setForm] = useState({
    area_acres: '', soil_type: 'Red', water_source: 'Rainfed',
    irrigation_available: false, suitable_crops: '', price_per_acre_per_season: '',
    contact_phone: ''
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // Messaging State
  const [activeChat, setActiveChat] = useState<number | null>(null)
  const [messages, setMessages] = useState<any[]>([])
  const [msgInput, setMsgInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)

  useEffect(() => {
    Promise.all([getMyLandListings(), getIncomingLandContracts()])
      .then(([ls, rs]) => {
        setListings(ls)
        setRequests(rs)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

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

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    try {
      const created = await createLandListing({
        ...form,
        area_acres: Number(form.area_acres),
        price_per_acre_per_season: Number(form.price_per_acre_per_season),
        suitable_crops: form.suitable_crops.split(',').map(s => s.trim()).filter(Boolean)
      })
      setListings([created, ...listings])
      setSaved(true)
      setForm({
        area_acres: '', soil_type: 'Red', water_source: 'Rainfed',
        irrigation_available: false, suitable_crops: '', price_per_acre_per_season: '',
        contact_phone: ''
      })
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const handleRespond = async (contractId: number, action: 'accept' | 'decline') => {
    try {
      const updated = await respondToLandContract(contractId, { action })
      setRequests(reqs => reqs.map(r => r.id === contractId ? updated : r))
    } catch (err) {
      console.error(err)
    }
  }

  if (loading) return <div className="p-8 text-center"><Spinner /></div>

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 fade-in">
      <h1 className="text-2xl font-bold text-field-900 mb-2">{t('fland.title')}</h1>
      <p className="text-field-600 mb-6">{t('fland.subtitle')}</p>

      {/* Tabs */}
      <div className="flex bg-white rounded-xl shadow-sm p-1 mb-6 border border-field-100">
        {[
          { id: 'upload', label: t('fland.tab.upload') },
          { id: 'myland', label: t('fland.tab.myland') },
          { id: 'requests', label: t('fland.tab.requests') }
        ].map(tb => (
          <button
            key={tb.id}
            onClick={() => { setTab(tb.id as any); setActiveChat(null) }}
            className={`flex-1 py-2 text-sm font-semibold rounded-lg transition-colors ${
              tab === tb.id ? 'bg-earth-100 text-earth-800' : 'text-field-500 hover:bg-field-50'
            }`}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {activeChat ? (
        <Card className="flex flex-col h-[500px]">
          <div className="flex justify-between items-center mb-4 pb-4 border-b">
            <h3 className="font-bold text-lg">Chat with Buyer</h3>
            <Button variant="outline" onClick={() => setActiveChat(null)}>Back</Button>
          </div>
          <div className="flex-1 overflow-y-auto mb-4 space-y-4 pr-2">
            {chatLoading ? <Spinner /> : messages.length === 0 ? (
              <p className="text-gray-400 text-center text-sm italic mt-10">No messages yet. Say hello!</p>
            ) : (
              messages.map(m => (
                <div key={m.id} className={`flex ${m.is_mine ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[75%] p-3 rounded-2xl ${
                    m.is_mine ? 'bg-earth-600 text-white rounded-br-none' : 'bg-gray-100 text-gray-800 rounded-bl-none'
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
      ) : tab === 'upload' ? (
        <Card>
          <form onSubmit={handleUpload} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold text-field-700 mb-1">Area (Acres)</label>
                <input required type="number" step="0.1" className="w-full border rounded-lg px-3 py-2"
                  value={form.area_acres} onChange={e => setForm({...form, area_acres: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-semibold text-field-700 mb-1">Price per season (₹/acre)</label>
                <input required type="number" className="w-full border rounded-lg px-3 py-2"
                  value={form.price_per_acre_per_season} onChange={e => setForm({...form, price_per_acre_per_season: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-semibold text-field-700 mb-1">Soil Type</label>
                <select className="w-full border rounded-lg px-3 py-2"
                  value={form.soil_type} onChange={e => setForm({...form, soil_type: e.target.value})}>
                  <option>Red</option><option>Black</option><option>Alluvial</option><option>Loamy</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold text-field-700 mb-1">Water Source</label>
                <select className="w-full border rounded-lg px-3 py-2"
                  value={form.water_source} onChange={e => setForm({...form, water_source: e.target.value})}>
                  <option>Borewell</option><option>Canal</option><option>Rainfed</option><option>Tank</option>
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className="block text-sm font-semibold text-field-700 mb-1">Suitable Crops (comma separated)</label>
                <input required type="text" placeholder="e.g. Tomato, Onion, Cotton" className="w-full border rounded-lg px-3 py-2"
                  value={form.suitable_crops} onChange={e => setForm({...form, suitable_crops: e.target.value})} />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-sm font-semibold text-field-700 mb-1">Contact Phone</label>
                <input required type="tel" className="w-full border rounded-lg px-3 py-2"
                  value={form.contact_phone} onChange={e => setForm({...form, contact_phone: e.target.value})} />
              </div>
            </div>
            <Button type="submit" disabled={saving} className="w-full mt-4">
              {saving ? <Spinner /> : 'Upload Land for Contract'}
            </Button>
            {saved && <div className="text-emerald-600 font-medium text-center mt-2">Land uploaded successfully!</div>}
          </form>
        </Card>
      ) : tab === 'myland' ? (
        <div className="space-y-4">
          {listings.length === 0 ? <p className="text-center text-gray-500 py-8">You haven't uploaded any land yet.</p> : null}
          {listings.map(l => (
            <Card key={l.id} className="flex justify-between items-center">
              <div>
                <div className="font-bold text-lg">{l.area_acres} Acres in {l.village}, {l.district}</div>
                <div className="text-sm text-gray-500">{l.suitable_crops.join(', ')} • ₹{l.price_per_acre_per_season}/acre/season</div>
              </div>
              <StatusPill status={l.status} colors={STATUS_COLORS} />
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {requests.length === 0 ? <p className="text-center text-gray-500 py-8">No requests from buyers yet.</p> : null}
          {requests.map(r => (
            <Card key={r.id}>
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="font-bold text-lg">Request from {r.buyer_name}</h3>
                  <div className="text-sm text-gray-500">
                    For {r.listing_area_acres} Acres in {r.listing_village} • Crop: {r.agreed_crop}
                  </div>
                </div>
                <StatusPill status={r.status} colors={STATUS_COLORS} />
              </div>
              
              <div className="bg-gray-50 p-4 rounded-lg mb-4 text-sm">
                <div className="grid grid-cols-2 gap-4">
                  <div><strong>Total Offer:</strong> ₹{r.total_price}</div>
                  <div><strong>Start Date:</strong> {new Date(r.start_date).toLocaleDateString()}</div>
                </div>
              </div>

              <div className="flex gap-2">
                {r.status === 'pending' && (
                  <>
                    <Button onClick={() => handleRespond(r.id, 'accept')} className="bg-emerald-600 hover:bg-emerald-700">Accept</Button>
                    <Button variant="outline" onClick={() => handleRespond(r.id, 'decline')} className="text-red-600 border-red-200 hover:bg-red-50">Decline</Button>
                  </>
                )}
                <Button variant="outline" onClick={() => handleOpenChat(r.id)}>
                  💬 Message Buyer
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
