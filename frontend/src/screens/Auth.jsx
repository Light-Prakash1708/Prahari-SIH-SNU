/* PRAHARI · sign in and registration.

   The prototype had no authentication at all: /api/me returned the first row of
   the farmers table, so every phone in the world was the same farmer. This
   screen is the front door of the fix — but the boundary it opens is enforced
   entirely on the server. Nothing here filters anything. */
import React, { useEffect, useState } from 'react'
import { api, auth, setLang } from '../api'
import { ErrorNote } from '../ui'
import Icon from '../shell/Icon'
import '../shell/auth.css'

const LOGO = '/brand/logo.png'

const TALUKAS = [
  ['pimpalgaon', 'Pimpalgaon Baswant', 'पिंपळगाव बसवंत'],
  ['niphad', 'Niphad', 'निफाड'],
  ['dindori', 'Dindori', 'दिंडोरी'],
  ['lasalgaon', 'Lasalgaon', 'लासलगाव'],
  ['nashik', 'Nashik', 'नाशिक'],
  ['sinnar', 'Sinnar', 'सिन्नर'],
  ['igatpuri', 'Igatpuri', 'इगतपुरी'],
  ['yeola', 'Yeola', 'येवला'],
  ['chandvad', 'Chandvad', 'चांदवड'],
  ['malegaon', 'Malegaon', 'मालेगाव'],
]

const COPY = {
  mr: {
    tag: 'ओळखा · तपासा · वाचवा',
    sub: 'पिकावरील रोग आणि किडींचा धोका वेळेत ओळखण्यासाठी तुमच्या खात्यात जा.',
    secure: 'एन्क्रिप्टेड सत्र · माहिती सुरक्षित',
    signIn: 'साइन इन', signUp: 'नवीन खाते', reset: 'पासवर्ड विसरलात?',
    mobile: 'मोबाइल क्रमांक किंवा ईमेल', pass: 'पासवर्ड', name: 'पूर्ण नाव',
    taluka: 'तालुका', village: 'गाव (ऐच्छिक)', lang: 'भाषा',
    haveAccount: 'आधीच खाते आहे? साइन इन करा', noAccount: 'खाते नाही? नोंदणी करा',
    submitIn: 'साइन इन करा', submitUp: 'खाते तयार करा',
    passHint: 'किमान ८ अक्षरे', chooseTaluka: 'तालुका निवडा',
    resetSent: 'खाते असल्यास, रीसेट कोड पाठवला आहे.',
    back: 'मागे', newPass: 'नवीन पासवर्ड', code: 'रीसेट कोड',
  },
  en: {
    tag: 'Scan · Detect · Protect',
    sub: 'Sign in to see what is coming for your fields, and act only when it is needed.',
    secure: 'Encrypted session · Privacy first',
    signIn: 'Sign in', signUp: 'Create account', reset: 'Forgot password?',
    mobile: 'Mobile number or email', pass: 'Password', name: 'Full name',
    taluka: 'Taluka', village: 'Village (optional)', lang: 'Language',
    haveAccount: 'Already registered? Sign in', noAccount: 'New here? Create an account',
    submitIn: 'Sign in', submitUp: 'Create account',
    passHint: 'At least 8 characters', chooseTaluka: 'Choose your taluka',
    resetSent: 'If that account exists, a reset code has been sent to it.',
    back: 'Back', newPass: 'New password', code: 'Reset code',
  },
}

export default function Auth({ lang, onLang, onSignedIn }) {
  const [mode, setMode] = useState('in')     // in | up | reset | reset2
  const [form, setForm] = useState({ lang })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)
  const c = COPY[lang] || COPY.en

  useEffect(() => { setErr(null); setMsg(null) }, [mode])

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null); setMsg(null)
    try {
      if (mode === 'in') {
        const out = await api.login(form.identifier || '', form.password || '')
        auth.set(out.access_token)
        onSignedIn()
      } else if (mode === 'up') {
        const body = {
          full_name: form.full_name, password: form.password, lang,
          taluka: form.taluka, village: form.village || undefined,
        }
        const id = (form.identifier || '').trim()
        if (id.includes('@')) body.email = id; else body.phone = id
        const out = await api.register(body)
        auth.set(out.access_token)
        onSignedIn()
      } else if (mode === 'reset') {
        const out = await api.resetRequest(form.identifier || '')
        setMsg(out.dev_token
          ? `${c.resetSent}  (development code: ${out.dev_token})`
          : c.resetSent)
        setMode('reset2')
      } else {
        await api.resetPassword(form.code || '', form.password || '')
        setMsg(lang === 'mr' ? 'पासवर्ड बदलला. आता साइन इन करा.' : 'Password changed. Sign in now.')
        setMode('in')
      }
    } catch (e2) { setErr(e2) } finally { setBusy(false) }
  }

  const back = mode !== 'in'
    ? () => setMode(mode === 'reset2' ? 'reset' : 'in')
    : null

  const field = (icon, label, input, hint) => (
    <div className="px-auth__group">
      <label className="px-auth__label">{label}</label>
      <div className="px-auth__inputwrap">
        <span className="px-auth__ic"><Icon name={icon} size={15} /></span>
        {input}
      </div>
      {hint && <span className="px-auth__hint">{hint}</span>}
    </div>
  )

  return (
    <div className="px-auth">
      <div className="px-auth__wrap">
        <div className="px-auth__card">

          {/* Saurjya's curved cover, with his radar sweep behind the wordmark */}
          <header className="px-auth__cover">
            {back && (
              <button type="button" className="px-auth__back" onClick={back} aria-label={c.back}>
                <Icon name="back" size={14} />
              </button>
            )}
            <div className="px-auth__cover-svg" aria-hidden="true">
              <svg viewBox="0 0 380 140" fill="none" preserveAspectRatio="xMidYMid slice">
                <circle cx="190" cy="70" r="90" stroke="#86EFAC" strokeOpacity=".1" strokeWidth="1.5" />
                <circle cx="190" cy="70" r="60" stroke="#86EFAC" strokeOpacity=".2" strokeWidth="1.5" strokeDasharray="6 6" />
                <circle cx="190" cy="70" r="30" stroke="#86EFAC" strokeOpacity=".3" strokeWidth="1.5" />
                <line x1="190" y1="70" x2="260" y2="30" stroke="#86EFAC" strokeWidth="2" strokeLinecap="round" />
                <circle cx="110" cy="45" r="4" fill="#86EFAC" />
                <circle cx="270" cy="85" r="4" fill="#86EFAC" />
                <circle cx="230" cy="110" r="3" fill="#22C55E" />
              </svg>
            </div>
            <div className="px-auth__brand">
              <img src={LOGO} alt="PRAHARI" width="140" height="46" />
              <span className="px-auth__badge">
                <Icon name="shield" size={11} /> {c.tag}
              </span>
            </div>
          </header>

          <div className="px-auth__head">
            <h1 className="px-auth__title">
              {mode === 'in' ? c.signIn : mode === 'up' ? c.signUp
                : mode === 'reset' ? c.reset : c.newPass}
            </h1>
            <p className="px-auth__sub">{c.sub}</p>
          </div>

          {(mode === 'in' || mode === 'up') && (
            <div className="px-auth__seg">
              <button type="button" aria-pressed={mode === 'in'} onClick={() => setMode('in')}>{c.signIn}</button>
              <button type="button" aria-pressed={mode === 'up'} onClick={() => setMode('up')}>{c.signUp}</button>
            </div>
          )}

          <form onSubmit={submit}>
            {mode === 'up' && field('user', c.name,
              <input className="px-auth__input" required minLength={2} value={form.full_name || ''}
                     onChange={set('full_name')} autoComplete="name" placeholder={c.name} />)}

            {mode !== 'reset2' && field('card', c.mobile,
              <input className="px-auth__input" required value={form.identifier || ''}
                     onChange={set('identifier')} inputMode="text" autoComplete="username"
                     placeholder="9812345678" />)}

            {mode === 'reset2' && field('shield', c.code,
              <input className="px-auth__input" required value={form.code || ''}
                     onChange={set('code')} placeholder="------" />)}

            {mode !== 'reset' && field('shield',
              mode === 'reset2' ? c.newPass : c.pass,
              <input className="px-auth__input" required type="password" minLength={8}
                     value={form.password || ''} onChange={set('password')}
                     autoComplete={mode === 'in' ? 'current-password' : 'new-password'}
                     placeholder="••••••••" />,
              mode !== 'in' ? c.passHint : null)}

            {mode === 'up' && (
              <>
                {field('map', c.taluka,
                  <select className="px-auth__input" required value={form.taluka || ''} onChange={set('taluka')}>
                    <option value="">{c.chooseTaluka}</option>
                    {TALUKAS.map(([id, en, mr]) =>
                      <option key={id} value={id}>{lang === 'mr' ? mr : en}</option>)}
                  </select>)}
                {field('seedling', c.village,
                  <input className="px-auth__input" value={form.village || ''}
                         onChange={set('village')} placeholder={c.village} />)}
              </>
            )}

            {err && <div style={{ marginBottom: 12 }}><ErrorNote error={err} lang={lang} /></div>}
            {msg && <div className="px-auth__note">{msg}</div>}

            <button className="px-auth__btn px-auth__btn--primary" disabled={busy} type="submit">
              {busy ? '…' : (
                <>
                  <Icon name={mode === 'in' ? 'signout' : mode === 'up' ? 'user' : 'shield'} size={16} />
                  {mode === 'in' ? c.submitIn
                    : mode === 'up' ? c.submitUp
                    : mode === 'reset' ? (lang === 'mr' ? 'कोड पाठवा' : 'Send reset code')
                    : (lang === 'mr' ? 'पासवर्ड बदला' : 'Change password')}
                </>
              )}
            </button>
          </form>

          {mode === 'in' && (
            <div style={{ textAlign: 'center' }}>
              <button type="button" className="px-auth__btn--link" onClick={() => setMode('reset')}>
                {c.reset}
              </button>
            </div>
          )}

          <div className="px-auth__chips">
            {[['mr', 'मराठी'], ['hi', 'हिंदी'], ['en', 'English']].map(([code, label]) => (
              <button key={code} type="button" className="px-auth__chip" aria-pressed={lang === code}
                      onClick={() => { setLang(code); onLang(code) }}>
                <Icon name="globe" size={12} /> {label}
              </button>
            ))}
          </div>

          <div className="px-auth__foot">
            <Icon name="shield" size={13} />
            <span>{c.secure}</span>
          </div>
        </div>

        <p className="px-auth__legal">
          {lang === 'mr'
            ? 'तुमची शेतीविषयक माहिती तुमचीच आहे. ती दुसऱ्या शेतकऱ्याला दाखवली जात नाही; तालुका पातळीवरील निरीक्षण एकत्रित असते, त्यामुळे कोणतेही एक शेत ओळखता येत नाही.'
            : 'Your field data is yours: it is never shown to another farmer, and taluka surveillance is aggregated so no individual farm can be identified.'}
        </p>
      </div>
    </div>
  )
}
