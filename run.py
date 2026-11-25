import json, os, sys
from datetime import datetime, timedelta
import numpy as np
sys.path.insert(0, "code/server/climate")
import pwreg, ecmwf, daily as D
cycle = sys.argv[1]
clim = dict(np.load("/home/runner/clim/clim.npz"))
plat, plon = clim["pw_lat"], clim["pw_lon"]
t0 = datetime.strptime(cycle, "%Y%m%d%H")
latq, lonq = np.linspace(90, -90, 721), np.arange(0, 360, 0.25)
rows, boxes = [], []
for k in range(16):
    dt = t0 + timedelta(days=k)
    a = np.asarray(ecmwf._at(cycle, 24 * k, "tcwv", ""), dtype=np.float32)
    rows.append({"d": dt.strftime("%Y-%m-%d"), **pwreg.row(a, latq, lonq, clim["pw"][D.doy(dt)], plat, plon)})
    b = {"d": rows[-1]["d"]}
    g1 = a[::4, ::4]
    for key, (name, s, n, w, e) in D.BOXES.items():
        g = D.box_mean(g1, D.LAT1, D.LON1, s, n, w, e); c = D.box_mean(clim["pw"][D.doy(dt)], plat, plon, s, n, w, e)
        b[key] = int(round(100 * g / max(c, 1)))
    boxes.append(b)
    print(rows[-1]["d"], {k_: v["pct"] for k_, v in rows[-1].items() if k_ != "d"}, flush=True)
os.makedirs("o", exist_ok=True)
json.dump({"model": "ecmwf", "names": pwreg.names(), "rows": rows}, open("o/pw_reg.json", "w"), ensure_ascii=False)
json.dump(boxes, open("o/boxes.json", "w"))
np.savez_compressed("o/clim_pw.npz", pw=clim["pw"], pw_lat=plat, pw_lon=plon)
