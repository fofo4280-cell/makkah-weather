#!/usr/bin/env python3
"""Low-level warm event test (Fahad, 19 Nov 2026): PERSIANN daily rain 1 Sep-19 Nov 2026 over Tihama, Makkah and
the Hijaz/Asir escarpment (16-24 N, 38-44 E). Saves the median of PDIR-Now, CCS and PERSIANN on the 0.04 grid."""
import sys
from datetime import date
import numpy as np
import obs_box as ob

ob.S, ob.N, ob.W, ob.E = 16.0, 24.0, 38.0, 44.0
ob.D0, ob.D1 = date(2026, 9, 1), date(2026, 11, 20)


def main():
    fam = [("pdir", "https://persiann.eng.uci.edu/CHRSdata/PDIRNow/PDIRNowdaily/", 3000, 9000, 0.04, 60.0),
           ("ccs", "https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/daily/", 3000, 9000, 0.04, 60.0),
           ("pers", "https://persiann.eng.uci.edu/CHRSdata/PERSIANN/daily/", 480, 1440, 0.25, 60.0)]
    got = {n: ob.persiann_family(n, b, ny, nx, r, t) for n, b, ny, nx, r, t in fam}
    days = sorted(set(got["pdir"]) | set(got["ccs"]))
    out, kept = [], []
    for d in days:
        st = [got[n][d] for n in ("pdir", "ccs") if d in got[n]]
        if d in got["pers"]:
            if st:
                ny, nx = st[0].shape; P = got["pers"][d]
                jj = np.minimum((np.arange(ny) * 0.04 / 0.25).astype(int), P.shape[0] - 1)
                ii = np.minimum((np.arange(nx) * 0.04 / 0.25).astype(int), P.shape[1] - 1)
                st.append(P[jj][:, ii])
        st = [s for s in st if s is not None]
        out.append(np.nanmedian(np.stack(st), 0).astype(np.float16)); kept.append(d)
    np.savez_compressed(sys.argv[1], days=np.array(kept), rain=np.stack(out),
                        lat=ob.N - 0.02 - 0.04 * np.arange(out[0].shape[0]), lon=ob.W + 0.02 + 0.04 * np.arange(out[0].shape[1]))
    print("saved", len(kept), out[0].shape, flush=True)


if __name__ == "__main__":
    main()
