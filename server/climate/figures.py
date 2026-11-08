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
                ("جازان", 16.89, 42.55, "w", True), ("تبوك", 28.38, 36.57, "n", True), ("حائل", 27.52, 41.69, "n", True),
                ("سكاكا", 29.97, 40.21, "s", True), ("الطائف", 21.27, 40.42, "s", False), ("نجران", 17.49, 44.13, "e", False),
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
        return str(int(abs(x))).translate(AR)
    return _ar(f"{str(int(abs(x))).translate(AR)}{'ش' if x > 0 else 'غ'}")


def lat_label(y):
    if y == 0:
        return _ar("خط الاستواء") if False else "٠"
    return _ar(f"{str(int(abs(y))).translate(AR)}{'ش' if y > 0 else 'ج'}")


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
        if kind == "pw":
            draw_cities(ax, ccrs.PlateCarree(), fontsize=7.5)
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
                                                   (.64, "#f6d48f"), (.82, "#e39a2d"), (1, "#8a4b08")],
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
    cs = ax.contour(lo, la, z, levels=levels, colors=["#1d4f8f" if x < 0 else "#a8640c" for x in levels],
                    linewidths=0.7, alpha=0.8, transform=pc)
    ax.clabel(cs, fmt=lambda x: str(int(abs(x))).translate(AR), fontsize=6)
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
    draw_cities(ax, pc, fontsize=5.8, wide=True)
    halo = [pe.withStroke(linewidth=2.6, foreground="white")]
    for kind, y, x, val in marks:
        col = "#d2442a" if kind == "H" else "#1f6fc0"
        ax.text(x, y + 0.6, _ar("مرتفع") if kind == "H" else _ar("منخفض"), transform=pc, ha="center", va="bottom",
                fontsize=8, fontweight="bold", color=col, path_effects=halo, zorder=6)
        ax.text(x, y - 0.4, str(int(round(abs(val)))).translate(AR), transform=pc,
                ha="center", va="top", fontsize=7.5, fontweight="bold", color=col, path_effects=halo, zorder=6)
        ax.plot(x, y, marker="o", markersize=3.2, color=col, transform=pc, zorder=6, markeredgecolor="white")
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
