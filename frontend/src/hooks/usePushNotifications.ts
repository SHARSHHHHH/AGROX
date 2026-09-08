import { useCallback, useEffect, useState } from 'react'
import { getNotificationStatus, subscribePush, unsubscribePush } from '../services/api'

/**
 * Browser push subscription.
 *
 * WHY PUSH IS OPTIONAL AND NEVER BLOCKING
 * ---------------------------------------
 * Alerts are stored server-side and rendered by the Alerts page regardless.
 * Push is an extra nudge for the urgent ones. So every failure path here ends
 * quietly: no VAPID keys configured, permission denied, service workers
 * unsupported, an insecure origin — all of them leave the app fully working.
 *
 * The HTTPS requirement catches people out on mobile. Service workers and the
 * Push API only run on a secure origin; localhost counts, a bare LAN IP like
 * http://192.168.1.7:5173 does not. That is reported explicitly rather than
 * failing silently, because "the button does nothing" is impossible to debug.
 */

type PushState = {
  supported: boolean
  permission: NotificationPermission | 'unsupported'
  subscribed: boolean
  serverReady: boolean
  reason: string
  busy: boolean
}

/** VAPID keys travel as base64url; the browser wants a Uint8Array. */
function urlBase64ToUint8Array(base64: string): ArrayBuffer {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const normalised = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(normalised)
  // Returned as a plain ArrayBuffer: applicationServerKey rejects a
  // Uint8Array backed by a possibly-shared buffer under strict DOM typings.
  const buf = new ArrayBuffer(raw.length)
  const view = new Uint8Array(buf)
  for (let i = 0; i < raw.length; i += 1) view[i] = raw.charCodeAt(i)
  return buf
}

export function usePushNotifications() {
  const [state, setState] = useState<PushState>({
    supported: false, permission: 'unsupported', subscribed: false,
    serverReady: false, reason: '', busy: false,
  })
  const [publicKey, setPublicKey] = useState('')

  useEffect(() => {
    (async () => {
      const supported = typeof window !== 'undefined'
        && 'serviceWorker' in navigator
        && 'PushManager' in window
        && 'Notification' in window

      if (!supported) {
        setState((s) => ({
          ...s, supported: false, reason: window?.isSecureContext === false
            ? 'Push needs a secure connection (HTTPS). It will not work over a plain LAN address.'
            : 'This browser does not support notifications.',
        }))
        return
      }

      let serverReady = false
      let reason = ''
      try {
        const st = await getNotificationStatus()
        serverReady = !!st?.web_push?.ready
        reason = st?.web_push?.reason || ''
        if (st?.web_push?.public_key) setPublicKey(st.web_push.public_key)
      } catch {
        reason = 'Could not reach the notification service.'
      }

      let subscribed = false
      try {
        const reg = await navigator.serviceWorker.getRegistration()
        subscribed = !!(await reg?.pushManager.getSubscription())
      } catch { /* not registered yet */ }

      setState({
        supported: true, permission: Notification.permission,
        subscribed, serverReady, reason, busy: false,
      })
    })()
  }, [])

  const enable = useCallback(async () => {
    setState((s) => ({ ...s, busy: true, reason: '' }))
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        setState((s) => ({
          ...s, busy: false, permission,
          reason: 'Notification permission was denied. You can still see every alert on this page.',
        }))
        return false
      }

      const reg = await navigator.serviceWorker.register('/sw.js')
      await navigator.serviceWorker.ready

      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      })

      const json = sub.toJSON() as any
      await subscribePush({
        endpoint: sub.endpoint,
        p256dh: json.keys?.p256dh || '',
        auth: json.keys?.auth || '',
        user_agent: navigator.userAgent,
        min_priority: 'HIGH',
      })

      setState((s) => ({ ...s, busy: false, subscribed: true,
                         permission: 'granted' }))
      return true
    } catch (e: any) {
      setState((s) => ({
        ...s, busy: false,
        reason: e?.message || 'Could not enable notifications.',
      }))
      return false
    }
  }, [publicKey])

  const disable = useCallback(async () => {
    setState((s) => ({ ...s, busy: true }))
    try {
      const reg = await navigator.serviceWorker.getRegistration()
      const sub = await reg?.pushManager.getSubscription()
      if (sub) {
        await unsubscribePush(sub.endpoint)
        await sub.unsubscribe()
      }
      setState((s) => ({ ...s, busy: false, subscribed: false }))
    } catch {
      setState((s) => ({ ...s, busy: false }))
    }
  }, [])

  return { ...state, enable, disable }
}
