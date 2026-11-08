# Helper functions shared by the install and cycle scripts.
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

STATUS_PY="$(dirname "${BASH_SOURCE[0]}")/status.py"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

status() { python3 "$STATUS_PY" "$@" || true; }

# Copy the tail of a log file to the website so it can be read remotely.
publish_log() {
  local src=$1 name=$2 lines=${3:-400}
  mkdir -p "$WEB/data/logs"
  if [ -f "$src" ]; then
    tail -n "$lines" "$src" > "$WEB/data/logs/$name.txt.tmp" 2>/dev/null && \
      mv "$WEB/data/logs/$name.txt.tmp" "$WEB/data/logs/$name.txt"
    chmod 644 "$WEB/data/logs/$name.txt" 2>/dev/null || true
  fi
}

# Run a named step: marks it running/done/error on the status page.
# usage: step <id> <command...>
step() {
  local id=$1; shift
  status step "$id" running
  log "=== step $id: start"
  if "$@"; then
    status step "$id" done
    log "=== step $id: done"
    return 0
  else
    local rc=$?
    status step "$id" error "exit $rc"
    log "=== step $id: FAILED ($rc)"
    return $rc
  fi
}

# Copy the website files from the repository into the web root.
sync_site() {
  mkdir -p "$WEB/data"
  rsync -a --delete --exclude data/ "$REPO/site/" "$WEB/"
  chmod -R a+rX "$WEB" 2>/dev/null || true
}
