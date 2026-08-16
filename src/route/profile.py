"""
STEP 13E - Elevation profile computation.

Given route waypoints and an :py:class:`ElevationProvider`, produces per-segment
terrain features: distance, elevation, and gradient percentage.

Key formula (per segment):
    gradient_pct = (delta_elevation / horizontal_distance) * 100

Protects against zero-distance segments and documents why no aggressive
smoothing is applied.
"""

from __future__ import annotations

from src.route.distance import haversine_km

from typing import Optional

import numpy as np

from src.route.elevation import ElevationProvider, lookup_elevation_m


# ============================================================================
# Elevation profile result
# ============================================================================

class ElevationProfile:
    """Elevation profile result for a route segment sequence.

    Stores per-segment: horizontal distance (km), elevation (m),
    and gradient percentage.  Also provides aggregate statistics.

    Attributes
    ----------
    distances_km: list[float]
        Horizontal distance of each segment in km.
    elevations_m: list[float]
        Elevation at the end of each segment (from the provider), in metres.
    gradients_pct: list[float]
        Gradient percentage of each segment: (delta_elevation / distance) * 100.
        ``np.nan`` where distance is zero or data is missing.
    profile_source: str
        Label describing the elevation source (e.g. "MOCK_PROVIDER", "SRTM").
    """

    def __init__(
        self,
        distances_km: list[float],
        elevations_m: list[float],
        gradients_pct: list[float],
        profile_source: str,
    ):
        self.distances_km = distances_km
        self.elevations_m = elevations_m
        self.gradients_pct = gradients_pct
        self.profile_source = profile_source

    def __repr__(self) -> str:
        n = len(self.distances_km)
        return (
            f"ElevationProfile(n_segments={n}, "
            f"source={self.profile_source!r}, "
            f"has_nan_gradient={any(np.isnan(g) for g in self.gradients_pct)})"
        )

    @property
    def total_distance_km(self) -> float:
        """Sum of all segment distances."""
        return float(np.nansum(self.distances_km) if self.distances_km else 0.0)

    @property
    def total_elevation_gain_m(self) -> float:
        """Sum of positive elevation differences (gain only)."""
        gains = [e - p for e, p in zip(self.elevations_m, [0.0] + self.elevations_m[:-1])]
        return float(np.sum([g for g in gains if g > 0]))

    @property
    def total_elevation_loss_m(self) -> float:
        """Sum of negative elevation differences (loss only)."""
        losses = [p - e for e, p in zip(self.elevations_m, [0.0] + self.elevations_m[:-1])]
        return float(np.sum([l for l in losses if l > 0]))


# ============================================================================
# Profile computation
# ============================================================================

def compute_profile(
    waypoints: list["RoutePoint"],
    provider: ElevationProvider,
    segment_km: float | None = None,
) -> ElevationProfile:
    """Compute elevation profile from waypoints using the given provider.

    Parameters
    ----------
    waypoints: list[RoutePoint]
        Route waypoints in order.  Must have at least 2 points.
    provider: ElevationProvider
        Provider supplying elevations for the waypoints.
    segment_km: float | None
        If provided, forces equal-length segments of this size (km) for
        gradient calculation.  If ``None``, segments correspond to
        consecutive waypoint pairs.

    Returns
    -------
    ElevationProfile
        The computed elevation profile.

    Raises
    ------
    ValueError
        If fewer than 2 waypoints are given.
    """
    if len(waypoints) < 2:
        raise ValueError("compute_profile requires at least 2 waypoints")

    n_segments = len(waypoints) - 1

    # ---- Distances -------------------------------------------------------
    if segment_km is not None:
        # Equal-length segments as specified
        distances_km = [segment_km] * n_segments
    else:
        # Consecutive waypoint pairs using haversine
        distances_km = [
            haversine_km(waypoints[i].latitude, waypoints[i].longitude,
                                       waypoints[i + 1].latitude, waypoints[i + 1].longitude)
            for i in range(n_segments)
        ]

    # ---- Elevations ------------------------------------------------------
    # Collect waypoint lat/lon for the provider; we query elevations at
    # each waypoint position.  The provider may return np.nan for unknown.
    lats = np.array([w.latitude for w in waypoints], dtype=float)
    lons = np.array([w.longitude for w in waypoints], dtype=float)
    elevs = provider.get_elevations(lats, lons)  # np.ndarray, may contain nan

    # Elevation at the end of each segment = elevation at the *downstream* waypoint
    # Segment i goes from waypoint i to waypoint i+1; elevation at end = elevs[i+1]
    elevations_m = [float(elevs[i + 1]) if i + 1 < len(elevs) else np.nan
                   for i in range(n_segments)]

    # ---- Gradients -------------------------------------------------------
    gradients_pct = []
    for d, e_from, e_to in zip(distances_km, [0.0] + elevations_m[:-1], elevations_m):
        if d is None or d == 0 or np.isnan(d) or np.isnan(e_to) or np.isnan(e_from):
            gradients_pct.append(np.nan)
        else:
            gradients_pct.append((e_to - e_from) / d * 100.0)

    return ElevationProfile(
        distances_km=distances_km,
        elevations_m=elevations_m,
        gradients_pct=gradients_pct,
        profile_source=provider.__class__.__name__,
    )

    @staticmethod
    def _haversine_km_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Convenience: haversine distance in km between two points."""
        from src.route.distance import haversine_km
        return haversine_km(lat1, lon1, lat2, lon2)


# ============================================================================
# High-level convenience function
# ============================================================================

def elevation_profile_from_route(
    waypoints: list["RoutePoint"],
    provider: ElevationProvider,
    segment_km: float | None = None,
) -> ElevationProfile:
    """Convenience wrapper for :py:func:`compute_profile`.

    Parameters
    ----------
    waypoints: list[RoutePoint]
        Route waypoints in order.
    provider: ElevationProvider
        Elevation data source.
    segment_km: float | None, optional
        If provided, equal-length segments of this size (km) are used
        for gradient calculation.  If ``None``, segments correspond to
        consecutive waypoint pairs.

    Returns
    -------
    ElevationProfile
        The computed profile containing distances, elevations, and gradients.
    """
    return compute_profile(waypoints, provider, segment_km=segment_km)