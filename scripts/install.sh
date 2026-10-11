#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
mkdir -p .local
python3 -m venv .local/venv
export PIP_CACHE_DIR="$REPO_DIR/.local/pip-cache"
.local/venv/bin/python -m pip install --disable-pip-version-check -r requirements.lock
.local/venv/bin/python -m pip check
npm --prefix frontend ci --cache "$REPO_DIR/.local/npm-cache" --no-audit --no-fund
npm --prefix frontend run build
