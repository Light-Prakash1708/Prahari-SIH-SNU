/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · the Crop Journey

   The calendar screen, and the one thing it must never become is a wall chart
   of months and farming activities. It answers six questions in this order:

     where is my crop        → the stage rail, from this field's sowing date
     what threatens it now   → the watchlist, from the models firing today
     why is PRAHARI worried  → the prevention window, factor by factor
     when must I act         → the window's horizon
     what do I inspect       → the mission, which is the existing agenda
     what happened before    → the history, from the field's own rows

   Everything is drawn from ONE request. Nothing is computed here — this file
   contains no agronomy, only layout. Where the server sends null, the screen
   says so plainly instead of drawing an empty shape that looks like data.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Loading, Sheet, bi, fmtDate } from '../ui'
import Icon from '../shell/Icon'
import './crop-journey.css'

const T = {
  mr: {
    title: 'पीक प्रवास', sub: 'हंगामात कुठे आहात, आता काय धोका आहे, आणि काय तपासायचे.',
    day: 'दिवस', of: '/', stage: 'सध्याची अवस्था', next: 'पुढील अवस्था',
    inDays: 'दिवसांत', toHarvest: 'काढणीस', journey: 'पीक प्रवास',
    prevention: 'प्रतिबंध कालावधी', why: 'प्रहरी का चिंतेत आहे?',
    mission: 'आजचे काम', startMission: 'तपासणी सुरू करा', watch: 'लक्ष ठेवा',
    threats: 'अवस्थेनुसार धोका', history: 'शेताचा इतिहास', noHistory: 'अजून नोंदी नाहीत.',
    scout: 'शेत तपासा', trap: 'सापळा मोजा', scan: 'फोटो काढा',
    noDate: 'पेरणीची तारीख नोंदवलेली नाही, त्यामुळे अवस्था काढता येत नाही.',
    open: 'सुरू', closed: 'सध्या शांत', days: 'दिवस', etl: 'या अवस्थेतील मर्यादा',
    source: 'स्रोत', allClear: 'आज निर्णय घेण्याची गरज नाही.',
  },
  en: {
    title: 'Crop Journey', sub: 'Where you are in the season, what threatens it now, and what to inspect.',
    day: 'Day', of: 'of', stage: 'Current stage', next: 'Next stage',
    inDays: 'in', toHarvest: 'to harvest', journey: 'Crop journey',
    prevention: 'Prevention window', why: 'Why is PRAHARI concerned?',
    mission: "Today's mission", startMission: 'Start scout mission', watch: 'Watchlist',
    threats: 'Threat by stage', history: 'Field health history', noHistory: 'No records yet.',
    scout: 'Scout the field', trap: 'Count the trap', scan: 'Capture evidence',
    noDate: 'No sowing date on record, so the stage cannot be worked out.',
    open: 'Open', closed: 'Quiet right now', days: 'days', etl: 'Threshold at this stage',
    source: 'Source', allClear: 'Nothing needs a decision today.',
  },
}
const t = (lang, k) => (T[lang] || T.en)[k] ?? T.en[k]

const BAND_TONE = { high: 'bad', watch: 'warn', rising: 'warn', normal: 'ok', tolerant: 'ok', low: 'ok' }

export default function CropJourney({ lang, plot, plots, onPlot, go }) {
  const [cal, setCal] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)
  const [openStage, setOpenStage] = useState(null)

  const load = useCallback(() => {
    if (!plot) { setBusy(false); return }
    setBusy(true); setErr(null)
    api.cropCalendar(plot.id, lang)
      .then(d => { setCal(d); setErr(null) })
      .catch(e => { setErr(e); setCal(null) })
      .finally(() => setBusy(false))
  }, [plot, lang])

  useEffect(load, [load])

  if (!plot) {
    return (
      <>
        <Header lang={lang} />
        <div className="pad">
          <Card><p className="small muted">{t(lang, 'noDate')}</p></Card>
        </div>
      </>
    )
  }

  return (
    <>
      <Header lang={lang} />

      <div className="pad cj-wrap">
        {plots?.length > 1 && (
          <div className="cj-fieldrow">
            {plots.map(p => (
              <button key={p.id} onClick={() => onPlot(p.id)}
                      className={'cj-fieldchip' + (p.id === plot.id ? ' is-on' : '')}>
                {p.name}
              </button>
            ))}
          </div>
        )}

        {busy && <Loading lines={5} />}
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}

        {cal && !busy && (
          <>
            <CropHero cal={cal} lang={lang} />
            <StageRail cal={cal} lang={lang} onPick={setOpenStage} />
            <PreventionWindow cal={cal} lang={lang} go={go} />
            <Mission cal={cal} lang={lang} go={go} />
            <Watchlist cal={cal} lang={lang} />
            <ThreatByStage cal={cal} lang={lang} onPick={setOpenStage} />
            <History cal={cal} lang={lang} />
            <details className="method-fold">
              <summary>{bi(lang, 'How this screen is built', 'हा पडदा कसा तयार होतो')}</summary>
              <p className="small muted">{bi(lang, cal.method, cal.method_mr)}</p>
            </details>
          </>
        )}
      </div>

      <StageSheet stage={openStage} cal={cal} lang={lang}
                  onClose={() => setOpenStage(null)} go={go} />
    </>
  )
}

function Header({ lang }) {
  return (
    <header className="hdr">
      <div className="hdr-greet">{t(lang, 'title')}</div>
      <div className="hdr-sub">{t(lang, 'sub')}</div>
    </header>
  )
}

/* ── who and where ─────────────────────────────────────────────────────── */
function CropHero({ cal, lang }) {
  const { crop, field, crop_stage: st, next_stage: next } = cal
  const pct = st.progress == null ? null : Math.round(st.progress * 100)

  return (
    <Card className="cj-hero">
      <div className="cj-hero__top">
        <span className="cj-hero__em">{crop.em || '🌱'}</span>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="cj-hero__crop">
            {bi(lang, crop.name, crop.name_mr)}
            {crop.variety && <span className="cj-hero__variety"> · {crop.variety}</span>}
          </div>
          <div className="cj-hero__field">
            {field.name} · {field.area_acre} {lang === 'mr' ? 'एकर' : 'ac'}
            {crop.sown_on && <> · {fmtDate(crop.sown_on, lang)}</>}
          </div>
        </div>
      </div>

      {st.stage ? (
        <>
          <div className="cj-hero__stage">
            <div>
              <div className="cj-hero__stagelabel">{bi(lang, st.label, st.label_mr)}</div>
              <div className="cj-hero__day">{t(lang, 'day')} {st.days}</div>
            </div>
            {st.days_to_harvest != null && (
              <div className="cj-hero__harvest">
                <b>{st.days_to_harvest}</b>
                <span>{lang === 'mr' ? 'दिवस काढणीस' : `days ${t(lang, 'toHarvest')}`}</span>
              </div>
            )}
          </div>

          {pct != null && (
            <div className="cj-progress" role="progressbar" aria-valuenow={pct}
                 aria-valuemin={0} aria-valuemax={100}>
              <span style={{ width: `${pct}%` }} />
            </div>
          )}

          {next && (
            <div className="cj-hero__next">
              {t(lang, 'next')}: <b>{bi(lang, next.label, next.label_mr)}</b>
              {next.in_days != null && <> — {t(lang, 'inDays')} {next.in_days} {t(lang, 'days')}</>}
              {next.from && <span className="faint"> ({fmtDate(next.from, lang)})</span>}
            </div>
          )}
        </>
      ) : (
        <p className="small muted" style={{ marginTop: 10 }}>{t(lang, 'noDate')}</p>
      )}
    </Card>
  )
}

/* ── the rail ──────────────────────────────────────────────────────────── */
function StageRail({ cal, lang, onPick }) {
  const cur = cal.crop_stage.stage
  let passed = true
  return (
    <section className="cj-section">
      <h2 className="cj-h2">{t(lang, 'journey')}</h2>
      <div className="cj-rail" role="list">
        {cal.timeline.map(st => {
          const isNow = st.stage === cur
          const cls = isNow ? 'now' : passed ? 'done' : 'todo'
          if (isNow) passed = false
          const win = cal.threat_windows.find(w => w.stage === st.stage)
          return (
            <button key={st.stage} role="listitem"
                    className={`cj-stage is-${cls}`}
                    onClick={() => onPick(st.stage)}
                    aria-current={isNow ? 'step' : undefined}>
              <span className={`cj-stage__dot tone-${BAND_TONE[win?.band] || 'ok'}`} />
              <span className="cj-stage__label">{bi(lang, st.label, st.label_mr)}</span>
              <span className="cj-stage__days">
                {st.from ? fmtDate(st.from, lang) : `${st.day_from}–${st.day_to}d`}
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

/* ── the prevention window ─────────────────────────────────────────────── */
function PreventionWindow({ cal, lang, go }) {
  const pw = cal.prevention_window
  const tone = BAND_TONE[pw.level] || 'ok'

  return (
    <Card className={`cj-pw tone-${tone}`}>
      <div className="cj-pw__head">
        <span className="cj-pw__badge">{t(lang, 'prevention')}</span>
        <span className="cj-pw__state">
          {pw.open ? `${t(lang, 'open')} · ${pw.days} ${t(lang, 'days')}` : t(lang, 'closed')}
        </span>
      </div>

      <h3 className="cj-pw__title">{bi(lang, pw.title, pw.title_mr)}</h3>

      {pw.factors.length > 0 && (
        <>
          <div className="cj-pw__why">{t(lang, 'why')}</div>
          <ul className="cj-pw__factors">
            {pw.factors.map((f, i) => (
              <li key={i}>
                <span className="em">{f.em}</span>
                <span>{bi(lang, f.text, f.text_mr)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {pw.open && (
        <div className="cj-pw__actions">
          <button className="btn block" onClick={() => go('scan')}>
            <Icon name="camera" size={16} /> {t(lang, 'startMission')}
          </button>
          <div className="cj-pw__secondary">
            <button className="cj-minibtn" onClick={() => go('traps')}>
              <Icon name="bug" size={14} /> {t(lang, 'trap')}
            </button>
            <button className="cj-minibtn" onClick={() => go('forecast')}>
              <Icon name="radar" size={14} /> {lang === 'mr' ? 'अंदाज' : 'Forecast'}
            </button>
          </div>
        </div>
      )}

      <details className="method-fold">
        <summary>{bi(lang, 'How this window is set', 'ही मुदत कशी ठरते')}</summary>
        <p className="small muted">{bi(lang, pw.method, pw.method_mr)}</p>
      </details>
    </Card>
  )
}

/* ── today's mission — the existing agenda, not a second system ────────── */
function Mission({ cal, lang, go }) {
  const m = cal.mission
  const items = m?.items || []
  if (!items.length) {
    return (
      <Card className="cj-mission">
        <h2 className="cj-h2">{t(lang, 'mission')}</h2>
        <p className="small muted">{bi(lang, m?.all_clear_note, m?.all_clear_note_mr)
          || t(lang, 'allClear')}</p>
      </Card>
    )
  }
  return (
    <section className="cj-section">
      <h2 className="cj-h2">{t(lang, 'mission')}</h2>
      <div className="stack">
        {items.map((it, i) => (
          <Card key={i} className={`cj-task tone-${it.tone === 'urgent' ? 'bad'
            : it.tone === 'act' ? 'warn' : 'ok'}`}>
            <div className="cj-task__row">
              <span className="cj-task__em">{it.icon}</span>
              <div className="grow" style={{ minWidth: 0 }}>
                <div className="cj-task__title">{bi(lang, it.title, it.title_mr)}</div>
                <p className="cj-task__detail">{bi(lang, it.detail, it.detail_mr)}</p>
              </div>
            </div>
            {it.action?.do && (
              <button className="cj-minibtn cj-task__go" onClick={() => go(it.action.do)}>
                {lang === 'mr' ? 'उघडा' : 'Open'} <Icon name="chevron" size={12} />
              </button>
            )}
          </Card>
        ))}
      </div>
    </section>
  )
}

/* ── what to look for ──────────────────────────────────────────────────── */
function Watchlist({ cal, lang }) {
  if (!cal.watchlist.length) return null
  return (
    <section className="cj-section">
      <h2 className="cj-h2">{t(lang, 'watch')}</h2>
      <div className="stack">
        {cal.watchlist.map(w => (
          <Card key={w.id} className="cj-watch">
            <div className="cj-watch__head">
              <span className="cj-watch__em">{w.em}</span>
              <span className="cj-watch__name">{bi(lang, w.name, w.name_mr)}</span>
              {w.level && (
                <span className={`badge ${BAND_TONE[w.level] || 'grey'}`}>{w.level}</span>
              )}
            </div>
            {(w.scout || w.scout_mr) && (
              <p className="cj-watch__scout">{bi(lang, w.scout, w.scout_mr)}</p>
            )}
          </Card>
        ))}
      </div>
    </section>
  )
}

/* ── threat by stage ───────────────────────────────────────────────────── */
function ThreatByStage({ cal, lang, onPick }) {
  return (
    <section className="cj-section">
      <h2 className="cj-h2">{t(lang, 'threats')}</h2>
      <div className="cj-threatgrid">
        {cal.threat_windows.map(w => (
          <button key={w.stage} className={`cj-threat tone-${BAND_TONE[w.band] || 'ok'}`}
                  onClick={() => onPick(w.stage)}>
            <span className="cj-threat__stage">{bi(lang, w.label, w.label_mr)}</span>
            <span className="cj-threat__band">{w.band}</span>
            <span className="cj-threat__count">
              {w.diseases.length + w.pests.length || '—'}
            </span>
          </button>
        ))}
      </div>
      {/* The reason the later stages carry no disease colour, stated on the
          screen rather than buried in the API response. */}
      <details className="method-fold">
        <summary>{bi(lang, 'Why later stages are blank', 'पुढच्या अवस्था रिकाम्या का')}</summary>
        <p className="small muted">{bi(lang, cal.disease_note, cal.disease_note_mr)}</p>
      </details>
    </section>
  )
}

/* ── the per-stage detail sheet ────────────────────────────────────────── */
function StageSheet({ stage, cal, lang, onClose, go }) {
  const w = stage && cal ? cal.threat_windows.find(x => x.stage === stage) : null
  const st = stage && cal ? cal.timeline.find(x => x.stage === stage) : null
  if (!w || !st) return <Sheet open={false} onClose={onClose} title="" />

  return (
    <Sheet open={!!stage} onClose={onClose} title={bi(lang, st.label, st.label_mr)}>
      <p className="small muted" style={{ marginBottom: 12 }}>
        {st.from
          ? `${fmtDate(st.from, lang)} — ${fmtDate(st.to, lang)} · ${lang === 'mr' ? 'दिवस' : 'day'} ${st.day_from}–${st.day_to}`
          : `${lang === 'mr' ? 'दिवस' : 'Day'} ${st.day_from}–${st.day_to}`}
      </p>

      {w.diseases.length > 0 && (
        <div className="cj-sheetgroup">
          <div className="cj-sheetgroup__title">
            {lang === 'mr' ? 'सध्या सक्रिय रोग' : 'Diseases firing now'}
          </div>
          {w.diseases.map(d => (
            <div key={d.id} className="cj-sheetrow">
              <span className="em">{d.em}</span>
              <div className="grow">
                <b>{bi(lang, d.name, d.name_mr)}</b>
                <div className="tiny faint">
                  {d.model && <>{d.model}</>}{d.source && <> · {d.source}</>}
                </div>
              </div>
              <span className={`badge ${BAND_TONE[d.level] || 'grey'}`}>{d.level}</span>
            </div>
          ))}
        </div>
      )}

      {w.pests.length > 0 && (
        <div className="cj-sheetgroup">
          <div className="cj-sheetgroup__title">
            {lang === 'mr' ? 'या अवस्थेतील कीड' : 'Pests at this stage'}
          </div>
          {w.pests.map(p => (
            <div key={p.id} className="cj-sheetrow">
              <span className="em">{p.em}</span>
              <div className="grow">
                <b>{bi(lang, p.name, p.name_mr)}</b>
                <div className="tiny muted">
                  {t(lang, 'etl')}: <b>{p.etl_at_this_stage}</b> {p.unit}
                  {' '}({p.etl} × {p.stage_factor})
                </div>
                {p.source && <div className="tiny faint">{t(lang, 'source')}: {p.source}</div>}
              </div>
              <span className={`badge ${BAND_TONE[p.band] || 'grey'}`}>{p.band}</span>
            </div>
          ))}
        </div>
      )}

      {!w.diseases.length && !w.pests.length && (
        <p className="small muted">
          {lang === 'mr'
            ? 'या अवस्थेसाठी प्रकाशित मर्यादा तक्त्यात नोंद नाही.'
            : 'The published threshold tables carry no entry for this stage.'}
        </p>
      )}

      <button className="btn block ghost" style={{ marginTop: 14 }}
              onClick={() => { onClose(); go('scan') }}>
        {t(lang, 'scout')}
      </button>
    </Sheet>
  )
}

/* ── history ───────────────────────────────────────────────────────────── */
const HIST_TONE = { health: 'ok', diagnosis: 'warn', trap: 'warn', application: 'info', followup: 'ok' }

function History({ cal, lang }) {
  return (
    <section className="cj-section">
      <h2 className="cj-h2">{t(lang, 'history')}</h2>
      {cal.history.length === 0
        ? <Card><p className="small muted">{t(lang, 'noHistory')}</p></Card>
        : (
          <div className="cj-hist">
            {cal.history.map((h, i) => (
              <div key={i} className={`cj-hist__row tone-${HIST_TONE[h.kind] || 'ok'}`}>
                <span className="cj-hist__date">{fmtDate(h.on, lang)}</span>
                <span className="cj-hist__em">{h.em}</span>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="cj-hist__title">{h.title}</div>
                  {h.detail && <div className="tiny faint">{h.detail}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
    </section>
  )
}
