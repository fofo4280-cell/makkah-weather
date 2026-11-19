"""Where the afternoon winds collide around Taif, for the oscillation page (Fahad, 17 Nov 2026).

Study of 17 Nov 2026 (1 Aug-17 Nov 2026, with 2024 and 2025 for comparison): the afternoon collision line sits where
the westerly sea air climbing from Tihama meets the wind already blowing over the Taif plateau.
  - plateau wind at 850 hPa easterly (u <= -2 m/s): the sea air is stopped at the rim (40.3-40.5 E), the collision
    and the storms stay on the Al-Hada / Ash-Shafa edge (9 Sep-15 Oct 2026, and again from 15 Nov);
  - plateau wind weak, southerly or westerly (troughs to the north, the subtropical jet over the Hijaz): the sea air
    climbs over the rim, the collision goes east and north-east of Taif (Al-Sail, the plateau, Harrat Rahat)
    (16 Oct-14 Nov 2026).
  corr(u850 plateau, east minus edge convergence) 0.77 (2026), 0.70 (2025), 0.57 (2024).

The page window is 7 days before today, today and 7 days after (today = the day after the cycle's date, since the
nightly run uses the evening 12Z cycle and finishes after midnight Makkah). Days up to the cycle's date come from
that day's 06Z GFS cycle (f03, f06 = 12 and 3 PM Makkah: near-analyses); later days from the nightly 12Z cycle.

run(gfs_fields, cycle, out_fig) -> dict for mjo.json["taifc"]; draws fig/tconv_line.png, fig/tconv_NN.png (one map
per day, with the axis of each collision zone as a dashed line). Page maps from ECMWF since 19 Nov 2026 (Fahad), through\necmwf.fields_like_gfs; a GFS copy (draw=False) still feeds the nightly report's Makkah reading.
"""
import math
import os
from datetime import datetime, timedelta, timezone

import numpy as np

BOX = (13.0, 34.5, 32.0, 58.5)            # south, north, west, east of the data cut
# the whole Kingdom (Fahad, 18 Nov 2026: «خلها على عموم المملكة»; he zooms in on the page to look at the collisions);
# the same frame as the Kingdom maps of ksa.py. Was (37.8, 41.8, 20.2, 23.3) around Taif.
MAP = (33.0, 57.5, 14.0, 33.5)
SMOOTH = 1.5                              # as collide.py / plains.taif_zone (about 40 km)
CONV_MIN, CONV_SHIFT = 3.0, 0.5           # as plains.taif_zone
# 18 Nov 2026 (Fahad: "contradictions"): a stronger meeting east of Taif moves the storms there only when the air
# there has fuel; with surface CAPE (p75, 1 PM) under EAST_CAPE the cells stay on the edge (18 Nov: east 4.0 vs edge
# 3.1 but CAPE 28 vs 184 and GFS rain 0.8 vs 6.1 mm). Same rule in plains.taif_zone.
EAST_CAPE = 100
HOURS = ("11", "13", "15")                # Makkah hours of the maps (08, 10, 12 UTC)
AXIS_MIN = 3.0                            # convergence (1e-5 /s) along a drawn zone axis
U_EAST = -2.0                             # plateau 850 hPa u at or below this: the collision holds on the edge
PAST, NEXT = 7, 7
WIND = [("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:")]
UP = [("u850", r":UGRD:850 mb:"), ("v850", r":VGRD:850 mb:"), ("cape", r":CAPE:surface:")]
# afternoon surface CAPE (Fahad, 17 Nov 2026: third view of the card), J/kg; calm sequential scale on the dark map
CAPE_SCALE = {"vmin": 0, "vmax": 4000, "cols": [(0, "#00000000"), (.04, "#00000000"), (.1, "#2c7f8c"), (.2, "#3fa79a"),
                                                (.4, "#a9cf6a"), (.6, "#e9cf55"), (.8, "#e58a4c"), (1, "#c2445a")],
              "label": "طاقة عدم الاستقرار (النموذج الأوروبي)", "unit": "جول/كجم", "ticks": [0, 1000, 2000, 3000, 4000]}
# ECMWF gives the most-unstable CAPE (the best parcel of the lowest 300 hPa), higher than the GFS surface CAPE: scale 0-4000
STATIC = [("hgt", r":HGT:surface:"), ("land", r":LAND:surface:")]
PLACES = [("جدة", 21.54, 39.17), ("رابغ", 22.80, 39.03), ("مكة", 21.42, 39.83), ("الطائف", 21.27, 40.42), ("الهدا", 21.36, 40.28), ("الشفا", 21.07, 40.33),
          ("السيل", 21.6, 40.43), ("حرة رهاط", 22.8, 40.1), ("الجموم", 21.62, 39.70)]
AR = str.maketrans("0123456789.-", "٠١٢٣٤٥٦٧٨٩٫−")
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
WEEK = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
# dark page palette (as the Kingdom maps)
BG, INK, MUTED, GRID = "#0c1118", "#e8ecf1", "#9aa4b1", "#1f2833"
EDGE_C, EAST_C = "#6f9fd8", "#e0895a"            # calmer than the study charts (Fahad 17 Nov 2026)


def ar(x):
    return str(x).translate(AR)


def cut(a, lat, lon):
    s, n, w, e = BOX
    j = (lat >= s) & (lat <= n)
    i = (lon >= w) & (lon <= e)
    return a[np.ix_(j, i)], lat[j], lon[i]


def convergence(u, v, lat, dlon=0.25):
    from scipy.ndimage import gaussian_filter
    a = 6.371e6
    phi = np.radians(lat)[:, None]
    d = np.radians(dlon)
    u, v = gaussian_filter(u, SMOOTH), gaussian_filter(v, SMOOTH)
    return -(np.gradient(u, d, axis=1) / (a * np.cos(phi)) + np.gradient(v * np.cos(phi), -d, axis=0) / (a * np.cos(phi))) * 1e5


def _get(gfs_fields, cycle, fh, fl):
    f = gfs_fields(cycle, fh, res="0p25", fields=fl)
    k0 = next(iter(f))
    la = np.linspace(90, -90, f[k0].shape[0])
    lo = np.linspace(0, 360, f[k0].shape[1], endpoint=False)
    out = {}
    for k, a in f.items():
        out[k], lat, lon = cut(a, la, lo)
    return out, lat, lon


def day_fields(gfs_fields, cycle, fh9, static=None):
    """the 10 m wind and surface CAPE at 11 AM, 1 PM and 3 PM Makkah (08, 10, 12 UTC), the 850 hPa wind at 3 PM, rain
    09-21 UTC (noon to midnight). fh9 = the forecast hour of 09 UTC of the day.
    Hours (Fahad, 17 Nov 2026): convective cells start on the rim between 10 AM and 1 PM; by 3 PM the GFS line has
    already drifted east to Taif (16 and 17 Nov: peak 40.25 E at 11 AM, 40.5 at noon, 40.5-40.75 at 3 PM, while the
    storms formed on Al-Hada / Ash-Shafa). GFS 0.25 is hourly to 120 h; beyond, 11 AM = mean of 9 AM and noon and
    1 PM = noon."""
    hourly = fh9 + 3 <= 120
    W = WIND + [("cape", r":CAPE:surface:")]
    def at(fhs):
        got = [_get(gfs_fields, cycle, x, W)[0] for x in fhs]
        return tuple(np.mean([g[k] for g in got], axis=0) for k in ("u10", "v10", "cape"))
    a, lat, lon = _get(gfs_fields, cycle, fh9, [("ap1", rf":APCP:surface:0-{fh9} hour acc")] + ([] if static else STATIC))
    b, _, _ = _get(gfs_fields, cycle, fh9 + 3, W + UP)
    c, _, _ = _get(gfs_fields, cycle, fh9 + 12, [("ap2", rf":APCP:surface:0-{fh9 + 12} hour acc")])
    H = {"11": at([fh9 - 1] if hourly else [fh9 - 3, fh9]), "13": at([fh9 + 1] if hourly else [fh9]),
         "15": (b["u10"], b["v10"], b["cape"])}
    f = {"lat": lat, "lon": lon, "H": H, "u12": b["u10"], "v12": b["v10"], "u850": b["u850"], "v850": b["v850"],
         "cape": H["13"][2], "rain": np.clip(c["ap2"] - a["ap1"], 0, None)}
    f.update(static or {"hgt": a["hgt"], "land": a["land"]})
    # the day's collision (edge or east): the initiation window, 11 AM and 1 PM
    f["conv"] = np.mean([convergence(H[h][0], H[h][1], lat) for h in ("11", "13")], axis=0)
    return f


# the western region's collision index (Fahad, 18 Nov 2026: one signal for Taif, Jeddah, Makkah, Al-Jumum, the harrat,
# south of Makkah and the Red Sea beside them). Zones on the 0.25 grid, 20.25-23.3 N, 38.3-41.6 E:
#   edge  = the escarpment rim (first land cell >= 900 m from the west in each row) and the slopes 300-900 m below it,
#           plus the plains under it (Makkah, Al-Jumum, Jeddah, the Tihama south of Makkah): the collision "came down"
#   taif  = the plateau (>= 900 m) east of the rim (Taif itself, Al-Sail, its north-east and east, the harrat)
#           (the first plateau cell east of the rim is left out: with ~40 km smoothing an edge peak leaks into it)
#   edge stops at 21.9 N (Makkah, Al-Jumum, Al-Hada, Ash-Shafa, south of Makkah)
#   sea   = the Red Sea beside the coast
# The day's index is the strongest zone (peak convergence 11 AM-1 PM, 1e-5 /s): taif +peak, edge -peak, sea (its own
# colour, drawn below zero, west of the edge); weak when every peak is under CONV_MIN.
WREG = (20.25, 23.3, 38.3, 41.6)
EDGE_N = 21.9                            # the edge zone (Makkah-Taif mountains and south of Makkah) stops here


def west_zones(lat, lon, hgt, land):
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    s, n, w, e = WREG
    reg = (LA >= s) & (LA <= n) & (LO >= w) & (LO <= e)
    land = land > 0.5
    rim = np.zeros_like(land)
    door = np.zeros_like(land)
    for j in range(len(lat)):
        ii = np.where(land[j] & (hgt[j] >= 900) & (lon >= 39.5) & (lon <= e))[0]
        if len(ii):
            rim[j, ii[0]] = True
            door[j, ii[0] + 1:ii[0] + 2] = True       # the first plateau cell: with ~40 km smoothing an edge peak leaks here
            rim[j, :ii[0]] |= land[j, :ii[0]]       # everything on land west of the rim: slopes and plains
    south = LA <= EDGE_N
    edge = reg & land & rim & south
    # north of EDGE_N only the harrat plateau counts (with Taif's side): the plains under the harrat hold a sea-breeze
    # line nearly every day (39.5-40 E, 22.2-23 N) that would otherwise always win
    taif = reg & land & ~rim & ~door & (hgt >= 900)
    return {"taif": taif, "edge": edge, "sea": reg & ~land}


def west_index(f):
    Z = west_zones(f["lat"], f["lon"], f["hgt"], f["land"])
    c = f["conv"]
    pk = {k: float(np.where(m, c, -np.inf).max()) for k, m in Z.items()}
    at = {}
    for k, m in Z.items():
        j, i = np.unravel_index(np.where(m, c, -np.inf).argmax(), c.shape)
        at[k] = [round(float(f["lat"][j]), 2), round(float(f["lon"][i]), 2)]
    k = max(pk, key=pk.get)
    if pk[k] < CONV_MIN:
        k = "weak"
    wi = {"taif": pk["taif"], "edge": -pk["edge"], "sea": -pk["sea"]}.get(k, 0.0)
    return {"wz": k, "wi": round(wi, 1), "wt": round(pk["taif"], 1), "wg": round(pk["edge"], 1), "ws": round(pk["sea"], 1),
            "wat": at.get(k)}


def measure(f):
    """the numbers of one day (the boxes of plains.taif_zone)"""
    lat, lon, c = f["lat"], f["lon"], f["conv"]
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    B = lambda s, n, w, e: (LA >= s) & (LA <= n) & (LO >= w) & (LO <= e)
    box = B(20.85, 21.9, 40.1, 41.0) & (f["land"] > 0.5) & (f["hgt"] >= 900)
    edge = box & (LO < 40.45) & (LA < 21.45)
    east = box & ((LO >= 40.6) | ((LA >= 21.45) & (LO >= 40.35)))
    pk = lambda m: float(np.where(m, c, -np.inf).max())
    ce, cx = pk(edge), pk(east)
    plat = B(21.0, 22.0, 40.6, 41.6)
    u850, v850 = float(f["u850"][plat].mean()), float(f["v850"][plat].mean())
    # how far east the westerly (sea) air reaches at 3 PM Makkah, along 21.2-21.5 N
    jj, ii = (lat >= 21.2) & (lat <= 21.5), (lon >= 39.5) & (lon <= 42.5)
    prof, ll = f["u12"][np.ix_(jj, ii)].mean(0), lon[ii]
    k = 0
    while k < len(prof) and prof[k] > 0:
        k += 1
    front = float(ll[k - 1]) if k else 39.5
    rain = f["rain"]
    cape = f["cape"]
    cp_edge = float(np.percentile(cape[edge], 75))
    cp_east = float(np.percentile(cape[east], 75))
    r_edge = float(rain[B(20.85, 21.6, 40.15, 40.45)].mean())
    r_east = float(np.mean([rain[B(21.45, 21.85, 40.35, 40.7)].mean(), rain[B(20.9, 21.6, 40.6, 41.1)].mean(),
                            rain[B(22.2, 23.3, 39.8, 40.5)].mean()]))
    if cx >= CONV_MIN and cx >= ce + CONV_SHIFT:
        where = "east"     # (with fuel False the page says the cells still grow strongest on the edges)
    elif max(ce, cx) < CONV_MIN:
        where = "weak"
    else:
        where = "edge"
    return {"ce": round(ce, 1), "cx": round(cx, 1), "where": where, "fuel": bool(cp_east >= EAST_CAPE), "cape_edge": int(round(cp_edge)), "cape_east": int(round(cp_east)), "u850": round(u850, 1), "v850": round(v850, 1),
            "front": round(front, 2), "r_edge": round(r_edge, 1), "r_east": round(r_east, 1), **west_index(f)}


TAIF_SAY = {"edge": "حكم اليوم حول الطائف: التصادم على حافة الهدا والشفا",
            "east": "حكم اليوم حول الطائف: التصادم شرق الطائف وشماله",
            "eastdry": "حكم اليوم حول الطائف: التقارب أقوى شرقه لكن الطاقة هناك ضعيفة، فالحافة أرجح",
            "weak": "حكم اليوم حول الطائف: التصادم ضعيف"}


def explain(f, row, kind, hour):
    """the explanation lines of a map: where the collision (or the energy) is, at the cities, and the Taif verdict"""
    import figures as F
    N = F.ar_num
    lat, lon = f["lat"], f["lon"]
    uh, vh, caph = f["H"][hour]
    out = []
    if kind == "cape":
        v = F.nearest_vals(caph, lat, lon, radius=0.5, mode="max")
        hi = [f"{k} ({N(round(x, -1))})" for k, x in sorted(v.items(), key=lambda kv: -kv[1]) if x >= 250]
        out.append(f"أعلى طاقة قرب {F.ar_list(hi, 4)}" if hi else "طاقة ضعيفة (أقل من ٢٥٠) قرب المدن كلها")
    else:
        v = F.nearest_vals(convergence(uh, vh, lat), lat, lon, radius=0.5, mode="max")
        hi = [k for k, x in sorted(v.items(), key=lambda kv: -kv[1]) if x >= CONV_MIN]
        out.append(f"تصادم قوي قرب {F.ar_list(hi, 5)}" if hi else "لا تصادم قويًا قرب المدن في هذه الساعة")
    w_ = row.get("where")
    if w_ == "east" and not row.get("fuel", True):
        w_ = "eastdry"
    if w_ in TAIF_SAY:
        out.append(TAIF_SAY[w_])
    return out


def run(gfs_fields, cycle, out_fig, model="الأوروبي", draw=True):
    t0 = datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    d0 = t0.date()
    today = d0 + timedelta(days=1)
    days = [today + timedelta(days=k) for k in range(-PAST, NEXT + 1)]
    rows, flds, static = [], {}, None
    for d in days:
        try:
            if d <= d0:     # the day's own 06Z cycle: 03 and 06 h = 09 and 12 UTC
                f = day_fields(gfs_fields, d.strftime("%Y%m%d") + "06", 3, static)
                fc = False
            else:           # the nightly 12Z cycle
                f = day_fields(gfs_fields, cycle, int((datetime(d.year, d.month, d.day, 9, tzinfo=timezone.utc) - t0).total_seconds() // 3600), static)
                fc = True
            static = static or {"hgt": f["hgt"], "land": f["land"]}
            flds[d] = f
            rows.append({"d": d.isoformat(), "fc": fc, **measure(f)})
        except Exception as e:  # noqa: BLE001
            print("taif collision day failed", d, repr(e)[:160], flush=True)
            rows.append({"d": d.isoformat(), "fc": d > d0, "where": None})
    for k, d in enumerate(days):
        if d in flds and draw:
            try:
                for hh in HOURS:
                    draw_map(os.path.join(out_fig, f"tconv_{k:02d}_{hh}.png"), flds[d], hour=hh, when=d, model=model,
                             lines=explain(flds[d], rows[k], "conv", hh))
                    draw_map(os.path.join(out_fig, f"tcape_{k:02d}_{hh}.png"), flds[d], kind="cape", hour=hh, when=d,
                             model=model, lines=explain(flds[d], rows[k], "cape", hh))
            except Exception as e:  # noqa: BLE001
                print("taif collision map failed", k, repr(e)[:160], flush=True)
    try:
        if draw:
            draw_line(os.path.join(out_fig, "tconv_line.png"), rows, today)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("taif collision timeline failed", repr(e)[:160], flush=True)
    print("taif collision:", [(r["d"][5:], r.get("where"), r.get("u850")) for r in rows], flush=True)
    return {"days": [d.isoformat() for d in days], "today": today.isoformat(), "rows": rows, "u_east": U_EAST, "extent": list(MAP), "hours": list(HOURS),
            "cape_legend": {"label": CAPE_SCALE["label"], "unit": CAPE_SCALE["unit"], "vmin": CAPE_SCALE["vmin"],
                            "vmax": CAPE_SCALE["vmax"], "ticks": CAPE_SCALE["ticks"],
                            "stops": [{"p": p, "c": c[:7]} for p, c in CAPE_SCALE["cols"][2:]]}}


def _font():
    try:
        import figures as F
        return F._ar_font()
    except Exception:  # noqa: BLE001
        return "sans-serif"


def draw_map(path, f, width_px=1400, kind="conv", hour="11", when=None, model="الأوروبي", lines=()):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.colors import LightSource, LinearSegmentedColormap
    from scipy.ndimage import zoom, gaussian_filter
    fam = _font()
    w, e, s, n = MAP
    lat, lon = f["lat"], f["lon"]
    j = (lat >= s - .5) & (lat <= n + .5)
    i = (lon >= w - .5) & (lon <= e + .5)
    la, lo = lat[j], lon[i]
    sub = lambda a: a[np.ix_(j, i)]
    aspect = (n - s) / ((e - w) * math.cos(math.radians((s + n) / 2)))
    fig = plt.figure(figsize=(width_px / 200, width_px / 200 * aspect), dpi=200)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    up = 8
    ext = [lo[0], lo[-1], la[-1], la[0]]
    h = gaussian_filter(zoom(np.clip(sub(f["hgt"]), 0, None), up, order=3), 2)
    shade = LightSource(azdeg=315, altdeg=40).hillshade(h, vert_exag=0.02, dx=1, dy=1)
    land = gaussian_filter(zoom(sub(f["land"]).astype(float), up, order=1), 3) > 0.5
    base = np.where(land, 0.18 + 0.32 * shade, 0.07)
    ax.imshow(base, extent=ext, cmap="gray", vmin=0, vmax=1, interpolation="bilinear", zorder=0)
    cmap = LinearSegmentedColormap.from_list("c", [(0, "#2f7fd0"), (.38, "#8fd0ea00"), (.5, "#00000000"), (.62, "#f6e27a00"),
                                                   (.72, "#f5a623"), (.86, "#e2532d"), (1, "#b3124a")], N=256)
    uh, vh, caph = f["H"][hour]
    cv = zoom(sub(convergence(uh, vh, lat)), up, order=3)
    if kind == "cape":
        from matplotlib.colors import to_rgba
        cm2 = LinearSegmentedColormap.from_list("cape", [(p, to_rgba(c)) for p, c in CAPE_SCALE["cols"]], N=256)
        cp = np.clip(gaussian_filter(zoom(sub(caph), up, order=1), 3), 0, None)
        ax.imshow(cp, extent=ext, cmap=cm2, vmin=CAPE_SCALE["vmin"], vmax=CAPE_SCALE["vmax"], alpha=.85,
                  interpolation="bilinear", zorder=1)
    else:
        ax.imshow(cv, extent=ext, cmap=cmap, vmin=-8, vmax=8, alpha=.85, interpolation="bilinear", zorder=1)
    flo, fla = np.linspace(lo[0], lo[-1], h.shape[1]), np.linspace(la[0], la[-1], h.shape[0])
    ax.contour(flo, fla, h, levels=[900, 1500], colors=["#6b7480", "#aab3bd"], linewidths=[.35, .55], zorder=2)
    u, v = sub(uh), sub(vh)
    spd = np.hypot(u, v)
    ax.streamplot(lo, la[::-1], u[::-1], v[::-1], color=(0.93, 0.95, 0.97, 0.7 if kind == "conv" else 0.4), density=2.4,
                  linewidth=np.clip(0.25 + 0.06 * spd[::-1], 0.25, 0.9), arrowsize=0.5, zorder=3)
    # the axis of each collision zone (Fahad, 17 Nov 2026: «حط لي خط عليه زي خط الكنتور، منقط أو مقطع»)
    for xs, ys in conv_axes(cv, fla, flo, land):
        ax.plot(xs, ys, color="#fff6d8", lw=1.3, ls=(0, (4, 3)), solid_capstyle="round", zorder=4,
                path_effects=[pe.withStroke(linewidth=2.6, foreground="#3a1606")])
    halo = [pe.withStroke(linewidth=3, foreground=BG)]
    # place names are written by the page at a constant size (Fahad, 18 Nov 2026: soft names, right next to their dots)
    for name, y, x in []:
        if not (w < x < e and s < y < n):
            continue
        ax.plot(x, y, "o", ms=4.5, color="#ffffff", mec=BG, mew=1, zorder=5)
        left = name in ("الهدا", "الشفا", "مكة", "الجموم", "جدة", "رابغ")
        ax.text(x + (-0.05 if left else 0.05), y + 0.03, name, ha="right" if left else "left", va="bottom", fontsize=10,
                color=INK, family=fam, fontweight="bold", path_effects=halo, zorder=6)
    # coast and borders (Natural Earth 1:50m), thin, as the other Kingdom maps
    try:
        import cartopy.feature as cfeature
        for feat, col, lw in ((cfeature.NaturalEarthFeature("physical", "coastline", "50m"), "#5d6d7e", .6),
                              (cfeature.NaturalEarthFeature("cultural", "admin_0_boundary_lines_land", "50m"), "#4a5562", .5)):
            for g in feat.intersecting_geometries([w - 1, e + 1, s - 1, n + 1]):
                for ln in getattr(g, "geoms", [g]):
                    xy = np.asarray(ln.coords)
                    ax.plot(xy[:, 0], xy[:, 1], color=col, lw=lw, zorder=2.5)
    except Exception as ex:  # noqa: BLE001
        print("borders unavailable:", str(ex)[:80])
    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_aspect(1 / math.cos(math.radians((s + n) / 2)))
    ax.axis("off")
    if when is not None:
        # the card style (Fahad, 19 Nov 2026): names, title box with the explanation, legend box
        import figures as F
        F.card_cities(ax)
        if kind == "cape":
            leg = {"cols": CAPE_SCALE["cols"][2:], "vmin": CAPE_SCALE["vmin"], "vmax": CAPE_SCALE["vmax"],
                   "ticks": CAPE_SCALE["ticks"], "caption": "جول/كجم، والخط المتقطع محور تصادم الرياح"}
            leg["cols"] = [(0, CAPE_SCALE["cols"][2][1])] + leg["cols"]
            ttl = "طاقة عدم الاستقرار"
        else:
            leg = {"cols": [(0, "#8fd0ea"), (.5, "#3a434e"), (.62, "#f6e27a"), (.72, "#f5a623"), (.86, "#e2532d"),
                            (1, "#b3124a")], "vmin": -8, "vmax": 8, "ticks": [-8, -4, 0, 4, 8],
                   "caption": "تقارب الرياح السطحية (أحمر)، والمتقطع محور التصادم"}
            ttl = "تصادم الرياح السطحية"
        F.card_frame(fig, f"{ttl} — النموذج {model}", F.when_ar(when, int(hour)), lines, leg)
    fig.savefig(path, dpi=200, facecolor=BG)
    plt.close(fig)
    try:   # keep the files small: 90 maps a night
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=200, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


def conv_axes(cv, lat, lon, land, thr=AXIS_MIN, min_len=0.6):
    """the axis of every collision zone on the fine grid (lat increasing or decreasing): along each row the local
    maxima of convergence >= thr over land, chained row to row when they lie within 0.12 deg of longitude; chains
    shorter than min_len degrees dropped, then smoothed. Zones run roughly north-south along the escarpment, so
    row maxima trace them."""
    dl = abs(float(lon[1] - lon[0]))
    chains, open_ = [], []
    for j in range(cv.shape[0]):
        row = cv[j]
        ok = row >= thr          # over the sea too: a collision line off Jeddah matters (Fahad 17 Nov 2026)
        ok[1:-1] &= (row[1:-1] >= row[:-2]) & (row[1:-1] >= row[2:])
        ok[0] = ok[-1] = False
        pts = [float(lon[i]) for i in np.where(ok)[0]]
        nxt = []
        for x in pts:
            best = None
            for c in open_:
                if abs(c[-1][0] - x) <= 0.12 + dl and (best is None or abs(c[-1][0] - x) < abs(best[-1][0] - x)):
                    best = c
            if best is not None:
                open_.remove(best)
                best.append((x, float(lat[j])))
                nxt.append(best)
            else:
                c = [(x, float(lat[j]))]
                chains.append(c)
                nxt.append(c)
        open_ = nxt
    out = []
    for c in chains:
        if abs(c[-1][1] - c[0][1]) < min_len:
            continue
        xs = np.array([p[0] for p in c])
        ys = np.array([p[1] for p in c])
        k = 9
        if len(xs) > k:
            xs = np.convolve(np.pad(xs, k // 2, mode="edge"), np.ones(k) / k, "valid")
        out.append((xs, ys))
    return out


def _day_label(d):
    return f"{ar(d.day)}/{ar(d.month)}"


WEST_C = {"taif": "#e0895a", "edge": "#6f9fd8", "sea": "#3fb8a6"}


def draw_line(path, rows, today):
    """one signal: the western region's collision index, past week, today and the week ahead"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mt
    from matplotlib.patches import Patch
    fam = _font()
    plt.rcParams.update({"font.family": fam, "axes.unicode_minus": False})
    x = np.arange(len(rows))
    ds = [datetime.strptime(r["d"], "%Y-%m-%d").date() for r in rows]
    ti = ds.index(today) if today in ds else None
    fig, ax = plt.subplots(figsize=(6.0, 3.9), dpi=180)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=.6)
    ax.tick_params(colors=MUTED, length=0, labelsize=10)
    ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, p: ar(f"{v:g}")))
    wi = np.array([r.get("wi") if r.get("wz") else np.nan for r in rows], float)
    lim = max(8, np.nanmax(np.abs(wi)) * 1.25 if np.isfinite(wi).any() else 8)
    for k, r in enumerate(rows):
        z = r.get("wz")
        if z in WEST_C:
            ax.bar(k, wi[k], .62, color=WEST_C[z], alpha=.9 if not r.get("fc") else .75, hatch="~~~" if z == "sea" else None,
                   edgecolor=BG if z != "sea" else "#0c1118", lw=0)
            ax.text(k, wi[k] + (lim * .03 if wi[k] > 0 else -lim * .03), ar(f"{abs(wi[k]):.0f}"), ha="center",
                    va="bottom" if wi[k] > 0 else "top", color=WEST_C[z], fontsize=8)
        elif z == "weak":
            ax.plot(k, 0, "o", color="#5d6773", ms=4)
    ax.axhline(0, color="#56616e", lw=.9)
    if ti is not None:
        ax.axvline(ti, color="#c9d1db", lw=.8, ls=(0, (3, 3)), alpha=.5)
        ax.axvspan(ti + .5, len(rows) - .4, color="#ffffff", alpha=.025, lw=0)
    ax.set_ylim(-lim, lim)
    ax.text(len(rows) - .5, lim * .9, "موجب: التصادم على الطائف وهضبته", ha="right", va="top", color=WEST_C["taif"], fontsize=9.5)
    ax.text(len(rows) - .5, -lim * .9, "سالب: على الحافة والجبال وما تحتها", ha="right", va="bottom", color=WEST_C["edge"], fontsize=9.5)
    ax.legend(handles=[Patch(color=WEST_C["taif"], label="الطائف"), Patch(color=WEST_C["edge"], label="الحافة"),
                       Patch(facecolor=WEST_C["sea"], hatch="~~~", edgecolor=BG, label="فوق البحر"),
                       plt.Line2D([], [], marker="o", ls="", color="#5d6773", label="ضعيف")],
              loc="upper left", frameon=False, fontsize=9, labelcolor="#c9d1db", ncol=4, bbox_to_anchor=(0, 1.13), handlelength=1.2,
              columnspacing=1.0)
    ax.set_title("مؤشر مكان التصادم في المنطقة الغربية", loc="right", color="#c9d1db", fontsize=11.5, fontweight="semibold", pad=24)
    ax.set_xticks(x)
    ax.set_xticklabels([("اليوم" if d == today else _day_label(d)) for d in ds], rotation=0, fontsize=8.5, color=MUTED)
    for lab, d in zip(ax.get_xticklabels(), ds):
        if d == today:
            lab.set_color("#c9d1db")
    ax.set_xlim(-.6, len(rows) - .4)
    fig.subplots_adjust(left=.08, right=.98, top=.84, bottom=.08)
    fig.savefig(path, dpi=180, facecolor=BG)
    plt.close(fig)
