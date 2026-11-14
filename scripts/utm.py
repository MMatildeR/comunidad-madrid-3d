"""Conversión lat/lon (ETRS89/WGS84) -> UTM huso 30N (EPSG:25830), sin pyproj.

Serie de Krüger estándar; error < 1 mm en el área de Madrid.
"""
import numpy as np

A = 6378137.0
F = 1 / 298.257222101  # GRS80
K0 = 0.9996
LON0 = np.radians(-3.0)
FALSE_E = 500000.0

_n = F / (2 - F)
_A = A / (1 + _n) * (1 + _n**2 / 4 + _n**4 / 64)
_alpha = [
    _n / 2 - 2 * _n**2 / 3 + 5 * _n**3 / 16,
    13 * _n**2 / 48 - 3 * _n**3 / 5,
    61 * _n**3 / 240,
]


def lonlat_to_utm30(lon, lat):
    lon = np.radians(np.asarray(lon, dtype=float))
    lat = np.radians(np.asarray(lat, dtype=float))
    e = np.sqrt(F * (2 - F))
    t = np.sinh(np.arctanh(np.sin(lat)) - e * np.arctanh(e * np.sin(lat)))
    dl = lon - LON0
    xi = np.arctan2(t, np.cos(dl))
    eta = np.arctanh(np.sin(dl) / np.sqrt(1 + t**2))
    x = eta.copy()
    y = xi.copy()
    for j, a in enumerate(_alpha, start=1):
        x = x + a * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
        y = y + a * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
    return FALSE_E + K0 * _A * x, K0 * _A * y
