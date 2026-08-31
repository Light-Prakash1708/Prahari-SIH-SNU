/* PRAHARI · irrigation advisor and the weed check.

   Both screens exist to say the same uncomfortable thing clearly: this is a
   MODEL, not a measurement. The irrigation card ends with "push an auger in
   and look"; the weed card refuses to name a species or a herbicide. Neither
   is hedging — they are the honest boundary of what a weather feed and one
   photograph can tell you. */
import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Loading, Prov, Why, bi } from '../ui'

export default function Water({ lang, plot, go }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)
  const [weeds, setWeeds] = useState(null)
  const [series, setSeries] = useState(null)
  const fileRef = useRef(null)

  const load = () => {
    if (!plot) { setBusy(false); return }
    setBusy(true)
    api.irrigation(plot.id).then(setD).catch(setErr).finally(() => setBusy(false))
    api.weedSeries(plot.id).then(setSeries).catch(() => setSeries(null))
  }
  useEffect(load, [plot?.id])

  const logIt = async () => {
    try { await api.logIrrigation(plot.id, { mm_applied: d?.apply_mm || null }); load() }
    catch (e) { setErr(e) }
  }

  const checkWeeds = async (file) => {
    setErr(null)
    try { setWeeds(await api.weedCheck(plot.id, file)) } catch (e) { setErr(e) }
  }

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('crop')} aria-label="Back">←</button>
        <h1 className="grow">{lang === 'mr' ? 'पाणी आणि तण' : 'Water & weeds'}</h1>
      </div>

      <div className="pad stack" style={{ paddingTop: 12 }}>
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}
        {busy && <Loading lines={3} />}

        {d && !d.available && <div className="note">{d.reason}</div>}

        {d?.available && (
          <>
            <div className={`decision ${d.tone === 'warn' ? 'amber' : d.tone === 'ok' ? 'green'
              : d.tone === 'info' ? 'grey' : 'grey'}`}>
              <div className="shield">
                {d.verdict === 'irrigate' ? '💧' : d.verdict === 'wait_for_rain' ? '🌧'
                  : d.verdict === 'rainfed' ? '🌾' : '✅'}
              </div>
              <div className="ans">
                {d.verdict === 'irrigate' ? (lang === 'mr' ? 'पाणी द्या' : 'Irrigate')
                  : d.verdict === 'wait_for_rain' ? (lang === 'mr' ? 'पावसाची वाट पहा' : 'Wait for the rain')
                  : d.verdict === 'rainfed' ? (lang === 'mr' ? 'कोरडवाहू' : 'Rainfed')
                  : (lang === 'mr' ? 'आज नको' : 'Not today')}
              </div>
              <div className="why">{d.say}</div>
            </div>

            <Card>
              <div className="card-title" style={{ marginBottom: 10 }}>
                {lang === 'mr' ? 'पाण्याचा ताळेबंद' : 'The water balance'}
              </div>
              <div className="etlbar">
                <i style={{
                  width: `${Math.min(100, (d.depletion_mm / Math.max(d.taw_mm, 1)) * 100)}%`,
                  background: d.depletion_mm >= d.raw_mm ? 'var(--warn)' : 'var(--g-400)',
                }} />
              </div>
              <div className="row between tiny muted" style={{ marginTop: 6 }}>
                <span>{lang === 'mr' ? 'वापरलेले' : 'used'} {d.depletion_mm} mm</span>
                <span>{lang === 'mr' ? 'मर्यादा' : 'stress at'} {d.raw_mm} mm</span>
                <span>{lang === 'mr' ? 'एकूण' : 'holds'} {d.taw_mm} mm</span>
              </div>
              <div className="tiles" style={{ marginTop: 14 }}>
                <div className="tile"><div className="ic">☀️</div>
                  <div className="lbl">ET₀</div><div className="val">{d.et0_today} mm</div></div>
                <div className="tile"><div className="ic">🌱</div>
                  <div className="lbl">Kc</div><div className="val">{d.kc}</div></div>
                <div className="tile"><div className="ic">🌧</div>
                  <div className="lbl">{lang === 'mr' ? 'येणारा पाऊस' : 'rain ahead'}</div>
                  <div className="val">{d.forecast_effective_rain_mm} mm</div></div>
              </div>

              <Why label={lang === 'mr' ? 'हा आकडा कसा काढला?' : 'How is this computed?'}>
                <p style={{ marginBottom: 8 }}>{d.method_note}</p>
                <p className="mono tiny" style={{ marginBottom: 8 }}>
                  ET0 = 0.0023 × Ra × (Tmean + 17.8) × √(Tmax − Tmin)<br />
                  depletion = Σ (ET0 × Kc − effective rain), since {d.balance_since}
                </p>
                <p className="small">
                  {lang === 'mr' ? 'ताळेबंद येथून सुरू:' : 'Balance runs from:'} {d.balance_reset_by}.
                  {' '}{d.soil.label} soil, {d.root_depth_m} m rooting, p = {d.depletion_fraction_p}.
                </p>
                <Prov label="Source" value={d.source} />
                <Prov label="Weather" value={`${d.weather_source} (${d.weather_kind})`} />
              </Why>

              <div className="note warn" style={{ marginTop: 12 }}>
                {bi(lang, d.caveat, d.caveat_mr)}
              </div>
              <button className="btn block ghost" style={{ marginTop: 12 }} onClick={logIt}>
                {lang === 'mr' ? 'मी पाणी दिले — नोंदवा' : 'I irrigated — record it'}
              </button>
              {d.last_irrigation && (
                <div className="tiny faint center" style={{ marginTop: 8 }}>
                  {lang === 'mr' ? 'शेवटची नोंद' : 'last recorded'} {d.last_irrigation}
                </div>
              )}
            </Card>
          </>
        )}

        {/* ── weeds ────────────────────────────────────────────────────── */}
        <Card>
          <div className="card-title" style={{ marginBottom: 4 }}>
            {lang === 'mr' ? 'तण तपासणी' : 'Weed check'}
          </div>
          <p className="tiny muted" style={{ marginBottom: 12 }}>
            {lang === 'mr'
              ? 'दोन ओळींमधील जमिनीचा फोटो कमरेच्या उंचीवरून घ्या. दर आठवड्याला त्याच पद्धतीने घेतल्यास तुलना करता येते.'
              : 'Photograph the ground between two rows, from about waist height. Taken the same way each week, the series is what makes it useful.'}
          </p>
          <input ref={fileRef} type="file" accept="image/*" capture="environment"
                 style={{ display: 'none' }}
                 onChange={e => e.target.files?.[0] && checkWeeds(e.target.files[0])} />
          <button className="btn block ghost" onClick={() => fileRef.current?.click()}>
            📷 {lang === 'mr' ? 'जमिनीचा फोटो घ्या' : 'Photograph the ground'}
          </button>

          {weeds && !weeds.usable && (
            <div className="note warn" style={{ marginTop: 12 }}>
              {bi(lang, weeds.message, weeds.message_mr)}
            </div>
          )}
          {weeds?.usable && (
            <>
              <div className="row between" style={{ marginTop: 14 }}>
                <div>
                  <div className="gauge-num" style={{ fontSize: 30 }}>{weeds.green_cover_pct}%</div>
                  <div className="tiny muted">{lang === 'mr' ? 'हिरवे आच्छादन' : 'green cover'}</div>
                </div>
                <span className={`badge ${weeds.band === 'clean' ? 'ok'
                  : weeds.band === 'heavy' ? 'bad' : 'warn'}`}>
                  {weeds.band} · {weeds.pattern}
                </span>
              </div>
              <div className="note" style={{ marginTop: 10 }}>{weeds.advice?.say}</div>
              <Prov label="Index" value={weeds.index} />
              <Prov label={lang === 'mr' ? 'मर्यादा' : 'Limits'} value={weeds.limits} />
            </>
          )}

          {series?.checks?.length > 0 && (
            <>
              <div className="tiny" style={{ fontWeight: 700, marginTop: 16, marginBottom: 6 }}>
                {lang === 'mr' ? 'मागील तपासण्या' : 'Series'}
              </div>
              {series.checks.slice(0, 6).map(c => (
                <div className="changerow" key={c.id}>
                  <div className="ic" style={{ background: 'var(--sunk)' }}>🌿</div>
                  <div className="nm">{c.checked_on}</div>
                  <div className="st">
                    {c.usable ? `${Math.round((c.cover_fraction || 0) * 100)}%` : '—'}
                  </div>
                </div>
              ))}
              <Prov label={lang === 'mr' ? 'टीप' : 'Note'} value={series.note} />
            </>
          )}
        </Card>
      </div>
    </>
  )
}
