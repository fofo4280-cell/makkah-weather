"""The reference wave (Fahad, 25 Nov 2026: «في تقرير الموجة القادمة قارنها بالموجة السابقة من ناحية القوة والانتشار مثل
موجة ١٠ نوفمبر… هذه الموجة اين أقوى مناطق هطولها وكم قوة الهطول مقارنة بالسابقة وكم نسبة انتشارها للمملكة.. دائما في
كل موجة اجعل لك مرجع لموجة سابقة كان هطولها قوي ونسبة انتشارها جيدة»).

One measure for both waves, so the comparison is fair: the GFS daily rain on the 1 degree grid over the Kingdom
(ingredients.BOX), day by day.
  - spread: the share of the Kingdom with 5 mm or more (cos-weighted, as ingredients.spread);
  - intensity: the mean rain over the wet part (>= 5 mm), and the share with 20 mm or more;
  - the strongest areas: the regions where the wet part rains most, with the part of the region (west of Al-Qassim).
The reference is the past day with the best spread x intensity; it starts from 10 Nov 2026 (REF0, worked out from the
GFS 00Z run of that day) and the nightly run replaces it when today's rain (the first 24 hours of its cycle, the same
lead as the reference) beats it. It is carried from night to night in mjo.json ("ref_wave").
"""
import numpy as np

WET, HEAVY = 5.0, 20.0

def _load_ref0():
    import json, os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref_wave.json")
    return json.load(open(p)) if os.path.exists(p) else None


def _part(lat, lon, c_lat, c_lon, span):
    """the part of a region where the rain sits, from the rain's centre against the region's centre"""
    dy, dx = (lat - c_lat) / max(span[0], 0.5), (lon - c_lon) / max(span[1], 0.5)
    if abs(dy) < 0.18 and abs(dx) < 0.18:
        return "وسط"
    if abs(dx) >= 2 * abs(dy):
        return "غرب" if dx < 0 else "شرق"
    if abs(dy) >= 2 * abs(dx):
        return "جنوب" if dy < 0 else "شمال"
    return ("جنوب " if dy < 0 else "شمال ") + ("غرب" if dx < 0 else "شرق")


def day_metrics(rain):
    """metrics of one daily rain field cut to ingredients.BOX (mm) -> dict"""
    import ingredients as ING
    import sa_geo
    m = ING.kingdom_mask()
    regs = sa_geo.regions()
    la, lo = np.meshgrid(ING.LAT, ING.LON, indexing="ij")
    w = np.cos(np.radians(la))
    ksa = m >= 0
    wet = (rain >= WET) & ksa
    out = {"cover": float(w[wet].sum() / w[ksa].sum()),
           "heavy": float(w[(rain >= HEAVY) & ksa].sum() / w[ksa].sum()),
           "mean": float((rain * w)[wet].sum() / w[wet].sum()) if wet.any() else 0.0,
           "max": float(np.nanmax(np.where(ksa, rain, 0))), "regions": []}
    for k in sorted(set(m[ksa].tolist())):
        r = m == k
        rw = r & wet
        if not rw.any():
            continue
        cov = float(w[rw].sum() / w[r].sum())
        mean = float((rain * w)[rw].sum() / w[rw].sum())
        # the part of the region: the rain-weighted centre of its wet cells against the centre of the region
        q = rain[rw] * w[rw]
        c_lat, c_lon = float((la[rw] * q).sum() / q.sum()), float((lo[rw] * q).sum() / q.sum())
        span = (float(la[r].max() - la[r].min()) / 2, float(lo[r].max() - lo[r].min()) / 2)
        part = _part(c_lat, c_lon, float(la[r].mean()), float(lo[r].mean()), span) if r.sum() >= 4 and cov < 0.7 else ""
        out["regions"].append({"name": regs[k]["name"], "cover": round(cov, 3), "mean": round(mean, 1),
                               "max": round(float(rain[rw].max()), 1), "part": part,
                               # the region's rain weight: how much of the Kingdom's wet rain falls in it
                               "w": round(float(q.sum()), 1)})
    out["regions"].sort(key=lambda x: -x["w"])
    for k in ("cover", "heavy"):
        out[k] = round(out[k], 3)
    out["mean"], out["max"] = round(out["mean"], 1), round(out["max"], 1)
    return out


def score(m):
    """spread x intensity, the reference's yardstick"""
    return (m.get("cover") or 0) * (m.get("mean") or 0)


def strongest(m, n=3):
    """the strongest rain areas, as words («غرب القصيم»), strongest first"""
    if m.get("areas"):   # observed areas, written by hand for the seed
        return list(m["areas"])
    rg = [r for r in m.get("regions") or [] if r["mean"] >= 8 or r["cover"] >= 0.15][:n] or (m.get("regions") or [])[:1]
    out = []
    for r in rg:
        nm = r["name"]
        out.append((r["part"] + " " + nm) if r.get("part") and r["part"] != "وسط" else nm)
    return out


def current(prev):
    """the reference carried from the previous night, else the seed of 10 Nov 2026"""
    if prev and prev.get("d") and prev.get("cover") is not None:
        return prev
    return _load_ref0()


def update(prev, d, m):
    """the reference after today's rain m (lead 0-24 h) of day d: today replaces it when it beats it on spread x
    intensity -> (reference, replaced?)"""
    ref = current(prev)
    if m and (ref is None or score(m) > score(ref)) and m["cover"] >= 0.05:
        new = {k: v for k, v in m.items() if k != "areas"}
        new["d"] = d
        return new, True
    return ref, False


def wave_metrics(rows, a, b):
    """the wave a..b from the nightly day rows [{d, ...day_metrics}] -> the widest day's metrics with the wave's
    strongest areas over all its days, or None"""
    ds = [r for r in rows if a.isoformat() <= r["d"] <= b.isoformat()]
    if not ds:
        return None
    pk = max(ds, key=lambda r: (r["cover"], score(r)))   # the strongest day is the widest one (Fahad)
    out = dict(pk)
    # the strongest areas over the whole wave: each region's best day
    best = {}
    for r in ds:
        for g in r.get("regions") or []:
            if g["name"] not in best or g["w"] > best[g["name"]]["w"]:
                best[g["name"]] = g
    out["regions"] = sorted(best.values(), key=lambda g: -g["w"])
    return out
