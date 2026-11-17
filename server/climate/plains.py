"""The evening storms of the coastal plains (Fahad, 15 Nov 2026): a check, from the GFS forecast of the report day,
for the pattern our 3 km model tends to miss.

The pattern: storms form on the mountains in the afternoon (the Sarawat and Asir east of Tihama, Taif and the
Hijaz mountains east of Makkah); their cold outflow runs down the slopes into very hot, very humid lowland air,
lifts it (with the sea breeze coming in from the west), and new cells start over the plains in the evening, between
Maghrib and Isha. Weak steering keeps the cells in place, and the wadis bring the mountain flood water down.
15 Nov 2026: floods on the Al-Qunfudhah plains while the analysis put the rain on the slopes (PW 161 % of normal
over the southwest, steering under 5 m/s, SE upslope flow at 850 hPa).

For each plain, with its mountains just east of it, six enhancers are checked:
  1. moisture:      PW >= 130 % of normal over the page's box (Makkah 115, PCT_MIN), or >= 40 mm over the plain
  2. hot humid air: 2 m dew point over the plain >= 19 C at 15 Makkah (Al-Lith 18, Makkah 17; TD_MIN)
  3. instability:   most-unstable CAPE (180-0 hPa parcel) over the plain >= 1000 J/kg (75th percentile, 15 to 21 Makkah)
  4. mountain storms in the afternoon: GFS rain on the mountains >= 1 mm (90th percentile, 12-18 Makkah), or
     mountain CAPE >= 300 J/kg with 700 hPa RH >= 60 %; or our own model's mountain rain >= 5 mm (rainreport)
  5. the steering (700-500 hPa mean wind) weak (< 5 m/s) or carrying the cells west, down onto the plain
  6. inflow: the afternoon wind on the plain blows toward the mountains (sea breeze, or 850 hPa upslope)
A plain is named only when the mountain storms (4), some instability on the plain (CAPE >= 500) and some
moisture (PW >= 115 % or the humid air of 2) are all there, and 4 enhancers or more hold. Otherwise nothing is
written (Fahad: "if nothing is found, write nothing").

check(get, cycle, day, normal) -> [{key, name, region, ...}] ; get(cycle, fh, fields) as daily.gfs_fields at 0.25.
check_all(...) -> (plains rows, mountain-edge rows): the afternoon cells on the escarpment and the harrat (EDGES,
Fahad 16 Nov 2026), from the same fields; see edge_rows.
"""
import math
from datetime import datetime, timedelta

import numpy as np

# name, region of the report it belongs to, lat south/north, plain lon west/east, mountain lon west/east
# (the mountains in the same lat band, unless MTN_BOX gives the storm-making ridge itself)
PLAINS = [
    ("jazan", "سهول تهامة جازان (صبيا وأبو عريش وصامطة)", "جازان", 16.5, 17.9, 42.5, 43.1, 43.0, 43.6),
    ("asir", "تهامة عسير (محايل والدرب والبرك)", "عسير", 17.9, 18.9, 41.6, 42.35, 42.25, 43.0),
    ("qunf", "سهول القنفذة (القوز وحلي والمظيلف) وتهامة الباحة", "مكة المكرمة", 18.9, 19.9, 40.9, 41.55, 41.4, 42.2),
    ("lith", "سهول الليث وأضم", "مكة المكرمة", 19.9, 21.0, 40.1, 40.85, 40.8, 41.6),
    ("makkah", "سهول مكة والجموم وبحرة", "مكة المكرمة", 21.0, 22.2, 39.35, 40.2, 40.15, 40.8),
]
# The ridge where the plain's afternoon storms are born, when the band's mountain box would sample the wrong ground.
# Makkah (16 Nov 2026): the box 40.15-40.8 E over 21-22.2 N is mostly the Taif plateau and the Hijaz interior, where
# GFS CAPE was 4 J/kg, while the escarpment rim (Al-Hada, Ash-Shafa, the heights above Ash-Sharai) had 300-500 and
# storms formed there at 16-17 Makkah and came down onto Ash-Sharai. At 0.25 deg the rim is the 40.25 E column.
MTN_BOX = {"makkah": (21.0, 21.6, 40.15, 40.35)}
PLAIN_HGT, MTN_HGT = 500.0, 1000.0          # m, GFS 0.25 terrain (smoothed)
# the dew point that makes a plain "very humid": the Makkah plains sit farther from the sea and run drier at 2 m
# (13 Nov 2026, plains storms over Makkah and Al-Jumum at 17 C), Tihama at 19-21 C on its storm days
TD_MIN = {"makkah": 17.0, "lith": 18.0}
# PW (% of normal, page box) that counts as the moisture enhancer; Makkah 115 (17 Nov 2026, Fahad: "do not neglect
# PW"): storms on Arafat..Al-Hada with 116 %, 16 Nov with 119 %; test 1-17 Nov: no extra day named (1-9 Nov silent)
PCT_MIN = {"makkah": 115}

FIELDS = [("pw", r":PWAT:entire atmosphere \(considered as a single layer\):"),
          ("cape", r":CAPE:180-0 mb above ground:"), ("rh700", r":RH:700 mb:"),
          ("u700", r":UGRD:700 mb:"), ("v700", r":VGRD:700 mb:"), ("u500", r":UGRD:500 mb:"), ("v500", r":VGRD:500 mb:"),
          ("u850", r":UGRD:850 mb:"), ("v850", r":VGRD:850 mb:"),
          ("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
          ("t2", r":TMP:2 m above ground:"), ("td2", r":DPT:2 m above ground:"),
          # the support from aloft (Fahad 17 Nov 2026, see UPPER below)
          ("z500", r":HGT:500 mb:"), ("rh500", r":RH:500 mb:"), ("t500", r":TMP:500 mb:"),
          ("u200", r":UGRD:200 mb:"), ("v200", r":VGRD:200 mb:")]
STATIC = [("hgt", r":HGT:surface:"), ("land", r":LAND:surface:")]
UTC = (9, 12, 15, 18)                       # 12, 15, 18 and 21 Makkah
BOX = (15.5, 25.0, 38.5, 44.5)      # to 25 N for the harrat (edges below)


def apcp(fh):
    d = f"{fh // 24} day" if fh % 24 == 0 else f"{fh} hour"
    return [("apcp", rf":APCP:surface:0-{d} acc fcst:")]


def cut(a, lat, lon):
    s, n, w, e = BOX
    j, i = (lat >= s) & (lat <= n), (lon >= w) & (lon <= e)
    return a[np.ix_(j, i)], lat[j], lon[i]


def fetch(get, cycle, day, log=print):
    """the fields at UTC hours of the Makkah day `day` (date), from cycle; plus the GFS rain 09-15 and 15-21 UTC"""
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    hours, static, acc, grid = {}, None, {}, None
    for uh in UTC + (21,):
        vt = datetime(day.year, day.month, day.day, uh)
        fh = int((vt - t0).total_seconds() // 3600)
        if fh < 0:
            continue
        want = (FIELDS if uh in UTC else []) + apcp(fh) + (STATIC if static is None else [])
        try:
            f = get(cycle, fh, want)
        except Exception as e:  # noqa: BLE001
            log("plains: fields unavailable", fh, repr(e)[:120])
            continue
        la = np.linspace(90, -90, f["apcp"].shape[0])
        lo = np.linspace(0, 360, f["apcp"].shape[1], endpoint=False)
        sub = {}
        for k, a in f.items():
            sub[k], cla, clo = cut(a, la, lo)
        grid = (cla, clo)
        if static is None:
            static = {"hgt": sub.pop("hgt"), "land": sub.pop("land")}
        acc[uh] = sub.pop("apcp")
        if uh in UTC:
            hours[uh] = sub
        if uh == 12 and fh >= 24:          # the 500 hPa height a day earlier: has it fallen over the edge?
            try:
                g = get(cycle, fh - 24, [("z500", FIELDS_Z500)])["z500"]
                la = np.linspace(90, -90, g.shape[0])
                lo = np.linspace(0, 360, g.shape[1], endpoint=False)
                hours[12]["z500_prev"] = cut(g, la, lo)[0]
            except Exception as e:  # noqa: BLE001
                log("plains: z500 a day earlier unavailable", fh - 24, repr(e)[:120])
    return hours, static, acc, grid


FIELDS_Z500 = r":HGT:500 mb:"


def masks(static, lat, lon, p):
    key, _, _, s, n, pw_, pe, mw, me = p
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    band = (LA >= s) & (LA <= n)
    hg, land = static["hgt"], static["land"] > 0.5
    plain = band & (LO >= pw_) & (LO <= pe) & land & (hg <= PLAIN_HGT)
    if key in MTN_BOX:
        ms, mn, mw, me = MTN_BOX[key]
        band = (LA >= ms) & (LA <= mn)
    mtn = band & (LO >= mw) & (LO <= me) & (hg >= MTN_HGT)
    if mtn.sum() < 3:                          # smoothed terrain: the highest third of the mountain box
        box = band & (LO >= mw) & (LO <= me)
        mtn = box & (hg >= np.percentile(hg[box], 67))
    return plain, mtn


def check(get, cycle, day, pct_of, log=print):
    """pct_of(lat, lon) -> PW as % of normal on `day` for the oscillation page's box over that point (the same
    numbers as the page: southwest box south of 20 N, west box north of it)"""
    return check_all(get, cycle, day, pct_of, log)[0]


def check_all(get, cycle, day, pct_of, log=print):
    """(plains rows, mountain-edge rows) from one fetch of the GFS fields"""
    hours, static, acc, grid = fetch(get, cycle, day, log)
    if static is None or not {12, 15}.issubset(hours):
        return [], []
    prs, eds = plains_rows(hours, static, acc, grid, pct_of, log), edge_rows(hours, static, acc, grid, pct_of, log)
    by = {r["key"]: r for r in prs}
    for e in eds:                          # the plain under the edge, for the evening outflow (OUTFLOW_PLAIN)
        pr = by.get(OUTFLOW_PLAIN.get(e["key"], ""))
        if not pr:
            continue
        # 17 Nov 2026: a named Al-Hada edge is the plain's "mountain storms" (GFS rim CAPE 189 that day, while the
        # cells reached 50-55 dBZ); test 1-17 Nov: Makkah plain named 10, 13, 14, 16 and now 17 Nov, 1-9 Nov silent
        if edge_named(e)[0] and not pr["flags"]["mountain"]:
            pr["flags"]["mountain"] = True
            pr["mountain_from"] = e["key"]
            pr["gate"] = bool(pr["cape_plain"] >= 500 and (pr["pct"] >= 115 or pr["flags"]["humid"]))
            pr["score"] = int(sum(pr["flags"].values()))
        e["plain"] = {"key": pr["key"], "cape": pr["cape_plain"], "td": pr["td"], "steer": pr["steer"],
                      "pct": pr["pct"], "named": bool(named(pr)[0])}
    return prs, eds


def plains_rows(hours, static, acc, grid, pct_of, log=print):
    lat, lon = grid
    out = []
    for p in PLAINS:
        key, name, region = p[:3]
        pl, mt = masks(static, lat, lon, p)
        if pl.sum() < 3 or mt.sum() < 3:
            continue
        H = lambda k, h: hours[h][k] if h in hours else None
        eve = [h for h in (15, 18) if h in hours]
        aft = [h for h in (9, 12) if h in hours]
        pw = float(np.mean([H("pw", h)[pl].mean() for h in (12, 15)]))
        clat, clon = float((p[3] + p[4]) / 2), float((p[5] + p[6]) / 2)
        pct = int(pct_of(clat, clon))
        td = float(H("td2", 12)[pl].mean() - 273.15)
        t2 = float(H("t2", 12)[pl].mean() - 273.15)
        cape_pl = float(max(np.percentile(H("cape", h)[pl], 75) for h in [12] + eve))
        cape_mt = float(max(np.percentile(H("cape", h)[mt], 75) for h in aft))
        rh_mt = float(np.mean([H("rh700", h)[mt].mean() for h in aft]))
        r_mt = float(np.percentile(acc[15][mt] - acc[9][mt], 90)) if 9 in acc and 15 in acc else 0.0
        r_pl = float(np.percentile(acc[21][pl] - acc[15][pl], 90)) if 15 in acc and 21 in acc else None
        both = pl | mt
        us = float(np.mean([(H("u700", h)[both] + H("u500", h)[both]).mean() / 2 for h in (12, 15)]))
        vs = float(np.mean([(H("v700", h)[both] + H("v500", h)[both]).mean() / 2 for h in (12, 15)]))
        sp = math.hypot(us, vs)
        u10 = float(H("u10", 12)[pl].mean())
        u850 = float(H("u850", 12)[pl].mean())
        f = {
            "moist": pct >= PCT_MIN.get(key, 130) or pw >= 40,
            "humid": td >= TD_MIN.get(key, 19.0),
            "unstable": cape_pl >= 1000,
            "mountain": r_mt >= 1 or (cape_mt >= 300 and rh_mt >= 60),
            "steer": sp < 5 or (us <= -2 and sp < 10),
            "inflow": u10 >= 0.5 or u850 >= 1,
        }
        gate = f["mountain"] and cape_pl >= 500 and (pct >= 115 or f["humid"])
        row = {"key": key, "name": name, "region": region, "pw": round(pw, 1), "pct": pct, "td": round(td, 1),
               "t2": round(t2, 1), "cape_plain": int(cape_pl), "cape_mtn": int(cape_mt), "rh700_mtn": int(rh_mt),
               "rain_mtn_gfs": round(r_mt, 1), "rain_plain_gfs": None if r_pl is None else round(r_pl, 1),
               "steer": round(sp, 1), "steer_u": round(us, 1), "u10": round(u10, 1), "u850": round(u850, 1),
               "flags": f, "gate": bool(gate), "score": int(sum(f.values())),
               "box": [p[3], p[4], p[5], p[6]], "mbox": list(MTN_BOX.get(key, (p[3], p[4], p[7], p[8])))}
        log("plains:", key, row["score"], "gate" if gate else "-", {k: v for k, v in row.items() if k not in ("flags", "name", "box", "mbox")})
        out.append(row)
    return out


# ------------------------------------------------------------------ the mountain edges and the harrat (16 Nov 2026)
# Fahad, 16 Nov 2026: "measure the mountain edges". The southwestern highlands, Makkah's escarpment and the harrat
# north of Makkah make their own rain: the sea breeze and the moist southerly air run into the escarpment, the slope
# forces them up, and with steady moisture (PW around 120 % of normal) convective cells form in the afternoon, even
# with no active MJO or wave phase and no trough; scattered, not widespread. The harrat do the same, the black
# basalt heating fast under the sun. Case: 16 Nov, cells on Al-Hada and Ash-Shafa at 16-17 Makkah with PW 120 %.
# The edge is found on the GFS 0.25 terrain itself: land >= 600 m that stands 400 m or more above one of the two
# cells west of it (the escarpment line from Jazan to the west rim of Harrat Rahat); the harrat add their plateau.
# key, name, region, lat south/north, harra plateau box (lat s, n, lon w, e, min height) or None
EDGES = [
    ("jazan_h", "مرتفعات جازان (فيفاء وبني مالك والعيدابي)", "جازان", 16.3, 17.6, None),
    ("asir_s", "حافة عسير الجنوبية (أبها والسودة ورجال ألمع)", "عسير", 17.6, 18.6, None),
    ("asir_n", "حافة عسير الشمالية (النماص وتنومة وبللسمر)", "عسير", 18.6, 19.5, None),
    ("baha", "حافة الباحة (بلجرشي والباحة والمندق)", "الباحة", 19.5, 20.4, None),
    ("sarawat", "سروات مكة (ميسان وبني سعد فوق أضم والليث)", "مكة المكرمة", 20.4, 21.0, None),
    ("hada", "حافة الهدا والشفا فوق الشرائع", "مكة المكرمة", 21.0, 21.8, None),
    ("rahat_s", "حرة رهط وحافتها شرق خليص والكامل", "مكة المكرمة", 21.8, 23.3, (22.0, 23.3, 39.9, 40.75, 800.0)),
    ("rahat_n", "حرة رهط الشمالية جنوب المدينة", "المدينة المنورة", 23.3, 24.6, (23.3, 24.6, 39.6, 40.4, 800.0)),
    ("kishb", "حرة كشب", "مكة المكرمة", None, None, (22.6, 23.4, 41.0, 41.75, 900.0)),
]
EDGE_HGT, EDGE_RISE = 600.0, 400.0


def edge_masks(static, lat, lon, z):
    """(edge cells, their foot: the one or two cells west of them, lower down)"""
    key, _, _, s, n, harra = z
    hg, land = static["hgt"], static["land"] > 0.5
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    west = np.minimum(np.roll(hg, 1, 1), np.roll(hg, 2, 1))       # lon increases with the column
    edge = land & (hg >= EDGE_HGT) & (hg - west >= EDGE_RISE)
    edge[:, :2] = False
    edge &= ~np.roll(edge, 1, 1)               # the front of the escarpment: the first rise, where the sea breeze hits
    edge &= (LA >= s) & (LA <= n) if s is not None else False
    if harra:
        hs, hn, hw, he, hmin = harra
        edge |= land & (LA >= hs) & (LA <= hn) & (LO >= hw) & (LO <= he) & (hg >= hmin)
    foot = (np.roll(edge, -1, 1) | np.roll(edge, -2, 1)) & ~edge
    return edge, foot


def edge_rows(hours, static, acc, grid, pct_of, log=print):
    lat, lon = grid
    out = []
    for z in EDGES:
        key, name, region = z[:3]
        ed, ft = edge_masks(static, lat, lon, z)
        if ed.sum() < 3:
            continue
        H = lambda k, h: hours[h][k]
        aft = [h for h in (9, 12) if h in hours]
        day = [h for h in (9, 12, 15) if h in hours]          # 12, 15 and 18 Makkah: the cells start 15-17 Makkah
        LA, LO = np.meshgrid(lat, lon, indexing="ij")
        clat, clon = float(LA[ed].mean()), float(LO[ed].mean())
        pct = int(pct_of(clat, clon))
        both = ed | ft
        pw = float(np.mean([H("pw", h)[both].mean() for h in aft]))
        cape = float(max(np.percentile(H("cape", h)[ed], 75) for h in day))
        rh = float(np.mean([H("rh700", h)[ed].mean() for h in aft]))
        td = float(np.mean([H("td2", h)[ed].mean() - 273.15 for h in aft]))
        u_ft = float(max(H("u10", h)[ft].mean() for h in aft)) if ft.any() else 0.0
        v_low = float(np.mean([(H("v850", h)[both].mean() + H("v10", h)[both].mean()) / 2 for h in aft]))
        r = float(np.percentile(acc[15][ed] - acc[9][ed], 90)) if 9 in acc and 15 in acc else 0.0
        us = float(np.mean([(H("u700", h)[ed] + H("u500", h)[ed]).mean() / 2 for h in aft]))
        vs = float(np.mean([(H("v700", h)[ed] + H("v500", h)[ed]).mean() / 2 for h in aft]))
        sp = math.hypot(us, vs)
        up = upper(hours, ed, LA, LO, clat, clon, lat, lon)
        f = {
            "moist": pct >= EDGE_PCT or pw >= 35,
            "upslope": u_ft >= 1.0,
            "south": v_low >= 1.0,
            "unstable": cape >= 500,
            "midmoist": rh >= 50,
            "gfs_rain": r >= 0.5,
        }
        # 16 Nov 2026 season test (1 Aug-15 Oct + 1-16 Nov): mid-level moisture and a dew point on the edge cut the
        # dry-air days (the October harrat at Td 0-5 C, summer days with PW >= 35 mm but RH700 30-45 %)
        # ... unless GFS itself rains >= 1 mm on the edge: Fahad (16 Nov 2026), GFS catches convective behaviour better
        # than ECMWF, the test's reference; 25 of the 34 season days that gate removed had GFS rain >= 1 mm
        gate = (f["moist"] and cape >= EDGE_CAPE and (f["upslope"] or f["south"])
                and ((rh >= EDGE_RH and td >= EDGE_TD) or r >= 1.0))
        row = {"key": key, "name": name, "region": region, "kind": "harra" if z[5] else "edge",
               "pw": round(pw, 1), "pct": pct, "td": round(td, 1), "cape": int(cape), "rh700": int(rh),
               "u_foot": round(u_ft, 1), "v_low": round(v_low, 1), "rain_gfs": round(r, 1), "steer": round(sp, 1),
               "flags": f, "gate": bool(gate), "score": int(sum(f.values())), "upper": up,
               "box": [round(float(LA[ed].min()) - 0.125, 2), round(float(LA[ed].max()) + 0.125, 2),
                       round(float(LO[ed].min()) - 0.125, 2), round(float(LO[ed].max()) + 0.125, 2)]}
        log("edges:", key, row["score"], "gate" if gate else "-",
            {k: v for k, v in row.items() if k not in ("flags", "name", "box", "region")})
        out.append(row)
    return out


# ------------------------------------------------------------------ the support from aloft (17 Nov 2026)
# Fahad, 17 Nov 2026, after the second day running of storms on Al-Hada / Ash-Shafa / Arafat (50-55 dBZ at 17 Makkah,
# stronger and lower down the slope than on 16 Nov): watch, every night, what changed aloft. Against the same hour
# of 16 Nov (GFS 06Z f09): the 500 hPa height fell 15 m (5875 -> 5860, a trough's tip over Sinai), RH500 on the rim
# rose from 3 % to 10-22 % (less dry air drawn into the cells), the 200 hPa wind over Makkah rose from 23 to
# 30 m/s with weak divergence (+0.7e-5 /s over the box); T500 stayed near -6.5 C. CAPE over Arafat 900 -> 1150.
# For the Al-Hada / Ash-Shafa edge and the harrat (UPPER_KEYS, Fahad: "حافة الهدا والشفا والحرات") two or more of
# these add one ingredient to the score (a step of confidence) and are named in the sentence. One is enough: the
# day-before 12Z forecast for 17 Nov had only the height fall (-12 m on the Al-Hada edge; RH500 4 %, divergence
# below zero), and so did 16 Nov (-12 m); the edge's own gate (moisture, CAPE >= 250, upslope) still decides whether
# anything is written, so a dry day with falling heights stays silent (3 Nov: fall -8, CAPE 19, silent).
UPPER_KEYS = {"hada", "rahat_s", "rahat_n", "kishb"}
UP_FALL, UP_RH500, UP_DIV, UP_W200, UP_T500, UP_N = -10.0, 10.0, 0.3, 25.0, -7.0, 1
UP_BOX = 1.25                                 # deg round the edge for the 200 hPa divergence
# the plain under an edge: the evening outflow of the edge's cells reaches it (Ash-Sharai, east Makkah, Al-Jumum)
OUTFLOW_PLAIN = {"hada": "makkah"}
OUT_CAPE, OUT_STEER = 700, 5.0


def upper(hours, ed, LA, LO, clat, clon, lat, lon):
    """the support from aloft over an edge at 12 and 15 Makkah: 500 hPa height fall in 24 h (m), RH500 (%), T500 (C),
    the 200 hPa wind (m/s) and its divergence (1e-5 /s, box of +-UP_BOX deg round the edge)"""
    aft = [h for h in (9, 12) if h in hours and "z500" in hours[h]]
    if not aft:
        return None
    H = lambda k, h: hours[h][k]
    rh5 = float(np.mean([H("rh500", h)[ed].mean() for h in aft]))
    t5 = float(np.mean([H("t500", h)[ed].mean() for h in aft])) - 273.15
    fall = None
    if 12 in hours and "z500_prev" in hours[12]:
        fall = float((hours[12]["z500"][ed] - hours[12]["z500_prev"][ed]).mean())
    box = (np.abs(LA - clat) <= UP_BOX) & (np.abs(LO - clon) <= UP_BOX)
    R = 6.371e6
    dy = np.gradient(lat) * np.pi / 180 * R
    dx = np.gradient(lon)[None, :] * np.pi / 180 * R * np.cos(np.radians(lat))[:, None]
    div, w = [], []
    for h in aft:
        u, v = H("u200", h), H("v200", h)
        d = np.gradient(u, axis=1) / dx + np.gradient(v, axis=0) / dy[:, None]
        div.append(float(d[box].mean()) * 1e5)
        w.append(float(np.hypot(u, v)[box].mean()))
    dv, ww = float(np.mean(div)), float(np.mean(w))
    f = {"fall": fall is not None and fall <= UP_FALL, "rh500": rh5 >= UP_RH500,
         "jet": dv >= UP_DIV and ww >= UP_W200, "cold": t5 <= UP_T500}
    return {"fall": None if fall is None else round(fall), "rh500": round(rh5), "t500": round(t5, 1),
            "w200": round(ww), "div200": round(dv, 2), "flags": f, "n": int(sum(f.values()))}


def upper_ok(row):
    up = row.get("upper")
    return bool(row.get("key") in UPPER_KEYS and up and up["n"] >= UP_N)


EDGE_CAPE = 250                             # J/kg, 75th percentile on the front edge, 12-18 Makkah
EDGE_RH, EDGE_TD = 50, 6.0                  # %, C: the gate's mid-level moisture and edge dew point
EDGE_PCT = 115                              # 16 Nov 2026: 117 % on the west box with cells on Al-Hada


# ------------------------------------------------------------------ the words (rainreport adds them to the region)
def n0(x):
    from sa_geo import ar
    return ar(int(round(x)))


def confidence(score):
    return "عالية" if score >= 6 else "متوسطة" if score == 5 else "منخفضة"


def named(row, model_mtn_rain=None):
    """the final decision for a plain, with our model's afternoon mountain rain (mm, max) when known"""
    f = dict(row["flags"])
    if model_mtn_rain is not None and model_mtn_rain >= 5:
        f["mountain"] = True
    gate = f["mountain"] and row["cape_plain"] >= 500 and (row["pct"] >= 115 or f["humid"])
    score = sum(f.values())
    return (gate and score >= 4), score, f


MECHANISM = ("والمعنى أن تيارات السحب الباردة تنحدر من الجبال بعد العصر فترفع هواء السهل، فتنشأ عليه خلايا جديدة بين "
             "المغرب والعشاء، وتجري الأودية بسيول الجبال.")


def sentence(row, model_mtn_rain=None, model_plain_rain=None):
    """one Arabic sentence for the region's line, or None: the plain, its ingredients, the confidence and what our
    model shows there; the mechanism itself (MECHANISM) is added once per region by the rain report"""
    ok, score, f = named(row, model_mtn_rain)
    if not ok:
        return None
    why = []
    if f["moist"]:
        why.append(f"الماء القابل للهطول {n0(row['pct'])}٪ من معدله")
    if f["humid"]:
        why.append(f"ونقطة الندى {n0(row['td'])}° فالهواء حار رطب")
    if f["unstable"]:
        why.append(f"وطاقة عدم الاستقرار نحو {n0(round(row['cape_plain'], -2))} جول/كغ")
    if f["mountain"]:
        why.append("والسحب قائمة على الجبال المجاورة بعد الظهر" if not row.get("mountain_from") else
                   "والخلايا متوقعة على الحافة فوقه بعد الظهر")
    if f["steer"]:
        why.append(f"ورياح القيادة ضعيفة ({n0(row['steer'])} م/ث) فتبقى الخلايا في مكانها" if row["steer"] < 5 else
                   "ورياح القيادة تدفع الخلايا غربًا نحو السهل")
    if f["inflow"]:
        why.append("والرياح على السهل تهب نحو الجبال")
    why[0] = why[0].removeprefix("و")
    s = f"وتتهيأ في {row['name']} عوامل المطر المسائي على السهل: {'، '.join(why)}؛ والثقة {confidence(score)}"
    if model_plain_rain is not None and model_plain_rain < 2:
        s += "، ولا يُظهره نموذجنا على السهل"
    elif model_plain_rain is not None and model_plain_rain >= 5:
        s += "، ونموذجنا يُظهره على السهل أيضًا"
    return s + "."


# ------------------------------------------------------------------ the words for the mountain edges and the harrat
EDGE_MECHANISM = ("والمعنى أن نسيم البحر والهواء الجنوبي الرطب يصطدمان بالحافة فتجبرهما الجبال على الصعود، فتنشأ خلايا "
                  "رعدية متفرقة بعد الظهر حتى دون طور داعم أو موجة نشطة أو أخدود.")
HARRA_MECHANISM = "وتسخن صخور الحرة السوداء تحت الشمس فتقوّي الصعود."


def edge_named(row, model_rain=None):
    """the final decision for an edge, with our model's afternoon rain on it (mm, max) when known"""
    f = dict(row["flags"])
    if model_rain is not None and model_rain >= 5:
        f["gfs_rain"] = True
    f["upper"] = upper_ok(row)              # 17 Nov 2026: Al-Hada / Ash-Shafa and the harrat only
    score = sum(f.values())
    return (row["gate"] and score >= EDGE_SCORE), score, f


EDGE_SCORE = 4                              # with the gate (moisture, RH700 >= 50 %) that is 2 of the other 4


def short(name):
    return name.split(" (")[0]


def rng(a, b, unit):
    return f"{n0(a)}{unit}" if n0(a) == n0(b) else f"{n0(a)} إلى {n0(b)}{unit}"


def edges_sentence(items):
    """one sentence for the named edges of a region (Fahad wants it concise): items [(row, our model's rain or None)]"""
    from rainreport import jl
    got = []
    for row, mr in items:
        ok, score, f = edge_named(row, mr)
        if ok:
            got.append((row, mr, score, f))
    if not got:
        return None
    rows = [g[0] for g in got]
    anyf = lambda k: any(g[3][k] for g in got)
    caps = [round(r["cape"], -1 if r["cape"] < 100 else -2) for r in rows]
    why = [f"الماء القابل للهطول {rng(min(r['pct'] for r in rows), max(r['pct'] for r in rows), '٪')} من معدله"]
    if anyf("upslope"):
        why.append("ونسيم البحر يصعد الحافة")
    if anyf("south"):
        why.append("والهواء الجنوبي الرطب يصل إليها")
    why.append(f"وطاقة عدم الاستقرار نحو {rng(min(caps), max(caps), ' جول/كغ')}")
    if anyf("midmoist"):
        rh = [r["rh700"] for r, _, _, f in got if f["midmoist"]]
        why.append(f"والرطوبة عند ٧٠٠ هكتوباسكال {rng(min(rh), max(rh), '٪')}")
    ups = [r for r in rows if upper_ok(r)]
    if ups:
        u = [r["upper"] for r in ups]
        bits = []
        if any(x["flags"]["fall"] for x in u):
            bits.append(f"هبوط سطح ٥٠٠ هكتوباسكال نحو {n0(max(-x['fall'] for x in u if x['flags']['fall']))} مترًا خلال يوم")
        if any(x["flags"]["rh500"] for x in u):
            v = [x["rh500"] for x in u if x["flags"]["rh500"]]
            bits.append(f"ورطوبة ٥٠٠ هكتوباسكال {rng(min(v), max(v), '٪')} فيقل الهواء الجاف الذي يُضعف السحب")
        if any(x["flags"]["jet"] for x in u):
            v = [x["w200"] for x in u if x["flags"]["jet"]]
            bits.append(f"وتباعد علوي مع رياح ٢٠٠ هكتوباسكال {rng(min(v), max(v), ' م/ث')}")
        if any(x["flags"]["cold"] for x in u):
            v = [x["t500"] for x in u if x["flags"]["cold"]]
            bits.append(f"وبرودة ٥٠٠ هكتوباسكال {n0(min(v))}°")
        bits[0] = bits[0].removeprefix("و")
        where = "" if len(ups) == len(rows) else f" على {jl([short(r['name']) for r in ups])}"
        why.append(f"ويدعمها من الأعلى{where} {'، '.join(bits)}")
    conf = {}
    for r, _, sc, _ in got:
        conf.setdefault(confidence(sc), []).append(short(r["name"]))
    if len(conf) == 1:
        c = f"والثقة {next(iter(conf))}"
    else:
        c = "والثقة " + " و".join(f"{k} على {jl(v)}" for k, v in conf.items())
    s = f"وعلى {jl([r['name'] for r in rows])} تتهيأ أمطار الحمل الحراري بعد الظهر: {'، '.join(why)}؛ {c}"
    no = [short(r["name"]) for r, mr, _, _ in got if mr is not None and mr < 2]
    yes = [short(r["name"]) for r, mr, _, _ in got if mr is not None and mr >= 5]
    if no:
        s += "، ولا يُظهرها نموذجنا " + ("هناك" if len(no) == len(got) else f"على {jl(no)}")
    if yes:
        s += "، ونموذجنا يُظهرها " + ("هناك أيضًا" if len(yes) == len(got) else f"على {jl(yes)}")
    s += "."
    # the evening outflow down to the plain (Fahad 17 Nov 2026): hot unstable air below and slow cells above
    for r in rows:
        pl = r.get("plain")
        # (when the Makkah plain is itself named its own sentence says it, with the same ingredients)
        if (r["key"] == "hada" and pl and not pl.get("named") and pl["cape"] >= OUT_CAPE
                and r["steer"] < OUT_STEER):
            s += (" وقد تنحدر تيارات السحب الباردة من حافة الهدا والشفا نحو الشرائع والجعرانة وشرق مكة، والهواء "
                  f"على السهل غير مستقر (نحو {n0(round(pl['cape'], -2))} جول/كغ) والماء القابل للهطول "
                  f"{n0(pl.get('pct', r['pct']))}٪ من معدله، فتنشأ خلايا جديدة بين المغرب والعشاء "
                  "قد تصل إلى الجموم ووادي فاطمة.")
    return s
