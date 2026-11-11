"""Smooth static maps for the warm/cold event index (equirectangular, coastlines, white streamlines)."""
import os
import numpy as np

# (position 0..1 along the value range, colour)
SCALES = {
    "wc": {"vmin": -12, "vmax": 12, "cols": [(0, "#0c1238"), (.13, "#1a3f99"), (.27, "#3f7fc2"), (.4, "#9cc1df"), (.5, "#eef0f1"),
                                             (.6, "#e8c1b4"), (.73, "#cf765e"), (.87, "#a3202a"), (1, "#3a0612")],
           "label": "مؤشر الحدث الدافئ والبارد", "unit": "مليون م²/ث", "ticks": [-12, -8, -4, 0, 4, 8, 12]},
    "wcd": {"vmin": -6, "vmax": 6, "cols": [(0, "#203f74"), (.2, "#5f8fca"), (.4, "#c9daec"), (.5, "#f6f2ea"), (.62, "#f7dca6"),
                                            (.76, "#ef9a48"), (.9, "#c2441d"), (1, "#5a0c10")],
            "label": "تغير المؤشر خلال ٢٤ ساعة", "unit": "مليون م²/ث", "ticks": [-6, -4, -2, 0, 2, 4, 6]},
    "pw": {"vmin": 0, "vmax": 300, "cols": [(0, "#8c5a2b"), (.17, "#d9b98a"), (.333, "#f4efe6"), (.42, "#bfe6b6"), (.5, "#5cc28a"),
                                            (.6, "#2a9fb5"), (.72, "#2a63d0"), (.85, "#5b2fa8"), (1, "#2b0f55")],
           "label": "الماء القابل للهطول نسبة إلى المعدل", "unit": "٪", "ticks": [0, 50, 100, 150, 200, 250, 300]},
}


# main cities of the Kingdom, drawn on the regional maps so the lines can be placed at a glance
# main cities of the Kingdom, drawn on the regional maps so the lines can be placed at a glance:
# (name, lat, lon, where the label goes: n/s/e/w, shown on the wide wave map too)
SAUDI_CITIES = [("مكة", 21.42, 39.83, "e", True), ("جدة", 21.54, 39.17, "w", True), ("المدينة", 24.47, 39.61, "n", True),
                ("الرياض", 24.71, 46.68, "n", True), ("الدمام", 26.43, 50.10, "n", True), ("أبها", 18.22, 42.50, "e", True),
                ("جازان", 16.89, 42.55, "w", True), ("تبوك", 28.38, 36.57, "n", True), ("حائل", 27.52, 41.69, "e", True),
                ("سكاكا", 29.97, 40.21, "n", True), ("الطائف", 21.27, 40.42, "s", False), ("نجران", 17.49, 44.13, "e", False),
                ("الباحة", 20.01, 41.47, "s", False), ("بريدة", 26.33, 43.97, "s", False), ("ينبع", 24.09, 38.06, "w", False),
                ("عرعر", 30.98, 41.04, "n", False), ("وادي الدواسر", 20.47, 44.78, "e", False), ("الأحساء", 25.38, 49.59, "s", False)]


def draw_cities(ax, transform, fontsize=6.0, wide=False):
    from matplotlib import patheffects as pe
    halo = [pe.withStroke(linewidth=2.2, foreground="white")]
    gap = 0.45 if wide else 0.3
    for name, la, lo, where, on_wide in SAUDI_CITIES:
        if wide and not on_wide:
            continue
        ax.plot(lo, la, marker="o", markersize=2.4, color="#1b1b1b", markeredgecolor="white", markeredgewidth=0.5,
                transform=transform, zorder=7)
        dx, dy, ha, va = {"n": (0, gap, "center", "bottom"), "s": (0, -gap, "center", "top"),
                          "e": (gap, 0, "left", "center"), "w": (-gap, 0, "right", "center")}[where]
        ax.text(lo + dx, la + dy, _ar(name), transform=transform, ha=ha, va=va, fontsize=fontsize,
                color="#1b1b1b", path_effects=halo, zorder=7)


def _cmap(cols):
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("c", cols, N=512)


def legend(kind):
    sc = SCALES[kind]
    return {"label": sc["label"], "unit": sc["unit"], "vmin": sc["vmin"], "vmax": sc["vmax"], "ticks": sc["ticks"],
            "stops": [{"p": p, "c": c} for p, c in sc["cols"]]}


def _ar(text):
    """Arabic for matplotlib: new versions shape and order Arabic themselves; older ones need help."""
    try:
        import matplotlib
        if tuple(int(x) for x in matplotlib.__version__.split(".")[:2]) >= (3, 10):
            return text
    except Exception:
        pass
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def lon_label(x):
    x = ((x + 180) % 360) - 180
    if x == 0 or abs(x) == 180:
        return f"{int(abs(x))}°"
    return f"{int(abs(x))}°{'E' if x > 0 else 'W'}"


def lat_label(y):
    if y == 0:
        return "EQ"
    return f"{int(abs(y))}°{'N' if y > 0 else 'S'}"


def draw(path, field, lat, lon, kind, extent, stream=None, width_px=1600):
    """field on lat (descending) x lon (0..359 or a sub-range); extent = (west, east, south, north) in degrees."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sc = SCALES[kind]
    cmap, vmin, vmax = _cmap(sc["cols"]), sc["vmin"], sc["vmax"]
    w, e, s, n = extent
    aspect = (e - w) / (n - s)
    fig_w = width_px / 200
    fig = plt.figure(figsize=(fig_w, fig_w / aspect + 0.45), dpi=200)
    fig.patch.set_facecolor("#f7f5f0")
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        proj = ccrs.PlateCarree(central_longitude=(w + e) / 2)
        lm = 75 / width_px
        ax = fig.add_axes([lm, 0.09, 0.99 - lm, 0.89], projection=proj)
        ax.set_extent([w, e, s, n], crs=ccrs.PlateCarree())
        tr = {"transform": ccrs.PlateCarree()}
        have_cartopy = True
    except Exception:
        lm = 75 / width_px
        ax = fig.add_axes([lm, 0.09, 0.99 - lm, 0.89])
        ax.set_xlim(w, e); ax.set_ylim(s, n)
        tr = {}
        have_cartopy = False
    # wrap so the image is continuous across the 0/360 seam
    if lon[-1] - lon[0] > 350:
        lon_p = np.append(lon, lon[0] + 360)
        f = np.hstack([field, field[:, :1]])
    else:
        lon_p, f = lon, field
    # draw from a finely interpolated copy so the colours blend smoothly at any size
    from scipy.ndimage import zoom
    up = max(1, int(np.ceil(width_px * 1.2 / f.shape[1])))
    fine = zoom(np.nan_to_num(f), up, order=3)
    extra = {"regrid_shape": (fine.shape[0], fine.shape[1])} if tr else {}
    ax.imshow(fine, extent=[lon_p[0], lon_p[-1], lat[-1], lat[0]], origin="upper", cmap=cmap, vmin=vmin, vmax=vmax,
              interpolation="bilinear", **tr, **extra)
    if stream is not None:
        u, v = stream
        if lon[-1] - lon[0] > 350:
            u, v = np.hstack([u, u[:, :1]]), np.hstack([v, v[:, :1]])
        la = lat[::-1]
        uu, vv = u[::-1], v[::-1]
        spd = np.hypot(uu, vv)
        lw = 0.3 + 1.2 * spd / max(float(np.nanpercentile(spd, 98)), 1e-6)
        ax.streamplot(lon_p, la, uu, vv, color=(1, 1, 1, 0.85), linewidth=np.clip(lw, 0.3, 1.5),
                      density=(2.6, 0.85) if e - w > 200 else (1.4, 1.4), arrowsize=0.5, minlength=0.15, **tr)
    if have_cartopy:
        res = "110m" if kind != "pw" else "50m"
        try:  # load now, so a failed download does not break the drawing later
            import cartopy.io.shapereader as shp
            shp.natural_earth(resolution=res, category="physical", name="coastline")
            ax.coastlines(resolution=res, linewidth=0.55, color="#1b1b1b")
            if kind == "pw":
                shp.natural_earth(resolution=res, category="cultural", name="admin_0_boundary_lines_land")
                ax.add_feature(cfeature.BORDERS.with_scale(res), linewidth=0.4, edgecolor="#333333")
        except Exception as ex:
            print("coastlines unavailable:", str(ex)[:80])
        ax.spines["geo"].set_edgecolor("#999999")
    step_x = 60 if e - w > 200 else 10
    step_y = 15 if n - s > 60 else 10
    xt = np.arange(np.ceil(w / step_x) * step_x, e + 0.1, step_x)
    yt = np.arange(np.ceil(s / step_y) * step_y, n + 0.1, step_y)
    ax.set_xticks(xt, **({"crs": ccrs.PlateCarree()} if have_cartopy else {}))
    ax.set_yticks(yt, **({"crs": ccrs.PlateCarree()} if have_cartopy else {}))
    ax.set_xticklabels([lon_label(x) for x in xt], fontsize=7, color="#555555")
    ax.set_yticklabels([lat_label(y) for y in yt], fontsize=7, color="#555555")
    ax.tick_params(length=2.5, color="#999999")
    for y in yt:
        ax.plot([w, e], [y, y], color="#000000", alpha=0.08 if y else 0.25, linewidth=0.5, **tr)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    # keep the files small
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=200, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:
        pass


SCALES["wave"] = {"vmin": -60, "vmax": 60, "cols": [(0, "#0f3f7a"), (.18, "#2f78c4"), (.36, "#9ec6e8"), (.5, "#f4f2ec"),
                                                   (.64, "#f2b9ab"), (.82, "#d9533b"), (1, "#7a0f12")],
                  "label": "موجات الطبقة الوسطى (٥٠٠ هكتوباسكال)", "unit": "متر جيوديناميكي", "ticks": [-60, -40, -20, 0, 20, 40, 60]}


def draw_waves(path, zp, fx, fy, lat, lon, extent, marks, width_px=1500):
    """Wave height (filled + contours), H/L marks and wave-activity arrows over a regional map."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from scipy.ndimage import zoom
    sc = SCALES["wave"]
    w, e, s, n = extent
    j = (lat >= s - 2) & (lat <= n + 2)
    i = (lon >= w - 2) & (lon <= e + 2)
    la, lo = lat[j], lon[i]
    z = zp[np.ix_(j, i)]
    u, v = fx[np.ix_(j, i)], fy[np.ix_(j, i)]
    aspect = (e - w) / (n - s)
    fig_w = width_px / 200
    fig = plt.figure(figsize=(fig_w, fig_w / aspect + 0.4), dpi=200)
    fig.patch.set_facecolor("#f7f5f0")
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    pc = ccrs.PlateCarree()
    lm = 75 / width_px
    ax = fig.add_axes([lm, 0.08, 0.99 - lm, 0.9], projection=ccrs.PlateCarree(central_longitude=(w + e) / 2))
    ax.set_extent([w, e, s, n], crs=pc)
    up = 6
    fine = zoom(z, up, order=3)
    ax.imshow(fine, extent=[lo[0], lo[-1], la[-1], la[0]], origin="upper", cmap=_cmap(sc["cols"]), vmin=sc["vmin"],
              vmax=sc["vmax"], interpolation="bilinear", transform=pc, regrid_shape=fine.shape)
    try:
        import cartopy.io.shapereader as shp
        shp.natural_earth(resolution="50m", category="physical", name="coastline")
        ax.coastlines(resolution="50m", linewidth=0.5, color="#2a2a2a")
        shp.natural_earth(resolution="50m", category="cultural", name="admin_0_boundary_lines_land")
        ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.35, edgecolor="#555555")
    except Exception as ex:
        print("coastlines unavailable:", str(ex)[:80])
    levels = [x for x in range(-90, 91, 10) if x != 0]
    cs = ax.contour(lo, la, z, levels=levels, colors=["#1d4f8f" if x < 0 else "#9c2219" for x in levels],
                    linewidths=0.7, alpha=0.8, transform=pc)
    ax.clabel(cs, fmt=lambda x: f"{int(x)}", fontsize=6)
    ax.contour(lo, la, z, levels=[0], colors="#ffffff", linewidths=1.1, linestyles="dashdot", transform=pc)
    # wave-activity arrows, every 4 degrees where the flux matters
    st = 4
    mag = np.hypot(u, v)
    thr = max(float(np.nanpercentile(mag, 70)), 1e-6)
    sub = (slice(None, None, st), slice(None, None, st))
    U, V, M = u[sub], v[sub], mag[sub]
    LO, LA = np.meshgrid(lo[::st], la[::st])
    keep = M >= thr
    if keep.any():
        ref = float(np.nanpercentile(M[keep], 90))
        ax.quiver(LO[keep], LA[keep], U[keep] / ref, V[keep] / ref, transform=pc, color="#263238", alpha=0.75,
                  scale=28, width=0.0022, headwidth=4, headlength=4.5, zorder=4)
    halo = [pe.withStroke(linewidth=2.6, foreground="white")]
    for kind, y, x, val in marks:
        col = "#c62f22" if kind == "H" else "#1f6fc0"
        ax.text(x, y + 0.3, kind, transform=pc, ha="center", va="bottom", fontsize=15, fontweight="bold", color=col,
                path_effects=[pe.withStroke(linewidth=3, foreground="white")], zorder=6)
        ax.text(x, y - 0.2, f"{val:+.0f}", transform=pc, ha="center", va="top", fontsize=7.5, fontweight="bold",
                color=col, path_effects=halo, zorder=6)
    ax.spines["geo"].set_edgecolor("#999999")
    xt = np.arange(np.ceil(w / 10) * 10, e + 0.1, 10)
    yt = np.arange(np.ceil(s / 10) * 10, n + 0.1, 10)
    ax.set_xticks(xt, crs=pc); ax.set_yticks(yt, crs=pc)
    ax.set_xticklabels([lon_label(x) for x in xt], fontsize=7, color="#555555")
    ax.set_yticklabels([lat_label(y) for y in yt], fontsize=7, color="#555555")
    ax.tick_params(length=2.5, color="#999999")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=220, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:
        pass


SCALES["conv"] = {"vmin": 0, "vmax": 6, "cols": [(0, "#f6f3ec"), (.15, "#f6f3ec"), (.3, "#f9d77e"), (.5, "#f39a2b"), (.7, "#e04e1f"),
                                                (.85, "#b4162a"), (1, "#5c0a2a")],
                  "label": "التقاء الرياح عند ٩٢٥ هكتوباسكال", "unit": "×١٠⁻⁵ /ث", "ticks": [0, 1, 2, 3, 4, 5, 6]}


def draw_conv(path, conv, the, u, v, ground, lat, lon, extent, width_px=1300):
    """Where air meets at 925 hPa: convergence shaded, equivalent potential temperature contours, wind streamlines.
    Where the ground is higher than 925 hPa (the Hijaz highlands) the level is underground and is greyed out."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from scipy.ndimage import zoom
    sc = SCALES["conv"]
    w, e, s, n = extent
    pc = ccrs.PlateCarree()
    fig_w = width_px / 200
    fig = plt.figure(figsize=(fig_w, fig_w * (n - s) / (e - w) + 0.4), dpi=200)
    fig.patch.set_facecolor("#f7f5f0")
    lm = 75 / width_px
    ax = fig.add_axes([lm, 0.08, 0.99 - lm, 0.9], projection=ccrs.PlateCarree(central_longitude=(w + e) / 2))
    ax.set_extent([w, e, s, n], crs=pc)
    c = np.where(ground, np.nan, np.clip(conv, 0, None))
    fine = zoom(np.nan_to_num(c, nan=0), 4, order=1)
    ax.imshow(fine, extent=[lon[0], lon[-1], lat[-1], lat[0]], origin="upper", cmap=_cmap(sc["cols"]), vmin=sc["vmin"],
              vmax=sc["vmax"], interpolation="bilinear", transform=pc, regrid_shape=fine.shape)
    g = np.where(ground, 1.0, np.nan)
    ax.contourf(lon, lat, g, levels=[0.5, 1.5], colors=["#bdbab3"], alpha=0.85, transform=pc, zorder=3)
    try:
        import cartopy.io.shapereader as shp
        shp.natural_earth(resolution="50m", category="physical", name="coastline")
        ax.coastlines(resolution="50m", linewidth=0.6, color="#1b1b1b", zorder=5)
        shp.natural_earth(resolution="50m", category="cultural", name="admin_0_boundary_lines_land")
        ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.35, edgecolor="#555555", zorder=5)
    except Exception as ex:
        print("coastlines unavailable:", str(ex)[:80])
    cs = ax.contour(lon, lat, the, levels=np.arange(300, 372, 4), cmap="viridis", linewidths=0.8, alpha=0.9,
                    transform=pc, zorder=4)
    ax.clabel(cs, fmt=lambda x: f"{int(x)}", fontsize=5.5)
    la, uu, vv = lat[::-1], u[::-1], v[::-1]
    ax.streamplot(lon, la, uu, vv, color="#2b3440", linewidth=0.6, density=(1.6, 1.4), arrowsize=0.6, transform=pc,
                  zorder=6)
    ax.spines["geo"].set_edgecolor("#999999")
    xt = np.arange(np.ceil(w / 5) * 5, e + 0.1, 5)
    yt = np.arange(np.ceil(s / 5) * 5, n + 0.1, 5)
    ax.set_xticks(xt, crs=pc); ax.set_yticks(yt, crs=pc)
    ax.set_xticklabels([lon_label(x) for x in xt], fontsize=7, color="#555555")
    ax.set_yticklabels([lat_label(y) for y in yt], fontsize=7, color="#555555")
    ax.tick_params(length=2.5, color="#999999")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=230, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:
        pass


def draw_ar(path, k, data, lat, lon, qu, qv, mag, width_px=1500):
    """Atmospheric river map at step k: transport in categories, its arrows, the tracks of the river cores with
    a date every day, and below it the strength of each core and the largest transport over the Kingdom."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from datetime import datetime
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from scipy.ndimage import zoom
    import ar as AR
    s, n, w, e = AR.BOX[0], AR.BOX[1], AR.BOX[2], AR.BOX[3]
    pc = ccrs.PlateCarree()
    tt = lambda x: datetime.strptime(x, "%Y-%m-%dT%H:%MZ")
    times = [tt(x) for x in data["times"]]
    fig_w = width_px / 200
    map_h = fig_w * 0.97 * (n - s) / (e - w)
    top_h, cbar_h, ser_h = 0.42, 0.42, 1.45
    H = top_h + map_h + cbar_h + ser_h + 0.15
    fig = plt.figure(figsize=(fig_w, H), dpi=200)
    fig.patch.set_facecolor("#ffffff")
    y = lambda inches: inches / H
    ax = fig.add_axes([0.06, y(cbar_h + ser_h + 0.15), 0.92, y(map_h)], projection=ccrs.PlateCarree(central_longitude=(w + e) / 2))
    ax.set_extent([w, e, s, n], crs=pc)
    try:
        import cartopy.io.shapereader as shp
        shp.natural_earth(resolution="50m", category="physical", name="land")
        ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#e9edf1", edgecolor="none", zorder=0)
    except Exception as ex:
        print("land unavailable:", str(ex)[:80])
    m = mag[k]
    fine = zoom(m, max(1, int(round(3 * abs(lon[1] - lon[0]) / 0.5))), order=1)
    la_f = np.linspace(lat[0], lat[-1], fine.shape[0])
    lo_f = np.linspace(lon[0], lon[-1], fine.shape[1])
    cmap = ListedColormap(AR.CAT_COLS)
    norm = BoundaryNorm(AR.CATS + [10000], cmap.N)
    ax.contourf(lo_f, la_f, np.where(fine >= AR.CATS[0], fine, np.nan), levels=AR.CATS + [10000], cmap=cmap, norm=norm,
                transform=pc, zorder=1, alpha=0.92)
    try:
        import cartopy.io.shapereader as shp
        shp.natural_earth(resolution="50m", category="physical", name="coastline")
        ax.coastlines(resolution="50m", linewidth=0.5, color="#4a5560", zorder=3)
        shp.natural_earth(resolution="50m", category="cultural", name="admin_0_boundary_lines_land")
        ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.3, edgecolor="#7a8590", zorder=3)
    except Exception as ex:
        print("coastlines unavailable:", str(ex)[:80])
    # transport arrows every 2 degrees where it is a river or close to one
    st = max(1, int(round(2.0 / abs(lon[1] - lon[0]))))
    LO, LA = np.meshgrid(lon[::st], lat[::st])
    U, V, M = qu[k][::st, ::st], qv[k][::st, ::st], m[::st, ::st]
    keep = M >= 120
    if keep.any():
        ax.quiver(LO[keep], LA[keep], U[keep], V[keep], transform=pc, color="#1b1b1b", scale=26000, width=0.0016,
                      headwidth=3.6, headlength=4, zorder=4, alpha=0.85)
    halo = [pe.withStroke(linewidth=2.2, foreground="white")]
    cols = {"main": "#111111", "near": "#0b7a53"}
    t_now = times[k]
    for tr in data["tracks"]:
        pts = tr["pts"]
        if len(pts) < 2:
            continue
        c = cols.get(tr["kind"], "#111111")
        xs, ys = [p["lon"] for p in pts], [p["lat"] for p in pts]
        ax.plot(xs, ys, color="white", linewidth=3.0, transform=pc, zorder=5, solid_capstyle="round")
        ax.plot(xs, ys, color=c, linewidth=1.5, transform=pc, zorder=6, solid_capstyle="round")
        last_lab = None
        for p in pts:
            t = tt(p["t"])
            if t.hour != times[0].hour:
                continue
            if last_lab and np.hypot(p["lon"] - last_lab[0], p["lat"] - last_lab[1]) < 2.2:
                continue
            ax.plot(p["lon"], p["lat"], marker="o", markersize=2.6, color=c, transform=pc, zorder=7)
            ax.text(p["lon"] + 0.5, p["lat"] + 0.55, f"{t:%b %d}\n{t:%H}Z", transform=pc, fontsize=4.6, ha="left",
                    va="bottom", color="#111111", linespacing=0.95, zorder=8,
                    bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": c, "lw": 0.4, "alpha": 0.9})
            last_lab = (p["lon"], p["lat"])
        now = [p for p in pts if p["k"] == k]
        if now:
            ax.plot(now[0]["lon"], now[0]["lat"], marker="*", markersize=11, color="#ffd23f", markeredgecolor="#111111",
                    markeredgewidth=0.7, transform=pc, zorder=9)
    ax.spines["geo"].set_edgecolor("#9aa3ab")
    xt = np.arange(np.ceil(w / 20) * 20, e + 0.1, 20)
    yt = np.arange(np.ceil(s / 10) * 10, n + 0.1, 10)
    ax.set_xticks(xt, crs=pc); ax.set_yticks(yt, crs=pc)
    ax.set_xticklabels([lon_label(x) for x in xt], fontsize=6.5, color="#444444")
    ax.set_yticklabels([lat_label(v) for v in yt], fontsize=6.5, color="#444444")
    ax.tick_params(length=2.5, color="#9aa3ab")
    for v in yt:
        ax.plot([w, e], [v, v], color="#000000", alpha=0.06 if v else 0.2, linewidth=0.5, transform=pc, zorder=2)
    run = datetime.strptime(data["cycle"], "%Y%m%d%H")
    fig.text(0.5, 1 - y(0.16), "Atmospheric River Tracking — Indian Ocean & Arabia", ha="center", va="center",
             fontsize=9, fontweight="bold", color="#1b2a3a")
    fig.text(0.5, 1 - y(0.33), f"GFS {data.get('res', '0p50').replace('0p', '0.')}° · Run {run:%HZ %d %b %Y} · Valid {t_now:%a %d %b %Y %H:%M} UTC (+{k * data['step_h']}h) · "
             "IVT 1000–600 hPa (kg m⁻¹ s⁻¹)", ha="center", va="center", fontsize=5.8, color="#4a5560")
    # category bar
    cax = fig.add_axes([0.12, y(ser_h + 0.15 + 0.17), 0.80, y(0.11)])
    for j, col in enumerate(AR.CAT_COLS):
        cax.add_patch(plt.Rectangle((j, 0), 1, 1, color=col))
        hi = AR.CATS[j + 1] - 1 if j + 1 < len(AR.CATS) else None
        cax.text(j + 0.5, -0.25, f"{AR.CATS[j]}–{hi}" if hi else f"≥{AR.CATS[j]}", ha="center", va="top", fontsize=5.3,
                 color="#333333")
    cax.set_xlim(0, len(AR.CAT_COLS)); cax.set_ylim(0, 1); cax.axis("off")
    # strength of the cores and the largest transport over the Kingdom
    sx = fig.add_axes([0.09, y(0.32), 0.88, y(ser_h - 0.36)])
    names = {"main": "Main river core", "near": "River near Saudi Arabia"}
    for tr in data["tracks"]:
        if len(tr["pts"]) < 2:
            continue
        sx.plot([tt(p["t"]) for p in tr["pts"]], [p["v"] for p in tr["pts"]], color=cols.get(tr["kind"], "#111111"),
                linewidth=1.1, marker="o", markersize=1.2, label=names.get(tr["kind"], tr["kind"]))
    sx.plot(times, [r["v"] for r in data["sa"]], color="#2f6fc0", linewidth=1.0, linestyle="--",
            label="Max over Saudi land")
    sx.axhline(AR.THR_CORE, color="#999999", linewidth=0.6, linestyle=":")
    sx.axvline(t_now, color="#d13b2e", linewidth=0.9)
    sx.set_xlim(times[0], times[-1])
    sx.set_ylim(0, max(700, max([p["v"] for tr in data["tracks"] for p in tr["pts"]] + [r["v"] for r in data["sa"]]) * 1.1))
    import matplotlib.dates as mdates
    sx.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    sx.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    sx.tick_params(labelsize=5.8, length=2, colors="#444444")
    sx.set_ylabel("IVT", fontsize=6, color="#444444")
    for sp in ("top", "right"):
        sx.spines[sp].set_visible(False)
    sx.grid(axis="y", alpha=0.2, linewidth=0.5)
    sx.legend(fontsize=5.3, loc="upper left", frameon=False, ncol=3)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=200, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:
        pass


def mjo_scales(zmax, rmax):
    """The MJO component maps (800 hPa height, rain): scales set from the day's range, rounded."""
    def nice(x, steps):
        return next((v for v in steps if v >= x), steps[-1])
    z = nice(zmax, [5, 8, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100])
    r = nice(rmax, [1, 2, 3, 4, 5, 6, 8, 10, 15])
    SCALES["mjoz"] = {"vmin": -z, "vmax": z, "cols": [(0, "#000a5c"), (.15, "#0a1fd1"), (.35, "#7f8ff0"), (.5, "#f6f6f6"),
                                                      (.65, "#f58a8a"), (.85, "#e00f0f"), (1, "#5c0000")],
                      "label": "مكوّن التذبذب عند ٨٠٠ هكتوباسكال (الأزرق داعم للحمل)", "unit": "متر",
                      "ticks": [round(v, 1) for v in np.linspace(-z, z, 5)]}
    SCALES["mjop"] = {"vmin": -r, "vmax": r, "cols": [(0, "#3d2508"), (.2, "#8a5a1e"), (.4, "#d8b07a"), (.5, "#f4f2ea"),
                                                      (.6, "#9bd18a"), (.8, "#2e8b3c"), (1, "#08451a")],
                      "label": "الأمطار المرتبطة بالتذبذب", "unit": "ملم في اليوم",
                      "ticks": [round(v, 1) for v in np.linspace(-r, r, 5)]}
