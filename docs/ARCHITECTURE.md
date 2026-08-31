# PRAHARI · architecture

A map, written so a new teammate can find the file they need in under a minute
and know what may safely be changed in it.

---

## One sentence

A FastAPI backend that owns every agronomic decision, a React/Vite phone app
that renders those decisions and never computes them, and an ML pipeline whose
output the backend will refuse to serve until an evaluation has produced a
number for it.

```
                 ┌──────────────────────────────────────────┐
  phone ────────▶│  frontend/  React + Vite, one bundle     │
  (offline-      │  api.js — the only door to the backend   │
   capable)      └───────────────┬──────────────────────────┘
                                 │ /api/*   bearer token
                 ┌───────────────▼──────────────────────────┐
                 │  backend/app/routers/    HTTP only       │
                 │  backend/app/services/   the agronomy    │
                 │  backend/app/data/*.json the knowledge   │
                 └───────────────┬──────────────────────────┘
                    ┌────────────┼────────────┐
              PostgreSQL     open-meteo     storage
              (or SQLite)     weather      (local | S3)
                                              │
                                    ml/ ──▶ ONNX ──▶ vision_service
```

---

## The request path, once

Take "should I spray?" — it touches most of the system.

1. `routers/decisions.py` receives it, checks the token, and confirms the plot
   belongs to the caller (`deps.owned_plot`).
2. `services/risk.py` fetches weather (`weather.py`, cached, and **raising**
   rather than inventing if the provider is unreachable) and computes the crop
   stage from the sowing date against `data/crops.json`.
3. `services/decisions.py` reads the last trap count, scales the economic
   threshold from `data/thresholds.json` by that stage's factor, and returns a
   verdict with every term of the arithmetic attached.
4. If the verdict permits chemistry, `chemicals.py` filters to CIB&RC-verified
   label claims for that crop and pest from `data/label_claims.json`.
5. The router shapes the response. It adds no logic.

Every step is inspectable in the response body. That is deliberate: an
agronomist or a judge must be able to disagree with a specific number.

---

## Backend

### `routers/` — HTTP only
Validate input, call a service, shape output. If you are writing a comparison
against a threshold here, it belongs in a service.

`routers/cropcalendar.py` is the shortest example of the intended shape: 40
lines, all of it wiring.

### `services/` — the agronomy
| File | Owns |
|---|---|
| `services/risk.py` | crop stage, the risk board, trap state, field health |
| `services/diagnosis.py` | the Bayesian combination, and the decision to abstain |
| `services/decisions.py` | economic threshold, IPM ladder, the spray verdict |
| `forecast.py` | running infection models over a weather window |
| `agenda.py` | "what should I do today", in order of consequence |
| `cropcalendar.py` | composes the above for the calendar screen; owns nothing |
| `fieldboard.py` | one card per field, ordered by which needs attention first; owns nothing |
| `soil.py` | the visual soil assessment and the nutrient gap |
| `outbreak.py`, `signals.py`, `spatial.py` | regional aggregation and hotspots |

### `data/` — the knowledge base
Plain JSON, no code. Editing these changes what farmers are told, so every
threshold row carries a `source`.

| File | Contents |
|---|---|
| `crops.json` | 7 crops, stage bands in days after sowing |
| `problems.json` | 24 diseases + 7 pests: host crops, infection model, scouting text |
| `thresholds.json` | economic thresholds, **with a `stage_factor` per crop stage** |
| `ipm.json` | intervention ladders, climbed from the bottom |
| `label_claims.json` | CIB&RC claims, PHI, toxicity triangle, restricted list |
| `soil.json` | VSA questions, ICAR rating classes, recommended doses |
| `talukas.json` | the geography |

### `schema/` — migrations
Numbered, applied in order on startup, recorded in `schema_migrations`.
**Never edit a merged migration.** Add `005_*.sql`. Placeholders like
`{{PK_SERIAL}}` and `{{JSON}}` are substituted per dialect in `db.py`, so one
file serves SQLite and PostgreSQL.

### The seams
Three things are swapped by configuration, never by an `if` in a handler:

| Setting | Options | Behaviour when absent |
|---|---|---|
| `WEATHER_PROVIDER` | `openmeteo` / `demo` / `none` | **503, never generated data** |
| `VISION_PROVIDER` | `onnx` / `api` / `none` | reports "no evaluated model" |
| `LLM_PROVIDER` | `gemini` / `openai` / `none` | AgriDoc stays templated |
| `STORAGE_PROVIDER` | `local` / `s3` | — |

`config.py` refuses to start in production with a demo provider, a short JWT
secret, a wildcard CORS origin or a SQLite URL. CI asserts each refusal.

---

## Frontend

`api.js` is the only module that talks to the backend, and it carries four
things a component would otherwise have to reimplement: the bearer token,
a per-URL cache so the app opens with the last known state offline, a durable
write queue keyed on `client_ref` so a flaky connection cannot double-count a
trap, and a 401 handler that returns to sign-in.

Screens are one file each. Shared chrome — header, drawer, account sheet,
bottom bar, icons — lives in `shell/`. Primitives live in `ui.jsx`.

Role decides the whole product: `App.jsx` renders the farmer app, the officer
console or the expert portal from `/api/auth/me`. **The role is not a client
preference**; every screen behind it is scoped server-side, so the farmer app
asks for its own fields and is given only those.

### Two constraints
- **Bundled, never fetched.** Fonts and icons ship in the build. A CDN font is
  a Marathi interface of empty boxes on the phone this was built for.
- **200 kB gzipped.** CI fails above it. No charting library — charts are
  hand-drawn SVG in `ui.jsx`.

---

## ML

`ml/` is the pipeline; `backend/app/vision_service.py` is the seam it fills.

```
datasets/      adapters (Kaggle crop-disease, PlantDoc) → a manifest
preprocessing/ split grouped by FIELD, so no field is in two splits
training/      transfer learning, writes a run card with dataset + seed + commit
evaluation/    per-class precision/recall/F1, confusion matrix, abstention curve
export/        ONNX with numerical parity checked, then register_model.py
```

`vision.py` (the measurement layer) is separate and always runs: it segments
the leaf, measures explicit symptom features, and applies the quality gate.
A photograph that fails the gate is never diagnosed by anything.

**There are no trained weights in this repository.** `VISION_PROVIDER=none`
ships as the default and the app claims no accuracy anywhere. `ml/README.md`
carries the seven commands that produce weights, and the number that governs
the whole exercise: PlantVillage-trained models score ~99% on PlantVillage and
**19.73%** on real field photographs.

---

## Testing

275 tests. The interesting ones assert things that must **never** happen:

| File | Guards |
|---|---|
| `test_isolation.py` | one farmer cannot read another's field |
| `test_safety.py` | nothing authorises a chemical without a threshold crossing |
| `test_farm_ledger.py` | recording costs changes no agronomic output at all |
| `test_multi_image.py` | repeated uploads cannot talk the engine out of abstaining |
| `test_crop_calendar.py` | disease bands never appear on a stage with no weather |
| `test_followup_outcome.py` | a self-report is never presented as a measurement |
| `test_weather.py` | an unreachable provider produces an error, not a number |
| `test_privacy.py` | deleting my account never touches another farmer's records |
| `test_llm_seam.py` | a language model cannot introduce a number or a product name |
| `test_field_board.py` | the multi-field board never disagrees with a field's own screen |

When one of these fails, the feature is wrong, not the test.

---

## Deployment

One Docker image serves the API and the built frontend from a single origin, so
there is no CORS surface in production. `render.yaml` is a working blueprint;
`vercel.json` deploys the frontend alone if the API is hosted elsewhere.

Production requires: `APP_ENV=production`, a 32+ character `JWT_SECRET`, a
PostgreSQL `DATABASE_URL`, explicit `CORS_ORIGINS`, and a real
`WEATHER_PROVIDER`. The app refuses to start otherwise.

Move `STORAGE_PROVIDER` to `s3` for anything past a pilot — a container disk is
not a backup, and observation images are evidence.
