"""Atmospheric rivers from the Indian Ocean to Arabia.

Water-vapour transport integrated from 1000 to 600 hPa (IVT, kg m^-1 s^-1) from the GFS 0.5 degree forecast every
6 hours for 12 days, the track of the core of the strongest river and of the first river that comes near the Kingdom,
and the largest transport over the Kingdom at each time.

Each GFS file is read by byte ranges: only the levels and variables needed, neighbouring records fetched together.
"""
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import numpy as np

AWS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
LEVELS = [1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600]
BOX = (-25.0, 35.0, 25.0, 110.0)          # south, north, west, east of the computation and the map
STEP_H = 6
DAYS = 12
G = 9.80665
THR_CORE = 250.0                           # a river: transport of 250 and more
THR_KEEP = 150.0                           # the track goes on while the core stays above 150
SA_BOX = (17.0, 32.0, 36.0, 55.0)          # the Kingdom and its coasts
HEJAZ_BOX = (19.0, 25.0, 38.5, 42.0)
NEAR_SA = (5.0, 32.0, 32.0, 65.0)          # where a river counts as coming near the Kingdom
NEAR_STAY = (3.0, 34.0, 30.0, 72.0)        # and where its track is followed
IO_BOX = (-20.0, 22.0, 40.0, 98.0)         # where the strongest river is looked for
# category edges of the colours (the same as the regional river scale used by Khalid Al-Otaibi)
CATS = [150, 260, 370, 480, 560, 670]
CAT_COLS = ["#5ea4d8", "#f2c14e", "#f08a2a", "#e0535a", "#7b3fc0", "#1c1b2b"]


def _get(url, headers=None, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "saudi-wrf-climate", **(headers or {})})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            if k == tries - 1:
                raise
            print(f"retry {url}: {e}", flush=True)
            time.sleep(5 * (k + 1))


def _fetch(cycle, fh):
    """The needed GRIB records of one forecast hour, as one byte string."""
    d, hh = cycle[:8], cycle[8:10]
    base = f"{AWS}/gfs.{d}/{hh}/atmos/gfs.t{hh}z.pgrb2.0p50.f{fh:03d}"
    idx = _get(base + ".idx").decode().splitlines()
    starts = [int(l.split(":")[1]) for l in idx]
    where = {}
    for k, l in enumerate(idx):
        m = re.search(r":(UGRD|VGRD|SPFH|RH|TMP):(\d+) mb:", l)
        if m and int(m.group(2)) in LEVELS:
            where[(m.group(1), int(m.group(2)))] = k
        elif ":PRES:surface:" in l:
            where[("PRES", 0)] = k
    want = [where[("PRES", 0)]]
    for lev in LEVELS:
        want += [where[("UGRD", lev)], where[("VGRD", lev)]]
        if ("SPFH", lev) in where:
            want.append(where[("SPFH", lev)])
        else:  # specific humidity from relative humidity and temperature
            want += [where[("RH", lev)], where[("TMP", lev)]]
    want = sorted(set(want))
    groups, cur = [], [want[0]]
    for k in want[1:]:
        if k - cur[-1] <= 4:
            cur.append(k)
        else:
            groups.append(cur); cur = [k]
    groups.append(cur)
    blobs = []
    for g in groups:
        a = starts[g[0]]
        b = starts[g[-1] + 1] - 1 if g[-1] + 1 < len(starts) else ""
        blobs.append(_get(base, {"Range": f"bytes={a}-{b}"}))
    return b"".join(blobs)


def _decode(blob, tag):
    """IVT components on the box (lat descending), from one forecast hour."""
    import pygrib
    tmp = f"/tmp/ar_{os.getpid()}_{tag}.grb"
    open(tmp, "wb").write(blob)
    f = {}
    lat = lon = None
    with pygrib.open(tmp) as g:
        for m in g:
            sn, tl = m.shortName, m.typeOfLevel
            if tl == "surface" and sn == "sp":
                key = ("sp", 0)
            elif tl == "isobaricInhPa" and int(m.level) in LEVELS and sn in ("u", "v", "q", "r", "t"):
                key = (sn, int(m.level))
            else:
                continue
            if lat is None:
                la, lo = m.distinctLatitudes, m.distinctLongitudes
                j = np.where((la >= BOX[0]) & (la <= BOX[1]))[0]
                i = np.where((lo >= BOX[2]) & (lo <= BOX[3]))[0]
                lat, lon = la[j], lo[i]
                flip = lat[0] < lat[-1]
            a = np.asarray(m.values, dtype=np.float32)[np.ix_(j, i)]
            f[key] = a[::-1] if flip else a
    os.remove(tmp)
    if flip:
        lat = lat[::-1]
    for lev in LEVELS:
        if ("q", lev) not in f:
            t, rh = f[("t", lev)], np.clip(f[("r", lev)], 0, 100)
            es = 611.2 * np.exp(17.67 * (t - 273.15) / (t - 29.65))
            e = rh / 100 * es
            f[("q", lev)] = 0.622 * e / (lev * 100.0 - 0.378 * e)
    sp = f[("sp", 0)]
    qu = np.zeros_like(sp)
    qv = np.zeros_like(sp)
    for a, b in zip(LEVELS[:-1], LEVELS[1:]):
        above = (sp >= a * 100.0).astype(np.float32)        # both levels above the ground
        dp = (a - b) * 100.0
        qu += above * 0.5 * (f[("q", a)] * f[("u", a)] + f[("q", b)] * f[("u", b)]) * dp / G
        qv += above * 0.5 * (f[("q", a)] * f[("v", a)] + f[("q", b)] * f[("v", b)]) * dp / G
    return lat, lon, qu, qv


def fields(cycle):
    """IVT every STEP_H hours from the analysis to DAYS days: times (hours), lat, lon, qu[t], qv[t]."""
    hours = list(range(0, DAYS * 24 + 1, STEP_H))
    with ThreadPoolExecutor(8) as ex:
        blobs = list(ex.map(lambda h: _fetch(cycle, h), hours))
    qu, qv = [], []
    for h, b in zip(hours, blobs):
        lat, lon, u, v = _decode(b, h)
        qu.append(u); qv.append(v)
    return hours, lat, lon, np.array(qu), np.array(qv)


# ------------------------------------------------------------------ tracking
def _dist(lat, lon, la0, lo0):
    """Distance in degrees of latitude from (la0, lo0) on the grid."""
    return np.hypot((lon[None, :] - lo0) * np.cos(np.radians(la0)), lat[:, None] - la0)


def _objects(ms, mag, lat, lon, thr=THR_CORE):
    """Connected regions of transport above thr: (score, core lat, core lon, core value)."""
    from scipy.ndimage import label
    lab, n = label(ms >= thr)
    w = np.cos(np.radians(lat))[:, None]
    out = []
    for k in range(1, n + 1):
        m = lab == k
        if m.sum() < 6:
            continue
        sub = np.where(m, ms, -1)
        j, i = np.unravel_index(int(np.argmax(sub)), sub.shape)
        out.append((float((mag * w)[m].sum()), float(lat[j]), float(lon[i]), float(ms[j, i])))
    return sorted(out, reverse=True)


def _follow(MS, lat, lon, k0, la0, lo0, stay=None):
    """Follow a core forward from step k0: at each step the strongest transport near the expected position.
    stay = (south, north, west, east): the track ends when the core leaves it."""
    stay = stay or (BOX[0] + 1, BOX[1] - 1, BOX[2] + 1, BOX[3] - 1)
    pts = [(k0, la0, lo0, float(MS[k0][np.argmin(np.abs(lat - la0)), np.argmin(np.abs(lon - lo0))]))]
    vla = vlo = 0.0
    for k in range(k0 + 1, len(MS)):
        _, pla, plo, _ = pts[-1]
        gla, glo = pla + vla, plo + vlo
        d = _dist(lat, lon, gla, glo)
        score = np.where((MS[k] >= THR_KEEP) & (d <= 8.0), MS[k] * np.exp(-0.5 * (d / 4.0) ** 2), -1)
        if score.max() <= 0:
            break
        j, i = np.unravel_index(int(np.argmax(score)), score.shape)
        nla, nlo = float(lat[j]), float(lon[i])
        vla, vlo = 0.5 * vla + 0.5 * (nla - pla), 0.5 * vlo + 0.5 * (nlo - plo)
        pts.append((k, nla, nlo, float(MS[k][j, i])))
        if not (stay[0] <= nla <= stay[1] and stay[2] <= nlo <= stay[3]):
            break
    return pts


def saudi_mask(lat, lon):
    """Grid points over the land of the Kingdom (the box around it if the country outline cannot be read)."""
    LO, LA = np.meshgrid(lon, lat)
    try:
        import cartopy.io.shapereader as shp
        import shapely
        rec = next(r for r in shp.Reader(shp.natural_earth("50m", "cultural", "admin_0_countries")).records()
                   if r.attributes.get("ADM0_A3") == "SAU")
        m = shapely.contains_xy(rec.geometry, LO, LA)
        if m.sum() > 50:
            return m
    except Exception as e:
        print("country outline unavailable:", str(e)[:80], flush=True)
    s, n, w, e = SA_BOX
    return (LA >= s) & (LA <= n) & (LO >= w) & (LO <= e)


def _masked_max(a, mask):
    return float(np.nanmax(np.where(mask, a, np.nan)))


def region(la, lo):
    """Arabic name of where a point lies."""
    if 10 <= la < 17.5 and 42 <= lo <= 53.5:
        return "اليمن وخليج عدن"
    if 16 <= la <= 32 and 38.5 <= lo <= 55.5:
        return "المملكة"
    if 13 <= la <= 28 and 32.5 <= lo < 43.5:
        return "البحر الأحمر"
    if 23 <= la <= 30.5 and 47.5 <= lo <= 57:
        return "الخليج العربي"
    if 5 <= la <= 25 and 52 <= lo <= 77:
        return "بحر العرب"
    if 5 <= la <= 23 and 79 <= lo <= 97:
        return "خليج البنغال"
    if la > 30:
        return "شمال الجزيرة العربية والعراق"
    if lo < 42 and la > -12:
        return "شرق أفريقيا"
    if -6 <= la <= 6:
        part = "غرب" if lo < 60 else "وسط" if lo < 80 else "شرق"
        return f"{part} المحيط الهندي الاستوائي"
    if la < -6:
        part = "غرب" if lo < 60 else "وسط" if lo < 85 else "شرق"
        return f"جنوب {part} المحيط الهندي"
    return "شمال المحيط الهندي"


def analyse(cycle, t0):
    """Everything for the card and the report; the fields are returned too for the figures."""
    from scipy.ndimage import gaussian_filter
    hours, lat, lon, qu, qv = fields(cycle)
    mag = np.hypot(qu, qv)
    MS = np.array([gaussian_filter(m, 2.0) for m in mag])       # about 1 degree, so the core is the river's middle
    times = [t0 + timedelta(hours=h) for h in hours]
    tracks = []
    # 1. the strongest river over the Indian Ocean now
    obj = [o for o in _objects(MS[0], mag[0], lat, lon) if IO_BOX[0] <= o[1] <= IO_BOX[1] and IO_BOX[2] <= o[2] <= IO_BOX[3]]
    if obj:
        _, la0, lo0, _ = obj[0]
        tracks.append({"kind": "main", "pts": _follow(MS, lat, lon, 0, la0, lo0)})
    # 2. the first river whose core comes near the Kingdom in the first week, if it is not the same one
    for k in range(0, min(len(MS), 7 * 24 // STEP_H + 1)):
        near = [o for o in _objects(MS[k], mag[k], lat, lon)
                if NEAR_SA[0] <= o[1] <= NEAR_SA[1] and NEAR_SA[2] <= o[2] <= NEAR_SA[3]]
        if not near:
            continue
        _, la0, lo0, _ = near[0]
        same = False
        for t in tracks:
            p = [x for x in t["pts"] if x[0] == k]
            if p and np.hypot((p[0][2] - lo0) * np.cos(np.radians(la0)), p[0][1] - la0) < 6:
                same = True
        if not same:
            tracks.append({"kind": "near", "pts": _follow(MS, lat, lon, k, la0, lo0, NEAR_STAY)})
        break
    land = saudi_mask(lat, lon)
    LO, LA = np.meshgrid(lon, lat)
    hj = land & (LA >= HEJAZ_BOX[0]) & (LA <= HEJAZ_BOX[1]) & (LO >= HEJAZ_BOX[2]) & (LO <= HEJAZ_BOX[3])
    sa = [{"t": t.strftime("%Y-%m-%dT%H:%MZ"), "v": int(round(_masked_max(MS[k], land))),
           "hejaz": int(round(_masked_max(MS[k], hj)))} for k, t in enumerate(times)]
    out_tracks = []
    for t in tracks:
        pts = [{"t": times[k].strftime("%Y-%m-%dT%H:%MZ"), "k": k, "lat": round(la, 2), "lon": round(lo, 2),
                "v": int(round(v)), "region": region(la, lo)} for k, la, lo, v in t["pts"]]
        out_tracks.append({"kind": t["kind"], "pts": pts})
    data = {"cycle": cycle, "step_h": STEP_H, "times": [t.strftime("%Y-%m-%dT%H:%MZ") for t in times],
            "tracks": out_tracks, "sa": sa}
    return data, (lat, lon, qu, qv, mag)
