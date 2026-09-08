import { useEffect, useState } from 'react'
import { useLanguage } from '../contexts/LanguageContext'
import { getHarvestMessageNotifications, getHarvestMessages, markNotificationRead, sendHarvestMessage } from '../services/api'

export default function PreBooking() {
  const { t } = useLanguage()
  const [harvests, setHarvests] = useState([])
  const [myBookings, setMyBookings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedHarvest, setSelectedHarvest] = useState(null)
  const [showBookingForm, setShowBookingForm] = useState(false)
  const [activeTab, setActiveTab] = useState('available') // available | my-bookings
  const [formData, setFormData] = useState({
    quantity_kg: '',
    agreed_price_per_kg: '',
    delivery_date: '',
    delivery_location: '',
    buyer_message: ''
  })
  const [activeChat, setActiveChat] = useState(null)
  const [messages, setMessages] = useState([])
  const [messageText, setMessageText] = useState('')
  const [notifications, setNotifications] = useState([])

  useEffect(() => {
    fetchData()
  }, [])

  useEffect(() => {
    const loadNotifications = () => getHarvestMessageNotifications().then(setNotifications).catch(() => {})
    loadNotifications()
    const timer = window.setInterval(loadNotifications, 10000)
    return () => window.clearInterval(timer)
  }, [])

  const fetchData = async () => {
    try {
      const [harvestRes, bookingsRes] = await Promise.all([
        fetch('/api/harvest/available', {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        }),
        fetch('/api/harvest/prebooking/my', {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        })
      ])
      
      if (!harvestRes.ok || !bookingsRes.ok) throw new Error('Unable to load live harvest data')
      setHarvests(await harvestRes.json())
      setMyBookings(await bookingsRes.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmitBooking = async (e) => {
    e.preventDefault()
    if (!selectedHarvest) return

    try {
      const response = await fetch(`/api/harvest/prebooking?harvest_id=${selectedHarvest.id}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          ...formData,
          quantity_kg: formData.quantity_kg ? parseFloat(formData.quantity_kg) : null,
          agreed_price_per_kg: formData.agreed_price_per_kg ? parseFloat(formData.agreed_price_per_kg) : null
        })
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to create pre-booking')
      }

      setFormData({
        quantity_kg: '',
        agreed_price_per_kg: '',
        delivery_date: '',
        delivery_location: '',
        buyer_message: ''
      })
      setSelectedHarvest(null)
      setShowBookingForm(false)
      fetchData()
    } catch (err) {
      setError(err.message)
    }
  }

  const openChat = async (harvestId) => {
    setActiveChat(harvestId)
    setMessages(await getHarvestMessages(harvestId))
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!activeChat || !messageText.trim()) return
    const message = await sendHarvestMessage(activeChat, messageText.trim())
    setMessages(prev => [...prev, message])
    setMessageText('')
  }

  const getStatusColor = (status) => {
    const colors = {
      'planning': 'bg-blue-100 text-blue-800',
      'growing': 'bg-green-100 text-green-800',
      'ready_for_harvest': 'bg-yellow-100 text-yellow-800',
      'harvested': 'bg-gray-100 text-gray-800',
      'cancelled': 'bg-red-100 text-red-800',
      'requested': 'bg-blue-100 text-blue-800',
      'confirmed': 'bg-green-100 text-green-800',
      'declined': 'bg-red-100 text-red-800',
      'completed': 'bg-gray-100 text-gray-800'
    }
    return colors[status] || 'bg-gray-100 text-gray-800'
  }

  if (loading) return <div className="p-4">Loading...</div>

  return (
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-3xl font-bold mb-6">📅 {t('booking.title')}</h1>

      {notifications.length > 0 && (
        <section className="bg-amber-50 border border-amber-200 p-4 rounded-lg mb-6">
          <h2 className="font-bold mb-2">🔔 New Farmer Messages ({notifications.length})</h2>
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

      {/* Tabs */}
      <div className="flex gap-4 mb-6 border-b">
        <button
          onClick={() => setActiveTab('available')}
          className={`px-4 py-2 font-semibold ${
            activeTab === 'available'
              ? 'border-b-2 border-green-600 text-green-600'
              : 'text-gray-600'
          }`}
        >
          {t('booking.available')} ({harvests.length})
        </button>
        <button
          onClick={() => setActiveTab('my-bookings')}
          className={`px-4 py-2 font-semibold ${
            activeTab === 'my-bookings'
              ? 'border-b-2 border-green-600 text-green-600'
              : 'text-gray-600'
          }`}
        >
          {t('booking.my')} ({myBookings.length})
        </button>
      </div>

      {/* Available Harvests Tab */}
      {activeTab === 'available' && (
        <div>
          {harvests.length === 0 ? (
            <div className="bg-gray-100 p-6 rounded text-center">
              <p className="text-gray-600">{t('booking.noAvailable')}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {harvests.map(harvest => (
                <div key={harvest.id} className="bg-white p-4 rounded-lg shadow hover:shadow-lg transition">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <h3 className="text-xl font-bold">{harvest.crop} {harvest.variety && `(${harvest.variety})`}</h3>
                      <p className="text-gray-600 text-sm">Plot: {harvest.plot_size_acres} acres</p>
                    </div>
                    <span className={`px-3 py-1 rounded text-sm font-semibold ${getStatusColor(harvest.status)}`}>
                      {harvest.status.replace('_', ' ').toUpperCase()}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
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
                        <p className="text-gray-500">Est. Quantity</p>
                        <p className="font-semibold">{harvest.estimated_quantity_kg.toLocaleString()} kg</p>
                      </div>
                    )}
                    {harvest.expected_min_price && (
                      <div>
                        <p className="text-gray-500">Price Range</p>
                        <p className="font-semibold">₹{harvest.expected_min_price} - ₹{harvest.expected_max_price}</p>
                      </div>
                    )}
                  </div>

                  {harvest.notes && (
                    <p className="text-gray-700 mb-3 pt-3 border-t">{harvest.notes}</p>
                  )}

                  {selectedHarvest?.id === harvest.id && showBookingForm ? (
                    <form onSubmit={handleSubmitBooking} className="bg-blue-50 p-4 rounded mt-4">
                      <h4 className="font-bold mb-3">Submit Pre-Booking Request</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block font-semibold mb-2">Quantity (kg)</label>
                          <input
                            type="number"
                            name="quantity_kg"
                            value={formData.quantity_kg}
                            onChange={handleInputChange}
                            step="0.1"
                            className="w-full border rounded p-2"
                            placeholder="How much do you need?"
                          />
                        </div>
                        <div>
                          <label className="block font-semibold mb-2">Agreed Price per kg (₹)</label>
                          <input
                            type="number"
                            name="agreed_price_per_kg"
                            value={formData.agreed_price_per_kg}
                            onChange={handleInputChange}
                            step="0.01"
                            className="w-full border rounded p-2"
                            placeholder="Your offer price"
                          />
                        </div>
                        <div>
                          <label className="block font-semibold mb-2">Delivery Date</label>
                          <input
                            type="date"
                            name="delivery_date"
                            value={formData.delivery_date}
                            onChange={handleInputChange}
                            className="w-full border rounded p-2"
                          />
                        </div>
                        <div>
                          <label className="block font-semibold mb-2">Delivery Location</label>
                          <input
                            type="text"
                            name="delivery_location"
                            value={formData.delivery_location}
                            onChange={handleInputChange}
                            className="w-full border rounded p-2"
                            placeholder="Where should it be delivered?"
                          />
                        </div>
                      </div>
                      <div className="mt-4">
                        <label className="block font-semibold mb-2">Message to Farmer</label>
                        <textarea
                          name="buyer_message"
                          value={formData.buyer_message}
                          onChange={handleInputChange}
                          className="w-full border rounded p-2"
                          rows={3}
                          placeholder="Any special requirements or details..."
                        />
                      </div>
                      <div className="flex gap-2 mt-4">
                        <button
                          type="submit"
                          className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded"
                        >
                          {t('booking.sendRequest')}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowBookingForm(false)
                            setSelectedHarvest(null)
                          }}
                          className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  ) : (
                    <div className="mt-4 flex gap-3 flex-wrap">
                      <button
                        onClick={() => {
                          setSelectedHarvest(harvest)
                          setShowBookingForm(true)
                        }}
                        className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded"
                      >
                        Pre-Book This Harvest
                      </button>
                      {myBookings.some(booking => booking.harvest_id === harvest.id) && (
                        <button type="button" onClick={() => openChat(harvest.id)} className="text-green-700 font-semibold px-2 py-2">
                          💬 {t('booking.messageFarmer')}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeChat && (
        <section className="bg-white p-4 rounded-lg shadow mt-6">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-xl font-bold">{t('messages.title')}</h2>
            <button type="button" onClick={() => setActiveChat(null)} className="text-gray-600">{t('common.close')}</button>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto mb-3">
            {messages.length === 0 && <p className="text-gray-500">Start the conversation with the farmer.</p>}
            {messages.map(message => (
              <div key={message.id} className={`p-2 rounded ${message.is_mine ? 'bg-blue-100 ml-8' : 'bg-gray-100 mr-8'}`}>
                <p className="text-xs text-gray-500">{message.sender_name}</p>
                <p>{message.content}</p>
              </div>
            ))}
          </div>
          <form onSubmit={sendMessage} className="flex gap-2">
            <input value={messageText} onChange={e => setMessageText(e.target.value)} className="flex-1 border rounded p-2" placeholder="Write a message to the farmer" />
            <button type="submit" className="bg-green-600 text-white px-4 py-2 rounded">{t('messages.send')}</button>
          </form>
        </section>
      )}

      {/* My Pre-Bookings Tab */}
      {activeTab === 'my-bookings' && (
        <div>
          {myBookings.length === 0 ? (
            <div className="bg-gray-100 p-6 rounded text-center">
              <p className="text-gray-600">{t('booking.noBookings')}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {myBookings.map(booking => (
                <div key={booking.id} className="bg-white p-4 rounded-lg shadow">
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-lg font-bold">Booking #{booking.id}</h3>
                    <span className={`px-3 py-1 rounded text-sm font-semibold ${getStatusColor(booking.status)}`}>
                      {booking.status.toUpperCase()}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                    {booking.quantity_kg && (
                      <div>
                        <p className="text-gray-500">Quantity</p>
                        <p className="font-semibold">{booking.quantity_kg} kg</p>
                      </div>
                    )}
                    {booking.agreed_price_per_kg && (
                      <div>
                        <p className="text-gray-500">Agreed Price</p>
                        <p className="font-semibold">₹{booking.agreed_price_per_kg}/kg</p>
                      </div>
                    )}
                    {booking.delivery_date && (
                      <div>
                        <p className="text-gray-500">Delivery Date</p>
                        <p className="font-semibold">{new Date(booking.delivery_date).toLocaleDateString()}</p>
                      </div>
                    )}
                    <div>
                      <p className="text-gray-500">Requested</p>
                      <p className="font-semibold">{new Date(booking.created_at).toLocaleDateString()}</p>
                    </div>
                  </div>

                  {booking.delivery_location && (
                    <p className="text-gray-700 mb-2">
                      <span className="font-semibold">Delivery Location:</span> {booking.delivery_location}
                    </p>
                  )}

                  {booking.buyer_message && (
                    <p className="text-gray-700 mb-2">
                      <span className="font-semibold">Your Message:</span> {booking.buyer_message}
                    </p>
                  )}

                  {booking.farmer_response && (
                    <p className="text-gray-700 bg-gray-50 p-2 rounded mb-2">
                      <span className="font-semibold">Farmer's Response:</span> {booking.farmer_response}
                    </p>
                  )}

                  <button
                    type="button"
                    onClick={() => openChat(booking.harvest_id)}
                    className="text-green-700 font-semibold mt-2"
                  >
                    💬 Message Farmer
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
