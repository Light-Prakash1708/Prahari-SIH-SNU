/* PRAHARI · साथी — the assistant screen.

   Every answer arrives with the rows it came from, and the screen renders them.
   An answer with no source renders as a refusal, visibly different from a
   grounded one — because a farmer who cannot tell those two apart will trust
   both equally, and one of them does not deserve it. */
import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Prov, bi } from '../ui'

const SRC_ICON = {
  threshold: '📏', model: '🌦', weather: '🌦', ipm: '🌿',
  field_record: '📋', reference: '📖', policy: '🛡️', label_claim: '🧪',
}

export default function Saathi({ lang, plot, go }) {
  const [turns, setTurns] = useState([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [meta, setMeta] = useState(null)
  const endRef = useRef(null)

  useEffect(() => {
    api.saathiSuggestions(lang).then(setMeta).catch(() => setMeta(null))
  }, [lang])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns, busy])

  const send = async (text) => {
    const question = (text ?? q).trim()
    if (!question || busy) return
    setQ(''); setErr(null); setBusy(true)
    setTurns(t => [...t, { role: 'me', text: question }])
    try {
      const out = await api.saathiAsk(question, plot?.id, lang)
      setTurns(t => [...t, { role: 'saathi', ...out }])
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <div className="grow">
          <h1>{lang === 'mr' ? 'प्रहरी साथी' : 'PRAHARI Saathi'}</h1>
          <div className="tiny faint" style={{ marginTop: 1 }}>
            {plot ? plot.name : (lang === 'mr' ? 'शेत निवडलेले नाही' : 'no field selected')}
          </div>
        </div>
      </div>

      <div className="pad stack" style={{ paddingTop: 14 }}>
        {turns.length === 0 && (
          <>
            <Card style={{ background: 'var(--g-050)', borderColor: 'var(--g-300)' }}>
              <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
                <div style={{ fontSize: 26 }}>🌿</div>
                <div className="grow">
                  <div className="card-title">
                    {lang === 'mr' ? 'नमस्कार. काय विचारायचे आहे?' : 'Ask me about your field'}
                  </div>
                  <p className="small" style={{ marginTop: 6 }}>{meta?.scope}</p>
                </div>
              </div>
            </Card>

            {meta?.suggestions && (
              <div style={{ display: 'grid', gap: 8 }}>
                {meta.suggestions.map((s, i) => (
                  <button key={i} className="chip" style={{
                    textAlign: 'left', width: '100%', minHeight: 44, padding: '11px 14px',
                  }} onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            )}

            {meta?.will_not_do && (
              <Card className="tight">
                <div className="tiny" style={{ fontWeight: 700, color: 'var(--muted)',
                                               letterSpacing: '.05em', marginBottom: 7 }}>
                  {lang === 'mr' ? 'साथी हे करणार नाही' : 'WHAT SAATHI WILL NOT DO'}
                </div>
                {meta.will_not_do.map((w, i) => (
                  <div className="evid" key={i} style={{ padding: '4px 0' }}>
                    <span className="cross">✗</span><span className="small">{w}</span>
                  </div>
                ))}
              </Card>
            )}
          </>
        )}

        {turns.map((t, i) => t.role === 'me' ? (
          <div key={i} style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <div style={{
              background: 'var(--g-600)', color: '#fff', borderRadius: '16px 16px 4px 16px',
              padding: '10px 14px', maxWidth: '85%', fontSize: 14.5, lineHeight: 1.45,
            }}>{t.text}</div>
          </div>
        ) : (
          <Card key={i} style={{
            borderColor: t.grounded ? 'var(--rule-soft)' : 'var(--warn-line)',
            background: t.grounded ? 'var(--card)' : 'var(--warn-bg)',
          }}>
            {!t.grounded && (
              <div className="row" style={{ gap: 7, marginBottom: 8 }}>
                <span style={{ fontSize: 16 }}>🤷</span>
                <span className="tiny" style={{ fontWeight: 800, color: 'var(--warn)',
                                                letterSpacing: '.05em' }}>
                  {lang === 'mr' ? 'याचे उत्तर देता येत नाही' : 'CANNOT ANSWER THIS'}
                </span>
              </div>
            )}
            <div style={{ fontSize: 14.5, lineHeight: 1.6, whiteSpace: 'pre-line' }}>
              {t.answer}
            </div>

            {t.actions?.length > 0 && (
              <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
                {t.actions.map((a, j) => (
                  <button key={j} className="btn sm ghost"
                          onClick={() => go(a.do, a.target ? { target: a.target } : {})}>
                    {a.label} ›
                  </button>
                ))}
              </div>
            )}

            {t.sources?.length > 0 && (
              <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--rule-soft)' }}>
                <div className="tiny" style={{ fontWeight: 700, color: 'var(--muted)',
                                               letterSpacing: '.05em', marginBottom: 6 }}>
                  {lang === 'mr' ? 'हे कुठून आले' : 'WHERE THIS CAME FROM'}
                </div>
                {t.sources.filter(s => s.detail).map((s, j) => (
                  <div key={j} className="row" style={{
                    gap: 7, alignItems: 'flex-start', padding: '3px 0',
                  }}>
                    <span style={{ fontSize: 12 }}>{SRC_ICON[s.kind] || '·'}</span>
                    <span className="tiny" style={{ color: 'var(--muted)', lineHeight: 1.45 }}>
                      {s.detail}
                      {s.status === 'draft' && (
                        <span className="badge warn" style={{
                          marginLeft: 6, padding: '1px 6px', fontSize: 10,
                        }}>unverified</span>
                      )}
                      {s.generated && (
                        <span className="badge warn" style={{
                          marginLeft: 6, padding: '1px 6px', fontSize: 10,
                        }}>generated weather</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}

        {busy && (
          <Card className="tight">
            <div className="row" style={{ gap: 9 }}>
              <span style={{ fontSize: 15 }}>🌿</span>
              <span className="small muted">
                {lang === 'mr' ? 'नोंदी तपासत आहे…' : 'Looking through your records…'}
              </span>
            </div>
          </Card>
        )}

        {err && <ErrorNote error={err} lang={lang} />}
        <div ref={endRef} />
      </div>

      {/* composer, docked above the tab bar */}
      <div style={{
        position: 'fixed', bottom: 'calc(76px + env(safe-area-inset-bottom))',
        left: '50%', transform: 'translateX(-50%)', width: '100%', maxWidth: 'var(--shell)',
        padding: '10px 12px', background: 'var(--card)', borderTop: '1px solid var(--rule)',
        zIndex: 35,
      }}>
        <form className="row" style={{ gap: 8 }} onSubmit={e => { e.preventDefault(); send() }}>
          <input className="input grow" value={q} onChange={e => setQ(e.target.value)}
                 placeholder={lang === 'mr' ? 'तुमचा प्रश्न लिहा…' : 'Ask about your field…'}
                 style={{ minHeight: 44 }} />
          <button className="btn" type="submit" disabled={busy || !q.trim()}
                  style={{ minWidth: 52, padding: '10px 16px' }} aria-label="Send">↑</button>
        </form>
        <p className="tiny faint center" style={{ marginTop: 6 }}>
          {lang === 'mr'
            ? 'साथी फक्त तपासलेल्या माहितीवरून उत्तर देते — औषधाची मात्रा स्वतःहून सांगत नाही.'
            : 'Saathi answers only from verified records. It will not invent a pesticide dose.'}
        </p>
      </div>
      <div style={{ height: 92 }} />
    </>
  )
}
