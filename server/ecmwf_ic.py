#!/usr/bin/env python3
"""ECMWF IFS open data (0.25 degree) -> WPS intermediate files, for a run driven by ECMWF instead of GFS.

    ecmwf_ic.py YYYYMMDDHH MAXH OUTDIR [source]

Writes OUTDIR/FILE:YYYY-MM-DD_HH every 3 hours from 0 to MAXH, so metgrid reads them directly and ungrib is
not used (ungrib cannot read the open-data soil fields since IFS cycle 49r1, nor their CCSDS packing).
Fields: on the 13 pressure levels GHT TT UU VV RH; at the surface PSFC PMSL TT RH UU VV SKINTEMP LANDSEA SOILHGT,
soil temperature and moisture in the four IFS layers (0-7, 7-28, 28-100, 100-289 cm).
The area is the one taken from GFS (4-42 N, 25-66 E). source: ecmwf (data.ecmwf.int, recent days) or aws
(the open-data archive, older cycles); default: ecmwf, then aws.
"""
import os
import struct
import sys
from datetime import datetime, timedelta

import numpy as np

LAT0, LAT1, LON0, LON1 = 4.0, 42.0, 25.0, 66.0
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
PL = ["gh", "t", "u", "v", "r"]
SFC = ["sp", "msl", "2t", "2d", "10u", "10v", "skt", "lsm"]
SOIL = ["sot", "vsw"]
LAYERS = ["000007", "007028", "028100", "100289"]
G = 9.80665


# ------------------------------------------------------------------ WPS intermediate format (version 5)
def _rec(f, payload):
    f.write(struct.pack(">i", len(payload)) + payload + struct.pack(">i", len(payload)))


def write_field(f, hdate, field, units, desc, xlvl, a):
    """a: (ny, nx) with latitude increasing northwards, from the south-west corner."""
    ny, nx = a.shape
    _rec(f, struct.pack(">i", 5))
    _rec(f, hdate.ljust(24).encode() + struct.pack(">f", 0.0) + "ECMWF IFS open data".ljust(32).encode()
         + field.ljust(9).encode() + units.ljust(25).encode() + desc.ljust(46).encode()
         + struct.pack(">fiii", xlvl, nx, ny, 0))
    _rec(f, b"SWCORNER" + struct.pack(">fffff", LAT0, LON0, 0.25, 0.25, 6371.229))
    _rec(f, struct.pack(">i", 1))                       # winds relative to the earth
    _rec(f, np.ascontiguousarray(a, dtype=">f4").tobytes())


def read_field(f):
    """The reverse, to check a file: yields (field, xlvl, array)."""
    def rec():
        h = f.read(4)
        if not h:
            return None
        n = struct.unpack(">i", h)[0]
        b = f.read(n); f.read(4)
        return b
    while rec() is not None:
        r2 = rec()
        field = r2[60:69].decode().strip()
        xlvl, nx, ny, _ = struct.unpack(">fiii", r2[140:156])
        rec(); rec()
        a = np.frombuffer(rec(), dtype=">f4").reshape(ny, nx)
        yield field, xlvl, a


# ------------------------------------------------------------------ download
def fetch(cycle, steps, target, source):
    from ecmwf.opendata import Client
    d, h = datetime.strptime(cycle, "%Y%m%d%H"), int(cycle[8:])
    c = Client(source=source)
    kw = dict(date=d.strftime("%Y%m%d"), time=h, stream="oper", type="fc", step=steps)
    c.retrieve(param=PL, levelist=LEVELS, levtype="pl", target=target + ".pl", **kw)
    c.retrieve(param=SFC, levtype="sfc", target=target + ".sfc", **kw)
    c.retrieve(param=SOIL, levtype="sol", levelist=[1, 2, 3, 4], target=target + ".sol", **kw)
    c.retrieve(param=["z"], levtype="sfc", target=target + ".z", **dict(kw, step=0))


def messages(path):
    """(shortName, step, level, field cut to the area, south to north)"""
    import eccodes
    with open(path, "rb") as f:
        while True:
            g = eccodes.codes_grib_new_from_file(f)
            if g is None:
                break
            try:
                sn = eccodes.codes_get(g, "shortName")
                step = int(eccodes.codes_get(g, "endStep"))
                lev = eccodes.codes_get(g, "level")
                ni, nj = eccodes.codes_get(g, "Ni"), eccodes.codes_get(g, "Nj")
                la1 = eccodes.codes_get(g, "latitudeOfFirstGridPointInDegrees")
                lo1 = eccodes.codes_get(g, "longitudeOfFirstGridPointInDegrees")
                v = eccodes.codes_get_values(g).reshape(nj, ni).astype(float)
                if eccodes.codes_get(g, "bitmapPresent"):          # points without a value (soil over the sea)
                    v[v == eccodes.codes_get(g, "missingValue")] = np.nan
            finally:
                eccodes.codes_release(g)
            lats = la1 - 0.25 * np.arange(nj)
            lons = (lo1 + 0.25 * np.arange(ni) + 180) % 360 - 180
            jj = np.where((lats >= LAT0 - 1e-6) & (lats <= LAT1 + 1e-6))[0]
            ii = np.where((lons >= LON0 - 1e-6) & (lons <= LON1 + 1e-6))[0]
            ii = ii[np.argsort(lons[ii])]
            a = v[np.ix_(jj, ii)]
            if lats[jj[0]] > lats[jj[-1]]:
                a = a[::-1]
            yield sn, step, lev, a


def rh_from_dew(t, td):
    es = lambda x: 6.112 * np.exp(17.67 * (x - 273.15) / (x - 29.65))
    return np.clip(100.0 * es(td) / es(t), 0, 100)


def main():
    cycle, maxh, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    sources = sys.argv[4:5] or ["ecmwf", "aws"]
    os.makedirs(out, exist_ok=True)
    steps = list(range(0, maxh + 1, 3))
    grib = os.path.join(out, "ifs.grib2")
    for s in sources:
        try:
            fetch(cycle, steps, grib, s)
            print(f"downloaded from {s}")
            break
        except Exception as e:  # noqa: BLE001
            print(f"{s}: {e}")
    else:
        sys.exit("ECMWF open data not available for " + cycle)

    data = {}
    for part in ("pl", "sfc", "sol", "z"):
        for sn, step, lev, a in messages(f"{grib}.{part}"):
            data[(part, sn, step if part != "z" else 0, lev if part in ("pl", "sol") else 0)] = a
    bad = [k for k, v in data.items() if k[0] != "sol" and not np.isfinite(v).all()]
    if bad:
        sys.exit(f"fields with missing points: {bad[:6]}")
    print("fields at step 0:", sorted({(k[0], k[1]) for k in data if k[2] == 0}))
    z = next(v for k, v in data.items() if k[0] == "z")
    t0 = datetime.strptime(cycle, "%Y%m%d%H")
    for step in steps:
        hdate = (t0 + timedelta(hours=step)).strftime("%Y-%m-%d_%H:00:00")
        g = lambda part, sn, lev=0: data[(part, sn, step, lev)]
        path = os.path.join(out, "FILE:" + hdate[:13])
        with open(path, "wb") as f:
            for lev in LEVELS:
                p = lev * 100.0
                write_field(f, hdate, "GHT", "m", "Height", p, g("pl", "gh", lev))
                write_field(f, hdate, "TT", "K", "Temperature", p, g("pl", "t", lev))
                write_field(f, hdate, "UU", "m s-1", "U", p, g("pl", "u", lev))
                write_field(f, hdate, "VV", "m s-1", "V", p, g("pl", "v", lev))
                write_field(f, hdate, "RH", "%", "Relative Humidity", p, np.clip(g("pl", "r", lev), 0, 100))
            s = 200100.0
            t2, d2 = g("sfc", "2t"), g("sfc", "2d")
            write_field(f, hdate, "PSFC", "Pa", "Surface Pressure", s, g("sfc", "sp"))
            write_field(f, hdate, "PMSL", "Pa", "Sea-level Pressure", 201300.0, g("sfc", "msl"))
            write_field(f, hdate, "TT", "K", "Temperature", s, t2)
            write_field(f, hdate, "RH", "%", "Relative Humidity", s, rh_from_dew(t2, d2))
            write_field(f, hdate, "UU", "m s-1", "U", s, g("sfc", "10u"))
            write_field(f, hdate, "VV", "m s-1", "V", s, g("sfc", "10v"))
            write_field(f, hdate, "SKINTEMP", "K", "Skin temperature", s, g("sfc", "skt"))
            write_field(f, hdate, "LANDSEA", "proprtn", "Land/Sea flag", s, (g("sfc", "lsm") > 0.5).astype(float))
            write_field(f, hdate, "SOILHGT", "m", "Terrain field of source analysis", s, z / G)
            land = g("sfc", "lsm") > 0.5
            for k, lay in enumerate(LAYERS, start=1):
                st = g("sol", "sot", k)
                st = np.where(np.isfinite(st), st, g("sfc", "skt"))
                sm = g("sol", "vsw", k)
                sm = np.where(land & np.isfinite(sm), sm, np.where(land, 0.2, 1.0))
                write_field(f, hdate, "ST" + lay, "K", f"T {lay[:3]}-{lay[3:]} cm below ground layer", s, st)
                write_field(f, hdate, "SM" + lay, "m3 m-3", f"Soil moisture {lay[:3]}-{lay[3:]} cm", s, sm)
        print("wrote", path)
    for part in ("pl", "sfc", "sol", "z"):
        os.remove(f"{grib}.{part}")


if __name__ == "__main__":
    main()
