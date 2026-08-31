# PRAHARI · upgrade status

PHASE: 1 — Crop Calendar → Crop Journey
STATUS: complete and verified in a browser against the running backend

DONE:
- One aggregation endpoint `GET /api/crop-calendar/{plot_id}`. It COMPOSES
  services that already existed — `risk.crop_stage`, `risk.board`,
  `risk.trap_state`, `forecast.by_day`, `agenda`, `risk.snapshot_history`.
  No agronomy, no risk level and no date is re-derived inside it.
- Crop journey: the crop's own stage table resolved against THIS field's
  sowing date, so every band on the rail is a real date. No sowing date →
  day numbers and null dates, never invented ones.
- Threat windows per stage, from `thresholds.json.stage_factor` — a sourced
  ICAR table. Each row shows the base ETL, the stage factor, the adjusted
  threshold and its citation, so an agronomist can check the arithmetic.
- **Disease bands appear only on the CURRENT stage.** A disease fires on
  weather; weather beyond the forecast horizon does not exist; so future
  stages are left blank with `disease_note` saying why. This is the single
  most important honesty property of the screen and it has its own test.
- Prevention window with factor-by-factor reasons, assembled only from
  records that exist (models firing, stage lowering a threshold, trap counts
  recorded, regional corroboration). A missing factor is omitted, never
  rendered as "no data".
- Today's mission is the EXISTING agenda verbatim — a test asserts it is
  byte-identical to `/api/fields/{id}/today`, so no second mission system.
- Field health history read from five existing tables (health_snapshots,
  observations+diagnoses, trap_observations, applications, followups).
  Nothing new is written; an abstained diagnosis is reported as an
  abstention rather than smoothed into a blank scan.
- Frontend `CropJourney.jsx` + `crop-journey.css` in Saurjya's card language.
  The Crop tab now opens the journey; the older Crop screen is PRESERVED at
  route `cropRecord` and linked from the drawer.

FILES:
- new: backend/app/cropcalendar.py, backend/app/routers/cropcalendar.py
- new: backend/tests/test_crop_calendar.py
- new: frontend/src/screens/CropJourney.jsx, screens/crop-journey.css
- edit: backend/app/main.py (register router — 2 lines)
- edit: frontend/src/api.js (one client method)
- edit: frontend/src/App.jsx (route the Crop tab; keep old screen)
- edit: frontend/src/shell/Chrome.jsx (drawer entry for the old screen)
- edit: frontend/src/shell/shell.css (bottom sheets must sit above the
  floating nav bar and clear it — the bar was covering the last sheet row)

APIS: reused risk/board/trap_state/forecast/agenda/snapshot_history unchanged
NEW APIS: GET /api/crop-calendar/{plot_id} — aggregation only
DATABASE: no migration, no new table, no column added, no data touched
ML: none

CORRECTION MADE DURING THE PHASE — worth keeping:
The first banding compared each stage_factor against fixed cutoffs (under 0.8 =
high). Plausible, and useless: tomato's tables put whitefly at 0.5–0.6 early and
Tuta at 0.7 late, so four of five stages came back red and the timeline said
nothing. Factors are only meaningful RELATIVE TO THE SAME PEST, so each pest is
now banded against its own range across the crop's stages, and a stage is banded
by how many pests peak there rather than by its worst single pest. Tomato now
reads watch / watch / watch / HIGH / normal — fruiting alone, which is where Tuta
and Helicoverpa both bottom out. The absolute factor, the adjusted threshold and
`peak_factor` are all still returned, so the judgement stays checkable.

TESTS: tests/test_crop_calendar.py → 14 passed. Full suite → 213 passed
(199 before this phase). `npm run build` clean. Browser: Crop tab renders stage
rail, prevention window with four evidence factors, mission, watchlist, threat
grid and history, with zero console errors.
Covers: sowing date moves the calendar; crop changes the threats; no date → no
invented dates; disease bands never leak to future stages; every pest band
carries source + arithmetic; the timeline discriminates between stages; a peak
is relative to the pest, not an absolute cutoff; prevention factors are never
placeholders; history empty when there are no records; a real trap count reaches
history; mission identical to the agenda; stage agrees with /api/risk;
cross-farmer read blocked; anonymous blocked.

ISSUES:
- The `_history` limit is per-source, so a very busy field can return up to
  2x limit rows. Harmless, but worth a single ordered query later.
- Officer and Expert consoles still use the old chrome (unchanged this phase).

NEXT: Phase 2 — Soil Self-Test. The backend (`app/soil.py`, 6-question VSA,
scored/banded/stored, plus the lab nutrient-gap report) is already complete and
already carries the screening-vs-lab framing. The work is frontend: rebuild
`screens/Soil.jsx` in Saurjya's card language, make the questions adapt to the
crop and stage where the data supports it, and surface the existing
`soil_tests` history as a per-field trend. No new table.
