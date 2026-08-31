/* PRAHARI · the officer command centre.

   A different product from the farmer app, deliberately. This one is dense,
   dark, desktop-first and built for someone with five field visits a week and
   forty open cases.

   Everything shown here is scoped server-side to the talukas this officer is
   authorised for. Farmer contact details appear only on a case they have been
   assigned — never in the queue, never on the map. */
import React, { useEffect, useState } from 'react'
import { api, auth } from '../api'
import { Donut, ErrorNote, Loading, Prov, Shield, Spark } from '../ui'

const NAV = [
  ['overview', '▦', 'Overview'],
  ['hotspots', '◉', 'Hotspots'],
  ['queue', '☰', 'Priority queue'],
  ['route', '⇢', 'Field visits'],
  ['audit', '✓', 'Audit'],
]

export default function Officer({ me, health }) {
  const [tab, setTab] = useState('overview')
  const [summary, setSummary] = useState(null)
  const [err, setErr] = useState(null)

  const load = () => {
    setErr(null)
    api.officerSummary(14).then(setSummary).catch(setErr)
  }
  useEffect(load, [])

  return (
    <div className="oc">
      <aside className="oc-side">
        <div className="oc-brand">
          <Shield size={22} tone="#157A3C" leaf="#8BD3A4" />
          <span className="nm">PRAHARI</span>
        </div>
        <nav className="oc-nav">
          {NAV.map(([k, ic, label]) => (
            <button key={k} aria-current={tab === k ? 'page' : undefined} onClick={() => setTab(k)}>
              <span>{ic}</span><span>{label}</span>
            </button>
          ))}
        </nav>
        <div style={{ marginTop: 22, padding: '0 12px' }}>
          <div style={{ fontSize: 11, color: 'var(--d-muted)' }}>Signed in as</div>
          <div style={{ fontSize: 13, fontWeight: 700, marginTop: 3 }}>{me?.user?.full_name}</div>
          <div style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 2 }}>
            {(me?.scopes || []).length} taluka{(me?.scopes || []).length === 1 ? '' : 's'} in scope
          </div>
          <button className="oc-btn ghost" style={{ marginTop: 12, width: '100%' }}
                  onClick={async () => { try { await api.logout() } catch {} auth.clear() }}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="oc-main">
        <div className="oc-head">
          <div>
            <h1 style={{ fontFamily: 'var(--display)', fontSize: 20, fontWeight: 800 }}>
              {NAV.find(n => n[0] === tab)?.[2]}
            </h1>
            <div style={{ fontSize: 12, color: 'var(--d-muted)', marginTop: 3 }}>
              {summary?.scope_names?.join(' · ') || 'Loading scope…'}
            </div>
          </div>
          {health?.config?.demo_mode && (
            <span className="oc-badge mod">DEMO MODE — weather is generated</span>
          )}
        </div>

        {err && <div style={{ maxWidth: 620 }}><ErrorNote error={err} onRetry={load} /></div>}

        {tab === 'overview' && <Overview summary={summary} />}
        {tab === 'hotspots' && <Hotspots />}
        {tab === 'queue' && <Queue />}
        {tab === 'route' && <RoutePlan />}
        {tab === 'audit' && <Audit />}
      </main>
    </div>
  )
}

/* ── overview ──────────────────────────────────────────────────────────── */
function Overview({ summary }) {
  const [outbreaks, setOutbreaks] = useState(null)
  const [signals, setSignals] = useState(null)
  const [busy, setBusy] = useState(null)
  const [note, setNote] = useState('')
  useEffect(() => { api.outbreaks().then(r => setOutbreaks(r.events || [])).catch(() => setOutbreaks([])) }, [])
  const loadSignals = () =>
    api.officerSignals(true).then(r => setSignals(r.signals || [])).catch(() => setSignals([]))
  useEffect(() => { loadSignals() }, [])

  const decide = async (id, confirmed) => {
    const text = note.trim() || (confirmed
      ? 'Confirmed on a field visit.'
      : 'Inspected and not found — closing the signal.')
    setBusy(id)
    try { await api.confirmSignal(id, { confirmed, note: text }); setNote(''); await loadSignals() }
    finally { setBusy(null) }
  }

  if (!summary) return <Loading lines={3} />

  const kpis = [
    ['Active cases', summary.active_cases, 'observations open in your talukas'],
    ['Community reports', summary.community_posts ?? 0,
     `${summary.community_unanswered ?? 0} with nobody answering yet`],
    ['Awaiting verification', summary.awaiting_verification, 'expert cases not yet decided'],
    ['Model abstentions', summary.model_abstentions, 'the camera declined to answer'],
    ['Worse after treatment', summary.worsening_after_treatment?.length || 0, 'escalated automatically'],
  ]

  return (
    <>
      <div className="oc-kpis">
        {kpis.map(([label, val, sub]) => (
          <div className="oc-kpi" key={label}>
            <div className="lbl">{label}</div>
            <div className="val">{val ?? 0}</div>
            <div className="delta" style={{ color: 'var(--d-muted)', fontWeight: 500 }}>{sub}</div>
          </div>
        ))}
      </div>

      <div className="oc-grid">
        <div className="oc-card">
          <h3>Graded clusters in your scope</h3>
          {outbreaks === null && <Loading lines={2} />}
          {outbreaks?.length === 0 && (
            <p style={{ fontSize: 12.5, color: 'var(--d-muted)' }}>
              No cluster in your talukas currently meets the floor of 3 reports across 2 distinct
              fields. PRAHARI will not call anything a cluster below that.
            </p>
          )}
          {outbreaks?.map(o => (
            <div key={o.id} style={{
              border: '1px solid var(--d-rule)', borderRadius: 10, padding: 12, marginBottom: 10,
            }}>
              <div className="row between">
                <div>
                  <b style={{ fontSize: 13.5 }}>{o.problem_name} · {o.taluka_name}</b>
                  <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginTop: 3 }}>
                    {o.reports} reports · {o.confirmed} expert-confirmed
                    {o.gi_z != null && <> · Gi* z = {o.gi_z}</>}
                    {o.radius_km != null && <> · ~{o.radius_km} km</>}
                  </div>
                </div>
                <span className={`oc-badge ${o.grade === 'confirmed_hotspot' ? 'high'
                  : o.grade === 'suspected_hotspot' ? 'mod' : 'new'}`}>{o.label}</span>
              </div>
            </div>
          ))}
          <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 8, lineHeight: 1.5 }}>
            A cluster is graded by the evidence that exists: reports and distinct fields make it
            <b> emerging</b>, a significant Gi* makes it <b>suspected</b>, and only expert
            confirmations make it <b>confirmed</b>.
          </p>
        </div>

        <div className="oc-card">
          <h3>Reports by problem (14 days)</h3>
          {summary.by_problem?.length > 0
            ? <Donut data={summary.by_problem.map(p => ({ label: p.problem_name, value: p.n }))} />
            : <p style={{ fontSize: 12.5, color: 'var(--d-muted)' }}>No reports in this window.</p>}
          <h3 style={{ marginTop: 20 }}>By crop</h3>
          {summary.by_crop?.map(c => (
            <div className="row between" key={c.crop} style={{ fontSize: 12.5, padding: '5px 0' }}>
              <span style={{ textTransform: 'capitalize' }}>{c.crop}</span><b>{c.n}</b>
            </div>
          ))}
        </div>
      </div>

      {/* ── what farmers are SAYING, kept beside what has been DIAGNOSED ──
          Two different kinds of evidence — earlier, cheaper, weaker — and they
          justify different actions. A signal justifies a visit; a confirmed
          cluster justifies an advisory. Merging the panels would lose that. */}
      <div className="oc-card" style={{ marginTop: 14 }}>
        <div className="row between" style={{ marginBottom: 4 }}>
          <h3 style={{ margin: 0 }}>Community signals in your scope</h3>
          <button className="oc-btn ghost" onClick={loadSignals}>Recompute</button>
        </div>
        <p style={{ fontSize: 11.5, color: 'var(--d-muted)', margin: '6px 0 12px', lineHeight: 1.5 }}>
          What farmers are <b>saying</b>, graded separately from what has been <b>diagnosed</b>.
          A signal is not an outbreak: an outbreak declaration needs expert-confirmed diagnoses
          and lives in the panel above.
        </p>
        {signals === null && <Loading lines={2} />}
        {signals?.length === 0 && (
          <p style={{ fontSize: 12.5, color: 'var(--d-muted)' }}>
            Nothing is clustering in your talukas. PRAHARI needs 3 posts from at least 2 different
            farmers before it will use the word cluster — one farmer posting four times is one
            farmer.
          </p>
        )}
        {signals?.map(s => (
          <div className="oc-sig" key={s.id}>
            <span className="dot" style={{
              background: s.grade === 'confirmed_field_signal' ? 'var(--bad)'
                : s.grade === 'corroborated_signal' ? 'var(--warn)' : 'var(--info)',
            }} />
            <div className="grow">
              <div className="row between">
                <span className="nm">{s.problem_name} · {s.taluka_name}</span>
                <span className={`oc-badge ${s.grade === 'confirmed_field_signal' ? 'high'
                  : s.grade === 'corroborated_signal' ? 'mod' : 'new'}`}>{s.label}</span>
              </div>
              <div className="sub">
                {s.distinct_authors} different farmers · {s.distinct_villages} village(s) ·
                {' '}{s.same_problem_votes} said "me too" · {s.diagnoses_n} diagnosis(es) ·
                {' '}{s.expert_confirmations} expert · {s.trap_signals} trap(s) over threshold
              </div>
              <div className="sub" style={{ marginTop: 4 }}>{s.means}</div>
              {s.officer_note && (
                <div className="sub" style={{ marginTop: 4, fontStyle: 'italic' }}>
                  Your note: {s.officer_note}
                </div>
              )}
              {s.grade !== 'confirmed_field_signal' && (
                <div className="row" style={{ gap: 8, marginTop: 9 }}>
                  <input className="oc-input" placeholder="What did you find in the field?"
                         value={note} onChange={e => setNote(e.target.value)}
                         style={{ flex: 1, minWidth: 0 }} />
                  <button className="oc-btn" disabled={busy === s.id}
                          onClick={() => decide(s.id, true)}>Confirm on the ground</button>
                  <button className="oc-btn ghost" disabled={busy === s.id}
                          onClick={() => decide(s.id, false)}>Not found</button>
                </div>
              )}
            </div>
          </div>
        ))}
        <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10, lineHeight: 1.5 }}>
          Confirming tells every farmer in that taluka growing that crop to scout — as a count,
          never as a name. PRAHARI does not disclose whose fields the reports came from.
        </p>
      </div>

      {summary.high_risk_fields?.length > 0 && (
        <div className="oc-card" style={{ marginTop: 14 }}>
          <h3>High-risk fields (crop-health score below 50)</h3>
          <table className="oc-table">
            <thead><tr><th>Field</th><th>Crop</th><th>Taluka</th><th>Score</th><th>Day</th></tr></thead>
            <tbody>
              {summary.high_risk_fields.map(f => (
                <tr key={f.plot_id + f.day}>
                  <td>{f.plot_name}</td>
                  <td style={{ textTransform: 'capitalize' }}>{f.crop}</td>
                  <td>{f.taluka}</td>
                  <td><span className="oc-badge high">{Math.round(f.score)}</span></td>
                  <td style={{ color: 'var(--d-muted)' }}>{f.day}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {summary.worsening_after_treatment?.length > 0 && (
        <div className="oc-card" style={{ marginTop: 14, borderColor: '#4A2320' }}>
          <h3>Worse after treatment — escalated automatically</h3>
          <table className="oc-table">
            <thead><tr><th>Field</th><th>Crop</th><th>Taluka</th><th>Re-scanned</th></tr></thead>
            <tbody>
              {summary.worsening_after_treatment.map(w => (
                <tr key={w.id}>
                  <td>{w.plot_name}</td>
                  <td style={{ textTransform: 'capitalize' }}>{w.crop}</td>
                  <td>{w.taluka}</td>
                  <td style={{ color: 'var(--d-muted)' }}>{w.done_on}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10 }}>
            A field that is worse after treatment is the strongest available signal that the
            diagnosis was wrong. PRAHARI escalates it rather than offering a second spray.
          </p>
        </div>
      )}
    </>
  )
}

/* ── hotspots ──────────────────────────────────────────────────────────── */
const PROBLEMS = ['late_blight', 'early_blight', 'downy_mildew', 'powdery_mildew', 'purple_blotch', 'turcicum_blight']

function Hotspots() {
  const [problem, setProblem] = useState('late_blight')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setData(null); setErr(null)
    api.hotspots(problem).then(setData).catch(setErr)
  }, [problem])

  return (
    <>
      <div className="row" style={{ gap: 10, marginBottom: 14 }}>
        <select className="oc-input" value={problem} onChange={e => setProblem(e.target.value)}>
          {PROBLEMS.map(p => <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>)}
        </select>
      </div>

      {err && <ErrorNote error={err} />}
      {!data && !err && <Loading lines={2} />}

      {data && (
        <div className="oc-grid">
          <div className="oc-card">
            <h3>Getis-Ord Gi* — {data.problem_name} · {data.total_reports} reports in {data.window_days} days</h3>
            <HotspotMap hotspots={data.hotspots} />
            <div className="legend" style={{ marginTop: 12, color: 'var(--d-muted)' }}>
              <span><i style={{ background: '#7FD79E' }} />Low</span>
              <span><i style={{ background: '#F6C56B' }} />Elevated</span>
              <span><i style={{ background: '#FF9A97' }} />95% hotspot</span>
            </div>
            <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10, lineHeight: 1.5 }}>
              {data.statistic}
            </p>
            <p style={{ fontSize: 11, color: '#F6C56B', marginTop: 8, lineHeight: 1.5 }}>
              ⚠ {data.caveat}
            </p>
          </div>

          <div className="oc-card">
            <h3>Taluka scores</h3>
            <table className="oc-table">
              <thead><tr><th>Taluka</th><th>Reports</th><th>Per 1,000 farms</th><th>Gi* z</th><th>Class</th></tr></thead>
              <tbody>
                {data.hotspots.map(h => (
                  <tr key={h.taluka}>
                    <td>{h.name}</td>
                    <td>{h.cases ?? 0}</td>
                    <td className="mono">{h.incidence_per_1000}</td>
                    <td className="mono">{h.z}</td>
                    <td>
                      <span className={`oc-badge ${h.class === 'hot' ? 'high' : h.class === 'warm' ? 'mod' : 'low'}`}>
                        {h.class}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.front && (
              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--d-rule)' }}>
                <h3>Spread front</h3>
                <div style={{ fontSize: 12.5 }}>
                  Moving at about <b>{data.front.velocity_km_per_day} km/day</b>
                  {data.front.bearing != null && <> on a bearing of {Math.round(data.front.bearing)}°</>}
                </div>
                <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 6 }}>{data.front.caveat}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}

/* A schematic map: taluka centroids positioned by their real coordinates,
   sized by report count, coloured by Gi* class. Not a basemap — PRAHARI does
   not ship tiles it cannot serve offline, and a fake-looking basemap under real
   statistics is worse than no basemap at all. */
function HotspotMap({ hotspots }) {
  const pts = hotspots.filter(h => h.lat != null && h.lng != null)
  if (!pts.length) return <p style={{ fontSize: 12.5, color: 'var(--d-muted)' }}>No coordinates available.</p>
  const lats = pts.map(p => p.lat), lngs = pts.map(p => p.lng)
  const pad = 0.06
  const minLat = Math.min(...lats) - pad, maxLat = Math.max(...lats) + pad
  const minLng = Math.min(...lngs) - pad, maxLng = Math.max(...lngs) + pad
  const W = 460, H = 300
  const x = (lng) => ((lng - minLng) / (maxLng - minLng)) * (W - 40) + 20
  const y = (lat) => H - (((lat - minLat) / (maxLat - minLat)) * (H - 40) + 20)
  const maxCount = Math.max(1, ...pts.map(p => p.cases || 0))
  const colour = (c) => c === 'hot' ? '#FF9A97' : c === 'warm' ? '#F6C56B' : '#7FD79E'

  return (
    <div className="oc-map">
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', display: 'block' }}>
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40 0 L0 0 0 40" fill="none" stroke="#1C2E24" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="url(#grid)" />
        {pts.map(p => (
          <g key={p.taluka}>
            <circle cx={x(p.lng)} cy={y(p.lat)} r={10 + ((p.cases || 0) / maxCount) * 22}
                    fill={colour(p.class)} opacity=".18" />
            <circle cx={x(p.lng)} cy={y(p.lat)} r={5} fill={colour(p.class)} />
            <text x={x(p.lng)} y={y(p.lat) - 12} textAnchor="middle"
                  fill="#C7D6CD" fontSize="9.5" fontWeight="600">{p.name}</text>
            {p.cases > 0 && (
              <text x={x(p.lng)} y={y(p.lat) + 17} textAnchor="middle"
                    fill={colour(p.class)} fontSize="10" fontWeight="800">{p.cases}</text>
            )}
          </g>
        ))}
      </svg>
    </div>
  )
}

/* ── priority queue ────────────────────────────────────────────────────── */
function Queue() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(null)

  const load = () => { setErr(null); api.queue(5).then(setData).catch(setErr) }
  useEffect(load, [])

  const assign = async (obsId) => {
    setBusy(obsId)
    try { await api.assign({ observation_id: obsId, priority: 'P1', due_in_days: 2 }); load() }
    catch (e) { setErr(e) } finally { setBusy(null) }
  }

  if (err) return <ErrorNote error={err} onRetry={load} />
  if (!data) return <Loading lines={3} />

  return (
    <>
      <div className="oc-card">
        <h3>{data.queue.length} open cases · {data.capacity} visits this week</h3>
        <p style={{ fontSize: 12, color: 'var(--d-muted)', marginBottom: 14, lineHeight: 1.55 }}>
          {data.rationale}
        </p>
        <table className="oc-table">
          <thead>
            <tr><th>#</th><th>Field</th><th>Crop</th><th>Taluka</th><th>Suspected</th>
              <th>Why this ranks here</th><th>Priority</th><th /></tr>
          </thead>
          <tbody>
            {data.queue.map((c, i) => (
              <tr key={c.id}>
                <td style={{ color: 'var(--d-muted)' }}>{i + 1}</td>
                <td>{c.plot_name}</td>
                <td style={{ textTransform: 'capitalize' }}>{c.crop}</td>
                <td>{c.taluka_name || c.taluka}</td>
                <td>
                  {c.abstained
                    ? <span className="oc-badge mod">model declined</span>
                    : (c.top_problem_name || '—')}
                </td>
                <td style={{ color: 'var(--d-muted)', maxWidth: 320 }}>{c.why}</td>
                <td>
                  <span className={`oc-badge ${c.priority === 'P1' ? 'high' : c.priority === 'P2' ? 'mod' : 'low'}`}>
                    {c.priority}
                  </span>
                </td>
                <td>
                  <button className="oc-btn" disabled={busy === c.id} onClick={() => assign(c.id)}>
                    {busy === c.id ? '…' : 'Assign'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.queue.length === 0 && (
          <p style={{ fontSize: 12.5, color: 'var(--d-muted)' }}>No open cases in your talukas.</p>
        )}
      </div>
      <Assignments />
    </>
  )
}

function Assignments() {
  const [rows, setRows] = useState(null)
  const [open, setOpen] = useState(null)
  const load = () => api.assignments().then(r => setRows(r.assignments)).catch(() => setRows([]))
  useEffect(load, [])
  if (!rows?.length) return null
  return (
    <div className="oc-card" style={{ marginTop: 14 }}>
      <h3>Your assigned visits</h3>
      <table className="oc-table">
        <thead><tr><th>Field</th><th>Taluka</th><th>Due</th><th>Farmer</th><th>Status</th><th /></tr></thead>
        <tbody>
          {rows.map(a => (
            <tr key={a.id}>
              <td>{a.plot_name || '—'}</td>
              <td>{a.taluka}</td>
              <td>{a.due_on}</td>
              <td>{a.farmer_name}{a.farmer_phone ? ` · ${a.farmer_phone}` : ''}</td>
              <td><span className={`oc-badge ${a.status === 'assigned' ? 'new' : 'low'}`}>{a.status}</span></td>
              <td>
                {a.status === 'assigned' && (
                  <button className="oc-btn ghost" onClick={() => setOpen(a)}>Close visit</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10 }}>
        Farmer contact details appear here because you have been assigned this visit. They do not
        appear in the queue or on the map.
      </p>
      {open && <CloseVisit a={open} onClose={() => setOpen(null)} onDone={() => { setOpen(null); load() }} />}
    </div>
  )
}

function CloseVisit({ a, onClose, onDone }) {
  const [f, setF] = useState({ status: 'confirmed', confirmed_problem: 'late_blight', finding: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.closeAssignment(a.id, {
        status: f.status, finding: f.finding || undefined,
        confirmed_problem: f.status === 'confirmed' ? f.confirmed_problem : undefined,
      })
      onDone()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  return (
    <div className="scrim" onClick={onClose}>
      <div className="oc-card" onClick={e => e.stopPropagation()}
           style={{ maxWidth: 460, width: '92%', margin: 'auto', alignSelf: 'center' }}>
        <h3>Close visit — {a.plot_name}</h3>
        <label style={{ display: 'block', marginBottom: 10 }}>
          <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginBottom: 4 }}>Outcome</div>
          <select className="oc-input" style={{ width: '100%' }} value={f.status}
                  onChange={e => setF(x => ({ ...x, status: e.target.value }))}>
            <option value="confirmed">Confirmed on the ground</option>
            <option value="rejected">Not present / rejected</option>
            <option value="visited">Visited, inconclusive</option>
            <option value="escalated">Escalated further</option>
          </select>
        </label>
        {f.status === 'confirmed' && (
          <label style={{ display: 'block', marginBottom: 10 }}>
            <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginBottom: 4 }}>What was it?</div>
            <select className="oc-input" style={{ width: '100%' }} value={f.confirmed_problem}
                    onChange={e => setF(x => ({ ...x, confirmed_problem: e.target.value }))}>
              {PROBLEMS.map(p => <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>)}
            </select>
          </label>
        )}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginBottom: 4 }}>Finding</div>
          <textarea className="oc-input" style={{ width: '100%', minHeight: 76 }} value={f.finding}
                    onChange={e => setF(x => ({ ...x, finding: e.target.value }))} />
        </label>
        {err && <ErrorNote error={err} />}
        <div className="row" style={{ gap: 8 }}>
          <button className="oc-btn ghost" onClick={onClose}>Cancel</button>
          <button className="oc-btn" disabled={busy} onClick={save}>{busy ? '…' : 'Record'}</button>
        </div>
        <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10 }}>
          A confirmation adds exactly 1 to α for that problem in that taluka — the whole
          request-time learning step, and auditable by counting confirmed cases.
        </p>
      </div>
    </div>
  )
}

/* ── route plan ────────────────────────────────────────────────────────── */
function RoutePlan() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { api.route(5).then(setData).catch(setErr) }, [])
  if (err) return <ErrorNote error={err} />
  if (!data) return <Loading lines={2} />
  return (
    <div className="oc-card">
      <h3>Suggested inspection sequence · {data.stops} stops · {data.total_km} km</h3>
      {data.sequence.length === 0 && (
        <p style={{ fontSize: 12.5, color: 'var(--d-muted)' }}>{data.note || 'No cases with a location in scope.'}</p>
      )}
      <div style={{ marginTop: 10 }}>
        {data.sequence.map(s => (
          <div key={s.position} className="row" style={{
            gap: 12, padding: '11px 0', borderBottom: '1px solid var(--d-rule)', alignItems: 'flex-start',
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%', background: 'var(--g-600)', color: '#fff',
              display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 12.5, flex: 'none',
            }}>{s.position}</div>
            <div className="grow">
              <div style={{ fontSize: 13.5, fontWeight: 700 }}>{s.plot_name} · {s.taluka_name}</div>
              <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginTop: 3 }}>
                {s.crop} · {s.leg_km} km from the previous stop · {s.why}
              </div>
            </div>
            <span className={`oc-badge ${s.priority === 'P1' ? 'high' : 'mod'}`}>{s.priority}</span>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 12, lineHeight: 1.55 }}>
        <b>Method:</b> {data.method}<br />
        <b>Caveat:</b> {data.caveat}
      </p>
    </div>
  )
}

/* ── audit ─────────────────────────────────────────────────────────────── */
function Audit() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { api.audit().then(setData).catch(setErr) }, [])
  if (err) return <ErrorNote error={err} />
  if (!data) return <Loading lines={3} />

  const Table = ({ title, rows, cols }) => (
    <div className="oc-card" style={{ marginBottom: 14 }}>
      <h3>{title}</h3>
      {rows?.length ? (
        <table className="oc-table">
          <thead><tr>{cols.map(c => <th key={c}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>{cols.map(c => <td key={c}>{String(r[c] ?? '—')}</td>)}</tr>
            ))}
          </tbody>
        </table>
      ) : <p style={{ fontSize: 12.5, color: 'var(--d-muted)' }}>Nothing recorded yet.</p>}
    </div>
  )

  return (
    <>
      <div className="oc-card" style={{ marginBottom: 14 }}>
        <h3>How to read this page</h3>
        <p style={{ fontSize: 12.5, color: 'var(--d-muted)', lineHeight: 1.6 }}>{data.note}</p>
      </div>
      <Table title="Spray ledger — what the threshold gate actually prevented"
             rows={data.spray_ledger} cols={['crop', 'pest', 'checks', 'not_sprayed', 'sprayed', 'rupees_saved']} />
      <Table title="Model vs expert" rows={data.model_vs_expert} cols={['suspected', 'confirmed', 'n']} />
      <Table title="Abstentions, and whether an expert resolved them"
             rows={data.abstentions} cols={['abstain_reason', 'n', 'resolved_by_expert']} />
      <Table title="Chemical reference table by verification status"
             rows={data.label_claims_by_status} cols={['status', 'n']} />
      <Table title="Notification delivery — what the gateway actually said"
             rows={data.notification_deliveries} cols={['channel', 'state', 'n']} />
      <Table title="Harvest gates currently in force" rows={data.harvest_gate}
             cols={['name', 'crop', 'earliest_harvest']} />
    </>
  )
}
