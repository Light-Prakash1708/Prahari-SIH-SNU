/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · two sections that appear on more than one screen

   QuickActions — Saurjya's bento, with his exact tile order and his mint hero
   tile. Every tile routes somewhere that works; none is a placeholder.

   HowItWorks — his features grid, re-cut. His version is five marketing claims
   side by side. Ours is the LOOP, in order, because the sequence is the
   argument: weather fires a model days before a symptom, that becomes a scout
   mission, the mission produces evidence, the evidence is diagnosed or
   refused, a threshold decides whether anything gets sprayed, and a follow-up
   closes it. A bag of features does not say that; a chain does.

   Every step names the thing in this app that actually performs it, so the
   section is a map of the product rather than a poster for it.
   ═══════════════════════════════════════════════════════════════════════════ */
import React from 'react'
import Icon from '../shell/Icon'
import './saurjya.css'

/* ── Quick Actions ─────────────────────────────────────────────────────── */
const QA = {
  mr: {
    title: 'जलद कृती', all: 'सर्व पहा',
    scan: 'पीक\nस्कॅन', scanSub: 'एआय त्वरित तपासणी',
    fert: 'खत कॅल्क्युलेटर', fertSub: 'NPK मात्रा',
    pest: 'फवारणी निर्णय', pestSub: 'मर्यादा व मिश्रण',
    cal: 'पीक दिनदर्शिका', calSub: 'पेरणी ते काढणी',
    exp: 'शेती खर्च', expSub: 'हिशेब',
    soil: 'माती आरोग्य', soilSub: 'सामू, ओलावा व अन्नद्रव्ये',
  },
  en: {
    title: 'Quick Actions', all: 'View All',
    scan: 'Scan\nCrop', scanSub: 'AI instant scan',
    fert: 'Fertilizer Calculator', fertSub: 'NPK dosage',
    pest: 'Pesticide Decision', pestSub: 'Threshold & mix',
    cal: 'Crop Calendar', calSub: 'Sow to harvest',
    exp: 'Farm Expense', expSub: 'Cost tracker',
    soil: 'Soil Health', soilSub: 'pH, moisture & nutrients',
  },
}
const q = (lang, k) => (QA[lang] || QA.en)[k] ?? QA.en[k]

export function QuickActions({ lang, go, showAll = true }) {
  const tile = (key, icon, route, cls = '') => (
    <button className={`qa-tile ${cls}`} onClick={() => go(route)}>
      <span className="qa-tile__icon"><Icon name={icon} size={20} /></span>
      <span>
        <span className="qa-tile__title" style={{ whiteSpace: 'pre-line' }}>{q(lang, key)}</span>
        <span className="qa-tile__sub">{q(lang, key + 'Sub')}</span>
      </span>
    </button>
  )

  return (
    <section style={{ marginTop: 20 }}>
      <div className="qa-head">
        <h2>{q(lang, 'title')}</h2>
        {showAll && (
          <button className="qa-viewall" onClick={() => go('tools')}>
            {q(lang, 'all')} <Icon name="chevron" size={13} />
          </button>
        )}
      </div>

      <div className="qa-grid">
        {tile('scan', 'camera', 'scan', 'qa-tile--hero')}
        {tile('fert', 'calc', 'fertilizer')}
        {tile('pest', 'shield', 'decide')}
        {tile('cal', 'calendar', 'crop')}
        {tile('exp', 'wallet', 'expenses')}
        {tile('soil', 'leaf', 'soil', 'qa-tile--wide')}
      </div>
    </section>
  )
}

/* ── How PRAHARI works ─────────────────────────────────────────────────── */
const STEPS = [
  {
    icon: 'radar', route: 'forecast',
    en: ['Weather fires a model',
         'Published infection models — Hutton, TOMCAST — run on this field\'s own weather every day.',
         'Nothing here needs a photograph. That is what makes it early warning.'],
    mr: ['हवामानावरून मॉडेल सक्रिय',
         'प्रकाशित संसर्ग मॉडेल या शेताच्या हवामानावर दररोज चालतात.',
         'यासाठी फोटोची गरज नाही — म्हणूनच ही पूर्वसूचना आहे.'],
  },
  {
    icon: 'clipboard', route: 'crop',
    en: ['A prevention window opens',
         'Crop stage, trap counts, field history and nearby reports are combined into a window with a stated reason for each factor.',
         'Every factor names the record it came from.'],
    mr: ['प्रतिबंध कालावधी उघडतो',
         'पीक अवस्था, सापळे, शेताचा इतिहास आणि जवळपासच्या नोंदी एकत्र येतात.',
         'प्रत्येक कारण कोणत्या नोंदीवरून आले ते दिसते.'],
  },
  {
    icon: 'camera', route: 'scan',
    en: ['A scout mission collects evidence',
         'Targeted inspection, then a photograph. A blurred or distant frame is refused before anything looks at it.',
         'The quality gate shows its measurements, not just a verdict.'],
    mr: ['तपासणी मोहीम पुरावा गोळा करते',
         'नेमकी तपासणी, मग फोटो. अस्पष्ट फोटो निदानाआधीच नाकारला जातो.',
         'गुणवत्ता तपासणी आकडे दाखवते, फक्त निकाल नाही.'],
  },
  {
    icon: 'bug', route: 'scan',
    en: ['AI diagnoses — or declines',
         'Prior × image fit × weather, combined by Bayes. If nothing clears the confidence floor, PRAHARI says so.',
         'An abstention is an answer, not a failure.'],
    mr: ['एआय निदान करते — किंवा नकार देते',
         'खात्री पुरेशी नसेल तर प्रहरी स्पष्ट सांगते.',
         'नकार हेही उत्तर आहे, अपयश नाही.'],
  },
  {
    icon: 'users', route: 'community',
    en: ['An expert settles what the model cannot',
         'Low-confidence cases go to a human, with the image, the features and the field context attached.',
         'One confirmation moves that taluka\'s prior by exactly one.'],
    mr: ['मॉडेल ठरवू शकत नाही ते तज्ज्ञ ठरवतात',
         'कमी खात्रीची प्रकरणे फोटो व संदर्भासह तज्ज्ञांकडे जातात.',
         'एक पुष्टी तालुक्याचा अंदाज एका अंकाने बदलते.'],
  },
  {
    icon: 'shield', route: 'decide',
    en: ['A threshold decides whether to spray',
         'Knowing what it is does not authorise a chemical — a count against the economic threshold does. The IPM ladder is climbed from the bottom.',
         'Chemistry is the last rung, never the first.'],
    mr: ['फवारणी करायची का, हे मर्यादा ठरवते',
         'रोग ओळखणे पुरेसे नाही — मोजणी आणि आर्थिक मर्यादा लागते.',
         'रसायन ही शेवटची पायरी आहे, पहिली नाही.'],
  },
  {
    icon: 'history', route: 'home',
    en: ['A follow-up closes the loop',
         'A scheduled re-scan is compared with the first photograph and reported as a direction, never as a percentage.',
         'This is the only ground truth PRAHARI gets for free.'],
    mr: ['पुनर्तपासणी चक्र पूर्ण करते',
         'ठरलेली पुनर्तपासणी पहिल्या फोटोशी तुलना करते.',
         'हाच प्रहरीला मिळणारा खरा पुरावा आहे.'],
  },
]

const HW = {
  mr: {
    eyebrow: 'प्रहरी कसे काम करते',
    title: 'शोधापासून कृतीपर्यंत —', em: 'एक साखळी',
    lede: 'प्रहरी ही सुट्या सुविधांची यादी नाही. हवामानापासून पुनर्तपासणीपर्यंत प्रत्येक पायरी पुढच्या पायरीला पुरावा देते.',
    chips: ['बहुभाषिक', 'ऑफलाइन चालते', 'प्रत्येक आकड्याचा स्रोत', 'तज्ज्ञ पडताळणी'],
  },
  en: {
    eyebrow: 'How PRAHARI works',
    title: 'From detection to action —', em: 'one chain',
    lede: 'PRAHARI is not a list of features. Each step below hands evidence to the next, from the weather that fires a model to the follow-up that proves whether anything worked.',
    chips: ['Marathi · Hindi · English', 'Works offline', 'Every number cites its source', 'Expert validation'],
  },
}
const h = (lang, k) => (HW[lang] || HW.en)[k] ?? HW.en[k]

export function HowItWorks({ lang, go }) {
  const L = lang === 'mr' ? 'mr' : 'en'
  return (
    <section className="hw">
      <span className="hw__eyebrow"><Icon name="shield" size={11} /> {h(lang, 'eyebrow')}</span>
      <h2 className="hw__title">{h(lang, 'title')} <em>{h(lang, 'em')}</em></h2>
      <p className="hw__lede">{h(lang, 'lede')}</p>

      <div className="hw__steps">
        {STEPS.map((s, i) => {
          const [title, body, proof] = s[L] || s.en
          return (
            <button key={i} className="hw__step" onClick={() => go(s.route)}>
              <span className="hw__badge">
                <Icon name={s.icon} size={18} />
                <span className="hw__num">{i + 1}</span>
              </span>
              <span style={{ minWidth: 0 }}>
                <h3>{title}</h3>
                <p>{body}</p>
                <span className="hw__proof">{proof}</span>
              </span>
            </button>
          )
        })}
      </div>

      <div className="hw__foot">
        {h(lang, 'chips').map((c, i) => (
          <span className="hw__chip" key={i}><i><Icon name="shield" size={11} /></i> {c}</span>
        ))}
      </div>
    </section>
  )
}
