"""Probe (test branch only): can the Actions runner read ECMWF open data?"""
import time, urllib.request, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
for u in ["https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/20261119/12z/ifs/0p25/oper/20261119120000-360h-oper-fc.index",
          "https://data.ecmwf.int/forecasts/20261119/12z/ifs/0p25/oper/20261119120000-360h-oper-fc.index",
          "https://ai4edataeuwest.blob.core.windows.net/ecmwf/20261119/12z/ifs/0p25/oper/20261119120000-360h-oper-fc.index"]:
    t = time.time()
    try:
        with urllib.request.urlopen(u, timeout=60) as r:
            print("OK", r.status, len(r.read()), round(time.time() - t, 1), u, flush=True)
    except Exception as e:
        print("FAIL", repr(e)[:300], round(time.time() - t, 1), u, flush=True)
import ecmwf
print("module", ecmwf.__file__)
t = time.time(); print("available", ecmwf.available("2026111912", 360), round(time.time() - t, 1))
