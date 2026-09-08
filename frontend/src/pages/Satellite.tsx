import { useEffect, useState } from 'react'
import { Card, Button, Spinner, Empty } from '../components/UI'
import { useLanguage } from '../contexts/LanguageContext'
import { getSatelliteField, getSatelliteStatus, getFarms, updateFarm,
         validateFieldLocation } from '../services/api'

/**
 * Live Sentinel-2 view of the farmer's field.
 *
 * Every number here comes from Google Earth Engine via the backend. Nothing is
 * simulated, and when there is no clear satellite pass the page says so rather
 * than showing a stale or invented value — an invented NDVI is worse than a
 * blank card, because a farmer might act on it.
 */

const BAND_COLOUR: Record<string, string> = {
  BARE: '#b45309',
  'VERY LOW': '#d97706',
  LOW: '#ca8a04',
  MODERATE: '#65a30d',
  GOOD: '#16a34a',
  'VERY GOOD': '#15803d',
  EXCELLENT: '#166534',
  UNKNOWN: '#94a3b8',
}

const VERDICT_COLOUR: Record<string, string> = {
  'ON TRACK': '#16a34a',
  'ABOVE EXPECTED': '#15803d',
  'BELOW EXPECTED': '#d97706',
  'WELL BELOW EXPECTED': '#dc2626',
  UNKNOWN: '#94a3b8',
}

export default function Satellite() {
  const { t } = useLanguage()
  const [data, setData] = useState<any>(null)
  const [engine, setEngine] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [err, setErr] = useState('')
  // Lets a farmer (or a developer verifying the Earth Engine hookup) pull a
  // reading for any point without first completing the farm profile.
  const [manual, setManual] = useState(false)
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const [gpsBusy, setGpsBusy] = useState(false)
  const [gpsErr, setGpsErr] = useState('')
  const [landCheck, setLandCheck] = useState<any>(null)
  const [saved, setSaved] = useState('')

  /**
   * Read the phone's GPS and pull a satellite reading for wherever the
   * farmer is standing.
   *
   * WHY THIS ALSO OFFERS TO SAVE
   * ----------------------------
   * Typing coordinates gets a reading on THIS page only. Every other
   * satellite feature — the alerts, the irrigation second opinion, the
   * growth-curve check, the crop advisor context — reads the farm profile.
   * So a farmer who only ever types coordinates here would see satellite
   * data in exactly one place and nowhere else, which looks broken.
   * Saving once switches the whole app on.
   */
  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setGpsErr(t('sat.gpsUnsupported'))
      return
    }
    setGpsBusy(true); setGpsErr(''); setSaved(''); setLandCheck(null)

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const la = Number(pos.coords.latitude.toFixed(6))
        const lo = Number(pos.coords.longitude.toFixed(6))
        setLat(String(la)); setLon(String(lo))
        setManual(true)

        // Accuracy matters here in a way it does not for a map pin. The
        // reading covers a ~100 m circle, so a fix accurate to 2 km is
        // describing someone else's field. Warn rather than silently using it.
        if (pos.coords.accuracy && pos.coords.accuracy > 500) {
          setGpsErr(t('sat.gpsInaccurate').replace(
            '{m}', String(Math.round(pos.coords.accuracy))))
        }

        await load(false, true, { lat: la, lon: lo })

        // Sanity-check that the pin is on cropland at all.
        try {
          const chk = await validateFieldLocation(la, lo)
          if (chk?.checked) setLandCheck(chk.land_cover)
        } catch { /* advisory only — never block the reading */ }

        setGpsBusy(false)
      },
      (err) => {
        setGpsErr(err.code === err.PERMISSION_DENIED
          ? t('sat.gpsDenied')
          : err.code === err.TIMEOUT ? t('sat.gpsTimeout')
          : t('sat.gpsError'))
        setGpsBusy(false)
      },
      // High accuracy: we need field-level precision, not city-level.
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
    )
  }

  /** Persist the coordinates so the rest of the app can use them too. */
  const saveToFarm = async () => {
    setSaved(''); setGpsErr('')
    try {
      const farms = await getFarms()
      const farm = Array.isArray(farms) ? farms[0] : farms?.[0]
      if (!farm?.id) { setGpsErr(t('sat.saveNoFarm')); return }
      await updateFarm(farm.id, {
        ...farm, latitude: Number(lat), longitude: Number(lon),
      })
      setSaved(t('sat.savedOk'))
      setManual(false)
      load(false, false)
    } catch {
      setGpsErr(t('sat.saveFailed'))
    }
  }

  /**
   * Turn an axios failure into something the user can ACT on.
   *
   * The raw FastAPI 404 body is the string "Not Found", which tells the user
   * nothing. A 404 on this route has one overwhelmingly common cause: the
   * running backend predates the satellite router, i.e. uvicorn was not
   * restarted after updating. Say that instead of echoing the status text.
   */
  const explain = (e: any): string => {
    const code = e?.response?.status
    if (code === 404) return t('sat.err404')
    if (code === 401) return t('sat.err401')
    if (code >= 500) return t('sat.err500')
    if (e?.code === 'ERR_NETWORK') return t('sat.errNetwork')
    return e?.response?.data?.detail || e?.friendlyMessage || t('sat.error')
  }

  const load = async (force = false, useManual = manual,
                      override?: { lat: number; lon: number }) => {
    force ? setRefreshing(true) : setLoading(true)
    setErr('')

    // Fetched INDEPENDENTLY on purpose. Under Promise.all a failure in either
    // call discarded both results, so a broken field query also hid the engine
    // diagnostics — the very thing that explains the failure.
    const coords = override
      ? { lat: override.lat, lon: override.lon }
      : useManual && lat && lon
        ? { lat: Number(lat), lon: Number(lon) } : {}
    const [fieldRes, statusRes] = await Promise.allSettled([
      getSatelliteField({ force_refresh: force, months: 12, ...coords }),
      getSatelliteStatus(),
    ])

    if (statusRes.status === 'fulfilled') setEngine(statusRes.value)
    if (fieldRes.status === 'fulfilled') setData(fieldRes.value)
    else setErr(explain(fieldRes.reason))

    setLoading(false)
    setRefreshing(false)
  }

  useEffect(() => { load(false) }, [])

  if (loading) return <Spinner />

  const ok = data?.status === 'ok' || data?.status === 'stale'
  const obs = data?.observation || {}
  const band = data?.classification?.band || 'UNKNOWN'

  return (
    <div>
      <h1>🛰️ {t('sat.title')}</h1>
      <p className="muted">{t('sat.subtitle')}</p>

      {err && <div className="error">{err}</div>}

      {/* Setup checklist. Shown whenever the engine is not ready, because
          "no data" has three quite different causes and guessing between them
          wastes the user's time. */}
      {engine && !engine.ready && (
        <Card>
          <h3>{t('sat.setupTitle')}</h3>
          <p className="muted">{engine.error}</p>
          <ol>
            <li>{t('sat.setup1')}</li>
            <li>{t('sat.setup2')}</li>
            <li>{t('sat.setup3')}</li>
          </ol>
        </Card>
      )}

      {/* Manual coordinates — check any point without a farm profile. */}
      <Card>
        <h3>{t('sat.checkPoint')}</h3>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <Button onClick={useMyLocation} disabled={gpsBusy}>
            📍 {gpsBusy ? t('sat.locating') : t('sat.useMyLocation')}
          </Button>
          {lat && lon && (
            <Button variant="ghost" onClick={saveToFarm}>
              {t('sat.saveToFarm')}
            </Button>
          )}
        </div>
        {gpsErr && <div className="error">{gpsErr}</div>}
        {saved && <div style={{ color: '#16a34a', fontWeight: 600 }}>{saved}</div>}
        {landCheck && (
          <div style={{
            padding: 8, borderRadius: 8, margin: '8px 0',
            background: landCheck.verdict === 'NOT VEGETATED' ? '#fef3c7' : '#f0fdf4',
          }}>
            <strong>{t(`sat.cover.${landCheck.verdict}`)}</strong>
            <div className="muted" style={{ fontSize: 13 }}>{landCheck.note}</div>
          </div>
        )}
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <input value={lat} onChange={(e) => setLat(e.target.value)}
                 placeholder={t('sat.latitude')} style={{ width: 140 }} />
          <input value={lon} onChange={(e) => setLon(e.target.value)}
                 placeholder={t('sat.longitude')} style={{ width: 140 }} />
          <Button onClick={() => { setManual(true); load(false, true) }}
                  disabled={!lat || !lon}>
            {t('sat.check')}
          </Button>
          {manual && (
            <Button variant="ghost"
                    onClick={() => { setManual(false); load(false, false) }}>
              {t('sat.useMyFarm')}
            </Button>
          )}
        </div>
        <p className="muted" style={{ fontSize: 12 }}>{t('sat.checkHelp')}</p>
      </Card>

      {/* No coordinates saved yet. */}
      {data?.status === 'no_location' && (
        <Empty msg={data.message} />
      )}

      {/* Earth Engine answered, but every pass was too cloudy. */}
      {data?.status === 'no_observation' && (
        <Card>
          <h3>{t('sat.noPass')}</h3>
          <p className="muted">{data.message}</p>
        </Card>
      )}

      {ok && (
        <>
          {/* ---- Headline NDVI ---- */}
          <Card>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <div>
                <div className="muted">{t('sat.ndviLabel')}</div>
                <div style={{
                  fontSize: 52, fontWeight: 700, lineHeight: 1.1,
                  color: BAND_COLOUR[band] || '#334155',
                }}>
                  {data.ndvi?.toFixed(3)}
                </div>
                <div style={{ color: BAND_COLOUR[band], fontWeight: 600 }}>
                  {t(`sat.band.${band}`)}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div className="muted">{t('sat.observed')}</div>
                <div style={{ fontWeight: 600 }}>{obs.date}</div>
                <div className="muted">
                  {obs.days_ago} {t('sat.daysAgo')}
                </div>
                {obs.is_stale && (
                  <div style={{ color: '#d97706', fontWeight: 600 }}>
                    ⚠ {t('sat.stale')}
                  </div>
                )}
              </div>
            </div>
            <p className="muted">{data.classification?.meaning}</p>
            <div className="muted" style={{ fontSize: 13 }}>
              {t('sat.cloudFree')}:{' '}
              {Math.round((obs.clear_pixel_fraction || 0) * 100)}% ·{' '}
              {t('sat.resolution')}: {obs.resolution_m}m ·{' '}
              {t('sat.area')}: {obs.footprint?.area_ha} ha
              {data.cached && ` · ${t('sat.cached')}`}
            </div>
            <Button onClick={() => load(true)} disabled={refreshing}>
              {refreshing ? t('sat.refreshing') : t('sat.refresh')}
            </Button>
          </Card>

          {/* ---- Growth curve check ---- */}
          {data.phenology?.comparable && (
            <Card>
              <h3>{t('sat.growthCheck')}</h3>
              <div style={{
                fontWeight: 700, fontSize: 18,
                color: VERDICT_COLOUR[data.phenology.verdict] || '#334155',
              }}>
                {t(`sat.verdict.${data.phenology.verdict}`)}
              </div>
              <p>{data.phenology.note}</p>
              <div className="muted">
                {t('sat.measured')}: {data.phenology.measured_ndvi} ·{' '}
                {t('sat.expected')}: {data.phenology.expected_ndvi}
              </div>
            </Card>
          )}

          {/* ---- Other indices ---- */}
          <Card>
            <h3>{t('sat.indices')}</h3>
            <table>
              <tbody>
                {Object.entries(data.indices || {}).map(([k, v]: any) => (
                  <tr key={k}>
                    <td style={{ fontWeight: 600 }}>{k.toUpperCase()}</td>
                    <td>{v === null ? '—' : Number(v).toFixed(3)}</td>
                    <td className="muted" style={{ fontSize: 12 }}>
                      {data.index_definitions?.[k]}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* ---- Canopy moisture ---- */}
          {data.water_stress?.available && (
            <Card>
              <h3>{t('sat.moisture')}</h3>
              <div style={{ fontWeight: 700 }}>
                {t(`sat.water.${data.water_stress.level}`)}
              </div>
              <p>{data.water_stress.note}</p>
              <p>{data.water_stress.irrigation_hint}</p>
              <p className="muted" style={{ fontSize: 12 }}>
                {data.water_stress.caveat}
              </p>
            </Card>
          )}

          {/* ---- Field uniformity ---- */}
          {data.uniformity?.available && (
            <Card>
              <h3>{t('sat.uniformity')}</h3>
              <div style={{ fontWeight: 700 }}>
                {t(`sat.uniform.${data.uniformity.level}`)}
              </div>
              <p>{data.uniformity.advice}</p>
              <div className="muted">{data.uniformity.zone_note}</div>
              <p className="muted" style={{ fontSize: 12 }}>
                {data.uniformity.caveat}
              </p>
            </Card>
          )}

          {/* ---- Change since last pass ---- */}
          {data.change?.available && (
            <Card>
              <h3>{t('sat.change')}</h3>
              <div style={{ fontWeight: 700 }}>
                {t(`sat.dir.${data.change.direction}`)}{' '}
                ({data.change.change > 0 ? '+' : ''}{data.change.change})
              </div>
              <p>{data.change.note}</p>
              {data.change.possible_causes?.length > 0 && (
                <ul>
                  {data.change.possible_causes.map((c: string, i: number) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              )}
            </Card>
          )}

          {/* ---- Scouting priority ---- */}
          {data.scouting && (
            <Card>
              <h3>{t('sat.scouting')}</h3>
              <div style={{ fontWeight: 700 }}>
                {t(`sat.priority.${data.scouting.priority}`)}
              </div>
              <p>{data.scouting.window}</p>
              <ul>
                {data.scouting.reasons?.map((r: string, i: number) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              {data.scouting.start_here && <p>{data.scouting.start_here}</p>}
            </Card>
          )}

          {/* ---- Season curve ---- */}
          {data.series?.points?.length > 0 && (
            <Card>
              <h3>{t('sat.seasonCurve')}</h3>
              <NdviCurve points={data.series.points} />
              {data.productivity?.available && (
                <p className="muted">{data.productivity.note}</p>
              )}
            </Card>
          )}

          <p className="muted" style={{ fontSize: 12 }}>{data.disclaimer}</p>
        </>
      )}
    </div>
  )
}

/** Minimal inline NDVI curve. No chart library — this keeps the bundle small. */
function NdviCurve({ points }: { points: any[] }) {
  const W = 640, H = 180, PAD = 30
  const vals = points.map((p) => p.ndvi).filter((v) => v !== null)
  if (!vals.length) return null

  const max = Math.max(...vals, 0.8)
  const min = Math.min(...vals, 0)
  const span = max - min || 1

  const x = (i: number) => PAD + (i * (W - PAD * 2)) / Math.max(1, points.length - 1)
  const y = (v: number) => H - PAD - ((v - min) / span) * (H - PAD * 2)

  const path = points
    .map((p, i) => (p.ndvi === null ? null : `${x(i)},${y(p.ndvi)}`))
    .filter(Boolean)
    .join(' ')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto' }}>
      <polyline points={path} fill="none" stroke="#16a34a" strokeWidth={2.5} />
      {points.map((p, i) =>
        p.ndvi === null ? null : (
          <circle key={i} cx={x(i)} cy={y(p.ndvi)} r={3} fill="#16a34a">
            <title>{`${p.month}: ${p.ndvi}`}</title>
          </circle>
        )
      )}
      {points.map((p, i) =>
        i % 2 === 0 ? (
          <text key={`l${i}`} x={x(i)} y={H - 8} fontSize={10}
                textAnchor="middle" fill="#64748b">
            {p.month?.slice(2)}
          </text>
        ) : null
      )}
      <text x={4} y={y(max)} fontSize={10} fill="#64748b">{max.toFixed(2)}</text>
      <text x={4} y={y(min)} fontSize={10} fill="#64748b">{min.toFixed(2)}</text>
    </svg>
  )
}
