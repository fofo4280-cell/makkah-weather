"""Map products: how each field is computed from a WRF output frame and how it is coloured."""
import numpy as np

# Colour scales: list of (lower bound, hex colour). Values below the first bound are transparent.
REFL = [(5, "#9fe6ff"), (10, "#4cc3ef"), (15, "#2489d6"), (20, "#2fcf6b"), (25, "#1ea84a"), (30, "#127a30"),
        (35, "#f7e53b"), (40, "#f4b52d"), (45, "#ef7a1f"), (50, "#e2321f"), (55, "#b51c1c"), (60, "#d53be0"),
        (65, "#8d22b8"), (70, "#ffffff")]
RAIN1 = [(0.2, "#b5e3ff"), (1, "#6cc3f5"), (2, "#2c8fe0"), (5, "#2a5fc9"), (10, "#2fbf5c"), (15, "#f2d230"),
         (20, "#f39a26"), (30, "#e53b25"), (50, "#b01e8f")]
RAINACC = [(0.5, "#cdeeff"), (1, "#8fd3fb"), (2, "#4fb0ef"), (5, "#2a7fdc"), (10, "#2fbf5c"), (20, "#1e8a3c"),
           (30, "#f2d230"), (50, "#f39a26"), (75, "#e53b25"), (100, "#b01e8f"), (150, "#6a1b9a")]
WIND = [(15, "#cfe8f3"), (25, "#8fcbe6"), (35, "#4fa9d8"), (45, "#3fbf7f"), (55, "#f2d230"), (65, "#f39a26"),
        (75, "#e53b25"), (90, "#b01e8f"), (110, "#5b1680")]
WUP = [(2, "#c6e9ff"), (4, "#78c8f2"), (6, "#3496dd"), (8, "#30bf66"), (10, "#f2d230"), (15, "#f39a26"),
       (20, "#e53b25"), (30, "#a3188f")]


def _temp_scale():
    stops = [(-4, "#3b2a8c"), (4, "#2f6bd1"), (12, "#33b4d6"), (18, "#55c27a"), (24, "#d8d53a"),
             (30, "#f2a12d"), (36, "#e2502a"), (42, "#a8172f"), (48, "#5e0b24")]
    out = []
    for t in range(-4, 49, 2):
        for k in range(len(stops) - 1):
            if stops[k][0] <= t <= stops[k + 1][0]:
                a, b = stops[k], stops[k + 1]
                f = (t - a[0]) / (b[0] - a[0])
                ca = [int(a[1][i:i + 2], 16) for i in (1, 3, 5)]
                cb = [int(b[1][i:i + 2], 16) for i in (1, 3, 5)]
                c = [round(ca[i] + f * (cb[i] - ca[i])) for i in range(3)]
                out.append((t if t > -4 else -99, "#%02x%02x%02x" % tuple(c)))
                break
    return out


TEMP = _temp_scale()

# id -> label (Arabic), unit, scale, alpha
PRODUCTS = {
    "refl":    {"label": "الانعكاسية الرادارية المركبة", "unit": "ديسيبل", "scale": REFL, "alpha": 235},
    "rain1h":  {"label": "مطر الساعة", "unit": "ملم", "scale": RAIN1, "alpha": 235},
    "rainacc": {"label": "المطر المتراكم منذ البداية", "unit": "ملم", "scale": RAINACC, "alpha": 235},
    "t2":      {"label": "درجة الحرارة على ارتفاع مترين", "unit": "°م", "scale": TEMP, "alpha": 190},
    "wind":    {"label": "أقصى رياح سطحية خلال الساعة", "unit": "كم/س", "scale": WIND, "alpha": 210},
    "wup":     {"label": "أقصى تيار صاعد خلال الساعة", "unit": "م/ث", "scale": WUP, "alpha": 235},
}
DAILY = {
    "refl_day": {"label": "أقصى انعكاسية خلال اليوم", "unit": "ديسيبل", "scale": REFL, "alpha": 235, "from": "refl"},
    "rain_day": {"label": "مجموع مطر اليوم", "unit": "ملم", "scale": RAINACC, "alpha": 235, "from": "rain1h"},
}


def palette(scale, alpha):
    """Index 0 is transparent; index k (1..n) is scale[k-1]."""
    pal = [0, 0, 0]
    trans = [0]
    for _, hexc in scale:
        pal += [int(hexc[i:i + 2], 16) for i in (1, 3, 5)]
        trans.append(alpha)
    return pal, trans


def classify(field, scale):
    bounds = np.array([b for b, _ in scale], dtype=np.float32)
    idx = np.digitize(np.nan_to_num(field, nan=-1e9), bounds)  # 0 = below first bound
    idx[~np.isfinite(field)] = 0
    return idx.astype(np.uint8)


def legend(scale):
    return [{"v": (None if b == -99 else b), "c": c} for b, c in scale]


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
