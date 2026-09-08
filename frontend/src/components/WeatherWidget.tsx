import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getWeather } from '../services/api'

const CONDITION_ICON: Record<string, string> = {
  clear: '☀️', sunny: '☀️', cloudy: '☁️', 'partly cloudy': '⛅',
  rain: '🌧️', rainy: '🌧️', thunderstorm: '⛈️', storm: '⛈️',
  fog: '🌫️', mist: '🌫️', haze: '🌫️',
}

/**
 * Weather used to have its own sidebar tab; it's now a compact chip pinned
 * to the top-right of every farmer/balcony page instead — a quick glance
 * rather than a whole page to visit, since it's usually a "check and move
 * on" number. Tapping it still opens the full Weather page.
 */
export function WeatherWidget() {
  const nav = useNavigate()
  const [wx, setWx] = useState<any>(null)

  useEffect(() => {
    getWeather().then(setWx).catch(() => {})
  }, [])

  if (!wx) return null

  const icon = CONDITION_ICON[(wx.condition || '').toLowerCase()] || '🌤️'

  return (
    <button
      onClick={() => nav('/weather')}
      title="Open Weather"
      className="flex items-center gap-2 bg-white border border-gray-100 shadow-sm
                 rounded-full pl-2.5 pr-3.5 py-1.5 hover:bg-field-50 transition shrink-0"
    >
      <span className="text-lg leading-none">{icon}</span>
      <span className="text-sm font-semibold text-field-800">{Math.round(wx.temperature)}°C</span>
      <span className="text-xs text-gray-400 hidden sm:inline capitalize">{wx.condition}</span>
    </button>
  )
}
