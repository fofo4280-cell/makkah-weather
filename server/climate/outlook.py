"""Signs of a new rain wave over the Kingdom in the next 15 and 45 days, each with where it was read from.

Sources:
  - GFS (0.25 degree), rain of each Makkah day for 15 days, region by region (from daily.py).
  - ECMWF extended range (EC46, 51 members, 46 days) through Open-Meteo: weekly rain against the model's
    own climate (anomaly, share of members above normal, extreme forecast index), daily rain of each member,
    and weekly temperature anomaly, at two or three towns per region.
  - The MJO: the GFS projection of the RMM index for 15 days (daily.py), carried on at its own speed as an
    inference only (low confidence), and the moisture surges, troughs and polar index already in the report.
"""
import math, warnings
from datetime import date, timedelta

import numpy as np

import sa_geo as G
from sa_geo import ar, num, ar_date, ar_span, join

WET_PHASES = {7, 8, 1, 2}


# ------------------------------------------------------------------ GFS, day by day
def gfs_days(apcp, lat, lon, day0, regs):
    """apcp: list of accumulated rain grids (mm since the start of the run) at 00 Makkah of day0, day0+1, ...
    Returns [{d, regions: [{k, name, mean, cov, max, at}]}] for each day."""
    la2, lo2 = np.meshgrid(lat, lon, indexing="ij")
    sel = (la2 >= 15.5) & (la2 <= 33) & (lo2 >= 34) & (lo2 <= 56)
    fl, fo = la2[sel], lo2[sel]
    ri = G.region_of_points(regs, fl, fo)
    out = []
    for k in range(1, len(apcp)):
        v = np.clip((apcp[k] - apcp[k - 1])[sel], 0, None)
        rows = []
        for j, r in enumerate(regs):
            m = ri == j
            if not m.any():
                continue
            i = int(np.argmax(np.where(m, v, -1)))
            rows.append({"k": j, "name": r["name"], "mean": float(v[m].mean()), "cov": float((v[m] >= 1).mean()),
                         "max": float(v[i]), "at": G.nearest_place(fl[i], fo[i], r)[0]})
        out.append({"d": day0 + timedelta(days=k - 1), "regions": rows})
    return out


def episodes(days, first=0):
    """Runs of days on which some region gets real rain (gaps of one dry day are bridged)."""
    wet = []
    for x in days:
        rr = [r for r in x["regions"] if r["mean"] >= 0.5 or r["cov"] >= 0.1 or r["max"] >= 10]
        wet.append(rr)
    eps, cur, gap = [], None, 0
    for i, rr in enumerate(wet):
        if i < first:
            continue
        if rr:
            if cur is None:
                cur = {"a": i, "b": i, "regs": {}}
            cur["b"], gap = i, 0
            for r in rr:
                e = cur["regs"].setdefault(r["name"], {"sum": 0.0, "max": 0.0, "at": "", "d": None})
                e["sum"] += r["mean"]
                if r["max"] > e["max"]:
                    e.update(max=r["max"], at=r["at"], d=days[i]["d"])
        elif cur is not None:
            gap += 1
            if gap > 1:
                eps.append(cur); cur = None
    if cur is not None:
        eps.append(cur)
    for e in eps:
        e["da"], e["db"] = days[e["a"]]["d"], days[e["b"]]["d"]
    return eps


# ------------------------------------------------------------------ ECMWF extended range
def ec46(om, regs):
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    towns = {r["id"]: [t for t in G.NORMAL_TOWNS[r["id"]]] for r in regs}
    flat = [t for r in regs for t in towns[r["id"]]]
    lat = [G.PLACE[t][0] for t in flat]; lon = [G.PLACE[t][1] for t in flat]
    wk = om.get(G.SEASONAL, {"weekly": "precipitation_mean,precipitation_anomaly,precipitation_anomaly_gt0,"
                             "precipitation_efi,temperature_2m_anomaly", "models": "ecmwf_ec46"}, lat, lon, weight=1)
    dy = om.get(G.SEASONAL, {"daily": "precipitation_sum", "models": "ecmwf_ec46", "forecast_days": 46},
                lat, lon, weight=5.1 * 46 / 14)
    by = dict(zip(flat, zip(wk, dy)))
    weeks = [date.fromisoformat(s) for s in wk[0]["weekly"]["time"]]
    days = [date.fromisoformat(s) for s in dy[0]["daily"]["time"]]
    out = {"weeks": [], "days": days, "regions": []}
    for r in regs:
        W = {v: [] for v in ("precipitation_mean", "precipitation_anomaly", "precipitation_anomaly_gt0",
                             "precipitation_efi", "temperature_2m_anomaly")}
        mem = []
        for t in towns[r["id"]]:
            w, d = by[t]
            for v in W:
                W[v].append([np.nan if x is None else x for x in w["weekly"][v]])
            dd = d["daily"]
            ms = sorted(k for k in dd if k.startswith("precipitation_sum_member"))
            mem.append([[np.nan if x is None else x for x in dd[k]] for k in ms])
        reg = {"name": r["name"], "id": r["id"]}
        for v, a in W.items():
            reg[v] = np.nanmean(np.array(a, float), axis=0)
        m = np.nanmean(np.array(mem, float), axis=0)          # members x days, region average of its towns
        reg["p1"] = np.nanmean(m >= 1, axis=0)                 # share of members with 1 mm or more each day
        reg["wk_p5"] = np.array([np.nanmean(np.nansum(m[:, (np.array(days) >= w0) & (np.array(days) < w0 + timedelta(days=7))], 1) >= 5)
                                 for w0 in weeks])
        out["regions"].append(reg)
    out["weeks"] = weeks
    return out


def ec_signals(ec, day0):
    """Wet weeks: per region, weeks where 60 percent of the members or more see more rain than the model's
    normal and the mean excess is at least 1 mm, or the extreme forecast index reaches 0.5, or 40 percent of the
    members give the region 5 mm or more in the week while at least half are above normal."""
    sig = []
    for w, w0 in enumerate(ec["weeks"]):
        if w0 + timedelta(days=6) < day0:
            continue
        regs = []
        for r in ec["regions"]:
            p, a, e, p5 = (r["precipitation_anomaly_gt0"][w], r["precipitation_anomaly"][w],
                           r["precipitation_efi"][w], r["wk_p5"][w] if w < len(r["wk_p5"]) else np.nan)
            if not np.isfinite(p):
                continue
            if (p >= 60 and a >= 1) or (np.isfinite(e) and e >= 0.5) or (np.isfinite(p5) and p5 >= 0.4 and p >= 50):
                dd = [i for i, d in enumerate(ec["days"]) if w0 <= d < w0 + timedelta(days=7)]
                peak = ec["days"][max(dd, key=lambda i: r["p1"][i])] if dd else w0
                regs.append({"name": r["name"], "p": p, "a": a, "e": e, "p5": p5, "peak": peak,
                             "strong": (p >= 70 and a >= 3) or (np.isfinite(e) and e >= 0.7)})
        if regs:
            sig.append({"w0": w0, "w1": w0 + timedelta(days=6), "regs": sorted(regs, key=lambda x: -x["p"])})
    return sig


# ------------------------------------------------------------------ MJO
def mjo_window(st, today):
    """When the MJO would reach the phases that favour rain over the Kingdom (7, 8, 1, 2 in November-April):
    from the 15-day GFS projection, then carried on at the speed it has in that projection (an inference)."""
    fc = st.get("rmm_fc") or []
    if not st.get("wet_season") or len(fc) < 5:
        return None
    in_fc = [x for x in fc if x["phase"] in WET_PHASES and x["amp"] >= 1]
    if in_fc:
        return {"kind": "forecast", "d": date.fromisoformat(in_fc[0]["d"]), "phase": in_fc[0]["phase"],
                "amp": in_fc[0]["amp"]}
    ang = np.unwrap([math.atan2(x["r2"], x["r1"]) for x in fc])
    w = math.degrees(ang[-1] - ang[0]) / max(1, len(fc) - 1)     # degrees per day, eastward positive
    last = fc[-1]
    if last["amp"] < 1 or not (4 <= w <= 15):
        return {"kind": "none", "speed": w, "amp": last["amp"], "phase": last["phase"]}
    th = math.degrees(math.atan2(last["r2"], last["r1"]))
    need = (90 - th) % 360                                         # phase 7 starts at 90 degrees
    days = need / w
    d = date.fromisoformat(last["d"]) + timedelta(days=round(days))
    if (d - today).days > 45:
        return {"kind": "late", "d": d, "speed": w, "period": 360 / w}
    return {"kind": "inferred", "d": d, "speed": w, "period": 360 / w, "phase": last["phase"], "amp": last["amp"]}


# ------------------------------------------------------------------ text
def outlook(st, day0, gfs, ec, log=print):
    lines = []
    windows = []          # (source, first day, last day) of each sign of a new rain wave
    today = day0

    # 1. GFS, 15 days
    if gfs:
        eps = episodes(gfs, first=1)
        if eps:
            for e in eps[:3]:
                top = sorted(e["regs"].items(), key=lambda kv: -kv[1]["sum"])
                pk_name, pk = max(e["regs"].items(), key=lambda kv: kv[1]["max"])
                cont = e["a"] == 1 and any(r["mean"] >= 0.5 or r["cov"] >= 0.1 for r in gfs[0]["regions"])
                lines.append(
                    f"خلال ١٥ يومًا (قراءة من جي إف إس، أمطار كل يوم على مناطق المملكة بدقة ربع درجة): "
                    f"{'استمرار الحالة الحالية' if cont else 'حالة مطرية'} {ar_span(e['da'], e['db'])} على "
                    f"{join(n for n, _ in top[:5])}، أغزرها على {pk_name} حتى {num(pk['max'])} ملم قرب {pk['at']} "
                    f"يوم {ar_date(pk['d'])}" + ("؛ والثقة فيه أقل لأنه بعد اليوم السابع." if (e["da"] - today).days >= 7 else "."))
                if not cont:
                    windows.append(("جي إف إس", e["da"], e["db"]))
        else:
            mx = max((r for x in gfs[1:] for r in x["regions"]), key=lambda r: r["max"], default=None)
            ln = "خلال ١٥ يومًا (قراءة من جي إف إس): لا تظهر حالة مطرية واسعة على المملكة"
            if mx and mx["max"] >= 2:
                ln += f"، وأعلى ما يظهر زخات محلية حتى {num(mx['max'])} ملم قرب {mx['at']}"
            lines.append(ln + ".")

    # 2. ECMWF extended range, 46 days
    if ec:
        sig = ec_signals(ec, today)
        end = ec["days"][-1] if ec["days"] else today + timedelta(days=45)
        near = [s for s in sig if (s["w1"] - today).days <= 15]
        far = [s for s in sig if (s["w1"] - today).days > 15]

        def wline(s):
            rs = s["regs"]
            best = rs[0]
            txt = (f"أسبوع {ar_span(s['w0'], s['w1'])}: إشارة "
                   f"{'قوية' if any(r['strong'] for r in rs) else 'متوسطة'} على {join(r['name'] for r in rs[:6])}؛ "
                   f"{num(best['p'])}٪ من الأعضاء يرون أمطارًا فوق معدل النموذج على {best['name']}")
            if best["a"] >= 0.5:
                txt += f" بزيادة نحو {num(best['a'], 1)} ملم عن معدل الأسبوع"
            if np.isfinite(best["e"]) and best["e"] >= 0.3:
                txt += f"، ومؤشر التطرف {num(best['e'], 1)}"
            txt += f"، وأعلى احتمال يومي للمطر يوم {ar_date(best['peak'])}"
            return txt
        if near:
            lines.append("خلال الأسبوعين القادمين (قراءة من النموذج الأوروبي الممتد): " + "؛ و".join(wline(s) for s in near) + ".")
            for s in near:
                windows.append(("النموذج الأوروبي الممتد", s["w0"], s["w1"]))
        if far:
            lines.append("من ١٥ إلى ٤٥ يومًا (قراءة من النموذج الأوروبي الممتد لستة وأربعين يومًا، ٥١ عضوًا، "
                         "بمقارنة أمطار كل أسبوع بمعدل النموذج نفسه): ملامح موجة مطرية جديدة في "
                         + "؛ وفي ".join(wline(s) for s in far) + ".")
            for s in far:
                windows.append(("النموذج الأوروبي الممتد", s["w0"], s["w1"]))
        else:
            top = max(((r["precipitation_anomaly_gt0"][w], r["name"], ec["weeks"][w]) for r in ec["regions"]
                       for w in range(len(ec["weeks"])) if (ec["weeks"][w] - today).days >= 15
                       and np.isfinite(r["precipitation_anomaly_gt0"][w])), default=None)
            ln = (f"من ١٥ إلى ٤٥ يومًا (قراءة من النموذج الأوروبي الممتد لستة وأربعين يومًا): لا تظهر ملامح موجة "
                  f"مطرية جديدة حتى {ar_date(end)}")
            if top:
                ln += f"؛ أعلى نسبة أعضاء ترى أمطارًا فوق المعدل {num(top[0])}٪ على {top[1]} في أسبوع {ar_date(top[2])}"
            lines.append(ln + ".")
        cold = [(r["name"], r["temperature_2m_anomaly"][w], ec["weeks"][w]) for r in ec["regions"]
                for w in range(len(ec["weeks"])) if np.isfinite(r["temperature_2m_anomaly"][w])
                and r["temperature_2m_anomaly"][w] <= -2 and ec["weeks"][w] >= today - timedelta(days=6)]
        if cold:
            first = min(c[2] for c in cold)
            names = sorted({c[0] for c in cold if c[2] == first})
            lines.append(f"والنموذج الأوروبي الممتد يرى أسبوعًا أبرد من معدله بدرجتين فأكثر على {join(names)} "
                         f"ابتداءً من {ar_date(first)}.")

    if not gfs and not ec:
        lines.append("تعذر اليوم جلب توقع جي إف إس اليومي والنموذج الأوروبي الممتد، فهذا الجزء مبني على التذبذب المداري وحده.")

    # 3. MJO
    mw = mjo_window(st, today)
    if mw and mw["kind"] == "forecast":
        lines.append(f"التذبذب المداري (قراءة من إسقاط جي إف إس لخمسة عشر يومًا): يدخل الطور {ar(mw['phase'])} الرطب "
                     f"للمملكة بشدة {num(mw['amp'], 1)} يوم {ar_date(mw['d'])}، وهذا يدعم أي حالة مطرية في الأيام التالية له.")
        windows.append(("التذبذب المداري", mw["d"], mw["d"] + timedelta(days=10)))
    elif mw and mw["kind"] == "inferred":
        lines.append(f"التذبذب المداري (استنتاج): في آخر إسقاط جي إف إس يدور التذبذب شرقًا نحو {num(mw['speed'])} درجات "
                     f"في اليوم (دورة كاملة في نحو {num(mw['period'])} يومًا)، فإن حافظ على سرعته وشدته يصل إلى الأطوار "
                     f"الرطبة للمملكة (٧ و٨ و١ و٢) قرابة {ar_date(mw['d'])}، بهامش أسبوع تقريبًا. "
                     f"هذا استنتاج من سرعة الدوران لا توقع، وثقته منخفضة.")
        windows.append(("التذبذب المداري", mw["d"] - timedelta(days=5), mw["d"] + timedelta(days=10)))
    elif mw and mw["kind"] == "none":
        lines.append(f"التذبذب المداري: {'ضعيف' if mw['amp'] < 1 else 'لا يدور بانتظام'} في آخر إسقاط جي إف إس، "
                     "فلا يمكن الاستنتاج منه لما بعد خمسة عشر يومًا.")

    # 4. what agrees with what, for the coming fifteen days and for days 16 to 45: the days on which the
    #    most sources see a rain wave
    windows = [w for w in windows if w[2] > today + timedelta(days=1)]
    summary = []
    for k0, k1, label in ((2, 15, "خلال ١٥ يومًا"), (16, 46, "من ١٥ إلى ٤٥ يومًا")):
        cnt = []
        for k in range(k0, k1 + 1):
            d = today + timedelta(days=k)
            cnt.append((d, {s for s, a, b in windows if a <= d <= b}))
        top = max(len(c[1]) for c in cnt)
        if top == 0:
            summary.append(f"{label} لا ملامح لموجة مطرية جديدة في أي من المصادر")
            continue
        run = []
        for d, s_ in cnt:
            if len(s_) == top:
                run.append((d, s_))
            elif run:
                break
        a, b, src = run[0][0], run[-1][0], sorted(run[0][1])
        if top >= 2:
            summary.append(f"{label} تتفق إشارات {join(src)} على موجة مطرية {ar_span(a, b)}، "
                           f"والثقة {'متوسطة إلى جيدة' if top >= 3 else 'متوسطة'}")
        else:
            summary.append(f"{label} إشارة لموجة مطرية {ar_span(a, b)} من {src[0]} وحده، "
                           "ولا يؤكدها مصدر آخر في الوقت نفسه، فالثقة منخفضة")
    lines.append("الخلاصة: " + "؛ و".join(summary) + ". وتتضح المناطق والكميات حين تدخل الموجة في مدى النماذج "
                 "عالية الدقة، ويُحدَّث هذا الجزء كل يوم.")
    return {"heading": "ملامح موجة مطرية جديدة (١٥ و٤٥ يومًا)", "lines": lines}
