#!/usr/bin/env python3
"""Turn WRF output into map images and city time series for the website.

postprocess.py --wrfdir DIR --web WEBDIR --run YYYYMMDDHH [--watch DONEFLAG] [--finish]

--watch: keep going while WRF runs; a frame is processed once the next frame exists
         (or the done-flag file appears). Exits after the flag appears and all frames are done.
--finish: process what is there, then write daily products and mark the run complete.
Restart-safe: progress is kept in <run>/state.json.
"""
import argparse, glob, json, os, re, sys, time
from datetime import datetime, timedelta, timezone

import numpy as np
from netCDF4 import Dataset
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from products import (PRODUCTS, DAILY, SINGLE, POINT_VARS, palette, classify, legend, encode_point,  # noqa: E402
                      fields_from_frame, ivt_from_frame, conv925_from_frame)

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "..", os.environ.get("SWRF_DOMAINS") or "domains.json")))
# grids that only feed a nest are run but not drawn or published ("publish": false)
PUB = [d for d in CFG["domains"] if d.get("publish", True)]
CITIES = json.load(open(os.path.join(HERE, "cities.json")))
R_EARTH = 6370000.0
RIYADH = timezone(timedelta(hours=3))
UPSCALE = 2


def jdump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


# ------------------------------------------------------------------ geometry
class Grid:
    """Maps a WRF Lambert grid onto a Web-Mercator-aligned image so Leaflet can overlay it exactly."""

    def __init__(self, dom, lat, lon):
        from pyproj import Proj
        m = CFG["map"]
        self.P = Proj(proj="lcc", lat_1=m["truelat1"], lat_2=m["truelat2"], lon_0=m["stand_lon"],
                      lat_0=m["ref_lat"], R=R_EARTH)
        self.dx = dom["dx"]
        ny, nx = lat.shape
        x00, y00 = self.P(float(lon[0, 0]), float(lat[0, 0]))
        self.x00, self.y00 = x00, y00
        # check: the far corner must land on (nx-1, ny-1)
        xe, ye = self.P(float(lon[-1, -1]), float(lat[-1, -1]))
        err = max(abs((xe - x00) / self.dx - (nx - 1)), abs((ye - y00) / self.dx - (ny - 1)))
        if err > 0.3:
            print(f"warning: projection check off by {err:.2f} cells", file=sys.stderr)
        inner = 1  # drop the outermost row/column
        s, n = float(lat[inner:-inner, inner:-inner].min()), float(lat[inner:-inner, inner:-inner].max())
        w, e = float(lon[inner:-inner, inner:-inner].min()), float(lon[inner:-inner, inner:-inner].max())
        latc = 0.5 * (s + n)
        step_lon = self.dx / (111320.0 * np.cos(np.radians(latc))) / UPSCALE
        W = int(np.ceil((e - w) / step_lon))
        lons = w + (np.arange(W) + 0.5) * (e - w) / W

        def merc(phi):
            return np.log(np.tan(np.pi / 4 + np.radians(phi) / 2))

        ys, yn = merc(s), merc(n)
        step_y = np.radians(step_lon)
        H = int(np.ceil((yn - ys) / step_y))
        my = yn - (np.arange(H) + 0.5) * (yn - ys) / H  # north to south
        lats = np.degrees(2 * np.arctan(np.exp(my)) - np.pi / 2)
        LON, LAT = np.meshgrid(lons, lats)
        X, Y = self.P(LON, LAT)
        self.fi = ((X - x00) / self.dx).astype(np.float32)
        self.fj = ((Y - y00) / self.dx).astype(np.float32)
        self.bounds = [[round(s, 5), round(w, 5)], [round(n, 5), round(e, 5)]]
        self.shape = (H, W)
        self.nx, self.ny = nx, ny

    def sample(self, field):
        from scipy.ndimage import map_coordinates
        out = map_coordinates(field, [self.fj, self.fi], order=1, mode="constant", cval=np.nan)
        return out

    def index(self, lon, lat):
        x, y = self.P(lon, lat)
        i, j = (x - self.x00) / self.dx, (y - self.y00) / self.dx
        if 2 <= i <= self.nx - 3 and 2 <= j <= self.ny - 3:
            return int(round(i)), int(round(j))
        return None


def save_png(path, field, spec):
    idx = classify(field, spec)
    img = Image.fromarray(idx, "P")
    pal, trans = palette(spec)
    img.putpalette(pal)
    img.info["transparency"] = bytes(trans)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.png"
    img.save(tmp, optimize=True, transparency=bytes(trans))
    os.replace(tmp, path)


# ------------------------------------------------------------------ state
class RunState:
    def __init__(self, webdir, run):
        self.dir = os.path.join(webdir, "data", "runs", run)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "state.json")
        self.s = json.load(open(self.path)) if os.path.exists(self.path) else {"done": {}, "meteo": {}, "daily": {}}
        self.run = run

    def save(self):
        jdump(self.path, self.s)


def frame_time(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2}):(\d{2}):(\d{2})", os.path.basename(path))
    return datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H").replace(tzinfo=timezone.utc)


def neighbourhood_max(f, i, j, r):
    return float(np.nanmax(f[max(0, j - r):j + r + 1, max(0, i - r):i + r + 1]))


# ------------------------------------------------------------------ processing
class Processor:
    def __init__(self, wrfdir, webdir, run):
        self.wrfdir, self.web, self.run = wrfdir, webdir, run
        self.st = RunState(webdir, run)
        self.init = datetime.strptime(run, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        self.grids = {}
        self.dom = {d["id"]: d for d in PUB}
        self.pub = {d["id"]: d.get("pub", d["id"]) for d in PUB}  # name used on the website
        self.prev_acc = {}
        self._first = dict(self.st.s.get("first", {}))

    def files(self, did):
        return sorted(glob.glob(os.path.join(self.wrfdir, f"wrfout_{did}_*")))

    def grid(self, did, nc):
        if did not in self.grids:
            self.grids[did] = Grid(self.dom[did], np.array(nc.variables["XLAT"][0]), np.array(nc.variables["XLONG"][0]))
        return self.grids[did]

    def first_hour(self, did):
        """Forecast hour of a domain's first output (late-starting nests begin mid-run)."""
        if did not in self._first:
            fs = self.files(did)
            if fs:
                self._first[did] = int(round((frame_time(fs[0]) - self.init).total_seconds() / 3600))
            else:
                return 0
        return self._first[did]

    def acc_path(self, did):
        return os.path.join(self.st.dir, f".acc_{did}.npy")

    def process(self, did, path):
        t = frame_time(path)
        h = int(round((t - self.init).total_seconds() / 3600))
        prev = self.prev_acc.get(did)
        if prev is None and os.path.exists(self.acc_path(did)) and h > 0:
            prev = np.load(self.acc_path(did))
        first = h == self.first_hour(did)  # nothing accumulated yet (start of the run, or of a late nest)
        with Dataset(path) as nc:
            g = self.grid(did, nc)
            fields, acc = fields_from_frame(nc, None if first else prev)
        if first:
            fields.pop("rain1h", None)
        late = self.first_hour(did) > 0
        for pid, f in fields.items():
            if pid not in PRODUCTS or (late and pid == "rainacc") or PRODUCTS[pid].get("only") or PRODUCTS[pid].get("computed"):
                continue
            if pid in ("wind", "wup") and first:
                continue
            save_png(os.path.join(self.st.dir, self.pub[did], pid, f"{h:03d}.png"), g.sample(f), PRODUCTS[pid])
        if h == SINGLE["rain24"]["from_h"]:
            np.save(os.path.join(self.st.dir, f".acc3_{did}.npy"), acc)
        if h == SINGLE["rain24"]["from_h"] + SINGLE["rain24"]["len"]:   # end of the 24-hour map when the run is longer
            np.save(os.path.join(self.st.dir, f".acc27_{did}.npy"), acc)
        # strongest radar echo since hour 3, for the thunderstorm chance map
        ts = SINGLE["tsprob"]
        if not late and ts["from_h"] <= h <= ts["from_h"] + ts["len"] and "refl" in fields:
            rp = os.path.join(self.st.dir, f".rmax_{did}.npy")
            cur = np.load(rp) if os.path.exists(rp) and h > SINGLE["tsprob"]["from_h"] else None
            np.save(rp, fields["refl"] if cur is None else np.maximum(cur, fields["refl"]))
        if "conv925" in PRODUCTS:
            try:
                self.conv925(did, path, g, h)
            except Exception as e:
                print(f"conv925 failed {path}: {e}", file=sys.stderr)
        if self.dom[did].get("ivt"):
            try:
                self.ivt(did, path, g, h)
            except Exception as e:  # a missing variable must not stop the other maps
                print(f"ivt failed {path}: {e}", file=sys.stderr)
        # daily accumulators (local day in Riyadh time, hour ending at valid time)
        day = (t - timedelta(minutes=1)).astimezone(RIYADH).strftime("%Y%m%d")
        if not first and not late:
            for dpid, spec in DAILY.items():
                src = fields.get(spec["from"])
                if src is None:
                    continue
                p = os.path.join(self.st.dir, f".day_{did}_{dpid}_{day}.npy")
                cur = np.load(p) if os.path.exists(p) else None
                new = src if cur is None else (np.maximum(cur, src) if dpid == "refl_day" else cur + src)
                np.save(p, new.astype(np.float32))
                dd = self.st.s["daily"].setdefault(did, {}).setdefault(day, [])
                if h not in dd:
                    dd.append(h)
        # one byte per grid cell and variable, for tapping any point on the map
        pts = np.stack([encode_point(k, fields[k]) if k in fields else np.zeros(fields["t2"].shape, np.uint8)
                        for k in POINT_VARS])
        fields["_first"] = first; fields["_late"] = late
        np.save(os.path.join(self.st.dir, f".pts_{did}_{h:03d}.npy"), pts)
        # city series
        self.city_values(did, g, fields, h)
        self.prev_acc[did] = acc
        np.save(self.acc_path(did), acc)
        self.st.s["done"].setdefault(did, [])
        if h not in self.st.s["done"][did]:
            self.st.s["done"][did].append(h)
            self.st.s["done"][did].sort()

    def city_values(self, did, g, fields, h):
        res = self.dom[did]["dx"]
        r = max(1, int(round(5000 / res)))  # 5 km neighbourhood for convective fields
        for c in CITIES:
            ij = g.index(c["lon"], c["lat"])
            if ij is None:
                continue
            i, j = ij
            rec = self.st.s["meteo"].setdefault(c["id"], {}).setdefault(did, {})
            def put(k, val, nd=1):
                arr = rec.setdefault(k, {})
                arr[str(h)] = None if val is None or not np.isfinite(val) else round(float(val), nd)
            put("t2", fields["t2"][j, i])
            if "rain1h" in fields:
                put("rain", fields["rain1h"][j, i])
            if not fields.get("_late"):
                put("acc", fields["rainacc"][j, i])
            if "refl" in fields:
                put("refl", neighbourhood_max(fields["refl"], i, j, r), 0)
            if not fields.get("_first"):
                put("wind", fields["wind"][j, i], 0)
                if "wup" in fields:
                    put("wup", neighbourhood_max(fields["wup"], i, j, r))

    def ivt(self, did, path, g, h):
        with Dataset(path) as nc:
            mag, qu, qv = ivt_from_frame(nc)
            lat, lon = np.array(nc.variables["XLAT"][0]), np.array(nc.variables["XLONG"][0])
        save_png(os.path.join(self.st.dir, self.pub[did], "ivt", f"{h:03d}.png"), g.sample(mag), PRODUCTS["ivt"])
        k = max(1, int(round(80000 / self.dom[did]["dx"])))  # one arrow every ~80 km
        sl = (slice(k // 2, None, k), slice(k // 2, None, k))
        m, la, lo, a, b = mag[sl], lat[sl], lon[sl], qu[sl], qv[sl]
        keep = m >= 150
        vec = [[round(float(x), 2), round(float(y), 2), int(round(float(u))), int(round(float(v)))]
               for x, y, u, v in zip(la[keep], lo[keep], a[keep], b[keep])]
        out = os.path.join(self.st.dir, self.pub[did], "ivt_vec", f"{h:03d}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        jdump(out, {"h": h, "max": int(round(float(np.nanmax(mag)))), "v": vec})

    def conv925(self, did, path, g, h):
        dx = self.dom[did]["dx"]
        with Dataset(path) as nc:
            cv, u, v = conv925_from_frame(nc, dx)
            lat, lon = np.array(nc.variables["XLAT"][0]), np.array(nc.variables["XLONG"][0])
        save_png(os.path.join(self.st.dir, self.pub[did], "conv925", f"{h:03d}.png"), g.sample(cv), PRODUCTS["conv925"])
        k = max(1, int(round(max(30000, 5 * dx) / dx)))  # one arrow every 30-45 km
        sl = (slice(k // 2, None, k), slice(k // 2, None, k))
        la, lo, a, b = lat[sl], lon[sl], u[sl], v[sl]
        keep = np.isfinite(a) & np.isfinite(b)
        vec = [[round(float(x), 2), round(float(y), 2), round(float(p), 1), round(float(q), 1)]
               for x, y, p, q in zip(la[keep], lo[keep], a[keep], b[keep])]
        out = os.path.join(self.st.dir, self.pub[did], "conv_vec", f"{h:03d}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        jdump(out, {"h": h, "v": vec})

    def tsprob(self):
        """Share of points within 25 km where the radar echo reached 40 dBZ at some hour since hour 3."""
        from scipy.ndimage import convolve
        spec = SINGLE["tsprob"]
        out = self.st.s.setdefault("single_ts", {})
        for d in PUB:
            did = d["id"]
            rp = os.path.join(self.st.dir, f".rmax_{did}.npy")
            hours = self.st.s["done"].get(did, [])
            if self.first_hour(did) > 0 or not os.path.exists(rp) or not hours:
                continue
            last = min(max(hours), spec["from_h"] + spec["len"])   # a 24-hour map even when the run is longer
            if last <= spec["from_h"] or out.get(did, {}).get("to") == last:
                continue
            g = self.grids.get(did)
            if g is None:
                with Dataset(self.files(did)[0]) as nc:
                    g = self.grid(did, nc)
            r = max(1, int(round(spec["radius_km"] * 1000 / d["dx"])))
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
            disk = (xx ** 2 + yy ** 2 <= r * r).astype(np.float32)
            hit = (np.nan_to_num(np.load(rp), nan=0) >= spec["dbz"]).astype(np.float32)
            prob = 100 * convolve(hit, disk / disk.sum(), mode="constant", cval=0.0)
            save_png(os.path.join(self.st.dir, self.pub[did], "tsprob", "main.png"), g.sample(prob), spec)
            out[did] = {"from": spec["from_h"], "to": last}

    def single_products(self):
        """rain24: accumulated rain from hour 3 to hour 27, or to the last hour done so far (never past hour 27)."""
        spec = SINGLE["rain24"]
        out = self.st.s.setdefault("single", {})
        for d in PUB:
            did = d["id"]
            a3 = os.path.join(self.st.dir, f".acc3_{did}.npy")
            hours = self.st.s["done"].get(did, [])
            if self.first_hour(did) > 0 or not os.path.exists(a3) or not os.path.exists(self.acc_path(did)) or not hours:
                continue
            last = min(max(hours), spec["from_h"] + spec["len"])   # a 24-hour map even when the run is longer
            if last <= spec["from_h"] or out.get(did, {}).get("to") == last:
                continue
            g = self.grids.get(did)
            if g is None:
                with Dataset(self.files(did)[0]) as nc:
                    g = self.grid(did, nc)
            a27 = os.path.join(self.st.dir, f".acc27_{did}.npy")
            end = a27 if last == spec["from_h"] + spec["len"] and os.path.exists(a27) else self.acc_path(did)
            tot = np.maximum(np.load(end) - np.load(a3), 0)
            save_png(os.path.join(self.st.dir, self.pub[did], "rain24", "main.png"), g.sample(tot), spec)
            out[did] = {"from": spec["from_h"], "to": last}

    def daily_products(self, final):
        for fn in (self.single_products, self.tsprob):
            try:
                fn()
            except Exception as e:
                print(f"{fn.__name__} failed: {e}", file=sys.stderr)
        for did, days in self.st.s["daily"].items():
            g = self.grids.get(did)
            if g is None:
                fs = self.files(did)
                if not fs:
                    continue
                with Dataset(fs[0]) as nc:
                    g = self.grid(did, nc)
            for day, hours in days.items():
                if len(hours) < 12 and not final:
                    continue
                for dpid, spec in DAILY.items():
                    p = os.path.join(self.st.dir, f".day_{did}_{dpid}_{day}.npy")
                    if os.path.exists(p):
                        save_png(os.path.join(self.st.dir, self.pub[did], dpid, f"{day}.png"), g.sample(np.load(p)), spec)

    def manifest(self, status):
        doms = {}
        for d in PUB:
            did = d["id"]
            hours = self.st.s["done"].get(did, [])
            if not hours:
                continue
            g = self.grids.get(did)
            bounds = g.bounds if g else self.st.s.get("bounds", {}).get(did)
            if g:
                self.st.s.setdefault("bounds", {})[did] = g.bounds
            days = []
            for day, hrs in sorted(self.st.s["daily"].get(did, {}).items()):
                if os.path.exists(os.path.join(self.st.dir, self.pub[did], "refl_day", f"{day}.png")):
                    days.append({"date": day, "hours": len(hrs)})
            late = self.first_hour(did) > 0
            prods = [k for k in PRODUCTS if not (late and k == "rainacc") and not (PRODUCTS[k].get("only") and not d.get(PRODUCTS[k]["only"]))]
            if not late:
                prods += list(DAILY)
            if did in self.st.s.get("single", {}):
                prods.append("rain24")
            if did in self.st.s.get("single_ts", {}):
                prods.append("tsprob")
            doms[self.pub[did]] = {"name": d["name"], "res": d["res"], "dx": d["dx"], "bounds": bounds, "hours": hours,
                         "planned": d["hours"], "days": days, "products": prods,
                         "rain24": self.st.s.get("single", {}).get(did),
                         "tsprob": self.st.s.get("single_ts", {}).get(did)}
            pinfo = self.write_points(did, hours)
            if pinfo:
                doms[self.pub[did]]["points"] = pinfo
        man = {"run": self.run, "init": self.init.strftime("%Y-%m-%dT%H:%MZ"), "status": status,
               "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "domains": doms,
               "proj": {**CFG["map"], "R": R_EARTH},
               "products": {k: {"label": v["label"], "unit": v["unit"], "legend": legend(v)}
                            for k, v in {**PRODUCTS, **DAILY, **SINGLE}.items()}}
        jdump(os.path.join(self.st.dir, "manifest.json"), man)
        # city series in a compact form: per city the finest domain available
        meteo = {"run": self.run, "init": man["init"], "cities": []}
        for c in CITIES:
            rec = self.st.s["meteo"].get(c["id"])
            if not rec:
                continue
            best = max(rec.keys(), key=lambda k: (len(rec[k].get("t2", {})), -self.dom[k]["dx"]))
            # use the finest domain but fill later hours from coarser ones
            series = {}
            for did in sorted(rec.keys(), key=lambda k: self.dom[k]["dx"], reverse=True):
                for var, vals in rec[did].items():
                    series.setdefault(var, {}).update(vals)
            out = {}
            for var, vals in series.items():
                hs = sorted(int(k) for k in vals)
                out[var] = [[hh, vals[str(hh)]] for hh in hs]
            meteo["cities"].append({**c, "domain": self.pub[best], "series": out})
        jdump(os.path.join(self.st.dir, "meteo.json"), meteo)
        self.st.s["first"] = self._first
        self.st.save()
        update_index(self.web, self.run, status, doms)

    def write_points(self, did, hours):
        """All hours of the point values in one file: [variable][hour][row][column], one byte each."""
        frames = []
        for h in hours:
            f = os.path.join(self.st.dir, f".pts_{did}_{h:03d}.npy")
            if not os.path.exists(f):
                return self.st.s.get("points", {}).get(did)
            frames.append(np.load(f))
        if not frames:
            return None
        arr = np.stack(frames, axis=1)  # var, hour, ny, nx
        path = os.path.join(self.st.dir, self.pub[did], "points.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "wb") as fh:
            fh.write(np.ascontiguousarray(arr).tobytes())
        os.replace(path + ".tmp", path)
        g = self.grids.get(did)
        if g is None and self.files(did):
            with Dataset(self.files(did)[0]) as nc:
                g = self.grid(did, nc)
        info = {"file": f"{self.pub[did]}/points.bin", "vars": POINT_VARS, "hours": hours,
                "nx": int(arr.shape[3]), "ny": int(arr.shape[2]), "dx": self.dom[did]["dx"],
                "x00": round(g.x00, 2) if g else None, "y00": round(g.y00, 2) if g else None}
        if g:
            self.st.s.setdefault("points", {})[did] = info
        return info

    def pending(self, did, done_flag):
        fs = self.files(did)
        done = set(self.st.s["done"].get(did, []))
        out = []
        for k, f in enumerate(fs):
            h = int(round((frame_time(f) - self.init).total_seconds() / 3600))
            if h in done:
                continue
            complete = (k + 1 < len(fs)) or done_flag
            if complete:
                out.append(f)
        return out

    def step(self, done_flag):
        n = 0
        for d in PUB:
            for f in self.pending(d["id"], done_flag):
                try:
                    self.process(d["id"], f)
                    n += 1
                except Exception as e:  # a broken frame should not stop the rest
                    print(f"frame failed {f}: {e}", file=sys.stderr)
        return n


def update_index(web, run, status, doms):
    p = os.path.join(web, "data", "runs.json")
    try:
        idx = json.load(open(p))
    except Exception:
        idx = {"runs": []}
    idx["runs"] = [r for r in idx["runs"] if r["run"] != run]
    idx["runs"].append({"run": run, "status": status,
                        "hours": {k: (max(v["hours"]) if v["hours"] else 0) for k, v in doms.items()}})
    idx["runs"].sort(key=lambda r: r["run"], reverse=True)
    idx["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    jdump(p, idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wrfdir", required=True)
    ap.add_argument("--web", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--watch", help="file whose existence means WRF has finished")
    ap.add_argument("--finish", action="store_true")
    ap.add_argument("--failed", action="store_true", help="WRF stopped early: publish what exists")
    ap.add_argument("--partial", action="store_true", help="first part of a run split over two runners: publish what exists, the run goes on")
    a = ap.parse_args()
    P = Processor(a.wrfdir, a.web, a.run)
    if a.watch:
        last_manifest = 0
        while True:
            flag = os.path.exists(a.watch)
            n = P.step(flag)
            if n or time.time() - last_manifest > 600:
                P.daily_products(final=False)
                P.manifest("running")
                last_manifest = time.time()
            if flag and n == 0:
                break
            if n == 0:
                time.sleep(30)
    if a.partial:
        P.step(True)
        P.daily_products(final=False)
        P.manifest("running")
    elif a.finish or a.failed:
        P.step(True)
        P.daily_products(final=True)
        P.manifest("failed" if a.failed else "complete")


if __name__ == "__main__":
    main()
