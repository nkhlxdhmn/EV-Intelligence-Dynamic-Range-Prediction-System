"""
STEP 13F - Route-based terrain features.

Implement route-based versions of the existing model features:
    next_1km_*, next_2km_*, next_5km_*.

For each prediction point, calculate only from the PLANNED ROUTE ahead
of the current route position.

Features include the existing definitions where applicable:
    - uphill fraction
    - downhill fraction
    - gradient
    - net elevation change
    - elevation gain
    - elevation loss

IMPORTANT:
    These calculations must operate on route/DEM data.
    They must NOT access future vehicle telemetry.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from src.route.route_schema import RoutePoint
from src.route.profile import ElevationProfile, compute_profile


# ============================================================================
# Terrain feature extraction from an elevation profile
# ============================================================================

def _extract_next_features_from_profile(
    profile: ElevationProfile,
    horizon_km: float,
) -> dict[str, float | np.nan]:
    """Extract next-horizon terrain features from an :py:class:`ElevationProfile`.

    Parameters
    ----------
    profile: ElevationProfile
        The elevation profile computed from :py:func:`compute_profile`.
    horizon_km: float
        One of ``1.0``, ``2.0``, or ``5.0``.  Selects the profile subset
        covering the next *horizon_km* km.

    Returns
    -------
    dict[str, float | np.nan]
        Dictionary with keys:
            - ``next_{horizon_km}_net_elev_m``
            - ``next_{horizon_km}_gradient_pct``
            - ``next_{horizon_km}_gain_m``
            - ``next_{horizon_km}_loss_m``
            - ``next_{horizon_km}_uphill_frac``
            - ``next_{horizon_km}_downhill_frac``
            - ``next_{horizon_km}_flat_frac``
        Returns ``np.nan`` for any feature that cannot be computed (e.g.
        missing elevation data or zero distance).
    """
    dists = profile.distances_km
    grads = profile.gradients_pct
    elevs = profile.elevations_m

    # Find the index where the profile horizon exceeds *horizon_km*.
    # The profile distances are cumulative from the start; we want the
    # last segment whose cumulative distance is <= horizon_km.
    if not dists or all(np.isnan(d) for d in dists):
        # No distance data available → return all NaN
        feat_name = f"next_{horizon_km}"
        return {
            f"{feat_name}_net_elev_m": np.nan,
            f"{feat_name}_gradient_pct": np.nan,
            f"{feat_name}_gain_m": np.nan,
            f"{feat_name}_loss_m": np.nan,
            f"{feat_name}_uphill_frac": np.nan,
            f"{feat_name}_downhill_frac": np.nan,
            f"{feat_name}_flat_frac": np.nan,
        }

    # Determine the effective segment count within the horizon.
    # We use the cumulative distances; the last valid index i satisfies
    # dists[i] <= horizon_km.  We include segment i (i.e. waypoint i+1).
    valid_indices = [i for i, d in enumerate(dists) if not np.isnan(d) and d <= horizon_km]
    if not valid_indices:
        feat_name = f"next_{horizon_km}"
        return {
            f"{feat_name}_net_elev_m": np.nan,
            f"{feat_name}_gradient_pct": np.nan,
            f"{feat_name}_gain_m": np.nan,
            f"{feat_name}_loss_m": np.nan,
            f"{feat_name}_uphill_frac": np.nan,
            f"{feat_name}_downhill_frac": np.nan,
            f"{feat_name}_flat_frac": np.nan,
        }

    last_idx = valid_indices[-1] + 1  # include the waypoint at last_idx

    # Slice the profile data up to and including the last valid waypoint.
    # Distances and gradients are already aligned with segments (n_segments = n_waypoints - 1).
    # We need the elevation at waypoint indices 1..last_idx.
    seg_distances = dists[:last_idx]  # length = last_idx (number of segments)
    segment_gradients = grads[:last_idx] if last_idx <= len(grads) else grads
    segment_elevations = elevs[1 : last_idx + 1]  # elevation at waypoints 1..last_idx

    # Net elevation change = elevation at end - elevation at start
    net_elev = float(segment_elevations[-1] - segment_elevations[0]) if segment_elevations else np.nan

    # Gradient: use the average of the segment gradients within the horizon,
    # or compute from net elevation / total distance.
    valid_grads = [g for g in segment_gradients[:len(seg_distances)] if not np.isnan(g)]
    if valid_grads:
        avg_grad = float(np.mean(valid_grads))
    elif np.sum(~np.isnan(seg_distances)) > 0 and not np.isnan(net_elev):
        # Compute gradient from net elevation / total distance
        total_d = float(np.nansum(seg_distances))
        avg_grad = (net_elev / total_d) * 100.0 if total_d > 0 else np.nan
    else:
        avg_grad = np.nan

    # Gain = sum of positive elevation differences between consecutive waypoints
    gains = []
    for i in range(1, len(segment_elevations)):
        diff = segment_elevations[i] - segment_elevations[i - 1]
        gains.append(diff if diff > 0 else 0.0)
    total_gain = float(np.sum(gains)) if gains else 0.0

    # Loss = sum of negative elevation differences (absolute value)
    losses = []
    for i in range(1, len(segment_elevations)):
        diff = segment_elevations[i - 1] - segment_elevations[i]
        losses.append(diff if diff > 0 else 0.0)
    total_loss = float(np.sum(losses)) if losses else 0.0

    # Uphill fraction = proportion of gradient-positive segments
    uphill_frac = float(len(valid_grads) / len(seg_distances)) if seg_distances else np.nan

    # Downhill fraction = proportion of gradient-negative segments
    downhill_segments = [g for g in segment_gradients[:len(seg_distances)] if g < 0]
    downhill_frac = float(len(downhill_segments) / len(seg_distances)) if seg_distances else np.nan

    # Flat fraction = 1 - uphill - downhill
    flat_frac = 1.0 - uphill_frac - downhill_frac if not (np.isnan(uphill_frac) and np.isnan(downhill_frac)) else np.nan

    feat_name = f"next_{horizon_km}"
    return {
        f"{feat_name}_net_elev_m": net_elev,
        f"{feat_name}_gradient_pct": avg_grad,
        f"{feat_name}_gain_m": total_gain,
        f"{feat_name}_loss_m": total_loss,
        f"{feat_name}_uphill_frac": uphill_frac,
        f"{feat_name}_downhill_frac": downhill_frac,
        f"{feat_name}_flat_frac": flat_frac,
    }


# ============================================================================
# High-level feature extraction from waypoints + provider
# ============================================================================

def extract_terrain_features(
    waypoints: list[RoutePoint],
    provider: object,
    horizons: list[float] | None = None,
) -> dict[str, float | np.nan]:
    """Extract route-based terrain features for the given waypoints and provider.

    This is the main entry point for the route-aware feature pipeline.  It:

    1. Computes an :py:class:`ElevationProfile` from the waypoints and provider.
    2. Extracts next-1km, next-2km, and next-5km features from that profile.

    Parameters
    ----------
    waypoints: list[RoutePoint]
        Route waypoints in order.  Must have at least 2 points.
    provider: object
        An object implementing ``get_elevations(lats, lons)`` → np.ndarray.
        Typically a :py:class:`~src.route.elevation.ElevationProvider` subclass.
    horizons: list[float] | None
        Which horizons to compute features for.  Defaults to ``[1.0, 2.0, 5.0]``.

    Returns
    -------
    dict[str, float | np.nan]
        Dictionary of terrain feature names to values.  Feature names follow
        the pattern ``next_{horizon}_*`` (e.g. ``next_1km_gradient_pct``).
        Values are ``np.nan`` where the feature cannot be computed from the
        available data.

    Raises
    ------
    ValueError
        If fewer than 2 waypoints are given.
    """
    if horizons is None:
        horizons = [1.0, 2.0, 5.0]

    if len(waypoints) < 2:
        raise ValueError("extract_terrain_features requires at least 2 waypoints")

    # Step 1: compute the elevation profile
    profile = compute_profile(waypoints, provider)

    # Step 2: extract features for each horizon
    result: dict[str, float | np.nan] = {}
    for h in horizons:
        feat = _extract_next_features_from_profile(profile, h)
        result.update(feat)

    return result


# ============================================================================
# Convenience: map the 15 model feature names to feature extraction
# ============================================================================

# The 15 next_* features the frozen model expects:
#   next_1km_net_elev_m, next_1km_gradient_pct, next_1km_gain_m, next_1km_loss_m
#   next_2km_net_elev_m, next_2km_gradient_pct, next_2km_gain_m, next_2km_loss_m
#   next_5km_net_elev_m, next_5km_gradient_pct, next_5km_gain_m, next_5km_loss_m
#   next_5km_uphill_frac, next_5km_downhill_frac, next_5km_flat_frac

_TERRAIN_FEATURE_MAP: dict[str, str] = {
    "next_1km_net_elev_m": "next_1km_net_elev_m",
    "next_1km_gradient_pct": "next_1km_gradient_pct",
    "next_1km_gain_m": "next_1km_gain_m",
    "next_1km_loss_m": "next_1km_loss_m",
    "next_2km_net_elev_m": "next_2km_net_elev_m",
    "next_2km_gradient_pct": "next_2km_gradient_pct",
    "next_2km_gain_m": "next_2km_gain_m",
    "next_2km_loss_m": "next_2km_loss_m",
    "next_5km_net_elev_m": "next_5km_net_elev_m",
    "next_5km_gradient_pct": "next_5km_gradient_pct",
    "next_5km_gain_m": "next_5km_gain_m",
    "next_5km_loss_m": "next_5km_loss_m",
    "next_5km_uphill_frac": "next_5km_uphill_frac",
    "next_5km_downhill_frac": "next_5km_downhill_frac",
    "next_5km_flat_frac": "next_5km_flat_frac",
}


def map_model_feature_to_terrain(
    feature_name: str,
    terrain_values: dict[str, float | np.nan],
) -> float | np.nan:
    """Return the terrain value for a given model feature name.

    Parameters
    ----------
    feature_name: str
        Name of a model feature (e.g. ``next_1km_gradient_pct``).
    terrain_values: dict[str, float | np.nan]
        Dictionary returned by :py:func:`extract_terrain_features`.

    Returns
    -------
    float | np.nan
        The terrain value, or ``np.nan`` if the feature is not available.
    """
    terrain_key = _TERRAIN_FEATURE_MAP.get(feature_name)
    if terrain_key is None:
        return np.nan
    return terrain_values.get(terrain_key, np.nan)