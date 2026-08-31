/* PRAHARI · sign in and registration.

   The prototype had no authentication at all: /api/me returned the first row of
   the farmers table, so every phone in the world was the same farmer. This
   screen is the front door of the fix — but the boundary it opens is enforced
   entirely on the server. Nothing here filters anything. */
import React, { useEffect, useState } from 'react'
import { api, auth, setLang } from '../api'
import { ErrorNote, Shield } from '../ui'

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
    tag: 'प्रत्येक पिकाचे रक्षण, प्रत्येक हंगामाची सुरक्षा',
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
    tag: 'Guarding every crop, securing every harvest',
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

  return (
    <div className="auth">
      <div className="auth-brand">
        <div style={{ display: 'grid', placeItems: 'center', marginBottom: 6 }}><Shield size={52} tone="#fff" leaf="#8BD3A4" /></div>
        <div className="nm">PRAHARI</div>
        <div className="mr">प्रहरी</div>
        <div className="tag">{c.tag}</div>
      </div>

      <div className="card" style={{ boxShadow: 'var(--shadow-lg)' }}>
        <div className="seg" style={{ marginBottom: 16 }}>
          <button aria-pressed={mode === 'in'} onClick={() => setMode('in')}>{c.signIn}</button>
          <button aria-pressed={mode === 'up'} onClick={() => setMode('up')}>{c.signUp}</button>
        </div>

        <form onSubmit={submit}>
          {mode === 'up' && (
            <label className="field">
              <span className="lbl">{c.name}</span>
              <input className="input" required minLength={2} value={form.full_name || ''}
                     onChange={set('full_name')} autoComplete="name" />
            </label>
          )}

          {mode !== 'reset2' && (
            <label className="field">
              <span className="lbl">{c.mobile}</span>
              <input className="input" required value={form.identifier || ''} onChange={set('identifier')}
                     inputMode="text" autoComplete="username" placeholder="9812345678" />
            </label>
          )}

          {mode === 'reset2' && (
            <label className="field">
              <span className="lbl">{c.code}</span>
              <input className="input" required value={form.code || ''} onChange={set('code')} />
            </label>
          )}

          {mode !== 'reset' && (
            <label className="field">
              <span className="lbl">{mode === 'reset2' ? c.newPass : c.pass}</span>
              <input className="input" required type="password" minLength={8}
                     value={form.password || ''} onChange={set('password')}
                     autoComplete={mode === 'in' ? 'current-password' : 'new-password'} />
              {mode !== 'in' && <span className="hint">{c.passHint}</span>}
            </label>
          )}

          {mode === 'up' && (
            <>
              <label className="field">
                <span className="lbl">{c.taluka}</span>
                <select className="input" required value={form.taluka || ''} onChange={set('taluka')}>
                  <option value="">{c.chooseTaluka}</option>
                  {TALUKAS.map(([id, en, mr]) =>
                    <option key={id} value={id}>{lang === 'mr' ? mr : en}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="lbl">{c.village}</span>
                <input className="input" value={form.village || ''} onChange={set('village')} />
              </label>
            </>
          )}

          {err && <div style={{ marginBottom: 12 }}><ErrorNote error={err} lang={lang} /></div>}
          {msg && <div className="note" style={{ marginBottom: 12 }}>{msg}</div>}

          <button className="btn block" disabled={busy} type="submit">
            {busy ? '…' : mode === 'in' ? c.submitIn
              : mode === 'up' ? c.submitUp
              : mode === 'reset' ? (lang === 'mr' ? 'कोड पाठवा' : 'Send reset code')
              : (lang === 'mr' ? 'पासवर्ड बदला' : 'Change password')}
          </button>
        </form>

        {mode === 'in' && (
          <div className="center" style={{ marginTop: 10 }}>
            <button className="btn link" onClick={() => setMode('reset')}>{c.reset}</button>
          </div>
        )}
        {mode === 'reset' && (
          <div className="center" style={{ marginTop: 6 }}>
            <button className="btn link" onClick={() => setMode('in')}>{c.back}</button>
          </div>
        )}
      </div>

      <div className="row" style={{ justifyContent: 'center', marginTop: 18, gap: 8 }}>
        {[['mr', 'मराठी'], ['hi', 'हिंदी'], ['en', 'English']].map(([code, label]) => (
          <button key={code} className="chip" aria-pressed={lang === code}
                  onClick={() => { setLang(code); onLang(code) }}>{label}</button>
        ))}
      </div>

      <p className="tiny faint center" style={{ marginTop: 18, lineHeight: 1.6 }}>
        PRAHARI is an early-warning system for crop disease and pest infestation,
        built for the Maharashtra State Innovation Society problem statement.
        Your field data is yours: it is never shown to another farmer, and taluka
        surveillance is aggregated so no individual farm can be identified.
      </p>
    </div>
  )
}
