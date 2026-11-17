/* PRAHARI · the consoles, and who may open them.

   The role is not a client-side preference and never was — App.jsx hands each
   role a different product at the top of the tree, from `/api/auth/me`. That is
   correct and nothing here weakens it. What was missing was any way to SEE
   that: a farmer had no indication that an expert console and an officer
   console exist, and a signed-in officer arriving from a farmer device had no
   door to walk through.

   So this screen states the truth. It shows the account's own role, lists the
   three consoles, and opens one only when the signed-in account already has
   that role. When it does not, it says so plainly and offers the only honest
   route: sign in with an account that does. No mode switch, no client-side
   role, no demo bypass reaching production — the seeded credentials below are
   printed ONLY when the server reports demo_mode, because outside a demo they
   do not exist. */
import React, { useEffect, useState } from 'react'
import { api, auth } from '../api'
import { Card, bi } from '../ui'
import Icon from '../shell/Icon'

const CONSOLES = [
  {
    role: 'farmer', route: 'home', icon: 'seedling',
    title: ['Farmer', 'शेतकरी'],
    body: ['Your fields, scans, decisions and the day\'s work.',
           'तुमची शेते, तपासण्या, निर्णय आणि आजचे काम.'],
  },
  {
    role: 'expert', route: 'expert', icon: 'shield',
    title: ['Expert verification', 'तज्ज्ञ पडताळणी'],
    body: ['The queue of cases a farmer or the model could not settle, for an agronomist to confirm.',
           'शेतकरी किंवा मॉडेलला निश्चित करता न आलेली प्रकरणे — कृषितज्ज्ञाच्या पडताळणीसाठी.'],
  },
  {
    role: 'officer', route: 'officer', icon: 'radar',
    title: ['Officer / management console', 'अधिकारी नियंत्रण कक्ष'],
    body: ['District surveillance — clusters, the officer queue and the visit route.',
           'जिल्हा निरीक्षण — गट, अधिकारी रांग आणि भेटीचा मार्ग.'],
  },
  {
    role: 'admin', route: 'home', icon: 'gear',
    title: ['Administrator', 'प्रशासक'],
    body: ['Verify label claims, create staff, grant scope, read the audit trail.',
           'शिफारशी तपासणे, कर्मचारी तयार करणे, अधिकार देणे, नोंदवही पाहणे.'],
  },
]

/* The three consoles a presenter needs to show. `admin` is deliberately
   absent: nothing in a demonstration needs it, and a door nobody needs should
   not exist. */
const DEMO_CONSOLES = [
  ['farmer',  ['Farmer demo', 'शेतकरी डेमो']],
  ['expert',  ['Expert demo', 'तज्ञ डेमो']],
  ['officer', ['Officer demo', 'अधिकारी डेमो']],
  ['fpo',     ['FPO demo', 'उत्पादक संस्था डेमो']],
]

export default function Modes({ lang, me, health, go }) {
  const role = me?.user?.role
  /* The server's own answer, not a build flag: the card appears only where
     the deployment switched demo consoles on, and the button works only
     there, because the route 404s everywhere else. */
  const demoOpen = !!health?.config?.demo_console_access
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const openDemo = async (which) => {
    setBusy(which); setErr(null)
    try {
      const out = await api.demoConsole(which)
      /* Exactly what a normal sign-in does with its token. App.jsx then
         asks the SERVER for the role via /api/auth/me and hands over the
         matching console — nothing on this page decides what opens. */
      auth.set(out.access_token)
      window.location.reload()
    } catch (e) {
      setErr(e)
      setBusy(null)
    }
  }

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{lang === 'mr' ? 'प्रहरीचे कक्ष' : 'PRAHARI consoles'}</h1>
      </div>

      <div className="pad stack" style={{ paddingTop: 14 }}>
        <Card>
          <div className="card-title">{lang === 'mr' ? 'तुम्ही सध्या' : 'You are signed in as'}</div>
          <p className="small muted" style={{ marginTop: 6 }}>
            {bi(lang,
              'PRAHARI decides which console you get from your account, on the server. It is not a setting on this phone, which is why a console you may not open is not offered here.',
              'कोणता कक्ष उघडायचा हे प्रहरी तुमच्या खात्यावरून सर्व्हरवर ठरवते. हा फोनवरचा पर्याय नाही — म्हणून तुम्हाला परवानगी नसलेला कक्ष इथे दिला जात नाही.')}
          </p>
        </Card>

        {CONSOLES.map(c => {
          const mine = c.role === role
          return (
            <Card key={c.role} className={mine ? 'md-card is-mine' : 'md-card'}>
              <div className="md-head">
                <span className="md-ic"><Icon name={c.icon} size={17} /></span>
                <div className="grow">
                  <b>{bi(lang, c.title[0], c.title[1])}</b>
                  {mine && (
                    <span className="badge ok" style={{ marginLeft: 7 }}>
                      {lang === 'mr' ? 'तुमचे खाते' : 'your account'}
                    </span>
                  )}
                </div>
              </div>
              <p className="small muted" style={{ marginTop: 7 }}>
                {bi(lang, c.body[0], c.body[1])}
              </p>
              {mine ? (
                <button className="btn block" style={{ marginTop: 12 }}
                        onClick={() => go(c.route)}>
                  {lang === 'mr' ? 'उघडा' : 'Open'}
                </button>
              ) : (
                <p className="tiny faint" style={{ marginTop: 10, lineHeight: 1.5 }}>
                  {bi(lang,
                    'Opens only for an account with this role. Sign out and sign in with one.',
                    'ही भूमिका असलेल्या खात्यानेच उघडता येते. साइन आउट करून त्या खात्याने साइन इन करा.')}
                </p>
              )}
            </Card>
          )
        })}

        {demoOpen && (
          <Card className="md-demo-card">
            <div className="card-title">{bi(lang, 'Demo access', 'डेमो प्रवेश')}</div>
            <p className="tiny muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
              {bi(lang,
                'This instance has demo consoles switched on. Each button signs you in to a real account of that role on the server and opens the same console that role always gets — nothing here is simulated. No password is used, shown or stored.',
                'या आवृत्तीत डेमो कक्ष चालू आहेत. प्रत्येक बटण सर्व्हरवरील त्या भूमिकेच्या खऱ्या खात्याने साइन इन करते आणि नेहमीचाच कक्ष उघडते. काहीही बनावट नाही; पासवर्ड लागत नाही.')}
            </p>
            <div className="md-demo-btns">
              {DEMO_CONSOLES.map(([which, label]) => (
                <button key={which} className="btn sm" disabled={!!busy}
                        onClick={() => openDemo(which)}>
                  {busy === which
                    ? bi(lang, 'Opening…', 'उघडत आहे…')
                    : bi(lang, label[0], label[1])}
                </button>
              ))}
            </div>
            {err && (
              <p className="tiny" style={{ color: 'var(--warn)', marginTop: 9 }}>
                {bi(lang, 'Demo access is not available on this instance.',
                          'या आवृत्तीत डेमो प्रवेश उपलब्ध नाही.')}
              </p>
            )}
          </Card>
        )}

        {health?.config?.demo_mode && demoOpen && (
          <JudgePanel lang={lang} openDemo={openDemo} busy={busy} />
        )}

        <button className="btn block ghost" onClick={() => auth.clear()}>
          {lang === 'mr' ? 'साइन आउट' : 'Sign out'}
        </button>
      </div>
    </>
  )
}

/* ── judge mode ─────────────────────────────────────────────────────────────
   Only on a demo/staging deployment (the server reports demo_mode and the
   route 404s anywhere else). The eight cases, which console each needs, what
   should happen, and the honesty line to say out loud — read from the server so
   the script and the running build cannot drift apart. Reset restores the
   starting state without deleting anything. */
function JudgePanel({ lang, openDemo, busy }) {
  const [g, setG] = useState(null)
  const [state, setState] = useState(null)
  const [resetting, setResetting] = useState(false)
  const load = () => api.judge().then(setG).catch(() => setG(null))
  useEffect(() => { load() }, [])
  if (!g) return null

  const reset = async () => {
    setResetting(true); setState(null)
    try { setState(await api.judgeReset()); await load() }
    catch (e) { setState({ error: e?.message || 'reset failed' }) }
    finally { setResetting(false) }
  }

  return (
    <Card className="md-demo-card">
      <div className="row between">
        <div className="card-title">🎓 {bi(lang, 'Judge mode', 'परीक्षक मोड')}</div>
        <span className="badge grey">{bi(lang, 'staging · synthetic', 'स्टेजिंग · कृत्रिम')}</span>
      </div>
      <p className="tiny muted" style={{ marginTop: 6, lineHeight: 1.5 }}>{g.environment}</p>
      <ol className="judge-list">
        {g.cases.map(c => (
          <li key={c.key} className="judge-case">
            <div className="row between" style={{ gap: 8, alignItems: 'flex-start' }}>
              <b className="small">{c.n}. {c.title}</b>
              <button className="btn sm ghost" disabled={!!busy}
                      onClick={() => { if (c.role === 'farmer') window.history.replaceState(null, '', '#/' + c.route); openDemo(c.role) }}>
                {c.role}
              </button>
            </div>
            <div className="tiny" style={{ marginTop: 4 }}><b>{bi(lang, 'Do', 'करा')}:</b> {c.do}</div>
            <div className="tiny" style={{ marginTop: 2 }}><b>{bi(lang, 'Expect', 'अपेक्षित')}:</b> {c.expect}</div>
            <div className="tiny faint" style={{ marginTop: 2 }}>⚖ {c.honesty}</div>
          </li>
        ))}
      </ol>
      {!g.readiness.fpo_view_has_counts && (
        <div className="note warn" style={{ marginTop: 8 }}>
          {bi(lang, 'The FPO has fewer than 3 members, so its counts are suppressed. Reset fixes this.',
                    'FPO मध्ये ३ पेक्षा कमी सदस्य आहेत. रीसेट करा.')}
        </div>
      )}
      <button className="btn block" style={{ marginTop: 10 }} disabled={resetting} onClick={reset}>
        {resetting ? '…' : bi(lang, '↺ Reset the demo', '↺ डेमो रीसेट करा')}
      </button>
      {state && (
        <p className="tiny" style={{ marginTop: 8, color: state.error ? 'var(--bad)' : 'var(--ok)' }}>
          {state.error || state.note}
        </p>
      )}
    </Card>
  )
}
