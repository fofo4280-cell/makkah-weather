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
# test of 26 Nov 2026 (1 Oct-24 Nov 2026 nights, GFS 12 UTC +6..+18 h, PERSIANN-PDIR-Now >= 1 mm on 15 % of the
# stretch or its sea strip): index < 0.25 -> 3 % of nights wet, 0.25-0.65 -> 18 %, >= 0.65 -> 56 % (all 8 %)
LEVELS = (0.25, 0.65)
WORD = {1: "محتملة", 2: "مرجحة"}
PLAIN_MIN = 0.25   # Makkah and Al-Jumum: never above 0.45 in the test, so one level only
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


def parts(f):
    """the five ingredients of one stretch at one time, each 0..1"""
    cl = lambda x: float(np.clip(x, 0, 1))
    return {"fuel": cl((f["cape"] - 500) / 2500) * (1.0 if f["cin"] >= -50 else 0.5 if f["cin"] >= -150 else 0.0),
            "moist": cl((f["pw"] - 22) / 15), "trig": cl(f["conv"] / 2.0), "carry": cl(f["steer"] / 6.0),
            "mid": cl((f["rh700"] - 20) / 40)}


def index(f):
    """0..1 from one stretch's ingredients of one time"""
    p = parts(f)
    return round(p["fuel"] * p["moist"] * (0.35 + 0.65 * p["trig"]) * (0.3 + 0.7 * p["carry"]) * (0.5 + 0.5 * p["mid"]), 3)


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


HOUR = {18: "التاسعة مساءً", 0: "الثالثة فجرًا", 6: "التاسعة صباحًا"}
MISSING = {"fuel": "طاقة البحر ضعيفة", "moist": "الهواء فوق البحر غير رطب بما يكفي",
           "trig": "لا التقاء للرياح فوق البحر يرفع الهواء", "carry": "رياح الطبقات المتوسطة لا تحمل الخلايا نحو الساحل",
           "mid": "الطبقات المتوسطة جافة"}


def _num(x):
    from report2 import ar
    return ar(int(round(x)))


def _best(r, key):
    t = max(r["times"], key=lambda t: t["si"].get(key, 0))
    return t, t["f"][key]


def why(f):
    """the ingredients in words, with their numbers"""
    from report2 import num
    t = f"طاقة عدم الاستقرار فوق البحر نحو {_num(round(f['cape'], -2))} جول/كغ، والماء القابل للهطول {_num(f['pw'])} ملم، "
    t += (f"والتقاء الرياح قرب السطح فوق البحر {num(f['conv'], 1)} (×١٠⁻⁵/ث)، " if f["conv"] >= 0.5
          else "ولا التقاء يُذكر للرياح فوق البحر، ")
    t += (f"ورياح الطبقات المتوسطة تحمل الخلايا نحو الساحل بنحو {_num(f['steer'])} م/ث، " if f["steer"] >= 1.5
          else "ورياح الطبقات المتوسطة لا تحملها نحو الساحل، ")
    return t + f"والرطوبة على ٧٠٠ هكتوباسكال {_num(f['rh700'])}٪"


def lines(rows, d0, d1):
    """{d: ([(level, stretch key)], Makkah/Al-Jumum level)} for the nights d0..d1 with a weak chance or more"""
    out = {}
    for r in rows or []:
        if not (str(d0) <= r["d"] <= str(d1)) or not r.get("times"):
            continue
        xs = [(level(v), k) for k, v in r["si"].items() if level(v) >= 1]
        pl = 1 if r.get("plain", 0) >= PLAIN_MIN else 0
        if xs or pl:
            out[r["d"]] = (sorted(xs, key=lambda x: -x[0]), pl)
    return out


def _stretch_words(xs):
    from report2 import jl
    by = {}
    for lv, k in xs:
        by.setdefault(lv, []).append(NAME[k])
    return "، و".join(f"{WORD[lv]} على {jl(by[lv])}" for lv in sorted(by, reverse=True))  # «مرجحة على …، ومحتملة على …»


def tonight(rows, d):
    """the report's day: one paragraph on tonight's sea cells, or why there are none"""
    r = next((x for x in rows or [] if x["d"] == str(d)), None)
    if r is None or not r.get("times"):
        return None
    L = lines([r], d, d).get(str(d))
    key = max(r["si"], key=lambda k: r["si"][k])
    t, f = _best(r, key)
    if not L:
        p = parts(f)
        miss = sorted(p, key=lambda k: p[k])[:2]
        return ("الخلايا البحرية الليلة: لا تجتمع مكوناتها على سواحل الحجاز، لأن " + " و".join(MISSING[m] for m in miss)
                + f" (أقربها {NAME[key]}: {why(f)}).")
    xs, pl = L
    txt = "الخلايا البحرية الليلة (من التاسعة مساءً إلى التاسعة صباحًا): " + (_stretch_words(xs) if xs else "لا تجتمع على السواحل")
    txt += f"، وأقواها نحو {HOUR.get(t['h'], '')} على {NAME[key]}: {why(f)}."
    return txt + (" وقد تبلغ بعض خلاياها مكة والجموم وقد ضعفت." if pl else " ولا يُتوقع أن تبلغ مكة والجموم.")


def coming(rows, d0, d1):
    """the nights after the report's day: one paragraph"""
    from datetime import date
    from report2 import ar_date
    L = lines(rows, d0, d1)
    if not L:
        return ("الخلايا البحرية الليلية على سواحل الحجاز: لا تجتمع مكوناتها في الليالي القادمة حتى "
                f"{ar_date(date.fromisoformat(str(d1)))} في توقع الليلة.")
    ps = []
    for d, (xs, pl) in sorted(L.items()):
        # the weak chances only on a night with nothing stronger, to keep the line short
        t = f"ليلة {ar_date(date.fromisoformat(d))}: " + (_stretch_words(xs) if xs else "لا تجتمع على السواحل")
        if pl:
            t += "، وقد تبلغ بعض خلاياها مكة والجموم"
        ps.append(t)
    bd = max(L, key=lambda d: sum(next(x for x in rows if x["d"] == d)["si"].values()))
    r = next(x for x in rows if x["d"] == bd)
    key = max(r["si"], key=lambda k: r["si"][k])
    t, f = _best(r, key)
    return ("الخلايا البحرية الليلية على سواحل الحجاز (حمل حراري لا يحتاج إلى أخدود، يولد فوق البحر الدافئ ليلًا وتحمله "
            "الرياح إلى الساحل): " + "؛ ".join(ps) + f". وأقواها ليلة {ar_date(date.fromisoformat(bd))} نحو "
            f"{HOUR.get(t['h'], '')} على {NAME[key]}: {why(f)}. (في اختبار ليالي ١ أكتوبر إلى ٢٤ نوفمبر بأمطار الأقمار "
            "الصناعية: ما قُرئ «مرجحة» أمطر في ٥٦٪ من الليالي، و«محتملة» في ١٨٪، والمعتاد ٨٪.)")
