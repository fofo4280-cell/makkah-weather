"""The big-picture report: what drives the weather over the Kingdom now, and the nearest rain wave to come
(named by its drivers, with their dates and the parts of the Kingdom it reaches, followed night by night).

Built from the analyses and the GFS forecast already computed by daily.py (the MJO, the warm and cold events,
the 500 hPa Rossby waves, moisture over the Kingdom, the northern cold troughs, cold waves), and, beyond 15 days,
the inference of outlook.py from the MJO and the warm event.
"""
from datetime import date, timedelta

import bigpic as B
import troughs as TR
import outlook
from sa_geo import ar, num, ar_date, ar_span, join

BOX_NAME = {"west": "الحجاز وغرب المملكة", "southwest": "جنوب غرب المملكة", "central": "وسط المملكة",
            "east": "شرق المملكة", "north": "شمال المملكة"}
PHASE_AREA = {1: "نصف الكرة الغربي وأفريقيا", 2: "غرب المحيط الهندي", 3: "شرق المحيط الهندي",
              4: "القارة البحرية", 5: "القارة البحرية", 6: "غرب المحيط الهادئ", 7: "غرب المحيط الهادئ",
              8: "نصف الكرة الغربي وأفريقيا"}


def jl(names):
    """an Arabic list: 'أ'، 'أ وب'، 'أ، وب، وج' (commas from three items, so long lists stay readable)"""
    names = [x for x in names if x]
    if len(names) <= 2:
        return " و".join(names)
    return "، و".join(names)


def warm_ok(lo, a):
    """the warm event backs rain over the Peninsula: its centre in the favourable sector and strong enough (one
    rule for every line of the report; the factor line and the wave list used to differ)"""
    return a >= 4 and B.favourable(lo)


def mjo_word(m, wet_season=True):
    """the MJO phase as the report reads it. Phases 7, 8, 1, 2 count as supportive in the score; the 25-season
    test (15 Nov 2026) found phase 2 near the normal rain, so the text calls it weakly supportive (wording only,
    the score is unchanged in the stability phase)."""
    if not m:
        return ""
    if m["amp"] < 1:
        return "ضعيف الشدة، لا أثر يُذكر"
    if m["phase"] not in B.WET_PHASES:
        return "غير داعم"
    if not wet_season:
        return "داعم في موسم الأمطار، ونحن خارجه"
    return "داعم ضعيف" if m["phase"] == 2 else "داعم"


def trough_word(dam):
    """the depth of a 500 hPa trough (dam) in words: the strength index takes 6 dam as a full trough"""
    dam = round(dam + 1e-9, 1)   # as printed
    return "عميق" if dam >= 6 else "متوسط العمق" if dam >= 4 else "ضحل"


def when(a, b, day0):
    """a run of days as a phrase: 'اليوم'، 'من اليوم حتى …'، 'الخميس ١٩ نوفمبر'، 'من الجمعة ٢٠ إلى …'"""
    if b <= day0:
        return "اليوم"
    if a <= day0:
        return "من اليوم حتى " + ar_date(b)
    if a == b:
        return ("غدًا " if a == day0 + timedelta(days=1) else "") + ar_date(a)
    return ar_span(a, b)


def wave_name(a, b):
    """'الموجة الممتدة من … إلى …' or 'موجة الخميس ١٩ نوفمبر'"""
    return f"موجة {ar_date(a)}" if a == b else f"الموجة الممتدة {ar_span(a, b)}"


def _day_factors(st, d):
    """What backs rain over the Kingdom on day d: [(key, Arabic words)]."""
    out = []
    s = d.isoformat()
    m = B.rmm_on(st, d)
    if m and st.get("wet_season") and m["amp"] >= 1 and m["phase"] in B.WET_PHASES:
        out.append(("mjo", f"التذبذب المداري في الطور {ar(m['phase'])}"))
    w = next((x for x in B.warm(st["hov"]) if x[0] == s), None) if st.get("hov") else None
    if w and warm_ok(w[1], w[2]):
        out.append(("warm", "الحدث الدافئ في القطاع الداعم"))
    row = next((r for r in st.get("pw", []) if r["d"] == s), None)
    if row:
        boxes = [k for k in BOX_NAME if k in row and row[k]["pct"] >= 150]
        if boxes:
            out.append(("surge", "مد رطوبي فوق " + jl(BOX_NAME[k] for k in boxes)))
    wv = next((x for x in st.get("waves", []) if x["d"] == s), None)
    if wv and "trough" in wv and wv["trough"]["v"] <= -25:
        dam = -wv["trough"]["v"] / 10
        out.append(("trough", f"أخدود {trough_word(dam)} فوق {wv['trough']['area']}"))
    return out


def _supported(f):
    keys = {k for k, _ in f}
    return len(keys) >= 2 and ({"surge", "trough"} & keys)


PW_WORD = lambda p: ("مد رطوبي" if p >= 150 else "فوق المعدل" if p >= 110 else "قريبة من المعدل" if p >= 80 else "دون المعدل")
NUMS = "١٢٣٤٥٦٧٨٩"


def _today(st, day0):
    """the storms of the report day: their kind (heat of the day or cold aloft) and where the winds meet"""
    out = []
    pt = st.get("pattern") or {}
    zs = st.get("collide") or {}
    if zs.get("day") != day0.isoformat():
        zs = {}
    if pt.get("day") == day0.isoformat():
        bx = pt["boxes"]
        # the parts with a meeting zone first, else the west and the southwest, where most storms form
        import pattern as P
        reg_box = {"مكة المكرمة": "west", "المدينة المنورة": "west", "تبوك": "north", "الجوف": "north",
                   "الحدود الشمالية": "north", "حائل": "north", "القصيم": "central", "الرياض": "central",
                   "الشرقية": "east", "الباحة": "southwest", "عسير": "southwest", "جازان": "southwest",
                   "نجران": "southwest"}
        keys = list(dict.fromkeys(reg_box[r] for z in zs.get("zones", []) for r in (z.get("regions") or [z["region"]])
                                  if r in reg_box)) or ["west", "southwest"]
        groups = {}
        for k in keys:
            groups.setdefault(bx[k]["kind"], []).append(k)
        parts = []
        dev = lambda a: ("قريبة من معدلها" if abs(a) < 0.3 else
                         f"{'أبرد' if a < 0 else 'أدفأ'} من معدلها بـ{num(abs(a), 1)}°")
        for kd in ("upper", "mixed", "thermal"):
            if kd in groups:
                vals = jl(f"{n1(bx[k]['t'])}° فوق {bx[k]['name']} ({dev(bx[k]['anom'])})" for k in groups[kd])
                parts.append(f"{P.WORDS[kd][0]}، فحرارة ٥٠٠ هكتوباسكال عصر اليوم {vals}. {P.WORDS[kd][1]}")
        out.append("نمط الحالة: " + ". وفي غيرها: ".join(parts) + ".")
    if zs:
        if zs.get("lines"):
            out.append("مناطق تصادم الرياح التي تنشأ عليها السحب بعد الظهر (من ١١ صباحًا إلى ٥ عصرًا، برياح ٨٥٠ "
                       "هكتوباسكال، أو رياح ١٠ أمتار فوق المرتفعات، حيث الماء القابل للهطول ٢٠ ملم فأكثر)، من الأقوى:")
            out += [f"• {x}." for x in zs["lines"]]
        else:
            out.append("مناطق التصادم: لا يُظهر جي إف إس عصر اليوم منطقة تتصادم فيها الرياح في هواء رطب (ماء قابل للهطول ٢٠ ملم فأكثر)، "
                       "فالتضاريس وتسخين النهار هما ما يُنشئ السحب، ومواضعها في جدول الأمطار من نموذجنا.")
    return out


def _factors(st, day0):
    """the drivers of the day, read in a fixed order from the slowest to the fastest: one line each, in full
    sentences, each label checked against its own number"""
    out = []
    k = 0
    def add(t):
        nonlocal k
        out.append(f"{NUMS[k]}. {t}")
        k += 1
    m0 = B.rmm_on(st, day0)
    if m0:
        trend = ""
        fc = [x for x in st.get("rmm_fc") or [] if x["d"] > day0.isoformat()]
        if len(fc) >= 5:
            a5 = fc[min(4, len(fc) - 1)]["amp"]
            trend = " ويشتد" if a5 > m0["amp"] + 0.2 else " ويضعف" if a5 < m0["amp"] - 0.2 else " وشدته ثابتة"
        t = (f"التذبذب المداري (مادن-جوليان) في الطور {ar(m0['phase'])} بشدة {num(m0['amp'], 1)}{trend}، "
             f"وحمله النشط فوق {PHASE_AREA.get(m0['phase'], '')}: {mjo_word(m0, st.get('wet_season'))}")
        if m0["phase"] == 2 and m0["amp"] >= 1:
            t += "، لأن أثر الطور ٢ في أمطار المملكة قريب من المعتاد في دراسة ٢٥ موسمًا، والأقوى أثرًا الطوران ٨ و١"
        add(t + ".")
    mf0 = _mf(st, day0)
    if mf0:
        ref = st["mjof"].get("z_ref") or 10
        z0, _, core0 = mf0
        t = (f"مكوّن التذبذب عند ٨٠٠ هكتوباسكال فوق المملكة {n1(z0)} م: {mf_word(z0, ref)}. ومركز غلافه فوق "
             f"{B.region_name(core0)} عند {ar(core0 if core0 <= 180 else 360 - core0)}° {'شرقًا' if core0 <= 180 else 'غربًا'}")
        eff = _component_effect(st)
        if eff and eff.get("rank") is not None and z0 < 0 and eff["rank"] <= 10:
            t += "، وقيمته اليوم من أعمق قيمه" + (" في السجل" if eff["rank"] <= 1 else f" (أدنى من {ar(100 - eff['rank'])}٪ من الأيام)")
        if eff and None not in (eff.get("neg"), eff.get("pos")):
            t += (f". وفي مواسم الأمطار الماضية كانت الأمطار تغطي {n1(eff['neg'])}٪ من المملكة يوميًا في المتوسط حين يكون "
                  f"سالبًا بقوة، و{n1(eff['pos'])}٪ حين يكون موجبًا بقوة")
        add(t + ".")
    for fam in ("ros", "kel"):
        x = _tw(st, day0, fam)
        if not x:
            continue
        t = f"{TW_NAME[fam]} (جهد السرعة عند ٢٠٠ هكتوباسكال فوق المملكة) {n1(x[0])} مليون م²/ث: {tw_word(*x)}"
        eff = _tw_effect(st, fam)
        if fam == "ros" and eff and eff["rain_n"] >= 5:
            t += (f". كانت سالبة في {ar(eff['rain_neg'])} من {ar(eff['rain_n'])} يومًا مطيرًا واسعًا في الموسم الماضي، "
                  "لكن أثرها غير ثابت على مدى ٢٦ موسمًا")
        if fam == "kel":
            t += "، ولا تدخل في درجة الموجة لأن أثرها على أمطار المملكة لم يثبت"
        add(t + ".")
    w1 = {d: (lo, a) for d, lo, a in B.warm(st["hov"])} if st.get("hov") else {}
    if day0.isoformat() in w1:
        lo, a = w1[day0.isoformat()]
        where = ("في القطاع الداعم للجزيرة العربية" if warm_ok(lo, a) else
                 "في القطاع الداعم لكنه أضعف من أن يؤثر" if B.favourable(lo) else
                 "خارج القطاع الداعم للجزيرة العربية (من شرق المحيط الهادئ إلى غرب بحر العرب)")
        add(f"الحدث الدافئ (التباعد العلوي) فوق {B.region_name(lo)} بشدة {num(a, 1)}، {where}؛ "
            f"ويقابله الحدث البارد فوق {B.region_name((lo + 180) % 360)}.")
    row = next((r for r in st.get("pw", []) if r["d"] == day0.isoformat()), None)
    if row:
        ks = sorted([q for q in BOX_NAME if q in row], key=lambda q: -row[q]["pct"])
        if ks:
            p0 = row[ks[0]]["pct"]
            verdict = ("بلغ حد المد الرطوبي (١٥٠٪)" if p0 >= 150 else "فوق المعدل دون حد المد الرطوبي (١٥٠٪)" if p0 >= 110
                       else "قريب من المعدل" if p0 >= 80 else "دون المعدل")
            add("الرطوبة (الماء القابل للهطول نسبةً إلى معدله): " + jl(
                f"{ar(row[q]['pct'])}٪ فوق {BOX_NAME[q]}" for q in ks[:3]) + f"؛ فأرطب الأجزاء {verdict}.")
    wv0 = next((x for x in st.get("waves", []) if x["d"] == day0.isoformat()), None)
    if wv0 and "trough" in wv0:
        dam = -wv0["trough"]["v"] / 10
        add(f"الأخاديد: أخدود {trough_word(dam)} عند ٥٠٠ هكتوباسكال فوق {wv0['trough']['area']} بعمق {num(dam, 1)} ديكامتر"
            + ("، يسحب الرطوبة ويرفع الهواء أمامه." if wv0["trough"]["v"] <= -25 else "، لا يُعتد به."))
    else:
        add("الأخاديد: لا أخدود يُعتد به قرب المملكة اليوم.")
    return out


def report(st, day0):
    days = [day0 + timedelta(days=k) for k in range(16)]
    fac = {d: _day_factors(st, d) for d in days}
    # ---------------------------------------------------------------- the current wave
    f0 = fac[day0]
    if _supported(f0):
        end = day0
        for d in days[1:]:
            if _supported(fac[d]):
                end = d
            else:
                break
        gone = {k for k, _ in f0} - {k for k, _ in fac.get(end + timedelta(days=1), [])}
        words = {"mjo": "يخرج التذبذب من الأطوار الداعمة", "warm": "يغادر الحدث الدافئ القطاع الداعم",
                 "surge": "ينحسر المد الرطوبي", "trough": "يبتعد الأخدود"}
        cur = (f"الموجة الحالية قائمة، يسندها {jl(w for _, w in f0)}، وتنتهي قرابة {ar_date(end)}"
               + (f" حين {jl(words[k] for k in ['surge', 'trough', 'warm', 'mjo'] if k in gone)}" if gone else "") + ".")
        cur_end = end
    else:
        # the lesser helps of the day (moisture above normal, the Rossby family), named so the summary does not
        # contradict the drivers section below (17 Nov 2026: "one factor only" while Rossby and 134 % moisture helped)
        minor = []
        row0 = next((r for r in st.get("pw", []) if r["d"] == day0.isoformat()), None)
        if row0 and "surge" not in {k for k, _ in f0}:
            wet_b = [k for k in BOX_NAME if k in row0 and 110 <= row0[k]["pct"] < 150]
            if wet_b:
                kb = max(wet_b, key=lambda k: row0[k]["pct"])
                minor.append(f"رطوبة فوق المعدل ({ar(row0[kb]['pct'])}٪ فوق {BOX_NAME[kb]})")
        rv = _tw(st, day0, "ros")
        if rv and rv[0] <= -rv[1] / 3:
            minor.append("عائلة روسبي الاستوائية")
        need = "والحالة الواسعة تحتاج مدًا رطوبيًا (١٥٠٪ فأكثر) أو أخدودًا مع عامل آخر."
        if not f0:
            cur = ("لا موجة مطرية قائمة الآن، ولا عامل كبير يدعم المطر اليوم"
                   + (f"؛ وما يسنده دعم ثانوي: {jl(minor)}. " if minor else ". ") + need)
        else:
            big = (f"عامل كبير واحد هو {f0[0][1]}" if len(f0) == 1 else jl(w for _, w in f0))
            cur = (f"لا موجة مطرية قائمة الآن. يسند المطر اليوم {big}"
                   + (f"، ومعه دعم ثانوي من {jl(minor)}" if minor else "")
                   + f"، وهذا لا يكفي لحالة واسعة؛ {need[1:]}")
        cur_end = day0 - timedelta(days=1)
    # ---------------------------------------------------------------- the waves to come
    lines, watch = next_wave(st, day0, days, fac, cur_end)
    st["wave_watch"] = watch
    # ---------------------------------------------------------------- the summary first
    summ = []
    td = _today(st, day0)
    pt = st.get("pattern") or {}
    bits = []
    if pt.get("day") == day0.isoformat():
        import pattern as P
        kinds = {v["kind"] for k, v in pt["boxes"].items() if k in ("west", "southwest")}
        kd = "upper" if "upper" in kinds else "mixed" if "mixed" in kinds else "thermal"
        bits.append(f"نمط السحب في الغرب والجنوب الغربي {P.WORDS[kd][0]}")
    zs = (st.get("collide") or {})
    if zs.get("day") == day0.isoformat() and zs.get("zones"):
        rs = list(dict.fromkeys(r for z in zs["zones"] for r in (z.get("regions") or [z["region"]])))
        bits.append(f"وأبرز تصادم للرياح بعد الظهر فوق {jl(rs[:3])}")
    if bits:
        summ.append(f"اليوم {ar_date(day0)}: " + "، ".join(bits) + ".")
    summ.append(cur)
    if watch.get("start"):
        s0, e0 = date.fromisoformat(watch["start"]), date.fromisoformat(watch["end"])
        lead = (date.fromisoformat(watch["peak"]) - day0).days
        conf = {"عالية": "عالية لقرب موعدها", "متوسطة": "متوسطة", "منخفضة": "منخفضة لبعد موعدها"}[confidence(lead)]
        summ.append(f"الموجة القادمة {ar_span(s0, e0)}، وهي {grade(watch['score'])} ({n1(watch['score'])} من ٥)، "
                    f"والثقة في توقعها {conf}.")
        ws = watch.get("waves") or []
        if len(ws) > 1:
            best = max(ws, key=lambda w: w["score"])
            if best["start"] != watch["start"] and best["score"] >= watch["score"] + 0.3:
                a, b = date.fromisoformat(best["start"]), date.fromisoformat(best["end"])
                summ.append(f"وأقوى منها {wave_name(a, b)} ({grade(best['score'])}، {n1(best['score'])} من ٥)، "
                            "وهي الأولى بالمتابعة.")
    else:
        summ.append("لا تظهر موجة جديدة في توقع جي إف إس لستة عشر يومًا.")
    sections = [{"heading": "الخلاصة", "kind": "sum", "lines": summ}]
    # ---------------------------------------------------------------- 1. today
    dg = (st.get("diag") or {}).get("lines") or []
    if td or dg:
        sections.append({"heading": f"تشخيص اليوم ({ar_date(day0)})", "kind": "diag", "lines": td + dg})
    # ---------------------------------------------------------------- 2. the drivers, slowest first
    sections.append({"heading": "قراءة العوامل (من الأبطأ إلى الأسرع)", "lines": _factors(st, day0)})
    # ---------------------------------------------------------------- 3. the waves to come
    sections.append({"heading": "الموجات القادمة", "lines": lines + [METHOD]})
    return sections


METHOD = ("المصادر والمنهج: تحاليل جي إف إس وتوقعه لستة عشر يومًا. درجة الموجة من ٥ تجمع العوامل الستة (التذبذب في "
          "أطواره الداعمة، والحدث الدافئ في القطاع الداعم، والرطوبة فوق المعدل، وعمق الأخدود، ومكوّن التذبذب، وعائلة روسبي؛ "
          "لكل منها درجة واحدة، والمجموع لا يتجاوز ٥) مع انتشار الأمطار المتوقع، ويزيد وزن الانتشار كلما قرب اليوم؛ "
          "لذلك تنزل درجة الموجة عن درجة عواملها حين لا يُظهر التوقع مطرًا. والانتشار يجمع مطر جي إف إس ومؤشر مكونات الجو: "
          "جي إف إس أدق حتى ٥ أيام، ويتقاربان حتى اليوم الثامن، والمؤشر أدق بعده. والموجة ضعيفة دون ١٫٨، ومتوسطة حتى ٢٫٥، "
          "وقوية من ٢٫٦، وقوية جدًا من ٣٫٥. وعمق الأخدود: ضحل دون ٤ ديكامتر، ومتوسط حتى ٦، وعميق من ٦.")


# ---------------------------------------------------------------- the strength of a day: every driver on 0..1
def _mf(st, d):
    """the MJO component over the Kingdom on day d: (height m, rain mm/day, core longitude) or None"""
    m = st.get("mjof")
    if not m or d.isoformat() not in m["days"]:
        return None
    i = m["days"].index(d.isoformat())
    return m["z_ksa"][i], m["r_ksa"][i], m["core"][i]


TW_NAME = {"ros": "عائلة روسبي الاستوائية", "kel": "موجات كلفن"}


def _tw(st, d, fam):
    """the Kelvin ('kel') or Rossby ('ros') family of the 200 hPa velocity potential over the Kingdom on day d
    (million m2/s; negative = divergence aloft, it helps the rain), and its yardstick (the past spread); or None"""
    t = st.get("tw")
    if not t or d.isoformat() not in t["days"]:
        return None
    return t[fam + "_ksa"][t["days"].index(d.isoformat())], t.get(fam + "_ref") or 1.0


def tw_word(x, ref):
    return ("داعمة بقوة" if x <= -ref else "داعمة" if x <= -ref / 3 else "محايدة" if x < ref / 3 else
            "كابحة" if x < ref else "كابحة بقوة")


def _tw_effect(st, fam):
    """the share of the Kingdom wet (5 mm or more) on past rain-season days with the family strongly negative,
    near zero and strongly positive, from the same past days as the MJO component"""
    t, m = st.get("tw"), st.get("mjof")
    if not t or not m:
        return None
    cov = {d: c for d, c in zip(m["days"], m["cover"]) if c is not None and int(d[5:7]) in (11, 12, 1, 2, 3, 4)}
    ref = t.get(fam + "_ref") or 1.0
    rows = [(x, cov[d]) for d, x in zip(t["days"], t[fam + "_ksa"]) if d in cov]
    if len(rows) < 30:
        return None
    pct = lambda xs: round(100 * sum(xs) / len(xs), 1) if len(xs) >= 5 else None
    rain = [x for x, c in rows if c >= 0.08]
    return {"neg": pct([c for x, c in rows if x <= -ref]), "mid": pct([c for x, c in rows if -ref < x < ref]),
            "pos": pct([c for x, c in rows if x >= ref]), "rain_n": len(rain), "rain_neg": sum(1 for x in rain if x < 0)}


def fc_cover(st, d):
    """share of the Kingdom the GFS forecast wets with 5 mm or more on day d, or None"""
    m = st.get("mjof")
    if not m or not m.get("fc_cover") or d.isoformat() not in m["days"]:
        return None
    return m["fc_cover"][m["days"].index(d.isoformat())]


def _vals(st, d):
    s = d.isoformat()
    v = {"m": B.rmm_on(st, d)}
    w = next((x for x in B.warm(st["hov"]) if x[0] == s), None) if st.get("hov") else None
    v["w"] = (w[1], w[2]) if w else None
    row = next((r for r in st.get("pw", []) if r["d"] == s), None)
    v["pw"] = max(((row[k]["pct"], k) for k in BOX_NAME if row and k in row), default=None)
    wv = next((x for x in st.get("waves", []) if x["d"] == s), None)
    v["tr"] = (wv["trough"]["v"], wv["trough"]["area"]) if wv and "trough" in wv else None
    v["mf"] = _mf(st, d)
    return v


def strength(st, d):
    """{'mjo','warm','pw','trough','mjof','ros'} each 0..1, and 'total' (0..5).
    'ros': the Rossby family of the 200 hPa velocity potential over the Kingdom (Fahad, 14 Nov 2026), negative in
    22 of the 24 wide rain days of the past season; it adds to the five others, and the total is held at 5, so a
    day without it keeps the score it had."""
    v = _vals(st, d)
    c = {}
    m = v["m"]
    c["mjo"] = min(m["amp"] / 3, 1) if m and st.get("wet_season") and m["amp"] >= 1 and m["phase"] in B.WET_PHASES else 0.0
    c["warm"] = min(v["w"][1] / 12, 1) if v["w"] and B.favourable(v["w"][0]) else 0.0
    c["pw"] = min(max((v["pw"][0] - 100) / 100, 0), 1) if v["pw"] else 0.0
    c["trough"] = min(max(-v["tr"][0] / 60, 0), 1) if v["tr"] else 0.0
    ref = (st.get("mjof") or {}).get("z_ref") or 10
    c["mjof"] = min(max(-v["mf"][0] / (2 * ref), 0), 1) if v["mf"] else 0.0
    r = _tw(st, d, "ros")
    c["ros"] = min(max(-r[0] / (2 * r[1]), 0), 1) if r else 0.0
    c["total"] = round(min(sum(c.values()), 5.0), 2)
    return c


def mf_word(z, ref):
    """what a value of the MJO component over the Kingdom means (negative heights help the rain)"""
    return ("داعم بقوة للأمطار" if z <= -ref else "داعم للأمطار" if z <= -ref / 3 else
            "محايد، قريب من الصفر" if z < ref / 3 else "كابح للأمطار" if z < ref else "كابح بقوة للأمطار")


def lead_weight(lead):
    """the weight of the GFS rain spread against our ingredients index, from their test on the past year: the GFS
    rain is better up to 5 days ahead, they are even up to 8, the index is better beyond"""
    return 0.7 if lead <= 5 else 0.5 if lead <= 8 else 0.3


def confidence(lead):
    return "عالية" if lead <= 5 else "متوسطة" if lead <= 10 else "منخفضة"


def combined(st, d, day0):
    """{'ksa': share of the Kingdom likely to get 5 mm or more on day d, 'regions': {name: share}} from the GFS
    rain spread and our ingredients index weighted by lead; None when neither is known"""
    row = next((r for r in st.get("ingr", []) if r["d"] == d.isoformat()), None)
    if row is None:
        c = fc_cover(st, d)
        return None if c is None else {"ksa": c, "regions": {}}
    w = lead_weight((d - day0).days) if "gfs" in row else 0.0
    regs = {}
    for name, v in row["regions"].items():
        g = (row.get("gfs_regions") or {}).get(name, 0.0)
        regs[name] = w * g + (1 - w) * v
    return {"ksa": w * row.get("gfs", 0.0) + (1 - w) * row["ksa"], "regions": regs}


SHORT = {"مكة المكرمة": "منطقة مكة المكرمة", "المدينة المنورة": "منطقة المدينة المنورة"}


def scenario(st, day0, start, end, peak):
    """the wave day by day: where its rain begins, spreads, is widest and ends, with the confidence of each day"""
    ACT, STRONG = 0.05, 0.15
    days = [start + timedelta(days=k) for k in range(-2, (end - start).days + 2)]
    rows = {d: combined(st, d, day0) for d in days}
    near = [d for d in days if (d - day0).days <= 10 and rows[d] is not None]
    if not near:
        return ["• سيرها يومًا بيوم: بعيدة بعد أكثر من عشرة أيام، وتُفصَّل حين تقترب."]
    out = ["• سيرها يومًا بيوم (مطر جي إف إس مع مؤشر مكونات الجو):"]
    prev = set()
    seen_any = False
    last_active = ended = None
    for d in near:
        r = rows[d]
        act = {n for n, v in r["regions"].items() if v >= ACT}
        strong = sorted([n for n, v in r["regions"].items() if v >= STRONG], key=lambda n: -r["regions"][n])
        if not act and not seen_any:
            continue
        lead = (d - day0).days
        name = lambda xs: join([SHORT.get(x, x) for x in xs])
        parts = []
        if not seen_any:
            parts.append(f"تبدأ الأمطار على {name(sorted(act, key=lambda n: -r['regions'][n]))}")
            seen_any = True
        else:
            new = sorted(act - prev, key=lambda n: -r["regions"][n])
            gone = sorted(prev - act)
            stay = sorted(act & prev, key=lambda n: -r["regions"][n])
            if new:
                parts.append(f"تمتد إلى {name(new)}")
            if stay:
                parts.append(f"{'وتستمر' if new else 'تستمر'} على {name(stay)}")
            if gone:
                parts.append(f"{'وتنحسر' if parts else 'تنحسر'} عن {name(gone)}")
            if not act:
                parts = [f"تنحسر الأمطار عن {name(sorted(prev))}" if prev else "لا أمطار تُذكر"]
        if strong:
            parts.append(f"وأغزرها على {name(strong[:3])}")
        tag = f" ({'الذروة، ' if d == peak else ''}{ar(round(100 * r['ksa']))}٪ من المملكة، الثقة {confidence(lead)})"
        out.append(f"  - {ar_date(d)}: {'، '.join(parts)}{tag}.")
        if act:
            last_active = d
        prev = act
        if not act and seen_any:
            ended = d
            break
    if not seen_any:
        return ["• سيرها يومًا بيوم: لا يُظهر التوقع مطرًا واسعًا على أي منطقة في أيامها حتى الآن، ويُراجع ذلك كل ليلة."]
    far = [d for d in days if (d - day0).days > 10 and d <= end]
    if ended:
        out.append(f"  - تنتهي أمطارها بانقضاء {ar_date(last_active)}"
                   + ("، وقد تمتد بعدها لأن عواملها مستمرة حتى " + ar_date(end) if ended < end else "") + ".")
    elif far:
        out.append(f"  - بعد {ar_date(near[-1])}: لا تفصيل لبعد المدة، ويُكتب حين تقترب.")
    elif last_active and last_active < days[-1]:
        out.append(f"  - تنتهي بعد {ar_date(last_active)}.")
    return out


def wave_score(st, d, day0, drv, cover):
    """the strength of a day on 0..5: the drivers (strength index) and the forecast rain spread together; the
    spread weighs 70 % up to 3 days ahead, 50 % up to a week and 30 % beyond, as the rain forecast loses skill"""
    lead = (d - day0).days
    w = 0.0 if cover is None else 0.7 if lead <= 3 else 0.5 if lead <= 7 else 0.3
    s_rain = min((cover or 0) / 0.15, 1.0)
    return {"score": round(5 * (w * s_rain + (1 - w) * drv["total"] / 5), 2), "w": w}


def grade(x):
    x = round(x + 1e-9, 1)   # grade the number as it is printed: 1.78 shows as 1.8, so it is "medium", not "weak"
    return "قوية جدًا" if x >= 3.5 else "قوية" if x >= 2.6 else "متوسطة" if x >= 1.8 else "ضعيفة"


def n1(x):
    """one decimal, with a true minus sign so the number reads right in Arabic text"""
    return ("−" if x < 0 else "") + num(abs(x), 1)


def _component_effect(st):
    """what the MJO component has meant for rain over the Kingdom in the past rain seasons (November to April):
    mean share of the Kingdom with 5 mm or more on days with the component strongly negative, near zero, and
    strongly positive; and how today's value ranks among all past days"""
    m = st.get("mjof")
    if not m:
        return None
    ref = m.get("z_ref") or 10
    wet = {11, 12, 1, 2, 3, 4}
    rows = [(z, c) for d, z, c in zip(m["days"], m["z_ksa"], m["cover"]) if c is not None and int(d[5:7]) in wet]
    past = [z for d, z, c in zip(m["days"], m["z_ksa"], m["cover"]) if c is not None]
    out = {"ref": ref, "n": len(rows)}
    t0 = m.get("t0")
    if t0 and t0 in m["days"] and past:
        z0 = m["z_ksa"][m["days"].index(t0)]
        out["rank"] = round(100 * sum(1 for z in past if z <= z0) / len(past))
        out["days"] = len(past)
    if len(rows) < 30:
        return out
    neg = [c for z, c in rows if z <= -ref]
    mid = [c for z, c in rows if -ref < z < ref]
    pos = [c for z, c in rows if z >= ref]
    pct = lambda xs: round(100 * sum(xs) / len(xs), 1) if len(xs) >= 5 else None
    out.update(neg=pct(neg), mid=pct(mid), pos=pct(pos), nneg=len(neg), npos=len(pos))
    return out


def _past_cases(st, day0, v, cpeak=None):
    """the past rain episodes over the Kingdom most like the coming wave, by the MJO component over the Kingdom"""
    m = st.get("mjof")
    if not m or not m.get("episodes") or not v.get("mf"):
        return []
    eps = m["episodes"]
    z = v["mf"][0]
    out = []
    cur = [e for e in eps if date.fromisoformat(e["b"]) >= day0 - timedelta(days=2)]
    old = [e for e in eps if e not in cur]
    def words(e):
        a, b = date.fromisoformat(e["a"]), date.fromisoformat(e["b"])
        pk = date.fromisoformat(e["peak"])
        head = ar_date(a) if a == b else f"{ar_span(a, b)}، وأوسعها {ar_date(pk)}"
        return f"{head}: غطت أمطارها نحو {ar(round(100 * e['cover']))}٪ من المملكة، والمكوّن {n1(e['z'])} م"
    if cur:
        e = cur[-1]
        pk = date.fromisoformat(e["peak"])
        out.append(f"• للمقارنة، أوسع أمطار الحالة الحالية {ar_date(pk)}: نحو {ar(round(100 * e['cover']))}٪ من المملكة، "
                   f"والمكوّن {n1(e['z'])} م.")
    if old:
        best = sorted(old, key=lambda e: abs(e["z"] - z))[:2]
        out.append(f"• أشبه الحالات الماضية بها في قيمة المكوّن ({n1(z)} م): " + "؛ و".join(words(e) for e in best)
                   + ". (المساحة: ما نال ٥ ملم فأكثر في مطر جي إف إس لليوم الأول من كل توقع.)")
    return out


def _cold_days(st, days):
    """{date: (Kingdom area, depth at its centre dam, arrival, centre place, depth over the Kingdom dam)}: a northern
    cold trough whose axis reaches the Kingdom, on its arrival day and the next. The depth of the track is the one at
    the trough's centre, often over Turkey or Iraq; the depth where its axis crosses the Kingdom is much smaller and
    is given apart, so the report does not put the centre's 8 dam over the Kingdom (Fahad, 16 Nov 2026)."""
    out = {}
    for c in st.get("troughs") or []:
        if not c.get("arrive"):
            continue
        a = date.fromisoformat(c["arrive"])
        t = next((x for x in c["days"] if x["d"] == c["arrive"]), None)
        if not t:
            continue
        ksa = [p for p in t.get("axis") or [] if p[0] <= 31.5 and 34 <= TR.lon180(p[1]) <= 56]
        dk = round(-min(p[2] for p in ksa) / 10, 1) if ksa else None
        for d in (a, a + timedelta(days=1)):
            if d in days and d not in out:
                out[d] = (TR.kingdom_area(t["tip"][1]), -t["depth"], a, TR.place(t["lat"], t["lon"]), dk)
    return out


def _parts(area):
    """Kingdom parts named in an area's words: west, southwest, north, central, east."""
    # only the place after 'فوق' or 'يبلغ': the depth words before it ('متوسط العمق') must not read as the centre
    for key in ("فوق ", "يبلغ "):
        if key in area:
            area = area.split(key, 1)[1]
            break
    if "المملكة" not in area and "الحجاز" not in area:
        return set()
    out = set()
    if "جنوب غرب" in area:
        out.add("southwest")
    if "شمال غرب" in area:
        out |= {"north", "west"}
    if "شمال شرق" in area:
        out |= {"north", "east"}
    if "شمال" in area:
        out.add("north")
    if "وسط" in area:
        out.add("central")
    if "شرق" in area.replace("شمال شرق", ""):
        out.add("east")
    if "الحجاز" in area or "غربها" in area or ("غرب" in area.replace("جنوب غرب", "").replace("شمال غرب", "")):
        out.add("west")
    return out


def _span_words(ds, day0=None):
    ds = sorted(ds)
    if day0 and ds[0] <= day0:
        return f"من اليوم حتى {ar_date(ds[-1])}"
    return ar_span(ds[0], ds[-1])


def _plural_days(n):
    return "يوم واحد" if n == 1 else "يومان" if n == 2 else f"{ar(n)} أيام" if n <= 10 else f"{ar(n)} يومًا"


def _days_acc(n):
    """a number of days in the accusative, after a verb: 'يومًا واحدًا'، 'يومين'، '٣ أيام'، '١١ يومًا'"""
    return "يومًا واحدًا" if n == 1 else "يومين" if n == 2 else f"{ar(n)} أيام" if n <= 10 else f"{ar(n)} يومًا"


def _runs(days, has):
    """[(first, last)] of the unbroken runs of days where has(d)"""
    out, a = [], None
    for d in days:
        if has(d):
            a = a or d
        elif a:
            out.append((a, days[days.index(d) - 1])); a = None
    if a:
        out.append((a, days[-1]))
    return out


def _span_list(rs, day0):
    return "، و".join(when(a, b, day0) for a, b in rs)


def drivers_timeline(st, day0, days):
    """How the drivers move over the whole range of the data (Fahad, 14 Nov 2026: read the waves from the movement
    of the isolated MJO component and of the warm event and when they come back over the places that favour the
    Peninsula, with the other drivers): one sentence for each driver, its spans in time order."""
    out = []
    last = days[-1]
    ref = (st.get("mjof") or {}).get("z_ref") or 10
    # the isolated MJO component over the Kingdom
    mz = [(d, _mf(st, d)) for d in days]
    mz = [(d, x[0], x[2]) for d, x in mz if x]
    if mz:
        last = min(last, mz[-1][0])
        val = {d: z for d, z, _ in mz}
        ds = [d for d, _, _ in mz]
        spans = [(a, b, "brk") for a, b in _runs(ds, lambda d: val[d] >= ref / 3)]
        spans += [(a, b, "sup") for a, b in _runs(ds, lambda d: val[d] <= -ref / 3)]
        parts = []
        for a, b, k in sorted(spans):
            seg = [d for d in ds if a <= d <= b]
            if k == "brk":
                x = max(seg, key=lambda d: val[d])
                parts.append(f"كابح {when(a, b, day0)}، وأقصاه {n1(val[x])} م {ar_date(x)}")
            else:
                x = min(seg, key=lambda d: val[d])
                parts.append(f"داعم {when(a, b, day0)}، وأعمقه {n1(val[x])} م {ar_date(x)}")
        t = f"• مكوّن التذبذب عند ٨٠٠ (حتى {ar_date(mz[-1][0])}): " + ("؛ ثم ".join(parts) if parts else
                                                                        "قريب من الصفر طوال المدة، لا يدعم ولا يكبح")
        # where the envelope of the MJO goes: its centre's longitude
        c0, c1 = mz[0][2], mz[-1][2]
        if B.region_name(c0) != B.region_name(c1):
            jump = next((d for (d, _, c), (_, _, cp) in zip(mz[1:], mz) if abs(((c - cp + 180) % 360) - 180) > 60), None)
            gen = lambda x: x.replace("الأمريكتان", "الأمريكتين")
            t += (f". ومركز غلافه ينتقل من {gen(B.region_name(c0))} إلى {gen(B.region_name(c1))}"
                  + (f" {ar_date(jump)}، أي أن دورة جديدة تقترب من الغرب" if jump else ""))
        out.append(t + ".")
    # the Rossby and Kelvin families over the Kingdom
    for fam in ("ros", "kel"):
        xs = [(d, _tw(st, d, fam)) for d in days]
        xs = [(d, x[0], x[1]) for d, x in xs if x]
        if not xs:
            continue
        ref_ = xs[0][2]
        val = {d: x for d, x, _ in xs}
        ds = [d for d, _, _ in xs]
        spans = [(a, b, "sup") for a, b in _runs(ds, lambda d: val[d] <= -ref_ / 3)]
        spans += [(a, b, "brk") for a, b in _runs(ds, lambda d: val[d] >= ref_ / 3)]
        groups = []          # neighbouring spans of the same sign together: 'كابحة يوم كذا، ويوم كذا'
        for a, b, k in sorted(spans):
            if groups and groups[-1][0] == k:
                groups[-1][1].append((a, b))
            else:
                groups.append((k, [(a, b)]))
        parts = []
        for k, rs in groups:
            seg = [d for d in ds if any(a <= d <= b for a, b in rs)]
            x = (min if k == "sup" else max)(seg, key=lambda d: val[d])
            extra = f" ({n1(val[x])}{'' if len(seg) == 1 else ' ' + ar_date(x)})"
            parts.append(f"{'داعمة' if k == 'sup' else 'كابحة'} {_span_list(rs, day0)}{extra}")
        out.append(f"• {TW_NAME[fam]} (مليون م²/ث، والقيمة بين القوسين أشدها): "
                   + ("، ثم ".join(parts) if parts else "محايدة طوال المدة") + ".")
    # the warm event
    if st.get("hov"):
        w1 = {date.fromisoformat(d): (lo, a) for d, lo, a in B.warm(st["hov"])}
        wd = [d for d in days if d in w1]
        if wd:
            last = min(last, wd[-1])
            ok = lambda d: warm_ok(*w1[d])
            spans = [(a, b, True) for a, b in _runs(wd, ok)] + [(a, b, False) for a, b in _runs(wd, lambda d: not ok(d))]
            t = f"• الحدث الدافئ (حتى {ar_date(wd[-1])}): "
            if any(k for _, _, k in spans):
                parts = []
                for a, b, k in sorted(spans):
                    seg = [d for d in wd if a <= d <= b]
                    lo = w1[max(seg, key=lambda d: w1[d][1])][0]
                    where = B.region_name(lo).replace("الأمريكتان", "الأمريكتين")
                    parts.append(f"{'في القطاع الداعم' if k else 'خارج القطاع الداعم'} {when(a, b, day0)} (فوق {where})")
                t += "، ثم ".join(parts)
            else:
                t += (f"خارج القطاع الداعم طوال المدة، فوق {B.region_name(w1[wd[0]][0])}"
                      + (f" ثم {B.region_name(w1[wd[-1]][0])}" if B.region_name(w1[wd[-1]][0]) != B.region_name(w1[wd[0]][0]) else ""))
            out.append(t + ".")
    # the MJO itself
    ms = [(d, B.rmm_on(st, d)) for d in days]
    ms = [(d, m) for d, m in ms if m]
    if ms:
        good = lambda m: m["amp"] >= 1 and m["phase"] in B.WET_PHASES
        wet = _runs([d for d, _ in ms], lambda d: good(B.rmm_on(st, d)))
        t = "• التذبذب المداري: " + (f"في الأطوار الداعمة {_span_list(wet, day0)}" if wet else "خارج الأطوار الداعمة طوال المدة")
        phases = sorted({m["phase"] for _, m in ms if m["amp"] >= 1})
        if len(wet) >= 3 and len(phases) == 2 and abs(phases[0] - phases[1]) == 1:
            t += (f"؛ فهو يتأرجح على حد الطورين {ar(phases[0])} و{ar(phases[1])}، ودعمه لذلك متقطع"
                  + (" وضعيف" if 2 in phases else ""))
        pw_ = [(d, m) for d, m in ms if good(m)]
        if pw_:
            pk = max(pw_, key=lambda x: x[1]["amp"])
            t += f". أشد أيامه الداعمة {ar_date(pk[0])} (الطور {ar(pk[1]['phase'])} بشدة {n1(pk[1]['amp'])})"
        pk = max(ms, key=lambda x: x[1]["amp"])
        if not pw_ or not good(pk[1]):
            t += (f"{'، وأقصى' if pw_ else '. وأقصى'} شدته {n1(pk[1]['amp'])} {ar_date(pk[0])} في الطور {ar(pk[1]['phase'])}"
                  + ("، وهو طور غير داعم" if not good(pk[1]) else ""))
        t += f". وفي آخر المدى {ar_date(ms[-1][0])} يكون في الطور {ar(ms[-1][1]['phase'])} بشدة {n1(ms[-1][1]['amp'])}."
        out.insert(0, t)
    return out, last


def wave_regions(st, wd, f, kind):
    """the parts of the Kingdom a wave reaches: the moist boxes (130 % of normal or more) and the places of its
    troughs over the wave's days. One rule for the wave list and the nearest wave's detail (they gave different
    regions for the same wave before, 16 Nov 2026)."""
    hit = set()
    for d in wd:
        row = next((r for r in st.get("pw", []) if r["d"] == d.isoformat()), None)
        if row:
            hit |= {k for k in BOX_NAME if k in row and row[k]["pct"] >= 130}
        for k, w in f[d]:
            if k in ("trough", "cold"):
                hit |= _parts(w)
    if not hit:
        hit = {"southwest", "west"} if kind == "tropical" else {"north"}
    return [BOX_NAME[k] for k in ("west", "southwest", "north", "central", "east") if k in hit]


KINDS = {"mixed": "مدارية تسندها أخاديد", "tropical": "مدارية دون أخاديد", "troughs": "من الأخاديد دون دعم مداري"}


def wave_list(st, day0, days, f, cur_end):
    """Every wave in the range of the data: [{start, end, peak, top, kind, regions, for, against}]. Each driver is
    named for or against from its value on the peak day, by the same rules as the drivers' lines."""
    keys = lambda d: {k for k, _ in f[d]}
    ok = lambda d: (len(keys(d)) >= 2 and keys(d) & {"surge", "trough", "cold"}) or "cold" in keys(d)
    cand = [d for d in days if d > cur_end + timedelta(days=1)]
    sc = {d: strength(st, d) for d in days}
    rc = {d: (lambda c: None if c is None else c["ksa"])(combined(st, d, day0)) for d in days}
    ws = {d: wave_score(st, d, day0, sc[d], rc[d]) for d in days}
    ref = (st.get("mjof") or {}).get("z_ref") or 10
    out = []
    for a, b in _runs(cand, ok):
        wd = [d for d in days if a <= d <= b]
        allk = set().union(*(keys(d) for d in wd))
        T, R = allk & {"mjo", "warm"}, allk & {"trough", "cold"}
        kind = "mixed" if T and R else "tropical" if T else "troughs"
        peak = max(wd, key=lambda d: ws[d]["score"])
        c = sc[peak]
        v = _vals(st, peak)
        pro, con = [], []
        m = v["m"]
        if m and c.get("mjo", 0) > 0:
            pro.append(f"التذبذب المداري في الطور {ar(m['phase'])}" + (" (دعم ضعيف)" if m["phase"] == 2 else ""))
        if v["w"] and warm_ok(*v["w"]):
            pro.append(f"الحدث الدافئ في القطاع الداعم (فوق {B.region_name(v['w'][0])})")
        elif v["w"]:
            con.append(f"الحدث الدافئ خارج القطاع الداعم (فوق {B.region_name(v['w'][0])})")
        if v["pw"] and v["pw"][0] >= 110:
            pro.append(f"{'مد رطوبي' if v['pw'][0] >= 150 else 'رطوبة فوق المعدل'} ({ar(v['pw'][0])}٪ فوق {BOX_NAME[v['pw'][1]]})")
        elif v["pw"]:
            con.append(f"الرطوبة {'قريبة من المعدل' if v['pw'][0] >= 80 else 'دون المعدل'} ({ar(v['pw'][0])}٪ في أرطب الأجزاء)")
        # the trough by its place and depth (the 500 hPa wave band), counted only from 25 m as in the drivers' line
        tr = v["tr"]
        if tr and tr[0] <= -25:
            dam = -tr[0] / 10
            pro.append(f"أخدود {trough_word(dam)} فوق {tr[1]} ({num(dam, 1)} ديكامتر)")
        mf = v["mf"]
        if mf and mf[0] <= -ref / 3:
            pro.append(f"مكوّن التذبذب داعم ({n1(mf[0])} م)")
        elif mf and mf[0] >= ref / 3:
            con.append(f"مكوّن التذبذب كابح ({n1(mf[0])} م)")
        for fam in ("ros", "kel"):
            x = _tw(st, peak, fam)
            if x and x[0] <= -x[1] / 3:
                pro.append(f"{TW_NAME[fam]} ({n1(x[0])})")
            elif x and x[0] >= x[1] / 3:
                con.append(f"{TW_NAME[fam]} كابحة ({n1(x[0])})")
        out.append({"start": a, "end": b, "peak": peak, "top": ws[peak]["score"], "drivers": c["total"],
                    "cover": rc.get(peak), "kind": kind, "regions": wave_regions(st, wd, f, kind), "pro": pro, "con": con})
    return out


def waves_overview(st, day0, days, f, cur_end):
    """the lines that open the waves section: the drivers' movement, then every wave in the data's range"""
    tl, last = drivers_timeline(st, day0, days)
    lines = (["مسار العوامل:"] + tl) if tl else []
    days = [d for d in days if d <= last]
    wl = wave_list(st, day0, days, f, cur_end)
    if not wl:
        return lines, wl
    lines.append(f"الموجات المرتقبة حتى {ar_date(days[-1])}، من الأقرب:")
    for w in wl:
        span_w = ar_span(w["start"], w["end"]) if w["start"] != w["end"] else ar_date(w["start"])
        t = (f"• {span_w}: موجة {grade(w['top'])} ({n1(w['top'])} من ٥)، {KINDS[w['kind']]}"
             + (f"، ذروتها {ar_date(w['peak'])}" if w["start"] != w["end"] else "") + ".")
        if (w.get("cover") or 0) >= 0.01:
            t += f" ويغطي مطرها في التوقع نحو {ar(round(100 * w['cover']))}٪ من المملكة يوم ذروتها."
        elif w.get("cover") is not None:
            t += (f" ولا يُظهر لها توقع المطر انتشارًا يُذكر بعد، فدرجتها أدنى من درجة عواملها ({n1(w['drivers'])})."
                  if w["drivers"] >= w["top"] + 0.3 else " ولا يُظهر لها توقع المطر انتشارًا يُذكر بعد.")
        t += f" تسندها: {jl(w['pro'])}." if w["pro"] else " لا يسندها عامل يُذكر."
        if w["con"]:
            t += f" وتعاكسها: {jl(w['con'])}."
        t += f" المناطق المرشحة: {jl(w['regions'])}."
        lines.append(t)
    if len(wl) > 1:
        best = max(wl, key=lambda w: w["top"])
        if best is not wl[0] and best["top"] >= wl[0]["top"] + 0.3:
            lines.append(f"وأقوى الموجات ليست أقربها: {wave_name(best['start'], best['end'])} أولى بالمتابعة. "
                         "والثقة فيما بعد عشرة أيام منخفضة، ويُراجع التوقع كل ليلة.")
        else:
            lines.append("والثقة فيما بعد عشرة أيام منخفضة، ويُراجع التوقع كل ليلة.")
    lines.append("تفصيل أقرب موجة:")
    return lines, wl


def next_wave(st, day0, days, fac, cur_end):
    """The nearest rain wave after the current one, from the GFS forecast (16 days, the longest it gives), and
    beyond it from the eastward speed of the MJO and the warm event (up to 45 days). The wave is named by what
    drives it: tropical with troughs, tropical alone (no deepening troughs), or troughs alone; each driver with
    its own dates, and the parts of the Arabian Peninsula it reaches. Compared with yesterday's estimate."""
    cold = _cold_days(st, days)
    f = {d: list(fac[d]) + ([("cold", f"أخدود بارد يبلغ {cold[d][0]}")] if d in cold else []) for d in days}
    keys = lambda d: {k for k, _ in f[d]}
    tropical = {"mjo", "warm"}
    ok = lambda d: (len(keys(d)) >= 2 and keys(d) & {"surge", "trough", "cold"}) or "cold" in keys(d)
    lines, watch = [], {"day": day0.isoformat()}
    prev = st.get("prev_watch") or {}
    try:
        ov, wl = waves_overview(st, day0, days, f, cur_end)
        lines += ov
        watch["waves"] = [{"start": w["start"].isoformat(), "end": w["end"].isoformat(), "peak": w["peak"].isoformat(),
                           "score": w["top"], "kind": w["kind"]} for w in wl]
    except Exception as e:  # noqa: BLE001
        print("waves overview failed:", repr(e), flush=True)
    start = next((d for d in days if d > cur_end + timedelta(days=1) and ok(d)), None)

    if start:
        end = start
        for d in days[days.index(start) + 1:]:
            if ok(d):
                end = d
            else:
                break
        def run(has):
            """the days of the unbroken run of a driver that overlaps the wave, within the 16 days"""
            inside = [d for d in days if start <= d <= end and has(d)]
            if not inside:
                return []
            i, j = days.index(inside[0]), days.index(inside[-1])
            while i > 0 and has(days[i - 1]):
                i -= 1
            while j + 1 < len(days) and has(days[j + 1]):
                j += 1
            return days[i:j + 1]
        span = lambda key: run(lambda d: key in keys(d))
        near = [d for d in days if start <= d <= end]
        allk = set().union(*(keys(d) for d in days[days.index(start):days.index(end) + 1]))
        T, R = allk & tropical, allk & {"trough", "cold"}
        kind = "mixed" if T and R else "tropical" if T else "troughs"
        title = "موجة " + KINDS[kind]
        wave_days = days[days.index(start):days.index(end) + 1]
        sc = {d: strength(st, d) for d in days}
        rc = {d: (lambda c: None if c is None else c["ksa"])(combined(st, d, day0)) for d in days}
        ws = {d: wave_score(st, d, day0, sc[d], rc[d]) for d in days}
        # the strongest day of a wave: the drivers of our oscillation page and the forecast spread of the rain
        # together (the spread weighs more on the near days, the drivers on the far ones)
        peak = max(wave_days, key=lambda d: ws[d]["score"])
        top = ws[peak]["score"]
        i = j = wave_days.index(peak)
        while i > 0 and ws[wave_days[i - 1]]["score"] >= 0.85 * top:
            i -= 1
        while j + 1 < len(wave_days) and ws[wave_days[j + 1]]["score"] >= 0.85 * top:
            j += 1
        a, b = wave_days[i], wave_days[j]
        if start == end:
            lines.append(f"• الموعد والنوع: يوم {ar_date(start)}. وهي {title}.")
        else:
            lines.append(f"• الموعد والنوع: تمتد {ar_span(start, end)}، وتشتد {ar_span(a, b) if a != b else 'يوم ' + ar_date(a)}"
                         + (f" وذروتها {ar_date(peak)}" if a != b and any(v is not None for v in rc.values()) else "")
                         + f". وهي {title}.")
        # against the current wave: its strongest day among the days left
        cur_days = [d for d in days if day0 <= d <= max(cur_end, day0)]
        cpeak = max(cur_days, key=lambda d: ws[d]["score"])
        ctop = ws[cpeak]["score"]
        names = {"mjo": "التذبذب المداري", "warm": "الحدث الدافئ", "pw": "الرطوبة", "trough": "الأخدود",
                 "mjof": "دعم مكوّن التذبذب", "ros": "دعم عائلة روسبي"}
        has_cur = cur_end >= day0
        ref_word = "الموجة الحالية" if has_cur else "اليوم"
        diff = sorted(((sc[peak][k] - sc[cpeak][k], k) for k in names), key=lambda x: x[0])
        weaker = [names[k] for x, k in diff if x <= -0.2]
        stronger = [names[k] for x, k in diff[::-1] if x >= 0.2]
        if rc.get(peak) is not None and rc.get(cpeak) is not None:
            if rc[peak] >= rc[cpeak] + 0.02:
                stronger.append("انتشار الأمطار")
            elif rc[peak] <= rc[cpeak] - 0.02:
                weaker.append("انتشار الأمطار")
        cmp = ("أقوى من" if top >= ctop + 0.3 else "أضعف من" if top <= ctop - 0.3 else "قريبة من")
        why = []
        if stronger:
            why.append(f"وفيها {jl(stronger)} أقوى")
        if weaker:
            why.append(f"{'و' if stronger else 'وفيها '}{jl(weaker)} أضعف")
        def day_words(d):
            return (f"العوامل {n1(sc[d]['total'])} من ٥"
                    + ((f"، والمطر يغطي {ar(round(100 * rc[d]))}٪ من المملكة" if rc[d] >= 0.005 else "، ولا مطر واسع في التوقع")
                       if rc.get(d) is not None else ""))
        # without the rain spread, the drivers alone do not tell a wave's strongest day: say only what they tell
        has_rc = any(v is not None for v in rc.values())
        best = "ذروتها" if has_rc else "أعلى أيامها في العوامل"
        cmp_to = (f"الموجة الحالية في ذروتها {ar_date(cpeak)}" if has_cur else "درجة اليوم")
        lines.append(f"• القوة: {grade(top)}، {n1(top)} من ٥ في {best} {ar_date(peak)} ({day_words(peak)}). "
                     f"وهي {cmp} {cmp_to} ({n1(ctop)} من ٥: {day_words(cpeak)})"
                     + (f"؛ {'، '.join(why)}." if why else ".")
                     + ("" if has_rc else " (من العوامل وحدها، فالانتشار لم يُحسب بعد.)"))
        watch.update(peak=peak.isoformat(), score=round(top, 2), cover=rc.get(peak), drivers=sc[peak]["total"])
        # each driver at the peak, against the peak of the current wave (the same yardstick as the strength line)
        v, v0 = _vals(st, peak), _vals(st, cpeak)
        at0 = ar_date(cpeak)
        ref = (st.get("mjof") or {}).get("z_ref") or 10
        vals = []
        if v["m"]:
            vals.append(f"التذبذب: الطور {ar(v['m']['phase'])} بشدة {n1(v['m']['amp'])}، {mjo_word(v['m'], st.get('wet_season'))}"
                        + (f" (الطور {ar(v0['m']['phase'])} بشدة {n1(v0['m']['amp'])})" if v0["m"] else ""))
        if v["mf"]:
            far = (peak - day0).days >= 7
            vals.append(f"مكوّن التذبذب عند ٨٠٠: {n1(v['mf'][0])} م، {mf_word(v['mf'][0], ref)}"
                        + (f" ({n1(v0['mf'][0])} م)" if v0["mf"] else "")
                        + ("؛ وثقته بعد أسبوع أقل لأنه من آخر أيام التوقع" if far else ""))
        for fam in ("ros", "kel"):
            x, x0 = _tw(st, peak, fam), _tw(st, cpeak, fam)
            if x:
                vals.append(f"{TW_NAME[fam]}: {n1(x[0])} مليون م²/ث، {tw_word(*x)}" + (f" ({n1(x0[0])})" if x0 else ""))
        if v["w"]:
            vals.append(f"الحدث الدافئ: فوق {B.region_name(v['w'][0])} بشدة {n1(v['w'][1])}"
                        + ("، في القطاع الداعم" if warm_ok(*v["w"]) else "، خارج القطاع الداعم")
                        + (f" (فوق {B.region_name(v0['w'][0])} بشدة {n1(v0['w'][1])})" if v0["w"] else ""))
        if v["pw"]:
            vals.append(f"الرطوبة: {ar(v['pw'][0])}٪ من المعدل فوق {BOX_NAME[v['pw'][1]]}"
                        + (f" ({ar(v0['pw'][0])}٪ فوق {BOX_NAME[v0['pw'][1]]})" if v0["pw"] else ""))
        if v["tr"]:
            vals.append(f"الأخدود عند ٥٠٠: فوق {v['tr'][1]} بعمق {n1(-v['tr'][0] / 10)} ديكامتر، {trough_word(-v['tr'][0] / 10)}"
                        + (f" (فوق {v0['tr'][1]} بعمق {n1(-v0['tr'][0] / 10)})" if v0["tr"] else ""))
        if vals:
            lines.append(f"• العوامل يوم ذروتها {ar_date(peak)}، وبين القوسين قيمها "
                         + (f"في ذروة الموجة الحالية {ar_date(cpeak)}:" if has_cur else "اليوم:"))
            lines += [f"  - {x}." for x in vals]
        drivers = []
        if span("mjo"):
            ph = []
            for d in span("mjo"):
                m = B.rmm_on(st, d)
                if m and m["phase"] not in ph:
                    ph.append(m["phase"])
            drivers.append(f"التذبذب المداري (مادن-جوليان) في {'الطور' if len(ph) == 1 else 'الأطوار'} "
                           f"{jl(ar(p) for p in ph)} {_span_words(span('mjo'), day0)}"
                           + ("، وهو دعم ضعيف" if ph == [2] else ""))
        if span("warm"):
            drivers.append(f"الحدث الدافئ في القطاع الداعم {_span_words(span('warm'), day0)}، أي تباعد علوي يرفع الهواء ويغذي الحمل العميق")
        pwr = {r["d"]: r for r in st.get("pw", [])}
        wet = lambda k: (lambda d: k in pwr.get(d.isoformat(), {}) and pwr[d.isoformat()][k]["pct"] >= 150)
        boxes = {k: run(wet(k)) for k in BOX_NAME}
        boxes = {k: v for k, v in boxes.items() if v}
        for k, ds in boxes.items():
            drivers.append(f"مد رطوبي فوق {BOX_NAME[k]} {_span_words(ds, day0)}")
        areas = {}
        for d in [d for d in span("trough") if start <= d <= end]:
            wv = next((x for x in st.get("waves", []) if x["d"] == d.isoformat()), None)
            if wv and "trough" in wv:
                areas.setdefault(wv["trough"]["area"], []).append((d, -wv["trough"]["v"] / 10))
        for a, xs in areas.items():
            dam = max(x for _, x in xs)
            drivers.append(f"أخدود {trough_word(dam)} عند ٥٠٠ هكتوباسكال فوق {a} {_span_words([d for d, _ in xs])}، "
                           f"عمقه {num(dam, 1)} ديكامتر")
        seen = set()
        for d in span("cold"):
            area, depth, arr, centre, dk = cold[d]
            if arr in seen:
                continue
            seen.add(arr)
            drivers.append(f"أخدود بارد من الشمال عمقه {num(depth, 1)} ديكامتر في مركزه فوق {centre}، ويبلغ محوره "
                           f"{area} يوم {ar_date(arr)}"
                           + (f"، وعمقه هناك نحو {num(dk, 1)} ديكامتر فقط" if dk is not None and dk < depth - 1 else ""))
        lines.append("• عواملها وتواريخها:")
        lines += [f"  - {x}." for x in drivers]

        regs = wave_regions(st, wave_days, f, kind)
        lines.append(f"• المناطق المرشحة: {jl(regs)}.")
        lines += _past_cases(st, day0, v, cpeak)
        try:
            lines += scenario(st, day0, start, end, peak)
        except Exception as e:  # noqa: BLE001
            print("wave scenario failed:", repr(e), flush=True)
        g = grade(top)
        how = ("أمطار رعدية واسعة تغزر على عدة مناطق، مع احتمال البرد وجريان السيول" if top >= 2.6 else
               "أمطار رعدية متفرقة تغزر أحيانًا، أكثرها على المرتفعات وحيث تلتقي الرطوبة بالأخدود" if top >= 1.8 else
               "أمطار محدودة متفرقة، أغلبها على المرتفعات")
        why_kind = {"mixed": "الدعم المداري يرفع الرطوبة ويغذي الحمل العميق، والأخاديد تنظمه وتوسع رقعته",
                    "tropical": "الحمل المداري وحده يغذيها، فتتركز بعد الظهر والمساء على المرتفعات وتهامة",
                    "troughs": "الأخدود وحده يحكمها، فترافقها رياح وانخفاض في الحرارة وسحب رعدية على مقدمته"}[kind]
        lines.append(f"• الأثر المتوقع: {how}؛ ف{why_kind}. وتتضح المناطق والكميات في جدول الأمطار حين تدخل الموجة مدى نموذجنا.")
        watch.update(start=start.isoformat(), end=end.isoformat(), kind=kind, src="gfs")
    else:
        lines.append("لا تظهر موجة مطرية جديدة في توقع جي إف إس لستة عشر يومًا (أطول مدى يعطيه).")
        try:
            ol = outlook.outlook(st, day0)
            far = [x for x in ol["lines"] if x.startswith("من ١٥")]
            for x in far:
                lines.append(x.replace("من ١٥ إلى ٤٥ يومًا", "بعد ذلك حتى ٤٥ يومًا", 1))
        except Exception as e:
            print("outlook failed", repr(e), flush=True)
        watch.update(src="none")

    # day-by-day tracking of the estimate, until the wave arrives
    if watch.get("start"):
        s0 = date.fromisoformat(watch["start"])
        if prev.get("start") and prev.get("day") and prev["day"] < day0.isoformat() and prev.get("kind"):
            p0 = date.fromisoformat(prev["start"])
            first = prev.get("first_day", prev["day"])
            watch["first_day"], watch["first_start"] = first, prev.get("first_start", prev["start"])
            shift = (s0 - p0).days
            if shift == 0:
                track = f"• المتابعة: موعد بدئها ثابت على {ar_date(s0)} كما قُدّر أمس"
            else:
                track = (f"• المتابعة: {'تقدّم' if shift < 0 else 'تأخر'} موعد بدئها {_days_acc(abs(shift))}، "
                         f"فقد كان أمس {ar_date(p0)} وصار اليوم {ar_date(s0)}")
            if watch["first_start"] != prev["start"] or first != prev["day"]:
                track += (f"؛ ورُصدت أول مرة {ar_date(date.fromisoformat(first))} وكان موعدها حينها "
                          f"{ar_date(date.fromisoformat(watch['first_start']))}")
        else:
            watch["first_day"], watch["first_start"] = day0.isoformat(), watch["start"]
            track = "• المتابعة: رُصدت اليوم أول مرة، ويُحدَّث موعدها كل ليلة"
        left = (s0 - day0).days
        lines.append(track + ". " + (f"وتبدأ بعد {_days_acc(left)}." if left > 1 else
                                     "وتبدأ غدًا." if left == 1 else "وقد بدأت اليوم."))
    return lines, watch
