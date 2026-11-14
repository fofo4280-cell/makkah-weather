#!/usr/bin/env python3
"""How much of the rain over each part of the Kingdom in the wet season (November to April) the tropical system
explains on its own, against the troughs and moisture surges (Fahad, 14 Nov 2026, after Khalid Al-Otaibi's view that
the tropics are the best guide to a fertile month).

    tropics_share.py INGR_DIR MJO_JSON

Truth: the share of each part with 5 mm or more in the GFS first day (the backfilled fields of ingr-data, 1 degree).
Tropical drivers: the isolated MJO component over the Kingdom (mjof.z_ksa), the RMM (r1, r2, and the amplitude in the
phases that favour Arabia), the longitude of the MJO envelope centre.
Trough and moisture drivers: 500 hPa height and vorticity and precipitable water over each part, as departures from
their 31-day running mean (the passing troughs and surges, not the season).
Scores: cross-validated R2 (leave one month out) of linear fits on daily values, and on 10-day means; composites.
"""
import glob, json, os, sys
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingredients as I  # noqa: E402

GROUPS = {"الحجاز (مكة والمدينة)": [3, 2], "الجنوب الغربي (عسير وجازان والباحة ونجران)": [9, 11, 12, 8],
          "الشمال (تبوك والجوف والحدود الشمالية وحائل)": [7, 6, 4, 5], "الوسط (الرياض والقصيم)": [1, 10],
          "الشرق": [0], "المملكة كلها": list(range(13))}
WET = {11, 12, 1, 2, 3, 4}


def load(dirn):
    out = {}
    for p in sorted(glob.glob(os.path.join(dirn, "*_0.npz"))):
        d = date.fromisoformat(os.path.basename(p)[:8][:4] + "-" + os.path.basename(p)[4:6] + "-" + os.path.basename(p)[6:8])
        z = dict(np.load(p))
        r = z["rain"]
        if not np.isfinite(r).all() or r.max() > 400 or (r >= 5).mean() > 0.6:
            continue
        out[d] = z
    return out


def running(x, n=31):
    x = np.asarray(x, float)
    k = n // 2
    out = np.full_like(x, np.nan)
    for i in range(len(x)):
        a, b = max(0, i - k), min(len(x), i + k + 1)
        out[i] = np.nanmean(x[a:b])
    return out


def cv_r2(X, y, groups):
    """leave-one-group-out R2 of a ridge-regularised linear fit"""
    X = np.column_stack([np.ones(len(y)), X])
    pred = np.full(len(y), np.nan)
    for g in sorted(set(groups)):
        tr, te = groups != g, groups == g
        if tr.sum() < X.shape[1] + 5:
            continue
        A = X[tr]; lam = 1.0 * np.eye(X.shape[1]); lam[0, 0] = 0
        mu = A[:, 1:].mean(0); sd = A[:, 1:].std(0) + 1e-9
        As = A.copy(); As[:, 1:] = (A[:, 1:] - mu) / sd
        Xs = X[te].copy(); Xs[:, 1:] = (X[te][:, 1:] - mu) / sd
        b = np.linalg.solve(As.T @ As + lam, As.T @ y[tr])
        pred[te] = Xs @ b
    ok = np.isfinite(pred)
    return 1 - np.sum((y[ok] - pred[ok]) ** 2) / np.sum((y[ok] - y[ok].mean()) ** 2)


def main():
    data = load(sys.argv[1])
    st = json.load(open(sys.argv[2]))
    m = st["mjof"]
    zk = {date.fromisoformat(d): z for d, z in zip(m["days"], m["z_ksa"])}
    core = {date.fromisoformat(d): c for d, c in zip(m["days"], m["core"])}
    import daily
    rmm = {d: (r1, r2, ph, amp) for d, r1, r2, ph, amp in daily.read_rmm()}
    days = [d for d in sorted(data) if d in zk and d in rmm]
    print("days with all data", len(days), days[0], days[-1], flush=True)
    mask = I.kingdom_mask()
    w = np.cos(np.radians(I.LAT))[:, None] * np.ones(mask.shape)

    def gmean(a, ids):
        r = np.isin(mask, ids)
        return float((a * w)[r].sum() / w[r].sum())

    feats, truth = {}, {g: [] for g in GROUPS}
    raw = {g: {"z": [], "vo": [], "pw": []} for g in GROUPS}
    for d in days:
        z = data[d]
        f = I.features(z)
        for g, ids in GROUPS.items():
            truth[g].append(gmean((z["rain"] >= 5).astype(float), ids))
            raw[g]["z"].append(gmean(z["z500"], ids)); raw[g]["vo"].append(gmean(f["vort500"], ids))
            raw[g]["pw"].append(gmean(z["pw"], ids))
    for g in GROUPS:
        feats[g] = np.column_stack([np.array(raw[g]["z"]) - running(raw[g]["z"]),
                                    np.array(raw[g]["vo"]) - running(raw[g]["vo"]),
                                    np.array(raw[g]["pw"]) - running(raw[g]["pw"]), np.array(raw[g]["pw"])])
    fav = lambda d: rmm[d][3] if rmm[d][2] in (7, 8, 1, 2) and rmm[d][3] >= 1 else 0.0
    T = np.array([[zk[d], rmm[d][0], rmm[d][1], fav(d), np.cos(np.radians(core[d])), np.sin(np.radians(core[d]))] for d in days])
    wet = np.array([d.month in WET for d in days])
    month = np.array([d.year * 100 + d.month for d in days])
    dec = np.array([(d - days[0]).days // 10 for d in days])
    print(f"wet-season days {wet.sum()}, months {sorted(set(month[wet]))}\n")

    print("== Daily rain spread (wet season), cross-validated R2 (share of day-to-day variation explained)")
    for g in GROUPS:
        y = np.sqrt(np.array(truth[g]))[wet]
        rt = cv_r2(T[wet], y, month[wet]); re = cv_r2(feats[g][wet], y, month[wet])
        rb = cv_r2(np.hstack([T[wet], feats[g][wet]]), y, month[wet])
        print(f"{g}: tropics {100*rt:5.1f}%  troughs+moisture {100*re:5.1f}%  both {100*rb:5.1f}%  "
              f"| tropics alone add {100*(rb-re):5.1f}%  troughs alone add {100*(rb-rt):5.1f}%  mean daily spread {100*np.mean(np.array(truth[g])[wet]):.1f}%")

    print("\n== 10-day means (wet season): R2 in sample (few windows, indicative only)")
    for g in GROUPS:
        ys, Ts, Es = [], [], []
        for k in sorted(set(dec[wet])):
            s = wet & (dec == k)
            if s.sum() < 7:
                continue
            ys.append(np.mean(np.array(truth[g])[s])); Ts.append(T[s].mean(0)); Es.append(feats[g][s].mean(0))
        ys, Ts, Es = np.array(ys), np.array(Ts), np.array(Es)
        def r2(X):
            X = np.column_stack([np.ones(len(ys)), X]); b = np.linalg.lstsq(X, ys, rcond=None)[0]
            return 1 - np.sum((ys - X @ b) ** 2) / np.sum((ys - ys.mean()) ** 2)
        c = np.corrcoef(Ts[:, 0], ys)[0, 1]; cf = np.corrcoef(Ts[:, 3], ys)[0, 1]
        print(f"{g}: n={len(ys)} corr(component, rain) {c:+.2f}  corr(MJO favourable amplitude, rain) {cf:+.2f}  "
              f"R2 component+MJO {100*r2(Ts[:, [0, 3]]):.0f}%  R2 trough+moisture {100*r2(Es[:, [0, 2]]):.0f}%")

    print("\n== Monthly mean daily spread (%) with the mean component (m) and the share of days with the MJO in a favourable phase")
    for mo in sorted(set(month[wet])):
        s = month == mo
        print(f"{mo}: component {np.mean(T[s, 0]):+5.1f} m, favourable MJO days {100*np.mean(T[s, 3] > 0):3.0f}% | "
              + "  ".join(f"{g.split(' ')[0]} {100*np.mean(np.array(truth[g])[s]):4.1f}" for g in GROUPS))

    print("\n== Composites (wet season): mean daily spread (%) by the component over the Kingdom")
    bins = [(-99, -6), (-6, -2), (-2, 2), (2, 6), (6, 99)]
    for g in GROUPS:
        y = np.array(truth[g])
        row = []
        for a, b in bins:
            s = wet & (T[:, 0] > a) & (T[:, 0] <= b)
            row.append(f"{a if a > -99 else '..'}..{b if b < 99 else '..'}: {100*np.mean(y[s]):4.1f} (n={s.sum()})" if s.sum() else "-")
        s1, s0 = wet & (T[:, 3] > 0), wet & (T[:, 3] == 0)
        print(f"{g}: " + " | ".join(row) + f" || MJO favourable {100*np.mean(y[s1]):.1f} (n={s1.sum()}) vs not {100*np.mean(y[s0]):.1f} (n={s0.sum()})")


if __name__ == "__main__":
    main()
