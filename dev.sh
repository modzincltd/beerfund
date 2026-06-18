#!/usr/bin/env bash
# One command to run the dashboard locally: the FastAPI read API and the Next.js
# dashboard, together. Ctrl-C stops both. First run creates the venv and installs
# deps. Mirrors what App Platform serves (api + web); the paper/audit workers are
# optional locally — run them by hand if you want live data:
#   .venv/bin/python paper_trader.py        # needs HELIUS_API_KEY (+ DATABASE_URL)
set -euo pipefail
cd "$(dirname "$0")"

# Pick a Python >= 3.10 (the API uses 3.10+ syntax).
PY=""
for c in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 \
     && "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[[ -n "$PY" ]] || { echo "need Python 3.10+ (e.g. brew install python@3.11)" >&2; exit 1; }

# 1. venv + API deps (one-time)
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo ">> creating .venv ($("$PY" --version 2>&1)) + installing API deps"
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r api/requirements.txt
fi

# 2. web deps (one-time)
if [[ ! -d web/node_modules ]]; then
  echo ">> installing web deps"; (cd web && npm install)
fi

# 3. local frontend env — talk straight to the API (same-origin /api is prod-only)
[[ -f web/.env.local ]] || echo 'NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000' > web/.env.local

# 4. run both; one Ctrl-C stops both
pids=()
cleanup() { trap - EXIT INT TERM; echo; echo ">> stopping"; kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo ">> API        http://127.0.0.1:8000"
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 & pids+=($!)
echo ">> dashboard  http://localhost:3000"
( cd web && npm run dev ) & pids+=($!)

echo ">> both up — Ctrl-C to stop"
wait
