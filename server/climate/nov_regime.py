#!/usr/bin/env python3
"""November rain around Makkah by regime (Fahad, 16 Nov 2026: historically, what share of November rain around Makkah
comes from the summer-type convective regime, with no upper trough, against troughs and cut-off lows).

    nov_regime.py fetch FIRST_YEAR LAST_YEAR OUT.json     (one chunk of years; run chunks in parallel)
    nov_regime.py analyse DIR_OF_JSON

Rain: CHIRPS v2 daily, 0.25 degree (IRI library), the Makkah box 20.9-22.0N, 39.4-40.5E (Makkah, Al-Jumum, Bahra,
Al-Shara'i and the foot of the Taif escarpment).
Upper air: NCEP/NCAR reanalysis 1 daily means, 500 hPa height and temperature over 15-27.5N, 35-45E, and the
precipitable water at Makkah. Anomalies against the calendar mean of the whole period plus a linear trend (the
500 hPa heights rise with the warming). Prints to the log, publishes nothing.
"""
import json, os, sys, time
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tropics_long as L  # noqa: E402

BOX = (20.9, 22.0, 39.4, 40.5)
LA0, LA1, LO0, LO1 = 15.0, 27.5, 35.0, 45.0


def ncep_level(var, y, path, level):
    import netCDF4
    err = None
    for base in ("https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis/Dailies",
                 "https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis.dailyavgs"):
        for k in range(4):
            time.sleep(15)
            try:
                with netCDF4.Dataset(f"{base}/{path}") as nc:
                    la, lo = np.asarray(nc["lat"][:], float), np.asarray(nc["lon"][:], float)
                    jj = np.where((la >= LA0) & (la <= LA1))[0]; ii = np.where((lo >= LO0) & (lo <= LO1))[0]
                    if level is None:
                        a = nc[var][:, jj[0]:jj[-1] + 1, ii[0]:ii[-1] + 1]
                    else:
                        lev = list(np.asarray(nc["level"][:], float)).index(float(level))
                        a = nc[var][:, lev, jj[0]:jj[-1] + 1, ii[0]:ii[-1] + 1]
                    return la[jj], lo[ii], np.ma.filled(a.astype(float), np.nan)
            except Exception as e:  # noqa: BLE001
                err = e
                time.sleep(60 * (k + 1))
    print("ncep failed", var, y, repr(err)[:160], flush=True)
    return None


def fetch(y0, y1, outp):
    L.S, L.N, L.W, L.E = 20.5, 22.5, 39.0, 41.0
    rows = []
    for y in range(y0, y1 + 1):
        c = L.chirps_year(y)
        z = ncep_level("hgt", y, f"pressure/hgt.{y}.nc", 500)
        t = ncep_level("air", y, f"pressure/air.{y}.nc", 500)
        w = ncep_level("pr_wtr", y, f"surface/pr_wtr.eatm.{y}.nc", None)
        if z is None or t is None or w is None:
            print("skip", y, flush=True)
            continue
        la, lo, za = z
        rain = {}
        if c is not None:
            dd, cla, clo, p = c
            m = ((cla >= BOX[0]) & (cla <= BOX[1]))[:, None] & ((clo >= BOX[2]) & (clo <= BOX[3]))[None, :]
            for k, d in enumerate(dd):
                if d.month == 11:
                    v = p[k][m]; v = v[np.isfinite(v)]
                    if v.size:
                        rain[d] = (float(v.mean()), float(v.max()), float(np.mean(v >= 5)), int(v.size))
        jm = int(np.argmin(np.abs(la - 21.4))); im = int(np.argmin(np.abs(lo - 40.0)))
        d0 = date(y, 1, 1)
        for kd in range(za.shape[0]):
            d = d0 + timedelta(days=kd)
            if not ((d.month == 10 and d.day >= 15) or d.month == 11 or (d.month == 12 and d.day <= 15)):
                continue
            rows.append({"d": d.isoformat(), "z": np.round(za[kd], 1).tolist(), "t": np.round(t[2][kd], 2).tolist(),
                         "pw": float(w[2][kd][jm, im]), "r": rain.get(d)})
        print("year", y, "rain days", len(rain), "grid", la.tolist(), lo.tolist(), flush=True)
    json.dump({"la": la.tolist(), "lo": lo.tolist(), "rows": rows}, open(outp, "w"))


def analyse(dirn):
    import glob
    rows, la, lo = [], None, None
    for p in sorted(glob.glob(os.path.join(dirn, "**", "*.json"), recursive=True)):
        j = json.load(open(p)); rows += j["rows"]; la, lo = np.array(j["la"]), np.array(j["lo"])
    for r in rows:
        r["d"] = date.fromisoformat(r["d"])
    rows.sort(key=lambda r: r["d"])
    d = [r["d"] for r in rows]
    yr = np.array([x.year for x in d]); doy = np.array([x.timetuple().tm_yday for x in d])
    Z = np.array([r["z"] for r in rows]); T = np.array([r["t"] for r in rows]); PW = np.array([r["pw"] for r in rows])

    def anom(F):
        A = np.empty_like(F)
        for k in range(len(d)):
            s = np.abs(doy - doy[k]) <= 10
            A[k] = F[k] - F[s].mean(0)
        # remove the linear trend over the years of the box mean
        bm = A.reshape(len(d), -1).mean(1)
        a, b = np.polyfit(yr, bm, 1)
        return A - (a * yr + b)[:, None, None]
    ZA, TA = anom(Z), anom(T)
    pwc = np.array([PW[np.abs(doy - doy[k]) <= 10].mean() for k in range(len(d))]); PWP = 100 * PW / pwc
    # the trough box: 17.5-27.5N, 35-42.5E (over and upstream of Makkah), area-mean anomaly
    jb = (la >= 17.5) & (la <= 27.5); ib = (lo >= 35) & (lo <= 42.5)
    zmin = ZA[:, jb][:, :, ib].reshape(len(d), -1).mean(1)
    tmin = TA[:, jb][:, :, ib].reshape(len(d), -1).mean(1)
    # the day itself or the day before (a trough passing in the night still counts)
    zmin2 = np.minimum(zmin, np.r_[zmin[0], zmin[:-1]]); tmin2 = np.minimum(tmin, np.r_[tmin[0], tmin[:-1]])
    nov = np.array([x.month == 11 and r["r"] is not None for x, r in zip(d, rows)])
    R = np.array([r["r"][0] if r["r"] else np.nan for r in rows]); MX = np.array([r["r"][1] if r["r"] else np.nan for r in rows])
    print("Novembers:", sorted(set(yr[nov])), "days", nov.sum(), "cells", rows[np.where(nov)[0][0]]["r"][3])
    print(f"Nov total rain, box mean: {np.nansum(R[nov]) / len(set(yr[nov])):.1f} mm per November")
    print("trough strength percentiles on Nov days (zmin2):", np.percentile(zmin2[nov], [5, 10, 25, 50, 75]).round(0))

    def table(name, trough, weak):
        conv = nov & ~trough & ~weak
        out = []
        for lab, s in (("trough", nov & trough), ("weak", nov & weak), ("none (convective)", conv)):
            out.append(f"{lab}: days {100*s.sum()/nov.sum():.0f}%  rain {100*np.nansum(R[s])/np.nansum(R[nov]):.0f}%  "
                       f"raindays(>=1mm mean) {100*np.sum(s&(R>=1))/np.sum(nov&(R>=1)):.0f}%  "
                       f"heavy(max>=20) {100*np.sum(s&(MX>=20))/max(1,np.sum(nov&(MX>=20))):.0f}%  "
                       f"P(raindays) {100*np.mean(R[s]>=1):.1f}%  PW% {np.nanmean(PWP[s]):.0f}")
        print(f"\n## {name}\n  " + "\n  ".join(out))
    for zs, zw in ((-30, -15), (-40, -20), (-20, -10), (-25, -10)):
        table(f"strong <= {zs} m (or <= {zw} m with T500 <= -1.5 K), weak {zs}..{zw} m, day or day before",
              (zmin2 <= zs) | ((zmin2 <= zw) & (tmin2 <= -1.5)), (zmin2 > zs) & (zmin2 <= zw) & ~((zmin2 <= zw) & (tmin2 <= -1.5)))
    table("same day only, strong <= -30, weak -30..-15", zmin <= -30, (zmin > -30) & (zmin <= -15))
    # wet days listed
    print("\nwet days (box mean >= 3 mm): date, mean, max, zmin2, tmin2, PW%")
    for k in np.where(nov & (R >= 3))[0]:
        print(f"  {d[k]}  {R[k]:5.1f} {MX[k]:5.1f}  z{zmin2[k]:5.0f}  t{tmin2[k]:5.1f}  pw{PWP[k]:4.0f}")
    # by decade and by half of the month
    s0 = (zmin2 <= -30) | ((zmin2 <= -15) & (tmin2 <= -1.5)); w0 = (zmin2 > -30) & (zmin2 <= -15) & ~s0
    c0 = nov & ~s0 & ~w0
    for lab, f in (("1981-1995", yr <= 1995), ("1996-2010", (yr > 1995) & (yr <= 2010)), ("2011-2025", yr > 2010),
                   ("Nov 1-15", np.array([x.day <= 15 for x in d])), ("Nov 16-30", np.array([x.day > 15 for x in d]))):
        q = nov & f
        print(f"{lab}: rain {np.nansum(R[q])/len(set(yr[q])):.1f} mm/Nov, convective share "
              f"{100*np.nansum(R[c0&f])/np.nansum(R[q]):.0f}%, weak {100*np.nansum(R[w0&f])/np.nansum(R[q]):.0f}%, "
              f"trough {100*np.nansum(R[s0&f])/np.nansum(R[q]):.0f}%")
    # the share of each November's rain, year by year
    print("\nby year: total mm, convective %, trough %")
    for y in sorted(set(yr[nov])):
        q = nov & (yr == y); tot = np.nansum(R[q])
        if tot >= 2:
            print(f"  {y}: {tot:6.1f}  conv {100*np.nansum(R[q&c0])/tot:3.0f}  weak {100*np.nansum(R[q&w0])/tot:3.0f}  trough {100*np.nansum(R[q&s0])/tot:3.0f}")


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    else:
        analyse(sys.argv[2])
