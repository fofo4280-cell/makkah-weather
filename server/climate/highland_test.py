#!/usr/bin/env python3
"""The moisture needed for rain on the southwestern highlands and on Tihama, on their own (Fahad, 15 Nov 2026: in the
first part of the season the southwest gets heavy rain with the precipitable water at 150-190 % of normal, while the
whole-part test, diluted by the Najran desert, said rain there is rare).

    highland_test.py fetch FIRST_YEAR LAST_YEAR OUT.json HIST_DIR   (one chunk of years; run chunks in parallel)
    highland_test.py analyse DIR_OF_JSON

Rain: CHIRPS v2 daily (0.25 degree, IRI library) on two strips:
  the highlands (Sarawat of Asir and Al-Baha): within 0.45 degree of the line Abha side (17.5N 43.2E) to (20.5N 41.2E);
  Tihama of Jazan and Asir: within 0.3 degree of the line (16.6N 42.75E) to (19.3N 41.0E).
Moisture: NCEP/NCAR reanalysis precipitable water at the middle of each strip, as % of its normal for the date.
Trough: the 500 hPa synoptic waves (waves 4-8) at their lowest over 15-25N, 37.5-47.5E (the hist chunks of the method test).
MJO: the RMM (BoM).
"""
import os, sys
from datetime import date

import numpy as np
from scipy.interpolate import RegularGridInterpolator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tropics_long as L  # noqa: E402
import daily, waves  # noqa: E402
from method_test import load_hist, LAT5, LON  # noqa: E402

STRIPS = {"المرتفعات (السروات)": ((17.5, 43.2), (20.5, 41.2), 0.45, (19.0, 42.2)),
          "تهامة جازان وعسير": ((16.6, 42.75), (19.3, 41.0), 0.30, (17.9, 41.9))}


def seg_dist(la, lo, a, b):
    p = np.stack([la, lo], -1); a = np.array(a); b = np.array(b)
    t = np.clip(((p - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
    return np.linalg.norm(p - (a + t[..., None] * (b - a)), axis=-1)


def fetch(y0, y1, outp, hist):
    import json
    L.S, L.N, L.W, L.E = 16.0, 21.5, 40.0, 44.5
    rmm = {d: (r1, r2, ph, amp) for d, r1, r2, ph, amp in daily.read_rmm()}
    days, _, _, z5 = load_hist(hist)
    ix = {d: k for k, d in enumerate(days)}
    j5 = (LAT5 >= 15) & (LAT5 <= 25); i5 = (LON >= 37.5) & (LON <= 47.5)
    rows = []
    for y in range(y0, y1 + 1):
        c = L.chirps_year(y)
        pw = L.ncep("pr_wtr", y, f"surface/pr_wtr.eatm.{y}.nc")
        if c is None or pw is None:
            print("skip", y, c is None, pw is None, flush=True)
            continue
        dd, la, lo, p = c
        LA, LO = np.meshgrid(la, lo, indexing="ij")
        masks = {n: seg_dist(LA, LO, a, b) <= w for n, (a, b, w, _) in STRIPS.items()}
        pla, plo, pa = pw
        for k, d in enumerate(dd):
            if d not in rmm or d not in ix:
                continue
            kd = (d - date(y, 1, 1)).days
            if kd >= pa.shape[0]:
                continue
            r = {"d": d, "rmm": rmm[d]}
            zb = waves.band(z5[ix[d]].astype(float))[np.ix_(j5, i5)]
            r["tr"] = float(zb.min())
            for n, (a, b, w, mid) in STRIPS.items():
                v = p[k][masks[n]]
                v = v[np.isfinite(v)]
                # bilinear between the four reanalysis points around the middle of the strip
                f = RegularGridInterpolator(*((pla[::-1], plo), pa[kd][::-1]) if pla[0] > pla[-1] else ((pla, plo), pa[kd]))
                r[n] = (float(np.mean(v >= 5)) if v.size else np.nan, float(v.max()) if v.size else np.nan, float(f(mid)))
            rows.append(r)
        print("year", y, "rows", len(rows), "cells", {n: int(m.sum()) for n, m in masks.items()}, flush=True)
    json.dump([{**r, "d": r["d"].isoformat()} for r in rows], open(outp, "w"))


def analyse(dirn):
    import glob, json
    rows = []
    for p in sorted(glob.glob(os.path.join(dirn, "**", "*.json"), recursive=True)):
        rows += json.load(open(p))
    for r in rows:
        r["d"] = date.fromisoformat(r["d"])
    rows.sort(key=lambda r: r["d"])
    print("rows", len(rows), rows[0]["d"], rows[-1]["d"], flush=True)
    rd = [r["d"] for r in rows]
    mon = np.array([d.month for d in rd]); doy = np.array([d.timetuple().tm_yday for d in rd])
    ph = np.array([r["rmm"][2] for r in rows]); amp = np.array([r["rmm"][3] for r in rows])
    tr = np.array([r["tr"] for r in rows]) <= -25
    mjo = (amp >= 1) & np.isin(ph, (8, 1, 2))
    bins = ((0, 80), (80, 100), (100, 115), (115, 130), (130, 150), (150, 175), (175, 999))
    for n in STRIPS:
        sp = np.array([r[n][0] for r in rows]); mx = np.array([r[n][1] for r in rows]); pw = np.array([r[n][2] for r in rows])
        clim = np.array([np.nanmean(pw[np.abs(((doy - k + 183) % 366) - 183) <= 7]) for k in doy])
        pc = 100 * pw / clim
        print(f"\n######## {n}: P(10 mm or more somewhere on the strip) / P(5 mm or more on a fifth of it), by PW % of normal")
        print("  by month: " + "  ".join(f"{m}: P(10mm) {100*np.mean(mx[mon == m] >= 10):.0f}%, PW {np.nanmean(pw[mon == m]):.0f} mm"
                                        for m in (11, 12, 1, 2, 3, 4)))
        for h, ms in (("نوفمبر", (11,)), ("ديسمبر-يناير", (12, 1)), ("فبراير-أبريل", (2, 3, 4))):
            s = np.isin(mon, ms) & np.isfinite(sp) & np.isfinite(pc)
            for nm, f in (("all days", np.ones_like(s)), ("trough", tr), ("no trough", ~tr), ("MJO 8-1-2", mjo)):
                cells = []
                for a, b in bins:
                    q = s & f & (pc >= a) & (pc < b)
                    cells.append(f"{a}-{b if b < 999 else ''}: {100*np.mean(mx[q] >= 10):.0f}/{100*np.mean(sp[q] >= 0.2):.0f} (n{q.sum()})"
                                 if q.sum() >= 10 else f"{a}-{b if b < 999 else ''}: -")
                print(f"  {h} | {nm}: " + "  ".join(cells))


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5])
    else:
        analyse(sys.argv[2])
