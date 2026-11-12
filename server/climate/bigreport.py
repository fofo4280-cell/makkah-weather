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


def _day_factors(st, d):
    """What backs rain over the Kingdom on day d: [(key, Arabic words)]."""
    out = []
    s = d.isoformat()
    m = B.rmm_on(st, d)
    if m and st.get("wet_season") and m["amp"] >= 1 and m["phase"] in B.WET_PHASES:
        out.append(("mjo", f"التذبذب في الطور {ar(m['phase'])}"))
    w = next((x for x in B.wave1(st["hov"]) if x[0] == s), None) if st.get("hov") else None
    if w and w[2] >= 4 and B.favourable(w[1]):
        out.append(("warm", "الحدث الدافئ في القطاع المحفز"))
    row = next((r for r in st.get("pw", []) if r["d"] == s), None)
    if row:
        boxes = [k for k in BOX_NAME if k in row and row[k]["pct"] >= 150]
        if boxes:
            out.append(("surge", "مد رطوبي فوق " + join(BOX_NAME[k] for k in boxes)))
    wv = next((x for x in st.get("waves", []) if x["d"] == s), None)
    if wv and "trough" in wv and wv["trough"]["v"] <= -25:
        out.append(("trough", f"أخدود فوق {wv['trough']['area']}"))
    return out


def _supported(f):
    keys = {k for k, _ in f}
    return len(keys) >= 2 and ({"surge", "trough"} & keys)


def report(st, day0):
    sections = []
    days = [day0 + timedelta(days=k) for k in range(16)]
    fac = {d: _day_factors(st, d) for d in days}

    # ---------------------------------------------------------------- 1. now
    now = []
    m0 = B.rmm_on(st, day0)
    if m0:
        trend = ""
        fc = [x for x in st.get("rmm_fc") or [] if x["d"] > day0.isoformat()]
        if len(fc) >= 5:
            a5 = fc[min(4, len(fc) - 1)]["amp"]
            trend = "ويشتد" if a5 > m0["amp"] + 0.2 else "ويضعف" if a5 < m0["amp"] - 0.2 else "ويحافظ على شدته"
        wet = m0["phase"] in B.WET_PHASES and m0["amp"] >= 1 and st.get("wet_season")
        now.append(f"التذبذب المداري (مادن-جوليان) في الطور {ar(m0['phase'])} بشدة {num(m0['amp'], 1)}، أي أن الحمل النشط فوق "
                   f"{PHASE_AREA.get(m0['phase'], '')}، {trend}؛ وهو طور {'محفز لأمطار المملكة في هذا الموسم' if wet else 'لا يدعم أمطار المملكة'}.")
    w1 = {d: (lo, a) for d, lo, a in B.wave1(st["hov"])} if st.get("hov") else {}
    if day0.isoformat() in w1:
        lo, a = w1[day0.isoformat()]
        fw = B.favourable(lo)
        cold_lo = (lo + 180) % 360            # the cold event sits half a wave away
        now.append(f"الحدث الدافئ (التباعد في الطبقات العليا وصعود الهواء) متمركز فوق {B.region_name(lo)}"
                   f"{'، في القطاع المحفز للجزيرة العربية' if fw else '، بعيدًا عن القطاع المحفز للجزيرة العربية'}، "
                   f"والحدث البارد (التقارب العلوي وهبوط الهواء) في الجهة المقابلة فوق {B.region_name(cold_lo)}.")
    wv0 = next((x for x in st.get("waves", []) if x["d"] == day0.isoformat()), None)
    if wv0:
        t = []
        if "trough" in wv0:
            t.append(f"أخدود موجة روسبي عند ٥٠٠ هكتوباسكال فوق {wv0['trough']['area']} بعمق {num(-wv0['trough']['v'] / 10, 1)} ديكامتر")
        if "ridge" in wv0:
            t.append(f"يقابله مرتفع شرقًا عند {num(wv0['ridge']['lat'])}° شمالًا و{num(wv0['ridge']['lon'])}° شرقًا")
        if t:
            now.append("في الطبقة المتوسطة: " + "، و".join(t) + "؛ والأخدود يسحب الرطوبة من الجنوب ويهيئ صعود الهواء أمامه.")
    f0 = fac[day0]
    if _supported(f0):
        end = day0
        for d in days[1:]:
            if _supported(fac[d]):
                end = d
            else:
                break
        gone = {k for k, _ in f0} - {k for k, _ in fac.get(end + timedelta(days=1), [])}
        words = {"mjo": "يخرج التذبذب من الأطوار المحفزة", "warm": "يغادر الحدث الدافئ القطاع المحفز",
                 "surge": "ينحسر المد الرطوبي", "trough": "يبتعد الأخدود"}
        now.append(f"الموجة الحالية قائمة: {join(w for _, w in f0)}. وتنتهي قرابة {ar_date(end)}"
                   + (f"، حين {join(words[k] for k in ['surge', 'trough', 'warm', 'mjo'] if k in gone)}" if gone else "")
                   + "، فتتراجع فرص الأمطار بعدها.")
        cur_end = end
    else:
        now.append("لا موجة مطرية قائمة على المملكة الآن؛ "
                   + (f"والعوامل الحاضرة: {join(w for _, w in f0)}، وهي وحدها لا تكفي لحالة واسعة." if f0 else "ولا عامل كبيرًا يدعمها."))
        cur_end = day0 - timedelta(days=1)
    mf0 = _mf(st, day0)
    if mf0:
        ref = st["mjof"].get("z_ref") or 10
        z0, r0, core0 = mf0
        eff = _component_effect(st)
        txt = (f"مكوّن التذبذب المعزول عند ٨٠٠ هكتوباسكال (بطريقة قريبة من منهجية الدكتور خالد) فوق المملكة اليوم: "
               f"{n1(z0)} م، أي {mf_word(z0, ref)}. والرقم هو انحراف ارتفاع سطح ٨٠٠ هكتوباسكال الذي يصنعه التذبذب وحده: "
               f"السالب انخفاض يساعد على صعود الهواء والأمطار، والموجب ارتفاع يكبحها. ومركز غلاف التذبذب اليوم فوق "
               f"{B.region_name(core0)} (خط الطول {ar(core0 if core0 <= 180 else 360 - core0)}° {'شرقًا' if core0 <= 180 else 'غربًا'}).")
        if eff and eff.get("rank") is not None and z0 < 0 and eff["rank"] <= 10:
            mo = round(eff["days"] / 30)
            mo_w = "شهرين" if mo == 2 else f"{ar(mo)} أشهر" if mo <= 10 else f"{ar(mo)} شهرًا"
            txt += ((f" وهي أعمق قيمة له في آخر {mo_w}" if eff["rank"] <= 1 else
                     f" وهي من أعمق قيمه: أدنى من {ar(100 - eff['rank'])}٪ من أيام آخر {mo_w}")
                    + "، وقد تزامنت مع الموجة الحالية الواسعة.")
        if eff and None not in (eff.get("neg"), eff.get("mid"), eff.get("pos")):
            clear = eff["neg"] >= 2 * max(eff["pos"], 0.5)
            txt += (f" وأثره في مواسم الأمطار الماضية (نوفمبر إلى أبريل) {'واضح' if clear else 'محدود'}: في الأيام التي كان فيها "
                    f"سالبًا بقوة (أقل من {n1(-ref)} م) أصابت الأمطار في المتوسط {n1(eff['neg'])}٪ من مساحة المملكة يوميًا، "
                    f"مقابل {n1(eff['mid'])}٪ حين كان قريبًا من الصفر و{n1(eff['pos'])}٪ حين كان موجبًا بقوة.")
        now.append(txt)
    sections.append({"heading": f"الوضع الحالي ({ar_date(day0)})", "lines": now})

    # ---------------------------------------------------------------- 2. the nearest wave to come, tracked day by day
    lines, watch = next_wave(st, day0, days, fac, cur_end)
    st["wave_watch"] = watch
    sections.append({"heading": "أقرب موجة قادمة", "lines": lines})
    return sections


# ---------------------------------------------------------------- the strength of a day: every driver on 0..1
def _mf(st, d):
    """the MJO component over the Kingdom on day d: (height m, rain mm/day, core longitude) or None"""
    m = st.get("mjof")
    if not m or d.isoformat() not in m["days"]:
        return None
    i = m["days"].index(d.isoformat())
    return m["z_ksa"][i], m["r_ksa"][i], m["core"][i]


def fc_cover(st, d):
    """share of the Kingdom the GFS forecast wets with 5 mm or more on day d, or None"""
    m = st.get("mjof")
    if not m or not m.get("fc_cover") or d.isoformat() not in m["days"]:
        return None
    return m["fc_cover"][m["days"].index(d.isoformat())]


def _vals(st, d):
    s = d.isoformat()
    v = {"m": B.rmm_on(st, d)}
    w = next((x for x in B.wave1(st["hov"]) if x[0] == s), None) if st.get("hov") else None
    v["w"] = (w[1], w[2]) if w else None
    row = next((r for r in st.get("pw", []) if r["d"] == s), None)
    v["pw"] = max(((row[k]["pct"], k) for k in BOX_NAME if row and k in row), default=None)
    wv = next((x for x in st.get("waves", []) if x["d"] == s), None)
    v["tr"] = (wv["trough"]["v"], wv["trough"]["area"]) if wv and "trough" in wv else None
    v["mf"] = _mf(st, d)
    return v


def strength(st, d):
    """{'mjo','warm','pw','trough','mjof'} each 0..1, and 'total' (0..5)"""
    v = _vals(st, d)
    c = {}
    m = v["m"]
    c["mjo"] = min(m["amp"] / 3, 1) if m and st.get("wet_season") and m["amp"] >= 1 and m["phase"] in B.WET_PHASES else 0.0
    c["warm"] = min(v["w"][1] / 12, 1) if v["w"] and B.favourable(v["w"][0]) else 0.0
    c["pw"] = min(max((v["pw"][0] - 100) / 100, 0), 1) if v["pw"] else 0.0
    c["trough"] = min(max(-v["tr"][0] / 60, 0), 1) if v["tr"] else 0.0
    ref = (st.get("mjof") or {}).get("z_ref") or 10
    c["mjof"] = min(max(-v["mf"][0] / (2 * ref), 0), 1) if v["mf"] else 0.0
    c["total"] = round(sum(c.values()), 2)
    return c


def mf_word(z, ref):
    """what a value of the MJO component over the Kingdom means (negative heights help the rain)"""
    return ("داعم بقوة للأمطار" if z <= -ref else "داعم للأمطار" if z <= -ref / 3 else
            "قريب من الصفر، لا يدعم ولا يكبح" if z < ref / 3 else "كابح للأمطار" if z < ref else "كابح بقوة للأمطار")


def grade(x):
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
        return (f"موجة {ar_span(a, b)}، أصابت أمطارها في أوسع أيامها ({ar_date(date.fromisoformat(e['peak']))}) نحو "
                f"{ar(round(100 * e['cover']))}٪ من مساحة المملكة، وكان المكوّن فوق المملكة {n1(e['z'])} م")
    if cur:
        e = cur[-1]
        pk = date.fromisoformat(e["peak"])
        out.append(f"للمقارنة، الموجة الحالية: أوسع أمطارها حتى الآن كانت {ar_date(pk)}، حين أصابت نحو "
                   f"{ar(round(100 * e['cover']))}٪ من مساحة المملكة وكان المكوّن فوق المملكة {n1(e['z'])} م"
                   + ".")
    if old:
        best = sorted(old, key=lambda e: abs(e["z"] - z))[:2]
        out.append("وأشبه موجات السنة الماضية بها في قيمة المكوّن فوق المملكة: " + "؛ و".join(words(e) for e in best) + ".")
    if out:
        out.append("(مساحة الأمطار هنا من توقع جي إف إس لليوم الأول: نسبة مساحة المملكة التي نالت ٥ ملم فأكثر في اليوم.)")
    return out


def _cold_days(st, days):
    """{date: (area, depth dam)}: a northern cold trough whose axis reaches the Kingdom, on its arrival day and the next."""
    out = {}
    for c in st.get("troughs") or []:
        if not c.get("arrive"):
            continue
        a = date.fromisoformat(c["arrive"])
        t = next((x for x in c["days"] if x["d"] == c["arrive"]), None)
        if not t:
            continue
        for d in (a, a + timedelta(days=1)):
            if d in days and d not in out:
                out[d] = (TR.kingdom_area(t["tip"][1]), -t["depth"], a)
    return out


def _parts(area):
    """Kingdom parts named in an area's words: west, southwest, north, central, east."""
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
        return f"مستمر من اليوم حتى {ar_date(ds[-1])}"
    return ar_span(ds[0], ds[-1])


def _plural_days(n):
    return "يوم واحد" if n == 1 else "يومان" if n == 2 else f"{ar(n)} أيام" if n <= 10 else f"{ar(n)} يومًا"


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
        title = {"mixed": "موجة مدارية مع أخاديد (مركّبة)",
                 "tropical": "موجة مدارية معزولة، دون أخاديد متعمقة",
                 "troughs": "موجة أخاديد، دون دعم مداري"}[kind]
        wave_days = days[days.index(start):days.index(end) + 1]
        sc = {d: strength(st, d) for d in days}
        peak = max(wave_days, key=lambda d: sc[d]["total"])
        top = sc[peak]["total"]
        i = j = wave_days.index(peak)
        while i > 0 and sc[wave_days[i - 1]]["total"] >= 0.85 * top:
            i -= 1
        while j + 1 < len(wave_days) and sc[wave_days[j + 1]]["total"] >= 0.85 * top:
            j += 1
        a, b = wave_days[i], wave_days[j]
        # the day of the widest rain the GFS forecast gives, when it is known (the strongest day of a wave is the
        # day of its widest rain; the drivers' strongest day is spoken of as such)
        rc = {d: fc_cover(st, d) for d in days}
        has_rain = [d for d in wave_days if rc.get(d) is not None]
        rpeak = max(has_rain, key=lambda d: rc[d]) if has_rain and max(rc[d] for d in has_rain) >= 0.01 else None
        lines.append(f"أقرب موجة قادمة {ar_span(start, end)}، وتشتد {ar_span(a, b) if a != b else 'يوم ' + ar_date(a)}"
                     + (f"، وأوسع أمطارها المتوقعة {ar_date(rpeak)} (نحو {ar(round(100 * rc[rpeak]))}٪ من مساحة المملكة "
                        f"بخمسة ملم فأكثر في توقع جي إف إس)" if rpeak else "") + f": {title}.")
        # strength, against the current wave
        cur_days = [d for d in days if day0 <= d <= max(cur_end, day0)]
        cpeak = max(cur_days, key=lambda d: sc[d]["total"])
        ctop = sc[cpeak]["total"]
        c_rain = [d for d in cur_days if rc.get(d) is not None]
        crpeak = max(c_rain, key=lambda d: rc[d]) if c_rain else None
        names = {"mjo": "قوة التذبذب المداري", "warm": "قوة الحدث الدافئ", "pw": "الرطوبة", "trough": "عمق الأخاديد",
                 "mjof": "دعم المكوّن المعزول"}
        diff = sorted(((sc[peak][k] - sc[cpeak][k], k) for k in names), key=lambda x: x[0])
        weaker = [names[k] for x, k in diff if x <= -0.2]
        stronger = [names[k] for x, k in diff[::-1] if x >= 0.2]
        cmp = ("أقوى من" if top >= ctop + 0.3 else "أضعف من" if top <= ctop - 0.3 else "قريبة من")
        why = []
        if stronger:
            why.append(f"أقوى فيها {join(stronger)}")
        if weaker:
            why.append(f"{'وأضعف' if stronger else 'أضعف'} فيها {join(weaker)}")
        # the drivers' strongest day (the strength index) is named as such, never as the wave's strongest day: the
        # rain is spoken of by its own days (the widest rain so far, the widest rain forecast)
        lines.append(f"قوتها المتوقعة: {grade(top)}، فدرجة عواملها {n1(top)} من ٥ في أقوى أيام العوامل {ar_date(peak)}، {cmp} "
                     f"الموجة الحالية التي تبلغ درجة عواملها {n1(ctop)} {ar_date(cpeak)}."
                     + (f" الفرق بينهما: {'، '.join(why)}." if why else "")
                     + (f" ودرجة العوامل تقيس ما يهيئ للأمطار لا مساحتها؛ وأوسع أمطار الموجة الحالية في بقية أيامها "
                        f"متوقع {ar_date(crpeak)} بنحو {ar(round(100 * rc[crpeak]))}٪ من مساحة المملكة في توقع جي إف إس."
                        if crpeak else ""))
        lines.append("وتُحسب الدرجة من خمسة عوامل، لكل منها درجة واحدة كحد أعلى: قوة التذبذب في أطواره الداعمة، "
                     "ووجود الحدث الدافئ في القطاع الداعم، والماء القابل للهطول فوق المعدل، وعمق أخدود الطبقة الوسطى قرب المملكة، "
                     "ومكوّن التذبذب المعزول فوق المملكة. والقوية من ٢٫٦ فأكثر، والقوية جدًا من ٣٫٥.")
        # each driver at the peak, against the peak of the current wave (the same yardstick as the strength line)
        v, v0 = _vals(st, peak), _vals(st, cpeak)
        at0 = ar_date(cpeak)
        ref = (st.get("mjof") or {}).get("z_ref") or 10
        vals = []
        if v["m"]:
            vals.append(f"التذبذب المداري: الطور {ar(v['m']['phase'])} بشدة {n1(v['m']['amp'])}"
                        + ("، طور داعم للجزيرة العربية" if v['m']['phase'] in B.WET_PHASES and v['m']['amp'] >= 1 else "، غير داعم")
                        + (f" ({at0}: الطور {ar(v0['m']['phase'])} بشدة {n1(v0['m']['amp'])})" if v0["m"] else ""))
        if v["w"]:
            vals.append(f"الحدث الدافئ: فوق {B.region_name(v['w'][0])} بشدة {n1(v['w'][1])}"
                        + ("، في القطاع الداعم للجزيرة العربية" if B.favourable(v["w"][0]) else "، خارج القطاع الداعم")
                        + (f" ({at0}: فوق {B.region_name(v0['w'][0])} بشدة {n1(v0['w'][1])})" if v0["w"] else ""))
        if v["pw"]:
            vals.append(f"الرطوبة: الماء القابل للهطول {ar(v['pw'][0])}٪ من المعدل فوق {BOX_NAME[v['pw'][1]]}"
                        + (f" ({at0}: {ar(v0['pw'][0])}٪ فوق {BOX_NAME[v0['pw'][1]]})" if v0["pw"] else ""))
        if v["tr"]:
            vals.append(f"موجات روسبي: أخدود في الطبقة الوسطى فوق {v['tr'][1]} بعمق {n1(-v['tr'][0] / 10)} ديكامتر"
                        + (f" ({at0}: فوق {v0['tr'][1]} بعمق {n1(-v0['tr'][0] / 10)} ديكامتر)" if v0["tr"] else ""))
        if v["mf"]:
            far = (peak - day0).days >= 7
            vals.append(f"مكوّن التذبذب المعزول فوق المملكة: {n1(v['mf'][0])} م، أي {mf_word(v['mf'][0], ref)}"
                        + (f" ({at0}: {n1(v0['mf'][0])} م، {mf_word(v0['mf'][0], ref)})" if v0["mf"] else "")
                        + ("؛ وثقته بعد أسبوع أقل، لأنه يُحسب من آخر أيام توقع جي إف إس" if far else ""))
        if vals:
            lines.append(f"العوامل في أقوى أيام عوامل الموجة القادمة ({ar_date(peak)})، وبين القوسين في أقوى أيام عوامل الموجة الحالية ({ar_date(cpeak)}):")
            lines += [f"• {x}." for x in vals]
        drivers = []
        if span("mjo"):
            ph = []
            for d in span("mjo"):
                m = B.rmm_on(st, d)
                if m and m["phase"] not in ph:
                    ph.append(m["phase"])
            drivers.append(f"التذبذب المداري (مادن-جوليان) في {'الطور' if len(ph) == 1 else 'الأطوار'} "
                           f"{join(ar(p) for p in ph)} {'الداعم' if len(ph) == 1 else 'الداعمة'} للجزيرة العربية {_span_words(span('mjo'), day0)}")
        if span("warm"):
            drivers.append(f"الحدث الدافئ في القطاع الداعم، أي تباعد علوي يرفع الهواء ويغذي الحمل العميق، {_span_words(span('warm'), day0)}")
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
                areas.setdefault(wv["trough"]["area"], []).append(d)
        for a, ds in areas.items():
            drivers.append(f"أخدود في الطبقة الوسطى فوق {a} {_span_words(ds)}")
        seen = set()
        for d in span("cold"):
            area, depth, arr = cold[d]
            if arr in seen:
                continue
            seen.add(arr)
            drivers.append(f"أخدود بارد من الشمال يبلغ محوره {area} يوم {ar_date(arr)} بعمق {num(depth, 1)} ديكامتر")
        lines.append("عواملها وتواريخ كل منها:")
        lines += [f"• {x}." for x in drivers]

        hit = set(boxes)
        for d in span("cold"):
            hit |= _parts(cold[d][0])
        if not span("cold"):
            for a in areas:
                hit |= _parts(a)
        if not hit:
            hit = {"southwest", "west"} if kind == "tropical" else {"north"}
        regs = [BOX_NAME[k] for k in ("west", "southwest", "north", "central", "east") if k in hit]
        lines.append(f"المناطق المتأثرة من الجزيرة العربية: {join(regs)}.")
        lines += _past_cases(st, day0, v, cpeak)
        g = grade(top)
        how = ("أمطار رعدية واسعة تغزر على عدة مناطق، مع احتمال البرد وجريان السيول" if top >= 2.6 else
               "أمطار رعدية متفرقة تغزر أحيانًا، أكثرها على المرتفعات وحيث تلتقي الرطوبة بالأخدود" if top >= 1.8 else
               "أمطار محدودة متفرقة، أغلبها على المرتفعات")
        why_kind = {"mixed": "الدعم المداري يرفع الرطوبة ويغذي الحمل العميق، والأخاديد تنظمه وتوسع رقعته",
                    "tropical": "يغذيها الحمل المداري وحده، فتتركز بعد الظهر والمساء على المرتفعات وتهامة",
                    "troughs": "يحكمها الأخدود وحده، فترافقها رياح وانخفاض في الحرارة وسحب رعدية على مقدمته"}[kind]
        lines.append(f"التأثير المتوقع لموجة {g}: {how}؛ {why_kind}.")
        lines.append("تتضح المناطق والكميات بالتفصيل في تقرير الأمطار حين تدخل الموجة في مدى نموذجنا.")
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
            how = ("ثابت على موعده" if shift == 0 else f"تقدّم {_plural_days(-shift)}" if shift < 0 else f"تأخر {_plural_days(shift)}")
            track = f"متابعة يومية: كان تقدير أمس لبدئها {ar_date(p0)}، وهو اليوم {ar_date(s0)} ({how})"
            if watch["first_start"] != prev["start"] or first != prev["day"]:
                track += f"؛ ورُصدت أول مرة {ar_date(date.fromisoformat(first))} بموعد {ar_date(date.fromisoformat(watch['first_start']))}"
            lines.append(track + ".")
        else:
            watch["first_day"], watch["first_start"] = day0.isoformat(), watch["start"]
            lines.append(f"متابعة يومية: رُصدت هذه الموجة اليوم أول مرة، ويُحدَّث موعدها كل ليلة حتى تصل.")
        left = (s0 - day0).days
        lines.append(f"يتبقى على بدء مرحلة الخصب {_plural_days(left)}." if left > 1 else
                     "تبدأ مرحلة الخصب غدًا." if left == 1 else "بدأت مرحلة الخصب اليوم.")
    return lines, watch
