/* PRAHARI · the expert verification portal.

   The expert sees everything the model saw, and everything it could not: the
   images, the crop and its stage, the weather at that field, the ranked
   differential with its supporting and contradicting evidence, the taluka
   prior, the field's history and the farmer's answers to contextual questions.

   What they do NOT see is the farmer's phone number. An expert verifies a
   photograph; they do not need to ring anyone. */
import React, { useEffect, useState } from 'react'
import { api, auth } from '../api'
import { Card, Donut, Empty, ErrorNote, Loading, Prov, Shield } from '../ui'

export default function Expert({ me }) {
  const [cases, setCases] = useState(null)
  const [openCase, setOpenCase] = useState(null)
  const [err, setErr] = useState(null)
  const [tab, setTab] = useState('queue')

  const load = () => { setErr(null); api.expertCases().then(r => setCases(r.cases)).catch(setErr) }
  useEffect(load, [])

  return (
    <div className="oc">
      <aside className="oc-side">
        <div className="oc-brand">
          <Shield size={22} tone="#157A3C" leaf="#8BD3A4" />
          <span className="nm">PRAHARI</span>
        </div>
        <nav className="oc-nav">
          <button aria-current={tab === 'queue' ? 'page' : undefined} onClick={() => setTab('queue')}>
            <span>☰</span><span>Verification queue</span>
          </button>
          <button aria-current={tab === 'agreement' ? 'page' : undefined} onClick={() => setTab('agreement')}>
            <span>◐</span><span>Model monitoring</span>
          </button>
        </nav>
        <div style={{ marginTop: 22, padding: '0 12px' }}>
          <div style={{ fontSize: 11, color: 'var(--d-muted)' }}>Signed in as</div>
          <div style={{ fontSize: 13, fontWeight: 700, marginTop: 3 }}>{me?.user?.full_name}</div>
          <div style={{ fontSize: 11, color: 'var(--d-muted)' }}>{me?.profile?.institution}</div>
          <button className="oc-btn ghost" style={{ marginTop: 12, width: '100%' }}
                  onClick={async () => { try { await api.logout() } catch {} auth.clear() }}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="oc-main">
        <div className="oc-head">
          <h1 style={{ fontFamily: 'var(--display)', fontSize: 20, fontWeight: 800 }}>
            {tab === 'queue' ? 'Verification queue' : 'Model monitoring'}
          </h1>
        </div>

        {err && <ErrorNote error={err} onRetry={load} />}

        {tab === 'agreement' && <Agreement />}

        {tab === 'queue' && (
          <>
            {!cases && !err && <Loading lines={3} />}
            {cases?.length === 0 && (
              <div className="oc-card">
                <p style={{ fontSize: 13, color: 'var(--d-muted)' }}>
                  No cases waiting. A case reaches you when the model abstains for a reason
                  questions cannot settle, when a field is worse after treatment, or when a farmer
                  asks for a person.
                </p>
              </div>
            )}
            {cases?.length > 0 && (
              <div className="oc-card">
                <table className="oc-table">
                  <thead>
                    <tr><th>Case</th><th>Crop</th><th>Taluka</th><th>Model said</th>
                      <th>Reason</th><th>Urgency</th><th /></tr>
                  </thead>
                  <tbody>
                    {cases.map(c => (
                      <tr key={c.id}>
                        <td className="mono">{c.id}</td>
                        <td style={{ textTransform: 'capitalize' }}>{c.crop}</td>
                        <td>{c.taluka_name}</td>
                        <td>
                          {c.abstained
                            ? <span className="oc-badge mod">abstained</span>
                            : <>{c.top_problem_name} <span style={{ color: 'var(--d-muted)' }}>
                                {c.top_posterior ? `${Math.round(c.top_posterior * 100)}%` : ''}</span></>}
                        </td>
                        <td style={{ color: 'var(--d-muted)', maxWidth: 300 }}>
                          {c.abstain_reason || c.reason}
                        </td>
                        <td>
                          <span className={`oc-badge ${c.urgency === 'urgent' ? 'high' : 'new'}`}>
                            {c.urgency}
                          </span>
                        </td>
                        <td><button className="oc-btn" onClick={() => setOpenCase(c.id)}>Review</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </main>

      {openCase && <CaseDetail id={openCase} onClose={() => setOpenCase(null)}
                               onDone={() => { setOpenCase(null); load() }} />}
    </div>
  )
}

/* ── one case ──────────────────────────────────────────────────────────── */
function CaseDetail({ id, onClose, onDone }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [f, setF] = useState({ action: 'confirm', confidence: 'moderate', note: '' })
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState(null)

  useEffect(() => {
    api.expertCase(id).then(x => {
      setD(x)
      setF(v => ({ ...v, verdict: x.diagnosis?.top_problem || x.candidate_problems?.[0]?.id }))
    }).catch(setErr)
  }, [id])

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      const res = await api.expertReview(id, {
        action: f.action,
        verdict: ['confirm', 'change'].includes(f.action) ? f.verdict : undefined,
        confidence: f.confidence, note: f.note || undefined,
      })
      setOut(res)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <div className="scrim" style={{ alignItems: 'center', overflowY: 'auto', padding: 20 }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--d-card)', border: '1px solid var(--d-rule)', borderRadius: 16,
        maxWidth: 1000, width: '100%', color: 'var(--d-ink)', maxHeight: '92dvh', overflowY: 'auto',
      }}>
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--d-rule)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12,
          position: 'sticky', top: 0, background: 'var(--d-card)', zIndex: 2,
        }}>
          <div>
            <div style={{ fontFamily: 'var(--display)', fontWeight: 800, fontSize: 16 }}>Case {id}</div>
            {d && <div style={{ fontSize: 11.5, color: 'var(--d-muted)' }}>
              {d.plot?.crop} · {d.case?.taluka} · submitted {String(d.case?.submitted_at).slice(0, 10)}
            </div>}
          </div>
          <button className="oc-btn ghost" onClick={onClose}>Close</button>
        </div>

        <div style={{ padding: 20 }}>
          {err && <ErrorNote error={err} />}
          {!d && !err && <Loading lines={3} />}

          {out && (
            <div className="oc-card" style={{ marginBottom: 16, borderColor: 'var(--g-600)' }}>
              <h3>Recorded</h3>
              <p style={{ fontSize: 13 }}>
                Case is now <b>{out.status}</b>
                {out.verdict && <> · verdict <b>{out.verdict.replace(/_/g, ' ')}</b></>}
                {out.corrected_the_model === true && <> · <span className="oc-badge mod">the model was wrong</span></>}
                {out.corrected_the_model === false && <> · <span className="oc-badge low">the model agreed</span></>}
              </p>
              <p style={{ fontSize: 12, color: 'var(--d-muted)', marginTop: 8, lineHeight: 1.55 }}>
                {out.learning_note}
              </p>
              <p style={{ fontSize: 12, color: 'var(--d-muted)', marginTop: 6, lineHeight: 1.55 }}>
                {out.dataset_note}
              </p>
              <button className="oc-btn" style={{ marginTop: 12 }} onClick={onDone}>Back to the queue</button>
            </div>
          )}

          {d && !out && (
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.15fr) minmax(0,1fr)', gap: 16 }}>
              {/* left: what the model saw */}
              <div>
                <div className="oc-card" style={{ marginBottom: 14 }}>
                  <h3>The photograph</h3>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {d.images.map((im, i) => (
                      <a key={i} href={im.url} target="_blank" rel="noreferrer">
                        <img src={im.url} alt={im.role} style={{
                          width: 180, height: 180, objectFit: 'cover', borderRadius: 10,
                          border: '1px solid var(--d-rule)',
                        }} />
                      </a>
                    ))}
                  </div>
                  {d.images[0]?.features && (
                    <table className="oc-table" style={{ marginTop: 12 }}>
                      <tbody>
                        {['necrosis', 'chlorosis', 'powder', 'dark', 'healthy_fraction', 'lesions', 'edge', 'leaf_fraction']
                          .filter(k => d.images[0].features[k] != null)
                          .map(k => (
                            <tr key={k}>
                              <td style={{ color: 'var(--d-muted)', textTransform: 'capitalize' }}>
                                {k.replace(/_/g, ' ')}
                              </td>
                              <td className="mono" style={{ textAlign: 'right' }}>
                                {typeof d.images[0].features[k] === 'number'
                                  ? d.images[0].features[k].toFixed(3)
                                  : String(d.images[0].features[k])}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  )}
                  <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10 }}>
                    These are the measurements the ranking was built from. An agronomist can argue
                    with every one of them — that is the point of showing them.
                  </p>
                </div>

                <div className="oc-card" style={{ marginBottom: 14 }}>
                  <h3>What PRAHARI proposed</h3>
                  {d.diagnosis?.abstained
                    ? <div className="oc-badge mod" style={{ marginBottom: 10, display: 'inline-block' }}>
                        abstained — {d.diagnosis.abstain_reason}
                      </div>
                    : null}
                  {d.diagnosis?.explain && (
                    <p style={{ fontSize: 12.5, color: 'var(--d-muted)', marginBottom: 12, lineHeight: 1.55 }}>
                      {d.diagnosis.explain}
                    </p>
                  )}
                  <table className="oc-table">
                    <thead><tr><th>#</th><th>Candidate</th><th>Posterior</th><th>Prior</th><th>Image fit</th><th>Weather</th></tr></thead>
                    <tbody>
                      {d.differential.map(c => (
                        <tr key={c.problem}>
                          <td>{c.rank}</td>
                          <td>{c.problem_name}</td>
                          <td className="mono">{(c.posterior * 100).toFixed(0)}%</td>
                          <td className="mono">{c.prior != null ? (c.prior * 100).toFixed(0) + '%' : '—'}</td>
                          <td className="mono">{c.image_fit != null ? c.image_fit.toFixed(3) : '—'}</td>
                          <td className="mono">{c.weather_factor != null ? c.weather_factor.toFixed(2) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 8 }}>
                    Engine: <b>{d.diagnosis?.engine}</b> · model version <b>{d.diagnosis?.model_version}</b>
                  </p>
                </div>

                {d.farmer_answers?.length > 0 && (
                  <div className="oc-card" style={{ marginBottom: 14 }}>
                    <h3>What the farmer answered</h3>
                    {d.farmer_answers.map((a, i) => (
                      <div key={i} style={{ fontSize: 12.5, padding: '6px 0', borderBottom: '1px solid var(--d-rule)' }}>
                        <div style={{ color: 'var(--d-muted)' }}>{a.question}</div>
                        <b>{a.answer_label}</b>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* right: context and the decision */}
              <div>
                <div className="oc-card" style={{ marginBottom: 14 }}>
                  <h3>Context</h3>
                  <table className="oc-table">
                    <tbody>
                      <tr><td style={{ color: 'var(--d-muted)' }}>Crop</td><td style={{ textTransform: 'capitalize' }}>{d.plot?.crop}</td></tr>
                      <tr><td style={{ color: 'var(--d-muted)' }}>Stage</td><td>{d.crop_stage?.label} (day {d.crop_stage?.days})</td></tr>
                      <tr><td style={{ color: 'var(--d-muted)' }}>Area</td><td>{d.plot?.area_acre} acres</td></tr>
                      <tr><td style={{ color: 'var(--d-muted)' }}>Taluka</td><td>{d.case?.taluka}</td></tr>
                      <tr><td style={{ color: 'var(--d-muted)' }}>Reason it reached you</td><td>{d.case?.reason}</td></tr>
                    </tbody>
                  </table>
                </div>

                {d.weather && !d.weather.unavailable && (
                  <div className="oc-card" style={{ marginBottom: 14 }}>
                    <h3>Weather at this field · {d.weather.source}</h3>
                    <table className="oc-table">
                      <thead><tr><th>Date</th><th>Tmin</th><th>Tmax</th><th>RH≥90 h</th><th>Rain</th></tr></thead>
                      <tbody>
                        {d.weather.days.slice(-6).map(w => (
                          <tr key={w.date}>
                            <td>{w.date}</td>
                            <td className="mono">{w.tmin}</td>
                            <td className="mono">{w.tmax}</td>
                            <td className="mono">{w.rh90_hours}</td>
                            <td className="mono">{w.rain_mm}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {d.prior?.p && (
                  <div className="oc-card" style={{ marginBottom: 14 }}>
                    <h3>Taluka prior — {d.prior.confirmed_cases ?? 0} confirmed cases</h3>
                    {Object.entries(d.prior.p).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, v]) => (
                      <div key={k} className="row between" style={{ fontSize: 12.5, padding: '4px 0' }}>
                        <span style={{ textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</span>
                        <b className="mono">{(v * 100).toFixed(0)}%</b>
                      </div>
                    ))}
                    <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 8 }}>{d.prior.note}</p>
                  </div>
                )}

                {d.field_history?.length > 0 && (
                  <div className="oc-card" style={{ marginBottom: 14 }}>
                    <h3>This field's history</h3>
                    {d.field_history.slice(0, 8).map((e, i) => (
                      <div key={i} style={{ fontSize: 12, padding: '5px 0', borderBottom: '1px solid var(--d-rule)' }}>
                        <span style={{ color: 'var(--d-muted)' }}>{e.at}</span> — {e.title}
                      </div>
                    ))}
                  </div>
                )}

                <div className="oc-card" style={{ borderColor: 'var(--g-600)' }}>
                  <h3>Your decision</h3>
                  <label style={{ display: 'block', marginBottom: 10 }}>
                    <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginBottom: 4 }}>Action</div>
                    <select className="oc-input" style={{ width: '100%' }} value={f.action}
                            onChange={e => setF(x => ({ ...x, action: e.target.value }))}>
                      <option value="confirm">Confirm the model's diagnosis</option>
                      <option value="change">Change the diagnosis</option>
                      <option value="reject">Reject — no problem identifiable</option>
                      <option value="request_info">Request more information</option>
                      <option value="field_visit">Recommend a field visit</option>
                      <option value="mark_urgent">Mark urgent</option>
                    </select>
                  </label>

                  {['confirm', 'change'].includes(f.action) && (
                    <>
                      <label style={{ display: 'block', marginBottom: 10 }}>
                        <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginBottom: 4 }}>Verdict</div>
                        <select className="oc-input" style={{ width: '100%' }} value={f.verdict || ''}
                                onChange={e => setF(x => ({ ...x, verdict: e.target.value }))}>
                          {d.candidate_problems.map(p => (
                            <option key={p.id} value={p.id}>{p.name}{p.sci ? ` (${p.sci})` : ''}</option>
                          ))}
                        </select>
                      </label>
                      <label style={{ display: 'block', marginBottom: 10 }}>
                        <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginBottom: 4 }}>Your confidence</div>
                        <select className="oc-input" style={{ width: '100%' }} value={f.confidence}
                                onChange={e => setF(x => ({ ...x, confidence: e.target.value }))}>
                          <option value="high">High</option>
                          <option value="moderate">Moderate</option>
                          <option value="low">Low</option>
                        </select>
                      </label>
                    </>
                  )}

                  <label style={{ display: 'block', marginBottom: 12 }}>
                    <div style={{ fontSize: 11.5, color: 'var(--d-muted)', marginBottom: 4 }}>
                      Note to the farmer
                    </div>
                    <textarea className="oc-input" style={{ width: '100%', minHeight: 84 }} value={f.note}
                              onChange={e => setF(x => ({ ...x, note: e.target.value }))}
                              placeholder="What you saw, and what they should do." />
                  </label>

                  <button className="oc-btn" style={{ width: '100%' }} disabled={busy} onClick={submit}>
                    {busy ? '…' : 'Record decision'}
                  </button>
                  <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10, lineHeight: 1.55 }}>
                    A confirm or change adds exactly 1 to α for that problem in this taluka. It does
                    not retrain any model — confirmations accumulate into a reviewed dataset, and
                    retraining is a separate, versioned, evaluated act.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── model monitoring ──────────────────────────────────────────────────── */
function Agreement() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { api.modelAgreement().then(setD).catch(setErr) }, [])
  if (err) return <ErrorNote error={err} />
  if (!d) return <Loading lines={3} />

  return (
    <>
      <div className="oc-kpis">
        {[['Diagnoses', d.diagnoses_total], ['Abstentions', d.abstentions],
          ['Expert-reviewed', d.expert_reviewed], ['Agreed', d.agreed]].map(([l, v]) => (
          <div className="oc-kpi" key={l}><div className="lbl">{l}</div><div className="val">{v ?? 0}</div></div>
        ))}
      </div>

      <div className="oc-grid">
        <div className="oc-card">
          <h3>Agreement rate</h3>
          {d.agreement_rate != null ? (
            <div className="val" style={{ fontFamily: 'var(--display)', fontSize: 40, fontWeight: 800 }}>
              {Math.round(d.agreement_rate * 100)}%
            </div>
          ) : (
            <div className="oc-badge mod" style={{ display: 'inline-block' }}>Not enough data</div>
          )}
          <p style={{ fontSize: 12, color: 'var(--d-muted)', marginTop: 10, lineHeight: 1.55 }}>
            {d.agreement_rate_note || 'Computed from stored diagnoses with stored expert verdicts.'}
          </p>
          <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10, lineHeight: 1.55 }}>
            {d.method}
          </p>
        </div>

        <div className="oc-card">
          <h3>Why the model declined</h3>
          {d.abstention_reasons?.length
            ? <Donut data={d.abstention_reasons.map(r => ({
                label: (r.abstain_reason || 'unknown').replace(/-/g, ' '), value: r.n,
              }))} />
            : <p style={{ fontSize: 12.5, color: 'var(--d-muted)' }}>No abstentions recorded yet.</p>}
          <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 12, lineHeight: 1.55 }}>
            An abstention rate is a feature, not a fault. A system that answers 70% of cases well
            beats one that answers all of them badly.
          </p>
        </div>
      </div>

      {d.confusion?.length > 0 && (
        <div className="oc-card" style={{ marginTop: 14 }}>
          <h3>Where the model and the expert disagree</h3>
          <table className="oc-table">
            <thead><tr><th>Model said</th><th>Expert found</th><th>Cases</th><th /></tr></thead>
            <tbody>
              {d.confusion.map((c, i) => (
                <tr key={i}>
                  <td>{c.predicted_name}</td>
                  <td>{c.actual_name}</td>
                  <td className="mono">{c.n}</td>
                  <td>
                    {c.top_problem === c.confirmed
                      ? <span className="oc-badge low">agreed</span>
                      : <span className="oc-badge high">corrected</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11, color: 'var(--d-muted)', marginTop: 10 }}>
            These rows are the most valuable training data PRAHARI has: cases where a human
            corrected the model, with the photograph and the field context attached.
          </p>
        </div>
      )}
    </>
  )
}
