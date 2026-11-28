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
from datetime import date

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


HOURS = (0, 3, 6, 9, 12, 15, 18, 21)    # Makkah hours read for every day (Fahad 28 Nov 2026: the whole day, hour by hour)
NIGHT = (21, 0, 3, 6)                   # Makkah night hours, read with a lighter rule (see hourly)
KTH = 3                                 # the k-th strongest of the eight readings stands for the day (see hourly)
HOURLY_DAYS = 8                         # days 0..7 read every 3 hours; later days keep the 3 PM snapshot


def _one_hour(job):
    import ingredients as ING
    cycle, d, h, fh = job
    import daily
    for _ in range(2):
        try:
            f = daily.gfs_fields(cycle, fh, fields=list(ING.FIELDS))
            return d, h, index({n: ING.cut(f[n]) for n, _ in ING.FIELDS}, date.fromisoformat(d))
        except Exception as e:  # noqa: BLE001
            err = e
    print("hourly ingredients failed", d, h, repr(err)[:120], flush=True)
    return d, h, None


def hourly(cycle, days, procs=4):
    """the rain-making index read every 3 hours of each Makkah day (00..21 Makkah = 21 UTC the day before .. 18 UTC),
    instead of one picture at 3 PM (Fahad 28 Nov 2026: «هل درستها بساعاتها كاملة … ام اخذت متوسط اليوم»).
    A place counts with the third strongest of its eight readings: rain needs the ingredients on it for three readings
    (about nine hours) or more, not one passing frame. Tested on the 29 Nov-1 Dec 2026 wave: this keeps the spread of
    the peak day where the 3 PM picture (on which WET was fitted) put it (10.3 % vs 10.2 %), while the second strongest
    reading gave 14 % and the strongest 21 %, an inflation with no calibration behind it. -> {day: {"I": index 0..1, "hours": [[h, cover], ...]}}"""
    from datetime import datetime, timedelta
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    jobs = []
    for d in days:
        for h in HOURS:
            t = datetime(d.year, d.month, d.day) + timedelta(hours=h - 3)
            fh = int((t - t0).total_seconds() // 3600)
            if 0 <= fh <= 384 and fh % 3 == 0:
                jobs.append((cycle, d.isoformat(), h, fh))
    got = {}
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(procs) as ex:     # processes: gfs_fields' temporary file is per process
        for d, h, I in ex.map(_one_hour, jobs):
            if I is not None:
                got.setdefault(d, {})[h] = I
    out = {}
    for d, by in got.items():
        if len(by) < 4:
            continue                             # too few readings to stand for the day
        st_ = np.sort(np.stack(list(by.values())), axis=0)
        I = st_[-KTH] if len(by) >= KTH else st_[0]
        # the night (Fahad 28 Nov 2026: «غالب حالات الاخاديد تكون نشاط ليلي ثم تفوتك الحاله»): a trough's rain often
        # comes in a few night hours only; two night readings (9 PM to 6 AM) are enough there
        nh = [by[h] for h in NIGHT if h in by]
        night = None
        if len(nh) >= 2:
            night = np.sort(np.stack(nh), axis=0)[-2]
            I = np.maximum(I, night)
        out[d] = {"I": I, "hours": [[h, reading(by[h])["cover"]] for h in sorted(by)],
                  "night": reading(night)["cover"] if night is not None else 0.0}
    return out


def apply_hourly(st, cycle, day0, ndays=HOURLY_DAYS):
    """replace the wave_rain rows (and GRIDS) of days day0 .. day0+ndays-1 with the hourly reading"""
    from datetime import timedelta
    days = [day0 + timedelta(days=k) for k in range(ndays)]
    H = hourly(cycle, days)
    rows = st.get("wave_rain") or []
    by = {r["d"]: r for r in rows}
    n = 0
    for d, x in H.items():
        m = reading(x["I"])
        m["d"] = d
        m["hours"] = x["hours"]
        m["night"] = x["night"]
        pk = max(x["hours"], key=lambda t: t[1])
        m["peak_h"] = pk[0]
        GRIDS[d] = 100 * x["I"]
        if d in by:
            by[d].clear()
            by[d].update(m)
        else:
            rows.append(m)
        n += 1
    rows.sort(key=lambda r: r["d"])
    st["wave_rain"] = rows
    print("hourly rain-making reading:", n, "days", [(d[5:], round(by.get(d, {}).get("cover", 0), 3)) for d in sorted(H)], flush=True)
    return n


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
        if d in GRIDS:   # its map, for the picture beside the coming wave
            new["grid"] = np.round(GRIDS[d]).astype(int).tolist()
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


LEVELS = [20, 30, 40, 50, 60, 70, 80, 90]   # the full scale, as Fahad chose on 25 Nov 2026 («الالوان اجعلها هكذا»)
DARK = ["#9ad1f5", "#4fa3e8", "#2f6fd6", "#2fae5a", "#f3d33a", "#f28c28", "#e0402c", "#b02a8f"]


def _panel(fig, rect, grid, m, head, regs, ksa, fam, A, sea=None):
    """one map of the Kingdom: the index (x 100) where it reaches LEVELS[0], dark shades, and the strongest areas named"""
    from matplotlib import patheffects as pe
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from scipy.ndimage import zoom, gaussian_filter
    from shapely import contains_xy
    import figures as F
    import ingredients as ING
    W, E, S, N = 34.0, 56.5, 15.5, 32.6
    ax = fig.add_axes(rect)
    ax.set_facecolor("#1a2330")
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(1 / np.cos(np.radians(24)))
    ax.axis("off")
    try:   # the relief under everything, as the other maps
        from PIL import Image
        rw, re_, rs, rn = F.RELIEF["box"]
        rel = np.asarray(Image.open(F.RELIEF["path"]).convert("L"))
        ax.imshow(rel, extent=[rw, re_, rs, rn], origin="upper", cmap="gray", vmin=0, vmax=255, alpha=0.6,
                  interpolation="lanczos", zorder=0)
    except Exception as ex:  # noqa: BLE001
        print("relief unavailable:", str(ex)[:80])
    if grid is not None:
        up = 6
        g = np.asarray(grid, float)
        fine = np.clip(gaussian_filter(zoom(g, up, order=3), 2.5), 0, None)
        la = np.linspace(ING.LAT[0], ING.LAT[-1], fine.shape[0])
        lo = np.linspace(ING.LON[0], ING.LON[-1], fine.shape[1])
        LA, LO = np.meshgrid(la, lo, indexing="ij")
        inside = contains_xy(ksa, LO.ravel(), LA.ravel()).reshape(LA.shape)
        if sea is not None:   # the heavy sea cells and their path: drawn over the sea too
            sf = np.clip(gaussian_filter(zoom(np.asarray(sea, float), up, order=3), 2.5), 0, None)
            fine = np.maximum(fine, sf)
            inside = inside | (sf >= LEVELS[0])
        fine = np.where(inside & (fine >= LEVELS[0]), fine, np.nan)
        ax.imshow(fine, extent=[lo[0], lo[-1], la[-1], la[0]], origin="upper", cmap=ListedColormap(DARK),
                  norm=BoundaryNorm(LEVELS + [200], len(DARK)), alpha=0.85, interpolation="bilinear", zorder=1)
    for r in regs:
        for g_ in getattr(r["geom"], "geoms", [r["geom"]]):
            x, y = g_.exterior.xy
            ax.plot(x, y, color="#e8edf2", linewidth=0.4, alpha=0.5, zorder=2)
    for g_ in getattr(ksa, "geoms", [ksa]):
        x, y = g_.exterior.xy
        ax.plot(x, y, color="#f4f6f8", linewidth=1.0, alpha=0.9, zorder=2)
    try:
        F.draw_cities(ax, ax.transData, fontsize=5.6, wide=True)
    except Exception as ex:  # noqa: BLE001
        print("cities:", repr(ex)[:80])
    halo = [pe.withStroke(linewidth=2.4, foreground="#111111")]
    # no area names or circles on the map: the regions' borders and the cities say it (Fahad, 25 Nov 2026)
    ax.text(0.5, 0.985, A(head), transform=ax.transAxes, ha="center", va="top", fontsize=10, fontweight="bold",
            color="#ffffff", fontfamily=fam, path_effects=halo, zorder=7)
    return ax


def draw(path, panels, title, sub):
    """two maps side by side in one picture (Fahad, 25 Nov 2026: «احذف الدوائر ودائما ضع خريطتين في صورة واحدة بجانب
    بعض.. أشد أماكن الهطول لونها بألوان غامقه فقط»): panels = [(grid x 100, metrics, heading), ...], right to left,
    the coming wave first (on the right); the title strip above the maps, never over them"""
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
    pw = 6.0                                       # inches per map
    ph = pw * (32.6 - 15.5) / (56.5 - 34.0) * 1.1
    head, foot = 0.95, 0.75
    fig = plt.figure(figsize=(pw * n, ph + head + foot), dpi=160)
    fig.patch.set_facecolor("#111111")
    H = fig.get_figheight()
    for k, p_ in enumerate(panels):
        grid, m, hd = p_[:3]
        x0 = (n - 1 - k) / n                       # the first panel on the right (Arabic reading order)
        _panel(fig, [x0 + 0.004, foot / H, 1 / n - 0.008, ph / H], grid, m, hd, regs, ksa, fam, A,
               sea=p_[3] if len(p_) > 3 else None)
    tx = fig.add_axes([0, 1 - head / H, 1, head / H])
    tx.axis("off")
    tx.add_patch(Rectangle((0, 0), 1, 1, color="#161b22", transform=tx.transAxes))
    tx.text(0.985, 0.68, A(title), ha="right", va="center", fontsize=14, fontweight="bold", color="#ffffff", fontfamily=fam)
    tx.text(0.985, 0.27, A(sub), ha="right", va="center", fontsize=8.6, color="#b8c0c8", fontfamily=fam)
    # the colour key along the bottom
    kx = fig.add_axes([0.30, 0.45 * foot / H, 0.40, 0.22 * foot / H])
    kx.imshow(np.arange(len(DARK))[None, :], cmap=ListedColormap(DARK), aspect="auto", extent=[0, len(DARK), 0, 1])
    kx.set_xticks(np.arange(len(DARK)) + 0.5)
    kx.set_xticklabels([str(v).translate(F.AR_DIG) for v in LEVELS],
                       fontsize=7, color="#e8edf2", fontfamily=fam)
    kx.set_yticks([])
    kx.tick_params(length=0, pad=1.5)
    for sp_ in kx.spines.values():
        sp_.set_visible(False)
    fig.text(0.71, 0.56 * foot / H, A("قوة مكونات الهطول من ١٠٠"), ha="left", va="center", fontsize=7.5,
             color="#e8edf2", fontfamily=fam)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    try:   # fewer colours, a lighter picture (as the low-level maps, 22 Nov 2026)
        from PIL import Image
        Image.open(path).convert("RGB").quantize(colors=200).save(path, optimize=True)
    except Exception:  # noqa: BLE001
        pass


PLUME_H, PLUME_FADE = 5.0, 0.1   # hours a heavy cell is followed downstream, share of its strength lost per hour


def sea_plume(st, a, b):
    """the heavy sea cells of the nights a-1 .. b and their path inland, x 100 on the ingredients' 1 degree grid
    (Fahad 27 Nov 2026: «المفترض تكون رسمه متطابقة من الساحل للداخل»): each heavy core (seacell.heavy_core) is followed
    along its own 700-500 hPa steering wind for PLUME_H hours, fading PLUME_FADE per hour, as the cells it makes travel
    from the sea over the coast and inland; or None"""
    from datetime import timedelta
    import ingredients as ING
    import seacell
    G = np.zeros((len(ING.LAT), len(ING.LON)))
    any_ = False
    for r_ in st.get("seacell") or []:
        if not ((a - timedelta(days=1)).isoformat() <= r_["d"] <= b.isoformat()):
            continue
        for p in seacell.heavy_core(r_) or []:
            la_, lo_, v = p[0], p[1], 100 * p[2]
            u, w = (p[3], p[4]) if len(p) > 4 else (0.0, 0.0)
            for h in np.arange(0, PLUME_H + 1e-6, 0.25):
                y = la_ + w * 3600 * h / 111e3
                x = lo_ + u * 3600 * h / (111e3 * np.cos(np.radians(la_)))
                j, i = int(round((ING.LAT[0] - y) / 1.0)), int(round((x - ING.LON[0]) / 1.0))
                if 0 <= j < len(ING.LAT) and 0 <= i < len(ING.LON):
                    G[j, i] = max(G[j, i], v * (1 - PLUME_FADE * h))
                    any_ = True
    return G if any_ else None


def draw_wave(out_dir, st):
    """the picture of the wave the report compared (st['ref_cmp'], set by report3.ref_compare), beside the reference
    wave, from GRIDS and the reference's stored grid -> file name or None"""
    import os
    from datetime import date
    import sa_geo
    c = st.get("ref_cmp")
    if not c or not GRIDS:
        return None
    a, b = date.fromisoformat(c["a"]), date.fromisoformat(c["b"])
    days = [d for d in GRIDS if a.isoformat() <= d <= b.isoformat()]
    if not days:
        return None
    grid = np.max([GRIDS[d] for d in days], axis=0)
    m = wave_metrics(st.get("wave_rain") or [], a, b)
    ref = st.get("ref_wave") or current(None)
    panels = [(grid, m, c["head"], sea_plume(st, a, b))]
    if ref:
        panels.append((ref.get("grid"), ref, "الموجة المرجعية " + sa_geo.ar_date(date.fromisoformat(ref["d"]), weekday=False)))
    os.makedirs(os.path.join(out_dir, "fig"), exist_ok=True)
    draw(os.path.join(out_dir, "fig", "refwave.png"), panels, c["title"], c["sub"])
    return "refwave.png"
