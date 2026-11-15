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


# ------------------------------------------------------------------ the tropical belt panels (0-360, 35S-35N)
# All the belt maps share one frame, so they line up when stacked: the same longitudes under each other and the
# same marker lines (the MJO core, the warm event, the cold event) through all of them.
BELT = (0, 360, -35, 35)
MARKS = {"core": "#d9775a", "warm": "#a3202a", "cold": "#2b4a7f"}
_RDBU = [(0, "#08306b"), (.12, "#1f5fa8"), (.27, "#5e9fd0"), (.42, "#c8dff0"), (.5, "#f7f7f7"), (.58, "#f6d2c0"),
         (.73, "#e0795a"), (.88, "#b3202a"), (1, "#5c0010")]
SCALES["kel"] = {"vmin": -6, "vmax": 6, "cols": _RDBU, "step": 1.5,
                 "label": "موجات كلفن (الأزرق داعم للحمل)", "unit": "مليون م²/ث",
                 "ticks": [-6, -4, -2, 0, 2, 4, 6]}
SCALES["ros"] = {"vmin": -4, "vmax": 4, "cols": _RDBU, "step": 1.0,
                 "label": "عائلة روسبي (الأزرق داعم للحمل)", "unit": "مليون م²/ث",
                 "ticks": [-4, -3, -2, -1, 0, 1, 2, 3, 4]}


def _belt_panel(ax, field, lat, lon, kind, marks=None, vectors=None, stream=None, contours=False, width_px=3000,
                tick_labels=True, mark_labels=False):
    """one belt map drawn on ax (PlateCarree centred on 180)"""
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from scipy.ndimage import zoom
    sc = SCALES[kind]
    w, e, s, n = BELT
    j = (lat >= s - 2) & (lat <= n + 2)
    la = lat[j]
    f = np.hstack([field[j], field[j][:, :1]])            # continuous across the 0/360 seam
    lo = np.append(lon, lon[0] + 360)
    pc = ccrs.PlateCarree()
    ax.set_extent([w, e - 0.001, s, n], crs=pc)
    up = max(1, int(np.ceil(width_px * 1.1 / f.shape[1])))
    fine = zoom(np.nan_to_num(f), up, order=3)
    # drawn straight in the map's own coordinates (x = longitude - 180), so nothing is regridded
    ax.imshow(fine, extent=[lo[0] - 180, lo[-1] - 180, la[-1], la[0]], origin="upper", cmap=_cmap(sc["cols"]),
              vmin=sc["vmin"], vmax=sc["vmax"], interpolation="bilinear", transform=ax.projection)
    if contours and sc.get("step"):
        st = sc["step"]
        lv = np.arange(-20 * st, 20 * st + st / 2, st)
        lv = lv[np.abs(lv) > st / 2]
        ax.contour(lo, la, f, levels=lv, colors="white", linewidths=0.45, alpha=0.75, transform=pc,
                   linestyles=["dashed" if x < 0 else "solid" for x in lv])
    try:
        import cartopy.io.shapereader as shp
        shp.natural_earth(resolution="50m", category="physical", name="coastline")
        ax.coastlines(resolution="50m", linewidth=0.5, color="#111111", zorder=4)
        shp.natural_earth(resolution="50m", category="cultural", name="admin_0_boundary_lines_land")
        ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.25, edgecolor="#444444", zorder=4)
    except Exception as ex:
        print("coastlines unavailable:", str(ex)[:80])
    if vectors is not None:
        u, v = vectors
        u = np.hstack([u[j], u[j][:, :1]])
        v = np.hstack([v[j], v[j][:, :1]])
        st = 4
        U, V = u[::st, ::st], v[::st, ::st]
        LO, LA = np.meshgrid(lo[::st], la[::st])
        M = np.hypot(U, V)
        inside = (LA >= s) & (LA <= n) & (LO < e)
        thr = float(np.nanpercentile(M[inside], 45))
        keep = inside & (M >= thr)
        if keep.any():
            ref = max(float(np.nanpercentile(M[keep], 98)), 1e-6)
            ax.quiver(LO[keep], LA[keep], U[keep] / ref, V[keep] / ref, transform=pc, color="white", alpha=0.9,
                      scale=95, width=0.0010, headwidth=4.0, headlength=4.2, headaxislength=3.8, zorder=5)
    if stream is not None:
        u, v = stream
        u = np.hstack([u[j], u[j][:, :1]])[::-1]
        v = np.hstack([v[j], v[j][:, :1]])[::-1]
        spd = np.hypot(u, v)
        lw = 0.3 + 1.2 * spd / max(float(np.nanpercentile(spd, 98)), 1e-6)
        ax.streamplot(lo, la[::-1], u, v, color=(1, 1, 1, 0.85), linewidth=np.clip(lw, 0.3, 1.5), density=(4.2, 0.9),
                      arrowsize=0.55, minlength=0.15, transform=pc, zorder=5)
    for name, x in (marks or {}).items():
        if x is None:
            continue
        c = MARKS[name]
        x = float(x) % 360
        ax.plot([x, x], [s, n], color="white", linewidth=2.6, transform=pc, zorder=6)
        ax.plot([x, x], [s, n], color=c, linewidth=1.5, transform=pc, zorder=7)
        ax.plot([x], [n - 0.6], marker="v", markersize=5.5, color=c, markeredgecolor="white", markeredgewidth=0.5,
                transform=pc, zorder=8, clip_on=False)
    ax.spines["geo"].set_edgecolor("#999999")
    xt = np.arange(0, 361, 30)
    yt = np.arange(-30, 31, 15)
    ax.set_xticks(xt, crs=pc)
    ax.set_yticks(yt, crs=pc)
    ax.set_xticklabels([lon_label(x) for x in xt] if tick_labels else [""] * len(xt), fontsize=6.5, color="#555555")
    ax.set_yticklabels([lat_label(y) for y in yt], fontsize=6.5, color="#555555")
    ax.tick_params(length=2.5, color="#999999")
    for x in xt[1:-1]:
        ax.plot([x, x], [s, n], color="#000000", alpha=0.07, linewidth=0.4, transform=pc, zorder=3)
    for y in yt:
        ax.plot([w, e], [y, y], color="#000000", alpha=0.07 if y else 0.3, linewidth=0.45 if y else 0.6, transform=pc,
                zorder=3)
    im = ax.images[0] if ax.images else None
    return im


def draw_belt(path, field, lat, lon, kind, marks=None, vectors=None, stream=None, contours=False, width_px=3000):
    """A high-resolution map of the tropical belt (0-360, 35S-35N): the field shaded from a finely interpolated
    copy, coastlines and borders at 1:50 million, optional thin contours, divergent-wind arrows (vectors=(u, v))
    or streamlines (stream=(u, v)), and vertical marker lines: marks = {'core'|'warm'|'cold': longitude}.
    field: on lat (descending) x lon (0..359)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    w, e, s, n = BELT
    fig_w = width_px / 200
    lm, rm, bm, tm = 70 / width_px, 12 / width_px, 0.30, 0.08     # margins (inches for bottom/top)
    map_w = fig_w * (1 - lm - rm)
    map_h = map_w * (n - s) / (e - w)
    fig_h = map_h + bm + tm
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=200)
    fig.patch.set_facecolor("#f7f5f0")
    ax = fig.add_axes([lm, bm / fig_h, 1 - lm - rm, map_h / fig_h], projection=ccrs.PlateCarree(central_longitude=180))
    _belt_panel(ax, field, lat, lon, kind, marks, vectors, stream, contours, width_px)
    _save_png(fig, path)


def _save_png(fig, path):
    import matplotlib.pyplot as plt
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=240, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:
        pass


MARK_NAMES = {"core": "مركز التذبذب", "warm": "الحدث الدافئ", "cold": "الحدث البارد"}


def draw_belt_stack(path, panels, marks=None, title="", stamp="", width_px=3000):
    """The tropical belt maps stacked one under the other, as in the four-panel charts of the MJO literature:
    a title, the key of the marker lines (each with its longitude), then for every panel its title on the left,
    its level and time on the right, the map, and its colour bar at the right edge. The same marker lines run
    through all the maps. panels: [{field, lat, lon, kind, title, sub, vectors?, stream?, contours?}]"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable
    w, e, s, n = BELT
    fig_w = width_px / 200
    lm, rm = 70 / width_px, 150 / width_px
    map_w = fig_w * (1 - lm - rm)
    map_h = map_w * (n - s) / (e - w)
    head, gap_t, gap_b = 0.62, 0.30, 0.16           # inches: the title block, a panel's title, below a panel
    fig_h = head + len(panels) * (gap_t + map_h + gap_b) + 0.14
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=200)
    fig.patch.set_facecolor("#f7f5f0")
    if title:
        fig.text(lm, 1 - 0.10 / fig_h, _ar(title), ha="left", va="top", fontsize=11, fontweight="bold", color="#111111")
    if stamp:
        fig.text(1 - rm, 1 - 0.12 / fig_h, stamp, ha="right", va="top", fontsize=7.5, color="#555555", style="italic")
    # the key of the marker lines
    x0 = lm
    for name in ("core", "warm", "cold"):
        x = (marks or {}).get(name)
        if x is None:
            continue
        y = 1 - 0.43 / fig_h
        fig.lines.append(matplotlib.lines.Line2D([x0, x0 + 0.018], [y, y], color=MARKS[name], linewidth=2.2,
                                                 transform=fig.transFigure))
        t = fig.text(x0 + 0.024, y, f"{lon_label(float(x) % 360)}  " + _ar(MARK_NAMES[name]), ha="left", va="center",
                     fontsize=7.5, fontweight="bold", color="#222222")
        x0 += 0.20
    y_top = 1 - head / fig_h
    for k, pn in enumerate(panels):
        y_map = y_top - (gap_t + map_h) / fig_h
        ax = fig.add_axes([lm, y_map, 1 - lm - rm, map_h / fig_h], projection=ccrs.PlateCarree(central_longitude=180))
        fig.text(lm, y_top - 0.04 / fig_h, _ar(pn.get("title", "")), ha="left", va="top", fontsize=9, fontweight="bold",
                 color="#111111")
        if pn.get("sub"):
            fig.text(1 - rm, y_top - 0.07 / fig_h, pn["sub"], ha="right", va="top", fontsize=6.5, color="#666666",
                     style="italic")
        _belt_panel(ax, pn["field"], pn["lat"], pn["lon"], pn["kind"], marks, pn.get("vectors"), pn.get("stream"),
                    pn.get("contours", False), width_px, tick_labels=(k == len(panels) - 1))
        sc = SCALES[pn["kind"]]
        cax = fig.add_axes([1 - rm + 12 / width_px, y_map, 14 / width_px, map_h / fig_h])
        cb = fig.colorbar(ScalarMappable(Normalize(sc["vmin"], sc["vmax"]), _cmap(sc["cols"])), cax=cax)
        cb.ax.tick_params(labelsize=5.5, length=2, color="#999999", labelcolor="#444444")
        cb.outline.set_edgecolor("#999999")
        cb.outline.set_linewidth(0.4)
        if sc.get("unit"):
            cb.set_label(_ar(sc["unit"]), fontsize=6, color="#444444")
        y_top = y_map - gap_b / fig_h
    _save_png(fig, path)




# ------------------------------------------------------------------ the tropical wave maps (as Dr Khalid's SCORPION)
# One map per family (Rossby westward, Kelvin eastward): the filtered 200 hPa velocity potential shaded in the
# red-blue scale, thin white contours (solid above zero, dashed below), the divergent wind as white arrows on a
# regular grid, and nothing else drawn in the image: the titles, the colour bar and the date are on the page, in
# the site's own font. Every frame of a family has the same scale and the same arrow length for the same wind,
# so the days run on smoothly when played.
def _rdbu_stops(n=11):
    import matplotlib
    cm = matplotlib.colormaps["RdBu_r"]
    from matplotlib.colors import to_hex
    return [(round(k / (n - 1), 3), to_hex(cm(k / (n - 1)))) for k in range(n)]


SCALES["twr"] = {"vmin": -3.5, "vmax": 3.5, "cols": _rdbu_stops(), "step": 0.5,
                 "label": "عائلة روسبي (الأزرق داعم للحمل)", "unit": "مليون م²/ث",
                 "ticks": [-3, -2, -1, 0, 1, 2, 3]}
SCALES["twk"] = {"vmin": -6.5, "vmax": 6.5, "cols": _rdbu_stops(), "step": 1.0,
                 "label": "موجات كلفن (الأزرق داعم للحمل)", "unit": "مليون م²/ث",
                 "ticks": [-6, -4, -2, 0, 2, 4, 6]}
WAVE_BOX = (0, 360, -35, 35)


def wave_vec_ref(vectors_list, lat):
    """the wind that makes a full-length arrow: the 99th percentile of the divergent wind over all the frames"""
    s, n = WAVE_BOX[2], WAVE_BOX[3]
    j = (lat >= s) & (lat <= n)
    return max(float(np.nanpercentile(np.concatenate([np.hypot(u[j], v[j]).ravel() for u, v in vectors_list]), 99)),
               1e-6)


def draw_wave(path, field, lat, lon, kind, vectors, vec_ref, width_px=2400):
    """The tropical belt (0-360, 35S-35N) in the style of the mid-level wave map: grey shaded relief, the filtered
    200 hPa velocity potential as thin contours (blue below zero: divergence aloft that supports convection; gold
    above: convergence that suppresses it) with their values, the zero line dash-dot, every centre marked with its
    word and value (10^6 m2/s), and curved arrows along the divergent wind: out of the blue centres, into the gold.
    field (10^6 m2/s) and vectors (u, v m/s) on lat x lon (0..359, 1 degree); vec_ref is kept for the call."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    import cartopy.crs as ccrs
    from scipy.ndimage import zoom, maximum_filter, minimum_filter
    from scipy.interpolate import RegularGridInterpolator
    fam = _ar_font()
    sc = SCALES[kind]
    w, e, s, n = WAVE_BOX
    dpi = 200
    fig_w = width_px / dpi
    fig_h = fig_w * (n - s) / (e - w)
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor("#3a3f45")
    pc = ccrs.PlateCarree()
    ax = fig.add_axes([0, 0, 1, 1], projection=ccrs.PlateCarree(central_longitude=180))
    ax.set_extent([w, e - 0.001, s, n], crs=pc)
    try:
        from PIL import Image
        rel = np.asarray(Image.open(RELIEF_BELT).convert("L"))
        ax.imshow(rel, extent=[-180, 180, -36, 36], origin="upper", cmap="gray", vmin=0, vmax=255,
                  transform=ax.projection, interpolation="lanczos", zorder=0)
    except Exception as ex:
        print("relief unavailable:", str(ex)[:80])
    ax.coastlines(resolution="50m", linewidth=0.45, color="#2b2b2b", alpha=0.75, zorder=1)
    order = np.argsort(lat)                                         # ascending for the interpolators
    la = lat[order]
    f = field[order]
    u, v = vectors[0][order], vectors[1][order]
    j = (la >= s - 4) & (la <= n + 4)
    la, f, u, v = la[j], f[j], u[j], v[j]
    fw = np.hstack([f[:, -20:], f, f[:, :20]])                       # wrapped so the contours run on across 0/360
    low = np.concatenate([lon[-20:] - 360, lon, lon[:20] + 360])
    up = 3
    fz = zoom(fw, up, order=3)
    flo = np.linspace(low[0], low[-1], fz.shape[1])
    fla = np.linspace(la[0], la[-1], fz.shape[0])
    st = sc["step"]
    halo_l = [pe.withStroke(linewidth=2.2, foreground=(0.05, 0.08, 0.12, 0.5))]
    dig = (lambda x: f"{x:g}") if st >= 1 else (lambda x: f"{x:.1f}".rstrip("0").rstrip("."))
    for sign, col in ((-1, "#6fd0f6"), (1, "#f2c14e")):
        lv = sorted(sign * np.arange(st, 12 * st + st / 2, st))
        cs = ax.contour(flo, fla, fz, levels=lv, colors=col, linewidths=1.0, linestyles="solid", transform=pc,
                        zorder=3)
        try:
            cs.set_path_effects(halo_l)
        except Exception:
            pass
        lab = ax.clabel(cs, levels=lv[1::2] if sign > 0 else lv[-2::-2], inline=True, inline_spacing=2, fontsize=6.2,
                        fmt=lambda x: dig(x).replace(".", "٫").translate(AR_DIG))
        for t in lab:
            t.set_fontfamily(fam); t.set_fontweight("bold"); t.set_color(col)
            t.set_path_effects([pe.withStroke(linewidth=2, foreground="#10161d")])
    cz = ax.contour(flo, fla, fz, levels=[0], colors="#ffffff", linewidths=1.2, linestyles=[(0, (7, 3, 1.5, 3))],
                    transform=pc, zorder=3)
    # the centres: the strongest highs and lows of the field, at least 15 degrees apart
    vmax = sc["vmax"]
    jj = (la >= s + 3) & (la <= n - 3)
    sub, sla = f[jj], la[jj]
    marks = []
    for kd, filt, cmp in (("lo", minimum_filter, lambda x: x <= -0.35 * vmax), ("hi", maximum_filter, lambda x: x >= 0.35 * vmax)):
        m = (sub == filt(sub, size=(15, 25), mode=("nearest", "wrap"))) & cmp(sub)
        for a_, b_ in zip(*np.nonzero(m)):
            marks.append((kd, float(sla[a_]), float(lon[b_]), float(sub[a_, b_])))
    marks = sorted([m for m in marks if abs(m[3]) >= 0.45 * vmax], key=lambda m: -abs(m[3]))[:9]
    # curved arrows along the divergent wind (the gradient of chi): out of the blue centres, into the gold ones
    uw = np.hstack([u[:, -20:], u, u[:, :20]]); vw = np.hstack([v[:, -20:], v, v[:, :20]])
    U = RegularGridInterpolator((la, low), uw, bounds_error=False, fill_value=0)
    V = RegularGridInterpolator((la, low), vw, bounds_error=False, fill_value=0)
    for kd, y0, x0, val in marks:
        r0, r1 = (3.0, 10.0) if kd == "lo" else (12.0, 4.5)
        for q in range(6):
            a0 = 2 * np.pi * (q + 0.25) / 6
            x, y = x0 + r0 * np.cos(a0), y0 + r0 * np.sin(a0)
            pts, L = [(x, y)], 0.0
            while L < abs(r1 - r0) + 2:
                uu, vv = float(U((y, x))), float(V((y, x)))
                mm = np.hypot(uu, vv)
                if mm < 0.03:
                    break
                x += 0.2 * uu / mm; y += 0.2 * vv / mm
                L += 0.2
                if not (s + 0.5 < y < n - 0.5):
                    break
                pts.append((x, y))
                if kd == "hi" and np.hypot(x - x0, y - y0) < r1:
                    break
            if L < 4:
                continue
            xs, ys = zip(*pts)
            head = "#86ccef" if kd == "lo" else "#f3a06c"
            ax.plot(xs, ys, color="#e9edf1", linewidth=3.2, alpha=0.4, transform=pc, zorder=4, solid_capstyle="round")
            ax.plot(xs, ys, color="#2c333b", linewidth=1.6, transform=pc, zorder=4.1, solid_capstyle="round")
            k = max(1, len(pts) // 6)
            ax.annotate("", xy=pts[-1], xytext=pts[-1 - k], xycoords=pc._as_mpl_transform(ax),
                        arrowprops=dict(arrowstyle="-|>,head_length=0.8,head_width=0.42", color=head, lw=1.0,
                                        mutation_scale=9, shrinkA=0, shrinkB=0,
                                        path_effects=[pe.withStroke(linewidth=2.0, foreground="#2c333b")]), zorder=4.2)
    for name, y, x in BELT_PLACES:
        ax.text(x, y, _rtl(name), transform=pc, ha="center", va="center", fontsize=6.5, fontfamily=fam,
                fontweight="bold", color="#d9dde2", alpha=0.85,
                path_effects=[pe.withStroke(linewidth=1.8, foreground="#3a3f45")], zorder=5)
    ax.plot([39.83], [21.42], marker="o", markersize=2.8, color="#ffffff", markeredgecolor="#111111",
            markeredgewidth=0.7, transform=pc, zorder=5)
    for kd, y, x, val in marks:
        col = "#7cc6f2" if kd == "lo" else "#ffb36b"
        word = "تباعد" if kd == "lo" else "تقارب"
        ax.plot([x], [y], marker="o", markersize=4, color=col, markeredgecolor="#10161d", markeredgewidth=1.0,
                transform=pc, zorder=6)
        ax.text(x, y + 0.9, word, transform=pc, ha="center", va="bottom", fontsize=8.5, fontfamily=fam,
                fontweight="bold", color=col, path_effects=[pe.withStroke(linewidth=2.8, foreground="#10161d")],
                zorder=6)
        ax.text(x, y - 0.9, f"{val:+.1f}".replace(".", "٫").translate(AR_DIG), transform=pc, ha="center", va="top",
                fontsize=7.5, fontfamily=fam, fontweight="bold", color="#ffffff",
                path_effects=[pe.withStroke(linewidth=2.6, foreground="#10161d")], zorder=6)
    ax.plot([w, e], [0, 0], color="#ffffff", alpha=0.25, linewidth=0.6, transform=pc, zorder=2)
    for x in range(30, 360, 30):
        lab_ = lon_label(x).replace("°E", "° ش").replace("°W", "° غ")
        ax.text(x, s + 0.6, _rtl(lab_).translate(AR_DIG), transform=pc, ha="center", va="bottom", fontsize=5.8,
                fontfamily=fam, color="#f1f3f5", alpha=0.8, path_effects=[pe.withStroke(linewidth=1.6, foreground="#2b2f34")],
                zorder=5)
    for y, t in ((30, "٣٠ ش"), (15, "١٥ ش"), (0, "الاستواء"), (-15, "١٥ ج"), (-30, "٣٠ ج")):
        ax.text(1.0, y, _rtl(t), transform=pc, ha="left", va="center", fontsize=5.8, fontfamily=fam, color="#f1f3f5",
                alpha=0.8, path_effects=[pe.withStroke(linewidth=1.6, foreground="#2b2f34")], zorder=5)
    ax.spines["geo"].set_visible(False)
    _save_png(fig, path)


RELIEF_BELT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relief_belt.png")
BELT_PLACES = [("المحيط الهندي", -20, 72), ("المحيط الهادي", 2, 200), ("المحيط الأطلسي", 8, 325),
               ("الجزيرة العربية", 23, 46), ("أفريقيا", 3, 22), ("أستراليا", -24, 133), ("الهند", 21, 78),
               ("أمريكا الجنوبية", -10, 300)]


# ------------------------------------------------------------------ the mid-level wave map (as Dr Khalid's wave charts)
# Grey shaded relief (sea dark), the wave height as thin contours (blue below zero, gold above) with their values,
# the zero line dash-dot, each low and high marked with its value, and curved arrows that follow the wind turning
# around every centre (the geostrophic direction of the wave field, so the arrows are the flow itself, not a symbol).
# Arabic in the site's own font (IBM Plex Sans Arabic), Arabic-Indic digits.
RELIEF = {"path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "relief_mid.png"), "box": (5, 95, 5, 55)}
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
AR_DIG = str.maketrans("0123456789-", "٠١٢٣٤٥٦٧٨٩−")
WAVE_PLACES = [  # (name, lat, lon, kind) kind: sea or land
    ("البحر الأحمر", 17.6, 40.4, "sea"), ("الخليج العربي", 27.0, 51.3, "sea"), ("بحر العرب", 15.0, 63.0, "sea"),
    ("البحر المتوسط", 34.0, 19.0, "sea"), ("البحر الأسود", 43.3, 34.5, "sea"), ("بحر قزوين", 42.0, 50.8, "sea"),
    ("خليج البنغال", 15.0, 88.0, "sea"),
    ("مصر", 26.5, 29.5, "land"), ("السودان", 15.5, 30.0, "land"), ("إثيوبيا", 9.0, 39.5, "land"),
    ("اليمن", 15.6, 46.5, "land"), ("العراق", 33.0, 43.5, "land"), ("إيران", 32.5, 54.5, "land"),
    ("تركيا", 39.0, 34.0, "land"), ("باكستان", 29.0, 68.5, "land"), ("الهند", 22.0, 78.5, "land"),
    ("ليبيا", 27.0, 17.5, "land"), ("أفغانستان", 34.0, 65.5, "land"),
]


def _ar_font():
    from matplotlib import font_manager as fm
    for f in ("IBMPlexSansArabic-Bold.ttf", "IBMPlexSansArabic-SemiBold.ttf"):
        p = os.path.join(FONT_DIR, f)
        if os.path.exists(p) and p not in [x.fname for x in fm.fontManager.ttflist]:
            fm.fontManager.addfont(p)
    return "IBM Plex Sans Arabic"


def _rtl(text):
    """matplotlib shapes the Arabic letters but lays the words left to right: give it the words in reverse"""
    return " ".join(reversed(text.split(" ")))


def _flow_arcs(zp, lat, lon, marks, extent):
    """curved paths along the flow around each centre: [(kind, [(lon, lat), ...])]"""
    from scipy.interpolate import RegularGridInterpolator
    w, e, s, n = extent
    la = lat[::-1] if lat[0] > lat[-1] else lat
    z = zp[::-1] if lat[0] > lat[-1] else zp
    dzdy = np.gradient(z, np.radians(la), axis=0)
    dzdx = np.gradient(z, np.radians(lon), axis=1) / np.cos(np.radians(la))[:, None]
    # the geostrophic direction in the northern hemisphere: the gradient turned 90 degrees to the left
    U = RegularGridInterpolator((la, lon), -dzdy, bounds_error=False, fill_value=0)
    V = RegularGridInterpolator((la, lon), dzdx, bounds_error=False, fill_value=0)
    cen = [(m[1], m[2]) for m in marks]
    out = []
    for kind, y0, x0, val in marks:
        rings = [(3.6, 3), (6.6, 4)] + ([(9.6, 5)] if abs(val) >= 35 else [])
        for r, nseg in rings:
            for q in range(nseg):
                a0 = 2 * np.pi * (q + (0.5 if r > 5 and r < 8 else 0.0)) / nseg
                x, y = x0 + r * np.cos(a0) / np.cos(np.radians(y0)), y0 + r * np.sin(a0)
                # a seed nearer another centre belongs to that one
                if min(np.hypot((x - cx) * np.cos(np.radians(y)), y - cy) for cy, cx in cen) < r - 0.5:
                    continue
                if not (w + 1 < x < e - 1 and s + 1 < y < n - 1):
                    continue
                pts, L, Lmax = [(x, y)], 0.0, 0.62 * 2 * np.pi * r / nseg
                while L < Lmax:
                    u, v = float(U((y, x))), float(V((y, x)))
                    m = np.hypot(u, v)
                    if m < 1e-9:
                        break
                    st = 0.18
                    x += st * u / m / np.cos(np.radians(y))
                    y += st * v / m
                    if not (w < x < e and s < y < n):
                        break
                    pts.append((x, y))
                    L += st
                if L >= 0.6 * Lmax:
                    out.append((kind, pts))
    return out


def draw_waves(path, zp, fx, fy, lat, lon, extent, marks, width_px=2000):
    """The mid-level wave map (see above). fx, fy (the wave-activity flux) are kept in the signature but not drawn."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from scipy.ndimage import zoom
    fam = _ar_font()
    w, e, s, n = extent
    j = (lat >= s - 3) & (lat <= n + 3)
    i = (lon >= w - 3) & (lon <= e + 3)
    la, lo = lat[j], lon[i]
    z = zp[np.ix_(j, i)]
    dpi = 200
    fig_w = width_px / dpi
    fig_h = fig_w * (n - s) / (e - w)
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor("#0c1118")
    pc = ccrs.PlateCarree()
    ax = fig.add_axes([0, 0, 1, 1], projection=pc)
    ax.set_extent([w, e, s, n], crs=pc)
    try:
        from PIL import Image
        rw, re_, rs, rn = RELIEF["box"]
        rel = np.asarray(Image.open(RELIEF["path"]).convert("L"))
        ax.imshow(rel, extent=[rw, re_, rs, rn], origin="upper", cmap="gray", vmin=0, vmax=255, transform=pc,
                  interpolation="lanczos", zorder=0)
    except Exception as ex:
        print("relief unavailable:", str(ex)[:80])
        ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#c9c9c9")
        ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#4f4f4f")
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.45, edgecolor="#3b3b3b", alpha=0.55, zorder=1)
    ax.coastlines(resolution="50m", linewidth=0.5, color="#2b2b2b", alpha=0.8, zorder=1)
    # the wave height: smooth contours every 10 gpm
    up = 4
    fz = zoom(z, up, order=3)
    flo = np.linspace(lo[0], lo[-1], fz.shape[1])
    fla = np.linspace(la[0], la[-1], fz.shape[0])
    halo_l = [pe.withStroke(linewidth=2.4, foreground=(0.05, 0.08, 0.12, 0.55))]
    for sign, col in ((-1, "#6fd0f6"), (1, "#f2c14e")):
        lv = [x for x in range(10, 201, 10)]
        lv = sorted(sign * np.array(lv))
        cs = ax.contour(flo, fla, fz, levels=lv, colors=col, linewidths=1.25, linestyles="solid", transform=pc,
                        zorder=3)
        for c in cs.collections if hasattr(cs, "collections") else []:
            c.set_path_effects(halo_l)
        try:
            cs.set_path_effects(halo_l)
        except Exception:
            pass
        lab = ax.clabel(cs, levels=lv[::1], fmt=lambda x: f"{int(round(x))}".translate(AR_DIG), fontsize=7.5,
                        inline=True, inline_spacing=3)
        for t in lab:
            t.set_fontfamily(fam)
            t.set_fontweight("bold")
            t.set_color(col)
            t.set_path_effects([pe.withStroke(linewidth=2.2, foreground="#10161d")])
    cz = ax.contour(flo, fla, fz, levels=[0], colors="#ffffff", linewidths=1.5, linestyles=[(0, (7, 3, 1.5, 3))],
                    transform=pc, zorder=3)
    try:
        cz.set_path_effects([pe.withStroke(linewidth=2.8, foreground=(0, 0, 0, 0.35))])
    except Exception:
        pass
    # the flow around every centre
    for kind, pts in _flow_arcs(zp, lat, lon, marks, extent):
        xs, ys = zip(*pts)
        head = "#86ccef" if kind == "L" else "#f3a06c"
        ax.plot(xs, ys, color="#e9edf1", linewidth=4.0, alpha=0.45, transform=pc, zorder=4, solid_capstyle="round")
        ax.plot(xs, ys, color="#2c333b", linewidth=2.1, transform=pc, zorder=4.1, solid_capstyle="round")
        k = max(1, len(pts) // 6)
        ax.annotate("", xy=pts[-1], xytext=pts[-1 - k], xycoords=pc._as_mpl_transform(ax),
                    arrowprops=dict(arrowstyle="-|>,head_length=0.85,head_width=0.45", color=head, lw=1.2,
                                    mutation_scale=11, shrinkA=0, shrinkB=0,
                                    path_effects=[pe.withStroke(linewidth=2.4, foreground="#2c333b")]), zorder=4.2)
    # place names
    for name, y, x, kd in WAVE_PLACES:
        if not (w + 2 < x < e - 2 and s + 1 < y < n - 1):
            continue
        ax.text(x, y, _rtl(name), transform=pc, ha="center", va="center", fontsize=7 if kd == "sea" else 7.5,
                fontfamily=fam, fontweight="bold", color="#d9dde2" if kd == "sea" else "#22272d", alpha=0.9,
                path_effects=[pe.withStroke(linewidth=2, foreground="#3a3f45" if kd == "sea" else "#eef0f2")],
                zorder=5)
    ax.plot([39.83], [21.42], marker="o", markersize=3.5, color="#ffffff", markeredgecolor="#111111",
            markeredgewidth=0.8, transform=pc, zorder=5)
    ax.text(40.35, 21.42, "مكة", transform=pc, ha="left", va="center", fontsize=7, fontfamily=fam, fontweight="bold",
            color="#111111", path_effects=[pe.withStroke(linewidth=2, foreground="#ffffff")], zorder=5)
    # the centres
    for kind, y, x, val in marks:
        if not (w + 1 < x < e - 1 and s + 1 < y < n - 1):
            continue
        col = "#ff6b57" if kind == "H" else "#7cc6f2"
        word = "مرتفع" if kind == "H" else "منخفض"
        ax.plot([x], [y], marker="o", markersize=5, color=col, markeredgecolor="#10161d", markeredgewidth=1.2,
                transform=pc, zorder=6)
        ax.text(x, y + 0.45, word, transform=pc, ha="center", va="bottom", fontsize=11, fontfamily=fam,
                fontweight="bold", color=col, path_effects=[pe.withStroke(linewidth=3.2, foreground="#10161d")],
                zorder=6)
        ax.text(x, y - 0.45, f"{val:+.0f}".replace("+", "+").translate(AR_DIG), transform=pc, ha="center", va="top",
                fontsize=9.5, fontfamily=fam, fontweight="bold", color="#ffffff",
                path_effects=[pe.withStroke(linewidth=3, foreground="#10161d")], zorder=6)
    ax.spines["geo"].set_visible(False)
    _save_png(fig, path)
