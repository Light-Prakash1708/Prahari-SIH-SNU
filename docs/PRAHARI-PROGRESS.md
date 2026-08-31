# PRAHARI · integration progress

Saurjya's UI (visual truth) + the existing v3.0 backend (functional truth).
Read this file first in a new session, then open only the files NEXT TASK names.

---

CURRENT BATCH: 1–3 (assets/branding, application shell, authentication)
STATUS: complete, verified in a browser against the running backend

COMPLETED:
- Git checkpoint on branch `feat/saurjya-ui-integration`; original tree is the
  first commit on that branch. Nothing deleted.
- Saurjya's brand assets copied into `frontend/public/brand/`
  (logo, favicon, footer-logo, loader, hero-bg, 5 feature visuals).
- Design tokens re-anchored on Saurjya's palette in `src/brand.css`; every
  screen already written against `--g-900` / `--card` / `--sans` inherited the
  new identity without being rewritten.
- Plus Jakarta Sans added as a BUNDLED font (@fontsource) — not the CDN link
  Saurjya's static pages use. The app stays offline-capable.
- Application shell rebuilt to Saurjya's design in `src/shell/`:
  header (hamburger · centred logo · profile), navigation drawer, account
  sheet, floating bottom bar with the raised scan FAB. All items route through
  the app's existing `go()` router.
- Font Awesome replaced by inline SVG (`src/shell/Icon.jsx`) — same shapes, no
  CDN, no 200KB icon font.
- Auth screen restyled to Saurjya's phone card (curved cover, radar sweep,
  pill buttons). Form logic UNCHANGED — still posts to the existing
  /api/auth/register, /login, /password/reset-request, /password/reset.
- Removed the duplicated bell/profile pair from Home (the header owns them now).

FILES CHANGED:
- added: frontend/src/brand.css
- added: frontend/src/shell/{shell.css, auth.css, Icon.jsx, Chrome.jsx}
- added: frontend/public/brand/*
- edited: frontend/src/main.jsx (font + css imports)
- edited: frontend/src/App.jsx (shell wired in; emoji tab table removed)
- edited: frontend/src/screens/Auth.jsx (markup only)
- edited: frontend/src/screens/Home.jsx (removed duplicate header controls)
- edited: frontend/index.html (favicon, theme-color)

FUNCTIONALITY CONNECTED (all pre-existing backend, nothing rebuilt):
- register / login / logout / session token / role routing
- /api/auth/me → real name, role, taluka, village in the account sheet
- /api/plots → field count and field switcher
- /api/risk/:id → farm health score, crop stage, scout missions, forecast
- /api/notifications → unread badge on the header

NEW BACKEND: none. No endpoint, model or migration was added or changed.

TESTS:
- backend: tests/test_auth.py + tests/test_isolation.py → 21 passed
- frontend: `npm run build` clean
- browser: register → login → dashboard → drawer → account sheet → tab switch,
  zero console errors

KNOWN ISSUE:
- Officer and Expert consoles still render their own chrome (`shell wide`) and
  have not been restyled. Deliberate — officer is desktop-first, batch 14.
- Local sandbox has no egress to open-meteo, so the demo runs with
  WEATHER_PROVIDER=demo. The backend correctly refuses to invent weather when
  the provider is unreachable; this is not a bug to "fix".

NEXT TASK:
- BATCH 4–5: restyle Home dashboard cards and Fields/Crop screens to Saurjya's
  card and bento language (`quick-actions.css` bento grid is the reference).
  Start at frontend/src/screens/Home.jsx and Fields.jsx. Keep every existing
  api.* call; change presentation only.

RUN LOCALLY:
    cd backend && . .venv/bin/activate && DEMO_MODE=true WEATHER_PROVIDER=demo \
      python -m uvicorn app.main:app --port 8000
    cd frontend && npm run dev
