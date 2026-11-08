#!/bin/bash
# Static data for geogrid, only for the area the grids cover (runs only when the grid design changes).
set -euo pipefail
source "$(dirname "$0")/../lib.sh"
PY=$VENV/bin/python
mkdir -p "$GEOG/WPS_GEOG"
read S N W E < <("$PY" "$REPO/server/ci/bbox.py" d01)
log "static data for $S..$N N, $W..$E E"
wget -q -c -t 5 -O "$GEOG/geog.tgz" https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_high_res_mandatory.tar.gz
"$PY" "$REPO/server/geog_subset.py" "$GEOG/geog.tgz" "$GEOG/WPS_GEOG" "$S" "$N" "$W" "$E"
rm -f "$GEOG/geog.tgz"
du -sh "$GEOG/WPS_GEOG"
# 90 m terrain for the 3 km domain
read S N W E < <("$PY" "$REPO/server/ci/bbox.py" d02)
"$PY" "$REPO/server/make_terrain.py" --out "$GEOG/WPS_GEOG/topo_cop90" --cache "$GEOG/cop90_cache" \
  --lat0 "$(python3 -c "import math;print(math.floor($S)-1)")" --lat1 "$(python3 -c "import math;print(math.ceil($N)+1)")" \
  --lon0 "$(python3 -c "import math;print(math.floor($W)-1)")" --lon1 "$(python3 -c "import math;print(math.ceil($E)+1)")"
rm -rf "$GEOG/cop90_cache"
bash "$REPO/server/geogrid.sh"
rm -rf "$GEOG/WPS_GEOG"
