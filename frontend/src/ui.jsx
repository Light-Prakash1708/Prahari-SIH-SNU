/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · UI primitives

   Every chart here is hand-drawn SVG. No charting library: the farmer app has
   to open on a 2G connection on a phone with 2 GB of RAM, and a 300 kB bundle
   to draw six data points is a tax that user pays every single time.

   Two rules the components enforce rather than document:

   · Colour is never the only carrier of a state. Every risk band ships with a
     word next to it. Roughly one in twelve men in this user base cannot
     separate the red from the green.
   · Anything a farmer might act on carries its provenance. <Prov> is not
     decoration; it is where "who says so" lives.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useEffect, useRef, useState } from 'react'

/* ── the mark ──────────────────────────────────────────────────────────── */
export const Shield = ({ size = 34, tone = '#157A3C', leaf = '#8BD3A4' }) => (
  <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label="PRAHARI">
    <path d="M20 2 L35 8 V20 C35 29 28.5 35.5 20 38 C11.5 35.5 5 29 5 20 V8 Z"
          fill={tone} />
    <path d="M20 4.6 L32.6 9.6 V20 C32.6 27.6 27.2 33.3 20 35.5 C12.8 33.3 7.4 27.6 7.4 20 V9.6 Z"
          fill="none" stroke="rgba(255,255,255,.32)" strokeWidth="1.1" />
    <path d="M26 13.5c0 7-4.6 11.4-10.6 12.2-.6-6.2 3.2-11.4 10.6-12.2Z" fill={leaf} />
    <path d="M25.2 14.4c-4.4 2.4-7.4 6-9.2 10.9" fill="none"
          stroke={tone} strokeWidth="1.3" strokeLinecap="round" opacity=".55" />
  </svg>
)

/* ── i18n ──────────────────────────────────────────────────────────────── */
export const L = {
  mr: {
    home: 'मुख्यपृष्ठ', fields: 'शेते', scan: 'स्कॅन', alerts: 'सूचना', profile: 'प्रोफाइल',
    health: 'पीक आरोग्य', whatsChanging: 'काय बदलले?', quickActions: 'त्वरित कृती',
    scanCrop: 'पीक स्कॅन', pestTrap: 'कीड सापळा', shouldISpray: 'फवारणी करू का?',
    advisory: 'सल्ला', forecast: 'पुढील अंदाज', why: 'का?', seeDetails: 'तपशील पहा',
    diagnosis: 'निदान', confidence: 'खात्री', alternatives: 'इतर शक्यता',
    evidence: 'पुरावा', whatsNext: 'पुढे काय?', viewManagement: 'व्यवस्थापन पहा',
    signIn: 'साइन इन', signUp: 'नोंदणी करा', signOut: 'साइन आउट',
    mobile: 'मोबाइल क्रमांक', password: 'पासवर्ड', name: 'नाव', village: 'गाव', taluka: 'तालुका',
    addField: 'शेत जोडा', crop: 'पीक', area: 'क्षेत्र (एकर)', sowing: 'पेरणीची तारीख',
    save: 'जतन करा', cancel: 'रद्द', retake: 'पुन्हा फोटो', sendExpert: 'तज्ज्ञांकडे पाठवा',
    count: 'मोजणी', recheck: 'पुन्हा तपासा', loading: 'लोड होत आहे…',
    offline: 'ऑफलाइन', synced: 'सिंक झाले', timeline: 'शेताचा इतिहास',
    riskForecast: 'धोक्याचा अंदाज', ipm: 'एकात्मिक कीड व्यवस्थापन', expert: 'तज्ज्ञ',
  },
  en: {
    home: 'Home', fields: 'Fields', scan: 'Scan', alerts: 'Alerts', profile: 'Profile',
    health: 'Crop Health', whatsChanging: "What's Changing?", quickActions: 'Quick Actions',
    scanCrop: 'Scan Crop', pestTrap: 'Pest Trap', shouldISpray: 'Should I Spray?',
    advisory: 'Advisory', forecast: 'Forecast', why: 'Why?', seeDetails: 'See Details',
    diagnosis: 'Diagnosis', confidence: 'Confidence', alternatives: 'Alternative Possibilities',
    evidence: 'Evidence Found', whatsNext: "What's Next?", viewManagement: 'View Management',
    signIn: 'Sign in', signUp: 'Create account', signOut: 'Sign out',
    mobile: 'Mobile number', password: 'Password', name: 'Full name', village: 'Village', taluka: 'Taluka',
    addField: 'Add a field', crop: 'Crop', area: 'Area (acres)', sowing: 'Sowing date',
    save: 'Save', cancel: 'Cancel', retake: 'Take another photo', sendExpert: 'Send to an expert',
    count: 'Count', recheck: 'Re-check', loading: 'Loading…',
    offline: 'Offline', synced: 'Synced', timeline: 'Field history',
    riskForecast: 'Risk Forecast', ipm: 'IPM Recommendations', expert: 'Expert',
  },
}
L.hi = { ...L.en }
export const t = (lang, key) => (L[lang] || L.en)[key] || (L.en[key] || key)

/* pick the Marathi string when the farmer reads Marathi and one exists */
export const bi = (lang, en, mr) => (lang === 'mr' && mr) ? mr : en

/* ── layout ────────────────────────────────────────────────────────────── */
export const Card = ({ children, className = '', ...rest }) =>
  <section className={`card ${className}`} {...rest}>{children}</section>

export const Row = ({ children, between, className = '', ...rest }) =>
  <div className={`row ${between ? 'between' : ''} ${className}`} {...rest}>{children}</div>

export const Section = ({ title, action, children }) => (
  <>
    <div className="row between">
      <h2 className="sect-title" style={{ margin: '22px 0 10px' }}>{title}</h2>
      {action}
    </div>
    {children}
  </>
)

/* ── states ────────────────────────────────────────────────────────────── */
export const Loading = ({ lines = 3, label }) => (
  <div className="stack" aria-live="polite" aria-busy="true">
    <span className="sr">{label || 'Loading'}</span>
    {Array.from({ length: lines }).map((_, i) =>
      <div key={i} className="skel" style={{ height: i === 0 ? 92 : 58 }} />)}
  </div>
)

export const ErrorNote = ({ error, lang = 'en', onRetry }) => {
  if (!error) return null
  const msg = error.say ? error.say(lang) : (error.message || String(error))
  const tone = error.code === 'weather_unavailable' ? 'info'
    : (error.status === 403 || error.status === 401) ? 'warn' : 'bad'
  const PHOTO = ['not_an_image', 'unsupported_image_format', 'file_too_large',
                 'image_too_large_dimensions', 'image_too_small', 'empty_upload']
  const head = error.code === 'weather_unavailable' ? '🌦 Weather unavailable'
    : PHOTO.includes(error.code) ? '📷 That photo cannot be used'
    : error.code === 'no_verified_claim' ? '🧪 No verified recommendation'
    : error.code === 'chemical_not_authorised' ? '🛡️ Not authorised yet'
    : error.status === 403 ? '🔒 Not permitted'
    : error.status === 429 ? '⏳ Too many requests'
    : error.status === 0 ? '📴 Offline' : '⚠ Something went wrong'
  return (
    <div className={`note ${tone}`} role="alert">
      <div style={{ fontWeight: 700, marginBottom: 3 }}>{head}</div>
      <div>{msg}</div>
      {error.detail?.reason && <div className="tiny faint" style={{ marginTop: 5 }}>{error.detail.reason}</div>}
      {onRetry && error.retryable !== false && (
        <button className="btn sm ghost" style={{ marginTop: 10 }} onClick={onRetry}>Try again</button>
      )}
    </div>
  )
}

export const Empty = ({ icon = '🌱', title, body, action }) => (
  <div className="empty">
    <div className="ic">{icon}</div>
    <div className="h3" style={{ marginTop: 8 }}>{title}</div>
    {body && <p className="small muted" style={{ marginTop: 6, maxWidth: 320, marginInline: 'auto' }}>{body}</p>}
    {action && <div style={{ marginTop: 16 }}>{action}</div>}
  </div>
)

/* ── provenance ────────────────────────────────────────────────────────── */
export const Prov = ({ label = 'Source', value, url, extra }) => {
  if (!value) return null
  return (
    <p className="prov"><b>{label}:</b> {value}{extra ? ` · ${extra}` : ''}
      {url && <> · <a href={url} target="_blank" rel="noreferrer" style={{ textDecoration: 'underline' }}>reference</a></>}
    </p>
  )
}

/* ── a disclosure that keeps model detail off the farmer's main path ───── */
export const Why = ({ label = 'Why?', children, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{ marginTop: 10 }}>
      <button className="btn sm quiet" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        {open ? '▴' : '▾'} {label}
      </button>
      {open && <div className="note" style={{ marginTop: 9 }}>{children}</div>}
    </div>
  )
}

/* ── badges ────────────────────────────────────────────────────────────── */
const BAND_TONE = {
  safe: 'ok', low: 'ok', good: 'ok', watch: 'info', moderate: 'warn',
  rising: 'warn', high: 'bad', critical: 'bad',
}
export const Band = ({ band, label }) =>
  <span className={`badge ${BAND_TONE[band] || 'grey'}`}>{label || band}</span>

export const Badge = ({ tone = 'grey', children }) => <span className={`badge ${tone}`}>{children}</span>

/* ── gauge (Farm Health Score) ─────────────────────────────────────────── */
export function Gauge({ value = 0, size = 92, stroke = 9, band = 'safe' }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, value)) / 100
  const color = { safe: 'var(--ok)', watch: 'var(--g-400)', rising: 'var(--warn)', high: 'var(--bad)' }[band] || 'var(--ok)'
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
         aria-label={`Crop health score ${Math.round(value)} out of 100`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--rule-soft)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
              strokeLinecap="round" strokeDasharray={`${c * pct} ${c}`}
              transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  )
}

/* ── sparkline / trend line ────────────────────────────────────────────── */
export function Spark({ points = [], width = 300, height = 76, color = 'var(--bad)',
                        fill = true, threshold = null }) {
  if (!points.length) return <div className="small faint">No series recorded yet.</div>
  const pad = 6
  const max = Math.max(...points, threshold || 0) || 1
  const min = Math.min(...points, 0)
  const span = (max - min) || 1
  const x = (i) => pad + (i * (width - pad * 2)) / Math.max(1, points.length - 1)
  const y = (v) => height - pad - ((v - min) / span) * (height - pad * 2)
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p).toFixed(1)}`).join(' ')
  const area = `${d} L${x(points.length - 1).toFixed(1)} ${height - pad} L${x(0).toFixed(1)} ${height - pad} Z`
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"
         style={{ height }} role="img" aria-label={`Trend: ${points.join(', ')}`}>
      {fill && <path d={area} fill={color} opacity=".10" />}
      {threshold != null && (
        <line x1={pad} x2={width - pad} y1={y(threshold)} y2={y(threshold)}
              stroke="var(--ink)" strokeWidth="1" strokeDasharray="4 3" opacity=".45" />
      )}
      <path d={d} fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
      {points.map((p, i) => <circle key={i} cx={x(i)} cy={y(p)} r="3" fill={color} />)}
    </svg>
  )
}

/* ── bar series (trap counts) ──────────────────────────────────────────── */
export function Bars({ data = [], threshold = null, height = 96 }) {
  if (!data.length) return <div className="small faint">No counts recorded yet.</div>
  const max = Math.max(...data.map(d => d.value), threshold || 0) || 1
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height, position: 'relative' }}>
        {threshold != null && (
          <div style={{
            position: 'absolute', left: 0, right: 0, bottom: `${(threshold / max) * 100}%`,
            borderTop: '2px dashed var(--bad)', opacity: .55,
          }} />
        )}
        {data.map((d, i) => (
          <div key={i} style={{ flex: 1, display: 'grid', alignContent: 'end', gap: 4 }}>
            <div style={{
              height: `${Math.max(3, (d.value / max) * 100)}%`, borderRadius: '5px 5px 0 0',
              background: (threshold != null && d.value >= threshold)
                ? 'linear-gradient(180deg, var(--bad), #E5716B)'
                : 'linear-gradient(180deg, var(--g-500), var(--g-400))',
            }} title={`${d.label}: ${d.value}`} />
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 5 }}>
        {data.map((d, i) => (
          <div key={i} style={{ flex: 1, textAlign: 'center' }} className="tiny faint">{d.label}</div>
        ))}
      </div>
    </div>
  )
}

/* ── donut ─────────────────────────────────────────────────────────────── */
const DONUT = ['#34A45C', '#E5A13B', '#4C8FD6', '#C0574C', '#7E6BC4', '#3FA5A0']
export function Donut({ data = [], size = 118, thickness = 22 }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1
  const r = (size - thickness) / 2
  const c = 2 * Math.PI * r
  let acc = 0
  return (
    <div className="row" style={{ gap: 16, alignItems: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flex: 'none' }}>
        {data.map((d, i) => {
          const frac = d.value / total
          const el = (
            <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none"
                    stroke={d.color || DONUT[i % DONUT.length]} strokeWidth={thickness}
                    strokeDasharray={`${c * frac} ${c}`} strokeDashoffset={-c * acc}
                    transform={`rotate(-90 ${size / 2} ${size / 2})`} />
          )
          acc += frac
          return el
        })}
      </svg>
      <div className="grow" style={{ display: 'grid', gap: 6 }}>
        {data.map((d, i) => (
          <div key={i} className="row between" style={{ fontSize: 12 }}>
            <span><i style={{
              width: 9, height: 9, borderRadius: 2, display: 'inline-block', marginRight: 7,
              background: d.color || DONUT[i % DONUT.length],
            }} />{d.label}</span>
            <b>{Math.round((d.value / total) * 100)}%</b>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── segmented control ─────────────────────────────────────────────────── */
export const Seg = ({ options, value, onChange }) => (
  <div className="seg" role="tablist">
    {options.map(o => (
      <button key={o.value} role="tab" aria-pressed={value === o.value}
              onClick={() => onChange(o.value)}>{o.label}</button>
    ))}
  </div>
)

export const Chips = ({ options, value, onChange }) => (
  <div className="chips">
    {options.map(o => (
      <button key={o.value} className="chip" aria-pressed={value === o.value}
              onClick={() => onChange(o.value)}>{o.label}</button>
    ))}
  </div>
)

/* ── bottom sheet ──────────────────────────────────────────────────────── */
export function Sheet({ open, onClose, title, children }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="scrim" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="sheet-grip" />
        {title && (
          <div className="row between" style={{ marginBottom: 12 }}>
            <h2 className="h2">{title}</h2>
            <button onClick={onClose} aria-label="Close"
                    style={{ background: 'var(--sunk)', width: 34, height: 34, borderRadius: '50%' }}>✕</button>
          </div>
        )}
        {children}
      </div>
    </div>
  )
}

/* ── camera ────────────────────────────────────────────────────────────── */
export function Camera({ onCapture, onClose, title = 'Scan Crop', tips, lang = 'en' }) {
  const videoRef = useRef(null)
  const fileRef = useRef(null)
  const streamRef = useRef(null)
  const [err, setErr] = useState(null)
  const [preview, setPreview] = useState(null)

  useEffect(() => {
    let active = true
    navigator.mediaDevices?.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1600 } },
    })
      .then(s => {
        if (!active) { s.getTracks().forEach(x => x.stop()); return }
        streamRef.current = s
        if (videoRef.current) { videoRef.current.srcObject = s; videoRef.current.play().catch(() => {}) }
      })
      .catch(() => setErr('camera'))
    return () => { active = false; streamRef.current?.getTracks().forEach(x => x.stop()) }
  }, [])

  const stop = () => streamRef.current?.getTracks().forEach(x => x.stop())

  const shoot = () => {
    const v = videoRef.current
    if (!v || !v.videoWidth) { fileRef.current?.click(); return }
    const side = Math.min(v.videoWidth, v.videoHeight)
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = Math.min(1400, side)
    const ctx = canvas.getContext('2d')
    ctx.drawImage(v, (v.videoWidth - side) / 2, (v.videoHeight - side) / 2, side, side,
                  0, 0, canvas.width, canvas.height)
    canvas.toBlob(b => {
      if (!b) return
      setPreview(URL.createObjectURL(b))
      stop()
      onCapture(new File([b], 'scan.jpg', { type: 'image/jpeg' }))
    }, 'image/jpeg', 0.92)
  }

  const pick = (e) => {
    const f = e.target.files?.[0]
    if (f) { setPreview(URL.createObjectURL(f)); stop(); onCapture(f) }
  }

  const DEFAULT_TIPS = lang === 'mr'
    ? ['चांगला नैसर्गिक उजेड', 'बाधित भागाचा फोटो घ्या', 'एकच पान चौकटीत भरा']
    : ['Good natural light', 'Capture the affected part', 'Fill the frame with one leaf']

  return (
    <div className="cam">
      <div className="cam-top">
        <button className="hdr-back" onClick={() => { stop(); onClose() }} aria-label="Back">‹</button>
        <div className="grow" style={{ textAlign: 'center', fontWeight: 700, fontSize: 16 }}>{title}</div>
        <div className="hdr-back" style={{ opacity: 0 }} aria-hidden>?</div>
      </div>
      <div className="cam-view">
        {preview
          ? <img src={preview} alt="" />
          : err
            ? <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: '#fff', padding: 24, textAlign: 'center' }}>
                <div>
                  <div style={{ fontSize: 40 }}>📷</div>
                  <p style={{ marginTop: 10, fontSize: 14, opacity: .85 }}>
                    {lang === 'mr'
                      ? 'कॅमेरा उपलब्ध नाही. खालील बटणाने फोटो निवडा.'
                      : 'The camera is not available. Use the button below to choose a photo.'}
                  </p>
                </div>
              </div>
            : <video ref={videoRef} playsInline muted />}
        {!preview && <div className="cam-frame"><i /><i /><i /><i /></div>}
        {!preview && (
          <div className="cam-tips">
            <div className="t">{lang === 'mr' ? 'चांगल्या निकालासाठी' : 'Tips for best result'}</div>
            <ul>{(tips || DEFAULT_TIPS).map((x, i) => <li key={i}><span>✓</span><span>{x}</span></li>)}</ul>
          </div>
        )}
      </div>
      <div className="cam-bar">
        <button className="cam-side" onClick={() => fileRef.current?.click()}>
          <span className="ic">🖼</span><span>{lang === 'mr' ? 'गॅलरी' : 'Gallery'}</span>
        </button>
        <button className="shutter" onClick={shoot} aria-label={lang === 'mr' ? 'फोटो काढा' : 'Take photo'} />
        <div className="cam-side" style={{ opacity: .55 }}>
          <span className="ic">💡</span><span>{lang === 'mr' ? 'उजेड' : 'Light'}</span>
        </div>
      </div>
      <input ref={fileRef} type="file" accept="image/*" capture="environment"
             onChange={pick} style={{ display: 'none' }} />
    </div>
  )
}

/* ── connectivity + demo banners ───────────────────────────────────────── */
export const Banners = ({ online, queued, demo, stale, lang = 'en' }) => (
  <>
    {demo && (
      <div className="banner demo">
        <span>⚠</span>
        <span>{lang === 'mr'
          ? 'डेमो मोड — हवामान माहिती तयार केलेली आहे, प्रत्यक्ष निरीक्षण नाही.'
          : 'DEMO MODE — weather is generated, not observed.'}</span>
      </div>
    )}
    {!online && (
      <div className="banner offline">
        <span>📴</span>
        <span>{lang === 'mr'
          ? `ऑफलाइन${queued ? ` · ${queued} नोंदी पाठवायच्या आहेत` : ''}`
          : `Offline${queued ? ` · ${queued} record${queued > 1 ? 's' : ''} waiting to send` : ''}`}</span>
      </div>
    )}
    {online && queued > 0 && (
      <div className="banner stale">
        <span>⟳</span>
        <span>{lang === 'mr' ? `${queued} नोंदी पाठवत आहे…` : `Syncing ${queued} saved record${queued > 1 ? 's' : ''}…`}</span>
      </div>
    )}
    {stale && (
      <div className="banner stale">
        <span>🕘</span>
        <span>{lang === 'mr'
          ? `हे ${stale} चे साठवलेले दृश्य आहे`
          : `Showing what was saved on this phone at ${stale}`}</span>
      </div>
    )}
  </>
)

/* ── weather provenance strip — shown wherever weather drives a number ─── */
export function WeatherStrip({ weather }) {
  if (!weather) return null
  const gen = weather.generated
  const age = weather.freshness?.age_minutes
  return (
    <div className={`note ${gen ? 'warn' : weather.stale ? 'info' : ''}`} style={{ marginTop: 10 }}>
      <b>{gen ? '⚠ Generated weather (demo mode)' : `🌦 ${weather.source}`}</b>
      <div className="tiny" style={{ marginTop: 3 }}>
        {weather.observed_through && <>Observed through {weather.observed_through}. </>}
        {weather.forecast_from && <>Forecast from {weather.forecast_from}. </>}
        {age != null && <>Updated {age < 1 ? 'just now' : `${age} min ago`}. </>}
        {weather.stale && <><b>Stale</b> — the provider is unreachable, so this is the last real reading.</>}
      </div>
    </div>
  )
}

/* ── level helpers ─────────────────────────────────────────────────────── */
export const LEVEL_LABEL = {
  low: { en: 'Low', mr: 'कमी' }, watch: { en: 'Watch', mr: 'लक्ष ठेवा' },
  rising: { en: 'Rising', mr: 'वाढतोय' }, high: { en: 'High', mr: 'जास्त' },
  moderate: { en: 'Moderate', mr: 'मध्यम' }, safe: { en: 'Good', mr: 'चांगले' },
}
export const levelLabel = (l, lang) => (LEVEL_LABEL[l] || { en: l, mr: l })[lang === 'mr' ? 'mr' : 'en']

export const fmtDate = (iso, lang = 'en') => {
  if (!iso) return ''
  const d = new Date(String(iso).slice(0, 10) + 'T00:00:00')
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10)
  return d.toLocaleDateString(lang === 'mr' ? 'mr-IN' : 'en-IN', { day: 'numeric', month: 'short' })
}
export const fmtMoney = (n) => '₹' + Number(n || 0).toLocaleString('en-IN')
