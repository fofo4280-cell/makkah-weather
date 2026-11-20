"""Cold waves over the Kingdom in the next 16 days: GFS daily minimum temperature at two or three towns per
region (Open-Meteo) against the ERA5 normals of those towns (2001-2020, kept per calendar month).

A cold day for a region: the mean minimum of its towns 3 degrees or more below normal (5 or more: a strong one).
A cold wave: two or more such days in a row. Returns [{"regions", "a", "b", "days", "anom", "tmin", "town"}].
"""
from datetime import date, timedelta

import numpy as np

import sa_geo as G
import today as T


def cold_waves(om, state_dir, day0, days=16, log=print):
    regs = G.regions()
    towns = sorted({t for ts in G.NORMAL_TOWNS.values() for t in ts})
    js = om.get(G.FORECAST, {"daily": "temperature_2m_min", "models": "gfs_seamless", "timezone": "Asia/Riyadh",
                             "forecast_days": days}, [G.PLACE[t][0] for t in towns], [G.PLACE[t][1] for t in towns],
                weight=days / 14)
    tmin = {}
    dates = None
    for t, j in zip(towns, js):
        d = j.get("daily") or {}
        dates = [date.fromisoformat(x) for x in d.get("time", [])]
        tmin[t] = [np.nan if x is None else x for x in (d.get("temperature_2m_min") or d.get("temperature_2m_min_gfs_seamless") or [])]
    if not dates:
        return []
    norm = {}
    for dd in dates:
        try:
            norm[dd] = T.normals(om, state_dir, dd)
        except Exception as e:
            log(f"cold waves: normals for {dd} unavailable: {e!r}")
            norm[dd] = {}
    by_region = {}
    for r in regs:
        ts = [t for t in G.NORMAL_TOWNS[r["id"]] if t in tmin]
        rows = []
        for k, dd in enumerate(dates):
            an = [tmin[t][k] - norm[dd][t][1] for t in ts if t in norm[dd] and k < len(tmin[t]) and np.isfinite(tmin[t][k])]
            lows = [(tmin[t][k], t) for t in ts if k < len(tmin[t]) and np.isfinite(tmin[t][k])]
            rows.append((dd, float(np.mean(an)) if an else np.nan, min(lows) if lows else (np.nan, "")))
        by_region[r["name"]] = rows
    # episodes per region, then joined across regions that overlap in time
    eps = []
    for name, rows in by_region.items():
        run = []
        for dd, an, low in rows + [(None, np.nan, (np.nan, ""))]:
            if dd is not None and np.isfinite(an) and an <= -3:
                run.append((dd, an, low))
            else:
                if len(run) >= 2:
                    eps.append({"region": name, "a": run[0][0], "b": run[-1][0], "anom": min(x[1] for x in run),
                                "low": min(x[2] for x in run)})
                run = []
    eps.sort(key=lambda e: e["a"])
    waves_ = []
    for e in eps:
        for w in waves_:
            if e["a"] <= w["b"] + timedelta(days=1) and e["b"] >= w["a"] - timedelta(days=1):
                w["regions"].append(e["region"]); w["a"] = min(w["a"], e["a"]); w["b"] = max(w["b"], e["b"])
                w["anom"] = min(w["anom"], e["anom"])
                if e["low"][0] < w["low"][0]:
                    w["low"] = e["low"]
                break
        else:
            waves_.append({"regions": [e["region"]], "a": e["a"], "b": e["b"], "anom": e["anom"], "low": e["low"]})
    out = []
    for w in waves_:
        out.append({"regions": w["regions"], "a": w["a"].isoformat(), "b": w["b"].isoformat(),
                    "days": (w["b"] - w["a"]).days + 1, "anom": round(w["anom"], 1),
                    "tmin": round(float(w["low"][0]), 1), "town": w["low"][1],
                    "strong": w["anom"] <= -5})
    return out
