"""Map products: how each field is computed from a WRF output frame and how it is coloured.

Colours are continuous gradients: each image is an 8-bit palette PNG whose 255 entries run
smoothly through the colour stops, with transparency fading in at the weak end so storm
edges look soft instead of stepped.
"""
import math

import numpy as np

# Stops: (value, colour, alpha 0-255). tf: how values are spread along the scale.
REFL = [(5, "#7fdcff", 0), (10, "#5cc8f2", 120), (15, "#3aa6e8", 190), (20, "#2bc275", 225),
        (28, "#16994a", 235), (35, "#f7e348", 240), (42, "#f6a52c", 245), (50, "#ea4a2c", 250),
        (57, "#b8102f", 250), (63, "#e046e6", 250), (70, "#9a2bd1", 250), (75, "#ffffff", 255)]
RAIN = [(0.1, "#a8e2ff", 0), (0.5, "#79cbf6", 170), (1.5, "#3d9ce6", 215), (4, "#2a63d0", 235),
        (8, "#2fc06a", 240), (15, "#f4d53a", 245), (25, "#f58a28", 250), (40, "#e2322b", 250),
        (60, "#b0198f", 255), (100, "#6a1b9a", 255)]
RAINACC = [(0.2, "#a8e2ff", 0), (1, "#79cbf6", 170), (3, "#3d9ce6", 215), (8, "#2a63d0", 235),
           (15, "#2fc06a", 240), (25, "#f4d53a", 245), (40, "#f58a28", 250), (60, "#e2322b", 250),
           (100, "#b0198f", 255), (150, "#6a1b9a", 255)]
TEMP = [(-4, "#3b2a8c", 200), (4, "#2f6bd1", 200), (12, "#33b4d6", 200), (18, "#55c27a", 200),
        (24, "#d8d53a", 200), (30, "#f2a12d", 200), (36, "#e2502a", 200), (42, "#a8172f", 205),
        (48, "#5e0b24", 210)]
WIND = [(10, "#b9e3f2", 0), (20, "#8fcbe6", 150), (30, "#4fa9d8", 200), (40, "#3fbf7f", 220),
        (50, "#f2d230", 235), (60, "#f39a26", 240), (75, "#e53b25", 245), (90, "#b01e8f", 250),
        (110, "#5b1680", 255)]
WUP = [(1, "#b6e2fb", 0), (3, "#78c8f2", 160), (5, "#3496dd", 210), (8, "#30bf66", 230),
       (11, "#f2d230", 240), (15, "#f39a26", 245), (20, "#e53b25", 250), (30, "#a3188f", 255)]
# Vertically integrated water vapour transport 1000-600 hPa, banded like the atmospheric-river scale (kg/m/s)
IVT = [(150, "#56a3d4", 190), (259, "#56a3d4", 205), (260, "#f1c04c", 215), (369, "#f1c04c", 220), (370, "#f08a2a", 225),
       (479, "#f08a2a", 230), (480, "#df535a", 235), (559, "#df535a", 235), (560, "#7a2fbd", 240), (669, "#7a2fbd", 240),
       (670, "#14161e", 245), (900, "#000000", 250)]
# Chance of a thunderstorm (radar 40 dBZ or more) within 25 km at some hour of the 24 hours, in %
TSPROB = [(5, "#efeefe", 0), (10, "#d9d6fb", 150), (16, "#b9c7f1", 190), (20, "#55d3d6", 215), (25, "#27eee6", 225),
          (30, "#8cf37a", 230), (35, "#f4ee1d", 235), (40, "#ffb000", 240), (46, "#ff5810", 245), (50, "#e20000", 248),
          (60, "#8a0012", 250), (66, "#4a1b29", 250), (72, "#575757", 250), (90, "#c9c9c9", 250)]
# Where the air meets at 925 hPa (10^-5 /s); nothing is drawn where the ground is above 925 hPa
CONV = [(0.8, "#fbe7a1", 0), (1.5, "#f9d77e", 150), (2.5, "#f5ad3c", 200), (4, "#ea6a25", 225), (6, "#cf2d22", 240),
        (9, "#8f1030", 250), (13, "#4d0a3a", 255)]

PRODUCTS = {
    "refl":    {"label": "الانعكاسية الرادارية المركبة", "unit": "ديسيبل", "stops": REFL, "tf": "lin"},
    "rain1h":  {"label": "مطر الساعة", "unit": "ملم", "stops": RAIN, "tf": "sqrt", "bands": True},
    "conv925": {"label": "التقاء الرياح عند ٩٢٥ هكتوباسكال", "unit": "×١٠⁻⁵ /ث", "stops": CONV, "tf": "lin", "computed": True},
    "ivt":     {"label": "الأنهار الجوية: نقل بخار الماء", "unit": "كغ/م/ث", "stops": IVT, "tf": "lin", "only": "ivt"},
}
DAILY = {
    "refl_day": {"label": "أقصى انعكاسية لكل يوم", "unit": "ديسيبل", "stops": REFL, "tf": "lin", "from": "refl"},
}

# One map per run: rain over the 24 hours after the first 3 (the model's spin-up), or as far as the run got.
SINGLE = {
    "rain24": {"label": "المطر التراكمي +٢٤", "unit": "ملم", "stops": RAINACC, "tf": "sqrt", "from_h": 3, "len": 24,
               "bands": True},
    "tsprob": {"label": "احتمال العواصف الرعدية +٢٤", "unit": "٪", "stops": TSPROB, "tf": "lin", "from_h": 3,
               "len": 24, "dbz": 40, "radius_km": 25},
}
# Temperature and wind are no longer drawn as maps but stay in the tap-anywhere values and city charts.

# Point values for tap-anywhere: one byte per value.
POINT_VARS = ["rain1h", "refl", "t2", "wind"]


def encode_point(var, a):
    a = np.nan_to_num(np.asarray(a, dtype=np.float32), nan=0.0)
    if var == "rain1h":
        c = np.sqrt(np.clip(a, 0, 100)) * 25
    elif var == "refl":
        c = np.clip(a, 0, 85) * 3
    elif var == "t2":
        c = (a + 10) * 4
    else:  # wind km/h
        c = a * 2
    return np.clip(np.rint(c), 0, 255).astype(np.uint8)


def _t(v, tf):
    v = np.asarray(v, dtype=np.float64)
    return np.sqrt(np.maximum(v, 0)) if tf == "sqrt" else v


def _hex(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


BAND_ALPHA_MIN = 160


def palette(spec):
    """256-entry palette (index 0 transparent) interpolated through the stops."""
    stops, tf = spec["stops"], spec["tf"]
    pos = _t([s[0] for s in stops], tf)
    t = np.linspace(pos[0], pos[-1], 255)
    cols = np.array([_hex(s[1]) for s in stops], dtype=np.float64)
    al = np.array([s[2] for s in stops], dtype=np.float64)
    if spec.get("bands"):
        # solid colour bands, one per step of the scale (like a weather-service radar), the weakest band visible too
        b = np.clip(np.searchsorted(pos, t + 1e-9, side="right") - 1, 0, len(stops) - 1)
        rgb = cols[b]
        alpha = np.maximum(al[b], BAND_ALPHA_MIN)
        pal = [0, 0, 0] + [int(round(x)) for x in rgb.reshape(-1)]
        return pal, [0] + [int(round(x)) for x in alpha]
    rgb = np.stack([np.interp(t, pos, cols[:, k]) for k in range(3)], axis=1)
    alpha = np.interp(t, pos, al)
    pal = [0, 0, 0] + [int(round(x)) for x in rgb.reshape(-1)]
    trans = [0] + [int(round(x)) for x in alpha]
    return pal, trans


def classify(field, spec):
    """Map values to palette indices 1..255 (0 = transparent below the first stop)."""
    stops, tf = spec["stops"], spec["tf"]
    lo, hi = _t(stops[0][0], tf), _t(stops[-1][0], tf)
    f = np.asarray(field, dtype=np.float64)
    tv = _t(f, tf)
    idx = 1 + np.rint((tv - lo) / (hi - lo) * 254)
    if spec.get("bands"):
        # the exact band of each value (a value on a step gets the band above it), drawn with that band's middle entry
        pos = _t([x[0] for x in stops], tf)
        b = np.clip(np.searchsorted(pos, np.nan_to_num(tv, nan=lo), side="right") - 1, 0, len(stops) - 1)
        mid = np.array([1 + np.rint(((pos[i] + pos[min(i + 1, len(pos) - 1)]) / 2 - lo) / (hi - lo) * 254)
                        for i in range(len(pos))])
        idx = mid[b]
    idx = np.clip(idx, 1, 255)
    below = f < stops[0][0]
    if spec.get("opaque"):
        below = np.zeros_like(below)
    idx[below | ~np.isfinite(f)] = 0
    return idx.astype(np.uint8)


def legend(spec):
    stops, tf = spec["stops"], spec["tf"]
    pos = _t([s[0] for s in stops], tf)
    p = (pos - pos[0]) / (pos[-1] - pos[0])
    out = {"tf": tf, "vmin": stops[0][0], "vmax": stops[-1][0],
           "stops": [{"p": round(float(pp), 4), "v": s[0], "c": s[1], "a": s[2]} for pp, s in zip(p, stops)]}
    if spec.get("bands"):
        out["bands"] = True
        for x in out["stops"]:
            x["a"] = max(x["a"], BAND_ALPHA_MIN)
    return out


def ivt_from_frame(nc):
    """Water vapour transport 1000-600 hPa: magnitude and earth-relative east/north parts (kg/m/s)."""
    v = nc.variables
    p = np.array(v["P"][0], dtype=np.float32) + np.array(v["PB"][0], dtype=np.float32)
    q = np.array(v["QVAPOR"][0], dtype=np.float32)
    U, V = np.array(v["U"][0], dtype=np.float32), np.array(v["V"][0], dtype=np.float32)
    u, w = 0.5 * (U[:, :, 1:] + U[:, :, :-1]), 0.5 * (V[:, 1:, :] + V[:, :-1, :])
    pe = np.empty((p.shape[0] + 1,) + p.shape[1:], dtype=np.float32)  # layer edges, bottom to top
    pe[1:-1] = 0.5 * (p[1:] + p[:-1])
    pe[0], pe[-1] = p[0] + 0.5 * (p[0] - p[1]), p[-1] - 0.5 * (p[-2] - p[-1])
    dp = np.maximum(np.clip(pe[:-1], 60000, 100000) - np.clip(pe[1:], 60000, 100000), 0)
    qu, qv = (q * u * dp).sum(0) / 9.81, (q * w * dp).sum(0) / 9.81
    if "SINALPHA" in v and "COSALPHA" in v:
        sa, ca = np.array(v["SINALPHA"][0]), np.array(v["COSALPHA"][0])
        qu, qv = qu * ca - qv * sa, qv * ca + qu * sa
    return np.hypot(qu, qv), qu, qv


def conv925_from_frame(nc, dx):
    """Convergence at 925 hPa (10^-5 /s, NaN where the ground is higher) and the earth-relative wind there (m/s)."""
    from scipy.ndimage import gaussian_filter
    v = nc.variables
    p = np.array(v["P"][0], dtype=np.float32) + np.array(v["PB"][0], dtype=np.float32)
    U, V = np.array(v["U"][0], dtype=np.float32), np.array(v["V"][0], dtype=np.float32)
    u, w = 0.5 * (U[:, :, 1:] + U[:, :, :-1]), 0.5 * (V[:, 1:, :] + V[:, :-1, :])
    above = p < 92500.0                      # levels above 925 hPa
    k1 = np.argmax(above, axis=0)            # first level above
    ok = k1 > 0                              # 925 hPa is above the ground here
    k0 = np.clip(k1 - 1, 0, p.shape[0] - 1)
    take = lambda a, k: np.take_along_axis(a, k[None], 0)[0]
    p0, p1 = take(p, k0), take(p, k1)
    f = np.clip((np.log(p0) - np.log(92500.0)) / np.maximum(np.log(p0) - np.log(p1), 1e-6), 0, 1)
    u9 = take(u, k0) + f * (take(u, k1) - take(u, k0))
    v9 = take(w, k0) + f * (take(w, k1) - take(w, k0))
    sig = max(1.0, 9000.0 / dx)              # smooth to about 9 km so the lines stand out from the noise
    # Where the ground is above 925 hPa the "925 hPa wind" would be the wind over the mountain top; leave those
    # points out of the smoothing (normalised convolution) so the edge of the high ground does not show false
    # convergence, and leave out a margin where the level lies within ~150 m of the ground or next to the edge.
    from scipy.ndimage import binary_erosion
    good = ok & (p[0] >= 94000.0)
    wgt = gaussian_filter(good.astype(np.float32), sig)
    us = gaussian_filter(np.where(good, u9, 0.0), sig) / np.maximum(wgt, 1e-3)
    vs = gaussian_filter(np.where(good, v9, 0.0), sig) / np.maximum(wgt, 1e-3)
    conv = -(np.gradient(us, dx, axis=1) + np.gradient(vs, dx, axis=0)) * 1e5
    inner = binary_erosion(good, iterations=int(round(sig)) + 1, border_value=1)
    conv[~inner] = np.nan
    if "SINALPHA" in v and "COSALPHA" in v:
        sa, ca = np.array(v["SINALPHA"][0]), np.array(v["COSALPHA"][0])
        u9, v9 = u9 * ca - v9 * sa, v9 * ca + u9 * sa
    u9[~ok], v9[~ok] = np.nan, np.nan
    return conv, u9, v9


def fields_from_frame(nc, prev_acc):
    """Return dict of 2-D fields for one wrfout frame and the new accumulated rain."""
    v = nc.variables
    acc = np.array(v["RAINNC"][0], dtype=np.float32) + np.array(v["RAINC"][0], dtype=np.float32)
    if "I_RAINNC" in v:
        acc += 100.0 * np.array(v["I_RAINNC"][0], dtype=np.float32)
    out = {
        "refl": np.max(np.array(v["REFL_10CM"][0], dtype=np.float32), axis=0) if "REFL_10CM" in v else None,
        "rainacc": acc,
        "rain1h": np.maximum(acc - prev_acc, 0) if prev_acc is not None else np.zeros_like(acc),
        "t2": np.array(v["T2"][0], dtype=np.float32) - 273.15,
        "wind": (np.array(v["WSPD10MAX"][0], dtype=np.float32) * 3.6) if "WSPD10MAX" in v else
                np.hypot(np.array(v["U10"][0]), np.array(v["V10"][0])).astype(np.float32) * 3.6,
        "wup": np.array(v["W_UP_MAX"][0], dtype=np.float32) if "W_UP_MAX" in v else None,
    }
    return {k: f for k, f in out.items() if f is not None}, acc


COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _from_dir(u, v):
    """Meteorological direction the wind blows from (degrees) and its 8-point name."""
    a = (math.degrees(math.atan2(-u, -v)) + 360) % 360
    return a, COMPASS[int((a + 22.5) // 45) % 8]


def conv_labels(cv, u, v, hgt, lat, lon, dx, thr=3.0, seg_km=80.0, min_km2=300.0):
    """Where the 925 hPa air meets, which winds make it: one label per piece of each convergence area (pieces of
    about 80 km along long lines), placed on the strongest part of the colour.
    'W - E': a west wind meets an east wind (the one blowing from the larger compass angle first).
    'SW - Orographic': the lift comes from the wind running up the high ground.
    Returns [[lat, lon, text], ...]."""
    from scipy.ndimage import label, binary_dilation
    good = np.isfinite(cv)
    blobs, n = label(np.where(good, cv, 0) >= thr, structure=np.ones((3, 3)))
    if n == 0:
        return []
    hx = np.gradient(hgt.astype(np.float64), dx, axis=1)
    hy = np.gradient(hgt.astype(np.float64), dx, axis=0)
    r = max(2, int(round(15000.0 / dx)))
    jj, ii = np.mgrid[0:cv.shape[0], 0:cv.shape[1]]
    min_cells = max(4, int(min_km2 * 1e6 / dx ** 2))
    out = []
    for b in range(1, n + 1):
        m = blobs == b
        if m.sum() < min_cells:
            continue
        y, x = jj[m].astype(float), ii[m].astype(float)
        c = np.array([x.mean(), y.mean()])
        cov = np.cov(np.vstack([x - c[0], y - c[1]])) if m.sum() > 2 else np.eye(2)
        ev, evec = np.linalg.eigh(cov)
        ax = evec[:, 1]                              # along the line
        s = (x - c[0]) * ax[0] + (y - c[1]) * ax[1]
        nseg = max(1, int(round((s.max() - s.min()) * dx / 1000.0 / seg_km)))
        edges = np.linspace(s.min(), s.max() + 1e-6, nseg + 1)
        for k in range(nseg):
            sel = (s >= edges[k]) & (s < edges[k + 1])
            if sel.sum() < min_cells // 2 + 1:
                continue
            seg = np.zeros_like(m); seg[jj[m][sel], ii[m][sel]] = True
            w = np.clip(cv[seg], 0, None)
            sx, sy = (ii[seg] * w).sum() / w.sum(), (jj[seg] * w).sum() / w.sum()
            q = int(np.argmin((ii[seg] - sx) ** 2 + (jj[seg] - sy) ** 2))
            pj, pi = jj[seg][q], ii[seg][q]
            ring = binary_dilation(seg, iterations=r) & ~m & np.isfinite(u) & np.isfinite(v)
            side = ((ii - sx) * -ax[1] + (jj - sy) * ax[0]) > 0          # the two sides of the line
            winds = []
            for part in (ring & side, ring & ~side):
                if part.sum() >= 3:
                    winds.append((float(np.nanmean(u[part])), float(np.nanmean(v[part]))))
            if not winds:
                continue
            near = binary_dilation(seg, iterations=r)
            wu, wv = np.nanmean(u[near]), np.nanmean(v[near])
            up = np.nanmean((u * hx + v * hy)[near & np.isfinite(u)])          # m/s lifted by the slope
            # does the ground rise ahead of the wind? (250 m or more within 50 km downwind)
            toward = False
            sp = math.hypot(wu, wv)
            if sp > 1.5:
                h0 = float(np.nanmean(hgt[seg]))
                ahead = []
                for dkm in range(10, 55, 5):
                    ti = int(round(sx + wu / sp * dkm * 1000 / dx)); tj = int(round(sy + wv / sp * dkm * 1000 / dx))
                    if 0 <= tj < hgt.shape[0] and 0 <= ti < hgt.shape[1]:
                        ahead.append(float(hgt[tj, ti]))
                toward = bool(ahead) and max(ahead) - h0 >= 250
            names = [_from_dir(*wnd) for wnd in winds]
            two = len(names) == 2 and min(abs(names[0][0] - names[1][0]), 360 - abs(names[0][0] - names[1][0])) >= 45 \
                and names[0][1] != names[1][1]
            oro = (np.isfinite(up) and up >= 0.05) or toward
            if two and not oro:
                a, b2 = sorted(names, key=lambda t: -t[0])
                txt = f"{a[1]} - {b2[1]}"
            elif oro:
                # the main wind: the one blowing towards the high ground, else the mean
                main = _from_dir(wu, wv)[1]
                if two:
                    a, b2 = sorted(names, key=lambda t: -t[0])
                    txt = f"{a[1]} - {b2[1]} · Orographic"
                else:
                    txt = f"{main} - Orographic"
            else:
                txt = f"{_from_dir(wu, wv)[1]}"                              # one wind slowing down
            out.append([round(float(lat[pj, pi]), 3), round(float(lon[pj, pi]), 3), txt])
    return out
