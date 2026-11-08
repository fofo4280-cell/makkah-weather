"""Synoptic Rossby waves at 500 hPa: zonal wavenumbers 4-8 and the Plumb (1985) wave-activity flux."""
import numpy as np

A, OMEGA, G = 6.371e6, 7.292e-5, 9.80665
# soft band: half weight at the edges so the waves do not ring
WEIGHTS = {3: 0.5, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 0.5}


def band(z):
    """Keep zonal wavenumbers 4-8 (soft edges) of a lat x lon (global, 1 degree) field."""
    f = np.fft.rfft(z, axis=1)
    w = np.zeros(f.shape[1])
    for k, v in WEIGHTS.items():
        w[k] = v
    return np.fft.irfft(f * w[None, :], n=z.shape[1], axis=1)


def plumb_flux(zp, lat, lon, p_hpa=500.0):
    """Horizontal Plumb stationary wave-activity flux (m^2/s^2) from the wave height zp (gpm)."""
    phi = np.radians(lat)[:, None]
    lam = np.radians(lon)
    f = 2 * OMEGA * np.sin(phi)
    with np.errstate(divide="ignore", invalid="ignore"):
        psi = np.where(np.abs(np.degrees(phi)) >= 10, G * zp / f, 0.0)
    dl = lam[1] - lam[0]
    dp = np.radians(lat[1] - lat[0])
    psi_l = (np.roll(psi, -1, 1) - np.roll(psi, 1, 1)) / (2 * dl)
    psi_ll = (np.roll(psi, -1, 1) - 2 * psi + np.roll(psi, 1, 1)) / dl ** 2
    psi_p = np.gradient(psi, dp, axis=0)
    psi_lp = np.gradient(psi_l, dp, axis=0)
    c = np.cos(phi)
    pf = p_hpa / 1000.0
    with np.errstate(divide="ignore", invalid="ignore"):
        fx = pf * c / (2 * A ** 2 * c ** 2) * (psi_l ** 2 - psi * psi_ll)
        fy = pf * c / (2 * A ** 2 * c) * (psi_l * psi_p - psi * psi_lp)
    mask = np.abs(np.degrees(phi)) < 12
    fx = np.where(mask, 0, np.nan_to_num(fx))
    fy = np.where(mask, 0, np.nan_to_num(fy))
    return fx, fy


def extremes(zp, lat, lon, box, size=13, minimum=20.0):
    """Highs and lows of the wave field inside box (south, north, west, east): [(kind, lat, lon, value)]."""
    from scipy.ndimage import maximum_filter, minimum_filter
    s, n, w, e = box
    out = []
    hi = (zp == maximum_filter(zp, size=size, mode="wrap")) & (zp >= minimum)
    lo = (zp == minimum_filter(zp, size=size, mode="wrap")) & (zp <= -minimum)
    for kind, m in (("H", hi), ("L", lo)):
        for j, i in zip(*np.nonzero(m)):
            if s <= lat[j] <= n and w <= lon[i] <= e:
                out.append((kind, float(lat[j]), float(lon[i]), float(zp[j, i])))
    return out
