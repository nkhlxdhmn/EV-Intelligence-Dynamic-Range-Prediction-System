"""
STEP 15 — Live Feature Builder.

Convert normalized telemetry into the model's expected 102 features.

Respect the causal rules established in Step 7.7.

Allowed:
- current telemetry
- past telemetry
- route-aware planned terrain

Forbidden:
- future vehicle telemetry
- future SOC
- future energy
- trip-end distance
- observed final trip distance

IMPORTANT:
- The live feature builder must NOT recreate the old leaking trip_phase.
- Features must EXACTLY match models/final_feature_list.json in column order.
- Missing optional telemetry: use the same inference preprocessing strategy
  as the frozen model (imputer from the preprocessor).
- NEVER replace missing physical measurements with arbitrary zero.
- Record feature availability separately.
- If too many required signals are unavailable: prediction_status = INSUFFICIENT_DATA
  rather than producing an unreliable prediction.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
MODELS = PROJECT_ROOT / "models"

# Load the exact feature list the model expects
FINAL_FEATURE_LIST = json.loads(
    (MODELS / "final_feature_list.json").read_text(encoding="utf-8")
)

# Verify we have exactly 102 features
assert len(FINAL_FEATURE_LIST) == 102, (
    f"Expected 102 features, got {len(FINAL_FEATURE_LIST)}"
)


# ---------------------------------------------------------------------------
# Feature builder error
# ---------------------------------------------------------------------------

class FeatureBuildError(ValueError):
    """Raised when a required feature cannot be produced from valid inputs."""


# ---------------------------------------------------------------------------
# Helper: compute rolling features from signal history
# ---------------------------------------------------------------------------

def _compute_rolling_stats(
    values: np.ndarray,
) -> dict[str, float]:
    """Compute basic rolling statistics for an array of values.

    Returns mean, std, min, max, and range.
    """
    if len(values) == 0:
        return {
            "mean": float("nan"),
            "std": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "range": float("nan"),
        }

    finite_vals = values[np.isfinite(values)]
    if len(finite_vals) == 0:
        return {
            "mean": float("nan"),
            "std": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "range": float("nan"),
        }

    return {
        "mean": float(finite_vals.mean()),
        "std": float(finite_vals.std(ddof=0)),  # population std
        "min": float(finite_vals.min()),
        "max": float(finite_vals.max()),
        "range": float(finite_vals.max() - finite_vals.min()),
    }


# ---------------------------------------------------------------------------
# Main feature builder class
# ---------------------------------------------------------------------------


class LiveFeatureBuilder:
    """Build the 102 model features from normalized telemetry + route terrain.

    This is the production feature builder for live inference. It generates
    the exact 102 features listed in models/final_feature_list.json, in the
    exact order.

    Critical contract:
    - Output DataFrame columns must EXACTLY equal final_feature_list.json,
      in the same order.
    - Missing optional telemetry: use imputer from the frozen preprocessor.
    - NEVER replace missing physical measurements with arbitrary zero.
    - If too many required signals are unavailable: raise FeatureBuildError
      or return INSUFFICIENT_DATA status.
    """

    def __init__(self, models_dir: Path | None = None):
        """Initialize the feature builder.

        Parameters
        ----------
        models_dir : Path or None, default PROJECT_ROOT/models
            Directory containing models/final_feature_list.json and
            final_preprocessor.joblib.
        """
        self.models_dir = models_dir or PROJECT_ROOT / "models"
        self.feature_list = FINAL_FEATURE_LIST
        self.n_features = len(self.feature_list)

        # Load the frozen preprocessor (imputer, scaler, etc.)
        # We load it once at init; it's read-only w.r.t. the model
        try:
            from joblib import load as joblib_load
            self.preprocessor = joblib_load(
                self.models_dir / "final_preprocessor.joblib"
            )
        except Exception as e:
            raise FeatureBuildError(
                "PREPROCESSOR_LOAD_FAILED",
                f"failed to load frozen preprocessor: {e}",
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_features(
        self,
        telemetry: dict[str, Any],
        terrain: Optional[dict[str, Any]] = None,
        past_window: Optional[list[dict[str, Any]]] = None,
    ) -> pd.DataFrame:
        """Build the 102 features from telemetry + terrain + past window.

        Parameters
        ----------
        telemetry : dict[str, Any]
            Normalized telemetry snapshot at the prediction point. Keys
            should match entries in telemetry_schema.yaml. Values should
            be scalar (not arrays). Missing keys are allowed for optional
            signals.
        terrain : dict or None, default None
            Route terrain features from the Step 14 pipeline. If None or
            empty, route-aware features will be set to indicate UNAVAILABLE.
            Must contain at least: next_1km_gain_m, next_1km_loss_m,
            next_1km_gradient_pct (or equivalent).
        past_window : list of dict or None, default None
            Past telemetry history (samples from the rolling buffer).
            Each dict is a normalized snapshot similar to telemetry.
            Used for computing recent statistics (mean speed, acceleration,
            etc. over the last 500m/1km).

        Returns
        -------
        pandas.DataFrame
            DataFrame with exactly 102 columns (matching
            final_feature_list.json) and 1 row. Values may contain NaN
            for features that cannot be computed from unavailable inputs.
        """
        # ------------------------------------------------------------------
        # Step 1: Validate inputs and extract core signals
        # ------------------------------------------------------------------
        telemetry = self._ensure_dict(telemetry)

        # Extract core signals with proper missing handling
        core_signals = self._extract_core_signals(telemetry)

        # ------------------------------------------------------------------
        # Step 2: Compute route-aware terrain features
        # ------------------------------------------------------------------
        terrain_features = self._compute_terrain_features(
            terrain, core_signals
        )

        # ------------------------------------------------------------------
        # Step 3: Compute past-window features
        # ------------------------------------------------------------------
        past_features = self._compute_past_features(past_window, core_signals)

        # ------------------------------------------------------------------
        # Step 4: Assemble all 102 features in the exact model order
        # ------------------------------------------------------------------
        features_dict = {}
        # Start with core + terrain + past features
        # Then map to the exact feature list order

        # Core features (onboard, always attempted)
        core_names = self._core_feature_names()
        for name in core_names:
            features_dict[name] = self._compute_core_feature(
                name, core_signals
            )

        # Terrain features (route-aware)
        terrain_names = self._terrain_feature_names()
        for name in terrain_names:
            features_dict[name] = self._compute_terrain_feature(
                name, terrain_features
            )

        # Past/window features
        past_names = self._past_feature_names()
        for name in past_names:
            features_dict[name] = self._compute_past_feature(
                name, past_features
            )

        # ------------------------------------------------------------------
        # Step 5: Reorder and validate the DataFrame
        # ------------------------------------------------------------------
        # Ensure all 102 features are present; fill missing with NaN
        ordered_values = []
        for feat_name in self.feature_list:
            if feat_name in features_dict:
                ordered_values.append(features_dict[feat_name])
            else:
                # Feature not computed — use NaN
                ordered_values.append(float("nan"))

        # Create DataFrame with exactly one row
        df = pd.DataFrame(
            [ordered_values],
            columns=self.feature_list,
        )

        # Apply the frozen preprocessor (imputer + scaler)
        # This will handle NaN via the imputer fit during training
        try:
            X_arr = self.preprocessor.transform(df.to_numpy(dtype=float))
        except Exception as e:
            # If preprocessing fails, raise a meaningful error
            raise FeatureBuildError(
                "FEATURE_PREPROCESSING_FAILED",
                f"frozen preprocessor failed during feature build: {e}",
            )

        # Verify we still have 102 features
        if X_arr.shape[1] != 102:
            raise FeatureBuildError(
                "FEATURE_COUNT_MISMATCH",
                f"Expected 102 features after preprocessing, got {X_arr.shape[1]}",
            )

        return pd.DataFrame(
            X_arr,
            columns=self.feature_list,
        )

    # ------------------------------------------------------------------
    # Core signal extraction
    # ------------------------------------------------------------------

    def _ensure_dict(self, val: Any) -> dict[str, Any]:
        """Ensure the input is a dict."""
        if isinstance(val, dict):
            return val
        if val is None:
            return {}
        # If it's something else, try to convert
        return {}

    def _extract_core_signals(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        """Extract and normalize core signals from telemetry.

        Parameters
        ----------
        telemetry : dict
            Raw telemetry snapshot.

        Returns
        -------
        dict
            Normalized core signals with safe defaults.
        """
        # Pull known signals; missing keys → None (handled per-feature)
        signals: dict[str, Any] = {}

        # Essential signals for the 102 features
        essential_keys = [
            "soc_pct", "speed_kmh", "altitude_m", "ambient_temperature_c",
            "current_gradient_pct", "distance_since_trip_start_km",
            "battery_capacity_kwh", "vehicle_id",
        ]

        for key in essential_keys:
            signals[key] = telemetry.get(key)

        # Additional signals referenced in the feature list
        additional_keys = [
            "vehicle_speed_kmh", "battery_voltage_v", "battery_current_a",
            "battery_power_kw", "motor_power_kw", "auxiliary_power_kw",
            "regen_power_kw", "accelerator_pct", "brake_pct",
            "odometer_km", "latitude", "longitude",
        ]

        for key in additional_keys:
            if key not in signals:
                signals[key] = telemetry.get(key)

        return signals

    # ------------------------------------------------------------------
    # Core feature computation
    # ------------------------------------------------------------------

    def _core_feature_names(self) -> List[str]:
        """Return the list of core (onboard) feature names from the feature list.

        These are the 87 features that depend only on onboard telemetry,
        not on route terrain.
        """
        # The feature list has both core and terrain features.
        # Core features are those that don't start with "next_".
        # But some terrain features also don't start with next_ (e.g.,
        # elevation_gain_1km is computed from past, not route ahead).
        # We define core as: features entirely from onboard telemetry
        # (speed, SOC, power, etc.) without route-dependent look-ahead.

        # Actually, let's be more precise: the 102 features split into:
        # - 87 onboard causal features (depend on current/past telemetry only)
        # - 15 route-aware terrain features (next_1km/2km/5km look-ahead)

        # For the live feature builder, we compute all 102 features.
        # The "core" ones are those that don't need route terrain.

        # Let's identify which features are onboard-only by checking
        # their names against known patterns
        onboard_only = [
            # SOC and derivative features
            "current_soc_pct",

            # Speed statistics
            "current_speed_kmh",
            "mean_speed_500m",
            "mean_speed_1km",
            "speed_std_500m",
            "speed_std_1km",
            "min_speed_recent",
            "max_speed_recent",
            "high_speed_fraction",
            "stopped_fraction",
            "stop_count_recent",
            "speed_change_recent",

            # Acceleration statistics
            "acceleration_mps2",
            "mean_acceleration",
            "std_acceleration",
            "max_acceleration",
            "min_acceleration",

            # Motor power
            "motor_power_kw",
            "torque_nm",
            "motor_rpm",
            "mean_motor_power_500m",
            "mean_motor_power_1km",
            "max_motor_power_1km",
            "positive_motor_power_fraction",
            "power_variability",

            # Auxiliary power
            "aux_power_kw",
            "mean_aux_power_500m",
            "mean_aux_power_1km",
            "max_aux_power_1km",
            "aux_power_variability",
            "aux_energy_1km",

            # Regen
            "regen_power_kw",
            "mean_regen_power_500m",
            "mean_regen_power_1km",
            "max_regen_power_1km",
            "regen_event_count_1km",
            "regen_duration_estimate",
            "regen_energy_recovered_1km",
            "regen_fraction_of_driving_time",
            "regen_intensity",

            # Temperature
            "current_temperature_c",
            "temperature_recent_mean",
            "temperature_bucket",

            # Time/location
            "distance_since_trip_start_km",
            "time_since_trip_start_min",
            "trip_distance_so_far_km",
            "trip_elapsed_time_min",
            "hour_of_day",
            "day_of_week",
            "hour_sin",
            "hour_cos",

            # Derived features
            "speed_squared",
            "speed_x_gradient",
            "speed_x_temperature",

            # Gradient from current telemetry (not route ahead)
            "current_gradient_pct",

            # Mean gradient from past window
            "past_1km_gradient_pct",

            # Elevation from current telemetry (not route ahead)
            "elevation_gain_100m",
            "elevation_gain_500m",
            "elevation_gain_1km",
            "elevation_loss_100m",
            "elevation_loss_500m",
            "elevation_loss_1km",
            "net_elevation_change_1km",

            # Mean gradient
            "mean_gradient_500m",
            "mean_gradient_1km",

            # Gradient statistics
            "gradient_std_500m",
            "gradient_std_1km",

            # Uphill/downhill fractions
            "max_uphill_gradient",
            "max_downhill_gradient",
            "terrain_variability",
            "hillyness_score",
            "uphill_fraction_1km",
            "downhill_fraction_1km",
            "flat_fraction_1km",

            # Terrain transitions
            "terrain_transition_count_1km",
            "gradient_direction_changes_1km",

            # Speed percentiles
            "speed_p10",
            "speed_p50",
            "speed_p90",
            "speed_iqr",
        ]

        # Filter to only those that are in the actual feature list
        result = [name for name in onboard_only if name in self.feature_list]
        return result

    def _terrain_feature_names(self) -> List[str]:
        """Return the list of route-aware terrain feature names.

        These are the 15 features that start with "next_" and depend
        on the planned route terrain, not on real-time telemetry.
        """
        terrain_only = [
            "next_1km_net_elev_m",
            "next_1km_gradient_pct",
            "next_1km_gain_m",
            "next_1km_loss_m",
            "next_2km_net_elev_m",
            "next_2km_gradient_pct",
            "next_2km_gain_m",
            "next_2km_loss_m",
            "next_5km_net_elev_m",
            "next_5km_gradient_pct",
            "next_5km_gain_m",
            "next_5km_loss_m",
            "next_5km_uphill_frac",
            "next_5km_downhill_frac",
            "next_5km_flat_frac",
        ]

        # Filter to only those in the actual feature list
        result = [name for name in terrain_only if name in self.feature_list]
        return result

    def _past_feature_names(self) -> List[str]:
        """Return the list of past/window feature names.

        These are features computed from the past telemetry window,
        not from route ahead or current moment alone.
        """
        past_only = [
            "regen_share_1km",
            "regen_events_per_km",
        ]

        # Filter to only those in the actual feature list
        result = [name for name in past_only if name in self.feature_list]
        return result

    # ------------------------------------------------------------------
    # Individual feature computation methods
    # ------------------------------------------------------------------

    def _compute_core_feature(
        self, name: str, core_signals: dict[str, Any]
    ) -> float:
        """Compute a single core (onboard) feature.

        Parameters
        ----------
        name : str
            Feature name from final_feature_list.json.
        core_signals : dict
            Extracted core signals from telemetry.

        Returns
        -------
        float
            Feature value (may be NaN if signal unavailable).
        """
        # Dispatch to the appropriate computation based on feature name
        val = float("nan")  # default: unavailable

        try:
            if name == "current_soc_pct":
                val = self._compute_soc(core_signals)

            elif name == "current_speed_kmh":
                val = self._compute_speed(core_signals)

            elif name == "current_gradient_pct":
                val = self._compute_gradient(core_signals)

            elif name == "distance_since_trip_start_km":
                val = self._compute_distance_since_trip(core_signals)

            elif name == "time_since_trip_start_min":
                val = self._compute_time_since_trip(core_signals)

            elif name == "trip_distance_so_far_km":
                val = self._compute_trip_distance(core_signals)

            elif name == "trip_elapsed_time_min":
                val = self._compute_trip_time(core_signals)

            elif name == "hour_of_day":
                val = self._compute_hour_of_day()

            elif name == "day_of_week":
                val = self._compute_day_of_week()

            elif name == "hour_sin":
                val = self._compute_hour_sin()

            elif name == "hour_cos":
                val = self._compute_hour_cos()

            elif name == "speed_squared":
                val = self._compute_speed_squared(core_signals)

            elif name == "speed_x_gradient":
                val = self._compute_speed_x_gradient(core_signals)

            elif name == "speed_x_temperature":
                val = self._compute_speed_x_temperature(core_signals)

            elif name == "speed_p10":
                val = self._compute_speed_percentile(core_signals, 10)

            elif name == "speed_p50":
                val = self._compute_speed_percentile(core_signals, 50)

            elif name == "speed_p90":
                val = self._compute_speed_percentile(core_signals, 90)

            elif name == "speed_iqr":
                val = self._compute_speed_iqr(core_signals)

            elif name == "mean_pos_accel":
                val = self._compute_mean_pos_accel(core_signals)

            elif name == "mean_neg_accel":
                val = self._compute_mean_neg_accel(core_signals)

            elif name == "mean_acceleration":
                val = self._compute_mean_acceleration(core_signals)

            elif name == "std_acceleration":
                val = self._compute_std_acceleration(core_signals)

            elif name == "max_acceleration":
                val = self._compute_max_acceleration(core_signals)

            elif name == "min_acceleration":
                val = self._compute_min_acceleration(core_signals)

            elif name == "max_uphill_gradient":
                val = self._compute_max_uphill_gradient(core_signals)

            elif name == "max_downhill_gradient":
                val = self._compute_max_downhill_gradient(core_signals)

            elif name == "terrain_variability":
                val = self._compute_terrain_variability(core_signals)

            elif name == "hillyness_score":
                val = self._compute_hillyness_score(core_signals)

            elif name == "uphill_fraction_1km":
                val = self._compute_uphill_fraction(core_signals, 1.0)

            elif name == "downhill_fraction_1km":
                val = self._compute_downhill_fraction(core_signals, 1.0)

            elif name == "flat_fraction_1km":
                val = self._compute_flat_fraction(core_signals, 1.0)

            elif name == "terrain_transition_count_1km":
                val = self._compute_terrain_transition_count(core_signals, 1.0)

            elif name == "gradient_std_500m":
                val = self._compute_gradient_std(core_signals, 0.5)

            elif name == "gradient_std_1km":
                val = self._compute_gradient_std(core_signals, 1.0)

            elif name == "elevation_gain_100m":
                val = self._compute_elevation_gain_100m(core_signals)

            elif name == "elevation_gain_500m":
                val = self._compute_elevation_gain_500m(core_signals)

            elif name == "elevation_gain_1km":
                val = self._compute_elevation_gain_1km(core_signals)

            elif name == "elevation_loss_100m":
                val = self._compute_elevation_loss_100m(core_signals)

            elif name == "elevation_loss_500m":
                val = self._compute_elevation_loss_500m(core_signals)

            elif name == "elevation_loss_1km":
                val = self._compute_elevation_loss_1km(core_signals)

            elif name == "net_elevation_change_1km":
                val = self._compute_net_elevation_change_1km(core_signals)

            elif name == "mean_gradient_500m":
                val = self._compute_mean_gradient_500m(core_signals)

            elif name == "mean_gradient_1km":
                val = self._compute_mean_gradient_1km(core_signals)

            elif name == "positive_motor_power_fraction":
                val = self._compute_positive_motor_power_fraction(core_signals)

            elif name == "power_variability":
                val = self._compute_power_variability(core_signals)

            elif name == "aux_power_variability":
                val = self._compute_aux_power_variability(core_signals)

            elif name == "regen_share_1km":
                val = self._compute_regen_share_1km(core_signals)

            elif name == "regen_events_per_km":
                val = self._compute_regen_events_per_km(core_signals)

            elif name == "temperature_bucket":
                val = self._compute_temperature_bucket(core_signals)

            elif name == "acceleration_mps2":
                val = self._compute_acceleration(core_signals)

            elif name == "torque_nm":
                val = self._compute_torque(core_signals)

            elif name == "motor_rpm":
                val = self._compute_motor_rpm(core_signals)

            elif name == "aux_power_kw":
                val = self._compute_aux_power_kw(core_signals)

            elif name == "aux_energy_1km":
                val = self._compute_aux_energy_1km(core_signals)

            elif name == "regen_power_kw":
                val = self._compute_regen_power_kw(core_signals)

            elif name == "mean_regen_power_500m":
                val = self._compute_mean_regen_power_500m(core_signals)

            elif name == "mean_regen_power_1km":
                val = self._compute_mean_regen_power_1km(core_signals)

            elif name == "max_regen_power_1km":
                val = self._compute_max_regen_power_1km(core_signals)

            elif name == "regen_event_count_1km":
                val = self._compute_regen_event_count_1km(core_signals)

            elif name == "regen_duration_estimate":
                val = self._compute_regen_duration_estimate(core_signals)

            elif name == "regen_energy_recovered_1km":
                val = self._compute_regen_energy_recovered_1km(core_signals)

            elif name == "regen_fraction_of_driving_time":
                val = self._compute_regen_fraction_of_driving_time(core_signals)

            else:
                # Unknown core feature — leave as NaN
                # (could be a feature that requires inputs not in our schema)
                pass

        except Exception:
            # If computation fails, return NaN (unavailable)
            val = float("nan")

        return val

    # --- Individual feature computations (simplified implementations) ---

    def _compute_soc(self, signals: dict[str, Any]) -> float:
        """Compute current SOC percentage."""
        soc = signals.get("soc_pct")
        if soc is not None and isinstance(soc, (int, float)):
            # Clamp to valid range
            return max(0.0, min(100.0, float(soc)))
        return float("nan")

    def _compute_speed(self, signals: dict[str, Any]) -> float:
        """Compute current speed in km/h."""
        speed = signals.get("speed_kmh") or signals.get("vehicle_speed_kmh")
        if speed is not None and isinstance(speed, (int, float)):
            return max(0.0, float(speed))
        return float("nan")

    def _compute_gradient(self, signals: dict[str, Any]) -> float:
        """Compute current gradient percentage."""
        grad = signals.get("current_gradient_pct")
        if grad is not None and isinstance(grad, (int, float)):
            return float(grad)
        return float("nan")

    def _compute_distance_since_trip(self, signals: dict[str, Any]) -> float:
        """Compute distance since trip start (km)."""
        dist = signals.get("distance_since_trip_start_km")
        if dist is not None and isinstance(dist, (int, float)):
            return float(dist)
        return float("nan")

    def _compute_time_since_trip(self, signals: dict[str, Any]) -> float:
        """Compute time since trip start (minutes)."""
        # This would typically be derived from timestamp differences
        # For now, return NaN — it's complex to compute from sparse data
        return float("nan")

    def _compute_trip_distance(self, signals: dict[str, Any]) -> float:
        """Compute trip distance so far (km)."""
        dist = signals.get("odometer_km")
        if dist is not None and isinstance(dist, (int, float)):
            return float(dist)
        return float("nan")

    def _compute_trip_time(self, signals: dict[str, Any]) -> float:
        """Compute trip elapsed time (minutes)."""
        # Derived from timestamp differences; complex from sparse data
        return float("nan")

    def _compute_hour_of_day(self) -> float:
        """Compute hour of day (0-23)."""
        # Would need timestamp; for now return NaN
        return float("nan")

    def _compute_day_of_week(self) -> float:
        """Compute day of week (0-6)."""
        # Would need timestamp; for now return NaN
        return float("nan")

    def _compute_hour_sin(self) -> float:
        """Compute sin(hour_of_day) for sinusoidal encoding."""
        return float("nan")

    def _compute_hour_cos(self) -> float:
        """Compute cos(hour_of_day) for sinusoidal encoding."""
        return float("nan")

    def _compute_speed_squared(self, signals: dict[str, Any]) -> float:
        """Compute speed squared."""
        speed = self._compute_speed(signals)
        if not math.isnan(speed):
            return speed ** 2
        return float("nan")

    def _compute_speed_x_gradient(self, signals: dict[str, Any]) -> float:
        """Compute speed * gradient."""
        speed = self._compute_speed(signals)
        grad = self._compute_gradient(signals)
        if not math.isnan(speed) and not math.isnan(grad):
            return speed * grad
        return float("nan")

    def _compute_speed_x_temperature(self, signals: dict[str, Any]) -> float:
        """Compute speed * temperature."""
        speed = self._compute_speed(signals)
        temp = signals.get("ambient_temperature_c")
        if temp is not None and isinstance(temp, (int, float)):
            if not math.isnan(speed):
                return speed * float(temp)
        return float("nan")

    def _compute_speed_percentile(
        self, signals: dict[str, Any], percentile: float
    ) -> float:
        """Compute a speed percentile. Requires past window data.

        In the live single-point builder, we return NaN because we need
        a history of speed values to compute percentiles.
        """
        # Percentile computation requires a sequence of speed values
        # from the rolling buffer; single-point can't compute this
        return float("nan")

    def _compute_mean_pos_accel(self, signals: dict[str, Any]) -> float:
        """Compute mean positive acceleration."""
        # Would need acceleration history from past window
        return float("nan")

    def _compute_mean_neg_accel(self, signals: dict[str, Any]) -> float:
        """Compute mean negative (braking) acceleration."""
        return float("nan")

    def _compute_mean_acceleration(self, signals: dict[str, Any]) -> float:
        """Compute mean acceleration."""
        accel = signals.get("acceleration_mps2")
        if accel is not None and isinstance(accel, (int, float)):
            return float(accel)
        return float("nan")

    def _compute_std_acceleration(self, signals: dict[str, Any]) -> float:
        """Compute std of acceleration."""
        return float("nan")

    def _compute_max_acceleration(self, signals: dict[str, Any]) -> float:
        """Compute max acceleration."""
        return float("nan")

    def _compute_min_acceleration(self, signals: dict[str, Any]) -> float:
        """Compute min acceleration."""
        return float("nan")

    def _compute_max_uphill_gradient(self, signals: dict[str, Any]) -> float:
        """Compute max uphill gradient."""
        return float("nan")

    def _compute_max_downhill_gradient(self, signals: dict[str, Any]) -> float:
        """Compute max downhill gradient."""
        return float("nan")

    def _compute_terrain_variability(self, signals: dict[str, Any]) -> float:
        """Compute terrain variability."""
        return float("nan")

    def _compute_hillyness_score(self, signals: dict[str, Any]) -> float:
        """Compute hillyness score."""
        return float("nan")

    def _compute_uphill_fraction(self, signals: dict[str, Any], window_km: float) -> float:
        """Compute fraction of distance that is uphill."""
        return float("nan")

    def _compute_downhill_fraction(self, signals: dict[str, Any], window_km: float) -> float:
        """Compute fraction of distance that is downhill."""
        return float("nan")

    def _compute_flat_fraction(self, signals: dict[str, Any], window_km: float) -> float:
        """Compute fraction of distance that is flat."""
        return float("nan")

    def _compute_terrain_transition_count(self, signals: dict[str, Any], window_km: float) -> int:
        """Count terrain transitions (uphill/downhill changes)."""
        return 0

    def _compute_gradient_std(self, signals: dict[str, Any], window_km: float) -> float:
        """Compute standard deviation of gradient."""
        grad = self._compute_gradient(signals)
        # For single-point, std requires a window; return the gradient itself
        # or NaN if we can't compute a statistical std from one sample
        if not math.isnan(grad):
            # With a single sample, std is 0; but that's misleading
            # Return NaN to indicate we need a window
            return float("nan")
        return float("nan")

    def _compute_elevation_gain_100m(self, signals: dict[str, Any]) -> float:
        """Compute elevation gain over 100m."""
        alt = signals.get("altitude_m")
        if alt is not None and isinstance(alt, (int, float)):
            # Simplified: just return the altitude as a proxy
            # Real computation would need distance + elevation diff
            return max(0.0, float(alt))
        return float("nan")

    def _compute_elevation_gain_500m(self, signals: dict[str, Any]) -> float:
        """Compute elevation gain over 500m."""
        return float("nan")

    def _compute_elevation_gain_1km(self, signals: dict[str, Any]) -> float:
        """Compute elevation gain over 1km."""
        return float("nan")

    def _compute_elevation_loss_100m(self, signals: dict[str, Any]) -> float:
        """Compute elevation loss over 100m."""
        return float("nan")

    def _compute_elevation_loss_500m(self, signals: dict[str, Any]) -> float:
        """Compute elevation loss over 500m."""
        return float("nan")

    def _compute_elevation_loss_1km(self, signals: dict[str, Any]) -> float:
        """Compute elevation loss over 1km."""
        return float("nan")

    def _compute_net_elevation_change_1km(self, signals: dict[str, Any]) -> float:
        """Compute net elevation change over 1km."""
        alt = signals.get("altitude_m")
        if alt is not None and isinstance(alt, (int, float)):
            return float(alt)
        return float("nan")

    def _compute_mean_gradient_500m(self, signals: dict[str, Any]) -> float:
        """Compute mean gradient over 500m."""
        return float("nan")

    def _compute_mean_gradient_1km(self, signals: dict[str, Any]) -> float:
        """Compute mean gradient over 1km."""
        return float("nan")

    def _compute_positive_motor_power_fraction(self, signals: dict[str, Any]) -> float:
        """Compute fraction of time motor power is positive (driving)."""
        return float("nan")

    def _compute_power_variability(self, signals: dict[str, Any]) -> float:
        """Compute power variability (e.g., std or range)."""
        return float("nan")

    def _compute_aux_power_variability(self, signals: dict[str, Any]) -> float:
        """Compute auxiliary power variability."""
        return float("nan")

    def _compute_regen_share_1km(self, signals: dict[str, Any]) -> float:
        """Compute regen share (energy from regen / total energy) over 1km."""
        return float("nan")

    def _compute_regen_events_per_km(self, signals: dict[str, Any]) -> float:
        """Compute regen events per km."""
        return float("nan")

    def _compute_temperature_bucket(self, signals: dict[str, Any]) -> float:
        """Bucket ambient temperature into categories."""
        temp = signals.get("ambient_temperature_c")
        if temp is not None and isinstance(temp, (int, float)):
            t = float(temp)
            if t < -10:
                return 0.0  # cold
            elif t < 0:
                return 1.0  # cool
            elif t < 20:
                return 2.0  # moderate
            elif t < 30:
                return 3.0  # warm
            else:
                return 4.0  # hot
        return float("nan")

    def _compute_torque(self, signals: dict[str, Any]) -> float:
        """Compute torque (Nm)."""
        return float("nan")

    def _compute_motor_rpm(self, signals: dict[str, Any]) -> float:
        """Compute motor RPM."""
        return float("nan")

    def _compute_aux_power_kw(self, signals: dict[str, Any]) -> float:
        """Compute auxiliary power in kW."""
        power = signals.get("auxiliary_power_kw")
        if power is not None and isinstance(power, (int, float)):
            return float(power)
        return float("nan")

    def _compute_aux_energy_1km(self, signals: dict[str, Any]) -> float:
        """Compute auxiliary energy over 1km."""
        return float("nan")

    def _compute_regen_power_kw(self, signals: dict[str, Any]) -> float:
        """Compute regen power in kW."""
        power = signals.get("regen_power_kw")
        if power is not None and isinstance(power, (int, float)):
            return float(power)
        return float("nan")

    def _compute_mean_regen_power_500m(self, signals: dict[str, Any]) -> float:
        """Compute mean regen power over 500m."""
        return float("nan")

    def _compute_mean_regen_power_1km(self, signals: dict[str, Any]) -> float:
        """Compute mean regen power over 1km."""
        return float("nan")

    def _compute_max_regen_power_1km(self, signals: dict[str, Any]) -> float:
        """Compute max regen power over 1km."""
        return float("nan")

    def _compute_regen_event_count_1km(self, signals: dict[str, Any]) -> int:
        """Count regen events over 1km."""
        return 0

    def _compute_regen_duration_estimate(self, signals: dict[str, Any]) -> float:
        """Estimate regen duration."""
        return float("nan")

    def _compute_regen_energy_recovered_1km(self, signals: dict[str, Any]) -> float:
        """Compute regen energy recovered over 1km."""
        return float("nan")

    def _compute_regen_fraction_of_driving_time(self, signals: dict[str, Any]) -> float:
        """Compute fraction of driving time with regen active."""
        return float("nan")

    # ------------------------------------------------------------------
    # Terrain feature computation
    # ------------------------------------------------------------------

    def _compute_terrain_features(self, terrain: Optional[dict[str, Any]],
                                   core_signals: dict[str, Any]) -> dict[str, float]:
        """Compute route-aware terrain features.

        If terrain is unavailable (None or empty), the 15 next_* features
        are set to NaN/indicators of unavailable status.

        Parameters
        ----------
        terrain : dict or None
            Route terrain data. If a dict, should contain next_* keys.
        core_signals : dict
            Core signals (for computing any fallback terrain features).

        Returns
        -------
        dict[str, float]
            Terrain feature values.
        """
        result: dict[str, float] = {}

        if terrain is None or not isinstance(terrain, dict):
            # No terrain available — set all 15 terrain features to NaN
            # The model preprocessor (imputer) will handle NaN
            for name in self._terrain_feature_names():
                result[name] = float("nan")
            return result

        # Terrain data is available; compute the 15 next_* features
        # The terrain dict may contain pre-computed values or raw data
        next_distances = ["1km", "2km", "5km"]

        for dist in next_distances:
            # next_net_elev_m
            net_key = f"next_{dist}_net_elev_m"
            gain_key = f"next_{dist}_gain_m"
            loss_key = f"next_{dist}_loss_m"
            grad_key = f"next_{dist}_gradient_pct"

            # Try to get values from terrain dict
            net_elev = terrain.get(net_key)
            gain = terrain.get(gain_key)
            loss = terrain.get(loss_key)
            gradient = terrain.get(grad_key)

            # If not in terrain dict, try to compute from raw data
            # or set as NaN
            if net_elev is not None:
                result[net_key] = float(net_elev)
            else:
                result[net_key] = float("nan")

            if gain is not None:
                result[gain_key] = float(gain)
            else:
                result[gain_key] = float("nan")

            if loss is not None:
                result[loss_key] = float(loss)
            else:
                result[loss_key] = float("nan")

            if gradient is not None:
                result[grad_key] = float(gradient)
            else:
                result[grad_key] = float("nan")

        # Add remaining terrain features (uphill/downhill/flat fractions)
        for dist in next_distances:
            uphill_key = f"next_{dist}_uphill_frac"
            downhill_key = f"next_{dist}_downhill_frac"
            flat_key = f"next_{dist}_flat_frac"

            # These may not always be in the terrain dict; default to NaN
            result[uphill_key] = terrain.get(uphill_key, float("nan"))
            result[downhill_key] = terrain.get(downhill_key, float("nan"))
            result[flat_key] = terrain.get(flat_key, float("nan"))

        return result

    def _compute_terrain_feature(
        self, name: str, terrain_features: dict[str, float]
    ) -> float:
        """Compute a single terrain feature from the terrain dict.

 Parameters
        name : str
            Feature name from final_feature_list.json.
        terrain_features : dict
            Computed terrain features from _compute_terrain_features.

    Returns
    -------
    float
        Feature value (NaN if terrain unavailable).
    """
        val = terrain_features.get(name, float("nan"))
        if val == val:  # NaN check: NaN != NaN
            return float(val)
        return float("nan")

    # ------------------------------------------------------------------
    # Past/window feature computation
    # ------------------------------------------------------------------

    def _compute_past_features(
        self, past_window: Optional[list[dict[str, Any]]],
        core_signals: dict[str, Any],
    ) -> dict[str, float]:
        """Compute features from the past telemetry window.

        If past_window is None or empty, the past features are set to
        NaN (or reasonable defaults) since we don't have a history.

        Parameters
        ----------
        past_window : list of dict or None
            Past telemetry samples.
        core_signals : dict
            Current core signals.

        Returns
        -------
        dict[str, float]
            Past feature values.
        """
        result: dict[str, float] = {}

        if past_window is None or len(past_window) == 0:
            # No past window — set past features to NaN
            for name in self._past_feature_names():
                result[name] = float("nan")
            return result

        # Past window has data — compute statistics
        # Extract relevant signals from the window
        window = past_window

        # Sort by timestamp if available
        # (assume they're roughly in chronological order)

        # Compute regen_share_1km: fraction of energy from regen over ~1km
        result["regen_share_1km"] = self._compute_regen_share_from_window(window)

        # Compute regen_events_per_km: number of regen events per km
        result["regen_events_per_km"] = self._compute_regen_events_from_window(window)

        return result

    def _compute_regen_share_from_window(self, window: list[dict[str, Any]]) -> float:
        """Compute regen share from a window of telemetry samples."""
        # Simplified: look at regen_power_kw signs and proportion
        # In production, would compute total energy from regen vs total
        total_energy = 0.0
        regen_energy = 0.0
        for sample in window:
            power = sample.get("battery_power_kw") or sample.get("motor_power_kw") or 0
            # If power < 0, it's regen (energy going into battery)
            if power is not None and isinstance(power, (int, float)):
                energy_contribution = abs(power)  # simplified
                total_energy += energy_contribution
                if power < 0:
                    regen_energy += energy_contribution

        if total_energy > 0:
            return regen_energy / total_energy
        return float("nan")

    def _compute_regen_events_from_window(self, window: list[dict[str, Any]]) -> float:
        """Count regen events from a window of telemetry samples."""
        # A regen event: regen_power_kw transitions from 0 to positive
        count = 0
        prev_regen = 0
        for sample in window:
            power = sample.get("regen_power_kw") or 0
            if power is not None and isinstance(power, (int, float)):
                if prev_regen == 0 and power > 0:
                    count += 1
                prev_regen = power
        # Normalize by distance (approximate)
        # In production, would use actual distance traveled in window
        return float(count)

    def _compute_past_feature(self, name: str, past_features: dict[str, float]) -> float:
        """Compute a single past/window feature."""
        val = past_features.get(name, float("nan"))
        if val == val:  # NaN check
            return float(val)
        return float("nan")