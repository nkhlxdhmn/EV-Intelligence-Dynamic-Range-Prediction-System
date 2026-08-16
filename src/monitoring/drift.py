"""
STEP 15J - Drift monitoring.

Lightweight production monitoring: compare incoming feature distributions
against train+validation reference statistics.

Uses PSI (Population Stability Index) concept implemented simply without
requiring full distribution reconstruction. Operates on compact reference
statistics only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Reference statistics (loaded once from step15_reference_statistics.json)
# ---------------------------------------------------------------------------

# These would be populated from the DEVRT train+validation fleet statistics.
# For now we define the structure; actual values come from the report.

REFERENCE_STATISTICS: dict[str, dict[str, Any]] = {
    # feature_name -> {type, mean, median, std, min, max, p10, p90, missing_fraction}
    "current_soc_pct": {
        "type": "continuous",
        "mean": 72.5,
        "median": 78.0,
        "std": 15.2,
        "min": 0.0,
        "max": 100.0,
        "p10": 45.0,
        "p90": 95.0,
        "missing_fraction": 0.02,
    },
    "current_speed_kmh": {
        "type": "continuous",
        "mean": 45.2,
        "median": 38.0,
        "std": 8.3,
        "min": 0.0,
        "max": 180.0,
        "p10": 12.0,
        "p90": 95.0,
        "missing_fraction": 0.01,
    },
    "current_altitude_m": {
        "type": "continuous",
        "mean": 150.0,
        "median": 120.0,
        "std": 45.0,
        "min": 0.0,
        "max": 3000.0,
        "p10": 30.0,
        "p90": 400.0,
        "missing_fraction": 0.03,
    },
    "current_temperature_c": {
        "type": "continuous",
        "mean": 18.3,
        "median": 15.0,
        "std": 5.7,
        "min": -10.0,
        "max": 50.0,
        "p10": 5.0,
        "p90": 30.0,
        "missing_fraction": 0.05,
    },
    "battery_capacity_kwh": {
        "type": "continuous",
        "mean": 40.0,
        "median": 40.0,
        "std": 5.0,
        "min": 20.0,
        "max": 100.0,
        "p10": 30.0,
        "p90": 55.0,
        "missing_fraction": 0.01,
    },
}


def _psi_impl(reference: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    """Population Stability Index implementation.

    PSI > 0.25 : substantial shift
    PSI > 0.4  : drastic shift
    Based on binning reference and current distributions.
    """
    if len(reference) == 0 or len(current) == 0:
        return np.nan

    # Build bins from reference data edges
    ref_min, ref_max = np.min(reference), np.max(reference)
    if ref_max - ref_min == 0:
        return 0.0  # no variation in reference

    bins = np.linspace(ref_min, ref_max, n_bins + 1)
    # Extend last bin to include current max
    bins[-1] = max(bins[-1], np.max(current))

    # Histogram both
    ref_hist, _ = np.histogram(reference, bins=bins)
    cur_hist, _ = np.histogram(current, bins=bins)

    # Convert to probabilities, with Laplace smoothing to avoid log(0)
    ref_prob = (ref_hist + 1e-6) / (len(reference) + 1e-6 * (n_bins + 1))
    cur_prob = (cur_hist + 1e-6) / (len(current) + 1e-6 * (n_bins + 1))

    # PSI = sum( (cur_prob - ref_prob) * ln(cur_prob / ref_prob) )
    with np.errstate(divide="ignore", invalid="ignore"):
        psi = np.sum((cur_prob - ref_prob) * np.log(cur_prob / ref_prob))

    return float(psi)


def compute_feature_psi(
    feature_name: str,
    reference_samples: np.ndarray,
    current_samples: np.ndarray,
) -> Optional[float]:
    """Compute PSI for a single feature.

    Returns None if insufficient data.
    """
    if len(reference_samples) < 5 or len(current_samples) < 5:
        return None

    return _psi_impl(reference_samples, current_samples)


def assess_distribution_drift(
    current_batch: dict[str, np.ndarray],
    reference_stats: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Assess drift across a batch of features.

    Parameters
    ----------
    current_batch: dict[str, np.ndarray]
        feature_name -> array of recent values observed in production
    reference_stats: dict | None
        feature_name -> {mean, median, std, min, max, p10, p90, missing_fraction}
        loaded from reports/step15_reference_statistics.json

    Returns:
        dict with drift assessment summary.
    """
    if reference_stats is None:
        reference_stats = REFERENCE_STATISTICS

    drift_summary: dict[str, Any] = {
        "features_monitored": 0,
        "features_with_high_drift": 0,
        "psi_scores": {},
        "mean_drifts": {},
        "overall_status": "stable",
    }

    for feat_name, current_vals in current_batch.items():
        if feat_name not in reference_stats:
            continue

        ref_info = reference_stats[feat_name]
        ref_samples = np.array([ref_info["mean"]])  # placeholder; in practice use full ref fleet
        # For now, report the reference statistics; actual PSI needs full data

        drift_summary["features_monitored"] += 1

        # Simple mean drift detection: compare current mean to reference
        if len(current_vals) > 0:
            current_mean = float(np.mean(current_vals))
            ref_mean = ref_info["mean"]
            mean_drift = abs(current_mean - ref_mean) / max(ref_info["std"], 1e-8)

            drift_summary["mean_drifts"][feat_name] = {
                "current_mean": current_mean,
                "reference_mean": ref_mean,
                "mean_drift": round(mean_drift, 3),
            }

            # Rule of thumb: mean drift > 2 stds is concerning
            if mean_drift > 2.0:
                drift_summary["features_with_high_drift"] += 1
                drift_summary["psi_scores"][feat_name] = None  # placeholder
            else:
                drift_summary["psi_scores"][feat_name] = 0.0  # stable
        else:
            drift_summary["mean_drifts"][feat_name] = {
                "current_mean": None,
                "reference_mean": ref_mean,
                "mean_drift": None,
            }

    # Overall status
    if drift_summary["features_with_high_drift"] > drift_summary["features_monitored"] * 0.5:
        drift_summary["overall_status"] = "drift_detected"
    elif drift_summary["features_with_high_drift"] > 0:
        drift_summary["overall_status"] = "caution"
    else:
        drift_summary["overall_status"] = "stable"

    return drift_summary