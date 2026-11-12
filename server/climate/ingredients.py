"""The rain-spread potential over Saudi Arabia from the large-scale ingredients of the GFS (more reliable days
ahead than its own rain): moisture, lift (troughs aloft, converging winds near the ground, spreading winds high
up), instability and the high ground. Each point of the Kingdom gets a chance of 5 mm or more in the day from a
model fitted on the past year (ingr_fit.py, coefficients in ingr_coef.json); the expected share of the Kingdom
that gets it is the day's potential spread, also for each part of the Kingdom.
"""
import json, os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BOX = (14, 34, 33, 58)                      # south, north, west, east (degrees)
LAT = np.arange(BOX[1], BOX[0] - 0.5, -1.0)  # GFS order: north to south
LON = np.arange(BOX[2], BOX[3] + 0.5, 1.0)
PW = ("pw", r":PWAT:entire atmosphere \(considered as a single layer\):")
APCP = ("apcp", r":APCP:surface:0-")
FIELDS = [PW, ("z500", r":HGT:500 mb:"), ("t500", r":TMP:500 mb:"), ("u500", r":UGRD:500 mb:"), ("v500", r":VGRD:500 mb:"),
          ("t925", r":TMP:925 mb:"), ("u925", r":UGRD:925 mb:"), ("v925", r":VGRD:925 mb:"), ("rh700", r":RH:700 mb:"),
          ("u200", r":UGRD:200 mb:"), ("v200", r":VGRD:200 mb:"), ("cape", r":CAPE:surface:"), ("psfc", r":PRES:surface:")]


def cut(a):
    """the BOX of a 1 degree global GFS field (lat 90..-90, lon 0..359)"""
    j0, j1 = 90 - BOX[1], 90 - BOX[0]
    return a[j0:j1 + 1, BOX[2]:BOX[3] + 1]


def _div(u, v, lat):
    """horizontal divergence (1e-5 /s) on the 1 degree grid, smoothed"""
    from scipy.ndimage import gaussian_filter
    a = 6.371e6
    phi = np.radians(lat)[:, None]
    d = np.radians(1.0)
    u, v = gaussian_filter(u, 1.0), gaussian_filter(v, 1.0)
    dudx = np.gradient(u, d, axis=1) / (a * np.cos(phi))
    dvdy = -np.gradient(v * np.cos(phi), d, axis=0) / (a * np.cos(phi))   # rows run north to south
    return (dudx + dvdy) * 1e5


def _vort(u, v, lat):
    """relative vorticity (1e-5 /s), positive cyclonic (troughs), smoothed"""
    from scipy.ndimage import gaussian_filter
    a = 6.371e6
    phi = np.radians(lat)[:, None]
    d = np.radians(1.0)
    u, v = gaussian_filter(u, 1.0), gaussian_filter(v, 1.0)
    dvdx = np.gradient(v, d, axis=1) / (a * np.cos(phi))
    dudy = -np.gradient(u * np.cos(phi), d, axis=0) / (a * np.cos(phi))
    return (dvdx - dudy) * 1e5


def features(f, pw_normal=None):
    """{name: 2-D array on LAT x LON} of the ingredients from the fields f (cut to BOX)"""
    out = {
        "pw": f["pw"],
        "lapse": f["t925"] - f["t500"],            # K, steeper is less stable
        "t500": f["t500"] - 273.15,                # deg C, cold aloft
        "vort500": _vort(f["u500"], f["v500"], LAT),
        "conv925": -_div(f["u925"], f["v925"], LAT),
        "div200": _div(f["u200"], f["v200"], LAT),
        "rh700": f["rh700"],
        "cape": np.log1p(np.maximum(f["cape"], 0)),
        "high": np.clip((95000 - f["psfc"]) / 10000, 0, 1.5),   # how high the ground is (0 at 950 hPa)
    }
    if pw_normal is not None:
        out["pwpct"] = 100 * f["pw"] / np.maximum(pw_normal, 1)
    return out


_MASK = None


def kingdom_mask():
    global _MASK
    if _MASK is None:
        import sa_geo
        regs = sa_geo.regions()
        la, lo = np.meshgrid(LAT, LON, indexing="ij")
        _MASK = sa_geo.region_of_points(regs, la.ravel(), lo.ravel()).reshape(la.shape)
    return _MASK


def coef():
    p = os.path.join(HERE, "ingr_coef.json")
    return json.load(open(p)) if os.path.exists(p) else None


def chance(feat, c=None):
    """chance of 5 mm or more in the day at each point (logistic model of ingr_coef.json)"""
    c = c or coef()
    z = np.full(feat["pw"].shape, c["b0"], float)
    zs = {}
    for k, (mu, sd, b) in c["terms"].items():
        x = (np.asarray(feat[k], float) - mu) / sd
        zs[k] = x
        z += b * x
        if k in c.get("sq", {}):
            z += c["sq"][k] * x * x
    for a, b2, w in c.get("inter", []):
        z += w * zs[a] * zs[b2]
    return 1 / (1 + np.exp(-np.clip(z, -40, 40)))


def potential(feat, c=None):
    """{'ksa': expected share of the Kingdom with 5 mm or more, 'regions': {region index: share}, 'p': chance map}"""
    p = chance(feat, c)
    m = kingdom_mask()
    w = np.cos(np.radians(LAT))[:, None] * np.ones_like(p)
    ksa = m >= 0
    c = c or coef()
    raw = float((p * w)[ksa].sum() / w[ksa].sum())
    f = 1.0
    if c.get("qmap"):          # in the units of the reference rain spread (quantile mapping of the fit)
        qp, qt = c["qmap"]
        f = float(np.interp(raw, qp, qt)) / max(raw, 1e-6)
    out = {"ksa": min(raw * f, 1.0), "raw": raw, "regions": {}, "regions_raw": {}, "p": p}
    for k in sorted(set(m[ksa].tolist())):
        r = m == k
        v = float((p * w)[r].sum() / w[r].sum())
        out["regions_raw"][int(k)] = v
        out["regions"][int(k)] = min(v * f, 1.0)
    return out


def spread(rain, thr=5.0):
    """{'ksa': share of the Kingdom with thr mm or more, 'regions': {region index: share}} of a daily rain field
    (cut to BOX)"""
    m = kingdom_mask()
    w = np.cos(np.radians(LAT))[:, None] * np.ones(rain.shape)
    wet = (rain >= thr).astype(float)
    ksa = m >= 0
    out = {"ksa": float((wet * w)[ksa].sum() / w[ksa].sum()), "regions": {}}
    for k in sorted(set(m[ksa].tolist())):
        r = m == k
        out["regions"][int(k)] = float((wet * w)[r].sum() / w[r].sum())
    return out


def pw_normal(clim, doy):
    """the normal precipitable water of day-of-year index doy (as daily.doy gives), on LAT x LON"""
    from scipy.ndimage import map_coordinates
    plat, plon = clim["pw_lat"], clim["pw_lon"]
    cl = clim["pw"][doy]
    J = (LAT[:, None] - plat[0]) / (plat[1] - plat[0]) * np.ones((1, len(LON)))
    I = (LON[None, :] - plon[0]) / (plon[1] - plon[0]) * np.ones((len(LAT), 1))
    return map_coordinates(cl, [J, I], order=1, mode="nearest")
