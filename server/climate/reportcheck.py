"""The self-check run on the night's report before it is published (Fahad 27 Nov 2026: «انت تحلل السعودية كاملة بحرا
وساحل ويابسة واي نشاط فيها يذكر.. ولا أريد اي أخطاء أخرى مره ثانية»). A report that fails is not published: the site
keeps the last good report and the failure is written to the status (status["report_check"]) and the job log.

    check(report, st, img=None) -> [error, ...]   ([] = publish)

What it checks:
  1. the analyst charter's 9 sections, in order, none empty;
  2. Arabic only (no Latin letter in any text) and no broken text (None, nan, braces, doubled commas or spaces);
  3. no repetition: no clause of 45+ characters in two blocks, no two identical paragraphs;
  4. one story: the nearest wave's period in the summary = in the waves section, and the wave map is of that period;
  5. nothing left out: every coast stretch with any sea-cell reading (passing showers or more) on the coming nights,
     and every zone of the Kingdom-wide sweep with activity, is named in the report; every wave area of the table is
     named in the summary or the waves section text;
  6. the reading covers the whole Kingdom: the sea-cell stretches run without a gap from Haql to Jazan and the Gulf
     coast is read; the trough/activity zones include every administrative region.
"""
import re
from datetime import date, timedelta

ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
REGIONS = {   # administrative region -> the sweep zones that cover it (troughreach.ZONES keys)
    "الرياض": ("riyadh", "kharj", "majmaah", "dawasir"), "مكة المكرمة": ("jeddah_makkah", "taif", "qunf"),
    "المدينة المنورة": ("madinah", "khaybar"), "القصيم": ("qassim",), "الشرقية": ("eastern", "ahsa", "gulf", "hafr"),
    "عسير": ("asir", "bisha"), "تبوك": ("tabuk", "duba", "c_tabuk"), "حائل": ("hail",), "الحدود الشمالية": ("nb",),
    "جازان": ("jazan",), "نجران": ("najran", "sharurah"), "الباحة": ("asir",), "الجوف": ("jouf",)}


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
    # 1. the 9 sections
    if len(secs) != 9:
        err.append(f"sections: {len(secs)} instead of 9")
    for i, s in enumerate(secs):
        if not (s.get("heading") or "").startswith(ARABIC_DIGITS[i + 1] + "."):
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
        wsec = secs[5]["blocks"]
        m = re.search(r"أقرب موجة: ([^،]+)،", summ)
        tab = next((b["table"] for b in wsec if "table" in b and b["table"]["head"][0] == "الفترة"), None)
        para = next((b["p"] for b in wsec if b.get("p", "").startswith("أقرب موجة: ")), "")
        per = tab["rows"][0][0] if tab else (re.search(r"أقرب موجة: ([^،]+)،", para) or [None, None])[1]
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
    return sorted(set(err), key=err.index)
