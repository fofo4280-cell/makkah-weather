"""The reference wave (Fahad, 25 Nov 2026: «في تقرير الموجة القادمة قارنها بالموجة السابقة من ناحية القوة والانتشار مثل
موجة ١٠ نوفمبر… هذه الموجة اين أقوى مناطق هطولها وكم قوة الهطول مقارنة بالسابقة وكم نسبة انتشارها للمملكة.. دائما في
كل موجة اجعل لك مرجع لموجة سابقة كان هطولها قوي ونسبة انتشارها جيدة»; then: «المهم ان تحديدك لاماكن الهطول لم يكن مبنى
على تراكمي الأمريكي بل على دراستك لجميع خرائط التذبذب وبناء ذلك بشكل علمي»).

The places, strength and spread come from a reading of the ingredients, never from model rain: on the 1 degree GFS
fields at 12 UTC of each day (ingredients.BOX), a rain-making index 0..1 at each point =
    moisture (precipitable water and 700 hPa humidity together)
  x lift (cold air aloft against the 12 UTC normal of pattern.py, cyclonic 500 hPa vorticity of a trough, spreading
          winds at 200 hPa; strengthened where the winds meet near the ground)
  x instability (925-500 hPa lapse rate).
  - spread: the share of the Kingdom where the index is 0.4 or more;
  - strength: the mean index over the strongest tenth of the Kingdom (its core), out of 100;
  - the strongest areas: the regions that hold most of the index over 0.4, with the part of the region.
Test 10-18 Nov 2026 against satellite rain (PERSIANN-PDIR-Now, 5 mm or more): 10 Nov core 72 (the highest), spread 12 %
(observed 13.5 %), first region Al-Qassim (observed Al-Qassim); 11 Nov core 56, spread 8 % (11.5 %); quiet days 15-17
Nov core under 10. Regions ranked against the observed shares: mean rank correlation 0.48 on the rain days.
The reference is the day with the best spread x strength; it starts from 10 Nov 2026 (ref_wave.json, GFS 00Z +12 h)
and the nightly run replaces it when today's reading beats it. It is carried from night to night in mjo.json.
"""
import numpy as np

WET, HEAVY = 40.0, 70.0      # index x 100: the rain-making threshold (fitted on the test above) and a strong core
PW0, RH0 = 15.0, 50.0


def _t500_normal(d, lat=None, lon=None):
    """the 12 UTC 500 hPa temperature normal (deg C) of pattern.py on ingredients' grid (or on lat x lon)"""
    import pattern
    import ingredients as ING
    from scipy.interpolate import RegularGridInterpolator
    c = pattern._clim()
    n, _ = pattern.normal(d)
    la, lo = np.asarray(c["lat"], float), np.asarray(c["lon"], float)
    if la[0] > la[-1]:
        la, n = la[::-1], n[::-1]
    f = RegularGridInterpolator((la, lo), n, bounds_error=False, fill_value=None)
    LA, LO = np.meshgrid(ING.LAT if lat is None else lat, ING.LON if lon is None else lon, indexing="ij")
    return f((LA, LO))


def index(g, d, lat=None, lon=None, step=1.0):
    """the rain-making index 0..1 on ingredients' grid from the fields g (ingredients.FIELDS, cut) of day d; on another
    grid (lat north to south, lon, spacing step degrees) when given (hijaz.py, 0.25 degree)"""
    import ingredients as ING
    cl = lambda x: np.clip(x, 0, 1)
    ft = ING.features(g, lat=lat, step=step)
    moist = cl((g["pw"] - PW0) / 15) * cl((g["rh700"] - RH0) / 40)
    ta = g["t500"] - 273.15 - _t500_normal(d, lat, lon)
    dyn = 1 - (1 - cl(-ta / 2.5)) * (1 - cl(ft["vort500"] / 3)) * (1 - cl(ft["div200"] / 2.5))
    lift = dyn * (0.5 + 0.5 * cl(ft["conv925"] / 1.5))
    inst = cl((ft["lapse"] - 20) / 10)
    return moist * lift * (0.4 + 0.6 * inst)


def reading(I):
    """the day's reading from the index I -> dict (cover, core, max, regions)"""
    import ingredients as ING
    m = day_metrics(100 * I, wet=WET, heavy=HEAVY)
    k = ING.kingdom_mask() >= 0
    v = np.sort(I[k])[::-1]
    m["core"] = round(float(100 * v[:max(1, len(v) // 10)].mean()), 1)
    m["kind"] = "ingr"
    return m


def _load_ref0():
    import json, os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref_wave.json")
    return json.load(open(p)) if os.path.exists(p) else None


def _part(lat, lon, c_lat, c_lon, span):
    """the part of a region where the rain sits, from the rain's centre against the region's centre"""
    dy, dx = (lat - c_lat) / max(span[0], 0.5), (lon - c_lon) / max(span[1], 0.5)
    if abs(dy) < 0.18 and abs(dx) < 0.18:
        return "وسط"
    if abs(dx) >= 2 * abs(dy):
        return "غرب" if dx < 0 else "شرق"
    if abs(dy) >= 2 * abs(dx):
        return "جنوب" if dy < 0 else "شمال"
    return ("جنوب " if dy < 0 else "شمال ") + ("غرب" if dx < 0 else "شرق")


def day_metrics(rain, wet=WET, heavy=HEAVY):
    """metrics of one daily rain field cut to ingredients.BOX (mm) -> dict"""
    import ingredients as ING
    import sa_geo
    m = ING.kingdom_mask()
    regs = sa_geo.regions()
    la, lo = np.meshgrid(ING.LAT, ING.LON, indexing="ij")
    w = np.cos(np.radians(la))
    ksa = m >= 0
    wet = (rain >= wet) & ksa
    out = {"cover": float(w[wet].sum() / w[ksa].sum()),
           "heavy": float(w[(rain >= heavy) & ksa].sum() / w[ksa].sum()),
           "mean": float((rain * w)[wet].sum() / w[wet].sum()) if wet.any() else 0.0,
           "max": float(np.nanmax(np.where(ksa, rain, 0))), "regions": []}
    for k in sorted(set(m[ksa].tolist())):
        r = m == k
        rw = r & wet
        if not rw.any():
            continue
        cov = float(w[rw].sum() / w[r].sum())
        mean = float((rain * w)[rw].sum() / w[rw].sum())
        # the part of the region: the rain-weighted centre of its wet cells against the centre of the region
        q = rain[rw] * w[rw]
        c_lat, c_lon = float((la[rw] * q).sum() / q.sum()), float((lo[rw] * q).sum() / q.sum())
        span = (float(la[r].max() - la[r].min()) / 2, float(lo[r].max() - lo[r].min()) / 2)
        part = _part(c_lat, c_lon, float(la[r].mean()), float(lo[r].mean()), span) if r.sum() >= 4 and cov < 0.7 else ""
        # where to circle it: the centre and the rain-weighted spread of the wet cells (degrees)
        sd = float(np.sqrt((q * ((la[rw] - c_lat) ** 2 + ((lo[rw] - c_lon) * np.cos(np.radians(c_lat))) ** 2)).sum() / q.sum()))
        out["regions"].append({"name": regs[k]["name"], "cover": round(cov, 3), "mean": round(mean, 1),
                               "lat": round(c_lat, 2), "lon": round(c_lon, 2), "rad": round(min(max(0.8, 1.6 * sd), 2.6), 2),
                               "max": round(float(rain[rw].max()), 1), "part": part,
                               # the region's rain weight: how much of the Kingdom's wet rain falls in it
                               "w": round(float(q.sum()), 1)})
    out["regions"].sort(key=lambda x: -x["w"])
    for k in ("cover", "heavy"):
        out[k] = round(out[k], 3)
    out["mean"], out["max"] = round(out["mean"], 1), round(out["max"], 1)
    return out


def score(m):
    """spread x strength, the reference's yardstick"""
    return (m.get("cover") or 0) * (m.get("core") or 0)


def strongest_regs(m, n=3):
    """the region entries of the strongest rain areas, strongest first"""
    return [r for r in m.get("regions") or [] if r["cover"] >= 0.1 or r["mean"] >= 55][:n] or (m.get("regions") or [])[:1]


def strongest(m, n=3):
    """the strongest rain areas, as words («غرب القصيم»), strongest first"""
    if m.get("areas"):   # observed areas, written by hand for the seed
        return list(m["areas"])
    out = []
    for r in strongest_regs(m, n):
        nm = r["name"]
        out.append((r["part"] + " " + nm) if r.get("part") and r["part"] != "وسط" else nm)
    return out


def current(prev):
    """the reference carried from the previous night, else the seed of 10 Nov 2026"""
    if prev and prev.get("d") and prev.get("kind") == "ingr":
        return prev
    return _load_ref0()


def update(prev, d, m):
    """the reference after today's rain m (lead 0-24 h) of day d: today replaces it when it beats it on spread x
    intensity -> (reference, replaced?)"""
    ref = current(prev)
    if m and (ref is None or score(m) > score(ref)) and m["cover"] >= 0.05:
        new = {k: v for k, v in m.items() if k != "areas"}
        new["d"] = d
        return new, True
    return ref, False


def wave_metrics(rows, a, b):
    """the wave a..b from the nightly day rows [{d, ...day_metrics}] -> the widest day's metrics with the wave's
    strongest areas over all its days, or None"""
    ds = [r for r in rows if a.isoformat() <= r["d"] <= b.isoformat()]
    if not ds:
        return None
    pk = max(ds, key=lambda r: (r["cover"], score(r)))   # the strongest day is the widest one (Fahad)
    out = dict(pk)
    # the strongest areas over the whole wave: each region's best day
    best = {}
    for r in ds:
        for g in r.get("regions") or []:
            if g["name"] not in best or g["w"] > best[g["name"]]["w"]:
                best[g["name"]] = g
    out["regions"] = sorted(best.values(), key=lambda g: -g["w"])
    return out


GRIDS = {}   # the nightly rain-making index x 100 (cut to ingredients.BOX), by date, for the map


def label(r):
    return (r["part"] + " " + r["name"]) if r.get("part") and r["part"] != "وسط" else r["name"]


def draw(path, rain, m, ref, title, sub, ref_day=""):
    """the Kingdom with the wave's rain-making index (its strongest over the wave days, x 100) and circles on its strongest areas (solid), and the
    reference wave's areas (dashed); the title strip above the map, never over it (Fahad, 20 Nov 2026)"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
    from matplotlib.patches import Circle, Rectangle
    from scipy.ndimage import zoom
    from shapely.ops import unary_union
    import figures as F
    import ingredients as ING
    import sa_geo
    fam = F._ar_font()
    A = F._ar
    W, E, S, N = 34.0, 56.5, 15.5, 32.6
    regs = sa_geo.regions()
    fig = plt.figure(figsize=(7.2, 7.2 * ((N - S) / (E - W)) * 1.04 + 1.15), dpi=170)
    fig.patch.set_facecolor("#111111")
    H = fig.get_figheight()
    top = 1.0 / H   # inches of the title strip as a share
    ax = fig.add_axes([0.0, 0.0, 1.0, 1 - top * 1.08])
    ax.set_facecolor("#1a2330")
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(1 / np.cos(np.radians(24)))
    ax.axis("off")
    try:   # the relief under everything, as the other maps
        from PIL import Image
        rw, re_, rs, rn = F.RELIEF["box"]
        rel = np.asarray(Image.open(F.RELIEF["path"]).convert("L"))
        ax.imshow(rel, extent=[rw, re_, rs, rn], origin="upper", cmap="gray", vmin=0, vmax=255, alpha=0.55,
                  interpolation="lanczos", zorder=0)
    except Exception as ex:  # noqa: BLE001
        print("relief unavailable:", str(ex)[:80])
    ksa = unary_union([r["geom"] for r in regs])
    # the rain, finer, inside the Kingdom only
    if rain is not None and np.nanmax(rain) > 0:
        up = 6
        from scipy.ndimage import gaussian_filter
        fine = np.clip(gaussian_filter(zoom(rain, up, order=3), 2.5), 0, None)
        la = np.linspace(ING.LAT[0], ING.LAT[-1], fine.shape[0])
        lo = np.linspace(ING.LON[0], ING.LON[-1], fine.shape[1])
        from shapely import contains_xy
        LA, LO = np.meshgrid(la, lo, indexing="ij")
        inside = contains_xy(ksa, LO.ravel(), LA.ravel()).reshape(LA.shape)
        lv = [20, 30, 40, 50, 60, 70, 80, 90]
        fine = np.where(inside & (fine >= lv[0]), fine, np.nan)
        cols = ["#9ad1f5", "#4fa3e8", "#2f6fd6", "#2fae5a", "#f3d33a", "#f28c28", "#e0402c", "#b02a8f"]
        cmap = LinearSegmentedColormap.from_list("r", cols, N=len(cols))
        cmap.set_over("#4a1a6e")
        ax.imshow(fine, extent=[lo[0], lo[-1], la[-1], la[0]], origin="upper", cmap=cmap,
                  norm=BoundaryNorm(lv + [200], cmap.N, extend="neither"), alpha=0.85, interpolation="bilinear", zorder=1)
        # the colour key, bottom right over the sea
        kx = fig.add_axes([0.60, 0.06, 0.36, 0.022])
        kx.imshow(np.arange(len(cols))[None, :], cmap=cmap, aspect="auto", extent=[0, len(cols), 0, 1])
        kx.set_xticks(range(len(cols) + 1))
        kx.set_xticklabels([str(x).translate(F.AR_DIG) for x in lv] + [""], fontsize=6.5,
                           color="#e8edf2", fontfamily=fam)
        kx.set_yticks([])
        kx.tick_params(length=0, pad=1.5)
        for sp in kx.spines.values():
            sp.set_visible(False)
        kx.set_title(A("قوة مكونات الهطول (من ١٠٠)"), fontsize=7, color="#e8edf2", fontfamily=fam, pad=2)
    for r in regs:
        gs = getattr(r["geom"], "geoms", [r["geom"]])
        for g in gs:
            x, y = g.exterior.xy
            ax.plot(x, y, color="#e8edf2", linewidth=0.45, alpha=0.55, zorder=2)
    for g in getattr(ksa, "geoms", [ksa]):
        x, y = g.exterior.xy
        ax.plot(x, y, color="#f4f6f8", linewidth=1.1, alpha=0.9, zorder=2)
    try:
        F.draw_cities(ax, ax.transData, fontsize=6.2, wide=True)
    except Exception as ex:  # noqa: BLE001
        print("cities:", repr(ex)[:80])
    halo = [pe.withStroke(linewidth=2.6, foreground="#111111")]
    asp = 1 / np.cos(np.radians(24))
    from matplotlib.patches import Ellipse

    def ring(r, col, ls, lw, txt, below):
        e = Ellipse((r["lon"], r["lat"]), 2 * r["rad"] * asp, 2 * r["rad"], fill=False, edgecolor=col, linewidth=lw,
                    linestyle=ls, zorder=5, path_effects=[pe.withStroke(linewidth=lw + 2.2, foreground="#111111")])
        ax.add_patch(e)
        if txt:
            ax.text(r["lon"], r["lat"] + (-1 if below else 1) * (r["rad"] + 0.25), A(txt), ha="center",
                va="top" if below else "bottom", fontsize=8.2, fontweight="bold", color=col, fontfamily=fam,
                path_effects=halo, zorder=6)
    if ref:
        rr = [r for r in strongest_regs(ref, 3) if "lat" in r]
        low = min(rr, key=lambda r: r["lat"] - r["rad"]) if rr else None
        for r in rr:   # one label, under the lowest ring
            ring(r, "#ffffff", (0, (4, 3)), 1.3, f"الموجة المرجعية {ref_day}" if r is low else "", True)
    for r in strongest_regs(m, 3):
        if "lat" in r:
            ring(r, "#ffd23f", "solid", 2.2, label(r), False)
    # the title strip
    tx = fig.add_axes([0, 1 - top * 1.08, 1, top * 1.08])
    tx.axis("off")
    tx.add_patch(Rectangle((0, 0), 1, 1, color="#161b22", transform=tx.transAxes))
    tx.text(0.97, 0.70, A(title), ha="right", va="center", fontsize=12.5, fontweight="bold", color="#ffffff", fontfamily=fam)
    tx.text(0.97, 0.30, A(sub), ha="right", va="center", fontsize=8.0, color="#b8c0c8", fontfamily=fam)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    try:   # fewer colours, a lighter picture (as the low-level maps, 22 Nov 2026)
        from PIL import Image
        Image.open(path).convert("RGB").quantize(colors=200).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


def draw_wave(out_dir, st):
    """the map of the wave the report compared (st['ref_cmp'], set by report3.ref_compare) from GRIDS -> file name or None"""
    import os
    from datetime import date
    c = st.get("ref_cmp")
    if not c or not GRIDS:
        return None
    a, b = date.fromisoformat(c["a"]), date.fromisoformat(c["b"])
    days = [d for d in GRIDS if a.isoformat() <= d <= b.isoformat()]
    if not days:
        return None
    rain = np.max([GRIDS[d] for d in days], axis=0)
    m = wave_metrics(st.get("wave_rain") or [], a, b)
    ref = st.get("ref_wave") or current(None)
    os.makedirs(os.path.join(out_dir, "fig"), exist_ok=True)
    import sa_geo
    draw(os.path.join(out_dir, "fig", "refwave.png"), rain, m, ref, c["title"], c["sub"],
         sa_geo.ar_date(date.fromisoformat(ref["d"]), weekday=False) if ref else "")
    return "refwave.png"
