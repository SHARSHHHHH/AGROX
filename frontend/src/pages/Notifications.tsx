import { useEffect, useState } from 'react'
import { deleteHarvestMessage, getHarvestMessageNotifications, getHarvestMessages, markNotificationRead, sendHarvestMessage } from '../services/api'
import { useLanguage } from '../contexts/LanguageContext'

export default function Notifications() {
  const { t } = useLanguage()
  const [notifications, setNotifications] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeHarvestId, setActiveHarvestId] = useState<number | null>(null)
  const [messages, setMessages] = useState<any[]>([])
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)

  const loadNotifications = async () => {
    try {
      setNotifications(await getHarvestMessageNotifications())
      setError('')
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('notifications.empty'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadNotifications()
    const timer = window.setInterval(loadNotifications, 10000)
    return () => window.clearInterval(timer)
  }, [])

  const openNotification = async (notification: any) => {
    if (!notification.read) {
      await markNotificationRead(notification.id).catch(() => {})
      setNotifications(current => current.map(item =>
        item.id === notification.id ? { ...item, read: true } : item
      ))
    }
    setActiveHarvestId(notification.harvest_id)
    setMessages(await getHarvestMessages(notification.harvest_id))
  }

  const sendReply = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!activeHarvestId || !reply.trim() || sending) return
    setSending(true)
    try {
      const message = await sendHarvestMessage(activeHarvestId, reply.trim())
      setMessages(current => [...current, message])
      setReply('')
      await loadNotifications()
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('messages.send'))
    } finally {
      setSending(false)
    }
  }

  const deleteMessage = async (messageId: number) => {
    if (!activeHarvestId || !window.confirm(t('messages.deleteConfirm'))) return
    try {
      await deleteHarvestMessage(activeHarvestId, messageId)
      setMessages(current => current.filter(message => message.id !== messageId))
      await loadNotifications()
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('messages.delete'))
    }
  }

  const unreadCount = notifications.filter(notification => !notification.read).length

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-field-800">🔔 {t('notifications.title')}</h1>
          <p className="text-sm text-gray-500 mt-1">{t('notifications.subtitle')}</p>
        </div>
        <button type="button" onClick={loadNotifications} className="text-sm text-field-700 font-semibold">
          {t('notifications.refresh')}
        </button>
      </div>

      {unreadCount > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 mb-4 font-semibold">
          {unreadCount} {t('notifications.unread')}{unreadCount === 1 ? '' : 's'}
        </div>
      )}

      {error && <div className="bg-red-50 text-red-700 rounded-lg p-4 mb-4">{error}</div>}
      {loading ? (
        <div className="bg-white rounded-lg border p-6">{t('notifications.loading')}</div>
      ) : notifications.length === 0 ? (
        <div className="bg-white rounded-lg border p-6 text-gray-600">{t('notifications.empty')}</div>
      ) : (
        <div className="space-y-3">
          {notifications.map(notification => (
            <button
              key={notification.id}
              type="button"
              onClick={() => openNotification(notification)}
              className={`w-full text-left rounded-lg border p-4 transition hover:border-field-400 ${notification.read ? 'bg-white' : 'bg-amber-50 border-amber-300'}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-field-800">{notification.title}</p>
                  <p className="text-sm text-gray-600 mt-1">
                    {notification.sender_name || 'Portal user'} · {notification.crop || 'Harvest'}
                  </p>
                </div>
                {!notification.read && <span className="text-xs font-bold text-amber-700">NEW</span>}
              </div>
              <p className="mt-2 text-gray-800">{notification.message}</p>
              <p className="mt-2 text-xs text-gray-500">
                {notification.created_at ? new Date(notification.created_at).toLocaleString() : ''}
              </p>
            </button>
          ))}
        </div>
      )}

      {activeHarvestId && (
        <section className="bg-white border rounded-lg p-4 mt-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-bold text-field-800">{t('messages.reply')}</h2>
            <button type="button" onClick={() => setActiveHarvestId(null)} className="text-sm text-gray-500">{t('common.close')}</button>
          </div>
          <div className="space-y-2 max-h-56 overflow-y-auto mb-3">
            {messages.map(message => (
              <div key={message.id} className={`rounded p-2 ${message.is_mine ? 'bg-green-100 ml-8' : 'bg-gray-100 mr-8'}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xs text-gray-500">{message.sender_name}</p>
                    <p>{message.content}</p>
                  </div>
                  <button
                    type="button"
                    title={t('messages.delete')}
                    aria-label={t('messages.delete')}
                    onClick={() => deleteMessage(message.id)}
                    className="text-red-600 hover:text-red-800 px-1"
                  >
                    🗑
                  </button>
                </div>
              </div>
            ))}
          </div>
          <form onSubmit={sendReply} className="flex gap-2">
            <input
              value={reply}
              onChange={event => setReply(event.target.value)}
              className="flex-1 border rounded p-2"
              placeholder={t('messages.writeReply')}
              disabled={sending}
            />
            <button type="submit" disabled={sending || !reply.trim()} className="bg-green-600 disabled:bg-gray-300 text-white px-4 py-2 rounded">
              {sending ? '...' : t('messages.send')}
            </button>
          </form>
        </section>
      )}
    </div>
  )
}
