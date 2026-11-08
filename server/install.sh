#!/bin/bash
# Installs everything the Saudi WRF system needs on a fresh Ubuntu 24.04 server.
# Safe to run again: finished stages are skipped (markers in $STATE).
# Runs as root. Set SWRF_TEST=1 to skip system changes (firewall, web server, swap, cron).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/lib.sh"
mkdir -p "$BUILD" "$GEOG" "$WORK" "$LOGS" "$STATE" "$WEB/data/logs"
LOG=$LOGS/install.log
exec > >(tee -a "$LOG") 2>&1
TEST=${SWRF_TEST:-0}

done_mark() { touch "$STATE/install_$1.done"; }
is_done()   { [ -f "$STATE/install_$1.done" ]; }

# ---------------------------------------------------------------- base system
stage_base() {
  is_done base && return 0
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q || return 1
  apt-get install -y -q build-essential gfortran m4 csh tcsh perl make cmake git curl wget rsync file time bc \
    libnetcdf-dev libnetcdff-dev netcdf-bin libhdf5-dev libopenmpi-dev openmpi-bin \
    libpng-dev zlib1g-dev python3 python3-venv python3-pip ca-certificates || return 1
  if [ "$TEST" != 1 ]; then
    apt-get install -y -q caddy ufw cron || return 1
    id "$WRF_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$WRF_USER"
    if [ ! -f /swapfile ]; then
      fallocate -l 8G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && \
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
  fi
  done_mark base
}

# ---------------------------------------------------------------- web server
stage_web() {
  [ "$TEST" = 1 ] && return 0
  local ip host
  ip=$(curl -s -m 5 http://169.254.169.254/hetzner/v1/metadata/public-ipv4 || true)
  [ -z "$ip" ] && ip=$(curl -s -m 10 https://api.ipify.org || true)
  host="${ip//./-}.sslip.io"
  echo "$ip" > "$STATE/public_ip"
  echo "https://$host" > "$STATE/url"
  cat > /etc/caddy/Caddyfile <<EOF
(site) {
	root * $WEB
	encode gzip
	file_server
	@data path /data/*
	header @data Cache-Control "no-cache"
	header X-Content-Type-Options nosniff
}
$host {
	import site
}
http:// {
	import site
}
EOF
  sync_site
  chown -R "$WRF_USER:$WRF_USER" "$WEB/data"
  systemctl enable caddy >/dev/null 2>&1
  systemctl restart caddy
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
  printf '{"url":"https://%s","ip":"%s"}\n' "$host" "$ip" > "$WEB/data/site.json"
  chmod 644 "$WEB/data/site.json"
  return 0
}

# ---------------------------------------------------------------- libraries
stage_jasper() {
  is_done jasper && return 0
  cd "$BUILD" || return 1
  rm -rf jasper-src jasper-build
  git clone -q --depth 1 --branch "$JASPER_VERSION" https://github.com/jasper-software/jasper jasper-src || return 1
  cmake -S jasper-src -B jasper-build -DCMAKE_INSTALL_PREFIX="$BUILD/jasper" -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_BUILD_TYPE=Release -DJAS_ENABLE_DOC=OFF -DJAS_ENABLE_PROGRAMS=OFF -DJAS_ENABLE_OPENGL=OFF \
    -DJAS_ENABLE_LIBJPEG=OFF -DJAS_ENABLE_SHARED=ON >/dev/null || return 1
  cmake --build jasper-build -j "$NPROC" >/dev/null || return 1
  cmake --install jasper-build >/dev/null || return 1
  ls "$BUILD/jasper/lib"/libjasper* >/dev/null || return 1
  rm -rf jasper-src jasper-build
  done_mark jasper
}

# Ubuntu splits netCDF C and Fortran; WRF wants one folder holding both.
stage_netcdf() {
  rm -rf "$NETCDF"; mkdir -p "$NETCDF/lib" "$NETCDF/bin"
  ln -s /usr/include "$NETCDF/include"
  for f in /usr/lib/$ARCH_TRIPLET/libnetcdf* /usr/lib/$ARCH_TRIPLET/libhdf5*; do
    [ -e "$f" ] && ln -sf "$f" "$NETCDF/lib/"
  done
  for b in nc-config nf-config ncdump ncgen; do
    command -v $b >/dev/null && ln -sf "$(command -v $b)" "$NETCDF/bin/$b"
  done
  [ -e "$NETCDF/lib/libnetcdff.so" ] && [ -e /usr/include/netcdf.mod ]
}

# ---------------------------------------------------------------- WRF
stage_wrf() {
  is_done wrf && return 0
  cd "$BUILD" || return 1
  if [ ! -d WRF/.git ]; then
    rm -rf WRF
    git clone -q --depth 1 --branch "$WRF_VERSION" --recurse-submodules --shallow-submodules \
      https://github.com/wrf-model/WRF WRF || return 1
  fi
  cd WRF || return 1
  ./clean -a >/dev/null 2>&1
  # with no input the menu script loops forever, so read only the first screen of it
  timeout 60 ./configure < /dev/null 2>&1 | head -c 100000 > configure.menu || true
  local opt
  opt=$(python3 "$HERE/pick_option.py" wrf configure.menu) || { cat configure.menu; return 1; }
  log "WRF configure option: $opt"
  printf '%s\n1\n' "$opt" | ./configure > configure.out 2>&1
  [ -f configure.wrf ] || { cat configure.out; return 1; }
  log "compiling WRF (takes a while)…"
  ./compile -j "$NPROC" em_real > compile.log 2>&1
  if [ ! -x main/wrf.exe ] || [ ! -x main/real.exe ]; then
    grep -n -i -E " error|Error:" compile.log | head -40
    return 1
  fi
  done_mark wrf
}

# ---------------------------------------------------------------- WPS
stage_wps() {
  is_done wps && return 0
  cd "$BUILD" || return 1
  if [ ! -d WPS/.git ]; then
    rm -rf WPS
    git clone -q --depth 1 --branch "$WPS_VERSION" https://github.com/wrf-model/WPS WPS || return 1
  fi
  cd WPS || return 1
  ./clean -a >/dev/null 2>&1
  # WPS lists no ARM entry; the generic gfortran one works there too.
  grep -q "Linux x86_64 aarch64, gfortran" arch/configure.defaults || \
    sed -i 's/^#ARCH    Linux x86_64, gfortran /#ARCH    Linux x86_64 aarch64, gfortran /' arch/configure.defaults
  timeout 60 ./configure < /dev/null 2>&1 | head -c 100000 > configure.menu || true
  local opt
  opt=$(python3 "$HERE/pick_option.py" wps configure.menu) || { cat configure.menu; return 1; }
  log "WPS configure option: $opt"
  printf '%s\n' "$opt" | ./configure > configure.out 2>&1
  [ -f configure.wps ] || { cat configure.out; return 1; }
  ./compile > compile.log 2>&1
  for x in geogrid metgrid ungrib; do
    [ -x $x.exe ] || [ -x $x/src/$x.exe ] || { grep -n -i -E "error" compile.log | head -40; return 1; }
  done
  # add the Copernicus 90 m terrain as an optional source for the inner domains
  python3 "$HERE/patch_geogrid_tbl.py" geogrid/GEOGRID.TBL.ARW || return 1
  done_mark wps
}

# ---------------------------------------------------------------- Python
stage_python() {
  is_done python && return 0
  python3 -m venv "$VENV" || return 1
  "$VENV/bin/pip" install -q --upgrade pip || return 1
  "$VENV/bin/pip" install -q numpy scipy netCDF4 pillow rasterio pyproj || return 1
  "$VENV/bin/python" -c "import numpy, scipy, netCDF4, PIL, rasterio, pyproj" || return 1
  done_mark python
}

# ---------------------------------------------------------------- static data
stage_geog() {
  is_done geog && return 0
  cd "$GEOG" || return 1
  local url=https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_high_res_mandatory.tar.gz
  wget -q -c -t 5 "$url" -O geog.tar.gz || return 1
  tar -xzf geog.tar.gz || return 1
  rm -f geog.tar.gz
  [ -d WPS_GEOG/topo_gmted2010_30s ] || return 1
  done_mark geog
}

stage_terrain() {
  is_done terrain && return 0
  "$VENV/bin/python" "$HERE/make_terrain.py" --out "$GEOG/WPS_GEOG/topo_cop90" \
    --lat0 17 --lat1 26 --lon0 37 --lon1 45 --cache "$GEOG/cop90_cache" || return 1
  rm -rf "$GEOG/cop90_cache"
  done_mark terrain
}

# ---------------------------------------------------------------- schedule
stage_cron() {
  [ "$TEST" = 1 ] && return 0
  chown -R "$WRF_USER:$WRF_USER" "$SWRF" "$WEB/data"
  chmod +x "$REPO"/server/*.sh
  cat > /etc/cron.d/swrf <<EOF
# Saudi WRF: daily forecast from the 18 UTC GFS, and an hourly check for updates from the repository.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
15 22 * * * $WRF_USER $REPO/server/run_cycle.sh >> $LOGS/cron.log 2>&1
7 * * * *   root $REPO/server/maint.sh >> $LOGS/maint.log 2>&1
EOF
  chmod 644 /etc/cron.d/swrf
  systemctl restart cron
}

# ---------------------------------------------------------------- main
status plan install "$(date -u +%Y%m%d)" \
  base=تجهيز_النظام web=تشغيل_الموقع cron=الجدولة_والصيانة jasper=مكتبة_جاسبر netcdf=مكتبات_نت_سي_دي_إف \
  wrf=بناء_النموذج wps=بناء_أدوات_المعالجة python=أدوات_الرسم geog=بيانات_التضاريس_والغطاء \
  terrain=تضاريس_دقيقة_للغربية
status phase install "جارٍ تثبيت النظام"
publish_log "$LOG" install

failed=""
git -C "$REPO" rev-parse HEAD > "$STATE/install_attempt" 2>/dev/null
for s in base web cron jasper netcdf wrf wps python geog terrain; do
  if ! step $s stage_$s; then failed=$s; break; fi
  publish_log "$LOG" install
done
publish_log "$LOG" install

if [ -n "$failed" ]; then
  [ -f "$BUILD/WRF/compile.log" ] && publish_log "$BUILD/WRF/compile.log" wrf_compile 300
  [ -f "$BUILD/WPS/compile.log" ] && publish_log "$BUILD/WPS/compile.log" wps_compile 300
  status phase error "توقف التثبيت عند خطوة: $failed"
  exit 1
fi

touch "$STATE/installed"
status phase idle "اكتمل التثبيت"
if [ "$TEST" != 1 ]; then
  chown -R "$WRF_USER:$WRF_USER" "$SWRF" "$WEB/data"
  # first forecast right away, from the newest GFS cycle available
  systemd-run --unit=swrf-first --uid="$WRF_USER" --setenv=ANY_CYCLE=1 "$REPO/server/run_cycle.sh" || true
fi
log "install finished"
