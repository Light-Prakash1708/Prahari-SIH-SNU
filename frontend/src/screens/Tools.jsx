/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · Quick Tools — the hub, and the two tools that had no screen

   Saurjya's Quick Actions page is a bento grid of six tools. Five of them
   already had working screens in this app; two did not. This file is the hub
   plus those two:

     · Farm Expenses  — the money ledger, which had no table until now
     · Fertilizer     — the nutrient gap, which had an API and no screen

   The hub does not invent a seventh tool to fill the grid. Every card here
   goes somewhere real.
   ═══════════════════════════════════════════════════════════════════════════ */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Card, ErrorNote, Loading, Sheet, bi, fmtDate, fmtMoney } from '../ui'
import Icon from '../shell/Icon'
import './tools.css'

const T = {
  mr: {
    hub: 'जलद साधने', hubSub: 'सर्व प्रहरी साधने एका ठिकाणी.',
    scan: 'पीक स्कॅन', scanSub: 'एआय तपासणी',
    calendar: 'पीक दिनदर्शिका', calendarSub: 'पेरणी ते काढणी',
    soil: 'माती आरोग्य', soilSub: 'स्वतः तपासा',
    fert: 'खत मार्गदर्शक', fertSub: 'अन्नद्रव्य तूट',
    pest: 'फवारणी निर्णय', pestSub: 'मर्यादा व आयपीएम',
    water: 'पाणी', waterSub: 'सिंचन नियोजन',
    expense: 'शेती खर्च', expenseSub: 'हिशेब',
    traps: 'सापळे', trapsSub: 'कीड मोजणी',
    search: 'साधन शोधा…', none: 'जुळणारे साधन नाही.',
  },
  en: {
    hub: 'Quick Tools', hubSub: 'Every PRAHARI tool, in one place.',
    scan: 'Scan Crop', scanSub: 'AI inspection',
    calendar: 'Crop Calendar', calendarSub: 'Sowing to harvest',
    soil: 'Soil Health', soilSub: 'Self-test',
    fert: 'Fertilizer Guide', fertSub: 'Nutrient gap',
    pest: 'Spray Decision', pestSub: 'Threshold & IPM',
    water: 'Irrigation', waterSub: 'Water balance',
    expense: 'Farm Expenses', expenseSub: 'Cost tracker',
    traps: 'Pest Traps', trapsSub: 'Counts',
    search: 'Search tools…', none: 'No matching tool.',
  },
}
const t = (lang, k) => (T[lang] || T.en)[k] ?? T.en[k]

/* ══ the hub ═══════════════════════════════════════════════════════════ */
export function Tools({ lang, go }) {
  const [q, setQ] = useState('')

  const cards = [
    { k: 'scan', icon: 'camera', route: 'scan', size: 'tall' },
    { k: 'calendar', icon: 'calendar', route: 'crop' },
    { k: 'pest', icon: 'shield', route: 'decide' },
    { k: 'soil', icon: 'leaf', route: 'soil' },
    { k: 'fert', icon: 'calc', route: 'fertilizer' },
    { k: 'water', icon: 'drop', route: 'water' },
    { k: 'traps', icon: 'bug', route: 'traps' },
    { k: 'expense', icon: 'wallet', route: 'expenses', size: 'wide' },
  ]

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return cards
    return cards.filter(c =>
      t(lang, c.k).toLowerCase().includes(needle) ||
      t(lang, c.k + 'Sub').toLowerCase().includes(needle) ||
      t('en', c.k).toLowerCase().includes(needle))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, lang])

  return (
    <>
      <header className="hdr">
        <div className="hdr-greet">{t(lang, 'hub')}</div>
        <div className="hdr-sub">{t(lang, 'hubSub')}</div>
      </header>

      <div className="pad" style={{ paddingTop: 14 }}>
        <div className="tl-search">
          <Icon name="info" size={16} />
          <input value={q} onChange={e => setQ(e.target.value)}
                 placeholder={t(lang, 'search')} aria-label={t(lang, 'search')} />
          {q && <button onClick={() => setQ('')} aria-label="Clear"><Icon name="xmark" size={14} /></button>}
        </div>

        {shown.length === 0
          ? <Card><p className="small muted">{t(lang, 'none')}</p></Card>
          : (
            <div className="tl-bento">
              {shown.map(c => (
                <button key={c.k} onClick={() => go(c.route)}
                        className={`tl-card${c.size ? ` tl-card--${c.size}` : ''}`}>
                  <span className="tl-card__badge"><Icon name={c.icon} size={20} /></span>
                  <span className="tl-card__body">
                    <span className="tl-card__title">{t(lang, c.k)}</span>
                    <span className="tl-card__sub">{t(lang, c.k + 'Sub')}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
      </div>
    </>
  )
}

/* ══ farm expenses ═════════════════════════════════════════════════════ */
const E = {
  mr: {
    title: 'शेती खर्च', sub: 'या शेतावर किती खर्च झाला.',
    total: 'एकूण खर्च', income: 'उत्पन्न', net: 'निव्वळ', perAcre: 'प्रति एकर',
    recent: 'अलीकडील नोंदी', none: 'अजून नोंद नाही.', add: 'खर्च नोंदवा',
    addTitle: 'नवीन नोंद', cat: 'श्रेणी', what: 'काय?', amount: 'रक्कम (₹)',
    date: 'तारीख', save: 'नोंद जतन करा', kind: 'प्रकार',
    expense: 'खर्च', incomeK: 'उत्पन्न', entries: 'नोंदी',
  },
  en: {
    title: 'Farm Expenses', sub: 'What this field has cost.',
    total: 'Total spend', income: 'Income', net: 'Net', perAcre: 'per acre',
    recent: 'Recent entries', none: 'No entries yet.', add: 'Add expense',
    addTitle: 'New entry', cat: 'Category', what: 'What was it?', amount: 'Amount (₹)',
    date: 'Date', save: 'Save entry', kind: 'Kind',
    expense: 'Expense', incomeK: 'Income', entries: 'entries',
  },
}
const e = (lang, k) => (E[lang] || E.en)[k] ?? E.en[k]

export function Expenses({ lang, plot, go }) {
  const [meta, setMeta] = useState(null)
  const [data, setData] = useState(null)
  const [sum, setSum] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(true)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ direction: 'expense', category: 'fertilizer' })
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    if (!plot) { setBusy(false); return }
    setBusy(true)
    Promise.all([
      api.ledger2(plot.id).catch(x => { setErr(x); return null }),
      api.ledgerSummary(plot.id).catch(() => null),
    ]).then(([d, s]) => { setData(d); setSum(s) }).finally(() => setBusy(false))
  }, [plot])

  useEffect(() => { api.ledgerMeta().then(setMeta).catch(() => setMeta(null)) }, [])
  useEffect(load, [load])

  const cats = form.direction === 'income'
    ? (meta?.income_categories || [])
    : (meta?.expense_categories || [])

  const save = async (ev) => {
    ev.preventDefault()
    setSaving(true); setErr(null)
    try {
      await api.ledgerAdd({
        plot_id: plot.id,
        direction: form.direction,
        category: form.category,
        title: form.title,
        amount_inr: Number(form.amount),
        spent_on: form.spent_on || undefined,
      })
      setOpen(false)
      setForm({ direction: 'expense', category: 'fertilizer' })
      load()
    } catch (x) { setErr(x) } finally { setSaving(false) }
  }

  if (!plot) return <NoField lang={lang} go={go} />

  const s = data?.summary
  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('tools')} aria-label="Back">
          <Icon name="back" size={17} />
        </button>
        <h1 className="grow">{e(lang, 'title')}</h1>
      </div>

      <div className="pad" style={{ paddingTop: 14 }}>
        {busy && <Loading lines={4} />}
        {err && <ErrorNote error={err} lang={lang} onRetry={load} />}

        {s && !busy && (
          <>
            <Card className="ex-hero">
              <div className="ex-hero__label">{e(lang, 'total')}</div>
              <div className="ex-hero__amount">{fmtMoney(s.expense_inr)}</div>
              <div className="ex-hero__meta">
                {s.entries} {e(lang, 'entries')}
                {sum?.per_acre_inr != null && <> · {fmtMoney(sum.per_acre_inr)} {e(lang, 'perAcre')}</>}
              </div>

              {s.income_inr > 0 && (
                <div className="ex-hero__row">
                  <span>{e(lang, 'income')} <b>{fmtMoney(s.income_inr)}</b></span>
                  <span>{e(lang, 'net')} <b className={s.net_inr >= 0 ? 'pos' : 'neg'}>
                    {fmtMoney(s.net_inr)}</b></span>
                </div>
              )}

              {/* A stacked bar rather than a donut: it stays readable at this
                  width, and every slice is labelled with its own figure. */}
              {s.by_category.length > 0 && (
                <>
                  <div className="ex-bar" role="img"
                       aria-label={`Spend by category: ${s.by_category
                         .map(c => `${c.label} ${Math.round(c.share * 100)}%`).join(', ')}`}>
                    {s.by_category.map((c, i) => (
                      <span key={c.category} className={`ex-bar__seg seg-${i % 6}`}
                            style={{ width: `${c.share * 100}%` }} />
                    ))}
                  </div>
                  <ul className="ex-legend">
                    {s.by_category.map((c, i) => (
                      <li key={c.category}>
                        <span className={`ex-dot seg-${i % 6}`} />
                        <span className="ex-legend__name">{c.em} {bi(lang, c.label, c.label_mr)}</span>
                        <span className="ex-legend__val">{fmtMoney(c.amount_inr)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Card>

            <section className="cj-section">
              <h2 className="cj-h2">{e(lang, 'recent')}</h2>
              {data.entries.length === 0
                ? <Card><p className="small muted">{e(lang, 'none')}</p></Card>
                : (
                  <div className="ex-list">
                    {data.entries.map(row => (
                      <div key={row.id} className="ex-row">
                        <span className="ex-row__date">{fmtDate(row.spent_on, lang)}</span>
                        <div className="grow" style={{ minWidth: 0 }}>
                          <div className="ex-row__title">{row.title}</div>
                          <div className="tiny faint">{row.category}</div>
                        </div>
                        <span className={`ex-row__amt ${row.direction === 'income' ? 'pos' : ''}`}>
                          {row.direction === 'income' ? '+' : '−'}{fmtMoney(row.amount_inr)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
            </section>

            {sum?.note && <p className="tiny faint cj-method">{sum.note}</p>}

            <button className="btn block" style={{ marginTop: 16 }} onClick={() => setOpen(true)}>
              <Icon name="wallet" size={16} /> {e(lang, 'add')}
            </button>
          </>
        )}
      </div>

      <Sheet open={open} onClose={() => setOpen(false)} title={e(lang, 'addTitle')}>
        <form onSubmit={save}>
          <div className="seg" style={{ marginBottom: 14 }}>
            <button type="button" aria-pressed={form.direction === 'expense'}
                    onClick={() => setForm(f => ({ ...f, direction: 'expense', category: 'fertilizer' }))}>
              {e(lang, 'expense')}
            </button>
            <button type="button" aria-pressed={form.direction === 'income'}
                    onClick={() => setForm(f => ({ ...f, direction: 'income', category: 'sale' }))}>
              {e(lang, 'incomeK')}
            </button>
          </div>

          <label className="field">
            <span className="lbl">{e(lang, 'cat')}</span>
            <div className="tl-cats">
              {cats.map(c => (
                <button type="button" key={c.id}
                        className={'tl-cat' + (form.category === c.id ? ' is-on' : '')}
                        onClick={() => setForm(f => ({ ...f, category: c.id }))}>
                  {c.em} {bi(lang, c.en, c.mr)}
                </button>
              ))}
            </div>
          </label>

          <label className="field">
            <span className="lbl">{e(lang, 'what')}</span>
            <input className="input" required maxLength={120} value={form.title || ''}
                   onChange={ev => setForm(f => ({ ...f, title: ev.target.value }))}
                   placeholder={lang === 'mr' ? 'उदा. युरिया २ पोती' : 'e.g. Urea, 2 bags'} />
          </label>

          <label className="field">
            <span className="lbl">{e(lang, 'amount')}</span>
            <input className="input" required type="number" min="1" step="1"
                   inputMode="numeric" value={form.amount || ''}
                   onChange={ev => setForm(f => ({ ...f, amount: ev.target.value }))} />
          </label>

          <label className="field">
            <span className="lbl">{e(lang, 'date')}</span>
            <input className="input" type="date" value={form.spent_on || ''}
                   onChange={ev => setForm(f => ({ ...f, spent_on: ev.target.value }))} />
          </label>

          {err && <div style={{ marginBottom: 12 }}><ErrorNote error={err} lang={lang} /></div>}

          <button className="btn block" type="submit" disabled={saving}>
            {saving ? '…' : e(lang, 'save')}
          </button>
        </form>
      </Sheet>
    </>
  )
}

/* ══ fertilizer — the nutrient gap, over the existing soil API ══════════ */
const F = {
  mr: {
    title: 'खत मार्गदर्शक', sub: 'मातीत काय आहे आणि पिकाला काय हवे, यातील फरक.',
    have: 'तुमच्या माती अहवालातील आकडे', crop: 'पीक', area: 'क्षेत्र (एकर)',
    calc: 'तूट काढा', need: 'शिफारस', missing: 'न मोजलेले',
    noLab: 'प्रयोगशाळेचे आकडे नसतील तर मृदा आरोग्य पत्रिकेतून भरा. रिकामे ठेवलेले घटक "मोजलेले नाही" म्हणून धरले जातात — शून्य नाही.',
  },
  en: {
    title: 'Fertilizer Guide', sub: 'The gap between what the soil has and what the crop needs.',
    have: 'Figures from your soil report', crop: 'Crop', area: 'Area (acres)',
    calc: 'Work out the gap', need: 'Recommendation', missing: 'not measured',
    noLab: 'Fill these in from your Soil Health Card. Anything left blank is treated as NOT MEASURED — never as zero, because zero is a reading and a very alarming one.',
  },
}
const f = (lang, k) => (F[lang] || F.en)[k] ?? F.en[k]

const LAB_FIELDS = [
  ['nitrogen_kg_ha', 'Nitrogen (N)', 'नत्र', 'kg/ha'],
  ['phosphorus_kg_ha', 'Phosphorus (P)', 'स्फुरद', 'kg/ha'],
  ['potassium_kg_ha', 'Potassium (K)', 'पालाश', 'kg/ha'],
  ['organic_carbon_pct', 'Organic carbon', 'सेंद्रिय कर्ब', '%'],
  ['ph', 'pH', 'सामू', ''],
]

export function Fertilizer({ lang, plot, go }) {
  const [vals, setVals] = useState({})
  const [plan, setPlan] = useState(null)
  const [ref, setRef] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.soilReference().then(setRef).catch(() => setRef(null)) }, [])
  useEffect(() => {
    if (plot) api.soilHistory(plot.id)
      .then(h => {
        // Pre-fill from the most recent LAB result if the field has one, so a
        // farmer who already entered a Soil Health Card is not asked twice.
        const lab = (h?.tests || []).find(x => x.kind === 'lab')
        if (lab) {
          setVals(Object.fromEntries(LAB_FIELDS
            .map(([k]) => [k, lab[k]]).filter(([, v]) => v != null)))
        }
      })
      .catch(() => {})
  }, [plot])

  const run = async (ev) => {
    ev.preventDefault()
    setBusy(true); setErr(null)
    try {
      const body = { plot_id: plot.id }
      LAB_FIELDS.forEach(([k]) => {
        if (vals[k] !== '' && vals[k] != null) body[k] = Number(vals[k])
      })
      setPlan(await api.soilLab(body))
    } catch (x) { setErr(x); setPlan(null) } finally { setBusy(false) }
  }

  if (!plot) return <NoField lang={lang} go={go} />

  return (
    <>
      <div className="topbar">
        <button className="icon-btn" onClick={() => go('tools')} aria-label="Back">
          <Icon name="back" size={17} />
        </button>
        <h1 className="grow">{f(lang, 'title')}</h1>
      </div>

      <div className="pad" style={{ paddingTop: 14 }}>
        <p className="small muted" style={{ marginBottom: 14 }}>{f(lang, 'sub')}</p>

        <Card>
          <form onSubmit={run}>
            <div className="cj-h2" style={{ marginBottom: 4 }}>{f(lang, 'have')}</div>
            <p className="tiny muted" style={{ marginBottom: 12 }}>{f(lang, 'noLab')}</p>

            {LAB_FIELDS.map(([k, en, mr, unit]) => (
              <label className="field" key={k}>
                <span className="lbl">{bi(lang, en, mr)} {unit && <span className="faint">{unit}</span>}</span>
                <input className="input" type="number" step="any" inputMode="decimal"
                       value={vals[k] ?? ''} placeholder={f(lang, 'missing')}
                       onChange={ev => setVals(v => ({ ...v, [k]: ev.target.value }))} />
              </label>
            ))}

            {err && <div style={{ marginBottom: 12 }}><ErrorNote error={err} lang={lang} /></div>}
            <button className="btn block" type="submit" disabled={busy}>
              {busy ? '…' : f(lang, 'calc')}
            </button>
          </form>
        </Card>

        {plan && <FertPlan plan={plan} lang={lang} />}

        {ref?.disclaimer && (
          <p className="tiny faint cj-method">{bi(lang, ref.disclaimer, ref.disclaimer_mr)}</p>
        )}
      </div>
    </>
  )
}

const NUTRIENT_LABEL = {
  nitrogen_kg_ha: ['Nitrogen (N)', 'नत्र'],
  phosphorus_kg_ha: ['Phosphorus (P)', 'स्फुरद'],
  potassium_kg_ha: ['Potassium (K)', 'पालाश'],
  organic_carbon_pct: ['Organic carbon', 'सेंद्रिय कर्ब'],
  ph: ['pH', 'सामू'],
}

function FertPlan({ plan, lang }) {
  /* `ratings` is keyed by nutrient and `plan` is the dose table. Both come
     straight from app/soil.py; nothing is recomputed here. */
  const ratings = Object.values(plan.ratings || {})
  const doses = plan.plan || []

  if (plan.available === false) {
    return (
      <Card style={{ marginTop: 16 }}>
        <p className="small muted">
          {plan.reason || (lang === 'mr'
            ? 'या पिकासाठी शिफारस उपलब्ध नाही.'
            : 'No published dose table is available for this crop.')}
        </p>
      </Card>
    )
  }

  return (
    <>
      {ratings.length > 0 && (
        <section className="cj-section">
          <h2 className="cj-h2">{lang === 'mr' ? 'तुमच्या मातीचे वर्गीकरण' : 'How your soil rates'}</h2>
          <div className="ex-list">
            {ratings.map(r => (
              <div key={r.key} className="ex-row" style={{ alignItems: 'flex-start' }}>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="ex-row__title">
                    {bi(lang, ...(NUTRIENT_LABEL[r.key] || [r.key, r.key]))}
                  </div>
                  <div className="tiny faint">{r.value} {r.unit || ''}</div>
                  {r.means && <div className="tiny muted" style={{ marginTop: 4 }}>{r.means}</div>}
                </div>
                {r.class && <span className={`badge ${r.tone || 'grey'}`}>{r.class}</span>}
              </div>
            ))}
          </div>
        </section>
      )}

      {doses.length > 0 && (
        <section className="cj-section">
          <h2 className="cj-h2">{lang === 'mr' ? 'शिफारस' : 'Recommendation'}</h2>
          <div className="ex-list">
            {doses.map(d => (
              <div key={d.nutrient} className="ex-row" style={{ alignItems: 'flex-start' }}>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="ex-row__title">
                    {d.material} <span className="faint">({d.nutrient})</span>
                  </div>
                  {/* The arithmetic is shown, not just the answer — the whole
                      point is that a farmer can check the shopkeeper's sum. */}
                  {d.arithmetic && <div className="tiny muted" style={{ marginTop: 3 }}>{d.arithmetic}</div>}
                  <div className="tiny faint" style={{ marginTop: 3 }}>
                    {d.general_kg_acre} kg/acre general dose · soil tests {d.soil_test_class} · {d.adjustment}
                  </div>
                  {d.why && <div className="tiny muted" style={{ marginTop: 3 }}>{d.why}</div>}
                </div>
                <span className="ex-row__amt">{d.material_total_kg} kg</span>
              </div>
            ))}
          </div>
          {plan.split && <p className="small muted cj-method">{plan.split}</p>}
        </section>
      )}

      {/* A value the farmer did not enter is named, so a missing nutrient is
          visible rather than silently treated as adequate. */}
      {plan.unmeasured?.length > 0 && (
        <Card style={{ marginTop: 14 }}>
          <div className="tiny" style={{ fontWeight: 800, marginBottom: 4 }}>
            {lang === 'mr' ? 'न मोजलेले' : 'Not measured'}
          </div>
          <p className="tiny muted">
            {plan.unmeasured.map(k => bi(lang, ...(NUTRIENT_LABEL[k] || [k, k]))).join(', ')}
            {' — '}
            {lang === 'mr'
              ? 'यासाठी सर्वसाधारण शिफारस वापरली आहे, तुमच्या मातीची नाही.'
              : 'the general dose was used for these, not your soil.'}
          </p>
        </Card>
      )}

      {plan.warnings?.length > 0 && plan.warnings.map((w, i) => (
        <Card key={i} className="cj-pw tone-warn" style={{ marginTop: 12 }}>
          <p className="small">{typeof w === 'string' ? w : w.text || w.message}</p>
        </Card>
      ))}

      {plan.method && <p className="tiny faint cj-method">{plan.method}</p>}
      {plan.no_brands && <p className="tiny faint cj-method">{plan.no_brands}</p>}
      {plan.disclaimer && <p className="tiny faint cj-method">
        {bi(lang, plan.disclaimer, plan.disclaimer_mr)}</p>}
    </>
  )
}

function NoField({ lang, go }) {
  return (
    <div className="pad" style={{ paddingTop: 30 }}>
      <div className="empty">
        <div className="ic">🌾</div>
        <div className="h3" style={{ marginTop: 8 }}>
          {lang === 'mr' ? 'आधी शेत नोंदवा' : 'Register a field first'}
        </div>
        <button className="btn" style={{ marginTop: 16 }} onClick={() => go('addField')}>
          {lang === 'mr' ? 'शेत जोडा' : 'Add a field'}
        </button>
      </div>
    </div>
  )
}

export default Tools
