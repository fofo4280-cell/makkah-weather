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
SEED_BOX = (0.0, 30.0, 38.0, 76.0)        # south, north, west, east: where the core is looked for and followed (the
                                          # river toward Arabia, not the Bay of Bengal one)
STORM_BOX = (0.0, 36.0, 30.0, 80.0)       # south, north, west, east: the chance is shown only here, around the area
                                          # the fit was made and tested on (2-33 N, 34-75 E)
STEP_DEG = 8.0
CORE_MIN = 250.0
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
    """[(lat, lon, ivt) or None] per day"""
    from scipy.ndimage import gaussian_filter
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    out, prev = [], None
    for m in mags:
        if m is None:
            out.append(None)
            continue
        sm = gaussian_filter(m, 3)
        if prev is not None:
            s, n, w, e = SEED_BOX
            near = (_km(prev[0], prev[1], LA, LO) <= STEP_DEG * 111) & (LA >= s - 4) & (LA <= n + 4) & (LO >= w - 4) \
                & (LO <= e)
            cand = np.where(near, sm, -1)
            j, i = np.unravel_index(np.argmax(cand), cand.shape)
            if cand[j, i] >= CORE_MIN:
                prev = (float(lat[j]), float(lon[i]), float(cand[j, i]))
                out.append(prev)
                continue
        s, n, w, e = SEED_BOX
        box = (LA >= s) & (LA <= n) & (LO >= w) & (LO <= e)
        cand = np.where(box, sm, -1)
        j, i = np.unravel_index(np.argmax(cand), cand.shape)
        prev = (float(lat[j]), float(lon[i]), float(cand[j, i])) if cand[j, i] >= CORE_MIN else None
        out.append(prev)
    return out


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
        if seg and i - seg[-1][0] > 1:
            ax.plot([q[1][1] for q in seg], [q[1][0] for q in seg], color=colour_, lw=1.3, zorder=7, path_effects=halo)
            seg = []
        seg.append((i, c))
    ax.plot([q[1][1] for q in seg], [q[1][0] for q in seg], color=colour_, lw=1.3, zorder=7, path_effects=halo)
    for i, c in pts:
        ax.plot(c[1], c[0], "o", ms=2.6, color=colour_, mec="white", mew=0.5, zorder=8)
        if i % 2 == 0 and i != k:
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
    W, E, S, N = RV.EXTENT
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
        ax.contour(flo, fla, mm, levels=[260, 480], colors=["#3f6fa0", "#26476e"], linewidths=[.7, 1.0], alpha=.75,
                   zorder=4)
    s_, n_, w_, e_ = STORM_BOX                # where the chance is drawn
    ax.plot([w_, e_, e_, w_, w_], [s_, s_, n_, n_, s_], color="#9aa5b1", lw=.5, ls=(0, (3, 3)), zorder=4)
    ax.contour(flo, fla, lf, levels=[0.5], colors=["#5d6670"], linewidths=[.5], zorder=3)
    txt = [pe.withStroke(linewidth=1.4, foreground=(1, 1, 1, 0.75))]
    for nm, y, x in RV.SEAS:
        ax.text(x, y, F._rtl(nm), ha="center", va="center", fontsize=8, color="#7a93ab", family=fam, zorder=5,
                path_effects=txt, fontweight="normal", alpha=0.9)
    for nm, y, x, side in RV.PLACES:
        ax.plot(x, y, "o", ms=2.4, color="#5b6673", mec="#ffffff", mew=.4, zorder=6)
        dx = .55 if side == "e" else -.55
        ax.text(x + dx, y + .05, F._rtl(nm), ha="left" if side == "e" else "right", va="center", fontsize=7.6,
                color="#4a5562", family=fam, path_effects=txt, zorder=6, fontweight="normal")
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
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=160, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass
