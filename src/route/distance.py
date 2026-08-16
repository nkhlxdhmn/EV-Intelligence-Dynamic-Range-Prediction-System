"""
STEP 13C - Memory-efficient route distance calculator.

Calculates:
- cumulative route distance
- segment distance
- route total distance
- distance between route points

Uses geodesic/haversine calculations. No external APIs.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


# ============================================================================
# Earth model constants
# ============================================================================

_R_EARTH_RADIUS_KM = 6371.0


# ============================================================================
# Haversine distance between two points
# ============================================================================

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two points in km.

    Uses the haversine formula with Earth radius 6371.0 km.
    """
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)
    a = (np.sin(delta_phi / 2.0) ** 2
         + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2)
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return float(_R_EARTH_RADIUS_KM * c)


# ============================================================================
# Route distance calculations (using RoutePoint / Route from route_schema)
# ============================================================================

def segment_distance_km(p1: "RoutePoint", p2: "RoutePoint") -> float:
    """Distance between two consecutive route points (haversine)."""
    return haversine_km(p1.latitude, p1.longitude, p2.latitude, p2.longitude)


def cumulative_distance_km(points: Sequence["RoutePoint"]) -> float:
    """Total cumulative distance along a route segment sequence.

    Sums haversine distances between consecutive points.
    Returns 0.0 for fewer than 2 points.
    """
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(points)):
        total += segment_distance_km(points[i - 1], points[i])
    return total


def cumulative_distances_km(points: Sequence["RoutePoint"]) -> list[float]:
    """Cumulative distance from the start for each waypoint.

    Returns a list where element i is the distance from point 0 to point i.
    First element is always 0.0.
    """
    if len(points) < 1:
        return []
    dists = [0.0]
    for i in range(1, len(points)):
        dists.append(dists[-1] + segment_distance_km(points[i - 1], points[i]))
    return dists


def total_route_distance_km(points: Sequence["RoutePoint"]) -> float:
    """Alias for cumulative_distance_km - total distance of the route."""
    return cumulative_distance_km(points)


# ============================================================================
# Convenience functions using raw lat/lon floats
# ============================================================================

def distance_between_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Convenience: haversine distance between two lat/lon pairs."""
    return haversine_km(lat1, lon1, lat2, lon2)


def cumulative_distances_from_start_km(
    lats: list[float],
    lons: list[float],
) -> list[float]:
    """Cumulative distances from the first point given separate lat/lon lists.

    Useful when points are generated independently before wrapping in RoutePoint.
    """
    if len(lats) != len(lons):
        raise ValueError("lats and lons must have the same length")
    if len(lats) < 1:
        return []
    dists = [0.0]
    for i in range(1, len(lats)):
        dists.append(dists[-1] + haversine_km(lats[i - 1], lons[i - 1], lats[i], lons[i]))
    return dists


# ============================================================================
# Validation / safety
# ============================================================================

def validate_latitude(lat: float) -> None:
    """Ensure latitude is in valid range [-90, 90], raise ValueError otherwise."""
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"Latitude {lat} out of range [-90, 90]")


def validate_longitude(lon: float) -> None:
    """Ensure longitude is in valid range [-180, 180], raise ValueError otherwise."""
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"Longitude {lon} out of range [-180, 180]")


# ============================================================================
# Module compatibility / introspection
# ============================================================================

__all__ = [
    "haversine_km",
    "segment_distance_km",
    "cumulative_distance_km",
    "cumulative_distances_km",
    "total_route_distance_km",
    "distance_between_km",
    "cumulative_distances_from_start_km",
    "validate_latitude",
    "validate_longitude",
]