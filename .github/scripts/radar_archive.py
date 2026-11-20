"""Keep the last 12 hours of the Saudi weather radar (RainViewer free service, NCM radars) for the model page.

The free service only keeps two hours. Every half hour this takes the frames we do not have yet, decodes the
"Universal Blue" colours back into reflectivity and stores one grey PNG per frame over the Kingdom and the Red Sea:
pixel 0 = no echo, otherwise v = round((dBZ + 10) * 3). Pixel grid = zoom 7 web-mercator pixels (about 1.2 km),
origin (x0, y0) in global zoom-7 pixel numbers. Frames older than 12 h are dropped.
usage: radar_archive.py <archive folder>
"""
import io, json, math, os, sys, time, urllib.request
import numpy as np
from PIL import Image

OUT = sys.argv[1]
KEEP_H = 12.2
BOX = (15.5, 33.0, 34.0, 56.0)   # south, north, west, east
UA = {"User-Agent": "Mozilla/5.0 (radar archive for a personal weather page)"}
UB = {15: 0x88ddee, 16: 0x6cd1eb, 17: 0x51c5e8, 18: 0x36bae5, 19: 0x1baee2, 20: 0x00a3e0, 21: 0x009ad5, 22: 0x0091ca, 23: 0x0088bf,
      24: 0x007fb4, 25: 0x0077aa, 26: 0x0070a3, 27: 0x00699c, 28: 0x006295, 29: 0x005b8e, 30: 0x005588, 31: 0x005180, 32: 0x004e78,
      33: 0x004a70, 34: 0x004768, 35: 0xffee00, 36: 0xffe000, 37: 0xffd200, 38: 0xffc500, 39: 0xffb700, 40: 0xffaa00, 41: 0xff9f00,
      42: 0xff9500, 43: 0xff8b00, 44: 0xff8100, 45: 0xff4400, 46: 0xf23600, 47: 0xe62800, 48: 0xd91b00, 49: 0xcd0d00, 50: 0xc10000,
      51: 0xa80000, 52: 0x8f0000, 53: 0x760000, 54: 0x5d0000, 55: 0xffaaff, 56: 0xff9fff, 57: 0xff95ff, 58: 0xff8bff, 59: 0xff81ff,
      60: 0xff77ff, 61: 0xff6cff, 62: 0xff62ff, 63: 0xff58ff, 64: 0xff4eff, 65: 0xffffff}
UBZ = np.array(list(UB.keys()), float)
UBC = np.array([[(c >> 16) & 255, (c >> 8) & 255, c & 255] for c in UB.values()], float)


def get(url, tries=4):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(3 * (k + 1))


def gx(lon, z): return (lon + 180) / 360 * 256 * 2 ** z
def gy(lat, z): return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 256 * 2 ** z


def decode(rgba):
    """RGBA tile -> dBZ (nan where no echo)"""
    r, g, b, a = [rgba[..., i].astype(float) for i in range(4)]
    d = np.full(r.shape, np.nan)
    some = a >= 6
    beige = some & (r > 0x60) & (np.abs(r - g) < 0x18) & (b < g) & (b > 0x50)
    d[beige] = np.where(a[beige] < 0x64, -10 + (a[beige] - 0x14) / 5.3, 5 + (a[beige] - 0x64) / 10)
    col = some & ~beige
    if col.any():
        px = np.stack([r[col], g[col], b[col]], 1)
        uniq, inv = np.unique(px, axis=0, return_inverse=True)
        near = ((uniq[:, None, :] - UBC[None]) ** 2).sum(2).argmin(1)
        d[col] = UBZ[near][inv.ravel()]
    return d


def frame(host, path, mode):
    s, n, w, e = BOX
    if mode == 512:   # zoom 6 tiles of 512 px = zoom 7 detail
        z, ts = 6, 512
    else:
        z, ts = 7, 256
    tx0, tx1 = int(gx(w, z) // 256), int(gx(e, z) // 256)
    ty0, ty1 = int(gy(n, z) // 256), int(gy(s, z) // 256)
    k = ts // 256
    W, H = (tx1 - tx0 + 1) * ts, (ty1 - ty0 + 1) * ts
    out = np.zeros((H, W), np.uint8)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            img = Image.open(io.BytesIO(get(f"{host}{path}/{ts}/{z}/{tx}/{ty}/2/1_0.png"))).convert("RGBA")
            if img.size != (ts, ts):
                raise ValueError(f"tile size {img.size}")
            d = decode(np.asarray(img))
            v = np.where(np.isfinite(d) & (d >= 0), np.clip(np.round((d + 10) * 3), 1, 255), 0).astype(np.uint8)
            out[(ty - ty0) * ts:(ty - ty0 + 1) * ts, (tx - tx0) * ts:(tx - tx0 + 1) * ts] = v
            time.sleep(0.4)   # the service allows about 100 requests a minute
    return out, tx0 * 256 * k, ty0 * 256 * k


def main():
    os.makedirs(os.path.join(OUT, "f"), exist_ok=True)
    ip = os.path.join(OUT, "index.json")
    idx = json.load(open(ip)) if os.path.exists(ip) else {"frames": []}
    have = {f["t"] for f in idx["frames"]}
    m = json.loads(get("https://api.rainviewer.com/public/weather-maps.json"))
    host = m.get("host", "https://tilecache.rainviewer.com")
    mode = idx.get("mode", 512)
    for f in m["radar"]["past"]:
        if f["time"] in have:
            continue
        try:
            v, x0, y0 = frame(host, f["path"], mode)
        except ValueError as e:   # 512 px tiles refused: zoom 7 tiles instead
            print("512 failed:", e); mode = 256
            v, x0, y0 = frame(host, f["path"], mode)
        Image.fromarray(v, "L").save(os.path.join(OUT, "f", f"{f['time']}.png"), optimize=True)
        idx["frames"].append({"t": f["time"]})
        idx.update({"z": 7, "x0": x0, "y0": y0, "w": int(v.shape[1]), "h": int(v.shape[0]), "mode": mode})
        print("saved", f["time"], v.shape, int((v > 0).sum()), "echo px")
    now = time.time()
    keep = sorted([f for f in idx["frames"] if now - f["t"] <= KEEP_H * 3600], key=lambda f: f["t"])
    for f in idx["frames"]:
        if f not in keep:
            try: os.remove(os.path.join(OUT, "f", f"{f['t']}.png"))
            except OSError: pass
    idx["frames"] = keep
    idx["src"] = "RainViewer (NCM radars); dBZ = v/3 - 10, 0 = no echo"
    idx["updated"] = int(now)
    json.dump(idx, open(ip, "w"), separators=(",", ":"))
    print(len(keep), "frames kept")


main()
