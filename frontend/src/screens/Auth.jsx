/* PRAHARI · sign in and registration.

   The prototype had no authentication at all: /api/me returned the first row of
   the farmers table, so every phone in the world was the same farmer. This
   screen is the front door of the fix — but the boundary it opens is enforced
   entirely on the server. Nothing here filters anything. */
import React, { useEffect, useState } from 'react'
import { api, auth, setLang } from '../api'
import { ErrorNote, bi } from '../ui'
import Icon from '../shell/Icon'
import '../shell/auth.css'
import { UnitOptions, useUnits } from '../units'

const LOGO = '/brand/logo.png'


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
    showPass: 'पासवर्ड दाखवा', hidePass: 'पासवर्ड लपवा',
  },
  /* DRAFT — for review with src/i18n/bn.js. */
  bn: {
    tag: 'স্ক্যান · শনাক্ত · সুরক্ষা',
    sub: 'আপনার জমির দিকে কী আসছে তা দেখতে সাইন ইন করুন, আর দরকার হলে তবেই ব্যবস্থা নিন।',
    secure: 'এনক্রিপ্ট করা সেশন · তথ্য সুরক্ষিত',
    signIn: 'সাইন ইন', signUp: 'নতুন অ্যাকাউন্ট', reset: 'পাসওয়ার্ড ভুলে গেছেন?',
    mobile: 'মোবাইল নম্বর বা ইমেল', pass: 'পাসওয়ার্ড', name: 'পুরো নাম',
    taluka: 'ব্লক', village: 'গ্রাম (ইচ্ছামতো)', lang: 'ভাষা',
    haveAccount: 'আগে থেকেই অ্যাকাউন্ট আছে? সাইন ইন করুন', noAccount: 'নতুন? অ্যাকাউন্ট খুলুন',
    submitIn: 'সাইন ইন করুন', submitUp: 'অ্যাকাউন্ট খুলুন',
    passHint: 'অন্তত ৮টি অক্ষর', chooseTaluka: 'আপনার ব্লক বেছে নিন',
    resetSent: 'অ্যাকাউন্ট থাকলে, তাতে রিসেট কোড পাঠানো হয়েছে।',
    back: 'পিছনে', newPass: 'নতুন পাসওয়ার্ড', code: 'রিসেট কোড',
    showPass: 'পাসওয়ার্ড দেখান', hidePass: 'পাসওয়ার্ড লুকান',
  },
  en: {
    tag: 'Scan · Detect · Protect',
    sub: 'Sign in to see what is coming for your fields, and act only when it is needed.',
    secure: 'Encrypted session · Privacy first',
    signIn: 'Sign in', signUp: 'Create account', reset: 'Forgot password?',
    mobile: 'Mobile number or email', pass: 'Password', name: 'Full name',
    taluka: 'Taluka / block', village: 'Village (optional)', lang: 'Language',
    haveAccount: 'Already registered? Sign in', noAccount: 'New here? Create an account',
    submitIn: 'Sign in', submitUp: 'Create account',
    passHint: 'At least 8 characters', chooseTaluka: 'Choose your taluka or block',
    resetSent: 'If that account exists, a reset code has been sent to it.',
    back: 'Back', newPass: 'New password', code: 'Reset code',
    showPass: 'Show password', hidePass: 'Hide password',
  },
}

export default function Auth({ lang, onLang, onSignedIn }) {
  const units = useUnits()
  const [mode, setMode] = useState('in')     // in | up | reset | reset2
  const [form, setForm] = useState({ lang })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)
  const [showPass, setShowPass] = useState(false)
  const c = COPY[lang] || COPY.en

  useEffect(() => { setErr(null); setMsg(null); setShowPass(false) }, [mode])

  /* Demo consoles on the front door, when — and only when — the SERVER says
     DEMO_CONSOLE_ACCESS is on. The buttons carry no credential: each asks the
     server for a session on one of its fixed demo accounts, the same call the
     Modes screen makes. With the switch off, /api/ready says so and nothing
     renders here. */
  const [demoOn, setDemoOn] = useState(false)
  const [demoData, setDemoData] = useState(false)
  const [demoBusy, setDemoBusy] = useState(null)
  useEffect(() => {
    api.ready().then(h => { setDemoOn(!!h?.config?.demo_console_access); setDemoData(!!h?.config?.demo_mode) }).catch(() => setDemoOn(false))
  }, [])
  const openDemo = async (role) => {
    setDemoBusy(role); setErr(null)
    try {
      const out = await api.demoConsole(role)
      auth.set(out.access_token)
      onSignedIn()
    } catch (e2) { setErr(e2) } finally { setDemoBusy(null) }
  }

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
        setMsg(bi(lang, 'Password changed. Sign in now.', 'पासवर्ड बदलला. आता साइन इन करा.'))
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
              <>
                <input className="px-auth__input px-auth__input--eye" required
                       type={showPass ? 'text' : 'password'} minLength={8}
                       value={form.password || ''} onChange={set('password')}
                       autoComplete={mode === 'in' ? 'current-password' : 'new-password'}
                       autoCapitalize="off" autoCorrect="off" spellCheck={false}
                       placeholder="••••••••" />
                {/* Shows the password as typed, on this screen only. A farmer
                    on a small keyboard checks what they entered before an
                    account is created with a typo they cannot recall. */}
                <button type="button" className="px-auth__eye"
                        onClick={() => setShowPass(v => !v)}
                        aria-pressed={showPass}
                        aria-label={showPass ? (c.hidePass || 'Hide password') : (c.showPass || 'Show password')}
                        title={showPass ? (c.hidePass || 'Hide password') : (c.showPass || 'Show password')}>
                  <Icon name={showPass ? 'eyeoff' : 'eye'} size={18} />
                </button>
              </>,
              mode !== 'in' ? c.passHint : null)}

            {mode === 'up' && (
              <>
                {field('map', c.taluka,
                  <select className="px-auth__input" required value={form.taluka || ''} onChange={set('taluka')}>
                    <option value="">{c.chooseTaluka}</option>
                    <UnitOptions units={units} lang={lang} />
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
                    : mode === 'reset' ? (bi(lang, 'Send reset code', 'कोड पाठवा'))
                    : (bi(lang, 'Change password', 'पासवर्ड बदला'))}
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

          {demoOn && mode === 'in' && (
            <div className="px-auth__demo">
              <div className="px-auth__demo-h">
                {bi(lang, 'Explore without an account — demo', 'खाते नसताना पाहा — डेमो')}
              </div>
              <div className="px-auth__demo-row">
                {[['farmer', 'Farmer', 'शेतकरी'], ['expert', 'Expert', 'तज्ज्ञ'],
                  ['officer', 'Officer', 'अधिकारी'], ['fpo', 'FPO', 'उत्पादक संस्था']]
                  .map(([role, en, mr]) => (
                    <button key={role} type="button" className="px-auth__chip"
                            disabled={!!demoBusy} onClick={() => openDemo(role)}>
                      {demoBusy === role ? '…' : (lang === 'mr' ? mr : en)}
                    </button>
                  ))}
              </div>
              <div className="px-auth__demo-note">
                {demoData
                  ? bi(lang, 'This is a demo service: synthetic farmers and generated, labelled weather. The engines are the production ones.',
                             'ही डेमो सेवा आहे: कृत्रिम शेतकरी आणि तयार केलेले, लेबल असलेले हवामान. इंजिने तीच आहेत.')
                  : bi(lang, 'Demo accounts are real accounts on live weather — not yours, and shared.', 'डेमो खाती खरी असतात आणि खरे हवामान वापरतात; ती तुमची नसतात.')}
              </div>
            </div>
          )}

          <div className="px-auth__chips">
            {[['bn', 'বাংলা'], ['mr', 'मराठी'], ['hi', 'हिंदी'], ['en', 'English']].map(([code, label]) => (
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
          {bi(lang, 'Your field data is yours: it is never shown to another farmer, and taluka surveillance is aggregated so no individual farm can be identified.', 'तुमची शेतीविषयक माहिती तुमचीच आहे. ती दुसऱ्या शेतकऱ्याला दाखवली जात नाही; तालुका पातळीवरील निरीक्षण एकत्रित असते, त्यामुळे कोणतेही एक शेत ओळखता येत नाही.')}
        </p>
      </div>
    </div>
  )
}
