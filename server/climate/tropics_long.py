#!/usr/bin/env python3
"""The long test (Fahad, 15 Nov 2026): over 25 wet seasons (November to April, 2001-2026), how much of the rain over
each part of the Kingdom the tropical system explains, against troughs and moisture surges.

Rain: CHIRPS v2 daily, 0.25 degree (satellite and gauges, through the IRI data library), share of each part with 5 mm or more, and mean rain.
Tropics: the RMM (Wheeler-Hendon, BoM) phase and amplitude; ENSO (Nino 3.4) and the Indian Ocean Dipole (monthly).
Troughs and moisture: NCEP/NCAR reanalysis 1 daily 500 hPa height and precipitable water over each part, as
departures from their 31-day running mean (the passing troughs and surges).

    tropics_long.py FIRST_YEAR LAST_YEAR OUT_JSON
Prints the tables; writes the daily series to OUT_JSON for later use.
"""
import json, os, subprocess, sys, time
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GROUPS = {"الحجاز": [3, 2], "الجنوب الغربي": [9, 11, 12, 8], "الشمال": [7, 6, 4, 5], "الوسط": [1, 10],
          "الشرق": [0], "المملكة": list(range(13))}
WET = (11, 12, 1, 2, 3, 4)
S, N, W, E = 15.0, 33.0, 34.0, 56.0


def sh(cmd):
    return subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)


def chirps_year(y, tmp="/tmp/ch.nc"):
    """the wet months of year y (January to April, November and December) of CHIRPS v2 over the Kingdom, cut on the
    server of the IRI data library (the CHC moved its version 2 files away, 15 Nov 2026)"""
    import netCDF4
    days, parts = [], []
    for a, b in ((f"1 Jan {y}", f"30 Apr {y}"), (f"1 Nov {y}", f"31 Dec {y}")):
        url = ("https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/.daily-improved/.global/.0p25/.prcp/"
               f"X/{W}/{E}/RANGEEDGES/Y/{S}/{N}/RANGEEDGES/T/({a})/({b})/RANGEEDGES/data.nc").replace(" ", "%20")
        for k in range(4):
            r = sh(f"curl -sfL -m 1200 -o {tmp} '{url}'")
            if r.returncode == 0 and os.path.getsize(tmp) > 1e4:
                break
            time.sleep(30 * (k + 1))
        else:
            print("chirps failed", y, a, flush=True)
            continue
        with netCDF4.Dataset(tmp) as nc:
            la, lo = np.asarray(nc["Y"][:], float), np.asarray(nc["X"][:], float)
            t = nc["T"]
            dd = netCDF4.num2date(t[:], t.units, getattr(t, "calendar", "standard"))
            p = np.ma.filled(nc["prcp"][:].astype(float), np.nan)
        if la[0] > la[-1]:
            la, p = la[::-1], p[:, ::-1]
        days += [date(x.year, x.month, x.day) for x in dd]; parts.append(p)
        os.remove(tmp)
    if not parts:
        return None
    return days, la, lo, np.concatenate(parts)


def ncep(var, y, path):
    import netCDF4
    for base in ("https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis/Dailies",
                 "https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis.dailyavgs"):
        for k in range(4):
            time.sleep(15)        # the PSL server answers too many requests with 429
            try:
                with netCDF4.Dataset(f"{base}/{path}") as nc:
                    la, lo = nc["lat"][:], nc["lon"][:]
                    jj = np.where((la >= S - 5) & (la <= N + 5))[0]; ii = np.where((lo >= W - 5) & (lo <= E + 5))[0]
                    if var == "hgt":
                        lev = list(nc["level"][:]).index(500)
                        a = nc[var][:, lev, jj[0]:jj[-1] + 1, ii[0]:ii[-1] + 1]
                    else:
                        a = nc[var][:, jj[0]:jj[-1] + 1, ii[0]:ii[-1] + 1]
                    return la[jj], lo[ii], np.ma.filled(a.astype(float), np.nan)
            except Exception as e:  # noqa: BLE001
                err = e
                time.sleep(60 * (k + 1))
    print("ncep failed", var, y, repr(err)[:120], flush=True)
    return None


def monthly_index(url, cols=12):
    """{(year, month): value} from a PSL-style monthly text table"""
    r = sh(f"curl -sfL -m 60 '{url}'")
    out = {}
    for line in r.stdout.splitlines():
        p = line.split()
        if len(p) == cols + 1 and p[0].isdigit() and len(p[0]) == 4:
            for m in range(cols):
                v = float(p[m + 1])
                if abs(v) < 90:
                    out[(int(p[0]), m + 1)] = v
    return out


def running(x, n=31):
    x = np.asarray(x, float); k = n // 2
    c = np.convolve(np.nan_to_num(x), np.ones(n), "same"); m = np.convolve(np.isfinite(x).astype(float), np.ones(n), "same")
    return c / np.maximum(m, 1)


def cv_r2(X, y, groups):
    X = np.column_stack([np.ones(len(y)), X]); pred = np.full(len(y), np.nan)
    for g in sorted(set(groups)):
        tr, te = groups != g, groups == g
        A = X[tr]; mu = A[:, 1:].mean(0); sd = A[:, 1:].std(0) + 1e-9
        As = A.copy(); As[:, 1:] = (A[:, 1:] - mu) / sd
        Xs = X[te].copy(); Xs[:, 1:] = (Xs[:, 1:] - mu) / sd
        lam = np.eye(X.shape[1]); lam[0, 0] = 0
        b = np.linalg.solve(As.T @ As + lam, As.T @ y[tr]); pred[te] = Xs @ b
    ok = np.isfinite(pred)
    return 1 - np.sum((y[ok] - pred[ok]) ** 2) / np.sum((y[ok] - y[ok].mean()) ** 2)


def main():
    y0, y1, outp = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    import sa_geo, daily
    regs = sa_geo.regions()
    rmm = {d: (r1, r2, ph, amp) for d, r1, r2, ph, amp in daily.read_rmm()}
    nino = monthly_index("https://psl.noaa.gov/data/correlation/nina34.anom.data")
    dmi = monthly_index("https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data")
    print("rmm days", len(rmm), "nino months", len(nino), "dmi months", len(dmi), flush=True)
    rows = []
    mask_c = mask_n = None
    for y in range(y0, y1 + 1):
        c = chirps_year(y)
        hg = ncep("hgt", y, f"pressure/hgt.{y}.nc")
        pw = ncep("pr_wtr", y, f"surface/pr_wtr.eatm.{y}.nc")
        if c is None:
            continue
        days, la, lo, p = c
        if mask_c is None:
            LA, LO = np.meshgrid(la, lo, indexing="ij")
            mask_c = sa_geo.region_of_points(regs, LA.ravel(), LO.ravel()).reshape(LA.shape)
            wc = np.cos(np.radians(LA))
        if hg is not None and mask_n is None:
            LA2, LO2 = np.meshgrid(hg[0], hg[1], indexing="ij")
            # each part of the Kingdom at 2.5 degrees: the reanalysis points within 1.5 degrees of the part's points
            mask_n = {}
            for g, ids in GROUPS.items():
                pts = np.argwhere(np.isin(mask_c, ids))
                pl, po = la[pts[:, 0]], lo[pts[:, 1]]
                near = np.zeros(LA2.shape, bool)
                for a, b in zip(pl[::8], po[::8]):
                    near |= (abs(LA2 - a) <= 1.3) & (abs(LO2 - b) <= 1.3)
                mask_n[g] = near
        for k, d in enumerate(days):
            if d.month not in WET:
                continue
            kd = (d - date(y, 1, 1)).days       # the day's place in the reanalysis files of the year
            r = {"d": d.isoformat()}
            pk = p[k]
            for g, ids in GROUPS.items():
                m = np.isin(mask_c, ids) & np.isfinite(pk)
                if m.sum() == 0:
                    continue
                r[g] = [round(float((wc * (pk >= 5))[m].sum() / wc[m].sum()), 4), round(float((wc * pk)[m].sum() / wc[m].sum()), 3)]
                if hg is not None and pw is not None and kd < hg[2].shape[0] and kd < pw[2].shape[0]:
                    r[g] += [round(float(np.nanmean(hg[2][kd][mask_n[g]])), 1), round(float(np.nanmean(pw[2][kd][mask_n[g]])), 2)]
            if d in rmm:
                r["rmm"] = list(rmm[d])
            r["nino"] = nino.get((d.year, d.month)); r["dmi"] = dmi.get((d.year, d.month))
            rows.append(r)
        print("year", y, "rows", len(rows), "ncep", hg is not None and pw is not None, flush=True)
    json.dump(rows, open(outp, "w"))
    analyse(rows)


def analyse(rows):
    rows = [r for r in rows if "rmm" in r and all(g in r for g in GROUPS)]
    days = [date.fromisoformat(r["d"]) for r in rows]
    season = np.array([d.year if d.month >= 11 else d.year - 1 for d in days])
    print(f"\nwet-season days {len(rows)}, seasons {season.min()}-{season.max()+1} ({len(set(season))})")
    amp = np.array([r["rmm"][3] for r in rows]); ph = np.array([r["rmm"][2] for r in rows])
    fav = np.where(np.isin(ph, [7, 8, 1, 2]) & (amp >= 1), amp, 0.0)
    nino = np.array([r["nino"] if r["nino"] is not None else np.nan for r in rows])
    dmi = np.array([r["dmi"] if r["dmi"] is not None else np.nan for r in rows])
    T = np.column_stack([[r["rmm"][0] for r in rows], [r["rmm"][1] for r in rows], fav, np.nan_to_num(nino), np.nan_to_num(dmi)])
    has_syn = all(len(rows[0][g]) == 4 for g in GROUPS)

    print("\n== 1. Daily (cross-validated, leave one season out): share of the day-to-day rain explained")
    for g in GROUPS:
        y = np.sqrt(np.array([r[g][0] for r in rows]))
        rt = cv_r2(T, y, season)
        line = f"{g}: tropics {100*rt:5.1f}%"
        if has_syn:
            z = np.array([r[g][2] for r in rows]); pw = np.array([r[g][3] for r in rows])
            Es = np.column_stack([z - running(z), pw - running(pw), pw])
            re = cv_r2(Es, y, season); rb = cv_r2(np.hstack([T, Es]), y, season)
            line += f"  troughs+moisture {100*re:5.1f}%  both {100*rb:5.1f}%"
        print(line + f"  (mean daily spread {100*np.mean(np.array([r[g][0] for r in rows])):.1f}%)")

    print("\n== 2. Monthly (each month of each season): correlation of the month's rain with the tropical drivers,"
          " and cross-validated R2 of the tropics together")
    keys = sorted({(d.year, d.month) for d in days})
    for g in GROUPS:
        ym = {k: [] for k in keys}
        for r, d in zip(rows, days):
            ym[(d.year, d.month)].append(r)
        rain = np.array([np.mean([r[g][1] for r in ym[k]]) for k in keys])
        favm = np.array([np.mean([1.0 if (r["rmm"][2] in (7, 8, 1, 2) and r["rmm"][3] >= 1) else 0.0 for r in ym[k]]) for k in keys])
        ampm = np.array([np.mean([r["rmm"][3] if (r["rmm"][2] in (7, 8, 1, 2)) else -r["rmm"][3] for r in ym[k]]) for k in keys])
        nm = np.array([ym[k][0]["nino"] if ym[k][0]["nino"] is not None else np.nan for k in keys])
        dm = np.array([ym[k][0]["dmi"] if ym[k][0]["dmi"] is not None else np.nan for k in keys])
        mo = np.array([k[1] for k in keys]); se = np.array([k[0] if k[1] >= 11 else k[0] - 1 for k in keys])
        # remove each calendar month's own mean (the season) before correlating
        anom = rain.copy()
        for m_ in set(mo):
            anom[mo == m_] -= rain[mo == m_].mean()
        cor = lambda x: np.corrcoef(x[np.isfinite(x)], anom[np.isfinite(x)])[0, 1]
        X = np.column_stack([favm, ampm, np.nan_to_num(nm), np.nan_to_num(dm)])
        r2 = cv_r2(X, anom, se)
        print(f"{g}: n={len(keys)} months | corr with: favourable-MJO days {cor(favm):+.2f}, signed MJO amplitude {cor(ampm):+.2f}, "
              f"ENSO {cor(nm):+.2f}, IOD {cor(dm):+.2f} | tropics together explain {100*r2:.0f}% (cross-validated)")

    print("\n== 3. Mean daily rain spread (%) by MJO phase (amplitude 1 or more), and on weak-MJO days")
    for part in (("نوفمبر-يناير", (11, 12, 1)), ("فبراير-أبريل", (2, 3, 4))):
        print(" ", part[0])
        sel = np.array([d.month in part[1] for d in days])
        for g in GROUPS:
            y = np.array([r[g][0] for r in rows])
            base = 100 * y[sel].mean()
            cells = []
            for p_ in range(1, 9):
                s = sel & (ph == p_) & (amp >= 1)
                cells.append(f"{p_}:{100*y[s].mean():4.1f}({100*y[s].mean()/max(base,1e-6):.0%})" if s.sum() >= 20 else f"{p_}: -")
            s = sel & (amp < 1)
            print(f"   {g}: all {base:.1f} | " + " ".join(cells) + f" | weak {100*y[s].mean():.1f}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--analyse":
        analyse(json.load(open(sys.argv[2])))
    else:
        main()
