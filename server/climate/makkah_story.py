"""One reading of the day round Makkah, Taif and the escarpment, before anything is written (18 Nov 2026).

Fahad, 18 Nov 2026: «مشكلة التقرير انه يتعامل بجمود ولا يقرأ العوامل كلها بشكل ذكي ... لا بد ان تتعلم جيدا كيف تقرأ
الحالة ثم تكتب». The Makkah section was written by separate rules (edges, Taif collision, plain outflow, model lines),
each blind to the others, so one paragraph said the storms move east of Taif while the next said the edge, and the
plain verdict sent cells to Al-Jumum while the steering and our run carried them north-east, away from the plain.

Here the factors are read together, in the order a forecaster reads them:
  1. where the cells start: the wind meeting at 11 AM-1 PM (GFS), checked against the fuel (CAPE) there, and the
     first cores of our run;
  2. where they peak and which edges the ingredients support (plains.edges);
  3. where they go: the 700-500 hPa steering (GFS) and the track of our run's cores, hour by hour;
  4. who gets rain and who does not, zone by zone, from our run, judged against the steering and the support;
  5. the support from aloft (500 hPa fall, cooling).
Every Makkah sentence of the report (summary line, plain verdict, overall assessment) is then written from this one
reading, so they cannot disagree.

track(doms, t_a) runs where our model fields are (rainreport.rain_report) and stores st["mstory"]; read(st) builds the
reading from it and the GFS rows in st["plains"].
"""
import math

import numpy as np

BOX = (20.7, 22.7, 39.5, 41.2)           # Makkah, Al-Jumum, Jeddah's east, Taif, Al-Sail, Harrat Shamnasir
CORE_DBZ = 40.0
# well-known places only (PROJECT.md rule), coordinates from sa_osm.json
PLACES = [("مكة", 21.42, 39.83), ("الجموم", 21.621, 39.699), ("الشرائع", 21.465, 39.948), ("الجعرانة", 21.560, 39.957),
          ("عرفة", 21.355, 39.984), ("بحرة", 21.401, 39.450), ("الزيمة", 21.617, 40.111), ("حاذة", 21.658, 40.005),
          ("المضيق", 21.679, 40.133), ("مدركة", 21.987, 39.994), ("رهاط", 22.087, 40.019), ("الكامل", 22.264, 39.798),
          ("الهدا", 21.369, 40.285), ("الشفا", 21.069, 40.312), ("وادي ملكان", 21.16, 40.15), ("الوهيط", 21.229, 40.342),
          ("الطائف", 21.270, 40.416), ("الحوية", 21.445, 40.503), ("السيل الصغير", 21.506, 40.482),
          ("السيل الكبير", 21.626, 40.415), ("العرفاء", 21.532, 40.620), ("عشيرة", 21.758, 40.651),
          ("القرشيات", 21.614, 40.713), ("قيا", 21.071, 41.007), ("ميسان", 20.737, 40.839), ("حرة شمنصير", 22.33, 39.96)]
# zones the report speaks of (s, n, w, e); "city" zones are where people live on the plain
ZONES = [
    ("makkah", "مكة", (21.33, 21.50, 39.75, 39.93), "plain"),
    ("jumum", "الجموم ووادي فاطمة", (21.55, 21.72, 39.58, 39.80), "plain"),
    ("sharai", "الشرائع والجعرانة", (21.44, 21.60, 39.93, 40.05), "plain"),
    ("east_hills", "مرتفعات شرق مكة وحراتها (حاذة والزيمة والمضيق)", (21.58, 21.95, 39.95, 40.22), "hills"),
    ("hada", "حافة الهدا", (21.27, 21.45, 40.17, 40.33), "edge"),
    ("shafa", "حافة الشفا ووادي ملكان", (20.95, 21.27, 40.05, 40.40), "edge"),
    ("taif", "الطائف", (21.20, 21.36, 40.35, 40.50), "plateau"),
    ("hawiyah", "الحوية والسيل الصغير", (21.38, 21.55, 40.43, 40.58), "plateau"),
    ("sail", "السيل الكبير", (21.55, 21.75, 40.33, 40.52), "plateau"),
    ("arfa", "العرفاء وعشيرة", (21.47, 21.85, 40.56, 40.80), "plateau"),
    ("east_taif", "شرق الطائف (القرشيات وقيا)", (21.00, 21.47, 40.62, 41.10), "plateau"),
    ("shamnasir", "حرة شمنصير", (22.15, 22.60, 39.85, 40.15), "hills"),
]
SHORT = {"east_hills": "مرتفعات شرق مكة وحراتها قرب حاذة", "shafa": "حافة الشفا", "hawiyah": "الحوية", "sharai": "الشرائع والجعرانة",
         "arfa": "العرفاء", "east_taif": "شرق الطائف"}
# the edges table's "our model" column, from the same zones as the reading (one number per place in the report)
EDGE_ZONES = {"hada": ("hada",), "shafa": ("shafa",), "sail": ("sail", "hawiyah"), "shamnasir": ("shamnasir",)}
DIRS = ["الشمال", "الشمال الشرقي", "الشرق", "الجنوب الشرقي", "الجنوب", "الجنوب الغربي", "الغرب", "الشمال الغربي"]


def place_of(la, lo):
    best = min(PLACES, key=lambda p: (p[1] - la) ** 2 + ((p[2] - lo) * math.cos(math.radians(la))) ** 2)
    return best[0]


def toward(u, v):
    """the compass word a motion (u east, v north) goes toward"""
    ang = (math.degrees(math.atan2(u, v)) + 360) % 360
    return DIRS[int((ang + 22.5) // 45) % 8]


def track(doms, t_a):
    """our run's cores round Makkah hour by hour, and the day's rain per zone (from the 3 km grid that covers it)"""
    best = None
    for d in doms:
        if d.get("dx", 9e9) > 5000:
            continue
        la, lo = d["lat"], d["lon"]
        m = (la >= BOX[0]) & (la <= BOX[1]) & (lo >= BOX[2]) & (lo <= BOX[3]) & d["inner"]
        if m.sum() > 2000 and (best is None or m.sum() > best[1].sum()):
            best = (d, m)
    if best is None:
        return None
    d, m = best
    la, lo = d["lat"], d["lon"]
    hours, tot = [], np.zeros(la.shape, np.float32)
    for i, h in enumerate(d["keys"]):
        z, r = d["refl"][i], d["rain"][i]
        tot += r
        idx = np.where(m & (z >= CORE_DBZ))[0]
        if not len(idx):
            continue
        cores = {}
        for j in idx[np.argsort(-z[idx])]:
            p = place_of(float(la[j]), float(lo[j]))
            if p not in cores:
                cores[p] = {"p": p, "dbz": int(round(float(z[j]))), "lat": round(float(la[j]), 2), "lon": round(float(lo[j]), 2)}
        w = z[idx] - CORE_DBZ + 1
        hours.append({"h": int(h), "n": int(len(idx)), "cores": list(cores.values())[:5],
                      "lat": round(float(np.average(la[idx], weights=w)), 3),
                      "lon": round(float(np.average(lo[idx], weights=w)), 3),
                      "rmax": round(float(r[m].max()), 1)})
    zones = {}
    for k, nm, (s, n, w_, e), kind in ZONES:
        zm = m & (la >= s) & (la <= n) & (lo >= w_) & (lo <= e)
        if zm.any():
            j = np.where(zm)[0][int(np.argmax(tot[zm]))]
            zones[k] = {"max": round(float(tot[zm].max()), 1), "p90": round(float(np.percentile(tot[zm], 90)), 1),
                        "at": place_of(float(la[j]), float(lo[j]))}
    return {"run": d["run"], "hours": hours, "zones": zones}


# ------------------------------------------------------------------ the reading
def read(st, pending=False):
    """{start, peak, motion, evening, rain, dry, upper, ...}: everything the Makkah sentences say, decided once"""
    pl = st.get("plains") or {}
    eds = {e["key"]: e for e in pl.get("edges") or []}
    prs = {r["key"]: r for r in pl.get("rows") or []}
    tr = None if pending else st.get("mstory")
    mk = prs.get("makkah") or {}
    tz = (eds.get("sail") or {}).get("taif_conv") or {}
    R = {"model": bool(tr), "pending": pending}
    import plains as P
    named = [k for k in ("hada", "shafa", "sail", "shamnasir", "rahat_s") if k in eds and P.edge_named(eds[k], eds[k].get("model_rain"))[0]]
    R["named"] = named
    # 1. the start: the meeting of the winds (GFS 11 AM-1 PM) against the fuel, then our run's first cores
    if tz:
        if tz.get("shifted"):
            R["meet"] = ("east", tz["east"].get("place"))
        elif tz.get("east_dry"):
            R["meet"] = ("east_dry", tz["east"].get("place"))
        else:
            R["meet"] = ("edge", tz["edge"].get("place"))
        R["cape_edge"], R["cape_east"] = tz.get("cape_edge"), tz.get("cape_east")
    # the regime the collision is telling (Fahad, 18 Nov 2026: «ارتفاع تصادم الرياح اليوم شمال الطائف دلالة على وجود
    # اخدود داعم حتى لو كان ضحل وضعيف»). The meeting moves north and east of Taif when the plateau wind is no longer
    # easterly enough to stop the sea air at the rim, which is what a trough to the north (westerlies, the jet over the
    # Hijaz) does; the study of 17 Nov found it 26 of 30 days with troughs north (16 Oct-14 Nov). So the shift is read
    # as a sign of support, confirmed by what the trough does aloft, not dismissed for the CAPE east of Taif.
    # Fahad, a minute later: «ليس دائما علامة لكن يعطيك تصور ما الذي تغير في الغلاف الجوي لتتغير أماكن التصادم ثم
    # تبحث عن السبب وتتأكد». So: compare with yesterday; if the meeting moved, look for the cause and call it a trough
    # only when the air aloft confirms it (two signs or more), otherwise name what did change.
    cues = []
    tc = st.get("taifc_gfs") or st.get("taifc") or {}     # the report reads the GFS collision (19 Nov 2026)
    rows_ = tc.get("rows") or []
    ti = next((i for i, r in enumerate(rows_) if r.get("d") == tc.get("today")), None)
    trow = rows_[ti] if ti is not None else None
    yrow = rows_[ti - 1] if ti else None
    side = lambda r: None if not r or not r.get("where") else ("east" if r["where"] in ("east", "eastdry") else r["where"])
    R["moved"] = (side(yrow), side(trow)) if side(yrow) and side(trow) and side(yrow) != side(trow) else None
    wind = lambda u: (f"غربية {n1(u)} م/ث" if u >= 0.5 else "شبه ساكنة" if u > -0.5 else f"شرقية {n1(-u)} م/ث")
    if trow and trow.get("u850") is not None:
        if yrow and yrow.get("u850") is not None and abs(trow["u850"] - yrow["u850"]) >= 1.5:
            cues.append(("u850", f"تحولت الرياح فوق هضبة الطائف عند ٨٥٠ من {wind(yrow['u850'])} أمس إلى {wind(trow['u850'])} اليوم"))
        elif trow["u850"] > -2:
            cues.append(("u850", f"الرياح فوق هضبة الطائف عند ٨٥٠ {wind(trow['u850'])} لا توقف هواء البحر عند الحافة"))
    day0 = tc.get("today") or pl.get("day")
    for t in st.get("troughs") or []:
        x = next((x for x in t.get("days") or [] if x.get("d") == day0), None)
        if x and x.get("tip") and x["tip"][0] <= 28 and 34 <= x["tip"][1] <= 44:
            cues.append(("tip", f"وطرف أخدود يمتد إلى نحو {ar(int(x['tip'][0]))} شمالًا فوق الحجاز"))
            break
    up_ = (eds.get("hada") or {}).get("upper") or {}
    if up_.get("fall") is not None and up_["fall"] <= -10:
        cues.append(("fall", f"وهبط سطح ٥٠٠ هكتوباسكال نحو {ar(abs(round(up_['fall'])))} مترًا خلال يوم"))
    if up_.get("t500") is not None and up_["t500"] <= -7:
        cues.append(("cold", f"وبردت طبقة ٥٠٠ إلى ‎−{n1(abs(up_['t500']))}°"))
    if up_.get("w200") is not None and up_["w200"] >= 30:
        cues.append(("jet", f"والتيار النفاث فوق الحجاز {ar(round(up_['w200']))} م/ث"))
    east_meet = bool(tz) and (tz.get("shifted") or tz.get("east_dry"))
    aloft = [c for c in cues if c[0] != "u850"]
    R["trough"] = len(aloft) >= 2            # confirmed aloft, not read from the collision alone
    R["cues"] = [c[1] for c in cues]
    R["cue_wind"] = next((c[1] for c in cues if c[0] == "u850"), None)
    R["cue_aloft"] = [c[1].removeprefix("و") for c in aloft]
    R["east_meet"] = east_meet
    hrs = (tr or {}).get("hours") or []
    day = [x for x in hrs if 10 <= x["h"] <= 21]
    if day:
        R["first"] = {"h": day[0]["h"], "places": [c["p"] for c in day[0]["cores"][:3]]}
        pk = max(day, key=lambda x: x["n"])
        R["peak"] = {"h": pk["h"], "places": [c["p"] for c in pk["cores"][:5]], "dbz": max(c["dbz"] for c in pk["cores"])}
        eve = [x for x in hrs if 18 <= x["h"] <= 23]
        if eve:
            seen = []
            for x in eve:
                for c in x["cores"][:3]:
                    if c["p"] not in seen:
                        seen.append(c["p"])
            R["evening"] = {"from": eve[0]["h"], "to": eve[-1]["h"], "places": seen[:5]}
        # the track of the cores after the peak (weighted centre, hour by hour)
        after = [x for x in hrs if x["h"] >= pk["h"]]
        if len(after) >= 3:
            dy = (after[-1]["lat"] - pk["lat"]) * 111
            dx = (after[-1]["lon"] - pk["lon"]) * 111 * math.cos(math.radians(pk["lat"]))
            if math.hypot(dx, dy) >= 15:
                R["model_track"] = toward(dx, dy)
    # 3. the steering (GFS 700-500 hPa over the Makkah plain and its mountains, noon and 3 PM)
    if mk.get("steer") is not None and mk.get("steer_v") is not None:
        R["steer"] = {"to": toward(mk["steer_u"], mk["steer_v"]), "speed": mk["steer"], "u": mk["steer_u"], "v": mk["steer_v"]}
    # 4. rain per zone from our run
    zs = (tr or {}).get("zones") or {}
    if zs:
        wet = sorted([(v["max"], k) for k, v in zs.items() if v["max"] >= 5], reverse=True)
        R["rain"] = [{"k": k, "name": dict((z[0], z[1]) for z in ZONES)[k], "max": v, "at": zs[k]["at"]} for v, k in wet]
    # the plain: does rain reach Makkah and Al-Jumum? our run, then the steering (west = down onto the plain)
    # down onto the plain: steering from the east, or an easterly 700 hPa wind (16 Nov 2026: 700 ESE carried the
    # Al-Hada cells to Ash-Sharai while the 700-500 mean was 1.8 m/s eastward), or steering so weak (< 3 m/s) that
    # the cold outflow, running downhill, decides where new cells form
    west = bool(R.get("steer") and (R["steer"]["u"] <= -1.0 or R["steer"]["speed"] < 3.0
                                     or (mk.get("u700") is not None and mk["u700"] <= -1.0)))
    R["toward_plain"] = west
    city = {}
    for k in ("makkah", "jumum", "sharai"):
        mr = (zs.get(k) or {}).get("max")
        if mr is not None and mr >= 5:
            city[k] = "rain"
        elif mr is not None and mr >= 1:
            city[k] = "light"
        elif (west and (mk.get("gate") or mk.get("flags", {}).get("mountain"))) or (mk.get("rain_plain_gfs") or 0) >= 3:
            city[k] = "possible"            # carried down from the edge even when our run keeps it on the mountains
        else:
            city[k] = "unlikely"
    R["city"] = city
    # 5. the support from aloft over Al-Hada
    up = (eds.get("hada") or {}).get("upper") or {}
    R["upper"] = {k: up.get(k) for k in ("fall", "t500", "rh500")} if up else {}
    return R


def ar(x):
    from sa_geo import ar as _ar
    return _ar(x)


def n1(x):
    from sa_geo import num
    return num(x, 1)


def clock(h):
    h = int(h) % 24
    if h == 0:
        return "منتصف الليل"
    if h == 12:
        return "الظهر"
    part = "صباحًا" if h < 12 else "ظهرًا" if h < 15 else "عصرًا" if h < 18 else "مساءً"
    return f"{ar(h if h <= 12 else h - 12)} {part}"


def jl(xs):
    xs = [x for x in xs if x]
    return xs[0] if len(xs) == 1 else "، و".join(xs[:-1]) + " و" + xs[-1] if xs else ""


def story(R):
    """the paragraphs of «قراءة الحالة اليوم», in the order the day unfolds"""
    out = []
    # the start
    m = R.get("meet")
    t = ""
    WH = {"edge": "حافة الهدا والشفا", "east": "شمال الطائف وشرقه", "weak": "ضعيفًا حول الطائف"}
    mv = R.get("moved")
    if mv:     # the meeting moved since yesterday: what changed, and is it confirmed aloft?
        t0 = f"انتقل تصادم الرياح من {WH.get(mv[0], mv[0])} أمس إلى {WH.get(mv[1], mv[1])} اليوم" + (f" (قرب {m[1]})" if m else "") + "."
        why = ([R["cue_wind"]] if R.get("cue_wind") else [])
        if R.get("trough"):
            t0 += (" وسبب ذلك: " + "، و".join(why + R["cue_aloft"]) + "؛ فهو أثر أخدود داعم وإن كان ضحلًا.")
        elif why:
            t0 += (" وسبب ذلك: " + why[0] + "، دون علامة علوية واضحة على أخدود"
                   + (f" ({R['cue_aloft'][0]} فقط)" if R.get("cue_aloft") else "") + "، فهو تغير في رياح الهضبة، وأثره أضعف.")
        else:
            t0 += " ولا يظهر في رياح الهضبة ولا في الجو العلوي سبب واضح لذلك، فالثقة في هذا الانتقال أقل."
        out.append(t0)
    if m and R.get("east_meet") and (R.get("trough") or mv):
        if not mv:
            out.append(f"ويبقى تصادم الرياح شمال الطائف وشرقه (قرب {m[1]})"
                       + ("، ويسنده من الأعلى " + "، و".join(R["cue_aloft"]) if R.get("trough") else "") + ".")
        t = "فتنشأ السحب أول النهار على الهضبة شمال الطائف وشرقه، ثم تمتد إلى الحواف مع تقدم النهار"
        if m[0] == "east_dry" and R.get("cape_east") is not None:
            t += (f"، والطاقة على الحواف أعلى (نحو {ar(round(R.get('cape_edge') or 0, -1))} جول/كغ مقابل "
                  f"{ar(round(R['cape_east'], -1))} شرق الطائف) فتكون أقوى الخلايا عليها")
    elif m:
        if m[0] == "east":
            t = f"تتقارب الرياح أول النهار (١١ صباحًا إلى ١ ظهرًا) شرق الطائف قرب {m[1]}، وفي الهواء هناك طاقة كافية، فتنشأ السحب الأولى هناك"
        elif m[0] == "east_dry":
            t = (f"تتقارب الرياح أول النهار (١١ صباحًا إلى ١ ظهرًا) أقوى ما يكون شرق الطائف قرب {m[1]}، لكن الطاقة هناك ضعيفة "
                 f"(نحو {ar(round(R.get('cape_east') or 0, -1))} جول/كغ مقابل {ar(round(R.get('cape_edge') or 0, -1))} على الحافة)، "
                 "فبدايات السحب هناك متواضعة")
        else:
            t = f"تتقارب الرياح أول النهار على الحافة قرب {m[1]}، فتنشأ السحب الأولى على حافة الهدا والشفا"
    f = R.get("first")
    if f:
        t += (("، " if t else "") + f"ويُظهر نموذجنا أول الخلايا نحو {clock(f['h'])} قرب {jl(f['places'])}")
    if t:
        out.append(t + ".")
    # the peak
    p = R.get("peak")
    if p:
        out.append(f"وتبلغ الخلايا ذروتها نحو {clock(p['h'])} على {jl(p['places'])}، بصدى رادار يصل إلى {ar(p['dbz'])} ديسيبل.")
    elif R.get("named"):
        out.append("وتجتمع مكونات الحمل الحراري بعد الظهر على الحواف المذكورة في الجدول أدناه"
                   + ("، ولا يُظهرها نموذجنا." if R.get("model") else "."))
    # the motion
    s = R.get("steer")
    mt = R.get("model_track")
    if s:
        if s["speed"] < 3:
            t = (f"والرياح الموجهة للسحب (بين ٧٠٠ و٥٠٠ هكتوباسكال) ضعيفة (نحو {ar(round(s['speed']))} م/ث)، فتبقى الخلايا شبه ثابتة، "
                 "ويحدد هواؤها البارد المنحدر مع الأودية أين تنشأ الخلايا الجديدة، ومنها نحو السهل")
        else:
            t = f"والرياح الموجهة للسحب (بين ٧٠٠ و٥٠٠ هكتوباسكال) تدفع الخلايا نحو {s['to']} بنحو {ar(round(s['speed']))} م/ث"
        if mt and mt != s["to"]:
            t += f"، ومسار الخلايا في نموذجنا نحو {mt}"
        elif mt:
            t += "، ويوافقها مسار الخلايا في نموذجنا"
        out.append(t + ".")
    ev = R.get("evening")
    if ev:
        out.append(f"ومن {clock(ev['from'])} تتجه الخلايا المسائية إلى {jl(ev['places'])}"
                   + (f" حتى {clock(ev['to'])}" if ev["to"] > ev["from"] else "") + ".")
    # who gets rain
    rn = R.get("rain") or []
    if rn:
        out.append("وأغزر المطر في نموذجنا: " + "، و".join(f"{SHORT.get(x['k'], x['name'])} (نحو {ar(round(x['max']))} ملم)" for x in rn[:5]) + ".")
    c = R.get("city") or {}
    if c:
        mkj = [c.get("makkah"), c.get("jumum")]
        if all(x == "unlikely" for x in mkj):
            why = []
            if s and s["u"] > -1:
                why.append(f"لأن الخلايا تتحرك نحو {s['to']} مبتعدة عن السهل")
            if R.get("model"):
                why.append("ونموذجنا لا يضع عليهما مطرًا")
            out.append("أما مكة والجموم ففرص المطر عليهما ضعيفة" + (("، " + "، ".join(why)) if why else "") + ".")
        elif "rain" in mkj or "light" in mkj:
            where = [nm for k, nm in (("makkah", "مكة"), ("jumum", "الجموم")) if c.get(k) in ("rain", "light")]
            out.append(f"ويصل المطر إلى {jl(where)} في نموذجنا مساءً.")
        elif "possible" in mkj:
            why = ("لأن الرياح الموجهة ضعيفة فينحدر هواء الخلايا البارد مع الأودية نحو السهل" if s and s["speed"] < 3
                   else "لأن الرياح عند ٧٠٠ هكتوباسكال شرقية تدفعها نحو السهل" if s and s["u"] > -1
                   else "لأن الرياح الموجهة تدفعها نحو السهل")
            out.append(f"وقد تنحدر خلايا الحافة غربًا إلى الشرائع وشرق مكة مساءً، {why}.")
    # aloft
    up = R.get("upper") or {}
    if up.get("fall") is not None and up["fall"] <= -10 and not (R.get("trough") and (R.get("east_meet") or R.get("moved"))):
        out.append(f"ويدعم ذلك من الأعلى هبوط سطح ٥٠٠ هكتوباسكال نحو {ar(abs(round(up['fall'])))} مترًا خلال يوم"
                   + (f" وبرودته إلى ‎−{ar(abs(round(up['t500'])))}°" if up.get("t500") is not None and up["t500"] <= -7 else "")
                   + "، فتقوى الخلايا.")
    return out


def edge_model_rain(st):
    """{edge key: mm} from the reading's zones, or {} without our run"""
    zs = (st.get("mstory") or {}).get("zones") or {}
    out = {}
    for k, zz in EDGE_ZONES.items():
        v = [zs[z]["max"] for z in zz if z in zs]
        if v:
            out[k] = max(v)
    return out


def summary_line(R):
    """the Makkah line of the summary (section 1)"""
    rn = [SHORT.get(x["k"], x["name"]) for x in (R.get("rain") or [])[:4]]
    t = ""
    if rn:
        t = f"أمطار رعدية بعد الظهر على {jl(rn)}"
    elif R.get("named"):
        return None
    ev = R.get("evening")
    if ev and ev["places"]:
        t += f"، وتتجه مساءً إلى {jl(ev['places'][:3])}"
    c = R.get("city") or {}
    if c and all(c.get(k) == "unlikely" for k in ("makkah", "jumum")):
        t += "؛ وفرصها ضعيفة على مكة والجموم"
    return (t + ".") if t else None


def audit(blocks, R):
    """the last check before the Makkah section is published: a sentence that says the opposite of the reading is
    dropped, and the drop is printed in the run's log (18 Nov 2026)"""
    rules = []
    c = R.get("city") or {}
    if c.get("jumum") == "unlikely":
        rules.append(("تصل إلى الجموم", "Al-Jumum unlikely in the reading"))
    if c.get("makkah") == "unlikely" and c.get("jumum") == "unlikely":
        rules.append(("أمطار على مكة والجموم", "Makkah unlikely in the reading"))
    if (R.get("meet") or ("",))[0] != "east":
        rules += [("فالفرص هناك أكبر منها على الحافة", "collision not shifted"), ("بعيدًا عن حافة الهدا", "collision not shifted")]
    zs = {x["k"]: x["max"] for x in R.get("rain") or []}
    if R.get("model") and any(zs.get(k, 0) >= 5 for k in ("taif", "hawiyah", "sail", "hada", "shafa")):
        rules.append(("لا تُظهر مخرجات نموذجنا أمطارًا تُذكر على الطائف", "model has rain on the heights"))
    out = []
    for b in blocks:
        txt = b.get("p") or ""
        bad = next((why for ph, why in rules if ph in txt), None)
        if bad:
            print("makkah_story.audit: dropped a sentence (" + bad + "):", txt[:120], flush=True)
            continue
        out.append(b)
    return out
