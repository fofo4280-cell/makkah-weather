#!/usr/bin/env python3
"""Rebuild the day's sections of the published report (the Kingdom and the Makkah region) once our later model run
is complete, without recomputing the rest of the page.

refresh_report.py <state_dir> <out_dir>      (our runs from SA_DATA, WEST_DATA, KM1_DATA as in daily.py)
"""
import json, os, sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_geo  # noqa: E402
import today as today_wx  # noqa: E402


def main():
    state, out = sys.argv[1:3]
    p = os.path.join(out, "mjo.json")
    st = json.load(open(p))
    rep = st.get("report") or {}
    secs = rep.get("sections") or []
    old = next((s for s in secs if s.get("heading", "").startswith("طقس المملكة")), None)
    if not old or "data" not in old:
        print("no day section to refresh"); return
    day = date.fromisoformat(old["data"]["day"])
    ours = [os.environ.get("SA_DATA"), os.environ.get("WEST_DATA"), os.environ.get("KM1_DATA")]
    tw = today_wx.situation(day, ours, state, st, sa_geo.OpenMeteo())
    mk = tw.pop("makkah", None)
    new = []
    for s in secs:
        h = s.get("heading", "")
        if h.startswith("طقس المملكة"):
            new.append(tw)
            if mk:
                new.append(mk)
        elif h.startswith("منطقة مكة المكرمة"):
            continue
        else:
            new.append(s)
    rep["sections"] = new
    json.dump(st, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
    rd = os.path.join(out, "reports")
    if os.path.isdir(rd):
        json.dump(rep, open(os.path.join(rd, st["cycle"][:8] + ".json"), "w"), ensure_ascii=False)
    print("report refreshed for", day)


if __name__ == "__main__":
    main()
