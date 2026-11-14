"""تشخيص الحالة: the synoptic story of the current spell, in the words a forecaster would use, from GFS analyses
of the last two days and the night's forecast for three days: where the upper trough or low is and where it goes
(away, back west, or still), the cold air it leaves aloft, the moisture and where it comes from, the low-level
winds against the mountains, and how the storms will move (with back-building when the steering is weak).

rows: case_study.summarise() dicts with an added "time" (datetime, UTC) and "kind" ("a" analysis, "f" forecast).
"""
import math
from datetime import timedelta

import case_study as CS
import troughs as TR
from sa_geo import ar, ar_date, join

DIRS_TO = ["الشمال", "الشمال الشرقي", "الشرق", "الجنوب الشرقي", "الجنوب", "الجنوب الغربي", "الغرب", "الشمال الغربي"]
DIRS_FROM = ["شمالية", "شمالية شرقية", "شرقية", "جنوبية شرقية", "جنوبية", "جنوبية غربية", "غربية", "شمالية غربية"]


def n1(x):
    return (f"{x:.1f}".rstrip("0").rstrip(".") if abs(x) < 10 else f"{x:.0f}").replace("-", "−").translate(
        str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫"))


def to_dir(u, v):
    return DIRS_TO[int(((math.degrees(math.atan2(u, v)) % 360) + 22.5) // 45) % 8]


def from_dir(u, v):
    return DIRS_FROM[int(((math.degrees(math.atan2(-u, -v)) % 360) + 22.5) // 45) % 8]


def bearing(la0, lo0, la1, lo1):
    return math.degrees(math.atan2((lo1 - lo0) * math.cos(math.radians((la0 + la1) / 2)), la1 - la0)) % 360


def snapshots(gfs_fields, analyses, fc_cycle, hours, log=print):
    """analyses: [cycle YYYYMMDDHH]; the forecast fc_cycle at hours. Rows in time order; a failed time is left out."""
    from datetime import datetime
    rows = []
    for c in analyses:
        try:
            r = CS.summarise(c, gfs_fields(c, 0, fields=CS.F))
            r["time"], r["kind"] = datetime.strptime(c, "%Y%m%d%H"), "a"
            rows.append(r)
        except Exception as e:  # noqa: BLE001
            log("diag: skip analysis", c, repr(e)[:100])
    t0 = datetime.strptime(fc_cycle, "%Y%m%d%H")
    for h in hours:
        try:
            r = CS.summarise(fc_cycle, gfs_fields(fc_cycle, h, fields=CS.F))
            r["time"], r["kind"] = t0 + timedelta(hours=h), "f"
            rows.append(r)
        except Exception as e:  # noqa: BLE001
            log("diag: skip forecast", h, repr(e)[:100])
    return sorted(rows, key=lambda r: r["time"])


def _lobe(r):
    """the main upper disturbance near Arabia: a closed low south of 36 N, else the strongest vorticity lobe"""
    lows = [x for x in r["lows"] if x["closed"] and 12 <= x["lat"] <= 36 and 25 <= x["lon"] <= 62]
    if lows:
        x = lows[0]
        return {"lat": x["lat"], "lon": x["lon"], "closed": True, "depth": x["depth_m"]}
    lb = [x for x in r["lobes"] if 14 <= x["lat"] <= 38 and 28 <= x["lon"] <= 60]
    near = [x for x in lb if x["lat"] <= 32 and 32 <= x["lon"] <= 56]     # the one over or beside the Kingdom first
    if near or lb:
        x = (near or lb)[0]
        return {"lat": x["lat"], "lon": x["lon"], "closed": False, "vort": x["vort"]}
    return None


def mk_day(t):
    return (t + timedelta(hours=3)).date()     # the Makkah day of a UTC time


def text(rows, now):
    """the diagnosis lines (Arabic). now: the newest analysis time"""
    if len(rows) < 3:
        return []
    past = [r for r in rows if r["kind"] == "a"]
    fut = [r for r in rows if r["kind"] == "f"]
    cur = past[-1]
    out = []
    # 1) the upper disturbance: where it was, where it is, where it goes
    with_lobe = [r for r in past if _lobe(r)]
    first = min(with_lobe, key=lambda r: (lambda x: abs(x["lat"] - 24) + abs(x["lon"] - 42))(_lobe(r))) if with_lobe else None
    l0, l1 = (_lobe(first) if first else None), _lobe(cur)
    if l0:
        what = "منخفض مقطوع مغلق" if l0["closed"] else "قاع الأخدود وذراع دوامته"
        s = f"الاضطراب العلوي (٥٠٠ هكتوباسكال): {what} فوق {TR.place(l0['lat'], l0['lon'])} {ar_date(mk_day(first['time']))}"
        if l1 and (abs(l1["lat"] - l0["lat"]) + abs(l1["lon"] - l0["lon"])) >= 3:
            b = bearing(l0["lat"], l0["lon"], l1["lat"], l1["lon"])
            moved = DIRS_TO[int((b + 22.5) // 45) % 8]
            kind = ("فهو يرحل" if 0 <= b < 135 else "فهو يرتد غربًا" if 180 <= b < 315 else "")
            s += f"، واليوم فوق {TR.place(l1['lat'], l1['lon'])} متجهًا نحو {moved}" + (f"، {kind}" if kind else "")
        elif l1:
            s += "، وما زال شبه ثابت"
        else:
            s += "، ثم ضعف وخرج من المنطقة"
        out.append(s + ".")
    # a new disturbance in the next three days, from the north-west or west
    nxt = None
    for r in fut:
        lb = _lobe(r)
        if lb and (not l1 or abs(lb["lon"] - l1["lon"]) + abs(lb["lat"] - l1["lat"]) >= 8) and lb["lon"] <= 45:
            nxt = (r, lb)
            break
    if nxt:
        out.append(f"وتقترب ذراع دوامة جديدة (مقدمة الأخدود التالي) فوق {TR.place(nxt[1]['lat'], nxt[1]['lon'])} "
                   f"{ar_date(mk_day(nxt[0]['time']))}.")
    # 2) the cold air aloft over Makkah and Taif
    t_pre = max(r["t500_makkah"] for r in past[:3])      # before the spell: the mildest of the first analyses
    t_now = cur["t500_makkah"]
    t_min = min(r["t500_makkah"] for r in past + fut)
    warm = next((r for r in fut if r["t500_makkah"] >= t_pre - 0.5), None)
    if t_now <= t_pre - 1.5 or t_min <= t_pre - 2:
        s = f"البرد العلوي فوق مكة والطائف: {n1(t_now)}° عند ٥٠٠ اليوم، وكان {n1(t_pre)}° قبل الموجة"
        cold_f = [r for r in fut if r["t500_makkah"] <= t_pre - 1.5]
        if cold_f:
            s += f"، ويبقى حول {n1(min(r['t500_makkah'] for r in cold_f))}° حتى {ar_date(mk_day(cold_f[-1]['time']))}"
        if warm:
            s += f"، ويزول {ar_date(mk_day(warm['time']))}"
        out.append(s + ".")
    # 3) the moisture, by area, now and in three days, and the plume from the east
    def pw_line(key, name):
        now_v = cur["pw"][key]
        end_v = fut[-1]["pw"][key] if fut else now_v
        trend = "ترتفع" if end_v >= now_v + 3 else "تنخفض" if end_v <= now_v - 3 else "تبقى"
        return f"{name} {n1(now_v)} ملم {trend}{' إلى ' + n1(end_v) if trend != 'تبقى' else ' قريبة منه'}"
    out.append("الماء القابل للهطول اليوم وبعد ثلاثة أيام: " + "؛ و".join(
        [pw_line("hijaz_makkah", "مكة والطائف"), pw_line("asir_jazan", "عسير وجازان"),
         pw_line("central", "الوسط")]) + ".")
    # 4) the low-level winds against the mountains
    u, v = cur["wind850_hijaz"]
    sp = math.hypot(u, v)
    if sp >= 3:
        d = from_dir(u, v)
        upslope = ("تصعد السفوح الشرقية للحجاز والسروات بالرطوبة من الداخل" if u < -1.5
                   else "تصعد السفوح الغربية من البحر الأحمر وتهامة" if u > 1.5 else "تسري على امتداد الجبال")
        out.append(f"رياح ٨٥٠ فوق الطائف {d} {n1(sp)} م/ث، {upslope}.")
    # 5) the winds by level over the Hijaz, today and in two days: a turn from the bottom up shows here
    if fut and "w700_hijaz" in cur:
        later_r = fut[min(3, len(fut) - 1)]
        def lv(r, key):
            u, v = r[key]
            sp = math.hypot(u, v)
            return "شبه ساكنة" if sp < 2.5 else f"{from_dir(u, v)} {n1(sp)} م/ث"
        lv_now = f"عند ٨٥٠ {lv(cur, 'wind850_hijaz')}، وعند ٧٠٠ {lv(cur, 'w700_hijaz')}، وعند ٥٠٠ {lv(cur, 'w500_hijaz')}"
        lv_then = f"عند ٨٥٠ {lv(later_r, 'wind850_hijaz')}، وعند ٧٠٠ {lv(later_r, 'w700_hijaz')}، وعند ٥٠٠ {lv(later_r, 'w500_hijaz')}"
        s = f"الرياح فوق الحجاز اليوم: {lv_now}؛ و{ar_date(mk_day(later_r['time']))}: {lv_then}."
        u8, _ = cur["wind850_hijaz"]
        u5 = cur["w500_hijaz"][0]
        if u8 < -1.5 and u5 > 1.5:
            s += (" فالرياح تنقلب من الأسفل: السفلى شرقية والعليا غربية تضعف مع رحيل الأخدود، فتقود الشرقية النشوء "
                  "وينشأ الخيال الجديد غرب السابق وجنوبه الغربي على السفوح.")
        if cur.get("dz500_ns") is not None and later_r.get("dz500_ns") is not None:
            a, b = cur["dz500_ns"], later_r["dz500_ns"]
            if a < 0 and b > a + 20:
                s += (f" وفرق ارتفاع ٥٠٠ بين شمال الحجاز وجنوبه {n1(a)} م اليوم، ويصير {n1(b)} م"
                      + ("، فينقلب التيار العلوي" if b > 0 else "، فيضعف التيار الغربي العلوي") + ".")
        out.append(s)
    # 6) how the storms will move
    lines = []
    for r in [cur] + fut[:5:2]:
        u, v = r["steer_hijaz"]
        lines.append((r, math.hypot(u, v), to_dir(u, v)))
    r0, s0, d0 = lines[0]
    mv = lambda sp, d: "شبه ساكنة" if sp < 2.5 else f"نحو {d} بسرعة {n1(sp)} م/ث"
    s = f"حركة الخلايا (رياح ٧٠٠ إلى ٥٠٠ فوق الحجاز): {mv(s0, d0)} اليوم"
    weak = [x for x in lines if x[1] < 5]
    later = [x for x in lines[1:] if x[2] != d0 or abs(x[1] - s0) >= 4]
    if later:
        s += "، ثم " + "، ثم ".join(f"{mv(x[1], x[2])} {ar_date(mk_day(x[0]['time']))}" for x in later[:2])
    out.append(s + ".")
    if weak:
        out.append(f"ومع ضعف رياح القيادة (دون ٥ م/ث {ar_date(mk_day(weak[0][0]['time']))}) تتولد الخلايا حيث يلتقي هواء "
                   "السحب البارد بالهواء الرطب، فتثبت فوق المواضع نفسها أو تتقدم عكس الرياح، وتنحدر ليلًا نحو تهامة والأودية؛ "
                   "فيتكرر المطر ويرتفع خطر السيول.")
    return out
