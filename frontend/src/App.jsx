/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · प्रहरी — the shell

   One build, three products, chosen by the ROLE ON THE SERVER-ISSUED TOKEN:

     farmer  → a five-tab phone app
     officer → a dark, dense command centre
     expert  → a verification portal

   The role is not a client-side preference and never was. It comes from
   /api/auth/me, and every screen behind it is scoped server-side — the farmer
   app asks for its own fields and is given only those, rather than receiving
   the district's list and filtering it in the browser.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api, auth, getLang, queue, setLang as persistLang } from './api'
import { Banners, ErrorNote, Loading } from './ui'
import Auth from './screens/Auth'
import Home from './screens/Home'
import Scan from './screens/Scan'
import Decide from './screens/Decide'
import { AddField, Fields, History } from './screens/Fields'
import { Alerts, Forecast, Profile, Rescan, Traps } from './screens/More'
import Saathi from './screens/Saathi'
import Crop from './screens/Crop'
import Community from './screens/Community'
import CommunityPost from './screens/CommunityPost'
import CommunityNew from './screens/CommunityNew'
import Soil from './screens/Soil'
import Water from './screens/Water'
import Officer from './screens/Officer'
import Expert from './screens/Expert'

/* Five tabs, and the middle one is a camera because that is the verb this app
   exists for. Fields moved into Crop and Profile moved behind the header —
   a farmer opens this app to answer "what is wrong and what do I do", and two
   of the five tabs were administration. */
const TABS = [
  ['home', '🏠', 'home'],
  ['crop', '🌾', 'crop'],
  ['scan', '📷', 'scan'],
  ['community', '👥', 'community'],
  ['agridoc', '🌿', 'agridoc'],
]

const TAB_LABEL = {
  mr: { home: 'मुख्य', crop: 'पीक', scan: 'स्कॅन', community: 'समुदाय', agridoc: 'साथी' },
  en: { home: 'Home', crop: 'Crop', scan: 'Scan', community: 'Community', agridoc: 'AgriDoc' },
}

export default function App() {
  const [lang, setLangState] = useState(getLang())
  const [signedIn, setSignedIn] = useState(auth.signedIn)
  const [me, setMe] = useState(null)
  const [plots, setPlots] = useState(null)
  const [plotId, setPlotId] = useState(null)
  const [route, setRoute] = useState({ name: 'home', params: {} })
  const [err, setErr] = useState(null)
  const [booting, setBooting] = useState(auth.signedIn)
  const [online, setOnline] = useState(navigator.onLine)
  const [queued, setQueued] = useState(queue.size)
  const [unread, setUnread] = useState(0)
  const [health, setHealth] = useState(null)
  const [demo, setDemo] = useState(null)

  /* ── auth changes (including a 401 clearing the token) ────────────────── */
  useEffect(() => auth.onChange(tok => {
    setSignedIn(!!tok)
    if (!tok) { setMe(null); setPlots(null); setPlotId(null); setRoute({ name: 'home', params: {} }) }
  }), [])

  /* ── connectivity, and flushing the offline queue ─────────────────────── */
  useEffect(() => {
    const flush = async () => {
      try { const r = await queue.flush(); if (r.flushed) { setQueued(queue.size); reload() } }
      catch { /* stays queued */ }
    }
    const up = () => { setOnline(true); flush() }
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    if (navigator.onLine && auth.signedIn) flush()
    const timer = setInterval(() => setQueued(queue.size), 4000)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signedIn])

  /* ── boot ─────────────────────────────────────────────────────────────── */
  const reload = useCallback(async (selectPlot) => {
    if (!auth.signedIn) return
    try {
      const who = await api.me()
      setMe(who)
      if (who.user?.lang && !localStorage.getItem('prahari.lang')) {
        setLangState(who.user.lang); persistLang(who.user.lang)
      }
      if (who.user?.role === 'farmer') {
        const p = await api.plots()
        setPlots(p.plots)
        setPlotId(prev => selectPlot || (p.plots.some(x => x.id === prev) ? prev : p.plots[0]?.id) || null)
        api.notifications().then(n => setUnread(n.unread || 0)).catch(() => {})
      }
      setErr(null)
    } catch (e) { setErr(e) } finally { setBooting(false) }
  }, [])

  useEffect(() => {
    if (!signedIn) { setBooting(false); return }
    setBooting(true)
    reload()
    api.ready().then(setHealth).catch(() => setHealth(null))
    api.scenarios().then(setDemo).catch(() => setDemo(null))
  }, [signedIn, reload])

  const plot = useMemo(() => plots?.find(p => p.id === plotId) || null, [plots, plotId])
  const go = useCallback((name, params = {}) => {
    setRoute({ name, params })
    window.scrollTo({ top: 0 })
  }, [])

  const setScenario = async (key) => {
    try {
      await api.setScenario(key, plot?.id)
      const d = await api.scenarios()
      setDemo(d)
      await reload(plotId)
      go('home')
    } catch { /* surfaced by the next load */ }
  }

  /* ── not signed in ────────────────────────────────────────────────────── */
  if (!signedIn) {
    return <Auth lang={lang} onLang={setLangState} onSignedIn={() => setSignedIn(true)} />
  }

  if (booting) {
    return (
      <div className="shell">
        <div className="hdr" style={{ paddingBottom: 40 }}>
          <div className="hdr-greet">PRAHARI · प्रहरी</div>
          <div className="hdr-sub">{lang === 'mr' ? 'लोड होत आहे…' : 'Loading…'}</div>
        </div>
        <div className="pad pull"><Loading lines={4} /></div>
      </div>
    )
  }

  if (err && !me) {
    return (
      <div className="shell">
        <div className="pad" style={{ paddingTop: 28 }}>
          <ErrorNote error={err} lang={lang} onRetry={() => reload()} />
          <button className="btn block ghost" style={{ marginTop: 14 }} onClick={() => auth.clear()}>
            {lang === 'mr' ? 'साइन आउट' : 'Sign out'}
          </button>
        </div>
      </div>
    )
  }

  const role = me?.user?.role

  /* ── officer and expert get their own products ────────────────────────── */
  if (role === 'officer' || role === 'admin') {
    return <div className="shell wide"><Officer me={me} health={health} /></div>
  }
  if (role === 'expert') {
    return <div className="shell wide"><Expert me={me} /></div>
  }

  /* ── the farmer app ───────────────────────────────────────────────────── */
  const isDemo = !!health?.config?.demo_mode
  const staleAt = null

  const screen = () => {
    switch (route.name) {
      case 'scan':
        if (!plot) return <NoField lang={lang} go={go} />
        return <Scan lang={lang} plot={plot} go={go} onDone={() => reload(plotId)} />
      case 'decide':
        if (!plot) return <NoField lang={lang} go={go} />
        return <Decide lang={lang} plot={plot} target={route.params.target} go={go} online={online} />
      case 'fields':
        return <Fields lang={lang} plots={plots} plot={plot} onPlot={setPlotId} go={go} reload={reload} />
      case 'addField':
        return <AddField lang={lang} go={go} reload={reload} />
      case 'history':
        if (!plot) return <NoField lang={lang} go={go} />
        return <History lang={lang} plot={plot} go={go} />
      case 'forecast':
        if (!plot) return <NoField lang={lang} go={go} />
        return <Forecast lang={lang} plot={plot} go={go} />
      case 'traps':
        if (!plot) return <NoField lang={lang} go={go} />
        return <Traps lang={lang} plot={plot} go={go} online={online} />
      case 'rescan':
        return <Rescan lang={lang} followup={route.params.followup} go={go} />
      case 'saathi':
      case 'agridoc':
        return <Saathi lang={lang} plot={plot} go={go} />
      case 'crop':
        return <Crop lang={lang} plot={plot} plots={plots} onPlot={setPlotId} go={go} />
      case 'soil':
        if (!plot) return <NoField lang={lang} go={go} />
        return <Soil lang={lang} plot={plot} go={go} />
      case 'water':
        if (!plot) return <NoField lang={lang} go={go} />
        return <Water lang={lang} plot={plot} go={go} />
      case 'community':
        return <Community lang={lang} me={me} plot={plot} plots={plots} go={go} />
      case 'communityPost':
        return <CommunityPost lang={lang} id={route.params.id} go={go} me={me} />
      case 'communityNew':
        return <CommunityNew lang={lang} plot={plot} plots={plots} go={go}
                             onDone={() => reload(plotId)} />
      case 'alerts':
        return <Alerts lang={lang} plot={plot} go={go} onRead={() => setUnread(0)} />
      case 'profile':
        return <Profile lang={lang} onLang={setLangState} me={me} plots={plots} go={go}
                        health={health} demo={demo} onScenario={setScenario} />
      default:
        return <Home lang={lang} me={me} plot={plot} plots={plots} onPlot={setPlotId} go={go}
                     unread={unread} onBell={() => go('alerts')} />
    }
  }

  const activeTab = ['home', 'crop', 'scan', 'community', 'agridoc'].includes(route.name)
    ? route.name
    : ['addField', 'history', 'fields', 'forecast', 'traps', 'soil', 'water']
        .includes(route.name) ? 'crop'
    : ['communityPost', 'communityNew'].includes(route.name) ? 'community'
    : route.name === 'saathi' ? 'agridoc'
    : 'home'

  /* the camera takes the whole screen, so the nav is hidden behind it */
  const fullscreen = route.name === 'scan'

  return (
    <div className="shell">
      {!fullscreen && (
        <Banners online={online} queued={queued} demo={isDemo} stale={staleAt} lang={lang} />
      )}
      {screen()}

      {!fullscreen && (
        <nav className="nav" aria-label="Main">
          {TABS.map(([k, ic]) => (
            <button key={k} aria-current={activeTab === k ? 'page' : undefined}
                    onClick={() => go(k)}>
              {k === 'scan'
                ? <span className="scan-ic">{ic}</span>
                : <span className="ic">{ic}</span>}
              <span className="lbl">{(TAB_LABEL[lang] || TAB_LABEL.en)[k]}</span>

            </button>
          ))}
        </nav>
      )}
    </div>
  )
}

function NoField({ lang, go }) {
  return (
    <>
      <div className="topbar"><h1 className="grow">PRAHARI</h1></div>
      <div className="pad" style={{ paddingTop: 30 }}>
        <div className="empty">
          <div className="ic">🌾</div>
          <div className="h3" style={{ marginTop: 8 }}>
            {lang === 'mr' ? 'आधी शेत नोंदवा' : 'Register a field first'}
          </div>
          <p className="small muted" style={{ marginTop: 6 }}>
            {lang === 'mr'
              ? 'प्रहरीला शेताचे ठिकाण, पीक आणि पेरणीची तारीख हवी — त्याशिवाय हवामानावर आधारित धोका मोजता येत नाही.'
              : 'PRAHARI needs a location, a crop and a sowing date before it can forecast anything.'}
          </p>
          <button className="btn" style={{ marginTop: 16 }} onClick={() => go('addField')}>
            {lang === 'mr' ? 'शेत जोडा' : 'Add a field'}
          </button>
        </div>
      </div>
    </>
  )
}
