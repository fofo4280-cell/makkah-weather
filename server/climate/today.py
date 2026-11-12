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


MAKKAH_TOWNS = ["مكة المكرمة", "جدة", "الطائف", "الجموم", "بحرة", "الكامل", "خليص", "رابغ", "الليث", "الهدا", "الشفا"]


def finest_city_rain(dirs, day, towns=MAKKAH_TOWNS):
    """Rain of each town over the Makkah day from the finest grid of our runs that covers each hour (1 km in its
    window, else 3 km), as on the town charts of the map page. Coarser than 3 km is not used here.
    Returns {"towns": {name: {"tot", "peak", "peak_h"}}, "res": {dx: [local hours]}, "h0", "h1"} or None."""
    t_a = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(hours=3)
    t_b = t_a + timedelta(hours=24)
    doms = []
    for root in [d for d in dirs if d and os.path.exists(os.path.join(d, "runs.json"))]:
        for r in json.load(open(os.path.join(root, "runs.json"))).get("runs", []):
            p = os.path.join(root, "runs", r["run"], "manifest.json")
            if not os.path.exists(p):
                continue
            man = json.load(open(p))
            init = datetime.strptime(man["init"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            for dom, d in (man.get("domains") or {}).items():
                P = d.get("points")
                if not P or P["dx"] > 3000 or not os.path.exists(os.path.join(root, "runs", r["run"], P["file"])):
                    continue
                doms.append({"root": root, "run": r["run"], "init": init, "P": P, "proj": d.get("proj") or man["proj"]})
    if not doms:
        return None
    cell = {}          # (domain index, town) -> (i, j) when the town is inside
    for q, c in enumerate(doms):
        for t in towns:
            la, lo = G.PLACE[t]
            x, y = lcc_forward(c["proj"], la, lo)
            i = int(round((float(x) - c["P"]["x00"]) / c["P"]["dx"])); j = int(round((float(y) - c["P"]["y00"]) / c["P"]["dx"]))
            if 1 <= i <= c["P"]["nx"] - 2 and 1 <= j <= c["P"]["ny"] - 2:
                cell[(q, t)] = (i, j)
    # for each hour of the day, the finest domain (then the newest run) that has it
    pick = {}
    for q, c in enumerate(doms):
        for k, h in enumerate(c["P"]["hours"]):
            vt = c["init"] + timedelta(hours=h)
            if k == 0 or not (t_a < vt <= t_b):
                continue
            key = int((vt - t_a).total_seconds() // 3600)           # local hour ending at key
            best = pick.get(key)
            if best is None or (c["P"]["dx"], -c["init"].timestamp()) < (doms[best[0]]["P"]["dx"], -doms[best[0]]["init"].timestamp()):
                pick[key] = (q, k)
    if len(pick) < 6:
        return None
    arrs = {}
    out = {t: {"tot": 0.0, "peak": 0.0, "peak_h": None} for t in towns}
    res = {}
    for key, (q, k) in sorted(pick.items()):
        c = doms[q]
        if q not in arrs:
            P = c["P"]
            raw = np.fromfile(os.path.join(c["root"], "runs", c["run"], P["file"]), np.uint8)
            arrs[q] = raw.reshape(len(P["vars"]), len(P["hours"]), P["ny"], P["nx"])[P["vars"].index("rain1h")]
        res.setdefault(c["P"]["dx"], []).append(key)
        for t in towns:
            if (q, t) not in cell:
                continue
            i, j = cell[(q, t)]
            v = float((arrs[q][k, j, i] / 25.0) ** 2)
            out[t]["tot"] += v
            if v > out[t]["peak"]:
                out[t]["peak"], out[t]["peak_h"] = v, key
    hrs = sorted(pick)
    return {"towns": out, "res": res, "h0": hrs[0] - 1, "h1": hrs[-1]}


def city_line(cr):
    """One Arabic paragraph for Makkah, Jeddah, Taif and the towns around them."""
    def spans(hs):
        hs = sorted(hs); out = []; a = b = hs[0]
        for h in hs[1:]:
            if h == b + 1:
                b = h
            else:
                out.append((a, b)); a = b = h
        out.append((a, b))
        return "، و".join(f"من الساعة {ar(x - 1)} إلى الساعة {ar(y)}" for x, y in out)
    res = "؛ و".join(f"{'١ كم' if dx <= 1500 else '٣ كم'} {spans(hs)}" for dx, hs in sorted(cr["res"].items()))
    wet = sorted([(t, v) for t, v in cr["towns"].items() if v["tot"] >= 0.5], key=lambda x: -x[1]["tot"])
    dry = [t for t, v in cr["towns"].items() if v["tot"] < 0.5]
    txt = f"مكة المكرمة وجدة والطائف وما حولها (من أدق شبكات نموذجنا: {res} بتوقيت مكة): "
    if wet:
        txt += "، ".join(f"{t} {num(v['tot'], 1 if v['tot'] < 10 else 0)} ملم"
                         + (f" أشدها الساعة {ar(v['peak_h'])}" if v["peak"] >= 1 else "") for t, v in wet)
        txt += (f"؛ ولا أمطار تُذكر على {join(dry)}." if dry else ".")
    else:
        txt += f"لا أمطار تُذكر على {join(dry)}."
    return txt


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

    # ---- rain: our own model only, the whole Makkah day, set against the large-scale picture
    import ourmodel as O
    doms, king = [], None
    try:
        doms = O.load(our_dirs, day, log)
        king = O.composite(doms)
    except Exception as e:
        log(f"report: our model runs unreadable: {e!r}")
    env = None
    try:
        env = O.environment(om, lat, lon, day)
    except Exception as e:
        log(f"report: storm environment unavailable: {e!r}")
    rainy, rows = [], []
    if king is None:
        lines.append("الأمطار: لم يكتمل تشغيل نموذجنا الذي يغطي هذا اليوم عند كتابة التقرير، فلا ترتيب للمناطق اليوم.")
    else:
        kri = G.region_of_points(regs, king["lat"], king["lon"])
        for k, r in enumerate(regs):
            m_k = kri == k
            if not m_k.any():
                continue
            d = O.describe(king, m_k)
            d.update(k=k, name=r["name"])
            if d["wet"]:
                j = np.flatnonzero(m_k)[d["jmax"]]
                d["place"] = G.describe(float(king["lat"][j]), float(king["lon"][j]), r)
                pts = ri == k
                d["hail"] = O.hail_level(d, O.fzl_at(env, pts, d["conv_hours"]))
                d["sc"], d["sc_vals"] = O.supercell_level(env, pts, d["conv_hours"])
            rows.append(d)
        rainy = sorted([x for x in rows if x["wet"] and (x["cov"] >= 0.03 or x["max"] >= 5)], key=lambda x: -x["mean"])
        hrs = king["keys"]
        span = ("من منتصف الليل إلى منتصف الليل" if len(hrs) >= 23 else
                f"من الساعة {ar(hrs[0] - 1)} إلى الساعة {ar(hrs[-1])} بتوقيت مكة، وهي الساعات التي يغطيها تشغيل نموذجنا")
        if rainy:
            parts = [f"{x['name']} ({rain_word(x['max'])}، تغطي نحو {num(100 * x['cov'])}٪ من المنطقة، وتصل إلى "
                     f"{num(x['max'])} ملم{' قرب ' + x['place'] if x['place'] else ''})" for x in rainy[:6]]
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
            lines.append("توقيت الأمطار وطابعها: " + "؛ ".join(
                f"{x['name']} {O.timing_word(x)} (ذروته الساعة {ar(x['peak_h'])})، {O.type_word(x)}" for x in rainy[:8]) + ".")
            hail = [x for x in rainy if x.get("hail")]
            sc = [x for x in rainy if x.get("sc")]
            hl = []
            h2 = [x for x in hail if x["hail"] == 2]; h1 = [x for x in hail if x["hail"] == 1]
            if hail:
                t_ = []
                if h2:
                    t_.append("فرص جيدة على " + join(f"{x['name']} (صدى رادار {num(x['zmax'])} ديسيبل الساعة {ar(x['zh'])})" for x in h2))
                if h1:
                    t_.append("فرص واردة على " + join(x["name"] for x in h1))
                hl.append("البَرَد: " + "، و".join(t_))
            if sc:
                s2 = [x for x in sc if x["sc"] == 2]; s1 = [x for x in sc if x["sc"] == 1]
                t_ = []
                if s2:
                    t_.append("فرص متوسطة على " + join(x["name"] for x in s2))
                if s1:
                    t_.append("فرص ضعيفة على " + join(x["name"] for x in s1))
                best = max(sc, key=lambda x: (x["sc"], (x["sc_vals"] or (0, 0))[0] or 0))
                v_ = best["sc_vals"]
                hl.append("الخلايا العملاقة (سوبر سل): " + "، و".join(t_)
                          + (f" (أعلاها على {best['name']}: طاقة الحمل حتى {num(v_[0], -2)} جول/كغ وقص الرياح حتى {num(v_[1])} م/ث)"
                             if v_ and v_[0] and v_[1] else ""))
            lines.append(("؛ و".join(hl) + ".") if hl else "البَرَد والخلايا العملاقة: لا مؤشرات عليها اليوم.")
            head.append(f"أمطار على {join(x['name'] for x in rainy[:4])}")
            if hail:
                head.append(f"فرص بَرَد على {join(x['name'] for x in hail[:3])}")
        else:
            lines.append(f"الأمطار ({span}): لا يُظهر نموذجنا أمطارًا تُذكر على مناطق المملكة.")
        data["rain"] = [{k: v for k, v in x.items() if k in ("name", "mean", "cov", "max", "peak_h", "conv", "zmax", "hail", "sc")}
                        for x in rainy]
        data["our_runs"] = king["used"]
    if st is not None:
        try:
            lines.append(big_picture(st, day, rainy))
        except Exception as e:
            log(f"report: large-scale check failed: {e!r}")
    bp_n = getattr(big_picture, "n", 0)
    try:
        if king is not None and bp_n >= 2:
            sa9 = O.composite([d_ for d_ in doms if d_["dx"] >= 9000 and d_["name"] == "السعودية"])
            al = []
            if sa9 is not None:
                sri = G.region_of_points(regs, sa9["lat"], sa9["lon"])
                for x in rows:
                    if x in rainy:
                        continue
                    a_ = O.aloft(king, kri == x["k"])
                    r9 = float(sa9["rain"][:, sri == x["k"]].sum(0).max()) if (sri == x["k"]).any() else 0.0
                    if (a_ >= 1 and r9 >= 0.5) or (r9 >= 2 and bp_n >= 3):
                        al.append((x["name"], r9, a_ >= 1))
            if al:
                lines.append(stratiform_alert("نموذجنا", al))
    except Exception as e:
        log(f"report: stratiform check failed: {e!r}")
    try:
        makkah = makkah_section(day, doms, env, regs, lat, lon, ri, our_dirs, log, bp_n)
    except Exception as e:
        log(f"report: Makkah region section failed: {e!r}")
        makkah = None

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
                rec.update(dmax=float(mx[j]), lvl=lvl, dcov=cov(200), lcov=cov({3: 1000, 2: 500, 1: 200, 0: 200}[lvl]),
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
            f"{x['name']} ({dword(x['lvl'])} على نحو {num(100 * x['lcov'])}٪ من المنطقة"
            + (f" وغبار عالق على نحو {num(100 * x['dcov'])}٪ منها" if x["lvl"] > 1 and x["dcov"] - x["lcov"] >= 0.1 else "")
            + f"، أشده قرب {x['dat']} نحو الساعة {ar(x['dhour'])} "
            f"بتركيز {num(x['dmax'])} ميكروغرام/م³" + (f"، وهبات رياح حتى {num(x['gust'])} كم/س" if x["gust"] >= 40 else "")
            + ")" for x in dusty[:6]) + ".")
        head.append(f"{'غبار كثيف' if dusty[0]['lvl'] == 3 else 'غبار'} على {join(x['name'] for x in dusty[:3])}")
    if windy:
        lines.append("رياح نشطة قد تثير الأتربة على " + join(f"{x['name']} (هبات حتى {num(x['gust'])} كم/س)" for x in windy) + ".")
    if not dusty and not windy and dust is not None:
        lines.append("الغبار: لا يتوقع نموذج كوبرنيكوس غبارًا مؤثرًا، والرياح في حدودها المعتادة.")
    data["dust"] = [{k: v for k, v in x.items()} for x in dusty]

    srcs = ""
    if king is not None:
        def run_txt(run):
            rd = date(int(run[:4]), int(run[4:6]), int(run[6:8]))
            return f"دورة {'الثالثة فجرًا' if run[8:10] == '00' else 'الثالثة عصرًا'} يوم {ar_date(rd)}"
        srcs += ("الأمطار وطابعها من نموذجنا وحده (" + "، و".join(f"{n} بدقة {r}" for n, r, _ in king["used"])
                 + f"، {run_txt(king['used'][0][2])})، وبيئة الخلايا العملاقة والبرد (طاقة الحمل وقص الرياح ومستوى التجمد) "
                 "من جي إف إس والنموذج الأوروبي؛ ")
    srcs += ("والحرارة والرياح من النموذج الأوروبي والأمريكي جي إف إس والألماني أيكون، والغبار من خدمة كوبرنيكوس "
             "الأوروبية لمراقبة الغلاف الجوي، والمعدلات من إعادة التحليل الأوروبية للفترة ٢٠٠١–٢٠٢٠ في مدن كل منطقة.")
    summary = ("أبرز ما يؤثر على طقس المملكة: " + "، و".join(head) + ".") if head else \
        "لا حالة جوية بارزة على المملكة: لا أمطار تُذكر ولا موجة حارة أو باردة ولا غبار مؤثر."
    lines = [summary] + lines + [f"المصادر: {srcs}"]
    log(f"report: today's section done, Open-Meteo weight {om.used:.0f}")
    return {"heading": f"طقس المملكة يوم {ar_date(day)} من منتصف الليل إلى منتصف الليل", "lines": lines, "data": data,
            "makkah": makkah}


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
    big_picture.n = n
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


def stratiform_alert(what, items):
    """items: (area, 9 km rain, echo aloft in the finer grid)."""
    why = []
    if len(items) == 1:
        n, r, e = items[0]
        if e:
            why.append("صدى سحب ممطرة في الأعلى يتبخر قبل الأرض")
        why.append(f"ونموذج ٩ كم يُنزل عليها أمطارًا خفيفة حتى {num(r, 1)} ملم" if e else f"نموذج ٩ كم يُنزل عليها أمطارًا خفيفة حتى {num(r, 1)} ملم")
    else:
        if any(e for _, _, e in items):
            why.append("صدى سحب ممطرة في الأعلى يتبخر قبل الأرض في " + join(n for n, _, e in items if e))
        why.append(("و" if why else "") + "نموذج ٩ كم يُنزل أمطارًا خفيفة (" + "، ".join(f"{n} حتى {num(r, 1)} ملم" for n, r, _ in items) + ")")
    return (f"تنبيه: احتمال أمطار ديمية خفيفة إلى متوسطة أعلى مما يُظهر {what} على {join(n for n, _, _ in items)}: "
            + "، ".join(why) + "، والصورة الكبرى تعزز الحالة. مثل هذه الأمطار يكثر أن تفوت النماذج حين تكون "
            "الطبقة تحت السحاب فيها أجف من الواقع (كما حدث في الجموم يوم ١٠ نوفمبر).")


# ------------------------------------------------------------------ Makkah region at 3 km
MAKKAH_AREAS = [
    ("جدة والساحل الشمالي (رابغ وخليص)", ["جدة", "رابغ", "خليص"]),
    ("مكة المكرمة وما حولها (الجموم وبحرة والكامل)", ["مكة المكرمة", "الجموم", "بحرة", "الكامل"]),
    ("الطائف والمرتفعات (الهدا والشفا وميسان)", ["الطائف", "الهدا", "الشفا", "ميسان"]),
    ("تهامة الجنوبية (الليث والقنفذة وأضم والعرضيات)", ["الليث", "القنفذة", "أضم", "العرضيات"]),
    ("شرق المنطقة (تربة والخرمة ورنية والمويه وظلم)", ["تربة", "الخرمة", "رنية", "المويه", "ظلم"]),
]


def makkah_section(day, doms, env, regs, glat, glon, gri, our_dirs, log=print, bp_n=0):
    """Makkah region from our 3 km grid (1 km only for the towns paragraph): the region, then five parts of it."""
    import ourmodel as O
    reg = next(r for r in regs if r["id"] == "SA-02")
    k_reg = regs.index(reg)
    head = f"منطقة مكة المكرمة بدقة ٣ كم يوم {ar_date(day)}"
    mk = O.composite([d for d in doms if 2000 <= d["dx"] <= 3500])
    lines = []
    if mk is None:
        lines.append("لم يكتمل تشغيل نموذجنا بدقة ٣ كم الذي يغطي هذا اليوم عند كتابة التقرير.")
        return {"heading": head, "lines": lines}
    inr = G.region_of_points(regs, mk["lat"], mk["lon"]) == k_reg
    if not inr.any():
        return None
    hrs = mk["keys"]
    span = ("من منتصف الليل إلى منتصف الليل" if len(hrs) >= 23 else
            f"من الساعة {ar(hrs[0] - 1)} إلى الساعة {ar(hrs[-1])} بتوقيت مكة، وهي الساعات التي يغطيها تشغيل ٣ كم")
    gpts = gri == k_reg
    d = O.describe(mk, inr)
    if d["wet"]:
        j = np.flatnonzero(inr)[d["jmax"]]
        pl = G.describe(float(mk["lat"][j]), float(mk["lon"][j]), reg)
        d["hail"] = O.hail_level(d, O.fzl_at(env, gpts, d["conv_hours"]))
        sc, scv = O.supercell_level(env, gpts, d["conv_hours"])
        lines.append(f"المنطقة كلها ({span}): " + O.area_text("", d, pl, d["hail"], sc, scv)[2:] + ".")
    else:
        lines.append(f"المنطقة كلها ({span}): لا يُظهر نموذجنا بدقة ٣ كم أمطارًا تُذكر على أي جزء منها.")
    # the five parts: each 3 km cell goes to the nearest of their towns
    towns = [(a, t) for a, ts in MAKKAH_AREAS for t in ts if t in G.PLACE]
    tl = np.array([G.PLACE[t][0] for _, t in towns]); to = np.array([G.PLACE[t][1] for _, t in towns])
    la, lo = mk["lat"][inr], mk["lon"][inr]
    near = np.argmin((la[:, None] - tl[None]) ** 2 + ((lo[:, None] - to[None]) * np.cos(np.radians(21.5))) ** 2, axis=1)
    area_of = np.array([towns[i][0] for i in near])
    gla, glo = glat[gpts], glon[gpts]
    gnear = np.argmin((gla[:, None] - tl[None]) ** 2 + ((glo[:, None] - to[None]) * np.cos(np.radians(21.5))) ** 2, axis=1)
    garea = np.array([towns[i][0] for i in gnear])
    parts, dry, alerts = [], [], []
    sa9 = O.composite([d_ for d_ in doms if d_["dx"] >= 9000 and d_["name"] == "السعودية"])
    for name, ts in MAKKAH_AREAS:
        m = np.zeros(inr.shape, bool); m[np.flatnonzero(inr)[area_of == name]] = True
        if not m.any():
            continue
        dd = O.describe(mk, m)
        if not dd["wet"] or (dd["cov"] < 0.03 and dd["max"] < 5):
            dry.append(name.split(" (")[0])
            if bp_n >= 2 and sa9 is not None:
                a_ = O.aloft(mk, m)
                pm = np.zeros(sa9["lat"].shape, bool)
                s_in = G.region_of_points(regs, sa9["lat"], sa9["lon"]) == k_reg
                if s_in.any():
                    sn = np.argmin((sa9["lat"][s_in, None] - tl[None]) ** 2
                                   + ((sa9["lon"][s_in, None] - to[None]) * np.cos(np.radians(21.5))) ** 2, axis=1)
                    pm[np.flatnonzero(s_in)[np.array([towns[i][0] for i in sn]) == name]] = True
                r9 = float(sa9["rain"][:, pm].sum(0).max()) if pm.any() else 0.0
                if (a_ >= 1 and r9 >= 0.5) or (r9 >= 2 and bp_n >= 3):
                    alerts.append((name.split(" (")[0], r9, a_ >= 1))
            continue
        j = np.flatnonzero(m)[dd["jmax"]]
        pl = G.describe(float(mk["lat"][j]), float(mk["lon"][j]), reg)
        p = np.zeros(gpts.shape, bool); p[np.flatnonzero(gpts)[garea == name]] = True
        hl = O.hail_level(dd, O.fzl_at(env, p, dd["conv_hours"]))
        sc, scv = O.supercell_level(env, p, dd["conv_hours"])
        parts.append((dd["mean"], O.area_text(name, dd, pl, hl, sc, scv)))
    if parts:
        lines += [t + "." for _, t in sorted(parts, key=lambda x: -x[0])]
    if dry and parts:
        lines.append(f"ولا أمطار تُذكر على {join(dry)}.")
    if alerts:
        lines.append(stratiform_alert("نموذج ٣ كم", alerts))
    try:
        cr = finest_city_rain(our_dirs, day)
        if cr:
            lines.append(city_line(cr))
    except Exception as e:
        log(f"report: town rain from the finest grids failed: {e!r}")
    lines.append(f"المصدر: نموذجنا بدقة ٣ كم ({join(f'{n} بدقة {r}' for n, r, _ in mk['used'])})، وبيئة الخلايا العملاقة والبرد "
                 "من جي إف إس والنموذج الأوروبي.")
    return {"heading": head, "lines": lines}
