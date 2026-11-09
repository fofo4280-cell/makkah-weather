"""The Kingdom's thirteen regions, a gazetteer of towns and Open-Meteo access for the daily report.

Region outlines: Natural Earth 10 m admin-1 (public domain), simplified to 0.01 degree (sa_regions.json).
"""
import json, os, time, urllib.parse, urllib.request

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
