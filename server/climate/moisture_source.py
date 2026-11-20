#!/usr/bin/env python3
"""Where the moisture of a rain wave came from (Fahad, 15 Nov 2026: the wave of 8-15 Nov with the MJO in phase 2).

    moisture_source.py FIRST_YYYYMMDDHH LAST_YYYYMMDDHH CLIM_NPZ

From the GFS analyses every 6 hours (1 degree):
  - precipitable water at four places (Makkah, Abha, Riyadh, Dammam) and its share of the normal (NCEP 1991-2020);
  - the water-vapour transport (925-500 hPa) through four gates: the southern Red Sea (Bab el-Mandeb), the Arabian
    Sea coast of Yemen and Oman, Sudan and Eritrea west of the Red Sea, the Arabian Gulf;
  - the 500 hPa trough west of the Kingdom (lowest height along 22-32N, 20-45E, and its longitude);
  - back trajectories, 4 days, from each place at 12 UTC of each day, on the 850, 700 and 600 hPa surfaces
    (horizontal winds only: a first answer to where the air came from), with its humidity along the way.
"""
import os, sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402

LEVELS = (925, 850, 700, 600, 500)
FIELDS = ([(f"u{p}", rf":UGRD:{p} mb:") for p in LEVELS] + [(f"v{p}", rf":VGRD:{p} mb:") for p in LEVELS]
          + [(f"q{p}", rf":SPFH:{p} mb:") for p in LEVELS] + [("z500", r":HGT:500 mb:"), daily.FIELDS[2]])
LAT = np.linspace(90, -90, 181)
LON = np.arange(0, 360, 1.0)
PLACES = {"مكة": (21.4, 39.8), "أبها": (18.2, 42.5), "الرياض": (24.7, 46.7), "الدمام": (26.4, 50.1)}
GATES = {"جنوب البحر الأحمر": (12, 16, 41, 45), "ساحل بحر العرب (اليمن وعُمان)": (14, 19, 49, 57),
         "السودان وإريتريا": (14, 20, 32, 38), "الخليج العربي": (24, 28, 49, 55)}


def one(t):
    try:
        f = daily.gfs_fields(t.strftime("%Y%m%d%H"), 0, fields=FIELDS)
        sub = {k: f[k][40:91, 0:91].astype(np.float32) for k in f}       # 50N..0, 0..90E
        return t, sub
    except Exception as e:  # noqa: BLE001
        print("skip", t, repr(e)[:150], flush=True)
        return t, None


LA, LO = LAT[40:91], LON[0:91]


def at(a, lat, lon):
    """bilinear value of a (LA x LO) at a point"""
    y = (LA[0] - lat); x = lon - LO[0]
    j, i = int(np.floor(y)), int(np.floor(x))
    j = min(max(j, 0), len(LA) - 2); i = min(max(i, 0), len(LO) - 2)
    fy, fx = y - j, x - i
    return ((1 - fy) * (1 - fx) * a[j, i] + (1 - fy) * fx * a[j, i + 1] + fy * (1 - fx) * a[j + 1, i] + fy * fx * a[j + 1, i + 1])


def boxm(a, s, n, w, e):
    j = (LA >= s) & (LA <= n); i = (LO >= w) & (LO <= e)
    return float(a[np.ix_(j, i)].mean())


def main():
    t0 = datetime.strptime(sys.argv[1], "%Y%m%d%H"); t1 = datetime.strptime(sys.argv[2], "%Y%m%d%H")
    clim = dict(np.load(sys.argv[3]))
    times = []
    t = t0
    while t <= t1:
        times.append(t); t += timedelta(hours=6)
    with ProcessPoolExecutor(4) as ex:
        got = dict(ex.map(one, times))
    got = {t: v for t, v in got.items() if v is not None}
    ts = sorted(got)
    print("analyses", len(ts), ts[0], ts[-1], flush=True)
    G = 9.80665
    # the transport 925-500 hPa (kg/m/s), trapezoid in pressure
    ivt = {}
    for t in ts:
        f = got[t]
        qu = [f[f"q{p}"] * f[f"u{p}"] for p in LEVELS]; qv = [f[f"q{p}"] * f[f"v{p}"] for p in LEVELS]
        ps = np.array(LEVELS, float) * 100
        iu = sum((qu[k] + qu[k + 1]) / 2 * (ps[k] - ps[k + 1]) for k in range(len(LEVELS) - 1)) / G
        iv = sum((qv[k] + qv[k + 1]) / 2 * (ps[k] - ps[k + 1]) for k in range(len(LEVELS) - 1)) / G
        ivt[t] = (iu, iv)

    def pw_clim(t, lat, lon):
        c = clim["pw"][min(t.timetuple().tm_yday - 1, 364)]
        plat, plon = clim["pw_lat"], clim["pw_lon"]
        j = int(np.argmin(np.abs(plat - lat))); i = int(np.argmin(np.abs(plon - lon)))
        return float(c[j, i])

    print("\n== Precipitable water at 12 UTC (mm, and % of normal)")
    for t in ts:
        if t.hour != 12:
            continue
        print(f"{t:%d %b}: " + " | ".join(f"{n} {at(got[t]['pw'], la, lo):.0f} ({100*at(got[t]['pw'], la, lo)/max(pw_clim(t, la, lo),1):.0f}%)"
                                         for n, (la, lo) in PLACES.items()))
    print("\n== Vapour transport 925-500 hPa through the gates, daily mean (kg/m/s, eastward / northward, and size)")
    days = sorted({t.date() for t in ts})
    for d in days:
        tt = [t for t in ts if t.date() == d]
        cells = []
        for n, b in GATES.items():
            u = np.mean([boxm(ivt[t][0], *b) for t in tt]); v = np.mean([boxm(ivt[t][1], *b) for t in tt])
            cells.append(f"{n} {u:+.0f}/{v:+.0f} ({np.hypot(u, v):.0f})")
        print(f"{d:%d %b}: " + " | ".join(cells))
    print("\n== The 500 hPa trough west of the Kingdom at 12 UTC (lowest height along 22-32N, 20-45E; its longitude) and the PW "
          "over the Red Sea (18-24N, 37-41E)")
    for t in ts:
        if t.hour != 12:
            continue
        z = got[t]["z500"]
        j = (LA >= 22) & (LA <= 32); i = (LO >= 20) & (LO <= 45)
        prof = z[np.ix_(j, i)].mean(0)
        k = int(np.argmin(prof))
        print(f"{t:%d %b}: lowest {prof[k]:.0f} m at {LO[i][k]:.0f}E (mean of the band {prof.mean():.0f} m) | "
              f"PW Red Sea {boxm(got[t]['pw'], 18, 24, 37, 41):.0f} mm, Rub al-Khali {boxm(got[t]['pw'], 18, 22, 47, 53):.0f} mm, "
              f"Sudan {boxm(got[t]['pw'], 14, 20, 30, 36):.0f} mm")

    # back trajectories
    print("\n== Back trajectories (4 days, horizontal, hourly steps): position every 24 h, specific humidity g/kg")
    tmin = ts[0]

    def wind(t, lev, lat, lon):
        # linear in time between the analyses
        a = max(x for x in ts if x <= t); b = min((x for x in ts if x >= t), default=a)
        fa, fb = got[a], got[b]
        w = 0.0 if a == b else (t - a).total_seconds() / (b - a).total_seconds()
        u = (1 - w) * at(fa[f"u{lev}"], lat, lon) + w * at(fb[f"u{lev}"], lat, lon)
        v = (1 - w) * at(fa[f"v{lev}"], lat, lon) + w * at(fb[f"v{lev}"], lat, lon)
        q = (1 - w) * at(fa[f"q{lev}"], lat, lon) + w * at(fb[f"q{lev}"], lat, lon)
        return u, v, q

    for d in days:
        ta = datetime(d.year, d.month, d.day, 12)
        if ta not in got or ta - timedelta(hours=96) < tmin:
            continue
        print(f"-- arriving {ta:%d %b} 12 UTC")
        for n, (la0, lo0) in PLACES.items():
            for lev in (850, 700, 600):
                lat, lon, t = la0, lo0, ta
                pts = []
                for h in range(96 + 1):
                    u, v, q = wind(t, lev, lat, lon)
                    if h % 24 == 0:
                        pts.append(f"{lat:.0f}N {lon:.0f}E q{1000*q:.0f}")
                    lat -= v * 3600 / 111e3; lon -= u * 3600 / (111e3 * np.cos(np.radians(lat))); t -= timedelta(hours=1)
                    if not (0 <= lat <= 50 and 0 <= lon <= 90):
                        break
                print(f"   {n} {lev}: " + " <- ".join(pts))


if __name__ == "__main__":
    main()
