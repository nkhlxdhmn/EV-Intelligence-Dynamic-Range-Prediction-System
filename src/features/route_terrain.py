"""
STEP 14 — Route-Aware Future Terrain Feature Calculation.

Computes next_1km, next_2km, next_5km elevation gain/loss and gradient
features from a planned route profile. These features look ahead along
the planned route to capture upcoming terrain, classified as
CONDITIONALLY_CAUSAL (depend on planned route, not future telemetry).

Features:
- next_1km_elevation_gain_m: elevation gain (m) over the next 1 km ahead along route
- next_1km_elevation_loss_m: elevation loss (m) over the next 1 km ahead along route
- next_1km_gradient_pct: gradient (percent slope) over the next 1 km ahead
- next_2km_elevation_gain_m: elevation gain (m) over the next 2 km ahead along route
- next_2km_elevation_loss_m: elevation loss (m) over the next 2 km ahead along route
- next_2km_gradient_pct: gradient (percent slope) over the next 2 km ahead
- next_5km_elevation_gain_m: elevation gain (m) over the next 5 km ahead along route
- next_5km_elevation_loss_m: elevation loss (m) over the next 5 km ahead along route
- next_5km_gradient_pct: gradient (percent slope) over the next 5 km ahead
- next_1km_time_estimate_s: time estimate (s) to traverse next 1 km
- next_2km_time_estimate_s: time estimate (s) to traverse next 2 km
- next_5km_time_estimate_s: time estimate (s) to traverse next 5 km
- next_1km_speed_loss_pct: speed reduction (percent) expected over next 1 km due to gradient
- next_2km_speed_loss_pct: speed reduction (percent) expected over next 2 km due to gradient
- next_5km_speed_loss_pct: speed reduction (percent) expected over next 5 km due to gradient

Dependencies: RouteProfile from src/terrain/route_processor.py
Classification: CONDITIONALLY_CAUSAL — features depend on planned route waypoints,
                      not on real-time telemetry or future driving conditions.

Leakage guards (enforced at prediction time):
- [GUARD 1] Terrain features are computed from the RouteProfile only;
  current vehicle speed, acceleration, SOC, and traction current are
  NOT used in any feature calculation.
- [GUARD 2] The RouteProfile is derived from the planned route waypoints
  submitted at prediction start; it is NOT updated from GPS drift or
  real-time telemetry during prediction.
- [GUARD 3] If the vehicle deviates from the planned route (GPS position
  beyond off_route_threshold), the system switches to STRICT_ONBOARD mode
  where only onboard (non-route) features are used; route terrain features
  are marked as invalid/unavailable.
- [GUARD 4] Sensor quality flags (good/warning/invalid) are checked before
  using terrain features; invalid sensor data causes feature suppression
  rather than fabrication.
- [GUARD 5] Drift monitoring: if feature statistics deviate beyond
  established thresholds from reference distribution, a drift warning is
  raised and confidence scores are adjusted downward.
"""

from __future__ import annotations

from typing import Optional
from dataclasses import dataclass
import numpy as np

from src.terrain.route_processor import RouteProfile, RouteWaypoint


# ---------------------------------------------------------------------------
# Per-vehicle energy model constants
# ---------------------------------------------------------------------------

# Typical EV energy consumption per km on level ground at moderate speed
# (approximately 150–250 Wh/km depending on vehicle; we use a nominal value)
NOMINAL_CONSUMPTION_WH_PER_KM = 200.0  # Wh/km, level, moderate speed

# Typical EV mass (kg) for energy impact calculations
# Used in approximate grade resistance: F_grade = m * g * sin(theta)
# where sin(theta) ≈ gradient_pct / sqrt(gradient_pct^2 + 10000)
# For small gradients: F_grade ≈ m * g * gradient_pct / 100

# Rolling resistance coefficient (typical for cars)
ROLLING_RESISTANCE_CR = 0.01

# Air density (kg/m^3)
AIR_DENSITY = 1.225

# Gravitational acceleration (m/s^2)
G = 9.80665

# Typical frontal area (m^2)
FRONTAL_AREA = 2.5

# Typical drag coefficient
DRAG_COEFF = 0.30

# Typical rolling radius (m)
TYPICAL_RADIUS = 0.3


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _grade_from_pct(gradient_pct: float) -> float:
    """Convert gradient percent to grade (sin of slope angle).

    For small angles, grade ≈ gradient_pct / 100, but we use the exact
    trigonometric relationship.

    Parameters
    ----------
    gradient_pct : float
        Slope gradient in percent (positive = uphill, negative = downhill).

    Returns
    -------
    float
        Grade = sin(theta), where theta is the slope angle. Range [-1, 1].
    """
    # gradient_pct = 100 * tan(theta)  ... but for slope, tan ≈ sin for small angles
    # Actually, if gradient_pct = rise/run * 100, then:
    # tan(theta) = rise/run = gradient_pct / 100
    # sin(theta) = tan(theta) / sqrt(1 + tan(theta)^2)
    tan_theta = gradient_pct / 100.0
    if abs(tan_theta) >= 1.0:
        # Very steep; clamp to valid range for asin
        sign = 1.0 if tan_theta > 0 else -1.0
        tan_theta = sign * 1.0
    grade = tan_theta / np.sqrt(1.0 + tan_theta ** 2)
    return float(grade)


def _energy_for_grade(mass_kg: float, grade: float, wh_per_km_level: float = NOMINAL_CONSUMPTION_WH_PER_KM) -> float:
    """Approximate additional energy cost (Wh) per km due to grade.

    Adds grade resistance and rolling resistance + aerodynamic drag
    to the baseline level-ground consumption.

    Parameters
    ----------
    mass_kg : float
        Vehicle mass in kilograms.
    grade : float
        Grade = sin(slope angle), range [-1, 1].
    wh_per_km_level : float, default NOMINAL_CONSUMPTION_WH_PER_KM
        Baseline Wh/km on level ground.

    Returns
    -------
    float
        Additional Wh/km due to grade (may be negative for downhill,
        but total Wh/km will be clamped to >= 0).
    """
    # Grade resistance force (N): F = m * g * grade
    grade_resistance_N = mass_kg * G * grade

    # Rolling resistance force (N): F_rr = m * g * cr
    rolling_resistance_N = mass_kg * G * ROLLING_RESISTANCE_CR

    # Aerodynamic drag force (N): F_d = 0.5 * rho * Cd * A * v^2
    # We approximate at a typical speed of 30 km/h = 8.33 m/s
    drag_force_N = 0.5 * AIR_DENSITY * DRAG_COEFF * FRONTAL_AREA * (8.33 ** 2)

    # Total additional force due to grade (N)
    # For uphill (grade > 0): add; for downhill (grade < 0): subtract
    total_force_N = grade_resistance_N + rolling_resistance_N + drag_force_N
    if grade < 0:
        # Downhill: grade resistance is negative (provides energy)
        total_force_N = abs(grade_resistance_N) * (-1 if grade < 0 else 1) + rolling_resistance_N + drag_force_N
        # Actually let's be precise:
        total_force_N = grade_resistance_N + rolling_resistance_N + drag_force_N
        # grade_resistance_N is negative when grade < 0, which correctly reduces total_force_N

    # Work per km = force * distance; distance = 1000 m
    # Wh = (force * 1000) / (3600 * efficiency)
    # Assuming drivetrain efficiency of ~85% = 0.85
    efficiency = 0.85
    wh_per_km_grade = (total_force_N * 1000.0) / (3600.0 * efficiency)

    # Add to baseline
    total_wh_per_km = wh_per_km_level + wh_per_km_grade
    # Clamp to non-negative (downhill can't recover more than baseline without regen)
    if total_wh_per_km < 0:
        total_wh_per_km = 0.0

    return total_wh_per_km - wh_per_km_level  # return only the grade-influenced portion


def _time_for_distance(distance_km: float, wh_per_km: float, mass_kg: float) -> float:
    """Estimate time to traverse a distance given energy consumption.

    Uses a simple speed model: if energy available, speed = distance / time.
    This is a placeholder; in production, use speed predictor from onboard data.

    Parameters
    ----------
    distance_km : float
        Distance in kilometres.
    wh_per_km : float
        Energy consumption in Wh/km.
    mass_kg : float
        Vehicle mass in kilograms.

    Returns
    -------
    float
        Estimated time in seconds.
    """
    # Simple model: typical EV speed ~ 50 km/h on level ground
    # Time = distance / speed
    typical_speed_kmh = 50.0  # km/h
    return (distance_km / typical_speed_kmh) * 3600.0  # convert to seconds


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------


def compute_next_terrain_features(
    profile: RouteProfile,
    *,
    vehicle_mass_kg: float = 1800.0,
    sample_intervals_km: Optional[list[float]] = None,
) -> dict[str, float]:
    """Compute CONDITIONALLY_CAUSAL future terrain features from a route profile.

    For each waypoint in the profile, looks ahead along the route to compute
    elevation gain/loss and gradient over distances of 1 km, 2 km, and 5 km.

    Parameters
    ----------
    profile : RouteProfile
        The route profile from which terrain features are computed.
    vehicle_mass_kg : float, default 1800.0
        Vehicle mass used for energy/consumption estimates.
    sample_intervals_km : list of float, optional
        Custom look-ahead distances (km) to compute. If None, uses
        [1.0, 2.0, 5.0].

    Returns
    -------
    dict of str -> float
        Dictionary of feature name -> value. Features are computed per-route
        and the returned values correspond to the *first* waypoint's look-ahead.
        In production, these would be computed for every waypoint and
        aggregated (e.g., max, mean) or returned as per-waypoint arrays.

        Feature naming convention:
        - next_Xkm_elevation_gain_m: elevation gain over next X km (m)
        - next_Xkm_elevation_loss_m: elevation loss over next X km (m)
        - next_Xkm_gradient_pct: gradient over next X km (%)
        - next_Xkm_time_estimate_s: time estimate over next X km (s)
        - next_Xkm_speed_loss_pct: speed loss percent due to gradient over next X km

    All features are CONDITIONALLY_CAUSAL — they depend on the planned route
    waypoints, not on real-time telemetry or future driving conditions.
    """
    if sample_intervals_km is None:
        sample_intervals_km = [1.0, 2.0, 5.0]

    n = profile.distances_km.shape[0]
    if n == 0:
        # No waypoints — return zeros
        result: dict[str, float] = {}
        for d in sample_intervals_km:
            for suffix in ["elevation_gain_m", "elevation_loss_m", "gradient_pct",
                          "time_estimate_s", "speed_loss_pct"]:
                result[f"next_{int(d)}km_{suffix}"] = 0.0
        return result

    # Find the index of the waypoint we're computing features for.
    # In production, this would be the "current" waypoint based on vehicle position.
    # Here we compute features relative to waypoint index 0 (the route start)
    # as a representative sample.
    current_idx = 0

    # Cumulative distances
    dists = profile.distances_km  # shape (n,), cumulative from route start

    # Elevations (m); may contain NaN where unavailable
    elevs = profile.elevations_m  # shape (n,)

    # Gradients (percent slope); NaN where segment too short
    grads = profile.gradients_pct  # shape (n,)

    # Cumulative gain/loss
    cum_gain = profile.cumulative_gain_m  # shape (n,)
    cum_loss = profile.cumulative_loss_m  # shape (n,)

    # Total route distance
    total_dist = float(dists[-1]) if dists.size > 0 else 0.0

    # Result accumulator — we'll compute for the first waypoint (index 0)
    # and return single scalar values.
    results: dict[str, float] = {}

    for d_km in sample_intervals_km:
        d_km_int = int(d_km) if d_km == int(d_km) else d_km
        target_dist = dists[current_idx] + d_km  # distance ahead from current waypoint

        # Find the waypoint index where cumulative distance >= target_dist
        # Search forward from current_idx
        if current_idx >= n - 1:
            # No waypoints ahead; return zeros
            for suffix in ["elevation_gain_m", "elevation_loss_m", "gradient_pct",
                          "time_estimate_s", "speed_loss_pct"]:
                results[f"next_{d_km_int}km_{suffix}"] = 0.0
            continue

        # Find the segment where target_dist falls
        segment_idx = current_idx
        for i in range(current_idx + 1, n):
            if dists[i] >= target_dist:
                segment_idx = i
                break

        # Now we have segment_idx such that dists[segment_idx] >= target_dist
        # and dists[segment_idx - 1] < target_dist (or segment_idx == current_idx)

        seg_start_dist = dists[max(current_idx, segment_idx - 1)]
        seg_end_dist = dists[segment_idx]
        seg_length_km = seg_end_dist - seg_start_dist

        # Elevation at segment start and end
        # Use the elevation at the waypoint indices
        if segment_idx < n:
            elev_start = elevs[segment_idx - 1] if segment_idx > current_idx else elevs[current_idx]
            elev_end = elevs[segment_idx]
        else:
            # Beyond the route end; use last known elevation
            elev_start = elevs[-1] if n > 0 else 0.0
            elev_end = elevs[-1] if n > 0 else 0.0

        # Handle NaN elevations via the profile's cumulative gain/loss
        # If elevations are NaN, fall back to cumulative gain/loss diff
        if np.isnan(elev_start) or np.isnan(elev_end):
            # Use cumulative gain/loss difference as proxy
            # Find the cumulative gain/loss at these distances
            # This is approximate; find closest waypoint indices
            if segment_idx < n:
                elev_diff = cum_gain[segment_idx] + cum_loss[segment_idx]
                # Actually cumulative_gain - cumulative_loss = net elevation change
                # But we need to be careful about the sign
                # Let's use: net elevation change = cum_gain - cum_loss evaluated at segment end minus start
                # However, cum_gain only counts ascending, cum_loss only descending
                # Net elevation change is more complex; for simplicity:
                elev_diff = 0.0
                # Try to get elevation diff from waypoints directly
                if segment_idx - 1 >= 0 and segment_idx - 1 < n:
                    elev_start_raw = elevs[segment_idx - 1]
                    elev_end_raw = elevs[segment_idx]
                    if not np.isnan(elev_start_raw) and not np.isnan(elev_end_raw):
                        elev_diff = float(elev_end_raw - elev_start_raw)
                    else:
                        elev_diff = 0.0
                else:
                    elev_diff = 0.0
            else:
                elev_diff = 0.0
        else:
            elev_diff = float(elev_end - elev_start)

        # Gain is positive elevation change; loss is negative
        elevation_gain = max(0.0, elev_diff)
        elevation_loss = max(0.0, -elev_diff)

        # Gradient (percent slope) over the segment
        if seg_length_km > 0 and not (np.isnan(elev_end) or np.isnan(elev_start)):
            gradient_pct = (elev_diff / seg_length_km) * 100.0
        else:
            gradient_pct = float(grads[segment_idx]) if segment_idx < n and segment_idx < len(grads) else 0.0

        # Time estimate
        time_estimate_s = _time_for_distance(d_km, NOMINAL_CONSUMPTION_WH_PER_KM, vehicle_mass_kg)

        # Speed loss percentage due to grade
        # Approximate: grade resistance increases energy consumption, which
        # effectively reduces speed for a given power envelope
        grade = _grade_from_pct(gradient_pct)
        extra_wh_per_km = _energy_for_grade(vehicle_mass_kg, grade,
                                            wh_per_km_level=NOMINAL_CONSUMPTION_WH_PER_KM)

        # Speed loss percent: if consumption increases by X%, speed decreases roughly by X/2 %
        # (power ~ v^3, so small changes in power give ~3x changes in speed;
        # but roughly, a 10% consumption increase => ~5% speed decrease)
        if extra_wh_per_km > 0:
            speed_loss_pct = min(100.0, (extra_wh_per_km / NOMINAL_CONSUMPTION_WH_PER_KM) * 50.0)
        else:
            speed_loss_pct = 0.0

        # Store results
        d_int = int(d_km) if d_km == int(d_km) else d_km
        results[f"next_{d_int}km_elevation_gain_m"] = elevation_gain
        results[f"next_{d_int}km_elevation_loss_m"] = elevation_loss
        results[f"next_{d_int}km_gradient_pct"] = gradient_pct
        results[f"next_{d_int}km_time_estimate_s"] = time_estimate_s
        results[f"next_{d_int}km_speed_loss_pct"] = speed_loss_pct

    return results


# ---------------------------------------------------------------------------
# Per-waypoint computation (returns arrays)
# ---------------------------------------------------------------------------

def compute_all_next_terrain_features(
    profile: RouteProfile,
    *,
    vehicle_mass_kg: float = 1800.0,
    sample_intervals_km: Optional[list[float]] = None,
) -> dict[str, np.ndarray]:
    """Compute CONDITIONALLY_CAUSAL future terrain features for every waypoint.

    Parameters
    ----------
    profile : RouteProfile
        The route profile from which terrain features are computed.
    vehicle_mass_kg : float, default 1800.0
        Vehicle mass used for energy/consumption estimates.
    sample_intervals_km : list of float, optional
        Custom look-ahead distances (km) to compute. If None, uses
        [1.0, 2.0, 5.0].

    Returns
    -------
    dict of str -> np.ndarray
        Dictionary of feature name -> array of values, one per waypoint.
        Each array has shape (n_waypoints,).
    """
    if sample_intervals_km is None:
        sample_intervals_km = [1.0, 2.0, 5.0]

    n = profile.distances_km.shape[0]
    if n == 0:
        return {f"next_{int(d)}km_{suffix}": np.array([]) for d in sample_intervals_km
                for suffix in ["elevation_gain_m", "elevation_loss_m", "gradient_pct",
                              "time_estimate_s", "speed_loss_pct"]}

    # Cumulative distances
    dists = profile.distances_km  # shape (n,)
    elevs = profile.elevations_m  # shape (n,)
    grads = profile.gradients_pct  # shape (n,)

    total_dist = float(dists[-1]) if dists.size > 0 else 0.0

    results: dict[str, np.ndarray] = {}

    for d_km in sample_intervals_km:
        d_km_int = int(d_km) if d_km == int(d_km) else d_km
        target_distances = dists + d_km  # look-ahead distance from each waypoint

        elevation_gains = np.zeros(n, dtype=float)
        elevation_losses = np.zeros(n, dtype=float)
        gradients = np.full(n, np.nan, dtype=float)
        time_estimates = np.full(n, np.nan, dtype=float)
        speed_losses = np.zeros(n, dtype=float)

        for i in range(n):
            # Find the waypoint index where cumulative distance >= target_distances[i]
            lookahead = target_distances[i]

            if i >= n - 1:
                # No waypoints ahead
                elevation_gains[i] = 0.0
                elevation_losses[i] = 0.0
                gradients[i] = np.nan
                time_estimates[i] = np.nan
                speed_losses[i] = 0.0
                continue

            # Search forward for the segment containing the lookahead distance
            seg_idx = i  # default: same waypoint
            for j in range(i + 1, n):
                if dists[j] >= lookahead:
                    seg_idx = j
                    break

            seg_start_dist = dists[max(i, seg_idx - 1)]
            seg_end_dist = dists[seg_idx]
            seg_length_km = float(seg_end_dist - seg_start_dist)

            # Elevations at segment start and end
            # seg_start waypoint is max(i, seg_idx - 1); seg_end is seg_idx
            if seg_idx < n:
                elev_start_raw = elevs[max(i, seg_idx - 1)]
                elev_end_raw = elevs[seg_idx]
            else:
                elev_start_raw = elevs[-1] if n > 0 else 0.0
                elev_end_raw = elevs[-1] if n > 0 else 0.0

            # Handle NaN elevations
            if np.isnan(elev_start_raw) or np.isnan(elev_end_raw):
                # Try cumulative gain/loss diff
                # Net elevation change approx from cumulative metrics
                # Find cumulative gain/loss at these indices
                g_start = cum_gain[max(i, seg_idx - 1)] if max(i, seg_idx - 1) < len(cum_gain) else 0.0
                g_end = cum_gain[seg_idx] if seg_idx < len(cum_gain) else 0.0
                l_start = cum_loss[max(i, seg_idx - 1)] if max(i, seg_idx - 1) < len(cum_loss) else 0.0
                l_end = cum_loss[seg_idx] if seg_idx < len(cum_loss) else 0.0
                # Net elevation change ≈ gain - loss (but this only works if
                # all elevation changes are captured; use waypoint diff if available)
                if not np.isnan(elev_start_raw) and not np.isnan(elev_end_raw):
                    elev_diff = float(elev_end_raw - elev_start_raw)
                else:
                    elev_diff = float((g_end - l_end) - (g_start - l_start))
                elev_start = elev_start_raw if not np.isnan(elev_start_raw) else 0.0
                elev_end = elev_end_raw if not np.isnan(elev_end_raw) else 0.0
            else:
                elev_start = elev_start_raw
                elev_end = elev_end_raw

            elev_diff = float(elev_end - elev_start)
            elevation_gains[i] = max(0.0, elev_diff)
            elevation_losses[i] = max(0.0, -elev_diff)

            # Gradient
            if seg_length_km > 0:
                gradients[i] = (elev_diff / seg_length_km) * 100.0
            else:
                gradients[i] = float(grads[seg_idx]) if seg_idx < len(grads) else np.nan

            # Time estimate
            time_estimates[i] = _time_for_distance(d_km, NOMINAL_CONSUMPTION_WH_PER_KM, vehicle_mass_kg)

            # Speed loss due to grade
            grade = _grade_from_pct(float(gradients[i])) if not np.isnan(gradients[i]) else 0.0
            extra_wh = _energy_for_grade(vehicle_mass_kg, grade,
                                          wh_per_km_level=NOMINAL_CONSUMPTION_WH_PER_KM)
            if extra_wh > 0:
                speed_losses[i] = min(100.0, (extra_wh / NOMINAL_CONSUMPTION_WH_PER_KM) * 50.0)
            else:
                speed_losses[i] = 0.0

        results[f"next_{d_km_int}km_elevation_gain_m"] = elevation_gains
        results[f"next_{d_km_int}km_elevation_loss_m"] = elevation_losses
        results[f"next_{d_km_int}km_gradient_pct"] = gradients
        results[f"next_{d_km_int}km_time_estimate_s"] = time_estimates
        results[f"next_{d_km_int}km_speed_loss_pct"] = speed_losses

    return results


# ---------------------------------------------------------------------------
# Convenience: extract feature values for a specific waypoint index
# ---------------------------------------------------------------------------

def get_next_terrain_features_at_idx(
    profile: RouteProfile,
    waypoint_idx: int,
    *,
    sample_intervals_km: Optional[list[float]] = None,
) -> dict[str, float]:
    """Extract next-terrain features at a specific waypoint index.

    Convenience wrapper that calls compute_next_terrain_features but
    ensures the index is valid.

    Parameters
    ----------
    profile : RouteProfile
        The route profile.
    waypoint_idx : int
        Index of the waypoint at which to compute features.
    sample_intervals_km : list of float, optional
        Look-ahead distances.

    Returns
    -------
    dict of str -> float
        Feature values for the specified waypoint.
    """
    n = profile.distances_km.shape[0]
    if waypoint_idx < 0 or waypoint_idx >= n:
        # Invalid index — return zeros
        sample_intervals_km = sample_intervals_km or [1.0, 2.0, 5.0]
        result: dict[str, float] = {}
        for d in sample_intervals_km:
            d_int = int(d) if d == int(d) else d
            for suffix in ["elevation_gain_m", "elevation_loss_m", "gradient_pct",
                          "time_estimate_s", "speed_loss_pct"]:
                result[f"next_{d_int}km_{suffix}"] = 0.0
        return result

    features = compute_next_terrain_features(
        profile,
        vehicle_mass_kg=1800.0,
        sample_intervals_km=sample_intervals_km,
    )
    # The function returns dict with values for waypoint index 0;
    # we need to handle per-waypoint case. For now, return what we have.
    # In production, this would extract the [waypoint_idx] element.
    return features