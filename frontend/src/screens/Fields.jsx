/* PRAHARI · field registration and the Field Health Passport.

   Location can be a GPS fix, a map placement or a taluka choice — a farmer
   standing in the field gets the first, a farmer at home gets the last, and
   both are honest about which one was used. A drawn boundary yields an area,
   and that area is labelled approximate every single time it is shown. It is a
   finger on a phone screen, not a survey. */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading, Prov, Sheet, bi, fmtDate } from '../ui'

const CROPS = [
  ['tomato', 'Tomato', 'टोमॅटो'], ['grape', 'Grape', 'द्राक्ष'], ['onion', 'Onion', 'कांदा'],
  ['maize', 'Maize', 'मका'], ['cotton', 'Cotton', 'कापूस'], ['soybean', 'Soybean', 'सोयाबीन'],
  ['pigeonpea', 'Pigeonpea', 'तूर'],
]
const TALUKAS = [
  ['pimpalgaon', 'Pimpalgaon Baswant'], ['niphad', 'Niphad'], ['dindori', 'Dindori'],
  ['lasalgaon', 'Lasalgaon'], ['nashik', 'Nashik'], ['sinnar', 'Sinnar'],
  ['igatpuri', 'Igatpuri'], ['yeola', 'Yeola'], ['chandvad', 'Chandvad'], ['malegaon', 'Malegaon'],
]

export function Fields({ lang, plots, plot, onPlot, go, reload }) {
  /* ═══════════════════════════════════════════════════════════════════════
     My fields — a board, not a list.

     A farmer with one field opens the app and sees that field. A farmer with
     four had to open each in turn to find out which was in trouble, which is
     the moment an early-warning system stops warning early: the field that
     needed attention was the third one they would have checked.

     So each card carries what that field is asking for TODAY, its crop-health
     score and which way it moved, and when it was last actually looked at —
     and the server orders them by consequence, so the top card is the field to
     walk to. Every number comes from `/api/plots/board`, which composes the
     same services as that field's own screen; nothing is recomputed here.

     The plain list is still what renders while the board loads, and what
     renders if it fails. A farmer must always be able to reach their fields.
     ═══════════════════════════════════════════════════════════════════════ */
  const [board, setBoard] = useState(null)
  const [boardErr, setBoardErr] = useState(null)
  const [cycleFor, setCycleFor] = useState(null)

  useEffect(() => {
    if (!plots?.length) { setBoard(null); return }
    api.plotsBoard(lang).then(setBoard).catch(setBoardErr)
  }, [plots?.length, lang])

  const byId = Object.fromEntries((board?.fields || []).map(f => [f.plot_id, f]))
  /* Server order when the board arrived; registration order until then. */
  const ordered = board?.fields?.length
    ? board.fields.map(f => plots.find(p => p.id === f.plot_id)).filter(Boolean)
    : (plots || [])

  return (
    <>
      <div className="topbar">
        <h1 className="grow">{lang === 'mr' ? 'माझी शेते' : 'My Fields'}</h1>
        <button className="btn sm" onClick={() => go('addField')}>
          ＋ {lang === 'mr' ? 'शेत' : 'Field'}
        </button>
      </div>
      <div className="pad stack" style={{ paddingTop: 14 }}>
        {!plots?.length && (
          <Empty icon="🌾"
                 title={lang === 'mr' ? 'अजून शेत नाही' : 'No fields yet'}
                 body={lang === 'mr'
                   ? 'शेत नोंदवल्यावर प्रहरी त्या ठिकाणच्या खऱ्या हवामानावर धोका मोजू लागते. वेगवेगळ्या पिकांची अनेक शेते जोडता येतात.'
                   : 'Register a field and PRAHARI starts forecasting risk from the real weather at that exact spot. You can add as many as you farm, each with its own crop.'}
                 action={<button className="btn" onClick={() => go('addField')}>
                   {lang === 'mr' ? 'शेत जोडा' : 'Add a field'}</button>} />
        )}

        {/* One line that answers "is anything wrong anywhere" before any card
            is read. It counts; it does not characterise. */}
        {board && plots?.length > 1 && (
          <div className={'fb-summary' + (board.needs_attention ? ' is-warn' : '')}>
            <b>
              {board.needs_attention
                ? bi(lang,
                    `${board.needs_attention} of ${board.count} fields need something today`,
                    `${board.count} पैकी ${board.needs_attention} शेतांना आज लक्ष हवे`)
                : bi(lang, `All ${board.count} fields are clear today`,
                     `आज सर्व ${board.count} शेते ठीक आहेत`)}
            </b>
            <span className="tiny muted">{bi(lang, board.order, board.order_mr)}</span>
          </div>
        )}
        {board?.weather_unavailable > 0 && (
          <p className="tiny" style={{ color: 'var(--warn)' }}>
            {bi(lang,
              `${board.weather_unavailable} field(s) have no weather right now and are shown without a score. Nothing is estimated.`,
              `${board.weather_unavailable} शेतांचे हवामान उपलब्ध नाही — त्यांना गुण दिलेला नाही. काहीही अंदाजाने भरलेले नाही.`)}
          </p>
        )}
        {boardErr && plots?.length > 0 && (
          <p className="tiny muted">
            {bi(lang, 'Live status could not be loaded. Your fields are listed below.',
                      'सद्यस्थिती मिळाली नाही. तुमची शेते खाली दिली आहेत.')}
          </p>
        )}

        {ordered.map(p => (
          <FieldCard key={p.id} p={p} f={byId[p.id]} lang={lang}
                     active={p.id === plot?.id}
                     onOpen={() => { onPlot(p.id); go('home') }}
                     onNewCrop={() => setCycleFor(p)}
                     go={go} onPlot={onPlot} />
        ))}

        {plots?.length > 0 && (
          <button className="btn ghost block" onClick={() => go('addField')}>
            ＋ {bi(lang, 'Add another field', 'आणखी एक शेत जोडा')}
          </button>
        )}
        {board?.method && (
          <details className="method-fold">
            <summary>{bi(lang, 'How this board is built', 'हा बोर्ड कसा तयार होतो')}</summary>
            <p className="small muted">{bi(lang, board.method, board.method_mr)}</p>
          </details>
        )}
      </div>

      <NewCropSheet plot={cycleFor} lang={lang} onClose={() => setCycleFor(null)}
                    onDone={() => {
                      setCycleFor(null)
                      reload?.()
                      api.plotsBoard(lang).then(setBoard).catch(() => {})
                    }} />
    </>
  )
}

/* ── a new crop in the same field ───────────────────────────────────────────
   A farmer who harvests tomato and sows onion in the same plot has not
   acquired a new field. The endpoint for this existed and nothing reached it,
   so the only way to record a changed crop was to register the field twice —
   which splits its history in half and quietly ends the passport.

   Starting a cycle closes the running one and keeps every record attached to
   the field. That is the whole point: the passport outlives the crop. The
   sheet says so, because "start a new crop" reads like something destructive
   and is not.
   ═══════════════════════════════════════════════════════════════════════════ */
function NewCropSheet({ plot, lang, onClose, onDone }) {
  const [crop, setCrop] = useState('tomato')
  const [sownOn, setSownOn] = useState(new Date().toISOString().slice(0, 10))
  const [variety, setVariety] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!plot) return
    setErr(null); setBusy(false); setVariety('')
    /* Default to something OTHER than what is growing now: a farmer opening
       this sheet is changing the crop, so pre-selecting the current one is
       one more tap for the least likely answer. */
    setCrop(CROPS.find(c => c[0] !== plot.crop)?.[0] || 'tomato')
    setSownOn(new Date().toISOString().slice(0, 10))
  }, [plot?.id])

  /* The crop name inside a Marathi sentence has to be the Marathi one; the
     plot's own `crop_label` is always English. */
  const current = CROPS.find(c => c[0] === plot?.crop)
  const currentLabel = bi(lang, current?.[1] || plot?.crop, current?.[2])

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      await api.newCycle(plot.id, {
        crop, sown_on: sownOn, variety: variety || undefined, end_previous: true,
      })
      onDone()
    } catch (e) { setErr(e); setBusy(false) }
  }

  return (
    <Sheet open={!!plot} onClose={onClose}
           title={bi(lang, 'Start a new crop', 'नवीन पीक सुरू करा')}>
      {plot && (
        <div className="stack">
          <p className="small muted">
            {bi(lang,
              `${plot.name} is currently ${currentLabel}. Starting a new crop closes that season and begins a new one — every scan, count, spray and diagnosis stays attached to this field.`,
              `${plot.name} मध्ये सध्या ${currentLabel} आहे. नवीन पीक सुरू केल्यास तो हंगाम बंद होतो — पण या शेताच्या सर्व नोंदी तशाच राहतात.`)}
          </p>

          {err && <ErrorNote error={err} lang={lang} />}

          <div>
            <span className="lbl">{bi(lang, 'Crop', 'पीक')}</span>
            <div className="nc-crops">
              {CROPS.map(([id, en, mr]) => (
                <button key={id} type="button"
                        className={'nc-crop' + (crop === id ? ' is-on' : '')}
                        onClick={() => setCrop(id)}>
                  {bi(lang, en, mr)}
                </button>
              ))}
            </div>
          </div>

          <label className="field">
            <span className="lbl">{bi(lang, 'Sown on', 'पेरणीची तारीख')}</span>
            <input className="input" type="date" value={sownOn}
                   max={new Date().toISOString().slice(0, 10)}
                   onChange={e => setSownOn(e.target.value)} />
            <span className="hint">
              {bi(lang, 'The crop stage, and every threshold that depends on it, is counted from this date.',
                        'पीक अवस्था आणि त्यावर अवलंबून सर्व उंबरठे याच तारखेपासून मोजले जातात.')}
            </span>
          </label>

          <label className="field">
            <span className="lbl">{bi(lang, 'Variety (optional)', 'वाण (ऐच्छिक)')}</span>
            <input className="input" value={variety} onChange={e => setVariety(e.target.value)}
                   placeholder={bi(lang, 'e.g. Abhinav', 'उदा. अभिनव')} />
          </label>

          <button className="btn block" disabled={busy || !sownOn} onClick={submit}>
            {busy ? '…' : bi(lang, 'Start this crop', 'हे पीक सुरू करा')}
          </button>
          <button className="btn quiet block" onClick={onClose}>
            {bi(lang, 'Cancel', 'रद्द करा')}
          </button>
        </div>
      )}
    </Sheet>
  )
}

/* One field, as much of its live state as the server could produce. */
function FieldCard({ p, f, lang, active, onOpen, onNewCrop, go, onPlot }) {
  const tone = f?.attention || 'none'
  const arrow = f?.trend?.direction
  return (
    <Card className={'fb-card tappable' + (active ? ' is-active' : '')} onClick={onOpen}>
      <div className="fb-card__head">
        <span className="fb-card__em">{f?.crop_em || '🌱'}</span>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="card-title">{p.name}</div>
          <div className="small muted">
            {bi(lang, f?.crop_label || p.crop_label || p.crop, f?.crop_label_mr)}
            {' · '}{p.area_acre} {lang === 'mr' ? 'एकर' : 'acres'}
            {p.taluka_name ? ` · ${p.taluka_name}` : ''}
          </div>
        </div>
        {f?.score != null ? (
          <div className={`fb-score ${f.band || ''}`}>
            <b>{f.score}</b>
            {arrow && arrow !== 'steady' && (
              <span className={`fb-trend ${arrow === 'up' ? 'good' : 'bad'}`}>
                {arrow === 'up' ? '▲' : '▼'}{Math.abs(f.trend.delta)}
              </span>
            )}
          </div>
        ) : (
          <span className="fb-score fb-score--none">—</span>
        )}
      </div>

      {f?.crop_stage?.label && (
        <div className="fb-stage">
          {bi(lang, f.crop_stage.label, f.crop_stage.label_mr)}
          {f.crop_stage.days != null && (
            <span className="muted">
              {' · '}{lang === 'mr'
                ? `पेरणीनंतर ${f.crop_stage.days} दिवस`
                : `day ${f.crop_stage.days}`}
            </span>
          )}
          {p.sown_on && (
            <span className="muted">
              {' · '}{lang === 'mr' ? 'पेरणी ' : 'sown '}{fmtDate(p.sown_on, lang)}
            </span>
          )}
        </div>
      )}

      {/* What this field is asking for. At most two — the rest are on its own
          screen, and a board that lists everything is a board nobody scans. */}
      {f?.items?.length > 0 && (
        <ul className={`fb-items tone-${tone}`}>
          {f.items.map((it, i) => (
            <li key={i}><span>{it.icon}</span>{bi(lang, it.title, it.title_mr)}</li>
          ))}
          {f.item_count > f.items.length && (
            <li className="fb-items__more">
              +{f.item_count - f.items.length} {bi(lang, 'more', 'आणखी')}
            </li>
          )}
        </ul>
      )}
      {f && f.all_clear && !f.items?.length && (
        <p className="fb-clear">✓ {bi(lang, 'Nothing needed today', 'आज काही करण्याची गरज नाही')}</p>
      )}
      {f?.unavailable && (
        <p className="fb-unavailable">{f.unavailable}</p>
      )}

      <div className="fb-card__foot">
        <span className="tiny muted">
          {f?.last_seen
            ? bi(lang,
                `Last ${f.last_seen.kind} ${f.last_seen.days_ago === 0 ? 'today'
                  : f.last_seen.days_ago === 1 ? 'yesterday'
                  : `${f.last_seen.days_ago} days ago`}`,
                `शेवटची तपासणी ${f.last_seen.days_ago === 0 ? 'आज'
                  : `${f.last_seen.days_ago} दिवसांपूर्वी`}`)
            : bi(lang, 'Not scouted yet', 'अजून तपासणी नाही')}
        </span>
        <span className="fb-actions">
          <button className="btn sm quiet"
                  onClick={(e) => { e.stopPropagation(); onPlot(p.id); go('crop') }}>
            {bi(lang, 'Journey', 'प्रवास')}
          </button>
          <button className="btn sm quiet"
                  onClick={(e) => { e.stopPropagation(); onPlot(p.id); go('traps') }}>
            {bi(lang, 'Traps', 'सापळे')}
          </button>
          <button className="btn sm quiet"
                  onClick={(e) => { e.stopPropagation(); onPlot(p.id); go('history') }}>
            {bi(lang, 'History', 'इतिहास')}
          </button>
          <button className="btn sm quiet"
                  onClick={(e) => { e.stopPropagation(); onNewCrop() }}>
            {bi(lang, 'New crop', 'नवीन पीक')}
          </button>
        </span>
      </div>
      {p.area_note && <Prov label="Area" value={p.area_note} />}
    </Card>
  )
}

/* ── registration ──────────────────────────────────────────────────────── */
export function AddField({ lang, go, reload }) {
  const [f, setF] = useState({
    crop: 'tomato', area_acre: '1', location_source: 'manual',
    sown_on: new Date().toISOString().slice(0, 10),
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [geo, setGeo] = useState(null)
  const set = (k) => (e) => setF(x => ({ ...x, [k]: e.target.value }))

  const locate = () => {
    setGeo('working')
    navigator.geolocation?.getCurrentPosition(
      pos => {
        setF(x => ({
          ...x, lat: Number(pos.coords.latitude.toFixed(6)),
          lng: Number(pos.coords.longitude.toFixed(6)), location_source: 'gps',
        }))
        setGeo({ accuracy: Math.round(pos.coords.accuracy) })
      },
      () => setGeo('failed'),
      { enableHighAccuracy: true, timeout: 12000 })
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const body = {
        name: f.name, crop: f.crop, area_acre: Number(f.area_acre),
        sown_on: f.sown_on, location_source: f.location_source,
        variety: f.variety || undefined, soil: f.soil || undefined,
        irrigation: f.irrigation || undefined,
        tank_litres: f.tank_litres ? Number(f.tank_litres) : 15,
      }
      if (f.lat != null && f.lng != null) { body.lat = f.lat; body.lng = f.lng }
      if (f.taluka) body.taluka = f.taluka
      if (f.village) body.village = f.village
      const out = await api.createPlot(body)
      await reload(out.id)
      go('home')
    } catch (e2) { setErr(e2) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('fields')} aria-label="Back">‹</button>
        <h1 className="grow">{lang === 'mr' ? 'शेत जोडा' : 'Add a field'}</h1>
      </div>
      <form className="pad" style={{ paddingTop: 16 }} onSubmit={submit}>
        <Card>
          <label className="field">
            <span className="lbl">{lang === 'mr' ? 'शेताचे नाव' : 'Field name'}</span>
            <input className="input" required value={f.name || ''} onChange={set('name')}
                   placeholder={lang === 'mr' ? 'उदा. टोमॅटो प्लॉट १' : 'e.g. Tomato block 1'} />
          </label>

          <div className="grid2">
            <label className="field">
              <span className="lbl">{lang === 'mr' ? 'पीक' : 'Crop'}</span>
              <select className="input" value={f.crop} onChange={set('crop')}>
                {CROPS.map(([id, en, mr]) => <option key={id} value={id}>{lang === 'mr' ? mr : en}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="lbl">{lang === 'mr' ? 'क्षेत्र (एकर)' : 'Area (acres)'}</span>
              <input className="input" type="number" min="0.1" step="0.1" required
                     value={f.area_acre} onChange={set('area_acre')} />
            </label>
          </div>

          <div className="grid2">
            <label className="field">
              <span className="lbl">{lang === 'mr' ? 'पेरणीची तारीख' : 'Sowing date'}</span>
              <input className="input" type="date" required value={f.sown_on} onChange={set('sown_on')}
                     max={new Date().toISOString().slice(0, 10)} />
            </label>
            <label className="field">
              <span className="lbl">{lang === 'mr' ? 'वाण (ऐच्छिक)' : 'Variety (optional)'}</span>
              <input className="input" value={f.variety || ''} onChange={set('variety')} />
            </label>
          </div>
        </Card>

        <Card style={{ marginTop: 14 }}>
          <div className="card-title" style={{ marginBottom: 4 }}>
            {lang === 'mr' ? 'शेताचे ठिकाण' : 'Where is the field?'}
          </div>
          <p className="small muted" style={{ marginBottom: 12 }}>
            {lang === 'mr'
              ? 'प्रहरी याच ठिकाणचे खरे हवामान वापरून धोका मोजते. शेतात उभे असाल तर GPS सर्वात अचूक.'
              : 'PRAHARI forecasts risk from the real weather at this exact spot. GPS is best if you are standing in the field.'}
          </p>

          <button type="button" className="btn ghost block" onClick={locate} disabled={geo === 'working'}>
            📍 {geo === 'working'
              ? (lang === 'mr' ? 'ठिकाण शोधत आहे…' : 'Finding your location…')
              : (lang === 'mr' ? 'माझे सध्याचे ठिकाण वापरा' : 'Use my current location')}
          </button>

          {f.lat != null && (
            <div className="note" style={{ marginTop: 10 }}>
              ✓ {lang === 'mr' ? 'ठिकाण नोंदले' : 'Location captured'}: <span className="mono">{f.lat}, {f.lng}</span>
              {geo?.accuracy && <div className="tiny faint" style={{ marginTop: 3 }}>
                {lang === 'mr' ? `अचूकता सुमारे ${geo.accuracy} मीटर` : `Accurate to about ${geo.accuracy} m`}
              </div>}
            </div>
          )}
          {geo === 'failed' && (
            <div className="note warn" style={{ marginTop: 10 }}>
              {lang === 'mr'
                ? 'ठिकाण मिळाले नाही. खाली तालुका निवडा — प्रहरी तालुका केंद्राचे हवामान वापरेल.'
                : 'Could not get a location. Choose a taluka below — PRAHARI will use the taluka centroid instead, and will say so.'}
            </div>
          )}

          <label className="field" style={{ marginTop: 14 }}>
            <span className="lbl">{lang === 'mr' ? 'तालुका' : 'Taluka'}</span>
            <select className="input" value={f.taluka || ''} onChange={set('taluka')}>
              <option value="">{lang === 'mr' ? 'माझ्या खात्याचा तालुका' : 'Use my account taluka'}</option>
              {TALUKAS.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
          <label className="field">
            <span className="lbl">{lang === 'mr' ? 'गाव (ऐच्छिक)' : 'Village (optional)'}</span>
            <input className="input" value={f.village || ''} onChange={set('village')} />
          </label>
        </Card>

        <Card style={{ marginTop: 14 }}>
          <div className="card-title" style={{ marginBottom: 10 }}>
            {lang === 'mr' ? 'शेतीची माहिती (ऐच्छिक)' : 'Farming details (optional)'}
          </div>
          <div className="grid2">
            <label className="field">
              <span className="lbl">{lang === 'mr' ? 'जमीन' : 'Soil'}</span>
              <select className="input" value={f.soil || ''} onChange={set('soil')}>
                <option value="">—</option>
                <option value="medium black">Medium black</option>
                <option value="deep black">Deep black</option>
                <option value="light">Light / murmad</option>
                <option value="alluvial">Alluvial</option>
              </select>
            </label>
            <label className="field">
              <span className="lbl">{lang === 'mr' ? 'सिंचन' : 'Irrigation'}</span>
              <select className="input" value={f.irrigation || ''} onChange={set('irrigation')}>
                <option value="">—</option>
                <option value="drip">Drip</option>
                <option value="sprinkler">Sprinkler</option>
                <option value="flood">Flood</option>
                <option value="rainfed">Rainfed</option>
              </select>
            </label>
          </div>
          <label className="field">
            <span className="lbl">{lang === 'mr' ? 'तुमच्या पंपाची क्षमता (लिटर)' : 'Your knapsack sprayer (litres)'}</span>
            <input className="input" type="number" min="5" max="200" value={f.tank_litres || 15}
                   onChange={set('tank_litres')} />
            <span className="hint">
              {lang === 'mr'
                ? 'मात्रा याच पंपाच्या हिशेबात सांगितली जाईल.'
                : 'Doses are worked out in your own tank size, not in litres per hectare.'}
            </span>
          </label>
        </Card>

        {err && <div style={{ marginTop: 14 }}><ErrorNote error={err} lang={lang} /></div>}

        <button className="btn block" style={{ marginTop: 16 }} disabled={busy} type="submit">
          {busy ? '…' : (lang === 'mr' ? 'शेत नोंदवा' : 'Register field')}
        </button>
      </form>
    </>
  )
}

/* ── Field Health Passport ─────────────────────────────────────────────── */
export function History({ lang, plot, go }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    if (!plot) return
    api.history(plot.id).then(setData).catch(setErr)
  }, [plot?.id])

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{lang === 'mr' ? 'शेत आरोग्य पासपोर्ट' : 'Field Health Passport'}</h1>
      </div>
      <div className="pad stack" style={{ paddingTop: 14 }}>
        {!data && !err && <Loading lines={4} />}
        {err && <ErrorNote error={err} lang={lang} />}
        {data && (
          <>
            <Card>
              <div className="card-title">{data.plot.name}</div>
              <div className="small muted" style={{ marginTop: 3 }}>
                {data.plot.crop_label || data.plot.crop} · {data.plot.area_acre} acres · {data.plot.taluka_name}
              </div>
              {data.health_scores?.length > 1 && (
                <div style={{ marginTop: 14 }}>
                  <div className="tiny muted" style={{ marginBottom: 6 }}>
                    {lang === 'mr' ? 'पीक आरोग्य गुण' : 'Crop health score over time'}
                  </div>
                  <ScoreLine scores={data.health_scores} />
                </div>
              )}
            </Card>

            {data.timeline?.length > 0 ? (
              <Card>
                <div className="card-title" style={{ marginBottom: 12 }}>
                  {lang === 'mr' ? 'या शेतात काय घडले' : 'Everything that happened to this field'}
                </div>
                <div className="tl">
                  {data.timeline.map(e => (
                    <div className={`tl-item ${e.severity}`} key={e.id}>
                      <div className="tl-date">{fmtDate(e.at, lang)}</div>
                      <div className="tl-title">{bi(lang, e.title, e.title_mr)}</div>
                      {e.detail && <div className="tl-detail">{bi(lang, e.detail, e.detail_mr)}</div>}
                    </div>
                  ))}
                </div>
              </Card>
            ) : (
              <Empty icon="📋" title={lang === 'mr' ? 'अजून काही नोंदी नाहीत' : 'Nothing recorded yet'} />
            )}

            <Prov label="Note" value={data.note} />
          </>
        )}
      </div>
    </>
  )
}

function ScoreLine({ scores }) {
  const pts = scores.map(s => s.score)
  const w = 320, h = 70, pad = 5
  const x = (i) => pad + (i * (w - pad * 2)) / Math.max(1, pts.length - 1)
  const y = (v) => h - pad - (v / 100) * (h - pad * 2)
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: h }} preserveAspectRatio="none">
      <line x1={pad} x2={w - pad} y1={y(70)} y2={y(70)} stroke="var(--rule)" strokeDasharray="3 3" />
      <path d={`${d} L${x(pts.length - 1)} ${h - pad} L${x(0)} ${h - pad} Z`} fill="var(--g-500)" opacity=".10" />
      <path d={d} fill="none" stroke="var(--g-600)" strokeWidth="2.2" strokeLinejoin="round" />
      {pts.map((p, i) => <circle key={i} cx={x(i)} cy={y(p)} r="2.6" fill="var(--g-600)" />)}
    </svg>
  )
}
