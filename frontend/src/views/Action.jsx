import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Why, Chip, Loading, ErrorNote, t, L } from '../ui'

/* ═══ ACTION PLAN ═════════════════════════════════════════════════════════
   Count → threshold → ladder → prescription → log.

   The order is the safety argument: nothing on this screen can reach a
   chemical without passing through a threshold crossing first, and the
   prescription itself is screened four more times before it is shown.
                                                                            */
export function Action({ plot, lang, pest, setPest, pests, target }) {
  const [count, setCount] = useState(2)
  const [d, setD] = useState(null)
  const [rx, setRx] = useState(null)
  const [busy, setBusy] = useState(false)
  const [applied, setApplied] = useState(null)
  const [err, setErr] = useState(null)

  const P = pests.find(p => p.id === pest)
  useEffect(() => { setD(null); setRx(null); setApplied(null); setErr(null) }, [pest, plot.id])

  async function check() {
    setBusy(true); setRx(null); setApplied(null); setErr(null)
    try {
      const r = await api.threshold(plot.id, pest, count)
      setD(r)
      if (r.chemical_authorised) setRx(await api.prescribe(plot.id, pest))
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  // A disease diagnosed by the camera has no trap count — go straight to the
  // ladder for it instead of pretending a count exists.
  const [dz, setDz] = useState(null)
  useEffect(() => {
    if (target && !pests.some(p => p.id === target)) {
      api.prescribe(plot.id, target).then(setDz).catch(() => setDz(null))
    } else setDz(null)
  }, [target, plot.id])

  const max = P ? Math.max(6, Math.round((P.etl || 5) * 3)) : 30

  return (
    <>
      <header className="mb">
        <p className="eyebrow">{plot.name} · {plot.crop}</p>
        <h1 className="h1">🪤 Count before you spray</h1>
        <p className="sub">
          A diagnosis tells you what it is. Only a threshold tells you whether it is worth treating.
        </p>
      </header>

      {dz && <DiseasePlan rx={dz} plot={plot} lang={lang} target={target} />}

      <Card title="Which pest are you monitoring?">
        <select className="sel" value={pest} onChange={e => setPest(e.target.value)}
                aria-label="Pest">
          {pests.map(p => <option key={p.id} value={p.id}>{p.em} {p.name} — {p.sci}</option>)}
        </select>
        {P && (
          <>
            <div className="note mt">
              <b>Trap:</b> {P.trap}<br />
              <b>How to look:</b> {lang === 'mr' && P.mr_scout ? P.mr_scout : P.scout}
            </div>
            <label className="mt" style={{ display: 'block', fontWeight: 700, fontSize: '.92rem' }}>
              Your count: <span className="mono">{count}</span>{' '}
              <span className="sub" style={{ fontWeight: 400 }}>{P.unit}</span>
            </label>
            <input type="range" min={0} max={max} step={1} value={count}
                   onChange={e => setCount(+e.target.value)} aria-label="Count" />
            <button className="btn block mt" onClick={check} disabled={busy}>
              {busy ? <span className="spin" /> : 'Check against the threshold'}
            </button>
          </>
        )}
      </Card>

      {err && <ErrorNote error={err} />}

      {d && (
        <>
          <section className={`verdict ${d.chemical_authorised ? 'act' : d.band === 'act-nonchemical' ? 'soft' : 'hold'}`}>
            <div className="big">
              <span>{d.chemical_authorised ? '⚠️' : '🟢'}</span>
              <span>{d.chemical_authorised ? L(lang, d, 'title') : t(lang, 'dontSpray')}</span>
            </div>

            <div className="scale">
              <div className="scale-track">
                <div className="scale-etl" />
                <div className="scale-mark" style={{ left: `${Math.min(96, (d.count / (d.etl_effective * 3)) * 100)}%` }} />
                <div className="scale-cur" style={{ left: `${Math.min(96, (d.count / (d.etl_effective * 3)) * 100)}%` }}>
                  {d.count}
                </div>
              </div>
              <div className="scale-lab">
                <span className="lo">0</span>
                <span className="etl">threshold {d.etl_effective}</span>
                <span className="hi">{(d.etl_effective * 3).toFixed(0)}</span>
              </div>
            </div>

            <p className="why">{L(lang, d, 'why')}</p>

            {d.trend_say && (
              <p className="small mt" style={{ fontWeight: 600 }}>
                {d.trend_direction === 'up' ? '📈' : d.trend_direction === 'down' ? '📉' : '➡️'}{' '}
                {d.trend_say}
              </p>
            )}
            {d.trend?.length > 1 && (
              <div className="spark mt" aria-hidden="true">
                {d.trend.map((x, i) => (
                  <i key={i} className={x.count >= d.etl_effective ? 'bg-high' : 'bg-watch'}
                     style={{ height: `${Math.max(6, (x.count / (d.etl_effective * 2)) * 100)}%` }} />
                ))}
              </div>
            )}

            {!d.chemical_authorised && d.saving_if_not_sprayed > 0 && (
              <div className="saved">
                Not spraying today keeps{' '}
                <b className="mono">₹{d.saving_if_not_sprayed.toLocaleString('en-IN')}</b> in your
                pocket — product plus labour for one application over {plot.area_acre} acre.
                <br /><b>Next review:</b> count again in 5 days.
              </div>
            )}

            <Why label="Where this threshold comes from">
              <p>
                <b>{d.source}</b>{d.source_status === 'draft' && ' — marked DRAFT pending verification'}.
                The base figure is {d.etl_base} {d.unit}; at the <b>{d.stage}</b> stage it is scaled
                by ×{d.stage_factor} to {d.etl_effective}, because the same count means different
                things at different crop stages.
              </p>
              {d.alt_threshold && <p><b>Equivalent field check:</b> {d.alt_threshold}</p>}
              {d.economics && (
                <>
                  <table className="tbl" style={{ marginTop: 8 }}>
                    <tbody>
                      <tr><td>Crop value at risk</td><td>₹{d.economics.crop_gross_value.toLocaleString('en-IN')}</td></tr>
                      <tr><td>Cost of one application</td><td>₹{d.economics.spray_cost.toLocaleString('en-IN')}</td></tr>
                      <tr><td>Estimated damage avoided</td><td>₹{d.economics.estimated_damage_avoided.toLocaleString('en-IN')}</td></tr>
                      <tr><td><b>Net of spraying</b></td><td><b>₹{d.economics.net_of_spraying.toLocaleString('en-IN')}</b></td></tr>
                    </tbody>
                  </table>
                  <p>{d.economics.note}</p>
                </>
              )}
            </Why>
          </section>

          <Card title={`🌱 ${t(lang, 'action')}`}>
            <div className="ladder">
              {d.ladder.map(s => (
                <div className={`rung ${s.withheld ? 'off' : 'on'}`} data-n={s.rung} key={s.rung}>
                  <div className="rung-t">{L(lang, s, 'title')}</div>
                  {s.items.map((i, n) => (
                    <div className="rung-i" key={n}>
                      {i.text}{i.cost ? <span className="cost"> · ₹{i.cost}/acre</span> : null}
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div className="note mt">
              <b>Then reassess.</b> Count again in five days. If the count has fallen, the cheap rungs
              worked and you have saved the cost of a spray.
            </div>
          </Card>
        </>
      )}

      {rx && <Prescription rx={rx} plot={plot} checkId={d?.check_id} target={pest}
                           onApplied={setApplied} lang={lang} />}

      {applied && (
        <Card>
          <div className="row">
            <span style={{ fontSize: '1.5rem' }}>⏳</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700 }}>Logged. {applied.phi.msg}</div>
              <p className="small mt" style={{ color: 'var(--slate)' }}>{applied.note}</p>
            </div>
          </div>
        </Card>
      )}
    </>
  )
}

/* A disease has no trap count — the ladder and the label screen still apply. */
function DiseasePlan({ rx, plot, lang, target }) {
  return (
    <Card title="🌱 For the problem you just scanned">
      <div className="ladder">
        {rx.ipm.filter(s => s.rung < 3).map(s => (
          <div className="rung on" data-n={s.rung} key={s.rung}>
            <div className="rung-t">{L(lang, s, 'title')}</div>
            {s.items.map((i, n) => (
              <div className="rung-i" key={n}>
                {i.text}{i.cost ? <span className="cost"> · ₹{i.cost}/acre</span> : null}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="note mt">
        Cultural and biological control apply immediately and cost little. A fungicide is a separate
        decision, and it is gated on the published infection model rather than on the photograph.
      </div>
    </Card>
  )
}

/* ═══ PRESCRIPTION ════════════════════════════════════════════════════════ */
function Prescription({ rx, plot, checkId, target, onApplied, lang }) {
  const [busy, setBusy] = useState(false)
  const rec = rx.recommended

  async function log() {
    setBusy(true)
    try { onApplied(await api.apply(plot.id, { ...rec, target }, checkId)) }
    finally { setBusy(false) }
  }

  return (
    <Card title="💊 What you may legally use">
      <div className="banner">{rx.verification_banner}</div>
      {rx.no_option_msg && <div className="note mb">{rx.no_option_msg}</div>}

      {rec && (
        <div className="dose mb">
          <p className="eyebrow" style={{ color: 'rgba(255,255,255,.55)' }}>Your dose, in your units</p>
          <div className="big" style={{ marginTop: 6 }}>
            {rec.dose.per_tank} {rec.dose.per_tank_unit} per {rec.dose.tank_litres} L tank
          </div>
          <div className="line">{rec.dose.plain}</div>
          <div className="line" style={{ marginTop: 9 }}><b>Protective gear:</b> {rec.ppe}</div>
        </div>
      )}

      {rx.options.map(o => (
        <div className={`rx ${o.blocked ? 'blocked' : ''} ${o === rec ? 'pick' : ''}`} key={o.product}>
          <div className="rx-hd">
            <span className={`tri ${o.toxicity}`} title={o.toxicity_label} />
            <span className="sr">{o.toxicity_label}</span>
            <div className="rx-n">{o.product}</div>
            <span className="chip flat">{o.moa}</span>
          </div>
          <div className="rx-m">
            {o.dose.label_rate} · PHI {o.phi_days} d · re-entry {o.reentry_hours} h ·
            ₹{o.cost_per_acre}/acre · {o.toxicity_label}
          </div>
          {o.blocks.map((b, i) => <div className="rx-block" key={i}><b>{b.rule}</b> — {b.msg}</div>)}
          {o.warnings.filter(w => w.rule !== 'verification').map((w, i) =>
            <div className="rx-warn" key={i}>{w.msg}</div>)}
        </div>
      ))}

      {rec && (
        <>
          <button className="btn block mt" onClick={log} disabled={busy}>
            {busy ? <span className="spin" />
                  : `Log this application — sets a ${rec.phi_days}-day harvest gate`}
          </button>
          <p className="tiny mt" style={{ color: 'var(--muted)', textAlign: 'center' }}>
            Logging records the mode-of-action group, which is what blocks the next prescription
            from repeating it, and starts the pre-harvest countdown.
          </p>
        </>
      )}

      <Why label="The four rules this screen enforces">
        <p><b>1 · Label claim.</b> India registers a pesticide against a specific crop <i>and</i> a
          specific pest. In October 2017, 21 farmers died in Yavatmal; the Centre for Science and
          Environment found that state advisories were recommending molecules with no CIB&amp;RC
          registration for the crop sprayed. Nothing appears above unless it is in the label-claim
          table for this exact crop and target.</p>
        <p><b>2 · State ban.</b> Section 27 of the Insecticides Act lets a state prohibit use in the
          public interest; Maharashtra used it in September 2018 on five formulations. The restricted
          list is data read at request time, never compiled in, so a recommendation can go stale
          overnight.</p>
        <p><b>3 · Resistance rotation.</b> IRAC and FRAC both say never to follow a mode-of-action
          group with itself. Pink bollworm broke Bt cotton in Maharashtra by exactly that route. Your
          last application used <b>{rx.last_moa_used || 'nothing yet'}</b>, and anything in that group
          is blocked above.</p>
        <p><b>4 · Pre-harvest interval.</b> A product whose PHI outruns the days to harvest is
          removed, because using it makes the crop unsellable to any buyer who tests residue.</p>
      </Why>
    </Card>
  )
}
