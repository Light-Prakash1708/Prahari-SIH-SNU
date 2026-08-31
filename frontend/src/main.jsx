import React from 'react'
import { createRoot } from 'react-dom/client'

/* Fonts are bundled, not fetched.
   ─────────────────────────────────────────────────────────────────────────
   Every weight this app uses ships inside the build. An earlier version linked
   Google Fonts, which meant the Devanagari face — the one carrying the entire
   Marathi interface — arrived over the network. On a venue laptop with no wifi,
   or on the offline phone this app is explicitly designed for, that renders the
   Marathi build as tofu boxes. An offline-first agricultural app cannot depend
   on a CDN to display its primary language.

   Only the Latin and Devanagari subsets are imported. The full packages also
   carry Cyrillic, Greek and Vietnamese, which this app has no way of
   displaying and would only pad the offline bundle. */
import '@fontsource/plus-jakarta-sans/latin-400.css'
import '@fontsource/plus-jakarta-sans/latin-600.css'
import '@fontsource/plus-jakarta-sans/latin-700.css'
import '@fontsource/plus-jakarta-sans/latin-800.css'
import '@fontsource/archivo/latin-700.css'
import '@fontsource/archivo/latin-800.css'
import '@fontsource/source-sans-3/latin-400.css'
import '@fontsource/source-sans-3/latin-600.css'
import '@fontsource/source-sans-3/latin-700.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import '@fontsource/noto-sans-devanagari/devanagari-400.css'
import '@fontsource/noto-sans-devanagari/devanagari-600.css'
import '@fontsource/noto-sans-devanagari/devanagari-700.css'

import './styles.css'
/* Saurjya's identity is layered over the design system: tokens first, then the
   chrome. Both come after styles.css so they win on equal specificity. */
import './brand.css'
import './shell/shell.css'
/* Saurjya's recurring surfaces — the Quick Actions bento, the AgriDoc sheet,
   the how-it-works pipeline and the scanner viewfinder — are imported here
   rather than from ui.jsx, because the Camera primitive lives in ui.jsx and a
   stylesheet import there would load on every screen that uses any primitive. */
import './screens/saurjya.css'
/* Last: the polish layer re-skins the components above with Saurjya's card
   language — 26px radii, his wide soft shadow, the pooled-light ground. */
import './polish.css'
import App from './App'

createRoot(document.getElementById('root')).render(<App />)
