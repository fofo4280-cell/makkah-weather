"""Cumulative rain maps of the nearest wave from the models' own accumulated rain (Fahad 28 Nov 2026, the short
nightly report: «استخدم بيانات الهطول التراكمي الفعلية من النموذج أو النماذج المتاحة، مع الاستفادة من المقارنة بين
النماذج لتحديد مناطق الاتفاق والاختلاف … لا تستنتج كميات بالملليمتر من مؤشرات الرطوبة أو طاقة الحمل»).

    make(st, out_dir, a, b) -> {"ok", "maps": [{"img", "a", "b", "kind", "caption"}], "models": [...], ...} or None

Sources: GFS 0.25 APCP «0-N hour acc» and ECMWF IFS open data «tp» (metres, accumulated from the start) of tonight's
12 UTC cycle, at the Makkah day boundaries (21 UTC). The two models are never averaged: each has its own panel, and
the last map adds a panel of where they agree (both 5 mm or more) and where only one of them has rain. Our 3 km WRF
run reaches 33 hours only, so it does not cover the days of a wave that starts tomorrow; it is named, not drawn.
Maps (fig/qpf_1.png ..): 1 the first day, 2 to the end of the second, 3 to the end of the third or of the wave,
4 the whole wave with the agreement panel. Same colour key on all.
If neither model gives a valid field, no amount is drawn (the report then shows the qualitative map of the impact
zones from the ingredients, labelled as such).
"""
import os
from datetime import date, datetime, timedelta

import numpy as np

LEVELS = [1, 2, 5, 10, 20, 30, 50, 75, 100]
COLS = ["#bfe3f2", "#7cc3e6", "#3c93d1", "#2459b8", "#2fa35a", "#e9cf3a", "#f09430", "#df4a2e", "#b3197a", "#6c1592"]
W, E, S, N = 34.0, 56.5, 15.5, 32.6
BOX = (13.0, 34.0, 32.0, 59.0)               # the fields are cut to this (lat s, n, lon w, e)
AGREE = 5.0                                  # mm: "rain" for the agreement panel
# towns drawn beside the main cities (figures.SAUDI_CITIES) and read for the agreement sentence
TOWNS = [("أملج", 25.02, 37.27), ("الوجه", 26.24, 36.45), ("رابغ", 22.80, 39.03), ("العلا", 26.61, 37.92),
         ("خيبر", 25.70, 39.29), ("القنفذة", 19.13, 41.08), ("بيشة", 20.00, 42.60), ("شرورة", 17.47, 47.11),
         ("حفر الباطن", 28.43, 45.97), ("الجبيل", 27.01, 49.66), ("طريف", 31.67, 38.66), ("القريات", 31.33, 37.34),
         ("ضباء", 27.35, 35.69), ("حقل", 29.29, 34.94), ("تيماء", 27.63, 38.55), ("الليث", 20.15, 40.27),
         ("الخرج", 24.15, 47.31), ("رفحاء", 29.63, 43.50), ("عنيزة", 26.08, 43.99), ("الحناكية", 24.86, 40.51),
         ("الدوادمي", 24.51, 44.39), ("محايل", 18.55, 42.05), ("صبيا", 17.15, 42.63)]
MODEL_W = {"ec": "الأوروبي", "gfs": "جي إف إس"}


def _grid():
    la = np.linspace(90, -90, 721)
    lo = np.linspace(0, 359.75, 1440)
    j = (la >= BOX[0]) & (la <= BOX[1])
    i = (lo >= BOX[2]) & (lo <= BOX[3])
    return la[j], lo[i], j, i


def fh_of(cycle, t):
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    return int((t - t0).total_seconds() // 3600)


def end_utc(d):
    """the end of Makkah day d (midnight Makkah) in UTC"""
    return datetime(d.year, d.month, d.day, 21)


def acc_gfs(cycle, fh):
    import daily
    if fh <= 0:
        return 0.0
    dd = f"{fh // 24} day" if fh % 24 == 0 else f"{fh} hour"
    f = daily.gfs_fields(cycle, fh, res="0p25", fields=[("apcp", rf":APCP:surface:0-{dd} acc fcst:")])
    la, lo, j, i = _grid()
    return np.asarray(f["apcp"], float)[np.ix_(j, i)]


def acc_ec(cycle, fh):
    import ecmwf
    if fh <= 0:
        return 0.0
    a = ecmwf._at(cycle, fh, "tp", "") * 1000.0
    la, lo, j, i = _grid()
    return np.asarray(a, float)[np.ix_(j, i)]


def fetch(cycle, hours):
    """{model: {fh: accumulated field}} for the hours asked; a model that fails any hour is left out"""
    out = {}
    for key, fn in (("ec", acc_ec), ("gfs", acc_gfs)):
        got = {}
        try:
            for h in hours:
                got[h] = fn(cycle, h)
            out[key] = got
        except Exception as e:  # noqa: BLE001
            print(f"qpf: {key} accumulated rain not read:", repr(e)[:160], flush=True)
    return out


def periods(a, b):
    """[(first day, last day, kind)]: day 1, to the end of day 2, to the end of day 3 or of the wave, the whole wave"""
    n = (b - a).days + 1
    out = [(a, a, "d1")]
    if n >= 2:
        out.append((a, a + timedelta(days=1), "d2"))
    if n >= 3:
        out.append((a, a + timedelta(days=2), "d3"))
    out.append((a, b, "tot"))
    return out


def _sea_mask(la, lo):
    from shapely import contains_xy
    from shapely.ops import unary_union
    import sa_geo
    ksa = unary_union([r["geom"] for r in sa_geo.regions()])
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    return contains_xy(ksa, LO.ravel(), LA.ravel()).reshape(LA.shape), ksa


def at_place(g, la, lo, lat, lon, r=0.25):
    m = np.ix_(np.abs(la - lat) <= r + 1e-6, np.abs(lo - lon) <= r + 1e-6)
    v = g[m]
    return float(v.max()) if v.size else 0.0


def places_over(g, la, lo, thr):
    import figures as F
    pl = [(n, a, b) for n, a, b, *_ in F.SAUDI_CITIES] + TOWNS
    return [n for n, a, b in pl if at_place(g, la, lo, a, b) >= thr]


def region_share(g, la, lo, regs_mask, thr):
    """{region name: share of its land with thr mm or more}"""
    return {nm: float((g[m] >= thr).mean()) for nm, m in regs_mask.items() if m.any()}


def _regions_mask(la, lo):
    from shapely import contains_xy
    import sa_geo
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    out = {}
    for r in sa_geo.regions():
        out[r["name"]] = contains_xy(r["geom"], LO.ravel(), LA.ravel()).reshape(LA.shape)
    return out


def centres(g, la, lo, n=3, thr=10.0, sep=1.5):
    """[(lat, lon, mm)] of the n strongest separate maxima of 'thr' mm or more"""
    from scipy.ndimage import maximum_filter
    mx = (g == maximum_filter(g, size=5)) & (g >= thr)
    pts = sorted(((g[j, i], la[j], lo[i]) for j, i in zip(*np.nonzero(mx))), reverse=True)
    out = []
    for v, a, b in pts:
        if W + 0.5 <= b <= E - 1.5 and S + 0.3 <= a <= N - 1.0 and all(abs(a - x) + abs(b - y) >= sep for x, y, _ in out):
            out.append((a, b, float(v)))
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------ drawing
def _panel(fig, rect, g, la, lo, head, regs, ksa, fam, A, agree=None):
    from matplotlib import patheffects as pe
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from scipy.ndimage import zoom, gaussian_filter
    import figures as F
    import report2 as R2
    ax = fig.add_axes(rect)
    ax.set_facecolor("#1a2330")
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(1 / np.cos(np.radians(24)))
    ax.axis("off")
    try:
        from PIL import Image
        rw, re_, rs, rn = F.RELIEF["box"]
        rel = np.asarray(Image.open(F.RELIEF["path"]).convert("L"))
        ax.imshow(rel, extent=[rw, re_, rs, rn], origin="upper", cmap="gray", vmin=0, vmax=255, alpha=0.6,
                  interpolation="lanczos", zorder=0)
    except Exception as ex:  # noqa: BLE001
        print("relief unavailable:", str(ex)[:80])
    ext = [lo[0], lo[-1], la[-1], la[0]]
    if agree is None:
        fine = np.clip(gaussian_filter(zoom(g, 4, order=3), 2.2), 0, None)   # one smooth field, sea and land alike
        fine = np.where(fine >= LEVELS[0], fine, np.nan)
        ax.imshow(fine, extent=ext, origin="upper", cmap=ListedColormap(COLS),
                  norm=BoundaryNorm(LEVELS + [1000], len(COLS)), alpha=0.88, interpolation="bilinear", zorder=1)
    else:
        e, gf = agree
        cat = np.where((e >= AGREE) & (gf >= AGREE), 3, np.where(e >= AGREE, 2, np.where(gf >= AGREE, 1, 0))).astype(float)
        cat = zoom(cat, 3, order=0)
        cat = np.where(cat > 0, cat, np.nan)
        ax.imshow(cat, extent=ext, origin="upper", cmap=ListedColormap(["#f09430", "#3c93d1", "#2fa35a"]),
                  norm=BoundaryNorm([0.5, 1.5, 2.5, 3.5], 3), alpha=0.85, interpolation="nearest", zorder=1)
    for r in regs:
        for g_ in getattr(r["geom"], "geoms", [r["geom"]]):
            x, y = g_.exterior.xy
            ax.plot(x, y, color="#e8edf2", linewidth=0.4, alpha=0.5, zorder=2)
    for g_ in getattr(ksa, "geoms", [ksa]):
        x, y = g_.exterior.xy
        ax.plot(x, y, color="#f4f6f8", linewidth=1.0, alpha=0.9, zorder=2)
    try:
        F.draw_cities(ax, ax.transData, fontsize=5.6, wide=False)
    except Exception as ex:  # noqa: BLE001
        print("cities:", repr(ex)[:80])
    soft = [pe.withStroke(linewidth=1.0, foreground=(1, 1, 1, 0.55))]
    for nm, a, b in TOWNS:
        ax.plot(b, a, marker="o", markersize=1.6, color="#1b1b1b", markeredgecolor="white", markeredgewidth=0.4, zorder=7)
        ax.text(b, a - 0.22, A(nm), ha="center", va="top", fontsize=4.3, color="#1b1b1b", fontfamily=fam,
                path_effects=soft, zorder=7)
    halo = [pe.withStroke(linewidth=2.4, foreground="#111111")]
    if agree is None:   # the strongest centres with their amount
        for a, b, v in centres(g, la, lo):
            ax.plot(b, a, marker="+", markersize=6, color="#ffffff", markeredgewidth=1.2, zorder=8, path_effects=halo)
            ax.text(b + 0.25, a + 0.2, A(f"{R2.ar(int(round(v)))} ملم"), ha="left", va="bottom", fontsize=6.4,
                    fontweight="bold", color="#ffffff", fontfamily=fam, path_effects=halo, zorder=8)
    ax.text(0.5, 0.985, A(head), transform=ax.transAxes, ha="center", va="top", fontsize=10, fontweight="bold",
            color="#ffffff", fontfamily=fam, path_effects=halo, zorder=9)
    return ax


def draw(path, panels, la, lo, title, sub, agree_key=False):
    """panels = [(field or None, head, agree pair or None)], right to left; the title strip above the maps"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Rectangle
    from shapely.ops import unary_union
    import figures as F
    import sa_geo
    fam = F._ar_font()
    A = F._ar
    regs = sa_geo.regions()
    ksa = unary_union([r["geom"] for r in regs])
    n = len(panels)
    pw = 6.0
    ph = pw * (N - S) / (E - W) * 1.1
    head, foot = 0.95, 0.8
    fig = plt.figure(figsize=(pw * n, ph + head + foot), dpi=150)
    fig.patch.set_facecolor("#111111")
    H = fig.get_figheight()
    for k, (g, hd, ag) in enumerate(panels):
        x0 = (n - 1 - k) / n
        _panel(fig, [x0 + 0.004, foot / H, 1 / n - 0.008, ph / H], g, la, lo, hd, regs, ksa, fam, A, agree=ag)
    tx = fig.add_axes([0, 1 - head / H, 1, head / H])
    tx.axis("off")
    tx.add_patch(Rectangle((0, 0), 1, 1, color="#161b22", transform=tx.transAxes))
    tx.text(0.985, 0.68, A(title), ha="right", va="center", fontsize=14, fontweight="bold", color="#ffffff", fontfamily=fam)
    tx.text(0.985, 0.27, A(sub), ha="right", va="center", fontsize=8.6, color="#b8c0c8", fontfamily=fam)
    # the one colour key, in mm, along the bottom
    kw = 0.42 if n > 2 else 0.5
    kx = fig.add_axes([0.5 - kw / 2, 0.45 * foot / H, kw, 0.22 * foot / H])
    kx.imshow(np.arange(len(COLS))[None, :], cmap=ListedColormap(COLS), aspect="auto", extent=[0, len(COLS), 0, 1])
    kx.set_xticks(np.arange(len(COLS)))
    kx.set_xticklabels([str(v).translate(F.AR_DIG) for v in LEVELS] + [""], fontsize=7, color="#e8edf2", fontfamily=fam)
    kx.set_yticks([])
    kx.tick_params(length=0, pad=1.5)
    for sp_ in kx.spines.values():
        sp_.set_visible(False)
    fig.text(0.5 + kw / 2 + 0.01, 0.56 * foot / H, A("ملم"), ha="left", va="center", fontsize=8, color="#e8edf2",
             fontfamily=fam)
    if agree_key:
        items = [("#2fa35a", "يتفقان على ٥ ملم فأكثر"), ("#3c93d1", "الأوروبي وحده"), ("#f09430", "جي إف إس وحده")]
        for k, (c, t) in enumerate(items):
            x = 1 / n - 0.03 - k * 0.095
            fig.add_artist(Rectangle((x, 0.12 * foot / H), 0.012, 0.14 * foot / H, color=c, transform=fig.transFigure))
            fig.text(x - 0.004, 0.19 * foot / H, A(t), ha="right", va="center", fontsize=6.6, color="#e8edf2", fontfamily=fam)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    try:
        from PIL import Image
        Image.open(path).convert("RGB").quantize(colors=200).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ the maps and their reading
def _span_words(a, b):
    from report2 import ar_date
    return ar_date(a) if a == b else f"{ar_date(a)} إلى {ar_date(b)}"


def compare_words(fields, la, lo, rmask, thr=10.0):
    """one sentence: where both models give thr mm or more, and where only one of them does (regions and towns)"""
    from report2 import jl, ar
    if len(fields) < 2:
        return None
    e, g = fields["ec"], fields["gfs"]
    se, sg = region_share(e, la, lo, rmask, thr), region_share(g, la, lo, rmask, thr)
    both = [k for k in se if se[k] >= 0.05 and sg.get(k, 0) >= 0.05]
    eo = [k for k in se if se[k] >= 0.05 and sg.get(k, 0) < 0.02]
    go = [k for k in sg if sg[k] >= 0.05 and se.get(k, 0) < 0.02]
    pe_, pg = set(places_over(e, la, lo, thr)), set(places_over(g, la, lo, thr))
    tb = [p for p in places_over(e, la, lo, thr) if p in pg]
    parts = []
    if both:
        parts.append(f"يتفق النموذجان على {ar(int(thr))} ملم فأكثر فوق {jl(both[:4])}" + (f" (منها {jl(tb[:4])})" if tb else ""))
    else:
        parts.append(f"لا يتفق النموذجان على {ar(int(thr))} ملم فأكثر فوق أي منطقة")
    if eo:
        parts.append(f"ويضعها الأوروبي وحده فوق {jl(eo[:3])}")
    if go:
        parts.append(f"وجي إف إس وحده فوق {jl(go[:3])}")
    return "، ".join(parts) + "."


def make(st, out_dir, a, b, cycle=None):
    from report2 import ar, ar_date
    cycle = str(cycle or st.get("cycle") or "")
    if len(cycle) != 10:
        return None
    pr = periods(a, b)
    t_start = end_utc(a - timedelta(days=1))
    hours = sorted({fh_of(cycle, t_start)} | {fh_of(cycle, end_utc(y)) for _, y, _ in pr})
    F = fetch(cycle, hours)
    la, lo, _, _ = _grid()
    models = [k for k in ("ec", "gfs") if k in F]
    res = {"cycle": cycle, "a": a.isoformat(), "b": b.isoformat(), "models": models, "ok": bool(models), "maps": []}
    if not models:
        return res
    if len(models) < 2:   # one model: no agreement panel, so the whole wave is not drawn twice
        last = pr[-1]
        pr = [p for p in pr[:-1] if p[1] != last[1]] + [last]
    rmask = _regions_mask(la, lo)
    os.makedirs(os.path.join(out_dir, "fig"), exist_ok=True)
    h0 = fh_of(cycle, t_start)
    run_w = f"تشغيل {ar(int(cycle[8:10]))} غرينتش {ar_date(date(int(cycle[:4]), int(cycle[4:6]), int(cycle[6:8])), weekday=False)}"
    v = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    for k, (x, y, kind) in enumerate(pr):
        h1 = fh_of(cycle, end_utc(y))
        fl = {m: np.clip(np.asarray(F[m][h1], float) - np.asarray(F[m][h0], float), 0, None) for m in models}
        title = {"d1": "التراكم في اليوم الأول", "d2": "التراكم حتى نهاية اليوم الثاني",
                 "d3": "التراكم حتى نهاية اليوم الثالث" if y < b else "التراكم حتى نهاية الموجة",
                 "tot": "إجمالي التراكم خلال الموجة"}[kind]
        when = (f"يوم {ar_date(x)} كاملًا بتوقيت مكة" if x == y else
                f"من بداية {ar_date(x)} إلى نهاية {ar_date(y)} بتوقيت مكة")
        sub = f"{when}، {run_w}، بالملليمتر"
        panels = [(fl[m], MODEL_W[m], None) for m in models]
        if kind == "tot" and len(models) == 2:
            panels.append((None, "الاتفاق والاختلاف", (fl["ec"], fl["gfs"])))
        img = f"qpf_{k + 1}.png"
        draw(os.path.join(out_dir, "fig", img), panels, la, lo, title, sub, agree_key=kind == "tot" and len(models) == 2)
        mx = {m: round(float(fl[m][np.ix_((la >= S) & (la <= N), (lo >= W) & (lo <= E))].max()), 1) for m in models}
        res["maps"].append({"img": img, "v": v, "a": x.isoformat(), "b": y.isoformat(), "kind": kind, "title": title,
                            "when": when, "max": mx, "cmp": compare_words(fl, la, lo, rmask) if kind in ("tot",) else None,
                            "cmp5": compare_words(fl, la, lo, rmask, thr=AGREE) if kind == "tot" else None})
        print("qpf map:", img, title, mx, flush=True)
    return res
