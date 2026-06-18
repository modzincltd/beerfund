#!/usr/bin/env bash
# Provision a Droplet to run the Beer Fund paper daemon.
# Idempotent: safe to re-run after pushing new code.
#
# Run ON the Droplet as root (cloud-init does this for you automatically):
#   sudo bash /opt/beerfund/deploy/setup.sh
#
# It does NOT start the service until you've filled in the real Helius key.
set -euo pipefail

APP_USER=beerfund
APP_DIR=/opt/beerfund
ENV_DIR=/etc/beerfund
ENV_FILE="$ENV_DIR/beerfund.env"
SERVICE=beerfund-paper

if [[ $EUID -ne 0 ]]; then
  echo "run as root (sudo bash $0)" >&2
  exit 1
fi

echo ">> ensuring python3 is present"
if ! command -v python3 >/dev/null; then
  apt-get update -y
  apt-get install -y python3
fi
# Project is stdlib-only by design — no pip, no venv needed.

echo ">> creating system user '$APP_USER'"
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

echo ">> preparing $APP_DIR"
mkdir -p "$APP_DIR/data/paper" "$APP_DIR/results"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo ">> installing env file at $ENV_FILE (if absent)"
mkdir -p "$ENV_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  install -m 640 -o root -g "$APP_USER" \
    "$APP_DIR/deploy/beerfund.env.example" "$ENV_FILE"
  echo "   -> EDIT $ENV_FILE and set HELIUS_API_KEY + WALLETS"
fi

echo ">> installing systemd unit"
install -m 644 "$APP_DIR/deploy/$SERVICE.service" \
  "/etc/systemd/system/$SERVICE.service"
systemctl daemon-reload
systemctl enable "$SERVICE"

echo
echo "Done. Next:"
echo "  1. sudo nano $ENV_FILE         # add your real Helius key"
echo "  2. sudo systemctl start $SERVICE"
echo "  3. journalctl -u $SERVICE -f   # watch it run"
