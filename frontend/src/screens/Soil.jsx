/* PRAHARI · soil health — the self-test and the nutrient gap.

   Two screens in one, kept visually apart because they rest on different
   evidence: six things a farmer can see with a spade, and numbers only a
   laboratory can give. The app never lets the first be read as the second. */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Loading, Prov, bi } from '../ui'

export default function Soil({ lang, plot, go }) {
  const [ref, setRef] = useState(null)
  const [tab, setTab] = useState('self')
  const [answers, setAnswers] = useState({})
  const [result, setResult] = useState(null)
  const [lab, setLab] = useState({})
  const [plan, setPlan] = useState(null)
  const [hist, setHist] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.soilReference().then(setRef).catch(setErr) }, [])
  useEffect(() => {
    if (plot) api.soilHistory(plot.id).then(setHist).catch(() => setHist(null))
  }, [plot?.id])

  const submitSelf = async () => {
    setBusy(true); setErr(null)
    try {
      const out = await api.soilSelfTest({ plot_id: plot.id, answers })
      setResult(out); api.soilHistory(plot.id).then(setHist).catch(() => {})
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const submitLab = async () => {
    setBusy(true); setErr(null)
    try {
      const body = { plot_id: plot.id }
      Object.entries(lab).forEach(([k, v]) => { if (v !== '') body[k] = Number(v) })
      const out = await api.soilLab(body)
      setPlan(out); api.soilHistory(plot.id).then(setHist).catch(() => {})
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const qs = ref?.questions || []
  const done = qs.length > 0 && qs.every(q => answers[q.id] !== undefined)

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('crop')} aria-label="Back">←</button>
        <h1 className="grow">{lang === 'mr' ? 'जमिनीचे आरोग्य' : 'Soil health'}</h1>
      </div>

      <div className="pad stack" style={{ paddingTop: 12 }}>
        {err && <ErrorNote error={err} lang={lang} />}
        {!ref && !err && <Loading lines={3} />}

        <div className="seg">
          <button aria-pressed={tab === 'self'} onClick={() => setTab('self')}>
            {lang === 'mr' ? 'स्वतः तपासा' : 'Self-test'}
          </button>
          <button aria-pressed={tab === 'lab'} onClick={() => setTab('lab')}>
            {lang === 'mr' ? 'तपासणी अहवाल' : 'Lab report'}
          </button>
        </div>

        {tab === 'self' && (
          <>
            <div className="note info">
              {bi(lang, ref?.self_test_note, ref?.self_test_note_mr)}
            </div>
            {qs.map((q, i) => (
              <div className="soilq" key={q.id}>
                <div className="q">{i + 1}. {bi(lang, q.q, q.q_mr)}</div>
                <div className="opts">
                  {q.options.map(o => (
                    <button key={o.v} aria-pressed={answers[q.id] === o.v}
                            onClick={() => setAnswers(a => ({ ...a, [q.id]: o.v }))}>
                      {bi(lang, o.label, o.label_mr)}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <button className="btn block" disabled={!done || busy} onClick={submitSelf}>
              {done ? (lang === 'mr' ? 'निकाल पहा' : 'See the result')
                    : (lang === 'mr' ? `${qs.length - Object.keys(answers).length} प्रश्न बाकी`
                                     : `${qs.length - Object.keys(answers).length} left`)}
            </button>

            {result && (
              <Card style={{ padding: 0, overflow: 'hidden', border: 'none', background: 'none' }}>
                {/* Saurjya's score dial. The number is the VSA score out of
                    twelve, not a laboratory grade, and the pill under it says
                    which of the two this is. */}
                <div className="sh-score">
                  <div className="sh-score__col">
                    <div className="sh-score__label">
                      {lang === 'mr' ? 'निरीक्षण गुण' : 'Visual assessment score'}
                    </div>
                    <div className="sh-score__val">
                      {result.score}<small> / {result.out_of}</small>
                    </div>
                    <span className="sh-score__pill">
                      {bi(lang, result.label, result.label_mr)}
                    </span>
                  </div>
                  <div className="sh-gauge">
                    <svg viewBox="0 0 92 92" width="92" height="92">
                      <circle className="sh-gauge__bg" cx="46" cy="46" r="38" />
                      <circle className="sh-gauge__val" cx="46" cy="46" r="38"
                              strokeDasharray={`${(result.percent / 100) * 238.8} 238.8`} />
                    </svg>
                    <div style={{ position: 'absolute', inset: 0, display: 'grid',
                                  placeItems: 'center', fontWeight: 800, fontSize: 17 }}>
                      {result.percent}%
                    </div>
                  </div>
                </div>

                <Card style={{ marginTop: 12 }}>
                <p className="small">{result.summary}</p>
                {result.findings.map(f => (
                  <div className="note warn" style={{ marginTop: 10 }} key={f.id}>
                    <b>{f.observation}</b>
                    <div style={{ marginTop: 4 }}>{bi(lang, f.fix, f.fix_mr)}</div>
                  </div>
                ))}
                <Prov label={lang === 'mr' ? 'हे का महत्त्वाचे' : 'Why this matters'}
                      value={result.why_it_matters} />
                </Card>
              </Card>
            )}
          </>
        )}

        {tab === 'lab' && (
          <>
            <div className="note">
              {lang === 'mr'
                ? 'तुमच्या मृदा आरोग्य पत्रिकेत जे आकडे आहेत तेवढेच भरा. रिकामे ठेवलेले शून्य मानले जात नाही.'
                : 'Enter whatever your Soil Health Card actually has. A blank stays UNMEASURED — it is never treated as zero.'}
            </div>
            {[['organic_carbon_pct', 'Organic carbon', 'सेंद्रिय कर्ब', '%'],
              ['nitrogen_kg_ha', 'Available nitrogen', 'उपलब्ध नत्र', 'kg/ha'],
              ['phosphorus_kg_ha', 'Available phosphorus', 'उपलब्ध स्फुरद', 'kg/ha'],
              ['potassium_kg_ha', 'Available potassium', 'उपलब्ध पालाश', 'kg/ha'],
              ['ph', 'pH', 'सामू (pH)', '']].map(([k, en, mr, unit]) => (
              <label className="field" key={k}>
                <span className="lbl">{bi(lang, en, mr)} {unit && `(${unit})`}</span>
                <input className="input" type="number" inputMode="decimal" step="0.01"
                       value={lab[k] ?? ''} placeholder={lang === 'mr' ? 'माहीत नाही' : 'not measured'}
                       onChange={e => setLab(l => ({ ...l, [k]: e.target.value }))} />
              </label>
            ))}
            <button className="btn block" disabled={busy} onClick={submitLab}>
              {lang === 'mr' ? 'खत नियोजन पहा' : 'See the nutrient plan'}
            </button>

            {/* Saurjya's nutrient cards. Each one shows the ICAR class the
                server assigned and the value it was assigned from; a nutrient
                the farmer did not enter reads "not measured" rather than
                being coloured as though it were adequate. */}
            {plan?.ratings && (
              <div className="sh-nutgrid">
                {[['nitrogen_kg_ha', 'N'], ['phosphorus_kg_ha', 'P'], ['potassium_kg_ha', 'K'],
                  ['ph', 'pH'], ['organic_carbon_pct', 'OC']].map(([key, sym]) => {
                  const r = plan.ratings[key]
                  const cls = r?.class
                  return (
                    <div key={key}
                         className={'sh-nut' + (!r ? ' sh-nut--empty'
                           : cls === 'low' ? ' sh-nut--low' : cls === 'high' ? ' sh-nut--high' : '')}>
                      <span className="sh-nut__sym">{sym}</span>
                      <span className="sh-nut__class">
                        {r ? cls : (lang === 'mr' ? 'न मोजलेले' : 'not measured')}
                      </span>
                      {r && <span className="sh-nut__val">{r.value} {r.unit?.split(' ')[0]}</span>}
                    </div>
                  )
                })}
              </div>
            )}

            {plan?.plan && (
              <Card>
                <div className="card-title" style={{ marginBottom: 4 }}>
                  {lang === 'mr' ? 'खत नियोजन' : 'Nutrient plan'} — {plan.crop_label}
                </div>
                <p className="tiny muted" style={{ marginBottom: 12 }}>
                  {plan.area_acre} {lang === 'mr' ? 'एकर' : 'acre(s)'}
                </p>
                {plan.plan.map(row => (
                  <div key={row.nutrient} className="rung open" style={{ marginBottom: 9 }}>
                    <div className="row between">
                      <b>{row.nutrient}</b>
                      <span className={`badge ${row.soil_test_class === 'low' ? 'warn'
                        : row.soil_test_class === 'high' ? 'info' : 'grey'}`}>
                        {row.soil_test_class || (lang === 'mr' ? 'न तपासलेले' : 'not measured')}
                        {row.adjustment !== 'no change' && ` · ${row.adjustment}`}
                      </span>
                    </div>
                    <div className="h3" style={{ marginTop: 6 }}>
                      {row.material_total_kg} kg {row.material}
                    </div>
                    <div className="mono tiny muted" style={{ marginTop: 4 }}>{row.arithmetic}</div>
                    <div className="small" style={{ marginTop: 6 }}>{row.why}</div>
                  </div>
                ))}
                {plan.split && <div className="note" style={{ marginTop: 6 }}>{plan.split}</div>}
                {plan.warnings?.map((w, i) => (
                  <div className="note warn" style={{ marginTop: 8 }} key={i}>{w}</div>
                ))}
                <Prov label={lang === 'mr' ? 'पद्धत' : 'Method'} value={plan.method} />
                <Prov label={lang === 'mr' ? 'ब्रँड नाही' : 'No brands'} value={plan.no_brands} />
                <Prov label={lang === 'mr' ? 'सूचना' : 'Note'}
                      value={bi(lang, plan.disclaimer, plan.disclaimer_mr)} />
              </Card>
            )}
          </>
        )}

        {hist?.tests?.length > 0 && (
          <Card>
            <div className="card-title" style={{ marginBottom: 8 }}>
              {lang === 'mr' ? 'मागील तपासण्या' : 'Previous tests'}
            </div>
            {hist.tests.slice(0, 6).map(t => (
              <div className="changerow" key={t.id}>
                <div className="ic" style={{ background: 'var(--sunk)' }}>
                  {t.kind === 'lab' ? '🧪' : '🪴'}
                </div>
                <div className="nm">{t.tested_on}</div>
                <div className="st">{t.kind === 'lab' ? 'lab' : `${t.score}/${t.out_of}`}</div>
              </div>
            ))}
            <Prov label={lang === 'mr' ? 'टीप' : 'Note'} value={hist.trend_note} />
          </Card>
        )}
      </div>
    </>
  )
}
