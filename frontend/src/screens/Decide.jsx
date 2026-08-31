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

export default function Decide({ lang, plot, target: initialTarget, go, online }) {
  const [target, setTarget] = useState(initialTarget || null)
  const [pests, setPests] = useState([])
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState('cultural')
  const [countOpen, setCountOpen] = useState(false)

  useEffect(() => {
    if (!plot) return
    api.risk(plot.id)
      .then(r => {
        const p = (r.board || []).filter(b => b.kind === 'pest' && b.etl != null)
        setPests(p)
        if (!target && p.length) setTarget(p[0].id)
      })
      .catch(() => {})
  }, [plot?.id])

  const load = () => {
    if (!plot || !target) return
    setBusy(true); setErr(null)
    api.shouldISpray(plot.id, target).then(setData).catch(setErr).finally(() => setBusy(false))
  }
  useEffect(load, [plot?.id, target])

  const d = data?.decision
  const th = data?.threshold
  const chem = data?.chemical
  const avail = data?.chemical_availability
  const ladder = data?.ipm_ladder || []
  const pest = pests.find(p => p.id === target)

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{lang === 'mr' ? 'फवारणी करू का?' : 'Should I Spray?'}</h1>
      </div>

      <div className="pad stack" style={{ paddingTop: 14 }}>
        {pests.length > 1 && (
          <div className="chips">
            {pests.map(p => (
              <button key={p.id} className="chip" aria-pressed={p.id === target}
                      onClick={() => setTarget(p.id)}>
                {p.em} {bi(lang, p.name, p.name_mr)}
              </button>
            ))}
          </div>
        )}

        {busy && <Loading lines={3} />}
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}

        {d && !busy && (
          <>
            {/* ── the decision ─────────────────────────────────────────── */}
            <div className={`decision ${d.tone}`}>
              <div className="shield">{d.icon}</div>
              <div className="ans">{bi(lang, d.answer, d.answer_mr)}</div>
              <p className="why">{bi(lang, d.reason, d.reason_mr)}</p>
            </div>

            {/* ── ETL status ───────────────────────────────────────────── */}
            {th ? (
              <Card>
                <div className="card-title" style={{ marginBottom: 10 }}>
                  {lang === 'mr' ? 'आर्थिक नुकसान मर्यादा (ETL)' : 'Economic Threshold status'}
                </div>
                <EtlBar pct={th.percent_of_threshold} />
                <div className="row between" style={{ marginTop: 14 }}>
                  <div>
                    <div className="tiny muted">{lang === 'mr' ? 'सध्याची मोजणी' : 'Current count'}</div>
                    <div className="num" style={{ fontSize: 26 }}>{th.count}</div>
                    <div className="tiny faint">{th.unit}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div className="tiny muted">{lang === 'mr' ? 'तुमच्या पिकासाठी मर्यादा' : 'Threshold for your crop'}</div>
                    <div className="num" style={{ fontSize: 26 }}>{th.etl_effective}</div>
                    <div className="tiny faint">
                      {th.stage_factor !== 1
                        ? `${th.etl_base} × ${th.stage_factor} (${th.stage})`
                        : th.unit}
                    </div>
                  </div>
                </div>

                {th.trend?.length > 1 && (
                  <div style={{ marginTop: 14 }}>
                    <div className="tiny muted" style={{ marginBottom: 5 }}>
                      {lang === 'mr' ? 'मागील मोजण्या' : 'Recent counts'}
                    </div>
                    <div className="row" style={{ gap: 6 }}>
                      {th.trend.map((tr, i) => (
                        <div key={i} className="grow" style={{
                          background: 'var(--sunk)', borderRadius: 8, padding: '7px 4px', textAlign: 'center',
                        }}>
                          <div className="num" style={{ fontSize: 15 }}>{tr.count}</div>
                          <div className="tiny faint">{fmtDate(tr.on, lang)}</div>
                        </div>
                      ))}
                    </div>
                    {th.trend_say && <p className="small muted" style={{ marginTop: 8 }}>{th.trend_say}</p>}
                    {th.trend_alert && <div className="note bad" style={{ marginTop: 8 }}>{th.trend_alert}</div>}
                  </div>
                )}

                {th.saving_if_not_sprayed && (
                  <div className="note" style={{ marginTop: 12 }}>
                    💰 {lang === 'mr'
                      ? `आत्ता फवारणी न केल्याने अंदाजे ${fmtMoney(th.saving_if_not_sprayed)} वाचतात.`
                      : `Not spraying today keeps about ${fmtMoney(th.saving_if_not_sprayed)} in your pocket.`}
                  </div>
                )}

                <Why label={lang === 'mr' ? 'ही मर्यादा कुठून आली?' : 'Where does this threshold come from?'}>
                  <Prov label="Source" value={th.etl_provenance?.source}
                        extra={th.etl_provenance?.status === 'draft'
                          ? 'transcribed, pending verification' : undefined} />
                  {th.etl_provenance?.alt && (
                    <p className="small" style={{ marginTop: 6 }}>
                      Alternative field check: {th.etl_provenance.alt}
                    </p>
                  )}
                  {th.economics && (
                    <div style={{ marginTop: 10 }}>
                      <div className="row between small"><span>Crop gross value</span><b>{fmtMoney(th.economics.crop_gross_value)}</b></div>
                      <div className="row between small"><span>One spray costs</span><b>{fmtMoney(th.economics.spray_cost)}</b></div>
                      <div className="row between small"><span>Estimated damage avoided</span><b>{fmtMoney(th.economics.estimated_damage_avoided)}</b></div>
                      <Prov label="Caveat" value={th.economics.note} />
                    </div>
                  )}
                </Why>
              </Card>
            ) : (
              <Card>
                <div className="card-title">{lang === 'mr' ? 'अजून मोजणी झालेली नाही' : 'Nothing counted yet'}</div>
                <p className="small muted" style={{ marginTop: 6 }}>
                  {lang === 'mr'
                    ? 'निदान काय आहे ते सांगते. कृती करावी का, हे फक्त मोजणी सांगते.'
                    : 'A diagnosis says what is there. Only a count says whether it is worth acting on.'}
                </p>
                <button className="btn block" style={{ marginTop: 12 }} onClick={() => setCountOpen(true)}>
                  {lang === 'mr' ? 'मोजणी नोंदवा' : 'Record a count'}
                </button>
              </Card>
            )}

            {/* ── evidence behind the decision ─────────────────────────── */}
            {d.evidence?.length > 0 && (
              <Card>
                <div className="card-title" style={{ marginBottom: 6 }}>
                  {lang === 'mr' ? 'हा निर्णय कशावर आधारित आहे' : 'What this decision rests on'}
                </div>
                {d.evidence.map((e, i) => (
                  <div className="evid" key={i}>
                    <span className="tick">•</span>
                    <span><b style={{ textTransform: 'capitalize' }}>{e.kind.replace(/_/g, ' ')}:</b> {e.detail || e.explain}</span>
                  </div>
                ))}
                {d.recheck_on && (
                  <div className="note info" style={{ marginTop: 10 }}>
                    🗓 {lang === 'mr'
                      ? `पुन्हा तपासा: ${fmtDate(d.recheck_on, lang)} (${d.recheck_after_hours} तासांनी)`
                      : `Re-check on ${fmtDate(d.recheck_on, lang)} — ${d.recheck_after_hours} hours from now`}
                  </div>
                )}
              </Card>
            )}

            {/* ── the IPM ladder ───────────────────────────────────────── */}
            <h2 className="sect-title">{lang === 'mr' ? 'एकात्मिक कीड व्यवस्थापन' : 'IPM Recommendations'}</h2>
            <div className="stack">
              {ladder.map(step => (
                <div className={`rung ${step.withheld ? 'shut' : 'open'}`} key={step.key}>
                  <div className="rung-head">
                    <span className="rung-n">{step.rung}</span>
                    <div className="grow">
                      <div style={{ fontWeight: 700, fontSize: 14 }}>{bi(lang, step.title, step.title_mr)}</div>
                      {step.cost != null && <div className="tiny faint">≈ {fmtMoney(step.cost)}/acre</div>}
                    </div>
                    {step.withheld && <span className="badge grey">{lang === 'mr' ? 'बंद' : 'Withheld'}</span>}
                  </div>
                  <div style={{ marginTop: 9 }}>
                    {step.items.map((it, i) => (
                      <div className="evid" key={i}>
                        <span className={step.withheld ? 'cross' : 'tick'}>{step.withheld ? '✗' : '✓'}</span>
                        <span>{it.text}{it.cost ? ` — ${fmtMoney(it.cost)}` : ''}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <Prov label="Principle" value={data.ladder_principle} />

            {/* ── chemical options ─────────────────────────────────────── */}
            {avail && !avail.verified_available && (
              <Card style={{ borderColor: 'var(--warn-line)', background: 'var(--warn-bg)' }}>
                <div className="card-title" style={{ color: 'var(--warn)' }}>
                  {lang === 'mr' ? 'तपासलेली रासायनिक शिफारस नाही' : 'No verified chemical recommendation'}
                </div>
                <p className="small" style={{ marginTop: 7 }}>
                  {bi(lang, avail.message, avail.message_mr)}
                </p>
                <Why label={lang === 'mr' ? 'का नाही?' : 'Why not?'}>
                  <p className="small">{avail.why}</p>
                  <Prov label="Process" value={avail.verification_process} />
                </Why>
              </Card>
            )}

            {chem?.options?.length > 0 && (
              <>
                <h2 className="sect-title">
                  {lang === 'mr' ? 'तपासलेले रासायनिक पर्याय' : 'Verified chemical options'}
                </h2>
                {chem.options.map(o => <ChemOption key={o.product} o={o} lang={lang} />)}
                {chem.recommended && (
                  <ApplyButton lang={lang} plot={plot} target={target} rec={chem.recommended}
                               checkId={th?.check_id} go={go} />
                )}
              </>
            )}

            {data.phi?.blocked && (
              <div className="note bad">
                🚫 {lang === 'mr'
                  ? `काढणी ${fmtDate(data.phi.clears_on, lang)} पर्यंत थांबवा — शेवटच्या फवारणीचा प्रतीक्षा कालावधी.`
                  : `Harvest is gated until ${fmtDate(data.phi.clears_on, lang)} by the pre-harvest interval of your last application.`}
              </div>
            )}

            <button className="btn block quiet" onClick={() => setCountOpen(true)}>
              {lang === 'mr' ? '＋ नवीन मोजणी नोंदवा' : '＋ Record a new count'}
            </button>
          </>
        )}
      </div>

      <CountSheet open={countOpen} onClose={() => setCountOpen(false)} lang={lang}
                  plot={plot} pest={pest} online={online} onSaved={load} />
    </>
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
