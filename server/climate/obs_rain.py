#!/usr/bin/env python3
"""Observed rain of past days over the Kingdom from satellite estimates, for the reading test (hindcast.py).

Source: PERSIANN-PDIR-Now daily (UC Irvine CHRS, 0.04 deg, public, about an hour behind), UTC days. Each day gives
the share of every region with 1 mm or more and 5 mm or more, its maximum, and the wettest spots named by the
nearest town. Other public sources are probed and listed in the log.

    obs_rain.py FIRST_DAY LAST_DAY OUT_JSON
"""
import gzip
import json
import os
import re
import sys
import urllib.request
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UA = "climate-report-test/1.0"
PDIR = "https://persiann.eng.uci.edu/CHRSdata/PDIRNow/PDIRNowdaily/"
PROBE = ["https://persiann.eng.uci.edu/CHRSdata/PDIRNow/", PDIR,
         "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH2/", "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_RT/",
         "https://ftp.cpc.ncep.noaa.gov/precip/CPC_UNI_PRCP/GAUGE_GLB/RT/2026/"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def probe():
    for u in PROBE:
        try:
            t = get(u).decode("latin-1")
            names = re.findall(r'href="([^"?/][^"]*)"', t)
            print("PROBE", u, len(names), names[:6], names[-6:], flush=True)
        except Exception as e:  # noqa: BLE001
            print("PROBE", u, "failed", repr(e)[:120], flush=True)


def pdir_day(d):
    """(rain mm on 0.04 deg from 60N, lon 0..360) or None"""
    names = [f"pdirnow1d{d:%y%m%d}.bin.gz", f"pdirnow1d{d:%Y%m%d}.bin.gz"]
    for n in names:
        try:
            raw = gzip.decompress(get(PDIR + n))
        except Exception as e:  # noqa: BLE001
            print("pdir", n, repr(e)[:100], flush=True)
            continue
        for dt in (">i2", "<i2", ">f4", "<f4"):
            if len(raw) != 3000 * 9000 * np.dtype(dt).itemsize:
                continue
            a = np.frombuffer(raw, dtype=dt).reshape(3000, 9000).astype(np.float32)
            if dt.endswith("i2"):
                a = np.where(a < 0, np.nan, a / 100.0)
            else:
                a = np.where(a < 0, np.nan, a)
            sub = a[:, :]
            ok = np.isfinite(sub)
            mx = float(np.nanmax(sub)) if ok.any() else 0
            print("pdir", n, dt, "max", mx, "wet share", float(np.nanmean(sub > 1)), flush=True)
            if 1 < mx < 2000:
                return a
        print("pdir", n, "size", len(raw), "not understood", flush=True)
    return None


def summarise(a, regs):
    import sa_geo as G
    lat = 60 - 0.04 * (np.arange(3000) + 0.5)
    lon = 0.04 * (np.arange(9000) + 0.5)
    j = (lat >= 15.5) & (lat <= 33)
    i = (lon >= 34) & (lon <= 56)
    sub = a[np.ix_(j, i)]
    LA, LO = np.meshgrid(lat[j], lon[i], indexing="ij")
    idx = G.region_of_points(regs, LA.ravel(), LO.ravel()).reshape(LA.shape)
    out = {"regions": {}}
    inside = idx >= 0
    v = np.nan_to_num(sub)
    out["ksa1"] = round(float((v[inside] >= 1).mean()), 4)
    out["ksa5"] = round(float((v[inside] >= 5).mean()), 4)
    for k, r in enumerate(regs):
        m = idx == k
        if not m.any():
            continue
        x = v[m]
        row = {"wet1": round(float((x >= 1).mean()), 4), "wet5": round(float((x >= 5).mean()), 4),
               "max": round(float(x.max()), 1), "spots": []}
        if x.max() >= 2:
            # the wettest spots, at least 25 km apart
            order = np.argsort(-np.where(m, v, -1).ravel())
            taken = []
            for q in order[:4000]:
                y = v.ravel()[q]
                if y < 2 or len(taken) >= 6:
                    break
                la_, lo_ = LA.ravel()[q], LO.ravel()[q]
                if any(abs(la_ - a_) < 0.25 and abs(lo_ - b_) < 0.25 for a_, b_, _ in taken):
                    continue
                taken.append((la_, lo_, y))
            for la_, lo_, y in taken:
                n_, dk = G.nearest_place(la_, lo_)
                row["spots"].append({"lat": round(float(la_), 2), "lon": round(float(lo_), 2), "mm": round(float(y), 1),
                                     "near": n_, "km": round(float(dk))})
        out["regions"][r["name"]] = row
    return out


def main():
    a, b, path = sys.argv[1:4]
    probe()
    import sa_geo as G
    regs = G.regions()
    res = {}
    d = date.fromisoformat(a)
    while d <= date.fromisoformat(b):
        try:
            x = pdir_day(d)
            res[d.isoformat()] = summarise(x, regs) if x is not None else None
            print(d, json.dumps(res[d.isoformat()], ensure_ascii=False)[:600], flush=True)
        except Exception as e:  # noqa: BLE001
            print(d, "failed", repr(e), flush=True)
        json.dump(res, open(path, "w"), ensure_ascii=False)
        d += timedelta(days=1)


if __name__ == "__main__":
    main()
