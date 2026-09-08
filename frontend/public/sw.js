/* Service worker for browser push notifications.
 *
 * Deliberately minimal. It does NOT cache or intercept fetches — this app
 * needs live sensor, weather and satellite data, and a stale cached response
 * for any of those would be worse than an offline message.
 *
 * Its only job is to show a notification and route the tap.
 */

self.addEventListener('push', (event) => {
  if (!event.data) return

  let payload = {}
  try {
    payload = event.data.json()
  } catch {
    payload = { title: 'Farm alert', body: event.data.text() }
  }

  // Critical alerts require a tap to dismiss; the rest fade on their own.
  // A flood warning that vanishes while the farmer is in the field is useless.
  const critical = payload.priority === 'CRITICAL'

  event.waitUntil(
    self.registration.showNotification(payload.title || 'Farm alert', {
      body: payload.body || '',
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      tag: `alert-${payload.id || Date.now()}`,
      requireInteraction: critical,
      data: { url: payload.url || '/alerts', id: payload.id },
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/alerts'

  // Focus an already-open tab rather than opening a second one.
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((list) => {
        for (const c of list) {
          if (c.url.includes(url) && 'focus' in c) return c.focus()
        }
        return clients.openWindow(url)
      })
  )
})
