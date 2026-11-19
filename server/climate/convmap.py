"""Tropical convection map (Fahad, 19 Nov 2026: «الصورة الأولى والثانية جميلة جدا» → «نعم مع الإشارة بخط مستقيم
عمودي بمكان mjo على الخريطة»): outgoing longwave radiation at the top of the atmosphere, mean of the last 24 hours of
GFS analyses (four cycles, 0-6 h averages), Africa to the central Pacific, with a vertical line at the MJO centre
from JMA's index (the same index the page uses): its phase angle placed on the belts drawn on the map, 20 degrees of
longitude a phase (phase 1 from 40 E, 2-3 Indian Ocean 60-100, 4-5 Maritime Continent 100-140, 6-7 western Pacific
140-180, 8 east of the date line). JMA's own `lon` column (135 + angle) does not match the usual belts, so not used.

    run(gfs_fields, cycle, fig_dir, jma_last) -> {"t0", "t1", "days", "phase", "amp", "d", ...};\n    writes fig/olr_00.png (analyses) and olr_01..15.png (forecast days)
"""
import os
from datetime import datetime, timedelta, timezone

import numpy as np

from sa_geo import ar

MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
FIELD = [("olr", r":ULWRF:top of atmosphere:0-6 hour ave")]


def _ar(t):
    try:
        from figures import _ar as f
        return f(t)
    except Exception:  # noqa: BLE001
        return t


SPEED = 8.0          # degrees of RMM angle a day, as season.py (tested)
FC_DAYS = 15


def _proj(jma, when):
    """the JMA phase carried east at the usual speed to date `when` (as the seasonal outlook)"""
    import math
    ang = math.degrees(math.atan2(jma["r2"], jma["r1"])) % 360
    lead = (when - datetime.strptime(jma["d"], "%Y-%m-%d").date()).days
    a = (ang + SPEED * max(lead, 0)) % 360
    return {**jma, "r1": math.cos(math.radians(a)), "r2": math.sin(math.radians(a)),
            "phase": int(((a - 180) % 360) // 45) + 1, "proj": lead > 0, "on": when.isoformat()}


def run(gfs_fields, cycle, fig_dir, jma_last, log=print):
    """day 0: the last 24 h of analyses; days 1-15 (Fahad, 19 Nov 2026: «زر الأيام المستقبلية لها وتتغير معها حتى
    آخر تاريخ ممكن»): 24 h means of this run, forecast hours (24k-18, 24k+6], with the MJO line projected"""
    t_end = datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    acc, used = None, []
    for k in range(4):
        c = (t_end - timedelta(hours=6 * k)).strftime("%Y%m%d%H")
        try:
            a = gfs_fields(c, 6, res="0p25", fields=FIELD)["olr"]
        except Exception as e:  # noqa: BLE001
            log("olr cycle", c, "failed:", repr(e))
            continue
        acc = a if acc is None else acc + a
        used.append(c)
    if not used:
        return None
    t1 = datetime.strptime(max(used), "%Y%m%d%H").replace(tzinfo=timezone.utc) + timedelta(hours=6)
    t0 = datetime.strptime(min(used), "%Y%m%d%H").replace(tzinfo=timezone.utc)
    draw(acc / len(used), t1, jma_last, os.path.join(fig_dir, "olr_00.png"), fc=False)
    days = [t1.strftime("%Y-%m-%dT%H:%MZ")]
    for k in range(1, FC_DAYS + 1):
        acc, n = None, 0
        for h in range(24 * k - 12, 24 * k + 7, 6):
            try:
                a = gfs_fields(cycle, h, res="0p25", fields=[("olr", rf":ULWRF:top of atmosphere:{h - 6}-{h} hour ave")])["olr"]
            except Exception as e:  # noqa: BLE001
                log("olr f", h, "failed:", repr(e))
                continue
            acc = a if acc is None else acc + a
            n += 1
        if n < 3:
            break
        te = t_end + timedelta(hours=24 * k + 6)
        j = _proj(jma_last, (te + timedelta(hours=3)).date()) if jma_last and jma_last.get("r1") is not None else None
        draw(acc / n, te, j, os.path.join(fig_dir, f"olr_{k:02d}.png"), fc=True)
        days.append(te.strftime("%Y-%m-%dT%H:%MZ"))
    out = {"t0": t0.strftime("%Y-%m-%dT%H:%MZ"), "t1": t1.strftime("%Y-%m-%dT%H:%MZ"), "cycles": len(used), "days": days}
    if jma_last:
        out.update({"r1": jma_last.get("r1"), "r2": jma_last.get("r2"), "phase": jma_last["phase"], "amp": jma_last["amp"], "d": jma_last["d"]})
    log("olr maps:", len(days))
    return out


def draw(olr, t1, jma, path, fc=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    import cartopy.feature as cf
    from matplotlib import font_manager as fm
    from matplotlib.colors import LinearSegmentedColormap
    here = os.path.dirname(os.path.abspath(__file__))
    fp = fm.FontProperties(fname=os.path.join(here, "fonts", "IBMPlexSansArabic-SemiBold.ttf"))
    fb = fm.FontProperties(fname=os.path.join(here, "fonts", "IBMPlexSansArabic-Bold.ttf"))
    ny, nx = olr.shape
    lat = np.linspace(90, -90, ny)
    lon = np.arange(nx) * 360.0 / nx
    j = (lat <= 40) & (lat >= -30)
    lat, v = lat[j], olr[j]
    fig = plt.figure(figsize=(15, 5.2), dpi=150, facecolor="#111")
    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=110))
    ax.set_facecolor("#1b2330")
    ax.set_extent([15, 215, -25, 38], ccrs.PlateCarree())
    ax.add_feature(cf.LAND.with_scale("50m"), facecolor="#3a3a3a", zorder=0)
    lev = [120, 140, 160, 180, 200, 220, 240]
    cmap = LinearSegmentedColormap.from_list("c", ["#e0306a", "#a01f8f", "#5a2a9e", "#2b4fb0", "#3a7fd8", "#7fb8f0", "#cfe8ff"])
    cm = ax.contourf(lon, lat, v, levels=lev, cmap=cmap, extend="min", transform=ccrs.PlateCarree(), alpha=.95)
    ax.coastlines("50m", lw=.6, color="#bbb")
    ax.add_feature(cf.BORDERS.with_scale("50m"), lw=.3, edgecolor="#888")
    ax.plot([0, 200], [0, 0], color="#666", lw=.6, ls="--", transform=ccrs.PlateCarree())
    for a, b, t in [(40, 60, "الطور ١"), (60, 100, "الطوران ٢ و٣: المحيط الهندي"),
                    (100, 140, "الطوران ٤ و٥: إندونيسيا"), (140, 180, "الطوران ٦ و٧: غرب الهادئ"), (180, 214, "الطور ٨")]:
        ax.plot([a, a], [-25, -18], color="#ddd", lw=.8, transform=ccrs.PlateCarree())
        ax.text((a + b) / 2, -22, _ar(t), fontproperties=fp, fontsize=10.5, color="#eee", ha="center", va="center",
                transform=ccrs.PlateCarree())
    sub = "كلما اشتد اللون كانت السحب الركامية أعمق وأعلى"
    if jma and jma.get("r1") is not None:
        import math
        ang = math.degrees(math.atan2(jma["r2"], jma["r1"])) % 360
        x = 40 + ((ang - 180) % 360) * 20 / 45
        d = datetime.strptime(jma["d"], "%Y-%m-%d")
        ax.plot([x, x], [-17, 37], color="#ffd34d", lw=2.2, transform=ccrs.PlateCarree(), zorder=6)
        ax.text(x, 34.5, _ar(f"مركز التذبذب{' المتوقع' if jma.get('proj') else ''}: الطور {ar(jma['phase'])}"), fontproperties=fb, fontsize=12, color="#ffd34d",
                ha="right", va="center", transform=ccrs.PlateCarree(), zorder=7,
                bbox=dict(boxstyle="round,pad=0.25", fc="#111", ec="none", alpha=.75))
        if jma.get("proj"):
            sub = (f"الخط الأصفر: مركز التذبذب متوقعًا بسرعته المعتادة من آخر رصد للوكالة اليابانية ({ar(d.day)} "
                   f"{MONTHS[d.month - 1]})، الطور {ar(jma['phase'])}؛ " + sub)
        else:
            sub = (f"الخط الأصفر: مركز التذبذب المداري حسب مؤشر الوكالة اليابانية للأرصاد الجوية في {ar(d.day)} "
                   f"{MONTHS[d.month - 1]}، الطور {ar(jma['phase'])} وقوته {ar(round(float(jma['amp']), 1)).replace('.', '٫')}؛ " + sub)
    mk = t1 + timedelta(hours=3)
    hr = mk.hour % 12 or 12
    when = "صباح" if mk.hour < 12 else ("عصر" if mk.hour < 18 else "مساء")
    if fc:
        title = f"الحمل الحراري المداري المتوقع: ٢٤ ساعة حتى {ar(hr)} {when} {DAYS[mk.weekday()]} {ar(mk.day)} {MONTHS[mk.month - 1]}"
    else:
        title = f"الحمل الحراري المداري في آخر ٢٤ ساعة حتى {ar(hr)} {when} {DAYS[mk.weekday()]} {ar(mk.day)} {MONTHS[mk.month - 1]}"
    fig.text(.5, .93, _ar(title), fontproperties=fb, fontsize=17, color="#fff", ha="center")
    fig.text(.5, .875, _ar(sub), fontproperties=fp, fontsize=11.5, color="#bbb", ha="center")
    cax = fig.add_axes([.3, .075, .4, .022])
    cb = plt.colorbar(cm, cax=cax, orientation="horizontal")
    cb.set_ticks(lev)
    cb.set_ticklabels([ar(x) for x in lev])
    cb.outline.set_edgecolor("#555")
    for t in cb.ax.get_xticklabels():
        t.set_fontproperties(fp); t.set_color("#ddd")
    foot = ("الأشعة الطويلة الصادرة من قمم السحب (واط/م²)، من " + ("توقع" if fc else "تحليلات")
            + " جي إف إس؛ أقل من ٢٤٠ حمل حراري، وأقل من ١٨٠ حمل عميق")
    fig.text(.5, -.005, _ar(foot), fontproperties=fp, fontsize=10.5, color="#aaa", ha="center")
    fig.savefig(path, facecolor="#111", bbox_inches="tight")
    plt.close(fig)
