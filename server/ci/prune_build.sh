#!/bin/bash
# Shrink the compiled model before it is cached: object files and sources are not needed to run.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"
cd "$BUILD" || exit 1
find WRF WPS -type f \( -name '*.o' -o -name '*.mod' -o -name '*.f90' -o -name '*.F' -o -name '*.F90' -o -name '*.c' -o -name '*.h' -o -name '*.a' \) -delete
rm -rf WRF/.git WPS/.git WRF/doc WRF/test WRF/var WRF/chem WRF/hydro WRF/wrftladj WRF/external
du -sh WRF WPS jasper 2>/dev/null
