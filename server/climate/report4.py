"""The chief analyst's nightly report (Fahad, 26 Nov 2026: the charter «كبير المحللين الجويين», saved verbatim in
docs/ANALYST.md on main).

Nine sections, each with its own predictive value and nothing said twice:
  ١ الخلاصة التنفيذية      conclusions only (today, tonight, the coming wave, the deciding variable, the biggest change)
  ٢ التشخيص الديناميكي     the upper systems, the tropics and the mid-latitudes, and what they mean together
  ٣ الرطوبة والحمل الحراري  moisture sources, transport and depth, the low-level event, the fuel; what is not readable
  ٤ التوقع الجغرافي والتوقيت places and hours, the four coincidence tests per region, supporting/limiting/suppressing,
                           and the numerical rain kept apart (for comparison only)
  ٥ الخلايا البحرية والتضاريسية the night sea cells (tonight and the coming nights) and the terrain cells of Makkah
  ٦ الموجة القادمة          the wave study (report3.waves without the season and the sea cells), three scenarios
  ٧ النظرة الموسمية         the seasonal background (season.py), kept apart from the daily forecast
  ٨ التغير عن التشغيل السابق only the changes that move the forecast decision (snapshot of each run in mjo.json)
  ٩ الثقة وحدود التوقع      confidence split into timing / place / intensity / spread, the inventory of the site's maps
                           (source, model, run, level, validity, read or not), and the known limits
Doctrine kept: the forecast is read from the ingredients, never from model rain (Fahad 19 and 25 Nov 2026); the sea
cells, the northern break and the daily analogs (26 Nov 2026) stay.
"""
from datetime import date, timedelta

import re

import report2 as R2
import report3 as R3
from report2 import ar, num, jl, sec, ar_date

L3 = ("منخفضة", "متوسطة", "عالية")
KIND = {"mixed": "مدارية أخدودية", "tropical": "مدارية", "troughs": "أخدودية"}
HEAD = ("الخلاصة التنفيذية", "التشخيص الديناميكي للحالة", "تحليل الرطوبة والحمل الحراري", "التوقع الجغرافي والتوقيت",
        "الخلايا البحرية والتضاريسية", "الموجة القادمة", "النظرة الموسمية", "التغير عن التشغيل السابق",
        "الثقة وحدود التوقع")
D9 = "١٢٣٤٥٦٧٨٩"


def _down(c, k=1):
    return L3[max(0, L3.index(c) - k)]


def n1(x):
    return R2.n1(x) if x >= 0 else "‎−" + R2.n1(-x)


def _cyc_words(cyc):
    try:
        d = date(int(cyc[:4]), int(cyc[4:6]), int(cyc[6:8]))
        return f"تشغيل {ar(int(cyc[8:10]))} غرينتش {ar_date(d, weekday=False)}"
    except Exception:  # noqa: BLE001
        return "تشغيل الليلة"


# ------------------------------------------------------------------ the reading, done once
def read(st, rep):
    import bigreport as BR
    import makkah_story as MS
    day0 = date.fromisoformat(rep.get("day") or st["days"][0])
    C = {"day0": day0, "st": st}
    try:
        C["W"] = R3.cold_wave(st, day0)
    except Exception as e:  # noqa: BLE001
        print("report4: cold wave failed:", repr(e), flush=True)
        C["W"] = None
    C["sc"] = BR.strength(st, day0)
    C["ws"] = C["sc"]["total"]
    rows = R3.region_reading(st, None, [], day0, C["W"], big=min(1.0, C["ws"] / 3))
    # the charter: no high level from a partial agreement. A region with two of the four coincidence tests or fewer
    # fully met stays «متوسطة» at most, three of four «مرجحة» at most
    W = C["W"] or {}
    C["no_trough"] = not W.get("trough") and not W.get("falls")
    a_min = min([x[1] for x in (W.get("anom") or {}).values()] or [0])
    for r in rows:
        # cooling aloft counts only with a real 500 hPa fall over the region or 1 degree below normal or more
        if r.get("trough") and not (W.get("trough") or r["name"] in (W.get("falls") or {}) or a_min <= -1):
            r["cool_weak"] = True
    for r in rows:
        if r.get("vague"):
            continue
        full = sum(1 for a, _ in tests(r) if a == "متحقق")
        cap = "ضعيفة" if full <= 1 else "متوسطة" if full == 2 else "مرجحة" if full == 3 else "قوية"
        if R3.LEVEL4.index(r["level"]) > R3.LEVEL4.index(cap):
            r["cover"] *= R3.COVER_OF[cap] / max(R3.COVER_OF[r["level"]], 1e-6)
            r["level0"], r["level"] = r["level"], cap
            if cap == "ضعيفة":       # passing showers: no place is moderate or heavy
                r["row"]["light"] = list(dict.fromkeys(r["row"]["heavy"] + r["row"]["moderate"] + r["row"]["light"]))
                r["row"]["heavy"], r["row"]["moderate"] = [], []
    rows.sort(key=lambda r: (r["name"] != "مكة المكرمة", -R3.LEVEL4.index(r["level"])))
    C["rows"] = rows
    C["lw"] = dict(getattr(R3.region_reading, "lowwarm", None) or {})
    try:
        C["RD"] = MS.read(st, True)
    except Exception:  # noqa: BLE001
        C["RD"] = {}
    C["kind"] = R2.case_kind(st, day0)
    C["fac0"] = BR._day_factors(st, day0)
    ksa_area = 2.15e6
    spread = sum((r["area"] or 0) * r["cover"] for r in rows) / ksa_area
    sfr = sum((r["area"] or 0) * r.get("strat", 0) for r in rows) / ksa_area
    C["spread"] = max(spread, 0.15 if C["ws"] >= 3.0 else 0.05 if C["ws"] >= 2.6 else 0.0, sfr)
    C["band"] = ("محدود، أقل من ٣٪ من مساحة المملكة" if C["spread"] < 0.03 else "متوسط، بين ٣ و١٠٪"
                 if C["spread"] < 0.10 else "واسع، أكثر من ١٠٪")
    try:
        C["weak"] = R3.weak_reasons(st, day0, C["W"]) if C["ws"] < 2.6 else []
    except Exception:  # noqa: BLE001
        C["weak"] = []
    try:
        wl, days, score, fac = R3.wave_set(st, day0)
    except Exception as e:  # noqa: BLE001
        print("report4: wave set failed:", repr(e), flush=True)
        wl, days, score, fac = [], [], {}, {}
    C["wl"], C["days"] = wl, days
    C["nw"] = next((x for x in wl if not x.get("sign")), wl[0] if wl else None)
    C["nb"] = nb_info(st, C["nw"]) if C["nw"] else None
    C["sea0"] = next((x for x in st.get("seacell") or [] if x["d"] == day0.isoformat()), None)
    C["an"] = st.get("analogs")
    C["ingr"] = {r["d"]: r for r in st.get("ingr") or []}
    C["wr"] = {r["d"]: r for r in st.get("wave_rain") or [] if r.get("kind") == "ingr"}
    return C


def nb_info(st, w):
    """the numbers behind report3.north_break: the easternmost trough tip, its southernmost latitude, the ridge east"""
    wd = {(w["start"] + timedelta(days=k)).isoformat() for k in range((w["end"] - w["start"]).days + 1)}
    tips = [x for sy in st.get("troughs") or [] for x in sy.get("days") or []
            if x["d"] in wd and x.get("tip") and 20 <= x["tip"][1] <= 45]
    ridges = [x["ridge"]["v"] for x in st.get("waves") or [] if x["d"] in wd and x.get("ridge") and x["ridge"]["lon"] >= 48]
    if not tips:
        return None
    return {"lon_min": min(x["tip"][1] for x in tips), "lon_max": max(x["tip"][1] for x in tips),
            "lat_min": min(x["tip"][0] for x in tips), "ridge": max(ridges or [0]),
            "blocked": max(x["tip"][1] for x in tips) <= 34 and max(ridges or [0]) >= 50}


def _sea_level(v):
    import seacell
    return seacell.level(v)


def _sea_places(r, lv_min=1):
    import seacell
    lv = seacell.levels(r)
    return [seacell.NAME[k] for k, v in sorted(r["si"].items(), key=lambda kv: -kv[1]) if lv[k] >= lv_min]


SHORT = {"wajh": "الوجه", "umluj": "أملج", "yanbu": "ينبع", "rais": "الرايس", "north": "رابغ", "jeddah": "جدة",
         "south": "الليث", "qunf": "القنفذة"}


def _runs(ks, order):
    """«بين أملج ورابغ وعلى القنفذة»: contiguous stretches as one span, north to south"""
    if not ks:
        return ""
    idx = sorted(order.index(k) for k in ks)
    runs, cur = [], [idx[0]]
    for i in idx[1:]:
        if i == cur[-1] + 1:
            cur.append(i)
        else:
            runs.append(cur)
            cur = [i]
    runs.append(cur)
    parts = [f"على {SHORT[order[r[0]]]}" if len(r) == 1 else f"بين {SHORT[order[r[0]]]} و{SHORT[order[r[-1]]]}" for r in runs]
    return "، و".join(parts)


def wave_reach(st, w):
    """[(zone, dz, t5, w)] where the trough's forcing reaches on the wave's days (troughreach.py), or []"""
    import troughreach
    if not w or not st.get("troughreach"):
        return []
    return troughreach.reach(st["troughreach"], w["start"] - timedelta(days=1), w["end"])


def reach_short(R, n=5):
    """«شمال البحر الأحمر، وساحل تبوك، والمدينة المنورة…» sea and coasts first"""
    import troughreach
    sea = [x for x in R if x[0] in troughreach.SEA]
    land = [x for x in R if x[0] not in troughreach.SEA]
    return jl([troughreach.NAME[x[0]] for x in (sea + land)[:n]])


def reach_brief(R):
    """«البحر الأحمر وسواحله من الوجه إلى رابغ، والجوف، وتبوك…»: the trough's reach in one short line, sea first"""
    import troughreach
    ks = [x[0] for x in R]
    south = ("جدة" if {"sea_s", "jeddah_makkah"} & set(ks) else "رابغ" if {"sea_m", "c_madinah"} & set(ks)
             else "أملج" if {"sea_n", "c_tabuk"} & set(ks) else None)
    out = [f"البحر الأحمر وسواحله من الوجه إلى {south}"] if south else []
    nm = {"jouf": "الجوف", "nb": "الحدود الشمالية"}
    out += [nm.get(k, troughreach.NAME[k]) for k in ks if k not in troughreach.SEA][:5]
    return jl(out)


def wave_sea(st, w):
    """the sea cells of a wave's days (the night before its first day to its last), in words, or None.
    27 Nov 2026 (Fahad: «حالة غزيرة جدا بين املج ورابغ بحرية ثم تخرج الى المدينة وحائل»): when the trough index leaves the
    coasts at zero but the sea cells are «مرجحة» or stronger, they are part of the wave, not a side line."""
    import seacell
    if not w:
        return None
    d0, d1 = (w["start"] - timedelta(days=1)).isoformat(), w["end"].isoformat()
    rows = [r for r in st.get("seacell") or [] if d0 <= r["d"] <= d1 and r.get("times")]
    best, ks, path, nights = {}, [], [], []
    for r in rows:
        lv = seacell.levels(r)
        hit = [k for k in lv if lv[k] >= 2]
        if hit:
            nights.append(r["d"])
        for k in hit:
            best[k] = max(best.get(k, 0), lv[k])
        path += [p for p in r.get("path") or [] if p not in path]
    if not best:
        return None
    order = [k for k, *_ in seacell.STRETCHES]
    strong = _runs([k for k in order if best.get(k) == 3], order)
    likely = _runs([k for k in order if best.get(k) == 2], order)
    a, b = date.fromisoformat(nights[0]), date.fromisoformat(nights[-1]) + timedelta(days=1)
    t = "خلايا بحرية "
    if strong:
        t += f"مرجحة وقد تكون غزيرة {strong}" + (f"، ومرجحة {likely}" if likely else "")
    else:
        t += f"مرجحة {likely}"
    t += f" من مساء {ar_date(a)} إلى عصر {ar_date(b)}"
    if path:
        t += f"، تخرج منها مع الرياح الجنوبية الغربية إلى {jl([seacell.INLAND[k][0] for k in path])}"
    return t


# ------------------------------------------------------------------ 1. executive summary
def s_exec(C):
    import bigreport as BR
    day0, rows = C["day0"], C["rows"]
    lab = C["kind"][0] if not C.get("no_trough") else "حمل حراري تضاريسي محلي بلا أخدود"
    B = []
    t = (f"اليوم {ar_date(day0)}: حالة {BR.grade(C['ws'])} (قوتها {R2.n1(C['ws'])} من ٥)، تصنيفها {lab}، "
         f"وانتشار المطر المقدّر {C['band']}.")
    named = [r for r in rows if not r.get("vague")]
    if named:
        mech = []
        for r in named:      # the mechanism of each region's strongest place, in the regions' order
            for k in ("heavy", "moderate", "light"):
                c = next((r["why"].get(p) for p in r["row"][k] if r["why"].get(p)), None)
                if c:
                    key = c.split(" تحت ")[0].replace(" الرطب", "")
                    if key not in [m_.split(" تحت ")[0].replace(" الرطب", "") for m_ in mech]:
                        mech.append(c)
                    break
        t += (" والمطر المحتمل محصور في " + jl([f"{r['name']} ({'زخات متفرقة محتملة' if r['level'] == 'ضعيفة' else 'فرصة ' + r['level']})" for r in named])
              + (f"، وآليته {jl(mech[:2])}" if mech else "") + "، بعد الظهر حتى المغرب.")
    else:
        t += " ولا تجتمع مكونات المطر على أي منطقة."
    if C["weak"]:
        t += f" وأهم ما يكبح الحالة {C['weak'][0]}."
    B.append({"p": t})
    s0 = C["sea0"]
    if s0 and s0.get("si"):
        lk = _sea_places(s0)
        import seacell
        mx = max(seacell.levels(s0).values() or [0])
        mk = ("، وقد تبلغ بعض خلاياها مكة والجموم." if s0.get("plain", 0) >= seacell.PLAIN_MIN
              else "، ولا يُتوقع أن تبلغ مكة والجموم.")
        B.append({"p": ("الليلة: خلايا بحرية " + seacell.WORD[max(mx, 1)] + f" على {jl(lk)}" + mk if lk else
                        "الليلة: لا تجتمع مكونات الخلايا البحرية على السواحل الغربية.")})
    w = C["nw"]
    if w:
        ws_ = wave_sea(C["st"], w)
        R_ = wave_reach(C["st"], w)
        t = (f"أقرب موجة: {R3.span_of_(w) if w['start'] != w['end'] else ar_date(w['start'])}، {KIND[w['kind']]}، "
             f"أوسع أيامها {ar_date(w['peak'])}")
        if R_:
            t += (f"، يقودها أخدود قوي من الشمال الغربي يبلغ تأثيره أمام محوره {reach_brief(R_)}"
                  + ("، وإن بقي محوره غرب البحر الأحمر" if C["nb"] and C["nb"]["blocked"] else ""))
        if ws_:
            rest = R3.land_rest(w)
            t += (f". وقلبها الغزير غربًا {ws_}"
                  + (f"، ثم أمطار أوسع وأخف على {jl(rest[:3])}" if rest else ""))
        else:
            t += f"، وتتركز مكوناتها على {jl(w['regions'][:3])}"
        B.append({"p": t + "."})
    a = C["an"]
    if a and a.get("rh") is not None and w:
        B.append({"p": f"المتغير الحاسم في هذه الموجة لمكة وجدة: الرطوبة عند ٧٠٠ هكتوباسكال غرب المملكة، وهي في توقع "
                       f"الليلة {ar(a['rh'])}٪ والحد الذي رافق كل حالة غزيرة مشابهة ٤٥٪ (التفصيل في القسم ٦)."})
    ch = C.get("changes") or []
    if ch:
        B.append({"p": "أبرز تغير عن التشغيل السابق: " + ch[0]["short"] + "."})
    return sec(HEAD[0], "sum", B)


# ------------------------------------------------------------------ 2. dynamic diagnosis
def _factor_table(C):
    rows = R3._factor_rows(C["st"], C["day0"])
    src = {"التذبذب المداري (مادن-جوليان)": "رصد الوكالة اليابانية، ثم إسقاط بسرعته المعتادة",
           "مكوّن التذبذب عند ٨٠٠ هكتوباسكال": "توقع جي إف إس مُرشَّح",
           "موجات روسبي الاستوائية": "توقع جي إف إس، ٢٠٠ هكتوباسكال",
           "موجات كلفن": "توقع جي إف إس، ٢٠٠ هكتوباسكال",
           "الحدث الدافئ (التباعد العلوي)": "توقع جي إف إس، ٢٠٠ هكتوباسكال",
           "الرطوبة": "توقع الأوروبي" if C["st"].get("pw_model") == "ecmwf" else "توقع جي إف إس",
           "الأخدود عند ٥٠٠ هكتوباسكال": "توقع جي إف إس",
           "حرارة ٥٠٠ هكتوباسكال فوق الحجاز (التبريد العلوي)": "توقع جي إف إس"}
    shallow = any("ضحل" in x for x in C["kind"][2])
    out = []
    for r in rows:
        v = r[1]
        if r[0] == "الأخدود عند ٥٠٠ هكتوباسكال" and v == "لا أخدود يُعتد به" and shallow:
            v = "أخدود ضحل دون ٢٫٥ ديكامتر"
        out.append([r[0], v, r[2], src.get(r[0], "توقع")])
    return out


def s_dyn(C):
    st, day0, W, RD = C["st"], C["day0"], C["W"], C["RD"]
    B = []
    # the upper systems: the cold wave reading (its own sub-heading dropped: this whole section is the diagnosis)
    if W:
        for b in R3.cold_wave_blocks(st, day0, effect=False, W=W):
            if "h" in b:
                continue
            if "p" in b and not W.get("falls") and "هبوط في سطح ٥٠٠" in b["p"]:
                # no height fall was found: say only what the signs show (no exaggeration)
                a = min([x[1] for x in (W.get("anom") or {}).values()] or [0])
                b = {"p": "لا موجة علوية باردة بالمعنى الكامل: لا أخدود واضح المحور فوق المملكة ولا هبوط يُعتد به في سطح "
                          f"٥٠٠ هكتوباسكال، بل برودة طفيفة في الطبقات العليا ({R2.n1(abs(a))}° دون المعدل)."}
            if "p" in b and b["p"].startswith("العلامات: ") and B and B[-1].get("p", "").startswith("لا موجة علوية باردة"):
                B[-1] = {"p": B[-1]["p"].split("، بل برودة طفيفة")[0] + "، بل برودة طفيفة: "
                         + b["p"].removeprefix("العلامات: ")}
                continue
            B.append(b)
    wv = next((x for x in st.get("waves") or [] if x["d"] == day0.isoformat()), {})
    if wv.get("ridge"):
        B.append({"p": f"وعند ٥٠٠ هكتوباسكال مرتفع شذوذه {ar(int(round(wv['ridge']['v'])))} م قرب خط الطول "
                       f"{ar(int(round(wv['ridge']['lon'])))}° شرقًا (توقع جي إف إس)."})
    cues = RD.get("cue_aloft") or []
    jet = [c for c in cues if "النفاث" in c]
    if jet:
        B.append({"p": f"و{jet[0]} (توقع جي إف إس)، ولا يُقرأ الليلة موضع التباعد حول محوره، فلا يُبنى عليه رفع."})
    B.append({"table": {"head": ["العنصر", "قيمته اليوم", "أثره", "المصدر"], "rows": _factor_table(C)}})
    lab, Tt, Rr = C["kind"]
    weak = list(C["weak"])
    if C.get("no_trough"):
        Rr = ["برودة علوية طفيفة بلا أخدود"]
        weak = [("لا أخدود علوي مؤثر" if "الأخدود العلوي ضحل" in x else x) for x in weak]
    sup = __import__("bigreport")._supported(C["fac0"])
    struct = 3 if sup and C["ws"] >= 3 else 2 if sup and C["ws"] >= 1.8 else 1 if (sup or Tt or Rr) else 0
    t = f"التفسير: بنية الحالة مع الصورة العامة {R3.LEVEL4[struct]}"
    why = []
    if Tt:
        why.append("من المداريات " + jl(Tt))
    if Rr:
        why.append("من العروض الوسطى " + jl(Rr))
    # the table above lists every factor; the reading names only the strongest on each side
    if Tt or Rr:
        t += "، أقوى ما يسندها " + (Tt or Rr)[0]
    if weak:
        t += "، وأقوى ما يكبحها " + weak[0]
    # what the pieces mean together
    shallow = not W or not any(k in (W.get("trough") or {}) for k in ("cutoff",)) and C["sc"].get("trough", 0) < 0.3
    if shallow and C["ws"] < 1.8:
        t += ("؛ فلا رفع واسع من الأعلى اليوم، والتبريد العلوي الضعيف يكفي فقط لتقوية خلايا يصنعها الرفع "
              "التضاريسي والتسخين النهاري حيث توجد رطوبة، فالحالة محلية لا منظمة")
    elif C["ws"] >= 2.6:
        t += "؛ فالرفع العلوي والدعم المداري يجتمعان، والمطر قابل للانتظام على مساحات أوسع من التضاريس"
    B.append({"p": t + "."})
    # the trough to come, so «no trough today» is not read as «no trough in the case» (Fahad 27 Nov 2026)
    try:
        import troughreach
        w = C["nw"]
        R_ = wave_reach(C["st"], w) if w else []
        first = next((r["d"] for r in C["st"].get("troughreach") or [] if r["d"] > C["day0"].isoformat()
                      and any(troughreach.reaches(v) for v in r["z"].values())), None)
        if R_ and first:
            B.append({"p": f"والأخدود القادم من الشمال الغربي يبدأ أثره على المملكة {ar_date(date.fromisoformat(first))}، "
                           "وتفصيله في القسم ٦."})
    except Exception as e:  # noqa: BLE001
        print("report4: trough ahead failed:", repr(e), flush=True)
    return sec(HEAD[1], "dyn", B)


# ------------------------------------------------------------------ 3. moisture and convection
OUT_DIR = None     # set by daily.py (and the hand republish) to the folder holding ksa_vals.bin


def ec_rh(st, day0):
    """{region: (RH700 %, RH500 %)} region means of the site's ECMWF humidity maps (ksa_vals.bin), or None when the
    file or the day cannot be read (then the report says so and does not guess)"""
    import os
    import numpy as np
    import sa_geo as G
    v = (st.get("ksa") or {}).get("vals")
    if not v or not OUT_DIR:
        return None
    days = (st.get("ksa") or {}).get("days") or []
    if day0.isoformat() not in days:
        return None
    k = days.index(day0.isoformat())
    if k in (v.get("missing") or []):
        return None
    p = os.path.join(OUT_DIR, v["file"])
    if not os.path.exists(p):
        return None
    ny, nx, nk = v["ny"], v["nx"], len(v["order"])
    a = np.fromfile(p, dtype=np.int16)
    if a.size < (k + 1) * ny * nx * nk:
        return None
    a = a[k * ny * nx * nk:(k + 1) * ny * nx * nk].reshape(nk, ny, nx) * v["scale"]
    la = v["lat0"] - v["d"] * np.arange(ny)
    lo = v["lon0"] + v["d"] * np.arange(nx)
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    regs = G.regions()
    idx = G.region_of_points(regs, LA.ravel(), LO.ravel()).reshape(ny, nx)
    i7, i5 = v["order"].index("rh7"), v["order"].index("rh5")
    out = {}
    for j, r in enumerate(regs):
        m = idx == j
        if m.sum() >= 2:
            out[r["name"]] = (float(a[i7][m].mean()), float(a[i5][m].mean()))
    return out or None


def _depth_word(r7, r5):
    return ("رطوبة عميقة" if r7 >= 50 and r5 >= 40 else "رطوبة حتى ٧٠٠ وجفاف فوقها" if r7 >= 50 else
            "رطوبة ضحلة تحت ٧٠٠")


def _pw_today(st, day0):
    pr = st.get("pw_reg") or {}
    row = next((r for r in pr.get("rows") or [] if r["d"] == day0.isoformat()), None)
    if not row:
        return None, pr.get("model")
    names = {k: nm for k, nm, _ in pr.get("names") or []}
    return {names[k]: row[k] for k in names if k in row}, pr.get("model")


def s_moist(C):
    st, day0, rows = C["st"], C["day0"], C["rows"]
    B = []
    pw, model = _pw_today(st, day0)
    src = "الأوروبي" if model == "ecmwf" else "جي إف إس"
    if pw:
        hi = sorted([(n, v) for n, v in pw.items() if v["pct"] >= 110], key=lambda x: -x[1]["pct"])
        lo = sorted([(n, v) for n, v in pw.items() if v["pct"] < 90], key=lambda x: x[1]["pct"])
        t = f"الماء القابل للهطول اليوم (توقع {src}، متوسط كل منطقة): "
        t += ("فوق معدله على " + jl([f"{n} ({ar(v['pct'])}٪، {ar(int(round(v['pw'])))} ملم)" for n, v in hi[:4]])
              if hi else "لا منطقة فوق ١١٠٪ من معدلها")
        if lo:
            t += "، ودون معدله بوضوح على " + jl([f"{n} ({ar(v['pct'])}٪)" for n, v in lo[:4]]) + (
                " وغيرها" if len(lo) > 4 else "")
        box = next((r for r in st.get("pw") or [] if r["d"] == day0.isoformat()), {}).get("southwest")
        sw = [pw[n]["pct"] for n in ("الباحة", "عسير") if n in pw]
        if box and sw and box["pct"] - max(sw) >= 15:
            t += (f". أما صندوق جنوب غرب المملكة كاملًا بسواحله فـ{ar(box['pct'])}٪، فالرطوبة الزائدة على سهول تهامة "
                  f"والبحر، والحواف نفسها قريبة من معدلها ({jl([ar(x) + '٪' for x in sw])}).")
        B.append({"p": t + ("" if t.endswith(".") else ".")})
    # depth of the moist layer: the site's ECMWF RH700/RH500 maps (region means), GFS only when they cannot be read
    want = [r["name"] for r in rows[:4]]
    if "مكة المكرمة" not in want:
        want.append("مكة المكرمة")
    ec = None
    try:
        ec = ec_rh(st, day0)
    except Exception as e:  # noqa: BLE001
        print("report4: ECMWF humidity not read:", repr(e), flush=True)
    sr = st.get("strat") or {}
    vals, src = {}, None
    if ec:
        vals, src = {n: ec[n] for n in want if n in ec}, "الأوروبي، من خرائط الرطوبة في الموقع"
    elif sr.get("day") == day0.isoformat():
        vals = {n: (x["rh7"], x["rh5"]) for n in want for x in [(sr.get("regions") or {}).get(n)] if x}
        src = "جي إف إس، لأن خرائط الرطوبة الأوروبية تعذرت قراءتها الليلة"
    if vals:
        dw = {_depth_word(a7, a5) for a7, a5 in vals.values()}
        one = len(dw) == 1 and len(vals) > 1     # the same depth everywhere: said once
        bits = [f"{n} {ar(int(round(a7)))}٪ عند ٧٠٠ و{ar(int(round(a5)))}٪ عند ٥٠٠"
                + ("" if one else f" ({_depth_word(a7, a5)})") for n, (a7, a5) in vals.items()]
        B.append({"p": f"عمق الطبقة الرطبة (متوسط الرطوبة النسبية لكل منطقة، توقع {src}): " + "، و".join(bits)
                       + (f"؛ فهي {next(iter(dw))} في كلها" if one else "")
                       + ". والجفاف فوق ٥٠٠ يحد من نمو الخلايا رأسيًا ويُسرع تبددها بعد الغروب."})
    else:
        B.append({"p": "عمق الطبقة الرطبة: تعذرت الليلة قراءة الرطوبة عند ٧٠٠ و٥٠٠ هكتوباسكال، فلم يُبنَ عليها حكم."})
    # transport: the river from the Arabian Sea and the Red Sea flow
    rv = next((r for r in (st.get("river") or {}).get("rows") or [] if r["d"] == day0.isoformat()), None)
    rf = next((r for r in (st.get("rsflow") or {}).get("rows") or [] if r["d"] == day0.isoformat()), None)
    tr = []
    if rv and rv.get("text"):
        tr.append(f"{rv['text']} (النقل الرطوبي، توقع الأوروبي)")
    if rf and rf.get("text"):
        tr.append("، و".join(rf["text"][:2]) + f" (تدفق البحر الأحمر، توقع {'جي إف إس' if rf.get('src') == 'gfs' else 'الأوروبي'})")
    if tr:
        B.append({"p": "النقل الرطوبي: " + "؛ و".join(tr) + "."})
    # the low-level event: what it does to the convection
    lw = C["lw"]
    if lw.get("cold_regions") or lw.get("sides"):
        where = list(lw.get("cold_regions") or [])
        if "high" in (lw.get("sides") or []):
            where.append("هضبة الطائف وحافتي الهدا والشفا")
        if "low" in (lw.get("sides") or []):
            where.append("سهول مكة وتهامة")
        rainy = {r["name"] for r in rows if not r.get("vague")}
        if not (rainy & set(lw.get("cold_regions") or []) or lw.get("sides")):
            B.append({"p": f"الحدث قرب الأرض: هواء أبرد وأجف من معدله في الطبقة السفلى فوق {jl(where)}، يحدّ شدة الخلايا "
                           "هناك، ولا تجتمع فيها مكونات المطر اليوم، فلا أثر له على مناطق المطر."})
        else:
            B.append({"p": f"الحدث قرب الأرض: هواء أبرد وأجف من معدله في الطبقة السفلى فوق {jl(where)}، يرفع الكبح ويخفض طاقة "
                       "الحمل، فيحدّ من شدة الخلايا ولا يلغيها: لا عواصف قوية ولا أمطار غزيرة، وقد تنشأ خلايا خفيفة إلى "
                       "متوسطة حيث يصعد هواء البحر الحواف تحت طبقة وسطى رطبة. ففي مكة والطائف والجنوب الغربي أساس المطر "
                       "التضاريس والتسخين السطحي والرطوبة، فإن توافقت نشأت الخلايا، والحدث قرب الأرض عامل ثانوي يحدّ "
                       "شدتها لا وجودها (في ٣٨٢ يومًا مختبرًا بأمطار الأقمار "
                       "الصناعية لم يبلغ المطر ٢٠ ملم حول مكة والطائف في أي يوم بارد كهذا، وهذه الأمطار تُضعف تقدير "
                       "خلايا الجبال الصغيرة)."})
    # the fuel
    fuel = [r for r in rows if not r.get("vague") and r["cape"] >= 150]
    if fuel:
        B.append({"p": "الطاقة: " + "، و".join(f"{r['name']} نحو {ar(int(round(r['cape'], -1)))} جول/كغ" for r in fuel)
                       + " على الحواف (أكثر الطبقات عدم استقرار، توقع جي إف إس)"
                       + ("، وهي طاقة تكفي لخلايا رعدية متفرقة حيث يقع الرفع، وشدتها رهينة القص الذي لا يُقرأ الليلة."
                          if max(r["cape"] for r in fuel) >= 500 else "، وهي طاقة محدودة لا تصنع إلا زخات قصيرة.")})
    B.append({"p": "ما لا يُقرأ الليلة: مثبط الحمل وارتفاع التكاثف ومستوى الحمل الحر والقص الرأسي ومستوى التجمد لا تُستخرج "
                   "قيمها في المنظومة إلا مثبط الحمل فوق البحر في نقاط الخلايا البحرية، فلم يُبنَ عليها حكم."})
    return sec(HEAD[2], "moist", B)


# ------------------------------------------------------------------ 4. geography and timing, the four tests
TIME_OF = {"هواء البحر الرطب يصعد الحافة": "بعد الظهر حتى المغرب", "هواء رطب يصعد الحرة": "بعد الظهر",
           "تبريد علوي فوق هواء رطب": "بعد الظهر", "التقاء الرياح على هضبة الطائف": "بعد الظهر",
           "هواء السحب البارد ينحدر مساءً من الجبال": "المساء",
           "صعود واسع لهواء رطب عميق في الطبقات الوسطى (مطر طبقي)": "على مدار اليوم"}


def _time_of(cause):
    if cause in TIME_OF:
        return TIME_OF[cause]
    if cause.startswith("التقاء رياح") or cause.startswith("رياح ") or cause.startswith("التقاء الرياح"):
        return "بعد الظهر"
    if cause.startswith("تدفعها"):
        return "آخر العصر والمساء"
    return "بعد الظهر"


def tests(r):
    """the four coincidence tests of the charter for one region of the reading: [(state, words)] x 4"""
    p = r["parts"]
    pw_ok, lift, fuel = p.get("الرطوبة", 0), p.get("التقاء الرياح", 0), p.get("الطاقة", 0)
    causes = [c for c in r["why"].values() if c]
    if any("طبقة وسطى رطبة" in c for c in causes):
        pw_ok = max(pw_ok, 0.5)     # a moist 700 hPa layer over the climbing sea air (26 Nov 2026 edge cells)
    if pw_ok >= 1 and lift >= 1 and fuel >= 1:
        sp = ("متحقق", "الرطوبة والرفع والطاقة فوق المكان نفسه")
    elif lift >= 1 and (pw_ok >= 0.5 or fuel >= 0.5):
        miss = [n for n, v in (("الرطوبة", pw_ok), ("الطاقة", fuel)) if v < 1]
        sp = ("جزئي", "الرفع قائم و" + jl(miss) + " دون الكافي")
    else:
        sp = ("غائب", "لا يجتمع الرفع مع الرطوبة والطاقة")
    if r.get("trough") and lift >= 1 and not r.get("cool_weak"):
        tm = ("متحقق", "التبريد العلوي فوق المنطقة وقت ذروة التسخين بعد الظهر")
    elif r.get("trough") and lift >= 1:
        tm = ("جزئي", "التسخين النهاري مع برودة علوية طفيفة لا تكفي لدعم متزامن")
    elif lift >= 1:
        tm = ("جزئي", "التسخين النهاري وحده، بلا دعم علوي متزامن")
    else:
        tm = ("غائب", "لا ذروة نشاط تتزامن مع المكونات")
    s = r.get("steer") or ""
    terrain = any("يصعد" in c for c in causes)
    if not s:
        wd = ("جزئي", "رياح التوجيه غير مقروءة فوق المنطقة")
    elif "ضعيفة" in s:
        wd = ("جزئي", "الخلايا شبه ثابتة، فيتركز مطرها محليًا وتنحدر سيولها مع الأودية")
    elif terrain and "الشرق" in s and "الشمال الشرقي" not in s or terrain and "الجنوب الشرقي" in s:
        wd = ("جزئي", f"تدفع الخلايا {s} من الحافة نحو الهضبة الأجف، فتضعف بعد ساعتين أو ثلاث")
    elif terrain and "الغرب" in s:
        wd = ("متحقق", f"تحمل الخلايا {s} نحو السهول تحت الحافة، فيمتد المطر إليها")
    else:
        wd = ("متحقق", f"تحمل الخلايا {s} على مسار الرطوبة")
    if causes:
        mc = ("متحقق", jl(sorted(set(causes))[:2]))
    elif r.get("vague"):
        mc = ("غائب", "رطوبة وتبريد بلا آلية رفع تحدد مكانًا")
    else:
        mc = ("غائب", "لا آلية رفع")
    return [sp, tm, wd, mc]


PART_W = {"الرطوبة": "الرطوبة", "الصورة الكبرى": "الصورة الكبرى", "التقاء الرياح": "الرفع على التضاريس",
          "التبريد العلوي": "التبريد العلوي", "الطاقة": "طاقة عدم الاستقرار"}


def factors(r, C):
    """(supporting, limiting, suppressing) for one region"""
    p = r["parts"]
    sup = [PART_W[k] for k, v in p.items() if v >= 1 and k != "الصورة الكبرى"
           and not (k == "التبريد العلوي" and r.get("cool_weak"))]
    lim = [PART_W[k] for k, v in p.items() if 0 < v < 1 and k != "الصورة الكبرى"]
    if r.get("cool_weak"):
        lim.append("ضعف التبريد العلوي")
    if r.get("steer") and "الشرق" in r["steer"] and any("يصعد" in c for c in r["why"].values()):
        lim.append("انتقال الخلايا عن الحافة")
    sp = []
    if C["sc"].get("mjo", 0) == 0 and C["weak"]:
        sp.append("الصورة الكبرى على مستوى المملكة (" + C["weak"][0].split("،")[0] + ")")
    if p.get("الرطوبة", 0) == 0 and not any("طبقة وسطى رطبة" in c for c in r["why"].values() if c):
        sp.append("جفاف الهواء")
    elif p.get("الرطوبة", 0) == 0:
        lim.append("جفاف العمود فوق الطبقة الوسطى الرطبة")
    if r["name"] in (C["lw"].get("cold_regions") or []) or (r["name"] == "مكة المكرمة" and C["lw"].get("sides")):
        # Fahad 26 Nov 2026: in Makkah, Taif and the southwest the rain rests on terrain, surface heating and
        # moisture; the low-level event is secondary there, it limits the intensity only
        if r["name"] == "مكة المكرمة" or r["name"] in R3.SOUTH:
            lim.append("الحدث البارد قرب الأرض (عامل ثانوي يحدّ الشدة)")
        else:
            sp.append("الحدث البارد قرب الأرض (يحدّ الشدة ولا يلغي الخلايا)")
    return sup, lim, sp


def s_geo(C):
    st, day0, rows = C["st"], C["day0"], C["rows"]
    B = []
    named = [r for r in rows if not r.get("vague")]
    LVW = {"heavy": "غزيرة", "moderate": "متوسطة", "light": "خفيفة"}
    if named:
        trs = []
        for r in named:
            first = True
            for k in ("heavy", "moderate", "light"):
                for pl_ in r["row"][k]:
                    c = r["why"].get(pl_, "")
                    trs.append([r["name"] if first else "", pl_, LVW[k], _time_of(c), c])
                    first = False
        B.append({"table": {"head": ["المنطقة", "المكان", "الشدة", "التوقيت", "الآلية"], "rows": trs}})
        tr = [[r["name"]] + [a for a, _ in tests(r)] for r in named]
        B.append({"h": "اختبار التوافق"})
        B.append({"table": {"head": ["المنطقة", "المكاني", "الزماني", "الرياح ومسار الخلايا", "الآلية"], "rows": tr}})
        # what every region shares is said once, before the regions (Fahad 27 Nov 2026: «ازل اي تكرار»)
        TN = ("المكاني", "الزماني", "الرياح", "الآلية")
        rd = []
        for r in named:
            sup, lim, sp = factors(r, C)
            ts = tests(r)
            nt = [f"{TN[i]} {a} ({b})" for i, (a, b) in enumerate(ts) if a != "متحقق"]
            rd.append((r, sup, lim, sp, ts, nt))
        common = lambda k: ([x for x in rd[0][k] if all(x in y[k] for y in rd[1:])] if len(rd) > 1 else [])
        c_lim, c_sp, c_nt = common(2), common(3), common(5)
        if c_lim or c_sp or c_nt:
            parts = ([f"الكابح {jl(c_sp)}"] if c_sp else []) + ([f"المحدد {jl(c_lim)}"] if c_lim else []) + c_nt
            B.append({"p": f"المشترك بين {jl([r['name'] for r in named])}: " + "، و".join(parts) + "."})
        groups = {}
        for r, sup, lim, sp, ts, nt in rd:
            lim = [x for x in lim if x not in c_lim]
            sp = [x for x in sp if x not in c_sp]
            nt = [x for x in nt if x not in c_nt]
            t = f"الداعم {jl(sup) if sup else 'لا عامل مكتمل'}"
            t += f"، والمحدد {jl(lim)}" if lim else ""
            t += f"، والكابح {jl(sp)}" if sp else ("" if c_sp else "، ولا كابح محلي")
            full = sum(1 for a, _ in ts if a == "متحقق")
            t += f". تحقق {ar(full)} من ٤ شروط" + (f"، و{'؛ و'.join(nt)}" if nt else "")
            t += "؛ فهي زخات متفرقة محتملة" if r["level"] == "ضعيفة" else f"؛ فالفرصة {r['level']}"
            if r.get("level0"):
                t += f" لا فرصة {r['level0']}، لأن التوافق غير مكتمل"
            if r.get("pw") and r["pw"] < 110 and r["level"] in ("مرجحة", "قوية"):
                t += " في نطاق الحواف وحدها، لا على المنطقة كلها"
            groups.setdefault(t, []).append(r["name"])
        for t, names in groups.items():   # regions read the same way are written once (no repetition)
            B.append({"p": f"{jl(names)}: {t}."})
    vague = [r["name"] for r in rows if r.get("vague")]
    if vague:
        B.append({"p": f"وعلى {jl(vague)} رطوبة وتبريد علوي بلا آلية رفع تحدد مكانًا، فالزخات هناك عابرة متفرقة."})
    if not rows:
        B.append({"p": "لا تجتمع مكونات المطر على أي منطقة اليوم."})
    # Makkah first: why it is out when it is
    if not any(r["name"] == "مكة المكرمة" for r in rows):
        RD, lw = C["RD"], C["lw"]
        t = "منطقة مكة المكرمة: لا فرصة تُذكر اليوم"
        why = []
        m = RD.get("meet")
        if m and lw.get("cut"):
            why.append(f"فالتقاء الرياح بعد الظهر {'شمال الطائف وشرقه' if m[0] != 'edge' else 'على حافتي الهدا والشفا'}"
                       + (f" قرب {m[1]}" if m[1] else "") + " يُضعفه الحدث البارد قرب الأرض فوق الهضبة")
        elif m and m[0] == "east_dry":
            why.append(f"فالرياح تلتقي شرق الطائف قرب {m[1]} والطاقة هناك ضعيفة")
        s = RD.get("steer")
        if s and s["speed"] >= 3:
            why.append(f"والخلايا تتجه نحو {s['to']} بعيدًا عن مكة والجموم")
        B.append({"p": t + ("، " + "، ".join(why) if why else "") + "."})
    # the numerical rain, kept apart
    g = C["ingr"].get(day0.isoformat()) or {}
    if "gfs" in g:
        gr = sorted(((n, v) for n, v in (g.get("gfs_regions") or {}).items() if v >= 0.01), key=lambda x: -x[1])
        t = ("للمقارنة فقط، ولا يدخل في الحكم: مطر جي إف إس العددي يغطي اليوم "
             + R2.cover_pct(g["gfs"]).removeprefix("نحو ") + " من المملكة")
        if gr:
            t += "، أكثره على " + jl([f"{n} ({R2.cover_pct(v).removeprefix('نحو ')})" for n, v in gr[:3]])
        B.append({"note": t + ". وهو ضعيف في تحديد مساحة المطر بحسب اختباراتنا، فمكانه الخريطة."})
    return sec(HEAD[3], "geo", B)


# ------------------------------------------------------------------ 5. sea and terrain cells
def s_cells(C):
    import seacell
    st, day0, RD, lw = C["st"], C["day0"], C["RD"], C["lw"]
    B = []
    try:
        t = seacell.tonight(st.get("seacell"), day0)
        if t:
            B.append({"p": t})
        if st.get("seacell"):
            B.append({"p": seacell.coming(st["seacell"], day0 + timedelta(days=1), day0 + timedelta(days=7))})
    except Exception as e:  # noqa: BLE001
        print("report4: sea cells failed:", repr(e), flush=True)
    # the terrain cells of Makkah, zone by zone (Hada, Shafa, Sail, Rahat, Shamnasir)
    m = RD.get("meet")
    if m:
        site = {"east": "شمال الطائف وشرقه", "east_dry": "شمال الطائف وشرقه", "edge": "على حافتي الهدا والشفا"}[m[0]]
        t = f"خلايا التضاريس حول مكة: تلتقي الرياح بعد الظهر {site}" + (f" قرب {m[1]}" if m[1] else "")
        mv = RD.get("moved")
        if mv and mv[0] != m[0].replace("_dry", ""):
            t += "، بعد أن كان أمس " + ("على الحافة" if mv[0] == "edge" else "شمال الطائف وشرقه")
        if m[0] == "east_dry" and not (RD.get("cape_edge") or 0) >= 50:
            t += "، والطاقة عند الالتقاء ضعيفة"
        if m[0] == "east_dry" and (RD.get("cape_edge") or 0) >= 50:
            t += (f"، وطاقة السطح على الحواف ({ar(int(round(RD.get('cape_edge') or 0, -1)))} جول/كغ) أعلى منها عند الالتقاء "
                  f"({ar(int(round(RD.get('cape_east') or 0, -1)))} جول/كغ)")
        if lw.get("cut"):
            t += "؛ والحدث البارد قرب الأرض فوق الهضبة يحدّ من شدته، فالخلايا إن نشأت على الهدا والشفا خفيفة إلى متوسطة"
        else:
            t += "؛ فهو موضع نشوء الخلايا اليوم، وحرتا رهاط وشمنصير خارج الحكم ما لم يهبط سطح ٥٠٠ هكتوباسكال"
        s = RD.get("steer")
        if s:
            t += (f"، ورياح التوجيه نحو {s['to']} بنحو {ar(round(s['speed']))} م/ث" if s["speed"] >= 3 else
                  "، والرياح الموجهة ضعيفة")
        B.append({"p": t + "."})
    pl = [(r["name"], p_) for r in C["rows"] for p_ in r.get("plains") or []]
    if pl:
        B.append({"p": "السهول: " + "، و".join(f"{p_} ({n_})" for n_, p_ in pl)
                       + "، إذا نزل هواء السحب البارد من الجبال مساءً إلى الهواء الحار الرطب تحتها."})
    else:
        B.append({"p": "السهول تحت الجبال (تهامة وسهول مكة والجموم): لا يُقرأ اليوم انحدار لهواء السحب البارد إليها."})
    return sec(HEAD[4], "cells", B)


# ------------------------------------------------------------------ 6. the coming wave
def _wave_blocks(st, day0):
    """report3.waves without the seasonal outlook (section 7) and the sea-cell nights (section 5)"""
    w = R3.waves(st, None, [], day0)
    try:
        wl = R3.wave_set(st, day0)[0]
        ws_ = wave_sea(st, next((x for x in wl if not x.get("sign")), wl[0] if wl else None))
    except Exception:  # noqa: BLE001
        ws_ = None
    try:
        import troughreach
        nw_ = next((x for x in wl if not x.get("sign")), wl[0] if wl else None)
        rw_ = troughreach.words(st.get("troughreach"), nw_["start"] - timedelta(days=1), nw_["end"]) if nw_ else None
    except Exception as e:  # noqa: BLE001
        print("report4: trough reach failed:", repr(e), flush=True)
        rw_ = None
    out, seen_h = [], False
    bl = w.get("blocks") or []
    has_h = any(b.get("h") == "أقرب موجة قادمة" for b in bl)
    multi = any("table" in b and len(b["table"]["rows"]) > 1 for b in bl)
    for b in bl:
        if has_h and not seen_h:
            if b.get("h") == "أقرب موجة قادمة":
                seen_h = True
            continue
        if "p" in b and (b["p"].startswith("الخلايا البحرية") or b["p"].startswith("لم تكتمل بعد في توقع الأيام القادمة")):
            continue                    # sea-cell nights: section 5; the season: section 7
        if "table" in b and len(b["table"]["rows"]) == 1:
            continue                    # one wave: the paragraph after it says the same
        if "p" in b:
            p_ = b["p"].replace("النظرة الموسمية أعلاه", "النظرة الموسمية (القسم ٧)")
            if multi:               # the table already names the areas of each wave
                p_ = re.sub(r"، والمناطق المتأثرة بها: .*?(?=\. |، والثقة)", "", p_)
            if p_.startswith("تستمر الموجة"):   # the window is in the table: keep only the warm event's days
                p_ = re.sub(r"^تستمر الموجة [^(]*\([^)]*\)، ويرافقها حدث دافئ قرب الأرض", "ويمتد هذا الحدث الدافئ", p_)
            p_ = re.sub(r"، وحدث دافئ قرب الأرض فوق [^.]*?(?=\.|$)", "، وحدث دافئ قرب الأرض", p_)
            b = dict(b, p=p_)
        out.append(b)
        if "p" in b and b["p"].startswith("نمط الموجة"):
            if rw_:
                out.append({"p": rw_})
            west = [r for r in (nw_ or {}).get("regions") or [] if r.startswith("البحر والساحل")]
            if ws_ and west:
                # the nights and numbers are in section 5 and the summary: here only where the core is and goes
                rest = R3.land_rest(nw_)
                inl = [r for r in nw_["regions"] if r in ("تبوك", "المدينة المنورة", "خيبر والعلا", "حائل")]
                out.append({"p": f"وقلب الموجة غربًا الخلايا البحرية الغزيرة {west[0].removeprefix('البحر والساحل ').strip()}"
                                 " (لياليها وأرقامها في القسم ٥)"
                                 + (f"، تخرج مع الرياح الجنوبية الغربية إلى {jl(inl)}" if inl else "")
                                 + (f"؛ ثم أمطار أوسع وأخف من صعود الهواء الرطب على {jl(rest[:4])}" if rest else "") + "."})
    return out


def scenarios(C):
    """three scenarios for the nearest wave (charter, part 4): base, stronger, weaker, and what tips each"""
    w, nb, a = C["nw"], C["nb"], C["an"]
    if not w:
        return []
    pk = ar_date(w["peak"])
    cov = w.get("cover") or 0
    cv = f"نحو {ar(int(round(100 * cov)))}٪" if cov >= 0.01 else "أقل من ١٪"
    regs = jl(w["regions"][:3])
    B = [{"h": "السيناريوهات"}]
    base = f"الأساسي (الأرجح): القراءة أعلاه كما هي ({cv} أوسعها {pk})"
    if nb and nb["blocked"]:
        west = [r for r in w.get("regions") or [] if r.startswith("البحر والساحل")]
        inl = [r for r in w.get("regions") or [] if r in ("تبوك", "المدينة المنورة", "خيبر والعلا", "حائل")]
        base += "، ومحور الأخدود يبقى محجوزًا غرب البحر الأحمر فلا ينفصل منخفض فوقه، ويعمل الأخدود أمام محوره"
        if west:
            base += "، فيبقى القلب الغزير بحريًا ساحليًا غربًا كما سبق، ومكة والجموم على أطرافه"
        else:
            base += "، ونصيب سواحل الحجاز خلايا بحرية ليلية، ومكة والجموم على أطرافها"
    B.append({"p": base + "."})
    strong = "الأقوى (إن تحسنت المكونات): "
    cond = []
    if nb:
        cond.append(f"أن يتقدم طرف الأخدود شرق خط الطول ٣٤° (أقصاه الليلة {ar(int(round(nb['lon_max'])))}°) "
                    "فينفصل منخفض معزول فوق البحر الأحمر")
    if a and a.get("rh") is not None:
        import analogs
        tri, jd, jm, mk, anyr = analogs.chances(a["pw"], 45)
        cond.append(f"أن ترتفع الرطوبة عند ٧٠٠ هكتوباسكال غرب المملكة إلى ٤٥٪ فأكثر (الليلة {ar(a['rh'])}٪)")
        strong += "، و".join(cond) + (f"؛ فترتفع فرصة المطر الغزير قرب جدة إلى نحو {ar(jd)}٪ ومكة {ar(mk)}٪ "
                                       "بحسب الحالات المشابهة، ويتسع الانتشار نحو انتشار الموجة المرجعية")
    elif cond:
        strong += "، و".join(cond) + "؛ فتدخل مكة وجدة دائرة المطر المنظم ويتسع الانتشار"
    else:
        strong += "أن يتعمق الأخدود ويتزامن مع ذروة الرطوبة، فيتسع الانتشار"
    B.append({"p": strong + "."})
    weak = "الأضعف (إن تراجعت المكونات أو لم تتزامن): "
    wc = []
    if nb and nb["ridge"] >= 50:
        wc.append(f"أن يشتد المرتفع فوق إيران والخليج (الليلة {ar(int(round(nb['ridge'])))} م) فيُسحب المد الرطوبي شرقًا "
                  "قبل أن يبلغه الرفع")
    wc.append("أو أن يسبق مرور الأخدود ذروة الرطوبة بيوم")
    rest = R3.land_rest(w)
    if wave_sea(C["st"], w):
        weak += " ".join(wc) + (f"؛ فتبقى الخلايا البحرية دون الغزارة، ويضيق المطر إلى زخات خفيفة متفرقة على "
                                f"{jl(['المدينة المنورة'] + rest[:1])}، ويقل انتشاره عن ٢٪.")
    else:
        weak += " ".join(wc) + f"؛ فيضيق المطر إلى زخات خفيفة متفرقة على {jl(w['regions'][:2])}، ويقل انتشاره عن ٢٪."
    B.append({"p": weak})
    pivot = []
    if a and a.get("rh") is not None:
        pivot.append("الرطوبة عند ٧٠٠ هكتوباسكال غرب المملكة")
    if nb:
        pivot.append("خط طول طرف الأخدود")
        pivot.append("قوة المرتفع الشرقي")
    if pivot:
        B.append({"p": "المتغير الذي يغير الحكم: " + jl(pivot) + "، ويُتابع كل ليلة حتى بداية الحالة."})
    return B


def next_pulse(C):
    """the next pulse of the trough after the nearest wave (troughreach.py): the first day after it with 3 or more zones
    reached, its falls and cold air, and whether the ingredients gather rain with it (Fahad's mid-level Rossby wave
    video, 27 Nov 2026: the low comes back south over the north on 4 Dec, cold aloft)"""
    import troughreach
    w = C["nw"]
    if not w:
        return None
    for r in C["st"].get("troughreach") or []:
        if r["d"] <= w["end"].isoformat():
            continue
        R = sorted([(k, v["dz"], v["t5"]) for k, v in r["z"].items() if troughreach.reaches(v)], key=lambda x: x[1])
        if len(R) < 3:
            continue
        cv = (C["wr"].get(r["d"]) or {}).get("cover") or 0
        d = date.fromisoformat(r["d"])
        nm = {"jouf": "الجوف", "nb": "الحدود الشمالية"}
        t = (f"وبعد الموجة نبضة ثانية للأخدود {ar_date(d)} على {jl([nm.get(k, troughreach.NAME[k]) for k, *_ in R[:4]])}: "
             f"يهبط سطح ٥٠٠ هكتوباسكال حتى {ar(-R[0][1])} م وتبلغ حرارة ٥٠٠ هكتوباسكال {ar(int(round(min(x[2] for x in R))))}°، "
             "فهي أبرد من الموجة الأولى في الأعلى")
        t += ("، لكن الرطوبة لا تجتمع معها في توقع الليلة (انتشار مكونات المطر دون ١٪)، فالأرجح برودة وغيوم وزخات "
              "خفيفة متفرقة في الشمال لا موجة مطرية، وتُتابع كل ليلة" if cv < 0.01 else
              f"، وتجتمع معها مكونات المطر على {R2.cover_pct(cv)} من المملكة")
        return t + "."
    return None


def s_wave(C):
    st, day0 = C["st"], C["day0"]
    B = _wave_blocks(st, day0)
    try:
        np_ = next_pulse(C)
        if np_:
            i = next((j for j, b in enumerate(B) if "p" in b and b["p"].startswith("وقلب الموجة غربًا")), None)
            B.insert(i + 1 if i is not None else len(B), {"p": np_})
    except Exception as e:  # noqa: BLE001
        print("report4: next pulse failed:", repr(e), flush=True)
    B += scenarios(C)
    w = C["nw"]
    if w:
        ds = [w["start"] + timedelta(days=k) for k in range((w["end"] - w["start"]).days + 1)]
        pr = []
        for d in ds:
            g = (C["ingr"].get(d.isoformat()) or {}).get("gfs")
            c = (C["wr"].get(d.isoformat()) or {}).get("cover")
            if g is not None and c is not None:
                pr.append(f"{ar_date(d)} {R2.cover_pct(g).removeprefix('نحو ')} مقابل {R2.cover_pct(c).removeprefix('نحو ')}")
        if pr:
            B.append({"note": "للمقارنة فقط، ولا يدخل في الحكم: انتشار مطر جي إف إس العددي مقابل قراءة المكونات في أيام الموجة: "
                              + "، و".join(pr) + "."})
    return sec(HEAD[5], "waves", B)


# ------------------------------------------------------------------ 7. seasonal outlook
def s_season(C):
    import season
    st, day0 = C["st"], C["day0"]
    B = season.blocks(st, day0) if st.get("wet_season") else []
    B = [b for b in B if b.get("h") != "النظرة الموسمية"]
    if not B:
        B = [{"p": "خارج موسم الأمطار الواسعة، فلا نظرة موسمية."}]
    B.append({"note": "هذه خلفية موسمية تحدد مدى ملاءمة الأسابيع القادمة للأمطار الواسعة، ولا تحدد يوم المطر ولا مكانه، "
                      "فلا يُبنى عليها توقع اليوم."})
    return sec(HEAD[6], "season", B)


# ------------------------------------------------------------------ 8. change from the previous run
def snapshot(C):
    """what the next night compares with (stored in mjo.json as analyst_snap)"""
    import bigreport as BR
    st, day0 = C["st"], C["day0"]
    days = {}
    tf = {r["d"]: r for r in (st.get("taifc_gfs") or st.get("taifc") or {}).get("rows") or []}
    lwd = (st.get("lowwarm") or {}).get("days") or []
    for k in range(8):
        d = (day0 + timedelta(days=k)).isoformat()
        x = {}
        r = C["wr"].get(d)
        if r:
            x["cover"], x["core"] = r.get("cover") or 0, r.get("core") or 0
            x["regions"] = [g["name"] for g in r.get("regions") or []][:4]
        s = next((y for y in st.get("seacell") or [] if y["d"] == d), None)
        if s and s.get("si"):
            import seacell
            x["sea"] = seacell.levels(s)
        if d in tf:
            x["meet"] = tf[d].get("where")
        if d in lwd:
            i = lwd.index(d)
            x["lw"] = [st["lowwarm"]["low"][i], st["lowwarm"]["high"][i]]
        wv = next((y for y in st.get("waves") or [] if y["d"] == d), {})
        if wv.get("trough"):
            x["trough"] = [wv["trough"]["v"], wv["trough"]["lon"], wv["trough"]["area"]]
        if wv.get("ridge"):
            x["ridge"] = wv["ridge"]["v"]
        days[d] = x
    w = C["nw"]
    wave = None
    if w:
        pk = w["peak"]
        wv = next((y for y in st.get("waves") or [] if y["d"] == pk.isoformat()), {})
        kel, ros, mf = BR._tw(st, pk, "kel"), BR._tw(st, pk, "ros"), BR._mf(st, pk)
        wave = {"start": w["start"].isoformat(), "end": w["end"].isoformat(), "peak": pk.isoformat(),
                "top": round(w["top"], 2), "cover": round(w.get("cover") or 0, 3), "regions": w["regions"][:4],
                "trough": (-wv["trough"]["v"] / 10) if wv.get("trough") else None,
                "kel": kel[0] if kel else None, "ros": ros[0] if ros else None, "mf": mf[0] if mf else None,
                "nb": C["nb"], "an": {k: C["an"][k] for k in ("pw", "rh")} if C["an"] else None}
    return {"v": 1, "day": day0.isoformat(), "cycle": st.get("cycle"), "ws": round(C["ws"], 2),
            "regions": {r["name"]: r["level"] for r in C["rows"]}, "days": days, "wave": wave, "method": "ingr"}


def changes(prev, now):
    """[{text, short}] of the changes that move the forecast decision, most important first"""
    if not prev:
        return []
    out = []
    pw, nw = prev.get("wave"), now.get("wave")
    if pw and nw:
        ps, pe, pp = (date.fromisoformat(pw[k]) for k in ("start", "end", "peak"))
        ns, ne, np_ = (date.fromisoformat(nw[k]) for k in ("start", "end", "peak"))
        if (ps, pe) != (ns, ne) or pp != np_:
            t = (f"نافذة الموجة صارت {R2.ar_span(ns, ne).removeprefix('من ')} بعد أن كانت {R2.ar_span(ps, pe).removeprefix('من ')}"
                 + (f"، وانتقلت ذروتها من {ar_date(pp)} إلى {ar_date(np_)}" if pp != np_ else ""))
            if prev.get("method") != "ingr":
                t += "؛ وجزء من هذا التغير منهجي لا جوي، إذ صارت أيام الموجة تُحدد من نبضات مكونات الهطول لا من نافذة العوامل الكبرى"
            out.append({"w": 5, "text": t, "short": f"الموجة صارت {R2.ar_span(ns, ne).removeprefix('من ')}"})
        dc = (nw.get("cover") or 0) - (pw.get("cover") or 0)
        if abs(dc) >= 0.02:
            out.append({"w": 4, "text": f"انتشار الموجة المقدّر {'اتسع' if dc > 0 else 'ضاق'} من نحو {ar(int(round(100 * pw['cover'])))}٪ "
                                        f"إلى نحو {ar(int(round(100 * nw['cover'])))}٪ من المملكة",
                        "short": f"انتشار الموجة {'اتسع' if dc > 0 else 'ضاق'} إلى نحو {ar(int(round(100 * nw['cover'])))}٪"})
        if abs((nw.get("top") or 0) - (pw.get("top") or 0)) >= 0.4:
            out.append({"w": 3, "text": f"قوة الموجة {'ارتفعت' if nw['top'] > pw['top'] else 'تراجعت'} من {R2.n1(pw['top'])} "
                                        f"إلى {R2.n1(nw['top'])} من ٥", "short": "قوة الموجة " + ('ارتفعت' if nw['top'] > pw['top'] else 'تراجعت')})
        if pw.get("trough") and nw.get("trough") and abs(nw["trough"] - pw["trough"]) >= 1:
            out.append({"w": 4, "text": f"الأخدود في ذروة الموجة {'تعمق' if nw['trough'] > pw['trough'] else 'ضعف'} من "
                                        f"{num(pw['trough'], 1)} إلى {num(nw['trough'], 1)} ديكامتر",
                        "short": "الأخدود " + ('تعمق' if nw['trough'] > pw['trough'] else 'ضعف')})
        for k, nm, sgn in (("kel", "موجات كلفن", 1), ("ros", "عائلة روسبي", 1)):
            a, b = pw.get(k), nw.get(k)
            if a is not None and b is not None and (a > 0) != (b > 0) and abs(a - b) >= 0.8:
                out.append({"w": 2, "text": f"{nm} في ذروة الموجة صارت {'داعمة' if b < 0 else 'كابحة'} ({n1(b)}) بعد أن كانت "
                                            f"{'داعمة' if a < 0 else 'كابحة'} ({n1(a)})", "short": f"{nm} صارت {'داعمة' if b < 0 else 'كابحة'}"})
        pn, nn = pw.get("nb"), nw.get("nb")
        if pn and nn:
            if abs(nn["lon_max"] - pn["lon_max"]) >= 2:
                out.append({"w": 4, "text": f"طرف الأخدود {'تقدم شرقًا' if nn['lon_max'] > pn['lon_max'] else 'تراجع غربًا'} من خط الطول "
                                            f"{ar(int(round(pn['lon_max'])))}° إلى {ar(int(round(nn['lon_max'])))}°",
                            "short": "طرف الأخدود " + ('تقدم شرقًا' if nn['lon_max'] > pn['lon_max'] else 'تراجع غربًا')})
            if abs(nn["ridge"] - pn["ridge"]) >= 15:
                out.append({"w": 3, "text": f"المرتفع الشرقي {'اشتد' if nn['ridge'] > pn['ridge'] else 'ضعف'} من {ar(int(round(pn['ridge'])))} "
                                            f"إلى {ar(int(round(nn['ridge'])))} م", "short": "المرتفع الشرقي " + ('اشتد' if nn['ridge'] > pn['ridge'] else 'ضعف')})
        pa, na = pw.get("an"), nw.get("an")
        if pa and na and (abs(na["rh"] - pa["rh"]) >= 3 or abs(na["pw"] - pa["pw"]) >= 5):
            out.append({"w": 5, "text": f"رطوبة غرب المملكة لليلة ٣٠ نوفمبر وصباح ١ ديسمبر: الماء الهطول {ar(na['pw'])}٪ (كان {ar(pa['pw'])}٪) "
                                        f"والرطوبة عند ٧٠٠ {ar(na['rh'])}٪ (كانت {ar(pa['rh'])}٪)",
                        "short": f"الرطوبة الوسطى غربًا {ar(na['rh'])}٪ (كانت {ar(pa['rh'])}٪)"})
    # the same valid days in both runs
    import seacell
    for d, x in sorted(now.get("days", {}).items()):
        y = (prev.get("days") or {}).get(d)
        if not y:
            continue
        dd = date.fromisoformat(d)
        if "sea" in x and "sea" in y:
            up = [seacell.NAME[k] for k, v in x["sea"].items() if v >= 2 and y["sea"].get(k, 0) < 2]
            dn = [seacell.NAME[k] for k, v in y["sea"].items() if v >= 2 and x["sea"].get(k, 0) < 2]
            if up or dn:
                t = f"الخلايا البحرية ليلة {ar_date(dd)}: " + "، و".join(
                    ([f"صارت مرجحة على {jl(up)}"] if up else []) + ([f"تراجعت على {jl(dn)}"] if dn else []))
                out.append({"w": 2, "text": t, "short": t})
        if x.get("meet") and y.get("meet") and x["meet"] != y["meet"] and dd <= date.fromisoformat(now["day"]) + timedelta(days=1):
            W_ = {"edge": "على حافتي الهدا والشفا", "east": "شمال الطائف وشرقه"}
            out.append({"w": 2, "text": f"التقاء الرياح حول الطائف {ar_date(dd)} انتقل إلى {W_.get(x['meet'], x['meet'])} بعد أن كان "
                                        f"{W_.get(y['meet'], y['meet'])}", "short": "التقاء الرياح حول الطائف انتقل"})
        if x.get("lw") and y.get("lw"):
            for i, nm in ((0, "سهول مكة وتهامة"), (1, "هضبة الطائف")):
                a, b = y["lw"][i], x["lw"][i]
                if a is not None and b is not None and (a <= -1) != (b <= -1):
                    out.append({"w": 3, "text": f"الحدث البارد قرب الأرض فوق {nm} {ar_date(dd)} " + ("ظهر" if b <= -1 else "زال"),
                                "short": f"الحدث البارد فوق {nm} " + ("ظهر" if b <= -1 else "زال")})
        if abs((x.get("cover") or 0) - (y.get("cover") or 0)) >= 0.02 and not pw:
            out.append({"w": 2, "text": f"انتشار مكونات الهطول {ar_date(dd)} صار نحو {ar(int(round(100 * x['cover'])))}٪",
                        "short": "تغير الانتشار"})
    out.sort(key=lambda c: -c["w"])
    return out


def s_change(C):
    ch = C.get("changes")
    prev = C.get("prev")
    B = []
    if not prev:
        B.append({"p": "لا تشغيل سابق محفوظ للمقارنة الليلة، وتبدأ المقارنة من الليلة القادمة."})
    elif not ch:
        B.append({"p": f"لا تغير مؤثر في القرار التنبؤي عن {_cyc_words(prev.get('cycle') or '')}؛ المكونات مستقرة."})
    else:
        B.append({"p": f"مقارنة بـ{_cyc_words(prev.get('cycle') or '')}، تغير ما يؤثر في القرار:"})
        for c in ch[:6]:
            B.append({"p": c["text"] + "."})
    return sec(HEAD[7], "change", B)


# ------------------------------------------------------------------ 9. confidence and limits
INV = [  # (figure family, the map's name on the site, model, level, how the report reads it)
    # read: a status key whose values the report reads; "ec_rh": the ECMWF humidity file; a str starting "~": said as is
    ("olr", "الحمل الحراري المداري ومركز التذبذب", "gfs", "قمة الغلاف (الإشعاع الطويل)", None),
    ("mjoz", "مكوّن التذبذب المعزول", "gfs", "٨٠٠ هكتوباسكال", "mjof"),
    ("mjop", "الأمطار المرتبطة بالتذبذب", "gfs", "السطح", None),
    ("kel", "موجات كلفن", "gfs", "٢٠٠ هكتوباسكال", "tw"),
    ("ros", "عائلة روسبي", "gfs", "٢٠٠ هكتوباسكال", "tw"),
    ("twk", "مسار موجات كلفن", "gfs", "٢٠٠ هكتوباسكال", "tw"),
    ("twr", "مسار عائلة روسبي", "gfs", "٢٠٠ هكتوباسكال", "tw"),
    ("belt", "اللوحة الاستوائية الشاملة", "gfs", "عدة مستويات", None),
    ("wave", "موجات روسبي في الطبقة الوسطى", "gfs", "٥٠٠ هكتوباسكال", "waves"),
    ("lw", "الحدث الدافئ والبارد قرب الأرض", "gfs", "قرب الأرض و٨٠٠ هكتوباسكال", "lowwarm"),
    ("lwd", "تغير الحدث خلال ٢٤ ساعة", "gfs", "قرب الأرض و٨٠٠ هكتوباسكال", None),
    ("lwe", "طاقة الحمل في الحدث", "gfs", "قرب الأرض", None),
    ("kw7", "الرياح", "wind", "٧٠٠ هكتوباسكال", "~رياح التوجيه من نقاط الحواف والسهول"),
    ("kw5", "الرياح", "wind", "٥٠٠ هكتوباسكال", "~رياح التوجيه من نقاط الحواف والسهول"),
    ("tconv", "تصادم الرياح السطحية", "taifc", "١٠ أمتار", "~قُرئ من نسخة جي إف إس للتصادم"),
    ("tcape", "طاقة عدم الاستقرار", "taifc", "أكثر الطبقات عدم استقرار", "~الطاقة من جي إف إس في نقاط الحواف"),
    ("pw", "رطوبة الجزيرة العربية", "pw", "عمود الهواء", "pw_reg"),
    ("krh7", "رطوبة ٧٠٠", "ksa", "٧٠٠ هكتوباسكال", "ec_rh"),
    ("krh5", "رطوبة ٥٠٠", "ksa", "٥٠٠ هكتوباسكال", "ec_rh"),
    ("kt5", "حرارة ٥٠٠", "ksa", "٥٠٠ هكتوباسكال", "~حرارة ٥٠٠ من جي إف إس"),
    ("riv", "النهر الجوي من بحر العرب", "ecmwf", "عمود الهواء (النقل الرطوبي)", "river"),
    ("rst", "العواصف الرعدية على مسار النهر", "gfs", "عمود الهواء", None),
    ("rsf", "تدفق البحر الأحمر نحو السواحل", "rsflow", "قرب الأرض", "rsflow"),
    ("rsc", "توغّل طاقة الحمل من البحر الأحمر", "rsflow", "قرب الأرض", None),
    ("svr", "احتمال العاصفة الشديدة (صفحة النموذج)", "gfs", "عدة مستويات", None),
]
MODEL_W = {"gfs": "جي إف إس", "ecmwf": "الأوروبي", "mixed": "الأوروبي مع جي إف إس"}


def _model_of(st, how):
    if how in MODEL_W:
        return MODEL_W[how]
    if how == "wind":
        return MODEL_W.get((st.get("ksa") or {}).get("wind_model"), "جي إف إس")
    if how == "pw":
        return "الأوروبي" if st.get("pw_ec") else "جي إف إس"
    if how == "rsflow":
        r = ((st.get("rsflow") or {}).get("rows") or [{}])[0]
        return MODEL_W.get(r.get("src"), "جي إف إس")
    return MODEL_W.get((st.get(how) or {}).get("model"), "جي إف إس")


def inventory(st, day0):
    fc = st.get("fig_count") or {}
    tot = {}
    for k, v in fc.items():
        b = k.split("_")[0]
        tot[b] = tot.get(b, 0) + (v or 0)
    days = st.get("days") or []
    span = (R2.ar_span(date.fromisoformat(days[0]), date.fromisoformat(days[-1])).removeprefix("من ") if days else "")
    rows, missing = [], []
    ec_ok = None
    for fam, name, how, lvl, key in INV:
        n = tot.get(fam, 0)
        if n == 0:
            state = "لم تُرسم الليلة"
            missing.append(name)
        elif key == "ec_rh":
            if ec_ok is None:
                try:
                    ec_ok = bool(ec_rh(st, day0))
                except Exception:  # noqa: BLE001
                    ec_ok = False
            state = "قُرئت قيمها" if ec_ok else "تعذرت قراءة قيمها"
            if not ec_ok:
                missing.append(name)
        elif key and key.startswith("~"):
            state = "مرسومة؛ " + key[1:]
        elif key and st.get(key):
            state = "قُرئت قيمها"
        elif key:
            state = "تعذرت قراءة قيمها"
            missing.append(name)
        else:
            state = "مرسومة، لم تُقرأ قيمها"
        rows.append([name, _model_of(st, how), lvl, (f"{ar(n)} خرائط" if 3 <= n <= 10 else f"{ar(n)} خريطة") if n else "—", state])
    return rows, missing, span


def conf_rows(C):
    import bigreport as BR
    rows, why = [], []
    named = [r for r in C["rows"] if not r.get("vague")]
    if named:
        place = "عالية" if all(r["meets"] for r in named) else "متوسطة"
        inten = "متوسطة" if max(r["cape"] for r in named) >= 500 and any(r.get("trough") and not r.get("cool_weak") for r in named) else "منخفضة"
        spread = "عالية" if C["spread"] < 0.03 and C["ws"] < 1.8 else "متوسطة"
        rows.append(["اليوم", "عالية", place, inten, spread])
        why.append("اليوم: التوقيت يحكمه التسخين النهاري والمكان تحدده التضاريس، أما الشدة فتتوقف على خلايا منفردة")
    s0 = C["sea0"]
    if s0 and s0.get("si") and _sea_places(s0):
        rows.append(["الخلايا البحرية الليلة", "متوسطة", "متوسطة", "منخفضة", "منخفضة"])
        why.append("الخلايا البحرية: نافذتها من التاسعة مساءً إلى الثالثة عصر الغد ومكانها شريط ساحلي، واختبارها على ٥٦ ليلة فقط، ودرجة الغزارة على ٩ ليالٍ")
    w = C["nw"]
    if w:
        lead = (w["start"] - C["day0"]).days
        t = BR.confidence(lead)
        pl = _down(t)
        a = C["an"]
        inten = "منخفضة" if (a and a.get("rh") is not None and a["rh"] < 45) or lead > 5 else pl
        g = (C["ingr"].get(w["peak"].isoformat()) or {}).get("gfs")
        cov = w.get("cover") or 0
        agree = g is not None and cov > 0 and 0.5 <= (g / cov if cov else 0) <= 2
        sp = pl if agree else _down(pl)
        rows.append(["الموجة القادمة", t, pl, inten, sp])
        why.append(f"الموجة: بدايتها بعد {R3._days_word(lead)} فالتوقيت أوثق من المكان"
                   + ("، والشدة رهينة الرطوبة الوسطى دون حدها" if a and a.get("rh") is not None and a["rh"] < 45 else "")
                   + ("" if agree else "، والانتشار مختلف بين قراءة المكونات ومطر جي إف إس العددي"))
    return rows, why


def s_conf(C):
    st, day0 = C["st"], C["day0"]
    B = []
    rows, why = conf_rows(C)
    if rows:
        B.append({"table": {"head": ["البند", "التوقيت", "المكان", "الشدة", "الانتشار"], "rows": rows}})
        B.append({"p": "؛ و".join(why) + "."})
    inv, missing, span = inventory(st, day0)
    B.append({"h": "حصر الخرائط"})
    B.append({"p": f"خرائط الموقع الليلة من {_cyc_words(st.get('cycle') or '')}، وصلاحيتها {span}. والقراءة من حقولها العددية لا من "
                   "صورها، ومطر النماذج معروض على الخريطة ولا يُبنى عليه الحكم."})
    B.append({"table": {"head": ["الخريطة", "النموذج", "المستوى", "العدد", "حالة القراءة"], "rows": inv}})
    if missing:
        B.append({"p": f"تعذرت الليلة: {jl(missing)}، ولم يُعوَّض ما فيها بالتخمين."})
    nr = [r[0] for r in inv if r[4] == "مرسومة، لم تُقرأ قيمها"]
    if nr:
        B.append({"p": f"ومرسومة في الموقع دون أن تدخل قيمها في الحكم بعد: {jl(list(dict.fromkeys(nr)))}، فلا يُبنى عليها حكم الليلة."})
    B.append({"h": "حدود التوقع"})
    B.append({"p": "قراءة المكونات اختُبرت على أيام ١٠ إلى ١٨ نوفمبر فقط (٩ أيام) بأمطار الأقمار الصناعية بالأشعة تحت الحمراء، "
                   "وهي تقلل من عواصف الجبال الصغيرة؛ ومؤشر الخلايا البحرية اختُبر على ليالي ١ أكتوبر إلى ٢٥ نوفمبر (٥٦ ليلة في ٨ أشرطة ساحلية من الوجه إلى القنفذة)؛ "
                   "والحالات المشابهة عشرون حالة من سبعة وستين موسمًا. والمطر الطبقي الواسع لا يُقرأ إلا بصعوده الواسع، "
                   "والعواصف المنفردة لا يُضبط موضعها بدقة أقل من عشرات الكيلومترات."})
    return sec(HEAD[8], "conf", B)


# ------------------------------------------------------------------ build
def build(rep, st):
    C = read(st, rep)
    prev = st.get("prev_snap") or None
    if prev and prev.get("cycle") == st.get("cycle"):
        prev = prev.get("base")      # the same run built again: compare with the run before it, not with itself
    C["prev"] = prev
    now = snapshot(C)
    if prev:
        now["base"] = {k: v for k, v in prev.items() if k != "base"}
    try:
        C["changes"] = changes(C["prev"], now)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("report4: changes failed:", repr(e), flush=True)
        C["changes"] = []
    st["analyst_snap"] = now
    out = []
    for f in (s_exec, s_dyn, s_moist, s_geo, s_cells, s_wave, s_season, s_change, s_conf):
        try:
            out.append(f(C))
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("report4:", f.__name__, "failed:", repr(e), flush=True)
            k = len(out)
            out.append(sec(HEAD[k], "error", [{"p": "تعذّر بناء هذا القسم الليلة، وسيُعاد بناؤه في التحديث القادم."}]))
    for k, x in enumerate(out):
        x["heading"] = f"{D9[k]}. {x['heading']}"
    new = dict(rep)
    new.update({"v": 2, "brand": R2.BRAND, "credit": R2.CREDIT, "date": ar_date(C["day0"]), "sections": out})
    return new
