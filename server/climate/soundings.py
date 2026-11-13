#!/usr/bin/env python3
"""GFS 0.25 degree soundings at a few points of the western sector, for a hand study of a day's convective chance.

    soundings.py CYCLE(YYYYMMDDHH) FIRST_FH LAST_FH STEP

Prints, per point and hour: the profile (T, Td, RH, wind) from 1000 to 300 hPa, the surface-based and
most-unstable parcels (CAPE, CIN, LCL, LFC, EL, source level), lapse rates, mean RH of layers, PW, and the
GFS's own CAPE/CIN fields. Nothing is published; it is read from the log.
"""
import os, re, sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LEV = [1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350, 300]
PTS = [("البحر غرب جدة", 21.50, 38.90), ("جدة", 21.54, 39.17), ("غرب الجموم (بحرة)", 21.45, 39.45),
       ("الجموم", 21.62, 39.70), ("مكة", 21.42, 39.83), ("الشرائع", 21.48, 40.00),
       ("الهدا", 21.37, 40.28), ("الطائف", 21.27, 40.42)]
SFC = [("ps", r":PRES:surface:"), ("t2", r":TMP:2 m above ground:"), ("td2", r":DPT:2 m above ground:"),
       ("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
       ("cape", r":CAPE:surface:"), ("cin", r":CIN:surface:"), ("mlcape", r":CAPE:180-0 mb above ground:"),
       ("mlcin", r":CIN:180-0 mb above ground:"), ("mucape", r":CAPE:255-0 mb above ground:"),
       ("pw", r":PWAT:entire atmosphere \(considered as a single layer\):"), ("hpbl", r":HPBL:surface:"),
       ("apcp", r":APCP:surface:"), ("cprat", r":CPRAT:surface:[0-9]+-[0-9]+ hour ave")]


def fields(cyc, fh):
    import daily
    want = list(SFC)
    for p in LEV:
        for v in ("TMP", "RH", "UGRD", "VGRD", "HGT"):
            want.append((f"{v}{p}", rf":{v}:{p} mb:"))
    out = {}
    # separate processes: daily.gfs_fields writes its temporary file under the process id
    with ProcessPoolExecutor(8) as ex:
        for k, a in ex.map(_one, [(cyc, fh, w) for w in want]):
            if a is not None:
                out[k] = a
    return out


def _one(arg):
    cyc, fh, item = arg
    import daily
    for _ in range(3):
        try:
            return item[0], daily.gfs_fields(cyc, fh, res="0p25", fields=[item])[item[0]]
        except Exception:  # noqa: BLE001
            continue
    return item[0], None


def pick(a, lat, lon):
    j = int(round((90 - lat) / 0.25)); i = int(round(lon / 0.25))
    return float(a[j, i])


def analyse(f, lat, lon):
    import metpy.calc as mc
    from metpy.units import units
    ps = pick(f["ps"], lat, lon) / 100
    lev = [p for p in LEV if p < ps - 5]
    T = np.array([pick(f[f"TMP{p}"], lat, lon) - 273.15 for p in lev])
    RH = np.array([pick(f[f"RH{p}"], lat, lon) for p in lev])
    U = np.array([pick(f[f"UGRD{p}"], lat, lon) for p in lev])
    V = np.array([pick(f[f"VGRD{p}"], lat, lon) for p in lev])
    Td = np.array(mc.dewpoint_from_relative_humidity(T * units.degC, np.clip(RH, 1, 100) * units.percent).m)
    t2, td2 = pick(f["t2"], lat, lon) - 273.15, pick(f["td2"], lat, lon) - 273.15
    P = np.r_[ps, lev]; TT = np.r_[t2, T]; DD = np.r_[min(td2, t2), Td]
    Pq, Tq, Dq = P * units.hPa, TT * units.degC, DD * units.degC
    res = {"ps": ps, "t2": t2, "td2": td2}
    try:
        prof = mc.parcel_profile(Pq, Tq[0], Dq[0])
        cape, cin = mc.cape_cin(Pq, Tq, Dq, prof)
        lcl = mc.lcl(Pq[0], Tq[0], Dq[0])[0]
        lfc = mc.lfc(Pq, Tq, Dq, prof)[0]
        el = mc.el(Pq, Tq, Dq, prof)[0]
        res.update(sbcape=cape.m, sbcin=cin.m, lcl=lcl.m, lfc=getattr(lfc, "m", np.nan), el=getattr(el, "m", np.nan))
    except Exception as e:  # noqa: BLE001
        res["err"] = repr(e)[:80]
    # most unstable parcel from the lowest 300 hPa: the elevated instability
    best = (0, None, 0)
    for k in range(len(P)):
        if P[k] < ps - 300:
            break
        try:
            pr = mc.parcel_profile(Pq[k:], Tq[k], Dq[k])
            c, n = mc.cape_cin(Pq[k:], Tq[k:], Dq[k:], pr)
            if c.m > best[0]:
                lf = mc.lfc(Pq[k:], Tq[k:], Dq[k:], pr)[0]
                best = (c.m, P[k], n.m, getattr(lf, "m", np.nan))
        except Exception:  # noqa: BLE001
            continue
    if best[1] is not None:
        res.update(mucape=best[0], mu_src=best[1], mucin=best[2], mu_lfc=best[3])
    g = lambda p, arr: float(np.interp(-p, -np.array(lev, float), arr)) if lev[0] >= p >= lev[-1] else np.nan
    z7, z5 = pick(f["HGT700"], lat, lon), pick(f["HGT500"], lat, lon)
    res["lapse_700_500"] = (g(700, T) - g(500, T)) / ((z5 - z7) / 1000)
    res["t500"] = g(500, T)
    res["rh_lay"] = {k: float(np.mean([g(p, RH) for p in ps_])) for k, ps_ in
                     {"925-850": (925, 900, 850), "850-700": (850, 800, 750, 700), "700-500": (700, 650, 600, 550, 500)}.items()}
    res["prof"] = [(p, round(t, 1), round(d, 1), round(r), round(np.degrees(np.arctan2(-u, -v)) % 360), round(np.hypot(u, v) * 3.6))
                   for p, t, d, r, u, v in zip(lev, T, Td, RH, U, V)]
    for k in ("cape", "cin", "mlcape", "mlcin", "mucape", "pw", "hpbl", "u10", "v10"):
        if k in f:
            res["gfs_" + k] = pick(f[k], lat, lon)
    if "cprat" in f:
        res["gfs_cprat_mmh"] = pick(f["cprat"], lat, lon) * 3600
    return res


def main():
    cyc, a, b, s = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    for fh in range(a, b + 1, s):
        f = fields(cyc, fh)
        lt = (int(cyc[8:10]) + fh + 3) % 24
        print(f"\n######## {cyc} +{fh}h  (Makkah {lt:02d}:00)  fields {len(f)}", flush=True)
        for name, lat, lon in PTS:
            try:
                r = analyse(f, lat, lon)
            except Exception as e:  # noqa: BLE001
                print(name, "failed", repr(e)[:100]); continue
            w10 = np.hypot(r.get("gfs_u10", 0), r.get("gfs_v10", 0)) * 3.6
            d10 = np.degrees(np.arctan2(-r.get("gfs_u10", 0), -r.get("gfs_v10", 0))) % 360
            print(f"== {name}: ps {r['ps']:.0f} T2 {r['t2']:.1f} Td2 {r['td2']:.1f} wind10 {d10:.0f}/{w10:.0f}km/h PW {r.get('gfs_pw', np.nan):.1f} "
                  f"HPBL {r.get('gfs_hpbl', np.nan):.0f}m")
            print(f"   SB: CAPE {r.get('sbcape', np.nan):.0f} CIN {r.get('sbcin', np.nan):.0f} LCL {r.get('lcl', np.nan):.0f} LFC {r.get('lfc', np.nan):.0f} EL {r.get('el', np.nan):.0f}"
                  f" | MU: CAPE {r.get('mucape', np.nan):.0f} from {r.get('mu_src', np.nan):.0f} CIN {r.get('mucin', np.nan):.0f} LFC {r.get('mu_lfc', np.nan):.0f}"
                  f" | GFS cape {r.get('gfs_cape', np.nan):.0f} cin {r.get('gfs_cin', np.nan):.0f} ml {r.get('gfs_mlcape', np.nan):.0f}/{r.get('gfs_mlcin', np.nan):.0f} mu {r.get('gfs_mucape', np.nan):.0f}"
                  f" conv-rain {r.get('gfs_cprat_mmh', np.nan):.2f}mm/h")
            print(f"   lapse700-500 {r['lapse_700_500']:.1f}C/km T500 {r['t500']:.1f}  RH " +
                  "  ".join(f"{k}:{v:.0f}%" for k, v in r["rh_lay"].items()))
            print("   " + " ".join(f"{p}:{t}/{d}/{rh}%/{dd}@{ws}" for p, t, d, rh, dd, ws in r["prof"]))


if __name__ == "__main__":
    main()
