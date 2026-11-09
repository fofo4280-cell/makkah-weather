"""The weather of one Makkah day over the Kingdom, region by region, for the daily report.

situation(day, sa_dir, state_dir) -> {"heading", "lines", "data"}

Sources (all read on the day the report is written):
  - ECMWF IFS 0.25, GFS and ICON daily rain, maximum and minimum temperature and gusts, through Open-Meteo,
    on a half-degree grid inside the Kingdom plus some 110 towns (the same three models as the main site).
  - Our own 9 km Kingdom run (model-data-sa branch): hourly rain and gusts of the hours it covers.
  - Dust near the ground from the CAMS global forecast (Copernicus), through Open-Meteo.
  - Daily normals of maximum and minimum temperature (ERA5, 2001-2020) at two or three towns per region,
    fetched once per calendar month and kept in the state folder.
"""
import json, math, os
from datetime import date, datetime, timedelta, timezone

import numpy as np

import sa_geo as G
from sa_geo import ar, num, ar_date, join, deg

MODELS = [("ecmwf_ifs025", "الأوروبي"), ("gfs_seamless", "الأمريكي"), ("icon_seamless", "الألماني")]
DVARS = ["temperature_2m_max", "temperature_2m_min", "wind_gusts_10m_max"]   # rain comes from our own model only
NORM_YEARS = range(2001, 2021)
TZ = "Asia/Riyadh"


# ------------------------------------------------------------------ data
def model_days(om, lat, lon, day):
    """{model: {var: array[2, n]}} for the day before and the day (Makkah calendar days)."""
    js = om.get(G.FORECAST, {"daily": ",".join(DVARS), "models": ",".join(m for m, _ in MODELS), "timezone": TZ,
                             "start_date": (day - timedelta(days=1)).isoformat(), "end_date": day.isoformat()},
                lat, lon, weight=len(DVARS) * len(MODELS) / 10)
    out = {}
    for m, _ in MODELS:
        out[m] = {}
        for v in DVARS:
            a = np.full((2, len(js)), np.nan)
            for i, j in enumerate(js):
                vals = (j.get("daily") or {}).get(f"{v}_{m}") or [None, None]
                a[:, i] = [np.nan if x is None else x for x in vals[:2]]
            out[m][v] = a
    return out


def dust_day(om, lat, lon, day):
    """Hourly dust near the ground (micrograms per cubic metre) for the day: array[24, n]."""
    js = om.get(G.AIR, {"hourly": "dust", "timezone": TZ, "start_date": day.isoformat(), "end_date": day.isoformat()},
                lat, lon)
    a = np.full((24, len(js)), np.nan)
    for i, j in enumerate(js):
        v = (j.get("hourly") or {}).get("dust") or []
        a[:len(v[:24]), i] = [np.nan if x is None else x for x in v[:24]]
    return a


def normals(om, state_dir, day):
    """{town: (tmax, tmin)} normal for the day: ERA5 2001-2020, a 15-day window around the date.
    A whole month is fetched at once and kept, so this costs Open-Meteo calls once per calendar month."""
    d = os.path.join(state_dir, "normals")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"m{day.month:02d}.json")
    if not os.path.exists(p):
        towns = sorted({t for ts in G.NORMAL_TOWNS.values() for t in ts})
        lat = [G.PLACE[t][0] for t in towns]; lon = [G.PLACE[t][1] for t in towns]
        acc = {t: {} for t in towns}         # MMDD -> list of (tmax, tmin)
        for y in NORM_YEARS:
            a = date(y, day.month, 1) - timedelta(days=8)
            b = (date(y + (day.month == 12), day.month % 12 + 1, 1)) + timedelta(days=8)
            js = om.get(G.ARCHIVE, {"daily": "temperature_2m_max,temperature_2m_min", "timezone": TZ,
                                    "start_date": a.isoformat(), "end_date": b.isoformat()},
                        lat, lon, weight=(b - a).days / 14)
            for t, j in zip(towns, js):
                dd = j["daily"]
                for s, hi, lo in zip(dd["time"], dd["temperature_2m_max"], dd["temperature_2m_min"]):
                    if hi is not None and lo is not None:
                        acc[t].setdefault(s[5:], []).append((hi, lo))
        res = {}
        for t in towns:
            res[t] = {}
            for k in range(1, 32):
                try:
                    c = date(2001, day.month, k)
                except ValueError:
                    continue
                win = [(c + timedelta(days=o)).strftime("%m-%d") for o in range(-7, 8)]
                v = [x for w in win for x in acc[t].get(w, [])]
                if v:
                    res[t][c.strftime("%m-%d")] = [round(float(np.mean([x[0] for x in v])), 1),
                                                   round(float(np.mean([x[1] for x in v])), 1)]
        json.dump(res, open(p, "w"), ensure_ascii=False)
    res = json.load(open(p))
    k = day.strftime("%m-%d") if day.strftime("%m-%d") != "02-29" else "02-28"
    return {t: tuple(v[k]) for t, v in res.items() if k in v}


def lcc_inverse(pr, x, y):
    r = math.pi / 180
    p1, p2, p0, l0 = pr["truelat1"] * r, pr["truelat2"] * r, pr["ref_lat"] * r, pr["stand_lon"] * r
    t = lambda p: math.tan(math.pi / 4 + p / 2)
    n = math.log(math.cos(p1) / math.cos(p2)) / math.log(t(p2) / t(p1))
    F = math.cos(p1) * t(p1) ** n / n
    R = pr.get("R", 6370000.0)
    rho0 = R * F / t(p0) ** n
    rho = np.sign(n) * np.hypot(x, rho0 - y)
    th = np.arctan2(x, rho0 - y)
    lon = (l0 + th / n) / r
    lat = (2 * np.arctan((R * F / rho) ** (1 / n)) - math.pi / 2) / r
    return lat, lon


def lcc_forward(pr, lat, lon):
    r = math.pi / 180
    p1, p2, p0, l0 = pr["truelat1"] * r, pr["truelat2"] * r, pr["ref_lat"] * r, pr["stand_lon"] * r
    t = lambda p: np.tan(math.pi / 4 + p / 2)
    n = math.log(math.cos(p1) / math.cos(p2)) / math.log(t(p2) / t(p1))
    F = math.cos(p1) * t(p1) ** n / n
    R = pr.get("R", 6370000.0)
    rho = R * F / t(np.asarray(lat) * r) ** n
    rho0 = R * F / t(p0) ** n
    th = n * (np.asarray(lon) * r - l0)
    return rho * np.sin(th), rho0 - rho * np.cos(th)


def our_model_day(dirs, day, log=print):
    """Rain (mm) and highest gust (km/h) of our own runs over the hours they cover of the Makkah day.
    dirs: published data folders (the Kingdom 9 km run and the western 3 km run). Every domain with point data
    takes part; where domains overlap, the finer one is used, as on the map page. Returns
    {lat, lon, rain, gust, w (cell area weight), doms: [(name, res, run)], hours, h0, h1} or None."""
    t_a = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(hours=3)   # 00 Makkah
    t_b = t_a + timedelta(hours=24)
    cands = []
    for root in [d for d in dirs if d and os.path.exists(os.path.join(d, "runs.json"))]:
        best = {}
        for r in json.load(open(os.path.join(root, "runs.json"))).get("runs", []):
            p = os.path.join(root, "runs", r["run"], "manifest.json")
            if not os.path.exists(p):
                continue
            man = json.load(open(p))
            init = datetime.strptime(man["init"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            for dom, d in (man.get("domains") or {}).items():
                P = d.get("points")
                if not P or not os.path.exists(os.path.join(root, "runs", r["run"], P["file"])):
                    continue
                hs = [k for k, h in enumerate(P["hours"]) if k > 0 and t_a < init + timedelta(hours=h) <= t_b]
                if dom not in best or len(hs) > len(best[dom]["hs"]):
                    best[dom] = {"root": root, "run": r["run"], "init": init, "P": P, "hs": hs, "dom": dom,
                                 "proj": d.get("proj") or man["proj"], "name": d.get("name", dom), "res": d.get("res", "")}
        cands += best.values()
    if not cands:
        return None
    top = max(len(c["hs"]) for c in cands)
    if top < 9:
        return None
    cands = [c for c in cands if len(c["hs"]) >= top - 1]          # same hours of the day (drops the 1 km window runs)
    cands.sort(key=lambda c: -c["P"]["dx"])
    for c in cands:
        P = c["P"]
        raw = np.fromfile(os.path.join(c["root"], "runs", c["run"], P["file"]), np.uint8)
        nh, ny, nx = len(P["hours"]), P["ny"], P["nx"]
        arr = raw.reshape(len(P["vars"]), nh, ny, nx)
        vi = {v: k for k, v in enumerate(P["vars"])}
        c["rain"] = ((arr[vi["rain1h"], c["hs"]].astype(np.float32) / 25) ** 2).sum(0).ravel()
        c["gust"] = (arr[vi["wind"], c["hs"]].astype(np.float32) / 2).max(0).ravel()
        jj, ii = np.mgrid[0:ny, 0:nx]
        la, lo = lcc_inverse(c["proj"], P["x00"] + ii * P["dx"], P["y00"] + jj * P["dx"])
        c["lat"], c["lon"] = la.ravel(), lo.ravel()
        c["keep"] = np.ones(c["lat"].shape, bool)
    for k, c in enumerate(cands):     # leave to a finer domain (or an earlier one as fine) what it covers
        for q, f in enumerate(cands):
            if q == k or f["P"]["dx"] > c["P"]["dx"] or (f["P"]["dx"] == c["P"]["dx"] and q > k):
                continue
            x, y = lcc_forward(f["proj"], c["lat"], c["lon"])
            i = np.round((x - f["P"]["x00"]) / f["P"]["dx"]); j = np.round((y - f["P"]["y00"]) / f["P"]["dx"])
            c["keep"] &= ~((i >= 2) & (j >= 2) & (i <= f["P"]["nx"] - 3) & (j <= f["P"]["ny"] - 3))
    cat = lambda key: np.concatenate([c[key][c["keep"]] for c in cands])
    c0 = cands[0]
    loc = lambda h: (c0["init"] + timedelta(hours=c0["P"]["hours"][h], minutes=180)).hour
    log("report: our runs used: " + ", ".join(f"{c['run']} {c['dom']} {len(c['hs'])} h" for c in cands))
    return {"lat": cat("lat"), "lon": cat("lon"), "rain": cat("rain"), "gust": cat("gust"),
            "w": np.concatenate([np.full(int(c["keep"].sum()), float(c["P"]["dx"]) ** 2) for c in cands]),
            "doms": [(c["name"], c["res"], c["run"]) for c in cands], "hours": top,
            "h0": (loc(c0["hs"][0]) - 1) % 24, "h1": loc(c0["hs"][-1]) or 24}


# ------------------------------------------------------------------ assessment
RAIN_WORDS = [(30, "أمطار غزيرة"), (15, "أمطار متوسطة إلى غزيرة"), (5, "أمطار متوسطة"), (1, "أمطار خفيفة"),
              (0, "رذاذ أو زخات خفيفة متفرقة")]


def rain_word(peak):
    return next(w for t, w in RAIN_WORDS if peak >= t)


def situation(day, our_dirs, state_dir, st=None, om=None, log=print):
    om = om or G.OpenMeteo()
    regs = G.tag_towns(G.regions())
    lat, lon, ri, names = G.grid_points(regs, 0.5)
    grid = np.array([n == "" for n in names])
    M = model_days(om, lat, lon, day)
    log(f"report: model days at {len(lat)} points, Open-Meteo weight so far {om.used:.0f}")
    data = {"day": day.isoformat(), "regions": []}
    lines, head = [], []

    # ---- rain: our own model only, set against the large-scale picture
    wrf = None
    try:
        wrf = our_model_day(our_dirs, day, log)
    except Exception as e:
        log(f"report: our model runs unreadable: {e!r}")
    rainy = []
    if wrf is None:
        lines.append("الأمطار: لم يكتمل تشغيل نموذجنا الذي يغطي هذا اليوم عند كتابة التقرير، فلا ترتيب للمناطق اليوم.")
    else:
        wri = G.region_of_points(regs, wrf["lat"], wrf["lon"])
        rows = []
        for k, r in enumerate(regs):
            m_k = wri == k
            if not m_k.any():
                continue
            v, w = wrf["rain"][m_k], wrf["w"][m_k]
            j = int(np.argmax(v))
            rows.append({"k": k, "name": r["name"], "mean": float((v * w).sum() / w.sum()),
                         "cov": float((w * (v >= 1)).sum() / w.sum()), "max": float(v[j]),
                         "at": (float(wrf["lat"][m_k][j]), float(wrf["lon"][m_k][j]))})
        rainy = sorted([x for x in rows if x["cov"] >= 0.03 or x["max"] >= 5], key=lambda x: -x["mean"])
        span = (f"من الساعة {ar(wrf['h0'])} إلى الساعة {ar(wrf['h1'])} بتوقيت مكة" if wrf["hours"] < 23
                else "على مدى اليوم كله")
        if rainy:
            parts = []
            for x in rainy[:6]:
                pl, dist = G.nearest_place(*x["at"], regs[x["k"]])
                near = f"قرب {pl}" if dist <= 45 else "في أنحاء من المنطقة"
                parts.append(f"{x['name']} ({rain_word(x['max'])}، تغطي نحو {num(100 * x['cov'])}٪ من المنطقة، "
                             f"وتصل إلى {num(x['max'])} ملم {near})")
            if len(rainy) == 1:
                line = f"الأمطار ({span}): على منطقة واحدة هي " + parts[0] + "."
            elif len(rainy) <= 6:
                line = (f"الأمطار ({span})، من الأغزر إلى الأقل بمجموعها على المنطقة: " + "، ثم ".join(parts[:-1])
                        + "، وأقلها " + parts[-1] + ".")
            else:
                rest = rainy[6:]
                line = f"الأمطار ({span})، من الأغزر إلى الأقل بمجموعها على المنطقة: " + "، ثم ".join(parts) + "."
                line += (f" وأقلها {rest[0]['name']}." if len(rest) == 1 else
                         f" وأمطار أقل على {join(x['name'] for x in rest[:-1])}، وأقلها {rest[-1]['name']}.")
            dry = [x["name"] for x in rows if x not in rainy]
            if dry:
                line += f" ولا أمطار تُذكر على {join(dry)}."
            lines.append(line)
            head.append(f"أمطار على {join(x['name'] for x in rainy[:4])}")
        else:
            lines.append(f"الأمطار ({span}): لا يُظهر نموذجنا أمطارًا تُذكر على مناطق المملكة.")
        data["rain"] = [{k: v for k, v in x.items() if k != "at"} for x in rainy]
        data["our_runs"] = wrf["doms"]
    if st is not None:
        try:
            lines.append(big_picture(st, day, rainy))
        except Exception as e:
            log(f"report: large-scale check failed: {e!r}")

    # ---- temperature: extremes, change from the day before, and departure from normal at the towns
    med = lambda v, d: np.nanmedian(np.stack([M[m][v][d] for m, _ in MODELS]), axis=0)
    tx, tn = med("temperature_2m_max", 1), med("temperature_2m_min", 1)
    dtx, dtn = tx - med("temperature_2m_max", 0), tn - med("temperature_2m_min", 0)
    try:
        nrm = normals(om, state_dir, day)
    except Exception as e:
        log(f"report: normals unavailable: {e}")
        nrm = {}
    tidx = {n: i for i, n in enumerate(names) if n}
    cold, hot, falls, rises = [], [], [], []
    for k, r in enumerate(regs):
        m_k = ri == k
        if not np.isfinite(tn[m_k]).any():
            continue
        jn = int(np.nanargmin(np.where(m_k, tn, np.inf))); jx = int(np.nanargmax(np.where(m_k, tx, -np.inf)))
        an = [(tn[tidx[t]] - nrm[t][1], tx[tidx[t]] - nrm[t][0]) for t in G.NORMAL_TOWNS[r["id"]] if t in nrm and t in tidx]
        a_n = float(np.mean([a[0] for a in an])) if an else None
        a_x = float(np.mean([a[1] for a in an])) if an else None
        rec = {"name": r["name"], "tmin": float(tn[jn]), "tmin_at": G.nearest_place(lat[jn], lon[jn], r)[0],
               "tmax": float(tx[jx]), "tmax_at": G.nearest_place(lat[jx], lon[jx], r)[0],
               "dmin": float(np.nanmean(dtn[m_k])), "dmax": float(np.nanmean(dtx[m_k])), "amin": a_n, "amax": a_x}
        data["regions"].append(rec)
        if (a_n is not None and a_n <= -4) or rec["tmin"] <= 2 or (rec["dmin"] <= -5 and (a_n is None or a_n <= -3)):
            cold.append(rec)
        elif rec["dmin"] <= -3 or rec["dmax"] <= -4:
            falls.append(rec)
        if (a_x is not None and a_x >= 4) or rec["tmax"] >= 48 or (rec["tmax"] >= 45 and (a_x or 0) >= 2):
            hot.append(rec)
        elif rec["dmax"] >= 4:
            rises.append(rec)

    def anom_txt(a):
        return "" if a is None else (f"، أقل من معدلها بنحو {deg(a)}" if a <= -1.5 else
                                     f"، أعلى من معدلها بنحو {deg(a)}" if a >= 1.5 else "، قريبة من معدلها")
    if cold:
        cold.sort(key=lambda x: x["tmin"])
        ln = "موجة باردة: " + "، و".join(
            f"{x['name']} (الصغرى {num(x['tmin'])}° قرب {x['tmin_at']}{anom_txt(x['amin'])}"
            + (f"، وتنخفض {deg(x['dmin'])} عن أمس" if x["dmin"] <= -2 else "") + ")" for x in cold[:6]) + "."
        if any(x["tmin"] <= 0 for x in cold):
            ln += f" يُتوقع الصقيع على {join(x['tmin_at'] for x in cold if x['tmin'] <= 0)}."
        lines.append(ln)
        head.append(f"موجة باردة على {join(x['name'] for x in cold[:3])}")
    if hot:
        hot.sort(key=lambda x: -x["tmax"])
        lines.append("موجة حارة: " + "، و".join(
            f"{x['name']} (العظمى {num(x['tmax'])}° قرب {x['tmax_at']}{anom_txt(x['amax'])})" for x in hot[:6]) + ".")
        head.append(f"موجة حارة على {join(x['name'] for x in hot[:3])}")
    if falls:
        lines.append("انخفاض ملموس في درجات الحرارة عن أمس على " + join(
            f"{x['name']} (نحو {deg(min(x['dmin'], x['dmax']))})" for x in falls) + ".")
    if rises:
        lines.append("ارتفاع ملموس في درجات الحرارة عن أمس على " + join(
            f"{x['name']} (نحو {deg(x['dmax'])})" for x in rises) + ".")
    if data["regions"]:
        lo_ = min(data["regions"], key=lambda x: x["tmin"]); hi_ = max(data["regions"], key=lambda x: x["tmax"])
        lines.append(f"{'' if cold or hot else 'الحرارة في حدود معدلاتها دون موجة حارة أو باردة. '}"
                     f"أعلى عظمى في المملكة {num(hi_['tmax'])}° قرب {hi_['tmax_at']} ({hi_['name']})، "
                     f"وأدنى صغرى {num(lo_['tmin'])}° قرب {lo_['tmin_at']} ({lo_['name']}).")

    # ---- dust and wind
    gust = med("wind_gusts_10m_max", 1)
    try:
        dlat, dlon, dri, dnames = G.grid_points(regs, 1.0)
        dust = dust_day(om, dlat, dlon, day)
        dgrid = np.array([n == "" for n in dnames])
    except Exception as e:
        log(f"report: dust forecast unavailable: {e}")
        dust = None
    dusty, windy = [], []
    for k, r in enumerate(regs):
        g_k = (ri == k) & grid
        gx = float(np.nanpercentile(gust[ri == k], 90)) if np.isfinite(gust[ri == k]).any() else 0
        rec = {"name": r["name"], "gust": gx}
        if dust is not None:
            m_k = dri == k
            mx = np.nanmax(dust[:, m_k], axis=0) if m_k.any() else np.array([0.0])
            gm = dgrid[m_k] if m_k.any() else np.array([False])
            if np.isfinite(mx).any() and gm.any():
                j = int(np.nanargmax(mx))
                cov = lambda t: float(np.nanmean(mx[gm] >= t))
                lvl = 3 if cov(1000) >= 0.15 else 2 if cov(500) >= 0.15 else 1 if cov(200) >= 0.25 else 0
                rec.update(dmax=float(mx[j]), lvl=lvl, dcov=cov(200),
                           dat=G.nearest_place(dlat[m_k][j], dlon[m_k][j], r)[0],
                           dhour=int(np.nanargmax(dust[:, np.flatnonzero(m_k)[j]])))
        if rec.get("lvl", 0) > 0:
            dusty.append(rec)
        elif gx >= 50 and g_k.any():
            windy.append(rec)
    if dusty:
        dusty.sort(key=lambda x: (-x["lvl"], -x["dcov"]))

        def dword(v):
            return {3: "غبار كثيف قد يصل إلى عاصفة ترابية تخفض الرؤية بشدة", 2: "غبار مثار يحد من مدى الرؤية",
                    1: "غبار عالق خفيف"}[v]
        lines.append("الغبار: " + "، و".join(
            f"{x['name']} ({dword(x['lvl'])} على نحو {num(100 * x['dcov'])}٪ من المنطقة، أشده قرب {x['dat']} نحو الساعة {ar(x['dhour'])} "
            f"بتركيز {num(x['dmax'])} ميكروغرام/م³" + (f"، وهبات رياح حتى {num(x['gust'])} كم/س" if x["gust"] >= 40 else "")
            + ")" for x in dusty[:6]) + ".")
        head.append(f"{'غبار كثيف' if dusty[0]['lvl'] == 3 else 'غبار'} على {join(x['name'] for x in dusty[:3])}")
    if windy:
        lines.append("رياح نشطة قد تثير الأتربة على " + join(f"{x['name']} (هبات حتى {num(x['gust'])} كم/س)" for x in windy) + ".")
    if not dusty and not windy and dust is not None:
        lines.append("الغبار: لا يتوقع نموذج كوبرنيكوس غبارًا مؤثرًا، والرياح في حدودها المعتادة.")
    data["dust"] = [{k: v for k, v in x.items()} for x in dusty]

    srcs = ""
    if wrf is not None:
        def run_txt(run):
            rd = date(int(run[:4]), int(run[4:6]), int(run[6:8]))
            return f"دورة {'الثالثة فجرًا' if run[8:10] == '00' else 'الثالثة عصرًا'} يوم {ar_date(rd)}"
        srcs += "الأمطار من نموذجنا وحده (" + "، و".join(f"{n} بدقة {r}" for n, r, _ in wrf["doms"]) + f"، {run_txt(wrf['doms'][0][2])})؛ "
    srcs += ("والحرارة والرياح من النموذج الأوروبي والأمريكي جي إف إس والألماني أيكون، والغبار من خدمة كوبرنيكوس "
             "الأوروبية لمراقبة الغلاف الجوي، والمعدلات من إعادة التحليل الأوروبية للفترة ٢٠٠١–٢٠٢٠ في مدن كل منطقة.")
    summary = ("أبرز ما يؤثر على طقس المملكة: " + "، و".join(head) + ".") if head else \
        "لا حالة جوية بارزة على المملكة: لا أمطار تُذكر ولا موجة حارة أو باردة ولا غبار مؤثر."
    lines = [summary] + lines + [f"المصادر: {srcs}"]
    log(f"report: today's section done, Open-Meteo weight {om.used:.0f}")
    return {"heading": f"طقس المملكة يوم {ar_date(day)}", "lines": lines, "data": data}


# ------------------------------------------------------------------ the large-scale picture of the day
BOX_OF = {"SA-02": "west", "SA-03": "west", "SA-09": "southwest", "SA-14": "southwest", "SA-10": "southwest",
          "SA-11": "southwest", "SA-01": "central", "SA-05": "central", "SA-04": "east", "SA-06": "north",
          "SA-12": "north", "SA-08": "north", "SA-07": "north"}
BOX_NAME = {"west": "الحجاز وغرب المملكة", "southwest": "جنوب غرب المملكة", "central": "وسط المملكة",
            "east": "شرق المملكة", "north": "شمال المملكة"}


def big_picture(st, day, rainy):
    """Does the large-scale picture back the rain our model gives for the day? One Arabic paragraph."""
    import bigpic as B
    regs = {r["name"]: r for r in G.regions()}
    pro, con = [], []
    m = B.rmm_on(st, day)
    if m and st.get("wet_season"):
        if m["amp"] >= 1 and m["phase"] in B.WET_PHASES:
            pro.append(f"التذبذب المداري في الطور {ar(m['phase'])} الرطب للمملكة بشدة {num(m['amp'], 1)}")
        elif m["amp"] >= 1:
            con.append(f"التذبذب المداري في الطور {ar(m['phase'])} الجاف للمملكة فيكبت الحمل")
    w = next((x for x in B.wave1(st["hov"]) if x[0] == day.isoformat()), None) if st.get("hov") else None
    if w:
        if B.favourable(w[1]):
            pro.append(f"الحدث الدافئ (التباعد العلوي) متمركز فوق {B.region_name(w[1])} في القطاع المحفز للجزيرة العربية")
        else:
            con.append(f"الحدث الدافئ بعيد فوق {B.region_name(w[1])}")
    row = next((r for r in st.get("pw", []) if r["d"] == day.isoformat()), None)
    if row:
        boxes = [k for k in BOX_NAME if k in row and row[k]["pct"] >= 150]
        if boxes:
            pro.append("مد رطوبي فوق " + join(f"{BOX_NAME[k]} ({num(row[k]['pct'])}٪ من المعدل)" for k in boxes))
        else:
            dry = [k for k in BOX_NAME if k in row and row[k]["pct"] < 80]
            if dry and rainy and all(BOX_OF[regs[x["name"]]["id"]] in dry for x in rainy):
                con.append("الرطوبة دون المعدل فوق مناطق المطر")
    wv = next((x for x in st.get("waves", []) if x["d"] == day.isoformat()), None)
    if wv and "trough" in wv and wv["trough"]["v"] <= -25:
        pro.append(f"أخدود في الطبقة الوسطى فوق {wv['trough']['area']}")
    cv = [c for c in st.get("conv", []) if c.get("hejaz_max") is not None and c["hejaz_max"] >= 2]
    if cv:
        pro.append("التقاء رياح عند ٩٢٥ هكتوباسكال فوق الحجاز وتهامة")
    ar_ = st.get("ar") or {}
    mk = [r for r in ar_.get("sa", []) if (datetime.strptime(r["t"], "%Y-%m-%dT%H:%MZ") + timedelta(hours=3)).date() == day]
    if mk and max(r["v"] for r in mk) >= 250:
        pro.append(f"نهر جوي يبلغ أراضي المملكة بنقل {num(max(r['v'] for r in mk))} كغ/م/ث")
    n = len(pro)
    if rainy:
        verdict = ("تعزز الحالة بقوة، فالأمطار جزء من نظام واسع منظم" if n >= 3 else
                   "تعزز الحالة جزئيًا" if n >= 1 else
                   "لا تعزز الحالة، فالأمطار محلية من تسخين النهار والتضاريس وتبقى متفرقة")
    else:
        verdict = ("مهيأة للمطر، لكن نموذجنا لا يُظهر أمطارًا اليوم، فتُتابع التحديثات" if n >= 2 else
                   "لا تدعم حالة مطرية اليوم")
    txt = f"الصورة الكبرى {verdict}"
    if pro:
        txt += ": " + "، و".join(pro)
    if con:
        txt += ("؛ وفي المقابل " if pro else ": ") + "، و".join(con)
    return txt + "."
