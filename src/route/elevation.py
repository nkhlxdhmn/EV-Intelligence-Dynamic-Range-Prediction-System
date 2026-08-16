"""
STEP 13D - Elevation provider abstraction.

Defines the :py:class:`ElevationProvider` interface and a concrete
in-memory/mock provider for testing.  The interface is designed so that
real DEM providers (SRTM, Copernicus, online API) can be swapped in
without changing the ML model or the route terrain feature pipeline.

Rules:
- No internet dependency for the core / test setup.
- get_elevations returns elevations in metres for given lat/lon points.
- The provider may return ``np.nan`` for unknown points; callers must
  handle missing data (never fabricate).
"""

from __future__ import annotations

from typing import Optional

import numpy as np


# ============================================================================
# ElevationProvider interface
# ============================================================================

class ElevationProvider:
    """Abstract provider of elevation data for route waypoints.

    Subclasses implement ``get_elevations`` to return elevations for
    a sequence of (latitude, longitude) points.  The base class defines
    the contract and a small in-memory mock useful for unit testing.

    Notes
    -----
    - Returns ``np.nan`` for elevations that cannot be determined;
      callers must not fabricate values.
    - The interface is deliberately minimal — only ``get_elevations``
      is required.  Additional methods (caching, error handling,
      logging) can be added in subclasses.
    """

    def get_elevations(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        """Return elevation (metres) for each (lat, lon) pair.

        Parameters
        ----------
        lats: np.ndarray
            1-D array of decimal-degrees latitude values.
        lons: np.ndarray
            1-D array of decimal-degrees longitude values.

        Returns
        -------
        np.ndarray
            1-D array of elevation values in metres, same length as *lats*.
            May contain ``np.nan`` where elevation is unknown.
        """
        raise NotImplementedError(
            "ElevationProvider.get_elevations() is not implemented."
        )


# ============================================================================
# In-memory / mock provider for testing / demos
# ============================================================================

class MockElevationProvider(ElevationProvider):
    """Simple in-memory elevation provider for testing and demonstrations.

    Stores a static set of (lat, lon, elevation) tuples and interpolates
    for query points.  The profile is a gentle sinusoidal hill — useful
    for testing terrain feature calculations without requiring a DEM.

    Parameters
    ----------
    points: list[tuple[float, float, float]], optional
        List of ``(latitude, longitude, elevation_m)`` tuples defining
        the mock terrain.  If provided, these points serve as the
        known elevation dataset; queries between them are interpolated.
        If ``None``, a default gentle sinusoidal hill is used.
    """

    def __init__(self, points: Optional[list[tuple[float, float, float]]] = None):
        if points is not None:
            self._lats = np.array([p[0] for p in points], dtype=float)
            self._lons = np.array([p[1] for p in points], dtype=float)
            self._elevations = np.array([p[2] for p in points], dtype=float)
        else:
            # Default: gentle sinusoidal hill centred at 150 m
            # longitude varies  -120 to -110, latitude  35 to 40
            n = 37
            self._lats = np.linspace(35.0, 40.0, n)
            self._lons = np.linspace(-120.0, -110.0, n)
            amplitude = 25.0
            period_lat = 5.0
            period_lon = 10.0
            self._elevations = (
                150.0
                + amplitude
                * np.sin(2 * np.pi * self._lats / period_lat)
                + amplitude * 0.5
                * np.sin(2 * np.pi * self._lons / period_lon)
            )

    def get_elevations(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        """Return elevation (m) for each (lat, lon) pair via nearest-neighbor.

        Parameters
        ----------
        lats: np.ndarray
            1-D array of latitude values.
        lons: np.ndarray
            1-D array of longitude values.

        Returns
        -------
        np.ndarray
            1-D array of elevation values in metres.  Contains ``np.nan``
            for points that cannot be matched to the mock dataset.
        """
        lats = np.asarray(lats, dtype=float)
        lons = np.asarray(lons, dtype=float)
        result = np.full_like(lats, np.nan, dtype=float)

        if self._lats.size == 0 or self._lons.size == 0:
            return result

        # Nearest-neighbor search: for each query point, find the closest
        # mock dataset point and use its elevation.
        for i, (q_lat, q_lon) in enumerate(zip(lats, lons)):
            # Compute squared distances to all mock points
            d2 = (self._lats - q_lat) ** 2 + (self._lons - q_lon) ** 2
            j = int(np.argmin(d2))
            result[i] = self._elevations[j]

        return result


# ============================================================================
# Provider helper: nearest-nelevation lookup
# ============================================================================

def lookup_elevation_m(
    provider: ElevationProvider,
    lat: float,
    lon: float,
) -> float:
    """Return elevation for a single point using *provider*.

    Parameters
    ----------
    provider: ElevationProvider
        A concrete implementation (e.g. :py:class:`MockElevationProvider`).
    lat: float
        Latitude in decimal degrees.
    lon: float
        Longitude in decimal degrees.

    Returns
    -------
    float
        Elevation in metres, or ``np.nan`` if the provider returns
        ``np.nan`` for this point.
    """
    elevations = provider.get_elevations(np.array([lat]), np.array([lon]))
    return float(elevations[0]) if not np.isnan(elevations[0]) else np.nan


# ============================================================================
# Module compatibility / introspection
# ============================================================================

__all__ = [
    "ElevationProvider",
    "MockElevationProvider",
    "lookup_elevation_m",
]