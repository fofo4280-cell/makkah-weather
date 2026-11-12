"""The rain report: rain over the Kingdom from our own model only, written twice a day (about midnight from the
12 UTC runs, about noon from the 00 UTC runs).

rain_report(t_a, t_b, dirs, st, om) -> {"heading", "lines", "table", "data"}

For each region: when it rains (windows of hours), where (cities and governorates, heavy / moderate / light),
what kind of rain (thunderstorms or steady rain), hail and supercell chances. The Kingdom summary comes first.
Rain, its timing and its type come from our runs only (the 3 km grids, the 9 km Kingdom grid where they do
not reach); the storm environment for hail and supercells (CAPE, deep shear, freezing level) from GFS and ECMWF.
"""
import math, re
from datetime import timedelta

import numpy as np

import sa_geo as G
import ourmodel as O
from sa_geo import ar, num, join, AR_DAYS

HEAVY, MODERATE, LIGHT = 20.0, 5.0, 0.5        # mm in the window at a place
TOWN_KM = 7.0                                   # a place gets the most rain within this distance


# ------------------------------------------------------------------ time words
def local(t):
    return t + timedelta(hours=3)


def clock(t):
    """'٣ ص', '٩ م', 'منتصف الليل', '١٢ ظهرًا' (Makkah time)."""
    h = local(t).hour
    if h == 0:
        return "منتصف الليل"
    if h == 12:
        return "١٢ ظهرًا"
    return f"{ar(h % 12)} {'ص' if h < 12 else 'م'}"


def span_words(a, b):
    """Window from a to b (UTC datetimes): 'من ٣ ص إلى ٨ ص', or 'طوال اليوم'."""
    if (b - a) >= timedelta(hours=22) and local(a).hour == 0:
        return "طوال اليوم"
    return f"من {clock(a)} إلى {clock(b)}"


def day_word(a, b):
    da, db = local(a).date(), local(b - timedelta(minutes=1)).date()
    return AR_DAYS[da.weekday()] if da == db else f"{AR_DAYS[da.weekday()]}–{AR_DAYS[db.weekday()]}"


def part_of_day(a, b):
    mid = local(a + (b - a) / 2).hour
    return ("الفجر" if 3 <= mid < 6 else "الصباح" if 6 <= mid < 11 else "الظهيرة" if 11 <= mid < 14 else
            "العصر" if 14 <= mid < 17 else "المساء" if 17 <= mid < 21 else "الليل")


# ------------------------------------------------------------------ the storm environment over the window
def environment(om, lat, lon, t_a, n):
    """CAPE, 0-6 km shear and freezing level (medians of GFS and ECMWF), arrays [n, points], row k = the value at
    t_a + k + 1 hours (the end of hour key k + 1)."""
    la, lb = local(t_a).date(), local(t_a + timedelta(hours=n)).date()
    mods = ["gfs_seamless", "ecmwf_ifs025"]
    js = om.get(G.FORECAST, {"hourly": ",".join(O.ENV), "models": ",".join(mods), "timezone": "Asia/Riyadh",
                             "wind_speed_unit": "ms", "start_date": la.isoformat(), "end_date": lb.isoformat()},
                lat, lon, weight=len(O.ENV) * len(mods) / 10 * max(1, (lb - la).days + 1) / 1)
    off = local(t_a).hour + 1
    out = {k: np.full((n, len(js)), np.nan) for k in ("cape", "shear", "fzl")}
    import warnings
    for i, j in enumerate(js):
        h = j.get("hourly") or {}
        get = lambda v, m: np.array([np.nan if x is None else x for x in (h.get(f"{v}_{m}") or [])], float)
        cape, shear, fzl = [], [], []
        for m in mods:
            s10, d10, s5, d5 = (get(v, m) for v in O.ENV[1:5])
            if s10.size == 0:
                continue
            u10, v10 = -s10 * np.sin(np.radians(d10)), -s10 * np.cos(np.radians(d10))
            u5, v5 = -s5 * np.sin(np.radians(d5)), -s5 * np.cos(np.radians(d5))
            cape.append(get("cape", m)); shear.append(np.hypot(u5 - u10, v5 - v10)); fzl.append(get("freezing_level_height", m))
        if not cape:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for k, a in (("cape", cape), ("shear", shear), ("fzl", fzl)):
                v = np.nanmedian(np.array([x[:max(len(y) for y in a)] for x in a], float), 0)
                seg = v[off:off + n]
                out[k][:len(seg), i] = seg
    return out


def storm_levels(env, pts, keys, d):
    """Hail (0, 1 possible, 2 good chances) and supercell (0, 1 low, 2 moderate) for an area's rain."""
    if env is None or not np.any(pts):
        return O.hail_level(d), 0, None
    rows = [k - 1 for k in d.get("conv_keys", []) if 0 <= k - 1 < env["cape"].shape[0]]
    fzl = None
    if rows:
        v = env["fzl"][np.ix_(rows, np.flatnonzero(pts))]
        fzl = float(np.nanmedian(v)) if np.isfinite(v).any() else None
    hail = O.hail_level(d, fzl)
    if not rows:
        return hail, 0, None
    cape = env["cape"][np.ix_(rows, np.flatnonzero(pts))]
    shear = env["shear"][np.ix_(rows, np.flatnonzero(pts))]
    good = np.nansum((cape >= 1000) & (shear >= 18)); weak = np.nansum((cape >= 500) & (shear >= 15))
    best = (float(np.nanmax(cape)) if np.isfinite(cape).any() else None,
            float(np.nanmax(np.where(cape >= 500, shear, np.nan))) if np.isfinite(np.where(cape >= 500, shear, np.nan)).any() else None)
    return hail, (2 if good >= 2 else 1 if weak >= 2 else 0), best


# ------------------------------------------------------------------ the rain itself
def windows(hourly_cov, hourly_max, keys, min_gap=1):
    """Runs of hours with rain over the region (1% of it at 0.5 mm/h or more, or 5 mm/h somewhere), with gaps of
    up to min_gap dry hours bridged. Returns [(first index, last index)]."""
    act = [(c >= 0.01 or m >= 5.0) for c, m in zip(hourly_cov, hourly_max)]
    out, a, last = [], None, None
    for i, on in enumerate(act):
        if on:
            if a is None:
                a = i
            elif i - last > min_gap + 1:
                out.append((a, last)); a = i
            last = i
    if a is not None:
        out.append((a, last))
    return out


def town_rain(cells, m, idx, towns):
    """Rain at each town over the hours idx: the most within TOWN_KM of it (cells of mask m)."""
    la, lo = cells["lat"][m], cells["lon"][m]
    tot = cells["rain"][idx][:, m].sum(0)
    peak = cells["rain"][idx][:, m].max(0)
    out = {}
    for t in towns:
        tl, to = G.PLACE[t]
        d = 111.2 * np.hypot(la - tl, (lo - to) * math.cos(math.radians(tl)))
        near = d <= TOWN_KM
        if not near.any():
            near = d <= d.min() + 1e-6
        out[t] = (float(tot[near].max()), float(peak[near].max()))
    return out


def window_type(cells, m, idx):
    rain, refl = cells["rain"][idx][:, m], cells["refl"][idx][:, m]
    dx = float(np.median(cells["dx"][m]))
    heavy = 5.0 if dx <= 3000 else 3.0
    wet = rain.sum(0) >= 1
    conv = float((rain[:, wet] * (rain[:, wet] >= heavy)).sum() / max(rain[:, wet].sum(), 1e-6)) if wet.any() else 0.0
    dur = float(np.mean((rain[:, wet] >= 0.2).sum(0))) if wet.any() else 0.0
    k = np.unravel_index(int(np.argmax(refl)), refl.shape) if refl.size else (0, 0)
    zmax = float(refl[k]) if refl.size else 0.0
    return {"conv": conv, "dur": dur, "zmax": zmax, "zk": int(idx[k[0]]) if refl.size else 0, "dx": dx,
            "conv_keys": [cells["keys"][i] for i in idx if refl[list(idx).index(i)].max() >= 40] if refl.size else []}


def type_word(t):
    if t["conv"] >= 0.6 or (t["zmax"] >= 45 and t["conv"] >= 0.4):
        return "رعدية"
    if t["conv"] < 0.25 and t["dur"] >= 3 and t["zmax"] < 45:
        return "ديمة هادئة متواصلة"
    return "ديمة تتخللها خلايا رعدية"


def amount_word(x):
    return ("غزيرة جدًا" if x >= 50 else "غزيرة" if x >= HEAVY else "متوسطة" if x >= MODERATE else "خفيفة")


# ------------------------------------------------------------------ the report
def rain_report(t_a, t_b, dirs, st=None, om=None, log=print, issue="midnight"):
    om = om or G.OpenMeteo()
    regs = G.tag_towns(G.regions())
    doms = O.load(dirs, log=log, t_a=t_a, t_b=t_b)
    # the 9 km grid is the Kingdom run's alone (the 9 km parents of the 3 km runs are not used)
    doms = [d for d in doms if d["dx"] < 9000 or d["name"] == "السعودية"]
    cells = O.composite(doms)
    head = (("تحديث الظهر: " if issue == "noon" else "") + f"الأمطار على المملكة من {ar(local(t_a).day)} {G.AR_MONTHS[local(t_a).month - 1]} الساعة {clock(t_a)}"
            f" إلى {ar(local(t_b).day)} {G.AR_MONTHS[local(t_b).month - 1]} الساعة {clock(t_b)}")
    if cells is None:
        return {"heading": head, "lines": ["لم يكتمل تشغيل نموذجنا الذي يغطي هذه المدة عند كتابة التقرير."], "table": [], "data": {}}
    keys = cells["keys"]
    tk = lambda i: t_a + timedelta(hours=keys[i])          # end of hour index i
    kri = G.region_of_points(regs, cells["lat"], cells["lon"])
    env = None
    try:
        glat, glon, gri, _ = G.grid_points(regs, 0.5)
        env = O.ENV and environment(om, glat, glon, t_a, len(keys) + keys[0] - 1)
    except Exception as e:
        log(f"rain report: storm environment unavailable: {e!r}")
        glat = glon = gri = None
    res_used = sorted({r for _, r, _ in cells["used"]})
    rows, table = [], []
    for k, r in enumerate(regs):
        m = kri == k
        if not m.any():
            continue
        w = cells["w"][m]
        rain = cells["rain"][:, m]
        cov = ((rain >= 0.5) * w).sum(1) / w.sum()
        mx = rain.max(1)
        tot = rain.sum(0)
        area = float((tot * w).sum() / w.sum())
        wins = [(a, b) for a, b in windows(cov, mx, keys) if rain[a:b + 1].sum(0).max() >= 2.0]
        if not wins:
            continue
        towns = sorted(r["_towns"])
        reg = {"k": k, "name": r["name"], "mean": area, "max": float(tot.max()), "wins": []}
        j = int(np.argmax(tot))
        reg["at"] = G.describe(float(cells["lat"][m][j]), float(cells["lon"][m][j]), r)   # where the most falls, exactly
        for a, b in wins:
            idx = np.arange(a, b + 1)
            tr = town_rain(cells, m, idx, towns)
            heavy = sorted([t for t, (v, p) in tr.items() if v >= HEAVY or p >= 10], key=lambda t: -tr[t][0])
            mod = sorted([t for t, (v, p) in tr.items() if MODERATE <= v < HEAVY and p < 10], key=lambda t: -tr[t][0])
            light = sorted([t for t, (v, p) in tr.items() if LIGHT <= v < MODERATE], key=lambda t: -tr[t][0])
            ty = window_type(cells, m, idx)
            pts = (gri == k) if gri is not None else None
            hail, sc, scv = storm_levels(env, pts, keys, ty) if pts is not None else (O.hail_level(ty), 0, None)
            wmax = float(rain[idx].sum(0).max())
            wj = int(np.argmax(rain[idx].sum(0)))
            win = {"a": tk(a) - timedelta(hours=1), "b": tk(b), "heavy": heavy, "moderate": mod, "light": light,
                   "type": type_word(ty), "hail": hail, "sc": sc, "scv": scv, "max": wmax, "z": ty["zmax"],
                   "loc": G.locate(float(cells["lat"][m][wj]), float(cells["lon"][m][wj]), r),
                   "peak": tk(a + int(np.argmax((rain[idx] * w).sum(1))))}
            win["at"] = win["loc"]["text"]
            # the place of the most rain goes first in its class (a known place, not only the towns of the list)
            sh = win["loc"]["short"]
            if sh and sh not in heavy + mod + light:
                (heavy if wmax >= HEAVY else mod if wmax >= MODERATE else light).insert(0, sh)
            reg["wins"].append(win)
            table.append({"region": r["name"], "day": day_word(win["a"], win["b"]),
                          "window": span_words(win["a"], win["b"]),
                          "heavy": heavy, "moderate": mod, "light": light})
        rows.append(reg)
    rows.sort(key=lambda x: -x["mean"])
    order = {x["name"]: i for i, x in enumerate(rows)}
    table.sort(key=lambda t: order[t["region"]])

    # ---- summary
    lines = []
    if not rows:
        lines.append(f"لا يُظهر نموذجنا أمطارًا تُذكر على مناطق المملكة {span_words(t_a, t_b)}.")
        return {"heading": head, "lines": lines, "table": [], "data": {}}
    n = len(rows)
    extent = "واسعة" if n >= 8 else "متوسطة الانتشار" if n >= 4 else "محدودة"
    count = "منطقة واحدة" if n == 1 else "منطقتين" if n == 2 else f"{ar(n)} {'مناطق' if n <= 10 else 'منطقة'}"
    a0 = min(w["a"] for x in rows for w in x["wins"]); b0 = max(w["b"] for x in rows for w in x["wins"])
    top = [x for x in rows if x["max"] >= HEAVY][:3] or rows[:2]
    types = [w["type"] for x in rows for w in x["wins"]]
    main_type = max(set(types), key=types.count)
    hail_regs = [x["name"] for x in rows if any(w["hail"] for w in x["wins"])]
    hail_good = [x["name"] for x in rows if any(w["hail"] == 2 for w in x["wins"])]
    sc_regs = [x["name"] for x in rows if any(w["sc"] for w in x["wins"])]
    sc_mod = [x["name"] for x in rows if any(w["sc"] == 2 for w in x["wins"])]
    when = span_words(a0, b0)
    when = "على مدى اليوم" if when == "طوال اليوم" else f"{when.replace('من ', 'تبدأ من الساعة ').replace(' إلى ', ' وتمتد إلى ')}"
    s = (f"تشهد المملكة حالة مطرية {extent} تشمل {count} من مناطقها الثلاث عشرة، {when}. ")
    tops = []
    for x in top:
        best = max(x["wins"], key=lambda w: w["max"])
        # the most rain is named where it falls (not at the first heavy town, which can be elsewhere in the region)
        tops.append(f"{x['name']} (أعلاها {num(x['max'])} ملم {x['at']} {part_of_day(best['a'], best['b'])})")
    s += f"وتتركز الأمطار الأغزر على {join(tops)}. "
    mids = [x["name"] for x in rows if x not in top and x["max"] >= MODERATE]
    lows = [x["name"] for x in rows if x["max"] < MODERATE]
    if mids:
        s += f"وتمتد الأمطار المتوسطة إلى {join(mids)}"
        s += f"، وتبقى خفيفة على {join(lows)}. " if lows else ". "
    elif lows:
        s += f"وتبقى خفيفة على {join(lows)}. "
    s += f"وطابع الحالة الغالب أمطار {main_type}"
    if hail_regs:
        s += (f"، مع فرص جيدة لتساقط البَرَد على {join(hail_good)}" if hail_good else "") + \
             (f"{'، وفرص واردة على ' if hail_good else '، مع فرص واردة لتساقط البَرَد على '}{join([h for h in hail_regs if h not in hail_good])}"
              if [h for h in hail_regs if h not in hail_good] else "")
    if sc_regs:
        s += (f"، واحتمال {'متوسط' if sc_mod else 'ضعيف'} لتشكل خلايا عملاقة (سوبر سل) على {join(sc_mod or sc_regs)}")
    lines.append(s.strip().rstrip("،") + ".")
    if st is not None:
        try:
            import today as T
            bp = T.big_picture(st, local(t_a).date(), [{"name": x["name"]} for x in rows])
            lines.append(bp)
        except Exception as e:
            log(f"rain report: large-scale line failed: {e!r}")

    # ---- region by region
    for x in rows:
        parts = []
        for w in x["wins"]:
            t = f"{day_word(w['a'], w['b'])} {span_words(w['a'], w['b'])}: أمطار {w['type']}"
            if w["heavy"]:
                t += f"، غزيرة على {join(w['heavy'][:6])}"
            if w["moderate"]:
                t += f"، ومتوسطة على {join(w['moderate'][:6])}"
            if w["light"] and len(w["heavy"]) + len(w["moderate"]) < 6:
                t += f"، وخفيفة على {join(w['light'][:5])}"
            t += f"؛ أعلاها {num(w['max'])} ملم {w['at']}"
            if w["hail"] == 2:
                t += f"، وفرص جيدة للبَرَد (صدى رادار {num(w['z'])} ديسيبل)"
            elif w["hail"] == 1:
                t += "، وفرص واردة للبَرَد"
            if w["sc"] == 2:
                t += "، واحتمال متوسط لخلايا عملاقة (سوبر سل)"
            elif w["sc"] == 1:
                t += "، واحتمال ضعيف لخلايا عملاقة (سوبر سل)"
            parts.append(t)
        lines.append(f"منطقة {x['name']} ({amount_word(x['max'])}): " + "؛ ثم ".join(parts) + ".")
    dry = [r["name"] for r in regs if r["name"] not in order]
    if dry:
        lines.append(f"ولا أمطار تُذكر على {join(dry)}.")
    lines.append("المصدر: نموذجنا وحده (" + "، و".join(f"{n_} بدقة {r_}" for n_, r_, _ in cells["used"])
                 + f")، الساعات {span_words(t_a, t_b)} بتوقيت مكة؛ والفئات للمدن والمحافظات: غزير ٢٠ ملم فأكثر "
                 "أو ١٠ ملم في ساعة، متوسط ٥ إلى ٢٠، خفيف دون ٥. وفرص البَرَد والخلايا العملاقة من صدى الرادار في نموذجنا "
                 "مع طاقة الحمل وقص الرياح ومستوى التجمد.")
    data = {"t_a": t_a.isoformat(), "t_b": t_b.isoformat(), "issue": issue, "res": res_used,
            "regions": [{"name": x["name"], "mean": round(x["mean"], 2), "max": round(x["max"], 1)} for x in rows]}
    return {"heading": head, "lines": lines, "table": table, "data": data}
