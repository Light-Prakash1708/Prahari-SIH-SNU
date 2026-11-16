/* PRAHARI · the one page a farmer can hand to somebody else.

   The problem this solves is not a missing document. It is that a farmer
   standing in front of a Krishi Sahayak has to reconstruct the whole case from
   memory — what the scan said, when, what they did, whether it helped, what
   the expert decided — and the parts they forget are usually the parts that
   matter.

   So every line here is a row that already exists. Nothing is computed for the
   report and nothing is estimated to fill a gap: a field with no expert
   verdict prints that it has none, which is information. The disclaimer is not
   decoration — this page will be read by people who did not watch it being
   made, and it has to say what it is. */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Loading, bi, fmtDate } from '../ui'
import Outcomes from './Outcomes'

const TRAJ = {
  improving: ['🟢 Improving', '🟢 सुधारत आहे'],
  stable:    ['🟢 Stable', '🟢 स्थिर'],
  watch:     ['🟡 Watch', '🟡 लक्ष ठेवा'],
  worsening: ['🔴 Worsening', '🔴 बिघडत आहे'],
  unknown:   ['⚪ Not known yet', '⚪ अजून माहीत नाही'],
}

export default function Report({ lang, plot, go }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [outcomes, setOutcomes] = useState(null)

  const load = () => {
    if (!plot) return
    setErr(null); setD(null); setOutcomes(null)
    api.fieldReport(plot.id).then(setD).catch(setErr)
    // Its own request and its own failure: the report stands without it.
    api.outcomes(plot.id).then(setOutcomes).catch(() => setOutcomes(null))
  }
  useEffect(load, [plot?.id])
  if (!plot) return null

  const row = (label, labelMr, value) => value ? (
    <div className="rp-row">
      <span className="rp-k">{bi(lang, label, labelMr)}</span>
      <span className="rp-v">{value}</span>
    </div>
  ) : null

  const none = bi(lang, 'None recorded', 'नोंद नाही')

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('home')} aria-label="Back">‹</button>
        <h1 className="grow">{bi(lang, 'Field report', 'शेत अहवाल')}</h1>
        {d && (
          /* The browser's own print dialog, which on a phone offers "Save as
             PDF" and on a shared device offers the printer an extension
             office already has. No new dependency, and nothing to upload. */
          <button className="btn sm ghost" onClick={() => window.print()}>
            {bi(lang, 'Print / Save', 'छापा / जतन')}
          </button>
        )}
      </div>

      <div className="pad stack mg" style={{ paddingTop: 14 }}>
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}
        {!d && !err && <Loading lines={5} />}

        {d && (
          <div className="rp">
            <div className="rp-head">
              <div className="rp-brand">PRAHARI</div>
              <div className="rp-title">{bi(lang, 'Field report', 'शेत अहवाल')}</div>
              <div className="tiny muted">
                {bi(lang, 'Generated', 'तयार केले')} {fmtDate(d.generated_at, lang)}
              </div>
            </div>

            <Card>
              <div className="card-title">{bi(lang, 'The field', 'शेत')}</div>
              {row('Field', 'शेत', d.plot?.name)}
              {row('Crop', 'पीक', d.plot?.crop)}
              {row('Area', 'क्षेत्र', d.plot?.area_acre ? `${d.plot.area_acre} acre` : null)}
              {row('Village', 'गाव', d.plot?.village)}
              {row('Taluka', 'तालुका', d.taluka_name)}
              {row('Sown on', 'लागवड', d.plot?.sown_on ? fmtDate(d.plot.sown_on, lang) : null)}
              {row('Crop stage', 'अवस्था',
                   d.crop_stage?.label ? bi(lang, d.crop_stage.label, d.crop_stage.label_mr) : null)}
            </Card>

            <Card>
              <div className="card-title">{bi(lang, 'Current condition', 'सध्याची स्थिती')}</div>
              {d.health?.unavailable ? (
                <p className="small muted" style={{ marginTop: 6 }}>
                  {bi(lang,
                    'The crop-health score could not be calculated because weather for this field was unavailable. Nothing has been estimated in its place.',
                    'हवामान उपलब्ध नसल्याने पीक-आरोग्य गुण काढता आला नाही. अंदाजाने काहीही भरलेले नाही.')}
                </p>
              ) : (
                <>
                  {row('Crop-health score', 'पीक-आरोग्य गुण',
                       d.health?.score != null ? `${d.health.score} / 100` : null)}
                  {row('Band', 'श्रेणी', d.health?.band_label
                    ? bi(lang, d.health.band_label, d.health.band_label_mr) : null)}
                  {d.health?.terms?.length > 0 && (
                    <div style={{ marginTop: 9 }}>
                      {d.health.terms.slice(0, 4).map((t, i) => (
                        <div className="evid" key={i}>
                          <span className="tick">•</span>
                          <span>{bi(lang, t.label || t.message, t.label_mr || t.message_mr)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="tiny faint" style={{ marginTop: 9 }}>{d.health?.meaning}</p>
                </>
              )}
            </Card>

            <Card>
              <div className="card-title">{bi(lang, 'Direction', 'दिशा')}</div>
              <div className="rp-traj">
                {bi(lang, TRAJ[d.trajectory?.state]?.[0] || '—',
                          TRAJ[d.trajectory?.state]?.[1] || '—')}
              </div>
              {d.trajectory?.note ? (
                <p className="small muted" style={{ marginTop: 6 }}>
                  {bi(lang, d.trajectory.note, d.trajectory.note_mr)}
                </p>
              ) : (
                <div style={{ marginTop: 7 }}>
                  {(d.trajectory?.reasons || []).map((r, i) => (
                    <div className="evid" key={i}>
                      <span className="tick">•</span>
                      <span>{bi(lang, r.text, r.text_mr)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <div className="card-title">{bi(lang, 'Latest scan', 'शेवटची तपासणी')}</div>
              {d.latest_diagnosis ? (
                <>
                  {row('Found', 'आढळले', d.latest_diagnosis.abstained
                    ? bi(lang, 'The camera declined to name it',
                               'कॅमेऱ्याने नाव सांगितले नाही')
                    : bi(lang, d.latest_diagnosis.problem_name,
                               d.latest_diagnosis.problem_name_mr))}
                  {row('On', 'दिनांक', fmtDate(d.latest_diagnosis.created_at, lang))}
                  {d.latest_diagnosis.abstain_reason &&
                    row('Reason', 'कारण', d.latest_diagnosis.abstain_reason)}
                  <p className="tiny faint" style={{ marginTop: 8 }}>
                    {bi(lang,
                      'An image assessment is a model reading a photograph. It is not a laboratory diagnosis.',
                      'फोटोवरून केलेले मूल्यांकन प्रयोगशाळेतील निदान नाही.')}
                  </p>
                </>
              ) : <p className="small muted" style={{ marginTop: 6 }}>{none}</p>}
            </Card>

            <Card>
              <div className="card-title">{bi(lang, 'What was done', 'काय केले')}</div>
              {d.last_action ? (
                <>
                  {row('Action', 'कृती', d.last_action.product || d.last_action.kind)}
                  {row('On', 'दिनांक', fmtDate(d.last_action.applied_on, lang))}
                  {d.last_action.clears_on &&
                    row('Harvest allowed from', 'काढणी यानंतर',
                        fmtDate(d.last_action.clears_on, lang))}
                </>
              ) : <p className="small muted" style={{ marginTop: 6 }}>{none}</p>}
            </Card>

            {outcomes && outcomes.total?.followups > 0 && (
              <Card>
                <div className="card-title">{bi(lang, 'After past actions', 'आधीच्या कृतींनंतर')}</div>
                <Outcomes data={outcomes} lang={lang} compact />
              </Card>
            )}

            <Card>
              <div className="card-title">{bi(lang, 'Follow-up', 'पुनर्तपासणी')}</div>
              {d.followup ? (
                <>
                  {row('Due', 'नियोजित', fmtDate(d.followup.due_on, lang))}
                  {row('Outcome reported', 'नोंदवलेला निकाल', d.followup.outcome
                    || bi(lang, 'Not answered yet', 'अजून उत्तर नाही'))}
                </>
              ) : <p className="small muted" style={{ marginTop: 6 }}>{none}</p>}
            </Card>

            <Card>
              <div className="card-title">{bi(lang, 'Expert decision', 'तज्ज्ञांचा निर्णय')}</div>
              {d.expert_verdict ? (
                <>
                  {row('Verdict', 'निर्णय', d.expert_verdict.verdict_name)}
                  {row('By', 'कोणी', d.expert_verdict.expert_name)}
                  {row('On', 'दिनांक', fmtDate(d.expert_verdict.reviewed_at, lang))}
                  {row('Confidence', 'खात्री', d.expert_verdict.confidence)}
                </>
              ) : (
                <p className="small muted" style={{ marginTop: 6 }}>
                  {bi(lang, 'No expert has reviewed this field.',
                            'या शेताची तज्ज्ञ पडताळणी झालेली नाही.')}
                </p>
              )}
            </Card>

            <Card style={{ borderColor: 'var(--warn-line)', background: 'var(--warn-bg)' }}>
              <div className="card-title" style={{ color: 'var(--warn)' }}>
                {bi(lang, 'Please read', 'कृपया वाचा')}
              </div>
              <p className="small" style={{ marginTop: 7, lineHeight: 1.5 }}>
                {bi(lang, d.disclaimer, d.disclaimer_mr)}
              </p>
            </Card>
          </div>
        )}
      </div>
    </>
  )
}
