import { useEffect, useState } from 'react'
import { getWeather } from '../services/api'
import { Card, Spinner, StatCard } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

export default function Weather() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const [wx, setWx] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getWeather().then((res) => {
      setWx(res)
      publish('Weather', res
        ? `Currently: ${res.condition}, ${res.temperature}°C, rain probability ${res.rain_probability}%. ${res.interpretation}`
        : 'No weather data available.')
    }).finally(() => setLoading(false))
  }, [])
  if (loading) return <Spinner />
  if (!wx) return <Card><p className="text-sm text-gray-400">{t('dash.noweather')}</p></Card>

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">🌤️ Weather</h1>
      <p className="text-sm text-gray-500 mb-5">{t('weather.subtitle')}</p>

      <Card className="mb-5 bg-gradient-to-br from-field-600 to-field-800 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-5xl font-bold font-display">{wx.temperature}°C</p>
            <p className="text-field-100 mt-1">{wx.condition}</p>
          </div>
          <div className="text-right text-sm">
            <p>💧 Humidity {wx.humidity}%</p>
            <p>🌧️ Rain {wx.rain_probability}%</p>
            <p>💨 Wind {wx.wind_speed} km/h</p>
          </div>
        </div>
        <div className="mt-4 bg-white/15 rounded-xl p-3 text-sm">
          🌱 {wx.interpretation}
        </div>
      </Card>

      {wx.forecast?.length > 0 && (
        <div>
          <h3 className="font-semibold text-field-800 mb-2">7-day outlook</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            {wx.forecast.map((d: any, i: number) => (
              <Card key={i} className="!p-3 text-center">
                <p className="text-xs text-gray-500">{new Date(d.date).toLocaleDateString(undefined, { weekday: 'short' })}</p>
                <p className="text-lg font-bold text-field-800 mt-1">{Math.round(d.temp_max)}°</p>
                <p className="text-xs text-gray-400">{Math.round(d.temp_min)}°</p>
                <p className="text-xs text-blue-500 mt-1">💧{d.rain_prob}%</p>
              </Card>
            ))}
          </div>
        </div>
      )}
      <p className="text-[11px] text-gray-400 mt-4">Source: {wx.source}</p>
    </div>
  )
}
