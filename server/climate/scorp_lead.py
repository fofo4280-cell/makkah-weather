#!/usr/bin/env python3
"""Study (Fahad, 17 Nov 2026): the Doctor's slow eastward 47-day cycle together with our Rossby family
(200 hPa velocity potential over the Kingdom box), over 26 wet seasons (NCEP/NCAR + CHIRPS), BY LEAD.
Each issue day t is filtered as the live page does: the past 400 days only, then
  rt0  : nothing after day t (no forecast)            -> the pessimistic case
  rt15 : the next 15 real days as a 'perfect forecast' -> the optimistic case (GFS is worse than this)
then the index at t+L (L = 0, 3, 6, 9) is set against the rain spread on t+L (Hijaz, Kingdom).
Also the hindsight index (whole record) for reference. Prints only.

    scorp_lead.py LONG_JSON HIST_DIR
"""
import json, os, sys
from datetime import date
import numpy as np
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sphere, wkfilt  # noqa: E402
from method_test import load_hist, harmonic_clim, trailing_mean, LAT, LON  # noqa: E402

NS = dict(cmin=0.0, cmax=1e9)
FAM = {"ros": wkfilt.FAMILIES["ros"], "east47": dict(east=True, kmin=1, kmax=5, pmin=30, pmax=70, **NS)}
LEADS = (0, 3, 6, 9)
WIN = 400
GR = ("الحجاز", "المملكة")


def wk(X, east, kmin, kmax, pmin, pmax, cmin, cmax, pad=120, taper=20):
    """wkfilt.wk_filter, but returning the padded tail too (the filter's own forecast past the data end)."""
    nt, ny, nx = X.shape
    Y = X - X.mean(0)
    t = np.arange(nt, dtype=float) - (nt - 1) / 2
    Y = Y - ((Y * t[:, None, None]).sum(0) / (t ** 2).sum()) * t[:, None, None]
    w = np.ones(nt)
    w[:taper] = 0.5 * (1 - np.cos(np.pi * np.arange(taper) / taper))
    Y = np.concatenate([Y * w[:, None, None], np.zeros((pad, ny, nx))])
    F = np.fft.fft2(Y, axes=(0, 2))
    f = np.fft.fftfreq(Y.shape[0])[:, None]
    k = np.fft.fftfreq(nx, 1.0 / nx)[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.abs(f) * wkfilt.EARTH / np.abs(k) / wkfilt.DAY
    dirn = (f * k < 0) if east else (f * k > 0)
    keep = ((np.abs(k) >= kmin) & (np.abs(k) <= kmax) & (np.abs(f) >= 1 / pmax) & (np.abs(f) <= 1 / pmin)
            & dirn & (c >= cmin) & (c <= cmax))
    F *= keep[:, None, :]
    return np.real(np.fft.ifft2(F, axes=(0, 2)))


def main():
    rows = json.load(open(sys.argv[1]))
    days, chi, z8, z5 = load_hist(sys.argv[2])
    del z8, z5
    an = chi - harmonic_clim(chi, days)
    an = an - trailing_mean(an)
    del chi
    s_, n_, w_, e_ = wkfilt.KSA
    bj = (LAT >= s_) & (LAT <= n_)
    bi = (LON >= w_) & (LON <= e_)
    X = np.stack([-sphere.smooth(-a / 1e6)[bj] for a in an]).astype(np.float64)   # box rows, all longitudes
    del an
    box = lambda A: A[:, :, bi].mean((1, 2))  # noqa: E731

    hind = {n: box(wk(X, **p)[:len(days)]) for n, p in FAM.items()}
    sd = {n: v.std() for n, v in hind.items()}
    hind["ros+east47"] = hind["ros"] / sd["ros"] + hind["east47"] / sd["east47"]
    sd["ros+east47"] = hind["ros+east47"].std()
    print("index std", {k: round(float(v), 3) for k, v in sd.items()}, flush=True)

    ix = {d: k for k, d in enumerate(days)}
    rain = {}
    for r in rows:
        d = date.fromisoformat(r["d"])
        if d in ix and all(g in r for g in GR):
            rain[ix[d]] = [r[g][0] for g in GR]
    issues = [k for k in sorted(rain) if k >= WIN and k + 15 < len(days) and days[k].month in (11, 12, 1, 2, 3, 4)]
    issues = issues[::2]
    print("issue days", len(issues), days[issues[0]], days[issues[-1]], flush=True)

    # forecasts: fc[mode][name][lead] -> list aligned with issues
    names = ("ros", "east47", "ros+east47")
    fc = {m: {n: {L: [] for L in LEADS} for n in names} for m in ("rt0", "rt15")}
    for j, k in enumerate(issues):
        for mode, extra in (("rt0", 0), ("rt15", 15)):
            seg = X[k - WIN + 1:k + 1 + extra]
            out = {n: box(wk(seg, **p)) for n, p in FAM.items()}
            out["ros+east47"] = out["ros"] / sd["ros"] + out["east47"] / sd["east47"]
            for n in names:
                for L in LEADS:
                    fc[mode][n][L].append(out[n][WIN - 1 + L])
        if j % 300 == 0:
            print("  issue", j, days[k], flush=True)

    season = np.array([days[k].year if days[k].month >= 11 else days[k].year - 1 for k in issues])
    for gi, g in enumerate(GR):
        print(f"\n######## {g}  (rain spread on day t+L, CHIRPS >= 5 mm)")
        for L in LEADS:
            ok = np.array([(k + L) in rain for k in issues])
            sp = np.array([rain.get(k + L, [np.nan, np.nan])[gi] for k in issues])
            thr = max(np.nanquantile(sp[ok], 0.9), 0.03)
            wide = ok & (sp >= thr)
            base = 100 * wide.sum() / ok.sum()
            print(f"  -- lead {L}: days {ok.sum()}, wide days {wide.sum()} (spread >= {100*thr:.0f}%), base wide {base:.0f}%")
            for n in names:
                for mode, x in (("hind", np.array([hind[n][k + L] if n in hind else np.nan for k in issues])),
                                ("rt0", np.array(fc["rt0"][n][L])), ("rt15", np.array(fc["rt15"][n][L]))):
                    rho = spearmanr(x[ok], sp[ok]).correlation
                    sup = ok & (x <= -sd[n] / 3)
                    off = ok & ~sup
                    ratio = np.nanmean(sp[sup]) / max(np.nanmean(sp[off]), 1e-6)
                    hit = 100 * (wide & sup).sum() / max(wide.sum(), 1)
                    wsup = 100 * (wide & sup).sum() / max(sup.sum(), 1)
                    # season-by-season sign of the correlation (stability)
                    pos = 0; tot = 0
                    for s in sorted(set(season)):
                        m = ok & (season == s)
                        if m.sum() > 20 and np.nanstd(sp[m]) > 0:
                            tot += 1; pos += spearmanr(x[m], sp[m]).correlation < 0
                    print(f"    {n:11s} {mode:5s} rho {rho:+.3f} | spread x{ratio:.2f} | wide days supported {hit:3.0f}% "
                          f"| wide when supported {wsup:3.0f}% (base {base:.0f}%) | seasons right sign {pos}/{tot}")


if __name__ == "__main__":
    main()
