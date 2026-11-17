# PRAHARI — Bengal AI Start-up Summit readiness

**Audit:** 17 November 2026.

**Code audited:** branch `summit-readiness`, cut from `origin/main` at `7ef5943`. That is the commit live on Render: deploy `dep-dbtueaek1f9s739po4g0`, redeployed 17 Nov after the weather setting change.

**Production checks:** taken from the Render API and from `/api/ready` on `https://prahari-7m0e.onrender.com`.

**Not verified here:**
- **GitHub Actions results.** This environment has no GitHub API access.
- **PostgreSQL migration tests.** There is no PostgreSQL in this environment. No migration was added in this sprint.

Every finding records:
- current state
- evidence
- user impact
- judge impact
- fix
- priority
- effort
- how to verify

**Status values:**
- **DONE**: changed in this sprint and tested.
- **CONFIG**: changed in a Render setting.
- **OWNER**: needs a decision, money or a credential.

## P0 — the demo must not fail

### 1. Production served generated weather to real fields — CONFIG + DONE
- **Current state:**
  - **Before:** `/api/ready` reported `demo_fallback: true`. Render logs showed every risk request ending in "live window too short for the models; serving GENERATED weather".
  - **Now:**
    - `WEATHER_DEMO_FALLBACK=false` is set on the live service. Render redeployed it at 05:33 UTC on 17 Nov.
    - The code now **refuses** the flag when `APP_ENV=production`. It logs an error and keeps the service up rather than crashing.
- **Evidence:**
  - `weather.py` (`WeatherService.__init__`).
  - Test `test_production_ignores_the_generated_weather_fallback`.
- **User impact:**
  - **Before:** a farmer's risk level was computed on invented weather.
  - **Now:** a field without enough history says the model cannot run.
- **Judge impact:** removes the single most damaging finding a technical judge could make.
- **Verify:**
  - `/api/ready` → `checks.weather.demo_fallback` is absent or false.
  - Logs show no "serving GENERATED weather".

### 2. Production cannot run the risk models for a new field — OWNER (blocker)
- **Current state:**
  - Open-Meteo answers HTTP 429 to Render's shared outbound IP, even on the first request after a cold start (log at 05:29:31 UTC, 17 Nov).
  - WeatherAPI's free plan gives one day of history. The models need 21.
  - The weather archive (migration 008) only helps a cell that has had one successful Open-Meteo answer. The logs show `missing: 20, found: 0`, so no production cell has been filled yet.
- **User impact:** every production field shows forecast weather, but no disease-risk level. This is honest, but it means no early warning.
- **Judge impact:** the headline feature ("risk before symptoms") cannot be shown on production today. Show it on staging (finding 6), and say why.
- **Fix:** give the history provider an IP-independent quota. Either option is a configuration change, not code:
  - **(a)** An Open-Meteo commercial API key. Set `OPEN_METEO_API_KEY` and `WEATHER_API_URL=https://customer-api.open-meteo.com/v1/forecast`. The code already sends the key.
  - **(b)** A WeatherAPI plan whose history covers 21 days. Raise `WEATHERAPI_HISTORY_DAYS` to match, and raise `WEATHERAPI_MAX_HISTORY_CALLS`.
- **Effort:** minutes, once a plan is bought.
- **Verify:** `/api/fields/<id>/weather` on production returns `history_days` ≥ 21, and the risk board shows a model level.
- **Not done:** another free source (NASA POWER) could not be tested from this environment, so it was not added blind.

### 3. Database expires on 16 December 2026 — OWNER
- **Current state:** Render reports `prahari-db` (`dpg-dbtg8rbrjlhs73f947e0-a`) on the free plan with `expiresAt 2026-12-16T13:26Z`. This has happened once already: the October outage.
- **User impact:** all accounts and records will be deleted on that date.
- **Judge impact:** none before the summit. After it, total loss.
- **Fix:** upgrade the database to a paid plan before 16 December, or move to an external PostgreSQL with backups. `render.yaml` already names `basic-256mb`.
- **Effort:** 5 minutes in the dashboard.
- **Verify:** `list_postgres_instances` shows no `expiresAt`.
- **Backups:** the free plan has no point-in-time recovery, and there is no backup of the current data.

### 4. Cold start of about 50 s on the free plan — OWNER
- **Current state:** the first request after idle returned Render's "Application loading" 503 for more than 20 s during this audit.
- **Judge impact:** a judge opening the link sees a loading page.
- **Fix:** a paid Starter instance, or open both services about 2 minutes before presenting. HEAD on `/api/health` returns 200, so an uptime monitor can keep them warm.
- **Verify:** time to first byte under 2 s on a cold browser.

### 5. Uploaded photos are lost on every restart — OWNER
- **Current state:** `STORAGE_PROVIDER=local` on a free service with no disk.
- **User impact:** evidence photos vanish. Decisions survive, because they are in the database.
- **Fix:** set `STORAGE_PROVIDER=s3` with the five `S3_*` variables (Cloudflare R2 works). The adapter already exists.

### 6. Judge mode was demonstrated on production — DONE
- **Current state:**
  - Demo consoles were reached on the production service. The demo accounts live in the production database.
  - Production does **not** have `DEMO_MODE`. `APP_ENV=production` refuses it.
- **Fix:**
  - **Separate staging service:** `prahari-staging` (`srv-dbtuos88v5cc73bdrf9g`, https://prahari-staging.onrender.com).
    - Settings: `APP_ENV=demo`, `DEMO_MODE=true`, `AUTO_SEED_DEMO=true`, `DEMO_CONSOLE_ACCESS=true`, `WEATHER_PROVIDER=demo`.
    - Its own SQLite file on the container. The database is separate and is re-seeded with synthetic data on every restart.
  - **Judge mode** (`app/judge.py`), mounted only when `DEMO_MODE=true`:
    - `GET /api/demo/judge` returns the eight cases.
    - `POST /api/demo/judge/reset` restores the starting state.
    - Reset archives (never deletes) the fixed demo farmer's fields, sets the labelled weather story, and gives the demo FPO three synthetic members.
  - **Consoles screen:** a Judge panel lists the cases and has a one-click reset.
- **Tests:** three judge tests, including that the routes do not exist without `DEMO_MODE`.
- **Open:**
  - Staging builds from `main`, so judge mode appears there only after this branch is pushed.
  - **OWNER:** consider `DEMO_CONSOLE_ACCESS=false` on production now that staging exists.

### 7. Environment drift — partly DONE
| Setting | `render.yaml` | Live service |
|---|---|---|
| Plan | starter + disk | free |
| Vision | `VISION_PROVIDER=none` | `vision.engine=gemini` (`/api/ready`) |
| Demo consoles | not declared | `DEMO_CONSOLE_ACCESS=true` |
| Admin bootstrap | not declared | `admin_bootstrap=armed` |

The staging service has been added to the blueprint. The live service is not driven by the blueprint, so this table is the record.

## P0 — Bengal relevance

### 8. A Bengal farmer could not register a Bengal location — DONE
- **Before:**
  - Sign-up and Add-field offered only 10 hard-coded Nashik talukas.
  - A GPS fix in Hooghly was assigned to the nearest Nashik taluka.
  - A field with no GPS used that Nashik taluka's coordinates for its weather.
- **Evidence:** `reference.nearest_taluka` (pure nearest-point, no distance limit) and `Auth.jsx` / `Fields.jsx` `TALUKAS` constants.
- **Impact:** wrong officer queue, wrong outbreak cluster, wrong local prior, and wrong weather for the risk models.
- **Fix:**
  - 11 West Bengal blocks were added, with Bengali names and Wikipedia coordinates. Farm counts are `null`: not sourced.
  - A field more than 40 km from any covered unit is refused (`outside_coverage`).
  - Gi* and the spread front run per region. Units without a farm count are excluded.
  - Sign-up and Add-field read the list from `/api/reference`, grouped by state and district.
- **Tests:** five geography tests.

### 9. No Bengali interface — DONE (draft, needs review)
- **What was built:**
  - `frontend/src/i18n/bn.js`: about 360 entries, keyed by the English source.
  - `bi()` and `t()` route Bengali through it. Simple Marathi ternaries in the core screens were converted to `bi()`, so Bengali reaches them.
  - Bengali sign-in copy.
  - Bengali offline banners and camera tips.
  - Bundled Noto Sans Bengali, loaded by unicode-range. No CDN, per the offline rule.
  - `bn` accepted as an account language.
  - The assistant answers in Bengali instead of Marathi.
  - Dictation requests `bn-IN`.
- **Not done:**
  - Server-composed agronomic text is still English for Bengali users.
  - Hindi still shows English. It always did; this is now recorded.
  - Bengali voice has not been tested.
- **Verify:** switch the language to বাংলা on the sign-in page. The farmer home, scan, refusal and IPM screens render in Bengali (Playwright screenshots taken during this sprint).

### 10. No Bengal crops — OWNER + agronomist (not built, on purpose)
- **Current state:** potato and paddy are absent.
- **Fix path:** `docs/BENGAL_CROP_VALIDATION.md` records the candidate models. These are JHULSACAST for the WB plains, INDO-BLIGHTCAST and EPIBLA, each with its citation, and with what must be sourced before anything is switched on.
- **Judge impact:** say plainly that the Bengal crop packs are the pilot's first deliverable and that the validation register already exists.

## P0/P1 — the decision screen ("View management", "What should I do?")

### 11. The IPM screen was static and repeated itself — DONE
**Before** (rendered at 390 px):
- "Record a count" appeared twice.
- The monitoring rung appeared twice ("What to do now" and "What to watch for").
- "No verified chemical" appeared twice.
- A whole card said only "Not known yet".
- The IPM ladder, the point of the screen, was folded under "More detail".
- Ticks did nothing and were forgotten on reload.
- The count sheet said **"Threshold for this crop: undefined"** before the first count.

**Now:**
- **Inline count.** The count is entered in the decision area with ± steppers.
- **Live preview.** While the farmer types, the server answers where that count would land. The new endpoint is `GET /api/management/{plot}/threshold-preview`: it writes nothing, names no chemical, and uses the same arithmetic as the saved decision.
- **Threshold known before the first count.** It comes from a new `etl_reference` field in the payload.
- **Checklist.** Ticks persist for the day on the phone, with a progress bar. Each row has its own action button (Count / Scan / Inspect / Re-scan).
- **Steps are clickable.** The Assess → Act → Monitor steps jump to where each step is done.
- **"Your IPM plan".** A visible card with the rungs as tabs:
  - The rung PRAHARI points to is open.
  - A crossed threshold points to chemistry only if a verified option exists. Otherwise it points to the highest open rung.
  - The chemical rung lists what would open it, ticked when met.
- **Duplicates removed.**

**Tests:**
- Preview writes nothing and names no chemical.
- Preview equals the saved decision.
- 404 for a disease target.
- Own field only.
- Reference present before the first count.

**Home:** the "Also due today" list is now a checklist with action buttons and day ticks. A tick is a note to self and never counts as work done.

### 12. Sign-up password visibility — DONE
An eye button shows or hides the password. It is a 44 px target with `aria-pressed`, and it resets when the form mode changes.

## P1 — explainability, passport, FPO, UX (not started this sprint)

| Item | State | Recommended next step |
|---|---|---|
| Evaluation framework (precision, recall, F1, calibration, abstention, selective accuracy) | `ml/` has a training pipeline but no labelled field set | Build the evaluator against a held-out labelled set. Report nothing until a field set exists. |
| Separating weather risk / quality / features / differential / human verification / provenance on the result screen | The scan result already labels the engine ("Symptom-feature classifier v1 (not a neural network)") and shows evidence rows | Group into those six headed sections |
| Field passport | Exists (Home passport, Fields history, printable report) | Mark measured vs self-reported vs expert-confirmed on every row |
| FPO dashboard | Counts-only with small-cell suppression, consent-based | A 30-second summary strip at the top |
| Sunlight / low-end Android | Large targets on new controls; no device test | Test on a real low-end phone outdoors |

## Verification run (this sprint)

| What | Result |
|---|---|
| Backend tests | **548 passed** (532 existing + 16 new in `tests/test_summit_readiness.py`). Python 3.13, SQLite. |
| Lint | `ruff check backend/app`: clean |
| Frontend build | Clean. JS 166.6 kB gzipped (budget 200 kB). |
| Browser (Playwright, 390 px) | Decision screen: count preview, tick persistence across reload, saving a count flips the verdict, IPM plan rungs. Scan: refusal for `bad_photo.jpg`; differential in Bengali for `late_blight.jpg`. Sign-up: eye toggle, Bengali copy, grouped block list. |
| Production `/api/ready` before the change | ready, PostgreSQL ok, `demo_fallback: true`, Open-Meteo cooling down (429) |
| Production after the change | Verified on `/api/ready`: `ready: true`, PostgreSQL ok, `demo_fallback` absent, Open-Meteo still cooling down (429). Vision engine on the live service is `gemini` (general model scoring a closed candidate list), not `none`. |
| GitHub CI | Not readable from this environment |
| PostgreSQL migration test | Not run here; no migration added |
