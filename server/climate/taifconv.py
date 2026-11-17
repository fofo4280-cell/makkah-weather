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
per day, with the axis of each collision zone as a dashed line). GFS only, as every product of the oscillation page.
"""
import math
import os
from datetime import datetime, timedelta, timezone

import numpy as np

BOX = (19.0, 24.5, 36.5, 43.5)            # south, north, west, east of the data cut
MAP = (37.8, 41.8, 20.2, 23.3)            # west, east, south, north of the map (Red Sea and Jeddah in, Fahad 17 Nov 2026)
SMOOTH = 1.5                              # as collide.py / plains.taif_zone (about 40 km)
CONV_MIN, CONV_SHIFT = 3.0, 0.5           # as plains.taif_zone
AXIS_MIN = 3.0                            # convergence (1e-5 /s) along a drawn zone axis
U_EAST = -2.0                             # plateau 850 hPa u at or below this: the collision holds on the edge
PAST, NEXT = 7, 7
WIND = [("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:")]
UP = [("u850", r":UGRD:850 mb:"), ("v850", r":VGRD:850 mb:"), ("cape", r":CAPE:surface:")]
# afternoon surface CAPE (Fahad, 17 Nov 2026: third view of the card), J/kg; calm sequential scale on the dark map
CAPE_SCALE = {"vmin": 0, "vmax": 2500, "cols": [(0, "#00000000"), (.04, "#00000000"), (.1, "#2c7f8c"), (.2, "#3fa79a"),
                                                (.4, "#a9cf6a"), (.6, "#e9cf55"), (.8, "#e58a4c"), (1, "#c2445a")],
              "label": "طاقة عدم الاستقرار عند ٣ عصرًا (النموذج الأمريكي)", "unit": "جول/كجم", "ticks": [0, 500, 1000, 1500, 2000, 2500]}
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
    """10 m wind at 09 and 12 UTC (12 and 3 PM Makkah), 850 hPa wind at 12 UTC, rain 09-21 UTC (noon to midnight)"""
    a, lat, lon = _get(gfs_fields, cycle, fh9, WIND + [("ap1", rf":APCP:surface:0-{fh9} hour acc")] + ([] if static else STATIC))
    b, _, _ = _get(gfs_fields, cycle, fh9 + 3, WIND + UP)
    c, _, _ = _get(gfs_fields, cycle, fh9 + 12, [("ap2", rf":APCP:surface:0-{fh9 + 12} hour acc")])
    f = {"lat": lat, "lon": lon, "u9": a["u10"], "v9": a["v10"], "u12": b["u10"], "v12": b["v10"],
         "u850": b["u850"], "v850": b["v850"], "cape": b["cape"], "rain": np.clip(c["ap2"] - a["ap1"], 0, None)}
    f.update(static or {"hgt": a["hgt"], "land": a["land"]})
    f["conv"] = np.mean([convergence(f["u9"], f["v9"], lat), convergence(f["u12"], f["v12"], lat)], axis=0)
    return f


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
        where = "east"
    elif max(ce, cx) < CONV_MIN:
        where = "weak"
    else:
        where = "edge"
    return {"ce": round(ce, 1), "cx": round(cx, 1), "where": where, "cape_edge": int(round(cp_edge)), "cape_east": int(round(cp_east)), "u850": round(u850, 1), "v850": round(v850, 1),
            "front": round(front, 2), "r_edge": round(r_edge, 1), "r_east": round(r_east, 1)}


def run(gfs_fields, cycle, out_fig):
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
        if d in flds:
            try:
                draw_map(os.path.join(out_fig, f"tconv_{k:02d}.png"), flds[d])
                draw_map(os.path.join(out_fig, f"tcape_{k:02d}.png"), flds[d], kind="cape")
            except Exception as e:  # noqa: BLE001
                print("taif collision map failed", k, repr(e)[:160], flush=True)
    try:
        draw_line(os.path.join(out_fig, "tconv_line.png"), rows, today)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("taif collision timeline failed", repr(e)[:160], flush=True)
    print("taif collision:", [(r["d"][5:], r.get("where"), r.get("u850")) for r in rows], flush=True)
    return {"days": [d.isoformat() for d in days], "today": today.isoformat(), "rows": rows, "u_east": U_EAST, "extent": list(MAP),
            "cape_legend": {"label": CAPE_SCALE["label"], "unit": CAPE_SCALE["unit"], "vmin": CAPE_SCALE["vmin"],
                            "vmax": CAPE_SCALE["vmax"], "ticks": CAPE_SCALE["ticks"],
                            "stops": [{"p": p, "c": c[:7]} for p, c in CAPE_SCALE["cols"][2:]]}}


def _font():
    try:
        import figures as F
        return F._ar_font()
    except Exception:  # noqa: BLE001
        return "sans-serif"


def draw_map(path, f, width_px=1000, kind="conv"):
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
    cv = zoom(sub(f["conv"]), up, order=3)
    if kind == "cape":
        from matplotlib.colors import to_rgba
        cm2 = LinearSegmentedColormap.from_list("cape", [(p, to_rgba(c)) for p, c in CAPE_SCALE["cols"]], N=256)
        cp = np.clip(gaussian_filter(zoom(sub(f["cape"]), up, order=1), 3), 0, None)
        ax.imshow(cp, extent=ext, cmap=cm2, vmin=CAPE_SCALE["vmin"], vmax=CAPE_SCALE["vmax"], alpha=.85,
                  interpolation="bilinear", zorder=1)
    else:
        ax.imshow(cv, extent=ext, cmap=cmap, vmin=-8, vmax=8, alpha=.85, interpolation="bilinear", zorder=1)
    flo, fla = np.linspace(lo[0], lo[-1], h.shape[1]), np.linspace(la[0], la[-1], h.shape[0])
    ax.contour(flo, fla, h, levels=[900, 1500], colors=["#6b7480", "#aab3bd"], linewidths=[.6, .9], zorder=2)
    ax.contour(flo, fla, land.astype(float), levels=[.5], colors=["#5d6d7e"], linewidths=.8, zorder=2)
    u, v = sub((f["u9"] + f["u12"]) / 2), sub((f["v9"] + f["v12"]) / 2)
    spd = np.hypot(u, v)
    ax.streamplot(lo, la[::-1], u[::-1], v[::-1], color=(0.93, 0.95, 0.97, 0.8 if kind == "conv" else 0.45), density=1.4,
                  linewidth=np.clip(0.4 + 0.12 * spd[::-1], 0.4, 1.5), arrowsize=0.8, zorder=3)
    # the axis of each collision zone (Fahad, 17 Nov 2026: «حط لي خط عليه زي خط الكنتور، منقط أو مقطع»)
    for xs, ys in conv_axes(cv, fla, flo, land):
        ax.plot(xs, ys, color="#fff6d8", lw=2.0, ls=(0, (5, 3.5)), solid_capstyle="round", zorder=4,
                path_effects=[pe.withStroke(linewidth=3.6, foreground="#3a1606")])
    halo = [pe.withStroke(linewidth=3, foreground=BG)]
    for name, y, x in PLACES:
        if not (w < x < e and s < y < n):
            continue
        ax.plot(x, y, "o", ms=4.5, color="#ffffff", mec=BG, mew=1, zorder=5)
        left = name in ("الهدا", "الشفا", "مكة", "الجموم", "جدة", "رابغ")
        ax.text(x + (-0.05 if left else 0.05), y + 0.03, name, ha="right" if left else "left", va="bottom", fontsize=10,
                color=INK, family=fam, fontweight="bold", path_effects=halo, zorder=6)
    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_aspect(1 / math.cos(math.radians((s + n) / 2)))
    ax.axis("off")
    fig.savefig(path, dpi=200, facecolor=BG)
    plt.close(fig)


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


def draw_line(path, rows, today):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mt
    fam = _font()
    plt.rcParams.update({"font.family": fam, "axes.unicode_minus": False})
    x = np.arange(len(rows))
    g = lambda k: np.array([np.nan if r.get(k) is None else r[k] for r in rows], float)
    ds = [datetime.strptime(r["d"], "%Y-%m-%d").date() for r in rows]
    ti = ds.index(today) if today in ds else None
    fig, axs = plt.subplots(4, 1, figsize=(6.0, 9.4), sharex=True, dpi=180,
                            gridspec_kw={"height_ratios": [1, 1, .9, .9], "hspace": .55})
    fig.patch.set_facecolor(BG)
    for ax in axs:
        ax.set_facecolor(BG)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color("#2a3440")
        ax.grid(axis="y", color=GRID, lw=.6)
        ax.tick_params(colors=MUTED, length=0, labelsize=10)
        ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, p: ar(f"{v:g}")))
        for k, r in enumerate(rows):   # the day's verdict as a faint band
            if r.get("where") in ("edge", "east"):
                ax.axvspan(k - .5, k + .5, color=EDGE_C if r["where"] == "edge" else EAST_C, alpha=.05, lw=0)
        if ti is not None:
            ax.axvline(ti, color="#c9d1db", lw=.8, ls=(0, (3, 3)), alpha=.5)
    T = lambda ax, t: ax.set_title(t, loc="right", color="#c9d1db", fontsize=11.5, fontweight="semibold", pad=7)
    ax = axs[0]
    ax.bar(x - .18, g("ce"), .32, color=EDGE_C, alpha=.85, label="حافة الهدا والشفا")
    ax.bar(x + .18, g("cx"), .32, color=EAST_C, alpha=.85, label="شرق الطائف والسيل")
    T(ax, "قوة التصادم ظهرًا وعصرًا")
    ax.legend(loc="upper left", frameon=False, fontsize=9.5, labelcolor="#c9d1db", ncol=2, bbox_to_anchor=(0, 1.0))
    ax.set_ylim(0, max(10, np.nanmax([g("ce"), g("cx")]) * 1.45))
    ax = axs[1]
    u = g("u850")
    ax.bar(x, u, .55, alpha=.85, color=[EDGE_C if (np.isfinite(v) and v <= U_EAST) else ("#5d6773" if (np.isfinite(v) and v < 0) else EAST_C) for v in u])
    ax.axhline(0, color="#56616e", lw=.8)
    ax.axhline(U_EAST, color=MUTED, lw=.8, ls=(0, (4, 3)))
    lim = max(6, np.nanmax(np.abs(u)) * 1.15)
    ax.set_ylim(-lim, lim)
    T(ax, "الرياح فوق هضبة الطائف عند ٨٥٠ (م/ث)")
    ax.text(len(rows) - .5, -lim * .93, "سالب = شرقية تُوقف هواء البحر عند الحافة", ha="right", color=EDGE_C, fontsize=9)
    ax.text(len(rows) - .5, lim * .82, "موجب = غربية تدفعه شرقًا", ha="right", color=EAST_C, fontsize=9)
    ax = axs[2]
    fr = g("front")
    ax.plot(x, fr, "-o", color="#c9d1db", lw=1.3, ms=3)
    places = ((40.3, "الهدا"), (40.75, "شرق الطائف"), (41.5, "عمق الهضبة"), (42.3, "شرقًا أبعد"))
    for v, _ in places:
        ax.axhline(v, color="#3a4552", lw=.6, ls=(0, (4, 3)))
    ax.set_ylim(42.6, 39.9)
    ax.set_yticks([v for v, _ in places])
    ax.set_yticklabels([t for _, t in places], fontsize=9)
    T(ax, "أبعد ما يصله هواء البحر عصرًا (خط طول)")
    ax = axs[3]
    b1 = ax.bar(x - .18, g("r_edge"), .32, color=EDGE_C, alpha=.85)
    b2 = ax.bar(x + .18, g("r_east"), .32, color=EAST_C, alpha=.85)
    ax.set_ylim(0, max(3, np.nanmax([g("r_edge"), g("r_east")]) * 1.45))
    ax.legend([b1, b2], ["حافة الهدا والشفا", "السيل وشرق الطائف ورهاط"], loc="upper left", frameon=False, fontsize=9.5, labelcolor="#c9d1db", ncol=2)
    T(ax, "متوسط المطر من الظهر إلى منتصف الليل (ملم)")
    ax.set_xticks(x)
    ax.set_xticklabels([("اليوم" if d == today else _day_label(d)) for d in ds], rotation=0, fontsize=8.5, color=MUTED)
    for lab, d in zip(ax.get_xticklabels(), ds):
        if d == today:
            lab.set_color("#c9d1db")
    ax.set_xlim(-.6, len(rows) - .4)
    fig.subplots_adjust(left=.16, right=.98, top=.96, bottom=.045)
    fig.savefig(path, dpi=180, facecolor=BG)
    plt.close(fig)
