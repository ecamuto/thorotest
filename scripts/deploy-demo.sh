#!/usr/bin/env bash
# Demo-VPS deploy step, invoked by .github/workflows/deploy-demo.yml AFTER
# the checkout has been reset to the target tag/branch — so this script always
# runs at the version being deployed.
#
# VPS assumptions (one-time setup, see DEPLOY.local.md):
#   - repo checkout at /opt/thorotest-demo with a ./venv virtualenv
#   - systemd unit `thorotest-demo` (uvicorn on 127.0.0.1:8001)
#   - deploy user can `sudo systemctl restart thorotest-demo` without password
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[deploy] db backup..."
if [ -f testhub.db ]; then
  cp testhub.db "testhub.db.bak.$(date +%Y%m%d-%H%M%S)"
  # keep the 5 most recent backups
  ls -t testhub.db.bak.* 2>/dev/null | tail -n +6 | xargs -r rm --
fi

echo "[deploy] python deps..."
./venv/bin/pip install -q -r requirements.txt

echo "[deploy] frontend build..."
npm install --no-audit --no-fund --silent
npm run build

echo "[deploy] restart..."
sudo systemctl restart thorotest-demo
sleep 3

echo "[deploy] verify..."
systemctl is-active --quiet thorotest-demo || {
  journalctl -u thorotest-demo -n 40 --no-pager
  exit 1
}
# /health checks DB connectivity too (Alembic migrations ran during boot)
curl -sf --max-time 10 http://127.0.0.1:8001/health >/dev/null || {
  journalctl -u thorotest-demo -n 40 --no-pager
  exit 1
}
echo "[deploy] OK — now at $(git rev-parse --short HEAD) ($(git describe --tags --always))"
