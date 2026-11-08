#!/bin/bash
# Hourly (root): pull updates from the repository, refresh the website files, run one-off tasks.
# A one-off task runs when server/task/ID changes; its output goes to the website logs.
set -uo pipefail
source /opt/swrf/repo/server/lib.sh
BRANCH=${BRANCH:-saudi-wrf}

git config --global --add safe.directory "$REPO" 2>/dev/null
git -C "$REPO" fetch -q origin "$BRANCH" && git -C "$REPO" reset -q --hard "origin/$BRANCH"
chmod +x "$REPO"/server/*.sh 2>/dev/null
sync_site
chown -R "$WRF_USER:$WRF_USER" "$REPO" "$WEB/data" 2>/dev/null

# finish an interrupted install
# (only after the repository changed since the last attempt, so a broken step is not rebuilt every hour)
if [ ! -f "$STATE/installed" ] && ! pgrep -f "server/install.sh" >/dev/null && \
   [ "$(git -C "$REPO" rev-parse HEAD)" != "$(cat "$STATE/install_attempt" 2>/dev/null)" ]; then
  bash "$REPO/server/install.sh" >> "$LOGS/install_retry.log" 2>&1 &
  exit 0
fi

if [ -f "$REPO/server/task/ID" ]; then
  ID=$(cat "$REPO/server/task/ID")
  if [ "$ID" != "$(cat "$STATE/task_done" 2>/dev/null)" ]; then
    echo "$ID" > "$STATE/task_done"
    {
      echo "task $ID started $(date -u)"
      bash "$REPO/server/task/run.sh"
      echo "task $ID ended rc=$? $(date -u)"
    } > "$LOGS/task.log" 2>&1
    publish_log "$LOGS/task.log" task 400
  fi
fi

# system snapshot for remote checks
{
  echo "time: $(date -u)"; uptime; echo; free -h; echo; df -h / | tail -1; echo
  echo "repo: $(git -C "$REPO" log -1 --format='%h %s')"
  echo "cron:"; cat /etc/cron.d/swrf 2>/dev/null
  echo; echo "processes:"; pgrep -af "wrf.exe|real.exe|metgrid|ungrib|geogrid|postprocess|install.sh" | head
} > "$LOGS/system.txt" 2>&1
publish_log "$LOGS/system.txt" system
publish_log "$LOGS/cron.log" cron 200
