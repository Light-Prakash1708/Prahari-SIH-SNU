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
import { Card, ErrorNote, Loading, Prov, Seg, Sheet, Why, bi, fmtDate, fmtMoney, levelLabel, useDayTicks } from '../ui'

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
  detected:   ['What was found', 'काय आढळले'],
  riskNow:    ['Risk now', 'सध्याचा धोका'],
  doNow:      ['Start here', 'इथून सुरू करा'],
  watchNext:  ['Then check again', 'नंतर पुन्हा तपासा'],
  notKnown:   ['Not known', 'माहीत नाही'],
  notForecast:['Not forecast — no weather', 'अंदाज नाही — हवामान नाही'],
  measured:   ['measured', 'मोजलेले'],
  estimated:  ['from a photograph', 'फोटोवरून'],
  howBad:     ['How serious is it?', 'किती गंभीर आहे?'],
  doNow2:     ['What to do now', 'आता काय करावे'],
  markChecked:['Mark field checked', 'शेत तपासले म्हणून नोंदवा'],
  moreDetail: ['More', 'अधिक'],
  flow:       ['Assess, act, monitor', 'पाहणी, कृती, देखरेख'],
  watchFor:   ['What to watch for', 'काय पहावे'],
  nextCheck:  ['Next field check', 'पुढील पाहणी'],
  needHelp:   ['Need help?', 'मदत हवी?'],
  escalateBecause: ['An expert would help here because:', 'तज्ज्ञांची मदत उपयोगी ठरेल, कारण:'],
  detail:     ['More detail', 'अधिक तपशील'],
  needsConf:  ['Needs field confirmation', 'शेतात खात्री करावी लागेल'],
  heading:    ['Where is this field heading?', 'हे शेत कोणत्या दिशेने चालले आहे?'],
}
const t = (lang, k) => bi(lang, T[k][0], T[k][1])

/* The four states app/trajectory.py can return, plus its honest fifth. The
   lamp and the band are decided here only so the same state cannot look
   different on two screens; the state itself is always the server's. */
const TRAJ = {
  improving: { lamp: '🟢', band: 'low',      en: 'Improving',  mr: 'सुधारत आहे' },
  stable:    { lamp: '🟢', band: 'low',      en: 'Stable',     mr: 'स्थिर' },
  watch:     { lamp: '🟡', band: 'moderate', en: 'Watch',      mr: 'लक्ष ठेवा' },
  worsening: { lamp: '🔴', band: 'high',     en: 'Worsening',  mr: 'बिघडत आहे' },
  unknown:   { lamp: '⚪', band: 'unknown',  en: 'Not known yet', mr: 'अजून माहीत नाही' },
}

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
  const [assessOpen, setAssessOpen] = useState(false)
  const [plan, togglePlan] = useDayTicks(`ipm.${plot?.id}.${target || 'auto'}`)

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
  /* Scroll to the part of the screen where a step is done. */
  const jump = (id) => {
    const el = document.getElementById(id === 'act' ? 'ipm-act' : id === 'monitor' ? 'ipm-monitor' : 'ipm-assess')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    if (id === 'assess' && kind !== 'pest') setAssessOpen(true)
  }
  const d = m?.decision
  const kind = m?.target_kind
  const state = STATE[d?.tone] || STATE.grey
  const measured = kind === 'pest' ? m?.threshold : m?.assessment
  /* The chosen target's own row on the risk board, so the glance strip states
     the level the server computed rather than deriving one here. */
  const targetRow = (m?.targets || []).find(x => x.id === m?.target)

  /* Everything below is DERIVED from what the server already returned. None of
     it is a new judgement and none of it is a second opinion — it is the same
     values, banded and ordered so the four questions a farmer actually has can
     be answered in the first screenful instead of the fifth. */
  const sev = severity(m, kind, measured, lang)
  const doNow = actionsNow(m, lang)
  const wxDay = m?.weather_available === false ? null : (m?.weather_context?.days || [])[0]
  const steps = stepStates(m, d, measured)
  /* Escalation is the SERVER's verdict now, from app/trajectory.py, and so is
     the trajectory. It used to be derived here, which meant the farmer's
     screen and the expert's case brief each had their own idea of why a case
     was sent. One source, two readers. */
  const esc = m?.escalation || null
  const escalate = esc?.reasons || []
  const traj = m?.trajectory || null

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
            <b>{bi(lang, m.weather_context?.message || 'Weather update temporarily unavailable',
                         m.weather_context?.message_mr || t(lang, 'noWx'))}</b>{' — '}
            {bi(lang, m.weather_context?.note, m.weather_context?.note_mr)}
            {' '}
            <button className="btn sm ghost" style={{ marginTop: 8 }} onClick={load}>
              {bi(lang, 'Try again', 'पुन्हा')}
            </button>
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
            {/* ── 1 · WHOSE FIELD, AND WHAT ────────────────────────────────
                The screen used to open on a verdict with no subject. A farmer
                arriving from a scan already knows what they photographed; a
                farmer arriving from the home screen does not, and the same
                sentence serves both. Assembled only from values the server
                returned — crop, target, stage — so a field with no stage
                simply says less. */}
            <div className="ipm-who">
              <span className="ipm-who__crop">
                {(m.targets || []).find(x => x.id === m.target)?.em || '🌱'}{' '}
                {(m.crop || '').toUpperCase()}
              </span>
              <b className="ipm-who__what">{bi(lang, d.target_name, d.target_name_mr)}</b>
              <span className="ipm-who__where">
                {m.plot_name}
                {m.crop_stage?.label && ` · ${bi(lang, m.crop_stage.label, m.crop_stage.label_mr)}`}
              </span>
            </div>

            {/* ── 2 · THE DECISION, AND THE ONE THING THAT MOVES IT ─────────
                The verdict, how serious it is, and the action that changes it,
                in one card. It used to be three cards with the same "Record a
                count" button on two of them. The count is now entered HERE,
                and while the farmer types, the server says where that number
                would land against the published threshold — before anything
                is saved, and without authorising anything. */}
            <div className={`mg-decision ${state.cls}`} id="ipm-assess">
              <div className="mg-decision__lamp">{state.lamp}</div>
              <div className="mg-decision__ans">{bi(lang, d.answer, d.answer_mr)}</div>
              <p className="mg-decision__why">{bi(lang, d.reason, d.reason_mr)}</p>
              <div className="ipm-hero__sev">
                <span className={`ipm-sev__chip ${sev.band}`}>
                  {sev.lamp} {bi(lang, sev.label[0], sev.label[1])}
                </span>
                {traj && (
                  <span className={`ipm-sev__chip ${TRAJ[traj.state]?.band || 'unknown'}`}
                        title={bi(lang, traj.note, traj.note_mr) || undefined}>
                    {TRAJ[traj.state]?.lamp} {bi(lang, TRAJ[traj.state]?.en || traj.state,
                                                     TRAJ[traj.state]?.mr || traj.state)}
                  </span>
                )}
                {d.recheck_on && (
                  <span className="ipm-sev__chip unknown">📅 {fmtDate(d.recheck_on, lang)}</span>
                )}
              </div>
            </div>

            {kind === 'pest' ? (
              <QuickCount lang={lang} plot={plot} m={m} online={online} onSaved={load} />
            ) : (
              <Card className={`ipm-sev ${sev.band}`}>
                <div className="ipm-sev__top">
                  <span className="k">{t(lang, 'howBad')}</span>
                </div>
                <p className="ipm-sev__why">{bi(lang, sev.why[0], sev.why[1])}</p>
                {sev.basis && <div className="ipm-sev__basis">{sev.basis}</div>}
                <button className="btn block" style={{ marginTop: 11 }} onClick={() => setAssessOpen(true)}>
                  🔍 {measured ? bi(lang, 'Record a new inspection', 'नवीन पाहणी नोंदवा')
                               : t(lang, 'addAssess')}
                </button>
              </Card>
            )}

            {/* Trajectory reasons, only when there are some. "Not known yet"
                is already the chip above; a whole card saying so was noise. */}
            {traj && !traj.note && traj.reasons?.length > 0 && (
              <Card className={`ipm-traj ${traj.state}`}>
                <div className="k">{t(lang, 'heading')}</div>
                <div style={{ marginTop: 7 }}>
                  {traj.reasons.map((r, i) => (
                    <div className="evid" key={i}>
                      <span className="tick">•</span>
                      <span>{bi(lang, r.text, r.text_mr)}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* ── 3 · ASSESS → ACT → MONITOR ───────────────────────────────
                Where this field stands, read off records. Each step now takes
                you to the part of the screen where that step is done. */}
            <div className="ipm-steps" aria-label={t(lang, 'flow')}>
              {steps.map((s, i) => (
                <React.Fragment key={s.id}>
                  {i > 0 && <span className="ipm-steps__arrow" aria-hidden="true">›</span>}
                  <button type="button" className={`ipm-step is-${s.state}`}
                          onClick={() => jump(s.id)}>
                    <span className="ipm-step__n">{s.state === 'done' ? '✓' : i + 1}</span>
                    <span className="ipm-step__l">{bi(lang, s.label[0], s.label[1])}</span>
                    <span className="ipm-step__s">{bi(lang, s.sub[0], s.sub[1])}</span>
                  </button>
                </React.Fragment>
              ))}
            </div>

            {/* ── 4 · TODAY'S CHECKLIST ────────────────────────────────────
                Ticks are kept on this phone for today, so coming back after
                walking the field shows what is left. A tick is the farmer's
                note to self; only a saved count or inspection moves the
                decision, and each row that needs one offers it directly. */}
            {doNow.length > 0 && (
              <Card className="ipm-now">
                <div className="row between">
                  <div className="card-title">✅ {t(lang, 'doNow2')}</div>
                  <span className="tiny muted">
                    {plan.filter(k => doNow.some(x => x.key === k)).length}/{doNow.length}{' '}
                    {bi(lang, 'done', 'झाले')}
                  </span>
                </div>
                <div className="ipm-progress" aria-hidden="true">
                  <i style={{ width: `${Math.round(100 * plan.filter(k => doNow.some(x => x.key === k)).length / doNow.length)}%` }} />
                </div>
                <div className="ipm-now__list">
                  {doNow.map(it => {
                    const on = plan.includes(it.key)
                    const verb = rowAction(it, kind, lang)
                    return (
                      <div className={'ipm-act' + (on ? ' is-on' : '')} key={it.key}>
                        <button className="ipm-act__tick" aria-pressed={on}
                                aria-label={it.title}
                                onClick={() => togglePlan(it.key)}>
                          {on ? '✓' : ''}
                        </button>
                        <div className="ipm-act__body">
                          <div className="ipm-act__title">{it.title}</div>
                          {it.detail && (
                            <details className="ipm-act__more">
                              <summary>{t(lang, 'moreDetail')}</summary>
                              <p>{it.detail}</p>
                            </details>
                          )}
                        </div>
                        {verb && !on && (
                          <button type="button" className="btn sm ghost ipm-act__go"
                                  onClick={() => verb.run({ go, jump, openAssess: () => setAssessOpen(true) })}>
                            {verb.label}
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
                <p className="tiny faint" style={{ marginTop: 9 }}>
                  {bi(lang, 'Ticks stay on this phone for today. Only a saved count or inspection changes the decision.',
                            'खूण आजसाठी या फोनवर राहते. निर्णय फक्त नोंदवलेल्या मोजणी किंवा पाहणीने बदलतो.')}
                </p>
              </Card>
            )}

            {/* ── 5 · YOUR IPM PLAN ────────────────────────────────────────
                The ladder used to be folded under "More detail", so the IPM
                layer — the reason this screen exists — was the least visible
                thing on it. It is now a plan: the rung PRAHARI points to is
                open, the others are one tap away, and the chemical rung says
                exactly what would have to be true for it to open. */}
            <IpmPlan lang={lang} m={m} d={d} kind={kind} />

            {/* ── 6 · FIELD CONDITIONS ─────────────────────────────────────
                Only when the existing weather service actually returned a day.
                Generated weather says so on its face. */}
            {wxDay && (
              <Card className="ipm-wx">
                <div className="row between">
                  <div className="card-title">🌦 {t(lang, 'conditions')}</div>
                  {m.weather_context?.generated && (
                    <span className="badge grey">{bi(lang, 'Demo weather', 'प्रात्यक्षिक')}</span>
                  )}
                </div>
                <div className="ipm-wx__row">
                  {wxDay.condition && <span className="ipm-wx__c">{wxDay.condition}</span>}
                  {wxDay.tmax != null && <span className="ipm-wx__c">🌡 {Math.round(wxDay.tmax)}°C</span>}
                  {wxDay.rh_mean != null && <span className="ipm-wx__c">💧 {Math.round(wxDay.rh_mean)}%</span>}
                  {wxDay.rain_chance_pct != null &&
                    <span className="ipm-wx__c">🌧 {Math.round(wxDay.rain_chance_pct)}%</span>}
                </div>
                {m.prevention_window?.level && m.prevention_window.level !== 'none' && (
                  <p className="ipm-wx__note">
                    {bi(lang, m.prevention_window.title, m.prevention_window.title_mr)}
                    {' '}
                    {bi(lang, 'Walk the field early rather than spraying early.',
                              'लवकर फवारणी नको — लवकर पाहणी करा.')}
                  </p>
                )}
              </Card>
            )}

            {/* ── 8 · NEXT FIELD CHECK ─────────────────────────────────────
                Informational plus two real actions. There is no reminder
                infrastructure on this device, so none is promised. */}
            {(m.followup?.due_on || d.recheck_on) && (
              <Card className="ipm-next" id="ipm-monitor">
                <div className="row between">
                  <div>
                    <div className="k">{t(lang, 'nextCheck')}</div>
                    <b className="ipm-next__d">
                      📅 {fmtDate(m.followup?.due_on || d.recheck_on, lang)}
                    </b>
                  </div>
                  <button className="btn sm" onClick={() => go('scan')}>
                    {bi(lang, 'Scan again', 'पुन्हा स्कॅन')}
                  </button>
                </div>
                <p className="tiny faint" style={{ marginTop: 8 }}>
                  {kind === 'pest'
                    ? bi(lang, 'Count the same trap so the two numbers can be compared.',
                               'तोच सापळा मोजा म्हणजे दोन आकड्यांची तुलना करता येईल.')
                    : bi(lang, 'Photograph the same plant so the two pictures can be compared.',
                               'तेच झाड पुन्हा फोटो काढा म्हणजे तुलना करता येईल.')}
                </p>
              </Card>
            )}

            {/* ── 9 · NEED HELP? ───────────────────────────────────────────
                Escalation as an action, and honest about whether it is called
                for. The reasons listed are the ones that actually hold right
                now, read off the same records as everything else; when none
                holds the card still offers the route, quietly, because a
                farmer who wants a second opinion should not have to earn it. */}
            <Card className={'mg-expert' + (escalate.length ? ' is-urgent' : '')}>
              <div className="row between">
                <div className="card-title">🔬 {t(lang, 'needHelp')}</div>
                {esc?.level && esc.level !== 'low' && (
                  <span className={`badge ${esc.level === 'high' ? 'bad' : 'warn'}`}>
                    {bi(lang, esc.level === 'high' ? 'High' : 'Medium',
                              esc.level === 'high' ? 'जास्त' : 'मध्यम')}
                  </span>
                )}
              </div>
              {escalate.length > 0 ? (
                <>
                  <p className="small" style={{ marginTop: 6 }}>{t(lang, 'escalateBecause')}</p>
                  <div style={{ marginTop: 7 }}>
                    {escalate.map((r, i) => (
                      <div className="evid" key={i}>
                        <span className="tick">{r.level === 'high' ? '🔴' : '🟠'}</span>
                        <span>{bi(lang, r.text, r.text_mr)}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="small" style={{ marginTop: 6 }}>
                  {bi(lang, esc?.note, esc?.note_mr)
                    || bi(lang, 'Nothing here needs an expert right now.',
                                'सध्या तज्ज्ञांची गरज नाही.')}
                </p>
              )}
              <button className={'btn block' + (escalate.length ? '' : ' ghost')}
                      style={{ marginTop: 12 }}
                      onClick={() => go('community', { ask: m.target })}>
                {bi(lang, 'Ask an expert', 'तज्ज्ञांना विचारा')}
              </button>
              <p className="tiny faint center" style={{ marginTop: 8 }}>
                {bi(lang, 'Your scan and this field’s record go with the question.',
                          'तुमचा स्कॅन आणि शेताची नोंद प्रश्नासोबत जाते.')}
              </p>
            </Card>

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

            {/* ── 11 · EVERYTHING ELSE, FOLDED ─────────────────────────────
                Not deleted — moved. Every one of these was on the page before
                and is still one tap away. What changed is that none of them
                stands between the farmer and the four answers above. */}
            <h2 className="sect-title">{t(lang, 'detail')}</h2>

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

            <details className="method-fold mg-fold">
              <summary>{t(lang, 'trend')}</summary>
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
                <p className="small muted" style={{ marginTop: 6 }}>
                  {bi(lang, m.trend.note, m.trend.note_mr)}
                </p>
              )}
            </details>

            {kind === 'pest' && m.threshold && (
              <details className="method-fold mg-fold">
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
            )}

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

            {m.weather_context?.note && (
              <details className="method-fold mg-fold">
                <summary>🌦 {bi(lang, 'About this weather', 'या हवामानाबद्दल')}</summary>
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

      <AssessSheet open={assessOpen} onClose={() => setAssessOpen(false)} lang={lang}
                   plot={plot} problem={m?.target} name={m?.target_name}
                   name_mr={m?.target_name_mr} onSaved={load} />
    </>
  )
}

/* ── derived, never invented ────────────────────────────────────────────────
   Four small functions, and the discipline in all of them is the same: they
   read values the server computed and re-express them. Not one of them
   produces a number, a level or a claim that was not already in the payload,
   because a screen that quietly upgrades "not measured" into "low" is exactly
   the failure this whole application is built to avoid. */

/* How serious, from what the FARMER measured — never from the photograph.
   A diagnosis confidence is about WHAT this is; reading it as HOW MUCH is the
   mistake that turns a cautious system into a reckless one. With nothing
   counted the honest answer is that the field has not been looked at yet, and
   saying so is also the most useful thing this card can do, because the count
   is the next action anyway. */
function severity(m, kind, measured, lang) {
  const unknown = {
    band: 'unknown', lamp: '⚪',
    label: T.needsConf,
    why: ['Something was detected, but how much of it is in the field is not known yet. Only a count or an inspection can say.',
          'काहीतरी आढळले आहे, पण शेतात किती आहे हे अजून माहीत नाही. मोजणी किंवा पाहणीच ते सांगू शकते.'],
    basis: null,
  }
  if (!m || !measured) return unknown

  if (kind === 'pest') {
    const pct = m.threshold?.percent_of_threshold
    if (pct == null) return unknown
    const band = pct >= 100 ? 'high' : pct >= 50 ? 'moderate' : 'low'
    return {
      band,
      lamp: band === 'high' ? '🔴' : band === 'moderate' ? '🟡' : '🟢',
      label: { high: ['At the action threshold', 'कृती मर्यादेवर'],
               moderate: ['Approaching the threshold', 'मर्यादेजवळ'],
               low: ['Below the threshold', 'मर्यादेखाली'] }[band],
      why: { high: ['Your count has reached the published action threshold for this crop and stage.',
                    'तुमची मोजणी या पिकासाठी व अवस्थेसाठी प्रकाशित कृती मर्यादेपर्यंत पोहोचली आहे.'],
             moderate: ['Your count is over halfway to the published action threshold. Keep counting.',
                        'तुमची मोजणी प्रकाशित मर्यादेच्या निम्म्याहून पुढे आहे. मोजणी चालू ठेवा.'],
             low: ['Your count is well below the published action threshold.',
                   'तुमची मोजणी प्रकाशित मर्यादेपेक्षा बरीच कमी आहे.'] }[band],
      basis: `${m.threshold.count} ${m.threshold.unit} · ${bi(lang, 'threshold', 'मर्यादा')} ${m.threshold.etl_effective}`,
    }
  }

  const pct = m.assessment?.incidence_pct
  if (pct == null) return unknown
  const band = pct >= 34 ? 'high' : pct >= 10 ? 'moderate' : 'low'
  return {
    band,
    lamp: band === 'high' ? '🔴' : band === 'moderate' ? '🟡' : '🟢',
    label: { high: ['Widespread in what you inspected', 'तपासलेल्यांपैकी बऱ्याच झाडांवर'],
             moderate: ['Present in what you inspected', 'तपासलेल्यांपैकी काही झाडांवर'],
             low: ['Few plants affected', 'थोड्याच झाडांवर'] }[band],
    why: { high: ['More than a third of the plants you walked showed it. Widen the inspection to a part of the field you have not walked.',
                  'तुम्ही पाहिलेल्या एक तृतीयांशाहून अधिक झाडांवर आढळले. न पाहिलेल्या भागातही पाहणी करा.'],
           moderate: ['It is in the field but not through it. Walking a second stretch tells you whether it is spreading.',
                      'शेतात आहे पण सर्वत्र नाही. दुसऱ्या भागात पाहणी केल्यास पसरतोय का ते कळेल.'],
           low: ['Only a few of the plants you walked showed it.',
                 'तुम्ही पाहिलेल्या थोड्याच झाडांवर आढळले.'] }[band],
    basis: `${pct}% · ${m.assessment.arithmetic}`,
  }
}

/* The three to five things to do, from two lists the server already ordered.
   The order between them matters more than it looks. The agenda (`mission`) is
   the WHOLE FIELD's work for today — on a tomato plot in humid weather that is
   three "scout for late blight" rows, and they are the same three rows whether
   the farmer opened this screen for late blight or for whitefly. Leading with
   them made every target's advice identical for the first three lines, which
   is the exact failure this screen is supposed to fix.
   So the ladder's first rung goes first: it is chosen FOR this target and it
   is what makes a whitefly screen read differently from a late blight one. The
   agenda then tops up to five, because "while you are out there" is genuinely
   useful — just not the headline. */
function actionsNow(m, lang) {
  if (!m) return []
  const out = []
  const seen = new Set()
  const push = (key, title, detail, extra) => {
    const norm = (title || '').trim().toLowerCase()
    if (!title || seen.has(norm) || out.length >= 5) return
    seen.add(norm)
    out.push({ key, title, detail: detail || null, ...extra })
  }
  const first = (m.ipm_ladder || [])[0]
  ;(first?.items || []).forEach((it, i) =>
    push(`rung-${first.key}-${i}`, bi(lang, it.text, it.text_mr), null, { source_text: it.text }))
  ;(m.mission?.items || []).forEach((it, i) =>
    push(`mission-${i}`, bi(lang, it.title, it.title_mr), bi(lang, it.detail, it.detail_mr),
         { action: it.action, source_text: it.title }))
  return out
}

/* Where this field stands, read off records. "Done" means a row exists —
   nothing here claims the farmer did something PRAHARI cannot see. */
function stepStates(m, d, measured) {
  const assessed = Boolean(measured)
  const acted = Boolean(m?.history?.some(h => h.kind === 'application')) || Boolean(m?.phi?.blocked)
  const monitoring = Boolean(m?.followup?.due_on || d?.recheck_on)
  return [
    { id: 'assess', label: ['Assess', 'पाहणी'],
      sub: assessed ? ['Recorded', 'नोंदवले'] : ['Not yet', 'अजून नाही'],
      state: assessed ? 'done' : 'now' },
    { id: 'act', label: ['Act', 'कृती'],
      sub: acted ? ['Logged', 'नोंद आहे'] : ['Start at the lowest rung', 'सर्वात खालच्या पायरीपासून'],
      state: acted ? 'done' : assessed ? 'now' : 'next' },
    /* Exactly one step is ever "now". Two highlighted steps is not a flow, it
       is a pair of suggestions, and the farmer has to decide which is which —
       which is the job this strip was added to do for them. */
    { id: 'monitor', label: ['Monitor', 'देखरेख'],
      sub: monitoring ? ['Re-check set', 'पुनर्तपासणी ठरली'] : ['After you act', 'कृतीनंतर'],
      state: acted && monitoring ? 'now' : 'next' },
  ]
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
function EtlBar({ pct, lang = 'en' }) {
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
          {lang === 'mr' ? `मर्यादेच्या ${pct}%` : lang === 'bn' ? `সীমার ${pct}%` : `${pct}% of threshold`}
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
          ? <span className="badge bad">{bi(lang, 'Blocked', 'वापरू नका')}</span>
          : <span className="badge ok">{bi(lang, 'Allowed', 'वापरता येईल')}</span>}
      </div>

      {!o.blocked && o.dose && (
        <div className="note" style={{ marginTop: 10 }}>
          <b>{bi(lang, 'Dose', 'मात्रा')}:</b> {o.dose.plain}
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
        <div className="card-title">{bi(lang, 'Recorded', 'नोंद झाली')}</div>
        <p className="small" style={{ marginTop: 6 }}>{done.note}</p>
        <div className="note" style={{ marginTop: 10 }}>
          🗓 {bi(lang, 'Follow-up scan due', 'पुन्हा तपासणी')}: <b>{fmtDate(done.followup_due, lang)}</b>
          {done.harvest_gate && <> · {bi(lang, 'harvest gated until', 'काढणी थांबवा')} <b>{fmtDate(done.harvest_gate, lang)}</b></>}
        </div>
        <button className="btn block" style={{ marginTop: 12 }} onClick={() => go('home')}>
          {bi(lang, 'Done', 'ठीक आहे')}
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
        {busy ? '…' : (bi(lang, 'I applied this — record it', 'ही फवारणी केल्याची नोंद करा'))}
      </button>
      <p className="tiny faint center">
        {bi(lang, 'Recording it sets the pre-harvest gate and schedules the re-scan five days from now.', 'नोंद केल्यावर काढणीचा प्रतीक्षा कालावधी सुरू होतो आणि पाच दिवसांनी पुन्हा तपासणी ठरते.')}
      </p>
    </>
  )
}

/* ── what each checklist row can do, right there ────────────────────────────
   A row that says "count the trap" should let you count the trap. Matched on
   the server's own action where one exists (agenda items carry `action.do`),
   and on the ladder's wording only for the one instruction every pest ladder
   opens with. A row with nothing to do here simply has no button. */
function rowAction(it, kind, lang) {
  const doWhat = it.action?.do
  if (doWhat === 'scan') return { label: bi(lang, 'Scan', 'स्कॅन'), run: ({ go }) => go('scan') }
  if (doWhat === 'traps') return { label: bi(lang, 'Count', 'मोजा'), run: ({ jump }) => jump('assess') }
  if (doWhat === 'community') return { label: bi(lang, 'See', 'पहा'), run: ({ go }) => go('hotspots') }
  if (doWhat === 'rescan' && it.action.followup_id)
    return { label: bi(lang, 'Re-scan', 'पुन्हा'), run: ({ go }) => go('rescan', { followup: { id: it.action.followup_id } }) }
  const text = (it.source_text || '').toLowerCase()
  if (kind === 'pest' && /count|trap/.test(text))
    return { label: bi(lang, 'Count', 'मोजा'), run: ({ jump }) => jump('assess') }
  if (kind !== 'pest' && /inspect|walk|scout/.test(text))
    return { label: bi(lang, 'Inspect', 'पाहणी'), run: ({ openAssess }) => openAssess() }
  if (/photograph|photo|scan/.test(text))
    return { label: bi(lang, 'Scan', 'स्कॅन'), run: ({ go }) => go('scan') }
  return null
}

/* ── the count, entered where the decision is ──────────────────────────────
   Type a number and the server answers where it would land against the
   published threshold for this crop at today's stage — the same arithmetic the
   saved decision uses, so what the farmer sees while typing is what they get.
   The preview writes nothing and names no chemical. Offline, the threshold
   reference still shows (it came with the screen) and the count is queued with
   an idempotency key, exactly as the old sheet did. */
const BAND_TONE = { monitor: 'ok', 'act-nonchemical': 'warn', chemical: 'bad', urgent: 'bad' }

function QuickCount({ lang, plot, m, online, onSaved }) {
  const ref = m?.etl_reference || null
  const measured = m?.threshold || null
  const [open, setOpen] = useState(!measured)
  const [count, setCount] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [queued, setQueued] = useState(false)
  const unit = ref?.unit || measured?.unit || bi(lang, 'per trap', 'प्रति सापळा')

  useEffect(() => { setCount(''); setPreview(null); setQueued(false); setOpen(!measured) }, [m?.target, measured?.check_id])

  /* Debounced: a preview per keystroke on a 2G network is a queue of requests
     answering numbers the farmer has already changed. */
  useEffect(() => {
    if (count === '' || !ref || !online) { setPreview(null); return }
    const n = Number(count)
    if (!Number.isFinite(n) || n < 0) { setPreview(null); return }
    let live = true
    const h = setTimeout(() => {
      api.thresholdPreview(plot.id, m.target, n)
        .then(p => { if (live) setPreview(p) })
        .catch(() => { if (live) setPreview(null) })
    }, 350)
    return () => { live = false; clearTimeout(h) }
  }, [count, ref, online, plot?.id, m?.target])

  const step = (delta) => setCount(c => {
    const n = Math.max(0, (Number(c) || 0) + delta)
    return String(Math.round(n * 10) / 10)
  })

  const save = async () => {
    const n = Number(count)
    if (!Number.isFinite(n) || n < 0) return
    setBusy(true); setErr(null)
    try {
      await api.threshold({ plot_id: plot.id, pest: m.target, count: n })
      onSaved()
    } catch (e) {
      if (e.status === 0) {
        queue.add({ kind: 'threshold', plot_id: plot.id, payload: { pest: m.target, count: n }, client_ref: newRef() })
        setQueued(true)
      } else setErr(e)
    } finally { setBusy(false) }
  }

  return (
    <Card className="ipm-count">
      <div className="row between">
        <div className="card-title">🪤 {t(lang, 'howBad')}</div>
        {ref && (
          <span className="tiny muted">
            {bi(lang, 'Threshold today', 'आजची मर्यादा')}: <b>{ref.etl_effective}</b>
          </span>
        )}
      </div>

      {measured ? (
        <>
          <p className="small" style={{ marginTop: 6 }}>
            {bi(lang, 'Last count', 'शेवटची मोजणी')}: <b>{measured.count}</b> {measured.unit}
            {measured.counted_on && <span className="muted"> · {fmtDate(measured.counted_on, lang)}</span>}
          </p>
          <div style={{ marginTop: 10 }}><EtlBar pct={measured.percent_of_threshold} lang={lang} /></div>
          {!open && (
            <button className="btn block ghost" style={{ marginTop: 12 }} onClick={() => setOpen(true)}>
              ➕ {bi(lang, 'Record today’s count', 'आजची मोजणी नोंदवा')}
            </button>
          )}
        </>
      ) : (
        <p className="small" style={{ marginTop: 6 }}>
          {bi(lang, 'Count the trap (or the plants) and enter the number. Nothing is decided from a photograph alone.',
                    'सापळा (किंवा झाडे) मोजा आणि आकडा लिहा. फक्त फोटोवरून निर्णय होत नाही.')}
        </p>
      )}

      {queued && (
        <div className="note warn" style={{ marginTop: 10 }}>
          📴 {bi(lang, 'You are offline. This count is saved on your phone and will be sent when you reconnect — it cannot be counted twice.', 'तुम्ही ऑफलाइन आहात. ही मोजणी फोनवर साठवली आहे आणि इंटरनेट आल्यावर पाठवली जाईल — दोनदा मोजली जाणार नाही.')}
        </div>
      )}

      {open && !queued && (
        <div className="ipm-count__entry">
          <div className="ipm-stepper" role="group" aria-label={unit}>
            <button type="button" className="ipm-stepper__b" onClick={() => step(-1)} aria-label="−1">−</button>
            <input className="input ipm-stepper__n" type="number" inputMode="decimal" min="0" step="0.5"
                   value={count} placeholder="0" onChange={e => setCount(e.target.value)}
                   aria-label={unit} />
            <button type="button" className="ipm-stepper__b" onClick={() => step(1)} aria-label="+1">+</button>
          </div>
          <div className="tiny muted center" style={{ marginTop: 4 }}>{unit}</div>

          {preview ? (
            <div className={`note ${BAND_TONE[preview.band] || 'info'}`} style={{ marginTop: 10 }}>
              <b>{bi(lang, preview.title, preview.title_mr)}</b>
              <div className="tiny" style={{ marginTop: 3 }}>
                {preview.count} ÷ {preview.etl_effective} = {preview.percent_of_threshold}% ·{' '}
                {bi(lang, 'preview, not saved yet', 'पूर्वावलोकन — अजून नोंद नाही')}
              </div>
            </div>
          ) : ref ? (
            <p className="tiny faint" style={{ marginTop: 8 }}>
              {bi(lang, `Published threshold at this stage: ${ref.etl_effective} ${ref.unit}`,
                        `या अवस्थेसाठी प्रकाशित मर्यादा: ${ref.etl_effective} ${ref.unit}`)}
              {ref.alt_threshold ? ` (${ref.alt_threshold})` : ''}
            </p>
          ) : (
            <p className="tiny faint" style={{ marginTop: 8 }}>
              {bi(lang, 'No published threshold for this pest on this crop — the count is recorded, but it cannot be judged against one.',
                        'या पिकावर या किडीची प्रकाशित मर्यादा नाही — मोजणी नोंदवली जाईल, पण तुलना करता येणार नाही.')}
            </p>
          )}

          {err && <ErrorNote error={err} lang={lang} />}
          <button className="btn block" style={{ marginTop: 10 }} disabled={busy || count === ''} onClick={save}>
            {busy ? '…' : bi(lang, 'Save count', 'नोंदवा')}
          </button>
          {!online && (
            <p className="tiny faint center" style={{ marginTop: 6 }}>
              {bi(lang, 'This works offline — it will sync later.', 'ऑफलाइन असतानाही नोंद करता येते.')}
            </p>
          )}
        </div>
      )}

      {ref && (
        <Prov label="Source" value={ref.source}
              extra={ref.source_status === 'draft' ? 'transcribed, pending verification' : undefined} />
      )}
    </Card>
  )
}

/* ── the IPM plan ──────────────────────────────────────────────────────────
   One rung open at a time, starting from the rung the server's decision points
   at. The pointing is a reading of the decision the server already made —
   `threshold.action` for a counted pest, otherwise the monitoring rung — not a
   new judgement. The chemical rung is never opened by this screen: it shows
   what is offered only when the server put a verified option in
   `chemical.options`, and otherwise states what would have to be true. */
const RUNG_ICON = { monitor: '👁', cultural: '🌾', mechanical: '✋', biological: '🐞', chemical: '⚗' }

function IpmPlan({ lang, m, d, kind }) {
  const ladder = m?.ipm_ladder || []
  const action = m?.threshold?.action
  /* A crossed threshold points at chemistry only when the server actually
     offered a verified, unblocked option. Otherwise it points at the highest
     rung that is open — pointing a farmer at a locked door is not advice. */
  const chemOffered = (m?.chemical?.options || []).some(o => !o.blocked)
  const openRungs = ladder.filter(r => !r.withheld && r.key !== 'monitor')
  const highestOpen = openRungs.length ? openRungs[openRungs.length - 1].key : 'monitor'
  const pointed = action === 'chemical' ? (chemOffered ? 'chemical' : highestOpen)
    : action === 'cultural+bio' ? (ladder.find(r => r.key === 'cultural') ? 'cultural' : highestOpen)
    : 'monitor'
  const [sel, setSel] = useState(pointed)
  useEffect(() => { setSel(pointed) }, [pointed, m?.target])
  if (!ladder.length) return null
  const rung = ladder.find(r => r.key === sel) || ladder[0]
  const ref = m?.etl_reference || m?.threshold
  const chemAvail = m?.chemical_availability

  return (
    <Card className="ipm-plan" id="ipm-act">
      <div className="row between">
        <div className="card-title">🪜 {bi(lang, 'Your IPM plan', 'तुमचा IPM आराखडा')}</div>
        <span className="tiny muted">{bi(lang, 'cheapest first', 'आधी स्वस्त उपाय')}</span>
      </div>
      <div className="ipm-rungs" role="tablist">
        {ladder.map(r => (
          <button key={r.key} type="button" role="tab" aria-selected={r.key === sel}
                  className={'ipm-rung' + (r.key === sel ? ' is-sel' : '') + (r.withheld ? ' is-shut' : '')
                             + (r.key === pointed ? ' is-pointed' : '')}
                  onClick={() => setSel(r.key)}>
            <span className="ipm-rung__ic">{r.withheld ? '🔒' : (RUNG_ICON[r.key] || '•')}</span>
            <span className="ipm-rung__l">{bi(lang, RUNG_LABEL[r.key]?.[0] || r.key, RUNG_LABEL[r.key]?.[1] || r.key)}</span>
          </button>
        ))}
      </div>

      <div className="ipm-rung__panel" role="tabpanel">
        <div className="row between" style={{ alignItems: 'flex-start', gap: 8 }}>
          <b className="small">{bi(lang, rung.title, rung.title_mr)}</b>
          {rung.key === pointed && <span className="badge ok">{bi(lang, 'Start here', 'इथून सुरू करा')}</span>}
        </div>
        {rung.cost != null && (
          <div className="tiny faint" style={{ marginTop: 2 }}>
            {rung.cost === 0 ? bi(lang, 'Costs nothing', 'खर्च नाही') : `≈ ${fmtMoney(rung.cost)}/acre`}
          </div>
        )}
        {rung.key === 'monitor' && rung === ladder[0] ? (
          <p className="small muted" style={{ marginTop: 8 }}>
            {bi(lang, 'These steps are in today’s checklist above. The next rung opens only if your count or inspection shows the problem is building.',
                      'या पायऱ्या वरच्या आजच्या यादीत आहेत. मोजणी किंवा पाहणीत प्रादुर्भाव वाढताना दिसला तरच पुढची पायरी उघडते.')}
          </p>
        ) : (
        <div style={{ marginTop: 8 }}>
          {rung.items.map((it, i) => (
            <div className="evid" key={i}>
              <span className={rung.withheld ? 'cross' : 'tick'}>{rung.withheld ? '✗' : '✓'}</span>
              <span>{bi(lang, it.text, it.text_mr)}{it.cost ? ` — ${fmtMoney(it.cost)}` : ''}</span>
            </div>
          ))}
        </div>
        )}

        {rung.key === 'chemical' && rung.withheld && (
          <div className="note" style={{ marginTop: 10 }}>
            <b>{bi(lang, 'What would open this rung', 'ही पायरी कधी उघडेल')}</b>
            <div className="evid" style={{ marginTop: 6 }}>
              <span className="tick">{m?.threshold?.chemical_authorised ? '✓' : '1'}</span>
              <span>{kind === 'pest'
                ? (ref?.etl_effective != null
                    ? bi(lang, `A saved count at or above ${ref.etl_effective} ${ref.unit}`,
                               `${ref.etl_effective} ${ref.unit} किंवा अधिक नोंदवलेली मोजणी`)
                    : bi(lang, 'A saved count over a published threshold', 'प्रकाशित मर्यादेपेक्षा जास्त नोंदवलेली मोजणी'))
                : bi(lang, 'A field inspection showing the disease is established, not a photograph alone',
                           'फक्त फोटो नव्हे, तर रोग पसरल्याचे दाखवणारी शेत पाहणी')}</span>
            </div>
            <div className="evid">
              <span className="tick">{chemOffered ? '✓' : '2'}</span>
              <span>{bi(lang, 'A label claim for this crop and target verified by a named person against the CIB&RC register',
                              'या पिकासाठी व लक्ष्यासाठी CIB&RC नोंदणीशी जुळवून नावानिशी तपासलेला लेबल दावा')}</span>
            </div>
          </div>
        )}
      </div>

      {chemAvail && !chemAvail.verified_available && (
        <details className="method-fold" style={{ marginTop: 10 }}>
          <summary>⚗ {bi(lang, 'No verified chemical recommendation', 'तपासलेली रासायनिक शिफारस नाही')}</summary>
          <p className="small">{bi(lang, chemAvail.message, chemAvail.message_mr)}</p>
          {chemAvail.why && <p className="small muted">{chemAvail.why}</p>}
          <Prov label="Process" value={chemAvail.verification_process} />
        </details>
      )}
      <Prov label="Principle" value={m.ladder_principle} />
    </Card>
  )
}

const RUNG_LABEL = {
  monitor: ['Watch', 'पाहणी'], cultural: ['Cultural', 'मशागत'], mechanical: ['Mechanical', 'यांत्रिक'],
  biological: ['Biological', 'जैविक'], chemical: ['Chemical', 'रासायनिक'],
}
