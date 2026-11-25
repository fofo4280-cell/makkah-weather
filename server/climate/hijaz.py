"""Makkah and Madinah regions and their coasts, named apart in the report (Fahad, 25 Nov 2026: «في التقرير فرق بين
الحجاز وغرب المملكة بين المدينة المنورة ومكة وبين سواحل منطقة المدينة وسواحل منطقة مكة واذا كانت الحالة مثلا فقط على
شمال سواحل منطقة مكة اي شمال جدة وثول ورابغ اذكرها واذا كانت جنوب سواحل منطقة مكة اي الشعيبة اذكرها واذا كانت شاملة
الساحل اكتب سواحل منطقة مكة»).

The moisture box «west» (19-26 N, 38-43 E) covers both regions and their coasts, so a wave that reaches it used to be
written «الحجاز وغرب المملكة». Here the GFS day rain of the nightly cycle at 0.25 degree (the 1 degree grid of
ingredients.py has no land cell on the coast at Jeddah or Yanbu) is split into:
  - the coastal strip of each region (region land cells with sea within 0.5 degree to the west), cut into well-known
    stretches from north to south (Makkah: رابغ، ثول وشمال جدة، جدة، الشعيبة، الليث، القنفذة; Madinah: ينبع، الرايس);
  - the rest of each region (inland).
Day k = the 24 hours from the cycle time + 24 k h (the same days as status["ingr"] and status["wave_rain"]).
A stretch is wet when 30 % of its cells (two cells or more on the short ones) get 2 mm or more; the inland part when a tenth does.
"""
import numpy as np

BOX = (18.0, 28.0, 36.0, 43.5)   # lat0, lat1, lon0, lon1
RES = 0.25
WET_MM, COAST_SHARE, INLAND_SHARE = 2.0, 0.3, 0.10
MAKKAH, MADINAH = "مكة المكرمة", "المدينة المنورة"
# (key, name, lat from, lat to), north to south
MK_COAST = [("rabigh", "رابغ", 22.55, 99), ("thuwal", "ثول", 21.65, 22.55), ("jeddah", "جدة", 21.3, 21.65),
            ("shuaibah", "الشعيبة", 20.5, 21.3), ("lith", "الليث", 19.7, 20.5), ("qunf", "القنفذة", 0, 19.7)]
MD_COAST = [("yanbu", "ينبع", 23.85, 99), ("rais", "الرايس", 0, 23.85)]
NORTH, SOUTH = ("rabigh", "thuwal"), ("shuaibah", "lith", "qunf")
_ZONES = None


def _grid():
    la = np.arange(BOX[1], BOX[0] - 1e-6, -RES)
    lo = np.arange(BOX[2], BOX[3] + 1e-6, RES)
    return la, lo


def zones():
    """{key: boolean mask on the box grid}: every coastal stretch and the inland part of the two regions"""
    global _ZONES
    if _ZONES is not None:
        return _ZONES
    import sa_geo
    regs = sa_geo.regions()
    la, lo = _grid()
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    m = sa_geo.region_of_points(regs, LA.ravel(), LO.ravel()).reshape(LA.shape)
    idx = {r["name"]: k for k, r in enumerate(regs)}
    land = m >= 0
    # sea within 0.5 degree to the west (the Red Sea; the cut of the box itself is never the sea)
    sea_w = np.zeros_like(land)
    for s in (1, 2):
        sh = np.ones_like(land)
        sh[:, s:] = ~land[:, :-s]
        sh[:, :s] = False
        sea_w |= sh
    coast = land & sea_w
    out = {}
    for reg, stretches in ((MAKKAH, MK_COAST), (MADINAH, MD_COAST)):
        r = m == idx[reg]
        rc = r & coast
        for key, _n, a, b in stretches:
            out[key] = rc & (LA >= a) & (LA < b)
        out["in_" + ("mk" if reg == MAKKAH else "md")] = r & ~coast
    _ZONES = out
    return out


def cut(a):
    """the box of a global 0.25 degree GFS field (lat 90..-90, lon 0..359.75)"""
    j0, j1 = int(round((90 - BOX[1]) / RES)), int(round((90 - BOX[0]) / RES))
    i0, i1 = int(round(BOX[2] / RES)), int(round(BOX[3] / RES))
    return a[j0:j1 + 1, i0:i1 + 1]


def day_shares(rain):
    """{zone key: share of its cells with WET_MM or more} for one day's rain on the box"""
    return {k: round(float((rain[z] >= WET_MM).mean()), 3) for k, z in zones().items() if z.any()}


def fetch(cycle, days, gfs_fields):
    """[{d, s: day_shares}] for days 0..days-1 of the cycle (GFS 0.25 APCP from the run start)"""
    from datetime import datetime, timedelta
    t0 = datetime.strptime(cycle[:8], "%Y%m%d").date()
    P = [("apcp", r":APCP:surface:0-")]
    prev, rows = None, []
    for k in range(days + 1):
        a = None
        if k:
            for _t in range(3):
                try:
                    a = cut(gfs_fields(cycle, 24 * k, res="0p25", fields=P)["apcp"])
                    break
                except Exception as e:  # noqa: BLE001
                    print("hijaz rain download failed", k, repr(e)[:120], flush=True)
            if a is None:
                break
            day = np.maximum(a - (prev if prev is not None else 0.0), 0)
            rows.append({"d": (t0 + timedelta(days=k - 1)).isoformat(), "s": day_shares(day)})
        else:
            a = None
        prev = a
    return rows


def wet(rows, d0, d1):
    """the zone keys wet on any day from d0 to d1 (ISO dates or dates)"""
    a, b = str(d0), str(d1)
    out = set()
    for r in rows or []:
        if a <= r["d"] <= b:
            for k, v in r["s"].items():
                if v >= (INLAND_SHARE if k.startswith("in_") else COAST_SHARE):
                    out.add(k)
    return out


def _jl(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else "، ".join(xs[:-1]) + " و" + xs[-1]


def _and(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else " و".join(xs)


def mk_coast_words(keys):
    """Makkah coast in Fahad's words: the whole coast, its north part, its south part, or Jeddah"""
    keys = [k for k, *_ in MK_COAST if k in keys]
    if not keys:
        return None
    n = [k for k in keys if k in NORTH]
    s = [k for k in keys if k in SOUTH]
    name = {k: nm for k, nm, *_ in MK_COAST}
    if n and s:
        return "سواحل منطقة مكة المكرمة"
    if n:
        ws = (["جدة"] if "jeddah" in keys else ["شمال جدة"] if "thuwal" in n else []) + [name[k] for k in ("thuwal", "rabigh") if k in n]
        return f"شمال سواحل منطقة مكة المكرمة ({_and(ws)})"
    if s:
        ws = (["جدة"] if "jeddah" in keys else []) + [name[k] for k in SOUTH if k in s]
        return f"جنوب سواحل منطقة مكة المكرمة ({_and(ws)})"
    return "ساحل جدة"


def md_coast_words(keys):
    keys = [k for k, *_ in MD_COAST if k in keys]
    if not keys:
        return None
    if len(keys) == len(MD_COAST):
        return "سواحل منطقة المدينة المنورة (ينبع والرايس)"
    return "ساحل " + {k: nm for k, nm, *_ in MD_COAST}[keys[0]]


def names(keys):
    """the parts to write for the wet zone keys, Makkah first: [«منطقة مكة المكرمة», «شمال سواحل …», …]"""
    out = []
    if "in_mk" in keys:
        out.append("منطقة مكة المكرمة")
    c = mk_coast_words(keys)
    if c:
        out.append(c)
    if "in_md" in keys:
        out.append("منطقة المدينة المنورة")
    c = md_coast_words(keys)
    if c:
        out.append(c)
    return out


def wave_parts(st, d0, d1):
    """the words that replace the «west» box in a wave's regions, from the GFS rain of the wave's days; falls back to
    the two regions by the rain-spread index (st["ingr"]), then to both regions by name"""
    ks = wet(st.get("hijaz_rain"), d0, d1)
    out = names(ks)
    if out:
        return out
    regs = set()
    for r in st.get("ingr") or []:
        if str(d0) <= r["d"] <= str(d1):
            for nm in (MAKKAH, MADINAH):
                if max((r.get("regions") or {}).get(nm, 0), (r.get("gfs_regions") or {}).get(nm, 0)) >= 0.03:
                    regs.add(nm)
    if regs:
        return ["منطقة " + nm for nm in (MAKKAH, MADINAH) if nm in regs]
    return ["منطقتي مكة المكرمة والمدينة المنورة"]
