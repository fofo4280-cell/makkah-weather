#!/usr/bin/env python3
"""Training and test of the ECMWF thunderstorm outlook for the river tab (Fahad, 25 Nov 2026: Dr. Khalid's
"Atmospheric River Tracking - Thunderstorm Outlook", «لكن باستخدام الأوروبي»).

Event (as svrprob.py): PERSIANN PDIR-Now daily rain of 20 mm or more within 25 km, UTC day D.
Ingredients: ECMWF open data (IFS 0.25), 12 UTC run of D-1, steps 12..36 (= day D): total rain of the day, most-unstable
CAPE (largest of 09/12/15/18/21 UTC), deep shear 10 m -> 500 hPa, precipitable water, RH 700/500, T500 at 15 UTC,
ground height, land, season. Area: 2-33 N, 34-75 E (the Kingdom, the Red Sea, the Arabian Sea, the Horn of Africa),
every second 0.25 cell.

    stormec_study.py fetch FIRST LAST OUT.npz      (YYYY-MM-DD)
    stormec_study.py fit DIR_WITH_NPZ OUT_DIR        -> stormec_coef.json + report.txt
"""
import gzip
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np

EC = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
PDIR = "https://persiann.eng.uci.edu/CHRSdata/PDIRNow/PDIRNowdaily/"
BOX = (2.0, 33.0, 34.0, 75.0)     # south, north, west, east
STEP = 2                          # every second 0.25 cell
INST = (21, 24, 27, 30, 33)       # 09..21 UTC of day D from the 12 UTC run of D-1
MID = 27                          # 15 UTC
NAMES = ["tp", "tp_n", "cape", "cape_n", "shear", "pw", "rh7", "rh5", "t5", "hgt", "land",
         "capeXshear", "tpXcape", "pwXrh5", "cos", "sin"]


def get(url, rng=None, tries=8):
    for k in range(tries):
        try:
            h = {"User-Agent": "climate-study/1.0"}
            if rng:
                h["Range"] = "bytes=%d-%d" % rng
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise
            time.sleep(3 + 4 * k)


def rows_cols():
    lat = np.linspace(90, -90, 721)
    lon = np.arange(1440) * 0.25
    s, n, w, e = BOX
    j = np.where((lat >= s) & (lat <= n))[0]
    i = np.where((lon >= w) & (lon <= e))[0]
    return slice(j[0], j[-1] + 1), slice(i[0], i[-1] + 1), lat[j[0]:j[-1] + 1], lon[i[0]:i[-1] + 1]


def ec_field(cycle, fh, par, lev, idx_cache):
    import pygrib
    d, hh = cycle[:8], cycle[8:10]
    url = f"{EC}/{d}/{hh}z/ifs/0p25/oper/{d}{hh}0000-{fh}h-oper-fc"
    if (cycle, fh) not in idx_cache:
        idx_cache[(cycle, fh)] = [json.loads(x) for x in get(url + ".index").decode().splitlines()]
    it = next(x for x in idx_cache[(cycle, fh)] if x["param"] == par and x.get("levelist", "") == lev)
    g = pygrib.fromstring(get(url + ".grib2", (it["_offset"], it["_offset"] + it["_length"] - 1)))
    a = np.asarray(g.values, dtype=np.float32)
    if g.latlons()[0][0, 0] < g.latlons()[0][-1, 0]:
        a = a[::-1]
    if float(g.latlons()[1][0, 0]) < 0:
        a = np.roll(a, a.shape[1] // 2, axis=1)
    return a


def ec_day(cycle):
    """the raw fields of day D from the 12 UTC run of D-1, cropped (full 0.25)"""
    js, is_, lat, lon = rows_cols()
    jobs = [("mucape", "", fh) for fh in INST] + [("tp", "", 12), ("tp", "", 36)]
    jobs += [(p, lv, MID) for p, lv in (("10u", ""), ("10v", ""), ("u", "500"), ("v", "500"), ("r", "700"),
                                         ("r", "500"), ("t", "500"), ("tcwv", ""))]
    idx = {}
    # indices first (one thread), then the fields in parallel by bytes, decoded in this thread
    import pygrib
    d, hh = cycle[:8], cycle[8:10]
    url = lambda fh: f"{EC}/{d}/{hh}z/ifs/0p25/oper/{d}{hh}0000-{fh}h-oper-fc"  # noqa: E731
    for fh in sorted({j[2] for j in jobs}):
        idx[fh] = [json.loads(x) for x in get(url(fh) + ".index").decode().splitlines()]

    def pull(j):
        p, lv, fh = j
        it = next(x for x in idx[fh] if x["param"] == p and x.get("levelist", "") == lv)
        return get(url(fh) + ".grib2", (it["_offset"], it["_offset"] + it["_length"] - 1))
    with ThreadPoolExecutor(6) as ex:
        blobs = list(ex.map(pull, jobs))
    out = {}
    for (p, lv, fh), b in zip(jobs, blobs):
        g = pygrib.fromstring(b)
        a = np.asarray(g.values, dtype=np.float32)
        la = g.latlons()[0][:, 0]
        if la[0] < la[-1]:
            a = a[::-1]
        if float(g.latlons()[1][0, 0]) < 0:
            a = np.roll(a, a.shape[1] // 2, axis=1)
        out.setdefault((p + lv), []).append(a[js, is_])
    return out, lat, lon


def features(raw, hgt, land, doy):
    """raw: {name: [arrays]} as ec_day returns; the same features at run time (river storms)"""
    from scipy.ndimage import maximum_filter
    tp = np.clip(raw["tp"][1] - raw["tp"][0], 0, None) * 1000.0         # m -> mm, day D
    cape = np.clip(np.stack(raw["mucape"]).max(0), 0, None)
    sh = np.hypot(raw["u500"][0] - raw["10u"][0], raw["v500"][0] - raw["10v"][0])
    f = {"tp": np.log1p(tp), "cape": np.sqrt(cape), "shear": sh, "pw": raw["tcwv"][0], "rh7": raw["r700"][0],
         "rh5": raw["r500"][0], "t5": raw["t500"][0] - 273.15}
    f["tp_n"] = maximum_filter(f["tp"], size=3, mode="nearest")
    f["cape_n"] = maximum_filter(f["cape"], size=3, mode="nearest")
    f["hgt"] = np.clip(hgt, 0, None) / 1000
    f["land"] = land.astype(np.float32)
    f["capeXshear"] = f["cape_n"] * f["shear"] / 100
    f["tpXcape"] = f["tp_n"] * f["cape_n"] / 10
    f["pwXrh5"] = f["pw"] * f["rh5"] / 100
    f["cos"] = np.full(hgt.shape, np.cos(2 * np.pi * doy / 365), np.float32)
    f["sin"] = np.full(hgt.shape, np.sin(2 * np.pi * doy / 365), np.float32)
    return f


def pdir(d, lat, lon):
    """PDIR-Now daily (0.04 deg, 60N..60S, lon 0..360), max within 25 km of every 0.25 point"""
    from scipy.ndimage import maximum_filter
    for n in (f"pdirnow1d{d:%y%m%d}.bin.gz",):
        raw = gzip.decompress(get(PDIR + n))
        a = np.frombuffer(raw, dtype=">i2").reshape(3000, 9000).astype(np.float32)
        a = np.where(a < 0, np.nan, a / 100.0)
        if not (1 < np.nanmax(a) < 2000):
            a = np.frombuffer(raw, dtype="<i2").reshape(3000, 9000).astype(np.float32)
            a = np.where(a < 0, np.nan, a / 100.0)
        # 25 km ~ 6 cells of 0.04 deg
        yy, xx = np.mgrid[-6:7, -6:7]
        mx = maximum_filter(np.nan_to_num(a, nan=-1), footprint=(yy ** 2 + xx ** 2 <= 36), mode="nearest")
        jj = np.clip(np.round((59.98 - lat) / 0.04).astype(int), 0, 2999)
        ii = np.clip(np.round((lon - 0.02) / 0.04).astype(int), 0, 8999)
        return mx[np.ix_(jj, ii)]


def fetch(first, last, out):
    js, is_, lat, lon = rows_cols()
    d = date.fromisoformat(first)
    stat = None
    rows = {n: [] for n in NAMES + ["obs", "doy", "day", "lat", "lon"]}
    while d <= date.fromisoformat(last):
        cyc = (d - timedelta(days=1)).strftime("%Y%m%d") + "12"
        try:
            raw, _, _ = ec_day(cyc)
            if stat is None:
                import pygrib  # noqa: F401
                g0 = {}
                for p in ("lsm", "z"):
                    g0[p] = ec_field(cyc, 0, p, "", {})[js, is_]
                stat = (g0["z"] / 9.80665, g0["lsm"] > 0.5)
            ob = pdir(d, lat, lon)
            f = features(raw, stat[0], stat[1], d.timetuple().tm_yday)
            sl = (slice(None, None, STEP), slice(None, None, STEP))
            LA, LO = np.meshgrid(lat, lon, indexing="ij")
            for n in NAMES:
                rows[n].append(f[n][sl].ravel().astype(np.float32))
            rows["obs"].append(ob[sl].ravel().astype(np.float32))
            n_ = ob[sl].size
            rows["doy"].append(np.full(n_, d.timetuple().tm_yday, np.int16))
            rows["day"].append(np.full(n_, int(d.strftime("%Y%m%d")), np.int32))
            rows["lat"].append(LA[sl].ravel().astype(np.float32))
            rows["lon"].append(LO[sl].ravel().astype(np.float32))
            print("ok", d, "max obs", float(np.nanmax(ob)), "events", int((ob >= 20).sum()), flush=True)
        except Exception as e:  # noqa: BLE001
            print("skip", d, repr(e)[:150], flush=True)
        d += timedelta(days=1)
    np.savez_compressed(out, **{n: np.concatenate(v) for n, v in rows.items() if v})


def fit(src, outdir):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score, brier_score_loss
    parts = [np.load(os.path.join(src, f)) for f in sorted(os.listdir(src)) if f.endswith(".npz")]
    T = {n: np.concatenate([p[n] for p in parts if n in p.files]) for n in parts[0].files}
    ok = T["obs"] >= 0
    y = (T["obs"] >= 20)[ok]
    day = T["day"][ok]
    test = day >= 20260901
    X = np.stack([T[n][ok] for n in NAMES], 1)
    mu, sd = X[~test].mean(0), X[~test].std(0) + 1e-9
    Z = (X - mu) / sd
    m = LogisticRegression(C=1.0, max_iter=3000).fit(Z[~test], y[~test])
    p = m.predict_proba(Z[test])[:, 1]
    clim = y[~test].mean()
    bs0 = brier_score_loss(y[test], np.full(test.sum(), clim))
    lines = [f"rows {len(y)}  train days {len(np.unique(day[~test]))}  test days {len(np.unique(day[test]))}",
             f"base rate train {clim:.4f} test {y[test].mean():.4f}",
             f"ingredients AUC {roc_auc_score(y[test], p):.3f}  BSS {1 - brier_score_loss(y[test], p) / bs0:.3f}"]
    for nm, col in (("rain alone", "tp_n"), ("CAPE alone", "cape_n")):
        lines.append(f"{nm} AUC {roc_auc_score(y[test], X[test][:, NAMES.index(col)]):.3f}")
    la, lo = T["lat"][ok][test], T["lon"][ok][test]
    for nm, msk in (("Kingdom box 15-33N 34-56E", (la >= 15) & (lo <= 56)),
                    ("Arabian Sea + Horn 2-15N or E of 56E", ~((la >= 15) & (lo <= 56)))):
        if msk.any() and y[test][msk].any():
            lines.append(f"{nm}: AUC {roc_auc_score(y[test][msk], p[msk]):.3f} base {y[test][msk].mean():.4f}")
    for a, b in [(0, .02), (.02, .05), (.05, .1), (.1, .2), (.2, .3), (.3, .5), (.5, 1)]:
        s = (p >= a) & (p < b)
        lines.append(f"forecast {a * 100:3.0f}-{b * 100:3.0f}%: n={s.sum():7d} observed "
                     f"{(100 * y[test][s].mean()) if s.any() else float('nan'):.1f}%")
    # final fit on all days for the nightly run
    mu, sd = X.mean(0), X.std(0) + 1e-9
    mf = LogisticRegression(C=1.0, max_iter=3000).fit((X - mu) / sd, y)
    coef = mf.coef_[0] / sd
    icpt = float(mf.intercept_[0] - (coef * mu).sum())
    os.makedirs(outdir, exist_ok=True)
    json.dump({"names": NAMES, "coef": [float(c) for c in coef], "icpt": icpt,
               "event": "PDIR-Now daily rain >= 20 mm within 25 km (UTC day)",
               "train": "ECMWF IFS 0.25 12Z run of D-1, steps 12-36; " + ", ".join(sorted({str(x)[:6] for x in np.unique(day)}))},
              open(os.path.join(outdir, "stormec_coef.json"), "w"), indent=1)
    open(os.path.join(outdir, "report.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        fit(sys.argv[2], sys.argv[3])
