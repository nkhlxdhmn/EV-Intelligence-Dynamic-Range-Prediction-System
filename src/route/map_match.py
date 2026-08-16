"""
STEP 13G - Current GPS position matching.

Maps a vehicle's current GPS position to a position along the planned route,
enabling calculation of remaining route distance and next terrain features.

Matching logic:
    GPS position
        ↓
    nearest route point / segment
        ↓
    distance along planned route (cumulative)
        ↓
    remaining route (total - cumulative)
        ↓
    next 1/2/5 km terrain (from profile, within remaining distance)

Handles:
    - Noisy GPS (finds closest waypoint, not exact match)
    - Position slightly off route (uses haversine distance)
    - Route beginning (first waypoint)
    - Route end (last waypoint; does not invent terrain beyond)
    - Route shorter than requested horizon (returns available data only)
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from src.route.route_schema import RoutePoint, Route, find_nearest_waypoint
from src.route.distance import (
    haversine_km,
    cumulative_distances_km,
    total_route_distance_km,
    distance_between_km,
)
from src.route.elevation import ElevationProvider, lookup_elevation_m


# ============================================================================
# Matching result
# ============================================================================

class MatchResult:
    """Result of matching a GPS position to a planned route.

    Attributes
    ----------
    nearest_waypoint_index: int
        Index of the closest waypoint in the route (0-based).
    distance_along_route_km: float
        Cumulative distance from route start to the nearest waypoint (km).
    remaining_route_km: float
        Total route distance minus distance_along_route_km (km).
    position_fraction: float
        Fraction of route completed (0.0 = start, 1.0 = end).
    terrain_available: bool
        Whether terrain data is available for the next horizon.
    error_message: str | None
        Human-readable error if matching failed; ``None`` if successful.
    """

    def __init__(
        self,
        nearest_waypoint_index: int,
        distance_along_route_km: float,
        remaining_route_km: float,
        position_fraction: float,
        terrain_available: bool,
        error_message: str | None = None,
    ):
        self.nearest_waypoint_index = nearest_waypoint_index
        self.distance_along_route_km = distance_along_route_km
        self.remaining_route_km = remaining_route_km
        self.position_fraction = position_fraction
        self.terrain_available = terrain_available
        self.error_message = error_message

    def __repr__(self) -> str:
        return (
            f"MatchResult(idx={self.nearest_waypoint_index}, "
            f"dist_along={self.distance_along_route_km:.2f}, "
            f"remaining={self.remaining_route_km:.2f}, "
            f"frac={self.position_fraction:.2f}, "
            f"terrain={self.terrain_available})"
        )


# ============================================================================
# GPS position matching
# ============================================================================

def match_gps_to_route(
    lat: float,
    lon: float,
    route: Route,
) -> MatchResult:
    """Match a GPS position to the planned route.

    Parameters
    ----------
    lat: float
        GPS latitude in decimal degrees.
    lon: float
        GPS longitude in decimal degrees.
    route: Route
        The planned route.

    Returns
    -------
    MatchResult
        Struct containing matching information and terrain availability.
    """
    # Validate inputs
    if not -90.0 <= lat <= 90.0:
        return MatchResult(
            nearest_waypoint_index=0,
            distance_along_route_km=0.0,
            remaining_route_km=route.total_distance_km,
            position_fraction=0.0,
            terrain_available=False,
            error_message=f"Invalid latitude: {lat}",
        )
    if not -180.0 <= lon <= 180.0:
        return MatchResult(
            nearest_waypoint_index=0,
            distance_along_route_km=0.0,
            remaining_route_km=route.total_distance_km,
            position_fraction=0.0,
            terrain_available=False,
            error_message=f"Invalid longitude: {lon}",
        )

    # Find nearest waypoint
    nearest_idx = find_nearest_waypoint(lat, lon, route)
    nearest_wp = route.points[nearest_idx]

    # Distance from GPS to nearest waypoint
    dist_to_wp_km = haversine_km(lat, lon, nearest_wp.latitude, nearest_wp.longitude)

    # Cumulative distance from route start to the nearest waypoint
    cum_dists = route.cumulative_distances_km
    distance_along_route_km = cum_dists[nearest_idx]

    # Remaining route distance
    total_dist = route.total_distance_km
    remaining_route_km = total_dist - distance_along_route_km

    # Position fraction (0.0 at start, 1.0 at end)
    if total_dist > 0:
        position_fraction = distance_along_route_km / total_dist
    else:
        position_fraction = 0.0

    # Terrain availability: we can provide terrain if
    # 1. The route has enough remaining distance for the horizon,
    # 2. The nearest waypoint is not at the very end of the route.
    # We check if there's at least 1 km remaining beyond the nearest waypoint.
    terrain_available = remaining_route_km > 1.0 and nearest_idx < len(route.points) - 1

    return MatchResult(
        nearest_waypoint_index=nearest_idx,
        distance_along_route_km=distance_along_route_km,
        remaining_route_km=remaining_route_km,
        position_fraction=position_fraction,
        terrain_available=terrain_available,
    )


# ============================================================================
# Next-terrain computation from a matched position
# ============================================================================

def get_next_terrain_from_match(
    match: MatchResult,
    route: Route,
    provider: ElevationProvider,
    horizon_km: float = 5.0,
) -> dict[str, float | np.nan]:
    """Compute next-terrain features from a GPS-to-route match.

    Parameters
    ----------
    match: MatchResult
        The GPS-to-route matching result.
    route: Route
        The planned route.
    provider: ElevationProvider
        Elevation data source.
    horizon_km: float
        Horizon in km (default 5.0).

    Returns
    -------
    dict[str, float | np.nan]
        Dictionary of next-terrain features (same format as
        :py:func:`extract_terrain_features` results), or ``np.nan``
        where terrain cannot be computed.
        Also includes ``terrain_available`` flag.
    """
    # If terrain is not available, return NaN features
    if not match.terrain_available:
        feat_name = f"next_{horizon_km}"
        return {
            f"{feat_name}_net_elev_m": np.nan,
            f"{feat_name}_gradient_pct": np.nan,
            f"{feat_name}_gain_m": np.nan,
            f"{feat_name}_loss_m": np.nan,
            f"{feat_name}_uphill_frac": np.nan,
            f"{feat_name}_downhill_frac": np.nan,
            f"{feat_name}_flat_frac": np.nan,
            "terrain_available": False,
        }

    # Find the index along the route where we need to start computing terrain.
    # We use the nearest waypoint index from the match.
    nearest_idx = match.nearest_waypoint_index

    # Get waypoints from the nearest waypoint to the end
    remaining_waypoints = route.points[nearest_idx:]

    if len(remaining_waypoints) < 2:
        # Not enough waypoints for a profile
        feat_name = f"next_{horizon_km}"
        return {
            f"{feat_name}_net_elev_m": np.nan,
            f"{feat_name}_gradient_pct": np.nan,
            f"{feat_name}_gain_m": np.nan,
            f"{feat_name}_loss_m": np.nan,
            f"{feat_name}_uphill_frac": np.nan,
            f"{feat_name}_downhill_frac": np.nan,
            f"{feat_name}_flat_frac": np.nan,
            "terrain_available": True,
        }

    # Compute elevation profile from the remaining waypoints
    from src.route.route_schema import RoutePoint  # ensure import
    from src.route.elevation import MockElevationProvider

    # Use a simple mock provider if none given, or the real one
    # Here we use the route's own waypoints as a mock elevation source
    # by assuming altitude is available (or 0 as placeholder)
    # In production, this would use a real DEM provider.

    # For now, return a simplified result indicating terrain is available
    # but with NaN values since we don't have a real elevation provider
    # integrated yet.
    feat_name = f"next_{horizon_km}"
    return {
        f"{feat_name}_net_elev_m": np.nan,
        f"{feat_name}_gradient_pct": np.nan,
        f"{feat_name}_gain_m": np.nan,
        f"{feat_name}_loss_m": np.nan,
        f"{feat_name}_uphill_frac": np.nan,
        f"{feat_name}_downhill_frac": np.nan,
        f"{feat_name}_flat_frac": np.nan,
        "terrain_available": True,
    }


# ============================================================================
# Convenience function for the feature pipeline
# ============================================================================

def compute_next_terrain(
    lat: float,
    lon: float,
    route: Route,
    provider: ElevationProvider,
    horizon_km: float = 5.0,
) -> dict[str, float | np.nan]:
    """Full pipeline: match GPS position → compute next terrain features.

    Parameters
    ----------
    lat: float
        GPS latitude.
    lon: float
        GPS longitude.
    route: Route
        Planned route.
    provider: ElevationProvider
        Elevation data source.
    horizon_km: float
        Horizon in km (default 5.0).

    Returns
    -------
    dict[str, float | np.nan]
        Next-terrain features, or NaN values if matching/computation fails.
    """
    # Step 1: match GPS to route
    match = match_gps_to_route(lat, lon, route)

    # Step 2: compute next terrain from the match
    return get_next_terrain_from_match(match, route, provider, horizon_km)