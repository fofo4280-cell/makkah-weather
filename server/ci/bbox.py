#!/usr/bin/env python3
"""Print 'south north west east' of a domain in domains.json (uses the WRF Lambert grid geometry)."""
import json, math, os, sys
from pyproj import Proj

cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", os.environ.get("SWRF_DOMAINS") or "domains.json")))
m = cfg["map"]
P = Proj(proj="lcc", lat_1=m["truelat1"], lat_2=m["truelat2"], lon_0=m["stand_lon"], lat_0=m["ref_lat"], R=6370000)
D = {d["id"]: d for d in cfg["domains"]}
order = [d["id"] for d in cfg["domains"]]
x0, y0 = P(m["ref_lon"], m["ref_lat"])
d = cfg["domains"][0]
org = {d["id"]: (x0 - (d["e_we"] / 2 - 1) * d["dx"], y0 - (d["e_sn"] / 2 - 1) * d["dx"])}  # mass point (1,1)
for k in order[1:]:
    d, p = D[k], D[order[order.index(k) - 1]]
    po = org[p["id"]]
    org[k] = (po[0] + (d["ips"] - 1.5) * p["dx"] + 0.5 * d["dx"], po[1] + (d["jps"] - 1.5) * p["dx"] + 0.5 * d["dx"])
k = sys.argv[1]
d = D[k]
xs = [org[k][0], org[k][0] + (d["e_we"] - 2) * d["dx"]]
ys = [org[k][1], org[k][1] + (d["e_sn"] - 2) * d["dx"]]
pts = [P(x, y, inverse=True) for x in xs for y in ys]
# edges bulge in lat/lon, so sample along them too
for t in [i / 20 for i in range(21)]:
    for x in xs:
        pts.append(P(x, ys[0] + t * (ys[1] - ys[0]), inverse=True))
    for y in ys:
        pts.append(P(xs[0] + t * (xs[1] - xs[0]), y, inverse=True))
lons, lats = [p[0] for p in pts], [p[1] for p in pts]
print(f"{min(lats):.2f} {max(lats):.2f} {min(lons):.2f} {max(lons):.2f}")
