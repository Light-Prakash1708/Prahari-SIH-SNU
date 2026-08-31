/* PRAHARI · scan a leaf, and the diagnosis result.

   The most important rule in this file: when the quality gate rejects a
   photograph, this screen shows the guidance that fixes it and NOTHING ELSE.
   No candidate list, no "most likely", no percentage. A differential drawn
   under an unreadable image is worse than no answer, because a farmer will act
   on it.

   The second rule: the engine that produced the ranking is named on screen,
   every time. When no trained model is configured it says "symptom-feature
   classifier — not a neural network", because calling a heuristic an AI is how
   a system loses the right to be believed when it matters. */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Camera, Card, ErrorNote, Loading, Prov, Why, bi } from '../ui'

export default function Scan({ lang, plot, go, onDone }) {
  const [stage, setStage] = useState('camera')   // camera | working | result
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)

  const capture = async (file) => {
    setStage('working'); setErr(null)
    try {
      const out = await api.scan(plot.id, file)
      setResult(out)
      setStage('result')
      onDone?.()
    } catch (e) { setErr(e); setStage('result') }
  }

  if (stage === 'camera') {
    return <Camera lang={lang} onCapture={capture} onClose={() => go('home')}
                   title={lang === 'mr' ? 'पीक स्कॅन' : 'Scan Crop'} />
  }

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{lang === 'mr' ? 'निदान' : 'Diagnosis Result'}</h1>
      </div>
      <div className="pad stack" style={{ paddingTop: 14 }}>
        {stage === 'working' && (
          <>
            <Card>
              <div className="center" style={{ padding: '22px 8px' }}>
                <div style={{ fontSize: 32 }}>🔬</div>
                <div className="h3" style={{ marginTop: 10 }}>
                  {lang === 'mr' ? 'पान तपासत आहे…' : 'Measuring the leaf…'}
                </div>
                <p className="small muted" style={{ marginTop: 6 }}>
                  {lang === 'mr'
                    ? 'पान वेगळे करून डाग, पिवळेपणा आणि बुरशी मोजली जात आहे.'
                    : 'Segmenting the leaf, then measuring lesion area, chlorosis and powder inside it.'}
                </p>
              </div>
            </Card>
            <Loading lines={2} />
          </>
        )}

        {err && (
          <>
            <ErrorNote error={err} lang={lang} />
            <button className="btn block" onClick={() => { setErr(null); setStage('camera') }}>
              {lang === 'mr' ? 'पुन्हा फोटो काढा' : 'Take another photo'}
            </button>
            <button className="btn block quiet" onClick={() => go('home')}>
              {lang === 'mr' ? 'नंतर करेन' : 'Later'}
            </button>
          </>
        )}

        {result && <Result lang={lang} plot={plot} data={result} go={go}
                           onRetake={() => { setResult(null); setStage('camera') }}
                           onUpdated={setResult} />}
      </div>
    </>
  )
}

/* ═══ the result ═══════════════════════════════════════════════════════ */
function Result({ lang, plot, data, go, onRetake, onUpdated }) {
  const dx = data.diagnosis
  const q = data.quality
  const [answers, setAnswers] = useState({})
  const [after, setAfter] = useState(null)
  const [busy, setBusy] = useState(false)
  const [caseOut, setCaseOut] = useState(data.expert_case || null)

  if (!dx) return <ErrorNote error={{ message: 'No diagnosis was recorded for this observation.' }} />

  /* ── the quality gate refused ────────────────────────────────────────── */
  if (dx.reason === 'photo-quality') {
    return (
      <>
        <Card style={{ borderColor: 'var(--warn-line)', background: 'var(--warn-bg)' }}>
          <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
            <div style={{ fontSize: 26 }}>📷</div>
            <div className="grow">
              <div className="h3" style={{ color: 'var(--warn)' }}>
                {lang === 'mr' ? 'हा फोटो वापरता येणार नाही' : "We can't reliably analyse this photograph"}
              </div>
              <p className="small" style={{ marginTop: 6 }}>
                {lang === 'mr'
                  ? 'प्रहरीने या फोटोवरून कोणतेही निदान केलेले नाही. वाईट फोटोवर अंदाज लावण्यापेक्षा नकार देणे सुरक्षित आहे.'
                  : 'PRAHARI has not diagnosed anything from this image. Refusing a bad photograph is safer than guessing on one.'}
              </p>
            </div>
          </div>
        </Card>

        <Card>
          <div className="card-title" style={{ marginBottom: 8 }}>
            {lang === 'mr' ? 'हे करा' : 'Do this'}
          </div>
          {(q?.failures || []).map((f, i) => (
            <div className="evid" key={i}>
              <span className="cross">→</span>
              <span>{bi(lang, f.msg, f.mr)}</span>
            </div>
          ))}
          <Why label={lang === 'mr' ? 'काय मोजले गेले?' : 'What was measured?'}>
            {Object.entries(q?.checks || {}).map(([k, c]) => (
              <div className="row between small" key={k} style={{ padding: '4px 0' }}>
                <span style={{ textTransform: 'capitalize' }}>{k}</span>
                <span className="mono">
                  {c.value} {c.pass ? '✓' : '✗'} <span className="faint">(needs {c.needed})</span>
                </span>
              </div>
            ))}
            <Prov label="Rule" value="A photograph that fails the quality gate is never diagnosed, and no candidate list is shown underneath it." />
          </Why>
        </Card>

        <button className="btn block" onClick={onRetake}>
          {lang === 'mr' ? 'पुन्हा फोटो काढा' : 'Take another photo'}
        </button>
        <button className="btn block ghost" onClick={() => go('home')}>
          {lang === 'mr' ? 'नंतर करेन' : 'Later'}
        </button>
      </>
    )
  }

  /* ── crop with no reference set, or no model at all ──────────────────── */
  if (dx.reason === 'crop-not-covered' || dx.reason === 'model-unavailable') {
    return (
      <>
        <Card>
          <div className="h3">{lang === 'mr' ? 'कॅमेरा उत्तर देऊ शकत नाही' : 'The camera cannot answer this'}</div>
          <p className="small" style={{ marginTop: 8 }}>{dx.explain}</p>
          <div className="note info" style={{ marginTop: 12 }}>
            {lang === 'mr'
              ? 'तुमची नोंद साठवली आहे. हवामान व मर्यादा इंजिन सल्ला देत राहतील, आणि तुम्ही हे प्रकरण तज्ज्ञांकडे पाठवू शकता.'
              : 'Your observation is recorded. The weather and threshold engines carry the advisory, and you can send this case to an expert.'}
          </div>
        </Card>
        <ExpertButton lang={lang} data={data} caseOut={caseOut} setCaseOut={setCaseOut} />
        <button className="btn block ghost" onClick={onRetake}>
          {lang === 'mr' ? 'पुन्हा फोटो काढा' : 'Take another photo'}
        </button>
      </>
    )
  }

  const diff = after?.differential || dx.differential || []
  const top = after?.top || diff[0]
  const uncertain = after ? !after.decisive : dx.abstain
  const engine = dx.engine || {}

  const submitAnswers = async () => {
    setBusy(true)
    try {
      const out = await api.answer(data.observation.id, answers)
      setAfter(out)
    } catch (e) { /* surfaced below */ } finally { setBusy(false) }
  }

  return (
    <>
      {/* ── headline ────────────────────────────────────────────────────── */}
      <Card>
        <div className="row between" style={{ marginBottom: 10 }}>
          <span className={`badge ${uncertain ? 'warn' : 'ok'}`}>
            {uncertain
              ? (lang === 'mr' ? 'अनिश्चित निदान' : 'Uncertain — not confident enough')
              : (lang === 'mr' ? 'संभाव्य निदान' : 'Likely issue')}
          </span>
          {data.images?.[0]?.thumb_url && (
            <img src={data.images[0].thumb_url} alt="" width={44} height={44}
                 style={{ borderRadius: 10, objectFit: 'cover' }} />
          )}
        </div>

        {top ? (
          <>
            <div className="h1">{bi(lang, top.name, top.name_mr)}</div>
            {top.sci && <div className="sci small">({top.sci})</div>}
            <div style={{ marginTop: 14 }}>
              <div className="row between">
                <span className="small muted">{lang === 'mr' ? 'खात्री' : 'Confidence'}</span>
                <b className="num" style={{ fontSize: 17 }}>{top.confidence_pct}%</b>
              </div>
              <div className="confbar"><i style={{ width: `${top.confidence_pct}%` }} /></div>
            </div>
          </>
        ) : (
          <div className="h2">{lang === 'mr' ? 'निश्चित निदान नाही' : 'No confident diagnosis'}</div>
        )}

        {uncertain && dx.explain && (
          <div className="note warn" style={{ marginTop: 12 }}>
            <b>{lang === 'mr' ? 'प्रहरी खात्रीने सांगू शकत नाही' : 'PRAHARI is not confident enough to name this'}</b>
            <div style={{ marginTop: 5 }}>{dx.explain}</div>
          </div>
        )}

        {/* the engine is always named */}
        <div className="prov" style={{ marginTop: 12 }}>
          <b>{lang === 'mr' ? 'इंजिन' : 'Engine'}:</b> {engine.label || engine.engine}
          {engine.version && engine.version !== 'features-v1' ? ` · v${engine.version}` : ''}
        </div>
      </Card>

      {/* ── differential ────────────────────────────────────────────────── */}
      {diff.length > 1 && (
        <Card>
          <div className="card-title" style={{ marginBottom: 4 }}>
            {lang === 'mr' ? 'इतर शक्यता' : 'Alternative Possibilities'}
          </div>
          <p className="tiny faint" style={{ marginBottom: 6 }}>
            {lang === 'mr'
              ? 'प्रहरी एकच उत्तर देत नाही — सर्व शक्यता त्यांच्या खात्रीसह दाखवते.'
              : 'PRAHARI never forces one answer. Every candidate is shown with its confidence.'}
          </p>
          {diff.slice(1).map(c => (
            <div className="cand" key={c.id}>
              <span className="em">{c.em}</span>
              <span className="nm">{bi(lang, c.name, c.name_mr)}</span>
              <span className="pct">{c.confidence_pct}%</span>
            </div>
          ))}
        </Card>
      )}

      {/* ── evidence ────────────────────────────────────────────────────── */}
      {top && (top.supporting?.length > 0 || top.contradicting?.length > 0) && (
        <Card>
          <div className="card-title" style={{ marginBottom: 6 }}>
            {lang === 'mr' ? 'पुरावा' : 'Evidence Found'}
          </div>
          {(top.supporting || []).map((e, i) =>
            <div className="evid" key={`s${i}`}><span className="tick">✓</span>
              <span>{typeof e === 'string' ? e : bi(lang, e.en, e.mr)}</span></div>)}
          {(top.contradicting || []).map((e, i) =>
            <div className="evid" key={`c${i}`}><span className="cross">✗</span>
              <span>{typeof e === 'string' ? e : bi(lang, e.en, e.mr)}</span></div>)}
          <Why label={lang === 'mr' ? 'हे कसे ठरवले?' : 'How was this ranked?'}>
            <p className="mono tiny">posterior ∝ prior(taluka) × image-fit × weather-model</p>
            <p className="small" style={{ marginTop: 8 }}>
              Three independent sources of evidence, combined by Bayes, with every term visible.
              The taluka prior moves by exactly one integer per expert-confirmed case.
            </p>
            {dx.evidence?.ood_floor != null && (
              <p className="small" style={{ marginTop: 8 }}>
                Out-of-distribution floor {Math.round(dx.evidence.ood_floor * 100)}%: if nothing in
                this crop's reference set fits above it, PRAHARI says so instead of naming the
                least-bad option.
              </p>
            )}
          </Why>
        </Card>
      )}

      {/* ── another photograph ──────────────────────────────────────────
          Offered only when the engine is uncertain. When it is confident,
          asking for more pictures would invite a farmer to keep shooting until
          the answer changes — which is exactly what the backend refuses to let
          happen. */}
      {uncertain && (
        <MoreEvidence lang={lang} observationId={data.observation.id}
                      onUpdated={onUpdated} />
      )}

      {/* ── contextual questions ────────────────────────────────────────── */}
      {uncertain && data.questions?.length > 0 && !after && (
        <Card style={{ borderColor: 'var(--info-line)' }}>
          <div className="card-title">{lang === 'mr' ? 'काही प्रश्न' : 'A few questions'}</div>
          <p className="small muted" style={{ marginTop: 4, marginBottom: 12 }}>
            {lang === 'mr'
              ? 'हे प्रश्न फोटोवरून न कळणारी माहिती देतात. यामुळे निदान निश्चित होऊ शकते.'
              : 'These ask what the photograph cannot show. Your answers may settle it.'}
          </p>
          {data.questions.map(qq => (
            <div key={qq.id} style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>{bi(lang, qq.q, qq.q_mr)}</div>
              <div style={{ display: 'grid', gap: 7 }}>
                {qq.options.map(o => (
                  <button key={o.v} className="chip" aria-pressed={answers[qq.id] === o.v}
                          style={{ textAlign: 'left', width: '100%', minHeight: 44 }}
                          onClick={() => setAnswers(a => ({ ...a, [qq.id]: o.v }))}>
                    {bi(lang, o.t, o.t_mr)}
                  </button>
                ))}
              </div>
              {qq.why && <p className="tiny faint" style={{ marginTop: 6 }}>{qq.why}</p>}
            </div>
          ))}
          <button className="btn block" disabled={busy || !Object.keys(answers).length}
                  onClick={submitAnswers}>
            {busy ? '…' : (lang === 'mr' ? 'उत्तरे पाठवा' : 'Submit answers')}
          </button>
        </Card>
      )}

      {after && (
        <Card style={{ borderColor: after.decisive ? 'var(--ok-line)' : 'var(--warn-line)' }}>
          <div className="card-title">
            {after.decisive
              ? (lang === 'mr' ? 'उत्तरांनी निदान निश्चित झाले' : 'Your answers settled it')
              : (lang === 'mr' ? 'अजूनही निश्चित नाही' : 'Still not decisive')}
          </div>
          {after.moves?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              {after.moves.map((m, i) => (
                <div className="small" key={i} style={{ marginTop: 4 }}>
                  “{m.answer}” → <b>{m.candidate.replace(/_/g, ' ')}</b> ×{m.multiplier}
                </div>
              ))}
            </div>
          )}
          <Prov label="Rule" value={after.note} />
          {!after.decisive && (
            <div className="note warn" style={{ marginTop: 10 }}>
              {lang === 'mr'
                ? 'तज्ज्ञांकडे पाठवणे हा पुढचा योग्य पर्याय आहे.'
                : 'Sending this to an expert is the right next step.'}
            </div>
          )}
        </Card>
      )}

      {/* ── what next ───────────────────────────────────────────────────── */}
      <Card style={{ background: 'var(--g-050)', borderColor: 'var(--g-300)' }}>
        <div className="card-title">{lang === 'mr' ? 'पुढे काय?' : "What's Next?"}</div>
        <p className="small" style={{ marginTop: 6 }}>{bi(lang, data.next?.say, data.next?.say_mr)}</p>
      </Card>

      {/* ── actions ─────────────────────────────────────────────────────── */}
      {!uncertain && top && (
        <button className="btn block" onClick={() => go('decide', { target: top.id })}>
          {lang === 'mr' ? 'व्यवस्थापन पहा' : 'View management'}
        </button>
      )}
      <ExpertButton lang={lang} data={data} caseOut={caseOut} setCaseOut={setCaseOut} />
      <button className="btn block quiet" onClick={onRetake}>
        {lang === 'mr' ? 'दुसरा फोटो' : 'Scan another leaf'}
      </button>
    </>
  )
}

function ExpertButton({ lang, data, caseOut, setCaseOut }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (caseOut) {
    return (
      <Card style={{ borderColor: 'var(--info-line)' }}>
        <div className="row" style={{ gap: 10 }}>
          <div style={{ fontSize: 22 }}>👨‍🌾</div>
          <div className="grow">
            <div className="card-title">
              {lang === 'mr' ? `प्रकरण ${caseOut.id} तज्ज्ञांकडे` : `Case ${caseOut.id} is with an expert`}
            </div>
            <div className="small muted">
              {lang === 'mr'
                ? 'तज्ज्ञ फोटो, हवामान व शेताचा इतिहास पाहून निकाल कळवतील.'
                : 'An agronomist will review the photograph, the weather at your field and its history.'}
            </div>
          </div>
        </div>
      </Card>
    )
  }

  const ask = async () => {
    setBusy(true); setErr(null)
    try {
      const out = await api.askExpert(data.observation.id, { reason: 'Requested by the farmer', urgency: 'normal' })
      setCaseOut(out.case)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <>
      {err && <ErrorNote error={err} lang={lang} />}
      <button className="btn block ghost" disabled={busy} onClick={ask}>
        {busy ? '…' : (lang === 'mr' ? '👨‍🌾 तज्ज्ञांकडे पाठवा' : '👨‍🌾 Request expert review')}
      </button>
    </>
  )
}


/* ═══ another photograph of the same problem ═══════════════════════════
   Shown when the engine is uncertain. Each role tells the farmer WHAT to
   photograph next rather than just asking for "a better photo" — the second
   picture is only useful if it shows something the first one did not.

   The engine re-runs on the new image. It cannot be talked into a diagnosis
   it declined to make: the backend test for that lives in
   tests/test_multi_image.py. */
const ROLES = [
  ['whole_plant', '🌿', 'The whole plant', 'संपूर्ण झाड'],
  ['underside', '🍃', 'Underside of the leaf', 'पानाची खालची बाजू'],
  ['closeup', '🔍', 'Close-up of one spot', 'एका डागाचा जवळून फोटो'],
  ['stem', '🌱', 'Stem or fruit', 'खोड किंवा फळ'],
]

export function MoreEvidence({ lang, observationId, onUpdated }) {
  const [role, setRole] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [rejected, setRejected] = useState(null)

  const send = async (file) => {
    setBusy(true); setErr(null); setRejected(null)
    try {
      const out = await api.addImage(observationId, file, role)
      if (out.added_image && out.added_image.used_for_diagnosis === false) {
        // Saved, but the gate refused it. Say so plainly rather than showing
        // an unchanged result and letting the farmer think it was considered.
        setRejected(out.added_image.quality)
      }
      onUpdated?.(out)
      setRole(null)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  if (role) {
    return <Camera lang={lang} onCapture={send} onClose={() => setRole(null)}
                   title={bi(lang, ...(ROLES.find(r => r[0] === role) || []).slice(2))} />
  }

  return (
    <Card>
      <div className="card-title" style={{ marginBottom: 4 }}>
        {lang === 'mr' ? 'आणखी एक फोटो जोडा' : 'Add another photograph'}
      </div>
      <p className="tiny faint" style={{ marginBottom: 10 }}>
        {lang === 'mr'
          ? 'वेगळ्या बाजूचा फोटो घेतल्यास निदान सुधारू शकते. तोच फोटो पुन्हा दिल्याने काही फरक पडत नाही.'
          : 'A photograph showing something the first one did not can improve the answer. Re-sending the same view will not.'}
      </p>

      <div className="chips">
        {ROLES.map(([k, em, en, mr]) => (
          <button key={k} className="chip" disabled={busy} onClick={() => setRole(k)}>
            {em} {bi(lang, en, mr)}
          </button>
        ))}
      </div>

      {rejected && (
        <div className="note warn" style={{ marginTop: 12 }}>
          <b>{lang === 'mr' ? 'हा फोटो वापरता आला नाही' : 'That photograph could not be used'}</b>
          <ul style={{ margin: '6px 0 0 16px' }}>
            {(rejected.failures || []).map((f, i) => (
              <li key={i} className="small">{bi(lang, f.msg, f.mr)}</li>
            ))}
          </ul>
          <div className="tiny faint" style={{ marginTop: 6 }}>
            {lang === 'mr'
              ? 'फोटो जतन झाला आहे, पण निदानासाठी वापरला नाही.'
              : 'It has been saved to this observation, but it was not fed to the engine.'}
          </div>
        </div>
      )}

      {err && <div style={{ marginTop: 10 }}><ErrorNote error={err} lang={lang} /></div>}
    </Card>
  )
}
