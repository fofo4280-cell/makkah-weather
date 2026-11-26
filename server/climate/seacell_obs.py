#!/usr/bin/env python3
"""Observed rain (PERSIANN-PDIR-Now daily, UTC days) over the sea strip and the coast of each stretch of seacell.py and
over the Makkah plain, for the test of the night sea-cell reading.

    seacell_obs.py FIRST_DAY LAST_DAY CELLS_JSON OUT_JSON
"""
import json
import os
import sys
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs_rain  # noqa: E402


def stats(a, cells):
    """share >= 1 mm, share >= 5 mm and max over the 0.04 degree cells inside the 0.25 degree cells"""
    vals = []
    for la, lo in cells:
        j0, j1 = int((60 - (la + 0.125)) / 0.04), int((60 - (la - 0.125)) / 0.04)
        i0, i1 = int((lo - 0.125) / 0.04), int((lo + 0.125) / 0.04)
        vals.append(np.nan_to_num(a[j0:j1, i0:i1]).ravel())
    v = np.concatenate(vals) if vals else np.zeros(1)
    return {"w1": round(float((v >= 1).mean()), 3), "w5": round(float((v >= 5).mean()), 3), "max": round(float(v.max()), 1)}


def main():
    a, b, cells_p, out_p = sys.argv[1:5]
    cells = json.load(open(cells_p))
    res = {}
    d = date.fromisoformat(a)
    while d <= date.fromisoformat(b):
        try:
            x = obs_rain.pdir_day(d)
            if x is not None:
                res[d.isoformat()] = {k: {"sea": stats(x, c["sea"]), "coast": stats(x, c["coast"])} for k, c in cells.items()}
            print(d, json.dumps(res.get(d.isoformat()))[:300], flush=True)
        except Exception as e:  # noqa: BLE001
            print(d, "failed", repr(e), flush=True)
        json.dump(res, open(out_p, "w"))
        d += timedelta(days=1)


if __name__ == "__main__":
    main()
