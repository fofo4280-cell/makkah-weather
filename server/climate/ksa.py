"""Four Kingdom maps for every forecast day of the oscillation page (Fahad, 17 Nov 2026), from GFS alone:
  krh7  relative humidity at 700 hPa
  krh5  relative humidity at 500 hPa
  kconv where the surface (10 m) winds meet, with the sea-level isobars and any surface low over the Red Sea or land
  kt5   temperature at 500 hPa
All at 0.25 degrees, valid 12 UTC (15:00 Makkah) of each day of the page (day k = the GFS cycle + 24 k hours).

fields(gfs_fields, cycle, fh) -> dict of arrays cut to BOX (+ lat, lon)
lows(f) -> [{lat, lon, p, sea, where, closed}]
draw(path, kind, f, lows) -> PNG
"""
import math
import os

import numpy as np

FIELDS = [("rh7", r":RH:700 mb:"), ("rh5", r":RH:500 mb:"), ("t5", r":TMP:500 mb:"),
          ("u10", r":UGRD:10 m above ground:"), ("v10", r":VGRD:10 m above ground:"),
          ("mslp", r":MSLET:mean sea level:")]
STATIC = [("hgt", r":HGT:surface:"), ("land", r":LAND:surface:")]
BOX = (8.0, 38.0, 28.0, 62.0)            # south, north, west, east of the data (margin around the map)
EXTENT = (33.0, 57.5, 14.0, 33.5)        # west, east, south, north of the map
KINDS = ("krh7", "krh5", "kt5")            # kconv dropped 17 Nov 2026 (Fahad): convergence has its own card (taifconv)
SMOOTH = 1.5                             # convergence smoothing, grid lengths (about 40 km, as collide.py)

SCALES = {
    "krh7": {"vmin": 0, "vmax": 100, "cols": [(0, "#7a4a1f"), (.15, "#b88a52"), (.3, "#dcc49a"), (.45, "#ece6d6"),
                                               (.55, "#bfe3b4"), (.7, "#62bf7e"), (.82, "#1f9a62"), (.92, "#0b6e66"),
                                               (1, "#0a3f5c")],
             "label": "الرطوبة النسبية عند ٧٠٠ هكتوباسكال (نحو ٣ كم)", "unit": "٪", "ticks": [0, 20, 40, 60, 80, 100]},
    "krh5": {"vmin": 0, "vmax": 100, "cols": [(0, "#7a4a1f"), (.15, "#b88a52"), (.3, "#dcc49a"), (.45, "#ece6d6"),
                                               (.55, "#bfe3b4"), (.7, "#62bf7e"), (.82, "#1f9a62"), (.92, "#0b6e66"),
                                               (1, "#0a3f5c")],
             "label": "الرطوبة النسبية عند ٥٠٠ هكتوباسكال (نحو ٥٫٥ كم)", "unit": "٪", "ticks": [0, 20, 40, 60, 80, 100]},
    "kconv": {"vmin": 0, "vmax": 8, "cols": [(0, "#ffffff00"), (.12, "#ffffff00"), (.2, "#f6e27a"), (.4, "#f5a623"),
                                             (.6, "#e2532d"), (.8, "#b3124a"), (1, "#5c0a6b")],
              "label": "شدة تصادم الرياح السطحية (تقارب الرياح عند ١٠ أمتار)", "unit": "",
              "ticks": [1, 2, 4, 6, 8]},
    "kt5": {"vmin": -26, "vmax": -2, "cols": [(0, "#3b0f6f"), (.17, "#3a3fb0"), (.33, "#2f7fd0"), (.47, "#8fd0ea"),
                                              (.58, "#eef3ea"), (.68, "#f6d27a"), (.8, "#ef9440"), (.9, "#d2462b"),
                                              (1, "#7a0f12")],
            "label": "درجة الحرارة عند ٥٠٠ هكتوباسكال (نحو ٥٫٥ كم)", "unit": "°م",
            "ticks": [-26, -22, -18, -14, -10, -6, -2]},
}

# reference places for naming a low (name, lat, lon)
PLACES = [("جدة", 21.54, 39.17), ("مكة", 21.42, 39.83), ("ينبع", 24.09, 38.06), ("الوجه", 26.23, 36.47),
          ("ضباء", 27.35, 35.69), ("تبوك", 28.38, 36.57), ("المدينة", 24.47, 39.61), ("الليث", 20.15, 40.27),
          ("القنفذة", 19.13, 41.08), ("جازان", 16.89, 42.55), ("أبها", 18.22, 42.50), ("نجران", 17.49, 44.13),
          ("الطائف", 21.27, 40.42), ("الباحة", 20.01, 41.47), ("الرياض", 24.71, 46.68), ("بريدة", 26.33, 43.97),
          ("حائل", 27.52, 41.69), ("الجوف", 29.97, 40.21), ("عرعر", 30.98, 41.04), ("الدمام", 26.43, 50.10),
          ("الأحساء", 25.38, 49.59), ("وادي الدواسر", 20.47, 44.78), ("شرورة", 17.47, 47.11), ("بيشة", 20.0, 42.6),
          ("بورتسودان", 19.6, 37.2), ("الخرطوم", 15.6, 32.5), ("أسوان", 24.1, 32.9), ("الغردقة", 27.26, 33.81),
          ("صنعاء", 15.35, 44.2), ("عدن", 12.8, 45.03), ("الحديدة", 14.8, 42.95), ("أسمرة", 15.33, 38.93),
          ("مسقط", 23.6, 58.4), ("أبوظبي", 24.45, 54.38), ("الكويت", 29.37, 47.98), ("البصرة", 30.5, 47.8),
          ("بغداد", 33.3, 44.4), ("عمّان", 31.95, 35.93), ("المكلا", 14.54, 49.12), ("سيئون", 15.94, 48.79)]
DIR8 = ["شمال", "شمال شرق", "شرق", "جنوب شرق", "جنوب", "جنوب غرب", "غرب", "شمال غرب"]
AR = str.maketrans("0123456789-.", "٠١٢٣٤٥٦٧٨٩−٫")


def cut(a, lat, lon):
    s, n, w, e = BOX
    j = (lat >= s) & (lat <= n)
    i = (lon >= w) & (lon <= e)
    return a[np.ix_(j, i)], lat[j], lon[i]


def fields(gfs_fields, cycle, fh, static=None):
    """GFS 0.25 fields of one forecast hour cut to BOX; static (hgt, land) fetched once and passed back in"""
    f = gfs_fields(cycle, fh, res="0p25", fields=FIELDS + ([] if static else STATIC))
    la = np.linspace(90, -90, f["u10"].shape[0])
    lo = np.linspace(0, 360, f["u10"].shape[1], endpoint=False)
    out = {}
    for k, a in f.items():
        out[k], lat, lon = cut(a, la, lo)
    out["lat"], out["lon"] = lat, lon
    out["t5"] = out["t5"] - 273.15
    out["mslp"] = out["mslp"] / 100.0
    # the sea-level pressure 12 hours later (3 AM Makkah): the Red Sea trough is judged on the mean of the two, since
    # the afternoon heat lowers the pressure over Arabia and hides it at 12 UTC alone (24 Nov 2022, Jeddah floods)
    try:
        g = gfs_fields(cycle, fh + 12, res="0p25", fields=[("mslp", r":MSLET:mean sea level:")])
        out["mslp2"] = cut(g["mslp"], la, lo)[0] / 100.0
    except Exception as e:  # noqa: BLE001
        print("pressure 12 h later unavailable", fh + 12, repr(e)[:100], flush=True)
    if static:
        out.update(static)
    out["conv"] = convergence(out["u10"], out["v10"], lat, abs(float(lon[1] - lon[0])))
    return out


def convergence(u, v, lat, dlon):
    """-div(u, v) in 10^-5 /s on a lat (decreasing) x lon grid"""
    from scipy.ndimage import gaussian_filter
    a = 6.371e6
    phi = np.radians(lat)[:, None]
    d = np.radians(dlon)
    u, v = gaussian_filter(u, SMOOTH), gaussian_filter(v, SMOOTH)
    dudx = np.gradient(u, d, axis=1) / (a * np.cos(phi))
    dvdy = np.gradient(v * np.cos(phi), -d, axis=0) / (a * np.cos(phi))
    return -(dudx + dvdy) * 1e5


def _red_sea(la, lo):
    """a rough outline of the Red Sea, its two gulfs and Bab al-Mandab"""
    if 12.3 <= la <= 30.0 and 32.2 <= lo <= 43.6:
        # the sea runs NW-SE: its axis from (27.5N, 34.0E) to (13.0N, 43.0E)
        axis = 34.0 + (27.5 - la) * (9.0 / 14.5)
        return abs(lo - axis) <= 2.3 or (la >= 27.5 and lo <= 35.2)
    return False


def _where(la, lo):
    """«غرب جدة» from the nearest reference place"""
    best = None
    for name, y, x in PLACES:
        d = math.hypot((x - lo) * math.cos(math.radians(la)), y - la) * 111
        if best is None or d < best[0]:
            best = (d, name, y, x)
    d, name, y, x = best
    if d < 40:
        return f"قرب {name}"
    b = math.degrees(math.atan2((lo - x) * math.cos(math.radians(la)), la - y)) % 360
    return f"{DIR8[int((b + 22.5) // 45) % 8]} {name}"


def lows(f):
    """surface lows in the map: a smoothed sea-level pressure minimum enclosed by the isobar 1 hPa above it
    (0.5 hPa: a weak low), centre on ground below 1000 m (the sea-level pressure over high ground is a reduction
    and makes false lows), inside the map."""
    from scipy.ndimage import gaussian_filter, minimum_filter, label
    lat, lon = f["lat"], f["lon"]
    p = gaussian_filter(f["mslp"], 2.0)
    mins = (p == minimum_filter(p, size=13, mode="nearest"))
    w, e, s, n = EXTENT
    out = []
    for j, i in zip(*np.nonzero(mins)):
        la, lo = float(lat[j]), float(lon[i])
        if not (s + 0.5 <= la <= n - 0.5 and w + 0.5 <= lo <= e - 0.5):
            continue
        if f["hgt"][j, i] > 1000:
            continue
        p0 = float(p[j, i])
        best = None
        for dp in (1.0, 0.5):
            lab, _ = label(p < p0 + dp)
            reg = lab == lab[j, i]
            jj, ii = np.nonzero(reg)
            touches = jj.min() == 0 or ii.min() == 0 or jj.max() == p.shape[0] - 1 or ii.max() == p.shape[1] - 1
            wide = (jj.max() - jj.min()) * 0.25 > 12 or (ii.max() - ii.min()) * 0.25 > 14
            if not touches and not wide:
                best = dp
                break
        if best is None:
            continue
        sea = f["land"][j, i] < 0.5
        rs = sea and _red_sea(la, lo)
        place = ("فوق البحر الأحمر" if rs else "فوق الخليج العربي" if sea and lo > 47 and la > 23.5
                 else "فوق البحر" if sea else "فوق اليابسة")
        out.append({"lat": round(la, 2), "lon": round(lo, 2), "p": int(round(float(f["mslp"][j, i]))),
                    "sea": "red" if rs else ("sea" if sea else "land"), "where": f"{place} {_where(la, lo)}",
                    "closed": best == 1.0})
    out.sort(key=lambda x: x["p"])
    return out[:4]


def legend(kind):
    sc = SCALES[kind]
    stops = [{"p": p, "c": c[:7]} for p, c in sc["cols"]]
    if kind == "kconv":   # the bar starts where the colour starts (1.6)
        stops = [{"p": round((p - 0.2) / 0.8, 3), "c": c[:7]} for p, c in sc["cols"] if p >= 0.2]
        return {"label": sc["label"], "unit": sc["unit"], "vmin": 1.6, "vmax": 8, "ticks": [2, 4, 6, 8], "stops": stops}
    return {"label": sc["label"], "unit": sc["unit"], "vmin": sc["vmin"], "vmax": sc["vmax"], "ticks": sc["ticks"],
            "stops": stops}


def draw(path, kind, f, lws=(), trough=None, width_px=1000):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.colors import LinearSegmentedColormap, to_rgba
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from scipy.ndimage import zoom, gaussian_filter
    import figures as F
    fam = F._ar_font()
    sc = SCALES[kind]
    w, e, s, n = EXTENT
    # cut to the map (with a small margin), so every contour label falls inside the picture
    jm = (f["lat"] >= s - 0.75) & (f["lat"] <= n + 0.75)
    im = (f["lon"] >= w - 0.75) & (f["lon"] <= e + 0.75)
    f = {k: (v[np.ix_(jm, im)] if getattr(v, "ndim", 0) == 2 else v) for k, v in f.items()}
    lat, lon = f["lat"][jm], f["lon"][im]
    dpi = 200
    fig_w = width_px / dpi
    fig = plt.figure(figsize=(fig_w, fig_w * (n - s) / (e - w)), dpi=dpi)
    fig.patch.set_facecolor("#0c1118")
    pc = ccrs.PlateCarree()
    ax = fig.add_axes([0, 0, 1, 1], projection=pc)
    ax.set_extent([w, e, s, n], crs=pc)
    try:
        from PIL import Image
        rw, re_, rs, rn = F.RELIEF["box"]
        rel = np.asarray(Image.open(F.RELIEF["path"]).convert("L"))
        ax.imshow(rel, extent=[rw, re_, rs, rn], origin="upper", cmap="gray", vmin=0, vmax=255, transform=pc,
                  interpolation="lanczos", zorder=0)
    except Exception as ex:
        print("relief unavailable:", str(ex)[:80])
        ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#c9c9c9")
        ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#4f4f4f")
    cmap = LinearSegmentedColormap.from_list("k", [(p, to_rgba(c)) for p, c in sc["cols"]], N=512)
    up = 4
    field = {"krh7": "rh7", "krh5": "rh5", "kconv": "conv", "kt5": "t5"}[kind]
    a = f[field]
    if kind == "kconv":
        a = np.clip(a, 0, None)
    fine = zoom(a, up, order=3)
    flo = np.linspace(lon[0], lon[-1], fine.shape[1])
    fla = np.linspace(lat[0], lat[-1], fine.shape[0])
    ax.imshow(fine, extent=[lon[0], lon[-1], lat[-1], lat[0]], origin="upper", cmap=cmap, vmin=sc["vmin"],
              vmax=sc["vmax"], alpha=0.78 if kind != "kconv" else 0.92, transform=pc, interpolation="bilinear",
              zorder=1)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.55, edgecolor="#1d232a", alpha=0.75, zorder=2)
    ax.coastlines(resolution="50m", linewidth=0.6, color="#1d232a", alpha=0.9, zorder=2)
    halo = [pe.withStroke(linewidth=2.2, foreground="#10161d")]
    dig = lambda x: ("\u200e" if x < 0 else "") + f"{int(round(x))}".translate(AR)   # LRM: the minus stays in front
    if kind in ("krh7", "krh5"):
        cs = ax.contour(flo, fla, gaussian_filter(fine, 3), levels=[50, 70, 90], colors=["#f4efe2", "#d8f3dc", "#ffffff"],
                        linewidths=[0.7, 0.9, 1.1], transform=pc, zorder=3)
        lab = ax.clabel(cs, fmt=lambda x: dig(x) + "٪", fontsize=7, inline=True, inline_spacing=3)
    elif kind == "kt5":
        lv = np.arange(-40, 6, 1)
        cs = ax.contour(flo, fla, gaussian_filter(fine, 3), levels=lv, colors="#f4f6f8",
                        linewidths=[0.95 if x % 2 == 0 else 0.4 for x in lv], linestyles="solid", transform=pc, zorder=3)
        lab = ax.clabel(cs, levels=lv[lv % 2 == 0], fmt=dig, fontsize=7.5, inline=True, inline_spacing=3)
    else:
        lab = []
        # the 10 m wind (thin dark streamlines) and the sea-level isobars every 2 hPa
        uu, vv = f["u10"][::-1], f["v10"][::-1]
        spd = np.hypot(uu, vv)
        ax.streamplot(lon, lat[::-1], uu, vv, color=(0.93, 0.95, 0.97, 0.75),
                      linewidth=np.clip(0.35 + 0.9 * spd / 10, 0.35, 1.3), density=(2.2, 2.0), arrowsize=0.55,
                      minlength=0.2, transform=pc, zorder=3)
        pm = gaussian_filter(f["mslp"], 2.0)
        lv = np.arange(990, 1040, 2)
        cs = ax.contour(lon, lat, pm, levels=lv, colors="#1b2229", linewidths=0.75, alpha=0.85, transform=pc, zorder=3)
        lab = ax.clabel(cs, levels=lv[lv % 4 == 0], fmt=dig, fontsize=7, inline=True, inline_spacing=3)
        for t in lab:
            t.set_color("#e9edf1")
        if trough:
            xs = [q[1] for q in trough["pts"]]
            ys = [q[0] for q in trough["pts"]]
            ax.plot(xs, ys, color="#5fd4ff", linewidth=2.6, linestyle=(0, (6, 3.5)), transform=pc, zorder=5.5,
                    path_effects=[pe.withStroke(linewidth=4.6, foreground="#10161d")], solid_capstyle="round")
            ax.plot([xs[-1]], [ys[-1]], marker="^", markersize=8, color="#5fd4ff", markeredgecolor="#10161d",
                    markeredgewidth=1.2, transform=pc, zorder=5.6)
            # the name beside the line, west of it, south of Jeddah, where it fits inside the map
            cand = [k for k in range(len(xs)) if ys[k] <= 20.5 and xs[k] >= w + 5.4]
            m = cand[-1] if cand else len(xs) // 2
            ax.text(xs[m] - 0.45, ys[m], "أخدود البحر الأحمر", transform=pc, ha="right", va="center",
                    fontsize=9.5, fontfamily=fam, fontweight="bold", color="#5fd4ff",
                    path_effects=[pe.withStroke(linewidth=3.2, foreground="#10161d")], zorder=6)
        for lw_ in lws:
            x, y = lw_["lon"], lw_["lat"]
            col = "#ff4d4d" if lw_["closed"] else "#ff9a7a"
            ax.plot([x], [y], marker="o", markersize=6, color=col, markeredgecolor="#10161d", markeredgewidth=1.3,
                    transform=pc, zorder=6)
            # beside the dot when a city label sits just above it
            side = any(abs(cx - x) < 1.3 and 0 < cy - y < 1.2 for _, cy, cx, _, _ in F.SAUDI_CITIES)
            tx, ty, tha, tva = (x + 0.3, y, "left", "center") if side else (x, y + 0.35, "center", "bottom")
            ax.text(tx, ty, "منخفض" if lw_["closed"] else "منخفض ضعيف", transform=pc, ha=tha, va=tva,
                    fontsize=10.5, fontfamily=fam, fontweight="bold", color=col,
                    path_effects=[pe.withStroke(linewidth=3.2, foreground="#10161d")], zorder=6)
            ax.text(x, y - 0.35, dig(lw_["p"]), transform=pc, ha="center", va="top", fontsize=9, fontfamily=fam,
                    fontweight="bold", color="#ffffff", path_effects=[pe.withStroke(linewidth=3, foreground="#10161d")],
                    zorder=6)
    for t in lab:
        t.set_fontfamily(fam)
        t.set_fontweight("bold")
        if kind != "kconv":
            t.set_color("#ffffff")
        t.set_path_effects(halo)
    # places
    for name, y, x, kd in F.WAVE_PLACES:
        if not (w + 1.5 < x < e - 1.5 and s + 0.8 < y < n - 0.8):
            continue
        if trough and name == "البحر الأحمر":   # the trough line runs over it and carries the sea's name
            continue
        ax.text(x, y, F._rtl(name), transform=pc, ha="center", va="center", fontsize=8, fontfamily=fam,
                fontweight="bold", color="#e3e7eb" if kd == "sea" else "#22272d", alpha=0.85,
                path_effects=[pe.withStroke(linewidth=2, foreground="#3a3f45" if kd == "sea" else "#eef0f2")], zorder=5)
    for name, y, x, where, big in F.SAUDI_CITIES:
        if not big and name not in ("الطائف", "نجران", "الباحة", "بريدة", "ينبع"):
            continue
        ax.plot([x], [y], marker="o", markersize=3.2, color="#ffffff", markeredgecolor="#111111", markeredgewidth=0.8,
                transform=pc, zorder=5)
        where = {"الدمام": "w"}.get(name, where)   # the Gulf's name sits north of it
        dx, dy, ha, va = {"n": (0, 0.22, "center", "bottom"), "s": (0, -0.22, "center", "top"),
                          "e": (0.25, 0, "left", "center"), "w": (-0.25, 0, "right", "center")}[where]
        ax.text(x + dx, y + dy, F._rtl(name), transform=pc, ha=ha, va=va, fontsize=8, fontfamily=fam,
                fontweight="bold", color="#111111", path_effects=[pe.withStroke(linewidth=2, foreground="#ffffff")],
                zorder=5)
    ax.spines["geo"].set_visible(False)
    F._save_png(fig, path)


# ------------------------------------------------------------------ the Red Sea trough (Fahad, 17 Nov 2026)
# The low pressure of Sudan and the southern Red Sea reaching north along the sea as a tongue (often not a closed low,
# so the lows above miss it); it carries the southern moisture north toward Jeddah and Makkah. Every 0.5 deg of
# latitude from 14 N, the lowest sea-level pressure over the sea (within 2.3 deg of its axis) is compared with the
# land beside it: Arabia 3-7 deg east of the axis (ground < 1100 m, the Sarawat left out) and Africa 3-6.5 deg west
# (ground < 800 m). The tongue runs north from 14 N while the sea stays at least RST_DP lower than Arabia (one
# missing row allowed); it counts as the Red Sea trough when it reaches 18 N and in two rows or more the sea is
# lower than Africa too (a real tongue, not only the Sudan low's flank). Its north end is how far it reaches.
# Checked: 24 Nov 2022 (Jeddah floods) reaches the north of the sea; 16 Nov 2026 reaches Yanbu's latitude; 10 Nov
# 2026 none.
RST_DP = 0.5
COAST = [(16.89, "جازان"), (18.2, "الشقيق"), (19.13, "القنفذة"), (20.15, "الليث"), (21.54, "جدة"), (22.8, "رابغ"),
         (24.09, "ينبع"), (25.05, "أملج"), (26.23, "الوجه"), (27.35, "ضباء"), (28.5, "شمال البحر الأحمر")]


def rst(f, log=None):
    from scipy.ndimage import gaussian_filter
    lat, lon = f["lat"], f["lon"]
    p = gaussian_filter((f["mslp"] + f["mslp2"]) / 2 if "mslp2" in f else f["mslp"], 2.0)
    rows = []
    for la in np.arange(14.0, 29.01, 0.5):
        j = int(np.argmin(np.abs(lat - la)))
        axis = 34.0 + (27.5 - la) * (9.0 / 14.5)
        land, hgt = f["land"][j], f["hgt"][j]
        sea = [i for i in range(len(lon)) if land[i] < 0.5 and abs(lon[i] - axis) <= 2.3]
        wl = [i for i in range(len(lon)) if land[i] >= 0.5 and axis - 6.5 <= lon[i] <= axis - 3.0 and hgt[i] < 800]
        el = [i for i in range(len(lon)) if land[i] >= 0.5 and axis + 3.0 <= lon[i] <= axis + 7.0 and hgt[i] < 1100]
        if not (sea and len(wl) >= 3 and len(el) >= 3):
            rows.append((float(la), None, None, None))
            continue
        im = min(sea, key=lambda i: p[j, i])
        dw, de = float(np.mean(p[j, wl]) - p[j, im]), float(np.mean(p[j, el]) - p[j, im])
        if log:
            log(f"rst {la:.1f} lon {lon[im]:.2f} p {p[j, im]:.1f} africa +{dw:.1f} arabia +{de:.1f}")
        rows.append((float(la), float(np.mean(lon[sea])), dw, de))   # drawn along the middle of the sea
    pts, tongue, miss = [], 0, 0
    for la, lo, dw, de in rows:
        if de is not None and de >= RST_DP:
            pts.append([la, lo]); miss = 0
            tongue += dw >= RST_DP
        else:
            miss += 1
            if miss > 1:
                break
    if not pts or pts[-1][0] < 18.0 or tongue < 2:
        return None
    # a smooth line: the running mean of the longitudes
    los = [x[1] for x in pts]
    for k in range(len(pts)):
        pts[k][1] = float(np.mean(los[max(0, k - 2):k + 3]))
    north = pts[-1][0]
    near = min(COAST, key=lambda c: abs(c[0] - north))
    reach = near[1] if near[1].startswith("شمال") else f"محاذاة {near[1]}"
    return {"pts": [[round(a, 2), round(b, 2)] for a, b in pts], "north": round(north, 1), "reach": reach}
