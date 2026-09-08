import { useEffect, useRef, useState } from 'react'
import { analyzePest, getPestHistory, chat, getUser } from '../services/api'
import { Card, Button, Spinner, StatusPill } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

// Treatment categories in sustainable order — chemical is LAST by design.
const CATEGORY_META: Record<string, { emoji: string; key: string }> = {
  prevention: { emoji: '🌱', key: 'pest.prevention' },
  cultural: { emoji: '🌾', key: 'pest.cultural' },
  mechanical: { emoji: '🛠', key: 'pest.mechanical' },
  biological: { emoji: '🪲', key: 'pest.biological' },
  chemical: { emoji: '🧪', key: 'pest.chemical' },
}
const CATEGORY_ORDER = ['prevention', 'cultural', 'mechanical', 'biological', 'chemical']

const SEVERITY_STATUS: Record<string, string> = {
  LOW: 'Good', MODERATE: 'WARNING', HIGH: 'CRITICAL', UNKNOWN: 'INFO',
}

export default function PestManagement() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const user = getUser()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [crop, setCrop] = useState('')
  const [result, setResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState<any[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  // Follow-up Q&A about the detected pest
  const [followup, setFollowup] = useState('')
  const [answer, setAnswer] = useState('')
  const [asking, setAsking] = useState(false)

  const loadHistory = () => getPestHistory().then((h) => {
    setHistory(h)
    if (!result) publish('Pest Management', h.length
      ? `${h.length} past pest/disease check(s) on record. Most recent: `
        + `${h[0].type === 'pest' ? h[0].pest_name : h[0].type} on ${h[0].crop || 'unspecified crop'}.`
      : 'No pest checks recorded yet.')
  }).catch(() => {})
  useEffect(() => { loadHistory() }, [])

  const pick = (f: File) => {
    setFile(f); setPreview(URL.createObjectURL(f)); setResult(null); setAnswer('')
  }

  const analyze = async () => {
    if (!file) return
    setBusy(true); setResult(null); setAnswer('')
    try {
      const res = await analyzePest(file, crop)
      setResult(res)
      if (res.error) {
        publish('Pest Management', `Analysis failed: ${res.error}`)
      } else if (res.type === 'pest') {
        publish('Pest Management', `Just identified ${res.pest?.name} on ${crop || 'this crop'} `
          + `(confidence ${Math.round((res.pest?.confidence || 0) * 100)}%, severity ${res.severity?.level}). `
          + `Reason: ${res.severity?.reason || ''} Recommendation: ${res.sustainable_recommendation || ''}`)
      } else {
        publish('Pest Management', `Just analyzed a photo: ${res.type === 'disease' ? 'looks like a disease, not a pest'
          : res.type === 'healthy' ? 'no pest detected, looks healthy' : 'uncertain result'}. ${res.message || ''}`)
      }
      loadHistory()
    } catch {
      setResult({ error: 'Analysis failed. Ensure the backend and vision model (llava) are running.' })
    } finally {
      setBusy(false)
    }
  }

  const askFollowup = async () => {
    if (!followup.trim()) return
    setAsking(true); setAnswer('')
    try {
      const pestName = result?.pest?.name ? ` about ${result.pest.name}` : ''
      const res = await chat(`${followup}${pestName}`, user?.language)
      setAnswer(res.answer)
    } catch {
      setAnswer('Could not get an answer right now. Please try again.')
    } finally {
      setAsking(false)
    }
  }

  const isPest = result && result.type === 'pest' && !result.error
  const sev = result?.severity?.level

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">🐛 Pest Management</h1>
      <p className="text-sm text-gray-500 mb-5">
        Upload a photo of the affected leaves or the insect. You'll get pest identification,
        an infestation severity estimate, and a sustainable (IPM) treatment plan —
        chemical control only as a last resort.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Upload */}
        <Card>
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); e.dataTransfer.files[0] && pick(e.dataTransfer.files[0]) }}
            className="border-2 border-dashed border-field-300 rounded-2xl p-6 text-center cursor-pointer hover:bg-field-50 transition"
          >
            {preview ? (
              <img src={preview} alt="plant" className="max-h-56 mx-auto rounded-xl" />
            ) : (
              <div className="py-8 text-gray-400">
                <div className="text-4xl mb-2">📷</div>
                <p className="text-sm">{t('pest.upload')}</p>
              </div>
            )}
            <input ref={inputRef} type="file" accept="image/*" hidden
              onChange={(e) => e.target.files?.[0] && pick(e.target.files[0])} />
          </div>

          <input value={crop} onChange={(e) => setCrop(e.target.value)}
            placeholder={t('plant.cropph')}
            className="mt-3 w-full border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />

          <Button onClick={analyze} disabled={!file || busy}>
            {busy ? 'Analyzing…' : 'Analyze for pests'}
          </Button>
        </Card>

        {/* Result summary */}
        <Card>
          <h3 className="font-semibold text-field-800 mb-2">{t('common.result')}</h3>
          {busy && <Spinner />}
          {!busy && !result && <p className="text-sm text-gray-400 py-8 text-center">{t('crop.noanalysis')}</p>}
          {result?.error && <p className="text-sm text-red-600">{result.error}</p>}

          {/* Non-pest outcomes */}
          {result && !result.error && result.type !== 'pest' && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-field-800">
                  {result.type === 'disease' ? '🍃 Looks like a disease'
                    : result.type === 'healthy' ? '✅ No pest detected'
                    : '⚠️ Uncertain'}
                </span>
              </div>
              <p className="text-sm text-gray-600">{result.message}</p>
              {result.type === 'disease' && (
                <a href="/plant-health" className="text-sm text-field-700 font-semibold underline">
                  {t('pest.todisease')}
                </a>
              )}
              {result.model_guess && (
                <p className="text-xs text-gray-400">Low-confidence guess: {result.model_guess}</p>
              )}
            </div>
          )}

          {/* Pest identified */}
          {isPest && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xl font-bold text-field-800">{result.pest.name}</span>
                <StatusPill status={SEVERITY_STATUS[sev] || 'INFO'} />
              </div>
              {result.pest.scientific_name && (
                <p className="text-xs italic text-gray-400 -mt-2">{result.pest.scientific_name}</p>
              )}
              <p className="text-sm text-gray-500">
                Confidence: {(result.pest.confidence * 100).toFixed(0)}%
                {' · '}{t('pest.severity')}: <b>{tv(sev)}</b>
                {result.severity?.is_estimate && <span className="text-gray-400"> (estimate)</span>}
              </p>

              {result.pest.symptoms && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase">{t('common.symptoms')}</p>
                  <p className="text-sm text-gray-700">{result.pest.symptoms}</p>
                </div>
              )}

              <div className="bg-field-50 rounded-xl p-3">
                <p className="text-xs font-semibold text-field-700 uppercase mb-1">{t('pest.whyseverity')}</p>
                <p className="text-sm text-gray-700">{result.severity.reason}</p>
                {result.severity.factors?.length > 0 && (
                  <ul className="text-xs text-gray-600 list-disc pl-4 mt-1 space-y-0.5">
                    {result.severity.factors.map((f: string, i: number) => <li key={i}>{f}</li>)}
                  </ul>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* IPM plan */}
      {isPest && (
        <Card className="mt-5">
          <h3 className="font-semibold text-field-800 mb-1">🌿 Sustainable treatment plan (IPM)</h3>
          <p className="text-sm text-gray-600 mb-4">{result.sustainable_recommendation}</p>

          {/* Monitoring first */}
          {result.ipm.monitoring?.length > 0 && (
            <div className="mb-3 bg-blue-50 rounded-xl p-3">
              <p className="text-sm font-semibold text-blue-800 mb-1">🔍 Monitoring</p>
              <ul className="text-sm text-gray-700 list-disc pl-4 space-y-0.5">
                {result.ipm.monitoring.map((m: string, i: number) => <li key={i}>{m}</li>)}
              </ul>
            </div>
          )}

          {/* Escalation (HIGH) */}
          {result.ipm.escalation?.length > 0 && (
            <div className="mb-3 bg-red-50 rounded-xl p-3">
              <p className="text-sm font-semibold text-red-800 mb-1">🚨 Immediate containment</p>
              <ul className="text-sm text-gray-700 list-disc pl-4 space-y-0.5">
                {result.ipm.escalation.map((m: string, i: number) => <li key={i}>{m}</li>)}
              </ul>
            </div>
          )}

          {/* Category ladder — chemical always rendered last */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {CATEGORY_ORDER.map((cat) => {
              const items = result.ipm[cat] || []
              if (!items.length) return null
              const meta = CATEGORY_META[cat]
              const isChem = cat === 'chemical'
              return (
                <div key={cat} className={`rounded-xl p-3 border ${isChem ? 'border-amber-200 bg-amber-50' : 'border-gray-100 bg-white'}`}>
                  <p className="text-sm font-semibold mb-1" style={{ color: isChem ? '#b45309' : '#256232' }}>
                    {meta.emoji} {t(meta.key)}
                  </p>
                  <ul className="text-sm text-gray-700 list-disc pl-4 space-y-0.5">
                    {items.map((it: string, i: number) => <li key={i}>{it}</li>)}
                  </ul>
                </div>
              )
            })}
          </div>

          {/* Action threshold + environmental note */}
          {result.ipm.action_threshold && (
            <p className="text-xs text-gray-500 mt-3">
              <b>{t('pest.threshold')}</b> {result.ipm.action_threshold}
            </p>
          )}
          {result.environmental_considerations?.length > 0 && (
            <div className="mt-3 pt-3 border-t">
              <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{t('pest.environmental')}</p>
              <ul className="text-xs text-gray-600 list-disc pl-4 space-y-0.5">
                {result.environmental_considerations.map((e: string, i: number) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          )}
          <p className="text-[11px] text-gray-400 mt-3">
            This is an AI-assisted, IPM-based suggestion. Severity from an image is an estimate,
            not a lab measurement. For chemical options, use only locally registered products and
            follow the label and local agricultural guidance.
          </p>
        </Card>
      )}

      {/* Follow-up question */}
      {isPest && (
        <Card className="mt-5 bg-field-50/40">
          <h3 className="font-semibold text-field-800 mb-2">{t('pest.followup')}</h3>
          <div className="flex gap-2">
            <input value={followup} onChange={(e) => setFollowup(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && askFollowup()}
              placeholder={`e.g. How do I attract lady beetles for ${result.pest.name}?`}
              className="flex-1 border rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-field-600" />
            <Button onClick={askFollowup} disabled={asking || !followup.trim()}>
              {asking ? '…' : 'Ask'}
            </Button>
          </div>
          {answer && (
            <div className="mt-3 bg-white rounded-xl p-3 border">
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{answer}</p>
            </div>
          )}
        </Card>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className="mt-6">
          <h3 className="font-semibold text-field-800 mb-2">{t('pest.recent')}</h3>
          <div className="space-y-2">
            {history.map((h) => (
              <Card key={h.id} className="!p-3">
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">
                      {h.type === 'pest' ? h.pest_name : h.type === 'disease' ? 'Disease (see Plant Health)'
                        : h.type === 'healthy' ? 'No pest' : 'Uncertain'}
                    </span>
                    {h.type === 'pest' && <StatusPill status={SEVERITY_STATUS[h.severity] || 'INFO'} />}
                  </div>
                  <span className="text-gray-400">{new Date(h.date).toLocaleString()}</span>
                </div>
                {h.crop && <span className="text-xs text-gray-500">{h.crop}</span>}
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
