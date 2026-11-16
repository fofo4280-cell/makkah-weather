#!/usr/bin/env python3
"""Historical study of rain in the Hijaz (Fahad, 17 Nov 2026): Taif, Makkah, Al-Jumum and Jeddah, month by month.
For each city and month: how much, how often, how heavy; how much of the city and of the region gets rain on its rain
days; what kind of weather brings it (upper trough / cold aloft, or convection with no trough; moisture; the 700 hPa
steering wind); how the cities rain together; and which large-scale drivers favour each month (MJO phase, ENSO, IOD).

    hijaz_study.py fetch FIRST_YEAR LAST_YEAR OUT.npz   (one chunk of years; chunks run in parallel)
    hijaz_study.py analyse DIR                           (all chunks; prints the tables and writes hijaz.json)

Rain: CHIRPS v2 daily, 0.05 degree (IRI data library), 20.2-22.4N, 38.8-41.0E (0.25 degree if 0.05 fails).
Upper air: NCEP/NCAR reanalysis 1 daily means (PSL): 500 hPa height and temperature, precipitable water, 700 hPa wind
and relative humidity. RMM (BoM), Nino 3.4 and DMI (PSL). Station records for these cities are too broken in the
public archives (GHCN/GSOD) to use; CHIRPS is known to under-read Makkah's rain (about a third of the station normal
in November), so amounts are relative, while frequencies, spread and causes are the useful part.
"""
import glob, json, os, subprocess, sys, time
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BOX = (20.2, 22.4, 38.8, 41.0)                     # south, north, west, east
UP = (10.0, 35.0, 30.0, 50.0)                      # the upper-air window
CITIES = {                                         # south, north, west, east (degrees)
    "الطائف": (21.18, 21.38, 40.33, 40.53),
    "مكة": (21.33, 21.50, 39.75, 39.95),
    "الجموم": (21.55, 21.72, 39.62, 39.80),
    "جدة": (21.35, 21.78, 39.10, 39.28),
}
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def chirps_year(y, res="0p05", tmp="/tmp/hj.nc"):
    import netCDF4
    s, n, w, e = BOX
    url = (f"https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/.daily-improved/.global/.{res}/.prcp/"
           f"X/{w}/{e}/RANGEEDGES/Y/{s}/{n}/RANGEEDGES/T/(1 Jan {y})/(31 Dec {y})/RANGEEDGES/data.nc").replace(" ", "%20")
    for k in range(4):
        r = sh(f"curl -sfL -m 1500 -o {tmp} '{url}'")
        if r.returncode == 0 and os.path.getsize(tmp) > 1e4:
            break
        time.sleep(30 * (k + 1))
    else:
        return None
    with netCDF4.Dataset(tmp) as nc:
        la, lo = np.asarray(nc["Y"][:], float), np.asarray(nc["X"][:], float)
        t = nc["T"]
        tv, un = np.asarray(t[:], float), str(getattr(t, "units", ""))
        if "julian" in un.lower():                  # the IRI library counts julian days
            dd = [date.fromordinal(int(round(v - 1721424.5))) for v in tv]
        else:
            try:
                dd = netCDF4.num2date(tv, un, getattr(t, "calendar", "standard"))
            except ValueError:                      # an odd unit: the days run on from 1 January
                dd = [date(y, 1, 1) + timedelta(days=i) for i in range(len(tv))]
        p = np.ma.filled(nc["prcp"][:].astype(np.float32), np.nan)
    if dd[0].year != y or dd[0].month != 1 or dd[0].day != 1:
        print("chirps dates odd", y, un, dd[0], "-> counted from 1 January", flush=True)
        dd = [date(y, 1, 1) + timedelta(days=i) for i in range(len(tv))]
    os.remove(tmp)
    if la[0] > la[-1]:
        la, p = la[::-1], p[:, ::-1]
    return [date(x.year, x.month, x.day) for x in dd], la, lo, p


def ncep(var, path, level):
    import netCDF4
    err = None
    s, n, w, e = UP
    for base in ("https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis/Dailies",
                 "https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis.dailyavgs"):
        for k in range(4):
            time.sleep(12)
            try:
                with netCDF4.Dataset(f"{base}/{path}") as nc:
                    la, lo = np.asarray(nc["lat"][:], float), np.asarray(nc["lon"][:], float)
                    jj = np.where((la >= s) & (la <= n))[0]; ii = np.where((lo >= w) & (lo <= e))[0]
                    if level is None:
                        a = nc[var][:, jj[0]:jj[-1] + 1, ii[0]:ii[-1] + 1]
                    else:
                        lev = list(np.asarray(nc["level"][:], float)).index(float(level))
                        a = nc[var][:, lev, jj[0]:jj[-1] + 1, ii[0]:ii[-1] + 1]
                    return la[jj], lo[ii], np.ma.filled(a.astype(np.float32), np.nan)
            except Exception as ex:  # noqa: BLE001
                err = ex
                time.sleep(45 * (k + 1))
    print("ncep failed", var, path, repr(err)[:160], flush=True)
    return None


NCEP = [("z5", "hgt", "pressure/hgt.{y}.nc", 500), ("t5", "air", "pressure/air.{y}.nc", 500),
        ("pw", "pr_wtr", "surface/pr_wtr.eatm.{y}.nc", None), ("u7", "uwnd", "pressure/uwnd.{y}.nc", 700),
        ("v7", "vwnd", "pressure/vwnd.{y}.nc", 700), ("rh7", "rhum", "pressure/rhum.{y}.nc", 700)]


def fetch(y0, y1, outp):
    out = {"days": [], "rain": [], "res": None}
    up = {k: [] for k, *_ in NCEP}
    for y in range(y0, y1 + 1):
        c = chirps_year(y)
        res = "0p05"
        if c is None:
            c, res = chirps_year(y, "0p25"), "0p25"
        u = {}
        for key, var, path, lev in NCEP:
            r = ncep(var, path.format(y=y), lev)
            if r is None:
                break
            u[key] = r
        if c is None or len(u) < len(NCEP):
            print("skip year", y, "chirps", c is not None, "ncep", list(u), flush=True)
            continue
        dd, la, lo, p = c
        n = min(len(dd), len(u["z5"][2]))
        out["days"] += [d.isoformat() for d in dd[:n]]
        out["rain"].append(np.round(np.nan_to_num(p[:n], nan=-1) * 10).astype(np.int16))
        out["res"] = res
        out["la"], out["lo"] = la, lo
        for key in up:
            up[key].append(u[key][2][:n])
        out["ula"], out["ulo"] = u["z5"][0], u["z5"][1]
        print("year", y, res, "days", n, "rain grid", p.shape, flush=True)
    np.savez_compressed(outp, days=np.array(out["days"]), rain=np.concatenate(out["rain"]), la=out["la"], lo=out["lo"],
                        ula=out["ula"], ulo=out["ulo"], res=out["res"],
                        **{k: np.concatenate(v).astype(np.float32) for k, v in up.items()})


def load(dirn):
    parts = sorted(glob.glob(os.path.join(dirn, "**", "*.npz"), recursive=True))
    Z = [dict(np.load(p, allow_pickle=True)) for p in parts]
    Z = [z for z in Z if len(z["days"])]
    days = [date.fromisoformat(str(d)) for z in Z for d in z["days"]]
    o = np.argsort([d.toordinal() for d in days])
    cat = lambda k: np.concatenate([z[k] for z in Z])[o]
    D = {"days": [days[i] for i in o], "rain": cat("rain").astype(np.float32) / 10}
    D["rain"][D["rain"] < 0] = np.nan
    for k, *_ in NCEP:
        D[k] = cat(k)
    D.update(la=Z[0]["la"], lo=Z[0]["lo"], ula=Z[0]["ula"], ulo=Z[0]["ulo"], res=str(Z[0]["res"]))
    print("days", len(D["days"]), D["days"][0], D["days"][-1], "res", D["res"], "rain grid", D["rain"].shape, flush=True)
    return D


def anomalies(F, days):
    """minus the calendar mean (+-10 days) and the linear trend over the years"""
    doy = np.array([d.timetuple().tm_yday for d in days]); yr = np.array([d.year + d.timetuple().tm_yday / 366 for d in days])
    clim = np.empty_like(F)
    for k in range(1, 367):
        s = np.abs(((doy - k + 183) % 366) - 183) <= 10
        clim[doy == k] = F[s].mean(0)
    A = F - clim
    bm = A.reshape(len(days), -1).mean(1)
    a, b = np.polyfit(yr, bm, 1)
    return A - (a * yr + b).reshape((-1,) + (1,) * (F.ndim - 1)), clim


def analyse(dirn):
    import tropics_long as L
    import daily
    D = load(dirn)
    days = D["days"]; nd = len(days)
    mon = np.array([d.month for d in days]); yr = np.array([d.year for d in days])
    R = D["rain"]; la, lo = D["la"], D["lo"]
    land = np.isfinite(R).mean(0) > 0.9
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    cm = {c: land & (LA >= s) & (LA <= n) & (LO >= w) & (LO <= e) for c, (s, n, w, e) in CITIES.items()}
    for c, m in cm.items():
        print("city", c, "points", int(m.sum()), flush=True)
    reg = land
    city_mean = {c: np.nanmean(R[:, m], 1) for c, m in cm.items()}
    city_cov = {c: np.nanmean(R[:, m] >= 1, 1) for c, m in cm.items()}
    reg_cov = np.nanmean(R[:, reg] >= 1, 1)
    reg_mean = np.nanmean(R[:, reg], 1)
    # upper air: anomalies, boxes
    ula, ulo = D["ula"], D["ulo"]
    z5a, _ = anomalies(D["z5"], days); t5a, _ = anomalies(D["t5"], days)
    pw = D["pw"]; _, pwc = anomalies(pw, days)
    jb = (ula >= 17.5) & (ula <= 27.5); ib = (ulo >= 35) & (ulo <= 42.5)
    zbox = z5a[:, jb][:, :, ib].reshape(nd, -1).mean(1)
    tbox = t5a[:, jb][:, :, ib].reshape(nd, -1).mean(1)
    jm = int(np.argmin(np.abs(ula - 21.25))); im = int(np.argmin(np.abs(ulo - 40.0)))
    pwp = 100 * pw[:, jm, im] / np.maximum(pwc[:, jm, im], 1)
    u7, v7, rh7 = D["u7"][:, jm, im], D["v7"][:, jm, im], D["rh7"][:, jm, im]
    zprev = np.concatenate([[0], zbox[:-1]]); tprev = np.concatenate([[0], tbox[:-1]])
    trough = (np.minimum(zbox, zprev) <= -20) | (np.minimum(tbox, tprev) <= -1.5)
    easterly = u7 < -1.0                      # 700 hPa wind from the east (the eastern steering)
    moist = pwp >= 130
    try:
        rmm = {d: (ph, amp) for d, r1, r2, ph, amp in daily.read_rmm()}
    except Exception as ex:  # noqa: BLE001
        print("rmm unavailable", repr(ex)[:100], flush=True)
        rmm = {}
    ph = np.array([rmm.get(d, (0, 0))[0] for d in days]); amp = np.array([rmm.get(d, (0, 0))[1] for d in days])
    nino = L.monthly_index("https://psl.noaa.gov/data/correlation/nina34.anom.data")
    dmi = L.monthly_index("https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data")
    years = sorted(set(yr)); ny_ = len(years)
    out = {"years": [years[0], years[-1]], "res": D["res"], "cities": {}}

    print(f"\n==== {years[0]}-{years[-1]} ({ny_} years), CHIRPS {D['res']}")
    print("\n#### 1. Each city by month: mean rain mm | rain days (>=1 mm) per month | heavy days (>=10 mm) per 10 years | "
          "mean rain on a rain day | wettest day mm")
    for c in CITIES:
        x = city_mean[c]
        rows = []
        print(f"\n  {c}")
        for m in range(1, 13):
            q = mon == m
            tot = np.nansum(x[q]) / ny_
            wd = (x[q] >= 1).sum() / ny_
            hd = (x[q] >= 10).sum() / ny_ * 10
            inten = np.nanmean(x[q][x[q] >= 1]) if (x[q] >= 1).any() else 0
            mx = np.nanmax(x[q])
            rows.append({"m": m, "mm": round(float(tot), 1), "wd": round(float(wd), 2), "hd10": round(float(hd), 1),
                         "int": round(float(inten), 1), "max": round(float(mx), 1)})
            print(f"    {MONTHS[m-1]:>7s}: {tot:5.1f} mm | {wd:4.2f} days | {hd:4.1f} | {inten:4.1f} mm | max {mx:5.1f}")
        ann = sum(r["mm"] for r in rows)
        print(f"    year: {ann:.0f} mm; share Oct-Jan {100*sum(r['mm'] for r in rows if r['m'] in (10,11,12,1))/max(ann,1e-9):.0f}%, "
              f"Mar-May {100*sum(r['mm'] for r in rows if r['m'] in (3,4,5))/max(ann,1e-9):.0f}%, Jun-Sep {100*sum(r['mm'] for r in rows if r['m'] in (6,7,8,9))/max(ann,1e-9):.0f}%")
        out["cities"][c] = {"months": rows, "year_mm": round(ann, 1)}

    print("\n#### 2. Spread on the city's rain days, by month: share of the city itself wet | share of the region wet | "
          "kind: local (region < 15%) / medium / wide (region >= 40%)")
    for c in CITIES:
        x = city_mean[c]
        print(f"\n  {c}")
        for m in range(1, 13):
            q = (mon == m) & (x >= 1)
            if q.sum() < 8:
                print(f"    {MONTHS[m-1]:>7s}: too few rain days ({q.sum()})")
                continue
            rc = reg_cov[q]
            out["cities"][c]["months"][m - 1].update(city_cov=round(float(city_cov[c][q].mean()), 2),
                                                     reg_cov=round(float(rc.mean()), 2),
                                                     local=round(float(np.mean(rc < 0.15)), 2), wide=round(float(np.mean(rc >= 0.4)), 2))
            print(f"    {MONTHS[m-1]:>7s} (n={q.sum():3d}): city {100*city_cov[c][q].mean():3.0f}% | region {100*rc.mean():3.0f}% | "
                  f"local {100*np.mean(rc < 0.15):3.0f}% medium {100*np.mean((rc >= 0.15) & (rc < 0.4)):3.0f}% wide {100*np.mean(rc >= 0.4):3.0f}%")

    print("\n#### 3. What brings it, by month: share of the city's rain (mm) on trough/cold-aloft days | on moist days "
          "(PW >= 130% of normal) | with the 700 hPa wind from the east; and the region's spread with vs without each")
    for c in CITIES:
        x = city_mean[c]
        print(f"\n  {c}")
        for m in range(1, 13):
            q = (mon == m) & (x >= 1)
            if q.sum() < 8:
                continue
            tot = x[q].sum()
            f = lambda flag: 100 * x[q & flag].sum() / tot
            s_ = lambda flag: (100 * reg_cov[q & flag].mean() if (q & flag).sum() >= 3 else np.nan,
                               100 * reg_cov[q & ~flag].mean() if (q & ~flag).sum() >= 3 else np.nan)
            ta, tb = s_(trough); ma, mb = s_(moist); ea, eb = s_(easterly)
            # chance of a rain day: with the flag vs without (all days of the month)
            a = mon == m
            pr = lambda flag: (100 * np.mean(x[a & flag] >= 1), 100 * np.mean(x[a & ~flag] >= 1))
            pt, pm_, pe = pr(trough), pr(moist), pr(easterly)
            out["cities"][c]["months"][m - 1].update(
                rain_trough=round(f(trough)), rain_moist=round(f(moist)), rain_east=round(f(easterly)),
                p_trough=[round(pt[0], 1), round(pt[1], 1)], p_moist=[round(pm_[0], 1), round(pm_[1], 1)],
                p_east=[round(pe[0], 1), round(pe[1], 1)],
                pw_wet=round(float(np.median(pwp[q]))), rh7_wet=round(float(np.median(rh7[q]))))
            print(f"    {MONTHS[m-1]:>7s}: rain from trough {f(trough):3.0f}% | moist {f(moist):3.0f}% | east 700 {f(easterly):3.0f}% "
                  f"|| P(rain day) trough {pt[0]:4.1f}/{pt[1]:4.1f} moist {pm_[0]:4.1f}/{pm_[1]:4.1f} east {pe[0]:4.1f}/{pe[1]:4.1f} "
                  f"|| region spread trough {ta:3.0f}/{tb:3.0f} moist {ma:3.0f}/{mb:3.0f} east {ea:3.0f}/{eb:3.0f} "
                  f"|| median PW {np.median(pwp[q]):3.0f}% RH700 {np.median(rh7[q]):3.0f}%")

    print("\n#### 4. The cities together: P(other city rain day | this city rain day), Oct-May")
    wet = np.isin(mon, (10, 11, 12, 1, 2, 3, 4, 5))
    names = list(CITIES)
    print("    " + " ".join(f"{n:>8s}" for n in names))
    for a_ in names:
        qa = wet & (city_mean[a_] >= 1)
        print(f"    {a_:>8s} " + " ".join(f"{100*np.mean(city_mean[b_][qa] >= 1):8.0f}" for b_ in names) + f"   (n={qa.sum()})")

    print("\n#### 5. MJO phase (amplitude >= 1): rain-day chance as % of the month's normal, by season part")
    groups = {"سبتمبر-أكتوبر": (9, 10), "نوفمبر-ديسمبر": (11, 12), "يناير-فبراير": (1, 2), "مارس-مايو": (3, 4, 5)}
    for c in CITIES:
        x = city_mean[c]
        print(f"\n  {c}")
        mj = {}
        for gname, ms in groups.items():
            s = np.isin(mon, ms) & (amp > 0)
            if s.sum() < 100:
                continue
            base = np.mean(x[s] >= 1)
            cells = []
            vals = {}
            for p_ in range(1, 9):
                q = s & (ph == p_) & (amp >= 1)
                v = 100 * np.mean(x[q] >= 1) / max(base, 1e-9) if q.sum() >= 30 else np.nan
                vals[p_] = None if np.isnan(v) else round(float(v))
                cells.append(f"{p_}:{v:4.0f}")
            q = s & (amp < 1)
            vw = 100 * np.mean(x[q] >= 1) / max(base, 1e-9)
            vals["weak"] = round(float(vw))
            mj[gname] = vals
            print(f"    {gname:>14s}: " + " ".join(cells) + f" weak:{vw:4.0f}  (base {100*base:.1f}% of days)")
        out["cities"][c]["mjo"] = mj

    print("\n#### 6. ENSO and IOD (autumn: Sep-Nov mean) against each city's rain by season part, 1981-2025; |r| >= 0.30 ~ 95%")
    for c in CITIES:
        x = city_mean[c]
        print(f"\n  {c}")
        enso = {}
        for gname, ms in groups.items():
            xs_n, xs_d, ys = [], [], []
            for y in years:
                ys_ = y if ms[0] >= 9 else y + 1          # Sep-Dec of year y, Jan-May of y+1 (season starting in y)
                q = np.isin(mon, ms) & (yr == ys_)
                if q.sum() < 25:
                    continue
                vn = [nino.get((y, k)) for k in (9, 10, 11)]; vd = [dmi.get((y, k)) for k in (9, 10, 11)]
                if None in vn or None in vd:
                    continue
                xs_n.append(np.mean(vn)); xs_d.append(np.mean(vd)); ys.append(np.nansum(x[q]))
            rn = np.corrcoef(xs_n, ys)[0, 1] if len(ys) >= 15 else np.nan
            rd = np.corrcoef(xs_d, ys)[0, 1] if len(ys) >= 15 else np.nan
            # wet seasons: El Nino (>= 0.5) vs La Nina (<= -0.5) mean rain
            ys, xs_n = np.array(ys), np.array(xs_n)
            en, ln = ys[xs_n >= 0.5].mean() if (xs_n >= 0.5).sum() >= 3 else np.nan, ys[xs_n <= -0.5].mean() if (xs_n <= -0.5).sum() >= 3 else np.nan
            enso[gname] = {"r_nino": None if np.isnan(rn) else round(float(rn), 2), "r_dmi": None if np.isnan(rd) else round(float(rd), 2),
                           "elnino_mm": None if np.isnan(en) else round(float(en), 1), "lanina_mm": None if np.isnan(ln) else round(float(ln), 1),
                           "all_mm": round(float(ys.mean()), 1) if len(ys) else None}
            print(f"    {gname:>14s}: r Nino {rn:+.2f}, r IOD {rd:+.2f} | rain El Nino {en:5.1f} mm, La Nina {ln:5.1f} mm, all {ys.mean():5.1f} mm (n={len(ys)})")
        out["cities"][c]["enso"] = enso

    print("\n#### 7. Wettest and driest seasons (Sep-May) per city, and the trend per decade")
    for c in CITIES:
        x = city_mean[c]
        tots = []
        for y in years[:-1]:
            q = ((yr == y) & (mon >= 9)) | ((yr == y + 1) & (mon <= 5))
            tots.append((y, float(np.nansum(x[q]))))
        tots.sort(key=lambda t: -t[1])
        ys_ = np.array([t[0] for t in tots]); vs_ = np.array([t[1] for t in tots])
        a, b = np.polyfit(ys_, vs_, 1)
        out["cities"][c]["wettest"] = tots[:5]; out["cities"][c]["driest"] = tots[-5:]
        out["cities"][c]["trend_per_decade"] = round(float(a * 10), 1)
        print(f"  {c}: wettest " + ", ".join(f"{y}/{(y+1)%100:02d} {v:.0f}" for y, v in tots[:5]) +
              " | driest " + ", ".join(f"{y}/{(y+1)%100:02d} {v:.0f}" for y, v in tots[-5:]) + f" | trend {a*10:+.1f} mm/decade (mean {vs_.mean():.0f})")
    json.dump(out, open("hijaz.json", "w"), ensure_ascii=False, indent=1)
    print("\nwrote hijaz.json", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    else:
        analyse(sys.argv[2])
