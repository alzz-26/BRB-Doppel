#!/usr/bin/env bash
# Ship BRB's code to the server and restart it. Run from the repo root:
#
#   bash deploy/aws/update_brb.sh [ssh-host]
#
# The host defaults to brb-admin, an alias in ~/.ssh/config for the server's
# admin login. Only the code moves: the server keeps its own .env, ledger and
# Doppel folders.
set -euo pipefail

HOST="${1:-brb-admin}"
cd "$(dirname "$0")/../.."

echo "== Tests"
uv run --frozen pytest -q brb

echo "== Upload"
bundle="$(mktemp -d)/brb-bundle.tar.gz"
tar --force-local --exclude='__pycache__' -czf "$bundle" brb pyproject.toml uv.lock
ssh "$HOST" "mkdir -p ~/deploy"
scp -q "$bundle" "$HOST:deploy/brb-bundle.tar.gz"

echo "== Restart"
ssh -n "$HOST" 'set -e
cd /tmp
sudo tar -xzf ~/deploy/brb-bundle.tar.gz -C /opt/brb --no-same-owner
sudo chown -R brb:brb /opt/brb/brb /opt/brb/pyproject.toml /opt/brb/uv.lock
sudo -u brb -H sh -c "cd /opt/brb && /usr/local/bin/uv sync --frozen --quiet"
sudo systemctl restart brb
sleep 4
systemctl is-active brb
sudo journalctl -u brb -n 3 --no-pager -o cat'
