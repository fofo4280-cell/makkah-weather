"""The verification log of the nightly report (Fahad, 27 Nov 2026, the central charter part 14: «عند توافر بيانات الرصد
بعد انتهاء الحالة، قارن التوقع بالواقع ... أنشئ سجلاً تراكمياً لأداء النماذج ... لا تصدر أحكاماً إحصائية من عينات صغيرة»).

verif.json in the published data folder (climate-data) keeps
  fc[day]  = {"cycle", "regions": {region: level}}  the report's ingredients judgement for each of the 13 regions
             (a region missing = no rain read), recorded every night;
  obs[day] = {"regions": {region: wet1}}            the share of the region with 1 mm or more in the observed day
             (PERSIANN-PDIR-Now daily, UTC day, i.e. 3 AM to 3 AM Makkah; satellite infrared, it underestimates small
             mountain storms), fetched two days or more after the day.
The event: forecast «rain» = level «متوسطة» or stronger; observed «rain» = 2 % of the region or more with 1 mm. Scores
(probability of detection, false alarm ratio, critical success index) are given only from MIN_EVENTS events (forecast or
observed rain) up; below that the report says the sample is too small.

    load(out) -> log;  record(log, day, cycle, rows);  fill_obs(log, today, n=3);  save(out, log);  words(log, day0)
"""
import json
import os
from datetime import date, timedelta

YES = ("متوسطة", "مرجحة", "قوية")
WET = 0.02
MIN_EVENTS = 30
KEEP = 400


def load(out):
    try:
        return json.load(open(os.path.join(out, "verif.json")))
    except Exception:  # noqa: BLE001
        return {"v": 1, "fc": {}, "obs": {}}


def save(out, log):
    days = sorted(log["fc"])[-KEEP:]
    log["fc"] = {d: log["fc"][d] for d in days}
    log["obs"] = {d: v for d, v in log["obs"].items() if d in log["fc"]}
    json.dump(log, open(os.path.join(out, "verif.json"), "w"), ensure_ascii=False, separators=(",", ":"))


def record(log, day, cycle, rows):
    log["fc"][day.isoformat()] = {"cycle": cycle, "regions": {r["name"]: r["level"] for r in rows if not r.get("vague")}}


def fill_obs(log, today, n=3):
    import obs_rain
    import sa_geo as G
    regs = None
    got = 0
    for d in sorted(log["fc"], reverse=True):
        dd = date.fromisoformat(d)
        if d in log["obs"] or dd > today - timedelta(days=2) or dd < today - timedelta(days=30) or got >= n:
            continue
        try:
            a = obs_rain.pdir_day(dd)
        except Exception as e:  # noqa: BLE001
            print("verif: observed rain failed", d, repr(e)[:120], flush=True)
            continue
        if a is None:
            continue
        regs = regs or G.regions()
        s = obs_rain.summarise(a, regs)
        log["obs"][d] = {"regions": {k: v["wet1"] for k, v in s["regions"].items()}, "ksa1": s["ksa1"]}
        got += 1


def table(log):
    """(hits, false alarms, misses, correct negatives, days) over the days with both a forecast and an observation"""
    a = b = c = d_ = 0
    days = 0
    for d, o in log.get("obs", {}).items():
        f = log["fc"].get(d)
        if not f:
            continue
        days += 1
        for reg, wet in o["regions"].items():
            fy = f["regions"].get(reg) in YES
            oy = wet >= WET
            a += fy and oy
            b += fy and not oy
            c += oy and not fy
            d_ += not fy and not oy
    return a, b, c, d_, days


def words(log, day0):
    from report2 import ar, jl, ar_date
    if not log or not log.get("fc"):
        return None
    first = date.fromisoformat(min(log["fc"]))
    a, b, c, d_, days = table(log)
    t = (f"سجل التحقق بعد الحالة: يُحفظ حكم كل ليلة على المناطق الثلاث عشرة منذ {ar_date(first, weekday=False)}، ويُقارن بأمطار "
         "الأقمار الصناعية (بيرسيان الآني، بالأشعة تحت الحمراء، وهي تقلل من عواصف الجبال الصغيرة) بعد يومين من كل يوم. "
         "والحدث: حكم «متوسطة» فأكثر، ورصد ملم فأكثر على ٢٪ من مساحة المنطقة فأكثر. ")
    n = a + b + c
    if days == 0:
        t += "ولم يكتمل رصد أي يوم بعد."
    elif n < MIN_EVENTS:
        t += (f"واكتمل رصد {ar(days)} {'يوم' if days == 1 or days > 10 else 'أيام'} فيها {ar(n)} حالة مطر توقعًا أو رصدًا، "
              f"وهي عينة صغيرة دون {ar(MIN_EVENTS)} حالة، فلا تُحسب منها مؤشرات الأداء بعد.")
    else:
        pod, far, csi = a / max(a + c, 1), b / max(a + b, 1), a / max(n, 1)
        t += (f"وفي {ar(days)} يومًا ({ar(n)} حالة): نسبة الاكتشاف {ar(int(round(100 * pod)))}٪، ونسبة الإنذار الكاذب "
              f"{ar(int(round(100 * far)))}٪، ومؤشر النجاح الحرج {ar(int(round(100 * csi)))}٪.")
    return t
