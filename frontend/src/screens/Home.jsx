/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · the farmer's home screen

   Rebuilt around ONE question. The old screen answered five, in five cards,
   and left a farmer standing in a field to synthesise them. The order below is
   the order that survives being read on a cracked phone at midday:

       WHO AM I, WHAT AM I GROWING       greeting + crop + stage + day
       FARM HEALTH                       one number, one band, one sentence
       WHAT SHOULD I DO TODAY            instructions, largest type on the page
       WHAT'S COMING                     four days of published-model output
       CROP HEALTH PASSPORT              the field's record, as six counts

   The action list is NOT assembled here. It comes from /api/fields/{id}/today,
   which builds it from records in order of consequence and attaches the row
   behind each item — so "scout for late blight" can be traced to the Hutton
   criteria firing on this field's own weather, and a farmer who wants to see
   that can. Model detail stays behind "Why?".
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import {
  Band, Card, ErrorNote, Gauge, Loading, Prov, WeatherStrip, Why,
  bi, fmtDate, levelLabel,
} from '../ui'

const GREET = (h, lang) => {
  if (lang === 'mr') return h < 12 ? 'सुप्रभात' : h < 17 ? 'नमस्कार' : 'शुभ संध्याकाळ'
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

const CROP_EM = {
  tomato: '🍅', potato: '🥔', onion: '🧅', grape: '🍇', maize: '🌽',
  cotton: '🌱', soybean: '🌿', pigeonpea: '🫘', wheat: '🌾',
}

export default function Home({ lang, me, plot, plots, onPlot, go, unread, onBell }) {
  const [data, setData] = useState(null)
  const [fc, setFc] = useState(null)
  const [todo, setTodo] = useState(null)
  const [pass, setPass] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)

  const load = () => {
    if (!plot) { setBusy(false); return }
    setBusy(true); setErr(null)
    Promise.all([
      api.fieldHealth(plot.id),
      api.forecast(plot.id).catch(() => null),
      api.today(plot.id).catch(() => null),
      api.history(plot.id).catch(() => null),
    ])
      .then(([h, f, t, p]) => { setData(h); setFc(f); setTodo(t); setPass(p) })
      .catch(setErr)
      .finally(() => setBusy(false))
  }
  useEffect(load, [plot?.id])

  const name = (lang === 'mr' && me?.user?.full_name_mr) || me?.user?.full_name || ''
  const first = String(name).split(' ')[0]
  const hour = new Date().getHours()
  const stage = data?.stage || data?.crop_stage

  return (
    <>
      <header className="hdr">
        <div className="row between">
          <div className="grow">
            <div className="hdr-greet">{GREET(hour, lang)}, {first} 👋</div>
            <div className="hdr-sub">
              {plot ? `${plot.name} · ${plot.area_acre} ${lang === 'mr' ? 'एकर' : 'acres'}`
                    : (lang === 'mr' ? 'अजून शेत नोंदवलेले नाही' : 'No field registered yet')}
            </div>
          </div>
          {/* The brand header above owns the alert bell and the account sheet
              now, so the pair that used to sit here would be a second copy of
              the same two controls. `unread` and `onBell` stay in the props so
              the count can be surfaced in the greeting if it is ever wanted. */}
        </div>
        {plot && (
          <div className="cropline">
            <span className="em">{CROP_EM[plot.crop] || '🌱'}</span>
            <span className="txt">
              {plot.crop_label || plot.crop}
              {stage?.label && ` · ${bi(lang, stage.label, stage.label_mr)}`}
            </span>
            {stage?.days != null && (
              <span className="das">
                {lang === 'mr' ? `पेरणीनंतर ${stage.days} दिवस` : `day ${stage.days}`}
              </span>
            )}
          </div>
        )}
      </header>

      <div className="pad pull stack">
        {plots?.length > 1 && (
          <div className="chips" style={{ marginBottom: 2 }}>
            {plots.map(p => (
              <button key={p.id} className="chip" aria-pressed={p.id === plot?.id}
                      onClick={() => onPlot(p.id)}>{p.name}</button>
            ))}
          </div>
        )}

        {!plot && <FirstField lang={lang} go={go} />}
        {busy && plot && <Loading lines={4} />}
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}

        {data && !busy && (
          <>
            {/* ── FARM HEALTH ─────────────────────────────────────────── */}
            <Card>
              <div className="row between" style={{ marginBottom: 12 }}>
                <div className="card-title">{lang === 'mr' ? 'शेत आरोग्य' : 'Farm Health'}</div>
                <Band band={data.health.band}
                      label={bi(lang, data.health.band_label, data.health.band_label_mr)} />
              </div>
              <div className="gauge">
                <Gauge value={data.health.score} band={data.health.band} />
                <div className="grow">
                  <div className="row" style={{ alignItems: 'baseline', gap: 5 }}>
                    <span className="gauge-num">{data.health.score}</span>
                    <span className="gauge-den">/100</span>
                  </div>
                  <div className="small muted" style={{ marginTop: 4 }}>
                    {data.changed?.first_visit
                      ? bi(lang, data.changed.message, data.changed.message_mr)
                      : bi(lang, data.changed?.headline, data.changed?.headline_mr)}
                  </div>
                </div>
              </div>

              <div className="tiles">
                {[['weather', '🌦', lang === 'mr' ? 'हवामान' : 'Weather'],
                  ['pest', '🐛', lang === 'mr' ? 'कीड' : 'Pest'],
                  ['disease', '🍂', lang === 'mr' ? 'रोग' : 'Disease']].map(([k, ic, label]) => {
                  const comp = data.health.components[k]
                  return (
                    <div className="tile" key={k}>
                      <div className="ic">{ic}</div>
                      <div className="lbl">{label}</div>
                      <div className="val" style={{
                        color: comp.band === 'high' ? 'var(--bad)'
                          : comp.band === 'rising' ? 'var(--warn)'
                          : comp.band === 'watch' ? 'var(--info)' : 'var(--ok)',
                      }}>{levelLabel(comp.band, lang)}</div>
                    </div>
                  )
                })}
              </div>

              <Why label={lang === 'mr' ? 'हा आकडा कसा काढला?' : 'How is this number built?'}>
                <p style={{ marginBottom: 8 }}>{data.score_meaning}</p>
                <p className="mono tiny" style={{ marginBottom: 8 }}>
                  score = 100 − disease − pest − weather − nearby
                </p>
                {data.health.terms.length === 0
                  ? <p>Nothing has cost this field any points today.</p>
                  : data.health.terms.map((term, i) => (
                      <div key={i} className="row" style={{ alignItems: 'flex-start', gap: 8, marginTop: 6 }}>
                        <b className="mono" style={{ color: 'var(--bad)', flex: 'none' }}>−{term.cost}</b>
                        <span className="small">{term.why}</span>
                      </div>
                    ))}
                <Prov label="Method" value={data.health.method} />
              </Why>
              {data.weather && <WeatherStrip weather={data.weather} />}
            </Card>

            {/* ── WHAT SHOULD I DO TODAY ──────────────────────────────── */}
            <h2 className="sect-title">
              {lang === 'mr' ? 'आज काय करावे?' : 'What should I do today?'}
            </h2>
            {todo?.items?.length > 0 ? (
              <div className="today">
                {todo.items.map((it, i) => (
                  <button key={i} className={`todo ${it.tone}`} onClick={() => act(it, go)}>
                    <span className="ic">{it.icon}</span>
                    <span className="grow">
                      <span className="nm" style={{ display: 'block' }}>
                        {bi(lang, it.title, it.title_mr)}
                      </span>
                      <span className="sub" style={{ display: 'block' }}>
                        {bi(lang, it.detail, it.detail_mr)}
                      </span>
                    </span>
                    <span className="go">›</span>
                  </button>
                ))}
              </div>
            ) : (
              <Card>
                <div className="row" style={{ gap: 12 }}>
                  <div style={{ fontSize: 26 }}>✅</div>
                  <div className="grow small">
                    {bi(lang, todo?.all_clear_note, todo?.all_clear_note_mr)
                      || (lang === 'mr' ? 'आज काहीही करण्याची गरज नाही.' : 'Nothing needs a decision today.')}
                  </div>
                </div>
              </Card>
            )}
            {todo?.method && (
              <Card className="tight" style={{ marginTop: 2 }}>
                <Prov label={lang === 'mr' ? 'ही यादी कशी बनते' : 'How this list is built'}
                      value={todo.method} />
              </Card>
            )}

            {/* ── WHAT'S COMING ───────────────────────────────────────── */}
            {fc?.forecast?.length > 0 && (
              <Card>
                <div className="row between" style={{ marginBottom: 10 }}>
                  <div className="card-title">{lang === 'mr' ? 'पुढे काय येत आहे?' : "What's Coming"}</div>
                  <button className="btn sm quiet" onClick={() => go('forecast')}>
                    {lang === 'mr' ? 'तपशील' : 'Details'} ›
                  </button>
                </div>
                <div className="fcast">
                  {fc.forecast.map(d => (
                    <div className={`d ${d.level}`} key={d.date}>
                      <div className="dy">{d.offset === 0 ? (lang === 'mr' ? 'आज' : 'Today') : fmtDate(d.date, lang)}</div>
                      <div className="lv">{levelLabel(d.level, lang)}</div>
                    </div>
                  ))}
                </div>
                <div className="note" style={{ marginTop: 12 }}>
                  <b>{bi(lang, fc.headline.title, fc.headline.title_mr)}</b>
                  <ul style={{ margin: '7px 0 0 16px', fontSize: 13 }}>
                    {(lang === 'mr' ? fc.headline.reasons_mr : fc.headline.reasons).slice(0, 3)
                      .map((r, i) => <li key={i} style={{ marginTop: 3 }}>{r}</li>)}
                  </ul>
                </div>
                <Prov label="Method" value={fc.headline.method} />
              </Card>
            )}

            {/* ── CROP HEALTH PASSPORT ────────────────────────────────── */}
            <Card>
              <div className="row between" style={{ marginBottom: 10 }}>
                <div className="card-title">
                  {lang === 'mr' ? 'पीक आरोग्य पासपोर्ट' : 'Crop Health Passport'}
                </div>
                <button className="btn sm quiet" onClick={() => go('history')}>
                  {lang === 'mr' ? 'इतिहास' : 'History'} ›
                </button>
              </div>
              <Passport pass={pass} lang={lang} />
              <p className="tiny faint" style={{ marginTop: 10, lineHeight: 1.5 }}>
                {lang === 'mr'
                  ? 'या पिकाच्या हंगामातील प्रत्येक तपासणी, मोजणी, निर्णय आणि फवारणीची नोंद — काढणीच्या वेळी हाच पुरावा असतो.'
                  : 'Every scan, count, decision and application this season. At harvest, this is the record that shows what was used and when.'}
              </p>
            </Card>

            <div className="tiny faint center" style={{ padding: '18px 8px 4px', lineHeight: 1.6 }}>
              {lang === 'mr'
                ? 'प्रहरी हे पूर्वसूचना देणारे साधन आहे. निर्णय शेवटी तुमचा — आणि शंका असल्यास कृषी सहाय्यकाचा सल्ला घ्या.'
                : 'PRAHARI is an early-warning tool. The decision is yours — and when it is unclear, ask your Krishi Sahayak.'}
            </div>
          </>
        )}
      </div>
    </>
  )
}

function act(item, go) {
  const a = item.action || {}
  if (a.do === 'rescan') return go('rescan', { followup: { id: a.followup_id } })
  if (a.do === 'decide') return go('decide', { target: a.target })
  return go(a.do || 'home')
}

/* ── the passport strip: six counts, from the field's own record ────────── */
function Passport({ pass, lang }) {
  // Counted from the field's own event log and records — never estimated. The
  // kinds here are exactly the ones the routers write (see field_events).
  const ev = pass?.timeline || []
  const n = (kind) => ev.filter(e => e.kind === kind).length
  const cells = [
    ['📷', n('scan'), lang === 'mr' ? 'तपासण्या' : 'Scans'],
    ['🪤', n('count'), lang === 'mr' ? 'मोजण्या' : 'Counts'],
    ['⚖️', (pass?.threshold_checks || []).length, lang === 'mr' ? 'पातळी' : 'Checks'],
    ['🧪', (pass?.applications || []).length, lang === 'mr' ? 'फवारण्या' : 'Sprays'],
    ['🔁', n('followup'), lang === 'mr' ? 'पुनर्तपासणी' : 'Follow-ups'],
    ['✅', n('expert'), lang === 'mr' ? 'तज्ज्ञ' : 'Expert'],
  ]
  return (
    <div className="passport">
      {cells.map(([ic, count, label], i) => (
        <div className={`p ${count > 0 ? 'has' : ''}`} key={i}>
          <div className="ic">{ic}</div>
          <div className="n">{count}</div>
          <div className="l">{label}</div>
        </div>
      ))}
    </div>
  )
}

function FirstField({ lang, go }) {
  return (
    <Card>
      <div className="center" style={{ padding: '18px 4px' }}>
        <div style={{ fontSize: 34 }}>🌱</div>
        <h2 className="h2" style={{ marginTop: 8 }}>
          {lang === 'mr' ? 'तुमचे पहिले शेत नोंदवा' : 'Register your first field'}
        </h2>
        <p className="small muted" style={{ marginTop: 6 }}>
          {lang === 'mr'
            ? 'शेताचे ठिकाण, पीक आणि पेरणीची तारीख दिल्यावर प्रहरी त्या ठिकाणच्या खऱ्या हवामानावर धोका मोजू लागते.'
            : 'Give PRAHARI a location, a crop and a sowing date, and it starts forecasting risk from the real weather at that exact spot.'}
        </p>
        <button className="btn block" style={{ marginTop: 16 }} onClick={() => go('addField')}>
          {lang === 'mr' ? 'शेत जोडा' : 'Add a field'}
        </button>
      </div>
    </Card>
  )
}
