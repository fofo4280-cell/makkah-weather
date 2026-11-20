# Shared paths and settings for the Saudi WRF system. Sourced by every script.
export SWRF=${SWRF:-/opt/swrf}
export REPO=$SWRF/repo
export BUILD=$SWRF/build
export GEOG=$SWRF/geog
export WORK=$SWRF/work
export LOGS=$SWRF/logs
export STATE=$SWRF/state
export VENV=$SWRF/venv
export WEB=${WEB:-/var/www/swrf}
export WRF_USER=${WRF_USER:-wrf}

export WRF_VERSION=v4.7.1
export WPS_VERSION=v4.7.0
export JASPER_VERSION=version-2.0.33

export ARCH_TRIPLET=$(gcc -dumpmachine 2>/dev/null || echo "$(uname -m)-linux-gnu")
export NETCDF=$BUILD/netcdf
export JASPERLIB=$BUILD/jasper/lib
export JASPERINC=$BUILD/jasper/include
export WRF_DIR=$BUILD/WRF
export WPS_DIR=$BUILD/WPS
export WRFIO_NCD_LARGE_FILE_SUPPORT=1
export LD_LIBRARY_PATH=$BUILD/jasper/lib:${LD_LIBRARY_PATH:-}
export NPROC=${NPROC:-$(nproc)}
export OMP_NUM_THREADS=1
export OMPI_MCA_btl_vader_single_copy_mechanism=none
export OMPI_MCA_rmaps_base_oversubscribe=1
ulimit -s unlimited 2>/dev/null || true
