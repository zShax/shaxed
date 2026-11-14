#!/bin/sh
# Server-side deploy: pull main, rebuild the container, wait until it is healthy.
# Run by hand on the VPS, or over SSH by .github/workflows/deploy.yml, where it is
# the deploy key's forced command (authorized_keys), so that key can do nothing else.
#
# The whole body sits in { ... } so sh reads it all before running:
# `git pull` may rewrite this very file.
{
set -eu
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "[deploy] Aborted: the checkout on the server has uncommitted changes:" >&2
  git status --short --untracked-files=no >&2
  exit 3
fi

echo "[deploy] Pulling main..."
git checkout -q main
git pull --ff-only origin main
echo "[deploy] At $(git log -1 --format='%h %s')"

echo "[deploy] Building and restarting..."
docker compose up -d --build --wait --wait-timeout 120

docker image prune -f >/dev/null 2>&1 || true
echo "[deploy] Done: container healthy."
exit 0
}
