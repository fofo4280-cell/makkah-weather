#!/usr/bin/env python3
"""One-time climatology from the NCEP/NCAR reanalysis (1991-2020), read over OPeNDAP from NOAA PSL.

Writes <out>/clim.npz with
  chi    (365, 73, 144)  daily climatology of 200 hPa velocity potential (m^2/s), 2.5 deg, lat 90..-90
  pw     (365, ny, nx)   daily climatology of precipitable water (mm) over Arabia
  pw_lat, pw_lon
The daily means are smoothed to the annual mean plus three harmonics.

build_clim.py <out_dir> [first_year last_year]
"""
import os, sys, time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sphere  # noqa: E402

PSL = "https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis/Dailies"
PW_BOX = (5.0, 40.0, 25.0, 65.0)  # south, north, west, east


def no_leap(arr, year):
    """Drop 29 February so every year has 365 days."""
    if arr.shape[0] == 366:
        return np.delete(arr, 59, axis=0)
    return arr


def read(url, getter, tries=4):
    for k in range(tries):
        try:
            with Dataset(url) as d:
                return getter(d)
        except Exception as e:  # PSL sometimes drops a connection
            print(f"retry {k + 1} {url}: {e}", flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError(f"cannot read {url}")


def wind_year(y):
    def get(var):
        def g(d):
            lev = list(np.array(d.variables["level"][:]))
            k = lev.index(200.0)
            return np.array(d.variables[var][:, k, :, :], dtype=np.float32)
        return g
    u = read(f"{PSL}/pressure/uwnd.{y}.nc", get("uwnd"))
    v = read(f"{PSL}/pressure/vwnd.{y}.nc", get("vwnd"))
    print(f"winds {y}", flush=True)
    return no_leap(u, y), no_leap(v, y)


def pw_year(y):
    s, n, w, e = PW_BOX

    def g(d):
        lat, lon = np.array(d.variables["lat"][:]), np.array(d.variables["lon"][:])
        j = np.where((lat >= s) & (lat <= n))[0]
        i = np.where((lon >= w) & (lon <= e))[0]
        a = np.array(d.variables["pr_wtr"][:, j[0]:j[-1] + 1, i[0]:i[-1] + 1], dtype=np.float32)
        return a, lat[j[0]:j[-1] + 1], lon[i[0]:i[-1] + 1]
    a, la, lo = read(f"{PSL}/surface/pr_wtr.eatm.{y}.nc", g)
    print(f"pw {y}", flush=True)
    return no_leap(a, y), la, lo


def harmonics(daily, n=3):
    """Annual mean plus the first n harmonics along axis 0 (365 days)."""
    f = np.fft.rfft(daily, axis=0)
    f[n + 1:] = 0
    return np.fft.irfft(f, n=daily.shape[0], axis=0).astype(np.float32)


def main():
    out = sys.argv[1]
    y0, y1 = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (1991, 2020)
    os.makedirs(out, exist_ok=True)
    years = list(range(y0, y1 + 1))
    with ThreadPoolExecutor(4) as ex:
        winds = list(ex.map(wind_year, years))
        pws = list(ex.map(pw_year, years))
    u = np.mean([w[0] for w in winds], axis=0)
    v = np.mean([w[1] for w in winds], axis=0)
    lat = np.linspace(90, -90, 73)
    lon = np.arange(0, 360, 2.5)
    chi = np.stack([sphere.velocity_potential(u[d], v[d], lat, lon) for d in range(365)])
    chi = harmonics(chi)
    pw = harmonics(np.mean([p[0] for p in pws], axis=0))
    np.savez_compressed(os.path.join(out, "clim.npz"), chi=chi, pw=pw, pw_lat=pws[0][1], pw_lon=pws[0][2],
                        years=np.array([y0, y1]))
    print("climatology written", chi.shape, pw.shape)


if __name__ == "__main__":
    main()
