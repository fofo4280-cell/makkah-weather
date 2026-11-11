"""Northern cold troughs at 500 hPa, tracked day by day for 15 days (GFS), and whether and where they reach the
Kingdom.

A trough is a low of the synoptic wave field (zonal wavenumbers 4-8 of the 500 hPa height, as on the Rossby
wave maps) between 25 and 62 N and 20 W and 80 E, 40 gpm deep or more. Its axis is traced south from the low,
following the lowest height within 8 degrees of longitude, while the wave height stays below -20 gpm. Cold: the
500 hPa temperature wave (same wavenumbers) at the low. Lows on consecutive days are joined into tracks.
"""
import numpy as np

import waves

DEPTH = -40.0
TIP = -20.0


def lon180(x):
    return ((x + 180) % 360) - 180


def place(lat, lon):
    """An Arabic name for where a point lies (Europe, North Africa, the Middle East)."""
    lon = lon180(lon)
    if lat >= 52:
        return "شمال أوروبا وغرب روسيا" if lon < 45 else "روسيا ووسط آسيا"
    if lat >= 44:
        return ("غرب أوروبا" if lon < 8 else "وسط أوروبا" if lon < 22 else "شرق أوروبا وأوكرانيا" if lon < 40
                else "جنوب روسيا وشمال قزوين" if lon < 55 else "كازاخستان")
    if lat >= 36:
        return ("غرب المتوسط" if lon < 10 else "إيطاليا ووسط المتوسط" if lon < 20 else "اليونان والبلقان" if lon < 27
                else "تركيا والبحر الأسود" if lon < 42 else "القوقاز وبحر قزوين" if lon < 54 else "تركمانستان وشمال إيران" if lon < 66
                else "أفغانستان")
    if lat >= 29:
        return ("شمال أفريقيا" if lon < 10 else "ليبيا ووسط المتوسط" if lon < 25 else "مصر وشرق المتوسط" if lon < 33
                else "بلاد الشام والأردن" if lon < 39 else "العراق وشمال المملكة" if lon < 48 else "إيران والخليج العربي" if lon < 60
                else "باكستان")
    if lat >= 20:
        return ("الصحراء الكبرى" if lon < 25 else "مصر والبحر الأحمر" if lon < 36 else "غرب المملكة" if lon < 41
                else "وسط المملكة" if lon < 47 else "شرق المملكة والخليج" if lon < 56 else "عُمان وبحر العرب")
    return "جنوب الجزيرة العربية" if 36 <= lon < 56 else "أفريقيا" if lon < 36 else "بحر العرب"


def kingdom_area(lon):
    lon = lon180(lon)
    return ("شمال غرب المملكة وغربها" if lon < 40 else "شمال المملكة ووسطها" if lon < 47 else "شرق المملكة")


def trace_axis(zp, lat, lon, j0, i0):
    """From the low at (j0, i0) south: [(lat, lon, value)] while the wave height stays below TIP."""
    pts = [(float(lat[j0]), float(lon[i0]), float(zp[j0, i0]))]
    i = i0
    n = len(lon)
    for j in range(j0 + 1, len(lat)):          # lat runs north to south
        if lat[j] < 14:
            break
        cand = [(i + o) % n for o in range(-8, 9)]
        k = min(cand, key=lambda c: zp[j, c])
        if zp[j, k] > TIP:
            break
        i = k
        pts.append((float(lat[j]), float(lon[k]), float(zp[j, k])))
    return pts


def day_troughs(z, t, lat, lon):
    zp, tp = waves.band(z), waves.band(t) if t is not None else None
    out = []
    for kind, la, lo, v in waves.extremes(zp, lat, lon, (25, 62, 0, 360), size=11, minimum=-DEPTH):
        if kind != "L" or not (-20 <= lon180(lo) <= 80):
            continue
        j0 = int(np.argmin(np.abs(lat - la))); i0 = int(np.argmin(np.abs(lon - lo)))
        ax = trace_axis(zp, lat, lon, j0, i0)
        out.append({"lat": la, "lon": lon180(lo), "depth": round(v / 10, 1),
                    "cold": round(float(tp[j0, i0]), 1) if tp is not None else None,
                    "axis": [(a, round(lon180(b), 1), round(c, 0)) for a, b, c in ax[::3]] + [(ax[-1][0], round(lon180(ax[-1][1]), 1), round(ax[-1][2], 0))],
                    "tip": (ax[-1][0], round(lon180(ax[-1][1]), 1))})
    return out


def reaches(tr):
    """Does the trough axis reach the Kingdom: south of 31 N between 36 and 55 E with the wave height still
    30 gpm or more below normal there?"""
    return any(a <= 31 and 36 <= b <= 55 and v <= -30 for a, b, v in tr["axis"])


def track(days):
    """days: [(date, [troughs])] -> tracks: [{"days": [(date, trough)], "arrive": date or None}]."""
    tracks = []
    for d, ts in days:
        used = set()
        for tr in tracks:
            if tr["end"]:
                continue
            last_d, last = tr["days"][-1]
            best, bd = None, 1e9
            for k, t in enumerate(ts):
                if k in used:
                    continue
                dlon, dlat = t["lon"] - last["lon"], t["lat"] - last["lat"]
                if -10 <= dlon <= 25 and abs(dlat) <= 10:
                    dist = abs(dlon - 8) + abs(dlat)
                    if dist < bd:
                        best, bd = k, dist
            if best is None:
                tr["end"] = True
            else:
                used.add(best)
                tr["days"].append((d, ts[best]))
        for k, t in enumerate(ts):
            if k not in used:
                tracks.append({"days": [(d, t)], "end": False})
    out = []
    for tr in tracks:
        arrive = next((d for d, t in tr["days"] if reaches(t)), None)
        deepest = min(t["depth"] for _, t in tr["days"])
        lons = [t["lon"] for _, t in tr["days"]]
        # keep troughs that reach the Kingdom, or deep ones passing between Europe and Iran
        if arrive or (deepest <= -8 and min(lons) <= 60 and max(lons) >= 10):
            out.append({"days": tr["days"], "arrive": arrive, "deepest": deepest})
    out.sort(key=lambda x: (x["arrive"] is None, x["arrive"] or x["days"][0][0]))
    return out


def to_json(tracks):
    return [{"arrive": tr["arrive"].isoformat() if tr["arrive"] else None, "deepest": tr["deepest"],
             "days": [{"d": d.isoformat(), **t} for d, t in tr["days"]]} for tr in tracks]
