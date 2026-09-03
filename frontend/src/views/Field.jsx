import React, { useEffect, useRef, useState } from 'react'
import { api, SAMPLES } from '../api'
import { Card, Why, Chip, Loading, ErrorNote, Empty, Stale, t } from '../ui'

/* ═══ FIELD ═══════════════════════════════════════════════════════════════
   The plot's own record: what it is, how its health has moved, and every
   action anyone has taken on it.

   The timeline is written only by real events — a scan, a count, a spray, an
   officer assignment. Nothing here is back-filled to make the screen look
   populated, which is why a new plot shows an empty state instead of a
   convincing fiction.

   This is also where MONITOR lives. A follow-up rescan is the only free source
   of ground truth the system has, and the only way to answer the question the
   problem statement actually asks: did the intervention work?
                                                                            */
const KIND_ICON = {
  scan: '📷', count: '🪤', threshold: '🪤', apply: '🧪', spray: '🧪',
  followup: '🔁', officer: '🧑‍🌾', expert: '📨', risk: '🌧️',
  forecast: '🌧️', sown: '🌱',
}

export function Field({ plot, lang, go }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [due, setDue] = useState([])

  // `blank` only on a plot change. A refresh triggered by a follow-up must not
  // null the state, or it unmounts the follow-up card and destroys the result
  // the farmer just produced — see the same fix in the officer console.
  const load = (blank = false) => {
    if (blank) setD(null)
    setErr(null)
    api.timeline(plot.id).then(setD).catch(setErr)
    api.ledger(plot.id).then(setLedger).catch(() => setLedger(null))
    api.followups().then(r => setDue((r.followups || []).filter(f => f.plot_id === plot.id)))
      .catch(() => setDue([]))
  }
  useEffect(() => { load(true) }, [plot.id])

  if (err) return <ErrorNote error={err} retry={() => load(true)} />
  if (!d) return <Loading what="Opening the field record" />

  const stage = d.crop_stage || {}
  const scores = d.scores || []

  return (
    <>
      {d._stale && <Stale at={d._cachedAt} />}

      {/* ── the plot itself ─────────────────────────────────────────── */}
      <Card title={plot.name}
            right={<Chip level="flat">{plot.id}</Chip>}>
        <div className="grid2" style={{ gap: 0 }}>
          <Fact k="Crop" v={`${cap(plot.crop)}${plot.variety ? ` · ${plot.variety}` : ''}`} />
          <Fact k="Area" v={`${plot.area_acre} acre`} />
          <Fact k="Sown" v={plot.sown_on} />
          <Fact k="Stage" v={`${stage.label || '—'}, day ${stage.days ?? '—'}`} />
          <Fact k="Soil" v={plot.soil || '—'} />
          <Fact k="Irrigation" v={plot.irrigation || '—'} />
          <Fact k="Knapsack" v={`${plot.tank_litres} litre`} />
          <Fact k="Taluka" v={cap(plot.taluka || '')} />
        </div>
        {stage.days_to_harvest != null && (
          <p className="small mt" style={{ color: 'var(--slate)' }}>
            About {stage.days_to_harvest} days of season left. Every threshold on this plot is
            scaled to <b>{stage.label?.toLowerCase()}</b> rather than quoted flat, because the same
            trap count means different things at different stages.
          </p>
        )}
      </Card>

      {/* ── health over time ────────────────────────────────────────── */}
      <Card title="Crop health over time"
            right={scores.length > 1 &&
              <Chip level={delta(scores) > 0 ? 'safe' : delta(scores) < 0 ? 'high' : 'flat'}>
                {delta(scores) === 0 ? 'flat' : `${delta(scores) > 0 ? '+' : ''}${delta(scores)}`}
              </Chip>}>
        {scores.length === 0 ? (
          <Empty icon="📈" title="No health record yet"
                 body="A score is stored each day you open the app. Come back tomorrow and this becomes a line." />
        ) : scores.length === 1 ? (
          <div className="row">
            <div className={`kpi ${band(scores[0].score) === 'safe' ? 'calm' : 'alert'}`}
                 style={{ flex: 1 }}>
              <div className="l">First reading — {scores[0].day}</div>
              <div className="v">{Math.round(scores[0].score)} / 100</div>
              <div className="s">
                One day of history. A trend needs at least two, and drawing a line through a single
                point would invent a direction that has not been measured.
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="spark">
              {scores.map(s => (
                <i key={s.day} className={`bg-${band(s.score)}`}
                   style={{ height: `${Math.max(6, s.score)}%` }}
                   title={`${s.day} — ${Math.round(s.score)}`} />
              ))}
            </div>
            <div className="row tiny mt" style={{ color: 'var(--muted)' }}>
              <span>{scores[0].day}</span>
              <span style={{ flex: 1 }} />
              <span>{scores[scores.length - 1].day} · {Math.round(scores[scores.length - 1].score)}/100</span>
            </div>
          </>
        )}
        <Why label="What this line is, and what it is not">
          <p>
            One point per day the app was opened, computed at that moment from the weather series,
            the pest counts on record and the reports around this taluka. It is a record of
            <b> measured risk</b>, not of yield, and it moves when the inputs move.
          </p>
          <p>
            Days you did not open the app have no point. The line is not interpolated across them,
            because a drawn line between two real numbers invents a shape that was never measured.
          </p>
        </Why>
      </Card>

      {/* ── follow-up due ───────────────────────────────────────────── */}
      {due.length > 0 && <FollowUpDue due={due[0]} plot={plot} onDone={load} />}

      {/* ── the record ──────────────────────────────────────────────── */}
      <Card title={t(lang, 'fieldHistory')}
            right={<Chip level="flat">{d.events.length} events</Chip>}>
        {d.events.length === 0 ? (
          <Empty icon="🗒️" title="Nothing has happened on this plot yet"
                 body="Scan a leaf or record a trap count and it appears here."
                 action={<button className="btn ghost sm mt" onClick={() => go('scan')}>📷 Scan a leaf</button>} />
        ) : (
          <div className="tl">
            {d.events.map(e => (
              <div className={`tl-item ${e.severity || 'info'}`} key={e.id}>
                <div className="tl-d">{e.at}</div>
                <div className="tl-t">{KIND_ICON[e.kind] || '•'} {e.title}</div>
                {e.detail && <div className="tl-x">{e.detail}</div>}
                {e.ref && <div className="tl-x mono tiny" style={{ color: 'var(--faint)' }}>{e.ref}</div>}
              </div>
            ))}
          </div>
        )}
        <p className="note mt">{d.note}</p>
      </Card>

      {/* ── the spray ledger ────────────────────────────────────────── */}
      {ledger && ledger.checks?.length > 0 && (
        <Card title="Counts, and what they prevented"
              right={<Chip level="safe">{ledger.summary.avoided} sprays avoided</Chip>}>
          <table className="tbl">
            <thead><tr><th>Date</th><th>Pest</th><th>Count</th><th>Verdict</th></tr></thead>
            <tbody>
              {[...ledger.checks].reverse().map((c, i) => (
                <tr key={i}>
                  <td>{(c.checked_at || '').slice(0, 10)}</td>
                  <td style={{ textAlign: 'right', fontSize: '.72rem' }}>{c.pest}</td>
                  <td>{c.count}</td>
                  <td className={c.acted ? 't-high'
                                 : ['chemical', 'urgent'].includes(c.band) ? 't-rising' : 't-safe'}>
                    {c.acted ? 'sprayed'
                      : ['chemical', 'urgent'].includes(c.band) ? 'over, not logged' : 'held'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="note mt">
            Against a 7-day cover-spray calendar this plot would have had{' '}
            <b>{ledger.summary.calendar}</b> applications in {ledger.summary.season_days} days. It
            has had <b>{ledger.summary.actual}</b> — about{' '}
            <b>₹{ledger.summary.saved.toLocaleString('en-IN')}</b> and{' '}
            {ledger.summary.litres_not_applied} litres of formulation not applied.
          </div>
          <Why label="What this number is compared against">
            <p>{ledger.summary.baseline}</p>
            <p><b>{ledger.summary.caveat}</b></p>
            <p>
              This is deliberately the weakest claim available. A stronger one would need a paired
              untreated plot over a full season, and we have not run one — so we do not print a
              figure that implies we did.
            </p>
          </Why>
        </Card>
      )}

    </>
  )
}

function Fact({ k, v }) {
  return (
    <div style={{ padding: '8px 0', borderBottom: '1px solid var(--rule-soft)' }}>
      <div className="tiny" style={{ color: 'var(--muted)', fontWeight: 700, letterSpacing: '.05em', textTransform: 'uppercase' }}>{k}</div>
      <div style={{ fontWeight: 600, fontSize: '.9rem' }}>{v}</div>
    </div>
  )
}

const cap = (s) => (s || '').charAt(0).toUpperCase() + (s || '').slice(1)
const band = (s) => s >= 85 ? 'safe' : s >= 70 ? 'watch' : s >= 50 ? 'rising' : 'high'
const delta = (s) => s.length < 2 ? 0 : Math.round(s[s.length - 1].score - s[0].score)

/* ═══ MONITOR ═════════════════════════════════════════════════════════════
   The rescan. Deliberately reports a direction — better, same, worse — and not
   a percentage, because a difference between two phone photographs taken in
   different light does not support a number.

   "Worse" does not offer a second spray. It escalates to a human, because the
   strongest available evidence that a diagnosis was wrong is that treating it
   did not work.                                                             */
function FollowUpDue({ due, plot, onDone }) {
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const file = useRef(null)

  const send = async (blob) => {
    setBusy(true); setErr(null)
    try {
      const r = await api.followup(plot.id, blob)
      setRes(r); onDone()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const useSample = async (id) => {
    const r = await fetch(`/samples/${id}.jpg`).catch(() => null)
    if (!r || !r.ok) { setErr('That reference pattern could not be loaded.'); return }
    send(new File([await r.blob()], `${id}.jpg`, { type: 'image/jpeg' }))
  }

  if (res) {
    const c = res.comparison
    const tone = { better: 'hold', same: 'soft', worse: 'act' }[c.outcome]
    return (
      <section className={`verdict ${tone}`}>
        <div className="big">
          <span>{c.outcome === 'better' ? '🟢' : c.outcome === 'worse' ? '⚠️' : '🟡'}</span>
          <span>{c.label}</span>
        </div>
        <p className="why">{c.say}</p>
        {res.escalated_case && (
          <div className="saved">
            <b>Escalated to {res.escalated_case}.</b> A second spray is not being offered. The
            problem getting worse after treatment is the strongest signal available that the
            diagnosis was wrong, and repeating the same chemistry would build resistance against
            an organism it was never controlling.
          </div>
        )}
        <Why label="Why this is a direction and not a percentage">
          <p>
            Two photographs taken on different days, in different light, at a different distance,
            do not support "37% improvement". They support better, same, or worse. Quoting a
            precision the measurement cannot carry is the most common way an agri app loses a
            farmer's trust the second time they use it.
          </p>
          <p>Compared against the scan of {res.previous.at}.</p>
        </Why>
      </section>
    )
  }

  return (
    <Card title="🔁 Follow-up due"
          right={<Chip level={due.overdue ? 'high' : 'watch'}>
            {due.overdue ? `${-due.days_until}d overdue` : `in ${due.days_until}d`}
          </Chip>}>
      <p className="small">
        A re-check on this plot was due on <b>{due.due_on}</b>. Photograph the same part of the
        field again and PRAHARI will tell you whether the last decision worked — that answer is
        the only ground truth this system gets for free.
      </p>
      {err && <p className="small mt" style={{ color: 'var(--high)' }}>{err}</p>}
      <input ref={file} type="file" accept="image/*" hidden
             onChange={e => e.target.files[0] && send(e.target.files[0])} />
      <button className="btn block mt" disabled={busy} onClick={() => file.current.click()}>
        {busy ? <><span className="spin" /> Comparing…</> : '📷 Photograph it again'}
      </button>
      <div className="samples mt">
        {SAMPLES.slice(0, 3).map(s => (
          <button key={s.id} onClick={() => useSample(s.id)} disabled={busy}>{s.label}</button>
        ))}
      </div>
      <p className="tiny mt" style={{ color: 'var(--muted)' }}>
        Reference patterns are synthetic and labelled as such — they exist so the flow works on a
        laptop with no camera.
      </p>
    </Card>
  )
}
