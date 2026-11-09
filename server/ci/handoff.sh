#!/bin/bash
# Hand a forecast run that is split over two GitHub runners from the first to the second.
#   handoff.sh pack     after the first part: restart files, boundaries and the website folder (with the
#                       hidden accumulators the maps still need) go into $SWRF/handoff/state.tar
#   handoff.sh unpack   on the second runner: puts them back and prints the cycle (YYYYMMDDHH)
set -uo pipefail
source "$(dirname "$0")/../lib.sh"
H=$SWRF/handoff
case "${1:-}" in
  pack)
    f=$(ls "$WORK"/run/*/handoff.txt 2>/dev/null | sort | tail -1)
    [ -n "$f" ] || { echo "no handoff: the first part did not leave restart files"; exit 0; }
    RUN=$(dirname "$f"); CYC=$(basename "$RUN"); R=$(cat "$f")
    T=$(date -u -d "${CYC:0:8} ${CYC:8:2}:00 $R hours" +%Y-%m-%d_%H:%M:%S)
    ls "$RUN"/wrf/wrfrst_d0?_"$T" >/dev/null || { echo "restart files of $T missing"; exit 1; }
    rm -rf "$H"; mkdir -p "$H"
    echo "$CYC" > "$H/cycle"
    tar -cf "$H/state.tar" -C "$RUN/wrf" levels.txt wrfbdy_d01 $(cd "$RUN/wrf" && ls wrfrst_d0?_"$T") \
        -C "$WEB" data
    echo "handoff of $CYC at hour $R: $(du -sh "$H/state.tar" | cut -f1)"
    ;;
  unpack)
    [ -s "$H/cycle" ] && [ -s "$H/state.tar" ] || { echo "no handoff found" >&2; exit 1; }
    CYC=$(cat "$H/cycle"); RUN=$WORK/run/$CYC
    mkdir -p "$RUN/wrf" "$WEB"
    rm -rf "$WEB/data"
    tar -xf "$H/state.tar" -C "$RUN/wrf" --exclude 'data' --exclude 'data/*'
    tar -xf "$H/state.tar" -C "$WEB" data
    rm -f "$H/state.tar"
    echo "$CYC"
    ;;
  *) echo "usage: handoff.sh pack|unpack" >&2; exit 2 ;;
esac
