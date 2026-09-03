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
import React from 'react'
import { auth } from '../api'
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

const DEMO_ACCOUNTS = [
  ['officer', 'officer@prahari.demo'],
  ['expert', 'expert@prahari.demo'],
  ['admin', 'admin@prahari.demo'],
]

export default function Modes({ lang, me, health, go }) {
  const role = me?.user?.role
  const isDemo = !!health?.config?.demo_mode

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

        {isDemo && (
          <Card>
            <div className="card-title">{lang === 'mr' ? 'डेमो खाती' : 'Demo accounts'}</div>
            <p className="tiny muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
              {bi(lang,
                'Shown because this instance reports DEMO_MODE. These accounts are seeded only in a demo build and do not exist in a deployment. Password: prahari-demo-2026',
                'ही माहिती फक्त डेमो बिल्डमध्ये दिसते. ही खाती प्रत्यक्ष तैनातीत नसतात. पासवर्ड: prahari-demo-2026')}
            </p>
            <ul className="md-demo">
              {DEMO_ACCOUNTS.map(([r, id]) => (
                <li key={r}><b>{r}</b><span>{id}</span></li>
              ))}
            </ul>
          </Card>
        )}

        <button className="btn block ghost" onClick={() => auth.clear()}>
          {lang === 'mr' ? 'साइन आउट' : 'Sign out'}
        </button>
      </div>
    </>
  )
}
