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
    sections.append({"heading": f"الوضع الحالي ({ar_date(day0)})", "lines": now})

    # ---------------------------------------------------------------- 2. the nearest wave to come, tracked day by day
    lines, watch = next_wave(st, day0, days, fac, cur_end)
    st["wave_watch"] = watch
    sections.append({"heading": "أقرب موجة قادمة", "lines": lines})
    return sections


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
        lines.append(f"أقرب موجة قادمة {ar_span(start, end)}: {title}.")
        drivers = []
        if span("mjo"):
            ph = []
            for d in span("mjo"):
                m = B.rmm_on(st, d)
                if m and m["phase"] not in ph:
                    ph.append(m["phase"])
            drivers.append(f"التذبذب المداري (مادن-جوليان) في {'الطور' if len(ph) == 1 else 'الأطوار'} "
                           f"{join(ar(p) for p in ph)} {'المحفز' if len(ph) == 1 else 'المحفزة'} للجزيرة العربية {_span_words(span('mjo'), day0)}")
        if span("warm"):
            drivers.append(f"الحدث الدافئ في القطاع المحفز، أي تباعد علوي يرفع الهواء ويغذي الحمل العميق، {_span_words(span('warm'), day0)}")
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
        lines.append({"mixed": "التأثير المتوقع: الأقوى بين أنواع الموجات؛ الدعم المداري يرفع الرطوبة والحمل العميق، "
                               "والأخاديد تنظمه، فتتسع رقعة الأمطار الرعدية وتغزر أحيانًا مع احتمال البرد.",
                      "tropical": "التأثير المتوقع: أمطار رعدية يغذيها الحمل المداري على المرتفعات وتهامة والمناطق الرطبة، "
                                  "تتركز بعد الظهر والمساء، وانتشارها أضيق ما لم يصلها أخدود.",
                      "troughs": "التأثير المتوقع: يحكمه الأخدود؛ رياح وانخفاض في الحرارة وسحب رعدية على مقدمته، "
                                 "وتبقى الأمطار متفرقة ما لم تتوفر رطوبة كافية."}[kind])
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
