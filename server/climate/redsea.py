"""Red Sea flow toward the coasts, for the «الرياح» tab of the oscillation page (Fahad, 19 Nov 2026: «جميلة خريطة
التدفق هذه للبحر ونضيفها لقسم الرياح خاصة لتوقع السواحل.. لكنها تختلف عن الحمل الحراري وتدفقه»).

A coastal product, not a convective-jet index: it shows where the warm moist sea air is pushed along the Red Sea and
onto the coasts. Mean of 09, 12 and 15 UTC (12-6 PM Makkah), wind = mean of 925 hPa and 10 m, GFS 0.25 only.
  - along-sea component = -0.5 u + 0.866 v (the sea's axis runs about 330 deg); the meeting line is where the
    southerly flow coming up from the south meets the northerly (first + to - change going north from 15 N, 1 deg
    smoothing). The sea air feeds the coast south of that line.
  - north coast (Jeddah, Rabigh, Al-Lith, Makkah plain), score: +1 the southerly reaches 21 N (line >= 21 or along
    mean 19-24 N >= 0), +1 sea CAPE (180-0 hPa, p75, 16-23 N) >= 2500, +1 south-westerly aloft (v500 20-26 N,
    36-42 E) >= 2 m/s, -1 northerly <= -4 m/s over 19-24 N; land PW (18.5-23.5 N, 38.5-42 E) < 20 mm: confined over
    the sea. Score >= 1 supportive.
  - south coast (Al-Qunfudhah to Jazan): sea PW (16-23 N) >= 35 mm feeds it; named when the meeting line is on it.
Test 1 Oct-18 Nov 2026 vs PERSIANN-PDIR-Now (Jeddah/Makkah/Taif/Rabigh/Al-Lith land 20-23.5 N): supportive 24 days
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


def measure(fs, lat, lon, static):
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
    sc = (1 if (z >= 21 or r["al_n"] >= 0) else 0) + (1 if r["scape"] >= 2500 else 0) + (1 if r["v500"] >= 2 else 0) \
        - (1 if r["al_n"] <= -4 else 0)
    r["score"] = sc
    r["north"] = "confined" if (sc >= 1 and r["ipw"] < 20) else ("yes" if sc >= 1 else ("blocked" if r["al_n"] <= -4 else "no"))
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
    return n, line, s


def _font():
    try:
        import figures as F
        return F._ar_font()
    except Exception:  # noqa: BLE001
        return "sans-serif"


def draw(path, lat, lon, u, v, cape, m, hgt, z, width_px=1100):
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
    ax.imshow(cp, extent=ext, cmap=cm, vmin=0, vmax=CAPE_MAX, alpha=.8, interpolation="bilinear", zorder=1)
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
    for t in (0, 1000, 2000, 3000):
        ax.text(lx[0] + (lx[1] - lx[0]) * t / CAPE_MAX, ly - .08, str(t).translate(AR), ha="center", va="top",
                fontsize=7, color="#dfe5ea", family=fam, zorder=7, path_effects=halo)
    ax.text(lx[1] + .15, ly + .14, "طاقة عدم الاستقرار (جول/كجم)", ha="left", va="center", fontsize=6.5,
            color="#b9c3cd", family=fam, zorder=7, path_effects=halo)
    ax.text(W + .4, S + 1.3, "الأسهم: الرياح القريبة من السطح  •  ذهبي = جنوبية صاعدة مع البحر  •  أزرق = شمالية",
            ha="left", va="center", fontsize=6.3, color="#b9c3cd", family=fam, zorder=7, path_effects=halo)
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(1 / math.cos(math.radians((S + N) / 2)))
    ax.axis("off")
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
            fs = []
            for fh in (base - 3, base, base + 3):
                f = gfs_fields(cycle, fh, res="0p25", fields=FIELDS + ([] if static else STATIC))
                f, lat, lon = _cut(f)
                if static is None:
                    static = {"hgt": f.pop("hgt"), "land": f.pop("land")}
                fs.append(f)
            r, u, v, cape, m = measure(fs, lat, lon, static)
            r["d"] = d.isoformat()
            r["text"] = list(verdict(r))
            draw(os.path.join(out_fig, f"rsf_{k:02d}.png"), lat, lon, u, v, cape, m, static["hgt"], r["z"])
            log("red sea flow", d, r["north"], r["z"], r["at"], r["score"], flush=True)
        except Exception as e:  # noqa: BLE001
            log("red sea flow failed", d, repr(e)[:160], flush=True)
            r = {"d": d.isoformat()}
        rows.append(r)
        days.append(d.isoformat())
    return {"days": days, "rows": rows, "extent": list(EXTENT)}
