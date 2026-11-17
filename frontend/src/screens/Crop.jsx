/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · Crop — everything about the plant, in one tab.

   The old app scattered this across Fields, Forecast, Traps and History, which
   meant a farmer wanting to know "where is my crop in its season and what is
   due next" had to visit four screens and hold the answer in their head.

   Order: which field → where in the season → what is due → the record.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Empty, ErrorNote, Loading, Prov, bi, fmtDate } from '../ui'

const CROP_EM = {
  tomato: '🍅', potato: '🥔', onion: '🧅', grape: '🍇', maize: '🌽',
  cotton: '🌱', soybean: '🌿', pigeonpea: '🫘', wheat: '🌾',
}

export default function Crop({ lang, plot, plots, onPlot, go }) {
  const [ref, setRef] = useState(null)
  const [hist, setHist] = useState(null)
  const [traps, setTraps] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)

  useEffect(() => { api.reference().then(setRef).catch(() => setRef(null)) }, [])
  useEffect(() => {
    if (!plot) { setBusy(false); return }
    setBusy(true)
    Promise.all([
      api.history(plot.id).catch(() => null),
      api.traps(plot.id).catch(() => null),
    ]).then(([h, t]) => { setHist(h); setTraps(t) })
      .catch(setErr).finally(() => setBusy(false))
  }, [plot?.id])

  const crop = ref?.crops?.[plot?.crop]
  const stage = hist?.plot?.crop_stage

  return (
    <>
      <header className="hdr" style={{ paddingBottom: 54 }}>
        <div className="hdr-greet">{bi(lang, 'My Crop', 'माझे पीक')}</div>
        <div className="hdr-sub">
          {bi(lang, 'Where you are in the season, what is due, and the record so far.', 'हंगामात कुठे आहात, पुढे काय आहे, आणि आतापर्यंतची नोंद.')}
        </div>
      </header>

      <div className="pad pull stack">
        {/* ── which field ─────────────────────────────────────────────── */}
        {plots?.length > 0 ? (
          <div className="cropcards">
            {plots.map(p => (
              <button key={p.id} className="cropcard" aria-pressed={p.id === plot?.id}
                      onClick={() => onPlot(p.id)}>
                <div className="em">{CROP_EM[p.crop] || '🌱'}</div>
                <div className="nm">{p.name}</div>
                <div className="sub">
                  {p.crop_label || p.crop} · {p.area_acre} {bi(lang, 'ac', 'एकर')}
                </div>
              </button>
            ))}
            <button className="cropcard" onClick={() => go('addField')}>
              <div className="em">➕</div>
              <div className="nm">{bi(lang, 'Add a field', 'शेत जोडा')}</div>
              <div className="sub">{bi(lang, 'Register another', 'नवीन नोंदणी')}</div>
            </button>
          </div>
        ) : (
          <Empty icon="🌾" title={bi(lang, 'No field yet', 'अजून शेत नाही')}
                 action={<button className="btn" onClick={() => go('addField')}>
                   {bi(lang, 'Add a field', 'शेत जोडा')}</button>} />
        )}

        {busy && plot && <Loading lines={3} />}
        {err && <ErrorNote error={err} lang={lang} />}

        {/* ── the crop calendar ─────────────────────────────────────────
            This screen is the field RECORD — traps, passport, season detail.
            The calendar itself lives on the Crop tab, where the same stage
            table is resolved into real dates and carries threat windows, the
            prevention window and the field's history. Keeping a second,
            date-less copy here was the reason the calendar read as static: a
            farmer landing on this screen saw a bare five-stage bar with no
            dates on it and reasonably concluded nothing was computed. */}
        {crop?.stages && (
          <Card>
            <div className="card-title" style={{ marginBottom: 4 }}>
              {bi(lang, 'Crop calendar', 'पीक दिनदर्शिका')}
            </div>
            <p className="tiny muted" style={{ marginBottom: 10 }}>
              {stage?.days != null
                ? (lang === 'mr' ? `पेरणीनंतर ${stage.days} दिवस · ${bi(lang, stage.label, stage.label_mr)}`
                                 : `Day ${stage.days} after sowing · ${bi(lang, stage.label, stage.label_mr)}`)
                : (bi(lang, 'Add a sowing date to place the crop', 'पेरणीची तारीख नोंदवा'))}
            </p>

            <div className="calbar">
              {crop.stages.map(([key, lo, hi, label]) => {
                const d = stage?.days
                const cls = d == null ? '' : d > hi ? 'done' : (d >= lo && d <= hi) ? 'now' : ''
                return (
                  <div className={`st ${cls}`} key={key}>
                    <span>{label}</span>
                    {/* the day band, so the bar is never a row of bare words */}
                    <small style={{ display: 'block', fontSize: 9.5, opacity: .7, marginTop: 2 }}>
                      {lo}–{hi}d
                    </small>
                  </div>
                )
              })}
            </div>

            {stage?.days_to_harvest != null && (
              <div className="note" style={{ marginTop: 10 }}>
                {lang === 'mr'
                  ? `अंदाजे ${stage.days_to_harvest} दिवसांत काढणी.`
                  : `About ${stage.days_to_harvest} days to harvest.`}
              </div>
            )}

            <button className="btn block ghost" style={{ marginTop: 12 }}
                    onClick={() => go('crop')}>
              {bi(lang, 'Open the full Crop Journey — dates, threat windows, history', 'संपूर्ण पीक प्रवास पहा — धोक्याचा कालावधी व इतिहास')}
            </button>

            <div className="tiny faint" style={{ marginTop: 10, lineHeight: 1.5 }}>
              {bi(lang, 'The stage scales the economic threshold and decides whether a spray can physically reach the pest — it is not decoration.', 'अवस्था आर्थिक नुकसान मर्यादा बदलते आणि फवारणी किडीपर्यंत पोहोचेल का हे ठरवते.')}
            </div>
          </Card>
        )}

        {/* ── what is due ─────────────────────────────────────────────── */}
        <Card>
          <div className="card-title" style={{ marginBottom: 10 }}>
            {bi(lang, 'Scouting and counts', 'तपासणी आणि मोजणी')}
          </div>
          <div className="steps">
            <div className="s"><div className="n">1</div><div className="ic">🚶</div>
              <div className="l">{bi(lang, 'Walk the field', 'शेतात फिरा')}</div></div>
            <div className="s"><div className="n">2</div><div className="ic">📷</div>
              <div className="l">{bi(lang, 'Photograph a leaf', 'बाधित पानाचा फोटो')}</div></div>
            <div className="s"><div className="n">3</div><div className="ic">🪤</div>
              <div className="l">{bi(lang, 'Count the trap', 'सापळा मोजा')}</div></div>
          </div>
          <div className="quick" style={{ marginTop: 14 }}>
            {[['scan', '📷', bi(lang, 'Scan', 'स्कॅन')],
              ['traps', '🪤', bi(lang, 'Traps', 'सापळे')],
              ['forecast', '🌦', bi(lang, 'Forecast', 'अंदाज')],
              ['history', '📜', bi(lang, 'History', 'इतिहास')],
              ['soil', '🪴', bi(lang, 'Soil', 'जमीन')],
              ['water', '💧', bi(lang, 'Water', 'पाणी')],
              ['decide', '🛡️', bi(lang, 'Spray?', 'फवारू का?')],
              ['saathi', '🌿', bi(lang, 'AgriDoc', 'साथी')]].map(([k, ic, label]) => (
              <button key={k} onClick={() => go(k)}>
                <span className="ic">{ic}</span><span className="lbl">{label}</span>
              </button>
            ))}
          </div>
        </Card>

        {/* ── traps at a glance ───────────────────────────────────────── */}
        {traps?.traps?.length > 0 && (
          <Card>
            <div className="row between" style={{ marginBottom: 10 }}>
              <div className="card-title">{bi(lang, 'Pest traps', 'सापळे')}</div>
              <button className="btn sm quiet" onClick={() => go('traps')}>
                {bi(lang, 'All', 'सर्व')} ›
              </button>
            </div>
            {traps.traps.map(t => {
              const last = t.counts?.[0]
              return (
                <div className="changerow" key={t.id}>
                  <div className="ic" style={{ background: 'var(--sunk)' }}>🪤</div>
                  <div className="nm">{bi(lang, t.pest_name, t.pest_name_mr)}</div>
                  <div className="st">{last ? `${last.count}` : '—'}</div>
                  <div className="ar tiny muted" style={{ width: 'auto' }}>
                    {t.etl != null ? `/ ${t.etl}` : ''}
                  </div>
                </div>
              )
            })}
            <Prov label={bi(lang, 'Threshold', 'मर्यादा')}
                  value={traps.traps[0]?.etl_source} />
          </Card>
        )}

        {/* ── the record ──────────────────────────────────────────────── */}
        {hist?.timeline?.length > 0 && (
          <Card>
            <div className="row between" style={{ marginBottom: 10 }}>
              <div className="card-title">{bi(lang, 'Recent record', 'अलीकडील नोंदी')}</div>
              <button className="btn sm quiet" onClick={() => go('history')}>
                {bi(lang, 'Full', 'पूर्ण')} ›
              </button>
            </div>
            <div className="tl">
              {hist.timeline.slice(0, 6).map(e => (
                <div className={`tl-item ${e.severity}`} key={e.id}>
                  <div className="tl-date">{fmtDate(e.at, lang)}</div>
                  <div className="tl-title">{bi(lang, e.title, e.title_mr)}</div>
                  {e.detail && <div className="tl-detail">{bi(lang, e.detail, e.detail_mr)}</div>}
                </div>
              ))}
            </div>
            <Prov label={bi(lang, 'Note', 'टीप')} value={hist.note} />
          </Card>
        )}
      </div>
    </>
  )
}
