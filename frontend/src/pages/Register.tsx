import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { register } from '../services/api'
import { useLanguage } from '../contexts/LanguageContext'

const LANGS = [['en','English'],['ta','Tamil'],['te','Telugu'],['kn','Kannada'],['ml','Malayalam'],['hi','Hindi']]

export default function Register() {
  const { t, tv } = useLanguage()
  const [form, setForm] = useState({ name: '', email: '', password: '',
    mode: 'farm', language: 'en', state: '', district: '' })
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const nav = useNavigate()
  const set = (k: string, v: string) => setForm({ ...form, [k]: v })

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true); setErr('')
    try {
      await register(form)
      nav(form.mode === 'buyer' ? '/marketplace' : '/farm')
    } catch (e: any) {
      setErr(e.response?.data?.detail || 'Registration failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-field-800 to-field-600 p-4">
      <div className="bg-white rounded-3xl shadow-xl w-full max-w-md p-8">
        <h1 className="text-2xl font-bold text-field-800 font-display text-center mb-1">{t('register.submit')}</h1>
        <p className="text-sm text-gray-500 text-center mb-5">{t('register.choosemode')}</p>

        <div className="grid grid-cols-3 gap-2 mb-5">
          {[['farm','🌾 Farmer'],['balcony','🪴 Home'],['buyer','🛒 Buyer']].map(([v, l]) => (
            <button key={v} type="button" onClick={() => set('mode', v)}
              className={`py-3 rounded-xl border-2 font-semibold text-xs sm:text-sm transition
                ${form.mode === v ? 'border-field-600 bg-field-50 text-field-700' : 'border-gray-200 text-gray-500'}`}>
              {l}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          <input required placeholder={t('register.name')} value={form.name}
            onChange={(e) => set('name', e.target.value)}
            className="w-full border rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-field-600" />
          <input required type="email" placeholder={t('login.email')} value={form.email}
            onChange={(e) => set('email', e.target.value)}
            className="w-full border rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-field-600" />
          <input required type="password" placeholder={t('login.password')} value={form.password}
            onChange={(e) => set('password', e.target.value)}
            className="w-full border rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-field-600" />
          <div className="grid grid-cols-2 gap-3">
            <input placeholder={t('common.state')} value={form.state}
              onChange={(e) => set('state', e.target.value)}
              className="w-full border rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-field-600" />
            <input placeholder={t('common.district')} value={form.district}
              onChange={(e) => set('district', e.target.value)}
              className="w-full border rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-field-600" />
          </div>
          <select value={form.language} onChange={(e) => set('language', e.target.value)}
            className="w-full border rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-field-600">
            {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {err && <p className="text-sm text-red-600">{err}</p>}
          <button type="submit" disabled={loading}
            className="w-full bg-field-600 hover:bg-field-700 text-white font-semibold py-2.5 rounded-xl disabled:opacity-50">
            {loading ? 'Creating…' : 'Create account'}
          </button>
        </form>
        <div className="mt-4 text-center text-sm text-gray-500">
          {t('register.haveaccount')} <Link to="/login" className="text-field-700 font-semibold">{t('login.submit')}</Link>
        </div>
      </div>
    </div>
  )
}
