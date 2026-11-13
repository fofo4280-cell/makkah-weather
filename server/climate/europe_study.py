#!/usr/bin/env python3
"""A hand study of the weather of a far point (Istanbul by default) for a range of days, from the newest GFS,
the GEFS ensemble and the ECMWF open data (HRES and ENS): the large-scale pattern over Europe and the Black Sea,
the winds that bring cold (poyraz) or mild air (lodos), the sea-effect potential of the Black Sea, and day by day
the rain and temperatures with ensemble spreads and probabilities. Printed to the log only.

    europe_study.py FIRST_DAY(YYYYMMDD) LAST_DAY [LAT LON]
"""
import json, os, re, sys, time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import requests

AWS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
GEFS = "https://noaa-gefs-pds.s3.amazonaws.com"
LAT, LON = 41.01, 28.98


def get(url, rng=None, tries=4):
    for k in range(tries):
        try:
            r = requests.get(url, headers={"Range": f"bytes={rng}"} if rng else {}, timeout=60)
            if r.status_code in (200, 206):
                return r.content
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2 + 3 * k)
    raise RuntimeError(f"get failed {url}")


def grib_values(blob):
    import pygrib, tempfile
    with tempfile.NamedTemporaryFile(suffix=".grb") as f:
        f.write(blob); f.flush()
        with pygrib.open(f.name) as g:
            m = g.message(1)
            a = np.ma.filled(np.ma.asarray(m.values, dtype=np.float64), np.nan)
            la, lo = m.latlons()
    return a, la[:, 0], lo[0]


def fields(base, pats):
    """{name: (array, lat, lon)} of the messages of a NOAA GRIB file matching the regexes"""
    idx = get(base + ".idx").decode().splitlines()
    st = [int(l.split(":")[1]) for l in idx]
    out = {}
    for name, pat in pats:
        k = next((i for i, l in enumerate(idx) if re.search(pat, l)), None)
        if k is None:
            continue
        end = st[k + 1] - 1 if k + 1 < len(st) else ""
        out[name] = grib_values(get(base, f"{st[k]}-{end}"))
    return out


def at(f, lat, lon, box=0.0):
    a, la, lo = f
    lon = lon % 360 if lo.max() > 180 else lon
    if box:
        jj = (la >= lat - box) & (la <= lat + box); ii = (lo >= lon - box) & (lo <= lon + box)
        return float(np.nanmean(a[np.ix_(jj, ii)])), float(np.nanmax(a[np.ix_(jj, ii)]))
    j = int(np.argmin(abs(la - lat))); i = int(np.argmin(abs(lo - lon)))
    return float(a[j, i])


# ------------------------------------------------------------------ GFS deterministic (pattern)
GFS_P = [("z500", r":HGT:500 mb:"), ("t850", r":TMP:850 mb:"), ("t500", r":TMP:500 mb:"), ("mslp", r":PRMSL:mean sea level:"),
         ("t2", r":TMP:2 m above ground:"), ("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
         ("tsfc", r":TMP:surface:"), ("rh700", r":RH:700 mb:"), ("u300", r":UGRD:300 mb:"), ("v300", r":VGRD:300 mb:")]


def gfs_cycle():
    now = datetime.now(timezone.utc)
    for k in range(0, 48, 6):
        c = (now - timedelta(hours=k)).replace(minute=0, second=0, microsecond=0)
        c = c.replace(hour=c.hour // 6 * 6)
        try:
            get(f"{AWS}/gfs.{c:%Y%m%d}/{c:%H}/atmos/gfs.t{c:%H}z.pgrb2.0p25.f384.idx", tries=1)
            return c
        except Exception:  # noqa: BLE001
            continue


def gfs_step(arg):
    c, fh = arg
    base = f"{AWS}/gfs.{c:%Y%m%d}/{c:%H}/atmos/gfs.t{c:%H}z.pgrb2.0p25.f{fh:03d}"
    pats = GFS_P + [("apcp", rf":APCP:surface:0-{fh} hour acc")]
    try:
        f = fields(base, pats)
    except Exception as e:  # noqa: BLE001
        return fh, None, repr(e)[:80]
    r = {}
    r["z500"] = at(f["z500"], LAT, LON); r["t850"] = at(f["t850"], LAT, LON) - 273.15; r["t500"] = at(f["t500"], LAT, LON) - 273.15
    r["t2"] = at(f["t2"], LAT, LON) - 273.15; r["mslp"] = at(f["mslp"], LAT, LON) / 100
    u, v = at(f["u10"], LAT, LON), at(f["v10"], LAT, LON)
    r["w10"] = (round(np.degrees(np.arctan2(-u, -v)) % 360), round(np.hypot(u, v) * 3.6))
    r["rh700"] = at(f["rh700"], LAT, LON)
    # poyraz/lodos: pressure north of the Black Sea minus over the Aegean (hPa); + = north-easterly push
    r["dp_n_s"] = (at(f["mslp"], 45.0, 32.0) - at(f["mslp"], 38.5, 25.5)) / 100
    # Black Sea west: sea surface minus 850 hPa (sea-effect showers when about 13 C or more)
    r["sea_t850"] = (at(f["tsfc"], 42.5, 30.5) - at(f["t850"], 42.5, 30.5))
    r["apcp_tot"] = at(f["apcp"], LAT, LON, box=0.25)[0] if "apcp" in f else np.nan
    # the trough/ridge along 40-50 N from 0 to 60 E: longitude of the lowest and highest 500 hPa height
    a, la, lo = f["z500"]
    jj = (la >= 40) & (la <= 50); ii = lo <= 60
    zz = a[np.ix_(jj, ii)].mean(0)
    r["trough_lon"] = float(lo[ii][np.argmin(zz)]); r["ridge_lon"] = float(lo[ii][np.argmax(zz)])
    a3 = np.hypot(f["u300"][0], f["v300"][0])
    r["jet_ist"] = at((a3, f["u300"][1], f["u300"][2]), LAT, LON) * 3.6
    return fh, r, None


# ------------------------------------------------------------------ GEFS members at the point
GEFS_P = [("t850", r":TMP:850 mb:"), ("t2", r":TMP:2 m above ground:"), ("mslp", r":PRMSL:mean sea level:")]


def gefs_cycle(c0):
    for k in range(0, 48, 6):
        c = c0 - timedelta(hours=k)
        try:
            get(f"{GEFS}/gefs.{c:%Y%m%d}/{c:%H}/atmos/pgrb2ap5/gep30.t{c:%H}z.pgrb2a.0p50.f384.idx", tries=1)
            return c
        except Exception:  # noqa: BLE001
            continue


def gefs_step(arg):
    c, m, fh = arg
    name = "gec00" if m == 0 else f"gep{m:02d}"
    base = f"{GEFS}/gefs.{c:%Y%m%d}/{c:%H}/atmos/pgrb2ap5/{name}.t{c:%H}z.pgrb2a.0p50.f{fh:03d}"
    try:
        f = fields(base, GEFS_P + [("apcp", rf":APCP:surface:{fh - 6}-{fh} hour acc")])
    except Exception:  # noqa: BLE001
        return m, fh, None
    return m, fh, {"t850": at(f["t850"], LAT, LON) - 273.15, "t2": at(f["t2"], LAT, LON) - 273.15,
                   "apcp": at(f["apcp"], LAT, LON, box=0.25)[0] if "apcp" in f else np.nan}


# ------------------------------------------------------------------ ECMWF open data
def ecmwf(first, last):
    from ecmwf.opendata import Client
    import pygrib
    out = {}
    tgt = "/tmp/ec.grib2"
    cl = d = None
    # the AWS mirror throttled on 13 Nov 2026 (503 for 50 minutes): try the mirrors in turn, with few retries
    for src in ("ecmwf", "azure", "aws"):
        try:
            c_ = Client(source=src, preserve_request_order=True)
            try:
                c_.retries = 2; c_.delay = 10
            except Exception:  # noqa: BLE001
                pass
            d = c_.latest(type="ep", stream="enfo")
            cl = c_
            print("ECMWF source", src, "ENS cycle", d, flush=True)
            break
        except Exception as e:  # noqa: BLE001
            print("ECMWF", src, "failed", repr(e)[:120], flush=True)
    if cl is None:
        return out
    c = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    # probabilities of 24 h rain and of 2 m temperature anomalies, per day
    days = []
    D = first
    while D <= last:
        s0 = int((D - c).total_seconds() // 3600)
        if 0 <= s0 and s0 + 24 <= 360:
            days.append((D, s0))
        D += timedelta(days=1)
    for params in (["tpg1", "tpg5", "tpg10", "tpg20"], ["2tag0", "2tag1", "2tag2", "2talm1", "2talm2"]):
        try:
            cl.retrieve(date=c.strftime("%Y%m%d"), time=c.hour, stream="enfo", type="ep", param=params,
                        step=[f"{s}-{s + 24}" for _, s in days], target=tgt)
            with pygrib.open(tgt) as g:
                for m in g:
                    a = np.ma.filled(np.ma.asarray(m.values, float), np.nan); la, lo = m.latlons()
                    v = at((a, la[:, 0], lo[0]), LAT, LON)
                    out.setdefault(str(m.stepRange), {})[m.shortName] = v
        except Exception as e:  # noqa: BLE001
            print("ECMWF ep", params, "failed", repr(e)[:160], flush=True)
    # ensemble mean and spread of 850 hPa temperature, 500 hPa height, MSLP at 12 UTC each day
    steps = sorted({s + 12 for _, s in days if s + 12 <= 360})
    for typ in ("em", "es"):
        try:
            cl.retrieve(date=c.strftime("%Y%m%d"), time=c.hour, stream="enfo", type=typ, param=["t", "gh", "msl"],
                        levelist=[500, 850], step=steps, target=tgt)
            with pygrib.open(tgt) as g:
                for m in g:
                    a = np.ma.filled(np.ma.asarray(m.values, float), np.nan); la, lo = m.latlons()
                    v = at((a, la[:, 0], lo[0]), LAT, LON)
                    key = f"{typ}_{m.shortName}{getattr(m, 'level', '')}"
                    out.setdefault(f"step{m.step}", {})[key] = v
        except Exception as e:  # noqa: BLE001
            print("ECMWF", typ, "failed", repr(e)[:160], flush=True)
    # HRES (to 240 h): rain, 2 m temperature, 850 hPa temperature, MSLP every 6 h
    try:
        h = cl.latest(type="fc", stream="oper")
        hc = h.replace(tzinfo=timezone.utc) if h.tzinfo is None else h
        hs = [s for s in range(0, 241, 6) if first <= hc + timedelta(hours=s) <= last + timedelta(days=1)]
        if hs:
            cl.retrieve(date=hc.strftime("%Y%m%d"), time=hc.hour, stream="oper", type="fc", param=["tp", "2t", "msl"],
                        step=hs, target=tgt)
            with pygrib.open(tgt) as g:
                for m in g:
                    a = np.ma.filled(np.ma.asarray(m.values, float), np.nan); la, lo = m.latlons()
                    out.setdefault(f"hres{hc:%d%H}_{m.step}", {})[m.shortName] = at((a, la[:, 0], lo[0]), LAT, LON)
            cl.retrieve(date=hc.strftime("%Y%m%d"), time=hc.hour, stream="oper", type="fc", param=["t"], levelist=[850],
                        step=hs, target=tgt)
            with pygrib.open(tgt) as g:
                for m in g:
                    a = np.ma.filled(np.ma.asarray(m.values, float), np.nan); la, lo = m.latlons()
                    out.setdefault(f"hres{hc:%d%H}_{m.step}", {})["t850"] = at((a, la[:, 0], lo[0]), LAT, LON)
    except Exception as e:  # noqa: BLE001
        print("ECMWF HRES failed", repr(e)[:160], flush=True)
    out["_cycle"] = str(c)
    return out


def main():
    global LAT, LON
    first = datetime.strptime(sys.argv[1], "%Y%m%d").replace(tzinfo=timezone.utc)
    last = datetime.strptime(sys.argv[2], "%Y%m%d").replace(tzinfo=timezone.utc)
    if len(sys.argv) > 4:
        LAT, LON = float(sys.argv[3]), float(sys.argv[4])
    c = gfs_cycle()
    print("GFS cycle", c, flush=True)
    h0 = int((first - c).total_seconds() // 3600); h1 = int((last + timedelta(days=1) - c).total_seconds() // 3600)
    fhs = [h for h in range(max(h0, 0), min(h1, 384) + 1, 6)]
    with ProcessPoolExecutor(8) as ex:
        res = sorted(ex.map(gfs_step, [(c, h) for h in fhs]), key=lambda x: x[0])
    print("\n#### GFS deterministic at the point (Istanbul local = UTC+3)")
    prev = None
    for fh, r, err in res:
        t = c + timedelta(hours=fh)
        if r is None:
            print(t, "failed", err); continue
        rain6 = (r["apcp_tot"] - prev) if prev is not None and np.isfinite(r["apcp_tot"]) else np.nan
        prev = r["apcp_tot"]
        print(f"{t:%d %HZ} z500 {r['z500']:.0f} T850 {r['t850']:5.1f} T500 {r['t500']:5.1f} T2 {r['t2']:5.1f} MSLP {r['mslp']:6.1f} "
              f"wind10 {r['w10'][0]:3d}/{r['w10'][1]:2d}km/h dP(N-S) {r['dp_n_s']:+5.1f} sea-T850 {r['sea_t850']:4.1f} RH700 {r['rh700']:3.0f} "
              f"rain6h {rain6:5.1f} trough@{r['trough_lon']:.0f}E ridge@{r['ridge_lon']:.0f}E jet300 {r['jet_ist']:.0f}km/h", flush=True)

    g = gefs_cycle(c)
    print("\n#### GEFS cycle", g, flush=True)
    if g:
        h0 = int((first - g).total_seconds() // 3600); h1 = int((last + timedelta(days=1) - g).total_seconds() // 3600)
        fhs = [h for h in range(max(h0 + 6, 6), min(h1, 384) + 1, 6)]
        jobs = [(g, m, h) for m in range(0, 31) for h in fhs]
        with ProcessPoolExecutor(12) as ex:
            rows = list(ex.map(gefs_step, jobs, chunksize=4))
        data = {}
        for m, h, r in rows:
            if r:
                data.setdefault(m, {})[h] = r
        print("members", len(data))
        D = first
        while D <= last:
            hs = [h for h in fhs if D < g + timedelta(hours=h) <= D + timedelta(days=1)]
            rain, t850, tmin, tmax = [], [], [], []
            for m, mm in data.items():
                v = [mm[h] for h in hs if h in mm]
                if len(v) < len(hs) or not v:
                    continue
                rain.append(np.nansum([x["apcp"] for x in v])); t850.append(np.mean([x["t850"] for x in v]))
                tmin.append(min(x["t2"] for x in v)); tmax.append(max(x["t2"] for x in v))
            if rain:
                rain, t850 = np.array(rain), np.array(t850)
                q = lambda a, p: np.percentile(a, p)
                print(f"{D:%a %d %b} n={len(rain)} rain mm: median {q(rain,50):.1f} p10-p90 {q(rain,10):.1f}-{q(rain,90):.1f} "
                      f"P>=1 {100*np.mean(rain>=1):.0f}% P>=5 {100*np.mean(rain>=5):.0f}% P>=10 {100*np.mean(rain>=10):.0f}% P>=20 {100*np.mean(rain>=20):.0f}% | "
                      f"T850 mean {q(t850,50):.1f} p10-p90 {q(t850,10):.1f}-{q(t850,90):.1f} P(T850<=0) {100*np.mean(t850<=0):.0f}% P(<=-4) {100*np.mean(t850<=-4):.0f}% | "
                      f"T2 min med {np.median(tmin):.1f} max med {np.median(tmax):.1f}", flush=True)
            D += timedelta(days=1)

    print("\n#### ECMWF open data", flush=True)
    ec = ecmwf(first, last)
    for k in sorted(ec, key=lambda s: (len(s), s)):
        print(k, json.dumps(ec[k], default=lambda x: round(float(x), 2)) if isinstance(ec[k], dict) else ec[k])


if __name__ == "__main__":
    main()
