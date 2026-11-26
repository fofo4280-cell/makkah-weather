"""The historical analogs of the wave of 29 Nov-2 Dec 2026, followed night by night until it starts (Fahad, 26 Nov 2026:
«ابحث تاريخيا في نوفمبر وديسمبر حالات مشابهة للوضعية الحالية للموجه» … «تابع التحديثات اليومين القادمة واذكرها في
التقرير كل يوم حتى بداية الحالة»).

The study (thread of 26 Nov 2026; code and maps in the project files, analogs-nov-dec/): ERA5 Nov-Dec 1959-2025, the
20 closest 3-day patterns of 500 hPa height anomaly and PW % to the ECMWF forecast for 29 Nov-1 Dec, rain from
PERSIANN-CDR (from 1983). Within the analogs the pattern score said nothing about the rain; the PW of the west
(19-24 N 38-41 E) said the most about the Jeddah-Makkah rain (rank corr 0.72): >= 135 % of normal -> >= 20 mm near
Jeddah/Makkah in 5 of 7 cases, on the day matching 1 Dec; < 135 % -> 0 of 13. Every heavy case had 700 hPa RH >= 45 %
over the west; the ECMWF of 25 Nov 12 UTC had 35-39 %.

Each night this reads the same two ingredients from the ECMWF cycle for the evening of 30 Nov to midday 1 Dec and turns
them into the chance of heavy rain (>= 20 mm), the same rule as the study's answer of 26 Nov. Only for this case: it
says nothing after 30 Nov 2026.
"""
from datetime import datetime, timedelta, date

LAST_DAY = date(2026, 11, 30)          # the report of this day is the last one before the case reaches the Hijaz
TIMES = ["2026-11-30T12", "2026-11-30T18", "2026-12-01T00", "2026-12-01T06", "2026-12-01T12"]
# ERA5 1991-2020 normal PW (mm) of the west box, by date (the study's climatology)
CLIM = {"2026-11-30": 24.11, "2026-12-01": 23.95}
PW_BOX = (18.5, 24.5, 37.5, 41.5)
RH_BOX = (19.5, 23.5, 37.5, 41.5)
SEED = {"cycle": "2026112512", "pw": 139, "rh": 39}     # this reading of the 25 Nov 12 UTC cycle
AD = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def _box(a, b):
    la0, la1, lo0, lo1 = b
    i0, i1 = int(round((90 - la1) * 4)), int(round((90 - la0) * 4)) + 1
    k0, k1 = int(round(lo0 * 4)), int(round(lo1 * 4)) + 1
    return float(a[i0:i1, k0:k1].mean())


def fetch(cycle, prev=None):
    """{cycle, pw, rh, times, prev} from the ECMWF cycle 'YYYYMMDDHH' (00/12 UTC); None when out of reach"""
    import ecmwf
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    pws, rhs = [], []
    for t in TIMES:
        fh = int((datetime.strptime(t, "%Y-%m-%dT%H") - t0).total_seconds() // 3600)
        if fh < 0:
            continue
        pw = _box(ecmwf._at(cycle, fh, "tcwv", ""), PW_BOX)
        rh = _box(ecmwf._at(cycle, fh, "r", "700"), RH_BOX)
        pws.append(round(100 * pw / CLIM[t[:10]]))
        rhs.append(round(rh))
    if not pws:
        return None
    p = prev if prev and prev.get("cycle") != cycle else None
    if p and p.get("prev"):
        p = {k: p[k] for k in ("cycle", "pw", "rh")}
    return {"cycle": cycle, "pw": max(pws), "rh": max(rhs), "pws": pws, "rhs": rhs,
            "prev": {k: p[k] for k in ("cycle", "pw", "rh")} if p else SEED}


def chances(pw, rh):
    """(triangle heavy, Jeddah, Al-Jumum, Makkah, any rain) in %: the analogs' rate for the west PW, cut by the mid-level
    dryness (every heavy analog had RH700 >= 45 %), then shared out as the study's answer of 26 Nov (35 -> 25/20/15)"""
    base = 70 if pw >= 135 else 35 if pw >= 125 else 15 if pw >= 115 else 5
    f = 1.0 if rh >= 45 else 0.75 if rh >= 40 else 0.5 if rh >= 35 else 0.35
    tri = base * f
    r5 = lambda x: int(5 * round(x / 5))
    return r5(tri), r5(tri * 0.7), r5(tri * 0.57), r5(tri * 0.43), min(90, r5(tri + 15))


def text(a, day0):
    if not a or day0 > LAST_DAY:
        return None
    tri, jd, jm, mk, anyr = chances(a["pw"], a["rh"])
    n = lambda x: str(x).translate(AD)
    t = ("الحالات المشابهة تاريخيًا (دراسة ٢٦ نوفمبر في ٦٧ موسمًا، أقربها ديسمبر ٢٠٢٥ ونوفمبر ٢٠١٧ و٢٠١٨): حين تجاوز "
         "الماء الهطول غرب المملكة ١٣٥٪ من معتاده سقط ٢٠ ملم فأكثر قرب جدة ومكة في ٥ من ٧ حالات، ولم يسقط في أي من "
         "١٣ حالة دونه، وكانت الرطوبة عند ٧٠٠ هكتوباسكال ٤٥٪ فأكثر في كل حالة غزيرة. "
         f"وفي توقع الليلة للأوروبي من مساء ٣٠ نوفمبر إلى ظهر ١ ديسمبر: الماء الهطول غربًا {n(a['pw'])}٪ والرطوبة "
         f"الوسطى {n(a['rh'])}٪")
    p = a.get("prev")
    if p:
        dp, dr = a["pw"] - p["pw"], a["rh"] - p["rh"]
        if abs(dp) < 3 and abs(dr) < 3:
            t += " بلا تغير يذكر عن أمس"
        else:
            t += f" (أمس {n(p['pw'])}٪ و{n(p['rh'])}٪)"
        if p.get("pw") is not None:
            pt = chances(p["pw"], p["rh"])[0]
            if tri > pt:
                t += "، فارتفعت الفرصة"
            elif tri < pt:
                t += "، فتراجعت الفرصة"
    t += (f". فتقدير فرصة المطر الغزير (٢٠ ملم فأكثر): جدة {n(jd)}٪، الجموم {n(jm)}٪، مكة {n(mk)}٪، وفي موضع ما "
          f"بينها {n(tri)}٪، وأي مطر فيها {n(anyr)}٪.")
    if a["rh"] < 45:
        t += " والكابح الرطوبة الوسطى: لو تجاوزت ٤٥٪ لبلغت فرصة جدة قرابة النصف."
    return t
