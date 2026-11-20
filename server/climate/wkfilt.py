"""Tropical waves in the 200 hPa velocity potential, isolated by filtering in wavenumber and frequency
(after Wheeler and Kiladis): two families that move the upper-level outflow of deep convection.

  Kelvin family: eastward, planetary wavenumbers 1-9, periods 2-30 days, phase speed 8-60 m/s
                 (convectively coupled Kelvin waves; the slow MJO, about 5 m/s, is left out).
  Rossby family: westward, wavenumbers 1-9, periods 5-90 days, phase speed 0.5-25 m/s
                 (equatorial Rossby waves and the westward-moving part of the monsoon disturbances).

Input: the daily chi anomaly (the past analyses, then the 15-day GFS forecast, then zeros), so the forecast days
are filtered too; as with every such filter, the last days are the least certain.
Sign: chi as it is (m^2/s). Negative = divergence aloft, rising air (supports convection); positive = convergence
aloft, sinking air. The divergent wind (the gradient of chi) blows out of the negative centres.
"""
import numpy as np

EARTH = 40.03e6                  # equatorial circumference (m)
DAY = 86400.0
FAMILIES = {
    "kel": {"east": True, "kmin": 1, "kmax": 9, "pmin": 2.0, "pmax": 30.0, "cmin": 8.0, "cmax": 60.0},
    "ros": {"east": False, "kmin": 1, "kmax": 9, "pmin": 5.0, "pmax": 90.0, "cmin": 0.5, "cmax": 25.0},
}
KSA = (16, 32, 36, 55)           # south, north, west, east: the Kingdom box (as in mjofilt)


def wk_filter(X, east, kmin, kmax, pmin, pmax, cmin, cmax, pad=120, taper=20):
    """X: (days, lat, lon), daily. Keep one direction, wavenumbers kmin..kmax, periods pmin..pmax days and phase
    speeds cmin..cmax m/s (measured along the equator)."""
    nt, ny, nx = X.shape
    Y = X - X.mean(0)
    t = np.arange(nt, dtype=float) - (nt - 1) / 2
    Y = Y - ((Y * t[:, None, None]).sum(0) / (t ** 2).sum()) * t[:, None, None]
    w = np.ones(nt)
    w[:taper] = 0.5 * (1 - np.cos(np.pi * np.arange(taper) / taper))   # only the start: the end is what we want
    Y = np.concatenate([Y * w[:, None, None], np.zeros((pad, ny, nx))])
    F = np.fft.fft2(Y, axes=(0, 2))
    f = np.fft.fftfreq(Y.shape[0])[:, None]              # cycles per day
    k = np.fft.fftfreq(nx, 1.0 / nx)[None, :]            # waves around the globe
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.abs(f) * EARTH / np.abs(k) / DAY          # phase speed, m/s
    dirn = (f * k < 0) if east else (f * k > 0)          # exp(i(kx - wt)): eastward when f and k differ in sign
    keep = ((np.abs(k) >= kmin) & (np.abs(k) <= kmax) & (np.abs(f) >= 1 / pmax) & (np.abs(f) <= 1 / pmin)
            & dirn & (c >= cmin) & (c <= cmax))
    F *= keep[:, None, :]
    return np.real(np.fft.ifft2(F, axes=(0, 2)))[:nt]


def run(series, lat, band=(-40, 40)):
    """series: [(date, chi anomaly on lat x 0..359, m^2/s)] daily and continuous. Returns
    ({'kel': array, 'ros': array} on the band, band latitudes, info for the page and the report)."""
    j = (lat >= band[0]) & (lat <= band[1])
    X = np.stack([a[j] for _, a in series]).astype(np.float64)
    out = {name: wk_filter(X, **p) for name, p in FAMILIES.items()}
    la = lat[j]
    s, n, w, e = KSA
    jj = (la >= s) & (la <= n)
    lon = np.arange(X.shape[2]) * 360.0 / X.shape[2]
    ii = (lon >= w) & (lon <= e)
    eq = (la >= -10) & (la <= 10)
    info = {"days": [d.isoformat() for d, _ in series]}
    for name, a in out.items():
        info[name + "_ksa"] = [round(float(a[k][np.ix_(jj, ii)].mean()) / 1e6, 2) for k in range(len(series))]
        # the strongest divergence aloft along the equator: where the family's active phase is
        info[name + "_core"] = [int(lon[int(np.argmin(a[k][eq].mean(0)))]) for k in range(len(series))]
    return out, la, info
