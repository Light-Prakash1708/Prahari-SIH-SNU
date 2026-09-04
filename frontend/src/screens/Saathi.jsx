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
import { ErrorNote, Sheet, bi } from '../ui'
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
    keyTitle: 'उत्तर अधिक सोपे करा', keyOff: 'किल्ली नाही — ठराविक मजकूर',
    keyOn: 'जोडलेले', keySave: 'जोडा', keyRemove: 'किल्ली काढा',
    keyLabel: 'तुमची API किल्ली इथे टाका', keyClose: 'बंद करा',
  },
  en: {
    name: 'PRAHARI AgriDoc', status: 'Online · answers from your field records',
    greet: 'Namaste. I answer from your own field records, the weather models running on this plot, and verified recommendations — nothing else.',
    ask: 'Ask about your field…', thinking: 'Looking through your records…',
    cannot: 'Cannot answer this', where: 'Where this came from',
    noField: 'no field selected', wont: 'What AgriDoc will not do',
    foot: 'AgriDoc answers only from verified records. It will not invent a pesticide dose.',
    keyTitle: 'Better wording', keyOff: 'No key — answers are templated',
    keyOn: 'Connected', keySave: 'Connect', keyRemove: 'Remove key',
    keyLabel: 'Paste your API key', keyClose: 'Close',
  },
}
const t = (lang, k) => (T[lang] || T.en)[k] ?? T.en[k]

/* The order is the order a farmer reads in: what, why, then what to do about
   it. `answer` is deliberately not listed — it is already the prose above, and
   printing it twice under a heading makes the bubble look padded. */
const SECTION_ORDER = ['why', 'what_to_check', 'what_to_do_now', 'when_to_escalate', 'sources']
const SECTION_LABEL = {
  why: ['Why', 'का'],
  what_to_check: ['What to check', 'काय तपासावे'],
  what_to_do_now: ['What to do now', 'आता काय करावे'],
  when_to_escalate: ['When to ask an expert', 'तज्ज्ञांना कधी विचारावे'],
  sources: ['Based on', 'आधार'],
}

export default function Saathi({ lang, plot, go }) {
  const [turns, setTurns] = useState([])
  const [keyOpen, setKeyOpen] = useState(false)
  const [keyState, setKeyState] = useState(null)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [meta, setMeta] = useState(null)
  const endRef = useRef(null)

  useEffect(() => {
    api.saathiSuggestions(lang).then(setMeta).catch(() => setMeta(null))
  }, [lang])

  /* Whether a key is configured changes the header, so it is loaded once and
     re-read after the sheet closes. The key itself never comes back — only
     whether one exists and its last four characters. */
  const loadKey = () => api.saathiKey().then(setKeyState).catch(() => setKeyState(null))
  useEffect(() => { loadKey() }, [])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns, busy])

  const send = async (text) => {
    const question = (text ?? q).trim()
    if (!question || busy) return
    setQ(''); setErr(null); setBusy(true)
    setTurns(prev => [...prev, { role: 'me', text: question }])
    try {
      const out = await api.saathiAsk(question, plot?.id, lang, true)
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
        <button className="ad-head__gear" onClick={() => setKeyOpen(true)}
                aria-label={t(lang, 'keyTitle')}>
          <Icon name="gear" size={18} />
          {keyState?.configured && <span className="ad-head__gear-dot" />}
        </button>
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

        {/* The limits stay on the opening screen — they are the reason this
            assistant can be trusted with a pesticide question — but folded, so
            four refusals do not fill a phone before the farmer has asked
            anything. Shut by default, one tap, no network. */}
        {turns.length === 0 && meta?.will_not_do?.length > 0 && (
          <details className="ad-wont">
            <summary>{t(lang, 'wont')}</summary>
            {meta.will_not_do.map((w, i) => (
              <div key={i} className="evid" style={{ padding: '3px 0' }}>
                <span className="cross">✗</span>
                <span className="small">
                  {typeof w === 'string' ? w : bi(lang, w.en, w.mr)}
                </span>
              </div>
            ))}
          </details>
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

            {/* The same answer in named parts, when the model could produce
                them from the same records. Absent parts stay absent — a heading
                with nothing under it would read as "nothing to check here",
                which is a different claim from "PRAHARI does not know". */}
            {turn.sections?.available && (
              <div className="ad-sections">
                {SECTION_ORDER.filter(k => turn.sections.fields[k]).map(k => (
                  <div key={k} className="ad-section">
                    <div className="ad-section__h">
                      {SECTION_LABEL[k] ? bi(lang, SECTION_LABEL[k][0], SECTION_LABEL[k][1]) : k}
                    </div>
                    <div className="ad-section__b">{turn.sections.fields[k]}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Says which words the farmer is reading. A reworded answer is
                marked, and so is a rewording that was thrown away — an answer
                that quietly fell back would hide the one event worth seeing. */}
            {turn.llm?.used && (
              <div className="ad-bubble__llm" title={turn.llm.note}>
                <Icon name="robot" size={11} />
                {bi(lang, `Worded by ${turn.llm.provider} · numbers checked against the records`,
                          `${turn.llm.provider} ने मांडलेले · आकडे नोंदींशी तपासले`)}
              </div>
            )}
            {turn.llm?.available && !turn.llm.used && turn.llm.reason
              && !turn.llm.reason.startsWith('no provider') && (
              /* What the farmer is told and what an operator needs are two
                 different sentences. "provider returned HTTP 404" is the second
                 one and it was reaching the first: it reads like the answer
                 above is broken, when the answer above is the retrieved one and
                 is exactly as good as it always was. The status stays in the
                 tooltip for whoever is debugging. */
              <div className="ad-bubble__llm" title={turn.llm.reason}
                   style={{ color: 'var(--warn)',
                            background: 'var(--warn-bg)',
                            borderColor: 'var(--warn-line)' }}>
                {bi(lang, 'AI wording is temporarily unavailable — this answer comes '
                          + 'straight from your field records.',
                          'सध्या एआय भाषांतर उपलब्ध नाही — हे उत्तर थेट तुमच्या नोंदींवरून आहे.')}
              </div>
            )}

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

      <KeySheet open={keyOpen} lang={lang} state={keyState}
                onClose={() => { setKeyOpen(false); loadKey() }} />
    </>
  )
}

/* ── the optional language-model key ────────────────────────────────────────
   What a key changes, and what it cannot:

     changes   the WORDING of an answer — full sentences in Marathi instead of
               an assembled template
     cannot    where the answer comes from. Retrieval runs first and unchanged;
               the model is handed only what PRAHARI retrieved, and the server
               checks every number in its reply against those facts before the
               farmer sees it. A number that is not in the records means the
               model's version is discarded and the retrieved answer stands.

   The key is verified against the provider before it is stored, encrypted at
   rest, and never sent back to this screen — only whether one exists and its
   last four characters, so the owner can tell which key is in place.
   ═══════════════════════════════════════════════════════════════════════════ */
function KeySheet({ open, lang, state, onClose }) {
  const [provider, setProvider] = useState('gemini')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [ok, setOk] = useState(null)

  useEffect(() => { if (open) { setValue(''); setErr(null); setOk(null) } }, [open])

  const save = async () => {
    setBusy(true); setErr(null)
    try { setOk(await api.saathiKeySet(provider, value.trim())); setValue('') }
    catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const clear = async () => {
    setBusy(true); setErr(null)
    try { setOk(await api.saathiKeyClear()) }
    catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const cur = ok || state
  const providers = cur?.providers || [
    { id: 'gemini', label: 'Google Gemini', where: 'aistudio.google.com/apikey' },
    { id: 'openai', label: 'OpenAI', where: 'platform.openai.com/api-keys' },
  ]
  const chosen = providers.find(p => p.id === provider)

  return (
    <Sheet open={open} onClose={onClose} title={t(lang, 'keyTitle')}>
      <div className="ad-key">
        <div className={'ad-key__state' + (cur?.configured ? ' is-on' : '')}>
          <Icon name={cur?.configured ? 'shield' : 'info'} size={16} />
          {cur?.configured
            ? <span>{t(lang, 'keyOn')} · {cur.key?.provider}{' '}
                <span className="ad-key__hint">{cur.key?.hint}</span></span>
            : <span>{t(lang, 'keyOff')}</span>}
        </div>

        <p className="ad-key__policy">{bi(lang, cur?.policy, cur?.policy_mr)}</p>

        {err && <ErrorNote error={err} lang={lang} />}

        <div className="ad-prov">
          {providers.map(p => (
            <button key={p.id} className={provider === p.id ? 'is-on' : ''}
                    onClick={() => setProvider(p.id)}>{p.label}</button>
          ))}
        </div>

        <label className="field" style={{ marginBottom: 0 }}>
          <span className="lbl">{t(lang, 'keyLabel')}</span>
          <input className="input" type="password" value={value} spellCheck={false}
                 autoComplete="off" placeholder={provider === 'gemini' ? 'AIza…' : 'sk-…'}
                 onChange={e => setValue(e.target.value)} />
          <span className="hint">{chosen?.where}</span>
        </label>

        <button className="btn block" disabled={busy || value.trim().length < 8}
                onClick={save}>{busy ? '…' : t(lang, 'keySave')}</button>
        {cur?.configured && (
          <button className="btn quiet block" disabled={busy} onClick={clear}>
            {t(lang, 'keyRemove')}
          </button>
        )}
        <button className="btn quiet block" onClick={onClose}>{t(lang, 'keyClose')}</button>
      </div>
    </Sheet>
  )
}
