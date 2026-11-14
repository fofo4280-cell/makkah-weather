"""The kind of today's storms over each part of the Kingdom: driven by the heat of the day (thermal convection),
or by cold air aloft (upper cooling), from the 500 hPa temperature in the afternoon against its normal.

The normal: GFS 12 UTC analyses every second day, 23 Mar 2021 to 27 Feb 2026 (902 days), mean plus three annual
harmonics at each 1-degree point (t500_clim.npz, built once); the day-to-day spread around it is about 2 degrees.
Over Makkah and Taif the normal is about -6.5 C in mid-November and -8.8 C in mid-January.
  upper   : 2 degrees or more colder than normal (about one spread): the cold aloft makes the air unstable on its
            own, so storms start with little heating and can go on after sunset and reach the plains;
  mixed   : 1 to 2 degrees colder: the heat of the day leads, the cold aloft makes the storms stronger and wider;
  thermal : within a degree of normal or warmer: the heat of the day, the high ground and the moisture alone,
            storms in the afternoon over the mountains that fade after sunset.
On the 24 days of wide rain of the past year all three kinds occur over the Hijaz box (9 upper, 8 mixed,
7 thermal), so the kind tells how the storms behave, not whether it rains.
"""
import os
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BOXES = {   # as the moisture boxes of daily.py
    "west": ("الحجاز وغرب المملكة", 19, 26, 38, 43),
    "southwest": ("جنوب غرب المملكة", 16, 20, 41, 45),
    "central": ("وسط المملكة", 22, 27, 43, 48),
    "east": ("شرق المملكة", 23, 28, 48, 51),
    "north": ("شمال المملكة", 27, 32, 37, 44),
}
_C = None


def _clim():
    global _C
    if _C is None:
        _C = dict(np.load(os.path.join(HERE, "t500_clim.npz")))
    return _C


def normal(d):
    """(normal C, spread C) on the climatology grid for date d"""
    c = _clim()
    w = 2 * np.pi * d.timetuple().tm_yday / 365.25
    b = np.array([1] + [g(k * w) for k in (1, 2, 3) for g in (np.cos, np.sin)])
    return np.tensordot(b, c["coef"], 1), np.sqrt(np.tensordot(b[:3], c["sdcoef"], 1))


def kind(anom):
    return "upper" if anom <= -2.0 else "mixed" if anom <= -1.0 else "thermal"


def boxes(t500, lat, lon, d):
    """t500: 500 hPa temperature (K or C) on lat x lon (1 degree, any order) at 12 UTC of day d.
    {key: {"name", "t", "normal", "anom", "kind"}}"""
    c = _clim()
    nm, _ = normal(d)
    t = np.asarray(t500, float)
    if np.nanmean(t) > 150:
        t = t - 273.15
    out = {}
    for k, (name, s, n, w, e) in BOXES.items():
        j = (lat >= s) & (lat <= n)
        i = (lon >= w) & (lon <= e)
        cj = (c["lat"] >= s) & (c["lat"] <= n)
        ci = (c["lon"] >= w) & (c["lon"] <= e)
        tv = float(np.nanmean(t[np.ix_(j, i)]))
        nv = float(nm[np.ix_(cj, ci)].mean())
        out[k] = {"name": name, "t": round(tv, 1), "normal": round(nv, 1), "anom": round(tv - nv, 1),
                  "kind": kind(tv - nv)}
    return out


WORDS = {
    "upper": ("معتمد على تبريد علوي",
              "البرد في الأعلى يكفي وحده لزعزعة الجو، فتنشأ السحب بأقل تسخين، وقد تستمر بعد الغروب وتمتد إلى السهول، "
              "وتزيد فرص البرَد"),
    "mixed": ("حمل حراري يعززه تبريد علوي",
              "يقوده تسخين النهار، ويزيده البرد العلوي قوةً واتساعًا"),
    "thermal": ("حمل حراري",
                "يعتمد على تسخين النهار والتضاريس والرطوبة، فتنشأ السحب بعد الظهر على المرتفعات وتضعف بعد الغروب"),
}
