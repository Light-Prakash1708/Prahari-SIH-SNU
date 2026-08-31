# PRAHARI · upgrade status

CURRENT PHASE: 0 — audit
STATUS: complete. No code modified.

## The headline finding

The brief assumes the Crop Calendar, Soil Self-Test and Quick Tools are static
or broken. That is true of **Saurjya's HTML pages**, which were never ported.
It is **not** true of the React app: `Crop.jsx`, `Soil.jsx` and `Water.jsx`
already call real endpoints. So most of Phases 1–3 is *extend*, not *build*.

The one genuinely large gap is ML: `VISION_PROVIDER=none`. The ONNX seam,
quality gate, dataset adapters (including the exact Kaggle set named in the
brief), training script and evaluation harness all exist. **There are no
trained weights.** That is Phase 4 and it is the only phase needing real work
from zero.

## Feature audit — A functional · B partial · C static UI · D mock · E missing · F broken

| # | Feature | Grade | Action | Evidence |
|---|---|---|---|---|
| 1 | Authentication | A | KEEP | bcrypt+JWT, sessions, reset, roles, 21 tests |
| 2 | Database | A | KEEP | 48 tables, 3 migrations, SQLite dev / Postgres prod |
| 3 | Crop/field models | A | KEEP | plots, crop_cycles, field_events, health_snapshots |
| 4 | Crop calendar | B | EXTEND | Crop.jsx draws a real stage timeline; no threat windows, no prevention window, no mission launcher |
| 5 | Soil self-test | A | EXTEND (UI) | soil.py = 6-question VSA, scored, banded, stored; Soil.jsx wired. Only the Saurjya visual is missing |
| 6 | Quick action tools | B/E | MIXED | calendar/soil/irrigation/IPM exist; fertilizer has an API but no dedicated UI; **expense tracker missing entirely** |
| 7 | Image diagnosis | B | EXTEND | full pipeline, storage, candidates, questions, expert escalation — but no model behind it |
| 8 | ML / vision | B→E | BUILD | vision.py segments leaf + 8 symptom features + quality gate (all real). classify() returns None. `ml/` has adapters, trainer, evaluator, ONNX export. **No weights exist.** |
| 9 | Risk engine | A | KEEP | Hutton/Smith infection models on real weather, per-plot, server-side |
| 10 | Weather | A | KEEP | open-meteo + cache + freshness; refuses to invent weather when unreachable |
| 11 | Pest traps | A | KEEP | traps, counts, series, trap-image scan, degree-day models |
| 12 | Observations | A | KEEP | images, candidates, clarifying questions, context |
| 13 | Community | A | KEEP | posts, images, comments, reactions, moderation, blocks, topics |
| 14 | Expert workflow | A | KEEP | cases, queue, reviews, model-agreement metric |
| 15 | Officer dashboard | A | KEEP | summary, hotspots, outbreaks, queue, route, assignments, audit |
| 16 | AgriDoc / Saathi | A | KEEP | grounded assistant with plot context + suggestions |
| 17 | API client | A | KEEP | one layer, cache, offline queue with idempotent client_ref |
| 18 | Image storage | A | KEEP | local + S3 providers behind one interface |
| 19 | Deployment | A | KEEP | Dockerfile, render.yaml (single origin), vercel.json, CI |
| 20 | Tests | A | KEEP | **199 passed** |

## Knowledge base already on disk (Phase 1 needs no fabrication)

- `crops.json` — 7 crops, each with named stage bands in days-after-sowing
- `problems.json` — 24 diseases + 7 pests, each with host crops, infection
  model, scouting text (EN/MR), and for pests: trap type, degree-day base
- `thresholds.json` — economic thresholds **with a `stage_factor` per crop
  stage** and an ICAR source per row. This is exactly the data a threat-window
  timeline needs, already sourced and citable.
- `ipm.json` — intervention ladders · `label_claims.json` — CIB&RC claims,
  PHI, toxicity triangle, Maharashtra restricted list

## Classification summary

- **KEEP (13):** auth, DB, fields, soil engine, risk, weather, traps,
  observations, community, expert, officer, AgriDoc, API client, storage, deploy
- **EXTEND (4):** crop calendar → prevention view · soil → Saurjya UI +
  crop-adaptive questions · fertilizer → dedicated UI over existing API ·
  diagnosis → hierarchical + multi-image
- **BUILD (3):** trained vision model + evaluation · expense tracker (new
  table, no existing model fits) · image-quality feedback loop in the UI
- **REPAIR (0):** nothing is broken. 199 tests green.

FILES CHANGED: none (audit only)
APIS USED: none
NEW APIS: none
DATABASE CHANGES: none
ML CHANGES: none
TESTS: `pytest tests -q` → 199 passed, 93s. `npm run build` clean.

KNOWN ISSUES:
- No trained vision model; `VISION_PROVIDER=none` (blocks real diagnosis)
- Sandbox has no egress to open-meteo; demos need `WEATHER_PROVIDER=demo`
- Officer/Expert consoles not yet on the Saurjya visual (deliberate)

## Dependency order (why this order)

1. **Crop Calendar** — pure aggregation over services that already work. No new
   dependencies. Delivers the "preventive system" feel first.
2. **Soil Self-Test UI** — backend is done; this is presentation + storage of
   crop-adaptive answers.
3. **Quick tools** — fertilizer/IPM/irrigation reuse existing APIs; expenses is
   the only new table.
4. **ML diagnosis** — longest lead time (dataset → train → evaluate → export →
   register). Independent of 1–3, so it can start in parallel if wanted.
5. **Image quality + multi-image** — depends on 4 being in place to be useful.
6. **Community → signals → hotspots** — already functional; only needs the
   Saurjya UI and a tighter loop.
7. **Follow-up learning** — depends on 4 (needs diagnoses to learn from).
8. **AgriDoc context** — best last; it should be able to cite everything above.

NEXT EXACT ACTION:
Await "START PHASE 1". First file to open then:
`backend/app/routers/misc.py` (the `/api/fields/{plot_id}/today` agenda route)
and `frontend/src/screens/Crop.jsx`. Plan: one new aggregation endpoint
`GET /api/crop-calendar/{plot_id}` that composes existing
risk / weather / agenda / traps / history services and adds threat windows
derived from `thresholds.json.stage_factor` + `problems.json`. No business
logic duplicated, no new table.
