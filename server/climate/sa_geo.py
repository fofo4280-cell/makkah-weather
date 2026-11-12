"""The Kingdom's thirteen regions, a gazetteer of towns and Open-Meteo access for the daily report.

Region outlines: Natural Earth 10 m admin-1 (public domain), simplified to 0.01 degree (sa_regions.json).
"""
import json, math, os, re, time, urllib.parse, urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "saudi-wrf-climate/1.0"

# towns used to say where something happens ("near X"); name, lat, lon
PLACES = [
    ("الرياض", 24.71, 46.68), ("الخرج", 24.15, 47.31), ("الدوادمي", 24.51, 44.39), ("المجمعة", 25.90, 45.34),
    ("الزلفي", 26.30, 44.80), ("شقراء", 25.25, 45.25), ("عفيف", 23.91, 42.92), ("القويعية", 24.07, 45.28),
    ("وادي الدواسر", 20.47, 44.78), ("السليل", 20.46, 45.58), ("الأفلاج", 22.29, 46.73), ("حوطة بني تميم", 23.52, 46.84),
    ("مكة المكرمة", 21.42, 39.83), ("جدة", 21.54, 39.17), ("الطائف", 21.27, 40.42), ("الجموم", 21.62, 39.70),
    ("رابغ", 22.80, 39.03), ("خليص", 22.15, 39.33), ("الكامل", 22.22, 39.65), ("الليث", 20.15, 40.27),
    ("القنفذة", 19.13, 41.08), ("أضم", 20.48, 40.62), ("ميسان", 20.73, 40.87), ("رنية", 21.26, 42.84),
    ("تربة", 21.21, 41.63), ("الخرمة", 21.92, 42.05), ("المويه", 22.43, 41.76), ("ظلم", 22.71, 42.18),
    ("الشفا", 21.07, 40.35), ("الهدا", 21.37, 40.29), ("العرضيات", 19.76, 41.48), ("بحرة", 21.40, 39.45),
    ("المدينة المنورة", 24.47, 39.61), ("ينبع", 24.09, 38.06), ("العلا", 26.61, 37.92), ("بدر", 23.78, 38.79),
    ("مهد الذهب", 23.50, 40.86), ("الحناكية", 24.88, 40.53), ("خيبر", 25.70, 39.29), ("العيص", 25.06, 38.11),
    ("بريدة", 26.33, 43.97), ("عنيزة", 26.08, 43.99), ("الرس", 25.87, 43.50), ("البكيرية", 26.14, 43.66),
    ("المذنب", 25.86, 44.22), ("البدائع", 25.98, 43.73),
    ("الدمام", 26.43, 50.10), ("الظهران", 26.29, 50.11), ("الخبر", 26.28, 50.21), ("الجبيل", 27.01, 49.66),
    ("القطيف", 26.56, 50.01), ("الأحساء", 25.38, 49.59), ("حفر الباطن", 28.43, 45.96), ("الخفجي", 28.43, 48.49),
    ("النعيرية", 27.47, 48.49), ("قرية العليا", 27.55, 47.70), ("بقيق", 25.93, 49.67), ("يبرين", 23.31, 48.95),
    ("أبها", 18.22, 42.50), ("خميس مشيط", 18.31, 42.73), ("بيشة", 19.99, 42.60), ("محايل عسير", 18.54, 42.05),
    ("النماص", 19.12, 42.13), ("تنومة", 18.94, 42.17), ("سراة عبيدة", 18.09, 43.13), ("ظهران الجنوب", 17.66, 43.51),
    ("رجال ألمع", 18.20, 42.27), ("تثليث", 19.53, 43.51), ("بلقرن", 19.70, 42.00), ("المجاردة", 19.12, 41.92),
    ("أحد رفيدة", 18.20, 42.85), ("الحرجة", 17.93, 43.36),
    ("تبوك", 28.38, 36.57), ("الوجه", 26.24, 36.45), ("ضباء", 27.35, 35.69), ("أملج", 25.02, 37.27),
    ("تيماء", 27.63, 38.55), ("حقل", 29.29, 34.94), ("البدع", 28.48, 35.00), ("شرما", 28.03, 35.25),
    ("حائل", 27.52, 41.70), ("بقعاء", 27.89, 42.40), ("الغزالة", 26.79, 41.31), ("الشنان", 27.18, 42.44),
    ("الحائط", 25.99, 40.47), ("موقق", 27.38, 41.17),
    ("عرعر", 30.98, 41.04), ("رفحاء", 29.63, 43.50), ("طريف", 31.67, 38.66), ("العويقيلة", 30.33, 42.26),
    ("جازان", 16.89, 42.55), ("صبيا", 17.15, 42.63), ("أبو عريش", 16.97, 42.83), ("صامطة", 16.60, 42.94),
    ("فيفاء", 17.25, 43.10), ("الداير", 17.35, 43.14), ("العارضة", 17.04, 43.06), ("بيش", 17.39, 42.60),
    ("الدرب", 17.72, 42.25), ("فرسان", 16.70, 42.12),
    ("نجران", 17.49, 44.13), ("شرورة", 17.47, 47.11), ("حبونا", 17.83, 44.08), ("بدر الجنوب", 17.88, 43.85),
    ("يدمة", 18.38, 44.08), ("الخرخير", 18.88, 51.12),
    ("الباحة", 20.01, 41.47), ("المخواة", 19.78, 41.44), ("بلجرشي", 19.86, 41.56), ("المندق", 20.15, 41.29),
    ("قلوة", 19.95, 41.27), ("العقيق", 20.27, 41.65),
    ("سكاكا", 29.97, 40.21), ("القريات", 31.33, 37.34), ("دومة الجندل", 29.81, 39.87), ("طبرجل", 30.50, 38.22),
    ("الشويحطية", 30.08, 39.03),
    # more governorates and towns, so the rain report can name the places in each region
    ("الدرعية", 24.74, 46.57), ("المزاحمية", 24.47, 46.27), ("ضرما", 24.60, 46.13), ("الحريق", 23.62, 46.52),
    ("الغاط", 26.03, 44.96), ("رماح", 25.57, 47.16), ("ثادق", 25.29, 45.87), ("حريملاء", 25.13, 46.12),
    ("مرات", 25.07, 45.46), ("الدلم", 23.99, 47.16), ("ساجر", 25.18, 44.60), ("الرين", 23.55, 45.53),
    ("عيون الجواء", 26.51, 43.68), ("رياض الخبراء", 26.06, 43.56), ("الأسياح", 26.80, 44.23), ("النبهانية", 25.88, 42.71),
    ("الشماسية", 26.44, 44.29), ("عقلة الصقور", 25.84, 42.18), ("ضرية", 24.35, 43.32),
    ("الشملي", 26.67, 40.90), ("السليمي", 26.27, 41.31), ("سميراء", 26.52, 42.12), ("الحليفة", 26.63, 40.27),
    ("رأس تنورة", 26.64, 50.16), ("العديد", 24.60, 51.30), ("سلوى", 24.73, 50.81), ("الجشة", 25.37, 49.67),
    ("المهد", 23.50, 40.86), ("وادي الفرع", 23.93, 39.73), ("الحسو", 24.18, 40.62), ("الصويدرة", 24.70, 40.07),
    ("البريكة", 22.10, 40.97), ("ثقيف", 21.30, 40.68), ("السيل الكبير", 21.62, 40.43), ("مدركة", 22.08, 39.83),
    ("عسفان", 21.89, 39.35), ("ثول", 22.28, 39.10), ("الخبت", 21.50, 39.40), ("الشرائع", 21.48, 39.98),
    ("بني مالك", 20.62, 40.92), ("حداء", 21.29, 39.62), ("الحوية", 21.44, 40.50),
    ("البرك", 18.21, 41.54), ("بارق", 18.93, 41.92), ("طريب", 19.59, 44.57), ("الأمواه", 19.43, 42.93),
    ("السودة", 18.27, 42.37), ("الفرعاء", 18.42, 42.89), ("خميس البحر", 17.96, 42.06),
    ("ضمد", 17.11, 42.77), ("الريث", 17.58, 42.98), ("هروب", 17.47, 43.13), ("العيدابي", 17.24, 42.96),
    ("الطوال", 16.52, 42.98), ("أحد المسارحة", 16.71, 42.95), ("الحرث", 17.02, 43.20),
    ("غامد الزناد", 19.80, 41.95), ("بني حسن", 20.07, 41.52), ("القرى", 19.96, 41.60), ("الحجرة", 19.47, 41.69),
    ("ثار", 17.81, 44.43), ("خباش", 17.97, 45.55), ("الوديعة", 17.06, 47.12),
    ("حالة عمار", 29.13, 36.07),
    ("لينة", 28.76, 43.77),
]

# two or three towns per region whose daily normals (ERA5) are kept for the heat and cold checks
NORMAL_TOWNS = {
    "SA-01": ["الرياض", "الدوادمي", "وادي الدواسر"], "SA-02": ["مكة المكرمة", "جدة", "الطائف"],
    "SA-03": ["المدينة المنورة", "ينبع", "العلا"], "SA-04": ["الدمام", "الأحساء", "حفر الباطن"],
    "SA-05": ["بريدة", "الرس"], "SA-06": ["حائل", "الحائط"], "SA-07": ["تبوك", "الوجه"],
    "SA-08": ["عرعر", "رفحاء", "طريف"], "SA-09": ["جازان", "فيفاء"], "SA-10": ["نجران", "شرورة"],
    "SA-11": ["الباحة", "المخواة"], "SA-12": ["سكاكا", "القريات"], "SA-14": ["أبها", "بيشة", "محايل عسير"],
}
PLACE = {n: (la, lo) for n, la, lo in PLACES}


def regions():
    """[{id, name, area_km2, geom (shapely)}] in a fixed order: largest first."""
    from shapely.geometry import shape
    out = json.load(open(os.path.join(HERE, "sa_regions.json")))
    for r in out:
        r["geom"] = shape(r.pop("geometry"))
    return sorted(out, key=lambda r: -r["area_km2"])


def region_of_points(regs, lat, lon, towns_too=False):
    """Region index (or -1) of each point, for flat arrays of lat and lon."""
    from shapely import contains_xy
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    idx = np.full(lat.shape, -1, int)
    for k, r in enumerate(regs):
        m = contains_xy(r["geom"], lon, lat) & (idx < 0)
        idx[m] = k
    if towns_too and (idx < 0).any():   # coastal towns just outside the simplified outline
        for k, r in enumerate(regs):
            if "_buf" not in r:
                r["_buf"] = r["geom"].buffer(0.12)
            m = contains_xy(r["_buf"], lon, lat) & (idx < 0)
            idx[m] = k
    return idx


def grid_points(regs, step=0.5):
    """Points of a regular grid inside the Kingdom, plus every town, so that small regions are not empty.
    Returns lat, lon, region index, and the town name (or '') of each point."""
    la, lo = np.meshgrid(np.arange(16.25, 32.3, step), np.arange(34.75, 55.8, step), indexing="ij")
    la, lo = la.ravel(), lo.ravel()
    ri = region_of_points(regs, la, lo)
    keep = ri >= 0
    tl = np.array([p[1] for p in PLACES]); tn = np.array([p[2] for p in PLACES])
    lat = np.concatenate([la[keep], tl]); lon = np.concatenate([lo[keep], tn])
    names = [""] * int(keep.sum()) + [p[0] for p in PLACES]
    return lat, lon, region_of_points(regs, lat, lon, True), names


def nearest_place(lat, lon, region=None):
    """Name of the nearest town (in the same region when one is given), and the distance in km."""
    best, bd = None, 1e9
    for n, la, lo in PLACES:
        if region is not None and region.get("_towns") is not None and n not in region["_towns"]:
            continue
        d = 111.2 * np.hypot(la - lat, (lo - lon) * np.cos(np.radians(lat)))
        if d < bd:
            best, bd = n, d
    return best, bd


def tag_towns(regs):
    """Store in each region the set of gazetteer towns inside it."""
    idx = region_of_points(regs, [p[1] for p in PLACES], [p[2] for p in PLACES], True)
    for k, r in enumerate(regs):
        r["_towns"] = {PLACES[i][0] for i in range(len(PLACES)) if idx[i] == k}
    return regs


# ------------------------------------------------------------------ Open-Meteo (free, no key)
# The free tier counts one call per location, more with over ten variables or two weeks of data;
# stay under 600 per minute and 10 000 per day.
class OpenMeteo:
    PER_MIN = 400

    def __init__(self):
        self.spent = []
        self.used = 0

    def _budget(self, w):
        while True:
            now = time.time()
            self.spent = [s for s in self.spent if now - s[0] < 61]
            if not self.spent or sum(s[1] for s in self.spent) + w <= self.PER_MIN:
                self.spent.append((now, w)); self.used += w
                return
            time.sleep(61 - (now - self.spent[0][0]) + 0.3)

    def get(self, base, params, lat, lon, weight=1.0, chunk=100):
        """One JSON object per location, for many locations in chunks."""
        out = []
        for a in range(0, len(lat), chunk):
            la, lo = lat[a:a + chunk], lon[a:a + chunk]
            q = dict(params, latitude=",".join(f"{x:.3f}" for x in la), longitude=",".join(f"{x:.3f}" for x in lo))
            url = base + "?" + urllib.parse.urlencode(q, safe=",")
            self._budget(max(1.0, weight) * len(la))
            for k in range(4):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=180) as r:
                        j = json.loads(r.read())
                    break
                except urllib.error.HTTPError as e:
                    body = e.read()[:300]
                    if e.code == 429 and k < 3:
                        time.sleep(65); continue
                    raise RuntimeError(f"{e.code} {body}")
                except Exception:
                    if k == 3:
                        raise
                    time.sleep(10)
            out += j if isinstance(j, list) else [j]
        return out


FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
SEASONAL = "https://seasonal-api.open-meteo.com/v1/seasonal"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


# ------------------------------------------------------------------ Arabic text
AR_DIGITS = str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫")
AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def ar(x):
    t = str(x).translate(AR_DIGITS)
    return "‎−" + t[1:] if t.startswith("-") else t


def num(x, nd=0):
    """Arabic number, rounded; no trailing ٫٠."""
    v = round(float(x), nd)
    return ar(int(v) if nd == 0 or v == int(v) else v)


def ar_date(d, weekday=True):
    """d: datetime.date"""
    s = f"{ar(d.day)} {AR_MONTHS[d.month - 1]}"
    return f"{AR_DAYS[d.weekday()]} {s}" if weekday else s


def ar_span(a, b):
    """'من الخميس ١٢ إلى السبت ١٤ نوفمبر' or 'يوم الخميس ١٢ نوفمبر'."""
    if a == b:
        return f"يوم {ar_date(a)}"
    if a.month == b.month:
        return f"من {AR_DAYS[a.weekday()]} {ar(a.day)} إلى {ar_date(b)}"
    return f"من {ar_date(a)} إلى {ar_date(b)}"


def join(names):
    return " و".join(names)


def deg(x):
    """'درجة' / 'درجتين' / '٣ درجات' / '١٢ درجة' for a rounded amount of degrees."""
    n = int(round(abs(float(x))))
    return "درجة" if n == 1 else "درجتين" if n == 2 else f"{ar(n)} درجات" if 3 <= n <= 10 else f"{ar(n)} درجة"


# ------------------------------------------------------------------ exact places (OpenStreetMap gazetteer)
# sa_osm.json (built by build_places.py): villages, named roads, bridges, junctions, wadis and peaks with Arabic
# names, so the report can say where the heaviest rain is as a forecaster would: "عند كبري عشيرة على طريق حضن".
_OSM = None
SETTLE = {"city", "town", "village", "hamlet", "suburb", "quarter", "neighbourhood", "locality", "isolated_dwelling"}
DIRS = ["شمال", "شمال شرق", "شرق", "جنوب شرق", "جنوب", "جنوب غرب", "غرب", "شمال غرب"]


def _osm():
    global _OSM
    if _OSM is None:
        p = os.path.join(HERE, "sa_osm.json")
        if not os.path.exists(p):
            _OSM = {}
            return _OSM
        d = json.load(open(p))
        pl = d["places"]
        o = {"pn": [x[0] for x in pl], "plat": np.array([x[1] for x in pl]), "plon": np.array([x[2] for x in pl]),
             "pk": np.array([x[3] for x in pl])}
        ln, lk, la, lo = [], [], [], []
        for name, kind, pts in d["lines"]:
            for a, b in pts:
                ln.append(name); lk.append(kind); la.append(a); lo.append(b)
        o.update({"ln": ln, "lk": np.array(lk), "llat": np.array(la), "llon": np.array(lo)})
        _OSM = o
    return _OSM


def _km(lat, lon, la, lo):
    return 111.2 * np.hypot(la - lat, (lo - lon) * math.cos(math.radians(lat)))


def direction(lat0, lon0, lat, lon):
    """Arabic compass word for the bearing from (lat0, lon0) to (lat, lon)."""
    b = math.degrees(math.atan2((lon - lon0) * math.cos(math.radians(lat0)), lat - lat0)) % 360
    return DIRS[int((b + 22.5) // 45) % 8]


def _num(x):
    return str(int(round(x))).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def _road(name):
    return name if re.match(r"^(طريق|شارع|الطريق|دائري|الدائري|كوبري|جسر)", name) else "طريق " + name


def describe(lat, lon, region=None):
    """Where a point is, as precisely as the map allows, e.g.
    'عند كبري عشيرة على طريق حضن، ٣٢ كم شمال شرق الطائف' or 'قرب قرية الفيصلية في وادي قنونا، ١٤ كم شرق المظيلف'.
    Falls back to the nearest town of the coarse list when the fine gazetteer is missing."""
    town, td = nearest_place(lat, lon, region)
    o = _osm()
    if not o:
        return f"قرب {town}" if town else ""
    parts = []
    # a bridge or a junction within 2 km is the most exact landmark
    dp = _km(lat, lon, o["plat"], o["plon"])
    lm = np.where(np.isin(o["pk"], ["bridge", "junction"]) & (dp <= 2.0))[0]
    if lm.size:
        k = lm[np.argmin(dp[lm])]
        parts.append(f"عند {o['pn'][k]}")
    # the nearest settlement (village, hamlet or district)
    st = np.where(np.isin(o["pk"], list(SETTLE)) & (dp <= 8.0))[0]
    settle = None
    if st.size:
        k = st[np.argmin(dp[st])]
        settle = o["pn"][k]
        if not parts:
            parts.append(("في " if dp[k] <= 1.5 else "قرب ") + settle)
    # the road or the wadi it is on
    if o["llat"].size:
        dl = _km(lat, lon, o["llat"], o["llon"])
        rd = np.where((o["lk"] != "wadi") & (o["lk"] != "line") & (dl <= 2.0))[0]
        wd = np.where((o["lk"] == "wadi") & (dl <= 1.5))[0]
        if rd.size:
            k = rd[np.argmin(dl[rd])]
            parts.append(f"على {_road(o['ln'][k])}")
        elif wd.size:
            k = wd[np.argmin(dl[wd])]
            w = o["ln"][k]
            parts.append(("في " if w.startswith("وادي") else "في وادي ") + w)
    if not parts:   # open country: the nearest peak, or just the town
        pk = np.where((o["pk"] == "peak") & (dp <= 4.0))[0]
        if pk.size:
            parts.append(f"قرب {o['pn'][pk[np.argmin(dp[pk])]]}")
    txt = " ".join(parts)
    # the governorate town for orientation, unless the point is in it
    if town and (td > 4 or not txt):
        tl, to = PLACE[town]
        where = f"{_num(td)} كم {direction(tl, to, lat, lon)} {town}" if td > 4 else town
        txt = f"{txt}، {where}" if txt and town not in txt else (txt or f"قرب {where}")
    return txt.strip("، ")
