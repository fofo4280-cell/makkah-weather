#!/usr/bin/env python3
"""The full-method test (Fahad, 15 Nov 2026): every driver our report reads, rebuilt the same way from the NCEP/NCAR
reanalysis for 2000-2026, against the CHIRPS rain of 26 wet seasons (the series of tropics_long.py).

    method_test.py LONG_JSON HIST_DIR

Drivers, as in daily.py and bigreport.py:
  mjo     the RMM in phases 7, 8, 1, 2 with amplitude 1 or more (and phases 8 and 1 alone, from the long test)
  warm    the warm event: minus the 200 hPa velocity potential anomaly (climatology removed, then the mean of the
          previous 120 days), planetary scales (T30); its zonal wave-1 over 15S-15N; supportive when the centre is
          in the favourable sector (250E through 0 to 55E) with amplitude 4 or more; also its value over 45E
  ros/kel the Rossby and Kelvin families of the 200 hPa velocity potential anomaly (wkfilt) over the Kingdom box;
          supportive when at or below minus a third of their spread (divergence aloft)
  mjof    the isolated MJO component of the height (mjofilt; 850 hPa here for the 800 hPa of the GFS) over the
          Kingdom box; supportive when at or below minus a third of its spread
  trough  the 500 hPa synoptic waves (zonal wavenumbers 4-8, waves.band) at their lowest over each part;
          a trough when -25 m or lower
  pw      precipitable water over each part as a percentage of its normal for the date; surge at 150 %
The report's strength score (0..5) from the same pieces.
Note: the filters here see the whole series (past and future), so they are cleaner than in daily use, where the
last days are the least certain.
"""
import glob, json, os, sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sphere, wkfilt, mjofilt, waves, sa_geo  # noqa: E402
import bigpic as B  # noqa: E402
from tropics_long import GROUPS, cv_r2, running  # noqa: E402

LAT = np.linspace(90, -90, 73)
LON = np.arange(0, 360, 2.5)
LAT8 = LAT[20:53]          # 40N..40S
LAT5 = LAT[16:33]          # 50N..10N
HALVES = {"نوفمبر-يناير": (11, 12, 1), "فبراير-أبريل": (2, 3, 4)}
SUBS = ["الحجاز", "الجنوب الغربي", "الشمال", "الوسط", "الشرق"]


def load_hist(dirn):
    parts = sorted(glob.glob(os.path.join(dirn, "**", "*.npz"), recursive=True))
    days, chi, z8, z5 = [], [], [], []
    for p in parts:
        z = np.load(p)
        days += list(z["days"]); chi.append(z["chi"]); z8.append(z["z850"]); z5.append(z["z500"])
        print("chunk", os.path.basename(p), len(z["days"]), z["days"][0], z["days"][-1], flush=True)
    days = [date.fromisoformat(str(d)) for d in days]
    chi, z8, z5 = np.concatenate(chi), np.concatenate(z8), np.concatenate(z5)
    o = np.argsort([d.toordinal() for d in days])
    days = [days[i] for i in o]; chi, z8, z5 = chi[o], z8[o], z5[o]
    gaps = [(a, b) for a, b in zip(days, days[1:]) if (b - a).days != 1]
    print("days", len(days), days[0], days[-1], "gaps", gaps[:5], flush=True)
    return days, chi, z8, z5


def harmonic_clim(X, days, n=3):
    """the mean annual cycle (mean and n harmonics) of X (days, ...), evaluated on the days"""
    t = np.array([d.timetuple().tm_yday for d in days], float) * 2 * np.pi / 365.25
    A = np.column_stack([np.ones_like(t)] + [f(k * t) for k in range(1, n + 1) for f in (np.cos, np.sin)])
    flat = X.reshape(len(days), -1).astype(np.float64)
    b = np.linalg.lstsq(A, flat, rcond=None)[0]
    return (A @ b).reshape(X.shape).astype(np.float32)


def trailing_mean(X, n=120):
    """mean of the previous n days (excluding the day), the first days use what they have"""
    c = np.cumsum(np.concatenate([np.zeros((1,) + X.shape[1:], np.float64), X.astype(np.float64)]), axis=0)
    out = np.empty_like(X)
    for k in range(len(X)):
        a = max(0, k - n)
        out[k] = (c[k] - c[a]) / max(k - a, 1) if k > 0 else 0.0
    return out


def drivers(days, chi, z8, z5):
    # the warm event, as daily.py
    an = chi - harmonic_clim(chi, days)
    an = an - trailing_mean(an)
    W = np.stack([sphere.smooth(-a / 1e6) for a in an]).astype(np.float32)      # 10^6 m^2/s, warm positive
    eq = (LAT >= -15) & (LAT <= 15)
    lam = np.radians(LON)
    prof = W[:, eq, :].mean(1)
    c, s = (prof * np.cos(lam)).mean(1), (prof * np.sin(lam)).mean(1)
    w_lon = np.degrees(np.arctan2(s, c)) % 360
    w_amp = 2 * np.hypot(c, s)
    w45 = w_amp * np.cos(np.radians(w_lon - 45))
    print("warm event amplitude percentiles 25/50/75/90:", np.percentile(w_amp, [25, 50, 75, 90]).round(1), flush=True)
    # the Kelvin and Rossby families
    ser = [(d, -W[k] * 1e6) for k, d in enumerate(days)]
    wk, wla, tw = wkfilt.run(ser, LAT)
    del wk, ser
    ros, kel = np.array(tw["ros_ksa"]), np.array(tw["kel_ksa"])
    # the isolated MJO component of the height
    zf = mjofilt.mjo_filter(z8.astype(np.float64), kmax=3)
    mf = np.array([mjofilt.box(zf[k], *mjofilt.KSA, lat=LAT8, lon=LON) for k in range(len(days))])
    del zf
    # the synoptic waves at 500 hPa
    z5b = np.stack([waves.band(z5[k].astype(np.float64)) for k in range(len(days))]).astype(np.float32)
    return {"w_lon": w_lon, "w_amp": w_amp, "w45": w45, "ros": ros, "kel": kel, "mf": mf, "z5b": z5b}


def part_masks():
    regs = sa_geo.regions()
    la, lo = np.meshgrid(LAT5, LON, indexing="ij")
    lo180 = np.where(lo > 180, lo - 360, lo)
    # each grid point counts for the parts that any of its sub-points (a 5 x 5 grid inside the cell) falls in
    hit = {}
    for dj in np.linspace(-1.0, 1.0, 5):
        for di in np.linspace(-1.0, 1.0, 5):
            r = sa_geo.region_of_points(regs, (la + dj).ravel(), (lo180 + di).ravel()).reshape(la.shape)
            for g, ids in GROUPS.items():
                hit[g] = hit.get(g, np.zeros(la.shape, bool)) | np.isin(r, ids)
    for g in GROUPS:
        print("part", g, "points", int(hit[g].sum()), flush=True)
    return hit


def main():
    rows = json.load(open(sys.argv[1]))
    days, chi, z8, z5 = load_hist(sys.argv[2])
    D = drivers(days, chi, z8, z5)
    del chi, z8
    ix = {d: k for k, d in enumerate(days)}
    masks = part_masks()
    rows = [r for r in rows if "rmm" in r and date.fromisoformat(r["d"]) in ix and all(g in r for g in GROUPS)]
    rd = [date.fromisoformat(r["d"]) for r in rows]
    K = np.array([ix[d] for d in rd])
    mon = np.array([d.month for d in rd])
    season = np.array([d.year if d.month >= 11 else d.year - 1 for d in rd])
    doy = np.array([d.timetuple().tm_yday for d in rd])
    print("rain days joined", len(rows), rd[0], rd[-1], flush=True)

    ph = np.array([r["rmm"][2] for r in rows]); amp = np.array([r["rmm"][3] for r in rows])
    r1 = np.array([r["rmm"][0] for r in rows]); r2 = np.array([r["rmm"][1] for r in rows])
    mjo = (amp >= 1) & np.isin(ph, [7, 8, 1, 2])
    mjo81 = (amp >= 1) & np.isin(ph, [8, 1])
    wl, wa, w45 = D["w_lon"][K], D["w_amp"][K], D["w45"][K]
    fav = np.array([B.favourable(x) for x in wl])
    warm = fav & (wa >= 4)
    ros, kel, mf = D["ros"][K], D["kel"][K], D["mf"][K]
    sd = lambda x: float(np.std(x))
    rref, kref, mref = sd(D["ros"]), sd(D["kel"]), sd(D["mf"])
    print(f"yardsticks: Rossby {rref:.2f}, Kelvin {kref:.2f} (10^6 m^2/s), component {mref:.1f} m", flush=True)
    rosF, kelF, mfF = ros <= -rref / 3, kel <= -kref / 3, mf <= -mref / 3

    # checks of the rebuilt drivers: the warm-event centre against the RMM phase (where the convection is), and the
    # last season against what the daily system measured (the Rossby family negative on 22 of 24 wide days)
    print("\nchecks: warm-event centre (circular mean, degrees E) and amplitude by RMM phase (amplitude 1 or more)")
    for p_ in range(1, 9):
        q = (ph == p_) & (amp >= 1)
        cm = np.degrees(np.arctan2(np.sin(np.radians(wl[q])).mean(), np.cos(np.radians(wl[q])).mean())) % 360
        print(f"  phase {p_}: centre {cm:.0f}E, amplitude {wa[q].mean():.1f}, in the favourable sector {100*np.mean(fav[q] & (wa[q] >= 4)):.0f}% (n={q.sum()})")
    ksa_sp = np.array([r["المملكة"][0] for r in rows])
    for a, b in (("2025-12-01", "2026-03-17"), ("2001-01-01", "2026-03-17")):
        q = np.array([a <= r["d"] <= b for r in rows]) & (ksa_sp >= 0.08)
        print(f"  wide days (8 % of the Kingdom) {a}..{b}: n={q.sum()}, Rossby negative {100*np.mean(ros[q] < 0):.0f}% "
              f"(all wet days {100*np.mean(ros < 0):.0f}%), Kelvin negative {100*np.mean(kel[q] < 0):.0f}%, "
              f"component negative {100*np.mean(mf[q] < 0):.0f}%, warm in sector {100*np.mean(warm[q]):.0f}%, MJO 7-8-1-2 {100*np.mean(mjo[q]):.0f}%")
    for s_ in sorted(set(season)):
        q = (season == s_) & (ksa_sp >= 0.08)
        if q.sum() >= 5:
            print(f"    season {s_}: wide days {q.sum()}, Rossby negative {100*np.mean(ros[q] < 0):.0f}%, component negative {100*np.mean(mf[q] < 0):.0f}%")

    # per part: the trough, the moisture
    per = {}
    for g in GROUPS:
        sp = np.array([r[g][0] for r in rows]); rn = np.array([r[g][1] for r in rows])
        has = np.array([len(r[g]) == 4 for r in rows])
        pw = np.array([r[g][3] if len(r[g]) == 4 else np.nan for r in rows])
        clim = np.array([np.nanmean(pw[np.abs(((doy - k + 183) % 366) - 183) <= 7]) for k in doy])
        pct = 100 * pw / clim
        tr = np.array([float(np.min(D["z5b"][k][masks[g]])) for k in K])
        per[g] = {"sp": sp, "rn": rn, "has": has, "pct": pct, "tr": tr}
    # the Kingdom as the report reads it: the moistest part and the deepest trough
    per["المملكة"]["pct"] = np.nanmax(np.column_stack([per[g]["pct"] for g in SUBS]), 1)
    per["المملكة"]["tr"] = np.min(np.column_stack([per[g]["tr"] for g in SUBS]), 1)

    def strength(g):
        p = per[g]
        c = (np.where(mjo, np.minimum(amp / 3, 1), 0) + np.where(fav, np.minimum(wa / 12, 1), 0)
             + np.clip((np.nan_to_num(p["pct"], nan=100) - 100) / 100, 0, 1) + np.clip(-p["tr"] / 60, 0, 1)
             + np.clip(-mf / (2 * mref), 0, 1) + np.clip(-ros / (2 * rref), 0, 1))
        return np.minimum(c, 5)

    for g in GROUPS:
        p = per[g]
        sp, rn, has = p["sp"], p["rn"], p["has"]
        trF = p["tr"] <= -25
        surge = np.nan_to_num(p["pct"]) >= 150
        moist = np.nan_to_num(p["pct"]) >= 130
        flags = {"التذبذب ٧-٨-١-٢": mjo, "التذبذب ٨-١": mjo81, "الحدث الدافئ في القطاع": warm,
                 "الحدث البارد فوق ٤٥ شرقًا": w45 <= -4, "روسبي داعمة": rosF, "كلفن داعمة": kelF,
                 "المكوّن المعزول داعم": mfF, "أخدود ٢٥ م فأعمق": trF, "رطوبة ١٣٠٪ فأكثر": moist, "مد رطوبي ١٥٠٪": surge}
        S = strength(g)
        # who brings the moisture (Fahad, 15 Nov 2026): the chance of a moist day (130 % or more of normal) with each
        # driver on, the same day and some days before, and by MJO phase
        print(f"\n######## {g}: moisture drivers")
        for h, ms in HALVES.items():
            s = np.isin(mon, ms) & has
            base = moist[s].mean()
            out = [f"base {100*base:.0f}%"]
            for name, f in (("MJO 8-1", mjo81), ("MJO 7-8-1-2", mjo), ("warm", warm), ("cold45", w45 <= -4), ("Rossby", rosF),
                            ("Kelvin", kelF), ("component", mfF), ("trough", trF)):
                q = s & f
                out.append(f"{name} {100*moist[q].mean():.0f}% (x{moist[q].mean()/max(base,1e-6):.1f})")
            print(f"  {h}: P(moist) " + " | ".join(out))
            lagged = []
            for lag in (3, 7):
                kk = K - lag
                fl = {"warm": np.array([B.favourable(x) for x in D["w_lon"][kk]]) & (D["w_amp"][kk] >= 4),
                      "Kelvin": D["kel"][kk] <= -kref / 3, "component": D["mf"][kk] <= -mref / 3}
                lagged.append(f"{lag} days before: " + ", ".join(f"{n} {100*moist[s & f].mean():.0f}%" for n, f in fl.items()))
            print("    " + " | ".join(lagged))
            print("    by MJO phase (amplitude 1+): " + " ".join(
                f"{p_}:{100*moist[s & (ph == p_) & (amp >= 1)].mean():.0f}%" for p_ in range(1, 9))
                + f" weak:{100*moist[s & (amp < 1)].mean():.0f}%")
            m_ = s & moist
            T_ = mjo | warm | kelF | mfF
            print(f"    the moist days ({m_.sum()}): with a trough {100*np.mean(trF[m_]):.0f}% (all days {100*np.mean(trF[s]):.0f}%), "
                  f"with a tropical driver {100*np.mean(T_[m_]):.0f}% (all days {100*np.mean(T_[s]):.0f}%), "
                  f"both {100*np.mean((trF & T_)[m_]):.0f}%, neither {100*np.mean((~trF & ~T_)[m_]):.0f}% "
                  f"| rain on moist days with a trough {100*rn[m_ & trF].sum()/max(rn[s].sum(),1e-9):.0f}%, without {100*rn[m_ & ~trF].sum()/max(rn[s].sum(),1e-9):.0f}%")
        print(f"\n######## {g}")
        for h, ms in HALVES.items():
            s = np.isin(mon, ms) & has
            thr = max(np.quantile(sp[s], 0.9), 0.03)
            wide = s & (sp >= thr)
            base = sp[s].mean()
            print(f"  == {h}: days {s.sum()}, mean spread {100*base:.1f}%, wide days {wide.sum()} (spread >= {100*thr:.0f}%), "
                  f"rain {rn[s].mean():.2f} mm/day")
            for name, f in flags.items():
                on, off = s & f, s & ~f
                if on.sum() < 15:
                    print(f"    {name}: too few days ({on.sum()})")
                    continue
                print(f"    {name}: on {100*on.sum()/s.sum():.0f}% of days | spread on {100*sp[on].mean():.1f}% vs off {100*sp[off].mean():.1f}% "
                      f"(x{sp[on].mean()/max(sp[off].mean(),1e-6):.1f}) | on in {100*(wide & f).sum()/max(wide.sum(),1):.0f}% of wide days "
                      f"| rain share {100*rn[on].sum()/rn[s].sum():.0f}%")
            # the strength score
            cells = []
            for a, b in ((0, 1), (1, 2), (2, 3), (3, 5.1)):
                q = s & (S >= a) & (S < b)
                if q.sum():
                    cells.append(f"{a}-{int(b)}: {100*q.sum()/s.sum():.0f}% of days, spread {100*sp[q].mean():.1f}%, "
                                 f"P(wide) {100*(q & wide).sum()/q.sum():.0f}%")
            print("    strength score: " + " | ".join(cells))
            # the kinds of day: tropical drivers, synoptic drivers, both, neither
            T = mjo | warm | rosF | mfF
            R = trF | surge
            for nm, q in (("مداري وأخدود/رطوبة", T & R), ("مداري فقط", T & ~R), ("أخدود/رطوبة فقط", ~T & R), ("لا هذا ولا ذاك", ~T & ~R)):
                q = s & q
                print(f"    {nm}: {100*q.sum()/s.sum():.0f}% of days, spread {100*sp[q].mean():.1f}%, "
                      f"{100*(q & wide).sum()/max(wide.sum(),1):.0f}% of wide days, {100*rn[q].sum()/rn[s].sum():.0f}% of the rain")
            # lead: the tropical drivers some days before
            out = []
            for lag in (0, 5, 10, 15):
                kk = K - lag
                fl = {"warm": np.array([B.favourable(x) for x in D["w_lon"][kk]]) & (D["w_amp"][kk] >= 4),
                      "ros": D["ros"][kk] <= -rref / 3, "mf": D["mf"][kk] <= -mref / 3}
                out.append(f"lag {lag}: " + ", ".join(f"{n} spread {100*sp[s & f].mean():.1f}/{100*sp[s & ~f].mean():.1f}" for n, f in fl.items()))
            print("    lead (supportive/not, days before): " + " | ".join(out))
        # cross-validated share of the day-to-day rain explained (wet season, days with the reanalysis)
        y = np.sqrt(sp[has])
        Tm = np.column_stack([r1, r2, w45, ros, kel, mf])[has]
        Rm = np.column_stack([p["tr"], np.nan_to_num(p["pct"], nan=100)])[has]
        se = season[has]
        a, b, c = cv_r2(Tm, y, se), cv_r2(Rm, y, se), cv_r2(np.hstack([Tm, Rm]), y, se)
        print(f"  daily share explained: tropics (MJO, warm event, Rossby, Kelvin, component) {100*a:.1f}% | "
              f"troughs and moisture {100*b:.1f}% | all {100*c:.1f}%")
        for name, X in (("warm 45E", w45), ("Rossby", ros), ("Kelvin", kel), ("component", mf)):
            print(f"    alone {name}: {100*cv_r2(X[has, None], y, se):.1f}%  corr {np.corrcoef(X[has], sp[has])[0, 1]:+.2f}")

    # how far the moisture reaches (Fahad, 15 Nov 2026): when it stops at the Hijaz and the southwestern highlands and
    # when it goes deep into the interior; by MJO phase, amplitude, troughs and the warm/cold event
    pc = {g: np.nan_to_num(per[g]["pct"], nan=100) for g in SUBS}
    coast = (pc["الحجاز"] >= 130) | (pc["الجنوب الغربي"] >= 130)
    deep = pc["الوسط"] >= 130
    deepE = (pc["الوسط"] >= 130) | (pc["الشرق"] >= 130)
    trN = (per["الوسط"]["tr"] <= -25) | (per["الشمال"]["tr"] <= -25)
    hasall = np.all(np.column_stack([per[g]["has"] for g in SUBS]), 1)
    print("\n######## reach of the moisture: P(the centre moist, >= 130 %) on days the west or southwest is moist")
    for h, ms in HALVES.items():
        s = np.isin(mon, ms) & hasall
        c = s & coast
        print(f"  == {h}: coast-moist days {c.sum()} ({100*c.sum()/s.sum():.0f}% of days); of them the centre moist "
              f"{100*deep[c].mean():.0f}%, centre or east {100*deepE[c].mean():.0f}% | centre moist days {(s & deep).sum()}, "
              f"of them with the coast moist {100*coast[s & deep].mean():.0f}% (the rest came from the east and south)")
        print("    by MJO phase (amplitude 1+): " + " ".join(
            f"{p_}:{100*deep[c & (ph == p_) & (amp >= 1)].mean():.0f}%(n{(c & (ph == p_) & (amp >= 1)).sum()})" for p_ in range(1, 9))
            + f" weak:{100*deep[c & (amp < 1)].mean():.0f}%(n{(c & (amp < 1)).sum()})")
        for nm, P_ in (("8-1", (8, 1)), ("2-3", (2, 3)), ("all", tuple(range(1, 9)))):
            cells = []
            for a, b in ((0, 1), (1, 1.5), (1.5, 2), (2, 9)):
                q = c & np.isin(ph, P_) & (amp >= a) & (amp < b)
                cells.append(f"amp {a}-{b}: {100*deep[q].mean():.0f}% (n{q.sum()})" if q.sum() >= 10 else f"amp {a}-{b}: -")
            print(f"    phases {nm} by amplitude: " + " | ".join(cells))
        for nm, f in (("trough over the north/centre", trN), ("no trough there", ~trN), ("warm event in sector", warm),
                      ("cold event over 45E", w45 <= -4), ("Kelvin supportive", kelF), ("component supportive", mfF)):
            q = c & f
            print(f"    {nm}: {100*deep[q].mean():.0f}% (n{q.sum()})")
        q1, q2 = c & trN & np.isin(ph, (8, 1, 2)) & (amp >= 1), c & ~trN & np.isin(ph, (8, 1, 2)) & (amp >= 1)
        print(f"    MJO 8-1-2 with a trough {100*deep[q1].mean():.0f}% (n{q1.sum()}), without {100*deep[q2].mean():.0f}% (n{q2.sum()})")

    # the moisture needed for rain (Fahad, 15 Nov 2026): the chance of rain by precipitable water as a share of normal,
    # for each part, on all days, with a trough over the part, and with a trough and the MJO in phases 8, 1 or 2
    print("\n######## moisture needed: P(rain on 2 % of the part or more) / P(wide: 10 % or more), by PW % of normal")
    bins = ((0, 80), (80, 100), (100, 115), (115, 130), (130, 150), (150, 175), (175, 999))
    for g in GROUPS:
        p_ = per[g]
        sp, has, pc_ = p_["sp"], p_["has"], np.nan_to_num(p_["pct"], nan=100)
        trF = p_["tr"] <= -25
        mjo812 = (amp >= 1) & np.isin(ph, (8, 1, 2))
        print(f"  == {g}")
        for h, ms in HALVES.items():
            s = np.isin(mon, ms) & has
            for nm, f in (("all days", np.ones_like(s)), ("trough", trF), ("trough + MJO 8-1-2", trF & mjo812),
                          ("MJO 8-1-2, no trough", ~trF & mjo812)):
                cells = []
                for a, b in bins:
                    q = s & f & (pc_ >= a) & (pc_ < b)
                    cells.append(f"{a}-{b if b < 999 else ''}: {100*np.mean(sp[q] >= 0.02):.0f}/{100*np.mean(sp[q] >= 0.10):.0f} (n{q.sum()})"
                                 if q.sum() >= 12 else f"{a}-{b if b < 999 else ''}: -")
                print(f"    {h} | {nm}: " + "  ".join(cells))


if __name__ == "__main__":
    main()
