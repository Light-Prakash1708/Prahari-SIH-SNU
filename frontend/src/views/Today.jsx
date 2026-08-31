import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Why, Chip, Dial, Loading, ErrorNote, Stale, t, L, RISK_LABEL, trapLine } from '../ui'

/* ═══ TODAY ═══════════════════════════════════════════════════════════════
   The farmer's home screen, in the order the questions actually arrive:

     how is my field           the health score, with its four terms visible
     what is coming            the four-day forecast — the question no
                               photo-diagnosis app can answer
     should I act              the threshold verdict, which is usually "no"
     what is happening nearby  a count, never a neighbour
                                                                            */
export function Today({ plot, lang, go }) {
  const [d, setD] = useState(null)
  const [near, setNear] = useState(null)
  const [err, setErr] = useState(null)

  const load = () => {
    setD(null); setErr(null)
    api.fieldHealth(plot.id).then(setD).catch(setErr)
    api.nearby(plot.id).then(setNear).catch(() => setNear(null))
  }
  useEffect(() => { load() }, [plot.id])

  if (err) return <ErrorNote error={err} retry={load} />
  if (!d) return <Loading what="Reading your field" />

  const h = d.health
  const fh = d.forecast_headline
  const trap = pickTrap(d.traps, d.today)

  return (
    <>
      {d._stale && <Stale at={d._cachedAt} />}

      {/* ── health hero ─────────────────────────────────────────────── */}
      <section className={`hero ${h.band}`}>
        <div className="hero-top">
          <div className="hero-name">
            <p className="eyebrow">{t(lang, 'yourField')}</p>
            <h1 className="h1">{plot.name}</h1>
            <p className="sub">
              {L(lang, d.crop, 'name') || plot.crop} · {plot.area_acre}{' '}
              {lang === 'mr' ? 'एकर' : 'acre'} ·{' '}
              {L(lang, d.crop_stage, 'label')},{' '}
              {lang === 'mr' ? `${d.crop_stage.days} वा दिवस` : `day ${d.crop_stage.days}`}
            </p>
            <div className={`hero-band t-${h.band}`}>
              <span className={`dot bg-${h.band}`} />
              {lang === 'mr' ? h.band_label_mr : h.band_label}
            </div>
          </div>
          <Dial score={h.score} band={h.band} />
        </div>

        <div className="breakdown">
          {[['disease', t(lang, 'disease')], ['pest', t(lang, 'pest')],
            ['weather', t(lang, 'weather')], ['nearby', t(lang, 'nearby')]].map(([k, label]) => {
            const c = h.components[k]
            return (
              <div className="bd" key={k}>
                <div className="l">{label}</div>
                <div className={`v t-${c.band}`}>
                  {RISK_LABEL[c.band] ? RISK_LABEL[c.band][lang] || RISK_LABEL[c.band].en : c.band}
                </div>
                <div className="bar">
                  <i className={`bg-${c.band}`} style={{ width: `${(c.penalty / c.cap) * 100}%` }} />
                </div>
              </div>
            )
          })}
        </div>

        <Why label="How this score is built">
          <span className="eq">score = 100 − disease − pest − weather − nearby</span>
          <p>{h.method}</p>
          {h.terms.length > 0 ? (
            <>
              <p style={{ marginTop: 10, fontWeight: 700, color: 'var(--ink)' }}>
                What is costing this field points right now
              </p>
              <table className="tbl">
                <tbody>
                  {h.terms.map((x, i) => (
                    <tr key={i}><td>{x.why}</td><td>−{x.cost}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : <p style={{ marginTop: 8 }}>Nothing is costing this field any points today.</p>}
        </Why>
      </section>

      {/* ── what changed ────────────────────────────────────────────── */}
      {!d.changed.first_visit && (d.changed.score_delta !== 0 || d.changed.rows.some(r => r.delta)) && (
        <Card title={t(lang, 'whatChanged')}
              right={<span className="chip flat">{d.changed.days_since}d ago</span>}>
          <p style={{ fontWeight: 700 }}>{L(lang, d.changed, 'headline')}</p>
          {d.changed.reason && <p className="small mt" style={{ color: 'var(--slate)' }}>{d.changed.reason}</p>}
          <div className="mt">
            {d.changed.rows.map(r => (
              <div className="chg" key={r.key}>
                <span className="l">{L(lang, r, 'label')}</span>
                <span className={`v ${r.delta > 0 ? 't-high' : r.delta < 0 ? 't-safe' : ''}`}>
                  {r.delta === 0 ? '—' : `${r.delta > 0 ? '↑' : '↓'} ${Math.abs(r.delta)}`}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ── WHAT IS COMING ──────────────────────────────────────────── */}
      <section className={`coming ${fh.level}`}>
        <p className="eyebrow">⚠️ {t(lang, 'whatsComing')}</p>
        <h2>{L(lang, fh, 'title')}</h2>
        {(lang === 'mr' ? fh.reasons_mr : fh.reasons)?.length > 0 && (
          <ul>{(lang === 'mr' ? fh.reasons_mr : fh.reasons).map((r, i) => <li key={i}>{r}</li>)}</ul>
        )}

        <div className="strip">
          {d.forecast.map(f => (
            <div className={`d ${f.offset === 0 ? 'now' : ''}`} key={f.offset}>
              <div className="day">{f.offset === 0 ? (lang === 'mr' ? 'आज' : 'Today') : f.label}</div>
              <div className={`lvl t-${f.level}`}>{L(lang, f, 'level_label')}</div>
              <div className={`bar bg-${f.level}`} />
            </div>
          ))}
        </div>
        <p className="tiny" style={{ color: 'var(--muted)' }}>{t(lang, 'observedNote')}</p>

        <Why label="Why these days, and not a guess">
          <p>{fh.method}</p>
          <table className="tbl" style={{ marginTop: 8 }}>
            <thead><tr><th>Day</th><th>Min °C</th><th>h RH≥90</th><th>Rain</th><th>Level</th></tr></thead>
            <tbody>
              {d.forecast.map(f => (
                <tr key={f.offset}>
                  <td>{f.offset === 0 ? 'Today' : f.label}</td>
                  <td>{f.tmin}</td><td>{f.rh90_hours}</td><td>{f.rain_mm}</td>
                  <td><b>{f.level_label}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
          {d.forecast.flatMap(f => f.drivers).length > 0 && (
            <p style={{ marginTop: 9 }}>
              <b>{d.forecast.find(f => f.drivers.length)?.drivers[0].model}</b>{' — '}
              {d.forecast.find(f => f.drivers.length)?.drivers[0].detail}
            </p>
          )}
          <p style={{ marginTop: 9 }}>
            Weather source: <b>{d.weather.profile_label || d.weather.source}</b>. {d.weather.note}
          </p>
        </Why>
      </section>

      {/* ── the threshold verdict ───────────────────────────────────── */}
      {trap && <TrapVerdict trap={trap} lang={lang} go={go} plot={plot} />}

      {/* ── nearby ──────────────────────────────────────────────────── */}
      {near && (
        <Card title={`📍 ${t(lang, 'nearbyHealth')}`}
              right={<Chip level={near.band === 'low' ? 'safe' : near.band}>
                {RISK_LABEL[near.band === 'low' ? 'safe' : near.band]?.[lang] ||
                 (near.band === 'low' ? 'Low activity' : near.band)}
              </Chip>}>
          <p className="small">{L(lang, near, 'say')}</p>
          {near.top_problem && (
            <p className="small mt"><b>Most reported nearby:</b> {near.top_problem}</p>
          )}
          <Why label="What is shared, and what is not">
            <p>{L(lang, near, 'privacy')}</p>
            <p>
              Counts below three are suppressed entirely, because in a village of a few dozen farms a
              count of one is a name. The taluka statistic is computed from the same reports but
              aggregated far enough that it cannot be reversed.
            </p>
          </Why>
        </Card>
      )}

      {/* ── PHI gate ────────────────────────────────────────────────── */}
      {d.phi && !d.phi.clear && (
        <Card>
          <div className="row">
            <span style={{ fontSize: '1.5rem' }}>⏳</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700 }}>
                Harvest blocked for {d.phi.days_left} more day{d.phi.days_left === 1 ? '' : 's'}
              </div>
              <p className="small" style={{ color: 'var(--slate)' }}>{L(lang, d.phi, 'msg')}</p>
            </div>
          </div>
        </Card>
      )}

      <div className="row" style={{ marginTop: 4 }}>
        <button className="btn ghost" style={{ flex: 1 }} onClick={() => go('scan')}>
          📷 {t(lang, 'checkLeaf')}
        </button>
        <button className="btn ghost" style={{ flex: 1 }} onClick={() => go('action')}>
          🪤 {t(lang, 'checkTrap')}
        </button>
      </div>
    </>
  )
}

/* The pest worth putting on the home screen.
   Recency first, THEN severity. Ranking on the ratio alone put a ten-day-old
   count of 5 above a count taken this morning, so the headline verdict — the
   loudest thing on the screen — was answering a question about last week. A
   count that is not fresh is not a verdict; the age is printed either way. */
// Five days, because that is the re-count interval this app itself
// recommends after every verdict. A count older than its own advice is not the
// one to build today's headline on.
const FRESH_DAYS = 5
function pickTrap(traps, today) {
  const counted = (traps || []).filter(x => x.count != null)
  if (!counted.length) return null
  const withAge = counted.map(x => ({ ...x, age: ageDays(x.last_checked, today) }))
  const fresh = withAge.filter(x => x.age != null && x.age <= FRESH_DAYS)
  const pool = fresh.length ? fresh : withAge
  return pool.sort((a, b) => (b.count / b.etl) - (a.count / a.etl))[0]
}

function ageDays(d, today) {
  if (!d) return null
  const t = today ? new Date(today) : new Date()
  return Math.round((t - new Date(d)) / 86400000)
}

/* ═══ THE SIGNATURE FEATURE ═══════════════════════════════════════════════
   Below threshold, this screen says DO NOT SPRAY as loudly as most apps say
   BUY THIS. That inversion is the product.                                 */
function TrapVerdict({ trap, lang, go, plot }) {
  const ratio = trap.count / trap.etl
  const over = ratio >= 1
  const pct = Math.min(96, (trap.count / (trap.etl * 3)) * 100)

  return (
    <section className={`verdict ${over ? 'act' : ratio >= 0.5 ? 'soft' : 'hold'}`}>
      <div className="big">
        <span>{over ? '⚠️' : '🟢'}</span>
        <span>{over ? t(lang, 'sprayNow') : t(lang, 'dontSpray')}</span>
      </div>

      <div className="scale">
        <div className="scale-track">
          <div className="scale-etl" />
          <div className="scale-mark" style={{ left: `${pct}%` }} />
          <div className="scale-cur" style={{ left: `${pct}%` }}>{trap.count}</div>
        </div>
        <div className="scale-lab">
          <span className="lo">0</span>
          <span className="etl">threshold {trap.etl}</span>
          <span className="hi">{(trap.etl * 3).toFixed(0)}</span>
        </div>
      </div>

      <p className="why">
        {trapLine(lang, L(lang, trap, 'name') || trap.name, trap.count, trap.etl, trap.unit)}{' '}
        {over ? t(lang, 'sprayJustified') : t(lang, 'monitorFor')}
      </p>

      {trap.age != null && trap.age > 0 && (
        <p className="tiny" style={{ marginTop: 6, color: 'var(--slate)' }}>
          {trap.age === 1
            ? (lang === 'mr' ? 'ही मोजणी कालची आहे.' : 'This count is from yesterday.')
            : (lang === 'mr' ? `ही मोजणी ${trap.age} दिवसांपूर्वीची आहे.`
                             : `This count is ${trap.age} days old.`)}
          {trap.age > FRESH_DAYS &&
            (lang === 'mr' ? ' नवीन मोजणी करा.' : ' Take a fresh one before deciding.')}
        </p>
      )}

      {!over && (
        <div className="saved">{t(lang, 'nextReview')}</div>
      )}

      <button className="btn block mt" onClick={() => go('action')}>
        {over ? t(lang, 'seeOptions') : t(lang, 'recordCount')} →
      </button>

      <Why label="Where this threshold comes from">
        <p>
          <b>{trap.source}</b>. The base figure is {trap.etl_base} {trap.unit}; at{' '}
          {plot.crop}'s current stage it is scaled to {trap.etl}, because the same count means
          different things at different crop stages and a threshold quoted without a stage is
          agronomically meaningless.
        </p>
        <p>
          The growing-degree-day model puts this pest at <b>{trap.stage}</b> today
          {trap.damaging
            ? ' — the stage that causes damage, and the stage a spray can still reach.'
            : ', which a spray would not reach. That is why the count matters more than the calendar.'}
        </p>
        <p>
          Below threshold, a spray costs more than the damage it prevents and removes the natural
          enemies holding the population down. That is not a hedge — it is the finding the whole
          product is built on.
        </p>
      </Why>
    </section>
  )
}
