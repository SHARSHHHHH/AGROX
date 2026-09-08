import { useLanguage } from '../contexts/LanguageContext'
import { Card } from './UI'

/**
 * Crop lifecycle timeline.
 *
 * THE RULE THIS COMPONENT ENFORCES
 * --------------------------------
 * A stage is only highlighted when the farmer is ACTUALLY growing that crop.
 *
 * If they grow rice and open the cotton lifecycle, there is no cotton in the
 * field, so there is no cotton stage they could be "in". Highlighting one
 * would be inventing a fact. The backend already refuses to mark a current
 * stage on an explored crop; this component refuses to draw one.
 *
 * The three states the spec insists must never blur together:
 *   CURRENT CROP    growing it, stage highlighted
 *   EXPLORED CROP   just looking, nothing highlighted, warning shown
 *   (recommended crops are handled separately, on the advisor page)
 */

type Stage = {
  index: number
  stage: string
  start_day: number | null
  end_day: number | null
  duration_days: number | null
  tasks: string[]
  irrigation: string
  risks: string[]
  is_current: boolean
  is_past: boolean
  is_future: boolean
  image: string | null
}

type Props = {
  data: {
    crop: string
    display: string
    is_current_crop: boolean
    label: string
    warning: { short: string; message: string } | null
    days_after_sowing: number | null
    stages: Stage[]
    suitability?: any
  }
}

export function CropLifecycleTimeline({ data }: Props) {
  const { t } = useLanguage()
  if (!data?.stages?.length) return null

  return (
    <div>
      {/* Explored-crop warning. Deliberately loud: this is the single most
          confusing thing that can happen on this screen. */}
      {data.warning && (
        <div className="rounded-xl border-2 border-amber-300 bg-amber-50 p-3 mb-4">
          <p className="font-bold text-amber-900">⚠️ {data.warning.short}</p>
          <p className="text-sm text-amber-800 mt-1">{data.warning.message}</p>
        </div>
      )}

      <div className="flex items-center gap-2 mb-3">
        <span className={`text-[10px] font-bold px-2 py-1 rounded-full ${
          data.is_current_crop
            ? 'bg-field-700 text-white'
            : 'bg-gray-200 text-gray-700'}`}>
          {data.is_current_crop ? t('crop.currentLabel') : t('crop.exploredLabel')}
        </span>
        <h2 className="font-bold text-field-800 text-lg">{data.display}</h2>
        {data.is_current_crop && data.days_after_sowing !== null && (
          <span className="text-sm text-gray-600">
            · {t('crop.day')} {data.days_after_sowing}
          </span>
        )}
      </div>

      {/* Suitability for an explored crop: "not yours — but could you?" */}
      {!data.is_current_crop && data.suitability?.available && (
        <Card>
          <h3 className="font-semibold text-field-800">
            {t('crop.couldIGrow')}
          </h3>
          <p className="text-sm mt-1">
            <strong>{data.suitability.verdict}</strong> · {data.suitability.score}/100
          </p>
          {data.suitability.reasons?.length > 0 && (
            <ul className="text-sm text-gray-700 list-disc ml-5 mt-2">
              {data.suitability.reasons.map((r: string, i: number) =>
                <li key={i}>{r}</li>)}
            </ul>
          )}
          {data.suitability.limitations?.length > 0 && (
            <ul className="text-sm text-amber-800 list-disc ml-5 mt-2">
              {data.suitability.limitations.map((r: string, i: number) =>
                <li key={i}>{r}</li>)}
            </ul>
          )}
          <p className="text-[11px] text-gray-500 mt-2">{data.suitability.note}</p>
        </Card>
      )}

      <ol className="mt-4 space-y-3">
        {data.stages.map((st, i) => (
          <li key={st.index}>
            <div className={`rounded-2xl border p-3 ${
              st.is_current
                ? 'border-field-600 border-2 bg-field-50 shadow'
                : st.is_past ? 'border-gray-200 bg-gray-50 opacity-75'
                : 'border-gray-200 bg-white'}`}>

              <div className="flex items-start gap-3">
                {/* Stage photograph slot. Falls back to a numbered circle
                    rather than a broken image while assets are pending. */}
                {st.image ? (
                  <img src={st.image} alt={st.stage}
                       className="w-20 h-16 object-cover rounded-lg flex-shrink-0" />
                ) : (
                  <div className="w-20 h-16 rounded-lg flex-shrink-0 bg-field-100
                                  flex items-center justify-center text-field-700
                                  font-bold text-lg">
                    {i + 1}
                  </div>
                )}

                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-bold text-field-800">{st.stage}</h4>
                    {st.is_current && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full
                                       bg-field-700 text-white">
                        {t('crop.youAreHere')}
                      </span>
                    )}
                    {st.is_past && (
                      <span className="text-[10px] text-gray-500">
                        {t('crop.done')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500">
                    {t('crop.days')} {st.start_day}–{st.end_day}
                    {st.duration_days ? ` (${st.duration_days} ${t('crop.daysUnit')})` : ''}
                  </p>

                  {st.tasks?.length > 0 && (
                    <ul className="text-sm text-gray-700 list-disc ml-5 mt-2">
                      {st.tasks.map((task, k) => <li key={k}>{task}</li>)}
                    </ul>
                  )}

                  {st.irrigation && (
                    <p className="text-sm text-blue-800 mt-2">
                      💧 {st.irrigation}
                    </p>
                  )}

                  {st.risks?.length > 0 && (
                    <p className="text-sm text-amber-800 mt-1">
                      ⚠️ {st.risks.join(' · ')}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {i < data.stages.length - 1 && (
              <div className="text-center text-gray-300 leading-none">↓</div>
            )}
          </li>
        ))}
      </ol>

      {!data.is_current_crop && (
        <p className="text-sm text-gray-500 mt-3">{t('crop.notRegistered')}</p>
      )}
    </div>
  )
}
