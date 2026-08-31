import React, { useEffect, useRef, useState } from 'react'
import { api, SAMPLES } from '../api'
import { Card, Why, Chip, Loading, ErrorNote, t, L } from '../ui'

const STAGES = [
  'Image quality', 'Leaf detection', 'Symptom analysis',
  'Crop context', 'Weather context', 'Differential diagnosis',
]

/* ═══ SCAN ════════════════════════════════════════════════════════════════
   The plant-doctor flow. Three things make it different from every other one:
   guidance BEFORE the shutter, a visible quality gate, and the right to
   refuse afterwards.                                                        */
export function Scan({ plot, lang, onDiagnosed, go }) {
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState(-1)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [preview, setPreview] = useState(null)
  const [picked, setPicked] = useState(null)
  const [answers, setAnswers] = useState({})
  const [refined, setRefined] = useState(null)
  const [caseId, setCaseId] = useState(null)
  const fileRef = useRef()

  async function send(file, sampleId) {
    setBusy(true); setErr(null); setRes(null); setRefined(null)
    setAnswers({}); setCaseId(null); setPicked(sampleId || null)
    setPreview(URL.createObjectURL(file))
    // The stage list is a progress indicator over work that is genuinely
    // happening server-side, not a manufactured delay. It advances on a short
    // timer and is cut short the moment the response lands.
    setStage(0)
    const tick = setInterval(() => setStage(s => (s < STAGES.length - 1 ? s + 1 : s)), 210)
    try {
      const r = await api.scout(plot.id, file)
      setRes(r)
      if (!r.diagnosis?.abstain && r.diagnosis?.top) onDiagnosed?.(r.diagnosis.top.id)
    } catch (e) { setErr(e) } finally {
      clearInterval(tick); setStage(STAGES.length); setBusy(false)
    }
  }

  async function useSample(s) {
    try {
      const blob = await (await fetch(`/samples/${s.id}.jpg`)).blob()
      send(new File([blob], `${s.id}.jpg`, { type: 'image/jpeg' }), s.id)
    } catch { setErr(new Error('Could not load the reference pattern.')) }
  }

  async function submitAnswers() {
    setBusy(true)
    try { setRefined(await api.answers(res.scout_id, answers)) }
    catch (e) { setErr(e) } finally { setBusy(false) }
  }

  async function askExpert() {
    const r = await api.expertRequest(res.scout_id, res.diagnosis?.reason || 'farmer requested')
    setCaseId(r.case.id)
  }

  const dx = res?.diagnosis
  const q = res?.features?.quality
  const shown = refined?.ranked || dx?.ranked || []
  const top = refined?.decisive ? refined.top : (!dx?.abstain ? dx?.top : null)
  const stillBlocked = refined ? !refined.decisive : dx?.abstain
  // A photograph that failed the quality gate invalidates everything computed
  // from it, not just the headline.
  const unreadable = dx?.reason === 'photo-quality'

  return (
    <>
      <header className="mb">
        <p className="eyebrow">{plot.name} · {plot.crop}</p>
        <h1 className="h1">📷 {t(lang, 'takePhoto')}</h1>
        <p className="sub">A bad photograph will be refused, not diagnosed.</p>
      </header>

      <button className={`shot ${preview ? 'has' : ''}`} onClick={() => fileRef.current.click()}>
        {preview
          ? <img src={preview} alt="the leaf you photographed" />
          : <>
              <div style={{ fontSize: '2.4rem', marginBottom: 8 }}>🍃</div>
              <div style={{ fontWeight: 700, fontSize: '1rem' }}>Tap to take or choose a photo</div>
              <div className="sub small mt">Two or three photos give a better answer than one.</div>
            </>}
      </button>
      <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden
             onChange={e => e.target.files[0] && send(e.target.files[0])} />

      {!res && !busy && (
        <div className="guide">
          <div><span>📏</span><span>Fill the frame with <b>one leaf</b></span></div>
          <div><span>🌤️</span><span>Shade it — direct sun washes out the lesion</span></div>
          <div><span>🔄</span><span>Photograph the <b>underside</b> too, if it looks wet</span></div>
          <div><span>🍃</span><span>Include a <b>healthy</b> part of the same leaf</span></div>
        </div>
      )}

      <p className="tiny center mt" style={{ color: 'var(--muted)' }}>
        No camera on this device? These are <b>drawn reference patterns</b>, included so the
        measurement pipeline can be exercised without one:
      </p>
      <div className="samples">
        {SAMPLES.map(s => (
          <button key={s.id} title={s.label} aria-label={s.label}
                  aria-pressed={picked === s.id} onClick={() => useSample(s)}>
            <img src={`/samples/${s.id}.jpg`} alt="" />
            <span>{s.label}</span>
          </button>
        ))}
      </div>

      {busy && !res && (
        <Card title="PRAHARI is checking…">
          <ul className="stages">
            {STAGES.map((s, i) => (
              <li key={s} className={i < stage ? 'done' : i === stage ? 'now' : ''}>
                <span className="k">{i < stage ? '✓' : i + 1}</span>{s}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {err && <ErrorNote error={err} />}

      {res && !busy && (
        <>
          {q && (
            <Card title="Photograph quality">
              <div className="gates">
                {Object.entries(q.checks).map(([k, c]) => (
                  <div className={`gate ${c.pass ? 'pass' : 'fail'}`} key={k}>
                    <div className="l">{k}</div>
                    <div className="v">{c.value} {c.pass ? '✓' : '✗'}</div>
                    <div className="n">needs {c.needed}</div>
                  </div>
                ))}
              </div>
              <p className="tiny mt" style={{ color: 'var(--muted)' }}>
                Measured in {res.features.ms} ms from a 256×256 crop · {res.features.engine}
              </p>
            </Card>
          )}

          {/* ── the answer, or the refusal ─────────────────────────── */}
          {top && !stillBlocked ? (
            <div className="dx mb">
              <p className="most">{t(lang, 'mostLikely')}</p>
              <div className="name">{top.em} {L(lang, top, 'name') || top.name}</div>
              <div className="mr">{top.name_mr || top.mr}</div>
              <div className="row mt">
                <Chip level={top.posterior > 0.75 ? 'high' : 'rising'}>
                  {top.posterior > 0.75 ? 'High confidence' : 'Moderate confidence'}
                  {' · '}{Math.round(top.posterior * 100)}%
                </Chip>
              </div>

              <h3 className="h3" style={{ marginTop: 15 }}>{t(lang, 'whyThink')}</h3>
              <div className="mt">
                <Evidence tick>Symptom pattern measured on the leaf itself, inside a segmented boundary</Evidence>
                <Evidence tick>{res.problem?.name || top.name} occurs on {plot.crop} at {res.crop_stage.label.toLowerCase()}</Evidence>
                <Evidence tick={dx.ranked?.[0]?.weather > 1}>
                  {dx.ranked?.[0]?.weather > 1
                    ? 'Recent weather crossed this disease’s published infection model'
                    : 'Recent weather does NOT favour this disease — counted against it'}
                </Evidence>
                <Evidence tick>
                  {res.prior?.confirmations ?? 0} expert-confirmed cases in {res.taluka} in the last 28 days
                </Evidence>
              </div>

              {res.problem?.scout && (
                <div className="note mt">
                  <b>Check by eye:</b> {lang === 'mr' && res.problem.mr_scout ? res.problem.mr_scout : res.problem.scout}
                </div>
              )}
              {res.problem?.speed && res.problem.speed !== '—' && (
                <p className="small mt"><b>How fast it moves:</b> {res.problem.speed}</p>
              )}

              <button className="btn block mt" onClick={() => go('action', top.id)}>
                {t(lang, 'action')} →
              </button>
            </div>
          ) : (
            <Abstain res={res} refined={refined} lang={lang} caseId={caseId}
                     onExpert={askExpert} onRetake={() => fileRef.current.click()} />
          )}

          {/* ── contextual questions ───────────────────────────────── */}
          {res.questions?.length > 0 && !refined && (
            <Card title="Three quick questions">
              <p className="small mb" style={{ color: 'var(--slate)' }}>
                Only questions that could change the answer are asked. Each one separates two
                candidates the photograph alone cannot.
              </p>
              {res.questions.map(qq => (
                <div className="q" key={qq.id}>
                  <div className="qt">{lang === 'mr' && qq.q_mr ? qq.q_mr : qq.q}</div>
                  <div className="opts">
                    {qq.options.map(o => (
                      <button key={o.v} aria-pressed={answers[qq.id] === o.v}
                              onClick={() => setAnswers(a => ({ ...a, [qq.id]: o.v }))}>
                        {lang === 'mr' && o.t_mr ? o.t_mr : o.t}
                      </button>
                    ))}
                  </div>
                  <p className="tiny mt" style={{ color: 'var(--muted)' }}>{qq.why}</p>
                </div>
              ))}
              <button className="btn block" disabled={!Object.keys(answers).length || busy}
                      onClick={submitAnswers}>
                {busy ? <span className="spin" /> : 'Use my answers'}
              </button>
            </Card>
          )}

          {refined && (
            <Card title={refined.shifted ? 'Your answers changed the answer' : 'Your answers were applied'}>
              {refined.blocked_say && <div className="banner">{refined.blocked_say}</div>}
              {refined.moves.length > 0 ? (
                <table className="tbl">
                  <thead><tr><th>Your answer</th><th>Moved</th><th>By</th></tr></thead>
                  <tbody>
                    {refined.moves.map((m, i) => (
                      <tr key={i}><td>{m.answer}</td><td>{m.candidate.replace(/_/g, ' ')}</td>
                        <td>×{m.multiplier}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <p className="small">No answer you gave changes the ranking.</p>}
              <p className="tiny mt" style={{ color: 'var(--muted)' }}>{refined.note}</p>
            </Card>
          )}

          {/* ── differential ───────────────────────────────────────────
             Suppressed entirely when the photograph itself failed the quality
             gate. Everything below this line is derived from that image, so
             printing "No disease 87%, Late blight 13%" under a card that just
             said the photograph cannot be read is the app contradicting itself
             — and a farmer reading only the big number would act on a figure we
             have already declared meaningless.                          */}
          {unreadable ? (
            <Card title={t(lang, 'otherPossible')}>
              <p className="small">
                Not shown. Every candidate probability is computed from this photograph, and the
                quality gate rejected it — so any ranking underneath would be arithmetic on a
                measurement we have already said is not usable.
              </p>
              <p className="small mt" style={{ color: 'var(--slate)' }}>
                Take the photograph again and the full differential appears. The measured features
                below are kept because they are what failed, and an agronomist can check them.
              </p>
            </Card>
          ) : shown.length > 1 && (
            <Card title={t(lang, 'otherPossible')}>
              {shown.slice(0, 5).map(r => (
                <div className="diff-row" key={r.id}>
                  <div className="diff-n">{r.em} {r.name}</div>
                  <div className="diff-bar">
                    <div className={`diff-fill${stillBlocked || r.posterior < 0.2 ? ' dim' : ''}`}
                         style={{ width: `${Math.max(2, r.posterior * 100)}%` }} />
                    <span className="diff-pct"
                          style={r.posterior > 0.82 && !stillBlocked ? { color: '#fff' } : undefined}>
                      {Math.round(r.posterior * 100)}%
                    </span>
                  </div>
                </div>
              ))}
              {dx?.reason === 'unfamiliar-pattern' && (
                <div className="note mt">
                  These are ranked against each other, but <b>none of them fits well enough</b> —
                  no candidate cleared the {Math.round(dx.ood_floor * 100)}% fit floor. A ranking of
                  poor fits is still a ranking of poor fits, which is why the app declined rather
                  than naming the top row.
                </div>
              )}
              {shown.length > 1 && shown[1].posterior > 0.08 && (
                <p className="small mt" style={{ color: 'var(--slate)' }}>
                  {shown[0].name} and {shown[1].name} can look similar on a leaf.{' '}
                  {shown[0].weather > shown[1].weather
                    ? `Recent weather makes ${shown[0].name} more likely.`
                    : `The confirmed-case history in ${res.taluka} tilts it toward ${shown[0].name}.`}
                </p>
              )}

              <Why label="How each number was reached" open={false}>
                <span className="eq">posterior ∝ prior(taluka, 28 days) × L(image) × L(weather model)</span>
                <table className="tbl">
                  <thead><tr><th>Candidate</th><th>Prior</th><th>Image</th><th>Weather</th><th>Posterior</th></tr></thead>
                  <tbody>
                    {(dx.ranked || []).slice(0, 4).map(r => (
                      <tr key={r.id}>
                        <td>{r.name}</td><td>{Math.round(r.prior * 100)}%</td>
                        <td>×{r.image.toFixed(2)}</td><td>×{r.weather}</td>
                        <td><b>{Math.round(r.posterior * 100)}%</b></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p>
                  A model trained on PlantVillage scores 99% on PlantVillage and <b>19.73%</b> on real
                  field photographs. A model shown eight background pixels and no leaf at all still
                  scores 49% — the label is partly recoverable from the laboratory backdrop. So the
                  leaf is segmented first and every symptom is counted inside it.
                </p>
                <p>
                  <b>It can refuse.</b> Five separate checks: photograph quality; whether anything at
                  all clears the out-of-distribution floor of {Math.round(dx.ood_floor * 100)}%;
                  whether the winner is what fits best; whether any candidate reaches{' '}
                  {Math.round(dx.floors.posterior * 100)}%; and whether the top two are more than{' '}
                  {Math.round(dx.floors.margin * 100)} points apart.
                </p>
              </Why>
            </Card>
          )}

          {/* ── measurements ───────────────────────────────────────── */}
          <Card title="What the app measured">
            {[['Necrosis', res.features.necrosis], ['Chlorosis', res.features.chlorosis],
              ['Powdery', res.features.powder], ['Dark tissue', res.features.dark],
              ['Border sharpness', res.features.edge], ['Leaf in frame', res.features.leaf_fraction]]
              .map(([l, v]) => (
                <div className="chg" key={l}>
                  <span className="l" style={{ fontWeight: 500, fontSize: '.85rem' }}>{l}</span>
                  <span className="v mono">{Math.round(v * 100)}%</span>
                </div>
              ))}
            <div className="chg">
              <span className="l" style={{ fontWeight: 500, fontSize: '.85rem' }}>Distinct lesions</span>
              <span className="v mono">{res.features.lesions}</span>
            </div>
            <p className="tiny mt" style={{ color: 'var(--muted)' }}>
              Every number here is inspectable by an agronomist. A 2.3-million-parameter softmax is not.
            </p>
          </Card>
        </>
      )}
    </>
  )
}

function Evidence({ tick, children }) {
  return (
    <div className="evi">
      <span className="tick" style={tick ? undefined : { color: 'var(--muted)' }}>{tick ? '✓' : '−'}</span>
      <span>{children}</span>
    </div>
  )
}

/* ═══ ABSTENTION AS A FEATURE ══════════════════════════════════════════════ */
function Abstain({ res, refined, lang, caseId, onExpert, onRetake }) {
  const dx = res.diagnosis
  const reason = refined?.blocked_by || dx.reason
  const quality = reason === 'photo-quality'
  const title = reason === 'unfamiliar-pattern'
    ? "This doesn't match anything PRAHARI knows for this crop"
    : reason === 'crop-not-covered'
    ? 'The camera is not used for this crop'
    : quality
    ? 'That photograph cannot be read'
    : "PRAHARI isn't confident enough yet"

  return (
    <div className="abstain mb">
      <h3>🔬 {title}</h3>
      <p className="small" style={{ color: 'var(--ink)', opacity: .88 }}>
        {refined?.blocked_say || dx.explain}
      </p>
      <p className="small mt" style={{ color: 'var(--rising)' }}>
        Recommending a treatment now could make the problem worse — and a wrong spray is the exact
        harm this whole system exists to prevent.
      </p>

      <div className="steps">
        {quality && <div>Take another photo. Fill the frame with one leaf, in shade, and tap the
          leaf on screen before shooting.</div>}
        {!quality && reason !== 'crop-not-covered' &&
          <div>Answer the short questions below — they separate candidates a photograph cannot.</div>}
        {reason === 'crop-not-covered'
          ? <div>Use the weather forecast and the trap count instead. Both work for this crop and
              neither needs a photograph.</div>
          : <div>Ask an expert. Your photo and the measured features go with the request.</div>}
      </div>

      <div className="row mt">
        {quality && <button className="btn ghost sm" onClick={onRetake}>📷 Retake</button>}
        {caseId
          ? <span className="chip rising">Case {caseId} submitted</span>
          : reason !== 'crop-not-covered' &&
            <button className="btn sm" onClick={onExpert}>🔬 {t(lang, 'askExpert')}</button>}
      </div>
    </div>
  )
}
