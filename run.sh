#!/usr/bin/env bash
# PRAHARI — one command for a local run.
#
#   ./run.sh              build the UI if needed, migrate, serve on :8000
#   ./run.sh --demo       the above, plus seeded demo accounts and generated weather
#   ./run.sh --reseed     wipe the local database first
#   ./run.sh --test       run the test suite instead of serving
#
# The clock, the migrations and the chemical reference table are all applied on
# startup, so there is no separate seed step to forget.
set -euo pipefail
cd "$(dirname "$0")"

DEMO=0; RESEED=0; TEST=0
for arg in "$@"; do
  case "$arg" in
    --demo) DEMO=1 ;;
    --reseed) RESEED=1 ;;
    --test) TEST=1 ;;
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done

if [ "$TEST" = "1" ]; then
  cd backend
  exec python3 -m pytest tests -q
fi

mkdir -p var/uploads

if [ ! -d frontend/dist ]; then
  echo "── building the UI"
  (cd frontend && npm install --no-audit --fund=false && npm run build)
fi

[ "$RESEED" = "1" ] && rm -f var/prahari.db var/prahari.db-wal var/prahari.db-shm

export DATABASE_URL="${DATABASE_URL:-sqlite:///../var/prahari.db}"
export STORAGE_LOCAL_DIR="${STORAGE_LOCAL_DIR:-../var/uploads}"
export APP_ENV="${APP_ENV:-development}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:5173,http://127.0.0.1:8000}"
export JWT_SECRET="${JWT_SECRET:-local-development-secret-at-least-32-characters-long}"

if [ "$DEMO" = "1" ]; then
  export DEMO_MODE=true
  export AUTO_SEED_DEMO=true
  export WEATHER_PROVIDER="${WEATHER_PROVIDER:-demo}"
  echo
  echo "  DEMO MODE — weather is GENERATED, not observed."
  echo "  Accounts (password: prahari-demo-2026)"
  echo "    farmer   9000000001 … 9000000005"
  echo "    officer  officer@prahari.demo"
  echo "    expert   expert@prahari.demo"
  echo "    admin    admin@prahari.demo"
  echo
else
  export WEATHER_PROVIDER="${WEATHER_PROVIDER:-openmeteo}"
fi

echo "  PRAHARI on http://127.0.0.1:8000   ·   API docs at /docs"
cd backend
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
