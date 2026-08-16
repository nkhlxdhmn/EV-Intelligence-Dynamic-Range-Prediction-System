"""
STEP 13B - ROUTE INPUT SCHEMA.

Formal schema for planned route representation. Defines the minimum supported
route format for the route-aware EV energy consumption model.

The route is a sequence of GPS waypoints representing the planned road path.

Rules:
- Latitude: [-90, 90]
- Longitude: [-180, 180]
- Minimum 2 points
- No NaN coordinates
- Route ordering matters (sequential waypoints)
- Duplicate points are allowed but geometrically degenerate
- Impossible jumps (large distance gaps) are flagged but not rejected
  (deferred to the matching/matching logic)
"""

from __future__ import annotations

from typing import List, Literal

import numpy as np


# ============================================================================
# Core route representation
# ============================================================================

class RoutePoint:
    """A single GPS waypoint in the planned route.

    Attributes
    ----------
    latitude: float
        Decimal degrees, [-90, 90].
    longitude: float
        Decimal degrees, [-180, 180].
    timestamp: float | None
        Optional Unix timestamp (seconds since epoch). If provided, must be
        monotonically increasing.
    """

    __slots__ = ("latitude", "longitude", "timestamp")

    def __init__(self, latitude: float, longitude: float,
                 timestamp: float | None = None):
        # Check NaN FIRST - range check would reject NaN incorrectly
        if latitude != latitude:
            raise ValueError("latitude must not be NaN")
        if longitude != longitude:
            raise ValueError("longitude must not be NaN")
        # Validate latitude range
        if not -90.0 <= latitude <= 90.0:
            raise ValueError(f"latitude out of range: {latitude} (must be [-90, 90])")
        # Validate longitude range
        if not -180.0 <= longitude <= 180.0:
            raise ValueError(f"longitude out of range: {longitude} (must be [-180, 180])")
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.timestamp = float(timestamp) if timestamp is not None else None

    def __repr__(self) -> str:
        if self.timestamp is not None:
            return f"RoutePoint(lat={self.latitude:.6f}, lon={self.longitude:.6f}, t={self.timestamp:.0f})"
        return f"RoutePoint(lat={self.latitude:.6f}, lon={self.longitude:.6f})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, RoutePoint):
            return NotImplemented
        return (self.latitude == other.latitude and
                self.longitude == other.longitude and
                self.timestamp == other.timestamp)

    def __hash__(self) -> int:
        return hash((self.latitude, self.longitude, self.timestamp))


# ============================================================================
# Route sequence
# ============================================================================

class Route:
    """A sequence of RoutePoint waypoints representing a planned road path.

    Parameters
    ----------
    points: list[RoutePoint]
        Waypoints in order along the route. Minimum 2 points.
    """

    __slots__ = ("points",)

    def __init__(self, points: list[RoutePoint]):
        if not isinstance(points, list):
            raise TypeError("route points must be a list")
        if len(points) < 2:
            raise ValueError("route must have at least 2 waypoints")
        # Validate all points
        for p in points:
            if not isinstance(p, RoutePoint):
                raise TypeError(f"each point must be a RoutePoint, got {type(p)}")
        self.points = points

    def __len__(self) -> int:
        return len(self.points)

    def __getitem__(self, i) -> RoutePoint:
        return self.points[i]

    def __repr__(self) -> str:
        return f"Route({len(self.points)} waypoints)"

    @property
    def bounding_box(self) -> dict:
        """Return [min_lat, max_lat, min_lon, max_lon]."""
        lats = [p.latitude for p in self.points]
        lons = [p.longitude for p in self.points]
        return {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lon": min(lons),
            "max_lon": max(lons),
        }

    @property
    def total_distance_km(self) -> float:
        """Compute cumulative haversine distance along the route."""
        return _route_total_distance_km(self.points)

    @property
    def cumulative_distances_km(self) -> list[float]:
        """Return cumulative distance from start for each waypoint.

        First element is 0.0 (start point). Last element is total distance.
        """
        return _cumulative_distances_km(self.points)


# ============================================================================
# Route schema validation
# ============================================================================

def validate_route(route: Route) -> list[str]:
    """Validate a route and return a list of warning messages.

    Validates:
    - Latitude/longitude ranges
    - No NaN coordinates
    - Minimum 2 points
    - Monotonically increasing timestamps (if provided)
    - Duplicate points

    Returns
    -------
    list[str]
        Empty list if valid; otherwise list of warning messages.
    """
    warnings: list[str] = []

    if len(route.points) < 2:
        warnings.append("route must have at least 2 waypoints")

    # Check for NaN or infinite coordinates
    for i, p in enumerate(route.points):
        if p.latitude != p.latitude or p.longitude != p.longitude:  # NaN check
            warnings.append(f"waypoint {i}: NaN coordinate")

    # Check timestamp ordering if timestamps provided
    timestamps = [p.timestamp for p in route.points if p.timestamp is not None]
    if len(timestamps) > 1:
        for i in range(1, len(timestamps)):
            if timestamps[i] is not None and timestamps[i-1] is not None:
                if timestamps[i] < timestamps[i-1]:
                    warnings.append(
                        f"waypoint {i}: timestamp earlier than waypoint {i-1}")

    # Check for duplicate points
    seen = set()
    for i, p in enumerate(route.points):
        key = (p.latitude, p.longitude)
        if key in seen:
            warnings.append(f"waypoint {i}: duplicate coordinate ({p.latitude:.6f}, {p.longitude:.6f})")
        seen.add(key)

    return warnings


# ============================================================================
# Route serialization / deserialization
# ============================================================================

def route_to_dict(route: Route) -> dict:
    """Convert a Route to a dict for JSON serialization."""
    return {
        "points": [
            {
                "latitude": p.latitude,
                "longitude": p.longitude,
                "timestamp": p.timestamp,
            }
            for p in route.points
        ]
    }


def route_from_dict(data: dict) -> Route:
    """Create a Route from a dict (e.g. from JSON deserialization)."""
    points = [
        RoutePoint(
            latitude=p["latitude"],
            longitude=p["longitude"],
            timestamp=p.get("timestamp"),
        )
        for p in data.get("points", [])
    ]
    return Route(points)


# ============================================================================
# Haversine distance helpers
# ============================================================================

_R_EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two points in km."""
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)
    a = np.sin(delta_phi / 2.0) ** 2 + \
        np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return float(_R_EARTH_RADIUS_KM * c)


def _route_total_distance_km(points: list[RoutePoint]) -> float:
    """Cumulative haversine distance along a route path."""
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(points)):
        total += _haversine_km(
            points[i - 1].latitude, points[i - 1].longitude,
            points[i].latitude, points[i].longitude,
        )
    return total


def _cumulative_distances_km(points: list[RoutePoint]) -> list[float]:
    """Cumulative distance from start for each waypoint."""
    if len(points) < 2:
        return [0.0]
    dists = [0.0]
    for i in range(1, len(points)):
        d = _haversine_km(
            points[i - 1].latitude, points[i - 1].longitude,
            points[i].latitude, points[i].longitude,
        )
        dists.append(dists[-1] + d)
    return dists


# ============================================================================
# Route matching: find nearest waypoint to a GPS position
# ============================================================================

def find_nearest_waypoint(lat: float, lon: float, route: Route) -> int:
    """Find the index of the waypoint nearest to the given GPS position.

    Uses haversine distance. Returns the index (0-based) of the nearest
    waypoint. For routes with 2+ points, this is typically the closest
    segment endpoint.

    Parameters
    ----------
    lat: float
        GPS latitude.
    lon: float
        GPS longitude.
    route: Route
        The planned route.

    Returns
    -------
    int
        Index of the nearest waypoint.
    """
    if not route.points:
        return 0
    best_idx = 0
    best_dist = float('inf')
    for i, p in enumerate(route.points):
        d = _haversine_km(lat, lon, p.latitude, p.longitude)
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


# ============================================================================
# Route segment: distance along route from a given point
# ============================================================================

def distance_along_route(lat: float, lon: float, route: Route) -> float:
    """Return distance along the route from the start to the nearest waypoint.

    Parameters
    ----------
    lat: float
        GPS latitude of current position.
    lon: float
        GPS longitude of current position.
    route: Route
        The planned route.

    Returns
    -------
    float
        Distance in km from route start to the nearest waypoint.
    """
    idx = find_nearest_waypoint(lat, lon, route)
    return route.cumulative_distances_km[idx]