# PRAHARI — Repository and Deployment Audit

Audit date: 16 November 2026. Branch audited: `main` at `87478c8` (equal to `origin/main`), then work continued on `feat/evolution-reliability`.

## 1. Architecture as it actually is

PRAHARI is a single FastAPI process that serves both the JSON API under `/api` and the built React/Vite single-page app, from one Docker image on Render. There is one origin, so there is no CORS surface in production.

The backend is layered: routers (`backend/app/routers/*.py`, 126 route handlers across 18 routers) call composers (`management.py`, `fieldboard.py`, `agenda.py`, `cropcalendar.py`, `saathi.py`, `trajectory.py`), which call services built once in `runtime.py::Runtime` (risk, diagnosis, decisions, outbreak, signals, notifications, weather, vision, storage). The database layer (`db.py`) is a thin SQLAlchemy Core wrapper that runs the same SQL on SQLite (tests, offline demo laptop) and PostgreSQL (production); schema is six ordered migrations in `backend/app/schema/` applied by a runner at startup and recorded in `schema_migrations`.

Configuration is a pydantic `Settings` object (`config.py`) with production guards that refuse SQLite, `CORS_ORIGINS=*`, demo mode, auto-seeding and generated weather when `APP_ENV=production`. Secrets are read only from environment variables; `Settings.redacted()` exposes only whether a key is configured.

The frontend is React with hand-drawn SVG charts and maps (no chart or map library), a bilingual English/Marathi helper, an offline queue with `client_ref` idempotency and a read cache that serves the last good response when the API answers 503. JS is held under a 200 kB gzipped CI budget (last build 148.66 kB).

The language model (Gemini) sits behind one seam (`llm.py`) with guards: every number in a reworded answer must already exist in the retrieved facts, no product name may be introduced, a 429/5xx puts the key into cooldown, and the rule-based answer is always available. Vision can use ONNX, an external API, Gemini scoring a closed candidate list, or nothing. A chemical is reachable only through an economic-threshold crossing and a label claim whose status is `verified`; all 42 shipped claims are `draft`, so no chemical dose is currently actionable — that is deliberate, not a bug.

## 2. Feature inventory (what exists today)

Farmer: onboarding and fields with crop cycle; field health passport and score; weather card from WeatherAPI/Open-Meteo with an explicit unavailable state; weather-driven disease risk (Hutton, TOMCAST, Gubler-Thomas, 3-10); camera scan with a photo quality gate, differential diagnosis and the right to abstain; IPM management screen (verdict, severity, trajectory, escalation, action ladder, chemical gate); today agenda and "my next best action"; follow-up re-scans; trap counts and the economic threshold; crop calendar; soil, irrigation water balance and weeds; community posts graded into signals; Nearby Hotspots surveillance; AgriDoc/Saathi assistant with sectioned answers, flashcards and voice dictation; printable field report; privacy screen.

Expert: case queue, case brief with escalation, trajectory and information missing; confirmation feeds the taluka Dirichlet prior.

Officer: overview, early signals, outbreak grading (emerging cluster / suspected / confirmed), Getis-Ord Gi* hotspots, priority queue with reasons, assignments and route planning.

Admin: user provisioning for officer/expert, chemical label-claim verification, audit trail, first-admin bootstrap from environment variables, optional demo console access behind a server-side flag.

## 3. Critical bugs

The only critical defect found is operational and is described in section 6: the production database was deleted and the service could not start. No failing test, no lint error and no broken build was found on `main`.

One flaky pre-existing test is known: `tests/test_management.py::test_the_client_is_never_handed_the_providers_own_words` asserts that the string `429` never appears in a response body, and random hexadecimal ids contain `429` in roughly 0.9% of runs. It was left unchanged (weakening it is not allowed); it passes on re-run.

## 4. Security and reliability findings

No secret is committed. `.gitignore` excludes `.env*` (except the example), databases and uploads, and `git ls-files` finds no `.env`, database or key file. The Gemini key is read server-side only and never sent to the browser.

The WeatherAPI key was written to logs by `httpx` before commit `b34c5c6` silenced that logger. It should be rotated in the WeatherAPI dashboard, because old Render logs may still hold it.

Before this audit an unreachable database made the process exit at startup, which took the static frontend down with it. Fixed in `eea7e3d` (see execution log).

PostgreSQL connections had no connect timeout, so an unreachable but resolvable host could block a worker for minutes. Fixed in the same commit (`DB_CONNECT_TIMEOUT`, default 10 s).

The Render service has no health-check path configured although the blueprint names `/api/health`. On the free plan this is harmless; on a paid plan it should be set so zero-downtime deploys wait for the app.

## 5. UI/UX problems

`frontend/src/views/` (Action, Alerts, Field, Officer, Scan, Today) is not imported anywhere and is dead code from an earlier shell. `frontend/public/brand/hero-bg.png` is 3.4 MB and is not referenced by any component; it ships in every image and is fetched by nobody. Both are left in place for the owner to delete, because deletion is not possible from this environment.

The largest screens (`Decide.jsx` 1,072 lines, `Hotspots.jsx` 733, `More.jsx` 731, `Officer.jsx` 695) are long but coherent; splitting them is a maintainability task, not a user-facing defect.

## 6. Deployment problems (P0)

Evidence, all from the Render API for service `srv-dabkd2e7bikc73fukdig` (`prahari`, Docker, free plan, region Oregon, auto-deploy from `main`):

The last deploy, `dep-daij5joae00c73des1d0` for commit `87478c8` on 12 September 2026, succeeded and is the live deploy. The code did not break production.

From 2 October 2026 onwards every instance start ends in `server_failed` with `nonZeroExit: 3`, repeating on 6, 7, 8, 16 and 17 October and through to 15 November.

The application log at each start reads `sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) could not translate host name "dpg-dabk64qd0e5s739ljqmg-a" to address: Name or service not known`, followed by `Application startup failed. Exiting.`

`list_postgres_instances` returned no PostgreSQL instance in the workspace. The host in `DATABASE_URL` therefore no longer exists. A free Render PostgreSQL instance expires 30 days after creation and is deleted; the timing (service created 1 September, first failure 2 October) matches that exactly.

Root cause: the production database was deleted by the free-tier expiry, and `DATABASE_URL` still points at it. Its data is not recoverable through any interface available to this audit.

Secondary drift between `render.yaml` and the live service: the blueprint says `plan: starter` with a 10 GB disk and a paid database, while the live service is on the free plan with no disk and the database was free; the blueprint's `CORS_ORIGINS`/`TRUSTED_HOSTS` named `prahari.onrender.com` while the live host is `prahari-7m0e.onrender.com`; the blueprint did not declare `GEMINI_API_KEY`. Corrected in the blueprint on the feature branch.

Uploads: `STORAGE_PROVIDER=local` on a free web service has no persistent disk, so uploaded photos are lost at every restart. They are not lost data in the sense of decisions (those are in the database), but evidence photos will not survive. An object store (S3/R2) is the fix when budget allows.

## 7. Missing capabilities

There was no FPO (farmer producer organisation) entity, role or aggregate view (built afterwards; see the execution log). There is no WhatsApp channel. An HTTP SMS adapter and an S3/R2 storage adapter do exist and only need credentials: the live service runs with `SMS_PROVIDER=none` and `STORAGE_PROVIDER=local`. There is no marketplace (DigiHaat) and no billing or subscription layer. There is no AgriDoc document-upload pipeline. Chemical label claims are all `draft`, so chemical recommendations remain gated off until a named person verifies them against the CIB&RC register.

## 8. Priority order

1. Restore production: point `DATABASE_URL` at the new database and verify the live URL. Move the database to a plan that does not expire.
2. Keep the service up when a dependency fails (done: degraded mode).
3. Persist uploads in object storage.
4. Verify chemical label claims (a human task, not code).
5. Alert orchestration through an official SMS/WhatsApp Business provider.
6. FPO intelligence (new role and aggregate views).
7. DigiHaat and the commercial layer, only after the core has run stably on a persistent database.

## 9. Baseline

Backend: 496 tests passed on `main` (`$HOME/pv311/bin/python -m pytest tests -q`, Python 3.11, about two minutes). Ruff clean on `backend/app`. After the reliability fix on the feature branch: 502 passed, ruff clean. Frontend: last production build 148.66 kB gzipped JS, under the 200 kB budget.
