/* Inline SVG icons.
   ─────────────────────────────────────────────────────────────────────────
   Saurjya's pages pull Font Awesome from a CDN. This app is offline-first by
   design — the same reason its fonts are bundled — so the glyphs it actually
   uses are inlined here instead. Same shapes, no network, no 200KB icon font.
   Paths are 24×24 and inherit currentColor. */
import React from 'react'

const P = {
  home:     'M12 3 2.5 10.6V21a1 1 0 0 0 1 1H9v-6h6v6h5.5a1 1 0 0 0 1-1V10.6L12 3Z',
  seedling: 'M12 21v-6m0 0c0-3.3-2.7-6-6-6H3c0 3.3 2.7 6 6 6h3Zm0 0c0-4.4 3.6-8 8-8h1c0 4.4-3.6 8-8 8h-1Z',
  camera:   'M9 4h6l1.4 2H20a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3.6L9 4Zm3 5.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9Z',
  users:    'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7.5.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM2 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5v1H2v-1Zm15.5-4.6c2.7.4 4.5 2.1 4.5 4.6v1h-4.2v-1c0-1.7-.6-3.2-1.6-4.3l1.3-.3Z',
  robot:    'M12 2v3m-6 3h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2Zm3 5h.01M15 13h.01M9 17h6',
  bars:     'M3 6h18M3 12h18M3 18h18',
  user:     'M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Zm0 2c-4.4 0-8 2.5-8 5.6V21h16v-1.4c0-3.1-3.6-5.6-8-5.6Z',
  xmark:    'M6 6l12 12M18 6 6 18',
  chevron:  'M9 5l7 7-7 7',
  back:     'M15 5l-7 7 7 7',
  shield:   'M12 2 4 5.5v6C4 16.6 7.4 21 12 22c4.6-1 8-5.4 8-10.5v-6L12 2Z',
  info:     'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-14h.01M11 12h1v5h1',
  toolbox:  'M9 6V4h6v2m-11 .5h16a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7.5a1 1 0 0 1 1-1Zm-1 5h18M10 11.5v3h4v-3',
  radar:    'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-16a6 6 0 1 0 0 12 6 6 0 0 0 0-12Zm0 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z',
  bug:      'M8 6a4 4 0 0 1 8 0m-9 3h10a2 2 0 0 1 2 2v3a7 7 0 1 1-14 0v-3a2 2 0 0 1 2-2ZM3 11h2m14 0h2M4 17h2m12 0h2M12 12v8',
  leaf:     'M4 20c0-8 5-14 16-14 0 11-6 15-12 15-2 0-4-.4-4-1Zm4-2 8-8',
  drop:     'M12 3s6 6.4 6 10.5A6 6 0 1 1 6 13.5C6 9.4 12 3 12 3Z',
  wallet:   'M3 8a2 2 0 0 1 2-2h13a1 1 0 0 1 1 1v1m-16 0v10a2 2 0 0 0 2 2h13a1 1 0 0 0 1-1v-3m0-6h-4a2 2 0 0 0 0 4h4a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1Z',
  calc:     'M6 2h12a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Zm2 3h8v3H8V5Zm.5 6.5h1m3 0h1m3 0h1m-8 3h1m3 0h1m3 0h1m-8 3h1m3 0h1m3 0h1',
  calendar: 'M7 2v3m10-3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
  bell:     'M12 3a6 6 0 0 0-6 6c0 5-2 6-2 6h16s-2-1-2-6a6 6 0 0 0-6-6Zm-2 15a2 2 0 0 0 4 0',
  history:  'M3 12a9 9 0 1 0 3-6.7M3 4v4h4m5-1v5l3.5 2',
  globe:    'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM2 12h20M12 2c2.7 3 4 6.3 4 10s-1.3 7-4 10c-2.7-3-4-6.3-4-10s1.3-7 4-10Z',
  gear:     'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm8-3.5c0 .5 0 1-.1 1.4l2 1.6-2 3.5-2.4-1a8 8 0 0 1-2.4 1.4L14.7 22h-4l-.4-2.6a8 8 0 0 1-2.4-1.4l-2.4 1-2-3.5 2-1.6a8 8 0 0 1 0-2.8l-2-1.6 2-3.5 2.4 1a8 8 0 0 1 2.4-1.4L10.7 2h4l.4 2.6a8 8 0 0 1 2.4 1.4l2.4-1 2 3.5-2 1.6c.1.4.1.9.1 1.4Z',
  signout:  'M15 17v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2m3 10 4-5-4-5m4 5H9',
  card:     'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm4 4.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm-2.5 7c0-1.4 1.1-2.2 2.5-2.2s2.5.8 2.5 2.2M14 9h4m-4 3.5h4m-4 3.5h2.5',
  bookmark: 'M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1Z',
  clipboard:'M9 3h6v3H9V3Zm-3 2h2m8 0h2a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1ZM8.5 11h7m-7 4h5',
  map:      'M12 21s7-6.3 7-11a7 7 0 1 0-14 0c0 4.7 7 11 7 11Zm0-8.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
  headset:  'M4 14v-2a8 8 0 1 1 16 0v2m-16 0a2 2 0 0 1 2-2h1v6H6a2 2 0 0 1-2-2v-2Zm16 0a2 2 0 0 0-2-2h-1v6h1a2 2 0 0 0 2-2v-2Zm-3 4v1a3 3 0 0 1-3 3h-2',
}

const FILLED = new Set(['home', 'user', 'shield', 'drop', 'bookmark', 'leaf'])

export default function Icon({ name, size = 20, style, className }) {
  const d = P[name] || P.info
  const filled = FILLED.has(name)
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true"
         className={className} style={style}
         fill={filled ? 'currentColor' : 'none'}
         stroke="currentColor" strokeWidth={filled ? 0 : 1.9}
         strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}
