/* PRAHARI · "Should I spray?" and the IPM ladder.

   This is the screen the whole platform exists to get right, and the answer it
   gives most often is NO. "Do not spray" arrives here as a decision object with
   evidence, a rupee value and a re-check date — not as an empty section that
   looks like an oversight.

   The chemical rung opens only when the threshold gate authorised it AND a
   label claim has been verified against the CIB&RC list by a named person. When
   no verified claim exists, the rung says so and names nothing: printing the
   name of an unverified product is half of recommending it. */
import React, { useEffect, useState } from 'react'
import { api, newRef, queue } from '../api'
import { Card, ErrorNote, Loading, Prov, Seg, Sheet, Why, bi, fmtDate, fmtMoney } from '../ui'

const T = {
  title:      ['What should I do?', 'काय करावे?'],
  decide:     ['Should I spray?', 'फवारणी करू का?'],
  why:        ['Why PRAHARI says this', 'प्रहरी असे का म्हणते'],
  evidence:   ['Field evidence', 'शेतातील पुरावा'],
  aiConf:     ['AI confidence', 'AI ची खात्री'],
  fieldMeas:  ['Field measurement', 'शेतातील मोजमाप'],
  notMeasured:['Not measured yet', 'अजून मोजलेले नाही'],
  addCount:   ['Record a count', 'मोजणी नोंदवा'],
  addAssess:  ['Assess the field', 'शेताची पाहणी नोंदवा'],
  today:      ["Today's crop action", 'आजचे काम'],
  trend:      ['Pest activity', 'प्रादुर्भावाचा कल'],
  ladder:     ['What you can do', 'काय करता येईल'],
  startWith:  ['PRAHARI recommends starting with', 'प्रहरी सुचवते — इथून सुरू करा'],
  chem:       ['Verified chemical options', 'तपासलेले रासायनिक पर्याय'],
  expert:     ['Need confirmation?', 'खात्री हवी आहे?'],
  followup:   ['Follow-up', 'पुनर्तपासणी'],
  history:    ['Field health history', 'शेत आरोग्य इतिहास'],
  nextReview: ['Next review', 'पुढील तपासणी'],
  waiting:    ['What if I wait?', 'थांबलो तर काय?'],
  conditions: ['Field conditions', 'शेतातील परिस्थिती'],
  rising:     ['Rising', 'वाढतोय'], falling: ['Falling', 'घटतोय'], flat: ['No change', 'बदल नाही'],
  noWx:       ['No weather for this field right now', 'सध्या या शेताचे हवामान उपलब्ध नाही'],
}
const t = (lang, k) => bi(lang, T[k][0], T[k][1])

/* The five states a decision can wear, in the farmer's words. The tone comes
   from the server; this table only translates it into a colour and a lamp so
   the same decision cannot look different on two screens. */
const STATE = {
  green: { lamp: '🟢', cls: 'green' },
  amber: { lamp: '🟠', cls: 'amber' },
  red:   { lamp: '🔴', cls: 'red' },
  grey:  { lamp: '⚪', cls: 'grey' },
}

export default function Decide({ lang, plot, target: initialTarget, go, online }) {
  const [target, setTarget] = useState(initialTarget || null)
  const [m, setM] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)
  const [countOpen, setCountOpen] = useState(false)
  const [assessOpen, setAssessOpen] = useState(false)
  const [plan, setPlan] = useState([])

  /* One call. The screen needs the decision, its evidence, the ladder, the
     trend, the prevention window, the day's work, the open follow-up and the
     history — and every one of those already existed in a different service.
     Seven round trips on a village network is a screen nobody waits for. */
  const load = () => {
    if (!plot) return
    setBusy(true); setErr(null)
    api.management(plot.id, target, lang)
      .then(d => { setM(d); if (!target && d.target) setTarget(d.target) })
      .catch(setErr).finally(() => setBusy(false))
  }
  useEffect(load, [plot?.id, target, lang])

  if (!plot) return null
  const d = m?.decision
  const kind = m?.target_kind
  const state = STATE[d?.tone] || STATE.grey
  const measured = kind === 'pest' ? m?.threshold : m?.assessment
  const recordAction = kind === 'pest' ? () => setCountOpen(true) : () => setAssessOpen(true)

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{t(lang, 'title')}</h1>
      </div>

      <div className="pad stack mg" style={{ paddingTop: 14 }}>
        {m?.targets?.length > 1 && (
          <div className="chips">
            {m.targets.map(p => (
              <button key={p.id} className="chip" aria-pressed={p.id === m.target}
                      onClick={() => setTarget(p.id)}>
                {p.em} {bi(lang, p.name, p.name_mr)}
              </button>
            ))}
          </div>
        )}

        {busy && <Loading lines={4} />}
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}

        {/* Weather can be unavailable — an Open-Meteo rate limit, a village
            network — and this screen is mostly not about weather. It used to
            vanish entirely; now it says which parts are missing and why, and
            leaves the count, the threshold, the ladder and the history alone.
            The banner exists so the absence is read as an absence: a farmer
            who is not told will read a screen with no risk level as a screen
            with no risk. */}
        {m && !busy && m.weather_available === false && (
          <p className="fb-unavailable">
            <b>{t(lang, 'noWx')}</b>{' — '}
            {bi(lang, m.weather_context?.note, m.weather_context?.note_mr)}
          </p>
        )}
        {m?.empty && !busy && (
          <Card><p className="small muted">{m.empty}</p>
            <button className="btn block" style={{ marginTop: 12 }} onClick={() => go('scan')}>
              {bi(lang, 'Scan the crop', 'पीक स्कॅन करा')}
            </button>
          </Card>
        )}

        {d && !busy && (
          <>
            {/* ── 1 · THE DECISION ─────────────────────────────────────── */}
            <div className={`mg-decision ${state.cls}`}>
              <div className="mg-decision__lamp">{state.lamp}</div>
              <div className="mg-decision__ans">{bi(lang, d.answer, d.answer_mr)}</div>
              <div className="mg-decision__for">
                {bi(lang, d.target_name, d.target_name_mr)}
              </div>
              <p className="mg-decision__why">{bi(lang, d.reason, d.reason_mr)}</p>

              <div className="mg-decision__facts">
                <div>
                  <span className="k">{t(lang, 'fieldMeas')}</span>
                  <b>{kind === 'pest'
                    ? (m.threshold ? `${m.threshold.count} ${m.threshold.unit}` : t(lang, 'notMeasured'))
                    : (m.assessment ? `${m.assessment.incidence_pct}% ${bi(lang, 'of plants', 'झाडांवर')}`
                                    : t(lang, 'notMeasured'))}</b>
                </div>
                {kind === 'pest' && m.threshold && (
                  <div>
                    <span className="k">{bi(lang, 'Action threshold', 'कृती मर्यादा')}</span>
                    <b>{m.threshold.etl_effective} {m.threshold.unit}</b>
                  </div>
                )}
                {d.recheck_on && (
                  <div>
                    <span className="k">{t(lang, 'nextReview')}</span>
                    <b>{fmtDate(d.recheck_on, lang)}</b>
                  </div>
                )}
              </div>

              {!measured && (
                <button className="btn block" style={{ marginTop: 14 }} onClick={recordAction}>
                  {kind === 'pest' ? t(lang, 'addCount') : t(lang, 'addAssess')}
                </button>
              )}
            </div>

            {/* ── 2 · WHY ──────────────────────────────────────────────── */}
            {d.evidence?.length > 0 && (
              <details className="method-fold mg-fold">
                <summary>{t(lang, 'why')}</summary>
                <div style={{ marginTop: 8 }}>
                  {d.evidence.map((e, i) => (
                    <div className="evid" key={i}>
                      <span className="tick">{EV_ICON[e.kind] || '•'}</span>
                      <span>
                        <b>{bi(lang, EV_LABEL[e.kind]?.[0] || e.kind.replace(/_/g, ' '),
                                    EV_LABEL[e.kind]?.[1] || e.kind.replace(/_/g, ' '))}</b>
                        {' — '}{e.detail || e.explain}
                        {e.source && <Prov label="Source" value={e.source} />}
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {/* ── 3 · FIELD EVIDENCE ───────────────────────────────────── */}
            <Card className="mg-ev">
              <div className="card-title">{t(lang, 'evidence')}</div>

              {/* The two numbers that must never be confused. A diagnosis
                  confidence is about WHAT this is; a count or an incidence is
                  about HOW MUCH is there. They are printed under separate
                  headings, with the meaning of each spelled out, because
                  reading one as the other is how a cautious system becomes a
                  reckless one. */}
              <div className="mg-two">
                <div className="mg-two__cell">
                  <span className="k">{t(lang, 'aiConf')}</span>
                  {m.evidence.diagnosis ? (
                    <>
                      <b className={`mg-band ${m.evidence.diagnosis.confidence_band}`}>
                        {bi(lang,
                          m.evidence.diagnosis.confidence_band,
                          { low: 'कमी', moderate: 'मध्यम', high: 'जास्त' }[m.evidence.diagnosis.confidence_band])}
                      </b>
                      <span className="tiny muted">{m.evidence.diagnosis.problem_name}</span>
                    </>
                  ) : (
                    <>
                      <b className="mg-band low">{bi(lang, 'No scan', 'स्कॅन नाही')}</b>
                      <span className="tiny muted">
                        {bi(lang, 'Scan your crop first.', 'आधी पीक स्कॅन करा.')}
                      </span>
                    </>
                  )}
                  <span className="tiny faint">
                    {bi(lang, 'What it is — not how much.', 'हे काय आहे — किती नाही.')}
                  </span>
                </div>

                <div className="mg-two__cell">
                  <span className="k">{t(lang, 'fieldMeas')}</span>
                  {measured ? (
                    <>
                      <b>{kind === 'pest'
                        ? `${m.threshold.count} ${m.threshold.unit}`
                        : `${m.assessment.incidence_pct}%`}</b>
                      <span className="tiny muted">
                        {kind === 'pest'
                          ? `${bi(lang, 'counted', 'मोजले')} ${fmtDate(m.threshold.counted_on, lang)}`
                          : m.assessment.arithmetic}
                      </span>
                    </>
                  ) : (
                    <>
                      <b className="mg-band low">{t(lang, 'notMeasured')}</b>
                      <span className="tiny muted">
                        {kind === 'pest'
                          ? bi(lang, 'A count decides whether to act.', 'कृती करावी का हे मोजणी ठरवते.')
                          : bi(lang, 'An inspection decides whether to act.', 'कृती करावी का हे पाहणी ठरवते.')}
                      </span>
                    </>
                  )}
                  <span className="tiny faint">
                    {bi(lang, 'How much is out there.', 'शेतात किती आहे.')}
                  </span>
                </div>
              </div>

              <button className="btn ghost block" style={{ marginTop: 12 }} onClick={recordAction}>
                ＋ {kind === 'pest' ? t(lang, 'addCount') : t(lang, 'addAssess')}
              </button>

              {kind === 'pest' && m.threshold && (
                <>
                  <div style={{ marginTop: 16 }}><EtlBar pct={m.threshold.percent_of_threshold} /></div>
                  <details className="method-fold" style={{ marginTop: 12 }}>
                    <summary>{bi(lang, 'Where this threshold comes from', 'ही मर्यादा कुठून आली')}</summary>
                    <Prov label="Source" value={m.threshold.etl_provenance?.source}
                          extra={m.threshold.etl_provenance?.status === 'draft'
                            ? 'transcribed, pending verification' : undefined} />
                    {m.threshold.economics && (
                      <div style={{ marginTop: 8 }}>
                        <div className="row between small"><span>Crop gross value</span>
                          <b>{fmtMoney(m.threshold.economics.crop_gross_value)}</b></div>
                        <div className="row between small"><span>One spray costs</span>
                          <b>{fmtMoney(m.threshold.economics.spray_cost)}</b></div>
                        <Prov label="Caveat" value={m.threshold.economics.note} />
                      </div>
                    )}
                  </details>
                </>
              )}
            </Card>

            {/* ── 4 · PREVENTION WINDOW ────────────────────────────────── */}
            {m.prevention_window?.level && m.prevention_window.level !== 'none' && (
              <Card className={`mg-prev ${m.prevention_window.level}`}>
                <div className="card-title">
                  🟠 {bi(lang, 'Prevention window', 'प्रतिबंधाची वेळ')}
                </div>
                <p className="small" style={{ marginTop: 6 }}>
                  {bi(lang, m.prevention_window.title, m.prevention_window.title_mr)}
                </p>
                {m.prevention_window.factors?.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    {m.prevention_window.factors.map((f, i) => (
                      <div className="evid" key={i}>
                        <span className="tick">•</span>
                        <span>{bi(lang, f.text || f.label, f.text_mr || f.label_mr)}</span>
                      </div>
                    ))}
                  </div>
                )}
                <p className="tiny faint" style={{ marginTop: 10 }}>
                  {bi(lang,
                    'A prevention window is not a spray recommendation. It means act early, by looking.',
                    'ही फवारणीची शिफारस नाही. याचा अर्थ — लवकर पाहणी करा.')}
                </p>
                <button className="btn block" style={{ marginTop: 12 }} onClick={recordAction}>
                  {bi(lang, 'Start scouting', 'तपासणी सुरू करा')}
                </button>
              </Card>
            )}

            {/* ── 5 · TODAY'S ACTION ───────────────────────────────────── */}
            {m.mission?.items?.length > 0 && (
              <Card>
                <div className="card-title">🎯 {t(lang, 'today')}</div>
                <div style={{ marginTop: 8 }}>
                  {m.mission.items.slice(0, 4).map((it, i) => {
                    const key = it.key || `it${i}`
                    const on = plan.includes(key)
                    return (
                      <button key={key} className={'mg-check' + (on ? ' is-on' : '')}
                              onClick={() => setPlan(p => on ? p.filter(x => x !== key) : [...p, key])}>
                        <span className="box">{on ? '✓' : ''}</span>
                        <span className="txt">
                          <b>{bi(lang, it.title, it.title_mr)}</b>
                          {it.detail && <span className="tiny muted">{bi(lang, it.detail, it.detail_mr)}</span>}
                        </span>
                      </button>
                    )
                  })}
                </div>
                <p className="tiny faint" style={{ marginTop: 10 }}>
                  {bi(lang, 'Ticking is for you — it is not sent anywhere. Recording a count or an assessment is what moves the decision.',
                            'खूण करणे फक्त तुमच्यासाठी. निर्णय बदलण्यासाठी मोजणी किंवा पाहणी नोंदवा.')}
                </p>
              </Card>
            )}

            {/* ── 6 · TREND ────────────────────────────────────────────── */}
            <Card>
              <div className="card-title">{t(lang, 'trend')}</div>
              {m.trend.points.length > 0 ? (
                <>
                  <div className="mg-trend">
                    {m.trend.points.map((p, i) => (
                      <div className="mg-trend__pt" key={i}
                           aria-current={i === m.trend.points.length - 1 ? 'true' : undefined}>
                        <b>{p.value}</b>
                        <span className="tiny faint">{fmtDate(p.on, lang)}</span>
                      </div>
                    ))}
                  </div>
                  {m.trend.direction && (
                    <div className="row between" style={{ marginTop: 10 }}>
                      <span className={`badge ${m.trend.direction === 'rising' ? 'bad'
                        : m.trend.direction === 'falling' ? 'ok' : 'grey'}`}>
                        {t(lang, m.trend.direction)}
                      </span>
                      <span className="tiny muted">{m.trend.unit}</span>
                    </div>
                  )}
                  <p className="small muted" style={{ marginTop: 8 }}>
                    {bi(lang, m.trend.note, m.trend.note_mr)}
                  </p>
                </>
              ) : (
                <>
                  <p className="small muted" style={{ marginTop: 6 }}>
                    {bi(lang, m.trend.note, m.trend.note_mr)}
                  </p>
                  <button className="btn ghost block" style={{ marginTop: 10 }} onClick={recordAction}>
                    {kind === 'pest' ? t(lang, 'addCount') : t(lang, 'addAssess')}
                  </button>
                </>
              )}
            </Card>

            {/* ── 7 · THE LADDER ───────────────────────────────────────── */}
            <h2 className="sect-title">{t(lang, 'ladder')}</h2>
            {m.ipm_ladder[0] && (
              <Card className="mg-first">
                <div className="tiny muted">{t(lang, 'startWith')}</div>
                <div className="mg-first__title">
                  {bi(lang, m.ipm_ladder[0].title, m.ipm_ladder[0].title_mr)}
                </div>
                <div className="tiny">
                  {m.ipm_ladder[0].cost === 0
                    ? bi(lang, '₹0 — costs nothing but your time', '₹0 — फक्त तुमचा वेळ')
                    : m.ipm_ladder[0].cost != null ? `≈ ${fmtMoney(m.ipm_ladder[0].cost)}/acre` : ''}
                </div>
              </Card>
            )}
            <div className="stack">
              {m.ipm_ladder.map(step => (
                <details className={`rung ${step.withheld ? 'shut' : 'open'}`} key={step.key}
                         open={step.key === 'monitor' || step.rung === 1}>
                  <summary className="rung-head">
                    <span className="rung-n">{step.rung}</span>
                    <div className="grow">
                      <div style={{ fontWeight: 700, fontSize: 14 }}>
                        {bi(lang, step.title, step.title_mr)}
                      </div>
                      {step.cost != null && (
                        <div className="tiny faint">
                          {step.cost === 0 ? '₹0' : `≈ ${fmtMoney(step.cost)}/acre`}
                        </div>
                      )}
                    </div>
                    {step.withheld && <span className="badge grey">{bi(lang, 'Withheld', 'बंद')}</span>}
                  </summary>
                  <div style={{ marginTop: 9 }}>
                    {step.items.map((it, i) => (
                      <div className="evid" key={i}>
                        <span className={step.withheld ? 'cross' : 'tick'}>{step.withheld ? '✗' : '✓'}</span>
                        <span>{bi(lang, it.text, it.text_mr)}{it.cost ? ` — ${fmtMoney(it.cost)}` : ''}</span>
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
            <Prov label="Principle" value={m.ladder_principle} />

            {/* ── 8 · CHEMICAL GATE ────────────────────────────────────── */}
            {m.chemical_availability && !m.chemical_availability.verified_available && (
              <Card style={{ borderColor: 'var(--warn-line)', background: 'var(--warn-bg)' }}>
                <div className="card-title" style={{ color: 'var(--warn)' }}>
                  {bi(lang, 'No verified chemical recommendation', 'तपासलेली रासायनिक शिफारस नाही')}
                </div>
                <p className="small" style={{ marginTop: 7 }}>
                  {bi(lang, m.chemical_availability.message, m.chemical_availability.message_mr)}
                </p>
                <details className="method-fold" style={{ marginTop: 10 }}>
                  <summary>{bi(lang, 'Why not?', 'का नाही?')}</summary>
                  <p className="small">{m.chemical_availability.why}</p>
                  <Prov label="Process" value={m.chemical_availability.verification_process} />
                </details>
              </Card>
            )}

            {m.chemical?.options?.length > 0 && (
              <>
                <h2 className="sect-title">{t(lang, 'chem')}</h2>
                {m.chemical.options.map(o => <ChemOption key={o.product} o={o} lang={lang} />)}
                {m.chemical.recommended && (
                  <ApplyButton lang={lang} plot={plot} target={m.target} rec={m.chemical.recommended}
                               checkId={m.threshold?.check_id} go={go} />
                )}
              </>
            )}

            {m.phi?.blocked && (
              <div className="note bad">
                🚫 {bi(lang,
                  `Harvest is gated until ${fmtDate(m.phi.clears_on, lang)} by the pre-harvest interval of your last application.`,
                  `काढणी ${fmtDate(m.phi.clears_on, lang)} पर्यंत थांबवा — शेवटच्या फवारणीचा प्रतीक्षा कालावधी.`)}
              </div>
            )}

            {/* ── 9 · EXPERT ───────────────────────────────────────────── */}
            {(d.decision === 'expert_review' || d.reason_code === 'low_confidence') && (
              <Card className="mg-expert">
                <div className="card-title">🔬 {t(lang, 'expert')}</div>
                <p className="small" style={{ marginTop: 6 }}>
                  {bi(lang,
                    "PRAHARI is not confident enough to recommend a management action here.",
                    'इथे शिफारस करण्याइतकी प्रहरीला खात्री नाही.')}
                </p>
                <button className="btn block" style={{ marginTop: 12 }}
                        onClick={() => go('community', { ask: m.target })}>
                  {bi(lang, 'Ask an expert', 'तज्ज्ञांना विचारा')}
                </button>
                <p className="tiny faint center" style={{ marginTop: 8 }}>
                  {bi(lang, 'Your scan and this field’s record go with the question.',
                            'तुमचा स्कॅन आणि शेताची नोंद प्रश्नासोबत जाते.')}
                </p>
              </Card>
            )}

            {/* ── 10 · FOLLOW-UP ───────────────────────────────────────── */}
            {m.followup && (
              <Card className="mg-follow">
                <div className="card-title">🗓 {t(lang, 'followup')}</div>
                <p className="small" style={{ marginTop: 6 }}>
                  {bi(lang, `Due ${fmtDate(m.followup.due_on, lang)}.`,
                            `${fmtDate(m.followup.due_on, lang)} रोजी.`)}{' '}
                  {bi(lang, 'Re-scan the same plant so the two photographs can be compared.',
                            'तेच झाड पुन्हा स्कॅन करा म्हणजे दोन्ही फोटोंची तुलना करता येईल.')}
                </p>
                <button className="btn block" style={{ marginTop: 12 }} onClick={() => go('scan')}>
                  {bi(lang, 'Check the field again', 'पुन्हा तपासा')}
                </button>
              </Card>
            )}

            {/* ── 11 · HISTORY ─────────────────────────────────────────── */}
            {m.history?.length > 0 && (
              <details className="method-fold mg-fold">
                <summary>{t(lang, 'history')}</summary>
                <div className="mg-hist">
                  {m.history.map((h, i) => (
                    <div className="mg-hist__row" key={i}>
                      <span className="mg-hist__em">{h.em || '•'}</span>
                      <span className="mg-hist__txt">
                        <b>{bi(lang, h.title, h.title_mr)}</b>
                        {h.detail && <span className="tiny muted">{bi(lang, h.detail, h.detail_mr)}</span>}
                      </span>
                      <span className="tiny faint">{fmtDate(h.on || h.at, lang)}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {/* Field conditions, stated as context and never as a cause. */}
            {m.weather_context?.days?.length > 0 && (
              <details className="method-fold mg-fold">
                <summary>🌦 {t(lang, 'conditions')}</summary>
                <p className="small muted" style={{ marginTop: 8 }}>
                  {bi(lang, m.weather_context.note, m.weather_context.note_mr)}
                </p>
                {m.weather_context.warning && (
                  <p className="tiny" style={{ color: 'var(--warn)', marginTop: 6 }}>
                    {m.weather_context.warning}
                  </p>
                )}
              </details>
            )}
          </>
        )}
      </div>

      <CountSheet open={countOpen} onClose={() => setCountOpen(false)} lang={lang}
                  plot={plot} pest={m?.threshold ? { ...m.threshold, id: m.target,
                    name: m.target_name, name_mr: m.target_name_mr,
                    etl: m.threshold.etl_effective, unit: m.threshold.unit }
                    : { id: m?.target, name: m?.target_name, name_mr: m?.target_name_mr,
                        unit: bi(lang, 'per trap', 'प्रति सापळा') }}
                  online={online} onSaved={load} />
      <AssessSheet open={assessOpen} onClose={() => setAssessOpen(false)} lang={lang}
                   plot={plot} problem={m?.target} name={m?.target_name}
                   name_mr={m?.target_name_mr} onSaved={load} />
    </>
  )
}

const EV_ICON = {
  threshold: '📊', diagnosis: '📷', phenology: '🌱', label_claim: '⚗',
  field_assessment: '🔍', infection_model: '🌦', trap: '🪤',
}
const EV_LABEL = {
  threshold: ['Action threshold', 'कृती मर्यादा'],
  diagnosis: ['Diagnosis', 'निदान'],
  phenology: ['Pest life stage', 'किडीची अवस्था'],
  label_claim: ['Label claim', 'लेबल दावा'],
  field_assessment: ['Field assessment', 'शेत पाहणी'],
  infection_model: ['Infection model', 'संसर्ग मॉडेल'],
}

/* ── the disease assessment sheet ───────────────────────────────────────────
   What a farmer records instead of a trap count. Two numbers they can actually
   produce standing in the field — how many plants they walked, and how many of
   those showed it — and the app does the division in front of them. It never
   asks for a percentage: a percentage that arrives ready-made cannot be
   checked, and being checkable is the whole point of this record. */
function AssessSheet({ open, onClose, lang, plot, problem, name, name_mr, onSaved }) {
  const [inspected, setInspected] = useState('10')
  const [affected, setAffected] = useState('')
  const [band, setBand] = useState('few_spots')
  const [part, setPart] = useState('lower_leaves')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => { if (open) { setInspected('10'); setAffected(''); setErr(null) } }, [open])
  if (!problem) return null

  const ins = Number(inspected), aff = Number(affected)
  const ok = Number.isFinite(ins) && ins > 0 && Number.isFinite(aff) && aff >= 0 && aff <= ins
  const pct = ok && affected !== '' ? Math.round((aff / ins) * 1000) / 10 : null

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.assessDisease(plot.id, {
        problem, plants_inspected: ins, plants_affected: aff,
        spread_band: band, part, client_ref: newRef(),
      })
      onSaved(); onClose()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const BANDS = [['few_spots', 'A few spots', 'काही ठिपके'],
                 ['several_leaves', 'Several leaves', 'अनेक पाने'],
                 ['most_leaves', 'Most of the plant', 'बहुतेक झाड']]
  const PARTS = [['lower_leaves', 'Lower leaves', 'खालची पाने'],
                 ['upper_leaves', 'Upper leaves', 'वरची पाने'],
                 ['stem', 'Stem', 'खोड'], ['fruit', 'Fruit', 'फळ']]

  return (
    <Sheet open={open} onClose={onClose}
           title={bi(lang, 'Assess the field', 'शेताची पाहणी')}>
      <p className="small muted" style={{ marginBottom: 14 }}>
        <b>{bi(lang, name, name_mr)}</b> — {bi(lang,
          'Walk the field, look at a set number of plants, and record how many show it.',
          'शेतात फिरा, ठराविक झाडे पहा, आणि किती झाडांवर लक्षणे आहेत ते नोंदवा.')}
      </p>
      <div className="grid2">
        <label className="field">
          <span className="lbl">{bi(lang, 'Plants inspected', 'तपासलेली झाडे')}</span>
          <input className="input" type="number" inputMode="numeric" min="1" max="500"
                 value={inspected} onChange={e => setInspected(e.target.value)} />
        </label>
        <label className="field">
          <span className="lbl">{bi(lang, 'Showing symptoms', 'लक्षणे असलेली')}</span>
          <input className="input" type="number" inputMode="numeric" min="0" max="500"
                 value={affected} onChange={e => setAffected(e.target.value)} autoFocus />
        </label>
      </div>

      {pct != null && (
        <div className="note info" style={{ marginTop: -2, marginBottom: 12 }}>
          {aff} ÷ {ins} = <b>{pct}%</b> {bi(lang, 'of the plants you looked at', 'तपासलेल्या झाडांपैकी')}
        </div>
      )}
      {affected !== '' && !ok && (
        <div className="note bad" style={{ marginBottom: 12 }}>
          {bi(lang, 'More plants are marked affected than were inspected.',
                    'तपासलेल्या झाडांपेक्षा बाधित झाडे जास्त आहेत.')}
        </div>
      )}

      <label className="field">
        <span className="lbl">{bi(lang, 'How far it has gone on an affected plant', 'बाधित झाडावर किती पसरले')}</span>
        <div className="chips">
          {BANDS.map(([k, en, mr]) => (
            <button key={k} className="chip" aria-pressed={band === k} onClick={() => setBand(k)}>
              {bi(lang, en, mr)}
            </button>
          ))}
        </div>
      </label>
      <label className="field">
        <span className="lbl">{bi(lang, 'Where', 'कुठे')}</span>
        <div className="chips">
          {PARTS.map(([k, en, mr]) => (
            <button key={k} className="chip" aria-pressed={part === k} onClick={() => setPart(k)}>
              {bi(lang, en, mr)}
            </button>
          ))}
        </div>
      </label>

      {err && <ErrorNote error={err} lang={lang} />}
      <button className="btn block" disabled={!ok || affected === '' || busy} onClick={save}>
        {busy ? '…' : bi(lang, 'Save assessment', 'पाहणी नोंदवा')}
      </button>
      <p className="tiny faint center" style={{ marginTop: 8 }}>
        {bi(lang, 'A band, never a percentage you had to estimate. Nobody measures leaf area standing in a field.',
                  'अंदाजे टक्केवारी नाही — फक्त तुम्ही प्रत्यक्ष मोजलेली झाडे.')}
      </p>
    </Sheet>
  )
}

/* ── the ETL bar ───────────────────────────────────────────────────────── */
function EtlBar({ pct }) {
  const clamped = Math.min(200, Math.max(0, pct || 0))
  const width = (clamped / 200) * 100
  const colour = clamped < 50 ? 'var(--ok)' : clamped < 100 ? 'var(--warn)' : 'var(--bad)'
  return (
    <div>
      <div className="etlbar">
        <i style={{ width: `${width}%`, background: colour, borderRadius: 5 }} />
      </div>
      <div className="etlmark">
        <div className="pin" style={{ left: '50%' }} title="Economic threshold" />
      </div>
      <div className="row between tiny faint" style={{ marginTop: 8 }}>
        <span>0</span>
        <span style={{ fontWeight: 700, color: 'var(--ink-2)' }}>ETL (100%)</span>
        <span>2× ETL</span>
      </div>
      <div className="center" style={{ marginTop: 6 }}>
        <span className={`badge ${clamped < 50 ? 'ok' : clamped < 100 ? 'warn' : 'bad'}`}>
          {pct}% of threshold
        </span>
      </div>
    </div>
  )
}

/* ── one screened product ──────────────────────────────────────────────── */
const TOX_COLOUR = { red: 'var(--tox-red)', yellow: 'var(--tox-yellow)', blue: 'var(--tox-blue)', green: 'var(--tox-green)' }

function ChemOption({ o, lang }) {
  return (
    <Card className={o.blocked ? '' : ''} style={{ borderColor: o.blocked ? 'var(--rule)' : 'var(--g-300)' }}>
      <div className="row between" style={{ alignItems: 'flex-start', gap: 10 }}>
        <div className="grow">
          <div className="row" style={{ gap: 8 }}>
            <span style={{
              width: 0, height: 0, borderLeft: '7px solid transparent', borderRight: '7px solid transparent',
              borderBottom: `12px solid ${TOX_COLOUR[o.toxicity] || 'var(--faint)'}`, flex: 'none',
            }} title={o.toxicity_label} />
            <div style={{ fontWeight: 700, fontSize: 14.5 }}>{o.product}</div>
          </div>
          <div className="tiny faint" style={{ marginTop: 3 }}>
            {o.moa} · PHI {o.phi_days}d{o.reentry_hours ? ` · re-entry ${o.reentry_hours}h` : ''}
          </div>
        </div>
        {o.blocked
          ? <span className="badge bad">{lang === 'mr' ? 'वापरू नका' : 'Blocked'}</span>
          : <span className="badge ok">{lang === 'mr' ? 'वापरता येईल' : 'Allowed'}</span>}
      </div>

      {!o.blocked && o.dose && (
        <div className="note" style={{ marginTop: 10 }}>
          <b>{lang === 'mr' ? 'मात्रा' : 'Dose'}:</b> {o.dose.plain}
        </div>
      )}

      {o.blocks?.map((b, i) => (
        <div className="note bad" key={i} style={{ marginTop: 8 }}>
          <b style={{ textTransform: 'capitalize' }}>{b.rule.replace(/-/g, ' ')}:</b> {b.msg}
        </div>
      ))}
      {o.warnings?.map((w, i) => (
        <div className="note warn" key={i} style={{ marginTop: 8 }}>
          <b style={{ textTransform: 'capitalize' }}>{w.rule}:</b> {w.msg}
        </div>
      ))}

      <Prov label="Verified against" value={o.provenance?.source}
            url={o.provenance?.source_url}
            extra={o.provenance?.verified_by ? `by ${o.provenance.verified_by}` : undefined} />
    </Card>
  )
}

/* ── record the action ─────────────────────────────────────────────────── */
function ApplyButton({ lang, plot, target, rec, checkId, go }) {
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const [err, setErr] = useState(null)

  if (done) {
    return (
      <Card style={{ borderColor: 'var(--ok-line)', background: 'var(--ok-bg)' }}>
        <div className="card-title">{lang === 'mr' ? 'नोंद झाली' : 'Recorded'}</div>
        <p className="small" style={{ marginTop: 6 }}>{done.note}</p>
        <div className="note" style={{ marginTop: 10 }}>
          🗓 {lang === 'mr' ? 'पुन्हा तपासणी' : 'Follow-up scan due'}: <b>{fmtDate(done.followup_due, lang)}</b>
          {done.harvest_gate && <> · {lang === 'mr' ? 'काढणी थांबवा' : 'harvest gated until'} <b>{fmtDate(done.harvest_gate, lang)}</b></>}
        </div>
        <button className="btn block" style={{ marginTop: 12 }} onClick={() => go('home')}>
          {lang === 'mr' ? 'ठीक आहे' : 'Done'}
        </button>
      </Card>
    )
  }

  const record = async () => {
    setBusy(true); setErr(null)
    try {
      const out = await api.apply({
        plot_id: plot.id, target, kind: 'chemical', product: rec.product,
        claim_id: rec.claim_id, dose_text: rec.dose?.plain, check_id: checkId,
      })
      setDone(out)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <>
      {err && <ErrorNote error={err} lang={lang} />}
      <button className="btn block" disabled={busy} onClick={record}>
        {busy ? '…' : (lang === 'mr' ? 'ही फवारणी केल्याची नोंद करा' : 'I applied this — record it')}
      </button>
      <p className="tiny faint center">
        {lang === 'mr'
          ? 'नोंद केल्यावर काढणीचा प्रतीक्षा कालावधी सुरू होतो आणि पाच दिवसांनी पुन्हा तपासणी ठरते.'
          : 'Recording it sets the pre-harvest gate and schedules the re-scan five days from now.'}
      </p>
    </>
  )
}

/* ── the count sheet, with an offline path ─────────────────────────────── */
function CountSheet({ open, onClose, lang, plot, pest, online, onSaved }) {
  const [count, setCount] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [queued, setQueued] = useState(false)

  useEffect(() => { if (open) { setCount(''); setErr(null); setQueued(false) } }, [open])
  if (!pest) return null

  const save = async () => {
    const n = Number(count)
    if (!Number.isFinite(n) || n < 0) return
    setBusy(true); setErr(null)
    try {
      await api.threshold({ plot_id: plot.id, pest: pest.id, count: n })
      onSaved()
      onClose()
    } catch (e) {
      if (e.status === 0) {
        // Offline: the count is kept on the phone with an idempotency key and
        // sent when the connection returns. It is never silently dropped.
        queue.add({ kind: 'threshold', plot_id: plot.id, payload: { pest: pest.id, count: n }, client_ref: newRef() })
        setQueued(true)
      } else setErr(e)
    } finally { setBusy(false) }
  }

  return (
    <Sheet open={open} onClose={onClose}
           title={lang === 'mr' ? 'मोजणी नोंदवा' : 'Record a count'}>
      {queued ? (
        <>
          <div className="note warn">
            📴 {lang === 'mr'
              ? 'तुम्ही ऑफलाइन आहात. ही मोजणी फोनवर साठवली आहे आणि इंटरनेट आल्यावर पाठवली जाईल — दोनदा मोजली जाणार नाही.'
              : 'You are offline. This count is saved on your phone and will be sent when you reconnect — it cannot be counted twice.'}
          </div>
          <button className="btn block" style={{ marginTop: 14 }} onClick={onClose}>OK</button>
        </>
      ) : (
        <>
          <p className="small muted" style={{ marginBottom: 14 }}>
            {pest.em} <b>{bi(lang, pest.name, pest.name_mr)}</b> — {pest.scout || ''}
          </p>
          <label className="field">
            <span className="lbl">{pest.unit}</span>
            <input className="input" type="number" inputMode="decimal" min="0" step="0.5"
                   value={count} onChange={e => setCount(e.target.value)} autoFocus />
            <span className="hint">
              {lang === 'mr'
                ? `या पिकासाठी मर्यादा: ${pest.etl} ${pest.unit}`
                : `Threshold for this crop: ${pest.etl} ${pest.unit}`}
            </span>
          </label>
          {err && <ErrorNote error={err} lang={lang} />}
          <button className="btn block" disabled={busy || count === ''} onClick={save}>
            {busy ? '…' : (lang === 'mr' ? 'नोंदवा' : 'Save count')}
          </button>
          {!online && (
            <p className="tiny faint center" style={{ marginTop: 8 }}>
              {lang === 'mr' ? 'ऑफलाइन असतानाही नोंद करता येते.' : 'This works offline — it will sync later.'}
            </p>
          )}
        </>
      )}
    </Sheet>
  )
}
