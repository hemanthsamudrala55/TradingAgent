#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu 22.04 / 24.04 server.  Run as root:
#   bash setup.sh your-domain.com        (or with no argument to use <ip>.sslip.io)
set -euo pipefail
REPO=https://github.com/hemanthsamudrala55/TradingAgent.git
APP=/opt/tradingagent

IP=$(curl -fsS https://api.ipify.org)
DOMAIN=${1:-${IP//./-}.sslip.io}
echo "Server IP: $IP    Address: https://$DOMAIN"

apt-get update
apt-get install -y python3 python3-venv git ufw debian-keyring debian-archive-keyring apt-transport-https curl gpg
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update && apt-get install -y caddy
fi

id trader >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin trader
[ -d "$APP/.git" ] || git clone "$REPO" "$APP"
chown -R trader:trader "$APP"
sudo -u trader python3 -m venv "$APP/.venv"
sudo -u trader "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

sed "s/DOMAIN_HERE/$DOMAIN/" "$APP/deploy/Caddyfile" > /etc/caddy/Caddyfile
cp "$APP/deploy/tradingagent.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable tradingagent
systemctl reload caddy || systemctl restart caddy

ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable

echo
echo "Almost done. Set the owner password, then start the app:"
echo "  cd $APP && sudo -u trader .venv/bin/python -m web.set_password"
echo "  systemctl start tradingagent"
echo "Then open https://$DOMAIN"
