#!/usr/bin/env python3
"""Fit and test the rain-spread potential (ingredients.py) on the backfilled past fields.

    ingr_fit.py DIR [OUT_COEF]

The reference rain of a day is the GFS first-day forecast (lead 0), as elsewhere on the page. The model is a
logistic regression of "5 mm or more at a point" on the ingredients of the same day (lead 0), fitted on two
weeks in three and tested on the third. Then, for each lead (2, 5, 8 days), the share of the Kingdom it
predicts from the forecast ingredients is compared with the reference share, against the share the GFS rain of
that lead gives. Prints the scores; writes the coefficients (fitted on all days) to OUT_COEF.
"""
import glob, json, os, sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingredients as I  # noqa: E402

TERMS = ["pwpct", "pw", "lapse", "t500", "vort500", "conv925", "div200", "rh700", "cape", "high"]
SQ = ["pwpct", "lapse"]
INTER = [("pwpct", "cape"), ("pwpct", "high"), ("pwpct", "vort500"), ("pwpct", "t500"), ("pwpct", "conv925"), ("cape", "high")]
THR = 5.0


def doy(dt):
    d = dt.timetuple().tm_yday - 1
    if dt.month > 2 and dt.year % 4 == 0:
        d -= 1
    return min(max(d, 0), 364)


def load(dirn):
    pwc = np.load(os.path.join(dirn, "pwclim.npz"))["pw"]
    data = {}
    for p in glob.glob(os.path.join(dirn, "*_*.npz")):
        b = os.path.basename(p)[:-4]
        if b == "pwclim":
            continue
        ds, k = b.split("_")
        D = datetime.strptime(ds, "%Y%m%d")
        z = dict(np.load(p))
        r = z["rain"]
        # a broken download (a wrong message read as rain) gives the whole Kingdom wet or absurd amounts: skip it
        if not np.isfinite(r).all() or r.max() > 400 or (r >= THR).mean() > 0.6 or \
                any(not np.isfinite(v).all() for v in z.values()):
            print("skip", b, flush=True)
            continue
        f = I.features(z, pwc[doy(D)])
        data[(D, int(k))] = (f, z["rain"])
    return data


def raw(f, mask):
    return np.stack([np.asarray(f[t], float)[mask] for t in TERMS], 1)


def design(f, mask, stats=None):
    X = raw(f, mask)
    if stats is None:
        stats = (X.mean(0), X.std(0) + 1e-6)
    Z = (X - stats[0]) / stats[1]
    sq = np.stack([Z[:, TERMS.index(t)] ** 2 for t in SQ], 1)
    it = np.stack([Z[:, TERMS.index(a)] * Z[:, TERMS.index(b)] for a, b in INTER], 1)
    return np.hstack([np.ones((len(Z), 1)), Z, sq, it]), stats


def fit_logit(X, y, w, l2=1.0, it=60):
    b = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ b))
        W = w * p * (1 - p) + 1e-9
        g = X.T @ (w * (y - p)) - l2 * np.r_[0, b[1:]]
        H = (X * W[:, None]).T @ X + l2 * np.diag(np.r_[0, np.ones(len(b) - 1)])
        step = np.linalg.solve(H, g)
        b += step
        if np.abs(step).max() < 1e-6:
            break
    return b


def main():
    dirn = sys.argv[1]
    data = load(dirn)
    mask = I.kingdom_mask() >= 0
    wpt = (np.cos(np.radians(I.LAT))[:, None] * np.ones((len(I.LAT), len(I.LON))))[mask]
    days = sorted({D for D, k in data if k == 0})
    leads = sorted({k for _, k in data})
    print("days", len(days), "leads", leads)
    truth = {D: data[(D, 0)][1][mask] for D in days}
    tcov = {D: float(((truth[D] >= THR) * wpt).sum() / wpt.sum()) for D in days}
    # fit on lead 0: two weeks in three train, the third tests
    test = lambda D: (D.toordinal() // 7) % 3 == 2
    Xs, ys, ws = [], [], []
    for D in days:
        if not test(D):
            Xs.append(data[(D, 0)][0]); ys.append((truth[D] >= THR).astype(float)); ws.append(wpt)
    X = np.vstack([raw(f, mask) for f in Xs])
    stats = (X.mean(0), X.std(0) + 1e-6)
    Xd = np.vstack([design(f, mask, stats)[0] for f in Xs])
    b = fit_logit(Xd, np.concatenate(ys), np.concatenate(ws))

    def pred_cover(f):
        p = 1 / (1 + np.exp(-design(f, mask, stats)[0] @ b))
        return float((p * wpt).sum() / wpt.sum())

    def score(name, pairs):
        a = np.array(pairs)
        if len(a) < 5:
            return
        r = np.corrcoef(a[:, 0], a[:, 1])[0, 1]
        mae = np.abs(a[:, 0] - a[:, 1]).mean()
        wet = a[:, 0] >= 0.05
        hit = ((a[:, 1] >= 0.05) & wet).sum() / max(wet.sum(), 1)
        fa = ((a[:, 1] >= 0.05) & ~wet).sum() / max((a[:, 1] >= 0.05).sum(), 1)
        q = a[:, 1] >= np.quantile(a[:, 1], 0.9)
        tq = a[:, 0] >= np.quantile(a[:, 0], 0.9)
        rank_hit = (q & tq).sum() / max(tq.sum(), 1)
        from scipy.stats import spearmanr
        rho = spearmanr(a[:, 0], a[:, 1]).correlation
        print(f"  {name:28s} n={len(a):3d} rank corr {rho:5.2f}  widest tenth caught {100 * rank_hit:3.0f}%  corr {r:5.2f}  mean abs err {100 * mae:4.1f} pts  "
              f"wide days caught {100 * hit:3.0f}%  false alarms {100 * fa:3.0f}%")

    print("test days (not used in the fit); truth = share of the Kingdom with 5 mm+ in the GFS first day")
    for k in leads:
        ing, gfs = [], []
        for D in days:
            if not test(D) or (D, k) not in data:
                continue
            f, rain = data[(D, k)]
            ing.append((tcov[D], pred_cover(f)))
            gfs.append((tcov[D], float(((rain[mask] >= THR) * wpt).sum() / wpt.sum())))
        print(f"lead {k} days:")
        score("ingredients index", ing)
        score("GFS rain of that lead", gfs)
        if ing and gfs:
            score("both averaged", [(t, (x + y) / 2) for (t, x), (_, y) in zip(ing, gfs)])
    # coefficients on all days, for the page
    allX = [data[(D, 0)][0] for D in days]
    X = np.vstack([raw(f, mask) for f in allX])
    stats = (X.mean(0), X.std(0) + 1e-6)
    Xd = np.vstack([design(f, mask, stats)[0] for f in allX])
    b = fit_logit(Xd, np.concatenate([(truth[D] >= THR).astype(float) for D in days]), np.concatenate([wpt for _ in days]))
    print("coefficients:", {t: round(float(x), 3) for t, x in zip(["b0"] + TERMS + [s + "^2" for s in SQ] + [a + "*" + c for a, c in INTER], b)})
    if len(sys.argv) > 2:
        c = {"b0": float(b[0]), "terms": {t: [float(stats[0][i]), float(stats[1][i]), float(b[1 + i])] for i, t in enumerate(TERMS)},
             "sq": {t: float(b[1 + len(TERMS) + j]) for j, t in enumerate(SQ)},
             "inter": [[a, c, float(b[1 + len(TERMS) + len(SQ) + j])] for j, (a, c) in enumerate(INTER)],
             "thr_mm": THR, "days": len(days),
             "fitted": datetime.utcnow().strftime("%Y-%m-%d")}
        json.dump(c, open(sys.argv[2], "w"), indent=1)
        print("written", sys.argv[2])


if __name__ == "__main__":
    main()
