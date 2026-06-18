#!/usr/bin/env bash
# Provision the web/analysis layer ON TOP OF the existing paper-daemon setup.
# Run AFTER deploy/setup.sh. Idempotent; safe to re-run after a code push.
#
#   sudo bash /opt/beerfund/deploy/setup-web.sh
#
# This adds: a Python venv (psycopg/fastapi/anthropic), Postgres (local), and
# the ingest + api + audit systemd units/timer. The paper daemon and its
# stdlib-only runtime are left completely untouched.
set -euo pipefail

APP_USER=beerfund
APP_DIR=/opt/beerfund
ENV_FILE=/etc/beerfund/beerfund.env

[[ $EUID -eq 0 ]] || { echo "run as root (sudo bash $0)" >&2; exit 1; }

echo ">> installing python venv tooling"
apt-get update -y
apt-get install -y python3-venv
# Postgres is hosted on Supabase — nothing to install or run on this box.

echo ">> creating venv at $APP_DIR/.venv (web deps only)"
if [[ ! -d "$APP_DIR/.venv" ]]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/api/requirements.txt"

echo ">> applying schema.sql to Supabase (reads DATABASE_URL from $ENV_FILE)"
if ! grep -q '^DATABASE_URL=' "$ENV_FILE" 2>/dev/null; then
  echo "   !! DATABASE_URL not set in $ENV_FILE — add your Supabase string first, then re-run." >&2
  exit 1
fi
# Pull DATABASE_URL out of the env file and apply the schema with it.
DATABASE_URL="$(grep '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)" \
  "$APP_DIR/.venv/bin/python" -m beerfund.db

echo ">> data/cache must be writable by $APP_USER (audit caches Helius there)"
mkdir -p "$APP_DIR/data/cache"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/data"

echo ">> installing systemd units (ingest, api, audit timer)"
for unit in beerfund-ingest.service beerfund-api.service \
            beerfund-audit.service beerfund-audit.timer; do
  install -m 644 "$APP_DIR/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable beerfund-ingest beerfund-api beerfund-audit.timer

echo
echo "Done. Make sure $ENV_FILE has DATABASE_URL + (optional) ANTHROPIC_API_KEY + CORS_ORIGINS, then:"
echo "  sudo systemctl start beerfund-ingest beerfund-api"
echo "  sudo systemctl start beerfund-audit          # one immediate sweep"
echo "  systemctl list-timers beerfund-audit.timer   # confirm the daily sweep"
echo "  curl -s localhost:8000/summary | head        # API up?"
