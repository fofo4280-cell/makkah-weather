#!/usr/bin/env python3
"""Study (Fahad, 17 Nov 2026): in which months does the Indian Ocean Dipole (and ENSO) of a given month go with the
rain of the wet season? Monthly and half-monthly rain spread of each part (CHIRPS, the long series) against the DMI
and Nino 3.4 of each month from June before the season to March. Prints only.

    iod_test.py LONG_JSON
"""
import json, os, sys
from datetime import date
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tropics_long import GROUPS, monthly_index  # noqa: E402

dmi = monthly_index("https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data")
nino = monthly_index("https://psl.noaa.gov/data/correlation/nina34.anom.data")
print("dmi months", len(dmi), "nino months", len(nino), "last dmi", max(dmi) if dmi else None, flush=True)
rows = json.load(open(sys.argv[1]))
PRED = [(-1, m) for m in range(6, 13)] + [(0, m) for m in range(1, 4)]          # (year offset vs season start, month)
PNAME = {6: "يونيو", 7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر", 1: "يناير", 2: "فبراير", 3: "مارس"}
TARGET = [(11, 1), (11, 2), (12, 1), (12, 2), (1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2), (4, 1), (4, 2)]
for g in GROUPS:
    acc = {}
    for r in rows:
        if g not in r:
            continue
        d = date.fromisoformat(r["d"])
        s = d.year if d.month >= 11 else d.year - 1
        acc.setdefault((s, d.month, 1 if d.day <= 15 else 2), []).append(r[g][0])
    seasons = sorted({k[0] for k in acc})
    print(f"\n######## {g}  (seasons {seasons[0]}-{seasons[-1]}, n={len(seasons)}); r of rain spread vs index; |r|>=0.40 ~ 95%")
    for idx_name, IDX in (("DMI", dmi), ("Nino3.4", nino)):
        print(f"  {idx_name}: rows = the index month, columns = rain half-month (Nov-1 .. Apr-2)")
        print("   " + " ".join(f"{m:>2d}-{h}" for m, h in TARGET) + " | Nov-Dec Jan-Feb Mar-Apr whole")
        for off, pm in PRED:
            cells = []
            for m, h in TARGET:
                xs, ys = [], []
                for s in seasons:
                    y = s + (1 if m <= 4 else 0)
                    py = s + 1 + off if pm <= 5 else s + off + 1
                    # predictor year: months Jun-Dec belong to the season-start year s (offset -1 means year s)
                    py = s if pm >= 6 else s + 1
                    v = IDX.get((py, pm))
                    rr = acc.get((s, m, h))
                    if v is None or not rr:
                        continue
                    xs.append(v); ys.append(np.mean(rr))
                cells.append(np.corrcoef(xs, ys)[0, 1] if len(xs) >= 12 else np.nan)
            blocks = []
            for months in ((11, 12), (1, 2), (3, 4), (11, 12, 1, 2, 3, 4)):
                xs, ys = [], []
                for s in seasons:
                    py = s if pm >= 6 else s + 1
                    v = IDX.get((py, pm))
                    rr = [x for (s2, m, h), l in acc.items() if s2 == s and m in months for x in l]
                    if v is None or not rr:
                        continue
                    xs.append(v); ys.append(np.mean(rr))
                blocks.append(np.corrcoef(xs, ys)[0, 1] if len(xs) >= 12 else np.nan)
            print(f"  {PNAME[pm]:>7s} " + " ".join(f"{c:+.2f}" for c in cells) + " | " + "  ".join(f"{b:+.2f}" for b in blocks), flush=True)
