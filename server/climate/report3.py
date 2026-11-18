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


def pw_of(st, day0, region):
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
        B.append({"p": "تظهر ملامح تبريد علوي ضعيف: هبوط وبرودة في الطبقات العليا دون أخدود واضح المحور فوق المملكة."})
    signs = []
    fl = [(W["falls"][r][0], r, W["falls"][r][1]) for r in ORDER if r in W["falls"]]
    if fl:
        parts = []
        for i, (f, r, at) in enumerate(fl):
            at = list(dict.fromkeys(at))
            x = f"{'' if i == 0 else 'و'}{ar(abs(round(f)))} مترًا فوق {r}" + (f" ({jl(at[:3])})" if r == "مكة المكرمة" else "")
            parts.append(x)
        signs.append("هبط سطح ٥٠٠ هكتوباسكال خلال يوم نحو " + "، ".join(parts))
    for k, (nm, a, tt) in W["anom"].items():
        signs.append(f"وحرارة ٥٠٠ فوق {nm} ‎−{n1(abs(tt))}°، أبرد من معدلها بـ{n1(abs(a))}°")
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
    B.append({"p": "التوجيه: تؤخذ أماكن المطر واتساعه من تشغيل نموذجنا بالأوروبي (يكتمل قرابة السادسة صباحًا)، "
                   "وتُتابع مواضع العواصف الرعدية وشدتها من تشغيل نموذجنا بالأمريكي الذي بُني عليه هذا التقرير."})
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


def region_reading(st, rs, regs, day0, W):
    """one row per region worth naming: rain places, cause, spread, success (%) with its parts, level"""
    import plains as P
    import makkah_story as MS
    ours, gfs = _covers(st, rs, day0)
    pl = st.get("plains") or {}
    eds = pl.get("edges") or [] if pl.get("day") == day0.isoformat() else []
    prs = pl.get("rows") or [] if pl.get("day") == day0.isoformat() else []
    wregs = set((W or {}).get("regions") or [])
    T = (W or {}).get("trough")
    out = []
    for nm in ORDER:
        rr = next((r for r in regs if r["name"] == nm), None)
        ne = [e for e in eds if e["region"] == nm and P.edge_named(e, e.get("model_rain"))[0]]
        np_ = [r for r in prs if r["region"] == nm and P.named(r, r.get("model_mtn"))[0]]
        o, g = ours.get(nm), gfs.get(nm)
        pw = pw_of(st, day0, nm)
        # cold aloft over moist air lifts by itself (18 Nov 2026: south of Hail and around Al-Madinah had moderate
        # rain under the trough axis, PW 118-131 %, while both models were dry): a possible shower, not "no rain"
        aloft_moist = nm in wregs and (pw or 0) >= 110
        wet = (o or 0) >= 0.001 or (g or 0) >= 0.005 or rr or ne or np_ or aloft_moist
        if not wet and nm not in wregs:
            continue
        places = []
        if nm == "مكة المكرمة":
            try:
                places += [z["name"] for z in (MS.read(st, pending(rs)).get("rain") or [])][:3]
            except Exception:  # noqa: BLE001
                pass
        if rr:
            w = max(rr["wins"], key=lambda w: _num(w.get("max", 0)), default=None)
            for key in ("heavy", "moderate"):
                if w and w.get(key):
                    places += [x.strip() for x in w[key].replace(" و", "، ").split("، ")]
        places += [P.short(e["name"]) for e in ne] + [P.short(r["name"]) for r in np_]
        places = list(dict.fromkeys(x for x in places if x))[:3]
        if not places and aloft_moist:
            places = ["زخات متفرقة تحت الموجة الباردة"]
        # the cause
        lift = bool(ne or np_ or rr or (o or 0) >= 0.001)
        trough = None
        if nm in wregs:
            if T and T.get("cutoff") and nm in T["k"]["by"]:
                trough = "منخفض علوي منعزل"
            elif T and nm in T["k"]["by"] and T["k"]["by"][nm] <= -40:
                trough = "أخدود متعمق"
            else:
                trough = "أخدود ضحل"
        if trough and lift:
            cause = f"حمل حراري مع {trough}"
        elif trough:
            cause = trough
        else:
            cause = "حمل حراري"
        # the success: how many of five parts agree (shown, so the number is open)
        parts = {"الرطوبة": 1.0 if (pw or 0) >= 110 else 0.5 if (pw or 0) >= 95 else 0.0,
                 "الرفع": 1.0 if (ne or np_) else 0.5 if (lift or aloft_moist) else 0.0,
                 "الدعم العلوي": 1.0 if trough else 0.0,
                 "نموذجنا": 1.0 if (o or 0) >= 0.005 else 0.5 if (o or 0) >= 0.001 else 0.0,
                 "جي إف إس": 1.0 if (g or 0) >= 0.005 else 0.5 if (g or 0) >= 0.001 else 0.0}
        if pending(rs):
            parts.pop("نموذجنا")
        pct = round(100 * sum(parts.values()) / len(parts))
        if (o or 0) < 0.001 and (g or 0) < 0.001:
            pct = min(pct, 45)          # both models dry: the ingredients alone do not make it likely
            capped = True
        else:
            capped = False
        pct = min(pct, 95)              # nothing is certain
        rain = (o or 0) >= 0.001 or (g or 0) >= 0.005
        if trough and not lift:
            cause = f"{trough} (رفع من البرودة العلوية فوق هواء رطب)"
        out.append({"name": nm, "places": places, "cause": cause, "ours": o, "gfs": g, "pw": pw, "parts": parts,
                    "pct": pct, "level": level4(pct), "rain": rain, "capped": capped, "models_dry": (o or 0) < 0.001 and (g or 0) < 0.001, "cold": nm in wregs})
    return out


def _cov(v):
    return "—" if v is None else ("أقل من ٠٫١٪" if v < 0.001 else R2.cover_pct(v).removeprefix("نحو "))


def summary(st, rs, regs, day0):
    import bigreport as BR
    dat = (rs or {}).get("data") or {}
    ours, gfs = _covers(st, rs, day0)
    W = None
    try:
        W = cold_wave(st, day0)
    except Exception as e:  # noqa: BLE001
        print("report3: cold wave failed:", repr(e), flush=True)
    rows = region_reading(st, rs, regs, day0, W)
    B = []
    # a. the whole Kingdom
    sc = BR.strength(st, day0)
    c = BR.combined(st, day0, day0)
    ws = BR.wave_score(st, day0, day0, sc, None if c is None else c["ksa"])["score"]
    f0 = BR._day_factors(st, day0)
    label, Tt, Rr = R2.case_kind(st, day0)
    wide = next(t for lim, t in WIDE_CHANCE if ws < lim)
    if pending(rs):
        t = "يُكتب انتشار المطر في نموذجنا حين يكتمل تشغيله الليلي، قرابة الثانية فجرًا. "
    else:
        cov = ours.get(None) or 0
        t = f"{size_word(cov)}: يغطي المطر {_cov(cov)} من مساحة المملكة في نموذجنا"
        t += (f"، و{_cov(gfs.get(None))} بحسب جي إف إس. " if gfs.get(None) is not None else ". ")
    t += f"قوة الحالة {n1(ws)} من ٥ ({BR.grade(ws)})، وفرصة أن تكون حالة واسعة عند هذه القوة {wide} في سجل ٢٥ موسمًا."
    B.append({"p": t})
    # the structure against the big picture: four levels
    sup = BR._supported(f0)
    struct = 3 if sup and ws >= 3 else 2 if sup and ws >= 1.8 else 1 if (sup or Tt or Rr) else 0
    why = []
    if Tt:
        why.append("من المداريات " + jl(Tt))
    if Rr:
        why.append("من العروض الوسطى " + jl(Rr))
    B.append({"p": f"البنية مع الصورة العامة: {LEVEL4[struct]}. تصنيف الحالة: {label}"
                   + (f"، يسندها {'، و'.join(why)}" if why else "") + "."})
    # b. where the rain is, and why
    wet = [r for r in rows if r["rain"] or r["places"]]
    if wet:
        B.append({"h": "أماكن المطر وأسبابه"})
        B.append({"table": {"head": ["المنطقة", "الأماكن", "السبب", "الانتشار", "النجاح المتوقع"],
                            "rows": [[r["name"], "، ".join(r["places"]) or "متفرقة",
                                      r["cause"], f"{_cov(r['ours'])} (جي إف إس {_cov(r['gfs'])})",
                                      f"{ar(r['pct'])}٪ ({r['level']})"] for r in wet]}})
        for r in wet[:6]:
            ok = [k for k, v in r["parts"].items() if v >= 1]
            half = [k for k, v in r["parts"].items() if v == 0.5]
            no = [k for k, v in r["parts"].items() if v == 0]
            t = f"{r['name']}: {ar(r['pct'])}٪ لأن " + (f"{jl(ok)} {'يتوافقان' if len(ok) == 2 else 'تتوافق' if len(ok) > 2 else 'يتوافق'}" if ok else "لا مكون مكتمل")
            if half:
                t += f"، و{jl(half)} {'جزئيان' if len(half) == 2 else 'جزئية' if len(half) > 2 else 'جزئي'}"
            if no:
                t += f"، ويغيب {jl(no)}"
            if r["pw"]:
                t += f" (الماء القابل للهطول {ar(r['pw'])}٪ من معدله)"
            if r.get("capped"):
                t += "، وخُفضت إلى ٤٥٪ لأن النموذجين لا يُظهران مطرًا، وقد يفوتانه"
            B.append({"p": t + "."})
    else:
        B.append({"p": "لا أمطار تُذكر على مناطق المملكة اليوم."})
    # c. the upper cold wave: its cause, and whether the regions under it get rain
    if W:
        B += cold_wave_blocks(st, day0, effect=False, W=W)
        under = [r for r in rows if r["cold"]]
        wn = {r["name"] for r in wet}
        yes = [f"{r['name']} ({r['level']}" + ("، والنموذجان لا يُظهرانه)" if r.get("models_dry") else ")")
               for r in under if r["name"] in wn]
        no = [r for r in under if r["name"] not in wn]
        t = []
        if yes:
            t.append(f"يُحتمل المطر تحتها على {jl(yes)}")
        if no:
            why_no = []
            for r in no:
                w = "لجفاف الهواء"
                why_no.append(f"{r['name']} ({w})")
            t.append(f"ولا يُتوقع مطر تحتها على {jl(why_no)}، فأثرها هناك برودة ورياح")
        if t:
            B.insert(len(B) - 1, {"p": "المناطق تحت الموجة: " + "، ".join(t) + "."})
    B += spread_table(st, day0)
    B.append({"note": "النجاح المتوقع لكل منطقة = توافق خمسة مكونات: الرطوبة (١١٠٪ من المعدل فأكثر)، والرفع (حافة أو سهل "
                      "مرشح اليوم)، والدعم العلوي (موجة باردة فوقها)، ومطر نموذجنا، ومطر جي إف إس؛ المكون الجزئي بنصف. "
                      "والمستويات: دون ٤٠٪ ضعيفة، ثم متوسطة، ومن ٦٠٪ مرجحة، ومن ٨٠٪ قوية."})
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


def waves(st, rs, regs, day0):
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
    wl = BR.wave_list(st, day0, days, fac, cur_end)
    B = []
    rows = []
    # weak signs outside the waves: a trough over the Red Sea or the Kingdom (15 m or deeper)
    inw = lambda d: any(w["start"] <= d <= w["end"] for w in wl)
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
    if not wl and not sig:
        B.append({"p": f"لا تظهر موجة مطرية حتى {ar_date(days[-1])}، وهو أقصى تاريخ متاح في التوقع."})
        return sec("الموجات القادمة", "waves", B)
    tr_v = {(a, b): v for a, b, _, v in sig}
    for a, b, area, _ in sig:
        c = [BR.combined(st, d, day0) for d in days if a <= d <= b]
        cov = max([x["ksa"] for x in c if x] or [0])
        wl.append({"start": a, "end": b, "peak": a, "top": 0.0, "cover": cov, "kind": "troughs",
                   "regions": [area], "pro": [], "sign": BR.trough_word(-tr_v[(a, b)] / 10)})
    wl.sort(key=lambda w: w["start"])
    for w in wl:
        span = R2.ar_span(w["start"], w["end"]).removeprefix("من ") if w["start"] != w["end"] else ar_date(w["start"])
        lead = (w["peak"] - day0).days
        cov = w.get("cover")
        spread = ((R2.cover_pct(cov) + " من المملكة") if cov is not None and cov >= 0.01 else
                  "أقل من ١٪ من المملكة" if cov is not None else "لا يظهر انتشارها بعد")
        if w.get("sign"):
            span += f" (إشارة أخدود {w['sign']})"
        rows.append([span, BR.confidence(lead), spread, jl(w["regions"]), _strength_word(w)])
    B.append({"p": (f"الموجات حتى {ar_date(days[-1])}، وهو أقصى تاريخ متاح:" if any(not w.get("sign") for w in wl) else
                    f"لا موجة مطرية واسعة حتى {ar_date(days[-1])}، وهو أقصى تاريخ متاح؛ وما يظهر إشارات ضعيفة:")})
    B.append({"table": {"head": ["الفترة", "الثقة", "انتشار المطر", "المناطق", "الشدة"], "rows": rows}})
    # a wide fertile spell: tropical and trough support together, several days, strong
    for w in wl:
        n = (w["end"] - w["start"]).days + 1
        if w["kind"] == "mixed" and n >= 3 and w["top"] >= 2.6:
            span = R2.ar_span(w["start"], w["end"])
            if w["top"] >= 3.5 and BR.confidence((w["start"] - day0).days) == "عالية":
                B.append({"p": f"أمامنا موجة خصب واسعة على الجزيرة العربية {span}، وتطول لفترة طويلة، تتوافق عليها {jl(w['pro'])}."})
            else:
                B.append({"p": f"ألمح {span} ملامح موجة خصب واسعة على الجزيرة العربية، تتوافق عليها {jl(w['pro'])}، وتُتابع كل ليلة."})
            break
    B.append({"note": "الثقة عالية حتى ٥ أيام، ومتوسطة حتى ١٠ أيام، ومنخفضة بعدها."})
    return sec("الموجات القادمة", "waves", B)


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
    for f in (summary, makkah, others, big_picture, waves):
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
