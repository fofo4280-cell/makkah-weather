"""Night-time sea cells of the Red Sea reaching the Hijaz coasts, and Makkah and Al-Jumum behind them (Fahad, 26 Nov
2026: «ماذا عن النظام الحملي والتخاريج البحرية» … «انت محلل خبير والمفترض ما تفوتك هذه التفاصيل»).

A third of the Makkah-area rain of November falls with no trough (nov-regime study). The rain-making index of
refwave/hijaz weighs the lift aloft and is read at 12 UTC only, so it misses the cells that grow over the warm sea at
night and are carried onto the coast. This is a reading of their ingredients, never of model rain:

  - fuel over the sea: CAPE (the strongest tenth of the sea cells off the stretch) and the cap (CIN) above it;
  - moisture over the sea: precipitable water;
  - the trigger: low-level convergence over the sea (the southerly of the south Red Sea meeting the northerly), the
    strongest cell of the band, 10 m winds smoothed over half a degree;
  - the carrier: the 700-500 hPa wind across the coast (eastward = onshore);
  - the mid levels: 700 hPa relative humidity (dry air there kills weak cells and makes dusty outflows).

Each stretch of the coast (the same as hijaz.py, grouped: the north of the Makkah coast, Jeddah, the south of the
Makkah coast, Al-Qunfudhah, Yanbu, Ar-Rais) gets an index 0..1 at 18, 00 and 06 UTC of the night (9 PM, 3 AM, 9 AM
Makkah), and the night keeps its strongest time. Makkah and Al-Jumum get the index of the coast west of them (north of
the Makkah coast and Jeddah) carried inland by the steering wind, times the fuel on the plain itself.

Night k of a cycle = the evening of the cycle date + k, to the morning after: leads 24k+6, 24k+12, 24k+18 h of a 12 UTC
cycle.
"""
import numpy as np

BOX = (17.5, 25.5, 36.0, 41.5)   # lat0, lat1, lon0, lon1
RES = 0.25
SEA_W = 1.5                      # the sea strip off each stretch, degrees west of the coast
# (key, name, lat from, lat to), north to south
STRETCHES = [("yanbu", "ينبع", 23.85, 25.0, "md"), ("rais", "الرايس", 23.0, 23.85, "md"),
             ("north", "شمال سواحل منطقة مكة (ثول ورابغ)", 21.65, 23.0, "mk"), ("jeddah", "جدة", 21.3, 21.65, "mk"),
             ("south", "جنوب سواحل منطقة مكة (الشعيبة والليث)", 19.7, 21.3, "mk"),
             ("qunf", "القنفذة", 18.6, 19.7, "mk")]
NAME = {k: n for k, n, *_ in STRETCHES}
PLAIN = (21.2, 21.85, 39.6, 40.1)   # Makkah, Al-Jumum and Bahra
FIELDS = [("cape", r":CAPE:surface:"), ("cin", r":CIN:surface:"),
          ("pw", r":PWAT:entire atmosphere \(considered as a single layer\):"),
          ("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
          ("u700", r":UGRD:700 mb:"), ("u500", r":UGRD:500 mb:"), ("rh700", r":RH:700 mb:"), ("land", r":LAND:surface:")]
LEVELS = (0.25, 0.45, 0.65)   # weak, medium, likely (set by the test of 26 Nov 2026, see PROJECT.md)
WORD = {1: "ضعيفة", 2: "متوسطة", 3: "مرجحة"}
_MASKS = None


def _grid():
    return np.arange(BOX[1], BOX[0] - 1e-6, -RES), np.arange(BOX[2], BOX[3] + 1e-6, RES)


def cut(a):
    """the box of a global 0.25 degree GFS field (lat 90..-90, lon 0..359.75)"""
    j0, j1 = int(round((90 - BOX[1]) / RES)), int(round((90 - BOX[0]) / RES))
    i0, i1 = int(round(BOX[2] / RES)), int(round(BOX[3] / RES))
    return a[j0:j1 + 1, i0:i1 + 1]


def masks(land):
    """{key: (sea mask, coast land mask)} for each stretch and the plain, from the GFS land field of the box"""
    global _MASKS
    if _MASKS is not None:
        return _MASKS
    la, lo = _grid()
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    L = land >= 0.5
    # the Arabian coast in each row: the land cell just east of the easternmost sea cell (the African coast and the
    # islands lie west of it)
    out = {}
    coast_lon = np.full(len(la), np.nan)
    for j in range(len(la)):
        sea_i = np.nonzero(~L[j])[0]
        if len(sea_i) and sea_i[-1] + 1 < len(lo):
            coast_lon[j] = lo[sea_i[-1] + 1]
    for key, _n, a, b, _r in STRETCHES:
        band = (LA >= a) & (LA < b)
        cl = coast_lon[:, None] * np.ones_like(LO)
        sea = band & ~L & (LO < cl) & (LO >= cl - SEA_W)
        coast = band & L & (LO >= cl) & (LO <= cl + 0.5)
        out[key] = (sea, coast)
    plain = (LA >= PLAIN[0]) & (LA <= PLAIN[1]) & (LO >= PLAIN[2]) & (LO <= PLAIN[3]) & L
    out["plain"] = (plain, plain)
    _MASKS = out
    return out


def _conv(u, v):
    """low-level convergence (1e-5 /s, positive = converging) on the box, winds smoothed over half a degree"""
    from scipy.ndimage import uniform_filter
    la, _ = _grid()
    u, v = uniform_filter(u, 3, mode="nearest"), uniform_filter(v, 3, mode="nearest")
    dx = 111e3 * RES * np.cos(np.radians(la))[:, None]
    dy = 111e3 * RES
    dudx = np.gradient(u, axis=1) / dx
    dvdy = -np.gradient(v, axis=0) / dy   # rows run north to south
    return -(dudx + dvdy) * 1e5


def features(g):
    """{key: ingredients} of one time from the cut fields g"""
    M = masks(g["land"])
    cv = _conv(g["u10"], g["v10"])
    steer = 0.5 * (g["u700"] + g["u500"])
    out = {}
    for key, (sea, coast) in M.items():
        if not sea.any():
            continue
        cape = g["cape"][sea]
        top = cape >= np.quantile(cape, 0.9)
        out[key] = {"cape": round(float(np.quantile(cape, 0.9))), "cin": round(float(np.median(g["cin"][sea][top]))),
                    "pw": round(float(g["pw"][sea].mean()), 1), "conv": round(float(cv[sea].max()), 2),
                    "steer": round(float(steer[sea | coast].mean()), 1), "rh700": round(float(g["rh700"][sea].mean())),
                    "cape_coast": round(float(np.quantile(g["cape"][coast], 0.9))) if coast.any() else 0,
                    "cin_coast": round(float(np.median(g["cin"][coast]))) if coast.any() else 0}
    return out


def index(f):
    """0..1 from one stretch's ingredients of one time"""
    cl = lambda x: float(np.clip(x, 0, 1))
    fuel = cl((f["cape"] - 500) / 2500) * (1.0 if f["cin"] >= -50 else 0.5 if f["cin"] >= -150 else 0.0)
    moist = cl((f["pw"] - 22) / 15)
    trig = cl(f["conv"] / 2.0)
    carry = cl(f["steer"] / 6.0)
    mid = cl((f["rh700"] - 20) / 40)
    return round(fuel * moist * (0.35 + 0.65 * trig) * (0.3 + 0.7 * carry) * (0.5 + 0.5 * mid), 3)


def plain_index(night):
    """Makkah and Al-Jumum: the coast west of them carried inland, times the fuel on the plain itself"""
    best = 0.0
    for t in night["times"]:
        c = max(t["si"].get("jeddah", 0), t["si"].get("north", 0))
        p = t["f"].get("plain")
        if not p:
            continue
        reach = float(np.clip((p["steer"] - 3) / 7, 0, 1))
        fuel = float(np.clip((p["cape_coast"] - 300) / 1700, 0, 1)) * (1.0 if p["cin_coast"] >= -75 else 0.5)
        best = max(best, c * reach * (0.4 + 0.6 * fuel))
    return round(best, 3)


def night(get_fields, cycle, k):
    """{d, times: [{h, f, si}], si: {key: night max}, plain} for night k of a 12 UTC cycle (see the docstring)"""
    from datetime import datetime, timedelta
    t0 = datetime.strptime(cycle[:8], "%Y%m%d").date()
    base = 0 if cycle[8:10] == "12" else 12
    times = []
    for h in (6, 12, 18):
        fh = 24 * k + h + base
        g = None
        for _t in range(3):
            try:
                g = {n: cut(a) for n, a in get_fields(cycle, fh, res="0p25", fields=FIELDS).items()}
                break
            except Exception as e:  # noqa: BLE001
                print("seacell download failed", fh, repr(e)[:120], flush=True)
        if g is None:
            continue
        f = features(g)
        times.append({"h": (18 + h - 6) % 24, "f": f, "si": {key: index(v) for key, v in f.items() if key != "plain"}})
    out = {"d": (t0 + timedelta(days=k)).isoformat(), "times": times}
    keys = [key for key, *_ in STRETCHES]
    out["si"] = {key: max([t["si"].get(key, 0) for t in times] or [0]) for key in keys}
    out["plain"] = plain_index(out)
    return out


def fetch(cycle, nights, get_fields):
    """the nights 0..nights of the cycle (the report's day and the days after)"""
    rows = []
    for k in range(nights + 1):
        r = night(get_fields, cycle, k)
        if not r["times"]:
            break
        rows.append(r)
    return rows


def level(x):
    return sum(1 for t in LEVELS if x >= t)


def reasons(r, key):
    """the ingredients of the stretch at its strongest time, in words"""
    t = max(r["times"], key=lambda t: t["si"].get(key, 0))
    f = t["f"][key]
    hh = {18: "التاسعة مساءً", 0: "الثالثة فجرًا", 6: "التاسعة صباحًا"}.get(t["h"], "")
    return f, hh
