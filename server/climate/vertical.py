"""The vertical reading of the column, zone by zone over the whole Kingdom (Fahad, 27 Nov 2026, the central charter
«التعليمات المركزية لكبير المحللين الجويين», part 6: «أنشئ تصوراً رأسياً للغلاف الجوي ... CAPE بأنواعه المتاحة، CIN،
LCL وLFC، القص الرأسي، درجة التجمد، الحركة الرأسية»).

GFS 0.25 of the evening (12 UTC) run, 12 UTC of each day (3 PM Makkah, the peak of the afternoon convection), the
zones of troughreach.py (sea, coasts, plains, desert, every region). Per zone:
  rh925, rh850, rh700, rh500   mean relative humidity (%) on each level: the depth of the moist layer; 925 and 850
                               only over the ground below them (None over the high ground)
  hs                           the mean ground height (m)
  w700, w500                   the strongest ascent (Pa/s, negative = rising), 3x3 smoothed
  div200                       the strongest upper divergence (1e-5 /s), smoothed
  conv10                       the strongest surface (10 m) convergence (1e-5 /s, positive = converging), smoothed
  sbcape, mucape               90th percentile of surface-based and most-unstable CAPE (J/kg)
  cin                          the median surface-based CIN (J/kg, negative) over the points of the top CAPE quarter
  lcl                          the median cloud base estimate 125 x (T2m - Td2m) m above the ground (Espy), same points
  frz                          the mean height of the 0 C level (m above sea level)
  shear                        the mean bulk wind difference 10 m -> 500 hPa (m/s)
The level of free convection (LFC) is not in the GFS files we read and is not computed: the report says so.

Thresholds used in the report's words are common operational rules of thumb, stated as such, not physical limits.

    fetch(cycle, days, get_fields) -> [{d, z: {zone: {...}}}]
"""
import numpy as np

import troughreach as TR

FIELDS = [("rh925", r":RH:925 mb:"), ("rh850", r":RH:850 mb:"), ("rh700", r":RH:700 mb:"), ("rh500", r":RH:500 mb:"),
          ("w700", r":VVEL:700 mb:"), ("w500", r":VVEL:500 mb:"),
          ("u200", r":UGRD:200 mb:"), ("v200", r":VGRD:200 mb:"), ("u500", r":UGRD:500 mb:"), ("v500", r":VGRD:500 mb:"),
          ("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
          ("t2", r":TMP:2 m above ground:"), ("td2", r":DPT:2 m above ground:"),
          ("sbcape", r":CAPE:surface:"), ("cin", r":CIN:surface:"), ("mucape", r":CAPE:180-0 mb above ground:"),
          ("frz", r":HGT:0C isotherm:"), ("hs", r":HGT:surface:")]
LEVEL_Z = {"rh925": 750.0, "rh850": 1450.0}   # a level is read only over the ground below it (standard heights, m)


def _div(u, v, la):
    from scipy.ndimage import uniform_filter
    R, d = 6.371e6, np.deg2rad(TR.RES)
    c = np.cos(np.deg2rad(la))[:, None]
    du = np.gradient(u, axis=1) / (R * c * d)
    dv = -np.gradient(v * c, axis=0) / (R * c * d)    # rows run north to south
    return uniform_filter(1e5 * (du + dv), 3, mode="nearest")


def zone_vals(g):
    from scipy.ndimage import uniform_filter
    la, lo = TR._grid()
    w7, w5 = (uniform_filter(g[k], 3, mode="nearest") for k in ("w700", "w500"))
    d2 = _div(g["u200"], g["v200"], la)
    d9 = _div(g["u10"], g["v10"], la)
    sh = np.hypot(g["u500"] - g["u10"], g["v500"] - g["v10"])
    lcl = 125.0 * np.maximum(g["t2"] - g["td2"], 0)
    out = {}
    for key, _n, a, b, c, d in TR.ZONES:
        ix = np.ix_((la >= a) & (la <= b), (lo >= c) & (lo <= d))
        cape = g["sbcape"][ix]
        top = cape >= np.quantile(cape, 0.75)
        hs = g["hs"][ix]
        lv = {}
        for k_, zl in LEVEL_Z.items():
            m_ = hs < zl - 100
            lv[k_] = round(float(g[k_][ix][m_].mean())) if m_.mean() >= 0.25 else None
        out[key] = {"rh925": lv["rh925"], "rh850": lv["rh850"], "hs": int(round(float(hs.mean()), -1)),
                    "rh700": round(float(g["rh700"][ix].mean())), "rh500": round(float(g["rh500"][ix].mean())),
                    "w700": round(float(w7[ix].min()), 2), "w500": round(float(w5[ix].min()), 2),
                    "div200": round(float(d2[ix].max()), 1), "conv10": round(float(-d9[ix].min()), 1),
                    "sbcape": round(float(np.quantile(cape, 0.9))),
                    "mucape": round(float(np.quantile(g["mucape"][ix], 0.9))),
                    "cin": round(float(np.median(g["cin"][ix][top]))),
                    "lcl": int(round(float(np.median(lcl[ix][top])), -1)),
                    "frz": int(round(float(g["frz"][ix].mean()), -1)),
                    "shear": round(float(sh[ix].mean()), 1)}
    return out


def fetch(cycle, days, get_fields):
    """day k (k = 1 .. days) = the cycle date + k at 12 UTC (lead 24k of a 12 UTC cycle)"""
    from datetime import datetime, timedelta
    t0 = datetime.strptime(cycle[:8], "%Y%m%d").date()
    base = 0 if cycle[8:10] == "12" else 12
    rows = []
    for k in range(1, days + 1):
        fh = 24 * k + base
        try:
            g = {n: TR.cut(a) for n, a in get_fields(cycle, fh, res="0p25", fields=FIELDS).items()}
            rows.append({"d": (t0 + timedelta(days=k)).isoformat(), "h": 12, "z": zone_vals(g)})
        except Exception as e:  # noqa: BLE001
            print("vertical download failed", fh, repr(e)[:120], flush=True)
    return rows


# ------------------------------------------------------------------ the words (report4, section 4)
DEPTH_W = {"عميقة": "رطوبة عميقة", "حتى ٧٠٠ وجفاف فوقها": "رطوبة حتى ٧٠٠ وجفاف فوقها",
           "سطحية تحت ٧٠٠": "رطوبة سطحية تحت ٧٠٠", "وسطى فوق طبقة سفلى جافة": "رطوبة وسطى فوق طبقة سفلى جافة",
           "جافة": "عمود جاف"}


def _low(v):
    """the moisture of the lowest level above the ground (925, else 850, else 700 over the high ground)"""
    return next((v[k] for k in ("rh925", "rh850") if v.get(k) is not None), v["rh700"])


def depth(v):
    """the depth of the moist layer from the four levels"""
    lo_ = _low(v)
    if lo_ >= 60 and v["rh700"] >= 60 and v["rh500"] >= 50:
        return "عميقة"
    if lo_ >= 60 and v["rh700"] >= 50:
        return "حتى ٧٠٠ وجفاف فوقها"
    if lo_ >= 60:
        return "سطحية تحت ٧٠٠"
    if v["rh700"] >= 50:
        return "وسطى فوق طبقة سفلى جافة"
    return "جافة"


def dry_layer(v):
    if _low(v) >= 50 and v["rh500"] < 30:
        return "جفاف عند ٥٠٠"
    if _low(v) >= 50 and v["rh700"] < 40:
        return "جفاف عند ٧٠٠"
    return None


def lift(v):
    up7, up5, dv = v["w700"] <= -0.15, v["w500"] <= -0.15, v["div200"] >= 2
    if up7 and up5 and dv:
        return "عبر العمود"
    if up7 or up5:
        return "في الطبقة الوسطى فقط"
    return "غائب"


def cap(v):
    c = v["cin"]
    return "كابح قوي" if c <= -100 else "كابح متوسط" if c <= -50 else "كابح ضعيف" if c <= -15 else "لا كابح يُذكر"
