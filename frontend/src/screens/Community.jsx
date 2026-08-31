/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · Community

   Not a feed. A surveillance instrument that happens to look like one.

   Three things on this screen are load-bearing, and none of them is the
   scrolling:

   1. THE VERIFICATION BADGE. Every post carries one, and the default is grey
      and says "Community advice — not verified" in words. A farmer reading a
      reply that names a pesticide gets a red warning above it, not a footnote
      below it. Nothing in here is allowed to look like a diagnosis.

   2. "I AM SEEING THIS TOO". The most important control on the page and the
      cheapest one to use — one tap, from a farmer who may not write. It is
      what turns three separate worries into a counted signal.

   3. "WHY AM I SEEING THIS?" Each card shows the reasons it was ranked up:
      your taluka, your crop, an expert answered. A farmer can audit their own
      feed, which is more than most feeds allow.

   What is NOT here: follower counts, like counts as a ranking input, exact
   locations, phone numbers, and any way to reach another farmer's field
   records. The server does not send those; this file could not render them.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading, Prov, Sheet, bi } from '../ui'

const TABS = [
  ['for_you', 'For you', 'तुमच्यासाठी'],
  ['nearby', 'Nearby', 'जवळपास'],
  ['experts', 'Experts', 'तज्ज्ञ'],
  ['mine', 'My posts', 'माझ्या नोंदी'],
]

const initials = (s) => String(s || '?').trim().split(/\s+/).slice(0, 2)
  .map(w => w[0]).join('').toUpperCase()

/* The body minus whatever the title already said. */
function rest(post) {
  const body = String(post.body || '')
  const title = String(post.title || '').replace(/…$/, '')
  if (title && body.startsWith(title)) return body.slice(title.length).trim()
  return body
}

/* ── one card ───────────────────────────────────────────────────────────── */
export function PostCard({ post, lang, onOpen, onReact, compact }) {
  const v = post.verification_meta || {}
  const cat = post.category_meta || {}
  return (
    <article className="post">
      <div className="post-head">
        <div className={`avatar ${post.author_role === 'expert' ? 'expert' : ''}`}>
          {initials(post.author_display)}
        </div>
        <div className="grow">
          <div className="post-who">{post.author_display}</div>
          <div className="post-meta">
            <span>📍 {post.place}</span>
            <span>·</span>
            <span>{post.days_ago === 0 ? (lang === 'mr' ? 'आज' : 'Today')
              : `${post.days_ago}${lang === 'mr' ? ' दिवसांपूर्वी' : 'd ago'}`}</span>
            {post.crop_label && <><span>·</span><span>{post.crop_label}</span></>}
          </div>
        </div>
        <span className={`vbadge ${v.tone || 'grey'}`}>
          {v.tone === 'green' ? '✓' : v.tone === 'amber' ? '✎' : v.tone === 'info' ? '👤' : '•'}
          {' '}{bi(lang, v.label, v.label_mr)}
        </span>
      </div>

      <button className="post-body" style={{ display: 'block', width: '100%', textAlign: 'left' }}
              onClick={() => onOpen?.(post)}>
        <div className="post-title">
          <span style={{ marginRight: 6 }}>{cat.icon}</span>{post.title}
        </div>
        {/* A post with no title of its own gets one from its first sentence, so
            rendering both would print that sentence twice. Show the remainder. */}
        {rest(post) && <div className="post-text">{rest(post)}</div>}
      </button>

      {post.images?.length > 0 && (
        <div className="post-imgs">
          {post.images.map(im => (
            <img key={im.id} src={im.url} alt="" loading="lazy" />
          ))}
        </div>
      )}

      {post.symptom_labels?.length > 0 && (
        <div className="post-syms">
          {(lang === 'mr' ? post.symptom_labels_mr : post.symptom_labels).map((s, i) =>
            <span className="sym" key={i}>{s}</span>)}
        </div>
      )}

      {!compact && post.shown_because?.length > 0 && (
        <div className="why-shown">
          <span>{lang === 'mr' ? 'हे का दिसत आहे:' : 'Shown because:'}</span>
          {post.shown_because.slice(0, 3).map((r, i) => <i key={i}>{r}</i>)}
        </div>
      )}

      <div className="post-foot">
        <button className="pact" onClick={() => onReact?.(post, 'same_problem')}
                aria-pressed={false}>
          👀 <span className="n">{post.same_problem_count || 0}</span>
          <span>{lang === 'mr' ? 'मलाही' : 'Me too'}</span>
        </button>
        <button className="pact" onClick={() => onOpen?.(post)}>
          💬 <span className="n">{post.comment_count || 0}</span>
          <span>{lang === 'mr' ? 'उत्तरे' : 'Replies'}</span>
        </button>
        <button className="pact" onClick={() => onReact?.(post, 'saved')}>
          🔖 <span>{lang === 'mr' ? 'जतन' : 'Save'}</span>
        </button>
      </div>
    </article>
  )
}

/* ── the feed ───────────────────────────────────────────────────────────── */
export default function Community({ lang, me, plot, plots, go }) {
  const [tab, setTab] = useState('for_you')
  const [data, setData] = useState(null)
  const [meta, setMeta] = useState(null)
  const [signals, setSignals] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('')

  const load = useCallback(() => {
    setBusy(true); setErr(null)
    api.community({ tab, category: cat || undefined, q: q || undefined })
      .then(setData).catch(setErr).finally(() => setBusy(false))
  }, [tab, cat, q])

  useEffect(load, [load])
  useEffect(() => {
    api.communityMeta().then(setMeta).catch(() => setMeta(null))
    api.mySignals().then(setSignals).catch(() => setSignals(null))
  }, [])

  const react = async (post, kind) => {
    try {
      await api.communityReact(post.id, kind, true)
      load()
      if (kind === 'same_problem') api.mySignals().then(setSignals).catch(() => {})
    } catch (e) { setErr(e) }
  }

  return (
    <>
      <header className="hdr" style={{ paddingBottom: 54 }}>
        <div className="row between">
          <div className="grow">
            <div className="hdr-greet">{lang === 'mr' ? 'शेतकरी समुदाय' : 'Farmer Community'}</div>
            <div className="hdr-sub">
              {lang === 'mr'
                ? 'तुम्ही जे पाहता ते नोंदवा — तीच सर्वात लवकर मिळणारी सूचना आहे.'
                : 'What you notice is the earliest warning this district gets.'}
            </div>
          </div>
          <button className="hdr-bell" aria-label="New post" onClick={() => go('communityNew')}>✏️</button>
        </div>
      </header>

      <div className="pad pull stack">
        {/* what is clustering near this farmer, as counts */}
        {signals?.signals?.length > 0 && (
          <SignalStrip signals={signals.signals} lang={lang} note={signals.what_this_is_not} />
        )}

        <div className="seg" role="tablist">
          {TABS.map(([k, en, mr]) => (
            <button key={k} role="tab" aria-pressed={tab === k} onClick={() => setTab(k)}>
              {bi(lang, en, mr)}
            </button>
          ))}
        </div>

        <div className="row" style={{ gap: 8 }}>
          <input className="input grow" value={q} onChange={e => setQ(e.target.value)}
                 placeholder={lang === 'mr' ? 'पीक, रोग, कीड, लक्षण शोधा…'
                   : 'Search a crop, disease, pest or symptom…'} />
        </div>

        {meta?.categories && (
          <div className="chips">
            <button className="chip" aria-pressed={cat === ''} onClick={() => setCat('')}>
              {lang === 'mr' ? 'सर्व' : 'All'}
            </button>
            {Object.entries(meta.categories).map(([k, c]) => (
              <button key={k} className="chip" aria-pressed={cat === k} onClick={() => setCat(k)}>
                {c.icon} {bi(lang, c.label, c.label_mr)}
              </button>
            ))}
          </div>
        )}

        <button className="btn block" onClick={() => go('communityNew')}>
          {lang === 'mr' ? '✏️ नवीन नोंद करा' : '✏️ Post what you are seeing'}
        </button>

        {busy && <Loading lines={3} />}
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}

        {data && !busy && data.posts.length === 0 && (
          <Empty icon="🌾"
                 title={lang === 'mr' ? 'इथे अजून काही नाही' : 'Nothing here yet'}
                 body={lang === 'mr'
                   ? 'तुमच्या तालुक्यात अजून कोणी नोंद केलेली नाही. पहिली नोंद तुमची असू शकते.'
                   : 'Nobody near you has posted yet. Yours can be the first — and the first report is the one that starts a signal.'} />
        )}

        {data && !busy && data.posts.map(p => (
          <PostCard key={p.id} post={p} lang={lang}
                    onOpen={() => go('communityPost', { id: p.id })}
                    onReact={react} />
        ))}

        {data && (
          <Card className="tight">
            <Prov label={lang === 'mr' ? 'क्रम' : 'Ranking'} value={data.ranking} />
            <Prov label={lang === 'mr' ? 'गोपनीयता' : 'Privacy'}
                  value={bi(lang, data.privacy, data.privacy_mr)} />
          </Card>
        )}
      </div>
    </>
  )
}

/* ── the aggregate strip: counts, never names ───────────────────────────── */
function SignalStrip({ signals, lang, note }) {
  return (
    <>
      {signals.slice(0, 2).map(s => (
        <div className={`signal ${s.tone === 'bad' ? 'bad' : s.tone === 'warn' ? 'warn' : ''}`}
             key={s.id}>
          <div className="row between">
            <div className="g">{bi(lang, s.label, s.label_mr)}</div>
            <span className="badge grey">{s.taluka_name}</span>
          </div>
          <div className="m">
            <b>{bi(lang, s.problem_name, s.problem_name_mr)}</b> — {bi(lang, s.means, s.means_mr)}
          </div>
          <div className="sigcounts">
            <div className="c"><div className="n">{s.distinct_authors}</div>
              <div className="l">{lang === 'mr' ? 'शेतकरी' : 'farmers'}</div></div>
            <div className="c"><div className="n">{s.distinct_villages}</div>
              <div className="l">{lang === 'mr' ? 'गावे' : 'villages'}</div></div>
            <div className="c"><div className="n">{s.diagnoses_n}</div>
              <div className="l">{lang === 'mr' ? 'निदाने' : 'diagnoses'}</div></div>
            <div className="c"><div className="n">{s.expert_confirmations}</div>
              <div className="l">{lang === 'mr' ? 'तज्ज्ञ' : 'expert'}</div></div>
          </div>
          <div className="tiny faint" style={{ marginTop: 10, lineHeight: 1.5 }}>{note}</div>
        </div>
      ))}
    </>
  )
}
