/* PRAHARI · field registration and the Field Health Passport.

   Location can be a GPS fix, a map placement or a taluka choice — a farmer
   standing in the field gets the first, a farmer at home gets the last, and
   both are honest about which one was used. A drawn boundary yields an area,
   and that area is labelled approximate every single time it is shown. It is a
   finger on a phone screen, not a survey. */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading, Prov, bi, fmtDate } from '../ui'

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
                   ? 'शेत नोंदवल्यावर प्रहरी त्या ठिकाणच्या खऱ्या हवामानावर धोका मोजू लागते.'
                   : 'Register a field and PRAHARI starts forecasting risk from the real weather at that exact spot.'}
                 action={<button className="btn" onClick={() => go('addField')}>
                   {lang === 'mr' ? 'शेत जोडा' : 'Add a field'}</button>} />
        )}
        {plots?.map(p => (
          <Card key={p.id} onClick={() => { onPlot(p.id); go('home') }}
                style={{ cursor: 'pointer', borderColor: p.id === plot?.id ? 'var(--g-300)' : undefined }}>
            <div className="row between">
              <div className="grow">
                <div className="card-title">{p.name}</div>
                <div className="small muted" style={{ marginTop: 2 }}>
                  {p.crop_label || p.crop} · {p.area_acre} {lang === 'mr' ? 'एकर' : 'acres'} · {p.taluka_name}
                </div>
                <div className="tiny faint" style={{ marginTop: 4 }}>
                  {p.crop_stage?.label && <>{p.crop_stage.label} · day {p.crop_stage.days} · </>}
                  {lang === 'mr' ? 'पेरणी' : 'sown'} {fmtDate(p.sown_on, lang)}
                </div>
              </div>
              <div style={{ fontSize: 20, color: 'var(--faint)' }}>›</div>
            </div>
            {p.area_note && <Prov label="Area" value={p.area_note} />}
            <div className="row" style={{ gap: 8, marginTop: 12 }}>
              <button className="btn sm quiet grow" onClick={(e) => { e.stopPropagation(); onPlot(p.id); go('history') }}>
                📋 {lang === 'mr' ? 'इतिहास' : 'History'}
              </button>
              <button className="btn sm quiet grow" onClick={(e) => { e.stopPropagation(); onPlot(p.id); go('traps') }}>
                🪤 {lang === 'mr' ? 'सापळे' : 'Traps'}
              </button>
            </div>
          </Card>
        ))}
      </div>
    </>
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
