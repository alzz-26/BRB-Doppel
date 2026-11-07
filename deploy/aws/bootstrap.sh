#!/usr/bin/env bash
# Sets up one Ubuntu 24.04 server for Switch and BRB. Safe to run again.
#
#   sudo bash bootstrap.sh
#
# Expects compose.aws.yml, Caddyfile and brb.service beside it, and optionally
# brb-bundle.tar.gz (the BRB code). Secrets stay in /opt/switch/.env and are
# never printed.
set -euo pipefail

SWITCH_VERSION=0.31.0
HERE="$(cd "$(dirname "$0")" && pwd)"
PEOPLE="alisha aliva"
declare -A FOLDER=([alisha]=Alisha [aliva]=Aliva)

[ "$(id -u)" = 0 ] || { echo "Run with sudo." >&2; exit 1; }

echo "== Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 acl git tmux nodejs curl openssl >/dev/null
systemctl enable --now docker
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

echo "== Swap"
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== Public address"
TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
IP=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
DASHED=${IP//./-}
GATEWAY_HOST="gateway.$DASHED.sslip.io"
API_HOST="api.$DASHED.sslip.io"

echo "== Switch"
mkdir -p /opt/switch
cd /opt/switch
cp "$HERE/compose.aws.yml" "$HERE/Caddyfile" .
curl -fsSL -o standalone-docker-compose.yml \
  "https://raw.githubusercontent.com/sandbox-quantum/switch/switch-v$SWITCH_VERSION/deploy/local/standalone-docker-compose.yml"

if [ ! -f .env ]; then
  (
    umask 077
    cat > .env <<ENV
COMPOSE_PROJECT_NAME=switch
COMPOSE_FILE=standalone-docker-compose.yml:compose.aws.yml
COMPOSE_PROFILES=gateway
SWITCH_VERSION=$SWITCH_VERSION
SWITCH_BIND_ADDR=127.0.0.1
DB_USER=switch_app
DB_PASSWORD=$(openssl rand -hex 24)
DB_OWNER_USER=postgres
DB_OWNER_PASSWORD=$(openssl rand -hex 24)
DB_NAME=switch
AGENT_REGISTRATION_TOKEN=$(openssl rand -hex 24)
SECRET_KEYS=brb:$(openssl rand -hex 32)
CONTROLLER_TOKEN_SECRET=$(openssl rand -hex 32)
FEATURE_FLAGS_ENABLED=agent_management,agent_chats,switch_buddy,follow_the_conversation,service_connections
GATEWAY_ADMIN_EMAIL=admin@switch.local
GATEWAY_ADMIN_PASSWORD=$(openssl rand -hex 24)
GATEWAY_COOKIE_SECURE=true
TELEMETRY_ENABLED=false
ENV
  )
fi
# The address can change if the server is stopped without an Elastic IP.
sed -i '/^GATEWAY_HOST=/d;/^API_HOST=/d;/^FRONTEND_BASE_URL=/d;/^GATEWAY_PUBLIC_URL=/d' .env
cat >> .env <<ENV
GATEWAY_HOST=$GATEWAY_HOST
API_HOST=$API_HOST
FRONTEND_BASE_URL=https://$GATEWAY_HOST
GATEWAY_PUBLIC_URL=https://$GATEWAY_HOST
ENV
docker compose up -d --quiet-pull

echo "== People"
id brb >/dev/null 2>&1 || useradd --system --home-dir /opt/brb --shell /usr/sbin/nologin brb
mkdir -p /srv/doppels
chown root:root /srv/doppels
chmod 711 /srv/doppels            # People can enter, but can't list who else is here.

for person in $PEOPLE; do
  id "$person" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$person"
  chmod 700 "/home/$person"
  # No sudo on purpose: the Linux account is the wall between two people.
  install -d -m 700 -o "$person" -g "$person" "/home/$person/.ssh"
  install -m 600 -o "$person" -g "$person" /home/ubuntu/.ssh/authorized_keys "/home/$person/.ssh/authorized_keys"

  folder="/srv/doppels/${FOLDER[$person]}"
  install -d -m 700 -o "$person" -g "$person" "$folder"
  # BRB is the one other reader. It writes each persona and the lessons.
  setfacl -R -m "u:brb:rwX" -m "d:u:brb:rwX" -m "d:u:$person:rwX" "$folder"
done

echo "== BRB"
mkdir -p /opt/brb
if [ -f "$HERE/brb-bundle.tar.gz" ]; then
  tar -xzf "$HERE/brb-bundle.tar.gz" -C /opt/brb
fi
ln -sfn /srv/doppels /opt/brb/doppels
mkdir -p /opt/brb/data
chown -R brb:brb /opt/brb
chmod 750 /opt/brb
chmod 700 /opt/brb/data
[ ! -f /opt/brb/.env ] || chmod 600 /opt/brb/.env
install -m 644 "$HERE/brb.service" /etc/systemd/system/brb.service
systemctl daemon-reload
if [ -f /opt/brb/pyproject.toml ]; then
  sudo -u brb -H sh -c 'cd /opt/brb && uv sync --frozen --quiet'
fi

echo
echo "Done."
echo "Gateway URL: https://$GATEWAY_HOST"
echo "API URL:     https://$API_HOST"
