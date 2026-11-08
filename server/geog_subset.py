#!/usr/bin/env python3
"""Extract only the part of the WPS static data (geog_high_res_mandatory) that covers a region.

The full set unpacks to about 29 GB; the free runners have far less disk. The archive is read
twice as a stream: first for every dataset's 'index' file, then for the tiles that intersect
the region (plus a margin). Nothing large is written except the kept tiles.

geog_subset.py <url-or-file> <out_dir> <south> <north> <west> <east>
"""
import os, re, sys, tarfile, urllib.request

TILE = re.compile(r"^(\d+)-(\d+)\.(\d+)-(\d+)$")


def stream(src):
    if os.path.exists(src):
        return open(src, "rb")
    return urllib.request.urlopen(src, timeout=600)


def parse_index(text):
    d = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            d[k.strip().lower()] = v.strip().strip('"')
    return d


def tile_box(idx, x0, x1, y0, y1):
    try:
        if idx.get("projection", "regular_ll") != "regular_ll":
            return None
        dx, dy = float(idx["dx"]), float(idx["dy"])
        kx, ky = float(idx.get("known_x", 1)), float(idx.get("known_y", 1))
        klat, klon = float(idx["known_lat"]), float(idx["known_lon"])
    except (KeyError, ValueError):
        return None
    lat_a, lat_b = klat + (y0 - ky) * dy, klat + (y1 - ky) * dy
    lon_a, lon_b = klon + (x0 - kx) * dx, klon + (x1 - kx) * dx
    return min(lat_a, lat_b), max(lat_a, lat_b), min(lon_a, lon_b), max(lon_a, lon_b)


def lon_overlap(a, b, w, e):
    for shift in (-360, 0, 360):
        if a + shift <= e and b + shift >= w:
            return True
    return False


def main():
    src, out = sys.argv[1], sys.argv[2]
    S, N, W, E = (float(v) for v in sys.argv[3:7])
    m = 2.0
    S, N, W, E = S - m, N + m, W - m, E + m

    indexes = {}
    with stream(src) as f, tarfile.open(fileobj=f, mode="r|gz") as tf:
        for mem in tf:
            if mem.isfile() and os.path.basename(mem.name) == "index":
                indexes[os.path.dirname(mem.name)] = tf.extractfile(mem).read().decode("latin-1")
    print(f"pass 1: {len(indexes)} datasets", flush=True)
    parsed = {k: parse_index(v) for k, v in indexes.items()}

    kept = skipped = 0
    with stream(src) as f, tarfile.open(fileobj=f, mode="r|gz") as tf:
        for mem in tf:
            if not mem.isfile():
                continue
            d, name = os.path.dirname(mem.name), os.path.basename(mem.name)
            mt = TILE.match(name)
            keep = True
            if mt and d in parsed:
                x0, x1, y0, y1 = (int(g) for g in mt.groups())
                box = tile_box(parsed[d], x0, x1, y0, y1)
                if box is not None:
                    s, n, w, e = box
                    keep = s <= N and n >= S and lon_overlap(w, e, W, E)
            if not keep:
                skipped += 1
                continue
            dest = os.path.join(out, os.path.relpath(mem.name, start=mem.name.split("/")[0]) if "/" in mem.name else mem.name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with tf.extractfile(mem) as r, open(dest, "wb") as w_:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    w_.write(b)
            kept += 1
    print(f"pass 2: kept {kept} files, skipped {skipped}", flush=True)


if __name__ == "__main__":
    main()
