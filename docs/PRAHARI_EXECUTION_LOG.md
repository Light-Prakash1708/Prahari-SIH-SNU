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
