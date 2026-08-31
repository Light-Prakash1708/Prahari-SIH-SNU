import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Why, Chip, Kpi, Loading, ErrorNote, Empty } from '../ui'

/* ═══ CROP HEALTH COMMAND CENTER ══════════════════════════════════════════
   The officer's problem is not information. It is that one Krishi Sahayak
   covers thousands of farms and can make perhaps five field visits a week.

   So this screen is built around a single question — which five? — and every
   number on it is either a statistic the officer can reproduce (Getis-Ord Gi*,
   a spread-front regression) or a row they can open. There is no
   "AI recommendation" that cannot be traced to one of those two.
                                                                            */
export function Officer() {
  const [sum, setSum] = useState(null)
  const [err, setErr] = useState(null)
  const [problem, setProblem] = useState('late_blight')
  const [open, setOpen] = useState(null)      // taluka id of the open hotspot
  const [tab, setTab] = useState('queue')

  // Refreshing must not blank the state. An earlier version set `sum` to null
  // before refetching, which unmounted the whole officer subtree — so the
  // confirmation banner a validation had just produced was destroyed by the
  // refresh that validation triggered, and the action looked like it had done
  // nothing. Keep the old data on screen until the new data arrives.
  const load = () => { setErr(null); return api.summary().then(setSum).catch(setErr) }
  useEffect(() => { load() }, [])

  if (err) return <ErrorNote error={err} retry={load} />
  if (!sum) return <Loading what="Building the district picture" lines={4} />

  return (
    <>
      <div className="kpis">
        {sum.cards.map(c => (
          <Kpi key={c.key} label={c.label} value={c.value} sub={c.sub} tone={c.tone} />
        ))}
      </div>

      <Card title="Where the pressure is"
            right={
              <select className="filters-sel" value={problem} onChange={e => { setProblem(e.target.value); setOpen(null) }}
                      style={{ padding: '7px 10px', border: '1px solid var(--rule)', borderRadius: 9, fontWeight: 600, fontSize: '.82rem' }}>
                <option value="late_blight">Late blight</option>
                <option value="early_blight">Early blight</option>
                <option value="powdery_mildew">Powdery mildew</option>
                <option value="downy_mildew">Downy mildew</option>
              </select>}>
        <Hotspots problem={problem} onOpen={setOpen} openId={open} />
      </Card>

      {open && <HotspotDetail taluka={open} problem={problem} officers={sum.officers}
                              onClose={() => setOpen(null)} onAssigned={load} />}

      <div className="seg" style={{ background: 'var(--sunk)', margin: '16px 0 12px', width: 'fit-content' }}>
        {[['queue', 'Priority queue'], ['validate', 'Validation'], ['audit', 'Audit']].map(([k, l]) => (
          <button key={k} aria-pressed={tab === k} onClick={() => setTab(k)}
                  style={{ color: tab === k ? '#fff' : 'var(--slate)',
                           background: tab === k ? 'var(--ink)' : 'transparent' }}>{l}</button>
        ))}
      </div>

      {tab === 'queue' && <Queue officers={sum.officers} onAssigned={load} />}
      {tab === 'validate' && <Validation onDone={load} />}
      {tab === 'audit' && <Audit />}
    </>
  )
}

/* ── the map, drawn from coordinates rather than an image ────────────────── */
function Hotspots({ problem, onOpen, openId }) {
  const [d, setD] = useState(null)
  useEffect(() => { setD(null); api.hotspots(problem).then(setD).catch(() => setD({ hotspots: [] })) }, [problem])
  if (!d) return <Loading what="Computing Gi*" lines={2} />

  const hs = d.hotspots || []
  if (!hs.length) return <Empty icon="🗺️" title="No reports for this problem in the window" />

  const lats = hs.map(h => h.lat), lngs = hs.map(h => h.lng)
  const [y0, y1] = [Math.min(...lats), Math.max(...lats)]
  const [x0, x1] = [Math.min(...lngs), Math.max(...lngs)]
  const px = h => ((h.lng - x0) / (x1 - x0 || 1)) * 86 + 7
  const py = h => (1 - (h.lat - y0) / (y1 - y0 || 1)) * 80 + 10

  return (
    <>
      <div style={{ position: 'relative', height: 230, background: 'var(--sunk)',
                    border: '1px solid var(--rule)', borderRadius: 12, overflow: 'hidden', marginBottom: 12 }}>
        {hs.map(h => {
          const r = 9 + Math.min(20, h.cases * 1.5)
          const c = h.class === 'hot' ? 'var(--high)' : h.class === 'warm' ? 'var(--rising)' : 'var(--faint)'
          return (
            <button key={h.taluka} onClick={() => onOpen(h.taluka)} title={`${h.name} — z ${h.z}`}
                    style={{ position: 'absolute', left: `${px(h)}%`, top: `${py(h)}%`,
                             transform: 'translate(-50%,-50%)', width: r * 2, height: r * 2,
                             borderRadius: '50%', background: c, opacity: h.significant ? 0.34 : 0.2,
                             border: `2px solid ${c}`, outline: openId === h.taluka ? '2.5px solid var(--ink)' : 'none',
                             outlineOffset: 2, minHeight: 0 }} />
          )
        })}
        {hs.map(h => (
          <span key={h.taluka} style={{ position: 'absolute', left: `${px(h)}%`, top: `${py(h) + 9}%`,
                                        transform: 'translate(-50%,0)', fontSize: '.66rem', fontWeight: 700,
                                        pointerEvents: 'none', whiteSpace: 'nowrap',
                                        color: h.significant ? 'var(--ink)' : 'var(--muted)' }}>
            {h.name}
          </span>
        ))}
      </div>

      <div className="hsgrid">
        {hs.filter(h => h.cases > 0).map(h => (
          <button className={`hs ${h.class}`} key={h.taluka} onClick={() => onOpen(h.taluka)}>
            <div className="n">{h.name}</div>
            <div className="z">z = {h.z}</div>
            <div className="s">
              {h.cases} report{h.cases === 1 ? '' : 's'} · {h.incidence_per_1000}/1,000 farms
              <br />{h.significant ? '95% significant cluster' : 'not significant'}
            </div>
          </button>
        ))}
      </div>

      <Why label="What z means here, and why it is not just a case count">
        <span className="eq">
          Gi*(i) = [Σⱼ wᵢⱼxⱼ − x̄ Σⱼ wᵢⱼ] / [S √((n Σⱼ wᵢⱼ² − (Σⱼ wᵢⱼ)²)/(n−1))]
        </span>
        <p>
          Getis-Ord Gi* over a binary {d.band_km} km distance band, focal unit included, with
          x = incidence per 1,000 farm households. |z| &gt; 1.96 is the 95% threshold.
        </p>
        <p>
          A raw case count would put the biggest taluka at the top every time. Gi* asks a different
          question: is this taluka <b>and its neighbours together</b> higher than the district
          average by more than chance would produce? That is what distinguishes an outbreak from a
          crowd.
        </p>
        <p className="tiny">
          Window: last {d.window_days} days. Denominator: registered farm households per taluka.
        </p>
      </Why>
    </>
  )
}

/* ── one taluka, opened ──────────────────────────────────────────────────── */
function HotspotDetail({ taluka, problem, officers, onClose, onAssigned }) {
  const [d, setD] = useState(null)
  useEffect(() => { setD(null); api.hotspot(taluka, problem).then(setD).catch(() => setD(null)) }, [taluka, problem])
  if (!d) return <Card><Loading what="Opening the taluka" lines={2} /></Card>

  const s = d.stats
  return (
    <Card title={`${d.taluka.name} — ${d.problem_name || problem}`}
          right={<button className="btn ghost sm" onClick={onClose}>Close</button>}>
      <div className="grid3">
        <Stat k="Reports" v={s.reports} s={`last ${d.window_days} days`} />
        <Stat k="Confirmed" v={s.confirmed} s="by an officer" />
        <Stat k="Area" v={`${s.area_acre}`} s="acre affected" />
      </div>

      <div className="row mt">
        <Chip level={d.velocity.percent_change >= 40 ? 'high' : d.velocity.percent_change > 0 ? 'rising' : 'safe'}>
          {d.velocity.label}
        </Chip>
        <span className="small" style={{ color: 'var(--slate)' }}>{d.velocity.say}</span>
      </div>

      {d.timeline?.length > 1 && (() => {
        const m = Math.max(...d.timeline.map(x => x.reports)) || 1
        return (
          <div className="mt">
            <div className="spark">
              {d.timeline.map(x => (
                <i key={x.date} className="bg-rising"
                   style={{ height: `${(x.reports / m) * 100}%` }}
                   title={`${x.date} — ${x.reports} report${x.reports === 1 ? '' : 's'}`} />
              ))}
            </div>
            <div className="row tiny" style={{ color: 'var(--muted)', marginTop: 4 }}>
              <span>{d.timeline[0].date}</span>
              <span style={{ flex: 1, textAlign: 'center' }}>
                reports per day · peak {m}
              </span>
              <span>{d.timeline[d.timeline.length - 1].date}</span>
            </div>
          </div>
        )
      })()}

      {d.front && (
        <>
          <h3 className="h3" style={{ marginTop: 16 }}>Where it goes next</h3>
          <p className="small" style={{ color: 'var(--slate)' }}>
            Fitted from {d.front.index_taluka}: <b>{d.front.velocity_km_per_day} km/day</b>, R² ={' '}
            {d.front.r2} on {d.front.n_points} talukas.
          </p>
          {d.front.at_risk.map(a => (
            <div className="front-row" key={a.taluka}>
              <span className="front-eta">{a.days_away}d</span>
              <span style={{ flex: 1, fontWeight: 600, fontSize: '.87rem' }}>{a.name}</span>
              <div className="front-bar">
                <div className="front-f" style={{ width: `${Math.max(8, 100 - a.days_away * 6)}%` }} />
              </div>
              <span className="tiny mono" style={{ color: 'var(--muted)' }}>{a.km} km</span>
            </div>
          ))}
          <p className="note mt">{d.front.confidence_note}</p>
        </>
      )}

      <h3 className="h3" style={{ marginTop: 16 }}>Recommended response</h3>
      <div className="steps mt">
        {d.recommended_response.map((r, i) => <div key={i}>{r}</div>)}
      </div>

      <AssignBox taluka={taluka} officers={officers} onAssigned={onAssigned} />

      {d.assignments?.length > 0 && (
        <>
          <h3 className="h3" style={{ marginTop: 16 }}>Visits on this taluka</h3>
          <table className="tbl">
            <thead><tr><th>Officer</th><th>Priority</th><th>Due</th><th>Status</th></tr></thead>
            <tbody>
              {d.assignments.map(a => (
                <tr key={a.id}>
                  <td>{a.officer_name || a.officer_id}</td>
                  <td>{a.priority}</td><td>{a.due_on}</td><td>{a.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <Why label="Where each of these numbers comes from">
        <p>
          Reports, confirmations and acreage are counted from the <code>scouts</code> and{' '}
          <code>plots</code> tables. The velocity is reports in the last three days against the
          three before — no smoothing, so it moves when the field moves.
        </p>
        <p>
          The spread front is an ordinary least-squares fit of each taluka's first-case day on its
          distance from the index taluka. The slope is days per kilometre; its reciprocal is the
          front's speed. Every recommended step above is assembled from those numbers by a rule you
          can read in <code>_response_for()</code> — none of it is generated prose.
        </p>
      </Why>
    </Card>
  )
}

function Stat({ k, v, s }) {
  return (
    <div>
      <div className="tiny" style={{ color: 'var(--muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em' }}>{k}</div>
      <div style={{ fontFamily: 'var(--display)', fontSize: '1.5rem', fontWeight: 700 }}>{v}</div>
      <div className="tiny" style={{ color: 'var(--muted)' }}>{s}</div>
    </div>
  )
}

function AssignBox({ taluka, scoutId, officers, onAssigned }) {
  const [who, setWho] = useState('')
  const [pri, setPri] = useState('P1')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const list = officers || []

  const go = async () => {
    if (!who) return
    setBusy(true)
    try {
      const r = await api.assign({ officer_id: who, priority: pri, taluka, scout_id: scoutId, due_days: 3 })
      setRes(r); onAssigned && onAssigned()
    } catch (e) { setRes({ error: e.message }) } finally { setBusy(false) }
  }

  if (res && !res.error) {
    return (
      <div className="note mt">
        <b>Assigned to {res.officer.name}</b>, due {res.due_on}.{' '}
        {res.load && <>They now hold {res.load.open_visits} open visits against a capacity of{' '}
          {res.officer.visits_per_week} a week.</>}
        {res.warning && <div style={{ color: 'var(--high)', marginTop: 6 }}>⚠️ {res.warning}</div>}
        <div style={{ marginTop: 6 }}>The farmer has been notified that someone is coming.</div>
      </div>
    )
  }

  return (
    <div className="filters" style={{ marginTop: 14, marginBottom: 0 }}>
      <select value={who} onChange={e => setWho(e.target.value)}>
        <option value="">Assign a field visit…</option>
        {list.map(o => (
          <option key={o.id} value={o.id}>
            {o.name} — {o.open_visits}/{o.visits_per_week} this week
          </option>
        ))}
      </select>
      <select value={pri} onChange={e => setPri(e.target.value)}>
        <option value="P1">P1</option><option value="P2">P2</option><option value="P3">P3</option>
      </select>
      <button className="btn sm" disabled={!who || busy} onClick={go}>
        {busy ? <span className="spin" /> : 'Assign'}
      </button>
      {res?.error && <span className="small" style={{ color: 'var(--high)' }}>{res.error}</span>}
    </div>
  )
}

/* ── the queue: the whole point of the screen ────────────────────────────── */
function Queue({ officers, onAssigned }) {
  const [d, setD] = useState(null)
  const [cap, setCap] = useState(5)
  const [openRow, setOpenRow] = useState(null)
  const load = () => api.queue(cap).then(setD).catch(() => {})
  useEffect(() => { load() }, [cap])
  if (!d) return <Loading what="Ranking cases" lines={3} />
  const week = d.visit_this_week || []

  return (
    <Card title="This week's field visits"
          right={
            <select value={cap} onChange={e => setCap(Number(e.target.value))}
                    style={{ padding: '7px 10px', border: '1px solid var(--rule)', borderRadius: 9, fontWeight: 600, fontSize: '.82rem' }}>
              {[3, 5, 8, 12].map(n => <option key={n} value={n}>{n} visits</option>)}
            </select>}>
      {week.length === 0 ? (
        <Empty icon="✅" title="Nothing is waiting on a visit" />
      ) : week.map((q, i) => (
        <div key={q.id}>
          <div className="qrow">
            <span className={`p ${q.priority}`}>{q.priority}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: '.92rem' }}>
                {q.plot_name} · {q.taluka_name}
              </div>
              <div className="small" style={{ color: 'var(--slate)' }}>
                {q.farmer_name} · {q.crop} · {q.area_acre} acre
              </div>
              <div className="small" style={{ marginTop: 4 }}>
                <b>Why this is #{i + 1}:</b> {q.why}.
              </div>
              <button className="btn ghost sm mt" onClick={() => setOpenRow(openRow === q.id ? null : q.id)}>
                {openRow === q.id ? 'Hide' : 'Assign or inspect'}
              </button>
            </div>
            <span className="tiny" style={{ color: 'var(--muted)', textAlign: 'right', flexShrink: 0 }}>
              <span className="mono" style={{ fontSize: '.9rem', fontWeight: 700, color: 'var(--slate)' }}>
                {q.priority_score}
              </span><br />score
            </span>
          </div>
          {openRow === q.id && (
            <div style={{ margin: '-4px 0 12px', padding: '0 14px' }}>
              <table className="tbl">
                <tbody>
                  <tr><td>Scan</td><td>{q.id}</td></tr>
                  <tr><td>Suspected</td><td>{(q.suspected || '—').replace(/_/g, ' ')}</td></tr>
                  <tr><td>Model</td><td>{q.abstained ? `declined — ${q.abstain_reason}` :
                    `${Math.round((q.posterior || 0) * 100)}%`}</td></tr>
                  <tr><td>Hotspot</td><td>{q.hotspot_class} (z = {q.hotspot_z})</td></tr>
                  <tr><td>Phone</td><td>{q.phone}</td></tr>
                </tbody>
              </table>
              <AssignBox taluka={q.taluka} scoutId={q.id} officers={officers}
                         onAssigned={() => { onAssigned && onAssigned(); load() }} />
            </div>
          )}
        </div>
      ))}

      <Why label="How the order is decided">
        <p>{d.rationale}</p>
        <p>
          The list is deliberately cut to a number of visits one person can actually make. A queue
          of four hundred is the same as no queue — {d.deferred > 0
            ? `${d.deferred} further case${d.deferred === 1 ? ' is' : 's are'} held back rather than shown as an unworkable backlog.`
            : 'everything open fits inside this week.'}
        </p>
        <p>
          An abstention ranks <b>above</b> a confident diagnosis, which is the opposite of most
          triage. A case the model is sure about needs no expert; a case it refused to answer is
          exactly where a human adds something.
        </p>
      </Why>
    </Card>
  )
}

/* ── validation: one integer, and the whole learning step ────────────────── */
function Validation({ onDone }) {
  const [d, setD] = useState(null)
  const [res, setRes] = useState(null)
  const [pick, setPick] = useState({})
  const load = () => api.queue(20).then(setD).catch(() => {})
  useEffect(() => { load() }, [])
  if (!d) return <Loading what="Loading cases" lines={2} />

  const open = (d.queue || []).filter(q => q.abstained)
  const submit = async (q) => {
    const problem = pick[q.id] || q.suspected
    if (!problem) return
    try { setRes(await api.validate(q.id, problem)); load(); onDone && onDone() }
    catch (e) { setRes({ error: e.message }) }
  }

  return (
    <Card title="Confirm what it actually was">
      {res && !res.error && (
        <div className="note" style={{ marginBottom: 12, borderLeftColor: 'var(--safe)' }}>
          <b>{res.corrected ? 'Model corrected' : 'Model confirmed'}</b> — {res.note}
        </div>
      )}
      {res?.error && <p className="small" style={{ color: 'var(--high)' }}>{res.error}</p>}

      {open.length === 0 ? (
        <Empty icon="🎯" title="Every declined case has been reviewed" />
      ) : open.slice(0, 6).map(q => (
        <div className="qrow" key={q.id}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: '.9rem' }}>{q.plot_name} · {q.crop}</div>
            <div className="small" style={{ color: 'var(--slate)' }}>
              Declined: {q.abstain_reason} · suspected {(q.suspected || '—').replace(/_/g, ' ')}
            </div>
            <div className="filters" style={{ marginTop: 8, marginBottom: 0 }}>
              <select value={pick[q.id] || q.suspected || ''}
                      onChange={e => setPick({ ...pick, [q.id]: e.target.value })}>
                {['late_blight', 'early_blight', 'powdery_mildew', 'downy_mildew',
                  'bacterial_wilt', 'nitrogen_deficiency', 'healthy'].map(p => (
                  <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>
                ))}
              </select>
              <button className="btn sm" onClick={() => submit(q)}>Confirm</button>
            </div>
          </div>
        </div>
      ))}

      <Why label="What one confirmation changes">
        <p>
          The taluka prior is a Dirichlet distribution over the candidate problems. Every candidate
          starts at α = 1. A confirmation adds exactly one to that candidate's α — nothing else
          happens, and nothing is retrained.
        </p>
        <p>
          That means the model gets better where officers are working, at the speed they work, and
          any claim about it can be checked by counting rows in <code>priors</code>. A gradient
          update would be faster and completely unauditable to the person whose job depends on it.
        </p>
      </Why>
    </Card>
  )
}

/* ── audit: the views behind every number in this app ────────────────────── */
function Audit() {
  const [d, setD] = useState(null)
  useEffect(() => { api.audit().then(setD).catch(() => setD(null)) }, [])
  if (!d) return <Loading what="Reading the ledger" lines={2} />

  return (
    <>
      <Card title="Sprays avoided, by pest">
        <table className="tbl">
          <thead><tr><th>Crop / pest</th><th>Checks</th><th>Held</th><th>Sprayed</th><th>₹ saved</th></tr></thead>
          <tbody>
            {d.spray_ledger.map((r, i) => (
              <tr key={i}>
                <td>{r.crop} · {r.pest}</td><td>{r.checks}</td><td>{r.not_sprayed}</td>
                <td>{r.sprayed}</td><td>{Math.round(r.rupees_saved).toLocaleString('en-IN')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Where the model declined">
        <table className="tbl">
          <thead><tr><th>Reason</th><th>Cases</th><th>Resolved</th></tr></thead>
          <tbody>
            {d.abstentions.map((r, i) => (
              <tr key={i}>
                <td>{r.abstain_reason}</td><td>{r.n}</td><td>{r.resolved_by_expert}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note mt">
          An abstention rate that falls to zero is not a success — it means the floors have been
          set low enough that the model is guessing. This table is how that is caught.
        </p>
      </Card>

      {d.model_vs_expert?.length > 0 && (
        <Card title="Model against expert">
          <table className="tbl">
            <thead><tr><th>Model suspected</th><th>Expert confirmed</th><th>Cases</th><th></th></tr></thead>
            <tbody>
              {d.model_vs_expert.map((r, i) => (
                <tr key={i}>
                  <td>{(r.suspected || '—').replace(/_/g, ' ')}</td>
                  <td>{(r.confirmed || '—').replace(/_/g, ' ')}</td>
                  <td>{r.n}</td>
                  <td className={r.suspected === r.confirmed ? 't-safe' : 't-high'}>
                    {r.suspected === r.confirmed ? 'agreed' : 'corrected'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {d.harvest_gate?.length > 0 && (
        <Card title="Harvest gate">
          <table className="tbl">
            <thead><tr><th>Plot</th><th>Crop</th><th>Earliest harvest</th><th>Days</th></tr></thead>
            <tbody>
              {d.harvest_gate.map((r, i) => (
                <tr key={i}>
                  <td>{r.name}</td><td>{r.crop}</td><td>{r.earliest_harvest}</td>
                  <td className={r.days_left > 0 ? 't-high' : 't-safe'}>
                    {r.days_left > 0 ? `${r.days_left} to go` : 'clear'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <p className="note">{d.note}</p>
    </>
  )
}
