#!/usr/bin/env python3
"""Low-level warm event test for the whole Kingdom (Fahad, 19 Nov 2026): PERSIANN daily rain over 15-33 N, 34-56 E on
the days of the Makkah test (Nov 2024-May 2025, Oct-Dec 2025, 1 Sep-19 Nov 2026), median of PDIR-Now, CCS and PERSIANN,
averaged to 0.12 degrees (3x3 of 0.04)."""
import sys
from datetime import date, timedelta
import numpy as np
import obs_box as ob

ob.S, ob.N, ob.W, ob.E = 15.0, 33.0, 34.0, 56.0
RANGES = [(date(2024, 11, 1), date(2025, 6, 1)), (date(2025, 10, 1), date(2026, 1, 1)), (date(2026, 9, 1), date(2026, 11, 20))]


def days():
    for a, b in RANGES:
        d = a
        while d < b:
            yield d
            d += timedelta(1)


ob.days = days
_crop = ob.crop_global
ob.crop_global = lambda *a: _crop(*a).copy()      # a view would keep each whole global day in memory (runner died)


def main():
    fam = [("pdir", "https://persiann.eng.uci.edu/CHRSdata/PDIRNow/PDIRNowdaily/", 3000, 9000, 0.04, 60.0),
           ("ccs", "https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/daily/", 3000, 9000, 0.04, 60.0),
           ("pers", "https://persiann.eng.uci.edu/CHRSdata/PERSIANN/daily/", 480, 1440, 0.25, 60.0)]
    got = {n: ob.persiann_family(n, b, ny, nx, r, t) for n, b, ny, nx, r, t in fam}
    out, kept = [], []
    for d in sorted(set(got["pdir"]) | set(got["ccs"])):
        st = [got[n][d] for n in ("pdir", "ccs") if d in got[n]]
        ny, nx = st[0].shape
        if d in got["pers"]:
            P = got["pers"][d]
            jj = np.minimum((np.arange(ny) * 0.04 / 0.25).astype(int), P.shape[0] - 1)
            ii = np.minimum((np.arange(nx) * 0.04 / 0.25).astype(int), P.shape[1] - 1)
            st.append(P[jj][:, ii])
        m = np.nanmedian(np.stack(st), 0)
        m = m[:ny // 3 * 3, :nx // 3 * 3].reshape(ny // 3, 3, nx // 3, 3)
        out.append(np.nanmean(m, (1, 3)).astype(np.float16)); kept.append(d)
        got["pdir"].pop(d, None); got["ccs"].pop(d, None)
    np.savez_compressed(sys.argv[1], days=np.array(kept), rain=np.stack(out),
                        lat=ob.N - 0.06 - 0.12 * np.arange(out[0].shape[0]), lon=ob.W + 0.06 + 0.12 * np.arange(out[0].shape[1]))
    print("saved", len(kept), out[0].shape, flush=True)


if __name__ == "__main__":
    main()
