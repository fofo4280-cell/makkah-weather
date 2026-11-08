#!/bin/bash
# Push the website data (status, logs, maps) to the model-data branch as a single fresh commit,
# so the branch never grows. The viewer page on the main site reads it from there.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"
cd "$WEB/data" || exit 0
for f in "$LOGS"/cycle_*.log; do [ -f "$f" ] && publish_log "$f" cycle; done
rm -rf .git
printf '*.npy\n*.tmp\n*.tmp.png\nstate.json\n' > .gitignore
git init -q -b data
git -c user.name="model bot" -c user.email="actions@users.noreply.github.com" add -A
git -c user.name="model bot" -c user.email="actions@users.noreply.github.com" commit -q -m "model data $(date -u +%Y-%m-%dT%H:%MZ)"
for i in 1 2 3; do
  git push -q -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:"${PUBLISH_BRANCH:-model-data}" && break
  sleep 10
done
rm -rf .git
