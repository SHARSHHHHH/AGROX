import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCurrentCropLifecycle, getNextCrops } from '../services/api'
import { useLanguage } from '../contexts/LanguageContext'
import { Card, Spinner, StatusPill } from './UI'

/**
 * The four questions a farmer opens the dashboard to answer:
 *
 *   1. What am I currently growing?
 *   2. What stage is it in?
 *   3. What should I do now?
 *   4. What should I sow next, and why?
 *
 * WHY THIS IS A DASHBOARD AND NOT A DESCRIPTION
 * ---------------------------------------------
 * This panel used to answer those questions in prose and bullet lists: a
 * stage name, a paragraph of notes, an unordered list of tasks. All the
 * information was there, but a farmer checking their phone between jobs had
 * to READ it to find out whether anything needed doing today.
 *
 * The same data is now shown as position and quantity — how far through the
 * season the crop is, how many days remain, how many jobs are outstanding,
 * which risks are live. The prose sits behind the numbers for anyone who
 * wants it, rather than in front of them.
 *
 * Both calls are independent and both degrade quietly. A farmer with no crop
 * registered gets a prompt to add one, not an error; a farmer whose rotation
 * call fails still sees their current crop.
 *
 * The three crop states stay visually distinct throughout, per the UX rule:
 *   CURRENT (green, prominent) - NEXT/RECOMMENDED (neutral list) - EXPLORED
 *   (only ever on the Crop Advisor page, never here).
 */
export function CurrentCropPanel() {
  const { t } = useLanguage()
  const [crop, setCrop] = useState<any>(null)
  const [next, setNext] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [openStage, setOpenStage] = useState<number | null>(null)
  // Ticking a task is deliberately local and un-persisted: it is a "what have
  // I done while looking at this screen" aid, not a farm record. Storing it
  // would imply the app knows the job was actually done in the field.
  const [done, setDone] = useState<Record<string, boolean>>({})

  useEffect(() => {
    (async () => {
      const [c, n] = await Promise.allSettled([
        getCurrentCropLifecycle(), getNextCrops(3),
      ])
      if (c.status === 'fulfilled') setCrop(c.value)
      if (n.status === 'fulfilled') setNext(n.value)
      setLoading(false)
    })()
  }, [])

  if (loading) return <Spinner />

  if (!crop?.growing) {
    return (
      <Card>
        <h3 className="font-semibold text-field-800">{t('dash.noCrop')}</h3>
        <p className="text-sm text-gray-600 mt-1">{t('dash.noCropBody')}</p>
        <Link to="/farm" className="text-sm text-field-700 font-semibold mt-2 inline-block">
          {t('dash.addCrop')} →
        </Link>
      </Card>
    )
  }

  const stage = crop.current_stage
  const detail = stage?.detail || {}
  const stages: any[] = crop.stages || []
  const current = stages.find((s: any) => s.is_current)

  const das = crop.days_after_sowing?.value
  const duration = crop.expected_duration_days?.value
  // Season progress. Clamped because a crop left standing past its typical
  // duration must not draw a bar past 100%.
  const pct = das != null && duration
    ? Math.max(0, Math.min(100, Math.round((das / duration) * 100)))
    : null
  const daysLeft = das != null && duration ? duration - das : null

  const tasks: string[] = current?.tasks || detail.tasks || []
  const risks: string[] = current?.risks || detail.risks || []
  const doneCount = tasks.filter((x) => done[x]).length

  return (
    <>
      <Card>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <span className="text-[10px] font-bold px-2 py-1 rounded-full
                             bg-field-700 text-white">
              {t('crop.currentLabel')}
            </span>
            <h2 className="font-bold text-field-800 text-xl mt-2">
              🌾 {crop.display}
            </h2>
          </div>
          {stage?.value && (
            <div className="text-right flex-shrink-0">
              <p className="text-[10px] font-bold text-gray-400 uppercase leading-tight">
                {t('dash.currentStage')}
              </p>
              <p className="font-bold text-field-800">{stage.value}</p>
              {detail.stage_number && detail.of_stages && (
                <p className="text-[11px] text-gray-500">
                  {detail.stage_number} / {detail.of_stages}
                </p>
              )}
            </div>
          )}
        </div>

        {/* ---- Season progress: the one thing worth seeing at a glance ---- */}
        {pct != null && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="font-semibold text-gray-600">
                {t('dash.seasonProgress')}
              </span>
              <span className="font-bold text-field-800">{pct}%</span>
            </div>
            {/* Each stage drawn to scale, so a stage's width on screen means
                its real share of the season rather than an even fifth. */}
            <div className="flex h-3 rounded-full overflow-hidden bg-gray-100
                            border border-gray-200">
              {stages.map((s: any) => {
                const w = duration ? (s.duration_days / duration) * 100 : 0
                const passed = das != null && das > s.end_day
                const isNow = das != null && das >= s.start_day && das <= s.end_day
                return (
                  <div key={s.index} title={`${s.stage} (day ${s.start_day}-${s.end_day})`}
                       style={{ width: `${w}%` }}
                       className={`h-full border-r border-white/60 last:border-r-0
                         ${isNow ? 'bg-field-600'
                           : passed ? 'bg-field-300' : 'bg-gray-200'}`} />
                )
              })}
            </div>
            <div className="flex items-center justify-between text-[11px]
                            text-gray-500 mt-1">
              <span>{crop.sowing_date?.value ?? t('common.notAvailable')}</span>
              <span>{crop.expected_harvest_date?.value ?? t('common.notAvailable')}</span>
            </div>
          </div>
        )}

        {/* ---- KPI row ---- */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4">
          <Kpi label={t('dash.daysOld')} value={das} unit={t('dash.days')} />
          <Kpi label={t('dash.daysToHarvest')}
               value={daysLeft != null ? Math.max(0, daysLeft) : null}
               unit={t('dash.days')}
               tone={daysLeft != null && daysLeft <= 14 ? 'warn' : 'normal'} />
          <Kpi label={t('dash.stageEndsIn')}
               value={detail.days_left_in_stage} unit={t('dash.days')} />
          <Kpi label={t('dash.jobsNow')}
               value={tasks.length ? `${doneCount}/${tasks.length}` : 0} />
        </div>

        {/* A harvest date that contradicts the crop duration is a typo, and
            the farmer is the only one who can correct it. */}
        {crop.harvest_date_conflict && (
          <div className="mt-3 rounded-xl border-2 border-amber-300
                          bg-amber-50 p-2">
            <p className="text-sm text-amber-900">
              ⚠️ {crop.harvest_date_conflict}
            </p>
          </div>
        )}

        {crop.not_yet_sown && (
          <p className="text-sm text-gray-600 mt-2">
            {t('dash.plannedNotSown')}
          </p>
        )}

        {/* ---- Jobs, as things you can tick off ---- */}
        {tasks.length > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-bold text-gray-500 uppercase">
                {t('dash.doNow')}
              </p>
              {doneCount === tasks.length && <StatusPill status="OPTIMAL" />}
            </div>
            <div className="mt-1.5 space-y-1">
              {tasks.map((task: string) => (
                <label key={task}
                       className={`flex items-start gap-2 rounded-lg px-2 py-1.5
                         cursor-pointer border transition
                         ${done[task] ? 'bg-field-50 border-field-200'
                                      : 'bg-gray-50 border-transparent hover:border-gray-200'}`}>
                  <input type="checkbox" checked={!!done[task]}
                         onChange={() => setDone((d) => ({ ...d, [task]: !d[task] }))}
                         className="mt-0.5 w-4 h-4 accent-field-600 flex-shrink-0" />
                  <span className={`text-sm ${done[task]
                    ? 'text-gray-400 line-through' : 'text-gray-700'}`}>
                    {task}
                  </span>
                </label>
              ))}
            </div>
          </div>
        )}

        {/* ---- Risks as badges, not a sentence ---- */}
        {risks.length > 0 && (
          <div className="mt-3">
            <p className="text-[11px] font-bold text-gray-500 uppercase">
              {t('dash.watchFor')}
            </p>
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {risks.map((r: string) => (
                <span key={r} className="text-xs font-medium px-2 py-1 rounded-full
                                         bg-amber-50 text-amber-900 border border-amber-200">
                  ⚠ {r}
                </span>
              ))}
            </div>
          </div>
        )}

        {(current?.irrigation || detail.irrigation) && (
          <div className="mt-3 rounded-xl bg-blue-50 border border-blue-200 p-2.5">
            <p className="text-[10px] font-bold text-blue-800 uppercase">
              {t('dash.irrigationNow')}
            </p>
            <p className="text-sm text-gray-700 mt-0.5">
              {current?.irrigation || detail.irrigation}
            </p>
          </div>
        )}

        {/* ---- The full stage timeline, folded away ---- */}
        {stages.length > 0 && (
          <details className="mt-3 group">
            <summary className="cursor-pointer text-sm font-semibold
                                text-field-700 list-none flex items-center gap-1">
              {t('dash.allStages')}
              <span className="text-xs text-gray-400 group-open:hidden">▼</span>
              <span className="text-xs text-gray-400 hidden group-open:inline">▲</span>
            </summary>
            <table className="w-full text-sm mt-2">
              <tbody>
                {stages.map((s: any) => {
                  const passed = das != null && das > s.end_day
                  const isNow = das != null && das >= s.start_day && das <= s.end_day
                  return (
                    <tr key={s.index}
                        onClick={() => setOpenStage(openStage === s.index ? null : s.index)}
                        className={`border-b border-gray-100 cursor-pointer
                          ${isNow ? 'bg-field-50' : ''}`}>
                      <td className="py-1.5 pr-2 w-6 text-center align-top">
                        {passed ? '✓' : isNow ? '●' : '○'}
                      </td>
                      <td className={`py-1.5 ${isNow
                        ? 'font-bold text-field-800' : 'text-gray-600'}`}>
                        {s.stage}
                        {openStage === s.index && s.tasks?.length > 0 && (
                          <ul className="text-xs text-gray-600 list-disc ml-4 mt-1 mb-1
                                         font-normal">
                            {s.tasks.map((x: string) => <li key={x}>{x}</li>)}
                          </ul>
                        )}
                      </td>
                      <td className="py-1.5 text-right text-xs text-gray-500
                                     whitespace-nowrap align-top">
                        {t('dash.day')} {s.start_day}-{s.end_day}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </details>
        )}

        {stage?.confidence === 'ESTIMATED' && (
          <p className="text-[11px] text-gray-500 mt-2">
            {stage.note || crop.note}
          </p>
        )}

        {/* Deep-links to the LIFECYCLE tab. It used to point at
            /crop-advisor, which opens on the "what should I grow" ranking —
            the opposite of what this link promises. */}
        <Link to="/crop-advisor?tab=lifecycle"
              className="text-sm text-field-700 font-semibold mt-3 inline-block">
          {t('dash.viewLifecycle')} →
        </Link>
      </Card>

      {next?.available && next.recommendations?.length > 0 && (
        <Card>
          <h3 className="font-semibold text-field-800">{t('crop.nextCrops')}</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {t('dash.afterHarvest')} {crop.display}
            {next.expected_harvest ? ` (${next.expected_harvest})` : ''}
          </p>
          <ol className="mt-3 space-y-2">
            {next.recommendations.map((r: any, i: number) => (
              <li key={r.crop} className="border rounded-xl p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-field-800">
                    #{i + 1} {r.display}
                  </span>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {/* The score as a bar makes three ranked crops comparable
                        at a glance; the verdict word alone does not. */}
                    {typeof r.score === 'number' && (
                      <div className="w-16 h-2 rounded-full bg-gray-200 overflow-hidden">
                        <div className="h-full bg-field-600"
                             style={{ width: `${Math.max(4, Math.min(100,
                               r.score <= 1 ? r.score * 100 : r.score))}%` }} />
                      </div>
                    )}
                    <span className="text-[10px] text-gray-500">{r.verdict}</span>
                  </div>
                </div>
                {r.why?.length > 0 && (
                  <ul className="text-xs text-gray-600 list-disc ml-4 mt-1">
                    {r.why.slice(0, 3).map((w: string, k: number) =>
                      <li key={k}>{w}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ol>
          {next.nitrogen_note && (
            <p className="text-[11px] text-gray-500 mt-2">{next.nitrogen_note}</p>
          )}
        </Card>
      )}
    </>
  )
}

/** One KPI. A missing value reads "Not available", never a bare 0. */
function Kpi({ label, value, unit, tone = 'normal' }:
             { label: string; value: any; unit?: string
               tone?: 'normal' | 'warn' }) {
  const { t } = useLanguage()
  const missing = value === null || value === undefined
  return (
    <div className={`rounded-xl border p-2 ${tone === 'warn'
      ? 'border-amber-300 bg-amber-50' : 'border-gray-200 bg-white'}`}>
      <p className="text-[10px] font-semibold text-gray-500 uppercase leading-tight">
        {label}
      </p>
      <p className={`text-lg font-bold mt-0.5 ${tone === 'warn'
        ? 'text-amber-900' : 'text-field-800'}`}>
        {missing ? <span className="text-sm font-normal text-gray-400">
          {t('common.notAvailable')}</span> : value}
        {!missing && unit && (
          <span className="text-[11px] font-normal text-gray-400"> {unit}</span>
        )}
      </p>
    </div>
  )
}
