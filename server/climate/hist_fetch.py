#!/usr/bin/env python3
"""The reanalysis history for the full-method test (Fahad, 15 Nov 2026): NCEP/NCAR reanalysis 1 daily means,
2.5 degree, read over OPeNDAP from NOAA PSL, one calendar year at a time.

    hist_fetch.py FIRST_YEAR LAST_YEAR OUT.npz

Saved (days in calendar order, all months, so the wave filters see a continuous series):
  days   ISO dates
  chi    (days, 73, 144) 200 hPa velocity potential from the 200 hPa wind (m^2/s), lat 90..-90
  z850   (days, 33, 144) 850 hPa height, 40N..40S (the stand-in for the 800 hPa height of the MJO component)
  z500   (days, 17, 144) 500 hPa height, 50N..10N (the troughs: zonal waves 4-8)
"""
import os, sys, time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sphere  # noqa: E402

BASES = ("https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis/Dailies",
         "https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis.dailyavgs")
LAT = np.linspace(90, -90, 73)
LON = np.arange(0, 360, 2.5)


def read(path, var, level, j0, j1):
    """var at level (hPa) on latitude rows j0..j1 (of 90..-90), every day of the file"""
    import netCDF4
    err = None
    for k in range(6):
        for base in BASES:
            time.sleep(10)        # the PSL server answers too many requests with 429
            try:
                with netCDF4.Dataset(f"{base}/{path}") as nc:
                    lev = list(np.asarray(nc["level"][:], float)).index(float(level))
                    a = nc[var][:, lev, j0:j1 + 1, :]
                    t = nc["time"]
                    days = netCDF4.num2date(t[:], t.units, getattr(t, "calendar", "standard"))
                    return [f"{x.year:04d}-{x.month:02d}-{x.day:02d}" for x in days], np.ma.filled(a.astype(np.float32), np.nan)
            except Exception as e:  # noqa: BLE001
                err = e
        time.sleep(60 * (k + 1))
    raise RuntimeError(f"cannot read {path}: {err!r}"[:300])


def main():
    y0, y1, outp = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    days, chi, z850, z500 = [], [], [], []
    for y in range(y0, y1 + 1):
        d, u = read(f"pressure/uwnd.{y}.nc", "uwnd", 200, 0, 72)
        _, v = read(f"pressure/vwnd.{y}.nc", "vwnd", 200, 0, 72)
        _, h8 = read(f"pressure/hgt.{y}.nc", "hgt", 850, 20, 52)       # 40N..40S
        _, h5 = read(f"pressure/hgt.{y}.nc", "hgt", 500, 16, 32)       # 50N..10N
        n = min(len(d), len(u), len(v), len(h8), len(h5))
        for k in range(n):
            chi.append(sphere.velocity_potential(np.nan_to_num(u[k]), np.nan_to_num(v[k]), LAT, LON).astype(np.float32))
        days += d[:n]; z850.append(h8[:n]); z500.append(h5[:n])
        print("year", y, "days", n, d[0], d[n - 1], "chi range", float(np.min(chi[-1])), float(np.max(chi[-1])), flush=True)
    np.savez_compressed(outp, days=np.array(days), chi=np.stack(chi), z850=np.concatenate(z850), z500=np.concatenate(z500))
    print("saved", outp, len(days), flush=True)


if __name__ == "__main__":
    main()
