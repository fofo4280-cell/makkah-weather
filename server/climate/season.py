"""The seasonal outlook (Fahad, 19 Nov 2026: «النظرة الموسمية»): where the Madden-Julian oscillation is, when it reaches
the phases that favour widespread rain over the Kingdom, and the ENSO background, in plain words people can share.

Method (tested before publishing, 25 wet seasons 2001-2026, CHIRPS share of the Kingdom with 5 mm or more, weekly):
  - the index: JMA's MJO index (OLR + u850 + u200, ENSO removed; Dr. Khalid's reference; Fahad 19 Nov 2026:
    «اجعل التذبذب كما لدى الدكتور تمامًا»), st["rmm_jma"]; the BoM RMM (st["rmm_obs"]) only if JMA is missing;
  - the last observed value is carried eastward at the usual speed of the oscillation
    (one cycle in 45 days, 8 degrees a day); the GFS projection is NOT used here (it was not part of the test);
  - each coming week (7 days from the report day) is classed by its projected phases: supportive (4 days or more in
    phases 7, 8, 1), suppressing (4 days or more in phases 2-5), between, or weak (amplitude below 1);
  - the chance that a week is wetter than usual (top third of its month over the Kingdom) by class and lead, from the
    test with the JMA index (study branch study/season, docs in PROJECT.md): supportive 53/50/45/40/38 %, suppressing
    14/21/26/28/26 %, usual 33 % (with the BoM index 49/49/43/42/42 and 17/20/25/28/27);
  - ENSO: Nino 3.4 of the last month (PSL); El Nino seasons (Oct >= 0.5, 8 of 25) had wet weeks more often (38 % vs 31 %;
    widespread 20 % vs 15 %); the Indian Ocean Dipole showed no link with widespread weeks and is not used.
"""
import math
from datetime import date, timedelta

from sa_geo import ar, num, ar_date, ar_span

SPEED = 8.0                       # degrees a day: one cycle in 45 days
SUPP, SUPR = {7, 8, 1}, {2, 3, 4, 5}
WEEKS = 5
# chance (%) that the week is wetter than usual, by class and lead week (test, 25 seasons)
RATE = {"sup": [53, 50, 45, 40, 38], "supr": [14, 21, 26, 28, 26], "mid": [42, 32, 23, 25, 31], "weak": [33, 35, 35, 35, 37]}
CLS_WORD = {"sup": "داعم", "supr": "كابح", "mid": "انتقالي", "weak": "ضعيف"}
STATE_WORD = {"sup": "فرصة خصب واسع", "supr": "هدوء نسبي", "mid": "أمطار متفرقة كالمعتاد", "weak": "حسب الأخاديد"}


def _ang(r1, r2):
    return math.degrees(math.atan2(r2, r1)) % 360


def phase_of(a):
    return int(((a - 180) % 360) // 45) + 1


def _proj(obs, day):
    return phase_of((_ang(obs["r1"], obs["r2"]) + SPEED * (day - date.fromisoformat(obs["d"])).days) % 360)


def _entry(obs, phase, after):
    """first day on or after `after` when the projection enters `phase`"""
    for k in range(0, 60):
        d = after + timedelta(days=k)
        if _proj(obs, d) == phase:
            return d
    return None


def outlook(st, day0):
    src = "jma" if st.get("rmm_jma") else "bom"
    obs = (st.get("rmm_jma") or st.get("rmm_obs") or [None])[-1]
    if not obs:
        return None
    weeks = []
    for k in range(WEEKS):
        a, b = day0 + timedelta(days=7 * k), day0 + timedelta(days=7 * k + 6)
        ph = [_proj(obs, a + timedelta(days=i)) for i in range(7)]
        if obs["amp"] < 1:
            c = "weak"
        elif sum(p in SUPP for p in ph) >= 4:
            c = "sup"
        elif sum(p in SUPR for p in ph) >= 4:
            c = "supr"
        else:
            c = "mid"
        seen = []
        for p in ph:
            if p not in seen:
                seen.append(p)
        weeks.append({"a": a, "b": b, "phases": seen, "cls": c, "rate": RATE[c][k]})
    # the fertile spell: projected days in phases 7, 8, 1 (amplitude 1 or more), from the report day on
    spell = None
    if obs["amp"] >= 1:
        if _proj(obs, day0) in SUPP:
            s0 = day0
        else:
            s0 = _entry(obs, 7, day0)
        if s0:
            e = s0
            while _proj(obs, e + timedelta(days=1)) in SUPP:
                e += timedelta(days=1)
            spell = (s0, e)
    enso = st.get("enso")
    return {"obs": obs, "src": src, "weeks": weeks, "spell": spell, "enso": enso}


MONTH = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def _enso_text(e):
    v = e["v"]
    m = MONTH[int(e["m"][5:7]) - 1]
    if v >= 2.0:
        kind = "نينيو قوي جدًا"
    elif v >= 1.5:
        kind = "نينيو قوي"
    elif v >= 0.5:
        kind = "نينيو"
    elif v <= -0.5:
        kind = "نينيا"
    else:
        kind = None
    if kind is None:
        return (f"المحيط الهادئ قريب من معدله (فرق حرارة سطحه في وسطه {num(v, 1)} درجة في {m})، فلا يميل الموسم "
                "إلى الرطوبة ولا إلى الجفاف من جهته.")
    head = f"حرارة سطح الماء في وسط المحيط الهادئ {'أعلى' if v > 0 else 'أدنى'} من معدلها بـ{num(abs(v), 1)} درجة في {m}، أي {kind}. "
    if v >= 0.5:
        return head + ("وفي مواسم النينيو الثمانية من المواسم الخمسة والعشرين الماضية كانت الأسابيع الممطرة على المملكة أكثر "
                       "من غيرها (٣٨٪ من الأسابيع مقابل ٣١٪)، فالخلفية العامة للموسم مساندة بإذن الله.")
    return head + "ومواسم النينيا لم تختلف كثيرًا عن المعتاد في عدد الأسابيع الممطرة."


def blocks(st, day0):
    o = outlook(st, day0)
    if not o:
        return []
    ob = o["obs"]
    od = date.fromisoformat(ob["d"])
    strength = "نشط وقوي" if ob["amp"] >= 1.5 else "نشط" if ob["amp"] >= 1 else "ضعيف"
    B = [{"h": "النظرة الموسمية"}]
    nxt = []
    p = ob["phase"]
    for _ in range(2):
        p = p % 8 + 1
        nxt.append(ar(p))
    t = (f"التذبذب المداري (مادن-جوليان) في الطور {ar(ob['phase'])} وقوته {num(ob['amp'], 1)}، أي {strength} "
         f"(مؤشر {'الوكالة اليابانية للأرصاد الجوية' if o['src'] == 'jma' else 'مكتب الأرصاد الأسترالي'}، آخر رصد "
         f"{ar_date(od, weekday=False)})")
    hist = (st.get("rmm_jma") if o["src"] == "jma" else st.get("rmm_obs")) or []
    dwell = sum(1 for x in hist if x["phase"] in (3, 4))
    if len(hist) >= 50 and dwell >= 30 and ob["phase"] not in (3, 4):
        t += f"، بعد مكوث طويل في الطورين ٣ و٤ الكابحين ({ar(dwell)} يومًا من آخر {ar(len(hist))})"
    if ob["amp"] >= 1:
        t += f"، ويتقدم شرقًا نحو الطورين {nxt[0]} و{nxt[1]}"
    B.append({"p": t + ". أطوارنا الداعمة للأمطار الواسعة على المملكة هي ٧ و٨ و١، والأطوار ٣ و٤ و٥ أكثرها كبحًا."})
    sp = o["spell"]
    if sp:
        n_days = (sp[1] - sp[0]).days + 1
        wk = n_days / 7
        wk_t = ("نحو أسبوع" if wk < 1.4 else "نحو أسبوعين" if wk < 2.3 else "نحو أسبوعين ونصف" if wk < 2.8
                else f"نحو {ar(round(wk))} أسابيع")
        if sp[0] == day0:
            B.append({"p": f"التذبذب الآن في طور داعم، ويبقى فيه بسرعته المعتادة حتى نحو {ar_date(sp[1], weekday=False)}."})
        else:
            B.append({"p": f"بسرعته المعتادة يصل التذبذب إلى أطوارنا الداعمة نحو {ar_date(sp[0], weekday=False)}، "
                           f"ويبقى فيها حتى نحو {ar_date(sp[1], weekday=False)} ({wk_t})."})
    if o["enso"]:
        B.append({"p": _enso_text(o["enso"])})
    rows = []
    for k, w in enumerate(o["weeks"]):
        rows.append([ar_span(w["a"], w["b"]).removeprefix("من "), " ثم ".join(ar(p) for p in w["phases"]),
                     STATE_WORD[w["cls"]], f"{ar(w['rate'])}٪"])
    B.append({"table": {"head": ["الأسبوع", "طور التذبذب", "الحالة", "فرصة أسبوع ممطر"], "rows": rows}})
    # the verdict
    ws = o["weeks"]
    if ob["amp"] < 1:
        v = ("الحكم: التذبذب ضعيف الآن، فلا إشارة موسمية واضحة منه في الأسابيع القادمة، وتبقى الأمطار رهينة الأخاديد "
             "والمنخفضات العابرة.")
    elif sp:
        calm = [w for w in ws if w["b"] < sp[0] and w["cls"] == "supr"]
        v = "الحكم: "
        if sp[0] > day0:
            # the day before the spell is today: say «اليوم», not «حتى نحو» today's date (Fahad, 26 Nov 2026)
            v += (f"{'هدوء نسبي' if calm else 'أمطار متفرقة كالمعتاد'} " +
                  ("اليوم، " if (sp[0] - day0).days == 1 else
                   f"حتى نحو {ar_date(sp[0] - timedelta(days=1), weekday=False)}، "))
        v += (f"ثم فترة خصب واسعة متوقعة على المملكة {ar_span(sp[0], sp[1])} "
              f"({wk_t}) بإذن الله")
        if o["enso"] and o["enso"]["v"] >= 0.5:
            v += "، والنينيو يسندها"
        v += "."
        far = (sp[0] - day0).days
        v += (" والثقة عالية في توقيتها." if far <= 10 else " والثقة متوسطة في توقيتها لأنها بعد أكثر من أسبوع." if far <= 21
              else " والثقة منخفضة في توقيتها لأنها بعد أكثر من ثلاثة أسابيع، وتُحدّث كل ليلة.")
    else:
        v = ("الحكم: لا يصل التذبذب إلى أطوارنا الداعمة في الأسابيع الخمسة القادمة، فالأرجح هدوء نسبي مع أمطار "
             "تأتي بها الأخاديد فقط.")
    B.append({"p": v})
    B.append({"note": "اختُبرت هذه النظرة على خمسة وعشرين موسمًا ممطرًا (٢٠٠١-٢٠٢٦) بأمطار الأقمار الصناعية والمحطات أسبوعًا "
                      "بأسبوع: الأسابيع التي توقعنا فيها طورًا داعمًا كانت ممطرة على نطاق واسع فوق المعتاد في ٥٣٪ منها "
                      "(والمعتاد ٣٣٪)، وأمطارها شملت ٥٪ من المملكة فأكثر في ٢٤٪ منها، مقابل ١٤٪ و٥٪ في أسابيع الأطوار الكابحة، "
                      "وتبقى الإشارة نافعة حتى الأسبوع الخامس. وأسابيع الطور ٨ وحدها كانت ممطرة في ٦٢٪ منها. التذبذب لا يحدد "
                      "يوم المطر ومكانه، بل يرفع أو يخفض فرص الأمطار الواسعة."})
    return B
