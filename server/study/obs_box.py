#!/usr/bin/env python3
"""Convective-season model test (Fahad, 19 Nov 2026): observed daily rain 1 Sep-15 Oct 2026 over Makkah's east and
southeast (box 20-24 N, 39-42 E), from every public satellite source reachable from Actions. Saves obs.npz."""
import gzip, re, sys, time, urllib.request
from datetime import date, timedelta
import numpy as np

UA = "climate-study/1.0"
S, N, W, E = 20.0, 24.0, 39.0, 42.0
D0, D1 = date(2026, 9, 1), date(2026, 10, 16)


def get(url, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (k + 1))
    raise err


def listing(url):
    try:
        t = get(url, 2).decode("latin-1")
        return re.findall(r'href="([^"?#][^"]*)"', t)
    except Exception as e:  # noqa: BLE001
        print("LIST failed", url, repr(e)[:150], flush=True)
        return []


def days():
    d = D0
    while d < D1:
        yield d
        d += timedelta(1)


def crop_global(a, res, lat_top, lon0):
    """a[j, i] with lat from lat_top going down, lon from lon0 eastward"""
    j0 = int(round((lat_top - N) / res)); j1 = int(round((lat_top - S) / res))
    i0 = int(round((W - lon0) / res)); i1 = int(round((E - lon0) / res))
    return a[j0:j1, i0:i1]


def persiann_bin(raw, ny, nx):
    for dt in (">i2", "<i2", ">f4", "<f4"):
        if len(raw) != ny * nx * np.dtype(dt).itemsize:
            continue
        a = np.frombuffer(raw, dtype=dt).reshape(ny, nx).astype(np.float32)
        a = np.where(a < 0, np.nan, a / 100.0 if dt.endswith("i2") else a)
        mx = np.nanmax(a)
        if 1 < mx < 3000:
            return a, dt
    return None, None


def persiann_family(name, base, ny, nx, res, lat_top):
    files = listing(base)
    print("PROBE", name, base, len(files), files[:4], files[-4:], flush=True)
    out = {}
    for d in days():
        pats = [d.strftime("%y%m%d"), d.strftime("%Y%m%d"), d.strftime("%y") + "%03d" % d.timetuple().tm_yday,
                d.strftime("%Y") + "%03d" % d.timetuple().tm_yday]
        cand = [f for f in files if any(p in f for p in pats)]
        if not cand:
            continue
        try:
            raw = get(base + cand[0])
            if cand[0].endswith(".gz"):
                raw = gzip.decompress(raw)
            a, dt = persiann_bin(raw, ny, nx)
            if a is None:
                print(name, cand[0], "size", len(raw), "not understood", flush=True)
                continue
            out[d.isoformat()] = crop_global(a, res, lat_top, 0.0)
            print(name, d, cand[0], dt, "boxmax", np.nanmax(out[d.isoformat()]), flush=True)
        except Exception as e:  # noqa: BLE001
            print(name, d, "fail", repr(e)[:150], flush=True)
    return out


def chirps_iri(ver):
    url = (f"https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.{ver}/.daily-improved/.global/.0p05/.prcp/"
           f"X/{W}/{E}/RANGEEDGES/Y/{S}/{N}/RANGEEDGES/T/(1%20Sep%202026)/(15%20Oct%202026)/RANGEEDGES/data.nc")
    try:
        raw = get(url, 2)
        open("/tmp/chirps.nc", "wb").write(raw)
        import netCDF4
        nc = netCDF4.Dataset("/tmp/chirps.nc")
        print("CHIRPS", ver, {k: nc.variables[k].shape for k in nc.variables}, flush=True)
        return nc
    except Exception as e:  # noqa: BLE001
        print("CHIRPS", ver, "failed", repr(e)[:200], flush=True)
        return None


def main():
    res = {}
    fam = [("pdir", "https://persiann.eng.uci.edu/CHRSdata/PDIRNow/PDIRNowdaily/", 3000, 9000, 0.04, 60.0),
           ("ccs", "https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/daily/", 3000, 9000, 0.04, 60.0),
           ("pers", "https://persiann.eng.uci.edu/CHRSdata/PERSIANN/daily/", 480, 1440, 0.25, 60.0)]
    for name, base, ny, nx, r, top in fam:
        o = persiann_family(name, base, ny, nx, r, top)
        for k, v in o.items():
            res[f"{name}_{k}"] = v
    for u in ["https://persiann.eng.uci.edu/CHRSdata/", "https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/",
              "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH2/", "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_RT/",
              "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH2/CMORPH2NRT/", "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_RT/GLOBE/",
              "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_RT/GLOBE/data/2026/",
              "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2026/",
              "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/2026/",
              "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/", "https://data.chc.ucsb.edu/products/CHIRPS-2.0/prelim/global_daily/tifs/p05/2026/"]:
        f = listing(u)
        print("PROBE", u, len(f), f[:8], f[-8:], flush=True)
    for ver in ("v2p0", "v3p0"):
        nc = chirps_iri(ver)
        if nc is not None:
            v = nc.variables["prcp"][:]
            print("CHIRPS", ver, "shape", v.shape, "max", float(np.nanmax(v)), flush=True)
            res[f"chirps_{ver}"] = np.asarray(v.filled(np.nan) if hasattr(v, "filled") else v, dtype=np.float32)
            res[f"chirps_{ver}_lat"] = nc.variables["Y"][:]
            res[f"chirps_{ver}_lon"] = nc.variables["X"][:]
            res[f"chirps_{ver}_t"] = nc.variables["T"][:]
    np.savez_compressed(sys.argv[1], **res)
    print("saved", len(res), flush=True)


if __name__ == "__main__":
    main()
