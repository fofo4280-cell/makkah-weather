"""Map products: how each field is computed from a WRF output frame and how it is coloured.

Colours are continuous gradients: each image is an 8-bit palette PNG whose 255 entries run
smoothly through the colour stops, with transparency fading in at the weak end so storm
edges look soft instead of stepped.
"""
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

PRODUCTS = {
    "refl":    {"label": "الانعكاسية الرادارية المركبة", "unit": "ديسيبل", "stops": REFL, "tf": "lin"},
    "rain1h":  {"label": "مطر الساعة", "unit": "ملم", "stops": RAIN, "tf": "sqrt"},
    "ivt":     {"label": "الأنهار الجوية: نقل بخار الماء", "unit": "كغ/م/ث", "stops": IVT, "tf": "lin", "only": "ivt"},
}
DAILY = {
    "refl_day": {"label": "أقصى انعكاسية لكل يوم", "unit": "ديسيبل", "stops": REFL, "tf": "lin", "from": "refl"},
}

# One map per run: rain over the 24 hours after the first 3 (the model's spin-up), or as far as the run got.
SINGLE = {
    "rain24": {"label": "المطر التراكمي +٢٤", "unit": "ملم", "stops": RAINACC, "tf": "sqrt", "from_h": 3, "len": 24},
    "tsprob": {"label": "احتمال العواصف الرعدية +٢٤", "unit": "٪", "stops": TSPROB, "tf": "lin", "from_h": 3,
               "dbz": 40, "radius_km": 25},
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


def palette(spec):
    """256-entry palette (index 0 transparent) interpolated through the stops."""
    stops, tf = spec["stops"], spec["tf"]
    pos = _t([s[0] for s in stops], tf)
    t = np.linspace(pos[0], pos[-1], 255)
    cols = np.array([_hex(s[1]) for s in stops], dtype=np.float64)
    al = np.array([s[2] for s in stops], dtype=np.float64)
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
    return {"tf": tf, "vmin": stops[0][0], "vmax": stops[-1][0],
            "stops": [{"p": round(float(pp), 4), "v": s[0], "c": s[1], "a": s[2]} for pp, s in zip(p, stops)]}


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
