"""The low-level warm/cold event (Fahad, 19 Nov 2026, after Dr. Khalid's SCORPION "Warm/Cold Event Index (2m/800hPa)"
with its "CAPE proxy" panel): where the air near the ground and at 800 hPa is warmer and moister than usual for the
date, the environment of deep convection.

    I = z(theta-e at 2 m) + z(theta-e at 800 hPa)      (2 z(2 m) where the ground is above the 800 hPa level)

z = (value - climatology of the date) / standard deviation at that point; climatology and deviations from GFS 12 UTC
analyses 2021-2025 (lw_clim.npz, monthly means interpolated to the day). Energy panel: I x sqrt(CAPE 180-0 hPa).
Dr. Khalid has not published his formula; this is our reading of it, tested before publishing (1 Sep-18 Nov 2026 and
three earlier seasons, PERSIANN rain over Tihama and around Makkah: Makkah-area days with 10 mm or more 44 % when
I >= 1 against 11-20 % otherwise; earlier seasons 24 % against 2 %; the energy panel adds little to I alone).

    run(gfs_fields, cycle, days, fig_dir) -> {"days": [...], "low": [...], "high": [...], ...}; writes
    fig/lw_KK.png (the index), fig/lwe_KK.png (the energy: its own map and page tab since 25 Nov 2026, Fahad) and
    fig/lwd_KK.png (24 h change). In the report (Fahad, 19 Nov 2026): a cold event (-1 or less) over the low ground
    or over the Taif plateau cancels the rain there (382 days tested: no day with 20 mm, 2-5 % with 5 mm); a warm
    event (1 or more) only adds confidence to the other ingredients.
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
        draw(i, f["u8"], f["v8"], valid, os.path.join(fig_dir, f"lw_{kk}.png"))
        draw_energy(ep, f["u8"], f["v8"], valid, os.path.join(fig_dir, f"lwe_{kk}.png"))
        if prev is not None:
            draw_change(i - prev, f["u8"], f["v8"], valid, os.path.join(fig_dir, f"lwd_{kk}.png"))
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
    return {"days": out_days, "low": box, "high": hbox, "regions": regs, "energy": True}   # energy: lwe maps exist


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


# ------------------------------------------------------------------ drawing
# The look (Fahad, 22 Nov 2026, after the global "Warm/Cold Event index (2m/800hPa)" maps Dr. Khalid shares): cream
# paper, a smooth blue-white-red shading (dark navy cold .. dark red warm), white 800 hPa streamlines with a grid of
# white dots, thin black coasts, a light grid, the four MJO sectors along the top, the title strip above the map, the
# figures of the day in a box under it and the colour bar centred at the bottom. Style only: the numbers are unchanged.
PAPER, INK, MUTED, GRID = "#faf8f3", "#1d1d1d", "#6b6b6b", "#c9c4b8"
COLD_INK, WARM_INK = "#3b6aa8", "#c0392b"
PALETTE = ["#13305e", "#2a568f", "#5a88c0", "#9dbbdc", "#d3e0ec", "#f6f2e9",
           "#f4dcb0", "#eeb06c", "#e07f3d", "#c4512a", "#982519", "#5e0c10"]
SECTORS = [(45, "قطاع التذبذب الشرقي ١", COLD_INK), (135, "قطاع التذبذب الشرقي ٢", COLD_INK),
           (225, "قطاع التذبذب الغربي ١", WARM_INK), (315, "قطاع التذبذب الغربي ٢", WARM_INK)]
UP = 4                      # display only: the 1 degree field is drawn smooth at a quarter degree


def _fonts():
    from matplotlib import font_manager as fm
    return (fm.FontProperties(fname=os.path.join(HERE, "fonts", "IBMPlexSansArabic-SemiBold.ttf")),
            fm.FontProperties(fname=os.path.join(HERE, "fonts", "IBMPlexSansArabic-Bold.ttf")))


def _when(valid):
    mk = valid + timedelta(hours=3)
    return f"{DAYS[mk.weekday()]} {_n(mk.day)} {MONTHS[mk.month - 1]} {_n(mk.year)}، الثالثة عصرًا بتوقيت مكة"


def _n(x):
    return str(x).translate(str.maketrans("0123456789-.", "٠١٢٣٤٥٦٧٨٩−٫"))


def _sn(x, nd=1):
    """a number in Arabic digits, a negative one with the word «سالب» (a sign beside Arabic digits flips side)"""
    t = _n(f"{abs(x):.{nd}f}")
    return "سالب " + t if round(x, nd) < 0 else t


def _lon_ar(lo):
    lo = lo % 360
    if lo == 0 or lo == 180:
        return _n(int(lo))
    return _n(int(lo if lo < 180 else 360 - lo)) + (" شرقًا" if lo < 180 else " غربًا")


def _lat_ar(la):
    if la == 0:
        return "خط الاستواء"
    return _n(int(abs(la))) + (" شمالًا" if la > 0 else " جنوبًا")


def _cmap():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("lwscorp", PALETTE, N=512)


def _hires(a):
    """smooth display copy of a (rows 45 N .. 45 S, columns 0 .. 359 E): cubic, wrapped in longitude"""
    from scipy.ndimage import zoom
    p = np.concatenate([a[:, -3:], a, a[:, :3]], axis=1)
    z = zoom(np.nan_to_num(p), UP, order=3)
    return z[:, 3 * UP:3 * UP + a.shape[1] * UP]


def _map(fig, rect, fp, fb):
    """a cartopy map 0 .. 360 (centred on 180) by 45 N .. 45 S on cream paper, with grid, labels and sector boxes"""
    import cartopy.crs as ccrs
    ax = fig.add_axes(rect, projection=ccrs.PlateCarree(central_longitude=180))
    ax.set_extent([0.01, 359.99, -45, 45], ccrs.PlateCarree())
    ax.set_facecolor(PAPER)
    for s in ax.spines.values():
        s.set_edgecolor("#bdb7aa"); s.set_linewidth(.8)
    P = ccrs.PlateCarree()
    for la in (-30, 30):
        ax.plot([0, 360], [la, la], color=GRID, lw=.6, transform=P, zorder=4)
    ax.plot([0, 360], [0, 0], color="#555", lw=.8, transform=P, zorder=4)
    for lo in (90, 180, 270):
        ax.plot([lo, lo], [-45, 45], color="#9a958a", lw=.6, ls=(0, (4, 3)), transform=P, zorder=4)
    for lo in (60, 120, 240, 300):
        ax.plot([lo, lo], [-45, 45], color=GRID, lw=.4, alpha=.6, transform=P, zorder=4)
    for la in (45, 30, 0, -30, -45):
        ax.text(-.006, (la + 45) / 90, _lat_ar(la), transform=ax.transAxes, ha="right", va="center",
                fontproperties=fb, fontsize=9.5, color=MUTED)
    for lo in range(0, 361, 60):
        ax.text(lo / 360, -.025, _lon_ar(lo), transform=ax.transAxes, ha="center", va="top",
                fontproperties=fb, fontsize=9.5, color=MUTED)
        ax.plot([lo / 360] * 2, [0, -.012], color="#9a958a", lw=.8, transform=ax.transAxes, clip_on=False)
    for lo, name, c in SECTORS:
        ax.text(lo / 360, .975, name, transform=ax.transAxes, ha="center", va="top", fontproperties=fb,
                fontsize=8.5, color=c, zorder=9,
                bbox={"boxstyle": "square,pad=0.25", "fc": (1, 1, 1, .78), "ec": c, "lw": .7})
    return ax


def _shade(ax, a, vmax):
    import cartopy.crs as ccrs
    from matplotlib.colors import Normalize
    im = ax.imshow(np.clip(_hires(a), -vmax, vmax), extent=(-180, 180, -45 - .5, 45 + .5), origin="upper",
                   transform=ccrs.PlateCarree(central_longitude=180), cmap=_cmap(),
                   norm=Normalize(-vmax, vmax), interpolation="bilinear", zorder=0)
    return im


def _flow(ax, u, v):
    """white 800 hPa streamlines (thicker where faster) and a grid of white dots, in the map's own coordinates"""
    from matplotlib.axes import Axes
    lat = np.linspace(45, -45, u.shape[0])
    xs = np.arange(u.shape[1], dtype=float) - 180.0
    uu, vv = u[::-1], v[::-1]
    spd = np.hypot(uu, vv)
    lw = np.clip(.45 + 1.9 * spd / max(float(np.nanpercentile(spd, 98)), 1e-6), .45, 2.3)
    Axes.streamplot(ax, xs, lat[::-1], uu, vv, density=(6.5, 1.9), color=(1, 1, 1, .9), linewidth=lw,
                    arrowsize=.45, arrowstyle="-", minlength=.12, zorder=2)
    gx, gy = np.meshgrid(np.arange(-178.0, 180, 4), np.arange(-43.0, 45, 4))
    Axes.scatter(ax, gx.ravel(), gy.ravel(), s=3.2, c="white", alpha=.95, linewidths=0, zorder=2)


def _coasts(ax):
    ax.coastlines("50m", lw=.55, color="#111", zorder=5)


def _title(fig, y, line1, line2, fp, fb):
    fig.text(.985, y, line1, fontproperties=fb, fontsize=16.5, color=INK, ha="right", va="top")
    fig.text(.015, y - .004, line2, fontproperties=fp, fontsize=11, color=MUTED, ha="left", va="top")


def _stats(fig, x, y, lines, edge, fp):
    fig.text(x, y, "\n".join(lines), fontproperties=fp, fontsize=10, color=INK, ha="left", va="top", linespacing=1.5,
             bbox={"boxstyle": "square,pad=0.45", "fc": "white", "ec": edge, "lw": .8})


def _cbar(fig, im, rect, ticks, cold, warm, fp, fb):
    import matplotlib.pyplot as plt
    cax = fig.add_axes(rect)
    cb = plt.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_ticks(ticks)
    cb.set_ticklabels([_n(f"{t:g}") for t in ticks])
    cb.outline.set_edgecolor("#888"); cb.outline.set_linewidth(.6)
    cax.tick_params(length=3, color="#888")
    for t in cax.get_xticklabels():
        t.set_fontproperties(fb); t.set_color(MUTED); t.set_fontsize(9.5)
    x0, x1 = rect[0], rect[0] + rect[2]
    yl = rect[1] - .36 / fig.get_figheight()
    fig.text(x0, yl, cold, fontproperties=fb, fontsize=9.5, color=COLD_INK, ha="left", va="top")
    fig.text(x1, yl, warm, fontproperties=fb, fontsize=9.5, color=WARM_INK, ha="right", va="top")
    fig.text((x0 + x1) / 2, yl, "بلا وحدة", fontproperties=fb, fontsize=9.5, color=MUTED, ha="center", va="top")


def _save(fig, path):
    """save, then pack to 256 colours (dithered): a third of the size, no visible change (the page loads one per day)"""
    fig.savefig(path, facecolor=PAPER)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


def _ticks(vmax):
    step = next(s for s in (.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100) if vmax / s <= 3.2)
    k = int(vmax // step)
    return [step * j for j in range(-k, k + 1)]


def _extremes(a):
    """(fraction of the area above zero, area-weighted mean, (max, lon, lat), (min, lon, lat)) over 45 N .. 45 S"""
    lat = np.linspace(45, -45, a.shape[0])
    w = np.cos(np.radians(lat))[:, None] * np.ones_like(a)
    ok = np.isfinite(a)
    frac = float((w * (a > 0))[ok].sum() / w[ok].sum())
    mean = float((w * a)[ok].sum() / w[ok].sum())
    jx, ix = np.unravel_index(np.nanargmax(a), a.shape)
    jn, i_n = np.unravel_index(np.nanargmin(a), a.shape)
    return frac, mean, (float(a[jx, ix]), ix, lat[jx]), (float(a[jn, i_n]), i_n, lat[jn])


def _where(lo, la):
    return f"عند {_lon_ar(int(lo))} و{_lat_ar(int(round(la)))}"


DOMAIN = "النطاق بين ٤٥ شمالًا و٤٥ جنوبًا"


def _single(field, vmax, ticks, u, v, valid, path, title, stats, cold, warm, cbar_x=.45):
    """one map with its title strip above, streamlines, a stats box and the colour bar under it"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fp, fb = _fonts()
    W, H = 15, 5.9
    fig = plt.figure(figsize=(W, H), dpi=130, facecolor=PAPER)
    y = lambda inch: inch / H
    mw, mh = .9, .9 * W / 4
    _title(fig, y(H - .2), title, _when(valid) + " • النموذج الأمريكي", fp, fb)
    b = H - .75 - mh
    ax = _map(fig, [.07, y(b), mw, y(mh)], fp, fb)
    im = _shade(ax, field, vmax)
    _flow(ax, u, v)
    _coasts(ax)
    _stats(fig, .07, y(b - .5), stats, WARM_INK, fp)
    _cbar(fig, im, [cbar_x, y(b - .62), .48, y(.13)], ticks, cold, warm, fp, fb)
    _save(fig, path)
    plt.close(fig)


def draw(i, u, v, valid, path):
    """the index alone with the 800 hPa streamlines (fig/lw_KK.png); the energy is its own map since 25 Nov 2026"""
    fr, mn, hi, lo = _extremes(i)
    _single(i, 4.0, _ticks(4.0), u, v, valid, path,
            "مؤشر الحدث الدافئ والبارد قرب الأرض (٢ متر و٨٠٠ هكتوباسكال) وخطوط الرياح عند ٨٠٠ هكتوباسكال",
            [f"المؤشر • حدث دافئ على {_n(round(fr * 100))}٪ من {DOMAIN} • المتوسط {_sn(mn, 2)}",
             f"أقوى دافئ {_sn(hi[0])} {_where(hi[1], hi[2])} • أقوى بارد {_sn(lo[0])} {_where(lo[1], lo[2])}"],
            "حمل ضحل أو مكبوت (حدث بارد)", "حمل عميق مهيأ (حدث دافئ)")


def draw_energy(ep, u, v, valid, path):
    """the convective energy of the event: the index times the square root of CAPE (fig/lwe_KK.png; Fahad, 25 Nov 2026:
    the index and the energy each in its own tab and map)"""
    fr, mn, hi, lo = _extremes(ep)
    _single(ep, 120.0, [-120, -80, -40, 0, 40, 80, 120], u, v, valid, path,
            "طاقة الحمل في الحدث: مؤشر الحدث قرب الأرض مضروبًا في جذر طاقة عدم الاستقرار",
            [f"طاقة الحمل • موجبة على {_n(round(fr * 100))}٪ من {DOMAIN} • المتوسط {_sn(mn, 1)}",
             f"أعلى طاقة {_sn(hi[0], 0)} {_where(hi[1], hi[2])} • أشد كبت {_sn(lo[0], 0)} {_where(lo[1], lo[2])}"],
            "حدث بارد يكبت الحمل", "حدث دافئ ومعه طاقة عالية")


def draw_change(di, u, v, valid, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fp, fb = _fonts()
    W, H = 15, 5.9
    fig = plt.figure(figsize=(W, H), dpi=130, facecolor=PAPER)
    y = lambda inch: inch / H
    mw, mh = .9, .9 * W / 4
    _title(fig, y(H - .2), "تغير مؤشر الحدث الدافئ والبارد قرب الأرض (٢ متر و٨٠٠ هكتوباسكال) — ملخص ٢٤ ساعة",
           _when(valid) + " • النموذج الأمريكي", fp, fb)
    b = H - .75 - mh
    ax = _map(fig, [.07, y(b), mw, y(mh)], fp, fb)
    vmax = max(1.0, float(np.ceil(np.nanpercentile(np.abs(di), 99.7) * 2) / 2))
    im = _shade(ax, di, vmax)
    _flow(ax, u, v)
    _coasts(ax)
    fr, mn, hi, lo = _extremes(di)
    _stats(fig, .07, y(b - .5), [f"تغير ٢٤ ساعة • اشتداد على {_n(round(fr * 100))}٪ من {DOMAIN} • متوسط التغير {_sn(mn, 2)}",
                                 f"أكبر ارتفاع {_sn(hi[0])} {_where(hi[1], hi[2])} • أكبر هبوط {_sn(abs(lo[0]))} {_where(lo[1], lo[2])}"],
           WARM_INK, fp)
    _cbar(fig, im, [.45, y(b - .62), .48, y(.13)], _ticks(vmax), "نحو حمل ضحل أو مكبوت (حدث بارد)",
          "نحو حمل عميق مهيأ (حدث دافئ)", fp, fb)
    _save(fig, path)
    plt.close(fig)
