#!/usr/bin/env python3
"""Dec 1997 and Jan 1998 (Fahad, 20 Nov 2026): how wet were they in the Hijaz and across the Kingdom, and what brought
the rain. Hijaz: the hj-* chunks of the Hijaz study (CHIRPS 0.05 daily + NCEP R1). Kingdom: CHIRPS monthly regional
means from the IRI library, 1981-2025."""
import os, subprocess, sys, time
from datetime import date
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hijaz_study as H

MON = {(1997, 10): "أكتوبر ٩٧", (1997, 11): "نوفمبر ٩٧", (1997, 12): "ديسمبر ٩٧", (1998, 1): "يناير ٩٨",
       (1998, 2): "فبراير ٩٨", (1998, 3): "مارس ٩٨"}
REG = {"مكة والحجاز": (20, 23, 39, 42), "الباحة وعسير": (17.5, 20.5, 41, 44), "جازان": (16.3, 17.8, 42.4, 43.6),
       "نجران": (17, 18.5, 43.5, 47), "المدينة": (23, 26.5, 37.5, 41), "تبوك": (26.5, 30, 35, 39),
       "حائل والقصيم": (25, 28.5, 40, 44.5), "الرياض والوسطى": (22.5, 26.5, 44, 48), "الشرقية": (22, 28.5, 48, 51),
       "الجوف والحدود الشمالية": (29, 32, 37, 44)}


def hijaz(dirn):
    D = H.load(dirn)
    days = D["days"]; nd = len(days)
    mon = np.array([d.month for d in days]); yr = np.array([d.year for d in days])
    R = D["rain"]; la, lo = D["la"], D["lo"]
    land = np.isfinite(R).mean(0) > 0.9
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    cm = {c: land & (LA >= s) & (LA <= n) & (LO >= w) & (LO <= e) for c, (s, n, w, e) in H.CITIES.items()}
    city = {c: np.nanmean(R[:, m], 1) for c, m in cm.items()}
    regm = np.nanmean(R[:, land], 1); regc = np.nanmean(R[:, land] >= 1, 1)
    ula, ulo = D["ula"], D["ulo"]
    z5a, _ = H.anomalies(D["z5"], days); t5a, _ = H.anomalies(D["t5"], days)
    pw = D["pw"]; _, pwc = H.anomalies(pw, days)
    jb = (ula >= 17.5) & (ula <= 27.5); ib = (ulo >= 35) & (ulo <= 42.5)
    zb = z5a[:, jb][:, :, ib].reshape(nd, -1).mean(1); tb = t5a[:, jb][:, :, ib].reshape(nd, -1).mean(1)
    jm = int(np.argmin(np.abs(ula - 21.25))); im = int(np.argmin(np.abs(ulo - 40.0)))
    pwp = 100 * pw[:, jm, im] / np.maximum(pwc[:, jm, im], 1)
    zp = np.concatenate([[0], zb[:-1]]); tp = np.concatenate([[0], tb[:-1]])
    trough = (np.minimum(zb, zp) <= -20) | (np.minimum(tb, tp) <= -1.5)
    moist = pwp >= 130
    years = sorted(set(yr))
    print("\n#### Hijaz months: city mm (normal mm, rank of N years) | rain days | region mean mm | region wide days (>=40%)"
          " | trough days | moist days | mean PW% | mean z500 anom")
    for (Y, M), name in MON.items():
        q = (yr == Y) & (mon == M)
        print(f"\n  {name}:")
        for c, x in city.items():
            tot = np.nansum(x[q])
            per = [np.nansum(x[(yr == y) & (mon == M)]) for y in years]
            rank = 1 + sum(v > tot for v in per)
            print(f"    {c}: {tot:6.1f} mm (normal {np.mean(per):5.1f}, rank {rank}/{len(per)}) | rain days {(x[q] >= 1).sum()}")
        per = [np.nansum(regm[(yr == y) & (mon == M)]) for y in years]
        wd = [(regc[(yr == y) & (mon == M)] >= 0.4).sum() for y in years]
        trn = [trough[(yr == y) & (mon == M)].sum() for y in years]; mo = [moist[(yr == y) & (mon == M)].sum() for y in years]
        print(f"    region: {np.nansum(regm[q]):5.1f} mm (normal {np.mean(per):5.1f}, rank {1 + sum(v > np.nansum(regm[q]) for v in per)})"
              f" | wide days {(regc[q] >= 0.4).sum()} (normal {np.mean(wd):.1f}) | trough days {trough[q].sum()} (normal {np.mean(trn):.1f})"
              f" | moist days {moist[q].sum()} (normal {np.mean(mo):.1f}) | PW {np.mean(pwp[q]):.0f}% | z500 {np.mean(zb[q]):+.0f} m | T500 {np.mean(tb[q]):+.1f}")
    print("\n#### Rain days Dec 97 - Jan 98 (region >= 5% wet or a city >= 1 mm): date | Taif Makkah Jumum Jeddah mm |"
          " region wet % | z500 anom | T500 anom | PW %")
    for i, d in enumerate(days):
        if (d.year, d.month) in ((1997, 11), (1997, 12), (1998, 1)):
            cs = [city[c][i] for c in H.CITIES]
            if regc[i] >= 0.05 or max(cs) >= 1:
                print(f"    {d} | " + " ".join(f"{v:5.1f}" for v in cs) + f" | {100*regc[i]:3.0f}% | {zb[i]:+4.0f} | {tb[i]:+4.1f} | {pwp[i]:4.0f}%")


def kingdom():
    import netCDF4
    print("\n#### Kingdom regions, CHIRPS monthly mm: month value (percent of 1991-2020 normal, rank of 1981-2025)")
    for name, (s, n, w, e) in REG.items():
        url = (f"https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/.monthly/.global/.precipitation/"
               f"X/{w}/{e}/RANGEEDGES/Y/{s}/{n}/RANGEEDGES/T/(Jan 1981)/(Dec 2025)/RANGEEDGES/%5BX/Y%5Daverage/data.nc")
        for k in range(4):
            r = subprocess.run(["curl", "-sfL", "-m", "600", "-o", "/tmp/r.nc", url])
            if r.returncode == 0 and os.path.getsize("/tmp/r.nc") > 500:
                break
            time.sleep(20 * (k + 1))
        else:
            print("  ", name, "failed"); continue
        with netCDF4.Dataset("/tmp/r.nc") as nc:
            t = np.asarray(nc["T"][:], float); v = np.ma.filled(nc["precipitation"][:].astype(float), np.nan).ravel()
        # IRI monthly T = months since 1960-01-01
        ym = [(1960 + int(x) // 12, int(x) % 12 + 1) for x in np.floor(t)]
        val = dict(zip(ym, v))
        line = []
        for (Y, M), mn in MON.items():
            x = val.get((Y, M), np.nan)
            allv = [val[(y, M)] for y in range(1981, 2026) if (y, M) in val]
            nrm = np.nanmean([val[(y, M)] for y in range(1991, 2021) if (y, M) in val])
            rk = 1 + sum(a > x for a in allv)
            line.append(f"{mn} {x:5.1f} ({100*x/max(nrm,1e-6):4.0f}%, {rk}/{len(allv)})")
        dj = val.get((1997, 12), 0) + val.get((1998, 1), 0)
        djs = sorted([val.get((y, 12), 0) + val.get((y + 1, 1), 0) for y in range(1981, 2025)], reverse=True)
        print(f"  {name}: " + " | ".join(line) + f" | Dec+Jan rank {1 + sum(a > dj for a in djs)}/{len(djs)}", flush=True)


if __name__ == "__main__":
    try:
        kingdom()
    except Exception as ex:  # noqa: BLE001
        print("kingdom failed", repr(ex))
    hijaz(sys.argv[1])
