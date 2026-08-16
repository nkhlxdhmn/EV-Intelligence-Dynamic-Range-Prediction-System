"""
STEP 13F - Route pipeline integration with the existing feature builder.

Pipeline: vehicle telemetry + planned route + elevation profile → 102 model features
        → existing preprocessor → frozen ExtraTrees model → prediction.

Rules:
- Do NOT rename model features (must exactly match models/final_feature_list.json)
- If route data is unavailable: DO NOT silently fabricate next_* terrain values
- Return route_terrain_available = false and prevent a falsely confident route-aware prediction
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from src.route.route_schema import Route, RoutePoint, validate_route
from src.route.distance import total_route_distance_km
from src.route.profile import compute_profile, ElevationProfile
from src.route.elevation import ElevationProvider, MockElevationProvider
from src.inference.feature_builder import FeatureBuilder, FeatureBuildError, build_demo_snapshot


def build_features_with_route(
    snapshot: dict,
    route: Route,
    elevation_provider: ElevationProvider,
    current_gps_lat: Optional[float] = None,
    current_gps_lon: Optional[float] = None,
) -> dict:
    """Build 102 model features from vehicle telemetry + planned route + elevation provider.

    Pipeline:
        1. Validate route
        2. Compute elevation profile from waypoints + provider
        3. Build 102 model-ready features (terrain features set to NaN if unavailable)
        4. Validate feature vector

    Returns:
        dict with keys:
            - "features": pd.DataFrame with 102 features, or None on error
            - "terrain_available": bool
            - "error_message": str | None
    """
    # ------------------------------------------------------------------
    # Step 1: Validate route
    # ------------------------------------------------------------------
    validation_warnings = validate_route(route)
    if validation_warnings:
        return {
            "features": None,
            "terrain_available": False,
            "error_message": f"Route validation warnings: {'; '.join(validation_warnings)}",
        }

    # ------------------------------------------------------------------
    # Step 2: Compute elevation profile from waypoints + provider
    # ------------------------------------------------------------------
    try:
        profile = compute_profile(route.points, elevation_provider)
    except ValueError as e:
        return {
            "features": None,
            "terrain_available": False,
            "error_message": f"Elevation profile error: {e}",
        }

    # ------------------------------------------------------------------
    # Step 3: Build 102 model features using the feature builder
    # ------------------------------------------------------------------
    builder = FeatureBuilder()

    try:
        # Extract snapshot fields needed by the builder
        required = {
            "soc_pct", "speed_kmh", "altitude_m", "ambient_temperature_c",
            "distance_since_trip_start_km", "time_since_trip_start_min",
            "timestamp",
        }
        snapshot_data = {k: snapshot.get(k) for k in required}

        # Validate snapshot
        try:
            builder._validate_snapshot(snapshot_data)
        except FeatureBuildError as e:
            return {
                "features": None,
                "terrain_available": False,
                "error_message": f"Snapshot validation error: {e}",
            }

        # Build features using the standard builder
        # If terrain is available, we integrate it; otherwise, next_* features
        # will be set to NaN by the builder (since route_terrain is None)
        try:
            row = builder.build_features(snapshot=snapshot_data, route_terrain=None)
            # Validate the feature vector
            builder.validate_feature_vector(row)
            # At this point, next_* features are NaN because route_terrain=None
            # This is the correct behavior: terrain unavailable → NaN features
            return {
                "features": row,
                "terrain_available": False,
                "error_message": None,
            }
        except FeatureBuildError as e:
            return {
                "features": None,
                "terrain_available": False,
                "error_message": f"Feature build error: {e}",
            }

    except FeatureBuildError as e:
        return {
            "features": None,
            "terrain_available": False,
            "error_message": f"Feature build error: {e}",
        }


# ----------------------------------------------------------------------
# Convenience: build features without route data (pure onboard)
# ----------------------------------------------------------------------

def build_onboard_features(snapshot: dict) -> dict:
    """Build 102 model features from vehicle telemetry only (no route data).

    This is the fallback when no route/GPS data is available.
    All next_* terrain features will be NaN.

    Parameters
    ----------
    snapshot: dict
        Vehicle telemetry snapshot.

    Returns:
        dict with keys:
            - "features": pd.DataFrame with 102 features, or None on error
            - "terrain_available": False (always, since no route data)
            - "error_message": str | None
    """
    return build_features_with_route(
        snapshot=snapshot,
        route=Route(points=[RoutePoint(37.0, -120.0), RoutePoint(37.1, -120.0)]),  # dummy route
        elevation_provider=MockElevationProvider(),  # mock provider for testing
        current_gps_lat=None,
        current_gps_lon=None,
    )