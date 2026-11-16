#!/usr/bin/env python3
"""Study (Fahad, 17 Nov 2026): do the IOD and ENSO go with the convective (no-trough) rain rather than the trough
rain? Each wet-season day of each part is split by the 500 hPa synoptic trough over the part (waves 4-8 <= -25 m, the
report's rule, NCEP R1 as in method_test.py); the half-monthly rain of each kind against the DMI and Nino 3.4 of
September to November. Also the precipitable water (% of normal) by half-month against the same indices. Prints only.

    iod_conv.py LONG_JSON HIST_DIR
"""
import json, os, sys
from datetime import date
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import waves  # noqa: E402
from method_test import load_hist, part_masks  # noqa: E402
from tropics_long import GROUPS, monthly_index  # noqa: E402

dmi = monthly_index("https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data")
nino = monthly_index("https://psl.noaa.gov/data/correlation/nina34.anom.data")
rows = json.load(open(sys.argv[1]))
days, chi, z8, z5 = load_hist(sys.argv[2])
del chi, z8
ix = {d: k for k, d in enumerate(days)}
masks = part_masks()
TARGET = [(11, 1), (11, 2), (12, 1), (12, 2), (1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2), (4, 1), (4, 2)]
BAND = {}
PM = {9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر"}
for g in ("الحجاز", "الجنوب الغربي", "المملكة"):
    acc = {}
    for r in rows:
        d = date.fromisoformat(r["d"])
        if g not in r or d not in ix or len(r[g]) < 4:
            continue
        zb = BAND.setdefault(d, waves.band(z5[ix[d]].astype(np.float64)))
        tr = float(np.min(zb[masks[g]])) if g != "المملكة" else min(float(np.min(zb[masks[q]])) for q in GROUPS if q != "المملكة")
        s = d.year if d.month >= 11 else d.year - 1
        key = (s, d.month, 1 if d.day <= 15 else 2)
        a = acc.setdefault(key, {"conv": 0.0, "trough": 0.0, "n": 0, "pw": []})
        a["conv" if tr > -25 else "trough"] += r[g][0]
        a["n"] += 1
        a["pw"].append(r[g][3])
    seasons = sorted({k[0] for k in acc})
    # PW as % of the mean of that half-month over all seasons
    pwm = {(m, h): np.mean([np.mean(acc[(s, m, h)]["pw"]) for s in seasons if (s, m, h) in acc]) for m, h in TARGET}
    tot = {kind: sum(a[kind] for a in acc.values()) for kind in ("conv", "trough")}
    print(f"\n######## {g}: seasons {len(seasons)}; share of rain spread on no-trough (convective) days "
          f"{100*tot['conv']/(tot['conv']+tot['trough']):.0f}%; |r|>=0.40 ~ 95%")
    print("    kind     index month | " + " ".join(f"{m:>2d}-{h}" for m, h in TARGET) + " | Nov-Dec Mar-Apr whole")
    for kind in ("conv", "trough", "pw"):
        for nm, IDX in (("DMI", dmi), ("Nino", nino)):
            for pm in (9, 10, 11):
                def val(s, months):
                    ks = [(s, m, h) for m, h in TARGET if m in months and (s, m, h) in acc]
                    if not ks:
                        return None
                    if kind == "pw":
                        return np.mean([100 * np.mean(acc[k]["pw"]) / pwm[k[1:]] for k in ks])
                    return sum(acc[k][kind] for k in ks) / sum(acc[k]["n"] for k in ks)
                def corr(months):
                    xs, ys = [], []
                    for s in seasons:
                        v, y = IDX.get((s, pm)), val(s, months)
                        if v is not None and y is not None:
                            xs.append(v); ys.append(y)
                    return np.corrcoef(xs, ys)[0, 1] if len(xs) >= 12 else np.nan
                cells = [corr({m}) if False else np.nan for _ in ()]
                hs = []
                for m, h in TARGET:
                    xs, ys = [], []
                    for s in seasons:
                        k = (s, m, h)
                        v = IDX.get((s, pm))
                        if v is None or k not in acc:
                            continue
                        y = 100 * np.mean(acc[k]["pw"]) / pwm[(m, h)] if kind == "pw" else acc[k][kind] / acc[k]["n"]
                        xs.append(v); ys.append(y)
                    hs.append(np.corrcoef(xs, ys)[0, 1] if len(xs) >= 12 and np.std(ys) > 0 else np.nan)
                print(f"    {kind:6s} {nm:4s} {PM[pm]:>7s} | " + " ".join(f"{c:+.2f}" for c in hs)
                      + f" | {corr((11, 12)):+.2f}  {corr((3, 4)):+.2f}  {corr((11, 12, 1, 2, 3, 4)):+.2f}", flush=True)
