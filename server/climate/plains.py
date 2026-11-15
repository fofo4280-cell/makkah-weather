"""The evening storms of the coastal plains (Fahad, 15 Nov 2026): a check, from the GFS forecast of the report day,
for the pattern our 3 km model tends to miss.

The pattern: storms form on the mountains in the afternoon (the Sarawat and Asir east of Tihama, Taif and the
Hijaz mountains east of Makkah); their cold outflow runs down the slopes into very hot, very humid lowland air,
lifts it (with the sea breeze coming in from the west), and new cells start over the plains in the evening, between
Maghrib and Isha. Weak steering keeps the cells in place, and the wadis bring the mountain flood water down.
15 Nov 2026: floods on the Al-Qunfudhah plains while the analysis put the rain on the slopes (PW 161 % of normal
over the southwest, steering under 5 m/s, SE upslope flow at 850 hPa).

For each plain, with its mountains just east of it, six enhancers are checked:
  1. moisture:      PW >= 130 % of normal over the page's box (southwest / west), or >= 40 mm over the plain
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
"""
import math
from datetime import datetime, timedelta

import numpy as np

# name, region of the report it belongs to, lat south/north, plain lon west/east, mountain lon west/east
PLAINS = [
    ("jazan", "سهول تهامة جازان (صبيا وأبو عريش وصامطة)", "جازان", 16.5, 17.9, 42.5, 43.1, 43.0, 43.6),
    ("asir", "تهامة عسير (محايل والدرب والبرك)", "عسير", 17.9, 18.9, 41.6, 42.35, 42.25, 43.0),
    ("qunf", "سهول القنفذة (القوز وحلي والمظيلف) وتهامة الباحة", "مكة المكرمة", 18.9, 19.9, 40.9, 41.55, 41.4, 42.2),
    ("lith", "سهول الليث وأضم", "مكة المكرمة", 19.9, 21.0, 40.1, 40.85, 40.8, 41.6),
    ("makkah", "سهول مكة والجموم وبحرة", "مكة المكرمة", 21.0, 22.2, 39.35, 40.2, 40.15, 40.8),
]
PLAIN_HGT, MTN_HGT = 500.0, 1000.0          # m, GFS 0.25 terrain (smoothed)
# the dew point that makes a plain "very humid": the Makkah plains sit farther from the sea and run drier at 2 m
# (13 Nov 2026, plains storms over Makkah and Al-Jumum at 17 C), Tihama at 19-21 C on its storm days
TD_MIN = {"makkah": 17.0, "lith": 18.0}

FIELDS = [("pw", r":PWAT:entire atmosphere \(considered as a single layer\):"),
          ("cape", r":CAPE:180-0 mb above ground:"), ("rh700", r":RH:700 mb:"),
          ("u700", r":UGRD:700 mb:"), ("v700", r":VGRD:700 mb:"), ("u500", r":UGRD:500 mb:"), ("v500", r":VGRD:500 mb:"),
          ("u850", r":UGRD:850 mb:"), ("v850", r":VGRD:850 mb:"),
          ("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
          ("t2", r":TMP:2 m above ground:"), ("td2", r":DPT:2 m above ground:")]
STATIC = [("hgt", r":HGT:surface:"), ("land", r":LAND:surface:")]
UTC = (9, 12, 15, 18)                       # 12, 15, 18 and 21 Makkah
BOX = (15.5, 23.0, 38.5, 44.5)


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
    return hours, static, acc, grid


def masks(static, lat, lon, p):
    _, _, _, s, n, pw_, pe, mw, me = p
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    band = (LA >= s) & (LA <= n)
    hg, land = static["hgt"], static["land"] > 0.5
    plain = band & (LO >= pw_) & (LO <= pe) & land & (hg <= PLAIN_HGT)
    mtn = band & (LO >= mw) & (LO <= me) & (hg >= MTN_HGT)
    if mtn.sum() < 3:                          # smoothed terrain: the highest third of the mountain box
        box = band & (LO >= mw) & (LO <= me)
        mtn = box & (hg >= np.percentile(hg[box], 67))
    return plain, mtn


def check(get, cycle, day, pct_of, log=print):
    """pct_of(lat, lon) -> PW as % of normal on `day` for the oscillation page's box over that point (the same
    numbers as the page: southwest box south of 20 N, west box north of it)"""
    hours, static, acc, grid = fetch(get, cycle, day, log)
    if static is None or not {12, 15}.issubset(hours):
        return []
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
            "moist": pct >= 130 or pw >= 40,
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
               "box": [p[3], p[4], p[5], p[6]], "mbox": [p[3], p[4], p[7], p[8]]}
        log("plains:", key, row["score"], "gate" if gate else "-", {k: v for k, v in row.items() if k not in ("flags", "name", "box", "mbox")})
        out.append(row)
    return out


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


def sentence(row, model_mtn_rain=None, model_plain_rain=None):
    """one Arabic sentence for the region's line, or None"""
    ok, score, f = named(row, model_mtn_rain)
    if not ok:
        return None
    why = []
    if f["moist"]:
        why.append(f"الماء القابل للهطول {n0(row['pct'])}٪ من معدله")
    if f["humid"]:
        why.append(f"هواء السهل حار رطب (نقطة الندى {n0(row['td'])}°)")
    if f["unstable"]:
        why.append(f"طاقة عدم الاستقرار على السهل نحو {n0(round(row['cape_plain'], -2))} جول/كغ")
    if f["mountain"]:
        why.append("حمل الجبال المجاورة بعد الظهر قائم")
    if f["steer"]:
        why.append(f"رياح القيادة ضعيفة ({n0(row['steer'])} م/ث) فتثبت الخلايا" if row["steer"] < 5 else
                   "رياح القيادة تدفع الخلايا غربًا نحو السهل")
    if f["inflow"]:
        why.append("الرياح على السهل تهب نحو الجبال")
    s = (f"وفي {row['name']} معززات للنمط الحملي المسائي: {'، و'.join(why)}؛ فقد تنزل تيارات السحب الباردة من "
         "الجبال فترفع هواء السهل وتنشأ خلايا جديدة عليه بين المغرب والعشاء، وتجري الأودية بسيول الجبال؛ "
         f"والثقة {confidence(score)}")
    if model_plain_rain is not None and model_plain_rain < 2:
        s += "، ولا يظهره نموذجنا على السهل"
    elif model_plain_rain is not None and model_plain_rain >= 5:
        s += "، ويظهره نموذجنا على السهل أيضًا"
    return s + "."
