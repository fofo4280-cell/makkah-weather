"""Hour by hour (every 3 hours of the Makkah day) reading of the rain-making ingredients zone by zone over the whole
Kingdom, sea and coast included (Fahad, 28 Nov 2026: «اول كنت تقرأ وتكتب بناء على متوسط ساعات يومي أما الان فلدينا
حركة ساعاتيه مستمره»). The same zones and the same activity rule as the Kingdom-wide sweep (troughreach.ZONES, act):
thunder showers where the fuel (CAPE), a moist 700 hPa layer and ascent meet; light rain where a deep moist 700 hPa
layer rises. Each zone gets, per day, when the ingredients first meet, when they peak, when they end, and where the
700-500 hPa wind carries the cells; GFS 0.25 instant fields (GFS: the dynamics and the convective environment).

    fetch(cycle, day0, ndays, get_fields) -> {"hours": [...], "days": [{"d", "z": {zone: [per hour]}}]}
    runs(T, d) -> {zone: run}  windows(T, d0, d1) -> the report's table rows
"""
import math
from datetime import date, datetime, timedelta

import numpy as np

import troughreach as TR

HOURS = (0, 3, 6, 9, 12, 15, 18, 21)
HOUR_W = {0: "منتصف الليل", 3: "الثالثة فجرًا", 6: "السادسة صباحًا", 9: "التاسعة صباحًا", 12: "الظهر",
          15: "الثالثة عصرًا", 18: "السادسة مساءً", 21: "التاسعة ليلًا"}
FIELDS = [("w500", r":VVEL:500 mb:"), ("rh700", r":RH:700 mb:"),
          ("pw", r":PWAT:entire atmosphere \(considered as a single layer\):"), ("cape", r":CAPE:180-0 mb above ground:"),
          ("u6", r":UGRD:600 mb:"), ("v6", r":VGRD:600 mb:")]
DIRS = ["الشمال", "الشمال الشرقي", "الشرق", "الجنوب الشرقي", "الجنوب", "الجنوب الغربي", "الغرب", "الشمال الغربي"]


def _vals(g):
    from scipy.ndimage import uniform_filter
    la, lo = TR._grid()
    w = uniform_filter(g["w500"], 3, mode="nearest")
    out = {}
    for key, _n, a, b, c, d in TR.ZONES:
        ix = np.ix_((la >= a) & (la <= b), (lo >= c) & (lo <= d))
        v = {"rh": round(float(g["rh700"][ix].mean())), "pw": round(float(g["pw"][ix].mean()), 1),
             "cape": round(float(np.quantile(g["cape"][ix], 0.9))), "w": round(float(w[ix].min()), 2),
             "u": round(float(g["u6"][ix].mean()), 1), "v": round(float(g["v6"][ix].mean()), 1)}
        v["act"] = TR.act(v)
        out[key] = v
    return out


def fetch(cycle, day0, ndays, get_fields, procs=3):
    """the Makkah days day0 .. day0+ndays-1, every 3 hours; a missing time is left out"""
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    jobs = []
    for k in range(ndays):
        d = day0 + timedelta(days=k)
        for h in HOURS:
            fh = int((datetime(d.year, d.month, d.day) + timedelta(hours=h - 3) - t0).total_seconds() // 3600)
            if 0 <= fh <= 384 and not (fh > 120 and fh % 3):
                jobs.append((d.isoformat(), h, fh))
    res = {}

    def one(job):
        d, h, fh = job
        for _ in range(2):
            try:
                g = {n: TR.cut(a) for n, a in get_fields(cycle, fh, res="0p25", fields=FIELDS).items()}
                return d, h, _vals(g)
            except Exception as e:  # noqa: BLE001
                err = e
        print("timing download failed", d, h, repr(err)[:120], flush=True)
        return d, h, None
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(procs) as ex:
        for d, h, v in ex.map(one, jobs):
            if v:
                res.setdefault(d, {})[h] = v
    days = []
    for d in sorted(res):
        z = {key: [dict(res[d][h][key], h=h) for h in HOURS if h in res[d]] for key in TR.NAME}
        days.append({"d": d, "z": z})
    return {"hours": list(HOURS), "days": days, "cycle": cycle}


def steer_word(u, v):
    sp = math.hypot(u, v)
    if sp < 2 or sp > 60:      # calm, or a broken value
        return None, (sp if sp <= 60 else 0)
    ang = (math.degrees(math.atan2(u, v)) + 360) % 360      # toward
    return DIRS[int((ang + 22.5) // 45) % 8], sp


def episodes(hs):
    """[[h, ...], ...] runs of consecutive 3-hourly hours"""
    out = []
    for h in hs:
        if out and h - out[-1][-1] == 3:
            out[-1].append(h)
        else:
            out.append([h])
    return out


def ep_word(ep):
    return HOUR_W[ep[0]] if len(ep) == 1 else f"من {HOUR_W[ep[0]]} إلى {HOUR_W[ep[-1]]}"


def runs(T, d):
    """{zone: {"lv", "eps", "pk", "cape", "rh", "to", "sp"}} for the Makkah day d: the active hours cut into episodes,
    the peak hour (strongest level, then most fuel), the steering at the peak"""
    day = next((x for x in (T or {}).get("days") or [] if x["d"] == str(d)), None)
    if not day:
        return {}
    out = {}
    for k, hs in day["z"].items():
        on = [x for x in hs if x.get("act")]
        if not on:
            continue
        pk = max(on, key=lambda x: (x["act"], x["cape"]))
        to, sp = steer_word(pk["u"], pk["v"])
        out[k] = {"lv": max(x["act"] for x in on), "eps": episodes([x["h"] for x in on]), "pk": pk["h"],
                  "cape": pk["cape"], "rh": pk["rh"], "to": to, "sp": round(sp)}
    return out


def busiest(T, d0, d1, keys=None):
    """(day, hour, zones) of the time with the most zones active (thunder showers first) between d0 and d1"""
    best = None
    for day in (T or {}).get("days") or []:
        if not (str(d0) <= day["d"] <= str(d1)):
            continue
        for i, h in enumerate(T["hours"]):
            zs = [k for k, hs in day["z"].items() if (keys is None or k in keys)
                  for x in hs if x["h"] == h and x.get("act")]
            sc = (len(zs), day["d"], -h)
            if zs and (best is None or len(zs) > len(best[2])):
                best = (day["d"], h, zs)
    return best


def part(h):
    return "ليلي" if h >= 21 or h <= 3 else "صباحي" if h <= 9 else "نهاري" if h <= 15 else "مسائي"


def table(T, d0, d1, sea=True):
    """the rows of the hourly timing table: day, zones (the same hours together), activity, hours, peak, carried"""
    from report2 import ar, ar_date, jl
    rows = []
    d = d0
    while d <= d1:
        R = {k: r for k, r in runs(T, d).items() if sea or not k.startswith("sea_")}
        grp = {}
        for k, r in R.items():
            key = (r["lv"], tuple(tuple(e) for e in r["eps"]), r["pk"], r["to"])
            grp.setdefault(key, []).append(k)
        for (lv, eps, pk, to), ks in sorted(grp.items(), key=lambda x: (-x[0][0], x[0][1][0][0])):
            sp = max(R[k]["sp"] for k in ks)
            rows.append([ar_date(d), jl([TR.NAME[k] for k in ks]), TR.ACT_WORD[lv], "، ثم ".join(ep_word(e) for e in eps),
                         HOUR_W[pk] + f" ({part(pk)})", f"نحو {to} بنحو {ar(sp)} م/ث" if to else "شبه ثابتة"])
        d += timedelta(days=1)
    return rows


# the wind-collision map every 3 hours (taifconv hourly verdicts: «تصادم قوي قرب الطائف، أبها ومكة»): the trigger of
# the terrain cells, by region, from the cities each verdict names
CITY_REGION = {"الطائف": "مكة المكرمة", "مكة": "مكة المكرمة", "جدة": "مكة المكرمة", "الباحة": "الباحة", "أبها": "عسير",
               "جازان": "جازان", "نجران": "نجران", "المدينة": "المدينة المنورة", "حائل": "حائل", "بريدة": "القصيم",
               "تبوك": "تبوك", "الرياض": "الرياض", "الدمام": "الشرقية", "سكاكا": "الجوف", "عرعر": "الحدود الشمالية"}


def trigger_hours(st, d):
    """{region: [Makkah hours]} of strong wind collision near the region's city on the day d"""
    r = next((x for x in (st.get("taifc") or {}).get("rows") or [] if x["d"] == str(d)), None)
    out = {}
    for x in (r or {}).get("hours") or []:
        t = x.get("t") or ""
        if "لا تصادم" in t:
            continue
        for c, reg in CITY_REGION.items():
            if c in t and x["h"] not in out.get(reg, []):
                out.setdefault(reg, []).append(x["h"])
    return {k: sorted(v) for k, v in out.items()}


def day_window(hs):
    """the daytime-evening episode (noon to 9 PM side) of the trigger hours as words, or None"""
    eps = [e for e in episodes(sorted(hs)) if e[-1] >= 12]
    if not eps:
        return None
    e = max(eps, key=len)
    return ep_word(e) if len(e) > 1 else HOUR_W[e[0]]
