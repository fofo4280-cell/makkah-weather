#!/usr/bin/env python3
"""Fahad's question (15 Nov 2026): do troughs really bring the rain of March and April, or is spring rain the leftover
of the early-winter cold waves? Reads the daily series of tropics_long.py and prints, for each part and each half of
the season, the 500 hPa height and precipitable-water departures on the wide-rain days against all days, and the
share of the season's rain that fell on trough days.

    tropics_spring.py long.json
"""
import json, os, sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tropics_long import GROUPS, running  # noqa: E402

rows = [r for r in json.load(open(sys.argv[1])) if all(g in r and len(r[g]) == 4 for g in GROUPS)]
days = [date.fromisoformat(r["d"]) for r in rows]
season = np.array([d.year if d.month >= 11 else d.year - 1 for d in days])
mon = np.array([d.month for d in days])
HALVES = {"نوفمبر-يناير": (11, 12, 1), "فبراير": (2,), "مارس-أبريل": (3, 4)}
for g in GROUPS:
    sp = np.array([r[g][0] for r in rows]); rn = np.array([r[g][1] for r in rows])
    z = np.array([r[g][2] for r in rows]); pw = np.array([r[g][3] for r in rows])
    za, pa, zs = np.full_like(z, np.nan), np.full_like(pw, np.nan), np.full_like(z, np.nan)
    for q in set(season):
        s = season == q
        za[s] = z[s] - running(z[s]); pa[s] = pw[s] - running(pw[s])
    # the height against the same calendar days of all seasons (the season's own climate), for a second view
    doy = np.array([d.timetuple().tm_yday for d in days])
    for k in set(doy):
        s = np.abs(((doy - k + 183) % 366) - 183) <= 7
        zs[doy == k] = z[doy == k] - z[s].mean()
    print(f"\n== {g}")
    for h, ms in HALVES.items():
        s = np.isin(mon, ms)
        thr = np.quantile(sp[s], 0.95)
        w = s & (sp >= max(thr, 0.03))
        tot = rn[s].sum()
        tr = s & (za <= -20); tr2 = s & (zs <= -20); moist = s & (pa >= 3)
        print(f"  {h}: wide days n={w.sum()} (spread >= {100*max(thr,0.03):.0f}%) | z500 departure on wide days "
              f"{np.mean(za[w]):+.0f} m (all days {np.mean(za[s]):+.0f}), below normal on {100*np.mean(za[w] < 0):.0f}% of them, "
              f"against the calendar {np.mean(zs[w]):+.0f} m | PW departure {np.mean(pa[w]):+.1f} mm, PW {np.mean(pw[w]):.0f} mm "
              f"(all {np.mean(pw[s]):.0f}) | rain share: trough days (<=-20 m) {100*rn[tr].sum()/tot:.0f}% on {100*tr[s].mean():.0f}% of days, "
              f"calendar troughs {100*rn[tr2].sum()/tot:.0f}% on {100*tr2[s].mean():.0f}%, moisture surge (>=+3 mm) {100*rn[moist].sum()/tot:.0f}% on {100*moist[s].mean():.0f}%, "
              f"both {100*rn[tr & moist].sum()/tot:.0f}% on {100*(tr & moist)[s].mean():.0f}%")
    # monthly climate of the part: mean spread and mean rain by month
    print("  by month (mean spread %, mean rain mm/day): " + "  ".join(
        f"{m}:{100*sp[mon == m].mean():.1f}/{rn[mon == m].mean():.2f}" for m in (11, 12, 1, 2, 3, 4)))
