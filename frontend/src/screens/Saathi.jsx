/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · AgriDoc (साथी) — the assistant screen

   Saurjya's AI-agronomist sheet: the dark forest header with its avatar and
   live dot, the bubble thread, the suggestion rail, the pill composer with its
   round send button.

   What is NOT Saurjya's is the thing that matters. His mock replies with
   confident dosages. This one answers only from rows the server can point at,
   and an ungrounded answer renders as a visibly different bubble — because a
   farmer who cannot tell a sourced answer from an unsourced one will trust
   both equally, and one of them does not deserve it. Every source the server
   returns is printed under the bubble that used it.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { ErrorNote, bi } from '../ui'
import Icon from '../shell/Icon'
import './saurjya.css'

const SRC_ICON = {
  threshold: '📏', model: '🌦', weather: '🌦', ipm: '🌿',
  field_record: '📋', reference: '📖', policy: '🛡️', label_claim: '🧪',
}

const T = {
  mr: {
    name: 'प्रहरी अ‍ॅग्रीडॉक', status: 'ऑनलाइन · शेताच्या नोंदींवरून',
    greet: 'नमस्कार. मी तुमच्या शेताच्या नोंदी, हवामान मॉडेल आणि तपासलेल्या शिफारशी वापरून उत्तर देतो — दुसरे काहीही नाही.',
    ask: 'तुमच्या शेताबद्दल विचारा…', thinking: 'नोंदी तपासत आहे…',
    cannot: 'याचे उत्तर देता येत नाही', where: 'हे कुठून आले',
    noField: 'शेत निवडलेले नाही', wont: 'अ‍ॅग्रीडॉक हे करणार नाही',
    foot: 'अ‍ॅग्रीडॉक फक्त तपासलेल्या नोंदींवरून उत्तर देते — औषधाची मात्रा स्वतःहून सांगत नाही.',
  },
  en: {
    name: 'PRAHARI AgriDoc', status: 'Online · answers from your field records',
    greet: 'Namaste. I answer from your own field records, the weather models running on this plot, and verified recommendations — nothing else.',
    ask: 'Ask about your field…', thinking: 'Looking through your records…',
    cannot: 'Cannot answer this', where: 'Where this came from',
    noField: 'no field selected', wont: 'What AgriDoc will not do',
    foot: 'AgriDoc answers only from verified records. It will not invent a pesticide dose.',
  },
}
const t = (lang, k) => (T[lang] || T.en)[k] ?? T.en[k]

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
    setTurns(prev => [...prev, { role: 'me', text: question }])
    try {
      const out = await api.saathiAsk(question, plot?.id, lang)
      setTurns(prev => [...prev, { role: 'saathi', ...out }])
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <>
      {/* Saurjya's agronomist header */}
      <div className="ad-head">
        <span className="ad-head__avatar"><Icon name="robot" size={22} /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="ad-head__name">{t(lang, 'name')}</div>
          <div className="ad-head__status">
            <span className="ad-dot" />
            {plot ? `${plot.name} · ${t(lang, 'status')}` : t(lang, 'noField')}
          </div>
        </div>
      </div>

      <div className="ad-thread">
        {/* The greeting is a claim about scope, so it carries the server's own
            description of what this assistant may answer rather than a
            friendly sentence written here. */}
        <div className="ad-bubble ad-bubble--bot">
          {t(lang, 'greet')}
          {meta?.scope && (
            <div className="tiny muted" style={{ marginTop: 8, lineHeight: 1.5 }}>{meta.scope}</div>
          )}
        </div>

        {turns.length === 0 && meta?.will_not_do?.length > 0 && (
          <div className="ad-bubble ad-bubble--bot" style={{ maxWidth: '92%' }}>
            <div className="tiny" style={{ fontWeight: 800, color: 'var(--muted)',
                                           letterSpacing: '.05em', marginBottom: 7,
                                           textTransform: 'uppercase' }}>
              {t(lang, 'wont')}
            </div>
            {meta.will_not_do.map((w, i) => (
              <div key={i} className="evid" style={{ padding: '3px 0' }}>
                <span className="cross">✗</span><span className="small">{w}</span>
              </div>
            ))}
          </div>
        )}

        {turns.map((turn, i) => turn.role === 'me' ? (
          <div key={i} className="ad-bubble ad-bubble--me">{turn.text}</div>
        ) : (
          <div key={i}
               className={'ad-bubble ad-bubble--bot' + (turn.grounded ? '' : ' ad-bubble--refusal')}
               style={{ maxWidth: '92%' }}>
            {!turn.grounded && (
              <div className="tiny" style={{ fontWeight: 800, letterSpacing: '.05em',
                                             textTransform: 'uppercase', marginBottom: 7 }}>
                🤷 {t(lang, 'cannot')}
              </div>
            )}

            <div style={{ whiteSpace: 'pre-line' }}>{turn.answer}</div>

            {turn.actions?.length > 0 && (
              <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
                {turn.actions.map((a, j) => (
                  <button key={j} className="ad-chip"
                          onClick={() => go(a.do, a.target ? { target: a.target } : {})}>
                    {a.label} ›
                  </button>
                ))}
              </div>
            )}

            {turn.sources?.filter(s => s.detail).length > 0 && (
              <div className="ad-sources">
                <div className="tiny" style={{ fontWeight: 800, color: 'var(--muted)',
                                               letterSpacing: '.05em', textTransform: 'uppercase' }}>
                  {t(lang, 'where')}
                </div>
                {turn.sources.filter(s => s.detail).map((s, j) => (
                  <div key={j} className="ad-source">
                    <span>{SRC_ICON[s.kind] || '·'}</span>
                    <span>
                      {s.detail}
                      {s.status === 'draft' && (
                        <span className="badge warn" style={{ marginLeft: 6, padding: '1px 6px',
                                                              fontSize: 10 }}>unverified</span>
                      )}
                      {s.generated && (
                        <span className="badge warn" style={{ marginLeft: 6, padding: '1px 6px',
                                                              fontSize: 10 }}>generated weather</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {busy && (
          <div className="ad-bubble ad-bubble--bot">
            <span className="ad-typing"><i /><i /><i /></span>
            <span className="small muted" style={{ marginLeft: 8 }}>{t(lang, 'thinking')}</span>
          </div>
        )}

        {err && <ErrorNote error={err} lang={lang} />}
        <div ref={endRef} />
      </div>

      {meta?.suggestions?.length > 0 && (
        <div className="ad-chips">
          {meta.suggestions.map((s, i) => (
            <button key={i} className="ad-chip" onClick={() => send(s)}>{s}</button>
          ))}
        </div>
      )}

      <form className="ad-composer" onSubmit={e => { e.preventDefault(); send() }}>
        <input value={q} onChange={e => setQ(e.target.value)}
               placeholder={t(lang, 'ask')} aria-label={t(lang, 'ask')} />
        <button className="ad-send" type="submit" disabled={busy || !q.trim()} aria-label="Send">
          <Icon name="send" size={18} />
        </button>
      </form>

      {/* the floating bar sits over the foot of every screen, so this line
          reserves room for it rather than being half-hidden behind it */}
      <p className="tiny faint center"
         style={{ padding: '10px 16px calc(var(--botnav-h) + 8px)', lineHeight: 1.5 }}>
        {bi(lang, T.en.foot, T.mr.foot)}
      </p>
    </>
  )
}
