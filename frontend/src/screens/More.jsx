/* PRAHARI · forecast, traps, alerts, re-scan and profile.

   Grouped in one file because each is a single screen with one job, and a file
   per screen would be filing for its own sake. */
import React, { useEffect, useState } from 'react'
import { api, auth, setLang as persistLang } from '../api'
import {
  Bars, Card, Empty, ErrorNote, Loading, Prov, Seg, Sheet, Spark, WeatherStrip, Why,
  bi, fmtDate, fmtMoney, levelLabel,
} from '../ui'

/* ═══ WHAT IS COMING ═══════════════════════════════════════════════════ */
export function Forecast({ lang, plot, go }) {
  const [data, setData] = useState(null)
  const [risk, setRisk] = useState(null)
  const [err, setErr] = useState(null)
  const [tab, setTab] = useState('disease')

  const load = () => {
    if (!plot) return
    setErr(null)
    Promise.all([api.forecast(plot.id), api.risk(plot.id).catch(() => null)])
      .then(([f, r]) => { setData(f); setRisk(r) })
      .catch(setErr)
  }
  useEffect(load, [plot?.id])

  const board = (risk?.board || []).filter(b => b.kind === (tab === 'disease' ? 'disease' : 'pest'))

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{lang === 'mr' ? 'धोक्याचा अंदाज' : 'Risk Forecast'}</h1>
      </div>
      <div className="pad stack" style={{ paddingTop: 14 }}>
        <Seg value={tab} onChange={setTab} options={[
          { value: 'disease', label: lang === 'mr' ? 'रोगाचा धोका' : 'Disease Risk' },
          { value: 'pest', label: lang === 'mr' ? 'किडीचा धोका' : 'Pest Risk' },
        ]} />

        {!data && !err && <Loading lines={3} />}
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}

        {data && tab === 'disease' && (
          <>
            <Card>
              <div className="row between" style={{ marginBottom: 12 }}>
                <div>
                  <div className="card-title">{lang === 'mr' ? 'पुढील ४ दिवस' : 'Next 4 days'}</div>
                  <div className="tiny faint">{plot?.crop_label || plot?.crop} · {plot?.taluka_name}</div>
                </div>
                <span className={`badge ${data.headline.level === 'high' ? 'bad'
                  : data.headline.level === 'rising' ? 'warn'
                  : data.headline.level === 'watch' ? 'info' : 'ok'}`}>
                  {levelLabel(data.headline.level, lang)}
                </span>
              </div>
              <div className="fcast">
                {data.forecast.map(d => (
                  <div className={`d ${d.level}`} key={d.date}>
                    <div className="dy">{d.offset === 0 ? (lang === 'mr' ? 'आज' : 'Today') : fmtDate(d.date, lang)}</div>
                    <div className="lv">{levelLabel(d.level, lang)}</div>
                  </div>
                ))}
              </div>
              <h2 className="h2" style={{ marginTop: 16, fontSize: 17 }}>
                {bi(lang, data.headline.title, data.headline.title_mr)}
              </h2>
              <ul style={{ margin: '10px 0 0 17px', fontSize: 13.5, color: 'var(--ink-2)' }}>
                {(lang === 'mr' ? data.headline.reasons_mr : data.headline.reasons).map((r, i) =>
                  <li key={i} style={{ marginTop: 5 }}>{r}</li>)}
              </ul>
              <WeatherStrip weather={data.weather} />
            </Card>

            <Card>
              <div className="card-title" style={{ marginBottom: 10 }}>
                {lang === 'mr' ? 'हवामान घटक' : 'Contributing weather'}
              </div>
              {[['rh90_hours', lang === 'mr' ? 'आर्द्रता ९०%+ तास' : 'Hours at RH ≥ 90%', 'h'],
                ['rain_mm', lang === 'mr' ? 'पाऊस' : 'Rainfall', 'mm'],
                ['tmin', lang === 'mr' ? 'रात्रीचे किमान तापमान' : 'Night minimum', '°C']].map(([k, label, unit]) => (
                <div className="row between" key={k} style={{ padding: '9px 0', borderBottom: '1px solid var(--rule-soft)' }}>
                  <span className="small">{label}</span>
                  <span className="row" style={{ gap: 8 }}>
                    <span style={{ width: 110 }}>
                      <Spark points={data.forecast.map(d => d[k])} height={26} width={110}
                             color="var(--g-600)" fill={false} />
                    </span>
                    <b className="mono" style={{ fontSize: 13 }}>{data.forecast[0][k]}{unit}</b>
                  </span>
                </div>
              ))}
              <Prov label="Leaf wetness" value="No public feed measures leaf wetness directly, and dedicated sensors report near-100% false positives above 90% RH, so PRAHARI uses the RH ≥ 90% hour count as a proxy and says so." />
            </Card>

            {board.map(b => (
              <Card key={b.id}>
                <div className="row between">
                  <div className="grow">
                    <div className="row" style={{ gap: 7 }}>
                      <span style={{ fontSize: 17 }}>{b.em}</span>
                      <div className="card-title">{bi(lang, b.name, b.name_mr)}</div>
                    </div>
                    <div className="sci tiny">{b.sci}</div>
                  </div>
                  <span className={`badge ${b.level === 'high' ? 'bad' : b.level === 'rising' ? 'warn'
                    : b.level === 'watch' ? 'info' : 'ok'}`}>{levelLabel(b.level, lang)}</span>
                </div>
                {b.detail && <p className="small" style={{ marginTop: 9 }}>{b.detail}</p>}
                {b.scout && (
                  <div className="note" style={{ marginTop: 10 }}>
                    🔍 <b>{lang === 'mr' ? 'काय पहावे' : 'What to look for'}:</b> {bi(lang, b.scout, b.scout_mr)}
                  </div>
                )}
                {b.provenance?.source && (
                  <Why label={lang === 'mr' ? 'हे मॉडेल काय आहे?' : 'What model is this?'}>
                    <div style={{ fontWeight: 700 }}>{b.provenance.name}</div>
                    <p className="small" style={{ marginTop: 5 }}>{b.provenance.rule}</p>
                    <Prov label="Source" value={b.provenance.source} extra={b.provenance.source_type} />
                    <Prov label="Note" value={b.provenance.note} />
                  </Why>
                )}
              </Card>
            ))}
          </>
        )}

        {risk && tab === 'pest' && (
          <>
            {board.length === 0 && <Empty icon="🐛" title={lang === 'mr' ? 'या पिकासाठी कीड मॉडेल नाही' : 'No pest model for this crop'} />}
            {board.map(b => (
              <Card key={b.id}>
                <div className="row between">
                  <div className="grow">
                    <div className="row" style={{ gap: 7 }}>
                      <span style={{ fontSize: 17 }}>{b.em}</span>
                      <div className="card-title">{bi(lang, b.name, b.name_mr)}</div>
                    </div>
                    <div className="sci tiny">{b.sci}</div>
                  </div>
                  <span className={`badge ${b.damaging ? 'bad' : 'grey'}`}>
                    {b.damaging
                      ? (lang === 'mr' ? 'नुकसानकारक अवस्था' : 'Damaging stage')
                      : (lang === 'mr' ? 'फवारणी पोहोचणार नाही' : 'Spray cannot reach it')}
                  </span>
                </div>
                <div className="note" style={{ marginTop: 10 }}>
                  <b>{lang === 'mr' ? 'सध्याची अवस्था' : 'Current life stage'}:</b> {b.stage}
                  {b.gdd != null && <span className="mono tiny"> · {b.gdd} GDD</span>}
                </div>
                {b.etl != null && (
                  <div className="row between small" style={{ marginTop: 10 }}>
                    <span className="muted">{lang === 'mr' ? 'आर्थिक मर्यादा' : 'Economic threshold'}</span>
                    <b>{b.etl} {b.unit}</b>
                  </div>
                )}
                <Prov label="Threshold source" value={b.etl_source}
                      extra={b.etl_status === 'draft' ? 'transcribed, pending verification' : undefined} />
                <button className="btn sm ghost" style={{ marginTop: 10 }}
                        onClick={() => go('decide', { target: b.id })}>
                  {lang === 'mr' ? 'फवारणी करू का?' : 'Should I spray?'}
                </button>
              </Card>
            ))}
          </>
        )}

        {data?.self_consistency && (
          <Prov label="Self-check" value={data.self_consistency.note} />
        )}
      </div>
    </>
  )
}

/* ═══ PEST TRAP MONITOR ════════════════════════════════════════════════ */
export function Traps({ lang, plot, go, online }) {
  const [traps, setTraps] = useState(null)
  const [sel, setSel] = useState(0)
  const [err, setErr] = useState(null)
  const [addOpen, setAddOpen] = useState(false)
  const [countOpen, setCountOpen] = useState(false)

  const load = () => {
    if (!plot) return
    api.traps(plot.id).then(r => setTraps(r.traps)).catch(setErr)
  }
  useEffect(load, [plot?.id])

  const trap = traps?.[sel]
  const counts = trap?.counts || []
  const latest = counts[0]
  const over = latest && trap.etl != null && latest.count >= trap.etl

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{lang === 'mr' ? 'कीड सापळा' : 'Pest Trap Monitor'}</h1>
        <button className="btn sm" onClick={() => setAddOpen(true)}>＋</button>
      </div>
      <div className="pad stack" style={{ paddingTop: 14 }}>
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}
        {!traps && !err && <Loading lines={3} />}

        {traps?.length === 0 && (
          <Empty icon="🪤"
                 title={lang === 'mr' ? 'अजून सापळा नाही' : 'No traps installed'}
                 body={lang === 'mr'
                   ? 'सापळ्याची मोजणी हाच एकमेव पुरावा आहे ज्यावरून फवारणी योग्य आहे का ते ठरते.'
                   : 'A trap count is the only evidence that can justify an intervention. A photograph alone cannot.'}
                 action={<button className="btn" onClick={() => setAddOpen(true)}>
                   {lang === 'mr' ? 'सापळा जोडा' : 'Add a trap'}</button>} />
        )}

        {traps?.length > 0 && (
          <>
            <select className="input" value={sel} onChange={e => setSel(Number(e.target.value))}>
              {traps.map((t, i) => (
                <option key={t.id} value={i}>
                  {bi(lang, t.pest_name, t.pest_name_mr)} · {t.trap_type.replace(/_/g, ' ')}
                </option>
              ))}
            </select>

            <Card>
              <div className="row between" style={{ alignItems: 'flex-start' }}>
                <div>
                  <div className="tiny muted">{lang === 'mr' ? 'आजची मोजणी' : "Today's count"}</div>
                  <div className="row" style={{ alignItems: 'baseline', gap: 8, marginTop: 2 }}>
                    <span className="num" style={{ fontSize: 40 }}>{latest ? latest.count : '—'}</span>
                    {latest && <span className={`badge ${over ? 'bad' : 'ok'}`}>
                      {over ? (lang === 'mr' ? 'जास्त' : 'High') : (lang === 'mr' ? 'ठीक' : 'Below ETL')}
                    </span>}
                  </div>
                  <div className="tiny faint">{trap.etl_unit}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="tiny muted">{lang === 'mr' ? 'मर्यादा' : 'ETL'}</div>
                  <div className="num" style={{ fontSize: 22 }}>{trap.etl ?? '—'}</div>
                </div>
              </div>

              {counts.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <Bars threshold={trap.etl}
                        data={[...counts].reverse().slice(-8).map(c => ({
                          label: fmtDate(c.counted_on, lang), value: c.count,
                        }))} />
                  <div className="tiny faint" style={{ marginTop: 8 }}>
                    ⌁ {lang === 'mr' ? `या सापळ्याची मर्यादा: ${trap.etl}` : `ETL for this trap: ${trap.etl}`}
                  </div>
                </div>
              )}

              {trap.trend?.say && (
                <div className={`note ${trap.trend.spike ? 'bad' : ''}`} style={{ marginTop: 12 }}>
                  {trap.trend.direction === 'up' ? '↑' : trap.trend.direction === 'down' ? '↓' : '·'} {trap.trend.say}
                </div>
              )}

              {over && (
                <div className="note bad" style={{ marginTop: 10 }}>
                  <b>{lang === 'mr' ? 'मर्यादा ओलांडली' : 'Threshold crossed'}</b>
                  <div style={{ marginTop: 4 }}>
                    {lang === 'mr'
                      ? 'एकात्मिक कीड व्यवस्थापन पहा — रासायनिक पर्याय फक्त तपासलेली शिफारस असल्यासच दिसेल.'
                      : 'Open the IPM options. A chemical appears only if a verified label claim exists for this crop and pest.'}
                  </div>
                </div>
              )}

              <Prov label="Threshold source" value={trap.etl_source} />
            </Card>

            <button className="btn block" onClick={() => setCountOpen(true)}>
              📷 {lang === 'mr' ? 'मोजणी नोंदवा' : 'Add a trap count'}
            </button>
            <button className="btn block ghost" onClick={() => go('decide', { target: trap.pest })}>
              {lang === 'mr' ? 'व्यवस्थापन पर्याय पहा' : 'View IPM options'}
            </button>
          </>
        )}
      </div>

      <AddTrapSheet open={addOpen} onClose={() => setAddOpen(false)} lang={lang}
                    plot={plot} onSaved={() => { setAddOpen(false); load() }} />
      {trap && (
        <TrapCountSheet open={countOpen} onClose={() => setCountOpen(false)} lang={lang}
                        trap={trap} onSaved={() => { setCountOpen(false); load() }} />
      )}
    </>
  )
}

function AddTrapSheet({ open, onClose, lang, plot, onSaved }) {
  const [pests, setPests] = useState([])
  const [f, setF] = useState({ trap_type: 'pheromone' })
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open || !plot) return
    api.risk(plot.id)
      .then(r => {
        const p = (r.board || []).filter(b => b.kind === 'pest' && b.etl != null)
        setPests(p)
        setF(x => ({ ...x, pest: p[0]?.id }))
      })
      .catch(() => setPests([]))
  }, [open, plot?.id])

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.createTrap({ plot_id: plot.id, pest: f.pest, trap_type: f.trap_type })
      onSaved()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <Sheet open={open} onClose={onClose} title={lang === 'mr' ? 'सापळा जोडा' : 'Install a trap'}>
      {pests.length === 0
        ? <p className="small muted">
            {lang === 'mr'
              ? 'या पिकासाठी प्रहरीकडे प्रकाशित आर्थिक मर्यादा असलेली कोणतीही कीड नाही, त्यामुळे सापळ्याची मोजणी कशाशीही तुलना करता येणार नाही.'
              : 'PRAHARI has no pest with a published economic threshold for this crop, so a trap count could not be judged against anything.'}
          </p>
        : (
          <>
            <label className="field">
              <span className="lbl">{lang === 'mr' ? 'कीड' : 'Pest'}</span>
              <select className="input" value={f.pest || ''} onChange={e => setF(x => ({ ...x, pest: e.target.value }))}>
                {pests.map(p => <option key={p.id} value={p.id}>{bi(lang, p.name, p.name_mr)} — ETL {p.etl} {p.unit}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="lbl">{lang === 'mr' ? 'सापळ्याचा प्रकार' : 'Trap type'}</span>
              <select className="input" value={f.trap_type}
                      onChange={e => setF(x => ({ ...x, trap_type: e.target.value }))}>
                <option value="pheromone">Pheromone</option>
                <option value="sticky_yellow">Sticky yellow</option>
                <option value="sticky_blue">Sticky blue</option>
                <option value="light">Light trap</option>
              </select>
            </label>
            {err && <ErrorNote error={err} lang={lang} />}
            <button className="btn block" disabled={busy || !f.pest} onClick={save}>
              {busy ? '…' : (lang === 'mr' ? 'सापळा नोंदवा' : 'Install trap')}
            </button>
          </>
        )}
    </Sheet>
  )
}

function TrapCountSheet({ open, onClose, lang, trap, onSaved }) {
  const [count, setCount] = useState('')
  const [photo, setPhoto] = useState(null)
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => { if (open) { setCount(''); setPhoto(null); setOut(null); setErr(null) } }, [open])

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const res = photo
        ? await api.trapScan(trap.id, photo, count || undefined)
        : await api.trapCount(trap.id, { count: Number(count) })
      setOut(res)
      if (res.count_recorded) setTimeout(onSaved, 1400)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <Sheet open={open} onClose={onClose} title={lang === 'mr' ? 'सापळा मोजणी' : 'Trap count'}>
      <div className="note info" style={{ marginBottom: 14 }}>
        {lang === 'mr'
          ? 'फोटो जोडता येतो, पण प्रहरी फोटोवरून किडे मोजण्याचा दावा करत नाही — तुमचा आकडा हाच नोंद होतो.'
          : 'You may attach a photograph of the trap, but PRAHARI does not claim to count insects from it. Your own number is what gets recorded.'}
      </div>

      <label className="field">
        <span className="lbl">{trap.etl_unit || 'Count'}</span>
        <input className="input" type="number" min="0" step="1" value={count}
               onChange={e => setCount(e.target.value)} autoFocus />
        <span className="hint">
          {lang === 'mr' ? `मर्यादा: ${trap.etl}` : `Threshold: ${trap.etl} ${trap.etl_unit || ''}`}
        </span>
      </label>

      <label className="field">
        <span className="lbl">{lang === 'mr' ? 'सापळ्याचा फोटो (ऐच्छिक)' : 'Photograph of the trap (optional)'}</span>
        <input className="input" type="file" accept="image/*"
               onChange={e => setPhoto(e.target.files?.[0] || null)} />
      </label>

      {err && <ErrorNote error={err} lang={lang} />}
      {out?.note && <div className="note" style={{ marginBottom: 12 }}>{out.note}</div>}
      {out?.threshold && (
        <div className={`note ${out.threshold.chemical_authorised ? 'bad' : ''}`} style={{ marginBottom: 12 }}>
          <b>{bi(lang, out.threshold.title, out.threshold.title_mr)}</b>
          <div style={{ marginTop: 4 }}>{bi(lang, out.threshold.why, out.threshold.why_mr)}</div>
        </div>
      )}

      <button className="btn block" disabled={busy || count === ''} onClick={save}>
        {busy ? '…' : (lang === 'mr' ? 'नोंदवा' : 'Save count')}
      </button>
    </Sheet>
  )
}

/* ═══ ALERTS ═══════════════════════════════════════════════════════════ */
const KIND_ICON = { forecast: '🌦', threshold: '🐛', followup: '🔁', expert: '👨‍🌾', nearby: '📍', account: '🔑' }

export function Alerts({ lang, plot, go, onRead }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.notifications().then(d => { setData(d); api.markRead().then(onRead).catch(() => {}) }).catch(setErr)
  }, [])

  return (
    <>
      <div className="topbar"><h1 className="grow">{lang === 'mr' ? 'सूचना' : 'Alerts'}</h1></div>
      <div className="pad stack" style={{ paddingTop: 14 }}>
        {err && <ErrorNote error={err} lang={lang} />}
        {!data && !err && <Loading lines={4} />}
        {data?.notifications?.length === 0 && (
          <Empty icon="🔔" title={lang === 'mr' ? 'कोणतीही सूचना नाही' : 'No alerts yet'}
                 body={lang === 'mr'
                   ? 'धोका वाढला, मर्यादा ओलांडली किंवा तज्ज्ञांचा निकाल आला की इथे दिसेल.'
                   : 'You will see risk warnings, threshold crossings and expert verdicts here.'} />
        )}
        {data?.notifications?.map(n => (
          <Card key={n.id} className="tight" style={{
            borderLeft: `4px solid ${n.severity === 'high' ? 'var(--bad)'
              : n.severity === 'rising' ? 'var(--warn)'
              : n.severity === 'low' ? 'var(--ok)' : 'var(--info)'}`,
          }}>
            <div className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
              <div style={{ fontSize: 19 }}>{KIND_ICON[n.kind] || '🔔'}</div>
              <div className="grow">
                <div style={{ fontWeight: 700, fontSize: 14 }}>{bi(lang, n.title, n.title_mr)}</div>
                <div className="small muted" style={{ marginTop: 3 }}>{bi(lang, n.body, n.body_mr)}</div>
                <div className="tiny faint" style={{ marginTop: 6 }}>
                  {fmtDate(n.at, lang)}
                  {n.deliveries?.length > 0 && (
                    <> · {n.deliveries.map(d => `${d.channel}: ${d.state}`).join(' · ')}</>
                  )}
                </div>
              </div>
            </div>
          </Card>
        ))}
        {data?.delivery_note && <Prov label="Delivery" value={data.delivery_note} />}
      </div>
    </>
  )
}

/* ═══ FOLLOW-UP RE-SCAN ════════════════════════════════════════════════ */
export function Rescan({ lang, followup, go }) {
  const [file, setFile] = useState(null)
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const submit = async () => {
    if (!file) return
    setBusy(true); setErr(null)
    try { setOut(await api.rescan(followup.id, file)) }
    catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const report = async (outcome) => {
    setBusy(true); setErr(null)
    try {
      const r = await api.followupOutcome(followup.id, outcome)
      // Shaped like a rescan result so the same panel below renders it, but
      // `measured: false` travels with it and the panel says so.
      setOut({ outcome: r.outcome, comparison: null, measured: false, note: r.note })
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const TONE = { better: 'ok', same: 'info', worse: 'bad', unmeasurable: 'warn' }

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{lang === 'mr' ? 'पुन्हा तपासणी' : 'Follow-up scan'}</h1>
      </div>
      <div className="pad stack" style={{ paddingTop: 14 }}>
        {!out && (
          <>
            <Card>
              <div className="card-title">{lang === 'mr' ? 'उपाय लागू पडला का?' : 'Did the action work?'}</div>
              <p className="small muted" style={{ marginTop: 7 }}>
                {lang === 'mr'
                  ? 'त्याच शेतातील बाधित पानाचा फोटो काढा. प्रहरी पहिल्या फोटोशी तुलना करून दिशा सांगेल — टक्केवारी नाही, कारण दोन वेगळ्या पानांच्या हातातल्या फोटोंवरून तेवढी अचूकता मिळत नाही.'
                  : 'Photograph an affected leaf in the same field. PRAHARI compares it with the first scan and reports the DIRECTION of change — never a percentage, because two hand-held photographs of different leaves cannot support one.'}
              </p>
              <label className="field" style={{ marginTop: 14 }}>
                <input className="input" type="file" accept="image/*"
                       onChange={e => setFile(e.target.files?.[0] || null)} />
              </label>
              {err && <ErrorNote error={err} lang={lang} />}
              <button className="btn block" disabled={busy || !file} onClick={submit}>
                {busy ? '…' : (lang === 'mr' ? 'तुलना करा' : 'Compare with the first scan')}
              </button>
            </Card>

            {/* The loop has to close even when a comparable photograph is
                impossible — the leaf dropped, the crop is off, the light has
                gone. This path is recorded as the farmer's own account and is
                labelled that way wherever it is read, so an outcome nobody
                measured is never counted as evidence a treatment worked. */}
            <Card>
              <div className="card-title">
                {lang === 'mr' ? 'फोटो काढणे शक्य नाही?' : 'Cannot take a comparable photo?'}
              </div>
              <p className="small muted" style={{ marginTop: 7, marginBottom: 12 }}>
                {lang === 'mr'
                  ? 'तुम्ही स्वतः काय पाहिले ते सांगा. ही नोंद "शेतकऱ्याने सांगितलेली" म्हणून ठेवली जाते — मोजलेली तुलना म्हणून नाही.'
                  : 'Tell PRAHARI what you saw. It is stored as SELF-REPORTED, not as a measured comparison.'}
              </p>
              <div className="chips">
                {[['better', '🟢', 'Better', 'सुधारले'],
                  ['same', '🟡', 'About the same', 'तसेच आहे'],
                  ['worse', '🔴', 'Worse', 'वाढले'],
                  ['unmeasurable', '⚪', 'Nothing left to judge', 'तपासण्यासारखे काही नाही']]
                  .map(([k, em, en, mr]) => (
                    <button key={k} className="chip" disabled={busy}
                            onClick={() => report(k)}>{em} {bi(lang, en, mr)}</button>
                  ))}
              </div>
            </Card>
          </>
        )}

        {out && (
          <>
            <div className={`decision ${out.outcome === 'better' ? 'green'
              : out.outcome === 'worse' ? 'red' : out.outcome === 'same' ? 'grey' : 'amber'}`}>
              <div className="shield">{out.outcome === 'better' ? '📈' : out.outcome === 'worse' ? '📉' : '➖'}</div>
              <div className="ans">
                {out.comparison
                  ? bi(lang, out.comparison.label, out.comparison.label_mr)
                  : (lang === 'mr' ? 'तुलना करता आली नाही' : 'Could not be compared')}
              </div>
              <p className="why">{out.comparison?.say || out.note || out.message}</p>
            </div>

            {/* A self-report never wears the badge of a measurement. */}
            {out.measured === false && (
              <Card style={{ borderColor: 'var(--warn-line)', background: 'var(--warn-bg)' }}>
                <div className="card-title" style={{ color: 'var(--warn)' }}>
                  {lang === 'mr' ? 'शेतकऱ्याने सांगितलेली नोंद' : 'Self-reported'}
                </div>
                <p className="small" style={{ marginTop: 7 }}>
                  {lang === 'mr'
                    ? 'ही नोंद तुमच्या निरीक्षणावर आधारित आहे. दोन फोटोंची मोजलेली तुलना नाही — त्यामुळे उपाय लागू पडल्याचा पुरावा म्हणून ती धरली जात नाही.'
                    : 'This is your own account, not a measured comparison of two photographs, so it is not counted as evidence that the treatment worked.'}
                </p>
              </Card>
            )}

            {out.comparison && (
              <Card>
                <div className="row between small" style={{ padding: '6px 0' }}>
                  <span className="muted">{lang === 'mr' ? 'पहिल्या फोटोतले डाग' : 'Lesions in the first scan'}</span>
                  <b>{out.comparison.lesions_before}</b>
                </div>
                <div className="row between small" style={{ padding: '6px 0' }}>
                  <span className="muted">{lang === 'mr' ? 'आताच्या फोटोतले डाग' : 'Lesions now'}</span>
                  <b>{out.comparison.lesions_after}</b>
                </div>
                <Prov label="Why no percentage" value={out.comparison.why_no_percentage} />
                <Prov label="Method" value={out.comparison.method} />
              </Card>
            )}

            {out.escalation && (
              <Card style={{ borderColor: 'var(--bad-line)', background: 'var(--bad-bg)' }}>
                <div className="card-title" style={{ color: 'var(--bad)' }}>
                  {lang === 'mr' ? `तज्ज्ञांकडे पाठवले — ${out.escalation.case_id}` : `Escalated to an expert — ${out.escalation.case_id}`}
                </div>
                <p className="small" style={{ marginTop: 7 }}>{out.escalation.why}</p>
              </Card>
            )}

            <button className="btn block" onClick={() => go('home')}>
              {lang === 'mr' ? 'ठीक आहे' : 'Done'}
            </button>
          </>
        )}
      </div>
    </>
  )
}

/* ═══ PROFILE ══════════════════════════════════════════════════════════ */
export function Profile({ lang, onLang, me, plots, go, health, demo, onScenario }) {
  const [ledger, setLedger] = useState(null)
  const [busy, setBusy] = useState(null)

  useEffect(() => { api.ledger().then(setLedger).catch(() => {}) }, [])

  const signOut = async () => {
    try { await api.logout() } catch { /* the token is cleared regardless */ }
    auth.clear()
  }

  return (
    <>
      <div className="topbar"><h1 className="grow">{lang === 'mr' ? 'प्रोफाइल' : 'Profile'}</h1></div>
      <div className="pad stack" style={{ paddingTop: 14 }}>
        <Card>
          <div className="row" style={{ gap: 14 }}>
            <div style={{
              width: 54, height: 54, borderRadius: '50%', background: 'var(--g-100)',
              display: 'grid', placeItems: 'center', fontSize: 24, flex: 'none',
            }}>👨‍🌾</div>
            <div className="grow">
              <div className="card-title">
                {(lang === 'mr' && me?.user?.full_name_mr) || me?.user?.full_name}
              </div>
              <div className="small muted">
                {me?.profile?.village ? `${me.profile.village}, ` : ''}
                {me?.profile?.taluka} · {me?.user?.phone || me?.user?.email}
              </div>
              <div className="tiny faint" style={{ marginTop: 3 }}>
                {plots?.length || 0} {lang === 'mr' ? 'शेते नोंदवली' : 'field(s) registered'}
              </div>
            </div>
          </div>
        </Card>

        {ledger?.summary && (
          <Card>
            <div className="card-title">{lang === 'mr' ? 'टाळलेल्या फवारण्या' : 'Sprays avoided'}</div>
            <div className="row between" style={{ marginTop: 12 }}>
              <div>
                <div className="num" style={{ fontSize: 30 }}>{ledger.summary.avoided}</div>
                <div className="tiny muted">{lang === 'mr' ? 'फवारण्या टाळल्या' : 'applications avoided'}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div className="num" style={{ fontSize: 24, color: 'var(--ok)' }}>{fmtMoney(ledger.summary.saved)}</div>
                <div className="tiny muted">{lang === 'mr' ? 'अंदाजे बचत' : 'estimated saving'}</div>
              </div>
            </div>
            <Prov label="Compared against" value={ledger.summary.baseline} />
            <Prov label="Caveat" value={ledger.summary.caveat} />
          </Card>
        )}

        <Card>
          <div className="card-title" style={{ marginBottom: 10 }}>{lang === 'mr' ? 'भाषा' : 'Language'}</div>
          <div className="row" style={{ gap: 8 }}>
            {[['mr', 'मराठी'], ['hi', 'हिंदी'], ['en', 'English']].map(([code, label]) => (
              <button key={code} className="chip" aria-pressed={lang === code}
                      onClick={() => { persistLang(code); onLang(code) }}>{label}</button>
            ))}
          </div>
        </Card>

        {demo?.scenarios && (
          <Card style={{ borderColor: 'var(--warn-line)' }}>
            <div className="row between" style={{ marginBottom: 4 }}>
              <div className="card-title">{lang === 'mr' ? 'डेमो परिस्थिती' : 'Demo scenarios'}</div>
              <span className="badge warn">DEMO MODE</span>
            </div>
            <p className="tiny faint" style={{ marginBottom: 12 }}>{demo.separation}</p>
            {demo.scenarios.map(s => (
              <button key={s.key} className="rung" style={{
                width: '100%', textAlign: 'left', marginBottom: 8,
                borderColor: demo.current === s.key ? 'var(--g-300)' : 'var(--rule)',
                background: demo.current === s.key ? 'var(--g-050)' : 'transparent',
              }} disabled={busy === s.key}
                onClick={async () => { setBusy(s.key); await onScenario(s.key); setBusy(null) }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{bi(lang, s.title, s.title_mr)}</div>
                <div className="tiny muted" style={{ marginTop: 3 }}>{s.shows}</div>
              </button>
            ))}
          </Card>
        )}

        {health && (
          <Card>
            <div className="card-title" style={{ marginBottom: 8 }}>
              {lang === 'mr' ? 'यंत्रणेची स्थिती' : 'System status'}
            </div>
            {Object.entries({
              Weather: `${health.checks?.weather?.provider} (${health.checks?.weather?.kind})`,
              'Vision model': health.checks?.vision?.ready
                ? `${health.config?.vision_provider} v${health.config?.vision_model_version}`
                : 'none configured — symptom-feature classifier',
              Database: health.config?.database,
              Storage: health.checks?.storage?.provider,
              SMS: health.checks?.notifications?.sms?.configured ? 'configured' : 'not configured',
            }).map(([k, v]) => (
              <div className="row between small" key={k} style={{ padding: '5px 0' }}>
                <span className="muted">{k}</span><b style={{ fontSize: 12.5 }}>{v}</b>
              </div>
            ))}
            {health.soft_warnings?.map((w, i) => (
              <div className="note warn" key={i} style={{ marginTop: 8 }}>{w}</div>
            ))}
          </Card>
        )}

        <button className="btn block quiet" onClick={signOut}>
          {lang === 'mr' ? 'साइन आउट' : 'Sign out'}
        </button>

        <p className="tiny faint center" style={{ padding: '10px 6px 0', lineHeight: 1.6 }}>
          PRAHARI · प्रहरी — the one who keeps watch.<br />
          Your field data is never shown to another farmer. Surveillance is
          aggregated to taluka level so no individual farm can be identified.
        </p>
      </div>
    </>
  )
}
