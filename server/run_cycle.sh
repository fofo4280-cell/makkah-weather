#!/bin/bash
# One forecast cycle: GFS download -> WPS -> real -> WRF (images made while it runs) -> publish.
# Runs as the wrf user from cron. ANY_CYCLE=1 takes the newest GFS run of any hour.
# FORCE_CYCLE=YYYYMMDDHH runs that exact cycle.
# A run too long for one runner is split over two: SWRF_STOP_H=N makes the first stop at hour N, writing
# restart files every hour and leaving the newest good ones in $RUN/handoff.txt; RESUME=1 (with FORCE_CYCLE)
# makes the second go on from the restart files already placed in $RUN/wrf, skipping GFS, WPS and real.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/lib.sh"
# the second part must start on a 3-hourly boundary time of GFS: a restart between two of them blows up at the
# next one, so the hand-over hour is rounded down to a multiple of 3 (restart files are written every 3 hours)
if [ -n "${SWRF_STOP_H:-}" ]; then export SWRF_STOP_H=$(( SWRF_STOP_H / 3 * 3 )); fi

[ -f "$STATE/installed" ] || { log "install not finished yet"; exit 0; }
exec 9>"$STATE/cycle.lock"
if ! flock -n 9; then log "another cycle is running"; exit 0; fi

CYCLES=${CYCLES:-18}             # GFS cycles used by the scheduled run
WAIT_MIN=${WAIT_MIN:-120}        # how long to wait for GFS files
KEEP_RUNS=${KEEP_RUNS:-3}
MAXH=27   # recomputed once the cycle is known (windows depend on the cycle hour)
PY=$VENV/bin/python
NOMADS=https://nomads.ncep.noaa.gov
AWS=https://noaa-gfs-bdp-pds.s3.amazonaws.com

gfs_exists() { # $1=YYYYMMDDHH $2=fhour
  local d=${1:0:8} c=${1:8:2} f; f=$(printf '%03d' "$2")
  curl -s -f -I -m 20 "$NOMADS/pub/data/nccf/com/gfs/prod/gfs.$d/$c/atmos/gfs.t${c}z.pgrb2.0p25.f$f" >/dev/null && return 0
  curl -s -f -I -m 20 "$AWS/gfs.$d/$c/atmos/gfs.t${c}z.pgrb2.0p25.f$f" >/dev/null
}

pick_cycle() {
  if [ -n "${FORCE_CYCLE:-}" ]; then echo "$FORCE_CYCLE"; return 0; fi
  local now k c hh
  now=$(date -u +%s)
  for k in $(seq 0 8); do
    c=$(date -u -d "@$(( (now / 21600 - k) * 21600 ))" +%Y%m%d%H)
    hh=${c:8:2}
    if [ "${ANY_CYCLE:-0}" != 1 ] && [[ " $CYCLES " != *" ${hh#0} "* && " $CYCLES " != *" $hh "* ]]; then continue; fi
    if gfs_exists "$c" "$MAXH"; then echo "$c"; return 0; fi
    # scheduled run: wait for the newest wanted cycle instead of falling back to an older one
    if [ "${ANY_CYCLE:-0}" != 1 ] && [ $(( now - $(date -u -d "${c:0:8} ${c:8:2}:00" +%s) )) -lt $(( 8 * 3600 )) ]; then
      echo "WAIT:$c"; return 0
    fi
  done
  return 1
}

CYC=$(pick_cycle) || { log "no GFS cycle found"; status phase error "لم أجد بيانات جي إف إس"; exit 1; }
if [[ $CYC == WAIT:* ]]; then
  CYC=${CYC#WAIT:}
  log "waiting for GFS $CYC"
  for i in $(seq 1 $(( WAIT_MIN / 5 ))); do gfs_exists "$CYC" "$MAXH" && break; sleep 300; done
  gfs_exists "$CYC" "$MAXH" || { status phase error "تأخرت بيانات جي إف إس للدورة $CYC"; exit 1; }
fi
if [ -f "$STATE/done_$CYC" ] && [ -z "${FORCE_CYCLE:-}" ]; then log "cycle $CYC already done"; exit 0; fi
MAXH=$(python3 "$HERE/render_namelists.py" maxh "$CYC")
# stop the model in time to publish what is done when the job has a hard time limit (GitHub: 6 h)
DEADLINE=0
[ -n "${JOB_T0:-}" ] && DEADLINE=$(( JOB_T0 + ${JOB_BUDGET_MIN:-335} * 60 ))

RUN=$WORK/run/$CYC
mkdir -p "$RUN"/{gfs,wps,wrf}
LOG=$LOGS/cycle_$CYC.log
exec > >(tee -a "$LOG") 2>&1
T_START=$(date -u +%s)
log "cycle $CYC on $NPROC cores"

if [ "${RESUME:-0}" = 1 ]; then
  status plan cycle "$CYC" wrf=تشغيل_النموذج_الجزء_الثاني post=الخرائط_والنشر
else
  status plan cycle "$CYC" gfs=تنزيل_بيانات_جي_إف_إس wps=المعالجة_المسبقة real=التهيئة wrf=تشغيل_النموذج post=الخرائط_والنشر
fi
status phase cycle "الدورة قيد التشغيل"

publish() { publish_log "$LOG" cycle; }
hook() { [ -n "${PUBLISH_HOOK:-}" ] && bash "$PUBLISH_HOOK" >/dev/null 2>&1; true; }
hook
fail() {
  status phase error "$1"
  for f in "$RUN"/wrf/rsl.error.0000 "$RUN"/wps/ungrib.log "$RUN"/wps/metgrid.log "$WORK"/static/geogrid.log; do
    [ -f "$f" ] && { echo "----- $(basename "$f")"; tail -n 60 "$f"; }
  done
  publish
  exit 1
}

link_wrf_files() {
  for f in "$WRF_DIR"/run/*; do
    case $(basename "$f") in namelist.input|wrf.exe|real.exe|ndown.exe|tc.exe) ;; *) ln -sf "$f" . ;; esac
  done
  ln -sf "$WRF_DIR/main/real.exe" "$WRF_DIR/main/wrf.exe" .
}
hour_of() { # wrf file name -> forecast hour of this cycle
  local t; t=$(basename "$1" | grep -o '[0-9]\{4\}-[0-9][0-9]-[0-9][0-9]_[0-9][0-9]')
  echo $(( ($(date -u -d "${t/_/ }:00" +%s) - $(date -u -d "${CYC:0:8} ${CYC:8:2}:00" +%s)) / 3600 ))
}

if [ "${RESUME:-0}" != 1 ]; then
# ---------------------------------------------------------------- 1. GFS
get_gfs() {
  local d=${CYC:0:8} c=${CYC:8:2} f out url
  for fh in $(seq 0 3 "$MAXH"); do
    f=$(printf '%03d' "$fh"); out="$RUN/gfs/gfs.t${c}z.pgrb2.0p25.f$f"
    [ -s "$out" ] && continue
    url="$NOMADS/cgi-bin/filter_gfs_0p25.pl?dir=%2Fgfs.$d%2F$c%2Fatmos&file=gfs.t${c}z.pgrb2.0p25.f$f&all_var=on&all_lev=on&subregion=&toplat=42&leftlon=25&rightlon=66&bottomlat=4"
    if ! { curl -s -f -m 300 --retry 3 --retry-delay 20 -o "$out.part" "$url" && [ "$(head -c 4 "$out.part")" = GRIB ] && [ "$(stat -c %s "$out.part")" -gt 1000000 ]; }; then
      log "NOMADS failed for f$f, using AWS"
      curl -s -f -m 900 --retry 4 --retry-delay 30 -o "$out.part" "$AWS/gfs.$d/$c/atmos/gfs.t${c}z.pgrb2.0p25.f$f" || return 1
      [ "$(head -c 4 "$out.part")" = GRIB ] || return 1
    fi
    mv "$out.part" "$out"
    sleep 2
  done
}
# SWRF_IC=ecmwf: initial and boundary conditions from ECMWF IFS open data, written straight to WPS
# intermediate files (server/ecmwf_ic.py), instead of GFS through ungrib
get_ecmwf() {
  "$PY" -m pip install -q ecmwf-opendata eccodes || return 1
  "$PY" "$HERE/ecmwf_ic.py" "$CYC" "$MAXH" "$RUN/ecmwf"
}
if [ "${SWRF_IC:-gfs}" = ecmwf ]; then
  step gfs get_ecmwf || fail "تعذر تنزيل بيانات المركز الأوروبي"
else
  step gfs get_gfs || fail "تعذر تنزيل بيانات جي إف إس"
fi
publish

# ---------------------------------------------------------------- 2. WPS
run_wps() {
  local S=$WORK/static
  bash "$HERE/geogrid.sh" || return 1
  cd "$RUN/wps" || return 1
  rm -f FILE:* met_em.* GRIBFILE.* geo_em.*
  ln -sf "$S"/geo_em.d0*.nc .
  ln -sf "$WPS_DIR/metgrid" metgrid
  ln -sf "$WPS_DIR/ungrib/Variable_Tables/Vtable.GFS" Vtable
  "$PY" "$HERE/render_namelists.py" wps "$CYC" "$GEOG/WPS_GEOG" namelist.wps
  if [ "${SWRF_IC:-gfs}" = ecmwf ]; then
    ln -sf "$RUN"/ecmwf/FILE:* .
  else
    "$WPS_DIR/link_grib.csh" "$RUN"/gfs/gfs.t* >/dev/null
    "$WPS_DIR/ungrib.exe" > ungrib.out 2>&1
    grep -q "Successful completion of program ungrib" ungrib.log || { tail -n 40 ungrib.log; return 1; }
  fi
  "$WPS_DIR/metgrid.exe" > metgrid.out 2>&1
  grep -q "Successful completion of program metgrid" metgrid.log || { tail -n 40 metgrid.log; return 1; }
  rm -f FILE:*
}
step wps run_wps || fail "فشلت المعالجة المسبقة"
publish

# ---------------------------------------------------------------- 3. real
run_real() {
  cd "$RUN/wrf" || return 1
  find . -maxdepth 1 -type l -delete
  rm -f rsl.* wrfinput_d0* wrfbdy_d01 wrfout_* namelist.input
  link_wrf_files
  ln -sf "$RUN"/wps/met_em.d0* .
  local m nlev nsoil
  m=$(ls met_em.d01.* | head -1)
  nlev=$("$NETCDF/bin/ncdump" -h "$m" | sed -n 's/.*num_metgrid_levels = \([0-9]*\).*/\1/p' | head -1)
  nsoil=$("$NETCDF/bin/ncdump" -h "$m" | sed -n 's/.*NUM_METGRID_SOIL_LEVELS = \([0-9]*\).*/\1/p' | head -1)
  log "metgrid levels: $nlev, soil levels: ${nsoil:-4}"
  echo "$nlev ${nsoil:-4}" > levels.txt
  # real.exe always prepares the whole period, also when this runner stops the model early
  SWRF_STOP_H= "$PY" "$HERE/render_namelists.py" input "$CYC" "$nlev" "${nsoil:-4}" namelist.input
  mpirun --bind-to none -np "$NPROC" ./real.exe > real.out 2>&1
  grep -q "SUCCESS COMPLETE REAL_EM" rsl.out.0000 || { tail -n 40 rsl.error.0000; return 1; }
  mkdir -p real_logs && mv rsl.* real_logs/
}
step real run_real || fail "فشلت تهيئة النموذج"
publish; hook
fi

# ---------------------------------------------------------------- 4. WRF (+ images while it runs)
DONE_FLAG=$RUN/wrf/WRF_DONE
rm -f "$DONE_FLAG"
NP_WRF=$(( NPROC > 4 ? NPROC - 1 : NPROC ))   # one core left for making images
run_wrf() {
  cd "$RUN/wrf" || return 1
  if [ "${RESUME:-0}" = 1 ]; then
    find . -maxdepth 1 -type l -delete
    link_wrf_files
    local r0; r0=$(ls wrfrst_d01_* 2>/dev/null | sort | tail -1)
    [ -n "$r0" ] && [ -s wrfbdy_d01 ] && [ -s levels.txt ] || { log "restart files missing"; return 1; }
    export SWRF_RESTART_H; SWRF_RESTART_H=$(hour_of "$r0")
    log "going on from the restart files of hour $SWRF_RESTART_H"
    rm -f rsl.* namelist.input
  fi
  if [ -n "${SWRF_STOP_H:-}" ] || [ "${RESUME:-0}" = 1 ]; then
    read -r nlev nsoil < levels.txt
    "$PY" "$HERE/render_namelists.py" input "$CYC" "$nlev" "$nsoil" namelist.input || return 1
  fi
  # the maps are made at low priority so the model keeps the processors
  nice -n 15 "$PY" "$REPO/server/post/postprocess.py" --wrfdir "$RUN/wrf" --web "$WEB" --run "$CYC" --watch "$DONE_FLAG" \
     > "$RUN/post_watch.log" 2>&1 &
  local POSTPID=$!
  timeout 20h mpirun --bind-to none -np "$NP_WRF" ./wrf.exe > wrf.out 2>&1 &
  local WPID=$!
  local n=0 tries=0 t0; t0=$(date -u +%s)
  while kill -0 $WPID 2>/dev/null; do
    sleep 120
    if [ "$DEADLINE" -gt 0 ] && [ "$(date -u +%s)" -gt "$DEADLINE" ]; then
      log "time budget used up: stopping the model and publishing the hours that are done"
      pkill -f wrf.exe; sleep 20; break
    fi
    # a stuck model (12 Nov 2026: the west second part hung reading its restart files and wrote nothing for
    # 5 h 40 min): no new line in its log for 25 minutes -> stop it and start it again, once
    local m quiet; m=$(stat -c %Y rsl.error.0000 rsl.out.0000 2>/dev/null | sort -n | tail -1); quiet=$(( $(date -u +%s) - ${m:-$t0} ))
    if [ "$quiet" -gt 1500 ] && [ $(( $(date -u +%s) - t0 )) -gt 1500 ]; then
      if [ $tries -ge 1 ]; then
        log "the model is stuck again ($quiet s without output): stopping it"
        pkill -f wrf.exe; sleep 20; break
      fi
      tries=$((tries + 1))
      log "the model is stuck ($quiet s without output): starting it again"
      tail -n 5 rsl.error.0000 2>/dev/null
      pkill -f wrf.exe; sleep 20; wait $WPID 2>/dev/null
      mkdir -p stuck && mv -f rsl.* stuck/ 2>/dev/null
      timeout 20h mpirun --bind-to none -np "$NP_WRF" ./wrf.exe > wrf.out 2>&1 &
      WPID=$!; t0=$(date -u +%s)
      continue
    fi
    n=$((n + 1)); [ $((n % 10)) -eq 0 ] && hook
    local last hrs
    last=$(grep -h "Timing for main" rsl.out.0000 2>/dev/null | tail -1 | grep -o '[0-9]\{4\}-[0-9][0-9]-[0-9][0-9]_[0-9:]*' | head -1)
    if [ -n "$last" ]; then
      hrs=$(( ($(date -u -d "${last/_/ }" +%s) - $(date -u -d "${CYC:0:8} ${CYC:8:2}:00" +%s)) / 3600 ))
      status step wrf running "الساعة $hrs من ${MAXH}"
    fi
    publish_log rsl.error.0000 wrf_rsl 80
    # first part of a split run: keep only the two newest sets of restart files
    if [ -n "${SWRF_STOP_H:-}" ]; then
      ls wrfrst_d01_* 2>/dev/null | sort | head -n -2 | while read -r f; do rm -f wrfrst_d0?_"${f#wrfrst_d01_}"; done
    fi
  done
  wait $WPID; local rc=$?
  touch "$DONE_FLAG"
  wait $POSTPID
  grep -q "SUCCESS COMPLETE WRF" rsl.out.0000 && return 0
  log "wrf exit $rc"; tail -n 40 rsl.error.0000
  return 1
}
WRF_OK=1
step wrf run_wrf || WRF_OK=0
publish

# ---------------------------------------------------------------- 5. finish images and publish
# first part of a split run: pick the restart files the second runner goes on from
HANDOFF=""
if [ -n "${SWRF_STOP_H:-}" ]; then
  cd "$RUN/wrf"
  if [ $WRF_OK = 1 ]; then
    HANDOFF=$SWRF_STOP_H
  else   # stopped early: the newest restart time the model got past
    for f in $(ls wrfrst_d01_* 2>/dev/null | sort -r); do
      h=$(hour_of "$f")
      ls wrfout_d01_"$(date -u -d "${CYC:0:8} ${CYC:8:2}:00 $(( h + 1 )) hours" +%Y-%m-%d_%H)":* >/dev/null 2>&1 && { HANDOFF=$h; break; }
    done
  fi
  if [ -n "$HANDOFF" ] && [ "$HANDOFF" -lt "$MAXH" ]; then
    echo "$HANDOFF" > "$RUN/handoff.txt"
    log "first part done to hour $HANDOFF; the second runner goes on from there"
    WRF_OK=1
  else
    HANDOFF=""
  fi
  cd "$RUN"
fi

finish() {
  if [ -n "$HANDOFF" ]; then
    "$PY" "$REPO/server/post/postprocess.py" --wrfdir "$RUN/wrf" --web "$WEB" --run "$CYC" --partial
    return   # the accumulators (hidden .npy files) are still needed by the second part
  fi
  if [ $WRF_OK = 1 ]; then
    "$PY" "$REPO/server/post/postprocess.py" --wrfdir "$RUN/wrf" --web "$WEB" --run "$CYC" --finish
  else
    "$PY" "$REPO/server/post/postprocess.py" --wrfdir "$RUN/wrf" --web "$WEB" --run "$CYC" --failed
  fi
  # keep the newest runs only
  ls -1d "$WEB"/data/runs/[0-9]* 2>/dev/null | sort -r | tail -n +$((KEEP_RUNS + 1)) | xargs -r rm -rf
  "$PY" - "$WEB" <<'EOF'
import json, os, sys
web = sys.argv[1]; p = os.path.join(web, "data", "runs.json")
idx = json.load(open(p))
idx["runs"] = [r for r in idx["runs"] if os.path.isdir(os.path.join(web, "data", "runs", r["run"]))]
json.dump(idx, open(p, "w"), ensure_ascii=False)
EOF
  find "$WEB/data/runs" -name '.*.npy' -mmin +60 -delete 2>/dev/null
}
step post finish || log "post-processing reported a problem"

T_END=$(date -u +%s)
MINS=$(( (T_END - T_START) / 60 ))
status history "{\"cycle\":\"$CYC\",\"ok\":$WRF_OK,\"minutes\":$MINS,\"cores\":$NPROC,\"finished\":\"$(date -u +%Y-%m-%dT%H:%MZ)\"}"
if [ -n "$HANDOFF" ]; then
  status phase cycle "اكتمل الجزء الأول حتى الساعة $HANDOFF، ويكمل خادم ثانٍ بقية الساعات"
elif [ $WRF_OK = 1 ]; then
  touch "$STATE/done_$CYC"
  status phase idle "اكتملت آخر دورة في $MINS دقيقة"
  rm -rf "$RUN/gfs" "$RUN"/wrf/wrfout_* "$RUN"/wps/met_em.*
else
  fail "توقف النموذج قبل نهايته؛ نُشر ما اكتمل"
fi
# free disk: old work folders
ls -1d "$WORK"/run/[0-9]* 2>/dev/null | sort -r | tail -n +3 | xargs -r rm -rf
publish
log "cycle $CYC finished in $MINS min"
