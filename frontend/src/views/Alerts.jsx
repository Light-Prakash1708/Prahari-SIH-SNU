import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Why, Chip, Loading, ErrorNote, Empty, t, L } from '../ui'

/* ═══ ALERTS ══════════════════════════════════════════════════════════════
   Three things live here, and they are three different kinds of message:

     · warnings the system pushed         — forecast, threshold, escalation
     · cases waiting on a human           — the expert pipeline
     · re-checks the farmer owes the field — follow-ups due

   The pipeline is the part most apps do not have. When the model declines,
   something must happen next, and "submitted → reviewing → verified" is that
   something made visible so an abstention reads as a handover rather than a
   dead end.
                                                                            */
const ICON = {
  forecast: '🌧️', risk: '🌧️', threshold: '🪤', count: '🪤', expert: '📨',
  spray: '🧪', apply: '🧪', officer: '🧑‍🌾', followup: '🔁', scan: '📷',
}

export function Alerts({ plot, lang, go }) {
  const [n, setN] = useState(null)
  const [cases, setCases] = useState(null)
  const [due, setDue] = useState(null)
  const [err, setErr] = useState(null)

  const load = () => {
    setErr(null)
    api.notifications(plot.id).then(setN).catch(setErr)
    api.expertCases(plot.id).then(r => setCases(r.cases)).catch(() => setCases([]))
    api.followups().then(r => setDue((r.followups || []).filter(f => f.plot_id === plot.id)))
      .catch(() => setDue([]))
  }
  useEffect(() => { load() }, [plot.id])

  // Opening this screen is the read receipt. Mark once, then let the badge clear.
  useEffect(() => {
    if (n && n.unread) api.markRead(plot.id).catch(() => {})
  }, [n, plot.id])

  if (err) return <ErrorNote error={err} retry={load} />
  if (!n) return <Loading what="Checking for alerts" />

  return (
    <>
      {/* ── follow-ups owed ─────────────────────────────────────────── */}
      {due?.length > 0 && (
        <Card title={`🔁 ${t(lang, 'reReckDue')}`}
              right={<Chip level={due.some(f => f.overdue) ? 'high' : 'watch'}>{due.length}</Chip>}>
          {due.map(f => (
            <div className="chg" key={f.id}>
              <span className="l">
                {f.plot_name} · {f.crop}
                <span className="tiny" style={{ display: 'block', color: 'var(--muted)' }}>
                  due {f.due_on}
                </span>
              </span>
              <span className={`v ${f.overdue ? 't-high' : ''}`}>
                {f.overdue ? `${-f.days_until}d late` : `${f.days_until}d`}
              </span>
            </div>
          ))}
          <button className="btn ghost block mt" onClick={() => go('field')}>
            Open the field record to re-check →
          </button>
          <Why label="Why the app keeps asking">
            <p>
              A recommendation nobody checks is an opinion. The re-check is what turns it into
              evidence — and it is the only measurement in this system that can tell an officer
              whether the advisory worked, without funding a trial.
            </p>
          </Why>
        </Card>
      )}

      {/* ── expert pipeline ─────────────────────────────────────────── */}
      {cases?.length > 0 && (
        <Card title={t(lang, 'casesWithExpert')}
              right={<Chip level="flat">{cases.length}</Chip>}>
          {cases.map(c => <CaseRow key={c.id} c={c} />)}
          <Why label="What happens to a case">
            <p>
              A case is created when the model declines, or when a follow-up shows the problem got
              worse after treatment. It goes to the block extension officer with the photograph and
              the measured features attached — not with a guess.
            </p>
            <p>
              When the officer confirms it, one integer moves: the Dirichlet count for that disease
              in this taluka goes up by exactly one, which raises the model's sensitivity to it here
              for everyone. That is the entire learning mechanism — no retraining, and auditable by
              counting rows.
            </p>
          </Why>
        </Card>
      )}

      {/* ── the feed ────────────────────────────────────────────────── */}
      <Card title={t(lang, 'alerts')}
            right={n.unread ? <Chip level="high">{n.unread} new</Chip> : null}>
        {n.notifications.length === 0 ? (
          <Empty icon="🔔" title="Nothing needs your attention"
                 body="PRAHARI sends a message when a model fires, a threshold is crossed, or an officer responds — and stays quiet otherwise. An app that pings you daily gets muted by week two." />
        ) : n.notifications.map(a => (
          <div className={`alert ${a.read ? '' : 'unread'}`} key={a.id}>
            <span className="ic">{ICON[a.kind] || '•'}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="t">{L(lang, a, 'title')}</div>
              <div className="b">{L(lang, a, 'body')}</div>
              <div className="w">{a.at} · {a.kind}</div>
            </div>
            <Chip level={a.severity === 'info' ? 'flat' : a.severity === 'low' ? 'safe' : a.severity}>
              {a.severity}
            </Chip>
          </div>
        ))}
        <p className="note mt">
          Every message here was produced by a model firing or a person acting. Nothing is sent on a
          schedule, and there is no engagement loop — a farmer who hears from PRAHARI knows it means
          something.
        </p>
      </Card>
    </>
  )
}

function CaseRow({ c }) {
  const rejected = c.status === 'rejected'
  return (
    <div style={{ padding: '12px 0', borderBottom: '1px solid var(--rule-soft)' }}>
      <div className="row">
        <span className="mono" style={{ fontWeight: 800, fontSize: '.82rem' }}>{c.id}</span>
        <span style={{ flex: 1 }} />
        <Chip level={c.status === 'verified' ? 'safe' : rejected ? 'high' : 'watch'}>
          {c.status}
        </Chip>
      </div>
      <div className="small" style={{ color: 'var(--slate)', marginTop: 2 }}>
        {c.plot_name} · {c.crop} — {c.reason}
      </div>

      <div className="pipe">
        {c.stages.map((s, i) => (
          <div className={`s ${i < c.stage_index ? 'done' : i === c.stage_index ? 'now' : ''}`} key={s}>
            <div className="k">{i < c.stage_index ? '✓' : i + 1}</div>
            <div className="n">{rejected && i === 2 ? 'closed' : s}</div>
          </div>
        ))}
      </div>

      {c.verdict && (
        <div className="note" style={{ marginTop: 6 }}>
          <b>{c.expert || 'Extension officer'}:</b> {c.verdict}
          {c.note && <> — {c.note}</>}
        </div>
      )}
      {!c.verdict && c.suspected && (
        <p className="tiny" style={{ color: 'var(--muted)' }}>
          Suspected {c.suspected.replace(/_/g, ' ')}
          {c.posterior != null && <> · model confidence {Math.round(c.posterior * 100)}%</>}
          {c.abstained ? ' · the model declined to commit to this' : ''}
        </p>
      )}
    </div>
  )
}
