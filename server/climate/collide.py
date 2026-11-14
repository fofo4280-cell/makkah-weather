"""Where the winds meet over the Kingdom in the afternoon of the report day: the zones where new storms start.

From the GFS forecast at 0.25 degrees, hourly from 11:00 to 17:00 Makkah time (08 to 14 UTC):
  - the convergence of the 850 hPa wind, or of the 10 m wind where the ground stands higher than 870 hPa
    (the Sarawat, Asir and Taif highlands), smoothed over about 40 km and averaged over the seven hours;
  - kept where it reaches 2 x 10^-5 /s and the precipitable water is 20 mm or more (a meeting in dry air
    makes no cloud).
Tested on the 24 days of wide rain in the past year (Dec 2025 to Nov 2026), against the GFS rain of 09:00 to
21:00 Makkah time: 68 % of the zone points had 2 mm or more within 50 km, against 26 % of the Kingdom as a whole
(2.6 times), and about half of the wet area lay within 50 km of a zone. The 925 hPa level (below the ground
over much of the west) and the 10 m wind alone did worse (1.7 and 2.2 times). A wide area is split into its cores
(at 1.5, then 2.25 times the threshold); of the zones the report names (up to four a day, 3.8 on average) 62 %
had that rain within 50 km of their strongest point, the first-named 67 %.

zones(hours, lat, lon, regs) -> [{lat, lon, region, place, km, a, b, winds, oro, peak_h, c, pw}], strongest first.
hours: [(utc datetime, {u10, v10, u850, v850, pw, ps, hgt})] on lat (decreasing) x lon.
"""
import math

import numpy as np

FIELDS = [("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
          ("u850", r":UGRD:850 mb:"), ("v850", r":VGRD:850 mb:"),
          ("pw", r":PWAT:entire atmosphere \(considered as a single layer\):"), ("ps", r":PRES:surface:")]
HGT = [("hgt", r":HGT:surface:")]
BOX = (12.0, 34.0, 32.0, 58.0)          # south, north, west, east
UTC_HOURS = range(8, 15)                 # 11:00 to 17:00 Makkah
THR, PW_MIN, PS_HIGH = 2.0, 20.0, 87000.0
SMOOTH = 1.5                             # grid lengths (0.25 deg): about 40 km
DIRS_FROM = ["شمالية", "شمالية شرقية", "شرقية", "جنوبية شرقية", "جنوبية", "جنوبية غربية", "غربية", "شمالية غربية"]


def cut(a, lat, lon):
    s, n, w, e = BOX
    j = (lat >= s) & (lat <= n)
    i = (lon >= w) & (lon <= e)
    return a[np.ix_(j, i)], lat[j], lon[i]


def convergence(u, v, lat, dlon):
    """-div(u, v) in 10^-5 /s on a lat (decreasing) x lon grid of step dlon degrees"""
    from scipy.ndimage import gaussian_filter
    a = 6.371e6
    phi = np.radians(lat)[:, None]
    d = np.radians(dlon)
    u, v = gaussian_filter(u, SMOOTH), gaussian_filter(v, SMOOTH)
    dudx = np.gradient(u, d, axis=1) / (a * np.cos(phi))
    dvdy = np.gradient(v * np.cos(phi), -d, axis=0) / (a * np.cos(phi))
    return -(dudx + dvdy) * 1e5


def low_wind(f):
    """the wind of the zone: 850 hPa, or 10 m where the ground stands above 870 hPa"""
    hi = f["ps"] < PS_HIGH
    return np.where(hi, f["u10"], f["u850"]), np.where(hi, f["v10"], f["v850"])


def from_dir(u, v):
    return DIRS_FROM[int(((math.degrees(math.atan2(-u, -v)) % 360) + 22.5) // 45) % 8]


def zones(hours, lat, lon, regs, max_n=4):
    import sa_geo as G
    from scipy.ndimage import label, binary_dilation
    if len(hours) < 4:
        return []
    dl = abs(float(lon[1] - lon[0]))
    cs, us, vs, pws = [], [], [], []
    for _, f in hours:
        u, v = low_wind(f)
        cs.append(convergence(u, v, lat, dl)); us.append(u); vs.append(v); pws.append(f["pw"])
    C, U, V, PW = np.mean(cs, 0), np.mean(us, 0), np.mean(vs, 0), np.mean(pws, 0)
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    rix = G.region_of_points(regs, LA.ravel(), LO.ravel()).reshape(LA.shape)
    z = (C >= THR) & (PW >= PW_MIN) & (rix >= 0)
    hgt = hours[0][1].get("hgt")
    # the pieces: a wide area of convergence (over about 8000 km2) is split into its cores at a higher threshold
    pieces = []
    def split(mask, thr):
        lab, n = label(mask, structure=np.ones((3, 3)))
        for b in range(1, n + 1):
            m = lab == b
            if m.sum() < 4:                   # under about 2500 km2: noise at this grid
                continue
            if m.sum() > 12 and thr < 4 * THR and (m & (C >= thr * 1.5)).sum() >= 4:
                split(m & (C >= thr * 1.5), thr * 1.5)
            else:
                pieces.append(m)
    split(z, THR)
    out = []
    for m in pieces:
        k = np.argmax(np.where(m, C, -np.inf))
        jj, ii = np.unravel_index(k, C.shape)
        # which winds meet: the mean wind on each side of the zone, across its long axis
        y, x = np.nonzero(m)
        cov = np.cov(np.vstack([x, y])) if m.sum() > 2 else np.eye(2)
        ax = np.linalg.eigh(cov)[1][:, 1]
        ring = binary_dilation(m, iterations=3) & ~m
        Y, X = np.mgrid[0:C.shape[0], 0:C.shape[1]]
        side = ((X - x.mean()) * -ax[1] + (Y - y.mean()) * ax[0]) > 0
        winds = []
        for part in (ring & side, ring & ~side):
            if part.sum() >= 3:
                pu, pv = float(U[part].mean()), float(V[part].mean())
                if math.hypot(pu, pv) >= 1.0:
                    winds.append(from_dir(pu, pv))
        winds = list(dict.fromkeys(winds))   # one name: the same wind slows down and piles up (speed convergence)
        # lifted by the slope: the wind blowing up the ground (m/s of rise)
        oro = False
        if hgt is not None:
            a = 6.371e6
            hy = np.gradient(hgt, -np.radians(dl), axis=0) / a
            hx = np.gradient(hgt, np.radians(dl), axis=1) / (a * np.cos(np.radians(lat))[:, None])
            up = float(np.mean((U * hx + V * hy)[m]))
            oro = up >= 0.05
        # the hour of the strongest meeting at the peak point
        ph = max(range(len(hours)), key=lambda q: cs[q][jj, ii])
        cnt = np.bincount(rix[m][rix[m] >= 0])
        rs = [regs[int(q)]["name"] for q in np.argsort(-cnt) if cnt[q] >= max(2, 0.2 * m.sum())][:3]
        place, km = G.nearest_place(float(lat[jj]), float(lon[ii]))
        # the two ends of a long zone (over 150 km), named by their nearest towns
        a_, b_ = None, None
        s = (x - x.mean()) * ax[0] + (y - y.mean()) * ax[1]
        if (s.max() - s.min()) * dl * 111 >= 150:
            p0, p1 = int(np.argmin(s)), int(np.argmax(s))
            a_ = G.nearest_place(float(lat[y[p0]]), float(lon[x[p0]]))[0]
            b_ = G.nearest_place(float(lat[y[p1]]), float(lon[x[p1]]))[0]
            if a_ == b_:
                a_ = b_ = None
        out.append({"lat": round(float(lat[jj]), 2), "lon": round(float(lon[ii]), 2), "region": rs[0] if rs else "",
                    "regions": rs, "dir": G.direction(G.PLACE[place][0], G.PLACE[place][1], float(lat[jj]), float(lon[ii])),
                    "place": place, "km": round(km), "a": a_, "b": b_, "winds": winds, "oro": oro,
                    "peak_h": hours[ph][0].strftime("%Y-%m-%dT%H:%MZ"), "c": round(float(C[jj, ii]), 1),
                    "pw": round(float(PW[jj, ii])), "cells": int(m.sum())})
    out.sort(key=lambda r: -(r["c"] * min(r["cells"], 40)))
    return out[:max_n]


def mk_hour(iso):
    from datetime import datetime, timedelta
    h = (datetime.strptime(iso, "%Y-%m-%dT%H:%MZ") + timedelta(hours=3)).hour
    return h


def hour_words(h):
    from sa_geo import ar
    return "الظهر" if h == 12 else f"{ar(h if h <= 12 else h - 12)} {'ص' if h < 12 else 'م'}"


def zone_text(z):
    """one zone in words, e.g. 'قرب الطائف (مكة المكرمة): رياح غربية تلتقي بشرقية، ويرفعها الجبل، أشدها ٢ م'"""
    from sa_geo import join, ar
    if z["a"] and z["b"]:
        where = f"شريط من {z['a']} إلى {z['b']}"
        if z["place"] not in (z["a"], z["b"]):
            where += f"، أشده قرب {z['place']}" if z["km"] <= 30 else f"، أشده على بعد {ar(round(z['km'] / 10) * 10)} كم {z.get('dir') or 'من'} {z['place']}"
    elif z["km"] <= 30:
        where = f"قرب {z['place']}"
    else:
        where = f"على بعد {ar(round(z['km'] / 10) * 10)} كم {z.get('dir') or 'من'} {z['place']}"
    w = z["winds"]
    how = (f"رياح {w[0]} تلتقي برياح {w[1]}" if len(w) == 2 else f"رياح {w[0]} تتباطأ وتتكدس" if w else
           "رياح ضعيفة تتجمع")
    if z["oro"]:
        how += " وتصعد المرتفعات"
    return f"{where} ({join(z.get('regions') or [z['region']])}): {how}، أشدها نحو {hour_words(mk_hour(z['peak_h']))}"
