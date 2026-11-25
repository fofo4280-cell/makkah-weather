"""The atmospheric river from the Arabian Sea toward the Red Sea and the south-west of the Kingdom, ECMWF only
(Fahad, 22 Nov 2026: «ارسم رسمه أخرى اعتمد ع الأوروبي فقط توضح فيها النهر المتدفق بلون مميز يتحرك بتقدم الأيام
بدون أسهم.. اللون المميز يكفي واجعلها عصرية», then the «النهر الجوي» tab of the oscillation page).

The river is the water-vapour transport from the ground up to 600 hPa (IVT, kg per metre per second): q*|V|/g
integrated over pressure, every layer cut at the ground (surface pressure), from the IFS 0.25 open data of the
evening (12 UTC) run, 12 UTC of each of the 15 days. It is drawn in the fixed regional bands 150/260/370/480/560/670
(ICON ARIP colours, Fahad 23 Nov 2026) on a light map. No arrows.

The daily line says whether the river reaches three gates and when it first does:
  • جنوب البحر الأحمر (the sea from Bab al-Mandab to off Al-Qunfudhah),
  • جازان وعسير وتهامتها (the land of the south-west below 2000 m),
  • ساحل الحجاز حتى جدة ومكة (the sea and the low land between Al-Lith and Rabigh).
A gate is reached when the 90th percentile of its measure reaches GATE_IVT (the southern Red Sea counts only the
transport coming up the sea from the south). Test 22 Nov 2026 on 291 days (Nov 2024-Mar 2025, Oct-Dec 2025,
Oct-18 Nov 2026), 12 UTC analyses (GFS, same integration) against PERSIANN, a rain day = 10 % of the gate's land
with 1 mm:
  • Jeddah/Makkah coast >= 200: 18 % of days, rain 50 % against 10 % (same or next day 60 % vs 19 %), and it held in
    every season (41/7, 86/8, 67/21 %); 7 Nov 397 and 10 Nov 259 caught, the 13-19 Nov rains were not river-fed.
  • Jazan/Asir land >= 100 (21 % vs 7 %) and the southern Red Sea >= 230 (19 % vs 13 %) are weaker and failed in
    autumn 2025: the southerly up the southern Red Sea is the usual winter flow. They say where the river is, not rain.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import numpy as np

LEVELS = [1000, 925, 850, 700, 600]
EXTENT = (20.0, 100.0, -15.0, 45.0)               # west, east, south, north: the Indian Ocean and East Africa, to read
                                                  # the river with the MJO (Fahad, 23 Nov 2026), north to 45 like Dr.
                                                  # Khalid's river maps (25 Nov 2026)
G = 9.80665
DAYS = 15                                         # day 0 .. 14 at 12 UTC: steps 24 .. 360 of the 12 UTC run
# the fixed regional IVT bands of the river maps Fahad compares (ICON ARIP 1-6), and their colours
CATS = [150, 260, 370, 480, 560, 670]
CAT_COLS = ["#5ea4d8", "#f2c14e", "#f7922e", "#e8635a", "#8a4ccc", "#151a33"]
GATE_IVT = {"rs": 230.0, "sw": 100.0, "hj": 200.0}   # per gate, from the test (see the module text)
GATES = {   # name, (south, north, west, east), "sea" / "land" / "low" (sea + land below 600 m), land ceiling in m
    "rs": ("جنوب البحر الأحمر", (12.6, 19.5, 38.0, 43.6), "sea"),
    "sw": ("جازان وعسير", (16.3, 20.3, 41.3, 44.5), "land"),
    "hj": ("ساحل جدة ومكة", (20.0, 23.2, 38.3, 40.4), "low"),
}
PLACES = [("مكة", 21.42, 39.83, "e"), ("جدة", 21.54, 39.17, "w"), ("جازان", 16.89, 42.55, "e"), ("أبها", 18.22, 42.50, "e"),
          ("عدن", 12.79, 45.03, "e"), ("صنعاء", 15.37, 44.19, "e"), ("سقطرى", 12.47, 53.87, "e"), ("مسقط", 23.59, 58.41, "e"),
          ("الرياض", 24.71, 46.68, "e"), ("مقديشو", 2.05, 45.32, "e"), ("مومباي", 19.08, 72.88, "e"), ("المدينة", 24.47, 39.61, "e"),
          ("نيروبي", -1.29, 36.82, "e"), ("دار السلام", -6.80, 39.28, "e"), ("أديس أبابا", 9.03, 38.74, "w"),
          ("كراتشي", 24.86, 67.00, "e"), ("كولومبو", 6.93, 79.86, "e"), ("ماليه", 4.18, 73.51, "e"),
          ("القاهرة", 30.04, 31.24, "e"), ("بغداد", 33.31, 44.36, "e"), ("طهران", 35.69, 51.39, "e"),
          ("كابل", 34.53, 69.17, "e"), ("دلهي", 28.61, 77.21, "e")]
SEAS = [("بحر العرب", 14.5, 63.0), ("البحر الأحمر", 19.3, 38.6), ("خليج عدن", 11.6, 48.6), ("المحيط الهندي", -8.0, 70.0),
        ("خليج البنغال", 15.0, 88.0), ("الخليج العربي", 27.0, 51.6),
        ("البحر المتوسط", 33.6, 24.5), ("بحر قزوين", 41.6, 50.9)]
PAPER = "#ffffff"
LAND = "#f3ecd3"
SEA = "#dcebf7"


# ---------------------------------------------------------------- data
def _cut_box():
    """rows/cols of the 0.25 global grid (lat 90..-90, lon 0..359.75) inside the map, with a margin"""
    W, E, S, N = EXTENT
    lat = np.linspace(90, -90, 721)
    lon = np.arange(1440) * 0.25
    j = np.where((lat >= S - 1) & (lat <= N + 1))[0]
    i = np.where((lon >= W - 1) & (lon <= E + 1))[0]
    return slice(j[0], j[-1] + 1), slice(i[0], i[-1] + 1), lat[j[0]:j[-1] + 1], lon[i[0]:i[-1] + 1]


def ivt(q, u, v, ps):
    """q/u/v: {level: 2-D}; ps in Pa. Trapezoid in pressure from the ground (or 1000 hPa) up to 600 hPa; a layer
    below the ground counts only for its part above the ground. Returns IVT (kg/m/s) and the integrated vapour (mm)."""
    p = np.array(LEVELS, dtype=float) * 100.0
    ps = np.minimum(ps, 101500.0)
    qu = np.zeros_like(ps)
    qv = np.zeros_like(ps)
    iw = np.zeros_like(ps)
    # the part between the ground and 1000 hPa (when the ground is below 1000 hPa) uses the 1000 hPa values
    extra = np.clip(ps - p[0], 0, None)
    qu += q[LEVELS[0]] * u[LEVELS[0]] * extra
    qv += q[LEVELS[0]] * v[LEVELS[0]] * extra
    iw += q[LEVELS[0]] * extra
    for a, b in zip(range(len(p) - 1), range(1, len(p))):
        lo, hi = p[a], p[b]                    # lo > hi (pressure)
        top = hi
        bot = np.clip(np.minimum(ps, lo), hi, lo)   # the layer from bot to top is above the ground
        dp = bot - top
        la, lb = LEVELS[a], LEVELS[b]
        # values at bot by linear interpolation in pressure between the two levels
        w = (bot - hi) / (lo - hi)
        qb = q[lb] + w * (q[la] - q[lb])
        ub = u[lb] + w * (u[la] - u[lb])
        vb = v[lb] + w * (v[la] - v[lb])
        qu += 0.5 * (qb * ub + q[lb] * u[lb]) * dp
        qv += 0.5 * (qb * vb + q[lb] * v[lb]) * dp
        iw += 0.5 * (qb + q[lb]) * dp
    return np.hypot(qu, qv) / G, iw / G, qu / G, qv / G


def fetch_step(cycle, fh, field=None):
    """IVT and the vapour on the map box for one IFS step. field(cycle, fh, par, lev) -> global 721x1440"""
    import ecmwf
    js, is_, lat, lon = _cut_box()
    jobs = [("sp", "")] + [(par, str(lv)) for lv in LEVELS for par in ("q", "u", "v")]
    if field is None:
        # the bytes are fetched in parallel into ecmwf's cache; the GRIB decoding (pygrib) stays on one thread
        field = ecmwf._field

        def pull(pl):
            key = (cycle, fh, pl[0], pl[1])
            if key in ecmwf._raw:
                return
            it = next(x for x in ecmwf._index(cycle, fh) if x["param"] == pl[0] and x.get("levelist", "") == pl[1])
            ecmwf._raw[key] = ecmwf._get(ecmwf._url(cycle, fh) + ".grib2", (it["_offset"], it["_offset"] + it["_length"] - 1))
        ecmwf._index(cycle, fh)
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(pull, jobs))
    arrs = [field(cycle, fh, p, lv)[js, is_].astype(np.float64) for p, lv in jobs]
    got = dict(zip(jobs, arrs))
    q = {lv: got[("q", str(lv))] for lv in LEVELS}
    u = {lv: got[("u", str(lv))] for lv in LEVELS}
    v = {lv: got[("v", str(lv))] for lv in LEVELS}
    mag, iw, qu, qv = ivt(q, u, v, got[("sp", "")])
    return mag.astype(np.float32), qu.astype(np.float32), qv.astype(np.float32), lat, lon


# ---------------------------------------------------------------- the gates
def gate_masks(lat, lon, land, hgt):
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    out = {}
    for key, (_name, (s, n, w, e), kind) in GATES.items():
        box = (LA >= s) & (LA <= n) & (LO >= w) & (LO <= e)
        if kind == "sea":
            m = box & ~land
        elif kind == "land":
            m = box & land & (hgt < 2000)
        else:
            m = box & (~land | (hgt < 600))
        out[key] = m
    return out


AXIS = (-0.5, 0.866)       # up the Red Sea, from Bab al-Mandab toward the north-north-west


def gate_field(key, mag, qu, qv):
    """what each gate measures: on the southern Red Sea only the transport coming up the sea from the south (the
    northerly flow down the sea carries vapour too, but it is not the river); on land the whole transport"""
    if GATES[key][2] == "sea":
        return np.clip(qu * AXIS[0] + qv * AXIS[1], 0, None)
    return mag


def gate_values(mag, qu, qv, masks):
    return {k: (round(float(np.percentile(gate_field(k, mag, qu, qv)[m], 90)), 0) if m.any() else None)
            for k, m in masks.items()}


def lines(rows):
    """the Arabic line of each day + the first arrival of every gate. rows: [{"d", "g": {gate: ivt90}}]"""
    import figures as F
    first = {}
    for r in rows:
        for k, v in (r.get("g") or {}).items():
            if v is not None and v >= GATE_IVT[k] and k not in first:
                first[k] = r["d"]
    out = []
    for r in rows:
        g = r.get("g") or {}
        hit = [k for k in ("rs", "sw", "hj") if g.get(k) is not None and g[k] >= GATE_IVT[k]]
        if not g:
            t = "لا تتوفر بيانات لهذا اليوم"
        elif hit:
            t = "النهر يصل إلى " + F.ar_list([GATES[k][0] for k in hit])
            if "hj" in hit:
                t += "، فترتفع فرصة المطر على ساحل جدة ومكة إن وُجد رافع كالأخدود"
        else:
            near = max(("rs", "sw", "hj"), key=lambda k: (g.get(k) or 0) / GATE_IVT[k])
            share = (g.get(near) or 0) / GATE_IVT[near]
            t = ("النهر يقترب من " + GATES[near][0] if share >= 0.75 else
                 "لا يصل النهر إلى البحر الأحمر ولا إلى الجنوب الغربي")
        out.append(t)
    return out, first


def first_line(first, d0):
    import figures as F
    if not first:
        return "لا يصل النهر إلى البحر الأحمر ولا إلى الجنوب الغربي في الأيام الخمسة عشر"
    by = {}
    for k in ("rs", "sw", "hj"):
        if k in first:
            by.setdefault(first[k], []).append(GATES[k][0])
    parts = []
    for ds in sorted(by):
        dd = datetime.strptime(ds, "%Y-%m-%d").date()
        day = "اليوم" if dd == d0 else f"{F.WEEK_AR[dd.weekday()]} {F.ar_num(dd.day)} {F.MONTH_AR[dd.month - 1]}"
        parts.append(f"{F.ar_list(by[ds])} {day}")
    return "أول وصول للنهر: " + "، و".join(parts)


# ---------------------------------------------------------------- the picture
def _font():
    try:
        import figures as F
        return F._ar_font()
    except Exception:  # noqa: BLE001
        return "sans-serif"


def _blend(rgb, col, a):
    a = a[..., None]
    return rgb * (1 - a) + np.asarray(col, dtype=float)[None, None, :] * a


def draw(path, mag, lat, lon, land, hgt, width_px=1400, track=None):
    """a light map with the river in the fixed regional IVT bands (Fahad, 23 Nov 2026: the glow was disturbing, «اجعلها
    بهذه الألوان» = the ICON ARIP chart: light blue 150, yellow 260, orange 370, coral 480, violet 560, navy 670);
    no box over the map (the page writes the day above it), the key in a strip under the map"""
    import math
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.colors import BoundaryNorm, ListedColormap, to_rgb
    from scipy.ndimage import gaussian_filter, zoom
    import figures as F
    fam = _font()
    W, E, S, N = EXTENT
    j = (lat >= S) & (lat <= N)
    i = (lon >= W) & (lon <= E)
    la, lo = lat[j], lon[i]
    sb = lambda a: a[np.ix_(j, i)]
    kx = math.cos(math.radians((S + N) / 2))
    asp = (N - S) / ((E - W) * kx)
    leg_h = 0.11
    fig = plt.figure(figsize=(width_px / 200, width_px / 200 * asp * (1 + leg_h)), dpi=200)
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([0, leg_h / (1 + leg_h), 1, 1 / (1 + leg_h)])
    ax.set_facecolor(SEA)
    up = 4
    ext = [lo[0], lo[-1], la[-1], la[0]]
    lf = np.clip(gaussian_filter(zoom(sb(land).astype(float), up, order=1), 1.0), 0, 1)
    sea, ground = np.array(to_rgb(SEA)), np.array(to_rgb(LAND))
    rgb = sea[None, None, :] * (1 - lf[..., None]) + ground[None, None, :] * lf[..., None]
    ax.imshow(rgb, extent=ext, interpolation="bilinear", zorder=0)
    flo, fla = np.linspace(lo[0], lo[-1], lf.shape[1]), np.linspace(la[0], la[-1], lf.shape[0])
    m = gaussian_filter(zoom(sb(mag), up, order=1), 1.2)
    cm = ListedColormap(CAT_COLS)
    lv = CATS + [5000]
    ax.contourf(flo, fla, m, levels=lv, cmap=cm, norm=BoundaryNorm(lv, cm.N), zorder=1, antialiased=True)
    ax.contour(flo, fla, m, levels=[CATS[0]], colors=["#2f6f9f"], linewidths=[.35], alpha=.6, zorder=2)
    ax.contour(flo, fla, lf, levels=[0.5], colors=["#5d6670"], linewidths=[.55], zorder=3)
    txt = [pe.withStroke(linewidth=1.4, foreground=(1, 1, 1, 0.75))]     # soft names (Fahad, 23 Nov 2026)
    for nm, y, x in SEAS:
        ax.text(x, y, F._rtl(nm), ha="center", va="center", fontsize=8, color="#7a93ab", family=fam, zorder=5,
                path_effects=txt, fontweight="normal", alpha=0.9)
    for nm, y, x, side in PLACES:
        ax.plot(x, y, "o", ms=2.4, color="#5b6673", mec="#ffffff", mew=.4, zorder=6)
        dx = .55 if side == "e" else -.55
        ax.text(x + dx, y + .05, F._rtl(nm), ha="left" if side == "e" else "right", va="center", fontsize=7.6,
                color="#4a5562", family=fam, path_effects=txt, zorder=6, fontweight="normal")
    if track is not None:                         # the path of the river core (riverstorm.py), star on this day
        import riverstorm as RS
        RS.draw_track(ax, *track, fam, F)
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(1 / kx)
    ax.axis("off")
    # the key: six bands in a strip under the map
    hh = leg_h / (1 + leg_h)
    x0, wbar = 0.10, 0.80
    n = len(CATS)
    for k, (c, v) in enumerate(zip(CAT_COLS, CATS)):
        bx = fig.add_axes([x0 + wbar * k / n, 0.46 * hh, wbar / n, 0.18 * hh])
        bx.set_facecolor(c)
        bx.set_xticks([]); bx.set_yticks([])
        for sp_ in bx.spines.values():
            sp_.set_visible(False)
        rng = f"{F.ar_num(v)}–{F.ar_num(CATS[k + 1] - 1)}" if k + 1 < n else f"{F.ar_num(v)} فأكثر"
        fig.text(x0 + wbar * (k + .5) / n, 0.26 * hh, F._rtl(rng), ha="center", va="center", fontsize=8,
                 color="#33414f", family=fam)
    fig.text(0.5, 0.84 * hh, F._rtl("شدة تدفق الرطوبة نحو الأعلى حتى ارتفاع ٤ كم تقريبًا، كجم/م/ث"), ha="center",
             va="center", fontsize=8.5, color="#33414f", family=fam)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=200, facecolor=PAPER)
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- nightly
def run(cycle, out_fig, log=print, gfs_fields=None):
    """called by daily.py with the 12 UTC cycle; returns the mjo.json "river" block (None if ECMWF is missing).
    Two passes: the transport of every day first (gates, core track), then the pictures: the river with the core
    path, and the thunderstorm outlook along it (riverstorm.py, rst_KK.png, when stormec_coef.json is present)."""
    import ecmwf
    import riverstorm as RS
    if not ecmwf.available(cycle, 360):
        log("river: ECMWF run not complete, skipped", flush=True)
        return None
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    d0 = (t0 + timedelta(days=1)).date() if t0.hour >= 12 else t0.date()
    rows, masks, land, hgt, mags, grid = [], None, None, None, [], None
    days = [d0 + timedelta(days=k) for k in range(DAYS)]
    fhs = [int((datetime(d.year, d.month, d.day, 12) - t0).total_seconds() // 3600) for d in days]
    for d, fh in zip(days, fhs):
        r, m = {"d": d.isoformat()}, None
        try:
            try:
                m, qu, qv, lat, lon = fetch_step(cycle, fh)
            except Exception as e:  # noqa: BLE001  (the open-data bucket answers 503 SlowDown at times: one more go)
                log("river: retry", d, repr(e)[:100], flush=True)
                import time
                time.sleep(45)
                m, qu, qv, lat, lon = fetch_step(cycle, fh)
            grid = (lat, lon)
            if masks is None:
                land, hgt = static_from(cycle, lat, lon, gfs_fields)
                masks = gate_masks(lat, lon, land, hgt)
            r["g"] = gate_values(m, qu, qv, masks)
            r["peak"] = round(float(np.nanmax(np.where(~land, m, np.nan))), 0)
            log("river", d, r["g"], r["peak"], flush=True)
        except Exception as e:  # noqa: BLE001
            log("river failed", d, repr(e)[:160], flush=True)
            m = None
        rows.append(r)
        mags.append(m)
    cores = RS.track(mags, *grid) if grid is not None else [None] * DAYS
    for r, c in zip(rows, cores):
        r["core"] = None if c is None else [round(c[0], 2), round(c[1], 2), round(c[2])]
    # thunderstorm chance per UTC day (00-24 UTC = steps fh-12 .. fh+12), where the run reaches the day's end
    C, probs = RS.coef(), [None] * DAYS
    if C is not None and grid is not None:
        js, is_, _, _ = _cut_box()
        for k, (d, fh) in enumerate(zip(days, fhs)):
            try:
                raw = RS.fetch_day(cycle, fh - 12, js, is_)
                if raw is not None:
                    probs[k] = RS.limit(RS.probability(raw, hgt, land, d.timetuple().tm_yday, C), *grid)
            except Exception as e:  # noqa: BLE001
                log("river storms failed", d, repr(e)[:160], flush=True)
    for r, p, c in zip(rows, probs, cores):
        pk, mn = RS.around(p, c, *grid) if grid is not None else (None, None)
        r["storm"] = None if pk is None else [round(pk), round(mn, 1)]
    peak = [None if r.get("storm") is None else r["storm"][0] for r in rows]
    mean = [None if r.get("storm") is None else r["storm"][1] for r in rows]
    for k, m in enumerate(mags):
        if m is None:
            continue
        try:
            draw(os.path.join(out_fig, f"riv_{k:02d}.png"), m, *grid, land, hgt, track=(cores, days, k))
            if probs[k] is not None:
                RS.draw(os.path.join(out_fig, f"rst_{k:02d}.png"), probs[k], *grid, land, cores, days, k, peak, mean,
                        mag=m)
        except Exception as e:  # noqa: BLE001
            log("river picture failed", days[k], repr(e)[:160], flush=True)
    texts, first = lines(rows)
    for r, t in zip(rows, texts):
        r["text"] = t
    storm_days = sum(p is not None for p in probs)
    return {"days": [r["d"] for r in rows], "rows": rows, "first": first, "first_text": first_line(first, d0),
            "extent": list(EXTENT), "gate": GATE_IVT, "model": "ecmwf", "storm_days": storm_days,
            "storm_box": list(RS.STORM_BOX)}


def static_from(cycle, lat, lon, gfs_fields=None):
    """land mask and ground height on the map grid: from the GFS 0.25 surface file of the same cycle (the same points,
    as redsea.py does), or from the IFS step 0 (lsm, z) when GFS is not given or fails"""
    js, is_, _, _ = _cut_box()
    if gfs_fields is not None:
        try:
            f = gfs_fields(cycle, 24, res="0p25", fields=[("land", r":LAND:surface:"), ("hgt", r":HGT:surface:")])
            return np.asarray(f["land"])[js, is_] > 0.5, np.clip(np.asarray(f["hgt"], dtype=float)[js, is_], 0, None)
        except Exception as e:  # noqa: BLE001
            print("river: GFS terrain failed, IFS instead", repr(e)[:120], flush=True)
    import ecmwf
    land = ecmwf._field(cycle, 0, "lsm", "")[js, is_] > 0.5
    hgt = np.clip(ecmwf._field(cycle, 0, "z", "")[js, is_] / G, 0, None)
    return land, hgt
