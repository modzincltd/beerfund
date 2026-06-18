#!/usr/bin/env bash
# Push local code to the Droplet and (re)provision. Run LOCALLY from the repo root.
#
#   deploy/sync.sh root@<DROPLET_IP>
#
# rsync excludes secrets and local-only data so nothing sensitive leaves your
# machine and the server's state.json / trade log are never overwritten.
set -euo pipefail

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "usage: $0 user@host   (e.g. root@164.92.x.x)" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo ">> syncing $REPO_ROOT -> $TARGET:/opt/beerfund"

rsync -az --delete \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude '.next/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.claude/' \
  --exclude '.DS_Store' \
  --exclude 'data/cache/' \
  --exclude 'data/paper/' \
  --exclude 'results/' \
  "$REPO_ROOT/" "$TARGET:/opt/beerfund/"

echo ">> running setup.sh on the Droplet"
ssh "$TARGET" 'bash /opt/beerfund/deploy/setup.sh'

echo ">> restarting services (no-op for any not yet started)"
ssh "$TARGET" 'systemctl restart beerfund-paper beerfund-api beerfund-ingest 2>/dev/null || true'
echo "done."
echo
echo "If schema.sql or api/requirements.txt changed, also run (applies schema + deps):"
echo "  ssh $TARGET 'sudo bash /opt/beerfund/deploy/setup-web.sh'"
