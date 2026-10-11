#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
if [[ ! -x .local/venv/bin/python || ! -d frontend/node_modules ]]; then
  printf '%s\n' 'Dependencies missing. Run bash scripts/install.sh first.' >&2
  exit 1
fi
mkdir -p .local
export MISSION_SYNC_DB="${MISSION_SYNC_DB:-$REPO_DIR/.local/missionsync.db}"
export MISSION_SYNC_DEMO_AUTH="${MISSION_SYNC_DEMO_AUTH:-true}"
export MISSION_SYNC_API_TARGET="${MISSION_SYNC_API_TARGET:-http://127.0.0.1:${MISSION_SYNC_API_PORT:-8000}}"
.local/venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port "${MISSION_SYNC_API_PORT:-8000}" &
BACKEND_PID=$!
(
  cd frontend
  exec ./node_modules/.bin/vite --host 127.0.0.1 --port "${MISSION_SYNC_WEB_PORT:-5173}" --strictPort
) &
FRONTEND_PID=$!
cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
wait -n "$BACKEND_PID" "$FRONTEND_PID"
