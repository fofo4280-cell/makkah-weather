#!/bin/bash
# Run geogrid once for the grid design in domains.json; output goes to $WORK/static (reused every cycle).
set -uo pipefail
source "$(dirname "$0")/lib.sh"
PY=$VENV/bin/python
GH=$("$PY" "$REPO/server/render_namelists.py" geohash)
S=$WORK/static
if [ -f "$S/geo_em.d01.nc" ] && [ "$(cat "$S/geohash" 2>/dev/null)" = "$GH" ]; then exit 0; fi
log "running geogrid (grid design $GH)"
rm -rf "$S"; mkdir -p "$S"; cd "$S" || exit 1
ln -sf "$WPS_DIR/geogrid" geogrid
"$PY" "$REPO/server/render_namelists.py" wps 2000010100 "$GEOG/WPS_GEOG" namelist.wps
"$WPS_DIR/geogrid.exe" > geogrid.out 2>&1
if ! grep -q "Successful completion of program geogrid" geogrid.log; then tail -n 40 geogrid.log; exit 1; fi
echo "$GH" > geohash
rm -f geogrid
