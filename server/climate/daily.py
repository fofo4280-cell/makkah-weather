#!/usr/bin/env python3
"""Daily MJO / warm-cold event / moisture-surge products for the website.

daily.py <clim_dir> <state_dir> <out_dir>

Data:
  - RMM index (Wheeler and Hendon) from the Australian Bureau of Meteorology, observed.
  - GFS 1 degree analyses (00 UTC, last ~125 days) and the latest forecast to 15 days, from the NOAA archive
    on AWS: 200 hPa wind and precipitable water.
  - NCEP/NCAR reanalysis climatology (build_clim.py).

Warm/cold event index: minus the 200 hPa velocity potential anomaly (10^6 m^2/s), after removing the
climatology and the mean of the previous 120 days (as done for RMM). Positive (warm event) = upper-level
outflow over deep convection; negative (cold event) = convergence aloft, suppressed convection.
RMM forecast: the observed RMM is regressed on the zonal wave-1 of the equatorial index over the last
90 days, the fit is applied to the GFS forecast and anchored to the latest observation.
"""
import json, math, os, re, sys, urllib.request
from datetime import date, datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sphere  # noqa: E402
import figures
import ar as rivers  # noqa: E402
import waves  # noqa: E402
import sa_geo  # noqa: E402
import outlook as long_range  # noqa: E402,F401
import troughs  # noqa: E402
import coldwave  # noqa: E402
import rainreport  # noqa: E402
import bigreport  # noqa: E402
import mjofilt  # noqa: E402
import wkfilt  # noqa: E402
import ingredients as ING  # noqa: E402
import diag  # noqa: E402
import collide  # noqa: E402
import pattern  # noqa: E402

AWS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
CPC = "https://ftp.cpc.ncep.noaa.gov/cwlinks/"
RMM_URL = "https://www.bom.gov.au/clim_data/IDCKGEM000/rmm.74toRealtime.txt"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
HIST_DAYS = 400       # more than a year: the Rossby family (periods to 90 days) needs a long series (wkfilt)
MEAN_DAYS = 120
FC_DAYS = 15
LAT1 = np.linspace(90, -90, 181)
LON1 = np.arange(0, 360, 1.0)

# Saudi regions for the moisture check: south, north, west, east
BOXES = {
    "west": ("الحجاز وغرب المملكة", 19, 26, 38, 43),
    "southwest": ("جنوب غرب المملكة", 16, 20, 41, 45),
    "central": ("وسط المملكة", 22, 27, 43, 48),
    "east": ("شرق المملكة", 23, 28, 48, 51),
    "north": ("شمال المملكة", 27, 32, 37, 44),
}
# Wheeler-Hendon phases: where the enhanced convection is
PHASE_AREA = {1: "غرب نصف الكرة الغربي وأفريقيا", 2: "غرب المحيط الهندي", 3: "شرق المحيط الهندي",
              4: "القارة البحرية (إندونيسيا)", 5: "القارة البحرية (إندونيسيا)", 6: "غرب المحيط الهادئ",
              7: "غرب المحيط الهادئ", 8: "نصف الكرة الغربي وأفريقيا"}
WET_PHASES = {1, 2, 7, 8}      # Nov-Apr, Saudi Arabia (Alsaqr et al. / UEA study, 26 stations 1985-2021)
DRY_PHASES = {3, 4, 5, 6}


def region_name(lon):
    lon = lon % 360
    for a, b, n in [(0, 15, "غرب أفريقيا والأطلسي"), (15, 45, "شرق أفريقيا"), (45, 75, "غرب المحيط الهندي وبحر العرب"),
                    (75, 100, "وسط وشرق المحيط الهندي"), (100, 145, "القارة البحرية (إندونيسيا)"),
                    (145, 180, "غرب المحيط الهادئ"), (180, 240, "وسط المحيط الهادئ"), (240, 290, "شرق المحيط الهادئ"),
                    (290, 360, "الأمريكتان والأطلسي")]:
        if a <= lon < b:
            return n
    return ""


def get(url, headers=None, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            if k == tries - 1:
                raise
            print(f"retry {url}: {e}", flush=True)
    return None


# ------------------------------------------------------------------ GFS
FIELDS = [("u", r":UGRD:200 mb:"), ("v", r":VGRD:200 mb:"), ("pw", r":PWAT:entire atmosphere \(considered as a single layer\):")]


Z500 = ("z500", r":HGT:500 mb:")
T500 = ("t500", r":TMP:500 mb:")
WAVE_DAYS = 15


def gfs_fields(cycle, fh, extra=(), res="1p00", fields=None):
    """Fields from one GFS file by byte ranges, on its grid (lat 90..-90, lon 0..): u200, v200, pw by default."""
    import pygrib
    d, hh = cycle[:8], cycle[8:10]
    base = f"{AWS}/gfs.{d}/{hh}/atmos/gfs.t{hh}z.pgrb2.{res}.f{fh:03d}"
    idx = get(base + ".idx").decode().splitlines()
    starts = [int(l.split(":")[1]) for l in idx]
    out = {}
    for name, pat in list(FIELDS if fields is None else fields) + list(extra):
        k = next(i for i, l in enumerate(idx) if re.search(pat, l))
        end = starts[k + 1] - 1 if k + 1 < len(starts) else ""
        blob = get(base, {"Range": f"bytes={starts[k]}-{end}"})
        tmp = f"/tmp/gfs_{os.getpid()}.grb"
        open(tmp, "wb").write(blob)
        with pygrib.open(tmp) as g:
            m = g.message(1)
            a = np.ma.filled(np.ma.asarray(m.values, dtype=np.float32), np.nan)
            a[np.abs(a) > 1e6] = np.nan
            la = m.latlons()[0][:, 0]
        if la[0] < la[-1]:
            a = a[::-1]
        if not np.isfinite(a).all():
            raise ValueError(f"{name}: {int((~np.isfinite(a)).sum())} missing values")
        out[name] = a
    return out


def latest_cycle():
    now = datetime.now(timezone.utc)
    for k in range(0, 4):  # newest 00 or 12 UTC run that reaches 15 days
        d = (now - timedelta(days=k)).strftime("%Y%m%d")
        for hh in ("12", "00"):
            try:
                get(f"{AWS}/gfs.{d}/{hh}/atmos/gfs.t{hh}z.pgrb2.1p00.f{FC_DAYS * 24:03d}.idx")
                return d + hh
            except Exception:
                continue
    raise RuntimeError("no GFS forecast found")


# ------------------------------------------------------------------ helpers
def doy(dt):
    """0..364, 29 February counted as 28 February."""
    d = dt.timetuple().tm_yday - 1
    if dt.month > 2 and (dt.year % 4 == 0 and (dt.year % 100 != 0 or dt.year % 400 == 0)):
        d -= 1
    return min(max(d, 0), 364)


def clim_chi_1deg(clim, dt):
    """Climatological chi for a date, interpolated from 2.5 to 1 degree."""
    from scipy.ndimage import map_coordinates
    c = clim["chi"][doy(dt)]
    jj = (90 - LAT1) / 2.5
    ii = LON1 / 2.5
    J, I = np.meshgrid(jj, ii, indexing="ij")
    return map_coordinates(np.hstack([c, c[:, :1]]), [J, I], order=1, mode="nearest")


def box_mean(field, lat, lon, s, n, w, e):
    j = (lat >= s) & (lat <= n)
    i = (lon >= w) & (lon <= e)
    return float(np.mean(field[np.ix_(j, i)]))


def rmm_phase(r1, r2):
    a = math.degrees(math.atan2(r2, r1))
    return int(((a + 180) // 45) % 8) + 1


def read_rmm():
    txt = get(RMM_URL).decode("latin-1").splitlines()
    out = []
    for l in txt:
        p = l.split()
        if len(p) >= 7 and p[0].isdigit() and len(p[0]) == 4:
            try:
                r1, r2, amp = float(p[3]), float(p[4]), float(p[6])
            except ValueError:
                continue
            if not all(math.isfinite(x) for x in (r1, r2, amp)) or abs(r1) > 900 or abs(amp) > 900:
                continue
            out.append((date(int(p[0]), int(p[1]), int(p[2])), r1, r2, int(p[5]), amp))
    return out


def read_ao(t0):
    """Arctic Oscillation (CPC, 1000 hPa): observed daily values and the latest GEFS forecast (31 members)."""
    import csv, io
    obs = []
    for row in csv.DictReader(io.StringIO(get(CPC + "norm.daily.ao.cdas.z1000.19500101_current.csv").decode())):
        try:
            d = date(int(row["year"]), int(row["month"]), int(row["day"]))
            v = float(row["ao_index_cdas"])
        except (ValueError, KeyError):
            continue
        if d >= t0.date() - timedelta(days=90) and math.isfinite(v):
            obs.append({"d": d.isoformat(), "v": round(v, 2)})
    rows = list(csv.DictReader(io.StringIO(get(CPC + "norm.daily.ao.gefs.z1000.120days.csv").decode())))
    init = max(r["time"] for r in rows)
    by = {}
    for r in rows:
        if r["time"] == init:
            try:
                by.setdefault(r["valid_time"], []).append(float(r["ao_index"]))
            except ValueError:
                pass
    fc = []
    for vt in sorted(by):
        a = np.array(by[vt])
        fc.append({"d": vt, "mean": round(float(a.mean()), 2), "p10": round(float(np.percentile(a, 10)), 2),
                   "p90": round(float(np.percentile(a, 90)), 2), "n": int(a.size)})
    return {"obs": obs, "fc": fc, "init": init}


def trough_area(lat, lon):
    if lat >= 28:
        return "شرق المتوسط وسيناء" if lon < 35 else "شمال المملكة والأردن" if lon < 44 else "شمال شرق المملكة والعراق"
    if lon < 34:
        return "مصر والسودان"
    if lon < 41:
        return "البحر الأحمر وغرب المملكة"
    return "وسط المملكة"


def ao_words(v):
    if v <= -2: return "سالب قوي"
    if v <= -1: return "سالب"
    if v < -0.5: return "سالب ضعيف"
    if v < 0.5: return "قريب من الحياد"
    if v < 1: return "موجب ضعيف"
    if v < 2: return "موجب"
    return "موجب قوي"


# ------------------------------------------------------------------ images
def mercator_png(path, field, lat, lon, stops, south=-45, north=45, west=0, east=360, w=720):
    """Field on a regular lat/lon grid -> palette PNG whose rows follow Web Mercator (for a Leaflet overlay)."""
    from PIL import Image
    from scipy.ndimage import map_coordinates
    merc = lambda p: math.log(math.tan(math.pi / 4 + math.radians(p) / 2))
    ys, yn = merc(south), merc(north)
    step = math.radians(east - west) / w
    h = int(round((yn - ys) / step))
    lons = west + (np.arange(w) + 0.5) * (east - west) / w
    my = yn - (np.arange(h) + 0.5) * (yn - ys) / h
    lats = np.degrees(2 * np.arctan(np.exp(my)) - np.pi / 2)
    dlat, dlon = lat[1] - lat[0], lon[1] - lon[0]
    f = np.hstack([field, field[:, :1]]) if east - west >= 359 else field
    J, I = np.meshgrid((lats - lat[0]) / dlat, ((lons - lon[0]) % 360) / dlon, indexing="ij")
    v = map_coordinates(f, [J, I], order=1, mode="nearest")
    vals = np.array([s[0] for s in stops], float)
    cols = np.array([[int(s[1][i:i + 2], 16) for i in (1, 3, 5)] for s in stops], float)
    t = np.linspace(vals[0], vals[-1], 255)
    pal = np.stack([np.interp(t, vals, cols[:, k]) for k in range(3)], 1)
    alpha = np.interp(t, vals, [s[2] for s in stops])
    idx = 1 + np.clip(np.rint((v - vals[0]) / (vals[-1] - vals[0]) * 254), 0, 254)
    img = Image.fromarray(idx.astype(np.uint8), "P")
    img.putpalette([0, 0, 0] + [int(round(x)) for x in pal.reshape(-1)])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, transparency=bytes([0] + [int(round(a)) for a in alpha]), optimize=True)


WARM = [(-12, "#0b1440", 225), (-8, "#1d4fa8", 215), (-4, "#5f9fd0", 190), (-1.5, "#d5e4ef", 110), (0, "#f2f2f2", 60),
        (1.5, "#efd8d2", 110), (4, "#df8a6c", 190), (8, "#b5292a", 215), (12, "#4a0716", 225)]
CHANGE = [(-6, "#1f3f78", 215), (-3, "#6f9fd2", 190), (-1, "#dde8f1", 110), (0, "#f4f1ea", 60), (1, "#f5dfb5", 110),
          (3, "#ef9a4c", 190), (6, "#b8321b", 215), (9, "#5e0d10", 225)]
PWA = [(-100, "#8a5a2b", 0), (110, "#e9f6e5", 0), (125, "#bfe6b6", 150), (150, "#5cc28a", 200), (175, "#2a9fb5", 215),
       (200, "#2a63d0", 225), (250, "#5b2fa8", 235), (300, "#2b0f55", 240)]


def legend(stops, label, unit, lo, hi):
    return {"label": label, "unit": unit, "vmin": lo, "vmax": hi,
            "stops": [{"p": round((s[0] - lo) / (hi - lo), 4), "v": s[0], "c": s[1], "a": s[2]} for s in stops]}


def arrows(u, v, lat, lon, every=6, south=-40, north=40, scale=1.0, vmin=0.8):
    out = []
    for j in range(0, len(lat), every):
        if not south <= lat[j] <= north:
            continue
        for i in range(0, len(lon), every):
            a, b = float(u[j, i]) * scale, float(v[j, i]) * scale
            if math.hypot(a, b) >= vmin:
                out.append([round(float(lat[j]), 1), round(float(lon[i]), 1), round(a, 1), round(b, 1)])
    return out


# ------------------------------------------------------------------ main
def main():
    clim_dir, state, out = sys.argv[1:4]
    os.makedirs(state, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    clim = dict(np.load(os.path.join(clim_dir, "clim.npz")))
    print("climatology finite:", float(np.isfinite(clim["chi"]).mean()), float(np.nanmax(np.abs(clim["chi"]))), flush=True)
    hist_dir = os.path.join(state, "hist")
    os.makedirs(hist_dir, exist_ok=True)

    cycle = latest_cycle()
    t0 = datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    print("GFS cycle", cycle, flush=True)

    # 1. analyses of the last HIST_DAYS days (cached)
    hist = {}
    for k in range(HIST_DAYS, 0, -1):
        dt = t0 - timedelta(days=k)
        p = os.path.join(hist_dir, dt.strftime("%Y%m%d") + ".npz")
        if not os.path.exists(p):
            try:
                f = gfs_fields(dt.strftime("%Y%m%d00"), 0)
                chi = sphere.velocity_potential(f["u"], f["v"], LAT1, LON1)
                np.savez_compressed(p, chi=(chi / 1e6).astype(np.float16), pw=f["pw"].astype(np.float16))
            except Exception as e:
                print("skip", dt.date(), e, flush=True)
                continue
        z = np.load(p)
        rec = {"chi": z["chi"].astype(np.float32) * 1e6, "pw": z["pw"].astype(np.float32)}
        if not (np.isfinite(rec["chi"]).all() and np.isfinite(rec["pw"]).all()):
            print("bad cached day", dt.date(), flush=True)
            os.remove(p)
            continue
        hist[dt] = rec
    for f in os.listdir(hist_dir):  # keep the cache small
        try:
            if datetime.strptime(f[:8], "%Y%m%d").replace(tzinfo=timezone.utc) < t0 - timedelta(days=HIST_DAYS + 2):
                os.remove(os.path.join(hist_dir, f))
        except ValueError:
            pass
    print("analyses", len(hist), flush=True)

    # 2. the forecast: day 0 (analysis) to FC_DAYS
    fc = {}
    for d in range(0, FC_DAYS + 1):
        base = ((Z500, T500) if d <= WAVE_DAYS else ()) + (mjofilt.Z800,) + ((mjofilt.APCP,) if d else ())
        have = {"u", "v", "pw"} | {n for n, _ in base}
        ing = tuple(x for x in ING.FIELDS if x[0] not in have) if ING.coef() else ()
        f = gfs_fields(cycle, d * 24, base)
        if ing:   # the ingredients apart, so a failed download never stops the night's run
            for t_ in range(2):
                try:
                    f.update(gfs_fields(cycle, d * 24, fields=list(ing)))
                    break
                except Exception as e:  # noqa: BLE001
                    print("ingredients download failed", d, repr(e)[:120], flush=True)
        fc[t0 + timedelta(days=d)] = {"chi": sphere.velocity_potential(f["u"], f["v"], LAT1, LON1), "pw": f["pw"],
                                      "z500": f.get("z500"), "t500": f.get("t500"),
                                      "z800": f.get("z800"), "apcp": f.get("apcp"),
                                      "ingr": {n: ING.cut(f[n]) for n, _ in ING.FIELDS if n in f}
                                      if ing and all(n in f for n, _ in ING.FIELDS) else None}
    print("forecast days", len(fc), flush=True)

    # 3. anomalies: minus climatology, minus the mean anomaly of the previous MEAN_DAYS days
    def anom(dt, rec):
        return rec["chi"] - clim_chi_1deg(clim, dt)
    past = [anom(dt, r) for dt, r in hist.items() if dt >= t0 - timedelta(days=MEAN_DAYS)]
    bias = np.mean(past, axis=0) if past else 0.0
    print("bias finite:", float(np.isfinite(bias).mean()) if not np.isscalar(bias) else bias,
          "forecast chi finite:", float(np.isfinite(fc[t0]["chi"]).mean()), flush=True)
    series = {}
    for dt, r in sorted({**hist, **fc}.items()):
        series[dt] = sphere.smooth(-(anom(dt, r) - bias) / 1e6)   # warm event positive, 10^6 m^2/s, planetary scales

    # 4. maps for the forecast days (and the day before for the change)
    vec_all = {}
    wc_stream = {}
    days = sorted(fc)
    for k, dt in enumerate(days):
        W = series[dt]
        mercator_png(os.path.join(out, "wc", f"{k:02d}.png"), W, LAT1, LON1, WARM)
        prev = series.get(dt - timedelta(days=1))
        if prev is not None:
            mercator_png(os.path.join(out, "wcd", f"{k:02d}.png"), W - prev, LAT1, LON1, CHANGE)
        u, v = sphere.divergent_wind(-W * 1e6, LAT1)   # anomalous outflow at 200 hPa
        vec_all[k] = arrows(u, v, LAT1, LON1)
        wc_stream[k] = (u, v)          # the belt maps are drawn after the MJO component (their marker lines)
    json.dump(vec_all, open(os.path.join(out, "wc_vec.json"), "w"), separators=(",", ":"))

    # 5. Hovmoller: 15S-15N mean, 2.5 degree steps, last 60 days + forecast
    band = (LAT1 >= -15) & (LAT1 <= 15)
    hov_days = [dt for dt in sorted(series) if dt >= t0 - timedelta(days=60)]
    lon25 = np.arange(0, 360, 2.5)
    hov = []
    for dt in hov_days:
        prof = series[dt][band].mean(0)
        hov.append([round(float(x), 1) for x in np.interp(lon25, np.append(LON1, 360), np.append(prof, prof[0]))])

    # 6. RMM: observed, and a forecast through the wave-1 of the equatorial index
    rmm = read_rmm()
    rmm_by = {d: (r1, r2) for d, r1, r2, ph, amp in rmm}
    lam = np.radians(LON1)

    def wave1(dt):
        prof = series[dt][band].mean(0)
        return np.mean(prof * np.cos(lam)), np.mean(prof * np.sin(lam))
    X, Y = [], []
    for dt in sorted(series):
        if dt > t0 or dt < t0 - timedelta(days=90):
            continue
        if dt.date() in rmm_by:
            c, s = wave1(dt)
            X.append([c, s, 1.0]); Y.append(rmm_by[dt.date()])
    fit = None
    fc_rmm = []
    X, Y = np.array(X, dtype=float).reshape(-1, 3), np.array(Y, dtype=float).reshape(-1, 2)
    ok = np.isfinite(X).all(1) & np.isfinite(Y).all(1)
    X, Y = X[ok], Y[ok]
    print("rmm fit rows", len(X), flush=True)
    if len(X) >= 30:
        coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
        pred = X @ coef
        r = [float(np.corrcoef(pred[:, k], Y[:, k])[0, 1]) for k in (0, 1)]
        fit = {"days": len(X), "r1": round(r[0], 2), "r2": round(r[1], 2)}
        last_obs = max(d for d in rmm_by if d <= t0.date()) if rmm_by else None
        off = np.zeros(2)
        if last_obs:
            dt_lo = datetime(last_obs.year, last_obs.month, last_obs.day, tzinfo=timezone.utc)
            if dt_lo in series:
                c, s = wave1(dt_lo)
                off = np.array(rmm_by[last_obs]) - np.array([c, s, 1.0]) @ coef
        for dt in days:
            c, s = wave1(dt)
            lead = (dt.date() - (last_obs or t0.date())).days
            if lead <= 0:
                continue
            p = np.array([c, s, 1.0]) @ coef + off * math.exp(-lead / 7.0)
            amp = float(math.hypot(*p))
            fc_rmm.append({"d": dt.strftime("%Y-%m-%d"), "r1": round(float(p[0]), 2), "r2": round(float(p[1]), 2),
                           "phase": rmm_phase(*p), "amp": round(amp, 2)})
    obs = [{"d": d.isoformat(), "r1": round(r1, 2), "r2": round(r2, 2), "phase": ph, "amp": round(amp, 2)}
           for d, r1, r2, ph, amp in rmm if d >= t0.date() - timedelta(days=60)]

    # 7. where the warm and cold events are now
    prof = series[t0][band].mean(0)
    warm_lon, cold_lon = float(LON1[int(np.argmax(prof))]), float(LON1[int(np.argmin(prof))])

    # the marker lines of the belt maps: the MJO core (the component's equatorial minimum), the warm and cold events
    def marks_for(dt):
        p = series[dt][band].mean(0)
        m = {"core": None, "warm": float(LON1[int(np.argmax(p))]), "cold": float(LON1[int(np.argmin(p))])}
        if mjof and dt.date().isoformat() in mjof["days"]:
            m["core"] = mjof["core"][mjof["days"].index(dt.date().isoformat())]
        return m

    # 7b. the MJO component of the 800 hPa height and of the rain (Wheeler-Kiladis filter, as in Dr Khalid's maps)
    mjof = None
    try:
        mh = mjofilt.history(state, t0, mjofilt.HIST_DAYS, gfs_fields)
        ds = sorted(fc)
        fcl = []
        for k, dt in enumerate(ds):
            rain = None
            if k + 1 < len(ds) and fc[ds[k + 1]].get("apcp") is not None:
                prev_acc = fc[dt]["apcp"] if fc[dt].get("apcp") is not None else 0.0
                rain = mjofilt.band(np.maximum(fc[ds[k + 1]]["apcp"] - prev_acc, 0))
            fcl.append((dt.date(), mjofilt.band(fc[dt]["z800"]), rain))
        full, zf, rf, mjof = mjofilt.run(mh, fcl, t0.date())
        mjof["episodes"] = mjofilt.episodes(mjof, t0.date().isoformat())
        idx = [full.index(dt.date()) for dt in ds]
        trop = (mjofilt.LAT >= -35) & (mjofilt.LAT <= 35)
        zmax = float(np.percentile(np.abs(zf[idx][:, trop]), 99.5))
        rmax = float(np.percentile(np.abs(rf[idx][:, trop]), 99.5))
        figures.mjo_scales(zmax, rmax)
        for k, i in enumerate(idx):
            mk = marks_for(ds[k])
            for kind, arr in (("mjoz", zf[i]), ("mjop", rf[i])):
                try:
                    figures.draw_belt(os.path.join(out, "fig", f"{kind}_{k:02d}.png"), arr, mjofilt.LAT, mjofilt.LON,
                                      kind, marks=mk)
                except Exception as e:  # noqa: BLE001
                    print("figure failed", kind, k, repr(e), flush=True)
        print("mjo component episodes:", mjof["episodes"], flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("mjo component failed:", repr(e), flush=True)

    # 7c. the tropical waves in the 200 hPa velocity potential (Kelvin and Rossby families) and the belt maps of
    # the warm/cold event, all on one frame with the same marker lines
    tw = None
    belt_marks = []
    try:
        seq = sorted(series)
        byd = {dt.date(): -series[dt] * 1e6 for dt in seq}            # the chi anomaly, m^2/s
        d0, d1 = seq[0].date(), seq[-1].date()
        full_d = [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]
        have = sorted(byd)
        ser = []
        for d in full_d:                                             # a gap: linear between the neighbours
            if d in byd:
                ser.append((d, byd[d]))
                continue
            a = max(x for x in have if x < d)
            b = min(x for x in have if x > d)
            f_ = (d - a).days / (b - a).days
            ser.append((d, (1 - f_) * byd[a] + f_ * byd[b]))
        wk, wla, tw = wkfilt.run(ser, LAT1)
        past = [k for k, d in enumerate(full_d) if d < t0.date()]
        for fam in ("kel", "ros"):
            tw[fam + "_ref"] = round(float(np.std([tw[fam + "_ksa"][k] for k in past])) or 1.0, 2)
        tw["t0"] = t0.date().isoformat()
        print("tropical waves: days", len(full_d), "kel/ros over the Kingdom today",
              tw["kel_ksa"][full_d.index(t0.date())], tw["ros_ksa"][full_d.index(t0.date())], flush=True)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("tropical waves failed:", repr(e), flush=True)
        wk = None
    for k, dt in enumerate(days):
        mk = marks_for(dt)
        belt_marks.append({"d": dt.strftime("%Y-%m-%d"), **mk})
        W = series[dt]
        prev = series.get(dt - timedelta(days=1))
        try:
            figures.draw_belt(os.path.join(out, "fig", f"wc_{k:02d}.png"), W, LAT1, LON1, "wc", marks=mk,
                              stream=wc_stream.get(k))
            if prev is not None:
                figures.draw_belt(os.path.join(out, "fig", f"wcd_{k:02d}.png"), W - prev, LAT1, LON1, "wcd", marks=mk)
            if wk is not None:
                i = tw["days"].index(dt.date().isoformat())
                for fam in ("kel", "ros"):
                    a = wk[fam][i]
                    figures.draw_belt(os.path.join(out, "fig", f"{fam}_{k:02d}.png"), a / 1e6, wla, LON1, fam, marks=mk,
                                      vectors=sphere.divergent_wind(a, wla), contours=True)
        except Exception as e:  # noqa: BLE001
            print("figure failed", k, repr(e), flush=True)

    # 8. moisture over Saudi Arabia: precipitable water against the climatology
    plat, plon = clim["pw_lat"], clim["pw_lon"]
    pw_rows = []
    for k, dt in enumerate(days):
        row = {"d": dt.strftime("%Y-%m-%d")}
        for key, (name, s, n, w, e) in BOXES.items():
            g = box_mean(fc[dt]["pw"], LAT1, LON1, s, n, w, e)
            c = box_mean(clim["pw"][doy(dt)], plat, plon, s, n, w, e)
            row[key] = {"pw": round(g, 1), "clim": round(c, 1), "pct": int(round(100 * g / max(c, 1)))}
        pw_rows.append(row)
        # percent of normal map over Arabia
        from scipy.ndimage import map_coordinates
        cl = clim["pw"][doy(dt)]
        J = (LAT1[:, None] - plat[0]) / (plat[1] - plat[0]) * np.ones((1, len(LON1)))
        I = (LON1[None, :] - plon[0]) / (plon[1] - plon[0]) * np.ones((len(LAT1), 1))
        clim1 = map_coordinates(cl, [J, I], order=1, mode="nearest")
        pct = 100 * fc[dt]["pw"] / np.maximum(clim1, 1)
        sub_j = (LAT1 >= 5) & (LAT1 <= 40)
        sub_i = (LON1 >= 25) & (LON1 <= 65)
        mercator_png(os.path.join(out, "pw", f"{k:02d}.png"), pct[np.ix_(sub_j, sub_i)], LAT1[sub_j], LON1[sub_i], PWA,
                     south=6, north=39, west=25, east=65, w=400)
        try:
            figures.draw(os.path.join(out, "fig", f"pw_{k:02d}.png"), pct[np.ix_(sub_j, sub_i)], LAT1[sub_j], LON1[sub_i],
                         "pw", (25, 65, 6, 39), width_px=1100)
        except Exception as e:
            print("figure failed pw", k, e, flush=True)

    # 8b. synoptic Rossby waves at 500 hPa (wavenumbers 4-8) and their activity flux
    wave_rows = []
    for k, dt in enumerate(days[:WAVE_DAYS + 1]):
        z = fc[dt].get("z500")
        if z is None:
            continue
        zp = waves.band(z)
        fx, fy = waves.plumb_flux(zp, LAT1, LON1)
        marks = waves.extremes(zp, LAT1, LON1, (5, 55, 5, 95))
        try:
            figures.draw_waves(os.path.join(out, "fig", f"wave_{k:02d}.png"), zp, fx, fy, LAT1, LON1, (5, 95, 5, 55), marks)
        except Exception as e:
            print("wave figure failed", k, e, flush=True)
        # deepest wave trough next to the Kingdom (a trough axis need not be a closed low)
        jb, ib = (LAT1 >= 16) & (LAT1 <= 30), (LON1 >= 26) & (LON1 <= 48)
        sub = zp[np.ix_(jb, ib)]
        jj, ii = np.unravel_index(int(np.argmin(sub)), sub.shape)
        trough = [("L", float(LAT1[jb][jj]), float(LON1[ib][ii]), float(sub[jj, ii]))] if sub[jj, ii] <= -15 else []
        ridge = [m for m in waves.extremes(zp, LAT1, LON1, (10, 35, 46, 70), size=11, minimum=15) if m[0] == "H"]
        row = {"d": dt.strftime("%Y-%m-%d")}
        if trough:
            t = min(trough, key=lambda m: m[3])
            row["trough"] = {"lat": t[1], "lon": t[2], "v": int(round(t[3])), "area": trough_area(t[1], t[2])}
        if ridge:
            r = max(ridge, key=lambda m: m[3])
            row["ridge"] = {"lat": r[1], "lon": r[2], "v": int(round(r[3]))}
        wave_rows.append(row)

    # 8b2. northern cold troughs, tracked day by day for 15 days
    trough_tracks = []
    try:
        tdays = [(dt.date(), troughs.day_troughs(fc[dt]["z500"], fc[dt].get("t500"), LAT1, LON1))
                 for dt in days[:WAVE_DAYS + 1] if fc[dt].get("z500") is not None]
        trough_tracks = troughs.to_json(troughs.track(tdays))
        print("cold troughs:", [(t["days"][0]["d"], t["arrive"], t["deepest"]) for t in trough_tracks], flush=True)
    except Exception as e:
        print("trough tracking failed:", repr(e), flush=True)

    # 8c. where the winds meet in the afternoon of the report day (11:00 to 17:00 Makkah), 0.25 degree: the zones
    #     where storms start (collide.py), and the kind of the storms from the 500 hPa temperature (pattern.py)
    conv_rows = []
    collide_out = None
    first = t0.replace(hour=21, minute=0)          # 00:00 Makkah time = 21 UTC
    if first < t0:
        first += timedelta(days=1)
    try:
        hrs, hg = [], None
        for uh in collide.UTC_HOURS:
            vt = first + timedelta(hours=3 + uh)    # the Makkah day starts at 21 UTC; 08 UTC is 11 hours later
            fh = int((vt - t0).total_seconds() // 3600)
            try:
                f = gfs_fields(cycle, fh, res="0p25", fields=collide.FIELDS + ([] if hg is not None else collide.HGT))
            except Exception as e:  # noqa: BLE001
                print("collision fields unavailable", fh, repr(e)[:120], flush=True)
                continue
            if hg is None:
                hg = f.pop("hgt")
            la = np.linspace(90, -90, f["u10"].shape[0])
            lo = np.linspace(0, 360, f["u10"].shape[1], endpoint=False)
            sub = {}
            for n_, a_ in f.items():
                sub[n_], cla, clo = collide.cut(a_, la, lo)
            sub["hgt"] = collide.cut(hg, la, lo)[0]
            hrs.append((vt, sub))
        if hrs:
            zs = collide.zones(hrs, cla, clo, sa_geo.regions())
            collide_out = {"day": (first + timedelta(hours=3)).date().isoformat(), "hours": len(hrs), "zones": zs,
                           "lines": [collide.zone_text(z) for z in zs]}
            print("collision zones:", collide_out["lines"], flush=True)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("collision zones failed:", repr(e), flush=True)
    pattern_out = None
    try:
        dd = (first + timedelta(hours=3)).date()
        vt = datetime(dd.year, dd.month, dd.day, 12, tzinfo=t0.tzinfo)     # 15:00 Makkah, the storms' hour
        near = min(fc, key=lambda k: abs((k - vt).total_seconds()))
        if abs((near - vt).total_seconds()) <= 6 * 3600 and fc[near].get("t500") is not None:
            pattern_out = {"day": dd.isoformat(), "t": near.strftime("%Y-%m-%dT%H:%MZ"),
                           "boxes": pattern.boxes(fc[near]["t500"], LAT1, LON1, dd)}
            print("pattern:", {k: (v["anom"], v["kind"]) for k, v in pattern_out["boxes"].items()}, flush=True)
    except Exception as e:  # noqa: BLE001
        print("pattern failed:", repr(e), flush=True)

    # (the atmospheric rivers and the Arctic Oscillation are no longer shown on the page)
    ar_data = None

    # the report is written near midnight Makkah time, so it is about the day that starts then
    mk = datetime.now(timezone.utc) + timedelta(hours=3)
    day0 = mk.date() + timedelta(days=1 if mk.hour >= 18 else 0)

    ao = None

    # 10. assessment and report (written from fixed templates)
    month = t0.month
    wet_season = month in (11, 12, 1, 2, 3, 4)
    cold_season = month in (10, 11, 12, 1, 2, 3, 4)
    ao_cold = None
    if ao and ao["fc"] and cold_season:
        low = min(ao["fc"][:11], key=lambda x: x["mean"])
        if low["mean"] <= -1.5:
            ao_cold = low
    now_obs = obs[-1] if obs else None
    surge = []
    for row in pw_rows[1:11]:
        for key, (name, *_b) in BOXES.items():
            v = row[key]
            if v["pct"] >= 150 and v["pw"] - v["clim"] >= 5:
                surge.append({"d": row["d"], "region": name, "pct": v["pct"], "pw": v["pw"]})
    status = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "cycle": cycle,
        "rmm_now": now_obs, "rmm_obs": obs, "rmm_fc": fc_rmm, "fit": fit,
        # the official index lags by two days; today's value is the calibrated GFS estimate
        "rmm_today": next((x for x in fc_rmm if x["d"] == t0.strftime("%Y-%m-%d")), None),
        "warm": {"lon": warm_lon, "region": region_name(warm_lon), "value": round(float(prof.max()), 1)},
        "cold": {"lon": cold_lon, "region": region_name(cold_lon), "value": round(float(prof.min()), 1)},
        "waves": wave_rows, "conv": conv_rows, "collide": collide_out, "pattern": pattern_out, "ar": ar_data,
        "wet_season": wet_season, "cold_season": cold_season, "surge": surge, "pw": pw_rows, "ao": ao, "ao_cold": ao_cold,
        "days": [dt.strftime("%Y-%m-%d") for dt in days],
        "hov": {"lon0": 0, "dlon": 2.5, "days": [dt.strftime("%Y-%m-%d") for dt in hov_days], "v": hov,
                "first_fc": t0.strftime("%Y-%m-%d")},
        "legends": {"wc": legend(WARM, "مؤشر الحدث الدافئ والبارد", "مليون م²/ث", -12, 12),
                    "wcd": legend(CHANGE, "تغير المؤشر خلال ٢٤ ساعة", "مليون م²/ث", -6, 9),
                    "pw": legend(PWA, "الماء القابل للهطول نسبة إلى المعدل", "٪", -100, 300)},
        "bounds": {"wc": [[-45, 0], [45, 360]], "pw": [[6, 25], [39, 65]]},
        "figs": {k: figures.legend(k) for k in ("wc", "wcd", "pw", "wave", "conv", "mjoz", "mjop", "kel", "ros")
                 if k in figures.SCALES},
        "marks": belt_marks, "tw": tw,
    }
    status["troughs"] = trough_tracks
    status["mjof"] = mjof
    # the diagnosis of the current spell: the last 3.5 days of analyses and the next 3 days of this run
    try:
        ana = [(t0 - timedelta(hours=12 * k)).strftime("%Y%m%d%H") for k in range(7, -1, -1)]
        rows_ = diag.snapshots(lambda c, h, fields: gfs_fields(c, h, fields=fields), ana, cycle, range(12, 73, 12),
                               log=lambda *a: print(*a, flush=True))
        status["diag"] = {"lines": diag.text(rows_, t0.replace(tzinfo=None)), "cycle": cycle}
        print("diagnosis:", len(status["diag"]["lines"]), "lines", flush=True)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("diagnosis failed:", repr(e), flush=True)
    # the rain-spread potential from the large-scale ingredients, day by day over the Kingdom and its regions
    try:
        if ING.coef():
            regs_ = sa_geo.regions()
            rows = []
            ds_ = sorted(fc)
            for k_, dt in enumerate(ds_):
                g = fc[dt].get("ingr")
                if not g or len(g) < len(ING.FIELDS):
                    continue
                pot = ING.potential(ING.features(g, ING.pw_normal(clim, doy(dt))))
                row = {"d": dt.strftime("%Y-%m-%d"), "ksa": round(pot["ksa"], 3), "raw": round(pot["raw"], 4),
                       "regions": {regs_[k]["name"]: round(v, 3) for k, v in pot["regions"].items()},
                       "regions_raw": {regs_[k]["name"]: round(v, 4) for k, v in pot["regions_raw"].items()}}
                # the GFS rain over the 24 hours from this time, for the same regions
                if k_ + 1 < len(ds_) and fc[ds_[k_ + 1]].get("apcp") is not None:
                    a0 = fc[dt]["apcp"] if fc[dt].get("apcp") is not None else 0.0
                    sp = ING.spread(ING.cut(np.maximum(fc[ds_[k_ + 1]]["apcp"] - a0, 0)))
                    row["gfs"] = round(sp["ksa"], 3)
                    row["gfs_regions"] = {regs_[k]["name"]: round(v, 3) for k, v in sp["regions"].items()}
                rows.append(row)
            status["ingr"] = rows
            print("rain-spread potential:", [(r["d"][5:], r["ksa"]) for r in rows], flush=True)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("rain-spread potential failed:", repr(e), flush=True)
    # the reports: rain over the Kingdom from our own model (the Makkah day that starts at midnight), and the
    # big picture (now, the next wave, northern cold troughs day by day, cold waves, beyond 15 days)
    om = sa_geo.OpenMeteo()
    try:
        status["coldwaves"] = coldwave.cold_waves(om, state, day0)
    except Exception as e:
        print("cold waves unavailable:", repr(e), flush=True)
        status["coldwaves"] = []
    rain = None
    try:
        ours = ([os.environ.get("SA_DATA"), os.environ.get("WEST_DATA"), os.environ.get("KM1_DATA")]
                + os.environ.get("REGION_DATA", "").split())
        t_a = datetime(day0.year, day0.month, day0.day, tzinfo=timezone.utc) - timedelta(hours=3)
        if os.environ.get("RAIN_PENDING"):
            rain = {"heading": "الأمطار على المملكة", "table": [], "data": {},
                    "lines": ["يُكتب تقرير الأمطار حين يكتمل تشغيل نموذجنا الليلي (دورة ١٢ غرينتش) على المملكة، "
                              "قرابة الثانية فجرًا."]}
        else:
            rain = rainreport.rain_report(t_a, t_a + timedelta(hours=24), ours, status, om, issue="midnight")
    except Exception as e:
        print("rain report failed:", repr(e), flush=True)
    big = []
    try:   # yesterday's estimate of the next wave, to follow it day by day
        status["prev_watch"] = json.load(open(os.path.join(out, "mjo.json"))).get("wave_watch") or {}
    except Exception:
        status["prev_watch"] = {}
    try:
        big = bigreport.report(status, day0)
    except Exception as e:
        print("big-picture report failed:", repr(e), flush=True)
    status["report"] = {"title": f"تقرير {ar_date(day0.strftime('%Y-%m-%d'))}",
                        "issued": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "day": day0.isoformat(),
                        "sections": [x for x in big if x.get("kind") == "sum"] + ([dict(rain, kind="rain")] if rain else [])
                        + [x for x in big if x.get("kind") != "sum"]}
    print("Open-Meteo weight used:", round(om.used), flush=True)
    json.dump(status, open(os.path.join(out, "mjo.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    if status["report"]:
        rd = os.path.join(out, "reports")
        os.makedirs(rd, exist_ok=True)
        json.dump(status["report"], open(os.path.join(rd, t0.strftime("%Y%m%d") + ".json"), "w"), ensure_ascii=False)
    print("done; surge days:", len(surge), "fit:", fit, flush=True)


AR_DIGITS = str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫")
AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def ar(x):
    t = str(x).translate(AR_DIGITS)
    return "\u200e\u2212" + t[1:] if t.startswith("-") else t   # minus sign that stays on the left in Arabic text


def ar_date(s):
    d = date.fromisoformat(s)
    return f"{AR_DAYS[d.weekday()]} {ar(d.day)} {AR_MONTHS[d.month - 1]}"


if __name__ == "__main__":
    main()
