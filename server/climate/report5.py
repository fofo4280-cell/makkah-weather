"""The short published nightly report (Fahad 28 Nov 2026, «الدور: كبير المحللين الجويين والمحرر العلمي لمنظومة Fahad
AlEissa»). It answers two questions only: where and when it rains today and from what system, and when the nearest
fertile wave comes, where, how strong, how wide and how much. Order (fixed, nothing else is published):

  ١ توقعات الأمطار اليوم     a title naming the case, a summary of three lines at most, one table of the rainy places
                              only (region | towns and villages | timing | nature and intensity | system)
  ٢ أقرب موجة خصب            dates and the timing of each stage, the class, only the drivers that act, strength /5 with
                              its grade, the core apart from the spread, spread %, favoured and heavy areas, confidence
                              in timing / place / intensity / spread; one sentence on a change from the last run, only
                              when there is one
  ٣ خرائط الأمطار التراكمية   OUR reading, never model rain (Fahad 28 Nov 2026, 04:07): the rain-making index of the big
                              picture day by day (refwave), accumulated as the area reached: day 1, to day 2, to day 3 or
                              the wave's end, the whole wave beside the reference wave; strength out of 100, no mm
  ٤ ما قد يغير التوقع        one line: the factor that would change the call

The full analysis (report4: ten sections, the hourly reading, the whole-Kingdom sweep, model roles, the twelve-check
auditor) still runs every night, internally: it is saved to reports/analysis_YYYYMMDD.json and its auditor's
findings to status["analysis_check"]; it is not published. The today table and the wave call come from the
ingredients reading (report4.read), and so do the maps (qpf.py, model rain, is kept but no longer called). reportcheck.check5 audits this layout.
"""
import json
import os
import re
from datetime import date, timedelta

import report2 as R2
from report2 import ar, jl, sec, ar_date

LAYOUT = 5
HEAD = ("توقعات الأمطار اليوم", "أقرب موجة خصب", "خرائط الأمطار التراكمية", "ما قد يغير التوقع")
D = tuple(ar(k) for k in range(1, 5))
MAX_WORDS = 700
# the system classes of the charter
T_LOCAL, T_TROP, T_TROUGH, T_MIX, T_TERR, T_SEA = ("حمل حراري محلي", "نشاط مداري ورطوبي", "نظام أخدودي",
                                                  "نظام مختلط (مداري وأخدودي)", "حمل حراري تضاريسي", "خلايا بحرية")
# the sweep zones (troughreach.ZONES) -> administrative region, for the table
ZONE_REG = {"sea_n": "البحر الأحمر", "sea_m": "البحر الأحمر", "sea_s": "البحر الأحمر", "c_tabuk": "تبوك",
            "c_madinah": "المدينة المنورة", "jeddah_makkah": "مكة المكرمة", "taif": "مكة المكرمة", "qunf": "مكة المكرمة",
            "madinah": "المدينة المنورة", "khaybar": "المدينة المنورة", "tabuk": "تبوك", "duba": "تبوك", "tayma": "تبوك",
            "jouf": "الجوف", "nb": "الحدود الشمالية", "hail": "حائل", "qassim": "القصيم", "riyadh": "الرياض",
            "dawasir": "الرياض", "kharj": "الرياض", "majmaah": "الرياض", "eastern": "الشرقية", "ahsa": "الشرقية",
            "gulf": "الشرقية", "hafr": "الشرقية", "asir": "عسير", "bisha": "عسير", "jazan": "جازان", "najran": "نجران",
            "sharurah": "نجران"}
SEA_REG = {"tb": "تبوك", "md": "المدينة المنورة", "mk": "مكة المكرمة", "as": "عسير", "jz": "جازان", "gulf": "الشرقية"}
PROB = {"ضعيفة": "محتملة", "متوسطة": "محتملة", "مرجحة": "مرجحة", "قوية": "متوقعة"}
TIER = {"heavy": "غزيرة", "moderate": "متوسطة", "light": "خفيفة"}
SEA_W = {1: "محتملة", 2: "مرجحة", 3: "مرجحة وقد تكون غزيرة"}


def words(t):
    return len(re.findall(r"[\w٪°]+", t))


def report_words(rep):
    n = 0
    for s in rep.get("sections") or []:
        n += words(s.get("heading") or "")
        for b in s.get("blocks") or []:
            for k in ("p", "h", "note"):
                if isinstance(b.get(k), str):
                    n += words(b[k])
            if isinstance(b.get("ul"), list):
                n += sum(words(x) for x in b["ul"])
            if "table" in b:
                n += sum(words(str(x)) for x in b["table"]["head"])
                n += sum(words(str(x)) for r in b["table"]["rows"] for x in r)
    return n


# ------------------------------------------------------------------ 1. today
def _system(cause, r, C):
    if cause.startswith("صعود واسع"):
        return T_TROP
    if cause.startswith("تبريد علوي"):
        return T_TROUGH
    if "ينحدر" in cause:
        base = T_LOCAL
    else:
        base = T_TERR
    W = C.get("W") or {}
    if r.get("trough") and not r.get("cool_weak") and (W.get("trough") or r["name"] in (W.get("falls") or {})):
        return base + " يسنده أخدود"
    return base


def _when(cause, r, C):
    import report4 as R4
    if ("يصعد الحافة" in cause or cause.startswith("التقاء الرياح")) and C["trigw"].get(r["name"]):
        return C["trigw"][r["name"]]
    return R4._time_of(cause)


def today_rows(C):
    """the rows of the today table: one per region and system, places never repeated"""
    import seacell
    import timing
    rows, used, named_regs = [], set(), set()
    for r in C["rows"]:
        if r.get("vague"):
            continue
        prob = PROB.get(r["level"], "محتملة")
        grp = {}
        for tier in ("heavy", "moderate", "light"):
            for p in r["row"][tier]:
                if p in used:
                    continue
                cause = r["why"].get(p) or ""
                sy = _system(cause, r, C)
                nat = ("مطر خفيف متواصل " + prob if sy == T_TROP else
                       f"زخات {'رعدية ' if tier != 'light' else ''}{TIER[tier]} {prob}")
                key = (sy, _when(cause, r, C), nat)
                grp.setdefault(key, []).append(p)
                used.add(p)
        for (sy, wh, nat), ps in grp.items():
            rows.append([r["name"], "، ".join(ps), wh, nat, sy])
            named_regs.add(r["name"])
    # tonight's sea cells (from nine at night): one row for the whole coast, north to south
    s0 = C.get("sea0")
    if s0 and s0.get("times"):
        lv = seacell.levels(s0)
        ks = [k for k, *_ in seacell.STRETCHES if lv.get(k, 0) >= 1 and seacell.SHORT[k] not in used]
        if ks:
            mx = max(lv[k] for k in ks)
            pl = [seacell.SHORT[k] for k in ks]
            used.update(pl)
            t = "، ".join(pl)
            if s0.get("plain", 0) >= seacell.PLAIN_MIN:
                t += "، وقد تبلغ مكة والجموم"
            reg = "ساحل الخليج" if ks == ["gulf"] else "البحر الأحمر وسواحله"
            rows.append([reg, t, "من التاسعة ليلًا حتى الفجر", "زخات رعدية " + SEA_W[mx], T_SEA])
    # zones of the hourly sweep with rain ingredients (moisture and ascent met) not named above
    try:
        R = timing.runs(C["st"].get("timing"), C["day0"])
    except Exception:  # noqa: BLE001
        R = {}
    import troughreach as TR
    for k, x in sorted(R.items(), key=lambda kv: -kv[1]["lv"]):
        reg = ZONE_REG.get(k, "")
        nm = TR.NAME[k]
        if k.startswith("sea_") or reg in named_regs or any(nm in str(r_[1]) for r_ in rows):
            continue
        if any(s in nm for s in used):
            continue
        wh = "، ثم ".join(timing.ep_word(e) for e in x["eps"])
        nat = "زخات رعدية محتملة" if x["lv"] >= 2 else "مطر خفيف محتمل"
        sy = T_TROP if x["lv"] == 1 else (T_MIX if C["kind"][0] == "مدارية أخدودية" and not C.get("no_trough")
                                          else T_LOCAL)
        rows.append([reg, nm, wh, nat, sy])
        used.add(nm)
    return rows


def _title(rows, C):
    if not rows:
        return "لا مؤشرات مطر فعلية اليوم على المملكة"
    sys_ = list(dict.fromkeys(r[4].split(" يسنده")[0] for r in rows))
    regs = list(dict.fromkeys(r[0] for r in rows if r[4] != T_SEA))
    t = sys_[0] + (f" على {jl(regs[:3])}" if regs else "")
    if T_SEA in sys_ and sys_[0] != T_SEA:
        t += "، وخلايا بحرية ليلًا"
    return t


def s_today(C):
    import bigreport as BR
    rows = today_rows(C)
    C["today_rows"] = rows
    B = [{"h": _title(rows, C)}]
    if rows:
        land = [r for r in rows if r[4] != T_SEA]
        sea = [r for r in rows if r[4] == T_SEA]
        heavy = any("متوسطة" in r[3] or "غزيرة" in r[3] for r in land)
        t1 = (f"المطر اليوم {('زخات رعدية متوسطة في أقواها' if heavy else 'زخات خفيفة متفرقة')} "
              f"على {jl(list(dict.fromkeys(r[0] for r in land))[:4])}" if land else "لا مطر على اليابسة نهارًا")
        mech = list(dict.fromkeys(r[4].split(" يسنده")[0] for r in land))
        if mech:
            t1 += f"، مصدرها {jl(mech[:2])}"
        t2 = f"وانتشارها {C['band']}، وقوة الحالة {BR.grade(C['ws'])} ({R2.n1(C['ws'])} من ٥)."
        t3 = (f"ومن التاسعة ليلًا خلايا بحرية {sea[0][3].removeprefix('زخات رعدية ')} على السواحل الغربية، تمهّد للموجة."
              if sea and C.get("nw") and (C["nw"]["start"] - C["day0"]).days <= 1 else
              (f"ومن التاسعة ليلًا خلايا بحرية {sea[0][3].removeprefix('زخات رعدية ')} على السواحل." if sea else ""))
        B.append({"p": " ".join(x for x in (t1 + ".", t2, t3) if x)})
        B.append({"table": {"head": ["المنطقة", "المدن والمحافظات والقرى", "التوقيت", "طبيعة الهطول وشدته",
                                     "نوع النظام"], "rows": rows}})
    else:
        B.append({"p": "لا تجتمع الرطوبة والرفع على أي منطقة اليوم، فلا يُتوقع مطر يُذكر."})
    return sec(HEAD[0], "today", B)


# ------------------------------------------------------------------ 2. the nearest fertile wave
def _drivers(w, C):
    out = []
    for p in w.get("pro") or []:
        p = re.sub(r" \([^)]*\)", "", p)
        if p.startswith(("أخدود", "مد رطوبي", "التذبذب المداري", "عائلة روسبي", "موجة كلفن", "نهر")):
            out.append(p)
    ws = _sea_core(C)
    if ws:   # second, after the trough: it is the wave's core
        out.insert(min(1, len(out)), f"التقاء الرياح والرفع البحري ليلًا فوق البحر الأحمر: خلايا بحرية {ws['word']} {ws['where']}")
    return out[:5]


def _sea_core(C):
    """{best level, word, where (stretches), heavy (names), path} of the sea cells over the wave's nights, or None"""
    import seacell
    import report4 as R4
    w = C.get("nw")
    if not w:
        return None
    d0, d1 = (w["start"] - timedelta(days=1)).isoformat(), w["end"].isoformat()
    best, path = {}, []
    for r in C["st"].get("seacell") or []:
        if d0 <= r["d"] <= d1 and r.get("times"):
            for k, v in seacell.levels(r).items():
                if v >= 2:
                    best[k] = max(best.get(k, 0), v)
            path += [p for p in r.get("path") or [] if p not in path]
    if not best:
        return None
    order = [k for k, *_ in seacell.STRETCHES]
    mx = max(best.values())
    top = [k for k in order if best.get(k) == mx]
    return {"lv": mx, "word": SEA_W[mx], "where": R4._runs(top, order), "heavy": [seacell.SHORT[k] for k in top] if mx >= 3 else [],
            "path": [seacell.INLAND[k][0] for k in path]}


def _stages(C, w):
    """one clause per day of the wave, only what is new that day: the sea cells of the night before (their strongest
    level), the land zones where the ingredients meet for the first time in the wave, the hour they peak (timing.py)"""
    import timing
    import troughreach as TR
    import seacell
    import report4 as R4
    T = C["st"].get("timing")
    order = [k for k, *_ in seacell.STRETCHES]
    out, seen, sea_seen = [], set(), {}
    d = w["start"]
    while d <= w["end"]:
        R = timing.runs(T, d)
        land = [k for k, x in R.items() if x["lv"] >= 2 and not k.startswith("sea_")]
        new = [k for k in land if k not in seen]
        sea_r = next((r for r in C["st"].get("seacell") or [] if r["d"] == (d - timedelta(days=1)).isoformat()), None)
        lv = seacell.levels(sea_r) if sea_r and sea_r.get("times") else {}
        up = {k: v for k, v in lv.items() if v >= 2 and v > sea_seen.get(k, 0)}
        parts = []
        if up:
            mx = max(up.values())
            parts.append(f"خلايا بحرية {SEA_W[mx]} {R4._runs([k for k in order if up.get(k) == mx], order)} من الليلة السابقة")
        if new:
            pk = max(new, key=lambda k: R[k]["cape"])
            parts.append(("زخات على " if not seen else "وتتسع الزخات إلى ") + jl([TR.NAME[k] for k in new][:4])
                         + (" وغيرها" if len(new) > 4 else "")
                         + f" أشدها {timing.HOUR_W[R[pk]['pk']]}")
        elif land:
            parts.append(f"يستمر النشاط على {ar(len(land))} منطقة")
        if parts:
            out.append(f"{ar_date(d)}: " + "، ".join(parts).replace("، وتتسع", "، وتتسع").replace("، زخات", "، وزخات"))
        seen |= set(land)
        for k, v in lv.items():
            sea_seen[k] = max(sea_seen.get(k, 0), v)
        d += timedelta(days=1)
    return out


def s_wave(C):
    import bigreport as BR
    import report3 as R3
    import report4 as R4
    w = C.get("nw")
    if not w:
        return sec(HEAD[1], "wave", [{"p": "لا تظهر في توقع الليلة موجة مطرية واسعة على المملكة خلال الأيام الخمسة عشر القادمة."}])
    B = []
    d0 = C["day0"]
    t = ("الموعد: " + ("بدأت " if w["start"] < d0 else "تبدأ ") + R3.rel_day(max(w["start"], d0), d0)
         + (f" وتنتهي {ar_date(w['end'])}" if w["end"] != max(w["start"], d0) else " وتنتهي في يومها"))
    try:
        import timing
        b_ = timing.busiest(C["st"].get("timing"), w["start"], w["end"])
    except Exception as e:  # noqa: BLE001
        print("report5: busiest hour failed:", repr(e), flush=True)
        b_ = None
    t += ("، وذروتها في يومها الأخير" if w["peak"] == w["end"] and w["end"] != w["start"] else f"، وذروتها {ar_date(w['peak'])}")
    if b_ and b_[0] == w["peak"].isoformat():
        t += f" نحو {timing.HOUR_W[b_[1]]}"
    elif b_:
        t += f"، وأوسع ساعاتها {timing.HOUR_W[b_[1]]} {ar_date(date.fromisoformat(b_[0]))}"
    B.append({"p": t + "."})
    st_ = _stages(C, w)
    if st_:
        B.append({"ul": st_})
    B.append({"p": f"التصنيف: موجة {R4.KIND[w['kind']]}."})
    dr = _drivers(w, C)
    if dr:
        B.append({"h": "مصادر قوتها"})
        B.append({"ul": dr})
    sc = _sea_core(C)
    core = ("قوي محليًا" if (sc and sc["lv"] >= 3) else "متوسط" if (sc and sc["lv"] >= 2) or w["top"] >= 2.6 else "ضعيف")
    rows_c, _why = R4.conf_rows(C)
    cf = next((r for r in rows_c if r[0] == "الموجة القادمة"), None)
    heavy = []
    if sc and sc["heavy"]:
        heavy.append("البحر والساحل " + sc["where"].removeprefix("على "))
        if sc["path"]:
            heavy.append(f"وقد تمتد خلاياها إلى {jl(sc['path'][:2])}")
    fav = [x for x in w.get("regions") or [] if not (heavy and x.startswith("البحر والساحل"))][:6]
    tab = [["القوة", f"{R2.n1(w['top'])} من ٥ بالمقياس التشغيلي للمنظومة"],
           ["تصنيف الشدة", BR.grade(w["top"])],
           ["قوة القلب", core + (f" ({sc['where'].removeprefix('على ')})" if sc and sc["lv"] >= 3 else "")],
           ["الانتشار", f"{R2.cover_pct(w.get('cover') or 0)} من مساحة المملكة في يوم الذروة"],
           ["الأوفر حظًا", jl(fav)],
           ["الغزير المحتمل", " ".join(heavy) if heavy else "لا تظهر مؤشرات هطول غزير"]]
    if cf:
        tab.append(["الثقة", f"في التوقيت {cf[1]}، وفي المكان {cf[2]}، وفي الشدة {cf[3]}، وفي الانتشار {cf[4]}"])
    B.append({"table": {"head": ["التقييم", "الموجة"], "rows": tab}})
    ch = _change(C)
    if ch:
        B.append({"p": "التغير عن التشغيل السابق: " + ch + "."})
    return sec(HEAD[1], "wave", B)


def _change(C):
    """the one change that matters (timing, path, strength or reach of the wave), or None"""
    for c in C.get("changes") or []:
        s = c.get("short") or ""
        if c.get("w", 0) >= 4 and not re.search(r"[A-Za-z]", s) and ("الموجة" in s or "الأخدود" in s):
            return s
    return None


# ------------------------------------------------------------------ 3. cumulative maps
def _grids(C, days):
    """the rain-making index (x 100) of each day from the big-picture fields of tonight's cycle (refwave.GRIDS,
    filled by the nightly run; recomputed from GFS ingredients when missing)"""
    import refwave
    st = C["st"]
    cy = str(st.get("cycle") or "")
    c0 = date(int(cy[:4]), int(cy[4:6]), int(cy[6:8])) if len(cy) == 10 else None
    for d in days:
        if d.isoformat() in refwave.GRIDS or c0 is None:
            continue
        try:
            import daily
            import ingredients as ING
            f = daily.gfs_fields(cy, (d - c0).days * 24, fields=list(ING.FIELDS))
            refwave.GRIDS[d.isoformat()] = 100 * refwave.index({n: ING.cut(f[n]) for n, _ in ING.FIELDS}, d)
        except Exception as e:  # noqa: BLE001
            print("report5: ingredients of", d, "not read:", repr(e), flush=True)
    return {d.isoformat(): refwave.GRIDS[d.isoformat()] for d in days if d.isoformat() in refwave.GRIDS}


def _sea_new(C, ds, said):
    """«خلايا بحرية مرجحة وقد تكون غزيرة بين ينبع ورابغ»: the sea cells of the nights before these days at their
    strongest, when stronger than already said"""
    import seacell
    import report4 as R4
    order = [k for k, *_ in seacell.STRETCHES]
    best = {}
    for d in ds:
        r = next((x for x in C["st"].get("seacell") or [] if x["d"] == (date.fromisoformat(d) - timedelta(days=1)).isoformat()), None)
        if r and r.get("times"):
            for k, v in seacell.levels(r).items():
                if v >= 2:
                    best[k] = max(best.get(k, 0), v)
    if not best:
        return None
    mx = max(best.values())
    key = f"sea{mx}"
    if key in said:
        return None
    said.add(key)
    return f"وفوق البحر والساحل خلايا {SEA_W[mx]} {R4._runs([k for k in order if best.get(k) == mx], order)}"


def s_maps(C, out_dir):
    """the wave's rain from OUR reading (Fahad 28 Nov 2026, 04:07: «أيام الموجه تحللها وتتوقع مطرها من خلال الصورة
    الكبرى وخرائط التذبذب لا من النماذج»): the rain-making index of the big picture (refwave.index: moisture x lift from
    the trough, cold aloft, vorticity, divergence aloft, low-level convergence, lapse) day by day, with the heavy sea
    cells and their path inland; accumulated as the area reached so far (the strongest reading of each place to that
    day). The colours are the strength of the rain-making ingredients out of 100, never millimetres: no amount is
    taken from model rain."""
    import numpy as np
    import refwave
    w = C.get("nw")
    B = []
    C["wmaps"] = []
    if not (w and out_dir):
        return sec(HEAD[2], "maps", [{"p": "لا موجة قادمة في توقع الليلة، فلا خرائط تراكمية."}])
    days = [w["start"] + timedelta(days=k) for k in range((w["end"] - w["start"]).days + 1)]
    G = _grids(C, days)
    rows = {r["d"]: r for r in C["st"].get("wave_rain") or [] if r.get("kind") == "ingr"}
    os.makedirs(os.path.join(out_dir, "fig"), exist_ok=True)
    n = len(days)
    plan = [(days[0], "التراكم في اليوم الأول")]
    if n >= 2:
        plan.append((days[1], "التراكم حتى نهاية اليوم الثاني"))
    if n >= 3:
        plan.append((days[2], "التراكم حتى نهاية اليوم الثالث" if n > 3 else "التراكم حتى نهاية الموجة"))
    plan.append((days[-1], "إجمالي الموجة مقارنة بالموجة المرجعية"))
    from datetime import datetime as _dt
    v = _dt.utcnow().strftime("%Y%m%d%H%M%S")
    said = set()
    B.append({"note": "من قراءتنا للصورة الكبرى وخرائط التذبذب يومًا بيوم، لا من مطر النماذج؛ والألوان قوة مكونات الهطول "
                      "من ١٠٠ لا كميات بالملليمتر."})
    for k, (y, title) in enumerate(plan):
        ds = [d.isoformat() for d in days if d <= y]
        gs = [G[d] for d in ds if d in G]
        if not gs:
            continue
        grid = np.max(gs, axis=0)
        when = f"يوم {ar_date(days[0])}" if y == days[0] else f"من {ar_date(days[0])} إلى {ar_date(y)}"
        m = refwave.wave_metrics(C["st"].get("wave_rain") or [], days[0], y) or {}
        panels = [(grid, m, "الموجة القادمة" if k == len(plan) - 1 else when.removeprefix("يوم "),
                   refwave.sea_plume(C["st"], days[0], y))]
        if k == len(plan) - 1:
            ref = C["st"].get("ref_wave") or refwave.current(None)
            if ref and ref.get("grid") is not None:
                panels.append((ref["grid"], ref, "الموجة المرجعية " + ar_date(date.fromisoformat(ref["d"]), weekday=False)))
        img = f"wmap_{k + 1}.png"
        try:
            refwave.draw(os.path.join(out_dir, "fig", img), panels, title, f"{when} بتوقيت مكة، من قراءة الصورة الكبرى والتذبذب")
        except Exception as e:  # noqa: BLE001
            print("report5: wave map failed:", img, repr(e), flush=True)
            continue
        C["wmaps"].append(img)
        # what the map adds: the regions reached for the first time, the widest spread so far
        regs = []
        for d in ds:
            for r in (rows.get(d) or {}).get("regions") or []:
                lb = refwave.label(r)
                if lb not in said and lb not in regs:
                    regs.append(lb)
        cov = max([(rows.get(d) or {}).get("cover") or 0 for d in ds] or [0])
        sea_new = _sea_new(C, ds, said)
        cap = f"{title}، {when} بتوقيت مكة."
        if k == len(plan) - 1:
            if ref and m:
                cap += (f" قلبها {ar(int(round(m.get('core') or 0)))} من ١٠٠ مقابل {ar(int(round(ref.get('core') or 0)))} "
                        f"للمرجعية، وانتشارها {R2.cover_pct(m.get('cover') or 0)} مقابل {R2.cover_pct(ref.get('cover') or 0)}.")
        else:
            if sea_new:
                cap += f" {sea_new}."
            if regs:
                cap += f" يبلغ المطر {jl(regs[:4])}"
                cap += f"، والانتشار {R2.cover_pct(cov)}." if cov else "."
            elif cov:
                cap += f" والانتشار {R2.cover_pct(cov)}."
        said.update(regs)
        B.append({"img": img, "v": v, "alt": title})
        B.append({"note": cap})
    if not C["wmaps"]:
        B.append({"p": "تعذّر رسم خرائط الموجة الليلة، وتُرسم في التحديث القادم."})
    return sec(HEAD[2], "maps", B)


# ------------------------------------------------------------------ 4. the decisive factor
def s_key(C):
    a = C.get("an")
    w = C.get("nw")
    nb = C.get("nb")
    if a and a.get("rh") is not None and w:
        t = (f"الرطوبة عند ٧٠٠ هكتوباسكال غرب المملكة: إن ارتفعت فوق ٤٥٪ اتسع المطر الغزير من الساحل إلى جدة ومكة، "
             f"وإن بقيت عند {ar(a['rh'])}٪ بقي القلب بحريًا في الشمال الغربي.") if a["rh"] < 45 else (
            "مسار الأخدود: إن تقدم محوره شرق البحر الأحمر اتسع المطر إلى الداخل، وإن تباطأ بقي على الساحل.")
    elif nb and nb.get("blocked"):
        t = "مرتفع إيران والخليج: إن ضعف تقدم الأخدود شرقًا واتسع المطر، وإن ثبت انكسر شمالًا وقل المطر جنوبًا."
    elif w:
        t = "عمق الأخدود وتوقيت وصوله: يحددان اتساع المطر وشدته، ويُتابعان كل ليلة."
    else:
        t = "عودة الرطوبة من البحر الأحمر وبحر العرب مع أي أخدود قادم من الشمال الغربي."
    return sec(HEAD[3], "key", [{"p": t}])


# ------------------------------------------------------------------ build
def _trim(rep):
    """keep the text within MAX_WORDS: shorter lists first (drivers, stages), never the table's rainy places"""
    for s in rep["sections"]:
        for b in s["blocks"]:
            if report_words(rep) <= MAX_WORDS:
                return rep
            if isinstance(b.get("ul"), list) and len(b["ul"]) > 3:
                b["ul"] = b["ul"][:3]
    return rep


def build(rep, st, out_dir=None):
    import report4 as R4
    out_dir = out_dir or R4.OUT_DIR
    try:
        import reportcheck
        reportcheck.OUT_DIR = out_dir      # so the auditor can see the map files
    except Exception:  # noqa: BLE001
        pass
    full = R4.build(rep, st)          # the internal analysis, kept and audited, not published
    C = R4.LAST_C
    try:
        import reportcheck
        st["analysis_check"] = {"errors": reportcheck.check(full, st)}
    except Exception as e:  # noqa: BLE001
        st["analysis_check"] = {"errors": [f"internal auditor crashed: {e!r}"]}
    if out_dir:
        try:
            rd = os.path.join(out_dir, "reports")
            os.makedirs(rd, exist_ok=True)
            json.dump(full, open(os.path.join(rd, "analysis_" + C["day0"].strftime("%Y%m%d") + ".json"), "w"),
                      ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            print("report5: internal analysis not saved:", repr(e), flush=True)
    out = []
    for f in (s_today, s_wave, lambda c: s_maps(c, out_dir), s_key):
        try:
            out.append(f(C))
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("report5: section failed:", repr(e), flush=True)
            out.append(sec(HEAD[len(out)], "error", [{"p": "تعذّر بناء هذا القسم الليلة، وسيُعاد بناؤه في التحديث القادم."}]))
    for k, x in enumerate(out):
        x["heading"] = f"{D[k]}. {x['heading']}"
    new = dict(rep)
    new.update({"v": 2, "layout": LAYOUT, "brand": R2.BRAND, "credit": R2.CREDIT, "date": ar_date(C["day0"]),
                "sections": out, "changed": bool(_change(C))})
    new = _trim(new)
    new["words"] = report_words(new)
    st.pop("qpf", None)        # model rain is no longer drawn (Fahad 28 Nov 2026, 04:07)
    return new
