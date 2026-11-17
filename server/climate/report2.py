"""The report in Fahad's layout (17 Nov 2026): nine numbered sections, short headings, lists and small tables,
and a Makkah section built on the daily study of the mountain edges and the harrat (plains.py).

build(rep, st) takes the report as daily.py / refresh_report.py assemble it (the rain section of rainreport and the
big-picture sections of bigreport) and the page state st (mjo.json), and returns the same report with `v: 2`,
`brand`, `credit`, `date` and sections in the new order. Each section keeps `lines` (plain text, for anything that
reads the old shape) and adds `blocks`, which the page draws:
  {"h": text} a sub-heading · {"p": text} a paragraph · {"ul": [text]} a list · {"note": text} a small note
  {"table": {"head": [..], "rows": [[..]]}}
Anything that cannot be read from the data is left out rather than guessed; a section that fails falls back to the
old section's lines.
"""
import re
from datetime import date, datetime, timedelta

from sa_geo import ar, num, ar_date, ar_span

BRAND = "نموذج التنبؤ العددي عالي الدقة"
CREDIT = "Developed by Fahad AlEissa"
ORD = ["الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة", "السادسة"]
BOX_NAME = {"west": "الحجاز وغرب المملكة", "southwest": "جنوب غرب المملكة", "central": "وسط المملكة",
            "east": "شرق المملكة", "north": "شمال المملكة"}
# the edges and plains of the Makkah section, in the order of the table (short names for a phone-wide table)
MAKKAH_ZONES = [("hada", "الهدا والشفا"), ("sarawat", "سروات مكة"), ("rahat_s", "حرة رهط"),
                ("kishb", "حرة كشب"), ("rahat_n", "رهط الشمالية")]
YES, NO = "✓", "✗"


def jl(names):
    names = [x for x in names if x]
    return " و".join(names) if len(names) <= 2 else "، و".join(names)


def n1(x):
    return num(x, 1) if abs(x) < 10 else ar(int(round(x)))


def grade(x):
    from bigreport import grade as g
    return g(x)


def split_list(s):
    """'أ (ب، ج)، ود، وهـ' -> ['أ (ب، ج)', 'د', 'هـ']: commas inside brackets do not split"""
    out, depth, cur = [], 0, ""
    k = 0
    while k < len(s):
        c = s[k]
        depth += c == "("
        depth -= c == ")"
        if depth == 0 and s.startswith("، ", k):
            out.append(cur)
            cur = ""
            k += 2
            continue
        cur += c
        k += 1
    out.append(cur)
    res = []
    for x in out:
        x = x.strip().rstrip(".")
        x = re.sub(r"^و(?=\S)", "", x) if not x.startswith("وسط") else x
        # 'أ وب' at the end of a list of two
        res.append(x)
    if len(res) == 1 and " و" in res[0] and "(" not in res[0]:
        res = [res[0].split(" و", 1)[0], res[0].split(" و", 1)[1]]
    return [x for x in res if x]


def sec(heading, kind, blocks):
    lines = []
    for b in blocks:
        if "h" in b:
            lines.append(b["h"] + ":")
        elif "p" in b or "note" in b:
            lines.append(b.get("p") or b.get("note"))
        elif "ul" in b:
            lines += [f"• {x}" for x in b["ul"]]
        elif "table" in b:
            t = b["table"]
            lines.append(" | ".join(t["head"]))
            lines += [" | ".join(r) for r in t["rows"]]
    return {"heading": heading, "kind": kind, "blocks": blocks, "lines": lines}


def find(secs, kind=None, start=None):
    for s in secs:
        if kind and s.get("kind") == kind:
            return s
        if start and s.get("heading", "").startswith(start):
            return s
    return None


# ------------------------------------------------------------------ the rain windows of the rain section
def rain_regions(rs):
    """[{name, amount, wins: [{span, type, heavy, moderate, light, max, at, extra}]}] from the rain section"""
    out = []
    if not rs:
        return out
    for l in rs.get("lines", []):
        m = re.match(r"منطقة (.+?) \((.+?)\): (.*)$", l)
        if not m:
            continue
        name, amount, body = m.groups()
        body = body.split(". وعلى ")[0].split(". وتتهيأ ")[0]
        wins = []
        for part in body.split("؛ ثم "):
            w = {}
            mm = re.match(r"(.+?)، أمطار (.+?)(?:، (.*))?$", part.strip().rstrip("."))
            if not mm:
                continue
            w["span"], rest = mm.group(1), (mm.group(2) + ("، " + mm.group(3) if mm.group(3) else ""))
            tail = ""
            if "؛ وأعلاها " in rest:
                rest, tail = rest.split("؛ وأعلاها ", 1)
            bits = rest.split("، ")
            w["type"] = bits[0]
            for b in bits[1:]:
                b = b.removeprefix("و")
                for key, word in (("heavy", "غزيرة على "), ("moderate", "متوسطة على "), ("light", "خفيفة على ")):
                    if b.startswith(word):
                        w[key] = b[len(word):]
            if tail:
                mx = re.match(r"(\S+) ملم (.+?)(?:، (.*))?$", tail)
                if mx:
                    w["max"], w["at"], w["extra"] = mx.group(1), mx.group(2), mx.group(3)
            wins.append(w)
        out.append({"name": name, "amount": amount, "wins": wins})
    return out


def towns_of(w):
    return " ".join(w.get(k, "") for k in ("heavy", "moderate", "light"))


# ------------------------------------------------------------------ the edges of the Makkah section
def edge_cells(e, model):
    """the column of one edge in the ingredients table: (cells, verdict, confidence, reasons it fails)"""
    import plains as P
    f = e["flags"]
    up = e.get("upper") or {}
    uf = up.get("flags", {})
    mark = lambda ok: f" {YES}" if ok else f" {NO}"
    cells = [
        f"{ar(e['pct'])}٪" + mark(f["moist"]),
        f"{ar(round(e['cape'], -1))}" + mark(e["cape"] >= P.EDGE_CAPE),
        f"{ar(e['rh700'])}٪" + mark(f["midmoist"]),
        f"{ar(round(e['td']))}°" + mark(e["td"] >= P.EDGE_TD),
        f"{n1(e['u_foot'])}" + mark(f["upslope"]),
        f"{n1(e['v_low'])}" + mark(f["south"]),
        ("—" if up.get("fall") is None else f"{ar(up['fall'])} م" + mark(uf.get("fall"))) if up else "—",
        (f"{ar(up['rh500'])}٪" + mark(uf.get("rh500"))) if up else "—",
        (f"{ar(up['w200'])} م/ث، {n1(up['div200'])}" + mark(uf.get("jet"))) if up else "—",
        (f"{n1(up['t500'])}°" + mark(uf.get("cold"))) if up else "—",
        f"{n1(e['steer'])} م/ث",
        f"{n1(e['rain_gfs'])} ملم" + mark(f["gfs_rain"]),
        "—" if model is None else f"{n1(model)} ملم",
    ]
    ok, score, ff = P.edge_named(e, model)
    why = []
    if not f["moist"]:
        why.append(f"الماء القابل للهطول {ar(e['pct'])}٪ دون ١١٥٪")
    if e["cape"] < P.EDGE_CAPE:
        why.append(f"طاقة عدم الاستقرار {ar(round(e['cape'], -1))} جول/كغ دون {ar(P.EDGE_CAPE)}")
    if not (f["upslope"] or f["south"]):
        why.append("لا نسيم بحر يصعد الحافة ولا هواء جنوبي رطب")
    if not ((e["rh700"] >= P.EDGE_RH and e["td"] >= P.EDGE_TD) or e["rain_gfs"] >= 1):
        why.append("الهواء جاف عند ٧٠٠ هكتوباسكال أو على الحافة")
    if not why and not ok:
        why.append(f"اكتمل {ar(score)} من المكونات فقط")
    return cells, ok, P.confidence(score) if ok else None, why, ff


ROWS = ["الماء القابل للهطول من معدله", "طاقة عدم الاستقرار (جول/كغ)", "الرطوبة عند ٧٠٠", "نقطة الندى على الحافة",
        "نسيم البحر عند السفح (م/ث)", "الهواء الجنوبي (م/ث)", "تغير سطح ٥٠٠ خلال يوم", "الرطوبة عند ٥٠٠",
        "رياح ٢٠٠ والتباعد", "حرارة ٥٠٠", "رياح القيادة", "مطر جي إف إس بعد الظهر", "مطر نموذجنا"]


def makkah_section(st, rs, regs):
    import plains as P
    pl = st.get("plains") or {}
    eds = {e["key"]: e for e in pl.get("edges") or []}
    prs = {r["key"]: r for r in pl.get("rows") or []}
    B = []
    B.append({"p": "نطاق المتابعة الخاص: مكة المكرمة والجموم وجدة والطائف، وحواف الجبال المطلة عليها، والحرات."})
    B.append({"p": "تُدرس هذه المنطقة كل ليلة حافةً حافة: هل تجتمع على الحافة مكونات الحمل الحراري بعد الظهر، "
                   "وهل يدعمها الجو العلوي، وهل ينزل هواء السحب البارد مساءً إلى سهل مكة."})
    mk = next((r for r in regs if r["name"] == "مكة المكرمة"), None)

    def model_words(keys, label):
        if not mk:
            return f"لا تُظهر مخرجات نموذجنا أمطارًا تُذكر على {label}."
        hits = [w for w in mk["wins"] if any(k in towns_of(w) or k in w.get("at", "") for k in keys)]
        if not hits:
            return f"لا تُظهر مخرجات نموذجنا أمطارًا تُذكر على {label}."
        return "يُظهر نموذجنا: " + "؛ ".join(f"{w['span']}، أمطار {w['type']}" for w in hits) + "."

    # -------- the edges study first: the table, then a verdict per edge
    zones = [(k, nm) for k, nm in MAKKAH_ZONES if k in eds]
    named = {}
    if zones:
        cols = {}
        for k, nm in zones:
            cols[k] = edge_cells(eds[k], eds[k].get("model_rain"))
            if cols[k][1]:
                named[k] = cols[k]
        B.append({"h": "دراسة حواف الجبال والحرات اليوم"})
        rows = [[ROWS[i]] + [cols[k][0][i] for k, _ in zones] for i in range(len(ROWS))]
        rows.append(["الحكم"] + [("مرجح، ثقة " + cols[k][2]) if cols[k][1] else "غير مرجح" for k, _ in zones])
        B.append({"table": {"head": ["المكوّن"] + [nm for _, nm in zones], "rows": rows}})
        B.append({"note": f"{YES} المكوّن متوفر، {NO} غير متوفر. القيم من جي إف إس بين ١٢ ظهرًا و٦ مساءً بتوقيت مكة؛ "
                          "والتباعد عند ٢٠٠ بوحدة ١٠⁻⁵ في الثانية، وتغير سطح ٥٠٠ مقارنة باليوم السابق."})
        ul = []
        for k, nm in zones:
            cells, ok, conf, why, ff = cols[k]
            e = eds[k]
            if ok:
                t = f"{nm}: خلايا رعدية بعد الظهر مرجحة، والثقة {conf}"
                ups = []
                u = e.get("upper") or {}
                uf = u.get("flags", {})
                if P.upper_ok(e):
                    if uf.get("fall"):
                        ups.append(f"هبوط سطح ٥٠٠ نحو {ar(-u['fall'])} مترًا")
                    if uf.get("rh500"):
                        ups.append(f"رطوبة ٥٠٠ عند {ar(u['rh500'])}٪")
                    if uf.get("jet"):
                        ups.append(f"تباعد علوي مع رياح ٢٠٠ بسرعة {ar(u['w200'])} م/ث")
                    if uf.get("cold"):
                        ups.append(f"برودة ٥٠٠ عند {n1(u['t500'])}°")
                    t += f"، ويدعمها من الأعلى {jl(ups)}"
                mr = e.get("model_rain")
                if mr is not None:
                    t += "، ونموذجنا يُظهر مطرًا عليها" if mr >= 2 else "، ولا يُظهرها نموذجنا"
                ul.append(t + ".")
            else:
                ul.append(f"{nm}: غير مرجح اليوم، لأن {jl(why)}.")
        B.append({"ul": ul})
    # -------- Makkah and Al-Jumum: the plain under Al-Hada
    B.append({"h": "مكة المكرمة والجموم"})
    B.append({"p": model_words(["مكة", "الجموم", "بحرة", "الشرائع", "الجعرانة", "عرفة"], "مكة والجموم")})
    r = prs.get("makkah")
    h = eds.get("hada")
    if r:
        ok, score, f = P.named(r, r.get("model_mtn"))
        ing = [f"الماء القابل للهطول {ar(r['pct'])}٪ من معدله" + (f" {YES}" if f["moist"] else f" {NO}"),
               f"نقطة الندى على السهل {ar(round(r['td']))}°" + (f" {YES}" if f["humid"] else f" {NO}"),
               f"طاقة عدم الاستقرار على السهل نحو {ar(round(r['cape_plain'], -2))} جول/كغ" + (f" {YES}" if f["unstable"] else f" {NO}"),
               "خلايا على الحافة فوقه بعد الظهر" + (f" {YES}" if f["mountain"] else f" {NO}"),
               f"رياح القيادة {n1(r['steer'])} م/ث" + (f" {YES}" if f["steer"] else f" {NO}"),
               "الرياح على السهل تهب نحو الجبال" + (f" {YES}" if f["inflow"] else f" {NO}")]
        B.append({"p": "مكونات المطر المسائي على السهل (نزول هواء السحب البارد من الحافة):"})
        B.append({"ul": ing})
        if ok:
            B.append({"p": f"الحكم: خلايا جديدة واردة بين المغرب والعشاء على الشرائع والجعرانة وشرق مكة، وقد تصل إلى "
                           f"الجموم ووادي فاطمة، مع جريان محتمل في الأودية؛ والثقة {P.confidence(score)}."})
        elif h and h.get("plain") and named.get("hada") and h["plain"]["cape"] >= P.OUT_CAPE and h["steer"] < P.OUT_STEER:
            B.append({"p": "الحكم: إن نشأت الخلايا على حافة الهدا والشفا فقد ينحدر هواؤها البارد نحو الشرائع وشرق مكة "
                           "فيطلق خلايا جديدة بين المغرب والعشاء؛ والثقة منخفضة."})
        else:
            B.append({"p": "الحكم: لا تتهيأ عوامل المطر المسائي على سهل مكة اليوم."})
    # -------- Jeddah and the coastal plain
    B.append({"h": "جدة والسهل الساحلي"})
    B.append({"p": model_words(["جدة", "رابغ", "خليص", "الكامل", "بحرة"], "جدة والسهل الساحلي")})
    # -------- Taif and the western heights
    B.append({"h": "الطائف والمرتفعات الغربية"})
    B.append({"p": model_words(["الطائف", "الهدا", "الشفا", "ميسان", "أضم", "الليث"], "الطائف والمرتفعات")})
    # -------- the verdict for the region
    B.append({"h": "التقييم العام لمنطقة مكة"})
    if named:
        names = [nm for k, nm in zones if k in named]
        t = f"الحمل الحراري مرجح بعد الظهر على {jl(names)}"
        if r and (P.named(r, r.get("model_mtn"))[0] or (h and h.get("plain") and "hada" in named
                                                       and h["plain"]["cape"] >= P.OUT_CAPE and h["steer"] < P.OUT_STEER)):
            t += "، ومنها قد ينزل المطر بين المغرب والعشاء إلى الشرائع وشرق مكة"
        B.append({"p": t + "، دون إشارة واسعة داخل المدن." if not mk else t + "."})
    else:
        B.append({"p": "لا تجتمع مكونات الحمل الحراري على حواف مكة ولا حراتها اليوم."})
    return B


# ------------------------------------------------------------------ the whole report
def build(rep, st):
    secs = rep.get("sections") or []
    day0 = date.fromisoformat(rep.get("day") or st["days"][0])
    rs = find(secs, kind="rain")
    regs = rain_regions(rs)
    out = []
    for f in (s1, s2, s3, s4, s5, s6, s7, s8, s9):
        try:
            x = f(st, secs, rs, regs, day0)
            if x:
                out.append(x)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("report2:", f.__name__, "failed:", repr(e), flush=True)
    new = dict(rep)
    new.update({"v": 2, "brand": BRAND, "credit": CREDIT, "date": ar_date(day0), "sections": out})
    return new


def s1(st, secs, rs, regs, day0):
    import pattern as P
    B = [{"h": "المشهد الجوي اليوم"}]
    pt = st.get("pattern") or {}
    kind = "thermal"
    if pt.get("day") == day0.isoformat():
        kinds = {v["kind"] for k, v in pt["boxes"].items() if k in ("west", "southwest")}
        kind = "upper" if "upper" in kinds else "mixed" if "mixed" in kinds else "thermal"
    word = {"thermal": "حمل حراري محلي", "mixed": "حمل حراري يعززه تبريد علوي", "upper": "اضطراب علوي يبرد الجو"}[kind]
    edges = named_edges(st)
    t = f"تسود المملكة حالة {word}"
    if regs:
        t += f"، تتركز فرص الأمطار فيها على {jl(['منطقة ' + r['name'] for r in regs[:3]])}"
    if edges:
        t += f"، مع تهيؤ الحمل الحراري بعد الظهر على حواف {jl(list(dict.fromkeys(e['region'] for e in edges)))}"
    B.append({"p": t + "."})
    sm = find(secs, kind="sum")
    if sm:
        cur = next((l for l in sm["lines"] if "موجة" in l and ("قائمة" in l or "لا موجة" in l)), None)
        if cur:
            B.append({"p": cur})
    B.append({"h": "أبرز توقعات اليوم"})
    ul = []
    for r in regs:
        w = max(r["wins"], key=lambda w: float(str(w.get("max", "0")).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789."))
                                              or 0), default=None)
        if not w:
            continue
        t = f"{r['name']}: أمطار {w['type']}"
        if r["amount"].startswith("غزيرة"):
            t += f"، قد تكون غزيرة محليًا {w.get('at', '')}".rstrip()
        else:
            t += f" {r['amount']}"
        ul.append(t + ".")
    by_reg = {}
    for e in edges:
        by_reg.setdefault(e["region"], []).append(e)
    for reg, es in by_reg.items():
        if any(r["name"] == reg for r in regs):
            continue
        import plains as P
        ul.append(f"{reg}: الحمل الحراري مرجح بعد الظهر على {jl([P.short(e['name']) for e in es])}، "
                  "دون إشارة واضحة من نموذجنا.")
    if not ul:
        ul.append("لا أمطار تُذكر على المملكة في مخرجات نموذجنا.")
    B.append({"ul": ul})
    ww = st.get("wave_watch") or {}
    if ww.get("waves"):
        B.append({"h": "الموجات القادمة"})
        rows = [[ar_span(date.fromisoformat(w["start"]), date.fromisoformat(w["end"])).removeprefix("من "),
                 f"{n1(w['score'])} من ٥", grade(w["score"])] for w in ww["waves"]]
        B.append({"table": {"head": ["الفترة", "قوة الموجة", "التقييم"], "rows": rows}})
        best = max(ww["waves"], key=lambda w: w["score"])
        a, b = date.fromisoformat(best["start"]), date.fromisoformat(best["end"])
        B.append({"p": f"الموجة الممتدة {ar_span(a, b)} هي الأهم في المتابعة الحالية، مع ذروة متوقعة "
                       f"{ar_date(date.fromisoformat(best['peak']))}."})
    return sec("١. الخلاصة التنفيذية", "sum", B)


def named_edges(st):
    import plains as P
    out = []
    for e in (st.get("plains") or {}).get("edges") or []:
        if P.edge_named(e, e.get("model_rain"))[0]:
            out.append(e)
    return out


def s2(st, secs, rs, regs, day0):
    B = [{"p": f"الفترة: من منتصف ليل {ar_date(day0).split()[0]} إلى منتصف ليل "
               f"{ar_date(day0 + timedelta(days=1)).split()[0]}، بتوقيت مكة المكرمة."}]
    if rs and rs.get("lines"):
        first = rs["lines"][0]
        if not first.startswith("منطقة "):
            B.append({"p": first.split(". الصورة")[0]})
    for r in regs:
        B.append({"h": f"منطقة {r['name']}"})
        for i, w in enumerate(r["wins"]):
            lab = f"الفترة {ORD[i]}: " if len(r["wins"]) > 1 else ""
            B.append({"p": f"{lab}{w['span']}، أمطار {w['type']}:"})
            ul = []
            for key, word in (("heavy", "غزيرة"), ("moderate", "متوسطة"), ("light", "خفيفة")):
                if w.get(key):
                    ul.append(f"{word}: {w[key]}.")
            if ul:
                B.append({"ul": ul})
            if w.get("max"):
                B.append({"p": f"أعلى كمية متوقعة: {w['max']} ملم {w['at']}" + (f"، {w['extra']}" if w.get("extra") else "") + "."})
    if not regs:
        B.append({"p": "لا يُظهر نموذجنا أمطارًا تُذكر على مناطق المملكة اليوم."})
    return sec("٢. توقعات الأمطار اليوم", "rain", B)


def s3(st, secs, rs, regs, day0):
    return sec("٣. منطقة مكة المكرمة وما حولها", "makkah", makkah_section(st, rs, regs))


def s4(st, secs, rs, regs, day0):
    import plains as P
    pl = st.get("plains") or {}
    B = []
    by = {}
    for e in pl.get("edges") or []:
        if e["region"] == "مكة المكرمة":
            continue
        ok, sc, _ = P.edge_named(e, e.get("model_rain"))
        if ok:
            mr = e.get("model_rain")
            sig = ("، ونموذجنا يُظهر مطرًا عليها" if mr is not None and mr >= 2 else
                   "، دون إشارة مطرية واضحة من نموذجنا" if mr is not None else "")
            by.setdefault(e["region"], []).append(
                f"تتهيأ فرص الحمل الحراري بعد الظهر على {e['name']}: الماء القابل للهطول {ar(e['pct'])}٪ من معدله، "
                f"وطاقة عدم الاستقرار نحو {ar(round(e['cape'], -2))} جول/كغ؛ والثقة {P.confidence(sc)}{sig}.")
    for r in pl.get("rows") or []:
        if r["region"] == "مكة المكرمة" and r["key"] in ("makkah",):
            continue
        ok, sc, _ = P.named(r, r.get("model_mtn"))
        if ok:
            mp = r.get("model_plain")
            sig = ("، ونموذجنا يُظهره على السهل" if mp is not None and mp >= 5 else
                   "، لكن دون إشارة مطرية واضحة من نموذجنا على السهل" if mp is not None else "")
            by.setdefault(r["region"], []).append(
                f"تتهيأ ظروف الأمطار المسائية على {r['name']}: الماء القابل للهطول {ar(r['pct'])}٪ من معدله، ونقطة الندى "
                f"{ar(round(r['td']))}°، وطاقة عدم الاستقرار نحو {ar(round(r['cape_plain'], -2))} جول/كغ؛ "
                f"والثقة {P.confidence(sc)}{sig}.")
    rain_names = {r["name"] for r in regs}
    for reg, ls in by.items():
        if reg == "مكة المكرمة":
            B.append({"h": "سهول جنوب منطقة مكة"})
        else:
            B.append({"h": f"منطقة {reg}"})
        if reg in rain_names:
            B.append({"p": "أمطارها في القسم الثاني أعلاه، وإلى جانبها:"})
        for l in ls:
            B.append({"p": l})
    if rs:
        dry = next((l for l in rs.get("lines", []) if l.startswith("ولا أمطار تُذكر على")), None)
        if dry:
            B.append({"h": "مناطق أخرى"})
            B.append({"p": dry.removeprefix("و").replace("ولا أمطار", "لا أمطار")})
        unc = next((l for l in rs.get("lines", []) if l.startswith("ولم يغطِّ")), None)
        if unc:
            B.append({"note": unc.removeprefix("و")})
    return sec("٤. بقية المناطق المرشحة", "others", B) if B else None


def s5(st, secs, rs, regs, day0):
    import pattern as P
    B = []
    pt = st.get("pattern") or {}
    if pt.get("day") == day0.isoformat():
        bx = pt["boxes"]
        kinds = {bx[k]["kind"] for k in ("west", "southwest") if k in bx}
        kd = "upper" if "upper" in kinds else "mixed" if "mixed" in kinds else "thermal"
        B.append({"h": "نمط الحالة"})
        B.append({"p": f"النمط السائد {P.WORDS[kd][0]}، {P.WORDS[kd][1].removeprefix('ف')}."})
        ul = []
        for k in ("west", "southwest"):
            if k in bx:
                a = bx[k]["anom"]
                dev = ("قريبة من المعدل" if abs(a) < 0.3 else f"{'أبرد' if a < 0 else 'أعلى'} من المعدل بـ{num(abs(a), 1)}°")
                ul.append(f"{bx[k]['name']}: {n1(bx[k]['t'])}°، {dev}.")
        B.append({"p": "حرارة طبقة ٥٠٠ هكتوباسكال عصر اليوم:"})
        B.append({"ul": ul})
    row = next((r for r in st.get("pw", []) if r["d"] == day0.isoformat()), None)
    if row:
        ks = sorted([q for q in BOX_NAME if q in row], key=lambda q: -row[q]["pct"])
        B.append({"h": "الرطوبة"})
        B.append({"p": "الماء القابل للهطول مقارنة بالمعدل:"})
        B.append({"table": {"head": ["النطاق", "الكمية", "النسبة"],
                            "rows": [[BOX_NAME[q], f"{n1(row[q]['pw'])} ملم", f"{ar(row[q]['pct'])}٪"] for q in ks]}})
        p0 = row[ks[0]]["pct"]
        B.append({"p": "بلغت الرطوبة حد المد الرطوبي (١٥٠٪ فأكثر)." if p0 >= 150 else
                       "الرطوبة أعلى من المعدل، لكنها دون حد المد الرطوبي (١٥٠٪ فأكثر)." if p0 >= 110 else
                       "الرطوبة قريبة من المعدل أو دونه."})
    dg = (st.get("diag") or {}).get("lines") or []
    wl = next((l for l in dg if l.startswith("الرياح فوق الحجاز")), None)
    if wl:
        today = wl.split("؛ وعصر")[0]
        rows = []
        for lev in ("٨٥٠", "٧٠٠", "٥٠٠"):
            m = re.search(rf"عند {lev} ([^،؛.]+)", today)
            if m:
                v = m.group(1).strip()
                sp = re.search(r"(\S+) م/ث$", v)
                rows.append([f"{lev} هكتوباسكال", v[:sp.start()].strip() if sp else v, f"{sp.group(1)} م/ث" if sp else "—"])
        if rows:
            B.append({"h": "الرياح وحركة الخلايا"})
            B.append({"p": "فوق الحجاز عصر اليوم:"})
            B.append({"table": {"head": ["المستوى", "اتجاه الرياح", "السرعة"], "rows": rows}})
    mv = next((l for l in dg if l.startswith("حركة الخلايا")), None)
    if mv:
        B.append({"p": "حركة الخلايا المتوقعة " + mv.split(": ", 1)[1]})
    ws = next((l for l in dg if l.startswith("ومع ضعف رياح القيادة")), None)
    if ws:
        B.append({"p": ws.removeprefix("و")})
    up = [l for l in dg if l.startswith("الاضطراب العلوي") or l.startswith("وتقترب")]
    if up:
        B.append({"h": "الاضطرابات العلوية"})
        for l in up:
            B.append({"p": l.split("): ", 1)[1] if l.startswith("الاضطراب") else l.removeprefix("و")})
    dgs = find(secs, kind="diag")
    if dgs:
        col = next((l for l in dgs["lines"] if l.startswith("مناطق التصادم") or l.startswith("مناطق تصادم")), None)
        if col:
            B.append({"p": col.split(": ", 1)[1] if col.startswith("مناطق التصادم") else col})
            if col.startswith("مناطق تصادم"):
                B.append({"ul": [l.lstrip("• ").rstrip(".") + "." for l in dgs["lines"] if l.startswith("• ")]})
    return sec("٥. القراءة الجوية", "diag", B)


def _wave_items(secs):
    ws = find(secs, start="الموجات القادمة")
    return ws["lines"] if ws else []


def s6(st, secs, rs, regs, day0):
    lines = _wave_items(secs)
    try:
        i0 = next(i for i, l in enumerate(lines) if l.startswith("الموجات المرتقبة"))
    except StopIteration:
        return None
    B = []
    k = 0
    for l in lines[i0 + 1:]:
        if not l.startswith("• من "):
            break
        m = re.match(r"• (من .+?): موجة (\S+) \((.+?) من ٥\)، (.+?)، ذروتها (.+?)\. (.*)$", l)
        if not m:
            B.append({"p": l.lstrip("• ")})
            continue
        span, gr, sc, kind, peak, rest = m.groups()
        B.append({"h": f"الموجة {ORD[k]}: {span.removeprefix('من ')}"})
        k += 1
        B.append({"p": f"القوة: {gr}، {sc} من ٥"})
        regions = re.search(r"المناطق المرشحة: (.+?)\.?$", rest)
        impact = ("أمطار محدودة ومتفرقة، أغلبها على المرتفعات." if gr == "ضعيفة" else
                  "فرص أمطار متفاوتة، لم تتضح بعد مساحتها وكمياتها." if gr == "متوسطة" else
                  "أمطار واسعة محتملة على المناطق المرشحة.")
        ul = [f"الذروة: {peak}.", f"النوع: موجة {kind}."]
        if regions:
            ul.append(f"المناطق المرشحة: {regions.group(1)}.")
        ul.append(f"الأثر المتوقع: {impact}")
        B.append({"ul": ul})
        sup = re.search(r"تسندها: (.+?)\. (?:وتعاكسها|المناطق)", rest)
        opp = re.search(r"وتعاكسها: (.+?)\. (?:المناطق|$)", rest)
        if sup:
            B.append({"p": "العوامل الداعمة:"})
            B.append({"ul": [x + "." for x in split_list(sup.group(1))]})
        if opp:
            B.append({"p": "العوامل المعاكسة:"})
            B.append({"ul": [x + "." for x in split_list(opp.group(1))]})
        drv = re.search(r"درجة عواملها \((.+?)\)", rest)
        if drv:
            B.append({"p": f"تبلغ درجة العوامل {drv.group(1)} من ٥، مقابل درجة مطرية متوقعة تبلغ {sc} من ٥."})
        if "لا يُظهر لها توقع المطر انتشارًا" in rest:
            B.append({"p": "التقييم: " + ("موجة ضعيفة، يُتوقع أن تقتصر آثارها على أمطار محدودة ومتفرقة، ولا تزال التفاصيل "
                                         "المطرية غير واضحة." if gr == "ضعيفة" else
                                         "تُظهر العوامل بيئة أفضل من الإشارة المطرية المتاحة حتى الآن، فتُتابع "
                                         "التوقعات يوميًا.")})
    tail = next((l for l in lines if l.startswith("وأقوى الموجات") or l.startswith("وأقربها")), None)
    if tail:
        B.append({"note": tail.removeprefix("و")})
    return sec("٦. الموجات القادمة", "waves", B) if B else None


def s7(st, secs, rs, regs, day0):
    lines = _wave_items(secs)
    try:
        i0 = lines.index("مسار العوامل:")
    except ValueError:
        return None
    ul = []
    for l in lines[i0 + 1:]:
        if not l.startswith("• "):
            break
        ul.append(l[2:])
    last = (date.fromisoformat(st["days"][-1]) if st.get("days") else day0 + timedelta(days=14))
    B = [{"ul": ul}, {"note": "تظل هذه المؤشرات أدوات لتشخيص البيئة الجوية، ولا تمثل بمفردها ضمانًا لهطول الأمطار."}]
    fac = find(secs, start="قراءة العوامل")
    if fac:
        B = [{"h": "قراءة العوامل اليوم"}, {"ul": [re.sub(r"^\S+\. ", "", l) for l in fac["lines"]]},
             {"h": "المسار المتوقع"}] + B
    return sec(f"٧. تطور المؤشرات المدارية حتى {ar_date(last, weekday=False)}", "drivers", B)


def s8(st, secs, rs, regs, day0):
    lines = _wave_items(secs)
    try:
        i0 = lines.index("تفصيل أقرب موجة:")
    except ValueError:
        return None
    ww = st.get("wave_watch") or {}
    head = "٨. تحليل الموجة الأقرب"
    if ww.get("start"):
        head += f": {ar_span(date.fromisoformat(ww['start']), date.fromisoformat(ww['end'])).removeprefix('من ')}"
    B = []
    sub = None
    for l in lines[i0 + 1:]:
        if l.startswith("المصادر والمنهج"):
            break
        if l.startswith("• ") and l.endswith(":"):
            t_ = l[2:-1].split("، وبين القوسين")[0]
            B.append({"h": {"عواملها وتواريخها": "تطور الأخاديد والعوامل"}.get(t_, t_)})
            if "وبين القوسين" in l:
                B.append({"note": "وبين القوسين قيمها اليوم."})
            sub = []
            B.append({"ul": sub})
            continue
        if l.startswith("• "):
            m = re.match(r"• (.+?): (.*)$", l)
            if not m:
                B.append({"p": l[2:]})
                continue
            title, body = m.groups()
            title = {"الموعد والنوع": "الموعد والنوع", "عواملها وتواريخها": "تطور الأخاديد والعوامل",
                     "سيرها يومًا بيوم": "سيرها يومًا بيوم", "الأثر المتوقع": "التقييم النهائي"}.get(title, title)
            B.append({"h": title})
            if body:
                B.append({"p": body})
            sub = []
            B.append({"ul": sub})
        elif l.startswith("  - ") and sub is not None:
            sub.append(l[4:])
        else:
            B.append({"p": l})
    B = [b for b in B if not ("ul" in b and not b["ul"])]
    return sec(head, "nearest", B)


def s9(st, secs, rs, regs, day0):
    res = "٣ كم"
    grids = "ست شبكات عددية"
    if rs:
        src = next((l for l in rs.get("lines", []) if l.startswith("المصدر:")), "")
        m = re.search(r"\((.+?) تغطي المملكة\)", src)
        if m:
            grids = m.group(1).replace("٦ شبكات بدقة ٣ كم", "ست شبكات عددية بدقة مكانية تبلغ ٣ كم")
    B = [{"p": f"يعتمد {BRAND} على {grids}، تغطي المملكة."},
         {"h": "تصنيف كميات الأمطار"},
         {"table": {"head": ["الفئة", "كمية الأمطار"],
                    "rows": [["غزيرة", "٢٠ ملم فأكثر، أو ١٠ ملم خلال ساعة"], ["متوسطة", "من ٥ إلى أقل من ٢٠ ملم"],
                             ["خفيفة", "أقل من ٥ ملم"]]}},
         {"p": "تُقدّر فرص البَرَد والخلايا العملاقة من خلال صدى الرادار المتوقع، وطاقة عدم الاستقرار، وقص الرياح، ومستوى التجمد."},
         {"p": "تُدرس حواف الجبال والحرات كل ليلة من جي إف إس: الرطوبة ونسبتها إلى المعدل، وطاقة عدم الاستقرار، ونسيم "
               "البحر والهواء الجنوبي، والرطوبة عند ٧٠٠ و٥٠٠، وتغير سطح ٥٠٠، ورياح ٢٠٠ وتباعدها، وحرارة ٥٠٠، ورياح القيادة، "
               "ونزول هواء السحب البارد إلى السهول."},
         {"h": "ملاحظات منهجية"},
         {"ul": ["قوة العوامل الجوية لا تعادل بالضرورة قوة الموجة المطرية.", "الثقة في التوقع مستقلة عن درجة الموجة.",
                 "تهيؤ الظروف الجوية لا يعني بالضرورة ظهور أمطار في مخرجات النموذج.",
                 "تزداد موثوقية التفاصيل المكانية كلما اقترب موعد الحالة ودخلت نطاق التنبؤات عالية الدقة.",
                 "تُراجع التوقعات يوميًا وفق آخر مخرجات الشبكات العددية."]},
         {"note": "المصدر: نموذج Fahad AlEissa وحده. جميع الأوقات بتوقيت مكة المكرمة."},
         {"note": "إعداد وتطوير: Fahad AlEissa"}]
    return sec("٩. منهجية النموذج", "method", B)


def to_markdown(rep):
    """a plain preview of the new layout"""
    out = [f"# {rep.get('brand', '')}", rep.get("credit", ""), "", f"**{rep.get('date', '')}**", ""]
    for s in rep["sections"]:
        out += ["---", f"## {s['heading']}", ""]
        for b in s["blocks"]:
            if "h" in b:
                out += [f"### {b['h']}", ""]
            elif "p" in b:
                out += [b["p"], ""]
            elif "note" in b:
                out += [f"_{b['note']}_", ""]
            elif "ul" in b:
                out += [f"- {x}" for x in b["ul"]] + [""]
            elif "table" in b:
                t = b["table"]
                out += ["| " + " | ".join(t["head"]) + " |", "|" + "---|" * len(t["head"])]
                out += ["| " + " | ".join(r) + " |" for r in t["rows"]] + [""]
    return "\n".join(out)
