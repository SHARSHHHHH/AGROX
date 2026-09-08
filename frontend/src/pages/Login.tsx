import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login } from '../services/api'
import { LanguagePicker, VoiceField } from '../components/VoiceInput'
import { useLanguage } from '../contexts/LanguageContext'

export default function Login() {
  const [email, setEmail] = useState('farmer@demo.com')
  const [password, setPassword] = useState('demo123')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const nav = useNavigate()
  const { t } = useLanguage()

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true); setErr('')
    try {
      const user = await login(email, password)
      nav(user.role === 'admin' ? '/admin' : user.role === 'buyer' ? '/marketplace' : '/dashboard')
    } catch {
      setErr(t('login.error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-field-800 to-field-600 p-4">
      <div className="bg-white rounded-3xl shadow-xl w-full max-w-md p-8">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">🌾</div>
          <h1 className="text-2xl font-bold text-field-800 font-display">{t('app.name')}</h1>
          <p className="text-sm text-gray-500 mt-1">{t('app.tagline')}</p>
        </div>

        {/* Language is chosen BEFORE login and persists into the app, so a
            farmer never has to read English to reach their own language. */}
        <div className="mb-5">
          <LanguagePicker />
        </div>

        <form onSubmit={submit} className="space-y-4">
          {/* Voice-enabled so an email can be dictated rather than typed. */}
          <VoiceField
            label={t('login.email')}
            value={email}
            onChange={setEmail}
            type="email"
            placeholder="farmer@demo.com"
          />

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">
              {t('login.password')}
            </label>
            {/* Passwords are deliberately NOT voice-enabled — dictating a
                password aloud is a security problem, not a convenience. */}
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              className="w-full border rounded-xl px-3 py-2.5 text-sm focus:ring-2 focus:ring-field-600 outline-none"
            />
          </div>

          {err && <p className="text-sm text-red-600">{err}</p>}

          <button type="submit" disabled={loading}
            className="w-full bg-field-600 hover:bg-field-700 text-white font-semibold py-2.5 rounded-xl disabled:opacity-50">
            {loading ? t('login.signingin') : t('login.submit')}
          </button>
        </form>

        <div className="mt-4 text-center text-sm text-gray-500">
          {t('login.noaccount')} <Link to="/register" className="text-field-700 font-semibold">
            {t('login.register')}
          </Link>
        </div>

        <div className="mt-5 pt-4 border-t text-xs text-gray-400 space-y-1">
          <p className="font-semibold text-gray-500">{t('login.demologins')}</p>
          <p>👨‍🌾 farmer@demo.com / demo123</p>
          <p>🪴 balcony@demo.com / demo123</p>
          <p>🛒 buyer@demo.com / demo123</p>
          <p>🏛️ admin@agri.gov / admin123 (Govt dashboard)</p>
        </div>
      </div>
    </div>
  )
}
