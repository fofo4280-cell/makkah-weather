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
from products import PRODUCTS, DAILY, POINT_VARS, palette, classify, legend, encode_point, fields_from_frame  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "..", "domains.json")))
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
        self.dom = {d["id"]: d for d in CFG["domains"]}
        self.prev_acc = {}

    def files(self, did):
        return sorted(glob.glob(os.path.join(self.wrfdir, f"wrfout_{did}_*")))

    def grid(self, did, nc):
        if did not in self.grids:
            self.grids[did] = Grid(self.dom[did], np.array(nc.variables["XLAT"][0]), np.array(nc.variables["XLONG"][0]))
        return self.grids[did]

    def acc_path(self, did):
        return os.path.join(self.st.dir, f".acc_{did}.npy")

    def process(self, did, path):
        t = frame_time(path)
        h = int(round((t - self.init).total_seconds() / 3600))
        prev = self.prev_acc.get(did)
        if prev is None and os.path.exists(self.acc_path(did)) and h > 0:
            prev = np.load(self.acc_path(did))
        with Dataset(path) as nc:
            g = self.grid(did, nc)
            fields, acc = fields_from_frame(nc, prev if h > 0 else None)
        for pid, f in fields.items():
            if pid not in PRODUCTS:
                continue
            if pid in ("wind", "wup", "rain1h") and h == 0:
                continue
            save_png(os.path.join(self.st.dir, did, pid, f"{h:03d}.png"), g.sample(f), PRODUCTS[pid])
        # daily accumulators (local day in Riyadh time, hour ending at valid time)
        day = (t - timedelta(minutes=1)).astimezone(RIYADH).strftime("%Y%m%d")
        if h > 0:
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
            put("rain", fields["rain1h"][j, i] if h > 0 else None)
            put("acc", fields["rainacc"][j, i])
            if "refl" in fields:
                put("refl", neighbourhood_max(fields["refl"], i, j, r), 0)
            if h > 0:
                put("wind", fields["wind"][j, i], 0)
                if "wup" in fields:
                    put("wup", neighbourhood_max(fields["wup"], i, j, r))

    def daily_products(self, final):
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
                        save_png(os.path.join(self.st.dir, did, dpid, f"{day}.png"), g.sample(np.load(p)), spec)

    def manifest(self, status):
        doms = {}
        for d in CFG["domains"]:
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
                if os.path.exists(os.path.join(self.st.dir, did, "refl_day", f"{day}.png")):
                    days.append({"date": day, "hours": len(hrs)})
            doms[did] = {"name": d["name"], "res": d["res"], "bounds": bounds, "hours": hours,
                         "planned": d["hours"], "days": days}
            pinfo = self.write_points(did, hours)
            if pinfo:
                doms[did]["points"] = pinfo
        man = {"run": self.run, "init": self.init.strftime("%Y-%m-%dT%H:%MZ"), "status": status,
               "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "domains": doms,
               "proj": {**CFG["map"], "R": R_EARTH},
               "products": {k: {"label": v["label"], "unit": v["unit"], "legend": legend(v)}
                            for k, v in {**PRODUCTS, **DAILY}.items()}}
        jdump(os.path.join(self.st.dir, "manifest.json"), man)
        # city series in a compact form: per city the finest domain available
        meteo = {"run": self.run, "init": man["init"], "cities": []}
        for c in CITIES:
            rec = self.st.s["meteo"].get(c["id"])
            if not rec:
                continue
            best = max(rec.keys(), key=lambda k: (self.dom[k]["dx"] * -1, len(rec[k].get("t2", {}))))
            # use the finest domain but fill later hours from coarser ones
            series = {}
            for did in sorted(rec.keys(), key=lambda k: self.dom[k]["dx"], reverse=True):
                for var, vals in rec[did].items():
                    series.setdefault(var, {}).update(vals)
            out = {}
            for var, vals in series.items():
                hs = sorted(int(k) for k in vals)
                out[var] = [[hh, vals[str(hh)]] for hh in hs]
            meteo["cities"].append({**c, "domain": best, "series": out})
        jdump(os.path.join(self.st.dir, "meteo.json"), meteo)
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
        path = os.path.join(self.st.dir, did, "points.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "wb") as fh:
            fh.write(np.ascontiguousarray(arr).tobytes())
        os.replace(path + ".tmp", path)
        g = self.grids.get(did)
        if g is None and self.files(did):
            with Dataset(self.files(did)[0]) as nc:
                g = self.grid(did, nc)
        info = {"file": f"{did}/points.bin", "vars": POINT_VARS, "hours": hours,
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
        for d in CFG["domains"]:
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
    if a.finish or a.failed:
        P.step(True)
        P.daily_products(final=True)
        P.manifest("failed" if a.failed else "complete")


if __name__ == "__main__":
    main()
