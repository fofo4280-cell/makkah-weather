"""Our own model runs for the daily report: rain hour by hour over a Makkah day, and what kind of rain it is.

load(dirs, day): every domain with point data (points.bin: hourly rain, strongest radar echo, temperature, gust)
in the published folders, the run that covers most of the day for each.
describe(...): amount, coverage, timing (night, morning, afternoon, evening, or all day), type (steady stratiform
rain, thunderstorms, or both), and the strongest echo for hail.
environment(...): CAPE, 0-6 km shear and freezing level from GFS and ECMWF (Open-Meteo), for the supercell check.
"""
import json, math, os
from datetime import datetime, timedelta, timezone

import numpy as np

import sa_geo as G
from sa_geo import ar, num

BLOCKS = [("night", 1, 6), ("morning", 7, 12), ("afternoon", 13, 18), ("evening", 19, 24)]


# ------------------------------------------------------------------ projection
def _lcc(pr):
    r = math.pi / 180
    p1, p2, p0, l0 = pr["truelat1"] * r, pr["truelat2"] * r, pr["ref_lat"] * r, pr["stand_lon"] * r
    t = lambda p: np.tan(math.pi / 4 + p / 2)
    n = math.log(math.cos(p1) / math.cos(p2)) / math.log(t(p2) / t(p1))
    F = math.cos(p1) * t(p1) ** n / n
    R = pr.get("R", 6370000.0)
    return r, n, F, R, R * F / t(p0) ** n, l0, t


def lcc_forward(pr, lat, lon):
    r, n, F, R, rho0, l0, t = _lcc(pr)
    rho = R * F / t(np.asarray(lat, float) * r) ** n
    th = n * (np.asarray(lon, float) * r - l0)
    return rho * np.sin(th), rho0 - rho * np.cos(th)


def lcc_inverse(pr, x, y):
    r, n, F, R, rho0, l0, t = _lcc(pr)
    rho = np.sign(n) * np.hypot(x, rho0 - y)
    th = np.arctan2(x, rho0 - y)
    return (2 * np.arctan((R * F / rho) ** (1 / n)) - math.pi / 2) / r, (l0 + th / n) / r


# ------------------------------------------------------------------ data
def load(dirs, day=None, log=print, t_a=None, t_b=None):
    """Domains of our runs over the Makkah day (00 to 24), or over [t_a, t_b) (UTC datetimes): for each, the run
    with most hours of the window. Hour keys count the hours from the start of the window: key h is the hour
    ending h hours after it (1 to 24 for a Makkah day: the local hour at its end)."""
    if t_a is None:
        t_a = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(hours=3)
        t_b = t_a + timedelta(hours=24)
    out = []
    for root in [d for d in dirs if d and os.path.exists(os.path.join(d, "runs.json"))]:
        best = {}
        for r in json.load(open(os.path.join(root, "runs.json"))).get("runs", []):
            p = os.path.join(root, "runs", r["run"], "manifest.json")
            if not os.path.exists(p):
                continue
            man = json.load(open(p))
            init = datetime.strptime(man["init"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            for dom, d in (man.get("domains") or {}).items():
                P = d.get("points")
                if not P or not os.path.exists(os.path.join(root, "runs", r["run"], P["file"])):
                    continue
                ks = [(k, int((init + timedelta(hours=h) - t_a).total_seconds() // 3600))
                      for k, h in enumerate(P["hours"]) if k > 0 and t_a < init + timedelta(hours=h) <= t_b]
                if dom not in best or len(ks) > len(best[dom]["ks"]):
                    best[dom] = {"root": root, "run": r["run"], "init": init, "P": P, "ks": ks, "dom": dom,
                                 "proj": d.get("proj") or man["proj"], "name": d.get("name", dom),
                                 "res": d.get("res", ""), "dx": P["dx"]}
        out += [c for c in best.values() if len(c["ks"]) >= 3]
    for c in out:
        P = c["P"]
        raw = np.fromfile(os.path.join(c["root"], "runs", c["run"], P["file"]), np.uint8)
        arr = raw.reshape(len(P["vars"]), len(P["hours"]), P["ny"], P["nx"])
        idx = [k for k, _ in c["ks"]]
        c["keys"] = [h for _, h in c["ks"]]
        c["rain"] = ((arr[P["vars"].index("rain1h"), idx].astype(np.float32) / 25) ** 2).reshape(len(idx), -1)
        c["refl"] = (arr[P["vars"].index("refl"), idx].astype(np.float32) / 3).reshape(len(idx), -1)
        jj, ii = np.mgrid[0:P["ny"], 0:P["nx"]]
        la, lo = lcc_inverse(c["proj"], P["x00"] + ii * P["dx"], P["y00"] + jj * P["dx"])
        c["lat"], c["lon"] = la.ravel(), lo.ravel()
        c["inner"] = ((ii >= 2) & (jj >= 2) & (ii <= P["nx"] - 3) & (jj <= P["ny"] - 3)).ravel()
    log("report: our runs: " + ", ".join(f"{c['run']} {c['dom']} ({c['res']}) {len(c['keys'])} h" for c in out))
    return out


def covers(f, lat, lon):
    x, y = lcc_forward(f["proj"], lat, lon)
    i = np.round((x - f["P"]["x00"]) / f["P"]["dx"]); j = np.round((y - f["P"]["y00"]) / f["P"]["dx"])
    return (i >= 2) & (j >= 2) & (i <= f["P"]["nx"] - 3) & (j <= f["P"]["ny"] - 3)


def composite(doms, max_dx=1e9):
    """One set of cells from the domains that cover the same hours as the longest one: each place from the finest
    domain over it. Returns {lat, lon, w, rain[H,n], refl[H,n], keys, dx[n], used}, or None."""
    doms = [d for d in doms if d["dx"] <= max_dx]
    if not doms:
        return None
    top = max(len(d["keys"]) for d in doms)
    use = [d for d in doms if len(d["keys"]) >= top - 1]
    keys = sorted(set.intersection(*[set(d["keys"]) for d in use]))
    if len(keys) < 6:
        return None
    use.sort(key=lambda d: -d["dx"])
    parts = []
    for k, c in enumerate(use):
        keep = c["inner"].copy()
        for q, f in enumerate(use):
            if q != k and (f["dx"] < c["dx"] or (f["dx"] == c["dx"] and q < k)):
                keep &= ~covers(f, c["lat"], c["lon"])
        sel = [c["keys"].index(h) for h in keys]
        parts.append((c, keep, sel))
    cat = lambda f: np.concatenate([f(c, m, s) for c, m, s in parts], axis=-1)
    return {"lat": cat(lambda c, m, s: c["lat"][m]), "lon": cat(lambda c, m, s: c["lon"][m]),
            "w": cat(lambda c, m, s: np.full(int(m.sum()), float(c["dx"]) ** 2)),
            "dx": cat(lambda c, m, s: np.full(int(m.sum()), float(c["dx"]))),
            "rain": cat(lambda c, m, s: c["rain"][s][:, m]), "refl": cat(lambda c, m, s: c["refl"][s][:, m]),
            "keys": keys, "used": [(c["name"], c["res"], c["run"]) for c, _, _ in parts]}


# ------------------------------------------------------------------ what kind of rain
def describe(cells, m):
    """Rain over the cells picked by mask m: amount, timing, type, strongest echo."""
    rain, refl, w = cells["rain"][:, m], cells["refl"][:, m], cells["w"][m]
    keys = cells["keys"]
    tot = rain.sum(0)
    W = w.sum()
    res = {"mean": float((tot * w).sum() / W), "cov": float((w * (tot >= 1)).sum() / W), "max": float(tot.max()),
           "jmax": int(np.argmax(tot)), "n": int(m.sum())}
    if res["max"] < 1 and res["cov"] < 0.01:
        res["wet"] = False
        return res
    res["wet"] = True
    hourly = (rain * w).sum(1) / W
    s = hourly.sum()
    share = {}
    for name, a, b in BLOCKS:
        share[name] = float(sum(v for v, h in zip(hourly, keys) if a <= h <= b) / s) if s > 0 else 0.0
    res["share"] = share
    res["peak_h"] = int(keys[int(np.argmax(hourly))])
    res["hours"] = (keys[0] - 1, keys[-1])
    # type: share of the rain that falls at 5 mm/h or more (3 at 9 km, where the grid smooths the cells out),
    # and how long the wet places stay wet
    dxm = float(np.median(cells["dx"][m]))
    heavy = 5.0 if dxm <= 3000 else 3.0
    wet_cells = tot >= 1
    res["conv"] = float((rain[:, wet_cells] * (rain[:, wet_cells] >= heavy)).sum() / max(rain[:, wet_cells].sum(), 1e-6))
    res["dur"] = float(np.mean((rain[:, wet_cells] >= 0.2).sum(0))) if wet_cells.any() else 0.0
    k = np.unravel_index(int(np.argmax(refl)), refl.shape)
    res["zmax"], res["zh"], res["zj"] = float(refl[k]), int(keys[k[0]]), int(k[1])
    res["dx"] = dxm
    res["conv_hours"] = [h for h, z in zip(keys, refl.max(1)) if z >= 40]
    return res


def timing_word(d):
    sh = d["share"]
    n, mo, af, ev = sh["night"], sh["morning"], sh["afternoon"], sh["evening"]
    top = max(sh, key=sh.get)
    if sh[top] >= 0.6:
        return {"night": "ليلي حتى الفجر", "morning": "صباحي", "afternoon": "نهاري بعد الظهر والعصر",
                "evening": "مسائي"}[top]
    if af + ev >= 0.75:
        return "يبدأ بعد الظهر ويمتد إلى المساء"
    if ev + n >= 0.75:
        return "مسائي وليلي"
    if mo + af >= 0.75:
        return "نهاري"
    if n + mo >= 0.75:
        return "ليلي وصباحي"
    if sum(v >= 0.15 for v in sh.values()) >= 3:
        return "ممتد على مدار اليوم"
    return "متقطع على فترات من اليوم"


def type_word(d):
    if d["conv"] >= 0.6 or (d["zmax"] >= 45 and d["conv"] >= 0.4):
        return "رعدي"
    if d["conv"] < 0.25 and d["dur"] >= 4 and d["zmax"] < 45:
        return "ديمة (أمطار هادئة متواصلة)"
    return "ديمة تتخللها خلايا رعدية"


def hail_level(d, fzl=None):
    """0 none, 1 possible, 2 likely: an echo of 55 dBZ or more with the freezing level at 4200 m or lower is
    likely hail; 50 dBZ, or 55 with a higher freezing level, is possible hail; a freezing level of 4800 m or more
    melts most of it (unless the echo reaches 58)."""
    z = d.get("zmax", 0)
    f = fzl if fzl is not None and np.isfinite(fzl) else None
    if z >= 55 and (f is None or f <= 4200):
        return 2
    if z >= 50 and not (f is not None and f >= 4800 and z < 58):
        return 1
    return 0


# ------------------------------------------------------------------ the environment of the storms
ENV = ["cape", "wind_speed_10m", "wind_direction_10m", "wind_speed_500hPa", "wind_direction_500hPa",
       "freezing_level_height"]


def environment(om, lat, lon, day):
    """Hourly CAPE (J/kg), 0-6 km shear (10 m to 500 hPa, m/s) and freezing level (m) for the Makkah day:
    medians of GFS and ECMWF, arrays [24, n] (index = local hour)."""
    mods = ["gfs_seamless", "ecmwf_ifs025"]
    js = om.get(G.FORECAST, {"hourly": ",".join(ENV), "models": ",".join(mods), "timezone": "Asia/Riyadh",
                             "wind_speed_unit": "ms", "start_date": day.isoformat(), "end_date": day.isoformat()},
                lat, lon, weight=len(ENV) * len(mods) / 10)
    get = lambda j, v, m: np.array([np.nan if x is None else x for x in ((j.get("hourly") or {}).get(f"{v}_{m}") or [None] * 24)][:24], float)
    out = {k: np.full((24, len(js)), np.nan) for k in ("cape", "shear", "fzl")}
    for i, j in enumerate(js):
        cape, shear, fzl = [], [], []
        for m in mods:
            s10, d10, s5, d5 = (get(j, v, m) for v in ENV[1:5])
            u10, v10 = -s10 * np.sin(np.radians(d10)), -s10 * np.cos(np.radians(d10))
            u5, v5 = -s5 * np.sin(np.radians(d5)), -s5 * np.cos(np.radians(d5))
            cape.append(get(j, "cape", m)); shear.append(np.hypot(u5 - u10, v5 - v10)); fzl.append(get(j, "freezing_level_height", m))
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out["cape"][:, i] = np.nanmedian(cape, 0)
                out["shear"][:, i] = np.nanmedian(shear, 0)
                out["fzl"][:, i] = np.nanmedian(fzl, 0)
    return out


def supercell_level(env, pts, hours):
    """0 none, 1 low, 2 moderate: CAPE and deep shear together at the given points in the hours with storms."""
    if env is None or not hours or not np.any(pts):
        return 0, None
    rows = [min(h, 23) for h in hours]        # local hour ending h -> the hourly value at that time
    cape, shear = env["cape"][np.ix_(rows, np.flatnonzero(pts))], env["shear"][np.ix_(rows, np.flatnonzero(pts))]
    good = np.nansum((cape >= 1000) & (shear >= 18))
    weak = np.nansum((cape >= 500) & (shear >= 15))
    best = (float(np.nanmax(cape)) if np.isfinite(cape).any() else None,
            float(np.nanmax(np.where(cape >= 500, shear, np.nan))) if np.isfinite(np.where(cape >= 500, shear, np.nan)).any() else None)
    return (2 if good >= 2 else 1 if weak >= 2 else 0), best


def fzl_at(env, pts, hours):
    if env is None or not hours or not np.any(pts):
        return None
    v = env["fzl"][np.ix_([min(h, 23) for h in hours], np.flatnonzero(pts))]
    return float(np.nanmedian(v)) if np.isfinite(v).any() else None


# ------------------------------------------------------------------ text
def area_text(name, d, place, hail, sc, sc_vals):
    """One description: '(amount, timing, type, hail, supercell)'."""
    if not d["wet"]:
        return f"{name}: لا أمطار تُذكر"
    t = (f"{name}: {num(d['mean'], 1)} ملم في المتوسط وتصل إلى {num(d['max'])} ملم{(' قرب ' + place) if place else ''}، "
         f"تغطي نحو {num(100 * d['cov'])}٪؛ {timing_word(d)} (ذروته الساعة {ar(d['peak_h'])})، طابعه {type_word(d)}")
    if hail == 2:
        t += f"، وفرص البَرَد جيدة (صدى رادار {num(d['zmax'])} ديسيبل الساعة {ar(d['zh'])})"
    elif hail == 1:
        t += "، وفرص البَرَد واردة"
    if sc == 2:
        t += "، وفرص متوسطة لخلايا عملاقة (سوبر سل)"
    elif sc == 1:
        t += "، وفرص ضعيفة لخلايا عملاقة (سوبر سل)"
    return t


def aloft(cells, m, dbz=15.0):
    """How many places-and-hours of the area have a rain echo aloft (15 dBZ or more) but under 0.1 mm at the
    ground: rain the model makes in the cloud and evaporates on the way down. When the real low levels are moister
    than the model's, that rain reaches the ground, mostly as steady light rain (Al-Jumum, 10 November 2026: an
    echo of 18 dBZ east of Makkah in our 3 km run, no rain at the ground, two hours of steady rain in reality)."""
    rf, rn = cells["refl"][:, m], cells["rain"][:, m]
    return int(((rf >= dbz) & (rn < 0.1)).sum())
