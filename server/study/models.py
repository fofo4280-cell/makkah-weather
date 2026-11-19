import sys, os, time, urllib.request, numpy as np, eccodes
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
S,N,W,E = 20.0, 24.0, 39.0, 42.0
LAT = np.arange(N, S-0.01, -0.25); LON = np.arange(W, E+0.01, 0.25)
def get(url, rng=None):
    for k in range(6):
        try:
            h={"User-Agent":"study/1.0"}
            if rng: h["Range"]="bytes=%d-%d"%rng
            with urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=120) as r: return r.read()
        except Exception as e:
            err=e; time.sleep(3*(k+1))
    raise err
def decode(buf):
    g = eccodes.codes_new_from_message(buf)
    ni, nj = eccodes.codes_get(g,"Ni"), eccodes.codes_get(g,"Nj")
    la0, lo0 = eccodes.codes_get(g,"latitudeOfFirstGridPointInDegrees"), eccodes.codes_get(g,"longitudeOfFirstGridPointInDegrees")
    v = eccodes.codes_get_values(g).reshape(nj, ni); eccodes.codes_release(g)
    lo0 = lo0 % 360
    j = np.round((la0 - LAT)/0.25).astype(int); i = np.round(((LON - lo0) % 360)/0.25).astype(int)
    return v[np.ix_(j,i)].astype(np.float32)
def gfs(run, h):
    base=f"https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{run:%Y%m%d}/{run.hour:02d}/atmos/gfs.t{run.hour:02d}z.pgrb2.0p25.f{h:03d}"
    idx=get(base+".idx").decode().splitlines()
    for k,l in enumerate(idx):
        if f":APCP:surface:0-{h} hour acc" in l or (h%24==0 and f":APCP:surface:0-{h//24} day acc" in l):
            a=int(l.split(":")[1]); b=int(idx[k+1].split(":")[1])-1
            return decode(get(base,(a,b)))
    raise RuntimeError("no apcp "+base)
def ec(run, h):
    import json
    base=f"https://storage.googleapis.com/ecmwf-open-data/{run:%Y%m%d}/{run.hour:02d}z/ifs/0p25/oper/{run:%Y%m%d%H}0000-{h}h-oper-fc"
    for l in get(base+".index").decode().splitlines():
        d=json.loads(l)
        if d["param"]=="tp":
            return decode(get(base+".grib2",(d["_offset"],d["_offset"]+d["_length"]-1)))*1000.0
from datetime import datetime
def job(args):
    m, d, lead = args
    f = gfs if m=="gfs" else ec
    if lead=="d1":  run=datetime(d.year,d.month,d.day)-timedelta(hours=12); h0,h1=12,36
    elif lead=="d0": run=datetime(d.year,d.month,d.day); h0,h1=0,24
    else: run=datetime(d.year,d.month,d.day)-timedelta(hours=36); h0,h1=36,60
    try:
        a1=f(run,h1); a0=f(run,h0) if h0>0 else 0
        return (m,d.isoformat(),lead,np.maximum(a1-a0,0))
    except Exception as e:
        print("fail",m,d,lead,repr(e)[:150],flush=True); return (m,d.isoformat(),lead,None)
d0=date(2026,9,1); days=[d0+timedelta(k) for k in range(45)]  # to 15 Oct
jobs=[(m,d,l) for m in ("gfs",) for d in days for l in ("d0",)]
out={}
with ThreadPoolExecutor(8) as ex:
    for m,d,l,a in ex.map(job,jobs):
        if a is not None: out[f"{m}_{l}_{d}"]=a
np.savez_compressed("models_b.npz", lat=LAT, lon=LON, **out)
print("done",len(out),"of",len(jobs))
