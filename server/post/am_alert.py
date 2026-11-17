#!/usr/bin/env python3
"""Afternoon rain alert from the morning run (Fahad, 17 Nov 2026).

am_alert.py <model-data-am checkout> <cycle YYYYMMDD00>

Reads the run's manifest and points.bin (hourly rain and radar echo on the 3 km grid, one byte per value),
sums the rain from 10 AM to 9 PM Makkah in each zone (the edges, the harrat, Makkah, Al-Jumum, Jeddah...)
and writes alert.json: the numbers and a short Arabic text (Arabic-Indic digits, no Latin letters) that
Claude posts to Fahad every morning, also when nothing is expected. Not read by the reports.
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

import numpy as np
from pyproj import Proj

MAKKAH = timezone(timedelta(hours=3))
H0, H1 = 7, 18          # forecast hours (00 UTC run): rain of the hours ending 10 AM .. 9 PM Makkah
MEANINGFUL = 2.0        # mm: a zone is named from this zone maximum
# zones: key, name, south, north, west, east
ZONES = [
    ("hada", "حافة الهدا والشفا", 20.85, 21.60, 40.15, 40.45),
    ("rahjan", "رهجان والشرائع وشرق مكة", 21.25, 21.55, 39.92, 40.15),
    ("makkah", "مكة المكرمة", 21.30, 21.52, 39.72, 39.92),
    ("jumum", "الجموم ووادي فاطمة", 21.53, 21.80, 39.55, 39.90),
    ("south", "جنوب مكة حتى يلملم", 20.00, 21.28, 39.50, 40.15),
    ("taif", "الطائف ومحيطه", 20.70, 21.80, 40.45, 41.30),
    ("rahat", "حرة رهاط", 22.20, 23.60, 39.75, 40.60),
    ("usfan", "عسفان وخليص", 21.80, 22.45, 39.10, 39.65),
    ("jeddah", "جدة", 21.20, 21.85, 39.08, 39.32),
]
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def ar(x):
    return str(x).translate(str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫"))


def mm(v):
    return ar(int(round(v))) if v >= 3 else ar(f"{v:.1f}".rstrip("0").rstrip("."))


def clock(h):
    """Makkah hour (0-23) -> '١ ظهرًا'."""
    t = h % 12 or 12
    part = "صباحًا" if h < 12 else "ظهرًا" if h < 15 else "عصرًا" if h < 18 else "مساءً"
    return f"{ar(t)} {part}"


def grade(v):
    if v >= 20:
        return "أمطار غزيرة"
    if v >= 8:
        return "أمطار متوسطة"
    if v >= MEANINGFUL:
        return "أمطار خفيفة"
    return None


def decode(var, b):
    b = b.astype(np.float32)
    return (b / 25.0) ** 2 if var == "rain1h" else b / 3.0   # see products.encode_point


def main():
    root, cyc = sys.argv[1], sys.argv[2]
    init = datetime.strptime(cyc, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    day = (init + timedelta(hours=12)).astimezone(MAKKAH)
    dayname = f"{DAYS[day.weekday()]} {ar(day.day)} {MONTHS[day.month - 1]}"
    out = {"run": cyc, "made": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "day": day.strftime("%Y-%m-%d"),
           "window": [H0, H1], "zones": []}
    mp = os.path.join(root, "runs", cyc, "manifest.json")
    if not os.path.exists(mp):
        out["status"] = "missing"
        out["text"] = f"التشغيل الصباحي ليوم {dayname} لم يُنشر، فلا تنبيه اليوم."
        json.dump(out, open(os.path.join(root, "alert.json"), "w"), ensure_ascii=False, indent=1)
        return
    man = json.load(open(mp))
    d = man["domains"].get("d02")
    out["status"] = man.get("status")
    if not d or not d.get("points"):
        out["status"] = "failed"
        out["text"] = f"التشغيل الصباحي ليوم {dayname} لم ينتج خرائط الدقة ٣ كم، فلا تنبيه اليوم."
        json.dump(out, open(os.path.join(root, "alert.json"), "w"), ensure_ascii=False, indent=1)
        return
    P = d["points"]
    hours = P["hours"]
    nv, nh, ny, nx = len(P["vars"]), len(hours), P["ny"], P["nx"]
    arr = np.fromfile(os.path.join(root, "runs", cyc, P["file"]), dtype=np.uint8).reshape(nv, nh, ny, nx)
    rain = decode("rain1h", arr[P["vars"].index("rain1h")])
    refl = decode("refl", arr[P["vars"].index("refl")])
    pr = man["proj"]
    proj = Proj(proj="lcc", lat_1=pr["truelat1"], lat_2=pr["truelat2"], lon_0=pr["stand_lon"], lat_0=pr["ref_lat"], R=pr.get("R", 6370000))
    jj, ii = np.mgrid[0:ny, 0:nx]
    lon, lat = proj(P["x00"] + ii * P["dx"], P["y00"] + jj * P["dx"], inverse=True)
    sel = [k for k, h in enumerate(hours) if H0 <= h <= H1]
    last = max(hours)
    tot = rain[sel].sum(axis=0) if sel else np.zeros((ny, nx), np.float32)
    named, dry = [], []
    for key, name, s, n, w, e in ZONES:
        m = (lat >= s) & (lat <= n) & (lon >= w) & (lon <= e)
        m[:3, :] = m[-3:, :] = m[:, :3] = m[:, -3:] = False   # the grid's edge rows
        if not m.any():
            continue
        z = {"key": key, "name": name, "max": round(float(tot[m].max()), 1),
             "wide": round(float((tot[m] >= MEANINGFUL).mean() * 100), 1),
             "dbz": round(float(refl[sel][:, m].max()), 0) if sel else 0}
        hr = [(hours[k], float(rain[k][m].max()), float(rain[k][m].sum())) for k in sel]
        first = next((h for h, mx, _ in hr if mx >= 1.0), None)
        peak = max(hr, key=lambda x: x[2])[0] if hr and max(x[2] for x in hr) > 0 else None
        z["start"] = None if first is None else (first + 3) % 24 - 1   # hour ending h UTC -> the hour it starts, Makkah
        z["peak"] = None if peak is None else (peak + 3) % 24 - 1
        z["grade"] = grade(z["max"])
        out["zones"].append(z)
        if z["grade"]:
            t = f"• {name}: {z['grade']}، أعلى مجموع {mm(z['max'])} ملم"
            if z["wide"] >= 15:
                t += f" ويعم نحو {ar(int(round(z['wide'])))}٪ منها"
            if z["start"] is not None:
                t += f"، تبدأ قرابة {clock(z['start'])}"
                if z["peak"] is not None and z["peak"] != z["start"]:
                    t += f" وذروتها قرابة {clock(z['peak'])}"
            if z["dbz"] >= 45:
                t += f"، وصدى الرادار حتى {ar(int(z['dbz']))} ديسيبل (عواصف رعدية)"
            named.append(t + ".")
        else:
            dry.append(name)
    head = f"تنبيه التشغيل الصباحي (الأمريكي، دقة ٣ كم) لظهر وعصر {dayname}، من ١٠ صباحًا حتى ٩ مساءً بتوقيت مكة:"
    if named:
        lines = [head] + named
        if dry:
            lines.append("• بلا أمطار تُذكر: " + "، ".join(dry) + ".")
    else:
        lines = [head, "لا يُظهر التشغيل أمطارًا تُذكر على الحواف والحرات ومكة والجموم وجدة والطائف."]
    if man.get("status") != "complete" or last < H1:
        lines.append(f"تنبيه: التشغيل لم يكتمل، والأرقام حتى الساعة {clock((last + 3) % 24)} فقط.")
    out["named"] = len(named)
    out["text"] = "\n".join(lines)
    json.dump(out, open(os.path.join(root, "alert.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
