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
DVARS = ["precipitation_sum", "temperature_2m_max", "temperature_2m_min", "wind_gusts_10m_max"]
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


def wrf_day(sa_dir, day):
    """Rain (mm) and highest gust (km/h) of our 9 km Kingdom run over the hours it covers of the Makkah day:
    {run, hours, lat, lon, rain, gust, h0, h1} or None."""
    if not sa_dir or not os.path.exists(os.path.join(sa_dir, "runs.json")):
        return None
    t_a = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(hours=3)   # 00 Makkah
    t_b = t_a + timedelta(hours=24)
    best = None
    for r in json.load(open(os.path.join(sa_dir, "runs.json"))).get("runs", []):
        p = os.path.join(sa_dir, "runs", r["run"], "manifest.json")
        if not os.path.exists(p):
            continue
        man = json.load(open(p))
        d = (man.get("domains") or {}).get("sa") or {}
        P = d.get("points")
        if not P:
            continue
        init = datetime.strptime(man["init"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        hs = [k for k, h in enumerate(P["hours"]) if k > 0 and t_a < init + timedelta(hours=h) <= t_b]
        if best is None or len(hs) > len(best[2]):
            best = (r["run"], man, hs, P, init)
    if best is None or len(best[2]) < 9:
        return None
    run, man, hs, P, init = best
    raw = np.fromfile(os.path.join(sa_dir, "runs", run, P["file"]), np.uint8)
    nh, ny, nx = len(P["hours"]), P["ny"], P["nx"]
    arr = raw.reshape(len(P["vars"]), nh, ny, nx)
    vi = {v: k for k, v in enumerate(P["vars"])}
    rain = ((arr[vi["rain1h"], hs].astype(np.float32) / 25) ** 2).sum(0)
    gust = (arr[vi["wind"], hs].astype(np.float32) / 2).max(0)
    jj, ii = np.mgrid[0:ny, 0:nx]
    lat, lon = lcc_inverse(d.get("proj") or man["proj"], P["x00"] + ii * P["dx"], P["y00"] + jj * P["dx"])
    loc = lambda h: (init + timedelta(hours=P["hours"][h], minutes=180)).hour
    return {"run": run, "hours": len(hs), "lat": lat.ravel(), "lon": lon.ravel(), "rain": rain.ravel(),
            "gust": gust.ravel(), "h0": (loc(hs[0]) - 1) % 24, "h1": loc(hs[-1]) or 24}


# ------------------------------------------------------------------ assessment
RAIN_WORDS = [(30, "أمطار غزيرة"), (15, "أمطار متوسطة إلى غزيرة"), (5, "أمطار متوسطة"), (1, "أمطار خفيفة"),
              (0, "رذاذ أو زخات خفيفة متفرقة")]


def rain_word(peak):
    return next(w for t, w in RAIN_WORDS if peak >= t)


def situation(day, sa_dir, state_dir, om=None, log=print):
    om = om or G.OpenMeteo()
    regs = G.tag_towns(G.regions())
    lat, lon, ri, names = G.grid_points(regs, 0.5)
    grid = np.array([n == "" for n in names])
    M = model_days(om, lat, lon, day)
    log(f"report: model days at {len(lat)} points, Open-Meteo weight so far {om.used:.0f}")
    data = {"day": day.isoformat(), "regions": []}
    lines, head = [], []

    # ---- rain
    rain_rows = []
    for k, r in enumerate(regs):
        m_k = ri == k
        g_k = m_k & grid
        per = []
        for m, mname in MODELS:
            pr = M[m]["precipitation_sum"][1]
            if not np.isfinite(pr[g_k]).any():
                continue
            v = np.nan_to_num(pr)
            j = int(np.argmax(np.where(m_k, v, -1)))
            per.append({"m": mname, "mean": float(v[g_k].mean()), "cov": float((v[g_k] >= 1).mean()),
                        "max": float(v[j]), "at": (float(lat[j]), float(lon[j]))})
        if not per:
            continue
        wet = [p for p in per if p["cov"] >= 0.08 or p["max"] >= 5]
        row = {"k": k, "name": r["name"], "mean": float(np.median([p["mean"] for p in per])),
               "cov": float(np.median([p["cov"] for p in per])), "peak": float(np.median([p["max"] for p in per])),
               "top": max(per, key=lambda p: p["max"]), "wet": [p["m"] for p in wet], "n": len(per)}
        rain_rows.append(row)
    rainy = sorted([x for x in rain_rows if len(x["wet"]) >= 2 or (len(x["wet"]) == 1 and x["peak"] >= 5)],
                   key=lambda x: -(x["mean"] + 0.05 * x["peak"]))
    wrf = None
    try:
        wrf = wrf_day(sa_dir, day)
    except Exception as e:
        log(f"report: our Kingdom run unreadable: {e}")
    if rainy:
        parts = []
        for x in rainy[:5]:
            pl, dist = G.nearest_place(*x["top"]["at"], regs[x["k"]])
            near = f"قرب {pl}" if dist <= 45 else "في أنحاء من المنطقة"
            parts.append(f"{x['name']} ({rain_word(x['peak'])}؛ تغطي نحو {num(100 * x['cov'])}٪ من المنطقة، "
                         f"وتصل إلى {num(x['top']['max'])} ملم {near} في النموذج {x['top']['m']})")
        if len(rainy) == 1:
            line = "الأمطار: على منطقة واحدة هي " + parts[0] + "."
        elif len(rainy) <= 5:
            line = "الأمطار، من الأغزر إلى الأقل بمجموعها على المنطقة: " + "، ثم ".join(parts[:-1]) + "، وأقلها " + parts[-1] + "."
        else:
            rest = rainy[5:]
            line = "الأمطار، من الأغزر إلى الأقل بمجموعها على المنطقة: " + "، ثم ".join(parts) + "."
            line += (f" وأقلها {rest[0]['name']}." if len(rest) == 1 else
                     f" وأمطار أقل على {join(x['name'] for x in rest[:-1])}، وأقلها {rest[-1]['name']}.")
        agree = [x["name"] for x in rainy if len(x["wet"]) == x["n"] == 3]
        single = [(x["name"], x["wet"][0]) for x in rainy if len(x["wet"]) == 1]
        notes = []
        if agree:
            notes.append(f"تتفق النماذج الثلاثة على أمطار {join(agree)}")
        if single:
            notes.append("ويراها نموذج واحد فقط على " + join(f"{a} (النموذج {b})" for a, b in single))
        if notes:
            line += " " + "، ".join(notes) + "."
        dry = [x["name"] for x in rain_rows if x not in rainy]
        if dry:
            line += f" ولا أمطار تُذكر على {join(dry)}."
        lines.append(line)
        head.append(f"أمطار على {join(x['name'] for x in rainy[:4])}")
    else:
        top = max(rain_rows, key=lambda x: x["top"]["max"], default=None)
        line = "الأمطار: لا تتوقع النماذج الثلاثة أمطارًا تُذكر على مناطق المملكة"
        if top and top["top"]["max"] >= 1:
            pl, _ = G.nearest_place(*top["top"]["at"], regs[top["k"]])
            line += f"، عدا زخات معزولة قد تصل إلى {num(top['top']['max'])} ملم قرب {pl} في النموذج {top['top']['m']}"
        lines.append(line + ".")
    if wrf is not None:
        wri = G.region_of_points(regs, wrf["lat"], wrf["lon"])
        rows = []
        for k, r in enumerate(regs):
            m_k = wri == k
            if not m_k.any():
                continue
            v = wrf["rain"][m_k]
            j = int(np.argmax(v))
            rows.append((r["name"], float(v.mean()), float((v >= 1).mean()), float(v[j]),
                         float(wrf["lat"][m_k][j]), float(wrf["lon"][m_k][j]), k))
        wet = sorted([x for x in rows if x[2] >= 0.03 or x[3] >= 5], key=lambda x: -(x[1] + 0.05 * x[3]))
        span = f"من الساعة {ar(wrf['h0'])} إلى الساعة {ar(wrf['h1'])}"
        if wet:
            def one(x):
                pl, dist = G.nearest_place(x[4], x[5], regs[x[6]])
                return f"{x[0]} (حتى {num(x[3])} ملم{' قرب ' + pl if dist <= 45 else ''})"
            lines.append(f"ونموذجنا للمملكة بدقة ٩ كم ({span} بتوقيت مكة)، من الأغزر: "
                         + "، ثم ".join(one(x) for x in wet[:5]) + ".")
        else:
            lines.append(f"ونموذجنا للمملكة بدقة ٩ كم ({span} بتوقيت مكة) لا يُظهر أمطارًا تُذكر.")
        data["wrf"] = {"run": wrf["run"], "hours": wrf["hours"]}

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

    srcs = "النموذج الأوروبي (٢٥ كم) والأمريكي جي إف إس والألماني أيكون"
    if wrf is not None:
        rd = date(int(wrf["run"][:4]), int(wrf["run"][4:6]), int(wrf["run"][6:8]))
        srcs += (f"، ونموذجنا للمملكة بدقة ٩ كم (دورة {'الثالثة فجرًا' if wrf['run'][8:10] == '00' else 'الثالثة عصرًا'}"
                 f" يوم {ar_date(rd)})")
    srcs += "، والغبار من خدمة كوبرنيكوس الأوروبية لمراقبة الغلاف الجوي، والمعدلات من إعادة التحليل الأوروبية للفترة ٢٠٠١–٢٠٢٠ في مدن كل منطقة."
    summary = ("أبرز ما يؤثر على طقس المملكة: " + "، و".join(head) + ".") if head else \
        "لا حالة جوية بارزة على المملكة: لا أمطار تُذكر ولا موجة حارة أو باردة ولا غبار مؤثر."
    lines = [summary] + lines + [f"المصادر: {srcs}"]
    log(f"report: today's section done, Open-Meteo weight {om.used:.0f}")
    return {"heading": f"طقس المملكة يوم {ar_date(day)}", "lines": lines, "data": data}
