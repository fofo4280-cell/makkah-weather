"""The rain spread of past days, to compare today with yesterday, the day before and the last wave's peak
(Fahad, 18 Nov 2026: «مقارنة شدة انتشار المطر … اليوم مقارنتها بأمس … أول أمس … الموجة الأخيرة … في أعلى أيامها»).

cover_hist.json in the published data folder keeps, per Makkah day, the share of the Kingdom and of each region
with a day total of 1 mm or more:
  "ours": from our model (the report's rain section, recorded each night; our runs are kept three days only),
  "gfs":  from the GFS 0.25 deg forecast of the evening before (12 UTC, hours 9 to 33), one source for every day,
          so the last wave's peak (beyond our kept runs) compares with today on the same footing.
"""
import json
import os
from datetime import date, timedelta

import numpy as np

KEEP = 60          # days kept in the file
BACK = 21          # GFS days filled back from the report day
WAVE = 0.05        # a day of a wave: 5 % of the Kingdom or more wet (GFS)


def gfs_cover(d):
    """{'ksa', 'regions'} from the GFS 12 UTC run of the day before (21 UTC to 21 UTC = the Makkah day)"""
    import daily as D
    import sa_geo as G
    regs = G.regions()
    lat = np.arange(90, -90.01, -0.25)
    lon = np.arange(0, 360, 0.25)
    i0, i1 = np.searchsorted(-lat, -33), np.searchsorted(-lat, -15.5)
    j0, j1 = np.searchsorted(lon, 34), np.searchsorted(lon, 56)
    LA, LO = np.meshgrid(lat[i0:i1], lon[j0:j1], indexing="ij")
    kri = G.region_of_points(regs, LA.ravel(), LO.ravel()).reshape(LA.shape)
    w = np.cos(np.radians(LA))
    cyc = (d - timedelta(days=1)).strftime("%Y%m%d") + "12"
    P = ("apcp", r":APCP:surface:0-\d+ hour acc")
    a = D.gfs_fields(cyc, 33, res="0p25", fields=[P])["apcp"]
    b = D.gfs_fields(cyc, 9, res="0p25", fields=[P])["apcp"]
    wet = (a - b)[i0:i1, j0:j1] >= 1.0
    ins = kri >= 0
    rg = {}
    for k, R in enumerate(regs):
        m = kri == k
        if m.any():
            rg[R["name"]] = round(float((wet[m] * w[m]).sum() / w[m].sum()), 4)
    return {"ksa": round(float((wet * w)[ins].sum() / w[ins].sum()), 4), "regions": rg}


def attach(st, out, rain=None, day0=None, log=print):
    """load, update and save cover_hist.json; put it in st['cover_hist']"""
    p = os.path.join(out, "cover_hist.json")
    try:
        H = json.load(open(p))
    except Exception:  # noqa: BLE001
        H = {}
    H.setdefault("ours", {})
    H.setdefault("gfs", {})
    day0 = day0 or date.fromisoformat((st.get("report") or {}).get("day") or st["days"][0])
    dat = (rain or {}).get("data") or {}
    import report2
    if "cover_ksa" in dat and rain and not report2.pending(rain):
        H["ours"][day0.isoformat()] = {"ksa": dat["cover_ksa"], "regions": dat.get("cover_regions") or {}}
    for k in range(BACK, -1, -1):
        d = day0 - timedelta(days=k)
        if d.isoformat() in H["gfs"]:
            continue
        try:
            H["gfs"][d.isoformat()] = gfs_cover(d)
        except Exception as e:  # noqa: BLE001
            log("cover history: GFS skip", d, repr(e)[:120])
    cut = (day0 - timedelta(days=KEEP)).isoformat()
    for src in ("ours", "gfs"):
        H[src] = {d: v for d, v in sorted(H[src].items()) if d >= cut}
    try:
        json.dump(H, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
    except Exception as e:  # noqa: BLE001
        log("cover history: not saved", repr(e)[:120])
    st["cover_hist"] = H
    return H


def last_wave(H, day0):
    """the most recent wave before yesterday within two weeks: GFS days with 5 % of the Kingdom wet or more, a
    single quieter day between them kept in the wave (10-13 Nov 2026 was one wave with 12 Nov at 4 %); its days"""
    g = H.get("gfs") or {}
    days = [day0 - timedelta(days=k) for k in range(14, 2, -1)]
    wet = [d for d in days if (g.get(d.isoformat()) or {}).get("ksa", 0) >= WAVE]
    if not wet:
        return []
    runs = [[wet[0]]]
    for d in wet[1:]:
        if (d - runs[-1][-1]).days <= 2:
            runs[-1] += [runs[-1][-1] + timedelta(days=k) for k in range(1, (d - runs[-1][-1]).days + 1)]
        else:
            runs.append([d])
    return runs[-1]


def compare(H, day0, region=None):
    """{'ours': [today, yesterday, before], 'gfs': [...], 'peak': (date, value) or None} for the Kingdom or a region"""
    val = lambda src, d: (lambda v: None if v is None else (v["ksa"] if region is None else v["regions"].get(region)))(
        (H.get(src) or {}).get(d.isoformat()))
    ds = [day0, day0 - timedelta(days=1), day0 - timedelta(days=2)]
    wv = last_wave(H, day0)
    peak = None
    if wv:
        xs = [(val("gfs", d), d) for d in wv if val("gfs", d) is not None]
        if xs:
            v, d = max(xs)
            peak = (d, v)
    return {"ours": [val("ours", d) for d in ds], "gfs": [val("gfs", d) for d in ds], "peak": peak, "wave": wv}
