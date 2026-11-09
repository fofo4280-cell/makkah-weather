"""The large-scale picture for the daily report: where the MJO and the warm event are, and whether that favours rain
over the Arabian Peninsula.

Warm event: minus the 200 hPa velocity potential anomaly along the equator (15S-15N, the Hovmoller rows of
daily.py, 10^6 m^2/s). Its centre is the phase of the zonal wave-1 of that profile, which moves east with the MJO.
In November-April the MJO phases 7, 8, 1 and 2 favour rain over the Kingdom (26 stations, 1985-2021); the warm-event
centre then lies from the eastern Pacific and the Americas across the Atlantic and Africa to the western Arabian Sea:
in the analyses of autumn 2026 it sat near 320-350E in phase 8-1, 0-50E in phase 2 and 60-75E in phase 3, so the
favourable sector is taken as 250 to 55 degrees east.
"""
import math

import numpy as np

WET_PHASES = {7, 8, 1, 2}
SECTOR = (250.0, 55.0)          # favourable longitudes of the warm-event centre, through 0


def region_name(lon):
    lon = lon % 360
    for a, b, n in [(0, 15, "غرب أفريقيا والأطلسي"), (15, 55, "شرق أفريقيا وغرب بحر العرب"), (55, 75, "بحر العرب وغرب المحيط الهندي"),
                    (75, 100, "وسط وشرق المحيط الهندي"), (100, 145, "القارة البحرية (إندونيسيا)"),
                    (145, 180, "غرب المحيط الهادئ"), (180, 240, "وسط المحيط الهادئ"), (240, 290, "شرق المحيط الهادئ"),
                    (290, 360, "الأمريكتان والأطلسي")]:
        if a <= lon < b:
            return n
    return ""


def favourable(lon):
    lon = lon % 360
    return lon >= SECTOR[0] or lon < SECTOR[1]


def wave1(hov):
    """[(date string, centre lon, amplitude)] for every row of the Hovmoller (analyses, then the GFS forecast)."""
    lon = np.radians(hov["lon0"] + hov["dlon"] * np.arange(len(hov["v"][0])))
    out = []
    for d, row in zip(hov["days"], hov["v"]):
        v = np.asarray(row, float)
        c, s = (v * np.cos(lon)).mean(), (v * np.sin(lon)).mean()
        out.append((d, math.degrees(math.atan2(s, c)) % 360, 2 * math.hypot(c, s)))
    return out


def speed(lons, days=None):
    """Eastward speed in degrees per day from a series of longitudes (least squares on the unwrapped series)."""
    if len(lons) < 8:
        return None
    u = np.degrees(np.unwrap(np.radians(lons)))
    x = np.arange(len(u)) if days is None else np.asarray(days, float)
    return float(np.polyfit(x, u, 1)[0])


def rmm_on(st, day):
    """The MJO (RMM) on a date: the official value if there is one, else the calibrated GFS projection."""
    s = day.isoformat()
    for x in (st.get("rmm_obs") or []) + (st.get("rmm_fc") or []):
        if x["d"] == s:
            return x
    return st.get("rmm_today") or st.get("rmm_now")
