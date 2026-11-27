#!/usr/bin/env python3
"""Rewrite the rain section of the published report from our latest complete runs, without recomputing the rest
of the page.

refresh_report.py <state_dir> <out_dir> [midnight]   (noon removed on 15 Nov 2026)
  midnight: the Makkah day of the report (00:00 to 24:00), once the evening (12Z) runs are complete;
  noon:     an update at noon Makkah from the morning (00Z) runs, for the rest of the day (12:00 to 24:00).
Our runs come from SA_DATA, WEST_DATA, KM1_DATA and REGION_DATA as in daily.py.
"""
import json, os, sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_geo  # noqa: E402
import rainreport  # noqa: E402
import bigreport  # noqa: E402


def main():
    state, out = sys.argv[1:3]
    mode = sys.argv[3] if len(sys.argv) > 3 else "midnight"
    if mode != "midnight":   # the noon update and the daytime (00Z) run were removed (Fahad, 14-15 Nov 2026)
        sys.exit("only the midnight report exists now")
    p = os.path.join(out, "mjo.json")
    st = json.load(open(p))
    rep = st.get("report") or {}
    secs = rep.get("sections") or []
    ours = ([os.environ.get("SA_DATA"), os.environ.get("WEST_DATA"), os.environ.get("KM1_DATA")]
            + os.environ.get("REGION_DATA", "").split())
    if mode == "noon":
        day = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
        t_a = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(hours=9)
        t_b = t_a + timedelta(hours=12)
    else:
        day = date.fromisoformat(rep.get("day") or st["days"][0])
        try:   # the day of tonight's cycle (its 12 UTC run is for the next Makkah day): if the nightly self-check kept
            # yesterday's report, the rewrite is still for tonight's day, not yesterday's (28 Nov 2026)
            cy = str(st.get("cycle") or "")
            if len(cy) == 10 and cy.endswith("12"):
                day = max(day, date(int(cy[:4]), int(cy[4:6]), int(cy[6:8])) + timedelta(days=1))
        except Exception as e:  # noqa: BLE001
            print("cycle day not read:", repr(e), flush=True)
        t_a = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(hours=3)
        t_b = t_a + timedelta(hours=24)
    new = rainreport.rain_report(t_a, t_b, ours, st, sa_geo.OpenMeteo(), issue=mode)
    new["kind"] = "rain_noon" if mode == "noon" else "rain"
    keep = [s for s in secs if s.get("kind") not in ("rain", "rain_noon")]
    try:   # the big-picture sections are rebuilt too, so a change of their wording shows at the next issue
        keep = bigreport.report(st, day)
    except Exception as e:
        print("big-picture report not rebuilt:", repr(e), flush=True)
    night = next((s for s in secs if s.get("kind") == "rain"), None)
    if mode == "noon":
        # the noon update goes first; the night's report stays under it for comparison (same day only)
        rain = [new] + ([night] if night and rep.get("day") == day.isoformat() else [])
    else:
        rain = [new]
    # the summary first, then the rain table, then the rest (Fahad, 14 Nov 2026)
    if rep.get("day") != day.isoformat():   # yesterday's report was kept by the self-check: tonight's day and title
        rep["day"] = day.isoformat()
        rep["title"] = f"تقرير {sa_geo.ar_date(day)}"
        rep["issued"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    rep["sections"] = [x for x in keep if x.get("kind") == "sum"] + rain + [x for x in keep if x.get("kind") != "sum"]
    rep["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    # Fahad's layout only (17 Nov 2026: "the old layout, I do not want it"): report2.build never returns the old
    # sections; on a failure it publishes the layout with a note saying what failed
    try:   # the spread of past days, to compare today with them (Fahad, 18 Nov 2026)
        import covhist
        covhist.attach(st, out, new, day)
    except Exception as e:  # noqa: BLE001
        print("cover history failed:", repr(e), flush=True)
    import report2
    try:
        import report4
        report4.OUT_DIR = out
    except Exception as e:  # noqa: BLE001
        print("report4 import failed:", repr(e), flush=True)
    prev = st.get("report")
    rep = report2.build(rep, st)
    try:   # the self-check before publishing (reportcheck.py, 27 Nov 2026)
        import reportcheck
        errs = reportcheck.check(rep, st)
    except Exception as e:  # noqa: BLE001
        errs = [f"self-check crashed: {e!r}"]
    st["report_check"] = {"errors": errs}
    if errs:
        print("REPORT SELF-CHECK FAILED, not published:", *errs, sep="\n  ", flush=True)
        st["report"] = prev
        json.dump(st, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
        return
    st["report"] = rep
    try:   # tonight's judgement in the verification log, if the nightly run could not record it (verif.py)
        import verif
        vl = verif.load(out)
        if day.isoformat() not in vl["fc"]:
            verif.record(vl, day, st.get("cycle"), getattr(report4, "LAST_ROWS", []))
            verif.save(out, vl)
            print("verification log: recorded", day, flush=True)
    except Exception as e:  # noqa: BLE001
        print("verification log failed:", repr(e), flush=True)
    json.dump(st, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
    rd = os.path.join(out, "reports")
    os.makedirs(rd, exist_ok=True)
    json.dump(rep, open(os.path.join(rd, day.strftime("%Y%m%d") + ".json"), "w"), ensure_ascii=False)
    print(f"rain report ({mode}) refreshed for", day, flush=True)
    for line in [new["heading"]] + new["lines"]:
        print(line, flush=True)


if __name__ == "__main__":
    main()
