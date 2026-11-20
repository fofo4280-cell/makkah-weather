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


def text(rows, now, day0=None):
    """the diagnosis lines (Arabic). now: the newest analysis time; day0: the Makkah day of the report.
    Every time is named by its own day and part of the day: the newest analysis (12 UTC, the evening before the
    report) is not called 'today' any more, and the report day is read at its own afternoon (12 UTC) from the
    forecast (Fahad, 16 Nov 2026: the diagnosis called yesterday's analysis 'today')."""
    if len(rows) < 3:
        return []
    past = [r for r in rows if r["kind"] == "a"]
    fut = [r for r in rows if r["kind"] == "f"]
    cur = past[-1]
    day0 = day0 or mk_day(cur["time"])
    def when(t):
        loc = t + timedelta(hours=3)
        part = "فجر" if loc.hour < 6 else "صباح" if loc.hour < 12 else "عصر" if loc.hour < 18 else "مساء"
        return f"{part} اليوم" if loc.date() == day0 else f"{part} {ar_date(loc.date())}"
    def noon(d):
        """the row at 12 UTC (15:00 Makkah) of day d, or None"""
        return next((r for r in rows if r["time"].hour == 12 and mk_day(r["time"]) == d), None)
    today = noon(day0) or cur
    out = []
    # 1) the upper disturbance: where it was, where it is, where it goes
    with_lobe = [r for r in past if _lobe(r)]
    first = min(with_lobe, key=lambda r: (lambda x: abs(x["lat"] - 24) + abs(x["lon"] - 42))(_lobe(r))) if with_lobe else None
    l0, l1 = (_lobe(first) if first else None), _lobe(cur)
    if l0:
        what = "منخفض مقطوع مغلق" if l0["closed"] else "قاع الأخدود وذراع دوامته"
        s = f"الاضطراب العلوي (٥٠٠ هكتوباسكال): كان {what} فوق {TR.place(l0['lat'], l0['lon'])} {when(first['time'])}"
        if first is cur:
            s = f"الاضطراب العلوي (٥٠٠ هكتوباسكال): {what} فوق {TR.place(l0['lat'], l0['lon'])} في آخر تحليل ({when(cur['time'])})"
        elif l1 and l1["lat"] - l0["lat"] >= 8 and not (20 <= bearing(l0["lat"], l0["lon"], l1["lat"], l1["lon"]) < 300):
            # a jump of 8 degrees or more to the north or north-west is another disturbance, not this one moving
            # (17 Nov 2026: the trough over central Arabia on the 15th was said to have "moved north" to Turkey)
            s += (f"، ثم ضعف وخرج من المنطقة؛ وأقرب اضطراب في آخر تحليل ({when(cur['time'])}) "
                  f"فوق {TR.place(l1['lat'], l1['lon'])}")
        elif l1 and (abs(l1["lat"] - l0["lat"]) + abs(l1["lon"] - l0["lon"])) >= 3:
            b = bearing(l0["lat"], l0["lon"], l1["lat"], l1["lon"])
            moved = DIRS_TO[int((b + 22.5) // 45) % 8]
            kind = ("فهو يرحل" if 0 <= b < 135 else "فهو يرتد غربًا" if 180 <= b < 315 else "")
            s += (f"، وصار في آخر تحليل ({when(cur['time'])}) فوق {TR.place(l1['lat'], l1['lon'])} متجهًا نحو {moved}"
                  + (f"، {kind}" if kind else ""))
        elif l1:
            s += f"، وما زال شبه ثابت في آخر تحليل ({when(cur['time'])})"
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
        out.append(f"وتقترب ذراع دوامة جديدة (مقدمة الأخدود التالي)، فتكون فوق {TR.place(nxt[1]['lat'], nxt[1]['lon'])} "
                   f"{when(nxt[0]['time'])}.")
    # 2) the cold air aloft over Makkah and Taif
    t_pre = max(r["t500_makkah"] for r in past[:3])      # before the spell: the mildest of the first analyses
    t_now = cur["t500_makkah"]
    coldest = min(past, key=lambda r: r["t500_makkah"])
    t_min = min(r["t500_makkah"] for r in past + fut)
    if t_now <= t_pre - 1.5:
        s = (f"البرد العلوي فوق مكة والطائف: حرارة ٥٠٠ هكتوباسكال {n1(t_now)}° في آخر تحليل، "
             f"وكانت {n1(t_pre)}° قبل الموجة")
        cold_f = [r for r in fut if r["t500_makkah"] <= t_pre - 1.5]
        warm = next((r for r in fut if r["t500_makkah"] >= t_pre - 0.5), None)
        if cold_f:
            s += f"، وتبقى حول {n1(min(r['t500_makkah'] for r in cold_f))}° حتى {when(cold_f[-1]['time'])}"
        if warm:
            s += f"، ثم يزول البرد {when(warm['time'])}"
        out.append(s + ".")
    elif coldest["t500_makkah"] <= t_pre - 2:
        s = (f"زال البرد العلوي فوق مكة والطائف: حرارة ٥٠٠ هكتوباسكال {n1(t_now)}° في آخر تحليل، بعد أن بلغت "
             f"{n1(coldest['t500_makkah'])}° {when(coldest['time'])}، وكانت {n1(t_pre)}° قبل الموجة")
        back = next((r for r in fut if r["t500_makkah"] <= t_now - 1.5), None)
        if back:
            s += f"؛ ويعود البرد إلى {n1(back['t500_makkah'])}° {when(back['time'])}"
        out.append(s + ".")
    elif t_min <= t_pre - 2:
        r = min(fut, key=lambda r: r["t500_makkah"])
        out.append(f"برد علوي قادم فوق مكة والطائف: تنخفض حرارة ٥٠٠ هكتوباسكال من {n1(t_now)}° إلى "
                   f"{n1(r['t500_makkah'])}° {when(r['time'])}.")
    # 3) the moisture, by area, this afternoon and at the end of the forecast
    end_r = fut[-1] if fut else today
    def pw_line(key, name):
        now_v = today["pw"][key]
        end_v = end_r["pw"][key]
        trend = (f"ويرتفع إلى {n1(end_v)}" if end_v >= now_v + 3 else f"وينخفض إلى {n1(end_v)}" if end_v <= now_v - 3
                 else "ويبقى قريبًا من ذلك")
        return f"في {name} {n1(now_v)} ملم {trend}"
    out.append(f"الماء القابل للهطول {when(today['time'])}، ثم {when(end_r['time'])}: " + "؛ و".join(
        [pw_line("hijaz_makkah", "مكة والطائف"), pw_line("asir_jazan", "عسير وجازان"),
         pw_line("central", "الوسط")]) + ".")
    # 4) the low-level winds against the mountains
    u, v = today["wind850_hijaz"]
    sp = math.hypot(u, v)
    if sp >= 3:
        d = from_dir(u, v)
        upslope = ("فتصعد السفوح الشرقية للحجاز والسروات بالرطوبة من الداخل" if u < -1.5
                   else "فتصعد السفوح الغربية من البحر الأحمر وتهامة" if u > 1.5 else "وتسري على امتداد الجبال")
        out.append(f"رياح ٨٥٠ هكتوباسكال فوق الطائف {when(today['time'])} {d} بسرعة {n1(sp)} م/ث، {upslope}.")
    # 5) the winds by level over the Hijaz, this afternoon and two days later: a turn from the bottom up shows here
    later_r = noon(day0 + timedelta(days=2)) or (fut[-1] if fut else None)
    if later_r is not None and later_r is not today and "w700_hijaz" in today:
        def lv(r, key):
            u, v = r[key]
            sp = math.hypot(u, v)
            return "شبه ساكنة" if sp < 2.5 else f"{from_dir(u, v)} {n1(sp)} م/ث"
        levels = lambda r: (f"عند ٨٥٠ {lv(r, 'wind850_hijaz')}، وعند ٧٠٠ {lv(r, 'w700_hijaz')}، "
                            f"وعند ٥٠٠ {lv(r, 'w500_hijaz')}")
        s = f"الرياح فوق الحجاز {when(today['time'])}: {levels(today)}؛ و{when(later_r['time'])}: {levels(later_r)}."
        u8, v8 = today["wind850_hijaz"]
        u5, v5 = today["w500_hijaz"]
        # only when both winds are real (not the calm the line above reports)
        if u8 < -1.5 and math.hypot(u8, v8) >= 2.5 and u5 > 1.5 and math.hypot(u5, v5) >= 2.5:
            s += (" فالرياح السفلى شرقية والعليا غربية تضعف مع رحيل الأخدود، فتقود الشرقية نشوء السحب، وتنشأ الخلايا "
                  "الجديدة غرب السابقة وجنوبها الغربي على السفوح.")
        if today.get("dz500_ns") is not None and later_r.get("dz500_ns") is not None:
            a, b = today["dz500_ns"], later_r["dz500_ns"]
            if a < 0 and b > a + 20:
                s += (f" وفرق ارتفاع ٥٠٠ بين شمال الحجاز وجنوبه {n1(a)} م {when(today['time'])}، ويصير {n1(b)} م"
                      + ("، فينقلب التيار العلوي" if b > 0 else "، فيضعف التيار الغربي العلوي") + ".")
        out.append(s)
    # 6) how the storms will move: the steering at the afternoon of the report day and the next two days
    steer = []
    for k in range(3):
        r = noon(day0 + timedelta(days=k)) if day0 else None
        if r is None and k == 0:
            r = today
        if r is not None:
            u, v = r["steer_hijaz"]
            steer.append((r, math.hypot(u, v), to_dir(u, v)))
    if steer:
        r0, s0, d0 = steer[0]
        mv = lambda sp, d: "شبه ساكنة" if sp < 2.5 else f"نحو {d} بسرعة {n1(sp)} م/ث"
        s = f"حركة الخلايا (رياح ٧٠٠ إلى ٥٠٠ فوق الحجاز) {when(r0['time'])}: {mv(s0, d0)}"
        later = [x for x in steer[1:] if x[2] != d0 or abs(x[1] - s0) >= 2]
        if later:
            s += "، ثم " + "، ثم ".join(f"{mv(x[1], x[2])} {when(x[0]['time'])}" for x in later[:2])
        out.append(s + ".")
        weak = [x for x in steer if x[1] < 5]
        if weak:
            w0 = weak[0]
            out.append(f"ومع ضعف رياح القيادة {when(w0[0]['time'])} ({n1(w0[1])} م/ث) تتولد الخلايا حيث يلتقي هواء السحب "
                       "البارد بالهواء الرطب، فتثبت فوق المواضع نفسها أو تتقدم عكس الرياح، وتنحدر ليلًا نحو تهامة والأودية؛ "
                       "فيتكرر المطر ويرتفع خطر السيول.")
    return out
