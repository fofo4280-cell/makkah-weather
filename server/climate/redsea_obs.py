"""Probe (test branch only): ECMWF fetch through the mirror when AWS fails."""
import sys, time
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import ecmwf
real = ecmwf.EC
ecmwf.EC = "https://ecmwf-forecasts-broken.s3.eu-central-1.amazonaws.com"
t = time.time()
print("avail via mirror", ecmwf.available("2026111912", 360), round(time.time() - t, 1), flush=True)
a = ecmwf._field("2026111912", 24, "r", "700")
ecmwf.EC = real; ecmwf._idx.clear(); ecmwf._raw.clear()
b = ecmwf._field("2026111912", 24, "r", "700")
print("RESULT", a.shape, "max diff mirror vs aws", float(np.abs(a - b).max()), "mean", float(a.mean()), flush=True)
