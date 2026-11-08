"""Velocity potential and divergent wind on a global latitude-longitude grid (spherical harmonics)."""
import numpy as np

A = 6.371e6


def _dh(field):
    """Drop the south-pole row so the grid is the n x 2n Driscoll-Healy layout pyshtools expects."""
    return field[:-1] if field.shape[0] == field.shape[1] // 2 + 1 else field


def divergence(u, v, lat, lon):
    """Horizontal divergence (1/s); lat descending from 90, lon ascending, periodic."""
    phi, lam = np.radians(lat)[:, None], np.radians(lon)
    dlam = lam[1] - lam[0]
    cos = np.cos(phi)
    dudl = (np.roll(u, -1, axis=1) - np.roll(u, 1, axis=1)) / (2 * dlam)
    vc = v * cos
    dvc = np.gradient(vc, np.radians(lat), axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = (dudl + dvc) / (A * cos)
    d[np.abs(cos[:, 0]) < 1e-6] = 0.0
    return np.nan_to_num(d)


def velocity_potential(u, v, lat, lon):
    """chi with laplacian(chi) = divergence; returns an array on the input grid (m^2/s)."""
    import pyshtools as pysh
    d = divergence(u, v, lat, lon)
    full = d.shape[0] == d.shape[1] // 2 + 1
    c = pysh.SHGrid.from_array(_dh(d)).expand()
    l = np.arange(c.lmax + 1, dtype=float)
    f = np.zeros_like(l)
    f[1:] = -A ** 2 / (l[1:] * (l[1:] + 1))
    c.coeffs = c.coeffs * f[None, :, None]
    chi = c.expand(grid="DH2", extend=False).data
    if full:  # put the south pole back (copy of the last row)
        chi = np.vstack([chi, chi[-1:]])
    return chi


def divergent_wind(chi, lat):
    """u, v of the divergent wind (m/s): the gradient of chi."""
    phi = np.radians(lat)[:, None]
    nlon = chi.shape[1]
    dlam = 2 * np.pi / nlon
    with np.errstate(divide="ignore", invalid="ignore"):
        u = (np.roll(chi, -1, axis=1) - np.roll(chi, 1, axis=1)) / (2 * dlam) / (A * np.cos(phi))
    v = np.gradient(chi, np.radians(lat), axis=0) / A
    return np.nan_to_num(u), v


def smooth(field, trunc=30):
    """Keep only the planetary scales: spherical-harmonic truncation at degree 'trunc' (T30 ~ 650 km)."""
    import pyshtools as pysh
    full = field.shape[0] == field.shape[1] // 2 + 1
    c = pysh.SHGrid.from_array(_dh(np.asarray(field, dtype=float))).expand()
    c.coeffs[:, trunc + 1:, :] = 0
    out = c.expand(grid="DH2", extend=False).data
    return np.vstack([out, out[-1:]]) if full else out
