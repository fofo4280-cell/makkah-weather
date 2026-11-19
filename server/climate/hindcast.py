#!/usr/bin/env python3
"""Test of the report's expert reading on past days (Fahad, 19 Nov 2026: «قبل تنشر اختبر وتأكد من فعالية قراءتك ثم
انشر» and «اذا تريد توسع دائرة الاختبار ابدأ من 10 نوفمبر»).

For each day D the night's inputs are rebuilt from the GFS 12 UTC run of D-1, as the midnight report had them:
PW boxes against the climatology, the Taif collision, the 500 hPa troughs, the surface collision zones, the plains
and mountain edges, the 500 hPa temperature boxes, and the trough row of the waves. The big-picture drivers that need
the long series (MJO, warm event, Rossby family) are taken from the current state when it covers the day. Then
report3.region_reading and report3.summary are run, and the reading is written out for comparison with the observed
rain.

    hindcast.py CLIM_DIR STATE_JSON FIRST_DAY LAST_DAY OUT_JSON
"""
import copy
import json
import os
import sys
import tempfile
import traceback
from datetime import date, datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily as D  # noqa: E402


def inputs(day, clim, log=print):
    t0 = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc) - timedelta(days=1)
    cycle = t0.strftime("%Y%m%d%H")
    out = {"cycle": cycle}
    fc = {}
    for d in range(0, 4):
        f = D.gfs_fields(cycle, d * 24, (D.Z500, D.T500))
        fc[t0 + timedelta(days=d)] = f
    days = sorted(fc)
    plat, plon = clim["pw_lat"], clim["pw_lon"]
    pw_rows = []
    for dt in days:
        row = {"d": dt.strftime("%Y-%m-%d")}
        for key, (name, s, n, w, e) in D.BOXES.items():
            g = D.box_mean(fc[dt]["pw"], D.LAT1, D.LON1, s, n, w, e)
            c = D.box_mean(clim["pw"][D.doy(dt)], plat, plon, s, n, w, e)
            row[key] = {"pw": round(g, 1), "clim": round(c, 1), "pct": int(round(100 * g / max(c, 1)))}
        pw_rows.append(row)
    out["pw"] = pw_rows
    # the wave trough next to the Kingdom (bigreport's trough driver)
    import waves
    wave_rows = []
    for dt in days:
        zp = waves.band(fc[dt]["z500"])
        jb, ib = (D.LAT1 >= 16) & (D.LAT1 <= 30), (D.LON1 >= 26) & (D.LON1 <= 48)
        sub = zp[np.ix_(jb, ib)]
        jj, ii = np.unravel_index(int(np.argmin(sub)), sub.shape)
        row = {"d": dt.strftime("%Y-%m-%d")}
        if sub[jj, ii] <= -15:
            la_, lo_ = float(D.LAT1[jb][jj]), float(D.LON1[ib][ii])
            row["trough"] = {"lat": la_, "lon": lo_, "v": int(round(float(sub[jj, ii]))), "area": D.trough_area(la_, lo_)}
        wave_rows.append(row)
    out["waves"] = wave_rows
    import troughs
    try:
        out["troughs"] = troughs.to_json(troughs.track([(dt.date(), troughs.day_troughs(fc[dt]["z500"], fc[dt]["t500"], D.LAT1, D.LON1)) for dt in days]))
    except Exception as e:  # noqa: BLE001
        log("troughs failed", repr(e))
    import taifconv
    try:
        with tempfile.TemporaryDirectory() as td:
            taifconv.draw_map = lambda *a, **k: None
            taifconv.draw_line = lambda *a, **k: None
            out["taifc"] = taifconv.run(D.gfs_fields, cycle, td)
    except Exception as e:  # noqa: BLE001
        log("taif collision failed", repr(e))
    import collide
    import sa_geo
    first = t0.replace(hour=21, minute=0)
    try:
        hrs, hg = [], None
        for uh in collide.UTC_HOURS:
            vt = first + timedelta(hours=3 + uh)
            fh = int((vt - t0).total_seconds() // 3600)
            f = D.gfs_fields(cycle, fh, res="0p25", fields=collide.FIELDS + ([] if hg is not None else collide.HGT))
            if hg is None:
                hg = f.pop("hgt")
            la = np.linspace(90, -90, f["u10"].shape[0])
            lo = np.linspace(0, 360, f["u10"].shape[1], endpoint=False)
            sub = {}
            for n_, a_ in f.items():
                sub[n_], cla, clo = collide.cut(a_, la, lo)
            sub["hgt"] = collide.cut(hg, la, lo)[0]
            hrs.append((vt, sub))
        zs = collide.zones(hrs, cla, clo, sa_geo.regions())
        out["collide"] = {"day": day.isoformat(), "hours": len(hrs), "zones": zs}
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        log("collision failed", repr(e))
    import plains
    try:
        prow = next(r for r in pw_rows if r["d"] == day.isoformat())
        pct_of = lambda la_, lo_: prow["southwest" if la_ < 20 else "west"]["pct"]  # noqa: E731
        prs, eds = plains.check_all(lambda c, h, f: D.gfs_fields(c, h, res="0p25", fields=f), cycle, day, pct_of,
                                    log=lambda *a: None)
        out["plains"] = {"day": day.isoformat(), "cycle": cycle, "rows": prs, "edges": eds}
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        log("plains failed", repr(e))
    import pattern
    vt = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
    near = min(fc, key=lambda k: abs((k - vt).total_seconds()))
    out["pattern"] = {"day": day.isoformat(), "t": near.strftime("%Y-%m-%dT%H:%MZ"),
                      "boxes": pattern.boxes(fc[near]["t500"], D.LAT1, D.LON1, day)}
    return out


def flat(rows):
    """[{region, level, places: [(place, intensity, cause)]}] from region_reading"""
    out = []
    for r in rows:
        pl = [(p, k, (r.get("why") or {}).get(p, "")) for k in ("heavy", "moderate", "light") for p in r["row"][k]]
        out.append({"region": r["name"], "level": r["level"], "vague": bool(r.get("vague")), "places": pl,
                    "pw": r.get("pw"), "cape": r.get("cape"), "trough": r.get("trough"), "meets": r.get("meets")})
    return out


def main():
    clim_dir, state_path, a, b, out_path = sys.argv[1:6]
    clim = dict(np.load(os.path.join(clim_dir, "clim.npz")))
    base = json.load(open(state_path))
    import report3 as R
    import bigreport as BR
    res = {}
    d = date.fromisoformat(a)
    while d <= date.fromisoformat(b):
        print("==", d, flush=True)
        try:
            inp = inputs(d, clim)
            st = copy.deepcopy(base)
            for k in ("pw", "waves", "troughs", "taifc", "collide", "plains", "pattern"):
                if k in inp:
                    st[k] = inp[k]
            st.pop("mstory", None)
            st["wet_season"] = True
            W = R.cold_wave(st, d)
            sc = BR.strength(st, d)
            ws = BR.wave_score(st, d, d, sc, None)["score"]
            rows = R.region_reading(st, None, None, d, W, big=min(1.0, ws / 3))
            txt = []
            try:
                s = R.summary(st, None, None, d)
                for blk in s["blocks"]:
                    if "table" in blk:
                        txt.append(" | ".join(blk["table"]["head"]))
                        txt += [" | ".join(r) for r in blk["table"]["rows"]]
                    else:
                        txt.append(str(list(blk.values())[0]))
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                txt.append("summary failed " + repr(e))
            res[d.isoformat()] = {"cycle": inp["cycle"], "strength": sc, "ws": ws, "regions": flat(rows),
                                  "cold": (W or {}).get("regions"), "summary": txt,
                                  "inputs": {k: inp.get(k) for k in ("collide", "plains", "pattern", "taifc")}}
            print("\n".join(txt), flush=True)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res[d.isoformat()] = {"error": repr(e)}
        json.dump(res, open(out_path, "w"), ensure_ascii=False, default=str)
        d += timedelta(days=1)


if __name__ == "__main__":
    main()
