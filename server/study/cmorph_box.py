"""CMORPH daily (ICDR gauge-adjusted 0.25 00Z-00Z netCDF, and BLD gauge-blended 0.25 EOD) for the study box."""
import bz2, sys, urllib.request, time, numpy as np
from datetime import date, timedelta
B = "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_RT/"
def get(u):
    for k in range(4):
        try: return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "climate-study/1.0"}), timeout=300).read()
        except Exception as e: err = e; time.sleep(5 * (k + 1))
    raise err
print(get(B + "BLD/CTL/CMORPH_V0.x_BLD_0.25deg-DLY_EOD.ctl").decode("latin-1"), flush=True)
import netCDF4
res = {}
d = date(2026, 9, 1)
while d < date(2026, 10, 16):
    try:
        open("/tmp/c.nc", "wb").write(get(B + f"ICDR/0.25deg-DLY_00Z/CMORPH_V0.x_ADJ_0.25deg-DLY_00Z_{d:%Y%m%d}.nc"))
        nc = netCDF4.Dataset("/tmp/c.nc")
        if d.day == 1: print({k: (v.shape, getattr(v, 'units', '')) for k, v in nc.variables.items()}, flush=True)
        lat = nc.variables["lat"][:]; lon = nc.variables["lon"][:]
        name = "cmorph"
        v = np.squeeze(nc.variables[name][:]).astype(np.float32)
        v = np.asarray(np.ma.filled(v, np.nan)); v[v < 0] = np.nan
        j = (lat >= 19.9) & (lat <= 24.1); i = (lon >= 38.9) & (lon <= 42.1)
        res[f"icdr_{d}"] = v[np.ix_(j, i)]; res["icdr_lat"] = lat[j]; res["icdr_lon"] = lon[i]
        print("icdr", d, name, np.nanmax(res[f"icdr_{d}"]), flush=True)
    except Exception as e:
        print("icdr", d, "fail", repr(e)[:150], flush=True)
    try:
        raw = bz2.decompress(get(B + f"BLD/{d:%Y}/{d:%Y%m}/CMORPH_V0.x_BLD_0.25deg-DLY_EOD_{d:%Y%m%d}.bz2"))
        res[f"bldraw_{d}"] = np.frombuffer(raw, np.uint8).copy() if False else None
        n = len(raw); print("bld", d, "bytes", n, flush=True)
        a = np.frombuffer(raw, "<f4")
        if a.size == 1440 * 720 * 2 or a.size == 1440 * 720:
            a = a[:1440 * 720].reshape(720, 1440)   # assume 89.875S north, lon 0.125 east
            la = -89.875 + 0.25 * np.arange(720); lo = 0.125 + 0.25 * np.arange(1440)
            j = (la >= 19.9) & (la <= 24.1); i = (lo >= 38.9) & (lo <= 42.1)
            x = a[np.ix_(j, i)].copy(); x[x < 0] = np.nan
            res[f"bld_{d}"] = x; res["bld_lat"] = la[j]; res["bld_lon"] = lo[i]
            print("bld", d, "max", np.nanmax(x), flush=True)
        res.pop(f"bldraw_{d}")
    except Exception as e:
        print("bld", d, "fail", repr(e)[:150], flush=True)
    d += timedelta(1)
np.savez_compressed(sys.argv[1], **res); print("saved", len(res))
