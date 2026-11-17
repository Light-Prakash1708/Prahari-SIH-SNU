# PRAHARI — production upgrade plan (`summit-readiness` → `main`)

Prepared 17 November 2026. Nothing has been pushed or deployed.

**Production:**
- Service: `prahari` (`srv-dabkd2e7bikc73fukdig`), https://prahari-7m0e.onrender.com.
- Free plan; auto-deploys from `main`.
- Live commit: `7ef5943`.
- Database: `prahari-db` (`dpg-dbtg8rbrjlhs73f947e0-a`), PostgreSQL 16, free plan, **expires 16 Dec 2026**.

**Staging (judge):**
- Service: `prahari-staging` (`srv-dbtuos88v5cc73bdrf9g`), https://prahari-staging.onrender.com.
- Free plan; also auto-deploys from `main`.
- Configured with `APP_ENV=demo`, `DEMO_MODE=true`, its own throwaway SQLite.

## Git state

- **`main` (GitHub):** `7ef5943`.
- **`summit-readiness`:** `7ef5943` plus the release commits. It **fast-forwards** onto `main`: there are no unrelated commits to merge and no conflicts.
- **Working tree:** clean apart from this release's files.
- **Rollback point:** the tag `pre-summit-release` on `7ef5943`, created locally.

## Change classification

### A. Production-ready (ships to real farmers)

| Change | Files |
|---|---|
| Redesigned "What should I do?": inline count with − / +, live threshold preview, threshold shown before the first count, day checklist, row actions, Assess→Act→Monitor jumps, "Your IPM plan", duplicates removed | `frontend/src/screens/Decide.jsx`, `saurjya.css`, `api.js`; `backend/app/management.py`, `routers/management.py`, `etl.py` |
| Home "Also due today" checklist with action buttons and progress | `Home.jsx`, `ui.jsx` (`useDayTicks`) |
| Show/hide password at sign-up and sign-in | `Auth.jsx`, `auth.css`, `Icon.jsx` |
| Bengal: 11 Hooghly / Purba Bardhaman blocks; Bengali block names; fields more than 40 km from coverage refused instead of snapped to Nashik; region-aware Gi* and spread front; block list from `/api/reference` | `data/talukas.json`, `reference.py`, `spatial.py`, `routers/plots.py`, `units.jsx`, `Auth.jsx`, `Fields.jsx` |
| Bengali core farmer screens (draft, labelled on screen as under review); `bn` account language; assistant and dictation answer in Bengali, not Marathi | `i18n/bn.js`, `ui.jsx`, `Chrome.jsx`, `schemas.py`, `llm.py`, `Saathi.jsx`, `main.jsx` (bundled Bengali font) |
| Production never serves generated weather, even if `WEATHER_DEMO_FALLBACK` is set | `weather.py` |
| R2/S3 presigned URLs forced to SigV4. Found by the new storage tests: R2 rejects the legacy V2 signature. | `storage.py` |

### B. Demo-only (in the code, inert in production)

| Change | Why it is safe to ship |
|---|---|
| `app/judge.py`; `GET /api/demo/judge`, `POST /api/demo/judge/reset` | Defined on the demo router, which is mounted only when `DEMO_MODE=true`, and `APP_ENV=production` refuses `DEMO_MODE`. Verified on a production-mode run: 404/405. |
| Judge panel on the consoles screen | Renders only when the server reports `demo_mode`. Production reports `false`. |
| Demo-note wording on the sign-in page | Chooses the staging sentence only when `demo_mode` is true. |
| `render.yaml` staging entry | The live services are not blueprint-driven, so this is documentation. |

Staging needs the same code to run judge mode, which is why these files go to `main` rather than to a separate branch.

### C. Needs production configuration (owner, Render dashboard)

| Item | Setting | Status |
|---|---|---|
| Weather history | `OPEN_METEO_API_KEY` + `WEATHER_API_URL`, or WeatherAPI Pro+ with `WEATHERAPI_HISTORY_DAYS=21` | Blocked on a paid plan. See `PRODUCTION_WEATHER_CONFIGURATION.md`. |
| Generated weather | `WEATHER_DEMO_FALLBACK=false` | **Already set** (17 Nov). Do not remove. |
| Photo storage | `STORAGE_PROVIDER=s3`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION=auto`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Waiting for R2 credentials. See below. |
| Database continuity | Upgrade `prahari-db` to a paid instance (from $6/month, `0.1c-256mb`) | **Before 16 Dec 2026** |
| Demo console on production | `DEMO_CONSOLE_ACCESS` is `true` today | Owner decision. Recommended `false` now that staging exists. |

### D. Database migration / backfill

**None.** The release adds no migration (production stays at `008_weather_days`) and needs no backfill.

**`talukas.json`:**
- It is reference data read at start-up, not a table.
- Existing fields keep the taluka stored on their row.
- The 40 km rule applies only to new fields.

### E. Waits for agronomic validation (not in this release)

- Potato and paddy crop packs: stages, models (JHULSACAST-WB, INDO-BLIGHTCAST, EPIBLA), thresholds, label claims. See `BENGAL_CROP_VALIDATION.md`.
- Native-speaker review of `bn.js`, and Bengali for server-written advice.
- Farm-household counts for the Bengal blocks. Until then they are excluded from Gi*.

## Behaviour changes a real user can notice

1. **New fields outside coverage.** A new field with GPS more than 40 km from every covered taluka or block is refused with `outside_coverage`. Before, it was silently placed in the nearest Nashik taluka and given that taluka's surveillance and prior. Existing fields are untouched.
2. **Ticks are local.** Checklist ticks stay on the phone for the day only. They never reach the server.
3. **The new count box saves a real count.** A count entered in it is saved exactly like the old count sheet, with the same API and the same offline queue.

## Storage (R2) — prepared, not switched

**Adapter (`storage.py`):**
- Stores objects privately (no public grant).
- Serves 15-minute presigned SigV4 GETs.
- Every upload route re-encodes through Pillow first, which strips EXIF, including GPS.
- Verified against an S3 emulator: 3 tests, including a full scan upload landing in the bucket.

**Existing photos:**
- Production has had no disk, so photos stored before a switch were already lost at the last restart.
- Their rows remain, and the image links will not resolve. Nothing needs migrating and nothing is deleted.

**To switch:**
1. Create an R2 bucket (private) and an API token scoped to it.
2. Set the six variables above.
3. Redeploy.
4. Check `/api/ready` → `checks.storage.ok: true`.
5. Upload a scan, restart the service, and confirm the image still opens.

## Database

- **Plan:** upgrade to a paid instance before 16 Dec 2026. The upgrade keeps the same database, so the URL and data are preserved.
- **Backups:** Render gives point-in-time recovery to paid instances only. The window is 3 days on the Hobby workspace and 7 days on Pro. Free instances have **no** recovery.
- **First action after upgrading:** Dashboard → Recovery → Create export (a logical backup, kept 7 days).
- **External checks:** the database refuses external connections (empty allowlist), so its contents could not be inspected from here. That is the safer setting, so it was left alone.
