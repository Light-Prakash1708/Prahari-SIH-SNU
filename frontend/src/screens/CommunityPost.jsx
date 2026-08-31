/* PRAHARI · one community post — the thread, the expert verdict, similar cases.

   This screen is where the misinformation rule (spec §17) is actually enforced
   in front of a farmer's eyes: a reply that names a product and a dose is shown
   with a red warning ABOVE it, not a disclaimer at the bottom of the page. The
   server flags it; this file refuses to render it quietly. */
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading, Prov, Sheet, Why, bi } from '../ui'
import { PostCard } from './Community'

const initials = (s) => String(s || '?').trim().split(/\s+/).slice(0, 2)
  .map(w => w[0]).join('').toUpperCase()

export default function CommunityPost({ lang, id, go, me }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [reporting, setReporting] = useState(false)
  const [meta, setMeta] = useState(null)

  const load = useCallback(() => {
    setBusy(true)
    api.communityPost(id).then(setD).catch(setErr).finally(() => setBusy(false))
  }, [id])
  useEffect(load, [load])
  useEffect(() => { api.communityMeta().then(setMeta).catch(() => {}) }, [])

  const send = async () => {
    if (text.trim().length < 2) return
    setSending(true)
    try { await api.communityComment(id, text.trim()); setText(''); load() }
    catch (e) { setErr(e) } finally { setSending(false) }
  }

  const react = async (kind) => {
    try { await api.communityReact(id, kind, true); load() } catch (e) { setErr(e) }
  }

  if (busy && !d) return <><Bar lang={lang} go={go} /><div className="pad"><Loading lines={4} /></div></>
  if (err && !d) return <><Bar lang={lang} go={go} /><div className="pad"><ErrorNote error={err} lang={lang} onRetry={load} /></div></>

  const post = d.post
  const v = post.verification_meta || {}

  return (
    <>
      <Bar lang={lang} go={go} />
      <div className="pad stack" style={{ paddingTop: 12 }}>
        <PostCard post={post} lang={lang} compact onReact={(_, k) => react(k)} />

        {/* the notice, in words, above everything a farmer might act on */}
        {post.notice && (
          <div className="note warn">
            <b>{bi(lang, v.label, v.label_mr)}</b>
            <div style={{ marginTop: 4 }}>{bi(lang, post.notice, post.notice_mr)}</div>
          </div>
        )}

        {post.context && (
          <Card className="tight">
            <div className="card-title" style={{ marginBottom: 8 }}>
              {lang === 'mr' ? 'शेताची माहिती (नोंद करणाऱ्याने जोडलेली)' : 'Field context, attached by the author'}
            </div>
            <div className="small" style={{ lineHeight: 1.6 }}>
              {post.context.crop_label} · {post.context.crop_stage_label}
              {post.context.days_after_sowing != null && ` · ${post.context.days_after_sowing} days after sowing`}
              <br />{post.context.taluka_name}
              {post.context.weather_note && <><br />{post.context.weather_note}</>}
              {post.context.prahari_said && (
                <><br /><b>PRAHARI said:</b> {post.context.prahari_said.problem_name || '—'}
                  {' '}({post.context.prahari_said.confidence} confidence
                  {post.context.prahari_said.abstained ? ', abstained' : ''})</>
              )}
            </div>
            <Prov label={lang === 'mr' ? 'गोपनीयता' : 'Privacy'}
                  value={bi(lang, d.privacy, d.privacy_mr)} />
          </Card>
        )}

        {/* the aggregate answer to "am I alone in this?" */}
        {d.nearby_signal && (
          <div className={`signal ${d.nearby_signal.tone === 'bad' ? 'bad'
            : d.nearby_signal.tone === 'warn' ? 'warn' : ''}`}>
            <div className="g">{bi(lang, d.nearby_signal.label, d.nearby_signal.label_mr)}</div>
            <div className="m">
              {d.nearby_signal.reports} {lang === 'mr' ? 'नोंदी' : 'reports'} ·
              {' '}{d.nearby_signal.villages} {lang === 'mr' ? 'गावे' : 'villages'} ·
              {' '}{d.nearby_signal.taluka_name} · {d.nearby_signal.window_days}
              {lang === 'mr' ? ' दिवसांत' : ' days'}
              <br />{bi(lang, d.nearby_signal.means, d.nearby_signal.means_mr)}
            </div>
          </div>
        )}

        {/* expert verdicts, first, with the badge */}
        {d.expert_responses?.length > 0 && (
          <Card>
            <div className="card-title" style={{ marginBottom: 10 }}>
              {lang === 'mr' ? 'तज्ज्ञांचे उत्तर' : 'Expert response'}
            </div>
            {d.expert_responses.map(r => (
              <div key={r.id} className="reply expert" style={{ marginBottom: 10 }}>
                <div className="avatar expert">{initials(r.expert_name)}</div>
                <div className="bubble">
                  <div className="who">
                    {r.expert_name}
                    <span className="vbadge info">✓ {lang === 'mr' ? 'तज्ज्ञ' : 'Verified expert'}</span>
                    <span className={`vbadge ${r.status_meta?.tone || 'grey'}`}>{r.status}</span>
                  </div>
                  {r.institution && <div className="tiny faint">{r.institution}</div>}
                  <div className="txt">{r.body}</div>
                  {r.verdict_name && (
                    <div className="small" style={{ marginTop: 6 }}>
                      <b>{lang === 'mr' ? 'निर्णय:' : 'Verdict:'}</b> {r.verdict_name}
                      {r.confidence && ` · ${r.confidence} confidence`}
                    </div>
                  )}
                  {r.corrects && (
                    <div className="note warn" style={{ marginTop: 8 }}>
                      {lang === 'mr' ? 'दुरुस्ती: मूळ नोंदीत' : 'Correction: the post said'} {r.corrects}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </Card>
        )}

        {/* the thread */}
        <Card>
          <div className="card-title" style={{ marginBottom: 12 }}>
            {(() => {
              const n = d.comments.filter(c => !c.expert_response_id).length
              return lang === 'mr' ? `उत्तरे (${n})` : `Replies (${n})`
            })()}
          </div>
          {d.comments.filter(c => !c.expert_response_id).length === 0 && (
            <p className="small muted">
              {lang === 'mr' ? 'अजून कोणी उत्तर दिलेले नाही.' : 'Nobody has answered this yet.'}
            </p>
          )}
          <div className="thread">
            {/* An expert's formal response is also a comment, so it appears in
                the thread — but it is already rendered in full above, and
                printing it twice on one screen is noise. */}
            {d.comments.filter(c => !c.expert_response_id).map(c => (
              <div key={c.id}>
                {c.advice_warning && (
                  <div className="note bad" style={{ marginBottom: 6 }}>
                    <b>⚠ {lang === 'mr' ? 'तपासलेला सल्ला नाही' : 'Not a verified recommendation'}</b>
                    <div style={{ marginTop: 4 }}>
                      {bi(lang, c.advice_warning.text, c.advice_warning.text_mr)}
                    </div>
                  </div>
                )}
                <div className={`reply ${c.is_expert ? 'expert' : ''} ${c.parent_id ? 'child' : ''}`}>
                  <div className={`avatar ${c.is_expert ? 'expert' : ''}`}>{initials(c.author_display)}</div>
                  <div className="bubble">
                    <div className="who">
                      {c.author_display}
                      {c.is_expert && <span className="vbadge info">✓ {lang === 'mr' ? 'तज्ज्ञ' : 'Expert'}</span>}
                      {c.place && <span className="tiny faint">📍 {c.place}</span>}
                    </div>
                    <div className="txt">{c.body}</div>
                    <div className="row between" style={{ marginTop: 6 }}>
                      <span className="when">{c.days_ago === 0
                        ? (lang === 'mr' ? 'आज' : 'today') : `${c.days_ago}d`}</span>
                      <button className="btn sm quiet"
                              onClick={() => api.communityReactComment(c.id, 'helpful').then(load)}>
                        👍 {c.helpful_count || 0} {lang === 'mr' ? 'उपयुक्त' : 'Helpful'}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="composer" style={{ marginTop: 14 }}>
            <textarea value={text} onChange={e => setText(e.target.value)}
                      placeholder={lang === 'mr'
                        ? 'तुमचा अनुभव लिहा — तुमच्या शेतात असे झाले होते का?'
                        : 'What did you see in your own field?'} />
            <button className="btn" disabled={sending || text.trim().length < 2} onClick={send}>
              {lang === 'mr' ? 'पाठवा' : 'Send'}
            </button>
          </div>
          <p className="tiny faint" style={{ marginTop: 8, lineHeight: 1.5 }}>
            {lang === 'mr'
              ? 'कृपया कीटकनाशकाचे नाव आणि मात्रा लिहू नका — तो सल्ला तपासलेला नसतो आणि प्रहरी त्यावर इशारा दाखवेल.'
              : 'Please do not post a pesticide and a dose. That advice is not checked by anyone, and PRAHARI will mark it with a warning.'}
          </p>
        </Card>

        {/* similar cases */}
        {d.similar?.length > 0 && (
          <>
            <h2 className="sect-title">{lang === 'mr' ? 'अशाच नोंदी' : 'Similar reports'}</h2>
            {d.similar.map(s => (
              <div key={s.id} style={{ marginBottom: 10 }}>
                <PostCard post={s} lang={lang} compact
                          onOpen={() => go('communityPost', { id: s.id })} />
                {s.similar_because?.length > 0 && (
                  <div className="tiny faint" style={{ padding: '4px 14px' }}>
                    {lang === 'mr' ? 'साम्य:' : 'Similar:'} {s.similar_because.join(' · ')}
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        <div className="row" style={{ gap: 8, marginTop: 6 }}>
          <button className="btn sm quiet grow" onClick={() => setReporting(true)}>
            🚩 {lang === 'mr' ? 'तक्रार करा' : 'Report'}
          </button>
          {post.is_mine && (
            <button className="btn sm quiet grow"
                    onClick={() => api.communityWithdraw(post.id).then(() => go('community'))}>
              🗑 {lang === 'mr' ? 'काढून टाका' : 'Withdraw'}
            </button>
          )}
        </div>
      </div>

      {reporting && (
        <Sheet open onClose={() => setReporting(false)}
               title={lang === 'mr' ? 'काय अडचण आहे?' : 'What is wrong with this?'}>
          <div className="stack">
            {Object.entries(meta?.report_reasons || {}).map(([k, r]) => (
              <button key={k} className="btn block ghost" onClick={async () => {
                try { await api.communityReport(post.id, k); setReporting(false); load() }
                catch (e) { setErr(e); setReporting(false) }
              }}>{bi(lang, r.label, r.label_mr)}</button>
            ))}
            <p className="tiny faint" style={{ lineHeight: 1.5 }}>
              {lang === 'mr'
                ? 'एका तक्रारीवर नोंद काढली जात नाही. अनेक स्वतंत्र तक्रारी आल्यास ती तपासणीसाठी थांबवली जाते.'
                : 'PRAHARI does not remove a post because one person disagrees. Several independent reports flag it for a moderator, and an expert can correct it instead.'}
            </p>
          </div>
        </Sheet>
      )}
    </>
  )
}

function Bar({ lang, go }) {
  return (
    <div className="topbar">
      <button className="icon-btn" onClick={() => go('community')} aria-label="Back">←</button>
      <h1 className="grow">{lang === 'mr' ? 'नोंद' : 'Post'}</h1>
    </div>
  )
}
