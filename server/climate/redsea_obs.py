#!/usr/bin/env python3
"""Satellite rain (PERSIANN-PDIR-Now daily, UTC days) over the Red Sea and the west of the Kingdom, kept as a coarse
grid for the «تدفق البحر الأحمر» ingredient test (19 Nov 2026). 14-30 N, 34-46 E, 0.12 deg (3x3 mean of 0.04).

    redsea_obs.py FIRST_DAY LAST_DAY OUT_NPZ
"""
import os
import sys
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs_rain  # noqa: E402


def main():
    d0, d1, out = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]), sys.argv[3]
    lat = 60 - 0.04 * (np.arange(3000) + 0.5)
    lon = 0.04 * (np.arange(9000) + 0.5)
    j = np.where((lat < 30) & (lat > 14))[0]
    i = np.where((lon > 34) & (lon < 46))[0]
    j = j[: len(j) // 3 * 3]
    i = i[: len(i) // 3 * 3]
    days, grids, mx = [], [], []
    d = d0
    while d <= d1:
        a = obs_rain.pdir_day(d)
        if a is not None:
            s = a[np.ix_(j, i)]
            g = np.nanmean(s.reshape(len(j) // 3, 3, len(i) // 3, 3), axis=(1, 3))
            m = np.nanmax(s.reshape(len(j) // 3, 3, len(i) // 3, 3), axis=(1, 3))
            days.append(d.isoformat())
            grids.append(g.astype(np.float16))
            mx.append(m.astype(np.float16))
            print(d, "ok", float(np.nanmax(g)), flush=True)
        d += timedelta(days=1)
    la = lat[j].reshape(-1, 3).mean(1)
    lo = lon[i].reshape(-1, 3).mean(1)
    np.savez_compressed(out, days=np.array(days), rain=np.array(grids), rmax=np.array(mx), lat=la, lon=lo)


if __name__ == "__main__":
    main()
