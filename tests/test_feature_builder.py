"""
STEP 11K - Feature Builder tests.

Tests the 102-feature production builder: ordering, validation, route terrain
requirement, and missing-feature detection. Never touches DEVRT test data.
"""

import json

import numpy as np
import pandas as pd
import pytest

from src.inference.feature_builder import (
    FeatureBuilder,
    FeatureBuildError,
    RouteTerrain,
    SyntheticRouteTerrainProvider,
    build_demo_snapshot,
)

FEATURES = json.load(open("models/final_feature_list.json"))


@pytest.fixture(scope="module")
def builder():
    return FeatureBuilder()


@pytest.fixture(scope="module")
def snapshot():
    return build_demo_snapshot()


@pytest.fixture(scope="module")
def terrain():
    snap = build_demo_snapshot()
    return SyntheticRouteTerrainProvider().get_upcoming_terrain(
        snap["distance_since_trip_start_km"], snap["altitude_m"])


def test_builds_exact_feature_set(builder, snapshot, terrain):
    """Output columns must EXACTLY match final_feature_list (order + set)."""
    row = builder.build_features(snapshot, terrain)
    assert list(row.columns) == FEATURES
    assert row.shape[1] == 102
    assert row.shape[0] == 1


def test_missing_route_terrain_raises(builder, snapshot):
    """Route terrain is required; never fabricated."""
    with pytest.raises(FeatureBuildError):
        builder.build_features(snapshot, None)


def test_missing_required_telemetry_raises(builder, terrain):
    snap = build_demo_snapshot()
    del snap["soc_pct"]
    with pytest.raises(FeatureBuildError):
        builder.build_features(snap, terrain)


def test_invalid_soc_raises(builder, terrain):
    snap = build_demo_snapshot()
    snap["soc_pct"] = 150.0
    # range check in validate_feature_vector rejects soc > 100
    with pytest.raises(FeatureBuildError):
        builder.build_features(snap, terrain)


def test_route_features_present_and_finite(builder, snapshot, terrain):
    row = builder.build_features(snapshot, terrain)
    for name in FEATURES:
        if name.startswith("next_"):
            assert not np.isnan(float(row.iloc[0][name])), name


def test_validate_wrong_ordering(builder, snapshot, terrain):
    row = builder.build_features(snapshot, terrain)
    shuffled = row[list(reversed(FEATURES))]
    with pytest.raises(FeatureBuildError):
        builder.validate_feature_vector(shuffled)


def test_validate_unexpected_column(builder, snapshot, terrain):
    row = builder.build_features(snapshot, terrain)
    bad = row.copy()
    bad["not_a_real_feature"] = 1.0
    with pytest.raises(FeatureBuildError):
        builder.validate_feature_vector(bad)


def test_validate_missing_column(builder, snapshot, terrain):
    row = builder.build_features(snapshot, terrain)
    bad = row.drop(columns=[FEATURES[0]])
    with pytest.raises(FeatureBuildError):
        builder.validate_feature_vector(bad)


def test_validate_nan_critical_feature(builder, snapshot, terrain):
    row = builder.build_features(snapshot, terrain)
    bad = row.copy()
    bad["next_5km_gradient_pct"] = np.nan
    with pytest.raises(FeatureBuildError):
        builder.validate_feature_vector(bad)


def test_validate_range_check(builder, snapshot, terrain):
    row = builder.build_features(snapshot, terrain)
    bad = row.copy()
    bad["current_speed_kmh"] = 99999.0
    with pytest.raises(FeatureBuildError):
        builder.validate_feature_vector(bad)


def test_optional_telemetry_nan_allowed(builder, snapshot, terrain):
    """Motor/aux/regen missing -> NaN, allowed (imputer handles)."""
    snap = build_demo_snapshot()
    snap["motor_power_kw"] = None
    snap["aux_power_kw"] = None
    row = builder.build_features(snap, terrain)
    assert np.isnan(float(row.iloc[0]["motor_power_kw"]))
    # no error -> NaN in optional feature is accepted


def test_route_terrain_validation():
    """RouteTerrain rejects empty/non-finite/sorted-required input."""
    with pytest.raises(ValueError):
        RouteTerrain([], [], source="x")
    with pytest.raises(ValueError):
        RouteTerrain([0, 1], [np.nan, 2], source="x")
    t = RouteTerrain([1.0, 0.0, 0.5], [10.0, 0.0, 5.0], source="DEM")
    assert t.offsets_km[0] == 0.0  # sorted ascending
    assert t.elevation_at(0.75) == pytest.approx(7.5)


def test_past_window_features_computed(builder, snapshot, terrain):
    """With a past_window, mean_speed_1km etc. become finite."""
    snap = build_demo_snapshot()
    n = 30
    dists = np.linspace(10.0, 12.0, n)  # last ~2 km
    alts = np.linspace(120.0, 150.0, n)
    speeds = np.full(n, 60.0)
    past = pd.DataFrame({
        "timestamp": pd.date_range("2026-08-16T10:00:00Z", periods=n, freq="30s"),
        "distance_km": dists,
        "altitude_m": alts,
        "speed_kmh": speeds,
        "ambient_temperature_c": np.full(n, 18.0),
        "motor_power_kw": np.full(n, 10.0),
        "aux_power_kw": np.full(n, 0.5),
        "regen_power_kw": np.full(n, 0.0),
    })
    row = builder.build_features(snap, terrain, past=past)
    assert np.isfinite(float(row.iloc[0]["mean_speed_1km"]))
    assert np.isfinite(float(row.iloc[0]["elevation_gain_1km"]))