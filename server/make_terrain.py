#!/usr/bin/env python3
"""Build a WPS geogrid terrain dataset from the Copernicus DEM (GLO-90, 3 arc-second, ~90 m).

The result is used by the 3 km and 600 m domains so that the escarpment and Makkah's own
surrounding mountains (Jabal al-Nour, Thawr, the Arafat and Muzdalifah ridges, al-Hada, al-Shafa)
are represented far better than by the default 30-second data.

Tiles that do not exist (open sea) are filled with 0 m.
"""
import argparse, os, sys, time, urllib.request
import numpy as np

N = 1200  # pixels per degree at 3 arc-seconds
URL = ("https://copernicus-dem-90m.s3.amazonaws.com/"
       "Copernicus_DSM_COG_30_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
       "Copernicus_DSM_COG_30_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")


def tile_url(lat, lon):
    return URL.format(ns="N" if lat >= 0 else "S", lat=abs(lat), ew="E" if lon >= 0 else "W", lon=abs(lon))


def fetch(url, dest, tries=4):
    for k in range(tries):
        try:
            urllib.request.urlretrieve(url, dest + ".part")
            os.replace(dest + ".part", dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return False
            time.sleep(5 * (k + 1))
        except Exception:
            time.sleep(5 * (k + 1))
    raise RuntimeError("download failed: " + url)


def read_tile(path):
    import rasterio
    from rasterio.enums import Resampling
    with rasterio.open(path) as r:
        a = r.read(1, out_shape=(N, N), resampling=Resampling.average) if (r.width, r.height) != (N, N) else r.read(1)
        nod = r.nodata
    a = a.astype(np.float32)
    if nod is not None:
        a[a == nod] = 0
    a[~np.isfinite(a)] = 0
    return a[::-1, :]  # north-up rows -> bottom-to-top


def load_tile(lat, lon, cache, get=fetch):
    os.makedirs(cache, exist_ok=True)
    f = os.path.join(cache, f"cop_{lat}_{lon}.tif")
    miss = f + ".missing"
    if os.path.exists(miss):
        return np.zeros((N, N), np.float32)
    if not os.path.exists(f):
        if not get(tile_url(lat, lon), f):
            open(miss, "w").close()
            return np.zeros((N, N), np.float32)
    return read_tile(f)


def write_dataset(out, lat0, lat1, lon0, lon1, tile_source):
    """tile_source(lat, lon) -> (N,N) array, rows bottom-to-top."""
    os.makedirs(out, exist_ok=True)
    for j, lat in enumerate(range(lat0, lat1)):
        for i, lon in enumerate(range(lon0, lon1)):
            a = tile_source(lat, lon)
            a = np.clip(np.rint(a), -500, 9000).astype(">i2")
            x0, y0 = i * N + 1, j * N + 1
            name = f"{x0:05d}-{x0 + N - 1:05d}.{y0:05d}-{y0 + N - 1:05d}"
            a.tofile(os.path.join(out, name))
    with open(os.path.join(out, "index"), "w") as f:
        f.write(f"""type = continuous
signed = yes
projection = regular_ll
dx = {1.0 / N:.12f}
dy = {1.0 / N:.12f}
known_x = 1.0
known_y = 1.0
known_lat = {lat0 + 0.5 / N:.12f}
known_lon = {lon0 + 0.5 / N:.12f}
wordsize = 2
tile_x = {N}
tile_y = {N}
tile_z = 1
units = "meters MSL"
description = "Copernicus DEM GLO-90 (3 arc-second)"
row_order = bottom_top
endian = big
""")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--cache", required=True)
    p.add_argument("--lat0", type=int, required=True)
    p.add_argument("--lat1", type=int, required=True)
    p.add_argument("--lon0", type=int, required=True)
    p.add_argument("--lon1", type=int, required=True)
    a = p.parse_args()
    found = []

    def src(lat, lon):
        t = load_tile(lat, lon, a.cache)
        if t.any():
            found.append((lat, lon))
        print(f"tile {lat}N {lon}E max {t.max():.0f} m", flush=True)
        return t

    write_dataset(a.out, a.lat0, a.lat1, a.lon0, a.lon1, src)
    print(f"{len(found)} land tiles written to {a.out}")
    if len(found) < 10:
        sys.exit("too few terrain tiles found; check the download")
