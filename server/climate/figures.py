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


def _cmap(cols):
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("c", cols, N=512)


def legend(kind):
    sc = SCALES[kind]
    return {"label": sc["label"], "unit": sc["unit"], "vmin": sc["vmin"], "vmax": sc["vmax"], "ticks": sc["ticks"],
            "stops": [{"p": p, "c": c} for p, c in sc["cols"]]}


def _ar(text):
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
        ax = fig.add_axes([0.045, 0.09, 0.945, 0.89], projection=proj)
        ax.set_extent([w, e, s, n], crs=ccrs.PlateCarree())
        tr = {"transform": ccrs.PlateCarree()}
        have_cartopy = True
    except Exception:
        ax = fig.add_axes([0.045, 0.09, 0.945, 0.89])
        ax.set_xlim(w, e); ax.set_ylim(s, n)
        tr = {}
        have_cartopy = False
    # wrap so the image is continuous across the 0/360 seam
    if lon[-1] - lon[0] > 350:
        lon_p = np.append(lon, lon[0] + 360)
        f = np.hstack([field, field[:, :1]])
    else:
        lon_p, f = lon, field
    ax.imshow(f, extent=[lon_p[0], lon_p[-1], lat[-1], lat[0]], origin="upper", cmap=cmap, vmin=vmin, vmax=vmax,
              interpolation="bicubic", **tr)
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
