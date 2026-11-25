"""Precipitable water against the climatology for each of the Kingdom's regions, for the table of the «الرطوبة» tab
(Fahad, 25 Nov 2026: «قسمها الى مناطق افضل»).

The five moisture boxes of daily.BOXES stay as they are: the report, the surge check and the pattern study read them.
This table is the page's finer split: the thirteen administrative regions (sa_regions.json), with the Makkah and
Madinah regions cut into their coast and their inland part (the same coastal strip as hijaz.py: region land with the
Red Sea within 0.5 degree to the west), so Jeddah's coast and the Makkah-Taif inland are read apart.

Each value is the mean PW over the region's 0.25 degree land cells divided by that region's normal for the day, in %.
The normal (pwreg_clim.npz, built once): GFS 12 UTC analyses of PW at 0.25 degree every second day, 23 Mar 2021 -
23 Nov 2026, the region mean, fitted with the mean plus three annual harmonics. The NCEP 2.5 degree climatology of the
boxes is too coarse here: it does not see the mountains (Asir, Taif and Al-Madinah read 45-55 % on an ordinary day) nor
the coastal plains (Jazan read 160 %). ECMWF analyses are 3-6 % moister than GFS over the regions, so for ECMWF the
normal is multiplied by ec_ratio (the ECMWF/GFS ratio of the region means on 498 paired 12 UTC analyses, every second
day 2 Mar 2024 - 22 Nov 2026, mean plus one annual harmonic). A field on the 1 degree grid (the GFS fallback) is
interpolated to the cells.
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

RES = 0.25
LAT0, LAT1, LON0, LON1 = 16.0, 32.5, 34.5, 56.0
# key, page name, region, part (None = whole region); the page draws them in this order, a line above each group
# (Makkah, Madinah, the south, the centre and east, the north: GROUPS)
ROWS = [
    ("mk_coast", "سواحل منطقة مكة", "مكة المكرمة", "coast"),
    ("mk_in", "داخل منطقة مكة", "مكة المكرمة", "inland"),
    ("md_coast", "سواحل منطقة المدينة", "المدينة المنورة", "coast"),
    ("md_in", "داخل منطقة المدينة", "المدينة المنورة", "inland"),
    ("baha", "الباحة", "الباحة", None),
    ("asir", "عسير", "عسير", None),
    ("jazan", "جازان", "جازان", None),
    ("najran", "نجران", "نجران", None),
    ("riyadh", "الرياض", "الرياض", None),
    ("qassim", "القصيم", "القصيم", None),
    ("east", "الشرقية", "الشرقية", None),
    ("hail", "حائل", "حائل", None),
    ("tabuk", "تبوك", "تبوك", None),
    ("jouf", "الجوف", "الجوف", None),
    ("nb", "الحدود الشمالية", "الحدود الشمالية", None),
]
GROUPS = ("mk_coast", "md_coast", "baha", "riyadh", "hail")
_MASKS = None


def grid():
    la = np.arange(LAT1, LAT0 - 1e-6, -RES)
    lo = np.arange(LON0, LON1 + 1e-6, RES)
    return la, lo


def masks():
    """{row key: boolean mask on the grid}"""
    global _MASKS
    if _MASKS is not None:
        return _MASKS
    import sa_geo
    regs = sa_geo.regions()
    la, lo = grid()
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    m = sa_geo.region_of_points(regs, LA.ravel(), LO.ravel()).reshape(LA.shape)
    idx = {r["name"]: k for k, r in enumerate(regs)}
    land = m >= 0
    sea_w = np.zeros_like(land)          # the Red Sea within 0.5 degree to the west (as hijaz.zones)
    for s in (1, 2):
        sh = np.ones_like(land)
        sh[:, s:] = ~land[:, :-s]
        sh[:, :s] = False
        sea_w |= sh
    coast = land & sea_w
    out = {}
    for key, _n, reg, part in ROWS:
        r = m == idx[reg]
        out[key] = r & coast if part == "coast" else r & ~coast if part == "inland" else r
    _MASKS = out
    return out


def _on_grid(field, lat, lon):
    """a field on a regular lat/lon grid (lat either way, lon 0..360 or -180..180) sampled at the cells"""
    from scipy.ndimage import map_coordinates
    la, lo = grid()
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    J = (LA - lat[0]) / (lat[1] - lat[0])
    I = (LO % 360 - lon[0] % 360) / (lon[1] - lon[0])
    return map_coordinates(np.asarray(field, float), [J, I], order=1, mode="nearest")


_CLIM = None


def normal(doy, model="gfs"):
    """{key: normal region-mean PW (mm)} for day of year 0..364, as GFS or ECMWF would analyse it"""
    global _CLIM
    if _CLIM is None:
        d = np.load(os.path.join(HERE, "pwreg_clim.npz"))
        _CLIM = (d["coef"], [str(k) for k in d["keys"]], d["ec_ratio"])
    coef, keys, ratio = _CLIM
    w = 2 * np.pi * doy / 365.0
    x = np.array([1.0] + [f(n * w) for n in (1, 2, 3) for f in (np.cos, np.sin)])
    v = x @ coef
    if model == "ecmwf":
        v = v * (x[:3] @ ratio)
    return dict(zip(keys, v.tolist()))


def row(field, lat, lon, doy, model="gfs"):
    """{key: {pw, clim, pct}} for one day (doy 0..364 as daily.doy) of a GFS or ECMWF field"""
    g = _on_grid(field, lat, lon)
    c = normal(doy, model)
    out = {}
    for key, z in masks().items():
        if not z.any() or key not in c:
            continue
        a, b = float(g[z].mean()), float(c[key])
        out[key] = {"pw": round(a, 1), "clim": round(b, 1), "pct": int(round(100 * a / max(b, 1)))}
    return out


def names():
    """[[key, page name, 1 when a group starts here]]"""
    return [[k, n, int(k in GROUPS)] for k, n, *_ in ROWS]
