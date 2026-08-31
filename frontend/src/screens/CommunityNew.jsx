/* PRAHARI · writing a post.

   The composer is built for a farmer who may not type comfortably. Category is
   a tap, symptoms are taps, the crop and the place come from the field they
   already registered, and the only thing that has to be typed is one sentence.

   "Use my field" attaches a SUMMARY the server redacts before it stores it —
   crop, stage, days after sowing, whether an infection model fired, and what
   PRAHARI's own guess was as a band rather than a number. It does not attach
   the field. There is nothing in this form that can carry a coordinate. */
import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Prov, bi } from '../ui'

export default function CommunityNew({ lang, plot, plots, go, onDone }) {
  const [meta, setMeta] = useState(null)
  const [category, setCategory] = useState('disease')
  const [body, setBody] = useState('')
  const [symptoms, setSymptoms] = useState([])
  const [plotId, setPlotId] = useState(plot?.id || '')
  const [share, setShare] = useState(true)
  const [suspect, setSuspect] = useState('')
  const [files, setFiles] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)
  const [problems, setProblems] = useState([])

  useEffect(() => { api.communityMeta().then(setMeta).catch(() => {}) }, [])
  useEffect(() => {
    api.reference().then(r => {
      const p = { ...(r.diseases || {}), ...(r.pests || {}) }
      const crop = plots?.find(x => x.id === plotId)?.crop
      setProblems(Object.entries(p)
        .filter(([, v]) => !crop || (v.crops || []).includes(crop))
        .map(([k, v]) => ({ id: k, name: v.name, mr: v.mr, em: v.em })))
    }).catch(() => setProblems([]))
  }, [plotId, plots])

  const toggle = (s) => setSymptoms(x => x.includes(s) ? x.filter(y => y !== s) : [...x, s])

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      const out = await api.communityCreate({
        category, body: body.trim(), symptoms,
        plot_id: plotId || undefined,
        suspected_problem: suspect || undefined,
        share_context: share && !!plotId,
      })
      const id = out.post.id
      for (const f of files) {
        try { await api.communityImage(id, f) } catch { /* the post still stands */ }
      }
      onDone?.()
      go('communityPost', { id })
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const cats = Object.entries(meta?.categories || {})
  const syms = Object.entries(meta?.symptoms || {})

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('community')} aria-label="Back">←</button>
        <h1 className="grow">{lang === 'mr' ? 'नवीन नोंद' : 'New post'}</h1>
      </div>

      <div className="pad stack" style={{ paddingTop: 12 }}>
        {err && <ErrorNote error={err} lang={lang} />}

        <Card>
          <div className="card-title" style={{ marginBottom: 10 }}>
            {lang === 'mr' ? '१ · हे कशाबद्दल आहे?' : '1 · What is this about?'}
          </div>
          <div className="symgrid">
            {cats.map(([k, c]) => (
              <button key={k} aria-pressed={category === k} onClick={() => setCategory(k)}>
                <span style={{ fontSize: 17, marginRight: 6 }}>{c.icon}</span>
                {bi(lang, c.label, c.label_mr)}
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <div className="card-title" style={{ marginBottom: 10 }}>
            {lang === 'mr' ? '२ · तुम्हाला काय दिसत आहे?' : '2 · What are you seeing?'}
          </div>
          <textarea className="input" rows={4} value={body} maxLength={4000}
                    onChange={e => setBody(e.target.value)}
                    placeholder={lang === 'mr'
                      ? 'उदा. दोन दिवसांपासून खालच्या पानांवर करडे ओले डाग, पावसानंतर वाढत आहेत.'
                      : 'e.g. For two days, grey wet patches on the lower leaves, spreading after the rain.'} />
          <div className="tiny faint" style={{ marginTop: 6 }}>
            {body.trim().length < 10
              ? (lang === 'mr' ? 'किमान एक वाक्य लिहा.' : 'At least one sentence, please.')
              : `${body.trim().length} / 4000`}
          </div>
        </Card>

        {syms.length > 0 && (
          <Card>
            <div className="card-title" style={{ marginBottom: 4 }}>
              {lang === 'mr' ? '३ · लक्षणे निवडा' : '3 · Tap the symptoms'}
            </div>
            <p className="tiny muted" style={{ marginBottom: 10 }}>
              {lang === 'mr'
                ? 'हे लिहिण्यापेक्षा सोपे आहे — आणि यामुळेच प्रहरी अशाच नोंदी शोधू शकते.'
                : 'Easier than typing — and this is what lets PRAHARI find other farmers reporting the same thing.'}
            </p>
            <div className="symgrid">
              {syms.map(([k, s]) => (
                <button key={k} aria-pressed={symptoms.includes(k)} onClick={() => toggle(k)}>
                  {bi(lang, s.label, s.label_mr)}
                </button>
              ))}
            </div>
          </Card>
        )}

        <Card>
          <div className="card-title" style={{ marginBottom: 10 }}>
            {lang === 'mr' ? '४ · फोटो (ऐच्छिक)' : '4 · A photograph (optional)'}
          </div>
          <input ref={fileRef} type="file" accept="image/*" capture="environment"
                 style={{ display: 'none' }} multiple
                 onChange={e => setFiles(Array.from(e.target.files || []).slice(0, 4))} />
          <button className="btn block ghost" onClick={() => fileRef.current?.click()}>
            📷 {files.length
              ? (lang === 'mr' ? `${files.length} फोटो निवडले` : `${files.length} photo(s) selected`)
              : (lang === 'mr' ? 'फोटो जोडा' : 'Add a photo')}
          </button>
          <p className="tiny faint" style={{ marginTop: 8, lineHeight: 1.5 }}>
            {lang === 'mr'
              ? 'फोटो पुन्हा एन्कोड केला जातो — फोनने त्यात लिहिलेले GPS ठिकाण काढून टाकले जाते.'
              : 'The photo is re-encoded, which removes the GPS tag your phone writes into it. Your field location never leaves your account.'}
          </p>
        </Card>

        {plots?.length > 0 && (
          <Card>
            <div className="card-title" style={{ marginBottom: 10 }}>
              {lang === 'mr' ? '५ · कोणते शेत?' : '5 · Which field?'}
            </div>
            <div className="chips">
              {plots.map(p => (
                <button key={p.id} className="chip" aria-pressed={plotId === p.id}
                        onClick={() => setPlotId(p.id)}>{p.name}</button>
              ))}
              <button className="chip" aria-pressed={plotId === ''} onClick={() => setPlotId('')}>
                {lang === 'mr' ? 'कोणतेही नाही' : 'None'}
              </button>
            </div>
            {plotId && (
              <>
                <label className="row" style={{ marginTop: 14, gap: 10, alignItems: 'flex-start' }}>
                  <input type="checkbox" checked={share} onChange={e => setShare(e.target.checked)}
                         style={{ width: 20, height: 20, marginTop: 2 }} />
                  <span className="grow">
                    <b style={{ fontSize: 14 }}>
                      {lang === 'mr' ? 'माझ्या शेताची माहिती जोडा' : 'Use my field'}
                    </b>
                    <span className="small muted" style={{ display: 'block', marginTop: 3, lineHeight: 1.5 }}>
                      {lang === 'mr'
                        ? 'पीक, अवस्था, पेरणीपासूनचे दिवस आणि हवामान मॉडेल चालू आहे का — एवढेच. शेताचे ठिकाण, क्षेत्र किंवा तुमचा इतिहास नाही.'
                        : 'Crop, stage, days after sowing and whether an infection model fired. Not the location, not the area, and not your scan history.'}
                    </span>
                  </span>
                </label>
              </>
            )}
            {problems.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div className="tiny" style={{ fontWeight: 700, marginBottom: 6 }}>
                  {lang === 'mr' ? 'तुम्हाला काय वाटते? (ऐच्छिक)' : 'What do you think it is? (optional)'}
                </div>
                <div className="chips">
                  <button className="chip" aria-pressed={suspect === ''} onClick={() => setSuspect('')}>
                    {lang === 'mr' ? 'माहीत नाही' : "I don't know"}
                  </button>
                  {problems.map(p => (
                    <button key={p.id} className="chip" aria-pressed={suspect === p.id}
                            onClick={() => setSuspect(p.id)}>
                      {p.em} {bi(lang, p.name, p.mr)}
                    </button>
                  ))}
                </div>
                <p className="tiny faint" style={{ marginTop: 7, lineHeight: 1.5 }}>
                  {lang === 'mr'
                    ? 'हा फक्त तुमचा अंदाज म्हणून नोंदवला जातो. तज्ज्ञांनी तपासेपर्यंत तो "तपासलेला नाही" राहतो.'
                    : 'Recorded as YOUR guess. It stays "not verified" until an expert says otherwise — and it is what lets PRAHARI group your report with others.'}
                </p>
              </div>
            )}
          </Card>
        )}

        <button className="btn block" disabled={busy || body.trim().length < 10} onClick={submit}>
          {busy ? (lang === 'mr' ? 'पाठवत आहे…' : 'Posting…')
                : (lang === 'mr' ? 'नोंद प्रकाशित करा' : 'Post to the community')}
        </button>

        <Card className="tight">
          <Prov label={lang === 'mr' ? 'गोपनीयता' : 'Privacy'}
                value={bi(lang, meta?.privacy, meta?.privacy_mr)} />
          <Prov label={lang === 'mr' ? 'सूचना' : 'Notice'}
                value={bi(lang, meta?.unverified_notice, meta?.unverified_notice_mr)} />
        </Card>
      </div>
    </>
  )
}
