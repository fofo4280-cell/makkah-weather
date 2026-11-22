#!/usr/bin/env python3
"""Chance of a severe storm, the next 8 Makkah days (Fahad, 22 Nov 2026, after the DWD-ICON thunderstorm outlook).

One number per place and day: the chance that a strong storm (24 h rain of 20 mm or more, satellite estimate) falls
within 25 km of it during the Makkah day (midnight to midnight). Ingredients from GFS 0.25 (Dr. Khalid: GFS is the
better model for storm environments): convective and total rain of the day, most-unstable and surface CAPE (strongest
of the afternoon, 9 AM - 9 PM Makkah), deep shear 10 m -> 500 hPa at the time of the strongest CAPE, precipitable
water, humidity at 700 and 500 hPa, coldest T500, CIN, ground height, land, season. They are joined by a logistic
fit (svr_coef.json) trained on 383 days (Nov 2024-May 2025, Oct-Dec 2025, Sep-18 Nov 2026) against the median of
PERSIANN PDIR-Now / CCS / PERSIANN over 15-33 N, 34-56 E, then recalibrated for the lead time on held-out days.

Test (each season held out in turn, day 1): ROC area 0.96 (GFS convective rain alone 0.91, CAPE alone 0.84);
reliable after the calibration (forecast 10-20 % -> 12 % observed, 20-30 % -> 22 %, 30 %+ -> 36 %).
Day 3: area 0.93; day 5: 0.91 (Sep-Nov 2026). Small mountain cells that the satellites barely see (13-18 Nov 2026
around Makkah/Taif) are not what this map measures: it is for organised strong storms (6 and 10 Nov 2026 caught).

    run(cycle, out_dir) -> dict for svr.json (pictures fig/svr_KK.png)
"""
import base64
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
AWS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
DAYS = 8
# crop of the GFS 0.25 grid (north row first): 33..15 N, 34..56 E
J0, J1, I0, I1 = 228, 301, 136, 225
LAT0, LON0, D = 33.0, 34.0, 0.25
NY, NX = J1 - J0, I1 - I0
EXTENT = [34.0, 56.0, 15.0, 33.0]   # west, east, south, north (cell centres at the picture edges)
INST = [("mucape", r":CAPE:180-0 mb above ground:"), ("sbcape", r":CAPE:surface:"), ("sbcin", r":CIN:surface:"),
        ("pw", r":PWAT:entire atmosphere"), ("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
        ("u500", r":UGRD:500 mb:"), ("v500", r":VGRD:500 mb:"), ("rh700", r":RH:700 mb:"), ("rh500", r":RH:500 mb:"),
        ("t500", r":TMP:500 mb:")]
ACC = [("acp", r":ACPCP:surface:0-"), ("ap", r":APCP:surface:0-")]
STATIC = [("hgt", r":HGT:surface:"), ("land", r":LAND:surface:")]
# colours (value %, colour, alpha): a faint lilac from 2 %, cyan, green, yellow, orange, red, dark red, grey at the top
PAL = [(2, "#e8e6fb", 0), (5, "#c9c3f5", 140), (10, "#7fc8e8", 190), (15, "#27d7d0", 210), (20, "#8cf37a", 225),
       (25, "#f4ee1d", 235), (30, "#ffb000", 240), (40, "#ff5810", 245), (50, "#e20000", 248), (60, "#8a0012", 250),
       (70, "#575757", 250), (85, "#c9c9c9", 250)]
LABEL = "احتمال العاصفة الشديدة"


def get(url, rng=None, tries=6):
    for k in range(tries):
        try:
            h = {"User-Agent": "climate-report/1.0"}
            if rng:
                h["Range"] = "bytes=%d-%s" % rng
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise
            print(f"svr retry {url}: {e!r}"[:200], flush=True)
            time.sleep(3 + 5 * k)


def decode(blob):
    """one GRIB2 message -> the crop, north row first"""
    try:
        import pygrib
        m = pygrib.fromstring(blob)
        a = np.ma.filled(np.ma.asarray(m.values, dtype=np.float32), np.nan)
        la = m.latlons()[0][:, 0]
        if la[0] < la[-1]:
            a = a[::-1]
    except ImportError:
        import eccodes
        g = eccodes.codes_new_from_message(blob)
        a = eccodes.codes_get_values(g).reshape(721, 1440).astype(np.float32)
        eccodes.codes_release(g)
    return a[J0:J1, I0:I1].copy()


def fetch(cycle, fh, want):
    d, hh = cycle[:8], cycle[8:10]
    url = f"{AWS}/gfs.{d}/{hh}/atmos/gfs.t{hh}z.pgrb2.0p25.f{fh:03d}"
    idx = get(url + ".idx").decode().splitlines()
    starts = [int(l.split(":")[1]) for l in idx]
    out = {}
    for name, pat in want:
        k = next(i for i, l in enumerate(idx) if re.search(pat, l))
        end = str(starts[k + 1] - 1) if k + 1 < len(starts) else ""
        out[name] = decode(get(url, (starts[k], end)))
    return out


def features(g, acc, hgt, land, doy):
    from scipy.ndimage import maximum_filter
    cape = g["mucape"]
    k = cape.argmax(0)
    pick = lambda a: np.take_along_axis(a, k[None], 0)[0]  # noqa: E731
    sh = np.hypot(g["u500"] - g["u10"], g["v500"] - g["v10"])
    f = {"acp": np.log1p(np.clip(acc["acp"], 0, None)), "ap": np.log1p(np.clip(acc["ap"], 0, None)),
         "cape": np.sqrt(np.clip(cape.max(0), 0, None)), "sbcape": np.sqrt(np.clip(g["sbcape"].max(0), 0, None)),
         "shear": pick(sh), "pw": g["pw"].mean(0), "rh7": g["rh700"].mean(0), "rh5": g["rh500"].mean(0),
         "t5": g["t500"].min(0) - 273.15, "cin": np.sqrt(-np.clip(pick(g["sbcin"]), None, 0))}
    for n in ("acp", "ap", "cape"):
        f[n + "_n"] = maximum_filter(f[n], size=3, mode="nearest")
    f["hgt"] = np.clip(hgt, 0, None) / 1000
    f["land"] = land
    f["capeXshear"] = f["cape_n"] * f["shear"] / 100
    f["acpXcape"] = f["acp_n"] * f["cape_n"] / 10
    f["pwXrh5"] = f["pw"] * f["rh5"] / 100
    f["cos"] = np.full(hgt.shape, np.cos(2 * np.pi * doy / 365))
    f["sin"] = np.full(hgt.shape, np.sin(2 * np.pi * doy / 365))
    return f


def calib(lead, C):
    """(slope, offset) on the logit for a lead in days: fitted at days 1, 3 and 5, in between interpolated, beyond 5
    flattened further (less sure, closer to the usual chance)"""
    c = {int(k): v for k, v in C["cal"].items()}
    if lead <= 1:
        return c[1]
    if lead <= 3:
        w = (lead - 1) / 2
        return [c[1][i] * (1 - w) + c[3][i] * w for i in range(2)]
    if lead <= 5:
        w = (lead - 3) / 2
        return [c[3][i] * (1 - w) + c[5][i] * w for i in range(2)]
    return [c[5][0] - 0.04 * (lead - 5), c[5][1] - 0.1 * (lead - 5)]


def probability(f, lead, C):
    z = C["icpt"] + sum(c * f[n] for n, c in zip(C["names"], C["coef"]))
    a, b = calib(lead, C)
    return 1 / (1 + np.exp(-(a * z + b)))      # z is already the logit


def colour(p):
    """probability (%) -> RGBA picture, colours blended between the stops"""
    vs = np.array([s[0] for s in PAL], float)
    rgb = np.array([[int(s[1][i:i + 2], 16) for i in (1, 3, 5)] for s in PAL], float)
    al = np.array([s[2] for s in PAL], float)
    out = np.zeros(p.shape + (4,), np.uint8)
    for ch in range(3):
        out[..., ch] = np.interp(p, vs, rgb[:, ch]).astype(np.uint8)
    a = np.interp(p, vs, al)
    a[p < vs[0]] = 0
    out[..., 3] = a.astype(np.uint8)
    return out


def picture(p, path):
    """the 0.25 deg probability resampled to a smooth picture in Web Mercator rows (the page lays it on the map as is)"""
    from scipy.ndimage import gaussian_filter, map_coordinates
    from PIL import Image
    w, e, s, n = EXTENT
    W = int(round((e - w) / 0.04)) + 1
    my = lambda la: np.log(np.tan(np.pi / 4 + np.radians(la) / 2))  # noqa: E731
    H = int(round(W * (my(n) - my(s)) / np.radians(e - w)))
    ys = np.linspace(my(n), my(s), H)
    lat = np.degrees(2 * np.arctan(np.exp(ys)) - np.pi / 2)
    lon = np.linspace(w, e, W)
    jj = (LAT0 - lat) / D
    ii = (lon - LON0) / D
    J, I = np.meshgrid(jj, ii, indexing="ij")
    sm = gaussian_filter(p, 0.6, mode="nearest")
    v = map_coordinates(sm, [J, I], order=1, mode="nearest")
    rgba = colour(v)
    # fade the last 0.75 degree at the edges of the area (no hard cut where the data end)
    edge = np.minimum.outer(np.minimum(lat - s, n - lat), np.minimum(lon - w, e - lon))
    rgba[..., 3] = (rgba[..., 3] * np.clip(edge / 0.75, 0, 1)).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def legend():
    lo, hi = PAL[0][0], PAL[-1][0]
    return {"vmin": lo, "stops": [{"p": round((v - lo) / (hi - lo), 4), "v": v, "c": c, "a": a} for v, c, a in PAL]}


def run(cycle, figdir, days=DAYS):
    C = json.load(open(os.path.join(HERE, "svr_coef.json")))
    t0 = datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    st = fetch(cycle, 0, STATIC)
    first = (t0 + timedelta(hours=27)).date()    # 12Z run of day D: day 1 = D + 1 (00Z run: also D + 1)
    noon = lambda k: int((datetime.combine(first + timedelta(days=k - 1), datetime.min.time(), timezone.utc)  # noqa: E731
                          + timedelta(hours=12) - t0).total_seconds() // 3600)   # 3 PM Makkah of day k, hours from the run
    jobs = []
    for k in range(1, days + 1):
        c = noon(k)
        jobs += [(k, "i", c + o) for o in (-6, -3, 0, 3, 6)] + [(k, "a0", c - 15), (k, "a1", c + 9)]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda j: fetch(cycle, j[2], INST if j[1] == "i" else ACC), jobs))
    os.makedirs(figdir, exist_ok=True)
    out = {"cycle": cycle, "made": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "model": "gfs",
           "label": LABEL, "unit": "٪", "extent": EXTENT,
           "grid": {"lat0": LAT0, "lon0": LON0, "d": D, "ny": NY, "nx": NX}, "legend": legend(), "days": []}
    for k in range(1, days + 1):
        mine = [r for j, r in zip(jobs, res) if j[0] == k]
        inst = {n: np.stack([r[n] for r in mine[:5]]) for n in mine[0]}
        acc = {n: mine[6][n] - mine[5][n] for n in mine[5]}
        day = first + timedelta(days=k - 1)
        f = features(inst, acc, st["hgt"], st["land"], day.timetuple().tm_yday)
        p = 100 * probability(f, k, C)
        name = f"svr_{k:02d}.png"
        picture(p, os.path.join(figdir, name))
        v = np.clip(np.round(p), 0, 100).astype(np.uint8)
        out["days"].append({"d": day.isoformat(), "lead": k, "file": name, "max": int(v.max()),
                            "vals": base64.b64encode(v.tobytes()).decode()})
        print(f"svr {day} lead {k}: max {v.max()} %, cells >= 10 %: {int((v >= 10).sum())}", flush=True)
    return out


if __name__ == "__main__":
    cyc, outdir = sys.argv[1], sys.argv[2]
    o = run(cyc, os.path.join(outdir, "fig"))
    json.dump(o, open(os.path.join(outdir, "svr.json"), "w"), ensure_ascii=False, separators=(",", ":"))
