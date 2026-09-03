/* PRAHARI · where it is showing up nearby — the taluka hotspot map.

   This screen adds no data. `/api/fields/{id}/nearby` already ran a Getis-Ord
   Gi* over confirmed diagnoses per taluka and already returned every taluka's
   centroid, case count, incidence per 1,000 farms and z score; the response
   was simply dropping the centroid on the way out. So the map is a projection
   of a statistic PRAHARI already publishes on the field screen, drawn instead
   of listed.

   Two decisions worth stating:

   · NO MAPPING LIBRARY. The bundle is gated at 200 kB gzipped and the app is
     offline-first with nothing fetched from a CDN — a tile layer would break
     both, and would be a basemap of roads nobody needs to read a ten-taluka
     district. The plot is an equirectangular projection of ten centroids onto
     an SVG, which is accurate enough at this scale and costs nothing.

   · TALUKA RESOLUTION, NOT FIELD. Every circle sits on a taluka's own
     centroid. No other farmer's field, name or coordinates are on this screen,
     which is the same promise the nearby endpoint already makes.

   Sparse data is the normal state, not an error: a district with two confirmed
   cases has two confirmed cases, and the screen says so rather than drawing a
   heat cloud out of nothing. */
import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Loading, Prov, bi } from '../ui'

const CLASS_COLOR = {
  hot:  { fill: 'var(--bad)',  bg: 'var(--bad-bg)',  line: 'var(--bad-line)' },
  warm: { fill: 'var(--warn)', bg: 'var(--warn-bg)', line: 'var(--warn-line)' },
  none: { fill: 'var(--faint)', bg: 'var(--sunk)',   line: 'var(--rule)' },
  cold: { fill: 'var(--info)', bg: 'var(--info-bg)', line: 'var(--info-line)' },
}
const CLASS_LABEL = {
  hot:  ['Cluster', 'गट'],
  warm: ['Elevated', 'वाढलेले'],
  none: ['No signal', 'संकेत नाही'],
  cold: ['Below average', 'सरासरीखाली'],
}

export default function Hotspots({ lang, plot, go }) {
  const [problem, setProblem] = useState('late_blight')
  const [ref, setRef] = useState(null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)

  /* The problem chips come from the reference tables, not from the risk board,
     so this screen keeps working when weather does not. */
  useEffect(() => { api.reference().then(setRef).catch(() => setRef(null)) }, [])

  const load = () => {
    if (!plot) { setBusy(false); return }
    setBusy(true); setErr(null)
    api.nearby(plot.id, problem)
      .then(setData)
      .catch(e => { setErr(e); setData(null) })
      .finally(() => setBusy(false))
  }
  useEffect(load, [plot?.id, problem])

  const choices = useMemo(() => {
    const pool = { ...(ref?.diseases || {}), ...(ref?.pests || {}) }
    const forCrop = Object.entries(pool)
      .filter(([, p]) => !plot?.crop || (p.crops || []).includes(plot.crop))
      .map(([id, p]) => ({ id, name: p.name, name_mr: p.mr, em: p.em }))
    if (!forCrop.length) return [{ id: 'late_blight', name: 'Late blight', name_mr: 'उशिरा येणारा करपा', em: '🍂' }]
    return forCrop.sort((a, b) => a.name.localeCompare(b.name))
  }, [ref, plot?.crop])

  const rows = data?.nearby_talukas || []
  const mapped = rows.filter(r => r.lat != null && r.lng != null)
  const withCases = rows.filter(r => (r.cases || 0) > 0)

  if (!plot) {
    return (
      <>
        <Bar lang={lang} go={go} />
        <div className="pad stack" style={{ paddingTop: 14 }}>
          <Card><p className="small muted">
            {bi(lang, 'Register a field first — the map is drawn around the taluka your field is in.',
                      'आधी शेत नोंदवा — नकाशा तुमच्या शेताच्या तालुक्याभोवती काढला जातो.')}
          </p></Card>
        </div>
      </>
    )
  }

  return (
    <>
      <Bar lang={lang} go={go} />
      <div className="pad stack" style={{ paddingTop: 14 }}>
        <div className="chips">
          {choices.map(c => (
            <button key={c.id} className="chip" aria-pressed={c.id === problem}
                    onClick={() => setProblem(c.id)}>
              {c.em} {bi(lang, c.name, c.name_mr)}
            </button>
          ))}
        </div>

        {busy && <Loading lines={5} />}
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}

        {!busy && !err && data && (
          <>
            <Card>
              <div className="row between" style={{ marginBottom: 4 }}>
                <div className="card-title">
                  {bi(lang, data.problem_name, data.problem_name_mr)}
                </div>
                <span className="tiny muted">
                  {lang === 'mr' ? `गेले ${data.window_days} दिवस` : `last ${data.window_days} days`}
                </span>
              </div>

              {mapped.length === 0 ? (
                <p className="small muted" style={{ marginTop: 8 }}>
                  {bi(lang,
                    'No taluka centroids were returned, so there is nothing to plot.',
                    'तालुक्यांची ठिकाणे मिळाली नाहीत, त्यामुळे नकाशा काढता येत नाही.')}
                </p>
              ) : (
                <HotMap rows={mapped} me={data.taluka} lang={lang} />
              )}

              <div className="hs-legend">
                {['hot', 'warm', 'none'].map(k => (
                  <span className="hs-legend__i" key={k}>
                    <i style={{ background: CLASS_COLOR[k].fill }} />
                    {bi(lang, CLASS_LABEL[k][0], CLASS_LABEL[k][1])}
                  </span>
                ))}
                <span className="hs-legend__i">
                  <i className="hs-me" />{bi(lang, 'Your taluka', 'तुमचा तालुका')}
                </span>
              </div>
            </Card>

            {withCases.length === 0 ? (
              <Card>
                <p className="small muted">
                  {bi(lang,
                    `No confirmed case of this problem has been recorded anywhere in the district in the last ${data.window_days} days. That is a real reading, not a gap — nothing has been drawn to fill it.`,
                    `गेल्या ${data.window_days} दिवसांत जिल्ह्यात या समस्येची एकही खात्री झालेली नोंद नाही. ही खरी माहिती आहे — रिकामी जागा भरण्यासाठी काहीही काढलेले नाही.`)}
                </p>
              </Card>
            ) : (
              <Card>
                <div className="card-title" style={{ marginBottom: 8 }}>
                  {lang === 'mr' ? 'तालुकानिहाय' : 'By taluka'}
                  <span className="tiny muted" style={{ fontWeight: 600, marginLeft: 6 }}>
                    {lang === 'mr' ? `एकूण ${data.total_cases} नोंदी` : `${data.total_cases} confirmed`}
                  </span>
                </div>
                <ul className="hs-list">
                  {withCases.map(r => (
                    <li key={r.taluka} className={r.taluka === data.taluka ? 'is-me' : ''}>
                      <span className="hs-list__dot"
                            style={{ background: (CLASS_COLOR[r.class] || CLASS_COLOR.none).fill }} />
                      <span className="hs-list__name">
                        {bi(lang, r.name, r.name_mr)}
                        {r.taluka === data.taluka && (
                          <b className="hs-list__me">{lang === 'mr' ? ' · तुमचा' : ' · yours'}</b>
                        )}
                      </span>
                      <span className="hs-list__n">
                        {r.cases}
                        <em>{lang === 'mr' ? 'नोंदी' : 'cases'}</em>
                      </span>
                      <span className="hs-list__rate">
                        {r.incidence_per_1000}
                        <em>{lang === 'mr' ? '/१००० शेते' : '/1000 farms'}</em>
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {data.assessment?.summary && (
              <Card>
                <div className="card-title" style={{ marginBottom: 6 }}>
                  {lang === 'mr' ? 'याचा अर्थ' : 'What this means'}
                </div>
                <p className="small">{data.assessment.summary}</p>
              </Card>
            )}

            <Prov label={bi(lang, 'Method', 'पद्धत')}
                  value={bi(lang,
                    'Getis-Ord Gi* on confirmed diagnoses per 1,000 farms, over talukas within the neighbour band. A circle sits on the taluka centroid.',
                    'खात्री झालेल्या निदानांवर Getis-Ord Gi* — दर १००० शेतांमागे. वर्तुळ तालुक्याच्या मध्यबिंदूवर आहे.')} />
            <p className="tiny faint" style={{ lineHeight: 1.5 }}>
              {bi(lang, data.privacy, data.privacy_mr)}
            </p>
          </>
        )}
      </div>
    </>
  )
}

function Bar({ lang, go }) {
  return (
    <div className="topbar">
      <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
      <h1 className="grow">{lang === 'mr' ? 'आजूबाजूचा प्रादुर्भाव' : 'Nearby hotspots'}</h1>
    </div>
  )
}

/* ── the plot ──────────────────────────────────────────────────────────────
   An equirectangular projection of taluka centroids into a fixed viewBox, with
   longitude scaled by cos(latitude) so the district is not stretched sideways.
   At the scale of one district this is indistinguishable from a projected map
   and needs no library, no tiles and no network. */
function HotMap({ rows, me, lang }) {
  const W = 320, H = 240, PAD = 26

  const geom = useMemo(() => {
    const lats = rows.map(r => r.lat), lngs = rows.map(r => r.lng)
    const midLat = (Math.min(...lats) + Math.max(...lats)) / 2
    const k = Math.cos((midLat * Math.PI) / 180) || 1
    const xs = rows.map(r => r.lng * k)
    const x0 = Math.min(...xs), x1 = Math.max(...xs)
    const y0 = Math.min(...lats), y1 = Math.max(...lats)
    const sx = (x1 - x0) || 1, sy = (y1 - y0) || 1
    const maxCases = Math.max(1, ...rows.map(r => r.cases || 0))
    return rows.map((r, i) => ({
      ...r,
      x: PAD + ((xs[i] - x0) / sx) * (W - PAD * 2),
      // North at the top: latitude increases upward, y increases downward.
      y: PAD + (1 - (r.lat - y0) / sy) * (H - PAD * 2),
      // Area, not radius, carries the count — a radius scale exaggerates.
      r: 7 + 15 * Math.sqrt((r.cases || 0) / maxCases),
    }))
  }, [rows])

  return (
    <div className="hs-map">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={lang === 'mr'
             ? 'तालुकानिहाय प्रादुर्भावाचा नकाशा'
             : 'Map of confirmed cases by taluka'}>
        {geom.map(g => (
          <g key={g.taluka}>
            {(g.cases || 0) > 0 && (
              <circle cx={g.x} cy={g.y} r={g.r} opacity=".22"
                      fill={(CLASS_COLOR[g.class] || CLASS_COLOR.none).fill} />
            )}
            <circle cx={g.x} cy={g.y} r={g.taluka === me ? 6.5 : 4.5}
                    fill={(CLASS_COLOR[g.class] || CLASS_COLOR.none).fill}
                    stroke={g.taluka === me ? 'var(--g-900)' : 'var(--card)'}
                    strokeWidth={g.taluka === me ? 2.5 : 1.2} />
            <text x={g.x} y={g.y - (g.cases > 0 ? g.r : 8) - 4} textAnchor="middle"
                  className="hs-map__lbl">
              {bi(lang, g.name, g.name_mr)}
            </text>
            {(g.cases || 0) > 0 && (
              <text x={g.x} y={g.y + 3.5} textAnchor="middle" className="hs-map__n">
                {g.cases}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  )
}
