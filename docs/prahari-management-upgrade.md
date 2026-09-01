# View Management upgrade — audit

CURRENT STAGE: 0 — audit only. No application code modified.
STATUS: complete, waiting for "START MANAGEMENT STAGE 1".

## CURRENT IMPLEMENTATION
- Screen: `frontend/src/screens/Decide.jsx` (455 lines), route `decide`, title
  "Should I Spray?". Entered from Scan, Home agenda, Crop, More, Tools.
- API: `GET /api/decisions/{plot_id}/should-i-spray?target=` →
  `routers/decisions.py` → `services/decisions.py::spray_decision` +
  `prescription`, with `etl.py`, `prescribe.py`, `chemicals.py`, `reference.py`.
- Count source: latest row in `threshold_checks` — a real recorded field count.
- Recording an application (`POST /api/applications`) already INSERTs a
  `followups` row with `due_on` and queues a notification.

## REUSABLE LOGIC (do not rebuild any of this)
- The decision state machine already covers spec states A–F: abstained
  diagnosis → `low_confidence`; no count → `no_count`; below ETL →
  `etl_not_crossed`; `act-nonchemical` band; life stage unreachable →
  `life_stage_unsuitable`; no verified claim → `expert_review`; crossed →
  `intervene`. Each carries evidence rows and `recheck_after_hours`.
- ETL with per-stage `stage_factor`, provenance, economics, count trend +
  `trend_alert`, `saving_if_not_sprayed`.
- IPM ladder per target from `data/ipm.json`, with per-item cost; chemical rung
  gated on a VERIFIED CIB&RC claim. `prescribe.py` does MOA rotation, PHI,
  restricted list, flowering check, dose arithmetic.
- Prevention window: `cropcalendar._prevention_window` (built, not on Decide).
- Agenda/scout mission: `agenda.py`. Follow-ups: `routers/followups.py` with the
  self-report outcome path. Expert: `POST /api/observations/{id}/expert-review`.
  History: `GET /api/plots/{id}/history`. All exist and are unused by Decide.
- Authorization: every route calls `visible_plot(db, user, plot_id)`.

## PROBLEMS (verified, not assumed)
1. **Spec §7 does not apply here.** I searched for a posterior/confidence →
   count or severity conversion and there is none. Count comes only from
   `threshold_checks`. There is nothing to fix; nothing should be "separated".
2. **Diseases are a dead end.** Verified against the API: `target=late_blight`
   returns `no_count` and asks for a count. Diseases have no trap count — they
   need severity/incidence. Decide's chip list also filters
   `kind === 'pest' && etl != null`, so a disease arriving from Scan is not
   even selectable. This is the real diagnosis→management break.
3. Missing on screen though present in the backend: prevention window, today's
   scout task, follow-up loop, before/after, field history, expert escalation
   button (even when the decision itself is `expert_review`).
4. IPM ladder is display-only — no "add to plan"; a missing rung (these targets
   return cultural/biological/chemical only) is silently absent.
5. Everything renders expanded; no hierarchy, no collapsibles.
6. Weather is NOT an input to `spray_decision`. Spec §8/§20 must not claim it.

## FILES TO MODIFY
`frontend/src/screens/Decide.jsx`, `backend/app/services/decisions.py`,
`backend/app/routers/decisions.py`, `backend/app/etl.py` (disease path only),
`backend/tests/test_safety.py` + a new `test_management.py`.

## FILES TO AVOID
auth/login, Home, Community, CropJourney/Fields, Soil, Saathi, Officer/Expert/
Admin, `shell/`, `brand.css`, `polish.css`, all schema files.

## NEW BACKEND LOGIC REQUIRED
Only two things are genuinely missing:
- a **disease severity path** (assessed incidence vs an action level) so
  §26 state B/C works for a disease, not just a pest;
- surfacing existing services on this screen. A single
  `GET /api/management/{plot_id}?target=` aggregating should-i-spray +
  prevention window + agenda + open follow-up + history would remove 4 round
  trips on a mobile network. It must compose, own no agronomy.
DATABASE: no schema change identified as necessary. If the disease path needs
a severity record, `observations`/`threshold_checks` are candidates first.

## IMPLEMENTATION ORDER
1 decision card + states · 2 disease severity path · 3 why-this-decision ·
4 field evidence + add observation · 5 prevention window + today's action ·
6 trend · 7 actionable IPM ladder · 8 chemical gate + resistance ·
9 follow-up + before/after · 10 history · 11 collapsibles + i18n · 12 tests.

TESTS: none added yet. NEXT EXACT ACTION: await "START MANAGEMENT STAGE 1".
