#!/usr/bin/env python3
"""Make the static grid files (geo_em) of the morning run by cutting them out of the western run's own files.

crop_geo.py <west static dir> <out dir>

The morning grids (domains_am.json) are exact sub-rectangles of the western grids (domains_west.json): same
projection, same 9 km and 3 km points. So no geography download is needed (17 Nov 2026: the UCAR server
refused the GitHub runners), and the terrain/land data are identical to the evening run's.
Crop boxes ("crop" in domains_am.json): first and last mass point (1-based) of the western grid, i then j.
"""
import json, os, sys

import numpy as np
from netCDF4 import Dataset
from pyproj import Proj

HERE = os.path.dirname(os.path.abspath(__file__))
AM = json.load(open(os.path.join(HERE, "..", "domains_am.json")))
WEST = json.load(open(os.path.join(HERE, "..", "domains_west.json")))
R = 6370000.0


def crop(src, dst, box, dom, parent, cen_moad):
    i0, i1, j0, j1 = box          # 1-based mass points, inclusive
    sl = {"west_east": slice(i0 - 1, i1), "west_east_stag": slice(i0 - 1, i1 + 1),
          "south_north": slice(j0 - 1, j1), "south_north_stag": slice(j0 - 1, j1 + 1)}
    with Dataset(src) as a, Dataset(dst, "w", format=a.data_model) as b:
        for n, d in a.dimensions.items():
            size = None if d.isunlimited() else (len(range(*sl[n].indices(len(d)))) if n in sl else len(d))
            b.createDimension(n, size)
        for n, v in a.variables.items():
            w = b.createVariable(n, v.datatype, v.dimensions)
            w.setncatts({k: v.getncattr(k) for k in v.ncattrs()})
            w[:] = v[tuple(sl.get(dn, slice(None)) for dn in v.dimensions)]
        att = {k: a.getncattr(k) for k in a.ncattrs()}
        nx, ny = i1 - i0 + 1, j1 - j0 + 1
        att["WEST-EAST_GRID_DIMENSION"] = np.int32(nx + 1)
        att["SOUTH-NORTH_GRID_DIMENSION"] = np.int32(ny + 1)
        for k, v in (("WEST-EAST_PATCH_END_UNSTAG", nx), ("WEST-EAST_PATCH_END_STAG", nx + 1),
                     ("SOUTH-NORTH_PATCH_END_UNSTAG", ny), ("SOUTH-NORTH_PATCH_END_STAG", ny + 1)):
            if k in att:
                att[k] = np.int32(v)
        lat_m, lon_m = b["XLAT_M"][0], b["XLONG_M"][0]
        lat_u, lon_u = b["XLAT_U"][0], b["XLONG_U"][0]
        lat_v, lon_v = b["XLAT_V"][0], b["XLONG_V"][0]
        c = lambda A: [float(A[0, 0]), float(A[-1, 0]), float(A[-1, -1]), float(A[0, -1])]   # SW NW NE SE
        P = Proj(proj="lcc", lat_1=WEST["map"]["truelat1"], lat_2=WEST["map"]["truelat2"], lon_0=WEST["map"]["stand_lon"],
                 lat_0=WEST["map"]["ref_lat"], R=R)
        # corners of the doubly staggered grid: half a cell beyond the mass corners
        xs, ys = P(lon_m, lat_m)
        h = dom["dx"] / 2
        cs = [P(xs[0, 0] - h, ys[0, 0] - h, inverse=True), P(xs[-1, 0] - h, ys[-1, 0] + h, inverse=True),
              P(xs[-1, -1] + h, ys[-1, -1] + h, inverse=True), P(xs[0, -1] + h, ys[0, -1] - h, inverse=True)]
        att["corner_lats"] = np.array(c(lat_m) + c(lat_u) + c(lat_v) + [p[1] for p in cs], np.float32)
        att["corner_lons"] = np.array(c(lon_m) + c(lon_u) + c(lon_v) + [p[0] for p in cs], np.float32)
        xc, yc = (xs[0, 0] + xs[-1, -1]) / 2, (ys[0, 0] + ys[-1, -1]) / 2
        lonc, latc = P(xc, yc, inverse=True)
        att["CEN_LAT"], att["CEN_LON"] = np.float32(latc), np.float32(lonc)
        att["MOAD_CEN_LAT"] = np.float32(cen_moad)
        att["i_parent_start"], att["j_parent_start"] = np.int32(dom["ips"]), np.int32(dom["jps"])
        att["i_parent_end"] = np.int32(dom["ips"] + nx // dom["ratio"]) if parent else np.int32(nx + 1)
        att["j_parent_end"] = np.int32(dom["jps"] + ny // dom["ratio"]) if parent else np.int32(ny + 1)
        b.setncatts(att)
        # check: the cut points are where the morning design says they are
        m = AM["map"]
        Q = Proj(proj="lcc", lat_1=m["truelat1"], lat_2=m["truelat2"], lon_0=m["stand_lon"], lat_0=m["ref_lat"], R=R)
        x0, y0 = Q(m["ref_lon"], m["ref_lat"])
        d1 = AM["domains"][0]
        o = (x0 - (d1["e_we"] / 2 - 1) * d1["dx"], y0 - (d1["e_sn"] / 2 - 1) * d1["dx"])
        if parent:
            o = (o[0] + (dom["ips"] - 1.5) * d1["dx"] + 0.5 * dom["dx"], o[1] + (dom["jps"] - 1.5) * d1["dx"] + 0.5 * dom["dx"])
        X, Y = Q(lon_m, lat_m)
        err = max(np.abs((X - o[0]) / dom["dx"] - np.arange(nx)[None, :]).max(), np.abs((Y - o[1]) / dom["dx"] - np.arange(ny)[:, None]).max())
        print(f"{os.path.basename(dst)}: {nx} x {ny}, centre {latc:.3f} N {lonc:.3f} E, "
              f"lat {float(lat_m.min()):.2f}..{float(lat_m.max()):.2f} lon {float(lon_m.min()):.2f}..{float(lon_m.max()):.2f}, "
              f"position check {err:.3f} cells")
        if err > 0.05:
            sys.exit(f"the cut grid {dst} is off by {err:.2f} cells")
        return latc


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    d1, d2 = AM["domains"]
    cen = crop(os.path.join(src, "geo_em.d01.nc"), os.path.join(out, "geo_em.d01.nc"), d1["crop"], d1, None, AM["map"]["ref_lat"])
    crop(os.path.join(src, "geo_em.d02.nc"), os.path.join(out, "geo_em.d02.nc"), d2["crop"], d2, d1, cen)


if __name__ == "__main__":
    main()
