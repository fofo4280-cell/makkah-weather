"""Red Sea flow toward the coasts, for the «الرياح» tab of the oscillation page (Fahad, 19 Nov 2026: «جميلة خريطة
التدفق هذه للبحر ونضيفها لقسم الرياح خاصة لتوقع السواحل.. لكنها تختلف عن الحمل الحراري وتدفقه»).

A coastal product, not a convective-jet index: it shows where the warm moist sea air is pushed along the Red Sea and
onto the coasts. Mean of 09, 12 and 15 UTC (12-6 PM Makkah), wind = mean of 925 hPa and 10 m. Source: ECMWF open
data (IFS 0.25, MUCAPE), the one exception to the page's GFS-only rule (Fahad, 19 Nov 2026: Dr. Khalid Al-Otaibi
reads humidity, accumulated rain and the convective flow from ECMWF, the big picture from GFS); GFS when ECMWF is
missing, with its own thresholds (SRC). The energy tongue (CAPE >= 1000 along the sea and coast) is described, not
scored: in ECMWF it reaches 23-29 N on nearly every Oct-Nov day (corr with Hijaz rain 0.12).
  - along-sea component = -0.5 u + 0.866 v (the sea's axis runs about 330 deg); the meeting line is where the
    southerly flow coming up from the south meets the northerly (first + to - change going north from 15 N, 1 deg
    smoothing). The sea air feeds the coast south of that line.
  - north coast (Jeddah, Rabigh, Al-Lith, Makkah plain), score: +1 the southerly reaches 21 N (line >= 21 or along
    mean 19-24 N >= 0), +1 sea CAPE (p75, 16-23 N) >= 4000 ECMWF / 2500 GFS, +1 south-westerly aloft (v500 20-26 N,
    36-42 E) >= 2 m/s, -1 northerly <= -4 m/s over 19-24 N; land PW (18.5-23.5 N, 38.5-42 E) < 20 mm: confined over
    the sea. Supportive from 2 points (ECMWF) / 1 point (GFS).
  - south coast (Al-Qunfudhah to Jazan): sea PW (16-23 N) >= 35 mm feeds it; named when the meeting line is on it.
Test 1 Oct-18 Nov 2026 (same for GFS and ECMWF with SRC thresholds) vs PERSIANN-PDIR-Now (Jeddah/Makkah/Taif/Rabigh/Al-Lith land 20-23.5 N): supportive 24 days
mean wet share 13.5 % (10 of 11 wide days), not supportive 25 days 3.0 % (1 wide: 10 Nov, stratiform). South: sea PW
>= 35 mm 15 % vs 5 %. Part of the gap is seasonal (sea CAPE ~3000 in Oct, ~1300-1700 in Nov).

run(gfs_fields, cycle, out_fig) -> dict for mjo.json["rsflow"]; draws fig/rsf_NN.png, today (cycle date + 1) and
NEXT days after.
"""
import math
import os
from datetime import datetime, timedelta

import numpy as np

NEXT = 7
EXTENT = (33.5, 45.5, 14.0, 28.5)          # west, east, south, north of the map
CUT = (12.0, 36.0, 28.0, 52.0)             # south, north, west, east of the data
FIELDS = [("u925", r":UGRD:925 mb:"), ("v925", r":VGRD:925 mb:"), ("u10", r":UGRD:10 m above ground:"),
          ("v10", r":VGRD:10 m above ground:"), ("v500", r":VGRD:500 mb:"), ("cape", r":CAPE:180-0 mb above ground:"),
          ("pw", r":PWAT:entire atmosphere")]
STATIC = [("hgt", r":HGT:surface:"), ("land", r":LAND:surface:")]
WIND1 = [("u10", r":UGRD:10 m above ground:")]
COAST = [(16.9, "جازان"), (18.2, "الشقيق"), (19.1, "القنفذة"), (20.15, "الليث"), (21.5, "جدة"), (22.8, "رابغ"),
         (24.1, "ينبع"), (25.0, "أملج"), (26.2, "الوجه"), (27.4, "ضباء")]
PLACES = [("جدة", 21.54, 39.17), ("مكة", 21.42, 39.83), ("الطائف", 21.27, 40.42), ("الليث", 20.15, 40.27),
          ("القنفذة", 19.13, 41.08), ("جازان", 16.89, 42.55), ("ينبع", 24.09, 38.06), ("المدينة", 24.47, 39.61),
          ("الباحة", 20.01, 41.47), ("أبها", 18.22, 42.50), ("رابغ", 22.80, 39.03), ("الوجه", 26.2, 36.47)]
CAPE_COLS = [(0, "#00000000"), (.03, "#00000000"), (.08, "#2c7f8c"), (.2, "#3fa79a"), (.38, "#a9cf6a"),
             (.55, "#e9cf55"), (.75, "#e58a4c"), (1, "#c2445a")]
CAPE_MAX = 3500
BG = "#0c1118"
AR = str.maketrans("0123456789.-", "٠١٢٣٤٥٦٧٨٩٫−")


EC = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
EC_FIELDS = [("u10", "10u", ""), ("v10", "10v", ""), ("u925", "u", "925"), ("v925", "v", "925"), ("v500", "v", "500"),
             ("cape", "mucape", ""), ("pw", "tcwv", "")]
TONGUE = 1000                              # J/kg: the edge of the energy tongue


def _get(url, rng=None, tries=8):
    import time
    import urllib.request
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % rng} if rng else {})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if k == tries - 1:
                raise
            time.sleep(4 + 6 * k)


def ec_fields(cycle, fh):
    """ECMWF open data (IFS 0.25) fields of one step on the GFS layout (lat 90..-90, lon 0..360)"""
    import json
    import pygrib
    d, hh = cycle[:8], cycle[8:10]
    url = f"{EC}/{d}/{hh}z/ifs/0p25/oper/{d}{hh}0000-{fh}h-oper-fc"
    idx = [json.loads(x) for x in _get(url + ".index").decode().splitlines()]
    out = {}
    for name, par, lev in EC_FIELDS:
        it = next(x for x in idx if x["param"] == par and x.get("levelist", "") == lev)
        msg = _get(url + ".grib2", (it["_offset"], it["_offset"] + it["_length"] - 1))
        g = pygrib.fromstring(msg)
        a = np.asarray(g.values, dtype=np.float32)
        la = g.latlons()[0][:, 0]
        if la[0] < la[-1]:
            a = a[::-1]
        lo0 = float(g.latlons()[1][0, 0])
        if lo0 < 0:
            a = np.roll(a, a.shape[1] // 2, axis=1)
        out[name] = a
    return out


def ec_steps(base):
    """the three steps round base: 3-hourly to 144 h, 6-hourly after"""
    return (base - 3, base, base + 3) if base + 3 <= 144 else (base - 6, base, base + 6)


def tongue(cape, lat, m):
    """northernmost latitude the energy tongue (CAPE >= TONGUE over 30 % of the sea and coast row) reaches, running
    north from 16 N with up to 2 missing rows; and the share of the western interior under it"""
    from scipy.ndimage import binary_dilation
    cor = binary_dilation(m["sea"], iterations=4) & (m["LA"] >= 15) & (m["LA"] <= 30) & (m["LO"] >= 32) & (m["LO"] <= 44.5)
    inland = m["land"] & (m["LA"] >= 16) & (m["LA"] <= 28) & (m["LO"] >= 36) & (m["LO"] <= 44) & \
        ~binary_dilation(m["sea"], iterations=2)
    tip, gap = 15.0, 0
    for j in np.argsort(lat):
        if lat[j] < 16 or lat[j] > 30 or cor[j].sum() < 3:
            continue
        if (cape[j][cor[j]] >= TONGUE).mean() >= 0.3:
            tip, gap = float(lat[j]), 0
        else:
            gap += 1
            if gap > 2:
                break
    return tip, float((cape[inland] >= TONGUE).mean() * 100)


# inland penetration of the sea energy (Fahad, 19 Nov 2026: «تدفق الحمل الحراري cape احيانا يدخل الى داخل الجزيرة
# العربية في مواسم الخصب وهذا ما نريده ويقصده الدكتور»): share of Najd, Al-Qassim and the centre (land 18-30 N,
# 41.5-50 E) under CAPE >= INLAND_CAPE joined to the Red Sea. Test 19 Nov 2026 (ECMWF, 341 days: mid Nov 2024-May 2025,
# Oct-Dec 2025, 1 Oct-18 Nov 2026, vs PERSIANN, interior land 20-29 N 41.5-46 E, wide = 10 % wet): corr 0.43;
# >= 3 %: 39 days, mean wet 24.8 %, 64 % wide (others 4.9 %); >= 2 %: 69 days, 19.7 %, 54 % wide (others 4.1 %).
# Holds in autumn-winter (28.7 vs 4.7 %) and spring (20.4 vs 5.6 %). It catches 25 of 78 wide interior days: the
# rest come by other roads (Gulf moisture, troughs).
INLAND_CAPE = 500
INLAND_LEVELS = (2.0, 3.0)                 # % : «بداية دخول», «توغّل واضح»
# GFS (Fahad, 19 Nov 2026 night, after Dr. Khalid: «معطيات GFS المخصصة لسحب الحمل الحراري "بيئات العواصف الرعدية"
# أفضل من ECMWF»): GFS CAPE 180-0 hPa (max of 09/12/15 UTC, 12Z cycle of the day before), same 341 days and reference.
# Threshold 100 J/kg, levels set to keep EC's day counts: >= 4.5 %: 69 days, mean wet 21.9 %, 61 % wide (EC 19.7 / 54);
# >= 10.5 %: 40 days, 26.6 %, 72 % wide (EC 24.8 / 64); others 3.5 %; corr 0.46 (EC 0.43). 500 J/kg on GFS: corr 0.30.
INLAND_SRC = {"ec": (500, (2.0, 3.0)), "gfs": (100, (4.5, 10.5))}
IN_EXTENT = (32.5, 51.5, 14.0, 32.5)
DR_MAX = 3600
DR_COLS = [(0, "#00000000"), (140 / DR_MAX, "#00000000"), (150 / DR_MAX, "#2e9e3a"), (300 / DR_MAX, "#6cc04a"),
           (450 / DR_MAX, "#c8e04a"), (600 / DR_MAX, "#f3e33b"), (750 / DR_MAX, "#f7b22c"), (900 / DR_MAX, "#f07a22"),
           (1050 / DR_MAX, "#e2421b"), (1350 / DR_MAX, "#c0141a"), (1650 / DR_MAX, "#8a0d16"), (1950 / DR_MAX, "#4a0a10"),
           (2250 / DR_MAX, "#1c1416"), (2700 / DR_MAX, "#3b3b3d"), (3150 / DR_MAX, "#7d7d80"), (1, "#c8c8cc")]
IN_PLACES = [("جدة", 21.54, 39.17), ("مكة", 21.42, 39.83), ("الطائف", 21.27, 40.42), ("المدينة", 24.47, 39.61),
             ("تبوك", 28.38, 36.57), ("حائل", 27.52, 41.69), ("بريدة", 26.33, 43.97), ("الرياض", 24.71, 46.68),
             ("أبها", 18.22, 42.5), ("جازان", 16.89, 42.55), ("نجران", 17.49, 44.13), ("الدوادمي", 24.5, 44.39),
             ("بيشة", 19.99, 42.6), ("الدمام", 26.42, 50.09)]


def inland(cape, m, thr=None):
    """(share % of the interior under sea-joined CAPE, mask of that sea-joined land)"""
    from scipy.ndimage import label
    LA, LO = m["LA"], m["LO"]
    hi = (cape >= (INLAND_CAPE if thr is None else thr)) & m["land"]
    lab, _ = label(hi | (m["sea"] & (LA < 28)))
    seal = set(np.unique(lab[m["sea"] & (LA >= 16) & (LA <= 24)])) - {0}
    conn = np.isin(lab, list(seal)) & m["land"]
    interior = m["land"] & (LA >= 18) & (LA <= 30) & (LO >= 41.5) & (LO <= 50)
    return float(conn[interior].mean() * 100), conn


def draw_inland(path, lat, lon, u, v, cape, m, hgt, conn, width_px=1300, thr=INLAND_CAPE, card=None):
    """Dr. Khalid's colours (green, yellow, red, maroon, black, grey) over light terrain; dashed line round the
    sea-joined energy"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.colors import LightSource, LinearSegmentedColormap, to_rgba
    from scipy.ndimage import zoom, gaussian_filter
    fam = _font()
    W, E, S, N = IN_EXTENT
    j = (lat >= S - .5) & (lat <= N + .5)
    i = (lon >= W - .5) & (lon <= E + .5)
    la, lo = lat[j], lon[i]
    sb = lambda a: a[np.ix_(j, i)]
    asp = (N - S) / ((E - W) * math.cos(math.radians((S + N) / 2)))
    fig = plt.figure(figsize=(width_px / 200, width_px / 200 * asp), dpi=200)
    fig.patch.set_facecolor("#a3bad1")
    ax = fig.add_axes([0, 0, 1, 1])
    up = 6
    ext = [lo[0], lo[-1], la[-1], la[0]]
    h = gaussian_filter(zoom(np.clip(sb(hgt), 0, None), up, order=3), 2)
    shade = LightSource(azdeg=315, altdeg=40).hillshade(h, vert_exag=0.02, dx=1, dy=1)
    lf = gaussian_filter(zoom(sb(m["land"]).astype(float), up, order=1), 3)
    terr = LinearSegmentedColormap.from_list("t", [(0, "#9fb38a"), (.15, "#c9c08f"), (.35, "#c7a77a"), (.6, "#a98d6c"),
                                                   (1, "#8a7a6a")])
    rgb = terr(np.clip(h / 2500, 0, 1))[..., :3] * (0.75 + 0.35 * shade[..., None])
    ax.imshow(np.where((lf > 0.5)[..., None], np.clip(rgb, 0, 1), np.array([0.64, 0.73, 0.82])), extent=ext,
              interpolation="bilinear", zorder=0)
    cm = LinearSegmentedColormap.from_list("dr", [(p, to_rgba(c)) for p, c in DR_COLS], N=512)
    ax.imshow(np.clip(gaussian_filter(zoom(sb(cape), up, order=1), 3), 0, None), extent=ext, cmap=cm, vmin=0,
              vmax=DR_MAX, alpha=.92, interpolation="bilinear", zorder=1)
    flo, fla = np.linspace(lo[0], lo[-1], h.shape[1]), np.linspace(la[0], la[-1], h.shape[0])
    ax.contour(flo, fla, lf, levels=[.5], colors=["#4d5560"], linewidths=[.6], zorder=2)
    cf = gaussian_filter(zoom(sb(conn).astype(float), up, order=1), 2)
    if cf.max() > .5:
        ax.contour(flo, fla, cf, levels=[.5], colors=["#1d2a3a"], linewidths=[1.3], linestyles=[(0, (4, 3))], zorder=3)
    st = 4
    LOg, LAg = np.meshgrid(lo[::st], la[::st])
    ax.quiver(LOg, LAg, sb(u)[::st, ::st], sb(v)[::st, ::st], color="#26303b", alpha=.6, scale=230, width=0.0028,
              headwidth=3.4, zorder=4)
    halo = [pe.withStroke(linewidth=2.2, foreground="#f2efe6")]
    for nm, y, x in IN_PLACES:
        ax.plot(x, y, "o", ms=2.6, color="#ffffff", mec="#1b1f24", mew=.6, zorder=6)
        ax.text(x + .15, y, nm, ha="left", va="center", fontsize=7, color="#1b1f24", family=fam, path_effects=halo, zorder=6)
    lx, ly = [W + .5, W + 5.5], S + .6
    ax.imshow(np.linspace(0, 1, 200)[None, :], extent=[lx[0], lx[1], ly, ly + .3], cmap=cm, vmin=0, vmax=1, zorder=7,
              aspect="auto")
    for t in (150, 600, 1050, 1650, 2250, 3000, 3600):
        ax.text(lx[0] + (lx[1] - lx[0]) * t / DR_MAX, ly - .1, str(t).translate(AR), ha="center", va="top", fontsize=7,
                color="#1b1f24", family=fam, zorder=7, path_effects=halo)
    ax.text(lx[1] + .2, ly + .15, "طاقة الحمل (جول/كجم)", ha="left", va="center", fontsize=6.6, color="#1b1f24",
            family=fam, zorder=7, path_effects=halo)
    ax.text(W + .5, S + 1.5, "الخط المتقطع: الطاقة (" + str(thr).translate(AR) + " فأكثر) المتصلة بالبحر الأحمر  •  الأسهم: الرياح القريبة من السطح",
            ha="left", va="center", fontsize=6.4, color="#1b1f24", family=fam, zorder=7, path_effects=halo)
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(1 / math.cos(math.radians((S + N) / 2)))
    ax.axis("off")
    if card:   # the card style title box (Fahad, 19 Nov 2026)
        import figures as F
        F.card_frame(fig, *card)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=220, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


def _cut(f):
    la = np.linspace(90, -90, f["u10"].shape[0])
    lo = np.linspace(0, 360, f["u10"].shape[1], endpoint=False)
    s, n, w, e = CUT
    j = (la >= s - 1e-6) & (la <= n + 1e-6)
    i = (lo >= w - 1e-6) & (lo <= e + 1e-6)
    return {k: a[np.ix_(j, i)] for k, a in f.items()}, la[j], lo[i]


def masks(lat, lon, land):
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    land = land > 0.5
    sea = (~land) & (LA > 13) & (LA < 28.2) & (LO > 32) & (LO < 43.6) & ~((LA < 14.5) & (LO > 43))
    return dict(LA=LA, LO=LO, land=land, sea=sea, SEA=sea & (LA >= 16) & (LA <= 23),
                NSEA=sea & (LA >= 19) & (LA <= 24), INL=land & (LA >= 18.5) & (LA <= 23.5) & (LO >= 38.5) & (LO <= 42),
                WB=(LA >= 20) & (LA <= 26) & (LO >= 36) & (LO <= 42))


def meeting_line(al, lat, sea):
    rows = []
    for j in range(len(lat)):
        if 14 <= lat[j] <= 27 and sea[j].sum() >= 2:
            rows.append((lat[j], al[j][sea[j]].mean()))
    rows.sort()
    L = np.array([r[0] for r in rows])
    A = np.convolve(np.array([r[1] for r in rows]), np.ones(5) / 5, mode="same")
    for k in range(len(L) - 1):
        if L[k] >= 15 and A[k] > 0 and A[k + 1] <= 0:
            return float((L[k] + L[k + 1]) / 2)
    return 27.0 if A[L >= 15][0] > 0 else 15.0


def coast_of(z):
    return min(COAST, key=lambda c: abs(c[0] - z))[1]


# thresholds per source (19 Nov 2026 test): ECMWF's MUCAPE over the sea is far higher than GFS's (median p75 ~4400
# vs ~2000 J/kg), so its sea-energy point needs 4000 and the verdict 2 points; both give 24 supportive days of 49,
# mean wet share 13.5 % (10 of 11 wide days) vs 3.0 % on the others.
SRC = {"ec": {"scape": 4000, "need": 2, "cmax": 5000}, "gfs": {"scape": 2500, "need": 1, "cmax": 3500}}


def measure(fs, lat, lon, static, src="ec"):
    m = masks(lat, lon, static["land"])
    mean = lambda k: np.mean([f[k] for f in fs], axis=0)
    u = (mean("u925") + mean("u10")) / 2
    v = (mean("v925") + mean("v10")) / 2
    al = -0.5 * u + 0.866 * v
    cape = np.max([f["cape"] for f in fs], axis=0)
    pw = mean("pw")
    z = meeting_line(al, lat, m["sea"])
    r = dict(z=round(z, 2), at=coast_of(z), al_n=round(float(al[m["NSEA"]].mean()), 1),
             scape=int(np.percentile(cape[m["SEA"]], 75)), spw=round(float(pw[m["SEA"]].mean()), 1),
             ipw=round(float(pw[m["INL"]].mean()), 1), v500=round(float(mean("v500")[m["WB"]].mean()), 1))
    th = SRC[src]
    sc = (1 if (z >= 21 or r["al_n"] >= 0) else 0) + (1 if r["scape"] >= th["scape"] else 0) \
        + (1 if r["v500"] >= 2 else 0) - (1 if r["al_n"] <= -4 else 0)
    r["score"], r["src"] = sc, src
    ok = sc >= th["need"]
    r["north"] = "confined" if (ok and r["ipw"] < 20) else ("yes" if ok else ("blocked" if r["al_n"] <= -4 else "no"))
    r["tip"], r["inland"] = tongue(cape, lat, m)
    r["tip_at"] = coast_of(r["tip"])
    r["south"] = bool(r["spw"] >= 35)
    return r, u, v, cape, m


def verdict(r):
    """two Arabic sentences for the page"""
    n = {"yes": "تدفق داعم: هواء البحر الدافئ الرطب يُدفع نحو سواحل جدة ورابغ والليث وسهل مكة",
         "confined": "الجنوبية تصعد مع البحر لكن اليابسة جافة، فالتدفق محصور فوق البحر ولا يصل للساحل",
         "blocked": "شمالية قوية فوق البحر تكبت التدفق عن سواحل جدة ورابغ",
         "no": "لا تدفق داعم نحو سواحل جدة ورابغ والليث"}[r["north"]]
    line = ("الجنوبية تعم البحر كله" if r["z"] >= 27 else "الشمالية تعم البحر حتى جنوبه" if r["z"] <= 15
            else f"تلتقي الجنوبية بالشمالية فوق البحر عند محاذاة {r['at']}")
    s = ("رطوبة جنوب البحر عالية فتتغذى سواحل القنفذة وجازان" if r["south"]
         else "رطوبة جنوب البحر دون الداعم لسواحل القنفذة وجازان")
    t = ("لسان الطاقة (١٠٠٠ جول/كجم فأكثر) يمتد مع البحر حتى محاذاة " + r["tip_at"]) if r.get("tip", 15) >= 17 \
        else "لسان الطاقة لا يصعد مع البحر"
    return n, line, s, t


def _font():
    try:
        import figures as F
        return F._ar_font()
    except Exception:  # noqa: BLE001
        return "sans-serif"


def draw(path, lat, lon, u, v, cape, m, hgt, z, width_px=1100, cmax=CAPE_MAX, card=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.colors import LightSource, LinearSegmentedColormap, to_rgba
    from scipy.ndimage import zoom, gaussian_filter
    fam = _font()
    W, E, S, N = EXTENT
    j = (lat >= S - .5) & (lat <= N + .5)
    i = (lon >= W - .5) & (lon <= E + .5)
    la, lo = lat[j], lon[i]
    sb = lambda a: a[np.ix_(j, i)]
    asp = (N - S) / ((E - W) * math.cos(math.radians((S + N) / 2)))
    fig = plt.figure(figsize=(width_px / 200, width_px / 200 * asp), dpi=200)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    up = 8
    ext = [lo[0], lo[-1], la[-1], la[0]]
    h = gaussian_filter(zoom(np.clip(sb(hgt), 0, None), up, order=3), 2)
    shade = LightSource(azdeg=315, altdeg=40).hillshade(h, vert_exag=0.02, dx=1, dy=1)
    lf = gaussian_filter(zoom(sb(m["land"]).astype(float), up, order=1), 3)
    ax.imshow(np.where(lf > 0.5, 0.18 + 0.32 * shade, 0.07), extent=ext, cmap="gray", vmin=0, vmax=1,
              interpolation="bilinear", zorder=0)
    cm = LinearSegmentedColormap.from_list("cape", [(p, to_rgba(c)) for p, c in CAPE_COLS], N=256)
    cp = np.clip(gaussian_filter(zoom(sb(cape), up, order=1), 3), 0, None)
    ax.imshow(cp, extent=ext, cmap=cm, vmin=0, vmax=cmax, alpha=.8, interpolation="bilinear", zorder=1)
    flo, fla = np.linspace(lo[0], lo[-1], h.shape[1]), np.linspace(la[0], la[-1], h.shape[0])
    ax.contour(flo, fla, lf, levels=[0.5], colors=["#7d8a99"], linewidths=[.6], zorder=2)
    ax.contour(flo, fla, h, levels=[1500], colors=["#aab3bd"], linewidths=[.4], zorder=2)
    st = 3
    uu, vv = sb(u)[::st, ::st], sb(v)[::st, ::st]
    LO, LA = np.meshgrid(lo[::st], la[::st])
    al = -0.5 * uu + 0.866 * vv
    near = gaussian_filter(sb(m["sea"]).astype(float), 3)[::st, ::st] > 0.05
    col = np.where(al > 1, "#ffc65c", np.where(al < -1, "#8ccfff", "#e8edf2"))
    col = np.where(near, col, "#9aa4ae")
    ax.quiver(LO, LA, uu, vv, color=col.ravel(), scale=200, width=0.0040, headwidth=3.4, headlength=3.8, zorder=4,
              edgecolor=BG, linewidth=0.3)
    halo = [pe.withStroke(linewidth=2.4, foreground=BG)]
    jj = int(np.argmin(abs(lat - z)))
    xs = lon[m["sea"][jj]]
    if len(xs) and 15 < z < 27:
        x0, x1 = xs.min() - .2, xs.max() + .2
        ax.plot([x0, x1], [z, z], color="#fff6d8", lw=1.6, ls=(0, (4, 3)), zorder=5,
                path_effects=[pe.withStroke(linewidth=3, foreground="#3a1606")])
        ax.text((x0 + x1) / 2, z + .12, "التقاء الجنوبية بالشمالية", ha="center", va="bottom", fontsize=7.5,
                color="#fff6d8", family=fam, path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)], zorder=6)
    for nm, y, x in PLACES:
        ax.plot(x, y, "o", ms=2.6, color="#ffffff", mec=BG, mew=.6, zorder=6)
        ax.text(x + .12, y, nm, ha="left", va="center", fontsize=7, color="#cfd6de", family=fam, path_effects=halo,
                zorder=6)
    lx, ly = [W + .4, W + 4.4], S + .55
    ax.imshow(np.linspace(0, 1, 200)[None, :], extent=[lx[0], lx[1], ly, ly + .28], cmap=cm, vmin=0, vmax=1,
              zorder=7, aspect="auto")
    for t in range(0, cmax + 1, 1000):
        ax.text(lx[0] + (lx[1] - lx[0]) * t / cmax, ly - .08, str(t).translate(AR), ha="center", va="top",
                fontsize=7, color="#dfe5ea", family=fam, zorder=7, path_effects=halo)
    ax.text(lx[1] + .15, ly + .14, "طاقة عدم الاستقرار (جول/كجم)", ha="left", va="center", fontsize=6.5,
            color="#b9c3cd", family=fam, zorder=7, path_effects=halo)
    ax.text(W + .4, S + 1.3, "الأسهم: الرياح القريبة من السطح  •  ذهبي = جنوبية صاعدة مع البحر  •  أزرق = شمالية",
            ha="left", va="center", fontsize=6.3, color="#b9c3cd", family=fam, zorder=7, path_effects=halo)
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(1 / math.cos(math.radians((S + N) / 2)))
    ax.axis("off")
    if card:   # the card style title box (Fahad, 19 Nov 2026)
        import figures as F
        F.card_frame(fig, *card)
    fig.savefig(path, dpi=200, facecolor=BG)
    plt.close(fig)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.quantize(colors=200, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


def run(gfs_fields, cycle, out_fig, log=print):
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    today = (t0 + timedelta(days=1)).date() if t0.hour >= 12 else t0.date()
    static, lat, lon = None, None, None
    rows, days = [], []
    for k in range(NEXT + 1):
        d = today + timedelta(days=k)
        base = int((datetime(d.year, d.month, d.day, 12) - t0).total_seconds() // 3600)
        try:
            if static is None:   # terrain and land-sea mask from GFS (same 0.25 grid)
                f = gfs_fields(cycle, 24, res="0p25", fields=WIND1 + STATIC)
                f, lat, lon = _cut(f)
                static = {"hgt": f["hgt"], "land": f["land"]}
            fs, src = [], "ec"
            try:   # GFS since 19 Nov 2026 night (Fahad, after Dr. Khalid); ECMWF only if GFS fails
                fs, src = [_cut(gfs_fields(cycle, fh, res="0p25", fields=FIELDS))[0] for fh in (base - 3, base, base + 3)], "gfs"
            except Exception as e:  # noqa: BLE001
                log("red sea flow: GFS unavailable, ECMWF instead", d, repr(e)[:120], flush=True)
                fs, src = [], "ec"
            try:
                if src == "gfs":
                    raise StopIteration
                for fh in ec_steps(base):
                    try:
                        fs.append(_cut(ec_fields(cycle, fh))[0])
                    except Exception:  # noqa: BLE001  (the open-data bucket answers 503 at times: one more go)
                        import time
                        time.sleep(45)
                        fs.append(_cut(ec_fields(cycle, fh))[0])
            except StopIteration:
                pass
            r, u, v, cape, m = measure(fs, lat, lon, static, src)
            r["d"] = d.isoformat()
            r["text"] = list(verdict(r))
            import figures as F
            mdl = "الأمريكي" if src == "gfs" else "الأوروبي"
            when = F.when_ar(d, 12).replace("الساعة ١٢ ظهرًا", "من ١٢ ظهرًا إلى ٦ مساءً")
            draw(os.path.join(out_fig, f"rsf_{k:02d}.png"), lat, lon, u, v, cape, m, static["hgt"], r["z"],
                 cmax=SRC[src]["cmax"], card=(f"تدفق البحر الأحمر — النموذج {mdl}", when, r["text"][:1]))
            try:   # the inland penetration map, thresholds per model (INLAND_SRC)
                if True:
                    thr, lv = INLAND_SRC[src]
                    r["inland_share"], conn = inland(cape, m, thr)
                    r["inland"] = "clear" if r["inland_share"] >= lv[1] else ("start" if r["inland_share"] >= lv[0] else "none")
                    say = {"none": "الطاقة محصورة على البحر والساحل", "start": "بداية دخول لطاقة البحر نحو الداخل",
                           "clear": "توغّل واضح لطاقة البحر داخل الجزيرة"}[r["inland"]]
                    draw_inland(os.path.join(out_fig, f"rsc_{k:02d}.png"), lat, lon, u, v, cape, m, static["hgt"], conn,
                                thr=thr, card=(f"توغّل طاقة الحمل من البحر الأحمر — النموذج {mdl}", when,
                                               [f"{say}: {F.ar_num(r['inland_share'], 1)}٪ من نجد والقصيم والوسطى"]))
            except Exception as e:  # noqa: BLE001
                log("inland energy map failed", d, repr(e)[:160], flush=True)
            log("red sea flow", d, r["north"], r["z"], r["at"], r["score"], flush=True)
        except Exception as e:  # noqa: BLE001
            log("red sea flow failed", d, repr(e)[:160], flush=True)
            r = {"d": d.isoformat()}
        rows.append(r)
        days.append(d.isoformat())
    return {"days": days, "rows": rows, "extent": list(EXTENT), "in_extent": list(IN_EXTENT)}
