"""STEP 13B - Route input schema unit tests.

Tests for :py:mod:`src.route.route_schema` covering route representation,
validation, serialization, and distance calculations.
"""

import math

import numpy as np
import pytest

from src.route.route_schema import (
    RoutePoint,
    Route,
    validate_route,
    route_to_dict,
    route_from_dict,
    find_nearest_waypoint,
    distance_along_route,
    _haversine_km,
)


# --------------------------------------------------------------------------
# RoutePoint
# --------------------------------------------------------------------------

def test_route_point_creation():
    """RoutePoint accepts valid lat/lon and stores them."""
    p = RoutePoint(latitude=40.0, longitude=-120.0)
    assert p.latitude == 40.0
    assert p.longitude == -120.0
    assert p.timestamp is None


def test_route_point_with_timestamp():
    """RoutePoint accepts an optional timestamp."""
    p = RoutePoint(latitude=40.0, longitude=-120.0, timestamp=1000.0)
    assert p.timestamp == 1000.0


def test_route_point_latitude_range():
    """RoutePoint rejects latitude outside [-90, 90]."""
    with pytest.raises(ValueError, match="latitude out of range"):
        RoutePoint(latitude=91.0, longitude=0.0)
    with pytest.raises(ValueError, match="latitude out of range"):
        RoutePoint(latitude=-91.0, longitude=0.0)


def test_route_point_longitude_range():
    """RoutePoint rejects longitude outside [-180, 180]."""
    with pytest.raises(ValueError, match="longitude out of range"):
        RoutePoint(latitude=0.0, longitude=181.0)
    with pytest.raises(ValueError, match="longitude out of range"):
        RoutePoint(latitude=0.0, longitude=-181.0)


def test_route_point_nan_rejected():
    """RoutePoint rejects NaN coordinates."""
    with pytest.raises(ValueError, match="must not be NaN"):
        RoutePoint(latitude=float("nan"), longitude=0.0)
    with pytest.raises(ValueError, match="must not be NaN"):
        RoutePoint(latitude=0.0, longitude=float("nan"))


# --------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------

def test_route_minimum_points():
    """Route requires at least 2 waypoints."""
    with pytest.raises(ValueError, match="route must have at least 2 waypoints"):
        Route(points=[])


def test_route_single_point():
    """Route rejects single waypoint."""
    with pytest.raises(ValueError, match="route must have at least 2 waypoints"):
        Route(points=[RoutePoint(0.0, 0.0)])


def test_route_valid():
    """Route accepts valid waypoints."""
    r = Route(points=[
        RoutePoint(40.0, -120.0),
        RoutePoint(41.0, -121.0),
    ])
    assert len(r) == 2


def test_route_repr():
    """Route repr includes waypoint count."""
    r = Route(points=[RoutePoint(0.0, 0.0), RoutePoint(1.0, 1.0)])
    repr_str = repr(r)
    assert "2 waypoints" in repr_str


def test_route_bounding_box():
    """Route bounding box returns correct extremes."""
    r = Route(points=[
        RoutePoint(10.0, 20.0),
        RoutePoint(30.0, 40.0),
        RoutePoint(5.0, 10.0),
    ])
    bb = r.bounding_box
    assert bb["min_lat"] == 5.0
    assert bb["max_lat"] == 30.0
    assert bb["min_lon"] == 10.0
    assert bb["max_lon"] == 40.0


def test_route_total_distance_km():
    """Route total distance via haversine."""
    # 1 degree of longitude at equator ≈ 111 km
    r = Route(points=[
        RoutePoint(0.0, 0.0),
        RoutePoint(0.0, 1.0),  # 1 degree of longitude at equator
    ])
    total = r.total_distance_km
    assert abs(total - 111.3195) < 1.0, f"Expected ~111 km, got {total}"


def test_route_cumulative_distances_km():
    """Route cumulative distances: first is 0, last is total."""
    r = Route(points=[
        RoutePoint(0.0, 0.0),
        RoutePoint(0.0, 1.0),
        RoutePoint(0.0, 2.0),
    ])
    cums = r.cumulative_distances_km
    assert cums[0] == 0.0
    assert abs(cums[1] - 111.3195) < 1.0
    assert abs(cums[2] - 222.639) < 2.0


# --------------------------------------------------------------------------
# Route validation
# --------------------------------------------------------------------------

def test_validate_route_valid():
    """Valid route returns no warnings."""
    warnings = validate_route(Route(points=[
        RoutePoint(40.0, -120.0),
        RoutePoint(41.0, -121.0),
    ]))
    assert warnings == []


def test_validate_route_too_few_points():
    """Too few points raises ValueError."""
    with pytest.raises(ValueError, match="route must have at least 2 waypoints"):
        Route(points=[RoutePoint(0.0, 0.0)])


def test_validate_route_nan_coordinates():
    """NaN coordinates raise ValueError from RoutePoint."""
    with pytest.raises(ValueError, match="latitude must not be NaN"):
        RoutePoint(float("nan"), 0.0)


# --------------------------------------------------------------------------
# Route serialization
# --------------------------------------------------------------------------

def test_route_to_from_dict():
    """Round-trip: route -> dict -> route preserves waypoints."""
    original = Route(points=[
        RoutePoint(40.0, -120.0, timestamp=1000.0),
        RoutePoint(41.0, -121.0),
    ])
    d = route_to_dict(original)
    restored = route_from_dict(d)
    assert len(restored) == len(original)
    assert restored.points[0] == original.points[0]
    assert restored.points[1] == original.points[1]


# --------------------------------------------------------------------------
# Haversine distance
# --------------------------------------------------------------------------

def test_haversine_equator():
    """1 degree of longitude at equator ≈ 111 km."""
    d = _haversine_km(0.0, 0.0, 0.0, 1.0)
    assert abs(d - 111.3195) < 1.0


def test_haversine_generic():
    """Generic haversine distance is positive for distinct points."""
    d = _haversine_km(40.0, -120.0, 41.0, -121.0)
    assert d > 0


# --------------------------------------------------------------------------
# Nearest waypoint
# --------------------------------------------------------------------------

def test_find_nearest_waypoint():
    """Nearest waypoint to a known position."""
    r = Route(points=[
        RoutePoint(40.0, -120.0),
        RoutePoint(45.0, -120.0),
        RoutePoint(42.0, -120.0),
    ])
    idx = find_nearest_waypoint(42.5, -120.0, r)
    # 42.5 is halfway between 42 and 45, closer to 42 (dist 0.5 deg) than 45 (dist 2.5 deg)
    assert idx == 2  # index of waypoint at 42.0


def test_find_nearest_waypoint_first():
    """Nearest waypoint when position is closest to first."""
    r = Route(points=[
        RoutePoint(40.0, -120.0),
        RoutePoint(50.0, -120.0),
    ])
    idx = find_nearest_waypoint(41.0, -120.0, r)
    assert idx == 0  # closer to first waypoint


# --------------------------------------------------------------------------
# Distance along route
# --------------------------------------------------------------------------

def test_distance_along_route():
    """Distance along route from start to nearest waypoint."""
    r = Route(points=[
        RoutePoint(40.0, -120.0),
        RoutePoint(41.0, -120.0),
        RoutePoint(42.0, -120.0),
    ])
    d = distance_along_route(42.0, -120.0, r)
    # Should be cumulative distance to waypoint at index 2
    cums = r.cumulative_distances_km
    assert abs(d - cums[2]) < 0.01


def test_distance_along_route_offroute():
    """Distance along route for off-route position uses nearest waypoint."""
    r = Route(points=[
        RoutePoint(40.0, -120.0),
        RoutePoint(45.0, -120.0),
    ])
    d = distance_along_route(44.0, -120.0, r)
    # Should be distance to waypoint at index 1 (closer to 45 than 40)
    cums = r.cumulative_distances_km
    assert abs(d - cums[1]) < 0.01


# Run all tests if invoked directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])