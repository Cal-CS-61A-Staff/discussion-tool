#!/bin/bash
# Pulls the latest main, rebuilds anything that changed, applies
# migrations, restarts services. Invoked automatically by
# .github/workflows/deploy.yml (as the `deploy` user, over SSH) once CI
# passes on a push to main — this file is what actually runs on the VM,
# not just a local convenience script.
#
# Can also be run by hand as a sudo-capable admin user (not as `cs61a`
# itself — restarting a systemd unit needs root, which the app's own
# unprivileged user deliberately doesn't have): `bash
# deploy/scripts/deploy.sh` from /opt/cs61a-discussion. It delegates the
# file-ownership-sensitive steps (git pull, installing deps, building) to
# the `cs61a` user internally.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO_DIR="$(pwd)"

echo "==> Pulling latest main, installing deps, migrating, building (as cs61a)"
sudo -u cs61a bash <<EOF
set -euo pipefail
cd "$REPO_DIR"

git pull origin main

# Not a plain \`source .env\`: values like a Postgres URL's
# \`?sslmode=require&channel_binding=require\` contain a bare \`&\`, which bash
# would parse as "background this command" and silently drop the rest of
# the assignment. Reading line-by-line and exporting as literal strings
# avoids re-parsing the value as shell syntax at all.
set -a
while IFS='=' read -r key value; do
  [[ -z "\$key" || "\$key" == \\#* ]] && continue
  export "\$key=\$value"
done < .env
set +a

server/.venv/bin/pip install --quiet -r server/requirements.txt
FLASK_APP=server.app server/.venv/bin/flask db upgrade
cd client && npm install --silent && npm run build
EOF

echo "==> Restarting services"
sudo systemctl restart cs61a-discussion-web
# Pick up any change to the retention unit/timer (first deploy after this
# lands still needs a one-time `sudo systemctl enable --now
# cs61a-retention.timer`).
sudo systemctl daemon-reload
if systemctl list-unit-files cs61a-retention.timer >/dev/null 2>&1; then
  sudo systemctl restart cs61a-retention.timer || true
fi

echo "==> Waiting for the web app to come back up"
sleep 2
curl -sf http://127.0.0.1:8080/api/health && echo || {
  echo "Health check failed — check: sudo journalctl -u cs61a-discussion-web -n 50"
  exit 1
}

echo "==> Deploy complete"
