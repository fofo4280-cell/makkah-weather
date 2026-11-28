"""Thunderstorm outlook along the atmospheric river, ECMWF only (Fahad, 25 Nov 2026, after Dr. Khalid Al-Otaibi's
"Atmospheric River Tracking - Thunderstorm Outlook" from DWD-ICON: «ضيفها لتبويب الجوي لكن باستخدام الأوروبي»).

For every day of the river tab:
  • the chance (%) of a strong storm (PERSIANN 20 mm or more within 25 km in the UTC day) from the ingredients of the
    ECMWF 12 UTC run (stormec_study.py: rain of the day, most-unstable CAPE of 09-21 UTC, deep shear, PW, RH 700/500,
    T500, ground, season), joined by the logistic fit in stormec_coef.json;
  • the core of the river: the strongest transport (IVT smoothed over ~1 degree), followed day to day within 8 degrees
    ("feature continuity"), started near Arabia and the Arabian Sea;
  • around the core (500 km): the largest chance and the mean chance, for the time panel under the map.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_BOX = (3.0, 24.0, 38.0, 75.0)        # south, north, west, east: where the core is looked for and followed (the
                                          # river toward Arabia, not the Bay of Bengal one)
STORM_BOX = (0.0, 36.0, 30.0, 80.0)       # south, north, west, east: the chance is shown only here, around the area
                                          # the fit was made and tested on (2-33 N, 34-75 E)
# the Kingdom's towns on the storm map, soft and small (the main cities are already in river.PLACES)
KSA_TOWNS = [("تبوك", 28.38, 36.57, "e"), ("ضباء", 27.35, 35.70, "w"), ("الوجه", 26.24, 36.45, "w"),
             ("أملج", 25.05, 37.27, "w"), ("ينبع", 24.09, 38.06, "w"), ("رابغ", 22.80, 39.03, "w"),
             ("الطائف", 21.27, 40.42, "s"), ("الليث", 20.15, 40.27, "w"), ("القنفذة", 19.13, 41.08, "e"),
             ("الباحة", 20.01, 41.47, "e"), ("نجران", 17.49, 44.13, "e"),
             ("حائل", 27.52, 41.69, "e"), ("بريدة", 26.33, 43.97, "e"), ("سكاكا", 29.97, 40.21, "e"),
             ("عرعر", 30.98, 41.04, "e"), ("الدمام", 26.43, 50.10, "s"), ("العلا", 26.61, 37.92, "e"),
             ("خيبر", 25.70, 39.29, "e"), ("وادي الدواسر", 20.47, 44.78, "e")]
CORE_MIN = 250.0
JUMP_KM = 1200.0                          # the centre moves less than this in a day, or it is another river
RADIUS_KM = 500.0
PAL = [(2, "#e8e6fb", 0), (5, "#c9c3f5", 140), (10, "#7fc8e8", 190), (15, "#27d7d0", 210), (20, "#8cf37a", 225),
       (25, "#f4ee1d", 235), (30, "#ffb000", 240), (40, "#ff5810", 245), (50, "#e20000", 248), (60, "#8a0012", 250),
       (70, "#575757", 250), (85, "#c9c9c9", 250)]


def coef():
    p = os.path.join(HERE, "stormec_coef.json")
    return json.load(open(p)) if os.path.exists(p) else None


# ---------------------------------------------------------------- ingredients
def steps_of(cycle, fh0):
    """the IFS steps inside 09-21 UTC of the day starting fh0 hours after the run, the 15 UTC one, and the rain pair"""
    import ecmwf
    st = ecmwf.steps(cycle)
    inst = [s for s in st if fh0 + 9 <= s <= fh0 + 21]
    mid = min(inst, key=lambda s: abs(s - (fh0 + 15))) if inst else None
    return inst, mid, (fh0, fh0 + 24)


def fetch_day(cycle, fh0, js, is_):
    """raw ingredient fields of one UTC day (bytes fetched in threads, decoded on this thread: pygrib is not
    thread-safe). None when the day runs past the end of the IFS run."""
    import ecmwf
    inst, mid, (a, b) = steps_of(cycle, fh0)
    if not inst or b > ecmwf.steps(cycle)[-1]:
        return None
    return _fetch(cycle, inst, mid, a, b, js, is_)


def fetch_hour(cycle, s, js, is_):
    """the same ingredients around one IFS step s (Fahad, 28 Nov 2026: «العواصف الرعدية على مسار النهر خليها كل ٣
    ساعات»): the instability, shear, moisture and T500 of that hour, and the rain of the 24 h centred on it (the fit
    is for a day's rain), so the chance moves with the hour. None when s +- 12 h leaves the run."""
    import ecmwf
    st = ecmwf.steps(cycle)
    if s - 12 < 0 or s + 12 > st[-1]:
        return None
    a = min(st, key=lambda x: abs(x - (s - 12)))
    b = min(st, key=lambda x: abs(x - (s + 12)))
    return _fetch(cycle, [s], s, a, b, js, is_)


def _fetch(cycle, inst, mid, a, b, js, is_):
    import ecmwf
    jobs = [("mucape", "", s) for s in inst] + [("tp", "", a), ("tp", "", b)]
    jobs += [(p, lv, mid) for p, lv in (("10u", ""), ("10v", ""), ("u", "500"), ("v", "500"), ("r", "700"),
                                         ("r", "500"), ("t", "500"), ("tcwv", ""))]

    def pull(j):
        p, lv, fh = j
        key = (cycle, fh, p, lv)
        if key not in ecmwf._raw:
            it = next(x for x in ecmwf._index(cycle, fh) if x["param"] == p and x.get("levelist", "") == lv)
            ecmwf._raw[key] = ecmwf._get(ecmwf._url(cycle, fh) + ".grib2",
                                         (it["_offset"], it["_offset"] + it["_length"] - 1))
    for fh in sorted({j[2] for j in jobs}):
        ecmwf._index(cycle, fh)
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(pull, jobs))
    raw = {}
    for p, lv, fh in jobs:
        raw.setdefault(p + lv, []).append(ecmwf._field(cycle, fh, p, lv)[js, is_].astype(np.float32))
    return raw


def probability(raw, hgt, land, doy, C):
    import stormec_study as S
    f = S.features(raw, hgt, land, doy)
    z = C["icpt"] + sum(c * f[n] for n, c in zip(C["names"], C["coef"]))
    return 100.0 / (1.0 + np.exp(-z))


def limit(p, lat, lon):
    """the chance outside STORM_BOX set to NaN (not tested there)"""
    s, n, w, e = STORM_BOX
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    return np.where((LA >= s) & (LA <= n) & (LO >= w) & (LO <= e), p, np.nan).astype(np.float32)


# ---------------------------------------------------------------- the core of the river
def _km(la0, lo0, la, lo):
    r = np.radians
    return 6371.0 * np.arccos(np.clip(np.sin(r(la0)) * np.sin(r(la)) + np.cos(r(la0)) * np.cos(r(la)) * np.cos(r(lo - lo0)), -1, 1))


def track(mags, lat, lon):
    """[(lat, lon, ivt) or None] per day: the centre of the river over the Arabian Sea and its approaches to Arabia
    (SEED_BOX): the transport-weighted centre of the part >= CORE_MIN (smoothed over ~1 degree), so it moves with the
    body of the river instead of jumping between separate maxima; ivt = the largest value there"""
    from scipy.ndimage import gaussian_filter, label
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    s, n, w, e = SEED_BOX
    prev = None
    box = (LA >= s) & (LA <= n) & (LO >= w) & (LO <= e)
    out = []
    for m in mags:
        if m is None:
            out.append(None)
            continue
        sm = gaussian_filter(m, 3)
        wt = np.where(box, np.clip(sm - CORE_MIN, 0, None), 0.0)
        lab, nl = label(wt > 0)
        new = prev is None
        if nl == 0:
            out.append(None)
            continue
        size = np.bincount(lab.ravel(), weights=wt.ravel())
        size[0] = 0
        if prev is not None:                      # keep with the same body when it is still there
            cen = [(_centre(lab == q, wt, LA, LO), q) for q in range(1, nl + 1) if size[q] > 0.25 * size.max()]
            c, q = min(cen, key=lambda c: _km(prev[0], prev[1], c[0][0], c[0][1]))
            if _km(prev[0], prev[1], c[0], c[1]) > JUMP_KM:   # no body near yesterday's: a new river, a new line
                q, new = int(np.argmax(size)), True
        else:
            q = int(np.argmax(size))
        if (lab == q).sum() < 40:                 # less than ~2.5 square degrees: no river body
            out.append(None)
            prev = None
            continue
        wt = np.where(lab == q, wt, 0.0)
        out.append((float((wt * LA).sum() / wt.sum()), float((wt * LO).sum() / wt.sum()), float(sm[wt > 0].max()),
                    bool(new)))
        prev = out[-1]
    return out


def _centre(mask, wt, LA, LO):
    w = np.where(mask, wt, 0.0)
    return float((w * LA).sum() / w.sum()), float((w * LO).sum() / w.sum())


def around(p, core, lat, lon):
    """(largest, mean) chance within 500 km of the core"""
    if p is None or core is None:
        return None, None
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    v = p[_km(core[0], core[1], LA, LO) <= RADIUS_KM]
    v = v[np.isfinite(v)]
    return (float(v.max()), float(v.mean())) if v.size else (None, None)


# ---------------------------------------------------------------- pictures
def colour(p):
    vs = np.array([s[0] for s in PAL], float)
    rgb = np.array([[int(s[1][i:i + 2], 16) / 255 for i in (1, 3, 5)] for s in PAL], float)
    al = np.array([s[2] for s in PAL], float) / 255
    out = np.zeros(p.shape + (4,), np.float32)
    for ch in range(3):
        out[..., ch] = np.interp(p, vs, rgb[:, ch])
    a = np.interp(p, vs, al)
    a[p < vs[0]] = 0
    out[..., 3] = a
    return out


def draw_track(ax, cores, days, k, fam, F, colour_="#1d2530"):
    """the path of the core through the days, a label on every second day, a star on the shown day"""
    from matplotlib import patheffects as pe
    pts = [(i, c) for i, c in enumerate(cores) if c is not None]
    if len(pts) < 2:
        return
    halo = [pe.withStroke(linewidth=2.2, foreground=(1, 1, 1, 0.85))]
    seg = []
    for i, c in pts:
        if seg and (i - seg[-1][0] > 1 or (len(c) > 3 and c[3])):
            ax.plot([q[1][1] for q in seg], [q[1][0] for q in seg], color=colour_, lw=1.3, zorder=7, path_effects=halo)
            seg = []
        seg.append((i, c))
    ax.plot([q[1][1] for q in seg], [q[1][0] for q in seg], color=colour_, lw=1.3, zorder=7, path_effects=halo)
    placed = [cores[k][:2]] if 0 <= k < len(cores) and cores[k] is not None else []
    for i, c in pts:
        ax.plot(c[1], c[0], "o", ms=2.6, color=colour_, mec="white", mew=0.5, zorder=8)
        if i != k and all(abs(c[0] - p[0]) > 1.6 or abs(c[1] - p[1]) > 4.5 for p in placed):   # no piled-up dates
            placed.append(c[:2])
            dd = days[i]
            ax.text(c[1], c[0] + 0.9, F._rtl(f"{F.ar_num(dd.day)} {F.MONTH_AR[dd.month - 1]}"), ha="center",
                    va="bottom", fontsize=6.2, color="#33414f", family=fam, path_effects=halo, zorder=8)
    if 0 <= k < len(cores) and cores[k] is not None:
        c = cores[k]
        ax.plot(c[1], c[0], marker="*", ms=12, color="#ffd23a", mec="#1d2530", mew=0.8, zorder=9)


def draw_panel(fig, rect, days, peak, mean, k, fam, F):
    """the time panel under the map: the largest and the mean chance within 500 km of the core, the shown day marked"""
    ax = fig.add_axes(rect)
    x = np.arange(len(days))
    pk = np.array([np.nan if v is None else v for v in peak])
    mn = np.array([np.nan if v is None else v for v in mean])
    ax.fill_between(x, 0, np.nan_to_num(pk), where=np.isfinite(pk), color="#ffd9c7", alpha=0.6, lw=0)
    ax.plot(x, pk, color="#1d2530", lw=1.6)
    ax.plot(x, mn, color="#7a8794", lw=1.2, ls=(0, (4, 2)))
    if 0 <= k < len(days):
        ax.axvline(k, color="#e0535a", lw=1, alpha=0.7)
        if not np.isnan(pk[k]):
            ax.plot(k, pk[k], "o", ms=5, color="#e0535a", mec="white", mew=0.8, zorder=5)
    ax.set_xlim(-0.3, len(days) - 0.7)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([F.ar_num(v) for v in (0, 25, 50, 75, 100)], fontsize=6.5, color="#5b6673", family=fam)
    ax.set_xticks(x)
    ax.set_xticklabels([F.ar_num(d.day) for d in days], fontsize=6.5, color="#5b6673", family=fam)
    ax.tick_params(length=2, color="#c5ccd3")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c5ccd3")
    ax.grid(axis="y", color="#e6eaee", lw=0.6)
    ax.set_facecolor("#ffffff")
    fig.text(rect[0] + rect[2], rect[1] + rect[3] * 1.12,
             F._rtl("على مسار قلب النهر (٥٠٠ كم حوله): الخط المتصل أعلى احتمال، والمتقطع متوسطه"),
             ha="right", va="bottom", fontsize=7, color="#33414f", family=fam)


def draw(path, p, lat, lon, land, cores, days, k, peak, mean, mag=None, width_px=1400):
    import math
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.colors import to_rgb
    from scipy.ndimage import gaussian_filter, zoom
    import figures as F
    import river as RV
    fam = RV._font()
    S, N, W, E = STORM_BOX                    # the storm map covers only where the chance was made and tested
    j = (lat >= S) & (lat <= N)
    i = (lon >= W) & (lon <= E)
    la, lo = lat[j], lon[i]
    sb = lambda a: a[np.ix_(j, i)]  # noqa: E731
    kx = math.cos(math.radians((S + N) / 2))
    asp = (N - S) / ((E - W) * kx)
    key_h, pan_h = 0.12, 0.26                     # fractions of the map height: colour key, time panel
    tot = 1 + key_h + pan_h
    fig = plt.figure(figsize=(width_px / 200, width_px / 200 * asp * tot), dpi=200)
    fig.patch.set_facecolor("#ffffff")
    ax = fig.add_axes([0, (key_h + pan_h) / tot, 1, 1 / tot])
    up = 4
    ext = [lo[0], lo[-1], la[-1], la[0]]
    lf = np.clip(gaussian_filter(zoom(sb(land).astype(float), up, order=1), 1.0), 0, 1)
    sea, ground = np.array(to_rgb(RV.SEA)), np.array(to_rgb(RV.LAND))
    rgb = sea[None, None, :] * (1 - lf[..., None]) + ground[None, None, :] * lf[..., None]
    ax.imshow(rgb, extent=ext, interpolation="bilinear", zorder=0)
    if p is not None:
        pp = np.clip(gaussian_filter(zoom(np.nan_to_num(sb(p)), up, order=1), 1.0), 0, 100)
        ax.imshow(colour(pp), extent=ext, interpolation="bilinear", zorder=1)
    flo, fla = np.linspace(lo[0], lo[-1], lf.shape[1]), np.linspace(la[0], la[-1], lf.shape[0])
    if mag is not None:                       # the river itself: its 260 and 480 outlines (the ARIP yellow and coral)
        mm = gaussian_filter(zoom(sb(mag), up, order=1), 1.2)
        ax.contour(flo, fla, mm, levels=[260, 480], colors=["#2b5f93", "#17324f"], linewidths=[1.0, 1.4], alpha=.9,
                   zorder=4)
    ax.contour(flo, fla, lf, levels=[0.5], colors=["#5d6670"], linewidths=[.5], zorder=3)
    txt = [pe.withStroke(linewidth=1.4, foreground=(1, 1, 1, 0.75))]
    inside = lambda y, x: S + 1 < y < N - 1 and W + 1 < x < E - 1  # noqa: E731
    for nm, y, x in [q for q in RV.SEAS if inside(q[1], q[2])]:
        ax.text(x, y, F._rtl(nm), ha="center", va="center", fontsize=8, color="#7a93ab", family=fam, zorder=5,
                path_effects=txt, fontweight="normal", alpha=0.9)
    for nm, y, x, side in [q for q in RV.PLACES if inside(q[1], q[2])]:
        ax.plot(x, y, "o", ms=2.4, color="#5b6673", mec="#ffffff", mew=.4, zorder=6)
        dx = .55 if side == "e" else -.55
        ax.text(x + dx, y + .05, F._rtl(nm), ha="left" if side == "e" else "right", va="center", fontsize=7.6,
                color="#4a5562", family=fam, path_effects=txt, zorder=6, fontweight="normal")
    # the Kingdom's regions and its towns in a soft hand (Fahad, 28 Nov 2026: «حسن الخريطة بتقسيمها إلى مناطق مع ذكر
    # أسماء المدن بخط ناعم»)
    try:
        import sa_geo
        for r_ in sa_geo.regions():
            g_ = r_["geom"]
            for poly in getattr(g_, "geoms", [g_]):
                xs, ys = poly.exterior.xy
                ax.plot(xs, ys, color="#8b949e", lw=.35, alpha=.75, zorder=3)
    except Exception as e:  # noqa: BLE001
        print("storm map regions failed", repr(e)[:100], flush=True)
    soft = [pe.withStroke(linewidth=1.2, foreground=(1, 1, 1, 0.7))]
    for nm, y, x, side in KSA_TOWNS:
        ax.plot(x, y, "o", ms=1.6, color="#7b8590", mec="none", zorder=6)
        dx, dy, ha = {"e": (.4, 0, "left"), "w": (-.4, 0, "right"), "s": (0, -.55, "center"), "n": (0, .55, "center")}[side]
        ax.text(x + dx, y + dy, F._rtl(nm), ha=ha, va="center", fontsize=5.6, color="#69737e", family=fam,
                path_effects=soft, zorder=6, fontweight="normal", alpha=.95)
    draw_track(ax, cores, days, k, fam, F)
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(1 / kx)
    ax.axis("off")
    # colour key strip
    y0 = (pan_h + 0.42 * key_h) / tot
    bx = fig.add_axes([0.12, y0, 0.76, 0.2 * key_h / tot])
    vv = np.linspace(2, 90, 400)[None, :]
    c = colour(vv)
    c[..., 3] = np.maximum(c[..., 3], 0.25)
    bx.imshow(c, aspect="auto", extent=[2, 90, 0, 1])
    bx.set_yticks([])
    bx.set_xticks([10, 20, 30, 40, 50, 60, 70, 80])
    bx.set_xticklabels([F.ar_num(v) for v in (10, 20, 30, 40, 50, 60, 70, 80)], fontsize=6.5, color="#5b6673",
                       family=fam)
    bx.tick_params(length=2, color="#c5ccd3")
    for s in bx.spines.values():
        s.set_visible(False)
    fig.text(0.5, (pan_h + 0.83 * key_h) / tot, F._rtl("احتمال العاصفة الرعدية الشديدة خلال اليوم (٪)"), ha="center",
             va="center", fontsize=7.5, color="#33414f", family=fam)
    fig.text(0.5, (pan_h + 0.06 * key_h) / tot, F._rtl("الخطوط الزرقاء: حد النهر ٢٦٠ و٤٨٠ — النقاط: قلب النهر يومًا بيوم"),
             ha="center", va="center", fontsize=6.8, color="#5b6673", family=fam)
    draw_panel(fig, [0.08, 0.2 * pan_h / tot, 0.86, 0.6 * pan_h / tot], days, peak, mean, k, fam, F)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=200, facecolor="#ffffff")
    b = ax.get_position()        # the map's place in the picture, for tap-a-point coordinates on the page (both the
    pan = [round(float(v), 5) for v in (b.x0, b.x1, b.y0, b.y1)] + [W, E, S, N]   # day maps and the 3-hourly ones)
    F.GEO["rst.png"] = F.GEO["rsth.png"] = [pan]
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=160, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- every 3 hours (28 Nov 2026)
_H = {}


def _frame(job):
    k, h, s, path = job
    g = _H
    try:
        raw = fetch_hour(g["cycle"], s, g["js"], g["is_"])
        if raw is None:
            return k, h, None
        p = limit(probability(raw, g["hgt"], g["land"], g["doy"][k], g["C"]), *g["grid"])
        pk, mn = around(p, g["cores"][k], *g["grid"])
        draw(path + ".png", p, *g["grid"], g["land"], g["cores"], g["days"], k, g["peak"], g["mean"], mag=g["mags"][k])
        from PIL import Image
        Image.open(path + ".png").convert("RGB").save(path + ".webp", "WEBP", quality=80, method=4)
        os.remove(path + ".png")
        return k, h, {"h": h, "s": None if pk is None else [round(pk), round(mn, 1)]}
    except Exception as e:  # noqa: BLE001
        print("river storms hourly failed", k, h, repr(e)[:160], flush=True)
        return k, h, None


def hourly(cycle, out_fig, days, grid, land, hgt, cores, peak, mean, mags, C, js, is_, procs=2, log=print):
    """rsth_KK_HH.webp at every IFS step (3-hourly to 144 h, 6-hourly after), HH = Makkah hour, KK = the river day
    of that Makkah date; returns hrs[k] = [{h, s: [peak, mean around the core] or None}]"""
    import time
    from datetime import datetime, timedelta
    from multiprocessing import get_context
    import ecmwf
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    di = {d: k for k, d in enumerate(days)}
    jobs = []
    for s in ecmwf.steps(cycle):
        mk = t0 + timedelta(hours=s + 3)
        k = di.get(mk.date())
        if k is None or mk.hour % 3:
            continue
        jobs.append((k, mk.hour, s, os.path.join(out_fig, f"rsth_{k:02d}_{mk.hour:02d}")))
    _H.update(cycle=cycle, js=js, is_=is_, grid=grid, land=land, hgt=hgt, cores=cores, days=days, peak=peak,
              mean=mean, mags=mags, C=C, doy=[d.timetuple().tm_yday for d in days])
    ts, res = time.time(), {}
    with get_context("fork").Pool(procs) as pool:
        for k, h, r in pool.imap_unordered(_frame, jobs):
            if r:
                res.setdefault(k, []).append(r)
    log("river storms hourly:", sum(len(v) for v in res.values()), "of", len(jobs), "frames in",
        int(time.time() - ts), "s", flush=True)
    return [sorted(res.get(k, []), key=lambda x: x["h"]) for k in range(len(days))]
