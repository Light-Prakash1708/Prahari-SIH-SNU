/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · Your data

   Three things a farmer is entitled to and had no way to do: see what is held,
   take a copy of it, and end it.

   The screen is written to be readable rather than reassuring. It counts what
   exists, it says plainly which regional signals survive and why, and it puts
   the irreversible action behind a password and a typed word — not behind a
   sequence of "are you sure" taps, which train people to tap through.

   Nothing here is computed in the browser. Every count comes from
   /api/privacy/summary, every deletion is performed and then RE-COUNTED by the
   server, and the re-count is what the screen shows afterwards. "It is gone"
   should be a measurement, not a message.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useEffect, useState } from 'react'
import { api, auth } from '../api'
import { Card, ErrorNote, Loading, Row, Sheet, bi } from '../ui'
import Icon from '../shell/Icon'

const T = {
  title:    ['Your data', 'तुमची माहिती'],
  lede:     ['Everything PRAHARI holds about this account, and what you can do with it.',
             'प्रहरीकडे तुमच्या खात्याविषयी असलेली सर्व माहिती.'],
  held:     ['What is held', 'काय साठवलेले आहे'],
  download: ['Download a copy', 'प्रत उतरवा'],
  dlSub:    ['One JSON file with every record below. Take it before you delete anything.',
             'खालील सर्व नोंदी एका फाइलमध्ये. हटवण्यापूर्वी घेऊन ठेवा.'],
  del:      ['Delete records', 'नोंदी हटवा'],
  delSub:   ['Choose what to remove. Your account and fields stay.',
             'काय हटवायचे ते निवडा. खाते व शेत तसेच राहील.'],
  closeAcc: ['Close this account', 'खाते बंद करा'],
  closeSub: ['Deletes the account, your fields, and every record above. This cannot be undone.',
             'खाते, शेत आणि वरील सर्व नोंदी हटतील. हे परत मिळणार नाही.'],
  nothing:  ['Nothing recorded yet', 'अजून काही नोंदलेले नाही'],
  records:  ['records', 'नोंदी'],
  fields:   ['fields', 'शेत'],
  photos:   ['photographs', 'फोटो'],
  pwd:      ['Your password', 'तुमचा पासवर्ड'],
  typed:    ['Type DELETE to confirm', 'पुष्टीसाठी DELETE लिहा'],
  cancel:   ['Cancel', 'रद्द करा'],
  posts:    ['Your community posts', 'तुमच्या समुदाय पोस्ट'],
  pDel:     ['Delete them', 'त्या हटवा'],
  pDelSub:  ['Removed completely, along with any expert replies on them.',
             'तज्ज्ञांच्या उत्तरांसह पूर्ण हटतील.'],
  pAnon:    ['Keep them, remove my name', 'ठेवा, पण नाव काढा'],
  pAnonSub: ['They stay as "Deleted account" so neighbours who acted on them still see them.',
             '"हटवलेले खाते" म्हणून राहतील.'],
  done:     ['Done', 'झाले'],
}
const tt = (lang, k) => bi(lang, T[k][0], T[k][1])

export default function Privacy({ lang = 'en', go }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)
  const [picked, setPicked] = useState([])
  const [sheet, setSheet] = useState(null)          // 'records' | 'account'
  const [result, setResult] = useState(null)

  const load = () => {
    setBusy(true); setErr(null)
    api.privacySummary().then(setData).catch(setErr).finally(() => setBusy(false))
  }
  useEffect(load, [])

  const toggle = (id) =>
    setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id])

  /* The export is built in the browser from the JSON the server returns, so it
     never touches a third-party service and works with no signal beyond the
     one request. */
  const download = async () => {
    try {
      const all = await api.privacyExport()
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(all, null, 2)], { type: 'application/json' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `prahari-my-data-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) { setErr(e) }
  }

  if (busy) return <div className="pad stack"><Loading lines={5} /></div>
  if (err && !data) return <div className="pad"><ErrorNote error={err} lang={lang} onRetry={load} /></div>
  if (!data) return null

  return (
    <div className="pad stack pv">
      <div>
        <h2 className="h1">{tt(lang, 'title')}</h2>
        <p className="lede muted" style={{ marginTop: 6 }}>{tt(lang, 'lede')}</p>
      </div>

      {err && <ErrorNote error={err} lang={lang} />}

      <Card className="pv-account">
        <div className="pv-account__name">{data.account?.name}</div>
        <div className="small muted">
          {data.account?.phone || data.account?.email} · {data.account?.role}
        </div>
        <div className="pv-account__counts">
          <span><b>{data.fields}</b> {tt(lang, 'fields')}</span>
          <span><b>{data.images}</b> {tt(lang, 'photos')}</span>
          <span><b>{data.total}</b> {tt(lang, 'records')}</span>
        </div>
      </Card>

      <div className="sect-title">{tt(lang, 'held')}</div>
      <div className="pv-list">
        {data.categories.map(c => (
          <label key={c.id} className={`pv-item${c.count ? '' : ' pv-item--empty'}`}>
            <input type="checkbox" checked={picked.includes(c.id)}
                   disabled={!c.count} onChange={() => toggle(c.id)} />
            <span className="pv-item__body">
              <span className="pv-item__top">
                <b>{bi(lang, c.label, c.label_mr)}</b>
                <span className="pv-item__n">
                  {c.count || bi(lang, 'none', 'काही नाही')}
                </span>
              </span>
              <span className="small muted">{bi(lang, c.note, c.note_mr)}</span>
            </span>
          </label>
        ))}
      </div>

      <Card className="pv-note">
        <Row><Icon name="info" size={16} /><b className="small">
          {bi(lang, 'What is not deleted', 'काय हटत नाही')}</b></Row>
        <p className="small muted" style={{ marginTop: 6 }}>
          {bi(lang, data.retained_note, data.retained_note_mr)}
        </p>
      </Card>

      <button className="btn ghost block" onClick={download}>
        {tt(lang, 'download')}
      </button>
      <p className="tiny muted" style={{ marginTop: -4 }}>{tt(lang, 'dlSub')}</p>

      <button className="btn danger block" disabled={!picked.length}
              onClick={() => setSheet('records')}>
        {tt(lang, 'del')}{picked.length ? ` (${picked.length})` : ''}
      </button>
      <p className="tiny muted" style={{ marginTop: -4 }}>{tt(lang, 'delSub')}</p>

      <div className="pv-danger">
        <b className="small">{tt(lang, 'closeAcc')}</b>
        <p className="tiny muted">{tt(lang, 'closeSub')}</p>
        <button className="btn danger block" onClick={() => setSheet('account')}>
          {tt(lang, 'closeAcc')}
        </button>
      </div>

      <ConfirmSheet
        open={!!sheet} kind={sheet} lang={lang}
        picked={picked}
        hasCommunity={sheet === 'account'
          || picked.includes('community')}
        onClose={() => setSheet(null)}
        onDone={(r) => { setSheet(null); setResult(r); if (sheet === 'records') load() }}
        onError={setErr}
      />

      <Sheet open={!!result} onClose={() => {
        const wasAccount = result?.account_deleted
        setResult(null)
        if (wasAccount) auth.clear()          /* signs out; App returns to the door */
      }} title={tt(lang, 'done')}>
        {result && <Receipt result={result} lang={lang} />}
      </Sheet>
    </div>
  )
}

/* ── the receipt ────────────────────────────────────────────────────────────
   Shown after a deletion, built from the server's own re-count. A row that is
   not zero is displayed as a failure rather than hidden, because a deletion
   that half-worked is the case a person most needs to know about. */
function Receipt({ result, lang }) {
  const v = result.verified_gone
  return (
    <div className="stack">
      <p className="lede">
        {result.account_deleted
          ? bi(lang, result.message, result.message_mr)
          : bi(lang, `${result.rows} records deleted.`, `${result.rows} नोंदी हटवल्या.`)}
      </p>
      <Card className="tight">
        <div className="small"><b>{bi(lang, 'Removed', 'हटवले')}</b></div>
        {Object.entries(result.deleted || {}).map(([k, n]) => (
          <Row key={k} between className="small" style={{ marginTop: 4 }}>
            <span className="muted">{k}</span><b>{n}</b>
          </Row>
        ))}
        {result.images_removed > 0 && (
          <Row between className="small" style={{ marginTop: 4 }}>
            <span className="muted">{bi(lang, 'photographs', 'फोटो')}</span>
            <b>{result.images_removed}</b>
          </Row>
        )}
        {result.images_unreachable > 0 && (
          <p className="tiny" style={{ color: 'var(--warn)', marginTop: 6 }}>
            {bi(lang,
              `${result.images_unreachable} image files could not be reached in storage. The records are gone; tell us so the files can be cleared.`,
              `${result.images_unreachable} फाइल स्टोरेजमध्ये सापडल्या नाहीत. नोंदी हटल्या आहेत.`)}
          </p>
        )}
      </Card>
      {v && (
        <Card className="tight">
          <div className="small"><b>{bi(lang, 'Checked afterwards', 'नंतर तपासले')}</b></div>
          {Object.entries(v).map(([k, n]) => (
            <Row key={k} between className="small" style={{ marginTop: 4 }}>
              <span className="muted">{k}</span>
              <b style={{ color: n === 0 ? 'var(--ok)' : 'var(--bad)' }}>{n}</b>
            </Row>
          ))}
        </Card>
      )}
    </div>
  )
}

/* ── the confirmation ───────────────────────────────────────────────────────
   Password AND a typed word, because they guard different mistakes: the
   password proves who is holding the phone, the typed word proves they meant
   this particular thing. */
function ConfirmSheet({ open, kind, lang, picked, hasCommunity, onClose, onDone, onError }) {
  const [pwd, setPwd] = useState('')
  const [word, setWord] = useState('')
  const [mode, setMode] = useState('delete')
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (open) { setPwd(''); setWord(''); setBusy(false) } }, [open])

  const submit = async () => {
    setBusy(true)
    try {
      const body = { password: pwd, confirm: word, community_mode: mode }
      const r = kind === 'account'
        ? await api.privacyDeleteAccount(body)
        : await api.privacyDeleteRecords({ ...body, categories: picked })
      onDone(r)
    } catch (e) { onError(e) } finally { setBusy(false) }
  }

  const ready = pwd.length > 0 && /^(delete|डिलीट|हटवा)$/i.test(word.trim())

  return (
    <Sheet open={open} onClose={onClose}
           title={kind === 'account' ? tt(lang, 'closeAcc') : tt(lang, 'del')}>
      <div className="stack">
        {kind === 'account' && (
          <Card className="tight pv-warn">
            <b className="small">{bi(lang, 'This cannot be undone.', 'हे परत मिळणार नाही.')}</b>
            <p className="tiny muted" style={{ marginTop: 4 }}>
              {bi(lang,
                'Your account, your fields, your photographs, diagnoses, trap counts and expenses are removed. You will be signed out.',
                'खाते, शेत, फोटो, निदान, सापळ्यांची मोजणी व खर्च हटतील. तुम्ही साइन आउट व्हाल.')}
            </p>
          </Card>
        )}

        {hasCommunity && (
          <div>
            <div className="small"><b>{tt(lang, 'posts')}</b></div>
            <div className="pv-choice">
              {[['delete', 'pDel', 'pDelSub'], ['anonymise', 'pAnon', 'pAnonSub']].map(
                ([k, a, b]) => (
                  <button key={k} className={`pv-choice__opt${mode === k ? ' is-on' : ''}`}
                          onClick={() => setMode(k)}>
                    <b className="small">{tt(lang, a)}</b>
                    <span className="tiny muted">{tt(lang, b)}</span>
                  </button>
                ))}
            </div>
          </div>
        )}

        <label className="field">
          <span className="lbl">{tt(lang, 'pwd')}</span>
          <input className="input" type="password" value={pwd} autoComplete="current-password"
                 onChange={e => setPwd(e.target.value)} />
        </label>
        <label className="field">
          <span className="lbl">{tt(lang, 'typed')}</span>
          <input className="input" value={word} autoCapitalize="characters" spellCheck={false}
                 onChange={e => setWord(e.target.value)} placeholder="DELETE" />
        </label>

        <button className="btn danger block" disabled={!ready || busy} onClick={submit}>
          {busy ? '…' : (kind === 'account' ? tt(lang, 'closeAcc') : tt(lang, 'del'))}
        </button>
        <button className="btn quiet block" onClick={onClose}>{tt(lang, 'cancel')}</button>
      </div>
    </Sheet>
  )
}
