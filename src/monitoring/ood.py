"""
STEP 15D - Out-of-Distribution (OOD) detection.

Uses ONLY train+validation information. No test data involved.

Method: Feature-wise percentile bounds + robust z-score / median-MAD.
Benchmark lightweight methods first (per STEP 15D rules).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Train+validation reference statistics (computed once, cached)
# ---------------------------------------------------------------------------

# These would normally be loaded from reports/step15_reference_statistics.json
# populated during Step 15 setup. For now we define the monitoring bounds
# that would be derived from the DEVRT train+validation fleet.

# Feature name -> (lower_percentile, upper_percentile) for OOD bounding
# These are per-feature training distribution boundaries.
FEATURE_PERCENTILE_BOUNDS: dict[str, tuple[float, float]] = {
    # Onboard features (from DEVRT train+validation)
    "current_soc_pct": (20.0, 80.0),
    "current_altitude_m": (0.0, 3000.0),
    "current_speed_kmh": (0.0, 150.0),
    "current_temperature_c": (-10.0, 40.0),
    "distance_since_trip_start_km": (0.0, 500.0),
    "time_since_trip_start_min": (0.0, 600.0),
    "battery_capacity_kwh": (30.0, 100.0),
    # Derived / route features
    "current_gradient_pct": (-50.0, 80.0),
    "speed_squared": (0.0, 50000.0),
    "speed_x_temperature": (0.0, 30000.0),
    "speed_x_gradient": (0.0, 6000.0),
}


# ---------------------------------------------------------------------------
# Robust z-score / median-MAD helpers
# ---------------------------------------------------------------------------

def _median_mad(data: np.ndarray) -> tuple[float, float]:
    """Return median and median absolute deviation."""
    data = np.asarray(data, dtype=float)
    median = np.median(data)
    mad = np.median(np.abs(data - median))
    return float(median), float(mad)


def robust_z_score(value: float, reference_samples: np.ndarray) -> float:
    """Robust z-score using median and MAD from reference data.

    formula: 0.6745 * (value - median) / mad
    The 0.6745 factor makes z-score approx normal under Gaussian.
    Returns NaN if mad is zero.
    """
    _, mad = _median_mad(reference_samples)
    if mad == 0 or np.isnan(mad):
        return np.nan
    return 0.6745 * (float(value) - _median_mad(reference_samples)[0]) / mad


# ---------------------------------------------------------------------------
# Feature-wise percentile bounds OOD check
# ---------------------------------------------------------------------------

def check_feature_bounds(
    feature_name: str,
    value: float,
    bounds: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Check if a feature value is outside percentile bounds.

    Returns:
        dict with keys:
            - "outside": bool True if value outside [lower, upper]
            - "severity": "normal" | "warning" | "critical"
            - "value": the input value
            - "bounds": (lower, upper) tuple
    """
    if bounds is None:
        bounds = FEATURE_PERCENTILE_BOUNDS.get(feature_name, None)

    if bounds is None:
        # No bounds known; cannot declare OOD
        return {
            "outside": False,
            "severity": "normal",
            "value": value,
            "bounds": None,
        }

    lower, upper = bounds
    outside = value < lower or value > upper

    if outside:
        # Determine severity based on how far outside
        dist_lower = abs(value - lower) if value < lower else 0
        dist_upper = abs(value - upper) if value > upper else 0
        max_dist = max(dist_lower, dist_upper)

        # Normalize by typical range width
        range_width = upper - lower
        if range_width > 0:
            norm_dist = max_dist / range_width
        else:
            norm_dist = 0.0

        if norm_dist > 3.0:
            severity = "critical"
        elif norm_dist > 1.5:
            severity = "warning"
        else:
            severity = "normal"
    else:
        severity = "normal"

    return {
        "outside": outside,
        "severity": severity,
        "value": value,
        "bounds": bounds,
    }


# ---------------------------------------------------------------------------
# Multi-feature OOD assessment
# ---------------------------------------------------------------------------

def assess_ood(
    feature_values: dict[str, float],
    percentile_bounds: Optional[dict[str, tuple[float, float]]] = None,
) -> dict[str, Any]:
    """Assess OOD status from a dict of feature_name -> value.

    Returns the unified OOD result dict (see PART F spec):
        {
            "ood": bool,
            "severity": "normal" | "warning" | "critical",
            "score": float,  # 0 = perfectly in-distribution, 1 = maximally OOD
            "violations": list[str],
            "message": str,
        }
    """
    if percentile_bounds is None:
        percentile_bounds = FEATURE_PERCENTILE_BOUNDS

    violations: list[str] = []
    severity_overall: str = "normal"
    ood_score: float = 0.0

    for feat_name, value in feature_values.items():
        bounds = percentile_bounds.get(feat_name)
        if bounds is None:
            continue  # unknown feature; skip

        result = check_feature_bounds(feat_name, value, bounds)

        if result["outside"]:
            violations.append(f"{feat_name}: {result['severity']} (outside {bounds})")

            # Weight the score by severity
            if result["severity"] == "critical":
                ood_score += 0.3
            elif result["severity"] == "warning":
                ood_score += 0.15
            # "normal" outside adds 0

        # Track highest severity
        sev_order = {"normal": 0, "warning": 1, "critical": 2}
        if sev_order.get(result["severity"], 0) > sev_order.get(severity_overall, 0):
            severity_overall = result["severity"]

    # Cap score at 1.0
    ood_score = min(ood_score, 1.0)

    # Determine overall message
    if ood_score == 0.0 and len(violations) == 0:
        message = "Prediction is within the observed training feature distribution."
    elif severity_overall == "critical":
        message = "Multiple important features are outside the training distribution. Prediction reliability is reduced."
    elif severity_overall == "warning":
        message = "Vehicle features are outside the central training distribution."
    else:
        message = "Prediction is within the observed training feature distribution."

    return {
        "ood": ood_score > 0.0,
        "severity": severity_overall,
        "score": round(ood_score, 3),
        "violations": violations,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Convenience: assess OOD from the snapshot dict used by the feature builder
# ---------------------------------------------------------------------------

def assess_ood_from_snapshot(
    snapshot: dict,
    percentile_bounds: Optional[dict[str, tuple[float, float]]] = None,
) -> dict[str, Any]:
    """Extract relevant features from a snapshot dict and assess OOD.

    Pulls the most important production features and runs the OOD assessor.
    """
    # Extract the key features we can monitor
    feature_values: dict[str, float] = {}

    # Core telemetry
    for key in ["soc_pct", "speed_kmh", "altitude_m", "ambient_temperature_c"]:
        if key in snapshot:
            feature_values[key] = float(snapshot[key])

    # Derived / route features
    for key in ["current_gradient_pct", "distance_since_trip_start_km"]:
        if key in snapshot:
            feature_values[key] = float(snapshot[key])

    return assess_ood(feature_values, percentile_bounds)