/* PRAHARI · the producer-organisation console.

   For an FPO coordinator. Every number on this page is a COUNT across members
   who chose to join — the server never sends a member's name, phone, village,
   location or field, and any count below three arrives as "fewer than 3".
   This screen renders what it is given and does not try to work back from it.

   Same dark console shell as the officer product, because it is staff-facing
   and desktop-first; a different set of questions. */
import React, { useEffect, useState } from 'react'
import Outcomes from './Outcomes'
import { api, auth } from '../api'
import { ErrorNote, Loading } from '../ui'

const BAND_LABEL = { safe: 'Safe', watch: 'Watch', rising: 'Rising', high: 'High risk' }
const GRADE_LABEL = {
  emerging_cluster: 'Emerging cluster',
  suspected_hotspot: 'Suspected hotspot',
  confirmed_hotspot: 'Confirmed hotspot',
}

const Count = ({ c }) => (
  <b title={c?.suppressed ? 'Hidden so a small group does not identify a member' : undefined}>
    {c ? c.label : '—'}
  </b>
)

export default function Fpo({ me }) {
  const [fpos, setFpos] = useState(null)
  const [pick, setPick] = useState(null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.fpoMine().then(r => {
      setFpos(r.fpos || [])
      if (r.fpos?.length) setPick(r.fpos[0].id)
    }).catch(setErr)
  }, [])
  const load = () => {
    if (!pick) return
    setErr(null); setData(null)
    api.fpoSummary(pick).then(setData).catch(setErr)
  }
  useEffect(load, [pick])

  return (
    <div className="oc">
      <aside className="oc-side">
        <div className="oc-brand">
          <img src="/brand/logo.png" alt="PRAHARI" width="112" height="37" />
        </div>
        <nav className="oc-nav">
          {(fpos || []).map(f => (
            <button key={f.id} aria-current={pick === f.id ? 'page' : undefined}
                    onClick={() => setPick(f.id)}>
              <span>◎</span><span>{f.name}</span>
            </button>
          ))}
        </nav>
        <div style={{ marginTop: 22, padding: '0 12px' }}>
          <div style={{ fontSize: 11, color: 'var(--d-muted)' }}>Signed in as</div>
          <div style={{ fontSize: 13, fontWeight: 700, marginTop: 3 }}>{me?.user?.full_name}</div>
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
              {data?.fpo?.name || 'Producer organisation'}
            </h1>
            <div style={{ fontSize: 12, color: 'var(--d-muted)', marginTop: 3 }}>
              Counts across members who chose to join
            </div>
          </div>
        </div>

        {err && <ErrorNote error={err} onRetry={load} />}
        {fpos && fpos.length === 0 && (
          <section className="oc-card">
            <p className="small">This account is not linked to a producer organisation yet.
              An administrator links it from the admin console.</p>
          </section>
        )}
        {pick && !data && !err && <Loading lines={4} />}

        {data && (
          <>
            <div className="oc-kpis">
              {[['Members', data.members, 'farmers who joined'],
                ['Fields', data.fields, 'active member fields'],
                ['Open follow-ups', data.followups.open, 're-checks not yet done'],
                ['Overdue', data.followups.overdue, 'past their re-check date']]
                .map(([label, c, sub]) => (
                  <div className="oc-kpi" key={label}>
                    <div className="lbl">{label}</div>
                    <div className="val"><Count c={c} /></div>
                    <div className="delta" style={{ color: 'var(--d-muted)', fontWeight: 500 }}>{sub}</div>
                  </div>
                ))}
            </div>

            <section className="oc-card">
              <h3>Field health · latest score of each member field</h3>
              <div className="fpo-grid">
                {data.health.bands.map(b => (
                  <div key={b.band} className={`fpo-cell band-${b.band}`}>
                    <span>{BAND_LABEL[b.band] || b.band}</span><Count c={b} />
                  </div>
                ))}
                <div className="fpo-cell">
                  <span>Not scored</span><Count c={data.health.not_scored} />
                </div>
              </div>
              <p className="tiny muted" style={{ marginTop: 8 }}>{data.health.note}</p>
            </section>

            <section className="oc-card">
              <h3>Crops and talukas</h3>
              {data.crops.length === 0 && <p className="small muted">No member fields yet.</p>}
              <div className="fpo-grid">
                {data.crops.map(c => (
                  <div key={c.crop} className="fpo-cell"><span>{c.name}</span><Count c={c} /></div>
                ))}
              </div>
              <div className="fpo-grid" style={{ marginTop: 8 }}>
                {data.talukas.map(t => (
                  <div key={t.taluka} className="fpo-cell"><span>{t.name}</span><Count c={t} /></div>
                ))}
              </div>
            </section>

            <section className="oc-card">
              <h3>What is spreading in members’ talukas</h3>
              {data.outbreaks.events.length === 0 ? (
                <p className="small muted">No open outbreak event in these talukas.</p>
              ) : data.outbreaks.events.map((e, i) => (
                <div className="oc-sig" key={i}>
                  <div className="row between">
                    <b>{e.problem_name} · {e.taluka_name}</b>
                    <span className="oc-badge mod">{GRADE_LABEL[e.grade] || e.grade}</span>
                  </div>
                  <div className="oc-sig__meta">
                    <span>since {e.opened_on}</span>
                    <span>{e.reports} reports · {e.confirmed} confirmed</span>
                  </div>
                </div>
              ))}
              <p className="tiny muted" style={{ marginTop: 8 }}>{data.outbreaks.note}</p>
            </section>

            <section className="oc-card">
              <h3>After action · follow-up outcomes across members</h3>
              <Outcomes data={data.outcomes} lang="en" />
            </section>

            <p className="tiny muted" style={{ padding: '4px 2px' }}>{data.privacy}</p>
          </>
        )}
      </main>
    </div>
  )
}
