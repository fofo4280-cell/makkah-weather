"""The short nightly report (Fahad, 18 Nov 2026).

«انا عشان نختصر التقرير وما نطول فيه … كل اللي احتاجه في التقرير اول شيء الخلاصة … ثم تفصيل مختصر لكل منطقة … بعدين
اروح للمناطق الاخرى بصورة مختصرة». Three parts, no repetition:
  1. الخلاصة: a wide case or a small one, its strength and spread over the Kingdom, where it concentrates (regions),
     and whether the big picture supports it and by what; the Hijaz and the south need only moisture, lift and wind.
  2. منطقة مكة المكرمة: places, confidence (ضعيفة / متوسطة / مرجحة / عالية) and its reasons (big picture, where the
     winds meet: the plateau, north-east of Taif, east Makkah, the edges, or the sea breeze), moisture %, and the
     system (convection, or convection with a trough even a shallow one cooling aloft).
  3. المناطق الأخرى: the same, one short paragraph each.
Everything is read once (makkah_story.read, bigreport.strength, the edges and plains rows, our run) and written
from that reading; the long sections (indicators, method) are left out of the nightly page.
"""
from datetime import date

import report2 as R2
from report2 import ar, num, jl, n1, sec, find, pending, ar_date

CONF4 = ("ضعيفة", "متوسطة", "مرجحة", "عالية")
SOUTH = {"عسير", "الباحة", "جازان", "نجران"}
HIJAZ = {"مكة المكرمة", "المدينة المنورة"} | SOUTH
BOX_OF = {"عسير": "southwest", "الباحة": "southwest", "جازان": "southwest", "نجران": "southwest",
          "مكة المكرمة": "west", "المدينة المنورة": "west", "تبوك": "north", "الجوف": "north",
          "الحدود الشمالية": "north", "حائل": "north", "القصيم": "central", "الرياض": "central", "الشرقية": "east"}


PW_REG = {"الباحة": ("baha",), "عسير": ("asir",), "جازان": ("jazan",), "نجران": ("najran",), "الرياض": ("riyadh",),
          "القصيم": ("qassim",), "الشرقية": ("east",), "حائل": ("hail",), "تبوك": ("tabuk",), "الجوف": ("jouf",),
          "الحدود الشمالية": ("nb",), "مكة المكرمة": ("mk_in", "mk_coast"), "المدينة المنورة": ("md_in", "md_coast")}


def pw_of(st, day0, region):
    """the region's precipitable water, % of normal: each region its own (ECMWF, the trusted model for moisture;
    Fahad 26 Nov 2026: three regions showed the same 126 % of one wide box), else the wide box (GFS)"""
    pr = st.get("pw_reg") or {}
    row = next((r for r in pr.get("rows") or [] if r["d"] == day0.isoformat()), None)
    ks = PW_REG.get(region)
    if row and ks and all(k in row for k in ks):
        return max(row[k]["pct"] for k in ks)
    row = next((r for r in st.get("pw", []) if r["d"] == day0.isoformat()), None)
    b = BOX_OF.get(region)
    return row[b]["pct"] if row and b in row else None


def size_word(cover):
    """the case by the share of the Kingdom our run wets (>= 1 mm)"""
    v = 100 * (cover or 0)
    return "حالة واسعة" if v >= 10 else "حالة متوسطة الانتشار" if v >= 3 else "حالة بسيطة محدودة" if v >= 0.1 else "لا حالة مطرية تُذكر"


def conf_level(named_conf, model_mm, gfs_mm=0.0):
    """four levels from the ingredients' confidence and what the models show"""
    base = {"عالية": 2, "متوسطة": 1, "منخفضة": 0}.get(named_conf, 0)
    if model_mm is not None and model_mm >= 5:
        base += 1
    elif model_mm is not None and model_mm < 1 and (gfs_mm or 0) < 1:
        base -= 1
    return CONF4[max(0, min(3, base))]


def system_word(st, day0, region):
    label, T, Rr = R2.case_kind(st, day0, region)
    if Rr:
        shallow = "ضحل" in " ".join(Rr)
        return "حمل حراري مع أخدود" + (" ضحل يبرد الطبقات العليا" if shallow else "")
    return "حمل حراري" + ("، يسنده النظام المداري" if T else " محلي")


# ------------------------------------------------------------------ the spread against the past days (Fahad, 18 Nov 2026)
def _pc(v):
    return "—" if v is None else R2.cover_pct(v).removeprefix("نحو ")


def _ratio_words(today, peak):
    if today is None or not peak or peak <= 0:
        return None
    r = today / peak
    if r >= 0.8:
        return "يقارب انتشار ذروتها"
    if r >= 0.4:
        return "نحو نصف انتشار ذروتها"
    if r >= 0.2:
        return "نحو ربع انتشار ذروتها أو أقل"
    n = round(1 / max(r, 1e-6))
    return "أقل بكثير من انتشار ذروتها" + (f" (نحو جزء من {ar(n)})" if n <= 50 else "")


def spread_table(st, day0, region=None):
    """blocks: one table (our model and GFS, today, yesterday, the day before, the last wave's peak) and one line"""
    import covhist as CH
    H = st.get("cover_hist")
    if not H:
        return []
    c = CH.compare(H, day0, region)
    pk = c["peak"]
    head = ["المصدر", "اليوم", "أمس", "أول أمس"]
    if pk:
        head.append(f"ذروة الموجة الماضية ({ar_date(pk[0])})")
    rows = []
    if any(v is not None for v in c["ours"]):
        rows.append(["نموذجنا"] + [_pc(v) for v in c["ours"]] + (["لم يُحفظ"] if pk else []))
    rows.append(["جي إف إس"] + [_pc(v) for v in c["gfs"]] + ([_pc(pk[1])] if pk else []))
    B = [{"p": ("انتشار المطر على المملكة" if region is None else "انتشار المطر في المنطقة")
               + " (نسبة المساحة التي يبلغ مطرها ١ ملم فأكثر في اليوم):"},
         {"table": {"head": head, "rows": rows}}]
    if pk:
        w = c["wave"]
        span = ar_date(w[0]) if len(w) == 1 else R2.ar_span(w[0], w[-1])
        rw = _ratio_words(c["gfs"][0], pk[1])
        t = f"الموجة الماضية {span}"
        if rw:
            t += f"، وانتشار اليوم {rw} بحسب جي إف إس"
        B.append({"p": t + "."})
    else:
        B.append({"p": "لا موجة مطرية في الأسبوعين الماضيين للمقارنة بها."})
    return B


# ------------------------------------------------------------------ the upper cold wave (Fahad, 18 Nov 2026)
# «اي ملامح لموجة علوية باردة اذكرها في الخلاصة ووضح مناطقها وسبب الموجة الباردة ان كان اخدود ضحل ام متعمق وتأثيره
# على اي المناطق لكي نأخذ أماكن المطر من الأوروبي ونتابع العاصفة من الأمريكي». Read from the 500 hPa trough tracks
# (axis anomaly in m, centre depth in dam), the 24 h height fall and T500 over the edges, and the T500 anomaly of the
# boxes. Silent when no sign aloft. The trust rule (15-16 Nov 2026): with a trough, the rain area from the
# ECMWF-driven run, the storm spots and their strength from the GFS-driven run.
ORDER = ("مكة المكرمة", "المدينة المنورة", "الباحة", "عسير", "جازان", "نجران", "تبوك", "الجوف", "الحدود الشمالية",
         "حائل", "القصيم", "الرياض", "الشرقية")
BOX_REGS = {"west": ("مكة المكرمة", "المدينة المنورة"), "southwest": ("الباحة", "عسير", "جازان", "نجران"),
            "north": ("تبوك", "الجوف", "الحدود الشمالية", "حائل"), "central": ("القصيم", "الرياض"), "east": ("الشرقية",)}
EDGE_AT = {"hada": "حافة الهدا", "shafa": "حافة الشفا", "sail": "السيل الكبير", "shamnasir": "حرة شمنصير",
           "rahat_s": "حرة رهاط", "rahat_n": "حرة رهاط الشمالية", "kishb": "حرة كشب", "baha": "حافة الباحة",
           "asir_n": "حافة عسير الشمالية", "asir_s": "حافة عسير الجنوبية", "jazan_h": "مرتفعات جازان"}


def _axis_dense(axis, step=0.25):
    """the trough axis [(lat, lon, anomaly m)] sampled every ~step degrees"""
    out = []
    for (a1, b1, v1), (a2, b2, v2) in zip(axis, axis[1:]):
        n = max(1, int(max(abs(a2 - a1), abs(b2 - b1)) / step))
        for k in range(n):
            f = k / n
            out.append((a1 + f * (a2 - a1), b1 + f * (b2 - b1), v1 + f * (v2 - v1)))
    if axis:
        out.append(tuple(axis[-1]))
    return out


_REGS = []


def _in_kingdom(pts):
    """[(lat, lon, v, region name)] of the points that fall inside the Kingdom"""
    import sa_geo as G
    if not _REGS:
        _REGS.extend(G.regions())
    if not pts:
        return []
    idx = G.region_of_points(_REGS, [p[0] for p in pts], [p[1] for p in pts])
    return [(p[0], p[1], p[2], _REGS[k]["name"]) for p, k in zip(pts, idx) if k >= 0]


def _kingdom_part(x):
    """the part of one day's trough over the Kingdom: (deepest anomaly m, its lat, regions along the axis, tip lat)"""
    kp = [p for p in _in_kingdom(_axis_dense(x.get("axis") or [])) if p[2] <= -15]
    if not kp:
        return None
    deep = min(kp, key=lambda p: p[2])
    regs = list(dict.fromkeys(p[3] for p in kp))
    by = {}
    for p in kp:
        by[p[3]] = min(by.get(p[3], 0), p[2])
    return {"v": deep[2], "lat": deep[0], "regions": regs, "by": by, "tip": min(p[0] for p in kp),
            "tip_v": max(kp, key=lambda p: -p[0])[2]}


def cold_wave(st, day0):
    """the upper cold wave of the report day, or None: {trough, next, falls, colds, regions, ...}"""
    from datetime import timedelta
    d0, d1, dm = day0.isoformat(), (day0 + timedelta(days=1)).isoformat(), (day0 - timedelta(days=1)).isoformat()
    best = None
    for t in st.get("troughs") or []:
        x = next((x for x in t.get("days") or [] if x.get("d") == d0), None)
        if not x:
            continue
        kp = _kingdom_part(x)
        if kp and (best is None or kp["v"] < best[1]["v"]):
            best = (t, kp, x)
    W = {}
    if best:
        t, kp, x = best
        nx = next((y for y in t["days"] if y.get("d") == d1), None)
        pv = next((y for y in t["days"] if y.get("d") == dm), None)
        W["trough"] = {"centre": (x["lat"], x["lon"]), "depth": x["depth"], "k": kp,
                       # a closed 500 hPa low with its centre over or next to the Kingdom: a cut-off low
                       "cutoff": bool(x["lat"] <= 33 and 32 <= x["lon"] <= 57 and x["depth"] <= -4),
                       "next": None if not nx else {"depth": nx["depth"], "k": _kingdom_part(nx)},
                       "prev": None if not pv else {"depth": pv["depth"], "k": _kingdom_part(pv)}}
    # the height fall and the cold over the edges, region by region (GFS at 3 PM Makkah)
    falls, colds = {}, {}
    pl = st.get("plains") or {}
    if pl.get("day") == d0:
        for e in pl.get("edges") or []:
            up = e.get("upper") or {}
            if up.get("fall") is not None and up["fall"] <= -10:
                r = falls.setdefault(e["region"], [0, []])
                r[0] = min(r[0], up["fall"])
                r[1].append(EDGE_AT.get(e["key"], e["key"]))
            if up.get("t500") is not None and (up.get("flags") or {}).get("cold"):
                colds[e["region"]] = min(colds.get(e["region"], 0), up["t500"])
    W["falls"], W["colds"] = falls, colds
    pt = st.get("pattern") or {}
    W["anom"] = {}
    if pt.get("day") == d0:
        for k, b in (pt.get("boxes") or {}).items():
            if b.get("anom") is not None and b["anom"] <= -0.5:
                W["anom"][k] = (b["name"], b["anom"], b["t"])
    if not (W.get("trough") or falls or W["anom"]):
        return None
    regs = set(W["trough"]["k"]["regions"]) if W.get("trough") else set()
    regs |= set(falls)
    for k in W["anom"]:
        regs |= set(BOX_REGS.get(k, ()))
    W["regions"] = [r for r in ORDER if r in regs]
    return W


def _dam(v_m):
    return n1(abs(v_m) / 10)


def _span(vals):
    a, b = min(vals), max(vals)
    return f"{ar(a)}٪" if a == b else f"{ar(a)} إلى {ar(b)}٪"


def cold_wave_blocks(st, day0, effect=True, W=None):
    """the summary's paragraph on the upper cold wave (empty when there is none)"""
    import bigreport as BR
    import troughs as TR
    W = W or cold_wave(st, day0)
    if not W:
        return []
    B = [{"h": "الموجة العلوية الباردة"}]
    T = W.get("trough")
    if T:
        k = T["k"]
        kw = BR.trough_word(abs(k["v"]) / 10)
        nx = T.get("next")
        dc = None if not nx else nx["depth"] - T["depth"]          # dam, negative = deeper tomorrow
        trend = ("يتعمق" if dc is not None and dc <= -1 else "يضعف" if dc is not None and dc >= 1 else
                 "ثابت العمق" if dc is not None else None)
        head = (f"تظهر ملامح موجة علوية باردة: منخفض علوي منعزل فوق {TR.place(*T['centre'])}" if T.get("cutoff")
                else f"تظهر ملامح موجة علوية باردة: أخدود {kw} فوق المملكة")
        if trend:
            head += f"، {trend} في مركزه"
        if k["tip"] <= 27 and abs(k["tip_v"]) < 40:
            head += "، ويصل طرفه الضحل إلى الحجاز"
        B.append({"p": head + "."})
        t = (f"السبب: أخدود عند ٥٠٠ هكتوباسكال مركزه فوق {TR.place(*T['centre'])} بعمق {n1(abs(T['depth']))} ديكامتر، "
             f"يمتد محوره جنوبًا فوق {jl(k['regions'])} حتى نحو {ar(int(round(k['tip'])))} شمالًا؛ "
             f"وأعمق جزء منه داخل المملكة {_dam(k['v'])} ديكامتر دون المعدل عند {ar(int(round(k['lat'])))} شمالًا")
        if k["tip"] <= 27 and abs(k["tip_v"]) < 40:
            t += f"، و{_dam(k['tip_v'])} فقط عند طرفه الجنوبي"
        B.append({"p": t + "."})
        if nx and nx.get("k"):
            q = nx["k"]
            t = (f"وغدًا {'يتعمق مركزه' if trend == 'يتعمق' else 'يضعف مركزه' if trend == 'يضعف' else 'يبقى مركزه'} "
                 f"({n1(abs(T['depth']))} ثم {n1(abs(nx['depth']))} ديكامتر)، ويمتد محوره فوق {jl(q['regions'])}")
            if q["tip"] <= k["tip"] - 1:
                t += f" حتى نحو {ar(int(round(q['tip'])))} شمالًا"
            t += f"، بعمق {_dam(q['v'])} ديكامتر فوق المملكة."
            B.append({"p": t})
        elif nx:
            B.append({"p": "ويخرج محوره من المملكة غدًا، فهي موجة عابرة ليوم واحد."})
    else:
        B.append({"p": "تظهر ملامح تبريد علوي ضعيف: هبوط في سطح ٥٠٠ هكتوباسكال وبرودة في الطبقات العليا، دون أخدود واضح المحور فوق المملكة."})
    signs = []
    fl = [(W["falls"][r][0], r, W["falls"][r][1]) for r in ORDER if r in W["falls"]]
    if fl:
        parts = []
        for i, (f, r, at) in enumerate(fl):
            at = list(dict.fromkeys(at))
            x = f"{'' if i == 0 else 'و'}{ar(abs(round(f)))} مترًا فوق {r}"
            parts.append(x)
        signs.append("هبط سطح ٥٠٠ هكتوباسكال خلال يوم نحو " + "، ".join(parts))
    for k, (nm, a, tt) in W["anom"].items():
        signs.append(f"وحرارة ٥٠٠ هكتوباسكال فوق {nm} {chr(0x200e) + '−' if tt < 0 else ''}{n1(abs(tt))}°، "
                     f"{'أبرد' if a < 0 else 'أدفأ'} من معدلها بـ{n1(abs(a))}°")
    if signs:
        signs[0] = signs[0].removeprefix("و")
        B.append({"p": "العلامات: " + "، ".join(signs) + "."})
    # the effect, region by region: cold aloft over moist air helps the storms; over dry air it is wind and cold only
    hij, nor, dry = [], [], []
    for r in W["regions"]:
        pw = pw_of(st, day0, r)
        if pw is None or pw < 110:
            dry.append(r)
        elif r in HIJAZ:
            hij.append((r, pw))
        else:
            nor.append((r, pw))
    eff = []
    if hij:
        eff.append(f"على {jl([r for r, _ in hij])} (الماء القابل للهطول {_span([p for _, p in hij])} من معدله) "
                   "يبرّد الطبقات العليا فوق هواء رطب، فيقوي الخلايا الرعدية بعد الظهر على الحواف والحرات")
    if nor:
        eff.append(f"وعلى {jl([r for r, _ in nor])} ({_span([p for _, p in nor])}) برودة ورياح مع فرص زخات متفرقة")
    if dry:
        eff.append(f"وعلى {jl(dry)} برودة ورياح دون مطر يُذكر، لأن الهواء دون رطوبة كافية")
    if eff and effect:
        eff[0] = eff[0].removeprefix("و")
        B.append({"p": "الأثر: " + "، ".join(eff) + "."})
    # no «التوجيه» line sending the rain places to a model run (doctrine, Fahad 25 Nov 2026): the note under the
    # summary already says the places come from the ingredients and model rain stays on the map
    return B


# ------------------------------------------------------------------ 1. the summary
# Fahad, 18 Nov 2026 (evening): «في الخلاصة تدرس حالة المملكة كاملة، ثم تحدد أماكن وجود المطر، وهل وجود المطر بسبب حمل
# حراري أو أخدود متعمق أو أخدود ضحل أو أخدود منعزل أو معا مجتمعة. نسبة الانتشار، نسبة النجاح، توقعاتك في النجاح، البنية
# مع الصورة العامة، هل هي ضعيفة أم متوسطة أم مرجحة أم قوية. تذكر المناطق المتأثرة … سواء اللي فوقها موجة علوية باردة هل
# تتأثر بالمطر أو لا … خلاصة عملية جميلة واضحة شفافة عميقة».
LEVEL4 = ("ضعيفة", "متوسطة", "مرجحة", "قوية")
# the Kingdom's chance of a wide rain day by the strength score (25-season study, 15 Nov 2026: 3 % at 0-1, 9-11 % at
# 1-2, 16-19 % at 2-3, 23-33 % at 3-5)
WIDE_CHANCE = ((1, "نحو ٣٪"), (2, "نحو ١٠٪"), (3, "نحو ١٧٪"), (9, "٢٣ إلى ٣٣٪"))


def level4(pct):
    return LEVEL4[0 if pct < 40 else 1 if pct < 60 else 2 if pct < 80 else 3]


def _covers(st, rs, day0):
    """(ours, gfs): {region: share} and the Kingdom share under None, for the report day"""
    H = st.get("cover_hist") or {}
    dat = (rs or {}).get("data") or {}
    ours = dict(dat.get("cover_regions") or {})
    if dat.get("cover_ksa") is not None:
        ours[None] = dat["cover_ksa"]
    if not ours and not pending(rs):
        h = (H.get("ours") or {}).get(day0.isoformat())
        if h:
            ours = dict(h["regions"]); ours[None] = h["ksa"]
    g = (H.get("gfs") or {}).get(day0.isoformat())
    gfs = {}
    if g:
        gfs = dict(g["regions"]); gfs[None] = g["ksa"]
    return ours, gfs


def _num(x):
    try:
        return float(str(x).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")))
    except ValueError:
        return 0.0


MM_LEVELS = ((20, "heavy"), (5, "moderate"), (1, "light"))


def _towns(name):
    """the towns in brackets of an edge or plain name, else the name itself"""
    import re
    m = re.search(r"\((.+)\)", name)
    return m.group(1) if m else name


def _put(row, mm, place):
    for lim, k in MM_LEVELS:
        if mm is not None and mm >= lim:
            row[k].append(place)
            return


def _cape_word(c):
    return "heavy" if c >= 1000 else "moderate" if c >= 300 else "light"


STRAT_MIN = 0.05     # share of a region under wide lift before it is named (strat.py)
COVER_OF = {"ضعيفة": 0.01, "متوسطة": 0.03, "مرجحة": 0.08, "قوية": 0.15}   # share of a region that a reading of this level wets


LW_COLD, LW_WARM = -1.0, 1.0


def lowwarm_region(st, day0, nm):
    """the low-level index over a whole region (lowwarm.region_means), or None"""
    lw = st.get("lowwarm") or {}
    d = day0.isoformat()
    if d not in (lw.get("days") or []):
        return None
    v = (lw.get("regions") or {}).get(nm) or []
    k = lw["days"].index(d)
    return v[k] if k < len(v) else None


def lowwarm_of(st, day0):
    """the low-level warm/cold event of the day (lowwarm.py): (Makkah low ground and Tihama, Taif plateau and edges)"""
    lw = st.get("lowwarm") or {}
    d = day0.isoformat()
    if d not in (lw.get("days") or []):
        return None, None
    k = lw["days"].index(d)
    return (lw.get("low") or [None] * (k + 1))[k], (lw.get("high") or [None] * (k + 1))[k]


def region_reading(st, rs, regs, day0, W, big=0.5):
    """the expert reading of each region from the ingredients alone, not from any model's rain (Fahad, 19 Nov 2026:
    «ابني توقعاتك على صورة النمط الكبير ودراسة تصادم الرياح والرطوبة وتأثير التبريد العلوي والطاقة وعدم الاستقرار مع
    الإهتمام بتضاريس كل منطقة وحركة الرياح في الطبقات المتوسطة … بعيدا عن نموذجنا … لا تنشرها بناء على نموذجنا او gfs»).
    Ingredients: PW % of normal (box), where the winds meet (the Taif collision, the Kingdom surface collision zones, sea
    air climbing the escarpments, cold outflow onto the plains), the upper cold wave, CAPE, the terrain of each edge,
    plain and harra, and the 700-500 hPa steering."""
    import makkah_story as MS
    pl = st.get("plains") or {}
    same = pl.get("day") == day0.isoformat()
    eds = (pl.get("edges") or []) if same else []
    prs = (pl.get("rows") or []) if same else []
    cz = st.get("collide") or {}
    zones = cz.get("zones") or [] if cz.get("day") == day0.isoformat() else []
    wregs = set((W or {}).get("regions") or [])
    T = (W or {}).get("trough")
    RD = {}
    try:
        RD = MS.read(st, True)
    except Exception:  # noqa: BLE001
        pass
    meet_mk = RD.get("meet")
    strat = st.get("strat") if (st.get("strat") or {}).get("day") == day0.isoformat() else None
    areas = {}
    try:
        import sa_geo as G
        areas = {r["name"]: r["area_km2"] for r in G.regions()}
    except Exception:  # noqa: BLE001
        pass
    import plains as PL
    BOXES = {e[0]: e[5] for e in PL.EDGES if len(e) > 5 and e[5]}
    MZ = {z[0]: z[2] for z in MS.ZONES}
    _uv = [(r["steer_u"], r["steer_v"]) for r in prs if r.get("steer_u") is not None]
    uv_all = (sum(u for u, _ in _uv) / len(_uv), sum(v for _, v in _uv) / len(_uv)) if _uv else None
    out = []
    lw_low, lw_high = lowwarm_of(st, day0)
    region_reading.lowwarm = {"low": lw_low, "high": lw_high, "cut": []}
    for nm in ORDER:
        pw = pw_of(st, day0, nm)
        moist = (pw or 0) >= 110
        cold = nm in wregs
        row = {"heavy": [], "moderate": [], "light": []}
        why = {}
        src = []            # (lat, lon, level, name) where the cells are born, to follow them with the steering
        meets, capes, steer, plains_at = [], [], None, []
        strat_frac = 0.0
        _sr = (strat.get("regions") or {}).get(nm) if strat else None
        strat_here = bool(_sr and _sr["frac"] >= STRAT_MIN)

        zone = {}           # place -> "low" (Makkah plain, Al-Jumum, Tihama) or "high" (Taif plateau, edges, harrat)

        def add(lv, place, cause, at=None, z=None):
            if any(place in v for v in row.values()):
                return
            row[lv].append(place)
            why[place] = cause
            if z:
                zone[place] = z
            if at:
                src.append((at[0], at[1], lv, place))

        # the escarpments and the harrat: sea air or moist southerly air climbing, with fuel
        for e in eds:
            if e["region"] != nm:
                continue
            f = e.get("flags") or {}
            if nm == "مكة المكرمة" and e["key"] in ("hada", "shafa") and not (meet_mk and meet_mk[0] == "edge"):
                continue                # Fahad: the edges of Al-Hada and Ash-Shafa only when the winds meet there
            sail_meet = e["key"] == "sail" and meet_mk and meet_mk[0] != "edge"
            lift = f.get("upslope") or sail_meet
            up_cold = (e.get("upper") or {}).get("flags", {}).get("cold") or (e.get("upper") or {}).get("flags", {}).get("fall")
            fuel = (e.get("cape") or 0)
            harra = e.get("kind") == "harra" or "حرة" in e["name"]
            fall = (e.get("upper") or {}).get("fall")
            if harra and not (strat_here or (fall is not None and fall <= -10 and big >= 0.6)):
                continue                # 10-19 Nov test: Harrat Rahat named 13-17 Nov without a real height fall, all dry
            if f.get("moist") and (lift or (up_cold and fuel >= 100)) and (f.get("unstable") or fuel >= 150 or f.get("midmoist")):
                lv = _cape_word(fuel)
                if lv == "heavy" and not (up_cold and big >= 0.6):
                    lv = "moderate"     # heavy only with the cooling aloft and a supportive big picture
                if big < 0.4 and lv != "light":
                    lv = "moderate" if lv == "heavy" else "light"   # a very weak day: 14-17 Nov edges 0-19 % wet, light
                cause = ("التقاء الرياح على هضبة الطائف" if sail_meet else
                         ("هواء رطب يصعد الحرة" if harra else "هواء البحر الرطب يصعد الحافة") if f.get("upslope") else
                         "تبريد علوي فوق هواء رطب")
                bx = BOXES.get(e["key"])
                add(lv, _towns(e["name"]), cause, ((bx[0] + bx[1]) / 2, (bx[2] + bx[3]) / 2) if bx else None, "high")
                capes.append(fuel)
                if f.get("upslope") and e["key"] != "sail":
                    meets.append("هواء البحر الرطب يصعد " + P_short(e["name"]))
            if e.get("steer") is not None and steer is None and e.get("steer") >= 3:
                steer = e["steer"]
        # the plains under the mountains: cold outflow running down in the evening into hot moist air; written only
        # when the reading supports it (Fahad, 19 Nov 2026: «اذا رأيت فرص على السهول اكتبها واذا لم ترى لا تكتب»)
        for r in prs:
            if r["region"] != nm:
                continue
            f = r.get("flags") or {}
            if nm == "مكة المكرمة" and not RD.get("toward_plain"):
                continue                # 18 Nov 2026 test: cells moved NE, Makkah and Al-Jumum stayed dry
            if f.get("moist") and f.get("unstable") and (f.get("mountain") or f.get("inflow")):
                # the storms come down from the mountains: their strength follows the fuel up there, at most moderate
                pn = _towns(r["name"])
                add("moderate" if (r.get("cape_mtn") or 0) >= 300 else "light", pn, "هواء السحب البارد ينحدر مساءً من الجبال",
                    z="low")
                plains_at.append(pn)
                meets.append("هواء السحب البارد ينحدر مساءً إلى " + P_short(r["name"]))
        # the surface collision zones over the Kingdom
        for z in zones:
            if nm in (z.get("regions") or [z.get("region")]):
                w2 = z["winds"]
                cause = f"التقاء رياح {w2[0]} برياح {w2[1]}" if len(w2) > 1 else f"رياح {w2[0]} تتباطأ وتتكدس"
                meets.append(f"{cause} قرب {z['place']}")
                add("moderate" if (z.get("c") or 0) >= 4 else "light", f"قرب {z['place']}", cause, (z["lat"], z["lon"]),
                    "high" if z["lat"] >= 20.8 and z["lon"] >= 40.3 else "low")
        # wide lift of a deep moist layer ahead of a trough: stratiform rain the convective reading cannot see
        # (19 Nov 2026 test: 10-12 Nov over Riyadh and the Eastern Province)
        sr = (strat.get("regions") or {}).get(nm) if strat else None
        if sr and sr["frac"] >= STRAT_MIN:
            lvs = "moderate" if sr["frac"] >= 0.25 else "light"
            cause = "صعود واسع لهواء رطب عميق في الطبقات الوسطى (مطر طبقي)"
            for sp in sr["spots"] or ["أجزاء واسعة"]:
                add(lvs, sp, cause)
            meets.append(f"صعود واسع لهواء رطب عميق فوق نحو {ar(round(100 * sr['frac']))}٪ من المنطقة")
            strat_frac = sr["frac"]
        # Makkah: the afternoon meeting around Taif from the collision study
        if nm == "مكة المكرمة" and meet_mk:
            site = "على حافتي الهدا والشفا" if meet_mk[0] == "edge" else "شمال الطائف وشرقه"
            meets.insert(0, f"التقاء الرياح بعد الظهر {site}" + (f" قرب {meet_mk[1]}" if meet_mk[1] else ""))
            if meet_mk[0] != "edge" and meet_mk[1]:
                bx = MZ.get("east_taif")
                dry = meet_mk[0] == "east_dry"
                add("light" if dry else "moderate", f"شرق الطائف قرب {meet_mk[1]}",
                    "التقاء الرياح بعد الظهر" + ("، والطاقة هناك ضعيفة" if dry else ""),
                    ((bx[0] + bx[1]) / 2, (bx[2] + bx[3]) / 2) if bx else None, "high")
            if RD.get("steer"):
                sv = RD["steer"]
                steer = (f"نحو {sv['to']} بنحو {ar(round(sv['speed']))} م/ث" if sv["speed"] >= 3
                         else "ضعيفة فتبقى الخلايا شبه ثابتة وتنحدر مع الأودية")
        # follow the cells with the 700-500 hPa wind: where they drift in the 2-3 hours after they are born
        uv = None
        if nm == "مكة المكرمة" and RD.get("steer"):
            uv = (RD["steer"]["u"], RD["steer"]["v"])
        else:
            pr = next((r for r in prs if r["region"] == nm and r.get("steer_u") is not None), None)
            if pr:
                uv = (pr["steer_u"], pr["steer_v"])
            elif uv_all:
                uv = uv_all             # no plain of its own (Al-Baha, Al-Madinah): the mean steering over the west
        if uv and (uv[0] ** 2 + uv[1] ** 2) ** 0.5 >= 3:
            for la, lo, lv, pname in src[:3]:
                if lv == "light":
                    continue
                d = _downstream(la, lo, uv[0], uv[1], nm)
                if d:
                    add("light" if lv == "moderate" else "moderate", d,
                        f"تدفعها رياح الطبقات المتوسطة من {P_short(pname)}", z=zone.get(pname))
        if isinstance(steer, (int, float)):
            steer = (f"نحو {MS.toward(*uv)} بنحو {ar(round(steer))} م/ث" if uv else f"بنحو {ar(round(steer))} م/ث")
        for k in row:
            row[k] = list(dict.fromkeys(row[k]))[:5]
        # the low-level cold event cancels the rain where it lies (Fahad, 19 Nov 2026: «لما يكون هناك حدث بارد الغي كل
        # شيء غيره»). Tested on 382 days (1 Sep-18 Nov 2026 and three seasons before, troughs and stratiform days too):
        # with -1 or less no day had 20 mm around Makkah, in Tihama, on the Taif plateau or the edges, and 2-5 % had
        # 5 mm. Only the Makkah region was tested, so only there; places with no known ground go when both sides are cold.
        lw_cut = []
        if nm == "مكة المكرمة" and (lw_low is not None or lw_high is not None):
            cl, ch = lw_low is not None and lw_low <= LW_COLD, lw_high is not None and lw_high <= LW_COLD
            for k in row:
                keep = []
                for p_ in row[k]:
                    z_ = zone.get(p_)
                    if (z_ == "low" and cl) or (z_ == "high" and ch) or (z_ is None and cl and ch):
                        lw_cut.append(p_)
                    else:
                        keep.append(p_)
                row[k] = keep
            plains_at = [p_ for p_ in plains_at if p_ not in lw_cut]
            if cl or ch:
                region_reading.lowwarm["cut"] = lw_cut
                region_reading.lowwarm["sides"] = [s_ for s_, c_ in (("low", cl), ("high", ch)) if c_]
            if cl and ch:
                continue                # no showers either, vague or not
        # the other regions (Fahad: «ماذا عن بقية السعودية»; 383 days, PERSIANN, each region's own mean): on cold days
        # (-1 or less) a spot of 20 mm came 4 times in about 1,600 region-days, so the convective places go; wide light
        # rain under the cold air still came in Dec-May in the north and centre (Hail 11 of 92 days), so the stratiform
        # places stay, light
        lv_reg = lowwarm_region(st, day0, nm) if nm != "مكة المكرمة" else None
        if lv_reg is not None and lv_reg <= LW_COLD:
            strat_cause = "صعود واسع لهواء رطب عميق في الطبقات الوسطى (مطر طبقي)"
            for k in ("heavy", "moderate"):
                for p_ in list(row[k]):
                    row[k].remove(p_)
                    if why.get(p_) == strat_cause:
                        row["light"].append(p_)
                    else:
                        lw_cut.append(p_)
            for p_ in list(row["light"]):
                if why.get(p_) != strat_cause:
                    row["light"].remove(p_)
                    lw_cut.append(p_)
            plains_at = [p_ for p_ in plains_at if p_ not in lw_cut]
            region_reading.lowwarm.setdefault("cold_regions", []).append(nm)
            if not any(row.values()):
                continue
        if not any(row.values()):
            # no place where the rain can be pinned down: a moist region under the cold wave keeps passing showers,
            # named in one sentence, not as an empty row (Fahad, 19 Nov 2026)
            if cold and moist:
                out.append({"name": nm, "row": row, "why": {}, "trough": None, "meets": [], "pw": pw, "steer": None,
                            "cape": 0, "pct": 0, "level": "ضعيفة", "cold": True, "parts": {}, "cover": 0.002,
                            "area": areas.get(nm), "vague": True, "plains": []})
            continue
        trough = None
        if cold:
            if T and T.get("cutoff") and nm in T["k"]["by"]:
                trough = "منخفض علوي منعزل"
            elif T and nm in T["k"]["by"] and T["k"]["by"][nm] <= -40:
                trough = "أخدود متعمق"
            else:
                trough = "أخدود ضحل"
        cmax = max(capes) if capes else 0
        nplaces = sum(len(v) for v in row.values())
        parts = {"الرطوبة": 1.0 if moist else 0.5 if (pw or 0) >= 95 else 0.0,
                 "الصورة الكبرى": big,
                 "التقاء الرياح": 1.0 if meets else 0.0,
                 "التبريد العلوي": 1.0 if trough else 0.0,
                 "الطاقة": 1.0 if cmax >= 500 else 0.5 if cmax >= 150 else 0.0}
        pct = min(95, round(100 * sum(parts.values()) / len(parts)))
        # the low-level warm event only adds confidence to the other ingredients, it never makes rain alone (Fahad)
        lw_boost = False
        if meets and (parts["الرطوبة"] >= 0.5 or cmax >= 150):
            # warm (1 or more): wet 40-70 % of days against 13-36 % on neutral days in every region (383 days)
            vals = (lw_low, lw_high) if nm == "مكة المكرمة" else (lowwarm_region(st, day0, nm),)
            if any(v is not None and v >= LW_WARM for v in vals):
                pct = min(95, pct + 10)
                lw_boost = True
        lv = level4(pct)
        # not tested on enough cases yet (Fahad, 19 Nov 2026: «لا تصدر شيء الا متيقن منه»): no «قوية» on a weak day,
        # and a region with no meeting of the winds is a possible shower only
        if lv == "قوية" and strat_frac < 0.10:
            lv = "مرجحة"                 # 10-19 Nov test: the wide days were the wide-lift days (Qassim 91 %, Hail 45 %)
        if big < 0.6 and lv == "قوية":           # the Kingdom's strength under 1.8 of 5
            lv = "مرجحة"
        if big < 0.4 and strat_frac < STRAT_MIN:
            lv = min(lv, "متوسطة", key=LEVEL4.index)    # under 1.2 of 5: 12-18 Nov regions 0-19 % wet
        if not meets:
            lv = "ضعيفة"
        elif cmax < 150 and strat_frac < STRAT_MIN and lv in ("مرجحة", "قوية"):
            lv = "متوسطة"               # a meeting with no measured fuel
        cov = COVER_OF[lv] * (1.0 if meets else 0.5) * min(1.0, 0.4 + 0.15 * nplaces)
        cov = max(cov, 0.6 * strat_frac)           # wide lift wets about that share of the region
        out.append({"name": nm, "row": row, "why": why, "strat": strat_frac, "plains": plains_at, "vague": False, "trough": trough, "meets": list(dict.fromkeys(meets))[:3], "pw": pw,
                    "steer": steer, "cape": cmax, "pct": pct, "level": lv, "cold": cold, "parts": parts, "lw_boost": lw_boost,
                    "cover": cov, "area": areas.get(nm)})
    return out


def _downstream(lat, lon, u, v, region, hours=2.5):
    """the place the cells reach after a few hours with the steering wind (u, v m/s), or None when they stay put"""
    import math
    import sa_geo as G
    km = min(80.0, max(25.0, 3.6 * hours * math.hypot(u, v)))
    sp = math.hypot(u, v)
    la = lat + km * v / sp / 111.2
    lo = lon + km * u / sp / (111.2 * math.cos(math.radians(lat)))
    try:
        regs = G.regions()
        k = int(G.region_of_points(regs, [la], [lo])[0])
        if k >= 0 and regs[k]["name"] != region:
            return None              # out of the region: the next region's own reading covers it
    except Exception:  # noqa: BLE001
        pass
    n, d = G.nearest_place(la, lo)
    if not n:
        return None
    return f"قرب {n}" if d <= 20 else f"{G.direction(*_town_at(n), la, lo)} {n}" if _town_at(n) else None


def _town_at(name):
    import sa_geo as G
    for n, la, lo in G.PLACES:
        if n == name:
            return la, lo
    return None


def P_short(name):
    import plains as P
    return P.short(name)


def _cov(v):
    return "—" if v is None else ("أقل من ٠٫١٪" if v < 0.001 else R2.cover_pct(v).removeprefix("نحو "))


def weak_reasons(st, day0, W):
    """short reasons why the big picture over the Kingdom is weak today, from the drivers that are missing"""
    import bigreport as BR
    import bigpic as BP
    v = BR._vals(st, day0)
    c = BR.strength(st, day0)
    out = []
    m = v.get("m")
    if m and st.get("wet_season") is not False:
        if m["phase"] not in BP.WET_PHASES:
            out.append(f"التذبذب المداري متوقع اليوم في الطور {ar(m['phase'])}، وهو خارج أطوار الدعم")
        elif m["amp"] < 1.5:
            out.append(f"التذبذب المداري متوقع اليوم في الطور {ar(m['phase'])} بسعة ضعيفة ({n1(m['amp'])})")
    if v.get("mf"):
        ref = (st.get("mjof") or {}).get("z_ref") or 10
        z = v["mf"][0]
        if z >= ref / 3:
            out.append(f"مكوّن التذبذب فوق المملكة موجب ({n1(z)} م)، فهو {BR.mf_word(z, ref)}")
    if v.get("w") and c["warm"] == 0 and not BP.favourable(v["w"][0]):
        out.append(f"مركز الحدث الدافئ عند خط الطول {ar(round(v['w'][0]))}° شرقًا، خارج القطاع الداعم فوق غرب بحر العرب وشرق أفريقيا")
    T = (W or {}).get("trough")
    if T:
        k = T["k"]
        if not T.get("cutoff") and (k.get("tip_v") or 0) > -40:
            nx = T.get("next") or {}
            out.append(f"الأخدود مركزه خارج المملكة ولا يصل منه إلى الحجاز إلا طرف ضحل ({_dam(k['tip_v'])} ديكامتر)"
                       + ("، ويخرج غدًا" if not nx.get("k") else ""))
    elif c["trough"] < 0.3:
        # a shallow trough named by the case kind is weak, not absent: say it so the summary does not contradict itself
        Rk = R2.case_kind(st, day0)[2]
        out.append("الأخدود العلوي ضحل ضعيف الأثر" if any("ضحل" in x for x in Rk) else "لا أخدود علوي مؤثر")
    dry = [n for n in ORDER if (pw_of(st, day0, n) or 100) < 100]
    if dry:   # a long list of regions reads badly: say "all" or "most" instead (wording only)
        out.append("الهواء جاف على جميع مناطق المملكة" if len(dry) == len(ORDER) else
                   f"الهواء جاف على معظم المناطق ({ar(len(dry))} من {ar(len(ORDER))})" if len(dry) >= 9 else
                   f"الهواء جاف على {jl(dry)}")
    return out[:5]


def summary(st, rs, regs, day0):
    import bigreport as BR
    W = None
    try:
        W = cold_wave(st, day0)
    except Exception as e:  # noqa: BLE001
        print("report3: cold wave failed:", repr(e), flush=True)
    import bigreport as BR0
    f00 = BR0._day_factors(st, day0)
    lab0, T0, R0 = R2.case_kind(st, day0)
    sc0 = BR0.strength(st, day0)
    # the drivers alone, not the GFS rain spread (Fahad, 19 Nov 2026: nothing from the model in the reading); the
    # 10-19 Nov test: 3.3-3.4 on the two wide days (28-32 % of the Kingdom wet), 2.9 on 8 %, under 2.5 on 0.1-4 %
    ws0 = sc0["total"]
    rows = region_reading(st, rs, regs, day0, W, big=min(1.0, ws0 / 3))
    rows.sort(key=lambda r: (r["name"] != "مكة المكرمة", -r["pct"]))
    B = []
    # a. the strength of the case and our estimate of the rain spread over the Kingdom (from the reading, not a model)
    sc = BR.strength(st, day0)
    c = BR.combined(st, day0, day0)
    ws = sc["total"]
    f0 = BR._day_factors(st, day0)
    label, Tt, Rr = R2.case_kind(st, day0)
    tot = sum(r["area"] or 0 for r in rows)
    ksa_area = 2.15e6
    spread = sum((r["area"] or 0) * r["cover"] for r in rows) / ksa_area
    # the band from the strength of the drivers and the wide lift together (10-19 Nov test, see above)
    sfr = sum((r["area"] or 0) * r.get("strat", 0) for r in rows) / ksa_area
    spread = max(spread, 0.15 if ws >= 3.0 else 0.05 if ws >= 2.6 else 0.0, sfr)
    band = "محدود، أقل من ٣٪ من مساحة المملكة" if spread < 0.03 else "متوسط، بين ٣ و١٠٪" if spread < 0.10 else "واسع، أكثر من ١٠٪"
    B.append({"p": f"قوة الحالة {n1(ws)} من ٥ ({BR.grade(ws)})، وانتشار المطر المتوقع {band}. وفرصة أن تكون حالة واسعة "
                   f"عند هذه القوة {next(t for lim, t in WIDE_CHANCE if ws < lim)} في سجل ٢٥ موسمًا."})
    if ws < 2.6:
        wk = weak_reasons(st, day0, W)
        if wk:
            B.append({"p": f"أسباب {'ضعف' if ws < 1.8 else 'توسط'} الحالة على المملكة: " + "، و".join(wk) + "."})
    sup = BR._supported(f0)
    struct = 3 if sup and ws >= 3 else 2 if sup and ws >= 1.8 else 1 if (sup or Tt or Rr) else 0
    why = []
    if Tt:
        why.append("من المداريات " + jl(Tt))
    if Rr:
        why.append("من العروض الوسطى " + jl(Rr))
    B.append({"p": f"بنية الحالة مع الصورة العامة {LEVEL4[struct]}، وتصنيفها: {label}"
                   + (f"، يسندها {'، و'.join(why)}" if why else "") + "."})
    # b. the regions where the reading finds a chance of rain
    if rows:
        rows.sort(key=lambda r: (r["name"] != "مكة المكرمة", LEVEL4.index(r["level"]) * -1))
        items = [f"{r['name']} ({'زخات متفرقة محتملة' if r['level'] == 'ضعيفة' else 'فرصة ' + r['level']})" for r in rows]
        B.append({"p": "المناطق المتأثرة بحسب حالة اليوم: " + "، و".join(items) + "."})
        # one line per place, with what makes the rain there (Fahad, 19 Nov 2026: «حاول تحدد أماكن المطر من خلال
        # دراستك لمعطيات أماكن تصادم الرياح بجميع انواعها وتوجيه الرياح العليا للسحاب والرطوبة وتأثير التبريد العلوي»)
        LVW = {"heavy": "غزيرة", "moderate": "متوسطة", "light": "خفيفة"}
        trs = []
        for r in rows:
            if r.get("vague"):
                continue
            first = True
            for k in ("heavy", "moderate", "light"):
                for pl_ in r["row"][k]:
                    trs.append([r["name"] if first else "", pl_, LVW[k], r["why"].get(pl_, "")])
                    first = False
        if trs:
            B.append({"table": {"head": ["المنطقة", "المكان", "الشدة", "السبب"], "rows": trs}})
        plains_all = [(r["name"], p_) for r in rows for p_ in r.get("plains") or []]
        if plains_all:
            B.append({"p": "فرصة على السهول: " + "، و".join(f"{p_} ({n_})" for n_, p_ in plains_all)
                           + "، إذا نزل هواء السحب البارد من الجبال مساءً إلى الهواء الحار الرطب تحتها."})
        vague = [r["name"] for r in rows if r.get("vague")]
        if vague:
            B.append({"p": f"وعلى {jl(vague)} رطوبة وتبريد علوي بلا التقاء رياح يحدد مكانًا، فالزخات هناك عابرة متفرقة."})
        for r in rows:
            if r.get("vague"):
                continue
            bits = []
            if r["trough"]:
                bits.append(f"تبريد علوي من {r['trough']}")
            if r["pw"]:
                bits.append(f"الرطوبة {ar(r['pw'])}٪ من معدلها")
            if r["cape"] >= 150:
                bits.append(f"طاقة عدم الاستقرار نحو {ar(int(round(r['cape'], -1)))} جول/كغ")
            if r["steer"]:
                bits.append(f"الرياح في الطبقات المتوسطة تدفع الخلايا {r['steer']}")
            if r.get("lw_boost"):
                bits.append("حدث دافئ قرب الأرض يعزز الحمل ويرفع الثقة")
            if bits:
                B.append({"p": f"{r['name']}: " + "، و".join(bits) + "."})
    else:
        B.append({"p": "لا تجتمع مكونات المطر على أي منطقة اليوم."})
    lwr = getattr(region_reading, "lowwarm", None) or {}
    if lwr.get("cold_regions"):
        B.append({"p": f"حدث بارد قرب الأرض فوق {jl(lwr['cold_regions'])} يكبت الحمل الحراري، فلا تُتوقع هناك عواصف ولا أمطار غزيرة، "
                       "وقد يبقى مطر خفيف واسع إن وُجد صعود طبقي (في ٣٨٣ يومًا مختبرًا ندر أن بلغ المطر ٢٠ ملم في أيام "
                       "كهذه)."})
    if lwr.get("sides"):
        where = {"low": "سهول مكة وتهامة", "high": "هضبة الطائف وحافتي الهدا والشفا"}
        lead_ = "ويمتد الحدث البارد إلى" if lwr.get("cold_regions") else "حدث بارد قرب الأرض فوق"
        B.append({"p": f"{lead_} {' و'.join(where[x] for x in lwr['sides'])}، فلا يُتوقع هناك مطر يُذكر مهما اجتمعت "
                       "المكونات الأخرى، وقد تمر زخات خفيفة (في ٣٨٢ يومًا مختبرًا لم يبلغ المطر ٢٠ ملم في أي يوم بارد "
                       "كهذا)."})
    # tonight's sea cells over the Hijaz coasts, Makkah and Al-Jumum (no trough needed; Fahad 26 Nov 2026)
    try:
        import seacell
        t = seacell.tonight(st.get("seacell"), day0)
        if t:
            B.append({"p": t})
    except Exception as e:  # noqa: BLE001
        print("sea cells (summary) failed:", repr(e), flush=True)
    if W:
        B += cold_wave_blocks(st, day0, effect=False, W=W)
        wn = {r["name"] for r in rows}
        no = [n for n in W["regions"] if n not in wn and n not in ((getattr(region_reading, "lowwarm", None) or {}).get("cold_regions") or [])]
        if no:
            B.append({"p": f"ولا يُتوقع مطر تحت الموجة على {jl(no)}، لجفاف الهواء أو غياب الرفع، فأثرها هناك برودة ورياح."})
    B.append({"note": "هذه القراءة من المكونات لا من مطر النماذج: الرطوبة، والتقاء الرياح على التضاريس، والتبريد العلوي، "
                      "وطاقة عدم الاستقرار، ورياح الطبقات المتوسطة. ودرجة كل منطقة من توافقها، ولا تُعطى «قوية» في يوم ضعيف "
                      "الصورة الكبرى، والمنطقة التي لا تلتقي عليها الرياح زخاتها محتملة فقط. أما مطر نموذجنا فمكانه الخريطة."})
    return sec("الخلاصة", "sum", B)


# ------------------------------------------------------------------ 2. Makkah
def makkah(st, rs, regs, day0):
    import makkah_story as MS
    import plains as P
    RD = MS.read(st, pending(rs))
    eds = {e["key"]: e for e in (st.get("plains") or {}).get("edges") or []}
    zs = (st.get("mstory") or {}).get("zones") or {}
    B = []
    rows = []
    # places, grouped as Fahad names them: the edges, east and north of Makkah, the harrat, Taif and its plateau, the cities
    groups = [("حافتا الهدا والشفا", ("hada", "shafa"), ("hada", "shafa")),
              ("السيل والحوية والعرفاء", ("sail",), ("sail", "hawiyah", "arfa")),
              ("الطائف", (), ("taif",)),
              ("مرتفعات شرق مكة وحراتها", (), ("east_hills",)),
              ("حرة شمنصير", ("shamnasir",), ("shamnasir",)),
              ("الشرائع والجعرانة", (), ("sharai",)),
              ("مكة", (), ("makkah",)),
              ("الجموم", (), ("jumum",))]
    for name, ekeys, zkeys in groups:
        mm = max([zs[z]["max"] for z in zkeys if z in zs] or [None]) if zs else None
        confs = [P.confidence(P.edge_named(eds[k], eds[k].get("model_rain"))[1]) for k in ekeys
                 if k in eds and P.edge_named(eds[k], eds[k].get("model_rain"))[0]]
        gfs = max([eds[k]["rain_gfs"] for k in ekeys if k in eds] or [0])
        nc = max(confs, key=lambda c: {"عالية": 2, "متوسطة": 1, "منخفضة": 0}[c]) if confs else None
        if name in ("مكة", "الجموم", "الشرائع والجعرانة"):
            ck = {"مكة": "makkah", "الجموم": "jumum", "الشرائع والجعرانة": "sharai"}[name]
            cl = (RD.get("city") or {}).get(ck)
            lv = {"rain": "مرجحة", "light": "متوسطة", "possible": "متوسطة", "unlikely": "ضعيفة"}.get(cl, "ضعيفة")
        elif nc is None and (mm is None or mm < 1):
            continue
        else:
            lv = conf_level(nc or "منخفضة", mm, gfs)
        rows.append([name, "—" if mm is None else f"{n1(mm)} ملم", lv])
    if rows:
        B.append({"table": {"head": ["المكان", "مطر نموذجنا", "الثقة"], "rows": rows}})
    B += spread_table(st, day0, "مكة المكرمة")
    # reasons, short: the meeting of the winds, the motion, the support
    why = []
    m = RD.get("meet")
    mv = RD.get("moved")
    if m:
        site = {"east": "شمال الطائف وشرقه", "east_dry": "شمال الطائف وشرقه", "edge": "على حافة الهدا والشفا"}[m[0]]
        t = f"تقف الرياح بعد الظهر {site} (قرب {m[1]})"
        if mv:
            t += "، بعد أن كانت أمس " + ("على الحافة" if mv[0] == "edge" else "شمال الطائف وشرقه")
        if m[0] == "east_dry":
            t += f"، والطاقة على الحواف أعلى ({ar(round(RD.get('cape_edge') or 0, -1))} مقابل {ar(round(RD.get('cape_east') or 0, -1))} جول/كغ) فتقوى الخلايا عليها"
        why.append(t)
    s = RD.get("steer")
    if s:
        why.append(f"وتتحرك الخلايا نحو {s['to']} بنحو {ar(round(s['speed']))} م/ث" if s["speed"] >= 3
                   else "والرياح الموجهة ضعيفة فتبقى الخلايا شبه ثابتة وينحدر هواؤها البارد مع الأودية")
    pw = pw_of(st, day0, "مكة المكرمة")
    if pw:
        why.append(f"والماء القابل للهطول {ar(pw)}٪ من معدله")
    if RD.get("trough"):
        why.append("وأخدود ضحل يبرد الطبقات العليا (" + "، ".join(RD.get("cue_aloft") or []) + ")")
    B.append({"p": "أسباب الثقة: " + "، ".join(why) + "." if why else "أسباب الثقة: مكونات الحمل الحراري على الحواف."})
    c = RD.get("city") or {}
    if c and all(c.get(k) == "unlikely" for k in ("makkah", "jumum")):
        B.append({"p": "مكة والجموم: فرصهما ضعيفة" + (f"، لأن الخلايا تتجه نحو {s['to']}" if s and s["speed"] >= 3 else "") + "."})
    B.append({"p": f"النظام: {system_word(st, day0, 'مكة المكرمة')}."})
    if pending(rs):
        B.append({"note": "يُضاف مطر نموذجنا حين يكتمل تشغيله الليلي."})
    return sec("منطقة مكة المكرمة", "makkah", B)


# ------------------------------------------------------------------ 3. the other regions
def others(st, rs, regs, day0):
    import plains as P
    eds = [e for e in (st.get("plains") or {}).get("edges") or [] if e["region"] != "مكة المكرمة"]
    prs = [r for r in (st.get("plains") or {}).get("rows") or [] if r["region"] != "مكة المكرمة"]
    covr = ((rs or {}).get("data") or {}).get("cover_regions") or {}
    names = []
    for r in regs:
        if r["name"] != "مكة المكرمة":
            names.append(r["name"])
    for e in eds:
        if P.edge_named(e, e.get("model_rain"))[0] and e["region"] not in names:
            names.append(e["region"])
    for r in prs:
        if P.named(r, r.get("model_mtn"))[0] and r["region"] not in names:
            names.append(r["region"])
    B = []
    for nm in names:
        rr = next((r for r in regs if r["name"] == nm), None)
        places, conf, mm = [], None, None
        if rr:
            w = max(rr["wins"], key=lambda w: float(str(w.get("max", "0")).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")) or 0), default=None)
            if w:
                for key in ("heavy", "moderate", "light"):
                    if w.get(key):
                        places.append(w[key])
                mm = float(str(w.get("max", "0")).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")) or 0)
        ne = [e for e in eds if e["region"] == nm and P.edge_named(e, e.get("model_rain"))[0]]
        np_ = [r for r in prs if r["region"] == nm and P.named(r, r.get("model_mtn"))[0]]
        for e in ne:
            places.append(P.short(e["name"]))
        for r in np_:
            places.append(P.short(r["name"]) if hasattr(P, "short") else r["name"])
        confs = [P.confidence(P.edge_named(e, e.get("model_rain"))[1]) for e in ne] + \
                [P.confidence(P.named(r, r.get("model_mtn"))[1]) for r in np_]
        nc = max(confs, key=lambda c: {"عالية": 2, "متوسطة": 1, "منخفضة": 0}[c]) if confs else "متوسطة"
        conf = conf_level(nc, mm)
        why = []
        if ne:
            why.append("نسيم البحر والهواء الجنوبي الرطب يصعدان الحواف")
        if np_:
            why.append("وهواء السحب البارد ينحدر مساءً إلى السهول")
        if rr:
            why.append("ونموذجنا يُظهر المطر")
        elif ne or np_:
            why.append("ونموذجنا لا يُظهره")
        pw = pw_of(st, day0, nm)
        t = f"{nm}: " + ("، ".join(dict.fromkeys(places)) if places else "أمطار محدودة")
        if why:
            why[0] = why[0].removeprefix("و")
        t += f". الثقة {conf}" + (f" ({'، '.join(why)})" if why else "")
        if pw:
            t += f"، والماء القابل للهطول {ar(pw)}٪ من معدله"
        if nm in covr and covr[nm] >= 0.001:
            t += f"، ويغطي المطر {R2.cover_pct(covr[nm])} من مساحتها"
        t += f". النظام: {system_word(st, day0, nm)}."
        B.append({"p": t})
        H = st.get("cover_hist")
        if H:
            import covhist as CH
            c = CH.compare(H, day0, nm)
            g = c["gfs"]
            if g[0] is not None:
                u = (f"الانتشار بحسب جي إف إس: اليوم {_pc(g[0])}، وأمس {_pc(g[1])}، وأول أمس {_pc(g[2])}")
                if c["peak"]:
                    u += f"، وذروة الموجة الماضية {_pc(c['peak'][1])} ({ar_date(c['peak'][0])})"
                B.append({"p": u + "."})
    if not B:
        B.append({"p": "لا أمطار تُذكر على بقية المناطق."})
    else:
        dry = [n for n in BOX_OF if n not in names and n != "مكة المكرمة"]
        # the same reading as the summary: moist regions under the upper cold wave may get showers the models miss
        try:
            W = cold_wave(st, day0)
            maybe = [n for n in dry if W and n in W["regions"] and (pw_of(st, day0, n) or 0) >= 110]
        except Exception:  # noqa: BLE001
            maybe = []
        if maybe:
            B.append({"p": f"وتُحتمل زخات متفرقة على {jl(maybe)} تحت الموجة العلوية الباردة فوق هواء رطب، "
                           "والنموذجان لا يُظهرانها، فالثقة متوسطة."})
            dry = [n for n in dry if n not in maybe]
        if dry:
            B.append({"p": "ولا أمطار تُذكر على " + jl(dry) + "."})
    return sec("المناطق الأخرى", "regions", B)


# ------------------------------------------------------------------ 4. the big picture (Fahad, 18 Nov 2026)
def _factor_rows(st, day0):
    """[(element, value today, effect)] with effect in داعم / يكبح / محايد, each from its own number"""
    import bigreport as BR
    B = BR.B
    rows = []
    m = B.rmm_on(st, day0)
    if m:
        if m["amp"] < 1:
            ef = "محايد"
        elif m["phase"] in B.WET_PHASES and st.get("wet_season"):
            ef = "داعم ضعيف" if m["phase"] == 2 else "داعم"
        else:
            ef = "يكبح"
        rows.append(["التذبذب المداري (مادن-جوليان)", f"الطور {ar(m['phase'])}، شدة {num(m['amp'], 1)}", ef])
    mf = BR._mf(st, day0)
    if mf:
        ref = (st.get("mjof") or {}).get("z_ref") or 10
        z = mf[0]
        ef = "داعم" if z <= -ref / 3 else "يكبح" if z >= ref / 3 else "محايد"
        rows.append(["مكوّن التذبذب عند ٨٠٠ هكتوباسكال", f"{n1(z)} م", ef])
    for fam, name in (("ros", "موجات روسبي الاستوائية"), ("kel", "موجات كلفن")):
        x = BR._tw(st, day0, fam)
        if x:
            ef = "داعم" if x[0] <= -x[1] / 3 else "يكبح" if x[0] >= x[1] / 3 else "محايد"
            rows.append([name, f"{n1(x[0])} مليون م²/ث", ef])
    w = next((x for x in B.warm(st["hov"]) if x[0] == day0.isoformat()), None) if st.get("hov") else None
    if w:
        ok = BR.warm_ok(w[1], w[2])
        rows.append(["الحدث الدافئ (التباعد العلوي)", f"فوق {B.region_name(w[1])}",
                     "داعم" if ok else "محايد"])
    row = next((r for r in st.get("pw", []) if r["d"] == day0.isoformat()), None)
    if row:
        ks = [q for q in R2.BOX_NAME if q in row]
        if ks:
            q = max(ks, key=lambda q: row[q]["pct"])
            p0 = row[q]["pct"]
            ef = "داعم بقوة (مد رطوبي)" if p0 >= 150 else "داعم" if p0 >= 110 else "يكبح" if p0 < 90 else "محايد"
            rows.append(["الرطوبة", f"{ar(p0)}٪ من معدلها فوق {R2.BOX_NAME[q]}", ef])
    wv = next((x for x in st.get("waves", []) if x["d"] == day0.isoformat()), None)
    if wv and "trough" in wv and wv["trough"]["v"] <= -25:
        dam = -wv["trough"]["v"] / 10
        rows.append(["الأخدود عند ٥٠٠ هكتوباسكال", f"{BR.trough_word(dam)} فوق {wv['trough']['area']}", "داعم"])
    elif wv and "ridge" in wv and 35 <= wv["ridge"]["lon"] <= 56:
        rows.append(["الأخدود عند ٥٠٠ هكتوباسكال", "مرتفع فوق المملكة", "يكبح"])
    else:
        rows.append(["الأخدود عند ٥٠٠ هكتوباسكال", "لا أخدود يُعتد به", "محايد"])
    pt = st.get("pattern") or {}
    if pt.get("day") == day0.isoformat() and "west" in pt.get("boxes", {}):
        a = pt["boxes"]["west"]["anom"]
        ef = "داعم" if a <= -0.5 else "يكبح" if a >= 0.5 else "محايد"
        dev = "قريبة من معدلها" if abs(a) < 0.3 else f"{'أبرد' if a < 0 else 'أدفأ'} من معدلها بـ{num(abs(a), 1)}°"
        rows.append(["حرارة ٥٠٠ هكتوباسكال فوق الحجاز (التبريد العلوي)", dev, ef])
    return rows


def big_picture(st, rs, regs, day0):
    import bigreport as BR
    rows = _factor_rows(st, day0)
    pro = [r[0] for r in rows if r[2].startswith("داعم")]
    con = [r[0] for r in rows if r[2] == "يكبح"]
    sc = BR.strength(st, day0)
    c = BR.combined(st, day0, day0)
    ws = BR.wave_score(st, day0, day0, sc, None if c is None else c["ksa"])["score"]
    conf = round(20 * ws)
    f0 = BR._day_factors(st, day0)
    if BR._supported(f0) and ws >= 1.8:
        verdict = "داعمة"
    elif BR._supported(f0) or len(pro) > len(con):
        verdict = "داعمة دعمًا ضعيفًا لا يكفي لحالة واسعة"
    else:
        verdict = "غير داعمة"
    B = [{"p": f"الصورة الكبرى اليوم {verdict}" + (f"، بفعل {jl(pro)}" if pro else "")
               + (f"، ويكبحها {jl(con)}" if con else "") + "."},
         {"p": f"نسبة الثقة في انتشار المطر على المملكة اليوم: {ar(conf)}٪."},
         {"table": {"head": ["العنصر", "قيمته اليوم", "أثره"], "rows": rows}}]
    miss = []
    if "surge" not in {k for k, _ in f0}:
        miss.append("الرطوبة دون حد المد الرطوبي (١٥٠٪)")
    if "trough" not in {k for k, _ in f0}:
        miss.append("لا أخدود يُعتد به")
    if con:
        miss.append(f"{jl(con)} {'يكبح' if len(con) == 1 else 'تكبح'}")
    need = "" if verdict == "داعمة" or not miss else f"، لأن {jl(miss)}."
    B.append({"p": f"الخلاصة: الصورة العامة {verdict}{need or '.'}"})
    return sec("الصورة الكبرى", "bigpic", B)


# ------------------------------------------------------------------ 5. the waves to come
def _strength_word(w):
    cov = w.get("cover") or 0
    return ("غزيرة" if cov >= 0.15 or w["top"] >= 3.5 else
            "متوسطة" if cov >= 0.05 or w["top"] >= 2.6 else "خفيفة")


def lowwarm_spell(st, a, b):
    """the low-level warm/cold event around a wave (Fahad, 20 Nov 2026: «في أقرب موجة لا تنسى تضيف الحدث الدافئ ضمن
    نقاط قوة الموجة وكم تستمر الموجة من أيام مع معززاتها»): the warm run of days (3+ regions at I >= 1, or Makkah low
    ground) that overlaps the wave days a..b, whole even where it runs past them, and the cold regions inside the
    wave (I <= -1, which cancels the convective rain there). -> dict or None"""
    from datetime import date, timedelta
    lw = st.get("lowwarm") or {}
    ds = [date.fromisoformat(x) for x in lw.get("days") or []]
    R = lw.get("regions") or {}
    if not ds or not R:
        return None
    low = lw.get("low") or []
    warm_on = {}
    for k, d in enumerate(ds):
        w = [n for n, v in R.items() if k < len(v) and v[k] is not None and v[k] >= LW_WARM]
        mk = k < len(low) and low[k] is not None and low[k] >= LW_WARM
        if len(w) >= 3 or mk:
            warm_on[d] = w
    # the whole run of consecutive warm days that has the most days inside the wave (it may start before or end after)
    blocks, cur = [], []
    for d in sorted(warm_on):
        if cur and (d - cur[-1]).days == 1:
            cur.append(d)
        else:
            cur = [d]
            blocks.append(cur)
    blocks = [x for x in blocks if any(a <= y <= b for y in x)]
    run = max(blocks, key=lambda x: sum(1 for y in x if a <= y <= b)) if blocks else []
    out = {"warm": None, "cold": []}
    if run:
        cnt = {}
        for d in run:
            for n in warm_on[d]:
                cnt[n] = cnt.get(n, 0) + 1
        regs = [n for n, c in sorted(cnt.items(), key=lambda x: -x[1]) if c * 2 >= len(run)]
        out["warm"] = {"start": run[0], "end": run[-1], "regions": regs, "last": run[-1] == ds[-1],
                       "in_wave": sum(1 for x in run if a <= x <= b)}
    cold = {}
    for k, d in enumerate(ds):
        if a <= d <= b:
            for n, v in R.items():
                if k < len(v) and v[k] is not None and v[k] <= LW_COLD:
                    cold[n] = cold.get(n, 0) + 1
    out["cold"] = [n for n, c in sorted(cold.items(), key=lambda x: -x[1])]
    return out if (out["warm"] or out["cold"]) else None


def _lw_pro(sp):
    """the warm event as one of the wave's strengths, and the cold one as a brake"""
    pro, con = [], []
    if sp and sp["warm"]:
        w = sp["warm"]
        rg = w["regions"][:5]
        pro.append("حدث دافئ قرب الأرض" + (f" فوق {jl(rg)}" if rg else " فوق مكة المكرمة وتهامة")
                   + (" وغيرها" if len(w["regions"]) > 5 else ""))
    if sp and sp["cold"]:
        con.append(f"حدث بارد قرب الأرض في بعض أيامها فوق {jl(sp['cold'][:4])} يلغي المطر الحملي هناك")
    return pro, con


def _days_word(n):
    return "يومًا واحدًا" if n == 1 else "يومين" if n == 2 else f"{ar(n)} أيام" if n <= 10 else f"{ar(n)} يومًا"


def hijaz_regions(st, regions, d0, d1):
    """the «west» moisture box of a wave's regions written as Makkah and Madinah regions and their coasts apart
    (hijaz.py, Fahad 25 Nov 2026); the list is left as it was if that fails"""
    import bigreport as BR
    west = BR.BOX_NAME["west"]
    if west not in regions:
        return regions
    try:
        import hijaz
        parts = hijaz.wave_parts(st, d0, d1)
    except Exception as e:  # noqa: BLE001
        print("hijaz parts failed:", repr(e), flush=True)
        return regions
    out = []
    for r in regions:
        out.extend(parts if r == west else [r])
    return list(dict.fromkeys(out))


PULSE_CORE, PULSE_COVER = 20.0, 0.01   # an ingredients day is active from core 20/100 or 1 % of the Kingdom


def ingr_pulses(st, wl, day0, fac):
    """each wave window of the big drivers cut to its pulses of rain-making ingredients (Fahad, 26 Nov 2026: the
    window of 28 Nov-10 Dec with its peak after 8 days and spread under 1 % contradicted the ingredients reading
    of 30 Nov at 5 %). The drivers tell when the setting supports rain; the days, the peak (the widest day), the
    spread and the areas come from the nightly ingredients rows (refwave), never from model rain."""
    import bigreport as BR
    import refwave as RW
    from datetime import date as _d, timedelta
    rows = {r["d"]: r for r in st.get("wave_rain") or [] if r.get("kind") == "ingr"}
    if not rows:
        return wl
    act = lambda d: (lambda r: r is not None and ((r.get("core") or 0) >= PULSE_CORE or (r.get("cover") or 0) >= PULSE_COVER))(rows.get(d.isoformat()))
    out = []
    for w in wl:
        wd = [w["start"] + timedelta(days=k) for k in range((w["end"] - w["start"]).days + 1)]
        runs = BR._runs(wd, act)
        if not runs:
            # no day of the window gathers the ingredients yet: keep the window, its spread from the ingredients
            cv = {d: (rows.get(d.isoformat()) or {}).get("cover") or 0 for d in wd}
            sc = {d: BR.wave_score(st, d, day0, BR.strength(st, d), cv[d])["score"] for d in wd}
            w["peak"] = max(wd, key=lambda d: sc[d])
            w["cover"], w["top"] = max(cv.values()), sc[w["peak"]]
            w["pro"], w["con"] = BR.wave_pro_con(st, w["peak"])
            out.append(w)
            continue
        for k, (a, b) in enumerate(runs):
            m = RW.wave_metrics(list(rows.values()), a, b)
            pk = _d.fromisoformat(m["d"])
            c = BR.strength(st, pk)
            pro, con = BR.wave_pro_con(st, pk, c)
            pd = [a + timedelta(days=j) for j in range((b - a).days + 1)]
            allk = set().union(*({x for x, _ in fac.get(d, [])} for d in pd))
            T, R = allk & {"mjo", "warm"}, allk & {"trough", "cold"}
            kind = "mixed" if T and R else "tropical" if T else "troughs" if R else w["kind"]
            regs = [RW.label(g) for g in m["regions"] if g["cover"] >= 0.05 or g["w"] >= 30][:5] or RW.strongest(m)
            out.append({"start": a, "end": b, "peak": pk, "cover": m.get("cover") or 0,
                        "top": BR.wave_score(st, pk, day0, c, m.get("cover") or 0)["score"], "drivers": c["total"],
                        "kind": kind, "regions": regs, "pro": pro, "con": con, "ingr": True,
                        # the window of supportive drivers, said once after the last pulse
                        "win": (w["start"], w["end"]),
                        "window": (w["start"], w["end"]) if k == len(runs) - 1 else None})
    return out



def north_break(st, w):
    """the blocked trough read from its axis and the ridge east of it (Fahad's «كسير شمالي», 26 Nov 2026): the trough
    stays west of the Red Sea while a ridge over Iran and the Gulf holds it, so its northern half breaks off to the
    north-east with the moisture and its southern tail lags west, with no cut-off low over the Red Sea for Makkah"""
    from datetime import timedelta
    wd = {(w["start"] + timedelta(days=k)).isoformat() for k in range((w["end"] - w["start"]).days + 1)}
    tips = []
    for sy in st.get("troughs") or []:
        for x in sy.get("days") or []:
            if x["d"] in wd and x.get("tip") and 20 <= x["tip"][1] <= 45:
                tips.append(x)
    ridges = [x["ridge"] for x in st.get("waves") or [] if x["d"] in wd and x.get("ridge") and x["ridge"]["lon"] >= 48]
    if not tips:
        return None
    lon_max = max(x["tip"][1] for x in tips)
    lat_min = min(x["tip"][0] for x in tips)
    rv = max([r["v"] for r in ridges] or [0])
    if lon_max <= 34 and rv >= 50:
        lo = sorted({int(round(x["tip"][1])) for x in tips})
        t = (f"نمط الموجة: الأخدود محجوز، يقف طرفه عند خط الطول {ar(lo[0])}" + (f" إلى {ar(lo[-1])}" if lo[-1] != lo[0] else "")
             + f" شرقًا غرب البحر الأحمر، والمرتفع فوق إيران والخليج يبلغ {ar(int(round(rv)))} م فيصده عن التقدم. فالأرجح "
             f"كسير شمالي: ينكسر نصفه الشمالي ويُسحب نحو الشمال الشرقي حاملًا المد الرطوبي إلى {jl(w['regions'])}، ويبقى "
             f"ذيله الجنوبي فوق مصر عند خط العرض {ar(int(round(lat_min)))} شمالًا تقريبًا، فلا يُتوقع منه منخفض معزول فوق "
             "البحر الأحمر يبلغ مكة، ونصيب مكة وسواحل الحجاز من هذه الموجة الخلايا البحرية الليلية.")
        return t
    if lon_max > 34 and lat_min <= 24:
        return ("نمط الموجة: يعبر طرف الأخدود البحر الأحمر جنوبًا حتى خط العرض "
                f"{ar(int(round(lat_min)))} شمالًا، فيُتابع احتمال انفصال منخفض معزول فوقه، وهو أهم ما يرفع فرص مكة.")
    return None



def wave_set(st, day0):
    """the waves to come: (wave list, forecast days, day scores, day factors), shared by waves() and report4"""
    import bigreport as BR
    from datetime import timedelta
    days = [day0 + timedelta(days=k) for k in range(16)]
    fac = {d: BR._day_factors(st, d) for d in days}
    cur_end = day0 - timedelta(days=1)
    if BR._supported(fac[day0]):
        cur_end = day0
        for d in days[1:]:
            if BR._supported(fac[d]):
                cur_end = d
            else:
                break
    _, last = BR.drivers_timeline(st, day0, days)
    days = [d for d in days if d <= last]
    score = {}
    ir0 = {r["d"]: r for r in st.get("wave_rain") or [] if r.get("kind") == "ingr"}
    for d in days:
        # the spread of the ingredients reading, never model rain (doctrine, Fahad 25 Nov 2026)
        c = (ir0.get(d.isoformat()) or {}).get("cover") if ir0 else None
        score[d] = BR.wave_score(st, d, day0, BR.strength(st, d), c)["score"]
    wl = ingr_pulses(st, BR.wave_list(st, day0, days, fac, cur_end), day0, fac)
    # weak signs outside the waves: a trough over the Red Sea or the Kingdom (15 m or deeper)
    inw = lambda d: any((w.get("win") or (w["start"], w["end"]))[0] <= d <= (w.get("win") or (w["start"], w["end"]))[1] for w in wl)
    sig = []
    for d in days[1:]:
        wv = next((x for x in st.get("waves", []) if x["d"] == d.isoformat()), None)
        tr = (wv or {}).get("trough")
        if tr and tr["v"] <= -15 and ("المملكة" in tr["area"] or "البحر الأحمر" in tr["area"]) and not inw(d):
            if sig and (d - sig[-1][1]).days == 1 and sig[-1][2] == tr["area"]:
                sig[-1][1] = d
                sig[-1][3] = min(sig[-1][3], tr["v"])
            else:
                sig.append([d, d, tr["area"], tr["v"]])
    for a, b, area, v in sig:
        # the spread from the ingredients rows, not from model rain (doctrine, Fahad 25 Nov 2026)
        ir = {r["d"]: r for r in st.get("wave_rain") or [] if r.get("kind") == "ingr"}
        cv = max([(ir.get(d.isoformat()) or {}).get("cover") or 0 for d in days if a <= d <= b] or [0])
        pk = max([d for d in days if a <= d <= b], key=lambda d: score[d])
        wl.append({"start": a, "end": b, "peak": pk, "top": score[pk], "cover": cv,
                   "kind": "troughs", "regions": [area], "pro": [f"أخدود {BR.trough_word(-v / 10)} فوق {area}"], "con": [],
                   "sign": BR.trough_word(-v / 10)})
    wl.sort(key=lambda w: w["start"])
    for w in wl:
        if not w.get("ingr"):   # the ingredients' areas are already parts of regions
            w["regions"] = hijaz_regions(st, w["regions"], w["start"], w["end"])
        try:
            w["lw"] = lowwarm_spell(st, w["start"], w["end"])
        except Exception as e:  # noqa: BLE001
            print("lowwarm spell failed:", repr(e), flush=True)
            w["lw"] = None
        p_, c_ = _lw_pro(w["lw"])
        w["pro"] = list(w.get("pro") or []) + p_
        w["con"] = list(w.get("con") or []) + c_
    return wl, days, score, fac


def waves(st, rs, regs, day0):
    """the study of the waves to come (Fahad, 18 Nov 2026 evening: «تكلم عن أقرب موجة ترصدها ومدى ثقتك بالموجة ومتى
    أقرب فترة خصب واسعة جدا على الجزيرة العربية، ونسب كل موجة وتوقعاتك وثقتك بها، وكم وأي موجة ترصدها، ما هي الديار
    التي تتأثر بها»)"""
    import bigreport as BR
    from datetime import timedelta
    wl, days, score, fac = wave_set(st, day0)
    KIND = {"mixed": "مدارية أخدودية", "tropical": "مدارية", "troughs": "أخدودية"}
    B = []
    span_of = lambda w: (ar_date(w["start"]) if w["start"] == w["end"] else R2.ar_span(w["start"], w["end"]).removeprefix("من "))
    # whole percents, as in the reference comparison below, so the two never read differently (5.2 % vs 5 %)
    spread_of = lambda w: (f"نحو {ar(int(round(100 * w['cover'])))}٪ من المملكة" if w.get("cover") and w["cover"] >= 0.01 else "أقل من ١٪ من المملكة")
    full = [w for w in wl if not w.get("sign")]
    nsig = len(wl) - len(full)
    sig_t = ("إشارة أخدود ضعيفة واحدة" if nsig == 1 else "إشارتي أخدود ضعيفتين" if nsig == 2
             else f"{ar(nsig)} إشارات أخدود ضعيفة") if nsig else ""
    if full:
        cnt = ("نرصد موجة مطرية واحدة" if len(full) == 1 else "نرصد موجتين مطريتين" if len(full) == 2
               else f"نرصد {ar(len(full))} موجات مطرية" if len(full) <= 10 else f"نرصد {ar(len(full))} موجة مطرية")
        cnt += f" و{sig_t}" if sig_t else ""
    else:
        cnt = "لا نرصد موجة مطرية واسعة" + (f"، بل {sig_t}" if sig_t else "")
    B.append({"p": f"حتى {ar_date(days[-1])}، وهو أقصى ما يغطيه التوقع، {cnt}."})
    if wl:
        rows = []
        for w in wl:
            lead = (w["peak"] - day0).days
            rows.append([span_of(w), KIND[w["kind"]] + (f" ({w['sign']})" if w.get("sign") else ""),
                         f"{ar(round(20 * w['top']))}٪", spread_of(w), jl(w["regions"]), BR.confidence(lead)])
        B.append({"table": {"head": ["الفترة", "النوع", "القوة", "الانتشار", "المناطق", "الثقة"], "rows": rows}})
        # the nearest
        w = wl[0]
        lead = (w["peak"] - day0).days
        t = (f"{'أقرب إشارة' if w.get('sign') else 'أقرب موجة'}: {span_of(w)}، {KIND[w['kind']]}، قوتها {n1(w['top'])} من ٥ ({ar(round(20 * w['top']))}٪، "
             f"{BR.grade(w['top'])})، وانتشارها المتوقع {spread_of(w)}، والمناطق المتأثرة بها: {jl(w['regions'])}. "
             f"والثقة في توقيتها {BR.confidence(lead)} لأن ذروتها " + ("غدًا" if lead <= 1 else f"بعد {_days_word(lead)}"))
        if w.get("pro"):
            t += f"؛ يسندها {jl(w['pro'])}"
        if w.get("con"):
            t += f"، ويكبحها {jl(w['con'])}"
        B.append({"p": t + "."})
        # the nearest real wave too when the nearest is only a weak sign, and how long each lasts with its boosters
        nw = next((x for x in wl if not x.get("sign")), None)
        if nw is not None and nw is not w:
            ld = (nw["peak"] - day0).days
            t = (f"أقرب موجة مطرية: {span_of(nw)}، {KIND[nw['kind']]}، قوتها {n1(nw['top'])} من ٥ "
                 f"({ar(round(20 * nw['top']))}٪، {BR.grade(nw['top'])})، وانتشارها المتوقع {spread_of(nw)}، "
                 f"والمناطق المتأثرة بها: {jl(nw['regions'])}، والثقة في توقيتها {BR.confidence(ld)}")
            if nw.get("pro"):
                t += f"؛ يسندها {jl(nw['pro'])}"
            if nw.get("con"):
                t += f"، ويكبحها {jl(nw['con'])}"
            B.append({"p": t + "."})
        for x in [w] + ([nw] if nw is not None and nw is not w else []):
            B.append({"p": wave_length(x)})
            win = x.get("window")
            if win and win[1] > x["end"] and not any(y["start"] > x["end"] for y in wl if not y.get("sign")):
                B.append({"p": f"وتبقى العوامل الكبرى داعمة بعدها حتى {ar_date(win[1])}، لكن مكونات الهطول لا تجتمع "
                               "في تلك الأيام بعد في توقع الليلة، فتُتابع كل ليلة."})
        # the pattern of the wave and the night sea cells of the Hijaz coasts (Fahad, 26 Nov 2026: «ماذا عن النظام
        # الحملي والتخاريج البحرية» … «ما هي فرص الكسير الشمالي»)
        try:
            t = north_break(st, nw if nw is not None else w)
            if t:
                B.append({"p": t})
        except Exception as e:  # noqa: BLE001
            print("north break failed:", repr(e), flush=True)
        try:
            import seacell
            if st.get("seacell"):
                B.append({"p": seacell.coming(st["seacell"], day0 + timedelta(days=1), day0 + timedelta(days=7))})
        except Exception as e:  # noqa: BLE001
            print("sea cells (waves) failed:", repr(e), flush=True)
        try:
            import analogs
            t = analogs.text(st.get("analogs"), day0)
            if t:
                B.append({"p": t})
        except Exception as e:  # noqa: BLE001
            print("analogs (waves) failed:", repr(e), flush=True)
        # against the reference wave (Fahad, 25 Nov 2026)
        try:
            t = ref_compare(st, nw if nw is not None else w, day0)
            if t:
                B.append({"p": t})
                # its map (drawn by the nightly run, refwave.draw_wave; Fahad 25 Nov 2026: «ارسم صورة المملكة كخريطة
                # وحدد دائرة على المنطقة المذكورة»)
                B.append({"img": "refwave.png", "v": st.get("cycle") or "",
                          "alt": "خريطة أقوى مناطق هطول الموجة القادمة مقارنة بالموجة المرجعية"})
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("reference comparison failed:", repr(e), flush=True)
    # the next very wide fertile spell over Arabia: tropical and trough support together, several days, strong
    nw0 = next((x for x in wl if not x.get("sign")), None)
    fert = next((w for w in wl if w["kind"] == "mixed" and (w["end"] - w["start"]).days >= 2 and w["top"] >= 2.6), None)
    if fert:
        conf = BR.confidence((fert["start"] - day0).days)
        if any(fert is x for x in wl[:1]) or fert is nw0:
            # the same spell as the wave just described: do not repeat its supports (Fahad, 23 Nov 2026)
            B.append({"p": "وهذه الموجة نفسها هي أقرب فترة خصب واسعة على الجزيرة العربية، إذ يجتمع فيها الدعم المداري "
                           f"والأخدودي عدة أيام، والثقة في بدايتها {conf}."})
        else:
            B.append({"p": f"أقرب فترة خصب واسعة على الجزيرة العربية: {R2.ar_span(fert['start'], fert['end'])}، قوتها "
                           f"{n1(fert['top'])} من ٥، يتوافق عليها {jl(fert['pro'])}، والثقة في بدايتها {conf}."})
        if not any(fert is x for x in wl[:1]) and fert is not next((x for x in wl if not x.get("sign")), None):
            B.append({"p": wave_length(fert)})
    else:
        # where the support comes back: the MJO in a supportive phase with its component supportive
        ref = (st.get("mjof") or {}).get("z_ref") or 10
        back = [d for d in days[1:] if "mjo" in {k for k, _ in fac[d]} and (BR._mf(st, d) or [0])[0] <= -ref / 3]
        t = f"لا تظهر فترة خصب واسعة على الجزيرة العربية حتى {ar_date(days[-1])}"
        try:   # the seasonal outlook may see one coming from the MJO: say so, do not contradict it
            import season
            o_ = season.outlook(st, day0) if st.get("wet_season") else None
            sp_ = o_ and o_["spell"]
        except Exception:  # noqa: BLE001
            sp_ = None
        if sp_ and sp_[0] <= days[-1]:
            t = (f"لم تكتمل بعد في توقع الأيام القادمة عوامل فترة خصب واسعة على الجزيرة العربية حتى {ar_date(days[-1])}، "
                 f"لكن النظرة الموسمية أعلاه ترجّح بدايتها نحو {ar_date(sp_[0], weekday=False)} مع دخول التذبذب أطوارنا "
                 "الداعمة، فتُتابع كل ليلة")
            back = []
        if back:
            pk = max(back, key=lambda d: score[d])
            t += (f"؛ وأول ملامح عودة الدعم المداري {R2.ar_span(back[0], back[-1]) if len(back) > 1 else ar_date(back[0])}: "
                  f"التذبذب في طور داعم ومكوّنه داعم، وقوة الأيام {n1(score[pk])} من ٥ في أحسنها، فهي بداية دورة جديدة "
                  f"لا موجة خصب بعد، والثقة {BR.confidence((back[0] - day0).days)}")
        B.append({"p": t + "."})
    B.append({"note": "القوة من ٥ (والنسبة ٢٠٪ لكل درجة) تجمع العوامل الكبرى وانتشار المطر المقدّر من مكونات الجو. "
                      "الثقة عالية حتى ٥ أيام، ومتوسطة حتى ١٠ أيام، ومنخفضة بعدها. وتُحدّث كل ليلة."})
    # the seasonal outlook first (Fahad, 19 Nov 2026: «اجعلها داخل تبويب أقرب موجة قادمة وغيرها الى النظرة الموسمية
    # وأقرب موجة قادمة»); a failure leaves the waves part alone
    try:
        import season
        sb = season.blocks(st, day0) if st.get("wet_season") else []
    except Exception as e:  # noqa: BLE001
        print("season outlook failed:", repr(e), flush=True)
        sb = []
    if sb:
        B = sb + [{"h": "أقرب موجة قادمة"}] + B
        return sec("النظرة الموسمية وأقرب موجة قادمة", "waves", B)
    return sec("الموجات القادمة", "waves", B)


def _pct(x):
    return f"{ar(round(100 * x))}٪" if x >= 0.01 else "أقل من ١٪"


def _mm(x):
    return f"{ar(int(round(x)))} ملم"


def ref_compare(st, w, day0):
    """the coming wave against the reference wave of strong, wide rain (refwave.py): its strongest rain areas, its
    strength and its spread over the Kingdom, from the reading of the ingredients for both (never model rain;
    Fahad, 25 Nov 2026)"""
    import refwave as RW
    from datetime import date as _d
    ref = st.get("ref_wave") or RW.current(None)
    rows = [r for r in st.get("wave_rain") or [] if r.get("kind") == "ingr"]
    if not ref or not rows:
        return None
    m = RW.wave_metrics(rows, w["start"], w["end"])
    if m is None:
        return None
    rd = _d.fromisoformat(ref["d"])
    nm = "الإشارة" if w.get("sign") else "الموجة"
    sp_ = R2.ar_span(w["start"], w["end"]).removeprefix("من ").removeprefix("يوم ")
    st["ref_cmp"] = {"a": w["start"].isoformat(), "b": w["end"].isoformat(),
                     "title": f"{nm} القادمة بجانب الموجة المرجعية",
                     "head": f"{nm} القادمة: {sp_}",
                     "sub": "الألوان قوة مكونات الهطول (رطوبة ورفع وعدم استقرار) في أقوى أيام كل موجة"}
    core = lambda x: ar(int(round(x.get("core") or 0)))
    t = (f"مقارنة بالموجة المرجعية ({ar_date(rd, weekday=False)}، أقوى موجة واسعة في سجلنا: أقوى هطولها في "
         f"{jl(RW.strongest(ref))}، وقوة مكونات الهطول في قلبها {core(ref)} من ١٠٠، وانتشارها المقدّر "
         f"{_pct(ref['cover'])} من المملكة): ")
    if m["cover"] < 0.01:
        t += (f"لا تجتمع في هذه {nm} حتى الآن الرطوبة والرفع وعدم الاستقرار على أكثر من ١٪ من المملكة، وقوة مكوناتها في "
              f"قلبها {core(m)} من ١٠٠، فهي أضعف بكثير وأضيق من المرجعية")
    else:
        pk = _d.fromisoformat(m["d"])
        rc, ri = m["cover"] / max(ref["cover"], 1e-3), (m.get("core") or 0) / max(ref.get("core") or 0, 0.1)
        cw = ("أوسع من المرجعية" if rc >= 1.15 else "قريب من انتشار المرجعية" if rc >= 0.85 else
              "نحو نصف انتشار المرجعية" if 0.4 <= rc < 0.6 else f"نحو {ar(round(100 * rc))}٪ من انتشار المرجعية"
              if rc >= 0.15 else "أضيق بكثير من المرجعية")
        iw = ("أقوى من المرجعية" if ri >= 1.1 else "قريبة من المرجعية" if ri >= 0.9 else
              "نحو نصف قوة المرجعية" if 0.4 <= ri < 0.6 else f"نحو {ar(round(100 * ri))}٪ من قوة المرجعية"
              if ri >= 0.25 else "أضعف بكثير من المرجعية")
        t += (f"تجتمع مكونات الهطول في هذه {nm} أقوى ما تجتمع فوق {jl(RW.strongest(m))}، وأوسع أيامها {ar_date(pk)}؛ "
              f"وقوة مكوناتها في قلبها {core(m)} من ١٠٠، فهي {iw}؛ وانتشارها المقدّر {_pct(m['cover'])} من المملكة، "
              f"فانتشارها {cw}")
        big = RW.score(m) / max(RW.score(ref), 1e-3)
        t += ("، وهي في الجملة أقوى من المرجعية، فإن تحققت صارت هي المرجع الجديد" if big >= 1.1 else
              "، وهي في الجملة قريبة من المرجعية" if big >= 0.8 else
              "، وهي في الجملة أضعف من المرجعية")
        if (pk - day0).days > 7:
            t += "، والمقارنة تقريبية لبعد الموجة وتتضح كلما اقتربت"
    return (t + ". (القراءة من مكونات الجو لا من مطر النماذج: الرطوبة في عمود الهواء وفي المستوى المتوسط، والبرودة "
            "والأخاديد في الأعلى، وتباعد الرياح العليا، والتقاء الرياح قرب الأرض، وعدم الاستقرار؛ وفي اختبارها على "
            "أيام ١٠ إلى ١٨ نوفمبر قدّرت انتشار ١٠ نوفمبر ١٢٪ والمرصود ١٣٪، وحددت غرب نجد والقصيم كما رُصد.)")


def wave_length(w):
    """how long the wave lasts and how long its low-level warm booster lasts with it"""
    n = (w["end"] - w["start"]).days + 1
    nm = "الإشارة" if w.get("sign") else "الموجة"
    t = f"تستمر {nm} {_days_word(n)}" + (f" ({span_of_(w)})" if n > 1 else f" ({ar_date(w['start'])})")
    sp = w.get("lw")
    if sp and sp["warm"]:
        h = sp["warm"]
        m = (h["end"] - h["start"]).days + 1
        sp_t = R2.ar_span(h["start"], h["end"]) if m > 1 else ar_date(h["start"])
        if h.get("last"):
            sp_t += "، أي حتى نهاية التوقع"
        before, after = (w["start"] - h["start"]).days, (h["end"] - w["end"]).days
        if before <= 0 and after <= 0 and h["in_wave"] < n:
            t += f"، ويعززها الحدث الدافئ قرب الأرض {_days_word(m)} من أيامها ({sp_t.removeprefix('من ')})"
        else:
            t += ("، ويرافقها حدث دافئ قرب الأرض طوال أيامها" if before == 0 and after == 0 else
                  f"، ويرافقها حدث دافئ قرب الأرض {sp_t if m > 1 else 'يوم ' + sp_t}")
        if before > 0 or after > 0:
            # say once how long the warm setting lasts, without repeating the same number of days
            tot = (max(w["end"], h["end"]) - min(w["start"], h["start"])).days + 1
            ex = ["يبدأ قبلها " + ("بيوم واحد" if before == 1 else "بيومين" if before == 2 else f"بـ{_days_word(before)}") if before > 0 else "",
                  f"يبقى بعدها {_days_word(after)}" if after > 0 else ""]
            t += "، و" + " و".join(x for x in ex if x)
            if tot != m:
                t += f"، فتمتد بيئتها الدافئة الداعمة {_days_word(tot)}"
    elif sp and sp["cold"]:
        t += f"، ولا حدث دافئ قرب الأرض يعززها، بل حدث بارد فوق {jl(sp['cold'][:4])} يلغي المطر الحملي هناك"
    else:
        t += "، ولا حدث دافئ قرب الأرض يعززها"
    return t + "."


def span_of_(w):
    return R2.ar_span(w["start"], w["end"]).removeprefix("من ")


def build(rep, st):
    secs = rep.get("sections") or []
    day0 = date.fromisoformat(rep.get("day") or st["days"][0])
    rs = find(secs, kind="rain")
    regs = R2.rain_regions(rs)
    if not pending(rs):
        import makkah_story as MS
        em = MS.edge_model_rain(st)
        for e in (st.get("plains") or {}).get("edges") or []:
            if e["key"] in em:
                e["model_rain"] = em[e["key"]]
    out = []
    for f in (summary, waves):   # Fahad, 18 Nov 2026 evening: «خلاصة عن اليوم ودراسة عن الموجات المستقبلية»
        try:
            out.append(f(st, rs, regs, day0))
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("report3:", f.__name__, "failed:", repr(e), flush=True)
            out.append(sec(f.__name__, "error", [{"p": "تعذّر بناء هذا القسم الليلة، وسيُعاد بناؤه في التحديث القادم."}]))
    D = "١٢٣٤٥"
    for k, x in enumerate(out):
        x["heading"] = f"{D[k]}. {x['heading']}"
    new = dict(rep)
    new.update({"v": 2, "brand": R2.BRAND, "credit": R2.CREDIT, "date": ar_date(day0), "sections": out})
    return new
