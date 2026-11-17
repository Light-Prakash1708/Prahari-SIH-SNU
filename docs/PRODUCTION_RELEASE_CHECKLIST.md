# PRAHARI — production release checklist

Release: `summit-readiness` → `main` (fast-forward). Rollback tag: `pre-summit-release` (`7ef5943`).

## Before the push (verified 17 Nov 2026, cloud workspace)

| # | Check | Result | How |
|---|---|---|---|
| 1 | Backend tests | **551 passed** (532 existing + 16 summit + 3 storage) | `cd backend && python -m pytest tests -q` (Python 3.13, SQLite) |
| 2 | Lint | `ruff check backend/app`: all checks passed | |
| 3 | Frontend build | Clean; 167.7 kB gzipped JS (budget 200 kB) | `npx vite build` |
| 4 | Production config guards | All six refused (short JWT, `DEMO_MODE`, demo weather, `CORS=*`, SQLite, pinned clock) | The CI "production guards" script, run locally |
| 5 | Migrations on PostgreSQL 16 | Fresh database: `001`–`008` applied, re-run is a no-op, 58 tables | Local PostgreSQL 16 |
| 6 | Existing-data compatibility | Data created by **the code now live (`7ef5943`)** on PostgreSQL, then read by the release code: same 8 migrations, sign-in works, field and taluka intact, earlier trap count read by the new screen, scan record kept | Production-mode run (`APP_ENV=production`, PostgreSQL) |
| 7 | Weather refusal | With no provider: `weather_available: false`, no generated series. With `WEATHER_DEMO_FALLBACK=true` set: ignored, logged as an error, `demo_fallback` absent from `/api/ready`. | Production-mode run |
| 8 | Demo routes off in production | `/api/demo/judge` 404; `/api/demo/judge/reset` 405; `/api/demo/scenario` 405; `/api/auth/demo-console` 404 when the switch is unset | Production-mode run |
| 9 | Bengal workflow | `bn` registration in a Bengal block; Hooghly GPS → Tarakeswar; Delhi GPS → `outside_coverage`; `/api/reference` lists the blocks | Production-mode run + tests |
| 10 | Bengali and English farmer screens | Decision screen, count preview, tick persistence, saving a count flips the verdict, IPM plan; scan refusal (`bad_photo.jpg`) and differential (`late_blight.jpg`) in Bengali; sign-up eye toggle; grouped block list | Playwright at 390 px |
| 11 | Object storage adapter | Private object, SigV4 presigned URL, EXIF/GPS stripped, scan upload lands in the bucket | `tests/test_storage_s3.py` (moto) |
| 12 | GitHub Actions | **Not readable from this environment**: check the run on GitHub after pushing | |

## Push (owner, from the Mac)

```bash
cd ~/Downloads/"prahari 28"
git fetch origin
git log --oneline origin/main -1          # must print 7ef5943
git log --oneline origin/main..summit-readiness   # the release commits
git tag pre-summit-release 7ef5943        # rollback point (if not already present)
git push origin pre-summit-release
git push origin summit-readiness:main     # fast-forward; no --force
```

If `origin/main` is no longer `7ef5943`, **stop**: someone pushed in between. Merge or rebase deliberately; never force.

## After Render reports "live"

A successful build is not a successful release. Check each of these on https://prahari-7m0e.onrender.com:

1. **Readiness:** `/api/ready` shows `ready: true`, `database.dialect: postgresql`, `demo_mode: false`, migrations end at `008_weather_days`, and **no** `demo_fallback` key.
2. **Existing data:** sign in with an existing account. Its fields, history and earlier counts are present.
3. **Decision screen:** "What should I do?" → pest target. "Threshold today" is shown before counting. Type a number and the preview appears. Save, and the verdict updates.
4. **Checklist:** tick a row, reload, and the tick persists. Each row button opens the right action.
5. **IPM plan:** the plan card shows; the chemical rung lists what would open it.
6. **Bengali:** switch to বাংলা. Home, Scan, the decision screen and navigation render in Bengali, and the draft note shows under the language chooser.
7. **Geography:** sign up → the block list shows West Bengal · Hooghly and Purba Bardhaman. Adding a field far from coverage with GPS is refused.
8. **Weather:** a field's risk either shows a model level (only once a history plan is set) or says "Risk forecast needs more past weather than is available". Never generated weather.
9. **Photo diagnosis:** a poor photo is refused; a clear leaf returns a differential with the engine named.
10. **Expert and officer consoles:** they open and list cases.
11. **No judge or demo data:** `/api/demo/judge` → 404, and no "Judge mode" card on the consoles screen.
12. **Staging (separately):** https://prahari-staging.onrender.com redeploys from the same commit. Judge mode → Reset works there.
13. **Logs (10 minutes):** no 5xx, no "serving GENERATED weather".

Record the result of each line in `docs/PRAHARI_EXECUTION_LOG.md`.
