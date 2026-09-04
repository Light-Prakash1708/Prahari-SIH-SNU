/* PRAHARI · the explanation and the flashcards for a scan result.

   Both are WORDING, not knowledge. The vision engine decides what was found
   and how sure it is; the reference tables hold what the problem looks like,
   how fast it moves, the criteria that forecast it and the published cultural
   steps. The assistant is handed exactly those and asked to put them into
   short sentences — and when no key is configured, or the provider is down, or
   its answer fails the guards, the backend serves the retrieved text instead.
   So this component has no "AI unavailable" empty state for the cards: there
   is always something to read, and only the wording changes.

   No chemical product or dose appears here. Those reach a farmer through the
   recommendation screen, behind the threshold gate, with the arithmetic shown.
   The backend keeps them out of the facts entirely, which is what makes that
   true rather than merely intended. */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Loading, bi } from '../ui'

const T = {
  explain:  ['What this means', 'याचा अर्थ'],
  cards:    ['About this problem', 'या समस्येबद्दल'],
  worded:   ['Worded by AI from PRAHARI records', 'प्रहरीच्या नोंदींवरून AI ने मांडलेले'],
  ref:      ['From PRAHARI reference', 'प्रहरी संदर्भातून'],
  detected: ['Detected', 'आढळले'],
  notFound: ['Not identified', 'ओळखता आले नाही'],
  policy:   ['No product or dose appears here — open the recommendation screen for that.',
             'इथे औषध किंवा मात्रा दिलेली नाही — त्यासाठी शिफारस स्क्रीन पहा.'],
}
const t = (lang, k) => bi(lang, T[k][0], T[k][1])

const SECTION_LABEL = {
  what_was_found: ['What was found', 'काय आढळले'],
  how_sure: ['How sure', 'किती खात्री'],
  symptoms: ['Symptoms', 'लक्षणे'],
  likely_causes: ['Likely causes', 'संभाव्य कारणे'],
  severity: ['Severity', 'तीव्रता'],
  inspect_next: ['Inspect next', 'पुढे काय पहावे'],
  prevention: ['Prevention', 'प्रतिबंध'],
  management: ['Management', 'व्यवस्थापन'],
  cautions: ['Cautions', 'सावधगिरी'],
}
const ORDER = Object.keys(SECTION_LABEL)

export default function DiseaseCards({ lang, observationId, problem, plotId }) {
  const [ex, setEx] = useState(null)
  const [cards, setCards] = useState(null)
  const [busy, setBusy] = useState(true)

  useEffect(() => {
    let live = true
    setBusy(true)
    const jobs = [
      observationId ? api.scanExplain(observationId, lang).catch(() => null)
                    : Promise.resolve(null),
      problem ? api.flashcards(problem, plotId, lang).catch(() => null)
              : Promise.resolve(null),
    ]
    Promise.all(jobs).then(([e, c]) => {
      if (!live) return
      setEx(e); setCards(c)
    }).finally(() => live && setBusy(false))
    return () => { live = false }
  }, [observationId, problem, plotId, lang])

  if (busy) return <Card><Loading lines={3} /></Card>

  const sections = ORDER
    .map(k => [k, ex?.sections?.[k]])
    .filter(([, v]) => v && String(v).trim())
  const list = cards?.cards || []
  if (!sections.length && !list.length) return null

  return (
    <>
      {sections.length > 0 && (
        <Card>
          <div className="row between" style={{ marginBottom: 8 }}>
            <div className="card-title">{t(lang, 'explain')}</div>
            <span className={`dc-tag ${ex.abstained ? 'unknown' : 'found'}`}>
              {ex.abstained ? t(lang, 'notFound') : t(lang, 'detected')}
            </span>
          </div>
          <div className="dc-sections">
            {sections.map(([k, v]) => (
              <div className="dc-sec" key={k}>
                <span className="dc-sec__k">
                  {bi(lang, SECTION_LABEL[k][0], SECTION_LABEL[k][1])}
                </span>
                <p className="dc-sec__b">{v}</p>
              </div>
            ))}
          </div>
          <p className="tiny faint dc-foot">
            {ex.ai?.used ? t(lang, 'worded') : t(lang, 'ref')}
          </p>
        </Card>
      )}

      {list.length > 0 && (
        <Card>
          <div className="row between" style={{ marginBottom: 8 }}>
            <div className="card-title">{t(lang, 'cards')}</div>
            <span className="tiny faint">
              {cards.ai?.used ? t(lang, 'worded') : t(lang, 'ref')}
            </span>
          </div>
          <div className="dc-grid">
            {list.map(c => (
              <div className="dc-card" key={c.key}>
                <div className="dc-card__q">{bi(lang, c.label, c.label_mr)}</div>
                <div className="dc-card__a">{c.body}</div>
              </div>
            ))}
          </div>
          <p className="tiny faint dc-foot">{t(lang, 'policy')}</p>
        </Card>
      )}
    </>
  )
}
