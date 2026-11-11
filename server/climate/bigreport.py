"""The big-picture report: what drives the weather over the Kingdom now and in the next 15 days and beyond.

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

    # ---------------------------------------------------------------- 2. the nearest wave to come
    nxt = []
    start = next((d for d in days if d > cur_end + timedelta(days=1) and _supported(fac[d])), None)
    if start:
        end = start
        for d in days[days.index(start) + 1:]:
            if _supported(fac[d]):
                end = d
            else:
                break
        keys = {}
        for d in days[days.index(start):days.index(end) + 1]:
            for k, w in fac[d]:
                keys.setdefault(k, w)
        regs = []
        for d in days[days.index(start):days.index(end) + 1]:
            row = next((r for r in st.get("pw", []) if r["d"] == d.isoformat()), None)
            if row:
                regs += [BOX_NAME[k] for k in BOX_NAME if k in row and row[k]["pct"] >= 150 and BOX_NAME[k] not in regs]
        nxt.append(f"أقرب موجة قادمة {ar_span(start, end)}، تقودها: {join(keys.values())}"
                   + (f"؛ والمناطق الأقرب للتأثر بها {join(regs)}" if regs else "") + ".")
        cold = [t for t in (st.get("troughs") or []) if t.get("arrive") and start - timedelta(days=1) <= date.fromisoformat(t["arrive"]) <= end + timedelta(days=1)]
        if cold:
            c = cold[0]
            nxt.append(f"ويرافقها أخدود بارد من الشمال يبلغ {TR.kingdom_area(c['days'][-1]['lon'])} يوم {ar_date(date.fromisoformat(c['arrive']))}، "
                       "فيزيد عدم الاستقرار ويهيئ لعواصف رعدية مع انخفاض في درجات الحرارة.")
        nxt.append("التأثيرات المتوقعة: أمطار رعدية متفرقة إلى غزيرة أحيانًا حيث تجتمع الرطوبة مع صعود الهواء، "
                   "وتتضح المناطق والكميات في تقرير الأمطار حين تدخل في مدى نموذجنا.")
    else:
        nxt.append("لا تظهر في توقع جي إف إس لخمسة عشر يومًا موجة مطرية واسعة جديدة تجتمع فيها الرطوبة مع الأخدود أو التذبذب.")
    sections.append({"heading": "أقرب موجة قادمة", "lines": nxt})

    # ---------------------------------------------------------------- 3. northern cold troughs, day by day
    tl = []
    for c in (st.get("troughs") or [])[:3]:
        arrive = date.fromisoformat(c["arrive"]) if c.get("arrive") else None
        first = c["days"][0]
        head = (f"أخدود بارد يبدأ {ar_date(date.fromisoformat(first['d']))} فوق {TR.place(first['lat'], first['lon'])} "
                f"(عمق موجته {num(-first['depth'], 1)} ديكامتر"
                + (f"، وهواؤه أبرد من محيطه بنحو {num(-first['cold'], 1)} درجة عند ٥٠٠" if first.get("cold") is not None and first["cold"] <= -1 else "")
                + ")")
        head += (f"، ويصل محوره إلى {TR.kingdom_area(next(t for t in c['days'] if t['d'] == c['arrive'])['tip'][1])} يوم {ar_date(arrive)}."
                 if arrive else "، ولا يبلغ المملكة في مدى التوقع بل يمر شمالها.")
        steps = []
        for t in c["days"]:
            d = date.fromisoformat(t["d"])
            if arrive and d > arrive + timedelta(days=1):
                break
            tip = t["tip"]
            steps.append(f"{ar_date(d)}: مركزه فوق {TR.place(t['lat'], t['lon'])}، ومحوره يمتد جنوبًا حتى {TR.place(tip[0], tip[1])} "
                         f"(قرابة {num(tip[0])}° شمالًا)، وعمقه {num(-t['depth'], 1)} ديكامتر")
        tl.append(head + " مساره يومًا بيوم: " + "؛ ".join(steps) + ".")
        if arrive:
            deep = min(t["depth"] for t in c["days"])
            tip_lon = next(t for t in c["days"] if t["d"] == c["arrive"])["tip"][1]
            tl.append(f"أثره المتوقع: {'تعمق قوي' if deep <= -10 else 'تعمق متوسط'} يدفع هواءً باردًا نحو {TR.kingdom_area(tip_lon)}، "
                      "فتنخفض درجات الحرارة وتنشط الرياح، وإن صادف رطوبة كافية تكونت سحب رعدية على مقدمته.")
    if not tl:
        tl.append("لا أخاديد باردة شمالية عميقة متجهة نحو المملكة في توقع جي إف إس لخمسة عشر يومًا.")
    sections.append({"heading": "الأخاديد الباردة الشمالية (١٥ يومًا)", "lines": tl})

    # ---------------------------------------------------------------- 4. cold waves
    cw = []
    for w in st.get("coldwaves") or []:
        a, b = date.fromisoformat(w["a"]), date.fromisoformat(w["b"])
        cw.append(f"{'موجة باردة قوية' if w['strong'] else 'موجة باردة'} على {join(w['regions'])} {ar_span(a, b)} "
                  f"(مدتها {ar(w['days'])} {'أيام' if 3 <= w['days'] <= 10 else 'يومًا' if w['days'] > 10 else 'يومان'})، "
                  f"تنخفض فيها الصغرى عن معدلها بنحو {num(-w['anom'])} درجات، وأدناها {num(w['tmin'])}° في {w['town']}.")
    if not cw:
        cw.append("لا موجات باردة في الأيام الستة عشر القادمة: تبقى الصغرى قريبة من معدلاتها أو أعلى.")
    sections.append({"heading": "الموجات الباردة", "lines": cw})

    # ---------------------------------------------------------------- 5. beyond 15 days
    try:
        ol = outlook.outlook(st, day0)
        keep = [x for x in ol["lines"] if x.startswith(("من ١٥", "التذبذب المداري بعد", "تنبيه"))]
        sections.append({"heading": "النافذة البعيدة (١٥ إلى ٤٥ يومًا)", "lines": keep or ol["lines"][-1:]})
    except Exception as e:
        print("outlook failed", repr(e), flush=True)
    return sections
