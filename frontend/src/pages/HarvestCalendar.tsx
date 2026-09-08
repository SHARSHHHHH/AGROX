import { useEffect, useState } from 'react'
import { useLanguage } from '../contexts/LanguageContext'
import { getHarvestMessageNotifications, getHarvestMessages, markNotificationRead, sendHarvestMessage } from '../services/api'

export default function HarvestCalendar() {
  const { t } = useLanguage()
  const [harvests, setHarvests] = useState([])
  const [bookings, setBookings] = useState([])
  const [activeChat, setActiveChat] = useState(null)
  const [messages, setMessages] = useState([])
  const [messageText, setMessageText] = useState('')
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({
    crop: '',
    variety: '',
    sowing_date: '',
    expected_harvest_date: '',
    estimated_quantity_kg: '',
    expected_min_price: '',
    expected_max_price: '',
    plot_size_acres: '1.0',
    soil_type: '',
    irrigation_type: '',
    notes: ''
  })

  useEffect(() => {
    fetchHarvests()
  }, [])

  useEffect(() => {
    const loadNotifications = () => getHarvestMessageNotifications().then(setNotifications).catch(() => {})
    loadNotifications()
    const timer = window.setInterval(loadNotifications, 10000)
    return () => window.clearInterval(timer)
  }, [])

  const fetchHarvests = async () => {
    try {
      const headers = {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
      const [harvestResponse, bookingResponse] = await Promise.all([
        fetch('/api/harvest/calendar/my', { headers }),
        fetch('/api/harvest/prebooking/farmer/my', { headers })
      ])
      if (!harvestResponse.ok || !bookingResponse.ok) throw new Error('Failed to load harvests or buyer requests')
      const data = await harvestResponse.json()
      setHarvests(data)
      setBookings(await bookingResponse.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const respondToBooking = async (bookingId, status) => {
    try {
      const response = await fetch(`/api/harvest/prebooking/${bookingId}/respond`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ status, farmer_response: status === 'confirmed' ? 'Request confirmed.' : 'Request declined.' })
      })
      if (!response.ok) {
        const result = await response.json()
        throw new Error(result.detail || 'Failed to update request')
      }
      await fetchHarvests()
    } catch (err) {
      setError(err.message)
    }
  }

  const openChat = async (harvestId) => {
    setActiveChat(harvestId)
    setMessages(await getHarvestMessages(harvestId))
  }

  const sendMessage = async (event) => {
    event.preventDefault()
    if (!activeChat || !messageText.trim()) return
    const message = await sendHarvestMessage(activeChat, messageText.trim())
    setMessages(prev => [...prev, message])
    setMessageText('')
  }

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const response = await fetch('/api/harvest/calendar', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          ...formData,
          estimated_quantity_kg: formData.estimated_quantity_kg ? parseFloat(formData.estimated_quantity_kg) : null,
          expected_min_price: formData.expected_min_price ? parseFloat(formData.expected_min_price) : null,
          expected_max_price: formData.expected_max_price ? parseFloat(formData.expected_max_price) : null,
          plot_size_acres: parseFloat(formData.plot_size_acres) || 1.0
        })
      })
      if (!response.ok) throw new Error('Failed to create harvest')
      setFormData({
        crop: '',
        variety: '',
        sowing_date: '',
        expected_harvest_date: '',
        estimated_quantity_kg: '',
        expected_min_price: '',
        expected_max_price: '',
        plot_size_acres: '1.0',
        soil_type: '',
        irrigation_type: '',
        notes: ''
      })
      setShowForm(false)
      fetchHarvests()
    } catch (err) {
      setError(err.message)
    }
  }

  const getStatusColor = (status) => {
    const colors = {
      'planning': 'bg-blue-100 text-blue-800',
      'growing': 'bg-green-100 text-green-800',
      'ready_for_harvest': 'bg-yellow-100 text-yellow-800',
      'harvested': 'bg-gray-100 text-gray-800',
      'cancelled': 'bg-red-100 text-red-800'
    }
    return colors[status] || 'bg-gray-100 text-gray-800'
  }

  if (loading) return <div className="p-4">Loading...</div>

  return (
    <div className="max-w-6xl mx-auto p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">🌾 {t('harvest.title')}</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded"
        >
          {showForm ? t('harvest.cancel') : `+ ${t('harvest.plan')}`}
        </button>
      </div>

      {notifications.length > 0 && (
        <section className="bg-amber-50 border border-amber-200 p-4 rounded-lg mb-6">
          <h2 className="font-bold mb-2">🔔 New Buyer Messages ({notifications.length})</h2>
          <div className="space-y-2">
            {notifications.map(notification => (
              <button key={notification.id} type="button" onClick={() => { markNotificationRead(notification.id).catch(() => {}); openChat(notification.harvest_id) }} className="block w-full text-left bg-white rounded p-2 hover:bg-amber-100">
                <span className="font-semibold">{notification.sender_name}</span> on {notification.crop}: {notification.content}
              </button>
            ))}
          </div>
        </section>
      )}

      {error && <div className="bg-red-100 text-red-800 p-3 rounded mb-4">{error}</div>}

      <section className="bg-white p-4 rounded-lg shadow mb-6">
        <h2 className="text-xl font-bold mb-4">{t('harvest.buyerRequests')} ({bookings.length})</h2>
        {bookings.length === 0 ? (
          <p className="text-gray-600">{t('harvest.noRequests')}</p>
        ) : (
          <div className="space-y-3">
            {bookings.map(booking => (
              <div key={booking.id} className="border rounded p-3">
                <div className="flex justify-between items-start gap-3">
                  <div>
                    <p className="font-semibold">{booking.crop} {booking.variety && `(${booking.variety})`}</p>
                    <p className="text-sm text-gray-600">{booking.quantity_kg || 'Any'} kg at ₹{booking.agreed_price_per_kg || 'negotiable'} / kg</p>
                    <p className="text-sm text-gray-600">Delivery: {booking.delivery_location || 'Not specified'}</p>
                    {booking.buyer_message && <p className="text-sm mt-2">“{booking.buyer_message}”</p>}
                  </div>
                  <span className={`px-3 py-1 rounded text-sm font-semibold ${getStatusColor(booking.status)}`}>
                    {booking.status.toUpperCase()}
                  </span>
                </div>
                {booking.status === 'requested' && (
                  <div className="flex gap-2 mt-3">
                    <button type="button" onClick={() => respondToBooking(booking.id, 'confirmed')} className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded">Confirm</button>
                    <button type="button" onClick={() => respondToBooking(booking.id, 'declined')} className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded">Decline</button>
                  </div>
                )}
                <button type="button" onClick={() => openChat(booking.harvest_id)} className="mt-3 text-green-700 font-semibold">💬 {t('harvest.messageBuyer')}</button>
              </div>
            ))}
          </div>
        )}
      </section>

      {activeChat && (
        <section className="bg-white p-4 rounded-lg shadow mb-6">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-xl font-bold">Messages</h2>
            <button type="button" onClick={() => setActiveChat(null)} className="text-gray-600">Close</button>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto mb-3">
            {messages.length === 0 && <p className="text-gray-500">Start the conversation with the buyer.</p>}
            {messages.map(message => (
              <div key={message.id} className={`p-2 rounded ${message.is_mine ? 'bg-green-100 ml-8' : 'bg-gray-100 mr-8'}`}>
                <p className="text-xs text-gray-500">{message.sender_name}</p>
                <p>{message.content}</p>
              </div>
            ))}
          </div>
          <form onSubmit={sendMessage} className="flex gap-2">
            <input value={messageText} onChange={event => setMessageText(event.target.value)} className="flex-1 border rounded p-2" placeholder="Write a message to the buyer" />
            <button type="submit" className="bg-green-600 text-white px-4 py-2 rounded">Send</button>
          </form>
        </section>
      )}

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white p-6 rounded-lg shadow mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold mb-2">Crop *</label>
              <input
                type="text"
                name="crop"
                value={formData.crop}
                onChange={handleInputChange}
                required
                className="w-full border rounded p-2"
                placeholder="e.g., Tomato"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Variety</label>
              <input
                type="text"
                name="variety"
                value={formData.variety}
                onChange={handleInputChange}
                className="w-full border rounded p-2"
                placeholder="e.g., Roma"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Sowing Date</label>
              <input
                type="date"
                name="sowing_date"
                value={formData.sowing_date}
                onChange={handleInputChange}
                className="w-full border rounded p-2"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Expected Harvest Date *</label>
              <input
                type="date"
                name="expected_harvest_date"
                value={formData.expected_harvest_date}
                onChange={handleInputChange}
                required
                className="w-full border rounded p-2"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Estimated Quantity (kg)</label>
              <input
                type="number"
                name="estimated_quantity_kg"
                value={formData.estimated_quantity_kg}
                onChange={handleInputChange}
                step="0.1"
                className="w-full border rounded p-2"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Plot Size (acres)</label>
              <input
                type="number"
                name="plot_size_acres"
                value={formData.plot_size_acres}
                onChange={handleInputChange}
                step="0.1"
                className="w-full border rounded p-2"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Min Price per kg (₹)</label>
              <input
                type="number"
                name="expected_min_price"
                value={formData.expected_min_price}
                onChange={handleInputChange}
                step="0.01"
                className="w-full border rounded p-2"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Max Price per kg (₹)</label>
              <input
                type="number"
                name="expected_max_price"
                value={formData.expected_max_price}
                onChange={handleInputChange}
                step="0.01"
                className="w-full border rounded p-2"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Soil Type</label>
              <input
                type="text"
                name="soil_type"
                value={formData.soil_type}
                onChange={handleInputChange}
                className="w-full border rounded p-2"
                placeholder="e.g., Loamy"
              />
            </div>
            <div>
              <label className="block font-semibold mb-2">Irrigation Type</label>
              <input
                type="text"
                name="irrigation_type"
                value={formData.irrigation_type}
                onChange={handleInputChange}
                className="w-full border rounded p-2"
                placeholder="e.g., Drip"
              />
            </div>
          </div>
          <div className="mt-4">
            <label className="block font-semibold mb-2">Notes</label>
            <textarea
              name="notes"
              value={formData.notes}
              onChange={handleInputChange}
              className="w-full border rounded p-2"
              rows={3}
              placeholder="Any additional details about this harvest..."
            />
          </div>
          <button
            type="submit"
            className="mt-4 bg-green-600 hover:bg-green-700 text-white px-6 py-2 rounded"
          >
            Save Harvest Plan
          </button>
        </form>
      )}

      {harvests.length === 0 ? (
        <div className="bg-gray-100 p-6 rounded text-center">
          <p className="text-gray-600">No harvest plans yet. Create one to get started!</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {harvests.map(harvest => (
            <div key={harvest.id} className="bg-white p-4 rounded-lg shadow">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="text-xl font-bold">{harvest.crop} {harvest.variety && `(${harvest.variety})`}</h3>
                  <p className="text-gray-600 text-sm">Plot: {harvest.plot_size_acres} acres</p>
                </div>
                <span className={`px-3 py-1 rounded text-sm font-semibold ${getStatusColor(harvest.status)}`}>
                  {harvest.status.replace('_', ' ').toUpperCase()}
                </span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                {harvest.sowing_date && (
                  <div>
                    <p className="text-gray-500">Sowing Date</p>
                    <p className="font-semibold">{new Date(harvest.sowing_date).toLocaleDateString()}</p>
                  </div>
                )}
                <div>
                  <p className="text-gray-500">Expected Harvest</p>
                  <p className="font-semibold">{new Date(harvest.expected_harvest_date).toLocaleDateString()}</p>
                </div>
                {harvest.estimated_quantity_kg && (
                  <div>
                    <p className="text-gray-500">Estimated Qty</p>
                    <p className="font-semibold">{harvest.estimated_quantity_kg.toLocaleString()} kg</p>
                  </div>
                )}
                {harvest.expected_min_price && (
                  <div>
                    <p className="text-gray-500">Expected Price</p>
                    <p className="font-semibold">₹{harvest.expected_min_price} - ₹{harvest.expected_max_price}</p>
                  </div>
                )}
              </div>
              {harvest.notes && (
                <p className="text-gray-700 mt-3 pt-3 border-t">{harvest.notes}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
