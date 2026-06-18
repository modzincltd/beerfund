#!/usr/bin/env bash
# Put HTTPS in front of the read API so the Vercel frontend can call it.
#
# Installs Caddy and configures automatic Let's Encrypt TLS for $BEERFUND_API_HOST,
# reverse-proxying to the uvicorn API on 127.0.0.1:8000. Idempotent.
#
# Run as root ON the droplet, AFTER setup-web.sh and once beerfund-api is up:
#
#   # No domain? Use sslip.io — it resolves <ip>.sslip.io to <ip>, so Caddy can
#   # get a real cert with zero DNS setup:
#   sudo BEERFUND_API_HOST=203-0-113-7.sslip.io bash /opt/beerfund/deploy/setup-proxy.sh
#
#   # Own a domain? Point an A record (e.g. api.example.com -> droplet IP) first:
#   sudo BEERFUND_API_HOST=api.example.com bash /opt/beerfund/deploy/setup-proxy.sh
#
# NOTE: sslip.io uses dashes OR dots for the IP — 203-0-113-7.sslip.io is safest.
# Ports 80 and 443 must be reachable: if you use a DigitalOcean Cloud Firewall,
# allow 80/tcp + 443/tcp there too (this script only handles ufw).
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run as root (sudo bash $0)" >&2; exit 1; }

HOST="${BEERFUND_API_HOST:-}"
if [[ -z "$HOST" ]]; then
  echo "set BEERFUND_API_HOST, e.g.:" >&2
  echo "  sudo BEERFUND_API_HOST=<droplet-ip-with-dashes>.sslip.io bash $0" >&2
  echo "  sudo BEERFUND_API_HOST=api.yourdomain.com bash $0" >&2
  exit 1
fi

echo ">> installing Caddy (if absent)"
if ! command -v caddy >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

echo ">> writing /etc/caddy/Caddyfile for $HOST -> 127.0.0.1:8000"
cat > /etc/caddy/Caddyfile <<EOF
# Auto-HTTPS reverse proxy for the Beer Fund read API.
# CORS is handled by FastAPI (CORS_ORIGINS in /etc/beerfund/beerfund.env); Caddy
# just terminates TLS and forwards.
$HOST {
    reverse_proxy 127.0.0.1:8000
}
EOF

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo ">> ufw is active — allowing 80/443"
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
fi

echo ">> reloading Caddy"
caddy validate --config /etc/caddy/Caddyfile
systemctl enable caddy
systemctl reload caddy 2>/dev/null || systemctl restart caddy

echo
echo "Done. Caddy is serving https://$HOST -> 127.0.0.1:8000"
echo "Give it ~30s for the cert, then from your laptop:"
echo "  curl -s https://$HOST/health      # expect {\"ok\":true}"
echo
echo "Next: set NEXT_PUBLIC_API_BASE=https://$HOST in Vercel, and put your Vercel"
echo "URL in CORS_ORIGINS in /etc/beerfund/beerfund.env, then: systemctl restart beerfund-api"
