#!/usr/bin/env python3
"""Add the 'cop90' terrain source (Copernicus DEM, 90 m) to the HGT_M entry of GEOGRID.TBL.

Domains whose geog_data_res is 'cop90+default' then take terrain from it and fall back to the
standard 30-second data wherever it has no coverage.
"""
import sys

path = sys.argv[1]
lines = open(path).read().split("\n")
if any("topo_cop90" in l for l in lines):
    print("already patched"); sys.exit(0)

out, done = [], False
for l in lines:
    out.append(l)
    if not done and l.strip().replace(" ", "") == "name=HGT_M":
        out.append("        interp_option = cop90:average_gcell(4.0)+four_pt+average_4pt")
        out.append("        rel_path = cop90:topo_cop90/")
        done = True
if not done:
    sys.exit("HGT_M entry not found")
open(path, "w").write("\n".join(out))
print("patched")
