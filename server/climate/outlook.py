"""Signs of a new rain wave over the Kingdom in the next 15 and 45 days, from the large-scale picture only:
the MJO and the warm event (upper-level divergence) and whether they are, or come back to, the phases that favour
rain over the Arabian Peninsula. No model rain is used here.

Read from:
  - the RMM index observed by the Australian Bureau of Meteorology (last 60 days) and its 15-day projection from
    GFS 200 hPa winds (daily.py);
  - the warm event: equatorial 200 hPa velocity potential anomaly, from the GFS daily analyses of the last 60 days
    and the GFS forecast to 15 days (the Hovmoller of daily.py); its centre is the phase of the zonal wave-1.
Inferred (and said so): beyond 15 days, the return to the favourable phases at the eastward speed measured over
the last month, or, when that speed is not usable, from the usual MJO cycle of 30 to 60 days.
"""
import math
from datetime import date, timedelta

import bigpic as B
from sa_geo import ar, num, ar_date, ar_span, deg

SRC_RMM = "مؤشر مادن-جوليان الرصدي من مكتب الأرصاد الأسترالي وإسقاطه من رياح جي إف إس العلوية لخمسة عشر يومًا"
SRC_WARM = ("الحدث الدافئ: شذوذ جهد السرعة عند ٢٠٠ هكتوباسكال فوق خط الاستواء، من تحليلات جي إف إس اليومية "
            "لآخر ستين يومًا وتوقعه لخمسة عشر يومًا")
HEADING = "ملامح موجة مطرية جديدة: الصورة الكبرى (١٥ و٤٥ يومًا)"


def _rmm_angle(x):
    return math.degrees(math.atan2(x["r2"], x["r1"])) % 360


def outlook(st, day0, log=print):
    lines = []
    if not st.get("wet_season"):
        lines.append("خارج موسم الأمطار الذي يرتبط فيه التذبذب المداري بأمطار المملكة (نوفمبر إلى أبريل)، "
                     "فلا يُستنتج منه موعد موجة مطرية.")
        return {"heading": HEADING, "lines": lines}
    obs = st.get("rmm_obs") or []
    fc = [x for x in (st.get("rmm_fc") or []) if x["d"] >= day0.isoformat()]
    rmm = {x["d"]: x for x in obs + (st.get("rmm_fc") or [])}
    w1 = B.wave1(st["hov"]) if st.get("hov") else []
    warm = {d: (lon, amp) for d, lon, amp in w1}
    end15 = day0 + timedelta(days=15)
    good_m = lambda x: x is not None and x["amp"] >= 1 and x["phase"] in B.WET_PHASES
    good_w = lambda w: w is not None and w[1] >= 4 and B.favourable(w[0])

    # 1. now
    m0 = B.rmm_on(st, day0)
    wv0 = warm.get(day0.isoformat())
    now = []
    if m0:
        now.append(f"التذبذب المداري في الطور {ar(m0['phase'])} بشدة {num(m0['amp'], 1)}"
                   f" ({'طور محفز للأمطار' if good_m(m0) else 'ضعيف لا أثر واضح له' if m0['amp'] < 1 else 'طور غير محفز'})")
    if wv0:
        now.append(f"والحدث الدافئ متمركز فوق {B.region_name(wv0[0])}"
                   f" ({'في القطاع المحفز للجزيرة العربية' if good_w(wv0) else 'خارج القطاع المحفز'})")
    if now:
        lines.append("الآن: " + "، ".join(now) + ".")

    # 2. the next 15 days: the GFS projection of both
    fav = []
    for k in range(16):
        d = day0 + timedelta(days=k)
        m, w = rmm.get(d.isoformat()), warm.get(d.isoformat())
        fav.append((d, good_m(m), good_w(w), m, w))
    both = [x for x in fav if x[1] and x[2]]
    either = [x for x in fav if x[1] or x[2]]
    leave, last_good = None, None
    head = f"خلال ١٥ يومًا (قراءة من {SRC_RMM}، ومن {SRC_WARM}): "
    if fav[0][1] or fav[0][2]:
        k = 0
        while k + 1 < len(fav) and (fav[k + 1][1] or fav[k + 1][2]):
            k += 1
        last_good = fav[k][0]
        if k + 1 < len(fav):
            leave = fav[k + 1][0]
            nx = fav[k + 1]
            what = ("التذبذب المداري والحدث الدافئ" if fav[0][1] and fav[0][2] else
                    "التذبذب المداري" if fav[0][1] else "الحدث الدافئ")
            txt = f"يبقى {what} في الوضع المحفز للأمطار حتى {ar_date(last_good)}، ثم"
            ends = []
            if nx[3] and (not m0 or nx[3]["phase"] != m0["phase"]):
                ends.append(f"يتجه التذبذب إلى الطور {ar(nx[3]['phase'])}")
            if nx[4] and not good_w(nx[4]):
                ends.append(f"يبتعد الحدث الدافئ نحو {B.region_name(nx[4][0])}")
            txt += " " + (" و".join(ends) if ends else "تضعف الإشارة")
            if fav[0][2] and not fav[0][1] and m0 and m0["amp"] >= 1:
                txt += f"، أما مؤشر التذبذب نفسه ففي الطور {ar(m0['phase'])} غير المحفز"
            lines.append(head + txt + ".")
        else:
            lines.append(head + "تبقى الصورة الكبرى محفزة للأمطار حتى نهاية مدى الإسقاط، فتبقى الحالات المطرية مدعومة.")
    elif either:
        x = both[0] if both else either[0]
        which = ("يعود التذبذب المداري والحدث الدافئ معًا" if x[1] and x[2] else
                 "يعود التذبذب المداري" if x[1] else "يعود الحدث الدافئ")
        lines.append(head + f"إشارة: {which} إلى الأطوار المحفزة للجزيرة العربية يوم {ar_date(x[0])}"
                     + (f" (الطور {ar(x[3]['phase'])} بشدة {num(x[3]['amp'], 1)})" if x[3] else "")
                     + (f"، والحدث الدافئ فوق {B.region_name(x[4][0])}" if x[4] else "") + ".")
    else:
        lines.append(head + "لا يعود التذبذب ولا الحدث الدافئ إلى الأطوار المحفزة للجزيرة العربية في مدى الإسقاط.")

    # 3. 15 to 45 days: inference from the eastward speed of both over the last month (analyses and projection)
    infer = []
    still = fav[-1][1] or fav[-1][2]
    rel = lambda s: (date.fromisoformat(s) - day0).days
    ser = [x for x in obs if x["d"] >= (day0 - timedelta(days=30)).isoformat() and x["d"] < day0.isoformat()] + fc
    sp_m = B.speed([_rmm_angle(x) for x in ser], [rel(x["d"]) for x in ser]) if len(ser) >= 8 else None
    wser = [(d, lon) for d, lon, amp in w1 if d >= (day0 - timedelta(days=30)).isoformat() and amp >= 3]
    sp_w = B.speed([lon for _, lon in wser], [rel(d) for d, _ in wser]) if len(wser) >= 8 else None
    last_m = fc[-1] if fc else None
    last_w = w1[-1] if w1 else None
    if not still:
        if last_m and sp_m and 3 <= sp_m <= 20 and last_m["amp"] >= 1:
            need = (90 - _rmm_angle(last_m)) % 360                     # phase 7 starts at 90 degrees
            d = date.fromisoformat(last_m["d"]) + timedelta(days=round(need / sp_m))
            infer.append(("التذبذب المداري", d, f"يدور شرقًا بنحو {deg(sp_m)} في اليوم في الشهر الأخير "
                                                f"(دورة كاملة في نحو {num(360 / sp_m)} يومًا)"))
        if last_w and sp_w and 3 <= sp_w <= 20:
            need = (B.SECTOR[0] - last_w[1]) % 360
            d = date.fromisoformat(last_w[0]) + timedelta(days=round(need / sp_w))
            infer.append(("الحدث الدافئ", d, f"ينتقل شرقًا بنحو {deg(sp_w)} في اليوم في الشهر الأخير"))
    for name, d, why in infer:
        if (d - day0).days <= 46:
            lines.append(f"من ١٥ إلى ٤٥ يومًا (استنتاج من سرعة الانتقال): {name} {why}، فإن حافظ على سرعته "
                         f"يعود إلى القطاع المحفز للجزيرة العربية قرابة {ar_date(d)}، بهامش أسبوع تقريبًا.")
        else:
            lines.append(f"من ١٥ إلى ٤٥ يومًا (استنتاج من سرعة الانتقال): {name} {why}، وبهذه السرعة لا يعود إلى "
                         f"القطاع المحفز قبل {ar_date(d)}، أي بعد مدى الخمسة والأربعين يومًا.")
    usual = None
    if not infer:
        stall = (sp_m is not None and abs(sp_m) < 3) or (sp_w is not None and abs(sp_w) < 3)
        why = ("التذبذب شبه ثابت في موضعه في الشهر الأخير، فلا تُقاس له سرعة يُبنى عليها" if stall else
               "لا تُقاس للتذبذب سرعة منتظمة في الشهر الأخير")
        if still:
            lines.append(f"من ١٥ إلى ٤٥ يومًا (استنتاج): الصورة الكبرى ما زالت محفزة في آخر الإسقاط، ولا يُعرف متى "
                         f"تخرج منها؛ {why}.")
        else:
            out_d = leave or end15
            a, b = out_d + timedelta(days=15), out_d + timedelta(days=30)
            usual = (a, b)
            lines.append(f"من ١٥ إلى ٤٥ يومًا (استنتاج من الدورة المعتادة): {why}. وبالدورة المعتادة للتذبذب "
                         f"(٣٠ إلى ٦٠ يومًا، يقضي نصفها تقريبًا في الأطوار غير المحفزة) تعود الأطوار المحفزة للجزيرة "
                         f"العربية {ar_span(a, b)} تقريبًا، بشرط أن يحافظ التذبذب على شدته. الثقة منخفضة.")
    if last_m and last_m["amp"] < 1:
        lines.append("تنبيه: شدة التذبذب في آخر الإسقاط دون ١، وإن ضعف فقد لا يحمل إشارة واضحة حين يعود.")

    # 4. the signal, in one line
    near = sorted(d for _, d, _ in infer if 15 <= (d - day0).days <= 46)
    if last_good:
        sig = (f"الصورة الكبرى محفزة الآن حتى {ar_date(last_good)}" if leave else
               "الصورة الكبرى محفزة الآن وحتى آخر مدى الإسقاط")
    elif either:
        sig = f"إشارة عودة إلى الأطوار المحفزة يوم {ar_date((both[0] if both else either[0])[0])}"
    else:
        sig = "لا إشارة عودة في الأيام الخمسة عشر القادمة"
    if len(near) == 2 and (near[1] - near[0]).days <= 7:
        sig += f"؛ وتتفق سرعة التذبذب والحدث الدافئ على عودة جديدة {ar_span(near[0], near[1])}، والثقة متوسطة"
    elif near:
        sig += f"؛ وأقرب عودة مستنتجة بعد ذلك قرابة {ar_date(near[0])}، والثقة منخفضة"
    elif usual:
        sig += f"؛ والعودة المستنتجة من الدورة المعتادة {ar_span(*usual)}، والثقة منخفضة"
    lines.append("الخلاصة: " + sig + ". يُحدَّث كل يوم، وأي تغير في الإشارة يظهر هنا أولًا.")
    return {"heading": HEADING, "lines": lines}
