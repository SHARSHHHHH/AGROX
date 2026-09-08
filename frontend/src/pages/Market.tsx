import { useEffect, useState } from 'react'
import {
  calculateROI, getCropList, getOffers,
  getMandiSummary, getMyMandiPrice, getUser, getOnboardingStatus,
} from '../services/api'
import { Card, Button, Spinner } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { usePageContext } from '../contexts/PageContext'

/**
 * Status badge. The whole point of the market/fertilizer services is that they
 * never invent a number, so the UI must show WHICH kind of data the farmer is
 * looking at. A mock price rendered like a real one would defeat the backend
 * guarantee entirely.
 */
function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { cls: string; label: string }> = {
    ok: { cls: 'bg-green-100 text-green-800 border-green-300', label: 'LIVE GOVT DATA' },
    empty: { cls: 'bg-gray-100 text-gray-600 border-gray-300', label: 'NO ARRIVALS' },
    not_configured: { cls: 'bg-red-100 text-red-700 border-red-300', label: 'NOT CONFIGURED' },
    mock: { cls: 'bg-amber-100 text-amber-800 border-amber-400', label: '⚠ SAMPLE DATA' },
    unavailable: { cls: 'bg-gray-200 text-gray-600 border-gray-300', label: 'NO DATA' },
  }
  const s = map[status] || map.unavailable
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-bold ${s.cls}`}>
      {s.label}
    </span>
  )
}

export default function Market() {
  const { t, tv } = useLanguage()
  const { publish } = usePageContext()
  const [tab, setTab] = useState<'prices' | 'roi'>('prices')

  // --- prices ---
  const [crops, setCrops] = useState<any[]>([])
  const [crop, setCrop] = useState('soybean')
  const [price, setPrice] = useState<any>(null)
  const [myPrice, setMyPrice] = useState<any>(null)
  const [offers, setOffers] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [stateFilter, setStateFilter] = useState('')
  const [fellBackNationwide, setFellBackNationwide] = useState(false)

  // --- roi ---
  const [roiForm, setRoiForm] = useState({
    offer_price: '320', standard_price: '400', bags: '20',
    distance_km: '12', crop: 'soybean', acres: '2',
  })
  const [roi, setRoi] = useState<any>(null)
  const [roiBusy, setRoiBusy] = useState(false)

  useEffect(() => {
    getCropList().then(setCrops).catch(() => {})
    getMyMandiPrice().then(setMyPrice).catch(() => {})
    getOffers().then((res) => {
      setOffers(res)
      publish('Market & Offers', res?.offers?.length
        ? `${res.offers.length} fertilizer offer(s) available (${res.status}): `
          + res.offers.map((o: any) => `${o.product} from ${o.vendor} at ₹${o.offer_price} (normally ₹${o.standard_price})`).join('; ')
        : `No fertilizer offers currently available (${res?.status || 'unavailable'}).`)
    }).catch(() => {})

    // Prefill the state to check with the farmer's own saved state — this
    // used to be hardcoded to "Madhya Pradesh" for every farmer regardless
    // of where they actually are, which is the main reason "check price"
    // looked broken for anyone else: real government mandi data is reported
    // per state, so querying the wrong state routinely comes back empty.
    const u = getUser()
    if (u?.state) { setStateFilter(u.state); return }
    getOnboardingStatus().then((s) => {
      if (s?.farm?.state) setStateFilter(s.farm.state)
    }).catch(() => {})
  }, [])

  const lookup = async () => {
    setBusy(true); setPrice(null); setFellBackNationwide(false)
    try {
      let res = await getMandiSummary(crop, stateFilter)
      // AGMARKNET reporting is patchy day to day — not every state reports
      // every crop every day. Rather than dead-ending on "empty" for a
      // state-scoped query, fall back to a nationwide query so the farmer
      // still gets a real, current price, clearly labelled as nationwide
      // rather than silently swapped in.
      let fellBack = false
      if (res?.status === 'empty' && stateFilter) {
        const nationwide = await getMandiSummary(crop, '')
        if (nationwide?.status === 'ok') {
          res = nationwide
          fellBack = true
          setFellBackNationwide(true)
        }
      }
      setPrice(res)
      publish('Market & Offers', res?.status === 'ok'
        ? `Checked price for ${crop}${stateFilter ? ` in ${stateFilter}` : ''}: `
          + `₹${res.best_market.modal_price}/quintal at ${res.best_market.market || res.best_market.name || 'the reporting market'}, `
          + `as of ${res.latest_date}.` + (fellBack ? ' (No state data — showing nationwide price instead.)' : '')
        : `Checked price for ${crop}${stateFilter ? ` in ${stateFilter}` : ''} — `
          + `${res?.status === 'empty' ? 'no recent arrivals reported' : 'data unavailable'}.`)
    } catch { /* handled below */ }
    finally { setBusy(false) }
  }

  const runROI = async () => {
    setRoiBusy(true); setRoi(null)
    try {
      const res = await calculateROI({
        offer_price: Number(roiForm.offer_price),
        standard_price: Number(roiForm.standard_price),
        bags: Number(roiForm.bags),
        distance_km: Number(roiForm.distance_km),
        crop: roiForm.crop,
        acres: Number(roiForm.acres),
      })
      setRoi(res)
      publish('Market & Offers', `Checked whether a fertilizer offer is worth it: `
        + `offer ₹${roiForm.offer_price}/bag vs normal ₹${roiForm.standard_price}/bag, `
        + `${roiForm.bags} bag(s), ${roiForm.distance_km} km away. `
        + `Verdict: ${res.worth_it ? 'worth it' : 'not worth it'} — ${res.verdict} `
        + `Net: ₹${res.profit}. Break-even distance: ${res.break_even_distance_km} km.`)
    } catch { /* handled below */ }
    finally { setRoiBusy(false) }
  }

  const useOffer = (o: any) => {
    setRoiForm({
      ...roiForm,
      offer_price: String(o.offer_price),
      standard_price: String(o.standard_price),
      distance_km: String(o.distance_km),
    })
    setTab('roi')
  }

  const roiField = (key: keyof typeof roiForm, label: string) => (
    <div>
      <label className="block text-[11px] font-semibold text-gray-500 mb-1">{label}</label>
      <input
        value={roiForm[key]}
        onChange={(e) => setRoiForm({ ...roiForm, [key]: e.target.value })}
        className="w-full border rounded-lg px-2.5 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600"
      />
    </div>
  )

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-field-800 mb-1">💰 {t('market.title')}</h1>
      <p className="text-sm text-gray-500 mb-4">
        {t('market.subtitle')}
      </p>

      <div className="flex gap-2 mb-5">
        {(['prices', 'roi'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition
              ${tab === t ? 'bg-field-600 text-white shadow' : 'bg-white hover:bg-field-50 border'}`}
          >
            {t === 'prices' ? 'Crop prices' : 'Is this offer worth it?'}
          </button>
        ))}
      </div>

      {/* ---------------- PRICES ---------------- */}
      {tab === 'prices' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card>
            <h3 className="font-semibold text-field-800 mb-3">{t('market.check')}</h3>
            <div className="flex gap-2 mb-2">
              <select
                value={crop}
                onChange={(e) => setCrop(e.target.value)}
                className="flex-1 border rounded-lg px-2.5 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600"
              >
                {crops.map((c) => (
                  <option key={c.key} value={c.key}>{tv(c.display)}</option>
                ))}
              </select>
              <Button onClick={lookup} disabled={busy}>
                {busy ? '…' : 'Check'}
              </Button>
            </div>
            <input
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              placeholder={t('common.state')}
              className="w-full border rounded-lg px-2.5 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600"
            />

            {fellBackNationwide && (
              <p className="text-[11px] text-amber-800 bg-amber-50 rounded-lg p-2 mt-2">
                {t('mandi.nationwide')}
              </p>
            )}

            {price && (
              <div className="mt-4 border rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-field-800 capitalize">{tv(price.crop)}</span>
                  <StatusBadge status={price.status} />
                </div>

                {price.status === 'ok' ? (
                  <>
                    <div className="text-2xl font-bold text-field-800">
                      ₹{price.best_market.modal_price.toLocaleString()}
                      <span className="text-sm font-normal text-gray-500">
                        {' '}{t('mandi.perquintal')}
                      </span>
                    </div>
                    <div className="text-xs text-gray-600 mt-1">
                      🏆 {t('mandi.best')}: <b>{price.best_market.market}</b>,{' '}
                      {price.best_market.district}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      {t('mandi.range')} ₹{price.modal_min.toLocaleString()}–
                      ₹{price.modal_max.toLocaleString()} ·{' '}
                      {price.markets_reporting} {t('mandi.markets')}
                    </div>
                    <div className="text-[11px] text-gray-400 mt-1">
                      {t('mandi.date')} {price.latest_date}
                    </div>
                    <p className="text-[10px] text-gray-400 mt-2 border-t pt-2">
                      {price.disclaimer}
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-gray-600">
                    {price.status === 'empty' ? t('mandi.none') : t('mandi.unavailable')}
                  </p>
                )}

                {price.warning && (
                  <p className="text-[11px] text-amber-800 bg-amber-50 rounded-lg p-2 mt-2">
                    {price.warning}
                  </p>
                )}
                {price.advice && (
                  <p className="text-[11px] text-gray-500 mt-2">{price.advice}</p>
                )}
              </div>
            )}

            {myPrice && (
              <div className="mt-4 border-t pt-3">
                <p className="text-[11px] font-semibold text-gray-500 uppercase mb-1">
                  {t('market.yourcrop')}
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-sm capitalize">{myPrice.crop || '—'}</span>
                  <StatusBadge status={myPrice.status} />
                </div>
              </div>
            )}
          </Card>

          <Card>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-field-800">{t('market.offers')}</h3>
              {offers && <StatusBadge status={offers.status} />}
            </div>

            {!offers && <Spinner />}
            {offers?.offers?.length === 0 && (
              <p className="text-sm text-gray-500">{offers.message}</p>
            )}

            <div className="space-y-2">
              {offers?.offers?.map((o: any) => (
                <div key={o.id} className="border rounded-xl p-3">
                  <div className="font-semibold text-sm text-field-800">{o.product}</div>
                  <div className="text-xs text-gray-500">{o.vendor}</div>
                  <div className="text-sm mt-1">
                    <span className="font-bold text-green-700">₹{o.offer_price}</span>
                    <span className="line-through text-gray-400 ml-2">₹{o.standard_price}</span>
                    <span className="text-gray-500 ml-2">· {o.distance_km} km away</span>
                  </div>
                  <button
                    onClick={() => useOffer(o)}
                    className="mt-2 text-xs text-field-700 font-semibold hover:underline"
                  >
                    {t('market.worthit')}
                  </button>
                </div>
              ))}
            </div>

            {offers?.warning && (
              <p className="text-[11px] text-amber-800 bg-amber-50 rounded-lg p-2 mt-3">
                {offers.warning}
              </p>
            )}
          </Card>
        </div>
      )}

      {/* ---------------- ROI ---------------- */}
      {tab === 'roi' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card>
            <h3 className="font-semibold text-field-800 mb-3">{t('market.offerdetails')}</h3>
            <div className="grid grid-cols-2 gap-3">
              {roiField('offer_price', 'Offer price / bag (₹)')}
              {roiField('standard_price', 'Normal price / bag (₹)')}
              {roiField('bags', 'Number of bags')}
              {roiField('distance_km', 'Distance (km)')}
              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1">{t('common.crop')}</label>
                <select
                  value={roiForm.crop}
                  onChange={(e) => setRoiForm({ ...roiForm, crop: e.target.value })}
                  className="w-full border rounded-lg px-2.5 py-2 text-sm outline-none focus:ring-2 focus:ring-field-600"
                >
                  {crops.map((c) => (
                    <option key={c.key} value={c.key}>{tv(c.display)}</option>
                  ))}
                </select>
              </div>
              {roiField('acres', 'Acres')}
            </div>
            <Button onClick={runROI} disabled={roiBusy}>
              {roiBusy ? t('common.calculating') : t('common.calculate')}
            </Button>
          </Card>

          <Card>
            <h3 className="font-semibold text-field-800 mb-2">{t('common.result')}</h3>
            {roiBusy && <Spinner />}
            {!roiBusy && !roi && (
              <p className="text-sm text-gray-400 py-8 text-center">
                {t('market.enterpress')}
              </p>
            )}

            {roi && (
              <div className="space-y-3">
                <div className={`rounded-xl p-3 ${roi.worth_it ? 'bg-green-50' : 'bg-red-50'}`}>
                  <div className={`text-xl font-bold ${roi.worth_it ? 'text-green-800' : 'text-red-700'}`}>
                    {roi.worth_it ? '✅ Worth it' : '❌ Not worth it'}
                  </div>
                  <div className="text-sm text-gray-700 mt-1">{roi.verdict}</div>
                </div>

                <div>
                  <p className="text-[11px] font-semibold text-gray-500 uppercase mb-1">
                    {t('market.breakdown')}
                  </p>
                  <table className="w-full text-sm">
                    <tbody>
                      <tr className="border-b">
                        <td className="py-1 text-gray-600">{t('market.bagscost')}</td>
                        <td className="py-1 text-right">−₹{roi.breakdown.purchase_cost.toLocaleString()}</td>
                      </tr>
                      <tr className="border-b">
                        <td className="py-1 text-gray-600">
                          Transport ({roi.breakdown.distance_km} km round trip)
                        </td>
                        <td className="py-1 text-right">−₹{roi.breakdown.transport_cost.toLocaleString()}</td>
                      </tr>
                      <tr className="border-b">
                        <td className="py-1 text-gray-600">{t('market.saving')}</td>
                        <td className="py-1 text-right text-green-700">
                          +₹{roi.breakdown.store_savings.toLocaleString()}
                        </td>
                      </tr>
                      <tr className="border-b">
                        <td className="py-1 text-gray-600">
                          Extra yield ({roi.breakdown.extra_tonnes} t)
                        </td>
                        <td className="py-1 text-right text-green-700">
                          +₹{roi.breakdown.revenue_gain.toLocaleString()}
                        </td>
                      </tr>
                      <tr className="font-bold">
                        <td className="py-1.5">{t('market.net')}</td>
                        <td className={`py-1.5 text-right ${roi.profit >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                          {roi.profit >= 0 ? '+' : '−'}₹{Math.abs(roi.profit).toLocaleString()}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <p className="text-xs text-gray-600">
                  Break-even distance: <b>{roi.break_even_distance_km} km</b>
                </p>

                {!roi.yield_revenue_counted && (
                  <p className="text-[11px] text-amber-800 bg-amber-50 rounded-lg p-2">
                    {roi.revenue_note}
                  </p>
                )}

                <div>
                  <p className="text-[11px] font-semibold text-gray-500 uppercase mb-1">
                    {t('market.assumptions')}
                  </p>
                  <ul className="text-[11px] text-gray-500 list-disc ml-4 space-y-0.5">
                    {roi.assumptions.map((a: string, i: number) => <li key={i}>{a}</li>)}
                  </ul>
                </div>

                <p className="text-[10px] text-gray-400 border-t pt-2">{roi.disclaimer}</p>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
