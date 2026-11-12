#!/usr/bin/env python3
"""Past GFS fields over Saudi Arabia, to calibrate the rain-spread potential index (ingredients.py).

    ingr_backfill.py OUT_DIR DAYS STEP LEADS

For each day D (yesterday back DAYS days, every STEP days) and each lead k in LEADS (days): the GFS run of
D-k 00 UTC, its fields valid D 12 UTC (the afternoon, when the convection is) and its rain over day D (00 to
24 UTC). Lead 0 gives the reference rain of the day (the first-day forecast, as in mjofilt). One npz per
(D, k) in OUT_DIR, on the 1 degree grid over the box of ingredients.BOX.
"""
import os, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402
import ingredients as ING  # noqa: E402


def one(D, k, out):
    p = os.path.join(out, f"{D:%Y%m%d}_{k}.npz")
    if os.path.exists(p):
        return "have"
    cyc = (D - timedelta(days=k)).strftime("%Y%m%d") + "00"
    for t in range(3):
        try:
            f = daily.gfs_fields(cyc, 24 * k + 12, fields=ING.FIELDS)
            a1 = daily.gfs_fields(cyc, 24 * k + 24, fields=[ING.APCP])["apcp"]
            a0 = daily.gfs_fields(cyc, 24 * k, fields=[ING.APCP])["apcp"] if k else 0.0
            rain = np.maximum(a1 - a0, 0)
            sub = {n: ING.cut(v).astype(np.float32) for n, v in f.items()}
            sub["rain"] = ING.cut(rain).astype(np.float32)
            np.savez_compressed(p, **sub)
            return "ok"
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:160]
            time.sleep(5 * (t + 1))
    return "fail " + err


def main():
    out, days, step = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    leads = [int(x) for x in sys.argv[4].split(",")]
    os.makedirs(out, exist_ok=True)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    jobs = [(today - timedelta(days=n), k) for n in range(1, days + 1, step) for k in leads]
    done = 0
    with ThreadPoolExecutor(8) as ex:
        for (D, k), r in zip(jobs, ex.map(lambda j: one(j[0], j[1], out), jobs)):
            done += 1
            if not r.startswith(("ok", "have")) or done % 50 == 0:
                print(done, len(jobs), f"{D:%Y-%m-%d}", k, r, flush=True)
    print("done", len(os.listdir(out)), "files", flush=True)


if __name__ == "__main__":
    main()
