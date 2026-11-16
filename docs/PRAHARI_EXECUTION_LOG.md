# PRAHARI — Execution Log

Newest entries last. Each entry says what changed, why, how it was verified, and what is still open.

## 2026-11-16 — P0: production outage diagnosed

What was observed: `https://prahari-7m0e.onrender.com` has not served since 2 October 2026. Render events show repeated `server_failed` (`nonZeroExit: 3`); the application log at each start shows the PostgreSQL host `dpg-dabk64qd0e5s739ljqmg-a` cannot be resolved, then `Application startup failed. Exiting.` The workspace has no PostgreSQL instance. Root cause: the free-tier database expired 30 days after creation and was deleted. Its data is not recoverable from here. The last code deploy (`87478c8`, 12 September) succeeded and is not the cause. Full evidence: `docs/PRAHARI_AUDIT.md` section 6.

## 2026-11-16 — Replacement database created

A new Render PostgreSQL 16 instance, `prahari-db` (`dpg-dbtg8rbrjlhs73f947e0-a`, Oregon, same region as the service), was created and reached status `available`. It is on the free plan and therefore expires on 16 December 2026 unless upgraded. It accepts internal connections only (empty external IP allowlist), which is the safer default. The application creates its schema itself on first start through the migration runner; nothing was migrated by hand and no existing database was reset.

Open: the service's `DATABASE_URL` still points at the deleted host. The new database's internal connection string contains its password, and credentials are entered by the owner, not by the assistant. Once it is pasted (Render dashboard → prahari service → Environment → `DATABASE_URL` → the new database's Internal Database URL), Render redeploys and the live URL must be checked: `/api/health` should report `"database": "ok"` and `/api/ready` should return 200.

## 2026-11-16 — Degraded mode instead of exit (commit `eea7e3d`, branch `feat/evolution-reliability`)

Why: when the database disappeared, the process exited, so the static frontend disappeared too and users saw the host's error page for six weeks.

What: startup retries the bring-up three times; an `OperationalError`/`InterfaceError` is logged by type only and the process stays up. Data routes answer 503 `database_unavailable` with a bilingual message and `Retry-After`; `/api/health` stays 200 and reports `"database": "unavailable"`; `/api/ready` returns 503. The next request after `DB_RETRY_SECONDS` (30 s) retries, so the service recovers by itself. PostgreSQL gets a 10 s connect timeout. A schema error still stops the start, because retrying cannot fix it. The frontend already serves cached reads on 503, so screens a farmer has opened before keep working.

Verified: six new tests in `backend/tests/test_database_degraded.py` (start without a database, liveness, readiness, honest 503 on data routes, no connection details leaked, self-recovery when the database appears, healthy path unchanged). Full suite 502 passed; ruff clean.

## 2026-11-16 — Blueprint drift corrected (branch `feat/evolution-reliability`)

`render.yaml` now names the real hostname in `CORS_ORIGINS`/`TRUSTED_HOSTS`, declares `GEMINI_API_KEY` as a dashboard-only variable, and explains why the database must not be on the free plan. The live service is not driven by the blueprint, so this changes nothing in production by itself.

## Not pushed

Per the project rule, nothing on `feat/evolution-reliability` has been pushed to GitHub. Production restoration does not depend on these commits; it depends only on `DATABASE_URL`.

## 2026-11-16 — Production restored and verified

The owner pointed `DATABASE_URL` at the new database. Render redeployed commit `87478c8` (deploy `dep-dbtggfoae00c73dc6cjg`); the log shows all six migrations applied, 42 reference label claims inserted, "Application startup complete" and "Your service is live". Checked on the live URL: `/api/ready` returns `ready: true`, database `ok` on PostgreSQL, weather `live` (WeatherAPI + Open-Meteo), Gemini vision and assistant configured with key source `GEMINI_API_KEY`, `degraded: []`; the only soft warning is that no SMS gateway is configured. The sign-in page renders in Marathi. The database is empty: accounts from before the outage no longer exist. Demo console access is on; `ADMIN_BOOTSTRAP_*` is not set.

## 2026-11-16 — Module review against the code before building

Module A (multi-field command centre) already exists as `GET /api/plots/board` and the Fields screen, so nothing was built. Module B's SMS channel (`HttpSmsChannel`) and the S3/R2 storage adapter already exist and only need credentials, so nothing was built there either; the roadmap and audit were corrected. WhatsApp stays deferred until Meta business verification and approved templates exist.

## 2026-11-16 — Module D: outcomes after action (commit `e4c4879`)

`GET /api/followups/outcomes` counts closed follow-ups after logged actions by kind of action and target. It keeps measured outcomes (two photographs compared) apart from the farmer's own account, never sums them, and gives a share only from five measured outcomes. It never groups by product or supplier, and nothing in it reaches the chemical gate. The scoping is the same as `/api/followups`. It is shown on the printable field report and the officer overview. Verified by 9 tests and a jsdom render of the shared component.

## 2026-11-16 — Module C: producer organisations (commit `d86f999`)

Migration `007_fpo` adds `fpos`, `fpo_staff` and `fpo_members` (additive only). An administrator creates an FPO and links staff accounts with the new `fpo` role, which cannot be self-registered. Joining is the farmer's own act, with the consent time recorded and the sharing terms shown before the button, and the farmer can leave at any time. An administrator cannot join a farmer on their behalf. The FPO summary gives counts only: members, fields, crops, talukas, the latest health band per field ("not scored" is never "safe"), open and overdue follow-ups, open outbreak events in members' talukas, and outcomes after action. Any count below 3 is reported as "fewer than 3". Staff of one FPO cannot read another. The demo console gains an FPO account linked to an empty demo organisation, which nobody is joined to automatically.

Verified by 10 tests. A live jsdom render of the FPO console and the farmer's join card against a running backend caught a bug: a crop's name was overwritten by its own count label. It was fixed and a test now covers it. The full suite gives 521 passed, ruff is clean, and the build is 150.7 kB gzipped JS (budget 200 kB).

## 2026-11-16 — Front door, reliability and a visual pass (commits `27d8312`, `c08dfbd`)

Front door: the sign-in card shows the Farmer, Expert, Officer and FPO demo buttons only when the server reports `DEMO_CONSOLE_ACCESS`. The demo farmer now opens on one real field: taluka centre, tomato, sown 45 days ago, created through the normal `create_plot`. Its weather and risk are live and nothing on it is invented.

Reliability: every API call now has a deadline, 30 s for reads and 90 s for writes. A read that times out falls back to the cache. A write that times out is reported as a timeout (408) rather than as "offline", so it is never queued and sent twice. HEAD on `/` and `/api/health` now answers 200 instead of 405, so uptime monitors can see the site.

Visual pass: every main screen was rendered in Playwright at phone and desktop widths against a local build. Fixes:

- The tick boxes and dividers never drew, because four CSS tokens were undefined.
- Home listed the next best action twice. The second list now holds only what remains.
- Plurals ("1 acre", "1 more thing is").
- The profile and the officer table showed taluka IDs instead of names.
- The officer high-risk list showed a field once per bad day and kept listing recovered fields.
- Console cards touched edge to edge.

Suite: 527 passed. Build: 151.5 kB gzipped JS.

Push: this environment cannot push to GitHub (it allows clone and fetch only, and cannot type into Terminal). The owner pushes the branch from their own Mac: `git push origin feat/evolution-reliability:main`.
