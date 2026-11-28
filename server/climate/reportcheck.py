"""The self-check run on the night's report before it is published (Fahad 27 Nov 2026: «انت تحلل السعودية كاملة بحرا
وساحل ويابسة واي نشاط فيها يذكر.. ولا أريد اي أخطاء أخرى مره ثانية»). A report that fails is not published: the site
keeps the last good report and the failure is written to the status (status["report_check"]) and the job log.

    check(report, st, img=None) -> [error, ...]   ([] = publish)

What it checks:
  1. the central charter's 10 sections (Fahad 27 Nov 2026, replacing the 9 of 26 Nov), in order, none empty;
  2. Arabic only (no Latin letter in any text) and no broken text (None, nan, braces, doubled commas or spaces);
  3. no repetition: no clause of 45+ characters in two blocks, no two identical paragraphs;
  4. one story: the nearest wave's period in the summary = in the waves section, and the wave map is of that period;
  5. nothing left out: every coast stretch with any sea-cell reading (passing showers or more) on the coming nights,
     and every zone of the Kingdom-wide sweep with activity, is named in the report; every wave area of the table is
     named in the summary or the waves section text;
  6. the reading covers the whole Kingdom: the sea-cell stretches run without a gap from Haql to Jazan and the Gulf
     coast is read; the trough/activity zones include every administrative region;
  7. the independent scientific auditor of the central charter (part 13), its twelve checks: audit(report, st).
"""
import re
from datetime import date, timedelta

ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
NSEC = 10
SEC = {"sum": 0, "dyn": 1, "moist": 2, "vert": 3, "geo": 4, "cells": 5, "waves": 6, "season": 7, "change": 8, "conf": 9}


def _ar(n):
    return "".join(ARABIC_DIGITS[int(c)] for c in str(n))


def _int(t):
    return float(t.translate(str.maketrans(ARABIC_DIGITS + "٫", "0123456789.")))
REGIONS = {   # administrative region -> the sweep zones that cover it (troughreach.ZONES keys)
    "الرياض": ("riyadh", "kharj", "majmaah", "dawasir"), "مكة المكرمة": ("jeddah_makkah", "taif", "qunf"),
    "المدينة المنورة": ("madinah", "khaybar"), "القصيم": ("qassim",), "الشرقية": ("eastern", "ahsa", "gulf", "hafr"),
    "عسير": ("asir", "bisha"), "تبوك": ("tabuk", "duba", "c_tabuk"), "حائل": ("hail",), "الحدود الشمالية": ("nb",),
    "جازان": ("jazan",), "نجران": ("najran", "sharurah"), "الباحة": ("asir",), "الجوف": ("jouf",)}


def _span(t, day0):
    """«الأحد ٢٩ نوفمبر إلى الثلاثاء ١ ديسمبر» or «السبت ١٢ ديسمبر» -> (first day, last day); (None, None) if unread"""
    ds = []
    for dd, mm in re.findall(r"([٠-٩]+) (" + "|".join(MONTHS) + r")", t):
        m = MONTHS.index(mm) + 1
        y = day0.year + (1 if m < day0.month - 6 else -1 if m > day0.month + 6 else 0)
        try:
            ds.append(date(y, m, int(_int(dd))))
        except ValueError:
            pass
    return (ds[0], ds[-1]) if ds else (None, None)


def _texts(report):
    """[(section index, block index, text)] of every text in the report"""
    out = []
    for i, s in enumerate(report.get("sections") or []):
        out.append((i, -1, s.get("heading") or ""))
        for j, b in enumerate(s.get("blocks") or []):
            for k in ("p", "h", "note"):
                if isinstance(b.get(k), str):
                    out.append((i, j, b[k]))
            if "table" in b:
                t = b["table"]
                out.append((i, j, " | ".join(map(str, t.get("head") or []))))
                for r in t.get("rows") or []:
                    out.append((i, j, " | ".join(map(str, r))))
            if "alt" in b:
                out.append((i, j, b["alt"]))
    return out


def check(report, st, img=None):
    err = []
    secs = report.get("sections") or []
    # 1. the 10 sections
    if len(secs) != NSEC:
        err.append(f"sections: {len(secs)} instead of {NSEC}")
    for i, s in enumerate(secs):
        if not (s.get("heading") or "").startswith(_ar(i + 1) + "."):
            err.append(f"section {i + 1}: heading out of order: {s.get('heading')!r}")
        if not s.get("blocks"):
            err.append(f"section {i + 1}: empty")
        if any("تعذّر بناء هذا القسم" in (b.get("p") or "") for b in s.get("blocks") or []):
            err.append(f"section {i + 1}: failed to build")
    T = _texts(report)
    alltext = "\n".join(t for *_, t in T)
    # 2. Arabic only, no broken text
    for i, j, t in T:
        lat = re.findall(r"[A-Za-z]+", t)
        if lat:
            err.append(f"section {i + 1} block {j}: Latin letters {lat[:3]}")
        for bad in ("None", "nan", "{", "}", "،،", "، ،", "  ", "..", " ،", " .", "()"):
            if bad in t and not (bad == "  " and "|" in t):
                err.append(f"section {i + 1} block {j}: broken text {bad!r}")
    # 3. repetition
    seen, paras = {}, {}
    for i, j, t in T:
        if " | " in t or j < 0:
            continue
        if len(t) >= 60:
            if t in paras and paras[t] != (i, j):
                err.append(f"repeated paragraph in sections {paras[t][0] + 1} and {i + 1}: {t[:60]}")
            paras.setdefault(t, (i, j))
        for c in re.split(r"[؛.:]\s*|\(|\)", t):
            c = c.strip(" ،")
            if len(c) < 45:
                continue
            if c in seen and seen[c] != (i, j):
                err.append(f"repeated clause (sections {seen[c][0] + 1} and {i + 1}): {c[:70]}")
            seen.setdefault(c, (i, j))
    # 4. one story: the nearest wave's period, the map
    try:
        summ = " ".join(b.get("p", "") for b in secs[0]["blocks"])
        wsec = secs[SEC["waves"]]["blocks"]
        m = re.search(r"أقرب موجة: ([^،]+)،", summ)
        tab = next((b["table"] for b in wsec if "table" in b and b["table"]["head"][0] == "الفترة"), None)
        # the nearest RAIN wave: the table's first row may be a weaker trough signal («أقرب إشارة»), so the wave's own
        # paragraph («أقرب موجة: …» or «أقرب موجة مطرية: …») wins over the first row (28 Nov 2026 report was blocked)
        para = next((b["p"] for b in wsec if re.match(r"أقرب موجة( مطرية)?: ", b.get("p", ""))), "")
        mp = re.match(r"أقرب موجة(?: مطرية)?: ([^،]+)،", para)
        per = mp.group(1) if mp else (tab["rows"][0][0] if tab else None)
        if tab and per and per.strip() not in [str(r[0]).strip() for r in tab["rows"]]:
            err.append(f"nearest wave {per!r} is not a row of the waves table")
        if m and per and m.group(1).strip() != per.strip():
            err.append(f"nearest wave: summary says {m.group(1)!r}, waves section {per!r}")
        c = st.get("ref_cmp")
        if m and c and per and c.get("head", "").split(": ", 1)[-1] != per.strip():
            err.append(f"wave map is of {c.get('head')!r}, the wave is {per!r}")
        if img is not None and c and not img:
            err.append("wave map not drawn")
        # every wave area of the table named in prose (summary or waves section)
        if tab:
            prose = summ + " ".join(b.get("p", "") for b in wsec)
            for a in re.split(r"، و?|، ", tab["rows"][0][4]):
                a = a.strip()
                if a and a not in prose and a.replace("البحر والساحل ", "") not in prose:
                    err.append(f"wave area in the table only: {a}")
    except Exception as e:  # noqa: BLE001
        err.append(f"wave consistency not checked: {e!r}")
    # 4b. the current wave is never dropped (Fahad 28 Nov 2026: «كيف تتحدث عن موجة في ١٢ ديسمبر كموجة قادمة وموجتنا
    # من ٢٩ الى ٢ لم تبدأ بعد»): every day of the next 5 that gathers the rain-making ingredients (the pulse rule of
    # report3) lies inside a period of the waves table, and the summary's nearest wave is the earliest of them
    try:
        import report3 as R3
        day0_ = date.fromisoformat(report.get("day") or date.today().isoformat())
        rows = {r["d"]: r for r in st.get("wave_rain") or [] if r.get("kind") == "ingr"}
        tab = next((b["table"] for b in secs[SEC["waves"]]["blocks"] if "table" in b and b["table"]["head"][0] == "الفترة"), None)
        spans = [_span(str(r[0]), day0_) for r in (tab or {}).get("rows") or []]
        for k in range(0, 6):
            d = day0_ + timedelta(days=k)
            r = rows.get(d.isoformat())
            if r and ((r.get("core") or 0) >= R3.PULSE_CORE or (r.get("cover") or 0) >= R3.PULSE_COVER):
                if not any(a and a <= d <= b for a, b in spans):
                    err.append(f"current wave dropped: {d} gathers the ingredients (core {r.get('core')}, cover "
                               f"{r.get('cover')}) but is in no wave of section 7")
                    break
        m = re.search(r"أقرب موجة: ([^،]+)،", " ".join(b.get("p", "") for b in secs[0]["blocks"]))
        if m and spans and spans[0][0] and _span(m.group(1), day0_) != spans[0]:
            err.append(f"summary's nearest wave {m.group(1)!r} is not the first wave of section 7")
    except Exception as e:  # noqa: BLE001
        err.append(f"current wave not checked: {e!r}")
    # 4c. one timing (Fahad 28 Nov 2026: the hourly maps): the summary's busiest hour of the wave = the waves' hourly
    # reading; each place in section 5 driven from the terrain carries the hours of its region's trigger; every row of
    # the hourly table has its peak inside its hours; the summary's trigger window = the regions' trigger hours
    try:
        import timing
        day0_ = date.fromisoformat(report.get("day") or date.today().isoformat())
        TT = st.get("timing")
        summ_ = " ".join(b.get("p", "") for b in secs[0]["blocks"])
        geo_ = secs[SEC["geo"]]["blocks"]
        m = re.search(r"وأوسع ساعاتها ([^٠-٩]+?) [^ ]+ ([٠-٩]+ \S+) على ([٠-٩]+) منطقة", summ_)
        if m and TT:
            a, b = _span(summ_[summ_.find("أقرب موجة: "):].split("،")[0], day0_)
            bz = timing.busiest(TT, a, b) if a else None
            if not bz or timing.HOUR_W[bz[1]] != m.group(1) or _ar(len(bz[2])) != m.group(3):
                err.append(f"timing: the summary's busiest hour «{m.group(1)}» is not the hourly reading {bz and bz[:2]}")
        trig = timing.trigger_hours(st, day0_)
        tab = next((b_["table"] for b_ in geo_ if "table" in b_ and b_["table"]["head"][:2] == ["المنطقة", "المكان"]), None)
        reg = None
        for r in (tab or {}).get("rows") or []:
            reg = r[0] or reg
            w = timing.day_window(trig.get(reg, []))
            if w and ("يصعد الحافة" in r[4] or r[4].startswith("التقاء الرياح")) and r[3] != w:
                err.append(f"timing: {r[1]} ({reg}) says «{r[3]}», its trigger is {w}")
        ht = next((b_["table"] for b_ in geo_ if "table" in b_ and b_["table"]["head"][0] == "اليوم"
                   and "الذروة" in b_["table"]["head"]), None)
        HW = {v: k for k, v in timing.HOUR_W.items()}

        def hours_of(t):
            out = set()
            for e in t.split("، ثم "):
                mm_ = re.match(r"من (.+) إلى (.+)$", e)
                if mm_:
                    out |= set(range(HW[mm_.group(1)], HW[mm_.group(2)] + 1, 3))
                else:
                    out.add(HW[e])
            return out
        for r in (ht or {}).get("rows") or []:
            pk = r[4].split(" (")[0]
            if HW.get(pk) not in hours_of(r[3]):
                err.append(f"timing: the peak {pk} of {r[1]} ({r[0]}) is outside its hours «{r[3]}»")
        mw = re.search(r"والحافز قائم (.+?) بحسب خريطة", summ_)
        if mw and tab:
            regs = {r[0] for r in tab["rows"] if r[0]}
            hs = sorted({h for k in regs for h in trig.get(k, []) if h >= 9})
            if mw.group(1) != timing.day_window(hs):
                err.append(f"timing: the summary's trigger window «{mw.group(1)}» is not {timing.day_window(hs)}")
    except Exception as e:  # noqa: BLE001
        err.append(f"timing not checked: {e!r}")
    # 4d. every relative day beside its date agrees with the report's day (Fahad 28 Nov 2026: «اليوم 28 اذا كنت لا تعلم»)
    try:
        day0_ = date.fromisoformat(report.get("day") or date.today().isoformat())
        dp = r"(" + "|".join(WEEKDAYS) + r") ([٠-٩]+) (" + "|".join(MONTHS) + r")"

        def _d(dd, mm):
            m_ = MONTHS.index(mm) + 1
            y = day0_.year + (1 if m_ < day0_.month - 6 else -1 if m_ > day0_.month + 6 else 0)
            return date(y, m_, int(_int(dd)))
        for i, j, t in T:
            for rel, wd, dd, mm in re.findall(r"(اليوم|غدًا|بعد غد) " + dp, t):
                n = {"اليوم": 0, "غدًا": 1, "بعد غد": 2}[rel]
                if (_d(dd, mm) - day0_).days != n:
                    err.append(f"relative day: «{rel} {wd} {dd} {mm}» in section {i + 1}, the report's day is {day0_}")
            for wd, dd, mm, nn, unit in re.findall(dp + r"، بعد ([٠-٩]+|يومين) ?(أيام|يومًا)? من اليوم", t):
                n = 2 if nn == "يومين" else int(_int(nn))
                if (_d(dd, mm) - day0_).days != n:
                    err.append(f"relative day: «{wd} {dd} {mm}» is not {nn} days from {day0_} (section {i + 1})")
            if "لأن ذروتها بعد" in t or "لأن ذروتها غدًا" in t:
                err.append(f"relative day: a lead without its date in section {i + 1}")
    except Exception as e:  # noqa: BLE001
        err.append(f"relative days not checked: {e!r}")
    # 3b. no repetition inside a paragraph: the same run of 6 words twice in one text, a word doubled, «س إلى س»
    for i, j, t in T:
        if " | " in t:
            continue
        w = re.findall(r"[\w٪°]+", t)
        seen6 = {}
        for k in range(len(w) - 5):
            g = " ".join(w[k:k + 6])
            if g in seen6 and k - seen6[g] >= 6:
                err.append(f"repeated words in section {i + 1} block {j}: «{g}»")
                break
            seen6.setdefault(g, k)
        for a, b in zip(w, w[1:]):
            if a == b and not re.fullmatch(r"[٠-٩]+", a):
                err.append(f"doubled word in section {i + 1} block {j}: «{a} {b}»")
                break
        mm = re.search(r"(?<![٠-٩])([٠-٩]+) إلى \1(?![٠-٩])", t)
        if mm:
            err.append(f"empty range in section {i + 1} block {j}: «{mm.group(0)}»")
        for bad in ("بعد يومًا", "الحكم: ثم", "بعد ١ يوم"):
            if bad in t:
                err.append(f"broken wording in section {i + 1} block {j}: «{bad}»")
    # 5. nothing left out
    import seacell
    import troughreach
    day0 = date.fromisoformat(report.get("day") or st.get("report", {}).get("day") or date.today().isoformat())
    for r in st.get("seacell") or []:
        if not (day0.isoformat() <= r["d"] <= (day0 + timedelta(days=7)).isoformat()) or not r.get("times"):
            continue
        lv = seacell.levels(r)
        for k in set([k for k, v in lv.items() if v >= 1] + seacell.passing(r)):
            if seacell.NAME[k] not in alltext:
                err.append(f"sea cells on {seacell.NAME[k]} ({r['d']}) not named in the report")
    for d, by in troughreach.activity(st.get("troughreach"), day0 + timedelta(days=1), day0 + timedelta(days=8)).items():
        for ks in by.values():
            for k in ks:
                if troughreach.NAME[k] not in alltext:
                    err.append(f"activity on {troughreach.NAME[k]} ({d}) not named in the report")
    # 6. the whole Kingdom is read
    st_ = [(a, b) for k, _n, a, b, _r in seacell.STRETCHES if k not in seacell.GULF]
    if max(b for a, b in st_) < 29.3 or min(a for a, b in st_) > 16.5:
        err.append("sea cells do not run from Haql to Jazan")
    for (a1, b1), (a2, b2) in zip(st_, st_[1:]):
        if abs(a1 - b2) > 1e-6:
            err.append(f"gap between sea-cell stretches at {a1}-{b2} N")
    if not seacell.GULF or seacell.BOX[3] < 50.5 or seacell.BOX[0] > 16.3 or seacell.BOX[1] < 29.5:
        err.append("the sea-cell box does not cover the Gulf coast, Haql and Jazan")
    zk = set(troughreach.NAME)
    for reg, ks in REGIONS.items():
        if not zk & set(ks):
            err.append(f"no sweep zone over {reg}")
    try:
        err += audit(report, st)
    except Exception as e:  # noqa: BLE001
        err.append(f"auditor crashed: {e!r}")
    return sorted(set(err), key=err.index)


# ------------------------------------------------------------------ the independent scientific auditor
WEEKDAYS = ("السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة")
MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
LEVELS = {"٢٠٠", "٢٥٠", "٣٠٠", "٥٠٠", "٦٠٠", "٧٠٠", "٨٠٠", "٨٥٠", "٩٢٥", "١٠٠٠"}
SOURCES = ("الأوروبي", "جي إف إس", "الأقمار الصناعية", "الوكالة اليابانية", "بيرسيان", "إعادة التحليل", "رصد")
LEVEL_RANK = {"ضعيفة": 0, "متوسطة": 1, "مرجحة": 2, "قوية": 3}


def _blocks_text(b):
    if "table" in b:
        t = b["table"]
        return [" | ".join(map(str, t.get("head") or []))] + [" | ".join(map(str, r)) for r in t.get("rows") or []]
    return [b[k] for k in ("p", "note", "h") if isinstance(b.get(k), str)]


def audit(report, st):
    """the twelve checks of the central charter (part 13) -> [error]"""
    err = []
    secs = report.get("sections") or []
    if len(secs) != NSEC:
        return err
    day0 = date.fromisoformat(report.get("day") or st["days"][0])
    by = [[t for b in s.get("blocks") or [] for t in _blocks_text(b)] for s in secs]
    alltext = "\n".join(t for x in by for t in x)
    # 1. calculations and percentages: «a من b» never above b; shares of the Kingdom at most 100 %
    for i, x in enumerate(by):
        for t in x:
            for a, b in re.findall(r"(?<![٠-٩٫])([٠-٩][٠-٩٫]*) من ([٠-٩][٠-٩]*)(?![٠-٩٫])", t):
                if _int(a) > _int(b):
                    err.append(f"audit 1: «{a} من {b}» in section {i + 1}")
            for a in re.findall(r"([٠-٩][٠-٩٫]*)٪ من (?:المملكة|مساحة)", t):
                if _int(a) > 100:
                    err.append(f"audit 1: a share of {a}% of the Kingdom in section {i + 1}")
    # 2. the source of every value: a paragraph with values in the moisture and vertical sections names its model
    for k in ("moist", "vert"):
        seen_src = False
        for b in secs[SEC[k]].get("blocks") or []:
            t = " ".join(_blocks_text(b))
            seen_src = seen_src or any(w in t for w in SOURCES)
            if "p" in b and re.search(r"[٠-٩]+ ?(?:٪|جول/كغ|ملم|كغ/م/ث)", t) and not seen_src:
                err.append(f"audit 2: a value without its model in section {SEC[k] + 1}: {t[:60]}")
    # 3. the run and the valid time: the report day is the day after the evening run; the readings are of that run
    cyc = st.get("cycle") or ""
    try:
        cd = date(int(cyc[:4]), int(cyc[4:6]), int(cyc[6:8]))
        if cyc[8:10] == "12" and day0 != cd + timedelta(days=1):
            err.append(f"audit 3: report day {day0} is not the day after the run {cyc}")
        for key in ("troughreach", "vertical", "seacell"):
            rows = st.get(key) or []
            if rows and not (day0 - timedelta(days=1) <= date.fromisoformat(rows[0]["d"]) <= day0 + timedelta(days=1)):
                err.append(f"audit 3: {key} starts {rows[0]['d']}, not with the report day {day0}")
    except ValueError:
        err.append(f"audit 3: the run {cyc!r} cannot be read")
    # 4. pressure levels: only the levels the system reads
    for i, x in enumerate(by):
        for t in x:
            for lv in re.findall(r"([٠-٩]+) هكتوباسكال", t):
                if lv not in LEVELS:
                    err.append(f"audit 4: level {lv} hPa in section {i + 1}")
    # 5. the summary agrees with the details: each region's chance in the summary = its judgement in section 5
    summ = " ".join(by[0])
    geo = next((b["table"] for b in secs[SEC["geo"]].get("blocks") or [] if "table" in b
                and b["table"]["head"][-1] == "الحكم"), None)
    if geo:
        for r in geo["rows"]:
            v = str(r[-1]).split("،")[0]
            if f"{r[0]} ({v})" not in summ:
                err.append(f"audit 5: {r[0]} is «{v}» in section 5 but not so in the summary")
    # 6. no forecast time already past (forecast sections only; the change and limits sections look back)
    pat = r"(" + "|".join(WEEKDAYS) + r") ([٠-٩]+) (" + "|".join(MONTHS) + r")"
    for k in ("sum", "dyn", "moist", "vert", "geo", "cells", "waves", "season"):
        for t in by[SEC[k]]:
            for wd, dd, mm in re.findall(pat, t):
                m = MONTHS.index(mm) + 1
                y = day0.year + (1 if m < day0.month - 6 else -1 if m > day0.month + 6 else 0)
                try:
                    d = date(y, m, int(_int(dd)))
                except ValueError:
                    err.append(f"audit 6: impossible date {wd} {dd} {mm}")
                    continue
                if d < day0 - timedelta(days=1) or (d < day0 and not re.search("(ليلة|مساء|أمس) " + wd, t)):
                    err.append(f"audit 6: past date {wd} {dd} {mm} in section {SEC[k] + 1}")
                if WEEKDAYS[(d.weekday() + 2) % 7] != wd:
                    err.append(f"audit 6: {dd} {mm} is not a {wd}")
    # 7. no conclusion beyond the evidence: a high judgement needs the coincidence tests; heavy places need it too
    if geo:
        for r in geo["rows"]:
            n = int(_int(str(r[3]).split(" ")[0]))
            v = str(r[-1])
            if ("مرجحة" in v.split("،")[0] and n < 3) or ("قوية" in v.split("،")[0] and n < 4):
                err.append(f"audit 7: {r[0]} judged «{v}» with {n} of 4 tests")
    places = next((b["table"] for b in secs[SEC["geo"]].get("blocks") or [] if "table" in b
                   and b["table"]["head"][:3] == ["المنطقة", "المكان", "الشدة"]), None)
    if places and geo:
        lvl = {r[0]: str(r[-1]).split("،")[0] for r in geo["rows"]}
        reg = None
        for r in places["rows"]:
            reg = r[0] or reg
            if r[2] == "غزيرة" and not any(w in lvl.get(reg, "") for w in ("مرجحة", "قوية")):
                err.append(f"audit 7: heavy rain at {r[1]} under a «{lvl.get(reg)}» judgement")
    # 8. the chance of rain is not the chance of heavy rain: a heavy-rain chance states its threshold
    for i, x in enumerate(by):
        for t in x:
            if re.search(r"(فرصة|احتمال)[^.؛]{0,20}(المطر الغزير|الغزارة)[^.؛]*[٠-٩]+٪", t) and "ملم" not in t:
                err.append(f"audit 8: heavy-rain chance without its threshold in section {i + 1}: {t[:60]}")
    # 9. no comparison of different units
    for i, x in enumerate(by):
        for t in x:
            for a, u1, b, u2 in re.findall(r"([٠-٩][٠-٩٫]*) ?(٪|ملم|م/ث|م|جول/كغ) مقابل ([٠-٩][٠-٩٫]*) ?(٪|ملم|م/ث|م|جول/كغ)", t):
                if u1 != u2:
                    err.append(f"audit 9: {a}{u1} against {b}{u2} in section {i + 1}")
    # 10. repetition: in check() (clauses and paragraphs); here, no sentence said in two sections word for word
    sent = {}
    for i, x in enumerate(by):
        for t in x:
            if " | " in t:
                continue
            for c in re.split(r"[.؛]\s*", t):
                c = c.strip()
                if len(c) >= 80:
                    if c in sent and sent[c] != i:
                        err.append(f"audit 10: sentence in sections {sent[c] + 1} and {i + 1}: {c[:60]}")
                    sent.setdefault(c, i)
    # 11. the confidence follows the model disagreement
    mo = next((b["table"] for b in secs[SEC["moist"]].get("blocks") or [] if "table" in b
               and b["table"]["head"][:3] == ["المتغير والمنطقة", "الأوروبي", "جي إف إس"]), None)
    cf = next((b["table"] for b in secs[SEC["conf"]].get("blocks") or [] if "table" in b
               and b["table"]["head"][0] == "البند"), None)
    if mo and cf and geo:
        rain = {r[0] for r in geo["rows"]} | {"غرب المملكة (مكة والمدينة)", "جنوب غرب المملكة"}
        hit = [r for r in mo["rows"] if r[-1] == "مؤثر" and any(n in r[0] for n in rain)]
        today = next((r for r in cf["rows"] if r[0] == "اليوم"), None)
        if hit and today and today[3] != "منخفضة":
            err.append("audit 11: the models differ over the rain regions but the intensity confidence is not low")
    # 12. read and missing told apart: the coverage log and the missing variables are in section 10
    conf = " ".join(by[SEC["conf"]])
    for h in ("سجل التغطية", "المتغيرات غير المتوفرة وأثرها", "حصر الخرائط"):
        if h not in conf:
            err.append(f"audit 12: «{h}» missing from section 10")
    # no score without its method
    if "من ٥" in alltext and "تعريف القوة من ٥" not in alltext:
        err.append("audit: a score out of 5 without its method")
    if "من ١٠٠" in alltext and "تعريف قوة مكونات الهطول من ١٠٠" not in alltext:
        err.append("audit: a score out of 100 without its method")
    wt = next((b["table"] for b in secs[SEC["waves"]].get("blocks") or [] if "table" in b
               and b["table"]["head"][:3] == ["الفترة", "النوع", "القوة"]), None)
    if wt and any(str(r[2]).endswith("٪") for r in wt["rows"]):
        err.append("audit: wave strength given as a bare percentage")
    return err
