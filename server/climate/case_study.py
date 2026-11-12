#!/usr/bin/env python3
"""A case study of an upper low over Arabia: its track, depth, vorticity lobes, blocking ridges, moisture and
low-level winds, from GFS analyses and the newest forecast, to see whether a rain round is a rebound of the same
low and by which mechanism.

    case_study.py OUT_DIR FIRST_ANALYSIS(YYYYMMDDHH) LAST_ANALYSIS FORECAST_CYCLE MAX_FH

Writes OUT_DIR/track.json (one row per time) and OUT_DIR/map_<time>.png (four panels).
"""
import json, os, sys
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402

F = [("z500", r":HGT:500 mb:"), ("t500", r":TMP:500 mb:"), ("u500", r":UGRD:500 mb:"), ("v500", r":VGRD:500 mb:"),
     ("u250", r":UGRD:250 mb:"), ("v250", r":VGRD:250 mb:"), ("pw", r":PWAT:entire atmosphere \(considered as a single layer\):"),
     ("u700", r":UGRD:700 mb:"), ("v700", r":VGRD:700 mb:"), ("u850", r":UGRD:850 mb:"), ("v850", r":VGRD:850 mb:"), ("mslp", r":PRMSL:mean sea level:")]
S, N, W, E = 5, 55, 15, 75
LAT = np.arange(90, -90.5, -1.0)
LON = np.arange(0, 360, 1.0)
J = (LAT >= S) & (LAT <= N)
I = (LON >= W) & (LON <= E)
la, lo = LAT[J], LON[I]


def cut(a):
    return a[np.ix_(J, I)]


def vort(u, v):
    from scipy.ndimage import gaussian_filter
    a, d = 6.371e6, np.radians(1.0)
    phi = np.radians(la)[:, None]
    u, v = gaussian_filter(u, 1), gaussian_filter(v, 1)
    return (np.gradient(v, d, axis=1) / (a * np.cos(phi)) + np.gradient(u * np.cos(phi), d, axis=0) / (a * np.cos(phi))) * 1e5


def lows(z, t):
    """closed lows at 500 hPa between 10 and 42 N: centre, depth below the ring 5 degrees around, core temperature"""
    out = []
    for j in range(5, len(la) - 5):
        for i in range(5, len(lo) - 5):
            if not (10 <= la[j] <= 42):
                continue
            w = z[j - 2:j + 3, i - 2:i + 3]
            if z[j, i] > w.min():
                continue
            ring = np.r_[z[j - 5, i - 5:i + 6], z[j + 5, i - 5:i + 6], z[j - 5:j + 6, i - 5], z[j - 5:j + 6, i + 5]]
            depth = float(ring.mean() - z[j, i])
            closed = bool(ring.min() - z[j, i] > 5)
            if depth > 30:
                out.append({"lat": float(la[j]), "lon": float(lo[i]), "z": round(float(z[j, i])), "depth_m": round(depth),
                            "closed": closed, "t_core": round(float(t[j, i] - 273.15), 1)})
    return sorted(out, key=lambda x: -x["depth_m"])[:4]


def highs(z):
    """ridges/blocks: 500 hPa highs between 25 and 52 N"""
    out = []
    for j in range(3, len(la) - 3):
        for i in range(3, len(lo) - 3):
            if not (25 <= la[j] <= 52):
                continue
            w = z[j - 3:j + 4, i - 3:i + 4]
            if z[j, i] < w.max():
                continue
            ring = np.r_[z[j - 3, i - 3:i + 4], z[j + 3, i - 3:i + 4], z[j - 3:j + 4, i - 3], z[j - 3:j + 4, i + 3]]
            if z[j, i] - ring.mean() > 15:
                out.append({"lat": float(la[j]), "lon": float(lo[i]), "z": round(float(z[j, i]))})
    return sorted(out, key=lambda x: -x["z"])[:3]


def box(a, s, n, w, e):
    jj = (la >= s) & (la <= n); ii = (lo >= w) & (lo <= e)
    return float(a[np.ix_(jj, ii)].mean())


def summarise(t, f):
    z, tt = cut(f["z500"]), cut(f["t500"])
    vo = vort(cut(f["u500"]), cut(f["v500"]))
    pw = cut(f["pw"])
    u8, v8 = cut(f["u850"]), cut(f["v850"])
    lobes = []
    vv = vo.copy()
    for _ in range(4):        # the strongest vorticity maxima over and around Arabia
        j, i = np.unravel_index(np.argmax(np.where((la[:, None] >= 12) & (la[:, None] <= 38) & (lo[None, :] >= 30) & (lo[None, :] <= 60), vv, -99)), vv.shape)
        if vv[j, i] < 4:
            break
        lobes.append({"lat": float(la[j]), "lon": float(lo[i]), "vort": round(float(vv[j, i]), 1)})
        vv[max(0, j - 4):j + 5, max(0, i - 4):i + 5] = -99
    return {
        "t": t, "lows": lows(z, tt), "highs": highs(z), "lobes": lobes,
        "pw": {"hijaz_makkah": round(box(pw, 20, 23, 39, 42), 1), "asir_jazan": round(box(pw, 16, 20, 41, 44), 1),
               "madinah": round(box(pw, 23, 26, 38, 41), 1), "central": round(box(pw, 22, 27, 43, 47), 1)},
        "wind850_redsea": [round(box(u8, 18, 23, 37, 41), 1), round(box(v8, 18, 23, 37, 41), 1)],
        "wind850_hijaz": [round(box(u8, 20, 23, 40, 43), 1), round(box(v8, 20, 23, 40, 43), 1)],
        "t500_makkah": round(box(tt, 20, 23, 39, 42) - 273.15, 1),
        # the steering of the storms: the mean wind of 700 and 500 hPa (u east-west, v north-south, m/s)
        "steer_hijaz": [round((box(cut(f["u700"]), 20, 23, 39, 42) + box(cut(f["u500"]), 20, 23, 39, 42)) / 2, 1),
                        round((box(cut(f["v700"]), 20, 23, 39, 42) + box(cut(f["v500"]), 20, 23, 39, 42)) / 2, 1)],
        "steer_asir": [round((box(cut(f["u700"]), 17, 20, 41, 44) + box(cut(f["u500"]), 17, 20, 41, 44)) / 2, 1),
                       round((box(cut(f["v700"]), 17, 20, 41, 44) + box(cut(f["v500"]), 17, 20, 41, 44)) / 2, 1)],
    }


def plot(t, f, path):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    z, vo = cut(f["z500"]), vort(cut(f["u500"]), cut(f["v500"]))
    pw, u8, v8, ms = cut(f["pw"]), cut(f["u850"]), cut(f["v850"]), cut(f["mslp"]) / 100
    import sa_geo
    regs = sa_geo.regions()
    fig, ax = plt.subplots(1, 2, figsize=(14, 6), dpi=110)
    X, Y = np.meshgrid(lo, la)
    ax[0].contourf(X, Y, vo, levels=[2, 4, 6, 9, 12, 16, 20], cmap="YlOrRd", extend="max")
    cs = ax[0].contour(X, Y, z, levels=range(5400, 6000, 30), colors="k", linewidths=.7)
    ax[0].clabel(cs, fmt="%d", fontsize=6)
    ax[0].set_title(f"{t}  500 hPa height (m) and vorticity (1e-5/s)")
    ax[1].contourf(X, Y, pw, levels=[10, 15, 20, 25, 30, 35, 40, 50], cmap="GnBu", extend="max")
    cs = ax[1].contour(X, Y, ms, levels=range(996, 1036, 2), colors="gray", linewidths=.6)
    ax[1].clabel(cs, fmt="%d", fontsize=6)
    ax[1].quiver(X[::2, ::2], Y[::2, ::2], u8[::2, ::2], v8[::2, ::2], scale=400, width=.002)
    ax[1].set_title("precipitable water (mm), MSLP (hPa), 850 hPa wind")
    for a in ax:
        for r in regs:
            g = r.get("geom")
            for poly in getattr(g, "geoms", [g]) if g is not None else []:
                x, y = poly.exterior.xy; a.plot(x, y, color="#335", lw=.4)
        a.set_xlim(25, 65); a.set_ylim(8, 45)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def main():
    out, a0, a1, fc, maxh = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
    os.makedirs(out, exist_ok=True)
    rows = []
    t = datetime.strptime(a0, "%Y%m%d%H")
    while t <= datetime.strptime(a1, "%Y%m%d%H"):
        try:
            f = daily.gfs_fields(t.strftime("%Y%m%d%H"), 0, fields=F)
            r = summarise(t.strftime("%Y-%m-%d %HZ analysis"), f); rows.append(r)
            plot(r["t"], f, os.path.join(out, f"map_{t:%Y%m%d%H}_a.png"))
            print("analysis", t, r["lows"][:1], flush=True)
        except Exception as e:  # noqa: BLE001
            print("skip", t, repr(e)[:120], flush=True)
        t += timedelta(hours=12)
    c = datetime.strptime(fc, "%Y%m%d%H")
    for h in range(12, maxh + 1, 12):
        try:
            f = daily.gfs_fields(fc, h, fields=F)
            v = c + timedelta(hours=h)
            r = summarise(f"{v:%Y-%m-%d %HZ} forecast +{h}h", f); rows.append(r)
            plot(r["t"], f, os.path.join(out, f"map_{v:%Y%m%d%H}_f.png"))
            print("forecast", v, r["lows"][:1], flush=True)
        except Exception as e:  # noqa: BLE001
            print("skip fc", h, repr(e)[:120], flush=True)
    json.dump(rows, open(os.path.join(out, "track.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
