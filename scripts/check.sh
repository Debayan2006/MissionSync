#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
.local/venv/bin/python -m pytest tests backend/test_engine.py -q --backend-api-coverage
npm --prefix frontend run build
mkdir -p .local
export MISSION_SYNC_DB="$REPO_DIR/.local/browser-check-$$.db"
read -r MISSION_SYNC_API_PORT MISSION_SYNC_WEB_PORT < <(.local/venv/bin/python - <<'PY'
import socket
with socket.socket() as a, socket.socket() as b:
    a.bind(('127.0.0.1',0)); b.bind(('127.0.0.1',0))
    print(a.getsockname()[1], b.getsockname()[1])
PY
)
export MISSION_SYNC_API_PORT MISSION_SYNC_WEB_PORT
export MISSION_SYNC_API_URL="http://127.0.0.1:$MISSION_SYNC_API_PORT/api/v1"
export MISSION_SYNC_WEB_URL="http://127.0.0.1:$MISSION_SYNC_WEB_PORT"
bash scripts/start.sh > .local/browser-services.log 2>&1 &
SERVICE_PID=$!
cleanup() {
  kill -TERM "$SERVICE_PID" 2>/dev/null || true
  wait "$SERVICE_PID" 2>/dev/null || true
  rm -f "$MISSION_SYNC_DB" "$MISSION_SYNC_DB-shm" "$MISSION_SYNC_DB-wal"
}
trap cleanup EXIT INT TERM
.local/venv/bin/python - <<'PY'
import os,time,httpx
api=os.environ['MISSION_SYNC_API_URL']+'/ready'
web=os.environ['MISSION_SYNC_WEB_URL']
for attempt in range(100):
    try:
        if httpx.get(api,timeout=1).status_code==200 and httpx.get(web,timeout=1).status_code==200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(.2)
else:
    raise SystemExit('Services did not become ready; see .local/browser-services.log')
PY
.local/venv/bin/python -m pytest e2e -q
