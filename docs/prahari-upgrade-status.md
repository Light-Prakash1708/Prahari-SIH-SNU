# PRAHARI · upgrade status

PHASE: all — delivered in one pass
STATUS: complete. 237 backend tests pass, frontend builds, walked through a browser.

## What was built

**Saurjya UI integration** — brand tokens, bundled Plus Jakarta Sans, and the
header / drawer / account-sheet / floating-bar chrome as React components over
the existing design tokens. Font Awesome and Google Fonts inlined and bundled,
because the app is offline-first. The mock farmer in Saurjya's markup (Ramesh
Kumar, 14 reports, 98% accuracy) was replaced by `/api/auth/me`.

**Crop Journey** — `GET /api/crop-calendar/{plot_id}`, one aggregation over
services that already existed. Stage rail from this field's sowing date,
prevention window with factor-by-factor evidence, today's mission (the existing
agenda, verbatim), threat-by-stage, and history from five existing tables.

**Farm ledger** — `/api/farm-ledger`, the only new table (`farm_entries`,
migration `004_ledger.sql`). Expense and income, category breakdown, cost per
acre, idempotent on `client_ref` for the offline queue.

**Multi-image diagnosis** — `POST /api/observations/{id}/images` with five
roles, same quality gate, diagnosis re-run.

**Follow-up self-report** — `POST /api/followups/{id}/outcome` for a farmer who
cannot retake a comparable photograph.

**Quick Tools hub + Fertilizer Guide** — Saurjya's bento over the tools that
exist, plus a screen for the nutrient-gap API that had none.

**ML pipeline** — verified end to end; `--no-pretrained` added for offline runs;
`pretrained_init`/`deployable` recorded in the run card.

## The four properties that are enforced by tests, not by intention

1. **Disease bands never appear on a future stage.** Weather beyond the forecast
   horizon does not exist, so those stages stay blank with the reason on screen.
2. **Money never reaches the agronomic engines.** A test records costs and
   asserts the risk board, threat windows, prevention window and agenda are
   byte-identical before and after.
3. **Repetition cannot manufacture confidence.** The same leaf uploaded four
   times must not talk the engine out of an abstention.
4. **A self-reported outcome is never presented as a measured one.** Both close
   the loop; only a rescan produces evidence a treatment worked.

## Two corrections worth remembering

**Threat banding.** The first version compared each `stage_factor` to fixed
cutoffs. Tomato's tables put whitefly at 0.5–0.6 early and Tuta at 0.7 late, so
four of five stages came back red — true of some pest in every case, and no help
at all. Factors are only meaningful relative to the same pest, so each pest is
now banded against its own range and a stage is judged by how many pests peak
there. Tomato reads watch / watch / watch / HIGH / normal.

**Open follow-ups.** Adding the self-report path exposed a live bug: "open" was
defined as *no rescan observation*, so a follow-up closed by a report would have
been asked for forever. Now *no observation AND no outcome*, in all five places
that ask — the due list, the day's agenda and the field-health card included.

FILES ADDED
- backend: `app/cropcalendar.py`, `app/routers/cropcalendar.py`,
  `app/routers/ledger.py`, `app/schema/004_ledger.sql`
- tests: `test_crop_calendar.py` (14), `test_farm_ledger.py` (10),
  `test_multi_image.py` (7), `test_followup_outcome.py` (7)
- frontend: `brand.css`, `shell/{shell,auth}.css`, `shell/Icon.jsx`,
  `shell/Chrome.jsx`, `screens/CropJourney.jsx`, `screens/crop-journey.css`,
  `screens/Tools.jsx`, `screens/tools.css`, `public/brand/*`

DATABASE: one additive migration. Nothing dropped, truncated, reseeded or
renamed. No primary ID changed.

TESTS: 237 passed (199 before this work). `npm run build` clean.

## Known limitations — stated, not hidden

- **No trained vision weights.** The Kaggle dataset is behind an account and
  this build environment had no route to it. The pipeline is verified end to end
  and `ml/README.md` carries the exact commands; `VISION_PROVIDER` ships as
  `none` and the app claims no accuracy anywhere.
- **Officer and Expert consoles** still use the older chrome. They are
  desktop-first and were deliberately left alone.
- **`_history` in the crop calendar** limits per source, so a very busy field can
  return up to 2× the limit. Harmless; a single ordered query would be tidier.
- **Sentinel-2 field segmentation** was assessed and deferred — see
  `prahari-reference-notes.md`. It adds a raster pipeline for a benefit the
  officer console does not currently lack.
