/* PRAHARI · what happened after each kind of action.

   Reads /api/followups/outcomes. Counts, never a verdict: measured outcomes
   (two photographs compared) and the farmer's own account sit in separate
   columns and are never added together, and a percentage appears only when
   the server gives one — which it does only from five measured outcomes up.
   Grouped by kind of action, never by product, so nothing here reads as
   "buy this". */
import React from 'react'
import { bi } from '../ui'

const COLS = [['better', 'Better', 'सुधारले'], ['same', 'Same', 'तसेच'], ['worse', 'Worse', 'बिघडले']]

export default function Outcomes({ data, lang, compact = false }) {
  if (!data) return null
  const groups = data.groups || []
  if (!groups.length) {
    return (
      <p className="small muted">
        {bi(lang, 'No logged action has a follow-up yet.',
                  'अजून कोणत्याही नोंदवलेल्या कृतीची पुनर्तपासणी नाही.')}
      </p>
    )
  }
  return (
    <div className="oc-out">
      <table className="oc-out__t">
        <thead>
          <tr>
            <th>{bi(lang, 'Action', 'कृती')}</th>
            {COLS.map(([k, en, mr]) => <th key={k}>{bi(lang, en, mr)}</th>)}
            {!compact && <th>{bi(lang, 'Open', 'बाकी')}</th>}
          </tr>
        </thead>
        <tbody>
          {groups.map((g, i) => (
            <tr key={i}>
              <td>
                <b>{bi(lang, g.kind_label, g.kind_label_mr)}</b>
                {g.target_label && (
                  <span className="tiny muted"> · {bi(lang, g.target_label, g.target_label_mr)}</span>
                )}
                <div className="tiny muted">{bi(lang, g.statement, g.statement_mr)}</div>
              </td>
              {COLS.map(([k]) => (
                <td key={k}>
                  {g.measured[k]}
                  {g.self_reported[k] > 0 && (
                    <span className="tiny muted" title={bi(lang, 'self-reported', 'स्वतः सांगितलेले')}>
                      {' '}+{g.self_reported[k]}*
                    </span>
                  )}
                </td>
              ))}
              {!compact && <td>{g.open}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="tiny faint" style={{ marginTop: 6 }}>
        {bi(lang, '* the farmer’s own account, not measured. ', '* शेतकऱ्याने सांगितलेले, मोजलेले नाही. ')}
        {bi(lang, data.method, data.method_mr)}
      </p>
    </div>
  )
}
