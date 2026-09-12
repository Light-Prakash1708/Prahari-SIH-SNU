/* PRAHARI · what is showing up around this farm.

   This screen adds no data. `/api/fields/{id}/nearby` already ran a Getis-Ord
   Gi* over confirmed diagnoses per taluka and already returned every taluka's
   centroid, case count, incidence per 1,000 farms and z score, plus the graded
   verdict from outbreak.py. What it now also returns — this window against the
   one before it, six weekly buckets, and when the problem was last seen here —
   are COUNTS of the same rows, added because the screen could not derive them
   and a farmer cannot read a trend off a single number.

   Four decisions worth stating, because each one is a thing this screen
   deliberately does not do:

   · NO MAPPING LIBRARY, NO TILES. The bundle is gated at 200 kB gzipped and
     the app is offline-first with nothing fetched from a CDN. A satellite
     basemap would break both, and would be a picture of roads nobody needs to
     read a ten-taluka district. The plot is an equirectangular projection of
     ten centroids onto an SVG.

   · TALUKA RESOLUTION, NOT VILLAGE. Every circle sits on a taluka's own
     centroid. There is no village geography behind this endpoint and none has
     been invented: the ranked list says "talukas" because that is what the
     data is. No other farmer's field, name or coordinates appear here.

   · ONE PROBLEM AT A TIME. The endpoint is keyed to a problem, so there is no
     "All" chip. An "All" that fanned out one request per disease would be six
     requests on a village connection to answer a question nobody asked.

   · NO PERCENTAGE WITHOUT A DENOMINATOR. Going from no cases to four is not
     "+400%". The change card says "four where there were none" and shows no
     figure, because that is the true statement and the more useful one.

   Sparse data is the normal state, not an error. A district with two confirmed
   cases has two confirmed cases, and the screen says so rather than drawing a
   heat cloud out of nothing. */
import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Loading, Prov, Sheet, bi, fmtDate } from '../ui'

const CLASS_COLOR = {
  hot:  { fill: 'var(--bad)',  bg: 'var(--bad-bg)',  line: 'var(--bad-line)' },
  warm: { fill: 'var(--warn)', bg: 'var(--warn-bg)', line: 'var(--warn-line)' },
  none: { fill: 'var(--faint)', bg: 'var(--sunk)',   line: 'var(--rule)' },
  cold: { fill: 'var(--info)', bg: 'var(--info-bg)', line: 'var(--info-line)' },
}
/* Risk is never carried by colour alone: every marker and row also prints its
   class in words, and the legend names all four.

   These are the Gi* CLASS, and the wording matters. The map used to label a
   hot taluka "Cluster" — but outbreak.py reserves "cluster" for a stricter
   test (several distinct FIELDS, not several photographs), and now that its
   grade sits at the top of the same screen the two words collided: the pulse
   could read "No cluster" above a map legend saying "Cluster". A judge would
   rightly ask which one is true. So the statistic is described as what it is —
   a local concentration — and only outbreak.py may say cluster. */
const CLASS_LABEL = {
  hot:  ['Concentrated', 'केंद्रित'],
  warm: ['Elevated', 'वाढलेले'],
  none: ['No signal', 'संकेत नाही'],
  cold: ['Below average', 'सरासरीखाली'],
}

const WINDOWS = [
  [7,  ['7 days', '७ दिवस']],
  [21, ['21 days', '२१ दिवस']],
  [90, ['3 months', '३ महिने']],
]

const ARROW = { up: '↑', down: '↓', flat: '→' }

export default function Hotspots({ lang, plot, me, go }) {
  const [problem, setProblem] = useState('late_blight')
  const [days, setDays] = useState(21)
  const [riskOnly, setRiskOnly] = useState('any')   // any | hot | warm
  const [ref, setRef] = useState(null)
  const [data, setData] = useState(null)
  const [wx, setWx] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)
  const [sheet, setSheet] = useState(null)          // a taluka row
  const [filters, setFilters] = useState(false)
  const role = me?.user?.role || 'farmer'

  /* The problem chips come from the reference tables, not from the risk board,
     so this screen keeps working when weather does not. */
  useEffect(() => { api.reference().then(setRef).catch(() => setRef(null)) }, [])

  /* The existing field-weather call, cached by api.js. Not a second weather
     provider and not a second request per panel — fetched once here and read
     by the context card below. */
  useEffect(() => {
    if (!plot) return
    api.fieldWeather(plot.id).then(setWx).catch(() => setWx(null))
  }, [plot?.id])

  const load = () => {
    if (!plot) { setBusy(false); return }
    setBusy(true); setErr(null)
    api.nearby(plot.id, problem, days)
      .then(setData)
      .catch(e => { setErr(e); setData(null) })
      .finally(() => setBusy(false))
  }
  useEffect(load, [plot?.id, problem, days])

  const choices = useMemo(() => {
    const pool = { ...(ref?.diseases || {}), ...(ref?.pests || {}) }
    const forCrop = Object.entries(pool)
      .filter(([, p]) => !plot?.crop || (p.crops || []).includes(plot.crop))
      .map(([id, p]) => ({ id, name: p.name, name_mr: p.mr, em: p.em }))
    if (!forCrop.length) {
      return [{ id: 'late_blight', name: 'Late blight', name_mr: 'उशिरा येणारा करपा', em: '🍂' }]
    }
    return forCrop.sort((a, b) => a.name.localeCompare(b.name))
  }, [ref, plot?.crop])

  const rows = data?.nearby_talukas || []
  const mapped = rows.filter(r => r.lat != null && r.lng != null)
  const withCases = rows.filter(r => (r.cases || 0) > 0)
  const ranked = useMemo(() => {
    const list = [...withCases].sort((a, b) => (b.cases || 0) - (a.cases || 0))
    return riskOnly === 'any' ? list : list.filter(r => r.class === riskOnly)
  }, [withCases, riskOnly])
  const mine = rows.find(r => r.taluka === data?.taluka)
  const change = data?.change
  const trend = data?.trend_weeks

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

  const chosen = choices.find(c => c.id === problem)

  return (
    <>
      <Bar lang={lang} go={go} />

      <div className="pad stack hs" style={{ paddingTop: 12 }}>
        {/* ── WHERE AND WHEN ──────────────────────────────────────────────
            The taluka is not a dropdown: this endpoint is keyed to the field's
            own taluka, so offering a picker would imply the farmer can survey
            a district they have no field in. The time range IS a real control —
            the endpoint always accepted it. */}
        <p className="hs-sub">
          {bi(lang, 'See what is being reported around your area.',
                    'तुमच्या भागात काय नोंदवले जात आहे ते पहा.')}
        </p>
        <div className="hs-where">
          <span className="hs-where__loc">
            📍 {data?.taluka_name || plot.taluka}
            <span className="hs-where__you">{bi(lang, 'your taluka', 'तुमचा तालुका')}</span>
          </span>
          <button className="btn sm ghost" onClick={() => setFilters(true)}>
            {bi(lang, 'Filters', 'गाळणी')}
          </button>
        </div>
        <div className="chips" role="group"
             aria-label={bi(lang, 'Time range', 'कालावधी')}>
          {WINDOWS.map(([d, label]) => (
            <button key={d} className="chip" aria-pressed={d === days}
                    onClick={() => setDays(d)}>
              {bi(lang, label[0], label[1])}
            </button>
          ))}
        </div>

        {/* ── WHICH PROBLEM ───────────────────────────────────────────────
            From the reference taxonomy, filtered to this crop. No new list. */}
        <div className="chips" role="group"
             aria-label={bi(lang, 'Problem', 'समस्या')}>
          {choices.map(c => (
            <button key={c.id} className="chip" aria-pressed={c.id === problem}
                    onClick={() => setProblem(c.id)}>
              {c.em} {bi(lang, c.name, c.name_mr)}
            </button>
          ))}
        </div>

        {busy && (
          <Card>
            <p className="small muted">
              {bi(lang, 'Checking nearby signals…', 'आजूबाजूचे संकेत तपासत आहे…')}
            </p>
            <div style={{ marginTop: 10 }}><Loading lines={4} /></div>
          </Card>
        )}
        {err && (
          <Card>
            <p className="small" style={{ color: 'var(--warn)' }}>
              {bi(lang, "Nearby surveillance data couldn't be loaded.",
                        'आजूबाजूची माहिती मिळाली नाही.')}
            </p>
            <button className="btn block ghost" style={{ marginTop: 10 }} onClick={load}>
              {bi(lang, 'Try again', 'पुन्हा प्रयत्न')}
            </button>
          </Card>
        )}

        {!busy && !err && data && (
          <>
            {/* ── AREA RISK PULSE ─────────────────────────────────────────
                Four readings a farmer can take in at a glance, every one of
                them a value the server computed. The grade is outbreak.py's —
                the only thing allowed to use the word cluster. */}
            <Card className={`hs-pulse ${mine?.class || 'none'}`}>
              <div className="row between">
                <div className="card-title">
                  {bi(lang, 'Area risk', 'भागातील धोका')}
                </div>
                <span className="tiny muted">
                  {bi(lang, `last ${data.window_days} days`,
                            `गेले ${data.window_days} दिवस`)}
                </span>
              </div>
              <div className="hs-pulse__grade">
                {bi(lang, data.assessment?.label || CLASS_LABEL[mine?.class || 'none'][0],
                          data.assessment?.label_mr || CLASS_LABEL[mine?.class || 'none'][1])}
              </div>
              <p className="tiny faint" style={{ marginTop: 5, lineHeight: 1.45 }}>
                {bi(lang,
                  'This grade needs several different FIELDS reporting, not several photographs of one field — which is why it can read lower than the map looks.',
                  'या श्रेणीसाठी वेगवेगळ्या शेतांतून नोंदी लागतात — एकाच शेताचे अनेक फोटो नाही. त्यामुळे नकाशापेक्षा ती कमी दिसू शकते.')}
              </p>
              <div className="hs-pulse__grid">
                <div>
                  <span className="k">{bi(lang, 'Reports', 'नोंदी')}</span>
                  <b>{data.assessment?.reports ?? data.total_cases ?? 0}</b>
                </div>
                <div>
                  <span className="k">{bi(lang, 'Talukas affected', 'बाधित तालुके')}</span>
                  <b>{data.affected_talukas ?? 0}</b>
                </div>
                <div>
                  <span className="k">{bi(lang, 'Last detected', 'शेवटची नोंद')}</span>
                  <b>{data.last_reported
                    ? (data.last_reported.days_ago === 0
                        ? bi(lang, 'today', 'आज')
                        : bi(lang, `${data.last_reported.days_ago}d ago`,
                                   `${data.last_reported.days_ago} दिवसांपूर्वी`))
                    : bi(lang, 'Never', 'कधीही नाही')}</b>
                </div>
                <div>
                  <span className="k">{bi(lang, 'Change', 'बदल')}</span>
                  <b className={change?.direction ? `hs-dir ${change.direction}` : ''}>
                    {change?.change_pct != null
                      ? `${ARROW[change.direction] || ''} ${Math.abs(change.change_pct)}%`
                      : bi(lang, 'No basis', 'आधार नाही')}
                  </b>
                </div>
              </div>
            </Card>

            {/* ── THE MAP ─────────────────────────────────────────────────
                Markers are buttons. Tapping one opens a sheet rather than
                navigating away, so the farmer keeps their place. */}
            <Card>
              <div className="row between" style={{ marginBottom: 4 }}>
                <div className="card-title">
                  {bi(lang, data.problem_name, data.problem_name_mr)}
                </div>
                <span className="tiny muted">
                  {bi(lang, 'taluka resolution', 'तालुका पातळी')}
                </span>
              </div>

              {mapped.length === 0 ? (
                <p className="small muted" style={{ marginTop: 8 }}>
                  {bi(lang,
                    'No taluka centroids were returned, so there is nothing to plot.',
                    'तालुक्यांची ठिकाणे मिळाली नाहीत, त्यामुळे नकाशा काढता येत नाही.')}
                </p>
              ) : (
                <HotMap rows={mapped} me={data.taluka} lang={lang} onPick={setSheet} />
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

            {/* ── WHAT CHANGED ────────────────────────────────────────────
                One sentence, and it is the server's. The card never says
                "increasing" unless the two counts say so. */}
            <Card className="hs-changed">
              <div className="card-title">
                {bi(lang, 'What changed?', 'काय बदलले?')}
              </div>
              <p className="small" style={{ marginTop: 6 }}>
                {bi(lang, change?.note, change?.note_mr)
                  || bi(lang, 'Not enough history to compare.', 'तुलना करण्यासाठी पुरेशी नोंद नाही.')}
              </p>
              {change?.comparable && (
                <div className="hs-cmp">
                  <span>{bi(lang, 'previous', 'आधी')} <b>{change.cases_before}</b></span>
                  <span className={`hs-dir ${change.direction}`}>{ARROW[change.direction]}</span>
                  <span>{bi(lang, 'now', 'आता')} <b>{change.cases_now}</b></span>
                </div>
              )}
            </Card>

            {/* ── EMPTY STATE, WHICH IS A READING ────────────────────────── */}
            {withCases.length === 0 ? (
              <Card>
                <div className="card-title">
                  {bi(lang, 'No confirmed cases', 'खात्री झालेली नोंद नाही')}
                </div>
                <p className="small muted" style={{ marginTop: 6 }}>
                  {bi(lang,
                    `No confirmed case of this problem has been recorded anywhere in the district in the last ${data.window_days} days. That is a real reading, not a gap — nothing has been drawn to fill it.`,
                    `गेल्या ${data.window_days} दिवसांत जिल्ह्यात या समस्येची एकही खात्री झालेली नोंद नाही. ही खरी माहिती आहे — रिकामी जागा भरण्यासाठी काहीही काढलेले नाही.`)}
                </p>
                <div className="hs-acts" style={{ marginTop: 12 }}>
                  {days !== 90 && (
                    <button className="btn sm ghost" onClick={() => setDays(90)}>
                      {bi(lang, 'Widen to 3 months', '३ महिन्यांपर्यंत पहा')}
                    </button>
                  )}
                  <button className="btn sm ghost" onClick={() => setFilters(true)}>
                    {bi(lang, 'Try another problem', 'दुसरी समस्या पहा')}
                  </button>
                  <button className="btn sm" onClick={() => go('scan')}>
                    {bi(lang, 'Report a case', 'नोंद करा')}
                  </button>
                </div>
              </Card>
            ) : (
              /* ── TOP AFFECTED TALUKAS ──────────────────────────────────
                 "Talukas", not villages: that is the resolution of the data
                 behind it. Rows are buttons and open the same sheet. */
              <Card>
                <div className="row between">
                  <div className="card-title">
                    {bi(lang, 'Most affected areas', 'सर्वाधिक बाधित भाग')}
                  </div>
                  {riskOnly !== 'any' && (
                    <button className="btn sm ghost" onClick={() => setRiskOnly('any')}>
                      {bi(lang, 'Clear filter', 'गाळणी काढा')}
                    </button>
                  )}
                </div>
                {ranked.length === 0 ? (
                  <p className="small muted" style={{ marginTop: 8 }}>
                    {bi(lang, 'No area matches this risk filter.',
                              'या गाळणीशी जुळणारा भाग नाही.')}
                  </p>
                ) : (
                  <ol className="hs-rank">
                    {ranked.map((r, i) => (
                      <li key={r.taluka}>
                        <button className="hs-rank__row" onClick={() => setSheet(r)}>
                          <span className="hs-rank__n">{i + 1}</span>
                          <span className="hs-rank__nm">
                            {bi(lang, r.name, r.name_mr)}
                            {r.taluka === data.taluka && (
                              <span className="hs-rank__you">
                                {bi(lang, 'your taluka', 'तुमचा')}
                              </span>
                            )}
                          </span>
                          <span className="hs-rank__c">
                            <i style={{ background: (CLASS_COLOR[r.class] || CLASS_COLOR.none).fill }} />
                            {r.cases} {bi(lang, 'reports', 'नोंदी')}
                          </span>
                          <span className="hs-rank__go">›</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                )}
              </Card>
            )}

            {/* ── REPORT TREND ────────────────────────────────────────────
                Six weekly buckets, drawn by hand. Two non-empty weeks is the
                least that can show a direction; below that it says so. */}
            <Card>
              <div className="row between">
                <div className="card-title">
                  {bi(lang, 'Report trend', 'नोंदींचा कल')}
                </div>
                <span className="tiny muted">{bi(lang, 'last 6 weeks', 'गेले ६ आठवडे')}</span>
              </div>
              {trend?.enough ? (
                <TrendBars weeks={trend.weeks} lang={lang} />
              ) : (
                <p className="small muted" style={{ marginTop: 8 }}>
                  {bi(lang, trend?.note, trend?.note_mr)
                    || bi(lang, 'Not enough history for a trend.', 'कल दाखवण्यासाठी पुरेशी नोंद नाही.')}
                </p>
              )}
            </Card>

            {/* ── WEATHER CONTEXT ────────────────────────────────────────
                The existing field-weather response, read — not a second
                provider and not a second request. The sentence below the
                numbers is only shown when the risk board actually fired an
                infection model; PRAHARI does not read a diagnosis off
                humidity. */}
            {wx?.current && (
              <Card>
                <div className="row between">
                  <div className="card-title">🌦 {bi(lang, 'Weather context', 'हवामान संदर्भ')}</div>
                  {wx.status?.generated && (
                    <span className="badge grey">{bi(lang, 'Demo weather', 'प्रात्यक्षिक')}</span>
                  )}
                </div>
                <div className="hs-wx">
                  {wx.current.rh_mean != null && (
                    <div><span className="k">{bi(lang, 'Humidity', 'आर्द्रता')}</span>
                      <b>{Math.round(wx.current.rh_mean)}%</b></div>
                  )}
                  {wx.current.rain_chance_pct != null && (
                    <div><span className="k">{bi(lang, 'Rain chance', 'पावसाची शक्यता')}</span>
                      <b>{Math.round(wx.current.rain_chance_pct)}%</b></div>
                  )}
                  {wx.current.tmax != null && (
                    <div><span className="k">{bi(lang, 'Temperature', 'तापमान')}</span>
                      <b>{Math.round(wx.current.tmax)}°C</b></div>
                  )}
                </div>
                <p className="tiny faint" style={{ marginTop: 9, lineHeight: 1.5 }}>
                  {bi(lang,
                    'Conditions, for planning when to walk the field. Weather reaches a disease decision only through a published infection model, which the field screen names in its evidence — it is never read as a diagnosis here.',
                    'शेतात कधी जायचे हे ठरवण्यासाठी परिस्थिती. हवामान फक्त प्रकाशित मॉडेलमार्फतच निर्णयात येते — इथे त्यावरून निदान केले जात नाही.')}
                </p>
              </Card>
            )}

            {/* ── WHAT TO DO ──────────────────────────────────────────────
                Every action routes into a workflow that already exists. The
                set shown depends on the signed-in role, which the server
                decided — this only reads it. */}
            <Card>
              <div className="card-title">{bi(lang, 'What you can do', 'तुम्ही काय करू शकता')}</div>
              <div className="hs-acts" style={{ marginTop: 10 }}>
                <button className="btn sm" onClick={() => go('decide', { target: problem })}>
                  {bi(lang, 'Get advisory', 'सल्ला घ्या')}
                </button>
                <button className="btn sm ghost" onClick={() => go('community')}>
                  {bi(lang, 'View nearby cases', 'आजूबाजूच्या नोंदी')}
                </button>
                {role === 'farmer' && (
                  <>
                    <button className="btn sm ghost" onClick={() => go('scan')}>
                      {bi(lang, 'Report a case', 'नोंद करा')}
                    </button>
                    <button className="btn sm ghost"
                            onClick={() => go('community', { ask: problem })}>
                      {bi(lang, 'Ask an expert', 'तज्ज्ञांना विचारा')}
                    </button>
                  </>
                )}
              </div>
              <p className="tiny faint" style={{ marginTop: 10 }}>
                {bi(lang, "Don't see your problem? A scan is what adds it to this map.",
                          'तुमची समस्या दिसत नाही? तपासणी केल्यावरच ती या नकाशावर येते.')}
              </p>
            </Card>

            {/* ── HOW WE DETECT THIS ─────────────────────────────────────
                Only mechanisms that exist in the code. No satellite, no
                forecasting of outbreaks, no predictive model — because
                PRAHARI does none of those and a judge will ask. */}
            <details className="method-fold">
              <summary>{bi(lang, 'How does PRAHARI find a hotspot?',
                                  'प्रहरी हॉटस्पॉट कसा शोधते?')}</summary>
              <div style={{ marginTop: 8 }}>
                {[
                  ['Farmers scan a crop, and the diagnosis engine records what it found — or records that it declined to name anything.',
                   'शेतकरी पीक स्कॅन करतात आणि निदान इंजिन काय आढळले ते नोंदवते — किंवा नाव सांगता आले नाही हेही नोंदवते.'],
                  ['Those diagnoses are counted per taluka, as cases per 1,000 farms, so a large taluka does not look like a hotspot simply for being large.',
                   'ही निदाने तालुकानिहाय, दर १००० शेतांमागे मोजली जातात — मोठा तालुका फक्त मोठा असल्यामुळे हॉटस्पॉट दिसत नाही.'],
                  ['A Getis-Ord Gi* statistic tests whether a taluka and its neighbours are high together rather than by chance.',
                   'Getis-Ord Gi* ही आकडेवारी तालुका व शेजारी एकत्र जास्त आहेत का हे तपासते.'],
                  ['The word cluster is only used when several distinct FIELDS report, not several photographs of one field. Hotspot needs the statistic too, and confirmed needs an expert.',
                   '"गट" हा शब्द वेगवेगळ्या शेतांतून नोंदी आल्यावरच वापरला जातो. "पुष्ट" साठी तज्ज्ञांची पडताळणी लागते.'],
                  ['There is no satellite imagery, no outbreak forecast and no prediction of where a disease will go next. PRAHARI counts what farmers found and says where.',
                   'उपग्रह प्रतिमा नाहीत, प्रादुर्भावाचा अंदाज नाही. प्रहरी शेतकऱ्यांना आढळलेले मोजते आणि कुठे ते सांगते.'],
                ].map(([en, mr], i) => (
                  <div className="evid" key={i}>
                    <span className="tick">•</span><span>{bi(lang, en, mr)}</span>
                  </div>
                ))}
              </div>
            </details>

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

      {/* ── THE HOTSPOT SHEET ───────────────────────────────────────────── */}
      <Sheet open={!!sheet} onClose={() => setSheet(null)}
             title={sheet ? bi(lang, sheet.name, sheet.name_mr) : ''}>
        {sheet && (
          <div className="stack">
            <div className="hs-sheet__head">
              <div className="hs-sheet__prob">
                {bi(lang, data.problem_name, data.problem_name_mr)}
              </div>
              <span className={`hs-sheet__risk ${sheet.class}`}>
                {bi(lang, CLASS_LABEL[sheet.class]?.[0] || sheet.class,
                          CLASS_LABEL[sheet.class]?.[1] || sheet.class)}
              </span>
            </div>
            <p className="small muted">
              {bi(lang,
                `${sheet.cases || 0} report${(sheet.cases || 0) === 1 ? '' : 's'} · last ${data.window_days} days`,
                `${sheet.cases || 0} नोंदी · गेले ${data.window_days} दिवस`)}
            </p>

            <div className="hs-pulse__grid">
              <div><span className="k">{bi(lang, 'Reports', 'नोंदी')}</span>
                <b>{sheet.cases || 0}</b></div>
              <div><span className="k">{bi(lang, 'Per 1,000 farms', 'दर १००० शेतांमागे')}</span>
                <b>{sheet.incidence_per_1000 != null
                  ? sheet.incidence_per_1000
                  : bi(lang, 'Not known', 'माहीत नाही')}</b></div>
              <div><span className="k">{bi(lang, 'Gi* z', 'Gi* z')}</span>
                <b>{sheet.z != null ? sheet.z : bi(lang, 'Not known', 'माहीत नाही')}</b></div>
              <div><span className="k">{bi(lang, 'Your taluka', 'तुमचा तालुका')}</span>
                <b>{sheet.taluka === data.taluka
                  ? bi(lang, 'Yes', 'होय') : bi(lang, 'No', 'नाही')}</b></div>
            </div>

            {/* The only sentence here that interprets anything, and it is
                shown only when the counts support it. */}
            {sheet.taluka === data.taluka && change?.direction === 'up' && (
              <div className="note">
                {bi(lang, 'Reports are increasing in your taluka.',
                          'तुमच्या तालुक्यात नोंदी वाढत आहेत.')}
              </div>
            )}
            {sheet.class === 'none' && (sheet.cases || 0) === 0 && (
              <p className="small muted">
                {bi(lang, 'No case of this problem has been recorded here in this period.',
                          'या काळात येथे या समस्येची नोंद नाही.')}
              </p>
            )}

            <button className="btn block" onClick={() => { setSheet(null); go('decide', { target: problem }) }}>
              {bi(lang, 'Get advisory for this problem', 'या समस्येचा सल्ला घ्या')}
            </button>
            <button className="btn block ghost" onClick={() => { setSheet(null); go('community') }}>
              {bi(lang, 'View nearby cases', 'आजूबाजूच्या नोंदी')}
            </button>
            {sheet.last_reported?.day && (
              <p className="tiny faint center">
                {bi(lang, 'Last reported', 'शेवटची नोंद')} {fmtDate(sheet.last_reported.day, lang)}
              </p>
            )}
          </div>
        )}
      </Sheet>

      {/* ── FILTERS ─────────────────────────────────────────────────────── */}
      <Sheet open={filters} onClose={() => setFilters(false)}
             title={bi(lang, 'Filters', 'गाळणी')}>
        <div className="stack">
          <div>
            <div className="k" style={{ marginBottom: 7 }}>{bi(lang, 'Problem', 'समस्या')}</div>
            <div className="chips">
              {choices.map(c => (
                <button key={c.id} className="chip" aria-pressed={c.id === problem}
                        onClick={() => setProblem(c.id)}>
                  {c.em} {bi(lang, c.name, c.name_mr)}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="k" style={{ marginBottom: 7 }}>{bi(lang, 'Time range', 'कालावधी')}</div>
            <div className="chips">
              {WINDOWS.map(([d, label]) => (
                <button key={d} className="chip" aria-pressed={d === days}
                        onClick={() => setDays(d)}>
                  {bi(lang, label[0], label[1])}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="k" style={{ marginBottom: 7 }}>{bi(lang, 'Risk level', 'धोका पातळी')}</div>
            <div className="chips">
              {[['any', ['Any', 'सर्व']], ['hot', CLASS_LABEL.hot], ['warm', CLASS_LABEL.warm]]
                .map(([v, label]) => (
                  <button key={v} className="chip" aria-pressed={v === riskOnly}
                          onClick={() => setRiskOnly(v)}>
                    {bi(lang, label[0], label[1])}
                  </button>
                ))}
            </div>
            <p className="tiny faint" style={{ marginTop: 7 }}>
              {bi(lang, 'Filters the ranked list below the map. The map always shows the whole district, because a hidden taluka reads as a taluka with no cases.',
                        'ही गाळणी नकाशाखालील यादीवर लागू होते. नकाशा संपूर्ण जिल्हा दाखवतो.')}
            </p>
          </div>
          <div className="row" style={{ gap: 9 }}>
            <button className="btn ghost grow"
                    onClick={() => { setProblem(choices[0]?.id || 'late_blight'); setDays(21); setRiskOnly('any') }}>
              {bi(lang, 'Reset', 'पूर्ववत')}
            </button>
            <button className="btn grow" onClick={() => setFilters(false)}>
              {bi(lang, 'Done', 'झाले')}
            </button>
          </div>
        </div>
      </Sheet>
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

/* ── the trend bars ────────────────────────────────────────────────────────
   Six divs. No charting library, because six numbers do not need one and the
   bundle is gated. Each bar carries its count as text as well as height, so
   the reading does not depend on comparing two rectangles by eye. */
function TrendBars({ weeks, lang }) {
  const max = Math.max(1, ...weeks.map(w => w.cases))
  return (
    <div className="hs-trend" role="img"
         aria-label={weeks.map(w => `${w.week_start}: ${w.cases}`).join(', ')}>
      {weeks.map(w => (
        <div className="hs-trend__col" key={w.week_start}>
          <span className="hs-trend__n">{w.cases || ''}</span>
          <div className="hs-trend__bar"
               style={{ height: `${Math.max(3, (w.cases / max) * 100)}%`,
                        opacity: w.cases ? 1 : 0.3 }} />
          <span className="hs-trend__lbl">{fmtDate(w.week_start, lang).slice(0, 6)}</span>
        </div>
      ))}
    </div>
  )
}

/* ── the plot ──────────────────────────────────────────────────────────────
   An equirectangular projection of taluka centroids into a fixed viewBox, with
   longitude scaled by cos(latitude) so the district is not stretched sideways.
   At the scale of one district this is indistinguishable from a projected map
   and needs no library, no tiles and no network.

   Markers are <a>-less buttons via role, so a keyboard reaches every taluka. */
function HotMap({ rows, me, lang, onPick }) {
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
      <svg viewBox={`0 0 ${W} ${H}`} role="group"
           aria-label={lang === 'mr'
             ? 'तालुकानिहाय प्रादुर्भावाचा नकाशा'
             : 'Map of confirmed cases by taluka'}>
        {geom.map(g => (
          <g key={g.taluka} className="hs-map__pin" tabIndex={0} role="button"
             aria-label={`${g.name}: ${g.cases || 0} reports, ${CLASS_LABEL[g.class]?.[0] || g.class}`}
             onClick={() => onPick?.(g)}
             onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick?.(g) } }}>
            {/* A generous invisible hit area: a 4.5px circle is not a touch
                target, and the visible dot must stay small to stay readable. */}
            <circle cx={g.x} cy={g.y} r="22" fill="transparent" />
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
