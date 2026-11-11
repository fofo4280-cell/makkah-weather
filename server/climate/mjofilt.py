"""The MJO component of the 800 hPa height and of the rain, isolated by filtering in wavenumber and frequency
(eastward planetary waves 1 to 5, periods 20 to 100 days), after the method of Wheeler and Kiladis that
Dr Khalid's maps use. The series is the GFS analyses of the last months (00 UTC, one a day), followed by the
15-day GFS forecast and then zeros, so the last (forecast) days are filtered too.

Also, for the report: how the component sits over the Kingdom day by day, the rain the GFS gave the Kingdom on
each past day (its first-day forecast, as a stand-in for what fell), the past rain episodes, and a strength
index of the coming days built from all the drivers, compared with the current wave and the past episodes.
"""
import os
from datetime import timedelta

import numpy as np

LAT = np.arange(40, -40.1, -1.0)       # the tropical band kept (descending, like the GFS grid)
LON = np.arange(0, 360, 1.0)
Z800 = ("z800", r":HGT:800 mb:")
APCP = ("apcp", r":APCP:surface:0-")    # the accumulation from the start of the run
KSA = (16, 32, 36, 55)                  # south, north, west, east: the Kingdom box for the component
EPISODE_COVER = 0.08                    # a rain day: 8 % of the Kingdom with 5 mm or more in the day
HIST_DAYS = 400                         # more than a year, so the effect is measured over a whole rain season
WET_MONTHS = {11, 12, 1, 2, 3, 4}


def band(a):
    """the 40S-40N band of a 1 degree global field (lat 90..-90)"""
    return a[50:131].astype(np.float32)


# ------------------------------------------------------------------ the filter
def mjo_filter(X, kmin=1, kmax=5, pmin=20.0, pmax=100.0, pad=120, taper=20):
    """X: (days, lat, lon). The eastward part with wavenumbers kmin..kmax and periods pmin..pmax days."""
    nt, ny, nx = X.shape
    Y = X - X.mean(0)
    t = np.arange(nt, dtype=float) - (nt - 1) / 2
    Y = Y - ((Y * t[:, None, None]).sum(0) / (t ** 2).sum()) * t[:, None, None]
    w = np.ones(nt)
    w[:taper] = 0.5 * (1 - np.cos(np.pi * np.arange(taper) / taper))   # only the start: the end is what we want
    Y = np.concatenate([Y * w[:, None, None], np.zeros((pad, ny, nx))])
    F = np.fft.fft2(Y, axes=(0, 2))
    f = np.fft.fftfreq(Y.shape[0])[:, None]              # cycles per day
    k = np.fft.fftfreq(nx, 1.0 / nx)[None, :]            # waves around the globe
    keep = ((np.abs(k) >= kmin) & (np.abs(k) <= kmax) & (np.abs(f) >= 1 / pmax) & (np.abs(f) <= 1 / pmin)
            & (f * k < 0))                               # exp(i(kx - wt)): eastward when f and k differ in sign
    F *= keep[:, None, :]
    return np.real(np.fft.ifft2(F, axes=(0, 2)))[:nt]


def box(a, s, n, w, e, lat=LAT, lon=LON):
    j = (lat >= s) & (lat <= n)
    i = (lon >= w) & (lon <= e)
    return float(np.nanmean(a[np.ix_(j, i)]))


# ------------------------------------------------------------------ data
def history(state, t0, days, gfs_fields, log=print):
    """{date: {'z800', 'rain'}} for the past days, cached in state/hist as YYYYMMDD_m.npz.
    rain: the day's precipitation (mm) from the 00 UTC run's first 24 hours."""
    out = {}
    d = os.path.join(state, "hist")
    os.makedirs(d, exist_ok=True)
    for k in range(days, 0, -1):
        dt = t0 - timedelta(days=k)
        p = os.path.join(d, dt.strftime("%Y%m%d") + "_m.npz")
        if not os.path.exists(p):
            try:
                cyc = dt.strftime("%Y%m%d00")
                z = gfs_fields(cyc, 0, fields=[Z800])["z800"]
                r = gfs_fields(cyc, 24, fields=[APCP])["apcp"]
                np.savez_compressed(p, z800=band(z), rain=band(r))
            except Exception as e:
                log("mjo filter: skip", dt.date(), repr(e)[:120])
                continue
        try:
            q = np.load(p)
            out[dt.date()] = {"z800": q["z800"].astype(np.float32), "rain": q["rain"].astype(np.float32)}
        except Exception:
            os.remove(p)
    for f in os.listdir(d):
        if f.endswith("_m.npz") and f[:8] < (t0 - timedelta(days=days + 2)).strftime("%Y%m%d"):
            os.remove(os.path.join(d, f))
    return out


def kingdom_mask():
    import sa_geo
    regs = sa_geo.regions()
    la, lo = np.meshgrid(LAT, LON, indexing="ij")
    return (sa_geo.region_of_points(regs, la.ravel(), lo.ravel()) >= 0).reshape(la.shape)


# ------------------------------------------------------------------ the analysis
def run(hist, fc, t0, log=print):
    """hist: {date: {'z800', 'rain'}}; fc: [(date, z800 band, rain band or None)] from the analysis day on.
    Returns (dates, filtered z800, filtered rain, info)."""
    dates = sorted(hist) + [d for d, _, _ in fc if d not in hist]
    zd = {d: v["z800"] for d, v in hist.items()}
    rd = {d: v["rain"] for d, v in hist.items()}
    for d, z, r in fc:
        zd[d] = z
        if r is not None:
            rd[d] = r
    # a continuous daily series: missing days by linear interpolation in time
    full = [dates[0] + timedelta(days=k) for k in range((dates[-1] - dates[0]).days + 1)]

    def series(src):
        have = [d for d in full if d in src]
        arr = np.stack([src[d] for d in have])
        x = np.array([(d - full[0]).days for d in have], float)
        xi = np.arange(len(full), dtype=float)
        out = np.empty((len(full),) + arr.shape[1:], np.float32)
        flat = arr.reshape(len(have), -1)
        out_flat = out.reshape(len(full), -1)
        for c in range(flat.shape[1]):
            out_flat[:, c] = np.interp(xi, x, flat[:, c])
        return out
    Z = series(zd)
    last_rain = max(rd)
    R = series(rd)
    zf = mjo_filter(Z, kmax=3)          # the height: planetary waves 1-3, a clean envelope as on Dr Khalid's map
    rf = mjo_filter(R)
    mask = kingdom_mask()
    s, n, w, e = KSA
    info = {"days": [d.isoformat() for d in full], "z_ksa": [], "r_ksa": [], "core": [], "cover": [], "rain_ksa": []}
    eq = (LAT >= -10) & (LAT <= 10)
    for k, d in enumerate(full):
        info["z_ksa"].append(round(box(zf[k], s, n, w, e), 1))
        info["r_ksa"].append(round(box(rf[k], s, n, w, e), 2))
        prof = zf[k][eq].mean(0)
        info["core"].append(int(LON[int(np.argmin(prof))]))
        if d < t0 and d <= last_rain:     # the past days only: the first-day forecast as a stand-in for what fell
            day = R[k][mask]
            info["cover"].append(round(float((day >= 5).mean()), 3))
            info["rain_ksa"].append(round(float(day.mean()), 1))
        else:
            info["cover"].append(None)
            info["rain_ksa"].append(None)
    past = [v for v, d in zip(info["z_ksa"], full) if d < t0]
    info["z_ref"] = round(float(np.std(past)) or 1.0, 1)
    info["t0"] = t0.isoformat()
    log("mjo filter: days", len(full), "z ref", info["z_ref"], "core today", info["core"][full.index(t0)] if t0 in full else None)
    return full, zf, rf, info


def episodes(info, upto):
    """past rain episodes over the Kingdom: [{a, b, peak, cover, z, r}] (dates as ISO strings)"""
    out, cur = [], None
    for d, c, z, r in zip(info["days"], info["cover"], info["z_ksa"], info["r_ksa"]):
        if c is None or d >= upto:
            continue
        if c >= EPISODE_COVER:
            if cur and (np_days(d) - np_days(cur["b"])) <= 2:
                cur["b"] = d
                cur["z"].append(z); cur["r"].append(r)
                if c > cur["cover"]:
                    cur["cover"], cur["peak"] = c, d
            else:
                cur = {"a": d, "b": d, "peak": d, "cover": c, "z": [z], "r": [r]}
                out.append(cur)
    for x in out:
        x["z"] = round(float(np.mean(x["z"])), 1)
        x["r"] = round(float(np.mean(x["r"])), 2)
    return out


def np_days(iso):
    from datetime import date
    return date.fromisoformat(iso).toordinal()
