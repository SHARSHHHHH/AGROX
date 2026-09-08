import { useEffect, useState } from 'react'
import { getMyOrders } from '../services/api'
import { Card, Spinner, StatusPill } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

const STATUS_PILL: Record<string, string> = {
  requested: 'WARNING', confirmed: 'OPTIMAL', declined: 'CRITICAL', completed: 'Good',
}

export default function MyOrders() {
  const { tv } = useLanguage()
  const { publish } = usePageContext()
  const [orders, setOrders] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMyOrders().then((res) => {
      setOrders(res)
      publish('My Orders', res.length
        ? `${res.length} order request(s): ` + res.map((o: any) =>
            `${o.listing?.crop || 'unknown crop'} from ${o.listing?.farmer_name || 'unknown farmer'} — ${o.status}`).join('; ')
        : 'No order requests sent yet.')
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">📦 My Orders</h1>
      <p className="text-sm text-gray-500 mb-5">Requests you've sent to farmers.</p>

      {loading ? <Spinner /> : orders.length === 0 ? (
        <Card><p className="text-sm text-gray-400 text-center">
          No requests yet — browse the <a href="/marketplace" className="text-field-600 font-semibold">marketplace</a> to get started.
        </p></Card>
      ) : (
        <div className="space-y-3">
          {orders.map((o) => (
            <Card key={o.id}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold text-field-800">
                    {o.listing ? tv(o.listing.crop) : 'Listing removed'}
                    {o.listing?.variety && <span className="text-gray-400 font-normal"> ({o.listing.variety})</span>}
                  </div>
                  <div className="text-xs text-gray-500">
                    {o.quantity_kg ? `${o.quantity_kg} kg requested` : 'Quantity not specified'}
                    {o.listing?.price_per_kg ? ` · ₹${o.listing.price_per_kg}/kg` : ''}
                  </div>
                  <div className="text-xs text-gray-400">Farmer: {o.listing?.farmer_name}</div>
                </div>
                <StatusPill status={STATUS_PILL[o.status] || 'INFO'} />
              </div>
              {o.message && <p className="text-xs text-gray-500 mt-2">"{o.message}"</p>}
              {o.status === 'confirmed' && (
                <p className="text-xs text-field-700 mt-2 font-medium">
                  ✓ Confirmed by the farmer — use "Show farmer's contact" on the listing to arrange pickup/delivery.
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
