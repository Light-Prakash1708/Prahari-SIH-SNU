/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · the administrator's console

   Until now an admin account was handed the officer console, which is a
   district-surveillance product: useful, and not what an administrator's job
   is. The four things only an administrator can do had no interface at all.

   In order of consequence:

   1. VERIFY A LABEL CLAIM. `chemicals.py` will not return a claim that has not
      been verified against a cited CIB&RC source, so an unverified row is a
      recommendation PRAHARI is currently refusing to make. This is the highest
      -risk action in the entire system — it is the moment a chemical becomes
      something the app will tell a farmer to spray — so it is first, it names
      the person who verified it, and it demands the citation before it will
      submit.
   2. Who can act on other people's records, and where.
   3. What the system holds, and what it is running.
   4. The audit trail.

   The console owns no logic. Every number comes from /api/admin/overview, and
   every action is an existing endpoint that was already audited.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useEffect, useState } from 'react'
import { api, auth } from '../api'
import { ErrorNote, Loading } from '../ui'

const NAV = [
  ['overview', '▦', 'Overview'],
  ['claims', '⚗', 'Label claims'],
  ['staff', '☰', 'Staff & scope'],
  ['audit', '✓', 'Audit'],
]

export default function Admin({ me }) {
  const [tab, setTab] = useState('overview')
  const user = me?.user || {}

  return (
    <div className="oc">
      <aside className="oc-side">
        <div className="oc-brand">
          <img src="/brand/logo.png" alt="PRAHARI" width="112" height="37" />
        </div>
        <nav className="oc-nav">
          {NAV.map(([k, ic, label]) => (
            <button key={k} aria-current={tab === k ? 'page' : undefined}
                    onClick={() => setTab(k)}>
              <span aria-hidden="true">{ic}</span> {label}
            </button>
          ))}
        </nav>
        <div className="oc-who">
          <div className="tiny muted">Signed in as</div>
          <div className="nm">{user.full_name}</div>
          <div className="tiny muted">Administrator</div>
          <button className="oc-btn ghost" style={{ marginTop: 12, width: '100%' }}
                  onClick={() => auth.clear()}>Sign out</button>
        </div>
      </aside>

      <main className="oc-main">
        {tab === 'overview' && <Overview />}
        {tab === 'claims' && <Claims me={me} />}
        {tab === 'staff' && <Staff />}
        {tab === 'audit' && <Audit />}
      </main>
    </div>
  )
}

/* ── overview ─────────────────────────────────────────────────────────────── */
function Overview() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { api.adminOverview().then(setD).catch(setErr) }, [])

  if (err) return <ErrorNote error={err} />
  if (!d) return <Loading lines={4} />

  const unverified = d.claims.draft || 0
  return (
    <>
      <div className="oc-head"><h2>Overview</h2></div>

      <div className="oc-kpis">
        {[['Farmers', d.counts.farmers], ['Fields', d.counts.fields],
          ['Observations', d.counts.observations], ['Diagnoses', d.counts.diagnoses],
          ['Community posts', d.counts.community_posts], ['Staff accounts', d.counts.staff],
        ].map(([lbl, v]) => (
          <div className="oc-kpi" key={lbl}>
            <div className="lbl">{lbl}</div><div className="val">{v}</div>
          </div>
        ))}
      </div>

      {/* The one number on this screen that changes what farmers are told. */}
      <div className={'oc-card oc-gate' + (unverified ? ' is-open' : '')}
           style={{ marginTop: 14 }}>
        <h3>The chemical gate</h3>
        <div className="oc-gate__row">
          <div>
            <div className="val">{d.claims.verified || 0}</div>
            <div className="tiny muted">verified — may be recommended</div>
          </div>
          <div>
            <div className="val warn">{unverified}</div>
            <div className="tiny muted">draft — PRAHARI refuses to recommend these</div>
          </div>
          <div>
            <div className="val">{d.claims.rejected || 0}</div>
            <div className="tiny muted">rejected</div>
          </div>
          <div>
            <div className="val">{d.claims.expired || 0}</div>
            <div className="tiny muted">expired</div>
          </div>
        </div>
        <p className="tiny muted" style={{ marginTop: 10, lineHeight: 1.55 }}>
          {d.claims_note}
        </p>
      </div>

      <div className="oc-grid" style={{ marginTop: 14 }}>
        <div className="oc-card">
          <h3>Vision model</h3>
          <p className="small" style={{ lineHeight: 1.6 }}>{d.vision.reason || d.vision.engine}</p>
          <table className="oc-table" style={{ marginTop: 10 }}>
            <tbody>
              <tr><td>engine</td><td className="mono">{String(d.vision.engine)}</td></tr>
              <tr><td>ready</td><td className="mono">{String(d.vision.ready)}</td></tr>
              <tr><td>diagnosis possible</td>
                  <td className="mono">{String(d.vision.diagnosis_possible)}</td></tr>
            </tbody>
          </table>
        </div>
        <div className="oc-card">
          <h3>Deployment</h3>
          <table className="oc-table">
            <tbody>
              {Object.entries(d.config || {}).slice(0, 12).map(([k, v]) => (
                <tr key={k}><td>{k}</td><td className="mono">{String(v)}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="tiny muted" style={{ marginTop: 8 }}>
            {(d.migrations || []).length} migrations applied.
          </p>
        </div>
      </div>
    </>
  )
}

/* ── label claims — the gate ─────────────────────────────────────────────── */
function Claims({ me }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState(null)
  const [status, setStatus] = useState('draft')
  const [open, setOpen] = useState(null)

  const load = () => {
    setRows(null)
    api.adminClaims(status ? { status } : {}).then(r => setRows(r.claims)).catch(setErr)
  }
  useEffect(load, [status])

  return (
    <>
      <div className="oc-head">
        <h2>Label claims</h2>
        <div className="oc-seg">
          {['draft', 'verified', 'rejected', ''].map(s => (
            <button key={s || 'all'} aria-current={status === s ? 'page' : undefined}
                    onClick={() => setStatus(s)}>{s || 'all'}</button>
          ))}
        </div>
      </div>

      <div className="oc-card oc-warn">
        <h3>Read this before verifying anything</h3>
        <p className="small" style={{ lineHeight: 1.6 }}>
          Verifying a claim is what makes PRAHARI willing to name a chemical to a farmer.
          It records <b>your name</b>, the time, and the citation. Verify a row only after
          you have personally checked it against the CIB&amp;RC <i>Major Uses of Pesticides</i>
          list — the crop, the target pest, the dose and the pre-harvest interval. A row you
          leave in draft costs a farmer a recommendation; a row you verify wrongly costs them
          a crop or a residue rejection.
        </p>
      </div>

      {err && <ErrorNote error={err} />}
      {!rows && <Loading lines={5} />}
      {rows && (
        <div className="oc-card" style={{ marginTop: 14 }}>
          <h3>{rows.length} claim{rows.length === 1 ? '' : 's'}</h3>
          <div className="oc-scroll">
            <table className="oc-table">
              <thead>
                <tr><th>Product</th><th>Crop</th><th>Target</th><th>Dose</th>
                    <th>PHI</th><th>Status</th><th /></tr>
              </thead>
              <tbody>
                {rows.map(c => (
                  <tr key={c.id}>
                    <td><b>{c.product}</b><div className="tiny muted">{c.moa_group || '—'}</div></td>
                    <td>{c.crop}</td>
                    <td>{c.target}</td>
                    <td className="mono">{c.dose_text || '—'}</td>
                    <td className="mono">{c.phi_days ?? '—'}</td>
                    <td><span className={'oc-badge ' + (c.status === 'verified' ? 'ok' : 'mod')}>
                      {c.status}</span></td>
                    <td style={{ textAlign: 'right' }}>
                      {c.status !== 'verified' && (
                        <button className="oc-btn" onClick={() => setOpen(c)}>Verify</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {open && <VerifySheet claim={open} me={me}
                            onClose={() => setOpen(null)}
                            onDone={() => { setOpen(null); load() }} />}
    </>
  )
}

function VerifySheet({ claim, me, onClose, onDone }) {
  const [source, setSource] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      await api.adminVerifyClaim(claim.id, { source, source_url: url || undefined })
      onDone()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const reject = async () => {
    setBusy(true); setErr(null)
    try {
      await api.adminClaimStatus(claim.id, { status: 'rejected', note: source || 'not in the label' })
      onDone()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <div className="oc-modal" role="dialog" aria-modal="true">
      <div className="oc-modal__box">
        <h3>{claim.product}</h3>
        <p className="small muted">
          {claim.crop} · {claim.target} · {claim.dose_text || 'no dose recorded'}
          {claim.phi_days != null && ` · PHI ${claim.phi_days} days`}
        </p>

        {err && <ErrorNote error={err} />}

        <label className="field" style={{ marginTop: 14 }}>
          <span className="lbl">Citation — where you checked this</span>
          <input className="oc-input" value={source} autoFocus
                 onChange={e => setSource(e.target.value)}
                 placeholder="e.g. CIB&RC Major Uses of Pesticides, Jan 2026, p.114" />
        </label>
        <label className="field">
          <span className="lbl">Link (optional)</span>
          <input className="oc-input" value={url} onChange={e => setUrl(e.target.value)}
                 placeholder="https://…" />
        </label>

        <p className="tiny muted" style={{ lineHeight: 1.55 }}>
          This will be recorded as verified by <b>{me?.user?.full_name}</b>. After this,
          PRAHARI may name {claim.product} to a farmer growing {claim.crop} for {claim.target}
          — still subject to the state restriction list, resistance rotation and the
          pre-harvest interval.
        </p>

        <div className="oc-modal__foot">
          <button className="oc-btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="oc-btn ghost" onClick={reject} disabled={busy}>Reject</button>
          <button className="oc-btn" onClick={submit}
                  disabled={busy || source.trim().length < 8}>
            {busy ? '…' : 'Verify'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── staff and scope ─────────────────────────────────────────────────────── */
function Staff() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [adding, setAdding] = useState(false)

  const load = () => { setD(null); api.adminStaff().then(setD).catch(setErr) }
  useEffect(load, [])

  const grant = async (officerId, taluka) => {
    try { await api.adminGrantScope(officerId, taluka); load() }
    catch (e) { setErr(e) }
  }

  if (err) return <ErrorNote error={err} onRetry={load} />
  if (!d) return <Loading lines={4} />

  return (
    <>
      <div className="oc-head">
        <h2>Staff &amp; scope</h2>
        <button className="oc-btn" onClick={() => setAdding(true)}>＋ Add account</button>
      </div>

      <div className="oc-card">
        <h3>{d.staff.length} accounts that can act on other people&apos;s records</h3>
        <div className="oc-scroll">
          <table className="oc-table">
            <thead><tr><th>Name</th><th>Role</th><th>Email</th><th>Talukas in scope</th>
                       <th>Last sign-in</th><th /></tr></thead>
            <tbody>
              {d.staff.map(s => (
                <tr key={s.id}>
                  <td><b>{s.full_name}</b>
                    {s.institution && <div className="tiny muted">{s.institution}</div>}</td>
                  <td><span className="oc-badge mod">{s.role}</span></td>
                  <td className="mono">{s.email || '—'}</td>
                  <td>
                    {s.officer_id
                      ? (s.scopes.length
                          ? s.scopes.join(' · ')
                          : <span className="warn">no scope — this officer sees nothing</span>)
                      : <span className="muted">—</span>}
                  </td>
                  <td className="mono">{(s.last_login_at || '—').slice(0, 10)}</td>
                  <td style={{ textAlign: 'right' }}>
                    {s.officer_id && (
                      <select className="oc-input" defaultValue=""
                              onChange={e => { if (e.target.value) grant(s.officer_id, e.target.value) }}>
                        <option value="">Grant taluka…</option>
                        {d.talukas.filter(t => !s.scopes.includes(t.id))
                          .map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
                      </select>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="tiny muted" style={{ marginTop: 10, lineHeight: 1.55 }}>
          An officer sees only the talukas granted here. Scope is enforced server-side on every
          request, not in this table — removing a row from view would not remove the access.
        </p>
      </div>

      {adding && <AddStaff talukas={d.talukas} onClose={() => setAdding(false)}
                           onDone={() => { setAdding(false); load() }} />}
    </>
  )
}

function AddStaff({ talukas, onClose, onDone }) {
  const [f, setF] = useState({ role: 'officer', taluka: talukas[0]?.id || '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = k => e => setF(x => ({ ...x, [k]: e.target.value }))

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      await api.adminCreateUser({
        full_name: f.full_name, email: f.email, password: f.password,
        role: f.role, taluka: f.taluka,
        institution: f.institution || undefined,
      })
      onDone()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const ready = f.full_name && f.email && (f.password || '').length >= 12

  return (
    <div className="oc-modal" role="dialog" aria-modal="true">
      <div className="oc-modal__box">
        <h3>New staff account</h3>
        {err && <ErrorNote error={err} />}
        <label className="field"><span className="lbl">Full name</span>
          <input className="oc-input" onChange={set('full_name')} autoFocus /></label>
        <label className="field"><span className="lbl">Email</span>
          <input className="oc-input" type="email" onChange={set('email')} /></label>
        <label className="field"><span className="lbl">Temporary password (12+ characters)</span>
          <input className="oc-input" type="password" onChange={set('password')} /></label>
        <div className="oc-grid2">
          <label className="field"><span className="lbl">Role</span>
            <select className="oc-input" value={f.role} onChange={set('role')}>
              <option value="officer">Agriculture officer</option>
              <option value="expert">Expert</option>
              <option value="admin">Administrator</option>
            </select></label>
          <label className="field"><span className="lbl">Base taluka</span>
            <select className="oc-input" value={f.taluka} onChange={set('taluka')}>
              {talukas.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select></label>
        </div>
        {f.role === 'expert' && (
          <label className="field"><span className="lbl">Institution</span>
            <input className="oc-input" onChange={set('institution')}
                   placeholder="e.g. KVK Nashik" /></label>
        )}
        <p className="tiny muted">
          An officer still sees nothing until a taluka is granted on the previous screen.
          The password is temporary — tell them to change it at first sign-in.
        </p>
        <div className="oc-modal__foot">
          <button className="oc-btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="oc-btn" onClick={submit} disabled={!ready || busy}>
            {busy ? '…' : 'Create account'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── audit ───────────────────────────────────────────────────────────────── */
function Audit() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState(null)
  const [action, setAction] = useState('')

  useEffect(() => {
    setRows(null)
    api.adminAudit(action ? { action, limit: 200 } : { limit: 200 })
      .then(r => setRows(r.entries)).catch(setErr)
  }, [action])

  const actions = [...new Set((rows || []).map(r => r.action))].sort()

  return (
    <>
      <div className="oc-head">
        <h2>Audit</h2>
        <input className="oc-input" placeholder="filter by action, e.g. admin.verify_claim"
               value={action} onChange={e => setAction(e.target.value)}
               style={{ minWidth: 280 }} list="oc-actions" />
        <datalist id="oc-actions">
          {actions.map(a => <option key={a} value={a} />)}
        </datalist>
      </div>
      {err && <ErrorNote error={err} />}
      {!rows && <Loading lines={6} />}
      {rows && (
        <div className="oc-card">
          <h3>{rows.length} entries</h3>
          <div className="oc-scroll">
            <table className="oc-table">
              <thead><tr><th>When</th><th>Action</th><th>Entity</th><th>Role</th><th>Detail</th></tr></thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id}>
                    <td className="mono">{(r.at || '').replace('T', ' ').slice(0, 19)}</td>
                    <td><b>{r.action}</b></td>
                    <td className="mono">{r.entity}{r.entity_id ? ` ${r.entity_id}` : ''}</td>
                    <td>{r.role || '—'}</td>
                    <td className="mono tiny">
                      {Object.keys(r.detail || {}).length
                        ? JSON.stringify(r.detail).slice(0, 90)
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tiny muted" style={{ marginTop: 10 }}>
            Rows with no user are deliberate: when an account is deleted its audit entries are
            detached rather than erased, so what the system did stays answerable without
            keeping the person.
          </p>
        </div>
      )}
    </>
  )
}
