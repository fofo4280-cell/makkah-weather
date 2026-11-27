"""Where a trough's forcing reaches, zone by zone: the 24 h fall of the 500 hPa surface, the coldest 500 hPa air and
the strongest ascent at 500 hPa over the Red Sea, the coasts, the plains and the desert of the Kingdom (Fahad, 27 Nov
2026: «الحالة كلها مبنية على اخدود قوي يزحف من الشمال الغربي فالمفترض انك درست تأثيرات الاخدود من البحر وحتى حدود
السعودية كاملة من لحظة تأثيره على السعودية بحرا وساحلا وسهلا صحراء»).

Why: troughs.py follows the trough's AXIS and its southern tip. With the axis held over Egypt (28-31 E) by a ridge over
Iran, report3.north_break wrote «no cut-off for Makkah, the coasts only get no-trough sea cells», while the falls ahead of
the axis (40-70 m in 24 h over the northern Red Sea, Tabuk, Al-Jouf; 30-37 m over Yanbu-Rabigh and Al-Madinah in GFS and
ECMWF of 27 Nov) and the cold air aloft over the warm sea were the trough's own forcing of the Umluj-Rabigh cells. The
area ahead of the axis is where the lift is; this module reads it directly from the fields.

GFS 0.25, four times a day: day k keeps 18 UTC of the evening before and 00, 06, 12 UTC (9 PM to 3 PM Makkah, as the
sea cells), each against 24 h before. 27 Nov 2026: zones over the whole Kingdom (Duba-Haql, Tayma, Al-Qunfudhah-Al-Birk,
Bisha, Najran, Wadi Ad-Dawasir, Sharurah, Al-Kharj, Az-Zulfi, Hafr Al-Batin, Al-Ahsa, the Gulf coast) and an activity
flag per time (thunder showers possible / light rain possible), so any activity anywhere is named in the report.

    fetch(cycle, days, get_fields) -> [{d, z: {zone: {dz, t5, w}}}]
    reach(rows, d0, d1) -> [(zone, dz, t5, w)] of the zones the forcing reaches on those days, strongest fall first
    activity_table(rows, d0, d1) -> [[day, thunder showers possible, light rain possible]]
"""
import numpy as np

BOX = (14.0, 33.0, 34.0, 56.0)   # lat0, lat1, lon0, lon1
RES = 0.25
# (key, name, lat0, lat1, lon0, lon1): sea, coast, plain, desert, north to south then west to east
ZONES = [("sea_n", "شمال البحر الأحمر (مقابل الوجه وأملج)", 24.8, 27.0, 35.0, 37.0),
         ("sea_m", "وسط البحر الأحمر (مقابل ينبع ورابغ)", 22.3, 24.8, 37.0, 38.8),
         ("sea_s", "البحر الأحمر مقابل جدة والليث", 19.8, 22.3, 38.0, 39.3),
         ("c_tabuk", "ساحل تبوك (الوجه وأملج)", 24.8, 26.8, 36.6, 37.8),
         ("c_madinah", "ساحل المدينة (ينبع والرايس) ورابغ", 22.5, 24.5, 38.2, 39.4),
         ("jeddah_makkah", "جدة ومكة", 21.2, 21.9, 39.1, 40.1),
         ("taif", "الطائف والحواف", 20.9, 21.6, 40.1, 40.8),
         ("madinah", "المدينة المنورة", 24.0, 25.0, 39.2, 40.2),
         ("khaybar", "خيبر والعلا", 25.5, 26.8, 37.8, 39.6),
         ("tabuk", "تبوك", 27.8, 29.0, 35.8, 37.5),
         ("jouf", "الجوف والقريات", 29.5, 31.5, 37.5, 40.5),
         ("nb", "الحدود الشمالية", 29.5, 31.5, 41.0, 44.5),
         ("hail", "حائل", 26.8, 28.2, 40.8, 42.5),
         ("qassim", "القصيم", 25.8, 26.8, 42.8, 44.5),
         ("riyadh", "الرياض", 24.0, 25.5, 45.8, 47.5),
         ("eastern", "الشرقية", 25.5, 28.0, 47.5, 50.0),
         ("asir", "الباحة وعسير", 18.0, 20.3, 41.3, 43.0),
         ("jazan", "جازان", 16.6, 17.6, 42.5, 43.3),
         # the rest of the Kingdom (Fahad 27 Nov 2026: «انت تحلل السعودية كاملة بحرا وساحل ويابسة واي نشاط فيها يذكر»)
         ("duba", "ضباء وحقل", 27.0, 29.5, 34.8, 35.9), ("tayma", "تيماء", 27.2, 28.2, 38.0, 39.5),
         ("qunf", "القنفذة والبرك", 17.8, 20.0, 40.3, 41.5), ("bisha", "بيشة ورنية", 19.5, 21.0, 42.3, 43.8),
         ("najran", "نجران", 17.0, 18.6, 43.6, 45.5), ("dawasir", "وادي الدواسر والأفلاج", 20.0, 22.5, 44.5, 46.8),
         ("sharurah", "شرورة والربع الخالي", 17.0, 20.0, 46.5, 51.0), ("kharj", "الخرج والدلم", 23.0, 24.0, 46.8, 48.0),
         ("majmaah", "الزلفي والمجمعة", 25.5, 26.5, 44.5, 46.0), ("hafr", "حفر الباطن", 27.5, 28.8, 44.5, 46.5),
         ("ahsa", "الأحساء", 24.5, 25.5, 48.5, 50.0), ("gulf", "ساحل الخليج", 26.0, 27.8, 49.3, 50.3)]
NAME = {k: n for k, n, *_ in ZONES}
SEA = ("sea_n", "sea_m", "sea_s", "c_tabuk", "c_madinah", "jeddah_makkah")
FIELDS = [("z500", r":HGT:500 mb:"), ("t500", r":TMP:500 mb:"), ("w500", r":VVEL:500 mb:"), ("rh700", r":RH:700 mb:"),
          ("pw", r":PWAT:entire atmosphere \(considered as a single layer\):"), ("cape", r":CAPE:180-0 mb above ground:")]
# activity at one time (any place, any hour): thunder showers where the fuel, a moist 700 hPa layer and ascent meet;
# light rain where a deep moist 700 hPa layer rises (the stratiform rain of a trough), read 4 times a day
ACT_WORD = {2: "زخات رعدية ممكنة", 1: "مطر خفيف ممكن"}
FALL = -30.0     # m in 24 h: the forcing reaches the zone
FALL_COLD = (-20.0, -11.0)   # or a smaller fall with cold air aloft (C)


def cut(a):
    j0, j1 = int(round((90 - BOX[1]) / RES)), int(round((90 - BOX[0]) / RES))
    i0, i1 = int(round(BOX[2] / RES)), int(round(BOX[3] / RES))
    return a[j0:j1 + 1, i0:i1 + 1]


def _grid():
    return np.arange(BOX[1], BOX[0] - 1e-6, -RES), np.arange(BOX[2], BOX[3] + 1e-6, RES)


def _zone_vals(g, g0):
    from scipy.ndimage import uniform_filter
    la, lo = _grid()
    w = uniform_filter(g["w500"], 3, mode="nearest")
    out = {}
    for key, _n, a, b, c, d in ZONES:
        J, I = (la >= a) & (la <= b), (lo >= c) & (lo <= d)
        ix = np.ix_(J, I)
        v = {"dz": round(float(g["z500"][ix].mean() - g0["z500"][ix].mean())),
             "t5": round(float(g["t500"][ix].min() - 273.15), 1), "w": round(float(w[ix].min()), 2)}
        if "rh700" in g:
            v.update(rh=round(float(g["rh700"][ix].mean())), pw=round(float(g["pw"][ix].mean()), 1),
                     cape=round(float(np.quantile(g["cape"][ix], 0.9))))
            v["act"] = act(v)
        out[key] = v
    return out


def act(v):
    """2 thunder showers possible, 1 light rain possible, 0 nothing, from one time's zone values"""
    if v["cape"] >= 400 and v["rh"] >= 50 and v["w"] <= -0.15 and v["pw"] >= 12:
        return 2
    if v["rh"] >= 65 and v["w"] <= -0.25 and v["pw"] >= 10:
        return 1
    return 0


def fetch(cycle, days, get_fields):
    """the days 0..days of the cycle; day k = the cycle date + k, valid times 00 and 12 UTC (leads 24k+12, 24k+24 of
    a 12 UTC cycle), each against 24 h before; the day keeps the strongest fall, the coldest air and ascent"""
    from datetime import datetime, timedelta
    t0 = datetime.strptime(cycle[:8], "%Y%m%d").date()
    base = 0 if cycle[8:10] == "12" else 12
    cache = {}

    def g(fh):
        if fh not in cache:
            cache[fh] = {n: cut(a) for n, a in get_fields(cycle, fh, res="0p25", fields=FIELDS).items()}
        return cache[fh]
    rows = []
    for k in range(1, days + 1):
        vals = []
        for h in (6, 12, 18, 24):
            fh = 24 * (k - 1) + h + base
            try:
                vals.append(_zone_vals(g(fh), g(fh - 24 if fh >= 24 else 0)))
            except Exception as e:  # noqa: BLE001
                print("troughreach download failed", fh, repr(e)[:120], flush=True)
        if not vals:
            continue
        z = {key: {"dz": min(v[key]["dz"] for v in vals), "t5": min(v[key]["t5"] for v in vals),
                   "w": min(v[key]["w"] for v in vals), "act": max(v[key].get("act", 0) for v in vals)} for key in NAME}
        rows.append({"d": (t0 + timedelta(days=k)).isoformat(), "z": z})
    return rows


def reaches(v):
    return v["dz"] <= FALL or (v["dz"] <= FALL_COLD[0] and v["t5"] <= FALL_COLD[1])


def reach(rows, d0, d1):
    """[(zone, dz, t5, w)] reached on the days d0..d1 (strongest fall of the days), strongest fall first"""
    best = {}
    for r in rows or []:
        if not (str(d0) <= r["d"] <= str(d1)):
            continue
        for k, v in r["z"].items():
            if reaches(v) and (k not in best or v["dz"] < best[k]["dz"]):
                best[k] = v
    return sorted([(k, v["dz"], v["t5"], v["w"]) for k, v in best.items()], key=lambda x: x[1])


def words(rows, d0, d1):
    """one paragraph for the wave section, or None"""
    from report2 import ar, jl
    R = reach(rows, d0, d1)
    if not R:
        return None
    sea = [x for x in R if x[0] in SEA]
    land = [x for x in R if x[0] not in SEA]

    def item(x):
        return f"{NAME[x[0]]} ({ar(-x[1])} م، وحرارة ٥٠٠ {ar(int(round(x[2])))}°)"
    t = ("منطقة تأثير الأخدود أمام محوره: يهبط سطح ٥٠٠ هكتوباسكال في ٢٤ ساعة على ")
    t += jl([item(x) for x in R[:7]])
    if sea:
        t += ("؛ فالأخدود يبلغ البحر الأحمر والسواحل الغربية نفسها وإن بقي محوره غرب البحر، والهواء البارد في الأعلى فوق "
              "البحر الدافئ يرفع طاقة عدم الاستقرار، فالخلايا البحرية في أيامه من صنع الأخدود لا حمل بلا أخدود")
    return t + "."


def activity(rows, d0, d1):
    """{day: {2: [zones], 1: [zones]}} of the days d0..d1 with any activity"""
    out = {}
    for r in rows or []:
        if not (str(d0) <= r["d"] <= str(d1)):
            continue
        by = {}
        for k, v in r["z"].items():
            # the open sea is read by the sea-cell index (seacell.py), which tests its own fuel, trigger and carry
            if v.get("act") and not k.startswith("sea_"):
                by.setdefault(v["act"], []).append(k)
        if by:
            out[r["d"]] = by
    return out


def activity_table(rows, d0, d1):
    """the rows of the Kingdom-wide sweep table: day, thunder showers possible, light rain possible"""
    from datetime import date, timedelta
    from report2 import ar_date, jl
    out = []
    for d, by in sorted(activity(rows, d0, d1).items()):
        # day d runs from 9 PM of the day before: named as the night that starts then, as the sea cells
        out.append([ar_date(date.fromisoformat(d) - timedelta(days=1)), jl([NAME[k] for k in by.get(2, [])]) or "—",
                    jl([NAME[k] for k in by.get(1, [])]) or "—"])
    return out
