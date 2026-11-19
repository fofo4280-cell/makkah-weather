"""The low-level warm/cold event (Fahad, 19 Nov 2026, after Dr. Khalid's SCORPION "Warm/Cold Event Index (2m/800hPa)"
with its "CAPE proxy" panel): where the air near the ground and at 800 hPa is warmer and moister than usual for the
date, the environment of deep convection.

    I = z(theta-e at 2 m) + z(theta-e at 800 hPa)      (2 z(2 m) where the ground is above the 800 hPa level)

z = (value - climatology of the date) / standard deviation at that point; climatology and deviations from GFS 12 UTC
analyses 2021-2025 (lw_clim.npz, monthly means interpolated to the day). Energy panel: I x sqrt(CAPE 180-0 hPa).
Dr. Khalid has not published his formula; this is our reading of it, tested before publishing (1 Sep-18 Nov 2026 and
three earlier seasons, PERSIANN rain over Tihama and around Makkah: Makkah-area days with 10 mm or more 44 % when
I >= 1 against 11-20 % otherwise; earlier seasons 24 % against 2 %; the energy panel adds little to I alone).

    run(gfs_fields, cycle, days, fig_dir) -> {"days": [...], "low": [...], "high": [...]}; writes fig/lw_KK.png and
    fig/lwd_KK.png. In the report (Fahad, 19 Nov 2026): a cold event (-1 or less) over the low ground or over the Taif
    plateau cancels the rain there (382 days tested: no day with 20 mm, 2-5 % with 5 mm); a warm event (1 or more) only
    adds confidence to the other ingredients.
"""
import os
from datetime import datetime, timedelta, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FIELDS = [("t2", r":TMP:2 m above ground:"), ("d2", r":DPT:2 m above ground:"), ("ps", r":PRES:surface:"),
          ("t8", r":TMP:800 mb:"), ("r8", r":RH:800 mb:"), ("u8", r":UGRD:800 mb:"), ("v8", r":VGRD:800 mb:"),
          ("cape", r":CAPE:180-0 mb above ground:")]
J0, J1 = 45, 136          # rows of the 1 degree grid for 45 N .. 45 S
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def es(tc):
    return 6.112 * np.exp(17.67 * tc / (tc + 243.5))


def theta_e(t, td, p):
    """Bolton (1980); t, td in K, p in hPa"""
    td = np.minimum(td, t)
    e = es(td - 273.15)
    r = 1000 * 0.622 * e / (p - e)
    tl = 1 / (1 / (td - 56) + np.log(t / td) / 800) + 56
    return t * (1000 / p) ** (0.2854 * (1 - 0.28e-3 * r)) * np.exp((3.376 / tl - 0.00254) * r * (1 + 0.81e-3 * r))


def td_from_rh(t, rh):
    e = np.clip(rh, 1, 100) / 100 * es(t - 273.15)
    lg = np.log(e / 6.112)
    return 243.5 * lg / (17.67 - lg) + 273.15


def smooth(a, k=1):
    out = np.zeros_like(a)
    for dj in range(-k, k + 1):
        for di in range(-k, k + 1):
            out += np.roll(np.roll(a, dj, 0), di, 1)
    return out / (2 * k + 1) ** 2


def clim_for(day, C):
    """monthly means (mid-month) interpolated linearly to the day"""
    m = day.month - 1
    mid = datetime(day.year, day.month, 15).date()
    if day >= mid:
        nb = (m + 1) % 12
        nxt = datetime(day.year + (day.month == 12), nb + 1, 15).date()
        w = (day - mid).days / (nxt - mid).days
        a, b = m, nb
    else:
        pb = (m - 1) % 12
        prv = datetime(day.year - (day.month == 1), pb + 1, 15).date()
        w = (day - prv).days / (mid - prv).days
        a, b = pb, m
    return ((1 - w) * C["th2"][a] + w * C["th2"][b]).astype(np.float32), ((1 - w) * C["th8"][a] + w * C["th8"][b]).astype(np.float32)


def index(f, day, C):
    """I and its parts from one GFS file (1 degree, rows 45 N .. 45 S)"""
    p = f["ps"] / 100
    th2 = theta_e(f["t2"], f["d2"], p)
    th8 = theta_e(f["t8"], td_from_rh(f["t8"], f["r8"]), 800.0)
    c2, c8 = clim_for(day, C)
    z2 = (th2 - c2) / C["s2"]
    z8 = (th8 - c8) / C["s8"]
    i = np.where(p >= 830, z2 + z8, 2 * z2)
    return smooth(np.nan_to_num(i)).astype(np.float32)


def run(gfs_fields, cycle, days, fig_dir, log=print):
    C = {k: v.astype(np.float32) for k, v in np.load(os.path.join(HERE, "lw_clim.npz")).items()}
    t0 = datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    out_days, box, hbox, prev, regs = [], [], [], None, {}
    first = days[0] - timedelta(days=1)
    for k, d in enumerate([first] + list(days)):
        valid = datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc)
        fh = int((valid - t0).total_seconds() // 3600)
        cyc = cycle
        if fh < 0:                      # the day before the run: its own 12 UTC analysis
            cyc, fh = valid.strftime("%Y%m%d%H"), 0
        try:
            f = gfs_fields(cyc, fh, res="1p00", fields=FIELDS)
        except Exception as e:  # noqa: BLE001
            log("lowwarm", d, "failed:", repr(e))
            prev = None
            continue
        f = {n: a[J0:J1] for n, a in f.items()}
        i = index(f, d, C)
        if k == 0:
            prev = i
            continue
        ep = i * np.sqrt(np.maximum(f["cape"], 0))
        kk = f"{k - 1:02d}"
        draw(i, ep, f["u8"], f["v8"], valid, os.path.join(fig_dir, f"lw_{kk}.png"))
        if prev is not None:
            draw_change(i - prev, valid, os.path.join(fig_dir, f"lwd_{kk}.png"))
        prev = i
        out_days.append(d.isoformat())
        low, high = boxes(i, f["ps"])
        box.append(low)
        hbox.append(high)
        try:
            for nm, v in region_means(i).items():
                regs.setdefault(nm, []).append(v)
        except Exception as e:  # noqa: BLE001
            log("lowwarm regions failed:", repr(e))
    log("lowwarm maps:", len(out_days), "makkah low ground", box[:3], "taif", hbox[:3])
    return {"days": out_days, "low": box, "high": hbox, "regions": regs}


_RMASK = {}


def region_means(i):
    """the index over each region of the Kingdom: mean of the 1 degree cells inside it (Kingdom test, 383 days)"""
    if not _RMASK:
        import sa_geo as G
        regs = G.regions()
        la = np.arange(45, -46, -1.0)
        J = [j for j in range(91) if 15 <= la[j] <= 33]
        LA, LO = np.meshgrid(la[J], np.arange(34.0, 57.0), indexing="ij")
        r = np.array(G.region_of_points(regs, LA.ravel(), LO.ravel())).reshape(LA.shape)
        for q, rg in enumerate(regs):
            if (r == q).any():
                _RMASK[rg["name"]] = (J, r == q)
    return {nm: round(float(i[J][:, 34:57][m].mean()), 2) for nm, (J, m) in _RMASK.items()}


def boxes(i, ps):
    """the boxes of the test: Makkah's low ground and Tihama (cells 19-22 N, 39-41 E below about 700 m), and the Taif
    plateau with the Al-Hada and Ash-Shafa edges (cells 20-22 N, 40-42 E above it)"""
    jj, ii = slice(45 - 22, 45 - 19 + 1), slice(39, 42)
    m = ps[jj, ii] >= 93000
    low = round(float(np.mean(i[jj, ii][m])), 2) if m.any() else None
    jj, ii = slice(45 - 22, 45 - 20 + 1), slice(40, 43)
    m = ps[jj, ii] < 93000
    high = round(float(np.mean(i[jj, ii][m])), 2) if m.any() else None
    return low, high


def _fonts():
    from matplotlib import font_manager as fm
    return (fm.FontProperties(fname=os.path.join(HERE, "fonts", "IBMPlexSansArabic-SemiBold.ttf")),
            fm.FontProperties(fname=os.path.join(HERE, "fonts", "IBMPlexSansArabic-Bold.ttf")))


def _when(valid):
    mk = valid + timedelta(hours=3)
    return f"{DAYS[mk.weekday()]} {_n(mk.day)} {MONTHS[mk.month - 1]}، الثالثة عصرًا بتوقيت مكة"


def _n(x):
    return str(x).translate(str.maketrans("0123456789-.", "٠١٢٣٤٥٦٧٨٩−٫"))


def _axes(fig, rect):
    import cartopy.crs as ccrs
    import cartopy.feature as cf
    ax = fig.add_axes(rect, projection=ccrs.PlateCarree(central_longitude=180))
    ax.set_extent([0.01, 359.99, -35, 35], ccrs.PlateCarree())
    ax.set_facecolor("#1b2330")
    ax.coastlines("110m", lw=.6, color="#222")
    ax.add_feature(cf.BORDERS.with_scale("110m"), lw=.3, edgecolor="#555")
    ax.plot([0, 360], [0, 0], color="#444", lw=.5, ls="--", transform=ccrs.PlateCarree())
    for x in range(0, 360, 60):
        ax.text(x, -38, _n(x if x <= 180 else 360 - x) + ("°ش" if 0 < x < 180 else "°غ" if x > 180 else "°"),
                transform=ccrs.PlateCarree(), ha="center", va="top", fontsize=8, color="#aaa", fontproperties=_fonts()[0])
    return ax


def _cbar(fig, cm, rect, ticks, label, fp):
    import matplotlib.pyplot as plt
    cax = fig.add_axes(rect)
    cb = plt.colorbar(cm, cax=cax, orientation="horizontal")
    cb.set_ticks(ticks)
    cb.set_ticklabels([_n(t) for t in ticks])
    cb.outline.set_edgecolor("#555")
    for t in cb.ax.get_xticklabels():
        t.set_fontproperties(fp); t.set_color("#ddd"); t.set_fontsize(9)
    cax.set_title(label, fontproperties=fp, fontsize=10, color="#bbb", pad=3)


def draw(i, ep, u, v, valid, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
    fp, fb = _fonts()
    lat = np.linspace(45, -45, i.shape[0])
    lon = np.arange(i.shape[1], dtype=float)
    fig = plt.figure(figsize=(15, 9.6), dpi=130, facecolor="#111")
    fig.text(.5, .965, "الحدث الدافئ والبارد قرب الأرض (٢ متر و٨٠٠ هكتوباسكال) وطاقة الحمل", fontproperties=fb,
             fontsize=17, color="#fff", ha="center")
    fig.text(.5, .935, _when(valid) + "، من جي إف إس", fontproperties=fp, fontsize=11.5, color="#bbb", ha="center")
    # panel 1: the index with 800 hPa streamlines
    ax = _axes(fig, [.03, .53, .94, .36])
    warm = LinearSegmentedColormap.from_list("w", ["#1b3a8f", "#3d6fd1", "#9fbbea", "#f2f2f2", "#f0a39a", "#d9433a", "#8a1414"])
    lev = np.arange(-4, 4.01, .5)
    cm = ax.contourf(lon, lat, np.clip(i, -3.99, 3.99), levels=lev, cmap=warm, norm=BoundaryNorm(lev, warm.N),
                     transform=ccrs.PlateCarree(), zorder=0)
    sl = slice(10, 81)          # 35 N .. 35 S
    # in the map's own coordinates (longitude minus 180), so no regridding is needed
    xs = lon - 180.0
    from matplotlib.axes import Axes
    Axes.streamplot(ax, xs, lat[sl][::-1], u[sl][::-1], v[sl][::-1], density=(3.2, 1.2),
                  color="#ffffff", linewidth=.45, arrowsize=.6, zorder=2)
    ax.coastlines("110m", lw=.6, color="#222", zorder=3)
    ax.text(.995, 1.02, "مؤشر الحدث الدافئ والبارد قرب الأرض، وخطوط الرياح عند ٨٠٠ هكتوباسكال", transform=ax.transAxes,
            ha="right", va="bottom", fontproperties=fb, fontsize=12, color="#eee")
    _cbar(fig, cm, [.3, .475, .4, .016], [-4, -2, 0, 2, 4], "الأزرق حدث بارد يكبت الحمل، والأحمر حدث دافئ يهيئ للحمل العميق (بلا وحدة)", fp)
    # panel 2: index x sqrt(CAPE)
    ax2 = _axes(fig, [.03, .08, .94, .36])
    en = LinearSegmentedColormap.from_list("e", ["#0f5d55", "#3fa392", "#a8dccf", "#f4f1ec", "#e7b9a6", "#b8577e", "#5b1a66"])
    lev2 = np.arange(-120, 121, 15)
    cm2 = ax2.contourf(lon, lat, np.clip(ep, -119, 119), levels=lev2, cmap=en, norm=BoundaryNorm(lev2, en.N),
                       transform=ccrs.PlateCarree(), zorder=0)
    ax2.coastlines("110m", lw=.6, color="#222", zorder=3)
    ax2.text(.995, 1.02, "طاقة الحمل في الحدث: المؤشر مضروبًا في جذر طاقة عدم الاستقرار", transform=ax2.transAxes,
             ha="right", va="bottom", fontproperties=fb, fontsize=12, color="#eee")
    _cbar(fig, cm2, [.3, .03, .4, .016], [-120, -60, 0, 60, 120], "البنفسجي حدث دافئ ومعه طاقة عالية، والأخضر حدث بارد", fp)
    fig.savefig(path, facecolor="#111")
    plt.close(fig)


def draw_change(di, valid, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
    fp, fb = _fonts()
    lat = np.linspace(45, -45, di.shape[0])
    lon = np.arange(di.shape[1], dtype=float)
    fig = plt.figure(figsize=(15, 5.4), dpi=130, facecolor="#111")
    fig.text(.5, .93, "تغير الحدث الدافئ والبارد قرب الأرض خلال ٢٤ ساعة", fontproperties=fb, fontsize=17, color="#fff", ha="center")
    fig.text(.5, .87, "حتى " + _when(valid), fontproperties=fp, fontsize=11.5, color="#bbb", ha="center")
    ax = _axes(fig, [.03, .17, .94, .64])
    cmap = LinearSegmentedColormap.from_list("c", ["#1d4f91", "#6c9bd2", "#cfdff0", "#f4f1ec", "#f3c9a0", "#e07b39", "#8c2d04"])
    lev = np.arange(-3, 3.01, .5)
    cm = ax.contourf(lon, lat, np.clip(di, -2.99, 2.99), levels=lev, cmap=cmap, norm=BoundaryNorm(lev, cmap.N),
                     transform=ccrs.PlateCarree(), zorder=0)
    ax.coastlines("110m", lw=.6, color="#222", zorder=3)
    _cbar(fig, cm, [.3, .06, .4, .03], [-3, -2, -1, 0, 1, 2, 3], "البرتقالي اشتداد الحدث الدافئ أو ضعف البارد، والأزرق العكس", fp)
    fig.savefig(path, facecolor="#111")
    plt.close(fig)
