#!/usr/bin/env python3
"""Study (Fahad, 16 Nov 2026): our Rossby/Kelvin families of the 200 hPa velocity potential against variants closer
to Dr Khalid's SCORPION idea (the slow convectively coupled wave, ~5 m/s, kept; his 16-day and 47-day cycles),
over 26 wet seasons of NCEP/NCAR reanalysis and CHIRPS rain (the series of method_test.py). Prints only.

    scorp_test.py LONG_JSON HIST_DIR
"""
import json, os, sys
from datetime import date
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sphere, wkfilt, mjofilt  # noqa: E402
from method_test import load_hist, harmonic_clim, trailing_mean, LAT, LON, LAT8, HALVES  # noqa: E402
from tropics_long import GROUPS, cv_r2  # noqa: E402

EARTH, DAY = 40.03e6, 86400.0
NS = dict(cmin=0.0, cmax=1e9)
F0 = wkfilt.FAMILIES
VAR = {
    "ros": F0["ros"],
    "kel": F0["kel"],
    "kel_nospeed": dict(F0["kel"], **NS),
    "east16": dict(east=True, kmin=1, kmax=9, pmin=10, pmax=24, **NS),
    "east47": dict(east=True, kmin=1, kmax=5, pmin=30, pmax=70, **NS),
    "west47": dict(east=False, kmin=1, kmax=5, pmin=30, pmax=70, **NS),
}


def filt(X, east, kmin, kmax, pmin, pmax, cmin, cmax):
    nt, ny, nx = X.shape
    Y = X - X.mean(0)
    F = np.fft.fft2(Y, axes=(0, 2))
    f = np.fft.fftfreq(nt)[:, None]
    k = np.fft.fftfreq(nx, 1.0 / nx)[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.abs(f) * EARTH / np.abs(k) / DAY
    dirn = (f * k < 0) if east else (f * k > 0)
    keep = ((np.abs(k) >= kmin) & (np.abs(k) <= kmax) & (np.abs(f) >= 1 / pmax) & (np.abs(f) <= 1 / pmin)
            & dirn & (c >= cmin) & (c <= cmax))
    F *= keep[:, None, :]
    return np.real(np.fft.ifft2(F, axes=(0, 2)))


def main():
    rows = json.load(open(sys.argv[1]))
    days, chi, z8, z5 = load_hist(sys.argv[2])
    del z5
    an = chi - harmonic_clim(chi, days)
    an = an - trailing_mean(an)
    del chi
    s_, n_, w_, e_ = wkfilt.KSA
    jj = (LAT >= s_ - 5) & (LAT <= n_ + 5)                      # rows around the Kingdom only (the filter is per row)
    X = np.stack([-sphere.smooth(-a / 1e6)[jj] for a in an]).astype(np.float64)   # chi anomaly, 10^6 m2/s, T30
    del an
    la = LAT[jj]
    bj = (la >= s_) & (la <= n_)
    bi = (LON >= w_) & (LON <= e_)
    idx = {name: filt(X, **p)[:, bj][:, :, bi].mean((1, 2)) for name, p in VAR.items()}
    zf = mjofilt.mjo_filter(z8.astype(np.float64), kmax=3)
    idx["mf"] = np.array([mjofilt.box(zf[k], *mjofilt.KSA, lat=LAT8, lon=LON) for k in range(len(days))])
    del zf, z8
    idx["ros+kel"] = idx["ros"] / idx["ros"].std() + idx["kel"] / idx["kel"].std()
    idx["ros+kel_nospeed"] = idx["ros"] / idx["ros"].std() + idx["kel_nospeed"] / idx["kel_nospeed"].std()
    idx["ros+east47"] = idx["ros"] / idx["ros"].std() + idx["east47"] / idx["east47"].std()
    idx["ros+mf"] = idx["ros"] / idx["ros"].std() + idx["mf"] / idx["mf"].std()
    print("index std:", {k: round(float(v.std()), 2) for k, v in idx.items()}, flush=True)
    print("corr east47 vs mf (component at 850):", round(float(np.corrcoef(idx["east47"], idx["mf"])[0, 1]), 2),
          " east47 vs kel_nospeed:", round(float(np.corrcoef(idx["east47"], idx["kel_nospeed"])[0, 1]), 2), flush=True)

    ix = {d: k for k, d in enumerate(days)}
    rows = [r for r in rows if date.fromisoformat(r["d"]) in ix and all(g in r for g in GROUPS)]
    rd = [date.fromisoformat(r["d"]) for r in rows]
    K = np.array([ix[d] for d in rd])
    mon = np.array([d.month for d in rd])
    season = np.array([d.year if d.month >= 11 else d.year - 1 for d in rd])
    print("rain days joined", len(rows), rd[0], rd[-1], flush=True)
    for g in GROUPS:
        sp = np.array([r[g][0] for r in rows])
        has = np.array([len(r[g]) == 4 for r in rows])
        print(f"\n######## {g}")
        for h, ms in list(HALVES.items()) + [("الموسم كله", (11, 12, 1, 2, 3, 4))]:
            s = np.isin(mon, ms) & has
            thr = max(np.quantile(sp[s], 0.9), 0.03)
            wide = s & (sp >= thr)
            print(f"  == {h}: days {s.sum()}, wide days {wide.sum()} (spread >= {100*thr:.0f}%)")
            for name, v in idx.items():
                x = v[K]
                sup = x <= -v.std() / 3
                on, off = s & sup, s & ~sup
                y = np.sqrt(sp[s])
                r2 = cv_r2(x[s, None], y, season[s])
                print(f"    {name:16s} on {100*on.sum()/s.sum():3.0f}% | spread on {100*sp[on].mean():4.1f}% off {100*sp[off].mean():4.1f}% "
                      f"(x{sp[on].mean()/max(sp[off].mean(),1e-6):.2f}) | in {100*(wide & sup).sum()/max(wide.sum(),1):3.0f}% of wide days "
                      f"| corr {np.corrcoef(x[s], sp[s])[0,1]:+.3f} | cv share {100*r2:.2f}%")
            # added value on top of what the score already has (ros + mf)
            y = np.sqrt(sp[s])
            base = np.column_stack([idx["ros"][K], idx["mf"][K]])[s]
            b0 = cv_r2(base, y, season[s])
            for name in ("kel", "kel_nospeed", "east16", "east47", "west47"):
                b1 = cv_r2(np.column_stack([base, idx[name][K][s]]), y, season[s])
                print(f"    added to ros+mf: {name:12s} {100*b0:.2f}% -> {100*b1:.2f}%")


if __name__ == "__main__":
    main()
