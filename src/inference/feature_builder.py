"""
STEP 11D - PRODUCTION FEATURE BUILDER.

Generates the exact 102 route-aware causal features required by the frozen
model, in the exact order of models/final_feature_list.json.

This module is a SINGLE-POINT / SNAPSHOT feature builder for production
inference. It differs from scripts.comprehensive_feature_engineering.engineer_trip
(which is training-oriented: it builds the target, computes next_* from the
full trip distance array, and drops rows whose target is NaN).

The builder requires:
  1. A telemetry snapshot at the prediction point (SOC, speed, altitude, temp,
     motor power/torque/rpm, aux power, regen power, timestamps, distance &
     time since trip start).
  2. A RouteTerrainProvider that supplies UPCOMING terrain (next 1/2/5 km).
     Route-aware features (next_*) are NEVER fabricated: if the provider
     cannot supply terrain, the builder raises FeatureBuildError.

CRITICAL CONTRACT:
  - The output DataFrame columns must EXACTLY equal
    models/final_feature_list.json, in the same order.
  - validate_feature_vector() detects missing/unexpected/misordered features,
    NaN/invalid values, and invalid units.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
MODELS = PROJECT_ROOT / "models"

GRADIENT_THRESHOLD_PCT = 1.0
HARD_ACCELERATION_MPS2 = 2.0
HARD_BRAKING_MPS2 = -2.0
WINDOWS = {"100m": 0.1, "500m": 0.5, "1km": 1.0}


class FeatureBuildError(ValueError):
    """Raised when a required feature cannot be produced from valid inputs."""


def _load_feature_list(models_dir: Path | None = None) -> list[str]:
    path = (models_dir or MODELS) / "final_feature_list.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _left_indices(distance: np.ndarray, width: float) -> np.ndarray:
    """Causal distance-window start indices (reproduces engineer_trip)."""
    indices = np.searchsorted(distance, distance - width, side="left")
    return np.minimum(indices, np.arange(len(distance)))


def _window_values(values: np.ndarray, left: np.ndarray, i: int) -> np.ndarray:
    return values[left[i]:i + 1][np.isfinite(values[left[i]:i + 1])]


def _stat(values: np.ndarray, func) -> float:
    return float(func(values)) if len(values) else np.nan


class RouteTerrain:
    """Upcoming elevation profile from a RouteTerrainProvider.

    Parameters:
        offsets_km: np.ndarray, distance offsets ahead of the prediction point
            (>= 0, sorted ascending). offset 0 == prediction point.
        altitudes_m: np.ndarray, elevation at each offset.
        source: string label describing how the terrain was obtained
            (e.g. 'DEM_STATIC', 'SYNTHETIC_DEMO'). Never 'FABRICATED'.
    """

    def __init__(self, offsets_km: np.ndarray, altitudes_m: np.ndarray,
                 source: str):
        offsets_km = np.asarray(offsets_km, dtype=float)
        altitudes_m = np.asarray(altitudes_m, dtype=float)
        if offsets_km.ndim != 1 or altitudes_m.ndim != 1:
            raise ValueError("offsets_km and altitudes_m must be 1-D arrays")
        if len(offsets_km) != len(altitudes_m):
            raise ValueError("offsets_km and altitudes_m must have equal length")
        if len(offsets_km) == 0:
            raise ValueError("terrain profile is empty")
        if not np.all(np.isfinite(offsets_km)) or not np.all(np.isfinite(altitudes_m)):
            raise ValueError("terrain profile contains non-finite values")
        order = np.argsort(offsets_km)
        self.offsets_km = offsets_km[order]
        self.altitudes_m = altitudes_m[order]
        if self.offsets_km[0] < -1e-9:
            raise ValueError("terrain offsets must be >= 0")
        self.source = source

    def elevation_at(self, offset_km: float) -> float:
        """Elevation at a specific forward offset (linear interp, clamped)."""
        off = float(offset_km)
        if off <= self.offsets_km[0]:
            return float(self.altitudes_m[0])
        if off >= self.offsets_km[-1]:
            return float(self.altitudes_m[-1])
        return float(np.interp(off, self.offsets_km, self.altitudes_m))


class RouteTerrainProvider:
    """Abstract provider of upcoming route terrain (STEP 11E).

    A production implementation connects a real GPS + DEM source. This base
    class intentionally has no DEM data; get_upcoming_terrain() raises
    NotImplementedError instead of fabricating terrain.
    """

    def __init__(self, *args, **kwargs):
        """Base initializer. Subclasses may take real DEM/GPS connectors."""
        super().__init__()

    def get_upcoming_terrain(self, current_distance_km: float,
                             current_altitude_m: float,
                             lookahead_km: float = 5.0) -> RouteTerrain:
        """Return the elevation profile for the next `lookahead_km`.

        Args:
            current_distance_km: cumulative trip distance at prediction point.
            current_altitude_m: current elevation (m).
            lookahead_km: horizon to cover (default 5.0).

        Returns:
            RouteTerrain with offsets in [0, lookahead_km] and altitudes in m.

        Raises:
            NotImplementedError: if no real DEM/GPS is connected.
        """
        raise NotImplementedError(
            "RouteTerrainProvider has no DEM/GPS backend connected; "
            "real route terrain is required for route-aware inference. "
            "Route-aware (next_*) features are never fabricated.")


class SyntheticRouteTerrainProvider(RouteTerrainProvider):
    """DEMO-ONLY provider used by tests and the API demo terrain flag.

    It returns a clearly-labeled SYNTHETIC elevation profile. It is NOT a real
    DEM; predictions produced with it must never be presented as real-world
    validation. The profile is a gentle sinusoidal hill (deterministic).
    """

    def __init__(self, base_altitude_m: float = 150.0,
                 amplitude_m: float = 25.0,
                 period_km: float = 3.0):
        super().__init__()
        self.base_altitude_m = float(base_altitude_m)
        self.amplitude_m = float(amplitude_m)
        self.period_km = float(period_km)

    def get_upcoming_terrain(self, current_distance_km: float,
                             current_altitude_m: float,
                             lookahead_km: float = 5.0) -> RouteTerrain:
        n = 51
        offsets = np.linspace(0.0, float(lookahead_km), n)
        alt = (self.base_altitude_m
               + self.amplitude_m
               * np.sin(2 * np.pi * offsets / self.period_km))
        # anchor offset 0 to the current altitude so gradients are consistent
        alt[0] = float(current_altitude_m)
        return RouteTerrain(offsets, alt, source="SYNTHETIC_DEMO")


class FeatureBuilder:
    """Build the exact 102-feature model-ready row for one prediction point."""

    def __init__(self, models_dir: Path | None = None):
        self.models_dir = models_dir or MODELS
        self.features = _load_feature_list(self.models_dir)

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _validate_snapshot(snapshot: dict) -> None:
        required = {
            "soc_pct", "speed_kmh", "altitude_m", "ambient_temperature_c",
            "distance_since_trip_start_km", "time_since_trip_start_min",
            "timestamp",
        }
        missing = required - set(snapshot.keys())
        if missing:
            raise FeatureBuildError(f"missing required telemetry: {sorted(missing)}")
        for key in ("soc_pct", "speed_kmh", "altitude_m", "ambient_temperature_c",
                    "distance_since_trip_start_km", "time_since_trip_start_min"):
            v = snapshot.get(key)
            if v is None or not math.isfinite(float(v)):
                raise FeatureBuildError(f"telemetry field {key} must be a finite number")

    @staticmethod
    def _terrain_features(route_terrain: RouteTerrain,
                          current_altitude_m: float) -> dict:
        """Compute the 15 route-aware next_* features from a terrain profile.

        Reproduces the Step 7.6 P10 formulas: net elevation change, gradient,
        gain, loss over the next 1/2/5 km, and uphill/downhill/flat fractions.
        """
        out = {}
        for width in (1.0, 2.0, 5.0):
            alt_f = route_terrain.elevation_at(width)
            denom = width * 1000.0
            out[f"next_{int(width)}km_net_elev_m"] = alt_f - current_altitude_m
            out[f"next_{int(width)}km_gradient_pct"] = (
                (alt_f - current_altitude_m) * 100.0 / denom)

            # gain/loss: integrate elevation deltas along the profile
            lo = route_terrain.offsets_km
            hi = route_terrain.altitudes_m
            mask = lo <= width
            seg = np.diff(hi[mask]) if mask.sum() > 1 else np.array([])
            out[f"next_{int(width)}km_gain_m"] = float(
                np.clip(seg, 0, None).sum()) if len(seg) else 0.0
            out[f"next_{int(width)}km_loss_m"] = float(
                -np.clip(seg, None, 0).sum()) if len(seg) else 0.0

        g5 = out["next_5km_gradient_pct"]
        out["next_5km_uphill_frac"] = float(g5 > GRADIENT_THRESHOLD_PCT)
        out["next_5km_downhill_frac"] = float(g5 < -GRADIENT_THRESHOLD_PCT)
        out["next_5km_flat_frac"] = float(
            1.0 - out["next_5km_uphill_frac"] - out["next_5km_downhill_frac"])
        return out

    # -------------------------------------------------------------- building
    def build_features(self, snapshot: dict,
                       route_terrain: RouteTerrain,
                       past: pd.DataFrame | None = None) -> pd.DataFrame:
        """Build a single-row DataFrame with exactly the 102 frozen features.

        Args:
            snapshot: dict of current telemetry:
                - soc_pct, battery_capacity_kwh, speed_kmh, altitude_m,
                  ambient_temperature_c, distance_since_trip_start_km,
                  time_since_trip_start_min, timestamp (datetime/str)
                - optional (NaN if absent): motor_power_kw, motor_torque_nm,
                  motor_rpm, aux_power_kw, regen_power_kw
            route_terrain: upcoming elevation profile (never fabricated).
            past: optional DataFrame of recent history (past_window) enabling
                causal past-window features. Columns: distance_km, altitude_m,
                speed_kmh, timestamp, optional motor/aux/regen/temperature.
                If None, past-window features are median-imputed by the frozen
                preprocessor.

        Returns:
            pd.DataFrame with one row, columns == final_feature_list order.
        """
        self._validate_snapshot(snapshot)
        if route_terrain is None:
            raise FeatureBuildError(
                "route terrain is required; route-aware next_* features cannot "
                "be fabricated")

        f = {}
        # -- snapshot scalars ------------------------------------------------
        soc = float(snapshot["soc_pct"])
        speed = float(snapshot["speed_kmh"])
        altitude = float(snapshot["altitude_m"])
        temp = float(snapshot["ambient_temperature_c"])
        dist = float(snapshot["distance_since_trip_start_km"])
        tmin = float(snapshot["time_since_trip_start_min"])
        ts = pd.to_datetime(snapshot["timestamp"], utc=True, errors="coerce")

        f["current_soc_pct"] = soc
        f["current_altitude_m"] = altitude
        f["current_speed_kmh"] = speed
        f["current_temperature_c"] = temp
        f["distance_since_trip_start_km"] = dist
        f["trip_distance_so_far_km"] = dist
        f["time_since_trip_start_min"] = tmin
        f["trip_elapsed_time_min"] = tmin
        if ts is None or pd.isna(ts):
            raise FeatureBuildError("timestamp must be a valid datetime")
        f["hour_of_day"] = float(ts.hour)
        f["day_of_week"] = float(ts.dayofweek)
        f["hour_sin"] = float(np.sin(2 * np.pi * ts.hour / 24.0))
        f["hour_cos"] = float(np.cos(2 * np.pi * ts.hour / 24.0))

        # -- gradient / past terrain (from altitude + distance history) ------
        # At a single point without a past trajectory, the causal past-window
        # features are undefined (no history). A production deploy passes a
        # short past window via snapshot['past_window'] if available; otherwise
        # these features are NaN and the frozen median imputer fills them.
        past = past if past is not None else snapshot.get("past_window")
        if past is not None and len(past) > 0:
            f.update(self._compute_past_window(past, speed, altitude))
        else:
            for name in self.features:
                if name not in f and self._is_past_window_feature(name):
                    f[name] = np.nan

        # -- current gradient from terrain profile ---------------------------
        cur_grad = route_terrain.elevation_at(0.1)  # 100 m look-ahead proxy
        f["current_gradient_pct"] = (
            (cur_grad - altitude) * 100.0 / 100.0)
        f["past_1km_gradient_pct"] = np.nan

        # -- motor / aux / regen (NaN-safe: imputer fills) -------------------
        def _nan(v):
            return np.nan if v is None else float(v)
        f["motor_power_kw"] = _nan(snapshot.get("motor_power_kw"))
        f["motor_rpm"] = _nan(snapshot.get("motor_rpm"))
        f["torque_nm"] = _nan(snapshot.get("motor_torque_nm"))
        f["aux_power_kw"] = _nan(snapshot.get("aux_power_kw"))
        f["regen_power_kw"] = _nan(snapshot.get("regen_power_kw"))
        f["speed_squared"] = speed ** 2
        f["speed_x_temperature"] = speed * temp
        f["speed_x_gradient"] = speed * f["current_gradient_pct"]
        f["acceleration_mps2"] = np.nan

        # -- route-aware next_* (REQUIRED, from provider) --------------------
        f.update(self._terrain_features(route_terrain, altitude))

        # -- assemble in exact order -----------------------------------------
        missing = [name for name in self.features if name not in f]
        if missing:
            raise FeatureBuildError(f"features not produced: {missing}")
        row = pd.DataFrame([{name: f[name] for name in self.features}])
        self.validate_feature_vector(row)
        return row

    @staticmethod
    def _is_past_window_feature(name: str) -> bool:
        return any(tok in name for tok in (
            "mean_speed", "speed_std", "min_speed", "max_speed",
            "high_speed_fraction", "stopped_fraction", "stop_count",
            "speed_change_recent", "mean_acceleration", "std_acceleration",
            "max_acceleration", "min_acceleration", "mean_pos_accel",
            "mean_neg_accel", "mean_motor_power", "max_motor_power",
            "mean_aux_power", "max_aux_power", "aux_power_variability",
            "aux_energy_1km", "mean_regen_power", "max_regen_power",
            "regen_event_count", "regen_duration", "regen_energy",
            "regen_fraction", "regen_intensity", "regen_share",
            "regen_events_per_km", "elevation_gain", "elevation_loss",
            "net_elevation_change", "mean_gradient", "gradient_std",
            "max_uphill_gradient", "max_downhill_gradient",
            "terrain_transition_count", "gradient_direction_changes",
            "terrain_variability", "hillyness_score", "uphill_fraction",
            "downhill_fraction", "flat_fraction", "elevation_gain_rate",
            "elevation_loss_rate", "positive_motor_power_fraction",
            "power_variability", "temperature_recent_mean",
            "speed_p10", "speed_p50", "speed_p90", "speed_iqr",
            "temperature_bucket",
        ))

    def _compute_past_window(self, past: pd.DataFrame, speed: float,
                             altitude: float) -> dict:
        """Compute causal past-window features from a short history frame.

        `past` must contain columns: distance_km (cumulative), altitude_m,
        speed_kmh, optionally motor_power_kw / aux_power_kw / regen_power_kw /
        ambient_temperature_c. This reproduces the engineer_trip formulas for
        the current point (last row).
        """
        past = past.sort_values("distance_km").reset_index(drop=True)
        d = pd.to_numeric(past["distance_km"], errors="coerce").to_numpy(float)
        d = np.where(np.isfinite(d), d, 0.0)
        alt = pd.to_numeric(past["altitude_m"], errors="coerce").to_numpy(float)
        n = len(past)
        left = {name: _left_indices(d, w) for name, w in WINDOWS.items()}
        out = {}
        i = n - 1
        # timestamps -> dt_s (needed for gain/loss rates and aux/regen energy)
        time_col = past.get("timestamp")
        if time_col is not None and not pd.isna(time_col).all():
            ts = pd.to_datetime(time_col, utc=True, errors="coerce")
            tsec = ts.astype("int64").to_numpy(float) / 1e9
            dt_s = np.r_[np.nan, np.diff(tsec)]
        else:
            dt_s = np.full(n, np.nan)
        dt_s[(dt_s <= 0) | (dt_s > 120)] = np.nan
        # gradients
        for name, li in left.items():
            delta_d_m = (d - d[li]) * 1000
            grad = np.divide((alt - alt[li]) * 100, delta_d_m,
                             out=np.zeros(n), where=delta_d_m >= 50)
            past[f"_gradient_{name}"] = grad
        grad = past["_gradient_100m"].to_numpy(float)
        out["current_gradient_pct"] = float(grad[i])
        out["past_1km_gradient_pct"] = float(past["_gradient_1km"].to_numpy(float)[i])
        for name, li in left.items():
            diffs = np.diff(alt[li[i]:i + 1])
            diffs = diffs[np.isfinite(diffs)]
            out[f"elevation_gain_{name}"] = float(np.clip(diffs, 0, None).sum())
            out[f"elevation_loss_{name}"] = float(-np.clip(diffs, None, 0).sum())
        out["net_elevation_change_1km"] = float(alt[i] - alt[left["1km"][i]])
        elapsed_s = np.nansum(dt_s) if np.isfinite(dt_s).any() else 0.0
        gain1 = out.get("elevation_gain_1km", np.nan)
        loss1 = out.get("elevation_loss_1km", np.nan)
        out["elevation_gain_rate"] = (float(gain1) / elapsed_s
                                      if elapsed_s > 0 and np.isfinite(gain1) else np.nan)
        out["elevation_loss_rate"] = (float(loss1) / elapsed_s
                                      if elapsed_s > 0 and np.isfinite(loss1) else np.nan)
        for name in ("500m", "1km"):
            vals = past[f"_gradient_{name}"].to_numpy(float); li = left[name]
            out[f"mean_gradient_{name}"] = _stat(_window_values(vals, li, i), np.mean)
            out[f"gradient_std_{name}"] = _stat(_window_values(vals, li, i), np.std)
        li1 = left["1km"]
        out["max_uphill_gradient"] = _stat(_window_values(grad, li1, i), np.max)
        out["max_downhill_gradient"] = _stat(_window_values(grad, li1, i), np.min)
        out["terrain_variability"] = _stat(_window_values(grad, li1, i), np.nanstd)
        out["terrain_transition_count_1km"] = _stat(
            _window_values(grad, li1, i), lambda v: int(np.count_nonzero(np.diff(np.sign(v)))))
        out["gradient_direction_changes_1km"] = _stat(
            _window_values(grad, li1, i),
            lambda v: int(np.count_nonzero(np.diff(v[np.abs(v) > GRADIENT_THRESHOLD_PCT]))))
        out["hillyness_score"] = (out["terrain_variability"]
                                  * (1 + out["gradient_direction_changes_1km"]))
        out["uphill_fraction_1km"] = _stat(
            _window_values(grad, li1, i), lambda v: np.mean(v > GRADIENT_THRESHOLD_PCT))
        out["downhill_fraction_1km"] = _stat(
            _window_values(grad, li1, i), lambda v: np.mean(v < -GRADIENT_THRESHOLD_PCT))
        u, dw = out["uphill_fraction_1km"], out["downhill_fraction_1km"]
        out["flat_fraction_1km"] = float(1.0 - (u if np.isfinite(u) else 0.0)
                                         - (dw if np.isfinite(dw) else 0.0))
        # speed-based windows
        speed_arr = pd.to_numeric(past["speed_kmh"], errors="coerce").to_numpy(float)
        li500 = left["500m"]
        for name in ("500m", "1km"):
            out[f"mean_speed_{name}"] = _stat(_window_values(speed_arr, left[name], i), np.mean)
            out[f"speed_std_{name}"] = _stat(_window_values(speed_arr, left[name], i), np.std)
        out["min_speed_recent"] = _stat(_window_values(speed_arr, li500, i), np.min)
        out["max_speed_recent"] = _stat(_window_values(speed_arr, li500, i), np.max)
        out["high_speed_fraction"] = _stat(
            _window_values(speed_arr, li1, i), lambda v: np.mean(v > 80))
        out["stopped_fraction"] = _stat(
            _window_values(speed_arr, li1, i), lambda v: np.mean(v < 1))
        out["stop_count_recent"] = _stat(
            _window_values(speed_arr, li1, i),
            lambda v: int(np.count_nonzero((v < 1) & np.r_[True, v[:-1] >= 1])))
        out["speed_change_recent"] = float(speed_arr[i] - speed_arr[li500[i]])
        # acceleration
        accel = np.divide(np.r_[np.nan, np.diff(speed_arr / 3.6)], dt_s,
                          out=np.full(n, np.nan), where=np.isfinite(dt_s))
        out["acceleration_mps2"] = float(accel[i]) if np.isfinite(accel[i]) else np.nan
        for stat, fun in [("mean", np.nanmean), ("std", np.nanstd),
                          ("max", np.nanmax), ("min", np.nanmin)]:
            out[f"{stat}_acceleration"] = _stat(_window_values(accel, li500, i), fun)
        out["mean_pos_accel"] = _stat(np.clip(_window_values(accel, li500, i), 0, None), np.nanmean)
        out["mean_neg_accel"] = _stat(np.clip(_window_values(accel, li500, i), None, 0), np.nanmean)
        # motor / aux / regen windows
        for col, prefix in [("motor_power_kw", "motor_power"),
                            ("aux_power_kw", "aux_power"),
                            ("regen_power_kw", "regen_power")]:
            if col in past.columns:
                v = pd.to_numeric(past[col], errors="coerce").to_numpy(float)
                out[f"mean_{prefix}_500m"] = _stat(_window_values(v, li500, i), np.mean)
                out[f"mean_{prefix}_1km"] = _stat(_window_values(v, li1, i), np.mean)
                out[f"max_{prefix}_1km"] = _stat(_window_values(v, li1, i), np.max)
            else:
                out[f"mean_{prefix}_500m"] = out[f"mean_{prefix}_1km"] = np.nan
                out[f"max_{prefix}_1km"] = np.nan
        if "motor_power_kw" in past.columns:
            mv = pd.to_numeric(past["motor_power_kw"], errors="coerce").to_numpy(float)
            out["positive_motor_power_fraction"] = _stat(
                _window_values(mv, li1, i), lambda v: np.mean(v > 0))
            out["power_variability"] = _stat(_window_values(mv, li1, i), np.std)
        else:
            out["positive_motor_power_fraction"] = out["power_variability"] = np.nan
        if "aux_power_kw" in past.columns:
            av = pd.to_numeric(past["aux_power_kw"], errors="coerce").to_numpy(float)
            out["aux_power_variability"] = _stat(_window_values(av, li1, i), np.std)
            out["aux_energy_1km"] = float(np.nansum(
                av[li1[i]:i + 1] * dt_s[li1[i]:i + 1] / 3600))
        else:
            out["aux_power_variability"] = out["aux_energy_1km"] = np.nan
        if "regen_power_kw" in past.columns:
            rv = pd.to_numeric(past["regen_power_kw"], errors="coerce").to_numpy(float)
            out["max_regen_power_1km"] = _stat(_window_values(rv, li1, i), np.min)
            out["regen_event_count_1km"] = _stat(
                _window_values(rv, li1, i),
                lambda v: int(np.count_nonzero(np.diff((v < 0).astype(int)) == 1)))
            out["regen_duration_estimate"] = float(np.nansum(
                dt_s[li1[i]:i + 1][rv[li1[i]:i + 1] < 0]))
            p = rv[li1[i]:i + 1]; dt = dt_s[li1[i]:i + 1]
            valid = np.isfinite(p) & np.isfinite(dt) & (dt > 0) & (dt <= 120) & (p < 0)
            out["regen_energy_recovered_1km"] = float(
                (-p[valid] * dt[valid] / 3600).sum()) if valid.any() else np.nan
            elapsed = np.nansum(dt_s[li1[i]:i + 1])
            out["regen_fraction_of_driving_time"] = (
                out["regen_duration_estimate"] / elapsed if elapsed > 0 else np.nan)
            dist_covered = d[i] - d[li1[i]]
            out["regen_intensity"] = (
                out["regen_energy_recovered_1km"] / dist_covered
                if dist_covered > 0 else np.nan)
            traction = np.where(np.isfinite(mv), np.maximum(mv, 0), 0.0) + 0.0
            reg_abs = np.where(np.isfinite(rv), np.maximum(-rv, 0), 0.0)
            denom = np.nansum(traction[li1[i]:i + 1] * dt_s[li1[i]:i + 1])
            out["regen_share_1km"] = (np.nansum(reg_abs[li1[i]:i + 1] * dt_s[li1[i]:i + 1]) / denom
                                      if denom > 0 else np.nan)
            out["regen_events_per_km"] = (out["regen_event_count_1km"]
                                          / max(d[i] - d[li1[i]], 1e-9))
        else:
            for k in ("max_regen_power_1km", "regen_event_count_1km",
                      "regen_duration_estimate", "regen_energy_recovered_1km",
                      "regen_fraction_of_driving_time", "regen_intensity",
                      "regen_share_1km", "regen_events_per_km"):
                out[k] = np.nan
        # temperature + speed percentiles
        if "ambient_temperature_c" in past.columns:
            tv = pd.to_numeric(past["ambient_temperature_c"], errors="coerce").to_numpy(float)
            out["temperature_recent_mean"] = _stat(_window_values(tv, li500, i), np.mean)
        else:
            out["temperature_recent_mean"] = np.nan
        out["speed_p10"] = np.nanpercentile(speed_arr[max(0, i - 20):i + 1], 10)
        out["speed_p50"] = np.nanpercentile(speed_arr[max(0, i - 20):i + 1], 50)
        out["speed_p90"] = np.nanpercentile(speed_arr[max(0, i - 20):i + 1], 90)
        out["speed_iqr"] = out["speed_p90"] - out["speed_p10"]
        out["temperature_bucket"] = np.floor(
            np.nanmean(_window_values(
                pd.to_numeric(past["ambient_temperature_c"], errors="coerce").to_numpy(float),
                li500, i)) / 5.0) * 5.0 if "ambient_temperature_c" in past.columns else np.nan
        return out

    # ------------------------------------------------------------ validation
    def validate_feature_vector(self, df: pd.DataFrame) -> None:
        """Validate a model-ready feature DataFrame.

        Detects:
          - missing features (columns absent from final_feature_list)
          - unexpected features (columns not in final_feature_list)
          - wrong ordering
          - NaN/invalid values in any column
          - invalid units (range checks for known physical fields)
        """
        expected = self.features
        actual = list(df.columns)
        if set(actual) != set(expected):
            missing = sorted(set(expected) - set(actual))
            unexpected = sorted(set(actual) - set(expected))
            raise FeatureBuildError(
                f"feature set mismatch: missing={missing}, unexpected={unexpected}")
        if actual != expected:
            raise FeatureBuildError("feature ordering does not match final_feature_list.json")
        if df.shape[0] == 0:
            raise FeatureBuildError("feature vector is empty")

        data = df.to_dict(orient="records")[0]
        # Critical features that must NEVER be NaN: the model is route-aware,
        # so every next_* feature and every required scalar telemetry feature
        # must be present. Imputable telemetry features (motor/aux/regen and
        # windowed features over them) may be NaN pre-imputation and are filled
        # by the frozen median imputer.
        critical = {
            "current_soc_pct", "current_altitude_m", "current_speed_kmh",
            "current_temperature_c", "distance_since_trip_start_km",
            "trip_distance_so_far_km", "time_since_trip_start_min",
            "trip_elapsed_time_min", "hour_of_day", "day_of_week",
            "hour_sin", "hour_cos", "speed_squared", "speed_x_temperature",
        }
        critical |= {name for name in expected if name.startswith("next_")}
        for name in expected:
            v = data.get(name)
            if v is None:
                raise FeatureBuildError(f"feature {name} is None")
            if isinstance(v, (int, float)) and math.isnan(float(v)):
                if name in critical:
                    raise FeatureBuildError(
                        f"critical feature {name} is NaN; route terrain or "
                        f"required telemetry is missing")

        # unit / physical-range sanity checks (NaN skipped -> imputed later)
        range_checks = {
            "current_soc_pct": (0.0, 100.0),
            "hour_of_day": (0.0, 24.0),
            "day_of_week": (0.0, 6.0),
            "hour_sin": (-1.0, 1.0),
            "hour_cos": (-1.0, 1.0),
            "current_speed_kmh": (0.0, 400.0),
            "current_temperature_c": (-60.0, 80.0),
            "next_5km_uphill_frac": (0.0, 1.0),
            "next_5km_downhill_frac": (0.0, 1.0),
            "next_5km_flat_frac": (0.0, 1.0),
        }
        for name, (lo, hi) in range_checks.items():
            v = float(data[name])
            if math.isnan(v):
                continue
            if v < lo - 1e-9 or v > hi + 1e-9:
                raise FeatureBuildError(
                    f"feature {name} out of valid range [{lo}, {hi}]: {v}")


def build_demo_snapshot() -> dict:
    """Return a clearly-labeled DEMO telemetry snapshot (no real telemetry)."""
    return {
        "vehicle_id": "DEMO-VEHICLE",
        "timestamp": "2026-08-16T10:30:00Z",
        "soc_pct": 80.0,
        "battery_capacity_kwh": 40.0,
        "speed_kmh": 65.0,
        "altitude_m": 150.0,
        "ambient_temperature_c": 18.0,
        "distance_since_trip_start_km": 12.0,
        "time_since_trip_start_min": 20.0,
        "motor_power_kw": 12.0,
        "motor_rpm": 4200.0,
        "motor_torque_nm": 60.0,
        "aux_power_kw": 0.6,
        "regen_power_kw": -1.0,
        "demo": True,
    }


if __name__ == "__main__":
    from src.inference.feature_builder import SyntheticRouteTerrainProvider
    builder = FeatureBuilder()
    snap = build_demo_snapshot()
    provider = SyntheticRouteTerrainProvider()
    terrain = provider.get_upcoming_terrain(snap["distance_since_trip_start_km"],
                                            snap["altitude_m"])
    row = builder.build_features(snap, terrain)
    print("features:", row.shape[1], "| expected:", len(builder.features))
    print("order OK:", list(row.columns) == builder.features)
    print(row.iloc[0][["current_speed_kmh", "next_5km_gradient_pct",
                       "next_5km_uphill_frac", "next_5km_flat_frac"]].to_dict())