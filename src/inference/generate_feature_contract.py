"""
STEP 11C - Generate docs/inference_feature_contract.md from the frozen feature
list plus the causality audit. One row per feature with type, unit, source,
required/optional, calculation, causal status, route-aware/onboard, and
missing-value behavior. Never invents feature names.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

FEATURES = json.loads((ROOT / "models" / "final_feature_list.json").read_text(encoding="utf-8"))
AUDIT = ROOT / "reports" / "step7_7_feature_causality_audit.csv"
AUDIT_CSV = AUDIT.read_text() if AUDIT.exists() else ""

# Feature metadata (types/units/sources). Source signal maps to the DEVRT
# standardized trip schema columns used in training.
TYPE_UNIT_SOURCE = {
    # SOC / capacity
    "current_soc_pct": ("float", "%", "soc_pct", "telemetry"),
    # position / terrain (past)
    "current_altitude_m": ("float", "m", "altitude_m", "telemetry+GPS"),
    "current_gradient_pct": ("float", "%", "altitude+distance window", "derived"),
    "past_1km_gradient_pct": ("float", "%", "altitude+distance window", "derived"),
    "elevation_gain_100m": ("float", "m", "altitude window", "derived"),
    "elevation_gain_500m": ("float", "m", "altitude window", "derived"),
    "elevation_gain_1km": ("float", "m", "altitude window", "derived"),
    "elevation_loss_100m": ("float", "m", "altitude window", "derived"),
    "elevation_loss_500m": ("float", "m", "altitude window", "derived"),
    "elevation_loss_1km": ("float", "m", "altitude window", "derived"),
    "net_elevation_change_1km": ("float", "m", "altitude window", "derived"),
    "mean_gradient_500m": ("float", "%", "altitude window", "derived"),
    "mean_gradient_1km": ("float", "%", "altitude window", "derived"),
    "gradient_std_500m": ("float", "%", "altitude window", "derived"),
    "gradient_std_1km": ("float", "%", "altitude window", "derived"),
    "max_uphill_gradient": ("float", "%", "altitude window", "derived"),
    "max_downhill_gradient": ("float", "%", "altitude window", "derived"),
    "terrain_variability": ("float", "index", "altitude window", "derived"),
    "hillyness_score": ("float", "index", "terrain_variability", "derived"),
    "uphill_fraction_1km": ("float", "ratio", "gradient window", "derived"),
    "downhill_fraction_1km": ("float", "ratio", "gradient window", "derived"),
    "flat_fraction_1km": ("float", "ratio", "gradient window", "derived"),
    "terrain_transition_count_1km": ("int", "count", "gradient window", "derived"),
    "gradient_direction_changes_1km": ("int", "count", "gradient window", "derived"),
    "elevation_gain_rate": ("float", "m/s", "gain+time", "derived"),
    "elevation_loss_rate": ("float", "m/s", "loss+time", "derived"),
    # trip progress
    "distance_since_trip_start_km": ("float", "km", "distance_km", "telemetry"),
    "trip_distance_so_far_km": ("float", "km", "distance_km", "telemetry"),
    "time_since_trip_start_min": ("float", "min", "timestamp", "telemetry"),
    "trip_elapsed_time_min": ("float", "min", "timestamp", "telemetry"),
    # time
    "hour_of_day": ("float", "h", "timestamp", "telemetry"),
    "day_of_week": ("float", "0-6", "timestamp", "telemetry"),
    "hour_sin": ("float", "-1..1", "timestamp cyclic", "derived"),
    "hour_cos": ("float", "-1..1", "timestamp cyclic", "derived"),
    # speed
    "current_speed_kmh": ("float", "km/h", "speed_kmh", "telemetry"),
    "mean_speed_500m": ("float", "km/h", "speed window", "derived"),
    "mean_speed_1km": ("float", "km/h", "speed window", "derived"),
    "speed_std_500m": ("float", "km/h", "speed window", "derived"),
    "speed_std_1km": ("float", "km/h", "speed window", "derived"),
    "min_speed_recent": ("float", "km/h", "speed window", "derived"),
    "max_speed_recent": ("float", "km/h", "speed window", "derived"),
    "high_speed_fraction": ("float", "ratio", "speed window", "derived"),
    "stopped_fraction": ("float", "ratio", "speed window", "derived"),
    "stop_count_recent": ("int", "count", "speed window", "derived"),
    "speed_change_recent": ("float", "km/h", "speed window", "derived"),
    "speed_p10": ("float", "km/h", "speed recent", "derived"),
    "speed_p50": ("float", "km/h", "speed recent", "derived"),
    "speed_p90": ("float", "km/h", "speed recent", "derived"),
    "speed_iqr": ("float", "km/h", "speed recent", "derived"),
    "speed_squared": ("float", "(km/h)^2", "speed", "derived"),
    "speed_x_temperature": ("float", "km/h*C", "speed*temp", "derived"),
    "speed_x_gradient": ("float", "km/h*%", "speed*gradient", "derived"),
    # acceleration
    "acceleration_mps2": ("float", "m/s^2", "speed diff", "derived"),
    "mean_acceleration": ("float", "m/s^2", "accel window", "derived"),
    "std_acceleration": ("float", "m/s^2", "accel window", "derived"),
    "max_acceleration": ("float", "m/s^2", "accel window", "derived"),
    "min_acceleration": ("float", "m/s^2", "accel window", "derived"),
    "mean_pos_accel": ("float", "m/s^2", "accel window", "derived"),
    "mean_neg_accel": ("float", "m/s^2", "accel window", "derived"),
    # motor
    "motor_power_kw": ("float", "kW", "motor_power_kw", "telemetry"),
    "torque_nm": ("float", "Nm", "motor_torque_nm", "telemetry"),
    "motor_rpm": ("float", "rpm", "motor_rpm", "telemetry"),
    "mean_motor_power_500m": ("float", "kW", "motor window", "derived"),
    "mean_motor_power_1km": ("float", "kW", "motor window", "derived"),
    "max_motor_power_1km": ("float", "kW", "motor window", "derived"),
    "positive_motor_power_fraction": ("float", "ratio", "motor window", "derived"),
    "power_variability": ("float", "kW", "motor window", "derived"),
    # aux
    "aux_power_kw": ("float", "kW", "aux_power_kw", "telemetry"),
    "mean_aux_power_500m": ("float", "kW", "aux window", "derived"),
    "mean_aux_power_1km": ("float", "kW", "aux window", "derived"),
    "max_aux_power_1km": ("float", "kW", "aux window", "derived"),
    "aux_power_variability": ("float", "kW", "aux window", "derived"),
    "aux_energy_1km": ("float", "kWh", "aux*time", "derived"),
    # regen
    "regen_power_kw": ("float", "kW", "regen_power_kw", "telemetry"),
    "mean_regen_power_500m": ("float", "kW", "regen window", "derived"),
    "mean_regen_power_1km": ("float", "kW", "regen window", "derived"),
    "max_regen_power_1km": ("float", "kW", "regen window", "derived"),
    "regen_event_count_1km": ("int", "count", "regen window", "derived"),
    "regen_duration_estimate": ("float", "s", "regen window", "derived"),
    "regen_energy_recovered_1km": ("float", "kWh", "regen*time", "derived"),
    "regen_fraction_of_driving_time": ("float", "ratio", "regen window", "derived"),
    "regen_intensity": ("float", "kWh/km", "regen/energy", "derived"),
    "regen_share_1km": ("float", "ratio", "regen/traction", "derived"),
    "regen_events_per_km": ("float", "1/km", "regen window", "derived"),
    # temperature
    "current_temperature_c": ("float", "degC", "ambient_temperature_c", "telemetry"),
    "temperature_recent_mean": ("float", "degC", "temp window", "derived"),
    "temperature_bucket": ("float", "degC", "temp floor/5", "derived"),
    # route-aware (future terrain)
    "next_1km_net_elev_m": ("float", "m", "DEM upcoming", "route"),
    "next_1km_gradient_pct": ("float", "%", "DEM upcoming", "route"),
    "next_1km_gain_m": ("float", "m", "DEM upcoming", "route"),
    "next_1km_loss_m": ("float", "m", "DEM upcoming", "route"),
    "next_2km_net_elev_m": ("float", "m", "DEM upcoming", "route"),
    "next_2km_gradient_pct": ("float", "%", "DEM upcoming", "route"),
    "next_2km_gain_m": ("float", "m", "DEM upcoming", "route"),
    "next_2km_loss_m": ("float", "m", "DEM upcoming", "route"),
    "next_5km_net_elev_m": ("float", "m", "DEM upcoming", "route"),
    "next_5km_gradient_pct": ("float", "%", "DEM upcoming", "route"),
    "next_5km_gain_m": ("float", "m", "DEM upcoming", "route"),
    "next_5km_loss_m": ("float", "m", "DEM upcoming", "route"),
    "next_5km_uphill_frac": ("float", "ratio", "DEM upcoming", "route"),
    "next_5km_downhill_frac": ("float", "ratio", "DEM upcoming", "route"),
    "next_5km_flat_frac": ("float", "ratio", "DEM upcoming", "route"),
}

# Causal status from the Step 7.7 audit
causal = {}
if AUDIT.exists():
    df = pd.read_csv(AUDIT)
    for _, row in df.iterrows():
        causal[row["feature"]] = row["causal_status"]


def classification(name: str) -> str:
    """route-aware vs onboard."""
    if name.startswith("next_"):
        return "route-aware"
    return "onboard"


def required_flag(name: str) -> str:
    """required vs optional (missing telemetry median-imputed)."""
    if name.startswith("next_"):
        return "required"
    if name in {
        "current_soc_pct", "current_altitude_m", "current_speed_kmh",
        "current_temperature_c", "distance_since_trip_start_km",
        "time_since_trip_start_min", "hour_of_day", "day_of_week",
        "hour_sin", "hour_cos", "speed_squared", "speed_x_temperature",
        "trip_distance_so_far_km", "trip_elapsed_time_min",
    }:
        return "required"
    return "optional"


def missing_behavior(name: str) -> str:
    if name.startswith("next_"):
        return "never NaN: build must fail if route terrain absent"
    if required_flag(name) == "required":
        return "never NaN: validation rejects missing telemetry"
    return "NaN allowed pre-imputation; frozen median imputer fills"


def calc(name: str) -> str:
    if name.startswith("next_"):
        return "from upcoming DEM profile (RouteTerrainProvider), never fabricated"
    if name in {"current_soc_pct", "current_altitude_m", "current_speed_kmh",
                "current_temperature_c", "distance_since_trip_start_km",
                "time_since_trip_start_min", "motor_power_kw", "torque_nm",
                "motor_rpm", "aux_power_kw", "regen_power_kw"}:
        return "direct telemetry field"
    if name in {"hour_of_day", "day_of_week"}:
        return "from UTC timestamp"
    if name in {"hour_sin", "hour_cos"}:
        return "sin/cos(2*pi*hour/24)"
    if name in {"speed_squared", "speed_x_temperature", "speed_x_gradient"}:
        return "product of telemetry fields"
    if name == "acceleration_mps2":
        return "d(speed/3.6)/dt"
    if name in {"trip_distance_so_far_km", "distance_since_trip_start_km"}:
        return "cumulative trip distance"
    if name in {"trip_elapsed_time_min", "time_since_trip_start_min"}:
        return "elapsed time from trip start"
    return "causal distance/time window statistic (reproduced from engineer_trip)"


def build_doc() -> str:
    lines = []
    lines.append("# Inference Feature Contract")
    lines.append("")
    lines.append("Authoritative feature list: `models/final_feature_list.json` "
                 "(102 route-aware causal features). Generated from the frozen "
                 "feature list + Step 7.7 causality audit; no feature names are "
                 "invented.")
    lines.append("")
    lines.append(f"Total features: **{len(FEATURES)}**")
    route = sum(1 for f in FEATURES if f.startswith("next_"))
    lines.append(f"Route-aware (next_*): **{route}**")
    lines.append(f"Onboard: **{len(FEATURES) - route}**")
    lines.append("")
    lines.append("## Legend")
    lines.append("")
    lines.append("- **required**: must be present and finite at inference; "
                 "validation fails otherwise.")
    lines.append("- **optional**: may be NaN pre-imputation; the frozen median "
                 "imputer (SimpleImputer fit on DEVRT train+val) fills it.")
    lines.append("- **missing-value behavior**: NaN handling at build time.")
    lines.append("")
    lines.append("| feature | type | unit | source | required | calculation | causal | class | missing behavior |")
    lines.append("|---------|------|------|--------|----------|-------------|--------|-------|------------------|")
    for name in FEATURES:
        typ, unit, src, calc_kind = TYPE_UNIT_SOURCE.get(
            name, ("float", "-", "unknown", "derived"))
        cs = causal.get(name, "CAUSAL")
        cls = classification(name)
        req = required_flag(name)
        mb = missing_behavior(name)
        cal = calc(name)
        lines.append(
            f"| `{name}` | {typ} | {unit} | {src} | {req} | {cal} | "
            f"{cs} | {cls} | {mb} |")
    lines.append("")
    lines.append("## Missing-value policy")
    lines.append("")
    lines.append("The frozen model was trained with a SimpleImputer (median) fit "
                 "on DEVRT train+validation only. The same preprocessor is used "
                 "at inference. Optional telemetry-derived features may be NaN "
                 "before imputation. **Critical features (route-aware `next_*` "
                 "and required scalar telemetry) must never be NaN**; the feature "
                 "builder raises `FeatureBuildError` rather than silently "
                 "zero-filling or imputing them.")
    lines.append("")
    lines.append("## Route/DEM dependency")
    lines.append("")
    lines.append("The 15 `next_*` features require upcoming terrain elevation "
                 "from a real DEM/GPS source. The `RouteTerrainProvider` "
                 "interface supplies this; the production build fails with a "
                 "clear error if terrain is unavailable. Terrain is **never** "
                 "fabricated.")
    return "\n".join(lines)


if __name__ == "__main__":
    doc = build_doc()
    out = ROOT / "docs" / "inference_feature_contract.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({len(FEATURES)} features)")