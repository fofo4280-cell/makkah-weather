"""ECMWF open data (IFS 0.25) behind the same call as daily.gfs_fields, for the Kingdom maps of the oscillation page
(Fahad, 19 Nov 2026: «غيرها في الموقع كلها الى الاوروبي»; the big-picture products stay on GFS, he chose).

fields_like_gfs(gfs_fields) -> a function f(cycle, fh, res="0p25", fields=[(name, GFS regex)]) returning the same
arrays as gfs_fields (lat 90..-90, lon 0..359.75, 721 x 1440: the GFS 0.25 grid and the IFS open-data grid are the
same points once the longitudes are rolled). The GFS patterns are mapped to IFS parameters (MAP); what IFS open data
lacks (the ground height) and anything unmapped comes from GFS of the same cycle. IFS steps: 00/12 UTC 3-hourly to
144 h, 6-hourly to 360 h; 06/18 UTC 3-hourly to 90 h. A step between two available ones is interpolated linearly in
time (accumulated rain too), so callers written for hourly GFS work unchanged.
If IFS fails for a call, GFS answers it and the call is counted in FALLBACK (the maps then say «النموذج الأمريكي»).
"""
import json
import re
import time
import urllib.request

import numpy as np

EC = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
# the same files (same bytes, same .index offsets) on ECMWF's own server: used when the AWS copy does not answer
# (night of 19 Nov 2026: AWS did not answer for ~6 min and the Kingdom maps fell back to GFS)
MIRROR = "https://data.ecmwf.int/forecasts"
# GFS pattern (regex searched in the GFS line) -> (IFS param, level, scale, offset)
MAP = [(r":RH:(\d+) mb:", "r", 1.0), (r":TMP:(\d+) mb:", "t", 1.0), (r":UGRD:(\d+) mb:", "u", 1.0),
       (r":VGRD:(\d+) mb:", "v", 1.0), (r":HGT:(\d+) mb:", "gh", 1.0), (r":SPFH:(\d+) mb:", "q", 1.0),
       (r":VVEL:(\d+) mb:", "w", 1.0),
       (r":UGRD:10 m above ground:", "10u", 1.0), (r":VGRD:10 m above ground:", "10v", 1.0),
       (r":MSLET:mean sea level:", "msl", 1.0), (r":PRMSL:mean sea level:", "msl", 1.0),
       (r":CAPE:", "mucape", 1.0), (r":PWAT:entire", "tcwv", 1.0), (r":APCP:surface:0-\d+ hour acc", "tp", 1000.0),
       (r":LAND:surface:", "lsm", 1.0), (r":TMP:2 m above ground:", "2t", 1.0), (r":DPT:2 m above ground:", "2d", 1.0)]
FALLBACK = {"n": 0}
_idx, _raw = {}, {}
# the maps refresh after every GFS cycle (Fahad, 28 Nov 2026: «تحدث مع كل تحديث تشغيلي للنموذج الأمريكي والأوروبي»):
# a GFS 06/18 cycle (or a 00 cycle before the IFS 00 run reaches 15 days) reads the newest complete IFS 00/12 run.
# ALIAS[gfs cycle] = (IFS cycle, hours between them): every call keeps the GFS cycle's step frame (fh from the GFS
# run), only the file read is the IFS run's step fh + hours.
ALIAS = {}
STATIC_PARS = ("lsm", "z")


def latest_full(t0, tries=4):
    """the newest IFS 00/12 cycle at or before t0 (datetime) that reaches 360 h, or None"""
    from datetime import timedelta
    t = t0.replace(hour=0 if t0.hour < 12 else 12, minute=0, second=0, microsecond=0)
    for _ in range(tries):
        c = t.strftime("%Y%m%d%H")
        try:
            _get(_url_real(c, 360) + ".index", tries=2)
            return c
        except Exception:  # noqa: BLE001
            t -= timedelta(hours=12)
    return None


def _get(url, rng=None, tries=8):
    for k in range(tries):
        u = url if k % 2 == 0 else url.replace(EC, MIRROR)      # alternate AWS and ECMWF's own server
        try:
            req = urllib.request.Request(u, headers={"Range": "bytes=%d-%d" % rng} if rng else {})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise
            print("ECMWF fetch retry", k + 1, u.split("/")[2], repr(e)[:120], flush=True)
            time.sleep(3 + 4 * k)


def steps(cycle):
    if cycle in ALIAS:
        ec, off = ALIAS[cycle]
        return [x - off for x in steps(ec) if x >= off]
    hh = int(cycle[8:10])
    if hh in (6, 18):
        return list(range(0, 91, 3))
    return list(range(0, 145, 3)) + list(range(150, 361, 6))


def _url(cycle, fh):
    if cycle in ALIAS:
        cycle, fh = ALIAS[cycle][0], fh + ALIAS[cycle][1]
    return _url_real(cycle, fh)


def _url_real(cycle, fh):
    d, hh = cycle[:8], cycle[8:10]
    return f"{EC}/{d}/{hh}z/ifs/0p25/oper/{d}{hh}0000-{fh}h-oper-fc"


def _index(cycle, fh):
    k = (cycle, fh)
    if k not in _idx:
        _idx[k] = [json.loads(x) for x in _get(_url(cycle, fh) + ".index").decode().splitlines()]
    return _idx[k]


def _field(cycle, fh, par, lev):
    import pygrib
    if par in STATIC_PARS and cycle in ALIAS:     # the static fields are in the IFS run's step 0 only
        fh = -ALIAS[cycle][1]
    key = (cycle, fh, par, lev)
    if key not in _raw:
        it = next(x for x in _index(cycle, fh) if x["param"] == par and x.get("levelist", "") == lev)
        _raw[key] = _get(_url(cycle, fh) + ".grib2", (it["_offset"], it["_offset"] + it["_length"] - 1))
        if len(_raw) > 400:        # keep memory bounded on the runner
            _raw.pop(next(iter(_raw)))
    g = pygrib.fromstring(_raw[key])
    a = np.asarray(g.values, dtype=np.float32)
    la = g.latlons()[0][:, 0]
    if la[0] < la[-1]:
        a = a[::-1]
    if float(g.latlons()[1][0, 0]) < 0:
        a = np.roll(a, a.shape[1] // 2, axis=1)
    return a


def available(cycle, fh=0):
    if cycle in ALIAS:              # "the run is complete": the IFS run's last step
        fh = min(fh, steps(cycle)[-1])
    try:
        _index(cycle, fh)
        return True
    except Exception as e:  # noqa: BLE001
        print("ECMWF not available:", cycle, fh, repr(e)[:150], flush=True)
        return False


class OutOfRange(ValueError):
    pass


def _at(cycle, fh, par, lev):
    st = steps(cycle)
    if fh > st[-1] or fh < 0:
        raise OutOfRange(f"step {fh} beyond the IFS run ({st[-1]} h)")
    if fh in st:
        return _field(cycle, fh, par, lev)
    lo = max(x for x in st if x < fh)
    hi = min(x for x in st if x > fh)
    w = (fh - lo) / (hi - lo)
    return (1 - w) * _field(cycle, lo, par, lev) + w * _field(cycle, hi, par, lev)


def lookup(pat):
    for rx, par, scale in MAP:
        m = re.search(rx, pat.replace("\\", ""))
        if m:
            return par, (m.group(1) if m.groups() else ""), scale
    return None


def fields_like_gfs(gfs_fields):
    def f(cycle, fh, extra=(), res="0p25", fields=None):
        fl = list(fields or []) + list(extra)
        out, rest = {}, []
        for name, pat in fl:
            m = lookup(pat)
            if m is None:
                rest.append((name, pat))
                continue
            par, lev, scale = m
            try:
                out[name] = _at(cycle, fh, par, lev) * scale
            except OutOfRange:
                raise                  # beyond the run: the caller decides (GFS has no such hour either)
            except Exception as e:  # noqa: BLE001
                print("ECMWF missing, GFS used:", cycle, fh, name, repr(e)[:100], flush=True)
                FALLBACK["n"] += 1
                rest.append((name, pat))
        if rest:
            # the ground height (static) and anything IFS open data lacks: GFS of the same cycle
            static = all(re.search(r":(HGT|LAND):surface:", p) for _, p in rest)
            out.update(gfs_fields(cycle, 0 if static else fh, res="0p25", fields=rest))
        return out
    return f
