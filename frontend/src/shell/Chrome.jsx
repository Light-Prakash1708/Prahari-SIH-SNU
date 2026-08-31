/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · the chrome — Saurjya's header, drawer, account sheet, bottom bar

   Saurjya's static pages hard-code a farmer called Ramesh Kumar with 14 reports
   and 98% accuracy. None of that is here. The account sheet renders the user
   the server returned from /api/auth/me and the counts it renders are the ones
   the app already has in hand; where a count is not yet available it is simply
   not shown rather than invented.

   Every item routes through the app's own go(), so the drawer and the bottom
   bar drive the same router the rest of the app uses.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useEffect } from 'react'
import Icon from './Icon'

/* served from public/ — no bundler hash, so it is also the file the offline
   cache and the manifest can reference by a stable path. */
const LOGO = '/brand/logo.png'

const T = {
  mr: {
    home: 'मुख्य', crop: 'पीक', scan: 'स्कॅन', community: 'समुदाय', agridoc: 'साथी',
    menu: 'मेनू', account: 'खाते', signout: 'साइन आउट', close: 'बंद करा',
    nav: 'नेव्हिगेशन', tools: 'साधने', fields: 'शेते', forecast: 'अंदाज',
    traps: 'सापळे', soil: 'माती', water: 'पाणी', alerts: 'सूचना',
    profile: 'प्रोफाइल', history: 'इतिहास', fieldsCount: 'शेते', queued: 'रांगेत',
    unread: 'न वाचलेल्या', ipm: 'निर्णय', guest: 'वापरकर्ता',
  },
  en: {
    home: 'Home', crop: 'Crop', scan: 'Scan', community: 'Community', agridoc: 'AgriDoc',
    menu: 'Menu', account: 'Account', signout: 'Sign out', close: 'Close',
    nav: 'Navigation', tools: 'Tools', fields: 'Fields', forecast: 'Forecast',
    traps: 'Traps', soil: 'Soil', water: 'Water', alerts: 'Alerts',
    profile: 'Profile', history: 'History', fieldsCount: 'Fields', queued: 'Queued',
    unread: 'Unread', ipm: 'Decide', guest: 'User',
  },
}
const t = (lang, k) => (T[lang] || T.en)[k] ?? T.en[k]

const ROLE_LABEL = {
  farmer: { en: 'Farmer', mr: 'शेतकरी' },
  officer: { en: 'Agriculture Officer', mr: 'कृषी अधिकारी' },
  expert: { en: 'Expert', mr: 'तज्ज्ञ' },
  admin: { en: 'Administrator', mr: 'प्रशासक' },
}

/* ── header ───────────────────────────────────────────────────────────── */
export function Header({ lang, unread = 0, onMenu, onAccount, menuOpen, accountOpen }) {
  return (
    <header className="px-header">
      <div className="px-header__row">
        <button className="px-btn-chrome" type="button" onClick={onMenu}
                aria-label={t(lang, 'menu')} aria-expanded={menuOpen} aria-controls="px-drawer">
          <span className="px-hamburger"><span /><span /><span /></span>
        </button>

        <div className="px-header__brand">
          <img src={LOGO} alt="PRAHARI" width="140" height="46" />
        </div>

        <button className="px-btn-chrome" type="button" onClick={onAccount}
                aria-label={t(lang, 'account')} aria-expanded={accountOpen} aria-controls="px-sheet">
          <Icon name="user" size={18} />
          {unread > 0
            ? <span className="px-count-dot">{unread > 9 ? '9+' : unread}</span>
            : <span className="px-badge-dot" />}
        </button>
      </div>
    </header>
  )
}

/* ── drawer ───────────────────────────────────────────────────────────── */
export function Drawer({ open, onClose, lang, route, go, role }) {
  useEffect(() => {
    if (!open) return
    const esc = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', esc)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', esc); document.body.style.overflow = '' }
  }, [open, onClose])

  const pick = (name) => { onClose(); go(name) }

  const primary = role === 'farmer'
    ? [
        ['home', 'home', t(lang, 'home')],
        ['crop', 'seedling', t(lang, 'crop')],
        ['scan', 'camera', t(lang, 'scan')],
        ['decide', 'shield', t(lang, 'ipm')],
        ['community', 'users', t(lang, 'community')],
        ['agridoc', 'robot', t(lang, 'agridoc')],
      ]
    : [['home', 'home', t(lang, 'home')]]

  const tools = role === 'farmer'
    ? [
        ['fields', 'map', t(lang, 'fields')],
        ['forecast', 'radar', t(lang, 'forecast')],
        ['traps', 'bug', t(lang, 'traps')],
        ['soil', 'leaf', t(lang, 'soil')],
        ['water', 'drop', t(lang, 'water')],
        ['alerts', 'bell', t(lang, 'alerts')],
        ['history', 'history', t(lang, 'history')],
        ['profile', 'gear', t(lang, 'profile')],
      ]
    : []

  const item = ([name, icon, label]) => (
    <li key={name}>
      <button type="button" onClick={() => pick(name)}
              className={'px-drawer__link' + (route === name ? ' is-active' : '')}>
        <span className="px-drawer__icon"><Icon name={icon} size={15} /></span>
        <span className="px-drawer__label">{label}</span>
        <span className="px-drawer__arrow"><Icon name="chevron" size={12} /></span>
      </button>
    </li>
  )

  return (
    <>
      <div className={'px-backdrop' + (open ? ' is-open' : '')} onClick={onClose} />
      <aside id="px-drawer" className={'px-drawer' + (open ? ' is-open' : '')}
             aria-label={t(lang, 'nav')} aria-hidden={!open}>
        <div className="px-drawer__head">
          <div className="px-drawer__brand">
            <img src={LOGO} alt="PRAHARI" width="98" height="32" />
            <span className="px-drawer__badge"><Icon name="shield" size={11} /> Crop AI</span>
          </div>
          <button className="px-btn-chrome" type="button" onClick={onClose} aria-label={t(lang, 'close')}>
            <Icon name="xmark" size={17} />
          </button>
        </div>

        <div className="px-drawer__body">
          <ul className="px-drawer__menu">{primary.map(item)}</ul>
          {tools.length > 0 && (
            <>
              <div className="px-drawer__group-title">{t(lang, 'tools')}</div>
              <ul className="px-drawer__menu">{tools.map(item)}</ul>
            </>
          )}
        </div>
      </aside>
    </>
  )
}

/* ── account sheet ────────────────────────────────────────────────────── */
export function AccountSheet({ open, onClose, lang, me, plots, unread = 0, queued = 0,
                               go, onSignOut }) {
  useEffect(() => {
    if (!open) return
    const esc = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [open, onClose])

  const user = me?.user || {}
  const profile = me?.profile || {}
  /* The server sends full_name and, when the account was registered in
     Marathi, full_name_mr. Show the one matching the interface language and
     fall back rather than inventing a name. */
  const name = (lang === 'mr' && (user.full_name_mr || profile.name_mr))
    || user.full_name || profile.name || user.phone || user.email || t(lang, 'guest')
  const role = ROLE_LABEL[user.role]?.[lang] || ROLE_LABEL[user.role]?.en || user.role || ''
  /* taluka and village come from the farmer profile the account was created
     with — a real place, not a decorative "#PR-8821". */
  const place = [profile.village, profile.taluka].filter(Boolean).join(' · ')
  const initial = String(name).trim().charAt(0).toUpperCase() || 'P'
  const pick = (name_) => { onClose(); go(name_) }

  return (
    <>
      <div className={'px-backdrop' + (open ? ' is-open' : '')} onClick={onClose} />
      <div id="px-sheet" className={'px-sheet' + (open ? ' is-open' : '')}
           aria-label={t(lang, 'account')} aria-hidden={!open}>
        <div className="px-sheet__head">
          <div className="px-sheet__user">
            <span className="px-avatar">{initial}</span>
            <div style={{ minWidth: 0 }}>
              <div className="px-sheet__name">{name}</div>
              {role && (
                <div className="px-sheet__role">{role}{place ? ` · ${place}` : ''}</div>
              )}
            </div>
          </div>
          <button className="px-btn-chrome" type="button" onClick={onClose} aria-label={t(lang, 'close')}>
            <Icon name="xmark" size={17} />
          </button>
        </div>

        <div className="px-sheet__body">
          {/* Only counts the app actually holds. Nothing here is invented. */}
          {user.role === 'farmer' && (
            <div className="px-sheet__stats">
              <div className="px-stat"><b>{plots?.length ?? '—'}</b><span>{t(lang, 'fieldsCount')}</span></div>
              <div className="px-stat"><b>{unread}</b><span>{t(lang, 'unread')}</span></div>
              <div className="px-stat"><b>{queued}</b><span>{t(lang, 'queued')}</span></div>
            </div>
          )}

          {user.role === 'farmer' && (
            <ul className="px-sheet__list">
              <li>
                <button type="button" className="px-sheet__item" onClick={() => pick('profile')}>
                  <span className="ic"><Icon name="card" size={13} /></span>
                  <span className="txt">{t(lang, 'profile')}</span>
                </button>
              </li>
              <li>
                <button type="button" className="px-sheet__item" onClick={() => pick('alerts')}>
                  <span className="ic"><Icon name="bell" size={13} /></span>
                  <span className="txt">{t(lang, 'alerts')}</span>
                  {unread > 0 && <span className="tag">{unread}</span>}
                </button>
              </li>
              <li>
                <button type="button" className="px-sheet__item" onClick={() => pick('fields')}>
                  <span className="ic"><Icon name="map" size={13} /></span>
                  <span className="txt">{t(lang, 'fields')}</span>
                </button>
              </li>
              <li>
                <button type="button" className="px-sheet__item" onClick={() => pick('history')}>
                  <span className="ic"><Icon name="history" size={13} /></span>
                  <span className="txt">{t(lang, 'history')}</span>
                </button>
              </li>
            </ul>
          )}
        </div>

        <div className="px-sheet__foot">
          <button type="button" className="px-signout" onClick={onSignOut}>
            <Icon name="signout" size={16} /> {t(lang, 'signout')}
          </button>
        </div>
      </div>
    </>
  )
}

/* ── floating bottom bar ──────────────────────────────────────────────── */
export function BottomNav({ lang, active, go }) {
  const item = (key, icon, label) => (
    <button key={key} type="button" onClick={() => go(key)}
            className={'px-botnav__item' + (active === key ? ' is-active' : '')}
            aria-current={active === key ? 'page' : undefined} aria-label={label}>
      <span className="px-botnav__icon"><Icon name={icon} size={19} /></span>
      <span className="px-botnav__lbl">{label}</span>
    </button>
  )

  return (
    <nav className="px-botnav" aria-label="Primary">
      <div className="px-botnav__bar">
        {item('home', 'home', t(lang, 'home'))}
        {item('crop', 'seedling', t(lang, 'crop'))}
        <button type="button" onClick={() => go('scan')}
                className={'px-botnav__item px-botnav__item--center' + (active === 'scan' ? ' is-active' : '')}
                aria-label={t(lang, 'scan')}>
          <span className="px-botnav__fab"><Icon name="camera" size={24} /></span>
          <span className="px-botnav__lbl">{t(lang, 'scan')}</span>
        </button>
        {item('community', 'users', t(lang, 'community'))}
        {item('agridoc', 'robot', t(lang, 'agridoc'))}
      </div>
    </nav>
  )
}
