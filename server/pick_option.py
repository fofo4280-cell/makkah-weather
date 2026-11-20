#!/usr/bin/env python3
"""Pick the configure menu number for a GNU/gfortran build.

wrf: the (dmpar) entry on the GNU gfortran/gcc line.
wps: the 'gfortran (serial)' entry (with GRIB2).
Prints the number, exits 1 if not found.
"""
import re, sys

kind, path = sys.argv[1], sys.argv[2]
text = open(path, errors="replace").read()

if kind == "wrf":
    best = None
    for line in text.splitlines():
        if "(dmpar)" not in line:
            continue
        low = line.lower()
        if "gfortran" in low or "gnu" in low or "gcc compiler" in low:
            if any(bad in low for bad in ("pgi", "intel", "nvhpc", "armclang", "g95", "flang", "cray", "xl ")):
                continue
            m = re.search(r"(\d+)\.\s*\(dmpar\)", line)
            if m:
                score = 2 if "gfortran/gcc" in low or "($sfc/$scc)" in low else 1
                if best is None or score > best[0]:
                    best = (score, m.group(1))
    if best:
        print(best[1]); sys.exit(0)
elif kind == "wps":
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\.\s+(.*)\((serial)\)\s*$", line)
        if m and "gfortran" in m.group(2).lower() and "linux" in m.group(2).lower():
            print(m.group(1)); sys.exit(0)
sys.exit(1)
