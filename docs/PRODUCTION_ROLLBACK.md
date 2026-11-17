# PRAHARI — production rollback

This release adds **no database migration**, so rolling back the code never needs a database change. Production stays at `008_weather_days` either way.

## Fastest: roll back the deploy on Render (no Git change)

1. Render dashboard → `prahari` → **Events** (or Deploys).
2. Find the deploy of `7ef5943`. The last one before this release was `dep-dbtueaek1f9s739po4g0`, after the `WEATHER_DEMO_FALLBACK=false` change.
3. Choose **Rollback to this deploy**.
4. Check `/api/ready` → `ready: true`, `demo_mode: false`, no `demo_fallback`.

**Auto-deploy after a rollback:** Render may disable auto-deploy after a manual rollback. Re-enable it only once `main` holds the code you want live.

## In Git (keeps history; no force-push)

```bash
cd ~/Downloads/"prahari 28"
git fetch origin
git checkout main && git pull --ff-only
git revert --no-edit pre-summit-release..main    # new commits that undo the release
git push origin main
```

`pre-summit-release` is the tag on `7ef5943`, created before the release. Never use `git reset --hard` on `main` or `git push --force`.

## What a rollback does not undo

- **Data written after the release stays.**
  - Counts saved through the new screen are ordinary `threshold_checks` rows, which the old code reads.
  - Accounts with language `bn` are read by the old code, which shows them English (it has no Bengali dictionary).
- **New fields in West Bengal blocks keep taluka IDs like `wb_arambagh`.**
  - The old code does not know these IDs, so those fields would show the raw ID instead of a block name.
  - Their records are kept.
  - Rolling forward again restores the names.
- **Render settings are not rolled back** (`WEATHER_DEMO_FALLBACK=false` and any storage or weather credentials). Keep `WEATHER_DEMO_FALLBACK=false` regardless.

## Staging

Staging also deploys from `main`. Rolling back production in Git rolls staging back too, and judge mode disappears from it (its routes exist only in the release code). Use the Render-dashboard rollback for production alone if staging should keep judge mode.

## Database emergencies (separate from code rollback)

**Free instance (today):**
- There is no point-in-time recovery.
- Before any risky operation, take a logical dump from a machine allowed to connect (`pg_dump`). That requires adding your IP to the database allowlist temporarily.

**After upgrading to a paid instance:**
- Render point-in-time recovery restores into a **new** instance. The window is 3 days on Hobby and 7 days on Pro.
- Point `DATABASE_URL` at the new instance only after checking it.
- Never point production at the staging database (staging uses its own SQLite file).
