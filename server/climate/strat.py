"""Wide (stratiform) rain from large-scale lift, region by region (19 Nov 2026 test: 10-12 Nov rain over Riyadh and
the Eastern Province, up to 46-68 % of the Riyadh region wet, was missed by a reading built on convection alone;
Dr. Khalid Al-Otaibi via Fahad: GFS cannot make stratiform rain itself, so it is read from its ingredients).

Ingredients on the GFS 0.25 grid, the report day 09-18 UTC (12-21 Makkah), forecast of the 12 UTC run before:
  - a deep moist layer: RH 700 >= 80 % and RH 500 >= 60 %
  - lift through the middle layers: mean of the 700 and 500 hPa vertical velocity <= -0.10 Pa/s
A grid cell is "lifted" when both hold at one of the hours at least. The share of each region lifted, and the
places at the centre of the lifted area, are kept.

compute(get, cycle, day) -> {"day", "regions": {name: {"frac", "rh7", "rh5", "w", "spots": [names]}}}
"""
from datetime import datetime

import numpy as np

FIELDS = [("rh7", r":RH:700 mb:"), ("rh5", r":RH:500 mb:"), ("w7", r":VVEL:700 mb:"), ("w5", r":VVEL:500 mb:")]
HOURS = (9, 12, 15, 18)
RH7, RH5, W = 80.0, 60.0, -0.10
BOX = (15.5, 33.0, 34.0, 56.0)


def compute(get, cycle, day, log=print):
    import sa_geo as G
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    lat = np.arange(90, -90.01, -0.25)
    lon = np.arange(0, 360, 0.25)
    j = (lat >= BOX[0]) & (lat <= BOX[1])
    i = (lon >= BOX[2]) & (lon <= BOX[3])
    LA, LO = np.meshgrid(lat[j], lon[i], indexing="ij")
    regs = G.regions()
    idx = G.region_of_points(regs, LA.ravel(), LO.ravel()).reshape(LA.shape)
    hit = np.zeros(LA.shape, bool)
    acc = {k: [] for k, _ in FIELDS}
    n = 0
    for uh in HOURS:
        fh = int((datetime(day.year, day.month, day.day, uh) - t0).total_seconds() // 3600)
        try:
            f = get(cycle, fh, FIELDS)
        except Exception as e:  # noqa: BLE001
            log("strat: fields unavailable", fh, repr(e)[:120])
            continue
        s = {k: v[np.ix_(j, i)] for k, v in f.items()}
        w = (s["w7"] + s["w5"]) / 2
        hit |= (s["rh7"] >= RH7) & (s["rh5"] >= RH5) & (w <= W)
        for k in acc:
            acc[k].append(s[k])
        n += 1
    if not n:
        return None
    mean = {k: np.mean(v, axis=0) for k, v in acc.items()}
    out = {"day": day.isoformat(), "hours": n, "regions": {}}
    for k, r in enumerate(regs):
        m = idx == k
        if not m.any():
            continue
        frac = float(hit[m].mean())
        row = {"frac": round(frac, 3), "rh7": round(float(mean["rh7"][m].mean())), "rh5": round(float(mean["rh5"][m].mean())),
               "w": round(float(((mean["w7"] + mean["w5"]) / 2)[m].mean()), 2), "spots": []}
        if frac >= 0.02:
            # the places under the lifted area: its densest parts, at least 60 km apart
            from scipy.ndimage import uniform_filter
            dens = uniform_filter((hit & m).astype(float), 5)
            taken = []
            for q in np.argsort(-dens.ravel())[:3000]:
                if dens.ravel()[q] < 0.3 or len(taken) >= 3:
                    break
                a, b = LA.ravel()[q], LO.ravel()[q]
                if any(abs(a - x) < 0.6 and abs(b - y) < 0.6 for x, y in taken):
                    continue
                taken.append((a, b))
                nm, dk = G.nearest_place(a, b)
                if nm and nm not in row["spots"]:
                    row["spots"].append(nm if dk <= 25 else f"{G.direction(*_at(nm), a, b)} {nm}" if _at(nm) else nm)
        out["regions"][r["name"]] = row
    return out


def _at(name):
    import sa_geo as G
    for n, la, lo in G.PLACES:
        if n == name:
            return la, lo
    return None
