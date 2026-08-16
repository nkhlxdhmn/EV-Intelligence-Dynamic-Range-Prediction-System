"""Leakage-safe, memory-bounded DEVRT feature engineering for Step 7.5.

The input trips are read and written one at a time.  Every window ends at the
current row; distance windows include observations in ``[t-window, t]``.
"""
from __future__ import annotations

import gc
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from data.devrt_parser import timestamp_to_epoch_seconds

INPUT_DIR = Path("data/interim/devrt")
OUTPUT = Path("data/processed/devrt_ml_features_v2.parquet")
TARGET = "target_future_energy_kwh_per_km"
WINDOWS = {"100m": 0.1, "500m": 0.5, "1km": 1.0}
GRADIENT_THRESHOLD_PCT = 1.0
HARD_ACCELERATION_MPS2 = 2.0
HARD_BRAKING_MPS2 = -2.0

COMMON_FEATURES = [
    "current_soc_pct", "current_soh_pct", "battery_capacity_kwh",
    "current_altitude_m", "current_gradient_pct", "past_1km_gradient_pct",
    "terrain_class", "elevation_gain_100m", "elevation_gain_500m",
    "elevation_gain_1km", "elevation_loss_100m", "elevation_loss_500m",
    "elevation_loss_1km", "net_elevation_change_1km", "mean_gradient_500m",
    "mean_gradient_1km", "gradient_std_500m", "gradient_std_1km",
    "max_uphill_gradient", "max_downhill_gradient", "terrain_variability",
    "hillyness_score", "uphill_fraction_1km", "downhill_fraction_1km",
    "flat_fraction_1km", "terrain_transition_count_1km",
    "gradient_direction_changes_1km", "elevation_gain_rate",
    "elevation_loss_rate", "distance_since_trip_start_km",
    "time_since_trip_start_min", "trip_distance_so_far_km", "trip_elapsed_time_min",
]
OPTIONAL_NISSAN_FEATURES = [
    "current_speed_kmh", "mean_speed_100m", "mean_speed_500m", "mean_speed_1km",
    "speed_std_500m", "speed_std_1km", "min_speed_recent", "max_speed_recent",
    "high_speed_fraction", "stopped_fraction", "stop_count_recent", "speed_change_recent",
    "acceleration_mps2", "mean_acceleration", "std_acceleration", "max_acceleration",
    "min_acceleration", "hard_acceleration_count", "hard_braking_count",
    "acceleration_variability", "motor_power_kw", "torque_nm", "motor_rpm",
    "mean_motor_power_500m", "mean_motor_power_1km", "max_motor_power_1km",
    "motor_power_std_1km", "positive_motor_power_fraction", "power_variability",
    "aux_power_kw", "mean_aux_power_500m", "mean_aux_power_1km", "max_aux_power_1km",
    "aux_power_variability", "aux_energy_1km", "regen_power_kw", "mean_regen_power_500m",
    "mean_regen_power_1km", "max_regen_power_1km", "regen_event_count_1km",
    "regen_duration_estimate", "regen_energy_recovered_1km", "regen_fraction_of_driving_time",
    "regen_intensity", "current_temperature_c", "temperature_deviation_from_reference",
    "temperature_recent_mean", "temperature_recent_std", "speed_x_gradient",
    "speed_squared", "speed_x_temperature",
]
AVAILABILITY_FLAGS = ["has_speed_data", "has_motor_power", "has_aux_power", "has_regen_power", "has_temperature"]
EXPERIMENT_GROUPS = {
    "EXPERIMENT_A_BASIC": ["current_soc_pct", "current_soh_pct", "battery_capacity_kwh", "current_altitude_m", "past_1km_gradient_pct"],
    "EXPERIMENT_B_DRIVING": COMMON_FEATURES + [x for x in OPTIONAL_NISSAN_FEATURES if "speed" in x or "acceleration" in x or x in {"stopped_fraction", "stop_count_recent"}],
    "EXPERIMENT_C_POWERTRAIN": COMMON_FEATURES + OPTIONAL_NISSAN_FEATURES[:45],
    "EXPERIMENT_D_ENVIRONMENT": COMMON_FEATURES + OPTIONAL_NISSAN_FEATURES,
    "EXPERIMENT_E_FULL": COMMON_FEATURES + OPTIONAL_NISSAN_FEATURES + AVAILABILITY_FLAGS,
}

def _process_memory_mb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1048576
    except ImportError:
        return float("nan")

def _left_indices(distance: np.ndarray, width: float) -> np.ndarray:
    indices = np.searchsorted(distance, distance - width, side="left")
    # Legacy data can contain a short out-of-order tail after missing timestamps.
    # A causal window may never start after its current observation.
    return np.minimum(indices, np.arange(len(distance)))

def _window_values(values: np.ndarray, left: np.ndarray, i: int) -> np.ndarray:
    return values[left[i]:i + 1][np.isfinite(values[left[i]:i + 1])]

def _stat(values: np.ndarray, func) -> float:
    return float(func(values)) if len(values) else np.nan

def _integrated_positive_energy(power_kw: np.ndarray, dt_s: np.ndarray, left: np.ndarray, i: int) -> float:
    # Regen is negative power; recovered energy is reported as positive kWh.
    p, dt = power_kw[left[i]:i + 1], dt_s[left[i]:i + 1]
    valid = np.isfinite(p) & np.isfinite(dt) & (dt > 0) & (dt <= 120) & (p < 0)
    return float((-p[valid] * dt[valid] / 3600).sum()) if valid.any() else np.nan

def _target(distance: np.ndarray, soc: np.ndarray, capacity: np.ndarray) -> np.ndarray:
    result = np.full(len(distance), np.nan)
    for i, start in enumerate(distance):
        j = np.searchsorted(distance, start + 5.0, side="left")
        if j < len(distance) and distance[j] - start >= 4.5 and np.isfinite(soc[i]) and np.isfinite(soc[j]) and np.isfinite(capacity[i]):
            result[i] = (soc[i] - soc[j]) * capacity[i] / 100 / (distance[j] - start)
    return result

def engineer_trip(df: pd.DataFrame) -> pd.DataFrame:
    """Create causal features for one already-standardized trip."""
    # Match the established target construction order from Step 6.  NaT values
    # sort last; within equal timestamps stable source order is retained.
    df = df.sort_values(["timestamp", "source_row_id"], kind="stable", na_position="last").reset_index(drop=True).copy()
    d = pd.to_numeric(df.distance_km, errors="coerce").to_numpy(float)
    # Keep the existing Step 6 distance sequence unchanged so v2 retains the
    # established target population.  The standardized DEVRT distance signal
    # is cumulative within each trip.
    d = np.where(np.isfinite(d), d, 0.0)
    altitude = pd.to_numeric(df.altitude_m, errors="coerce").to_numpy(float)
    n = len(df)
    left = {name: _left_indices(d, width) for name, width in WINDOWS.items()}
    for name, li in left.items():
        delta_d_m = (d - d[li]) * 1000
        gradient = np.divide((altitude - altitude[li]) * 100, delta_d_m, out=np.zeros(n), where=delta_d_m >= 50)
        df[f"_gradient_{name}"] = gradient
    grad = df._gradient_100m.to_numpy(float)
    df["current_gradient_pct"] = grad
    df["past_1km_gradient_pct"] = df._gradient_1km
    df["terrain_class"] = np.select([grad > GRADIENT_THRESHOLD_PCT, grad < -GRADIENT_THRESHOLD_PCT], ["UPHILL", "DOWNHILL"], default="FLAT")
    df["current_soc_pct"] = df.soc_pct
    df["current_soh_pct"] = df.soh_pct
    df["current_altitude_m"] = df.altitude_m
    df["vehicle_model"] = "Dacia Spring" if "DACIA" in str(df.trip_id.iloc[0]).upper() else "Nissan Leaf"
    df["distance_since_trip_start_km"] = d - d[0]
    df["trip_distance_so_far_km"] = df.distance_since_trip_start_km
    timestamps = pd.to_datetime(df.timestamp, utc=True, errors="coerce")
    time_s = timestamp_to_epoch_seconds(timestamps)
    time_s[timestamps.isna().to_numpy()] = np.nan
    valid_time = np.isfinite(time_s)
    origin = time_s[valid_time][0] if valid_time.any() else np.nan
    df["time_since_trip_start_min"] = (time_s - origin) / 60
    df["trip_elapsed_time_min"] = df.time_since_trip_start_min
    dt_s = np.r_[np.nan, np.diff(time_s)]
    dt_s[(dt_s <= 0) | (dt_s > 120)] = np.nan
    for name, li in left.items():
        gain = np.zeros(n); loss = np.zeros(n)
        for i in range(n):
            diffs = np.diff(altitude[li[i]:i + 1]); diffs = diffs[np.isfinite(diffs)]
            gain[i], loss[i] = np.clip(diffs, 0, None).sum(), -np.clip(diffs, None, 0).sum()
        df[f"elevation_gain_{name}"] = gain
        df[f"elevation_loss_{name}"] = loss
    df["net_elevation_change_1km"] = altitude - altitude[left["1km"]]
    for name in ("500m", "1km"):
        vals = df[f"_gradient_{name}"].to_numpy(float); li = left[name]
        df[f"mean_gradient_{name}"] = [_stat(_window_values(vals, li, i), np.mean) for i in range(n)]
        df[f"gradient_std_{name}"] = [_stat(_window_values(vals, li, i), np.std) for i in range(n)]
    li1 = left["1km"]
    df["max_uphill_gradient"] = [_stat(_window_values(grad, li1, i), np.max) for i in range(n)]
    df["max_downhill_gradient"] = [_stat(_window_values(grad, li1, i), np.min) for i in range(n)]
    terrain_code = np.sign(grad); terrain_code[np.abs(grad) <= GRADIENT_THRESHOLD_PCT] = 0
    transitions=[]; direction_changes=[]; variability=[]
    for i in range(n):
        w = terrain_code[li1[i]:i+1]; nonflat=w[w != 0]
        transitions.append(int(np.count_nonzero(np.diff(w))))
        direction_changes.append(int(np.count_nonzero(np.diff(nonflat))))
        variability.append(float(np.nanstd(grad[li1[i]:i+1])))
    df["terrain_transition_count_1km"], df["gradient_direction_changes_1km"] = transitions, direction_changes
    df["terrain_variability"] = variability
    df["hillyness_score"] = df.terrain_variability * (1 + df.gradient_direction_changes_1km)
    df["uphill_fraction_1km"] = [np.mean(grad[li1[i]:i+1] > GRADIENT_THRESHOLD_PCT) for i in range(n)]
    df["downhill_fraction_1km"] = [np.mean(grad[li1[i]:i+1] < -GRADIENT_THRESHOLD_PCT) for i in range(n)]
    df["flat_fraction_1km"] = 1 - df.uphill_fraction_1km - df.downhill_fraction_1km
    elapsed_s = np.array([np.nansum(dt_s[li1[i]:i+1]) for i in range(n)])
    df["elevation_gain_rate"] = np.divide(df.elevation_gain_1km, elapsed_s, out=np.full(n, np.nan), where=elapsed_s > 0)
    df["elevation_loss_rate"] = np.divide(df.elevation_loss_1km, elapsed_s, out=np.full(n, np.nan), where=elapsed_s > 0)
    # STEP 7.6 P10: look-ahead terrain over the next 1/2/5 km (static geography,
    # known at prediction time -> legitimate features, not leakage).
    for width in (1.0, 2.0, 5.0):
        j = np.searchsorted(d, d + width, side="right") - 1
        j = np.clip(j, 0, n - 1)
        valid = j > np.arange(n)
        denom = np.where(valid, d[j] - d, np.nan)
        df[f"next_{int(width)}km_net_elev_m"] = np.where(valid, altitude[j] - altitude, np.nan)
        df[f"next_{int(width)}km_gradient_pct"] = np.divide(
            (altitude[j] - altitude) * 100, denom * 1000,
            out=np.full(n, np.nan), where=valid)
        gain = np.zeros(n); loss = np.zeros(n)
        for i in range(n):
            if valid[i]:
                seg = np.diff(altitude[i:j[i] + 1]); seg = seg[np.isfinite(seg)]
                gain[i] = float(np.clip(seg, 0, None).sum())
                loss[i] = float(-np.clip(seg, None, 0).sum())
        df[f"next_{int(width)}km_gain_m"] = gain
        df[f"next_{int(width)}km_loss_m"] = loss
    g5 = df["next_5km_gradient_pct"].to_numpy(float)
    df["next_5km_uphill_frac"] = np.where(np.isfinite(g5), g5 > GRADIENT_THRESHOLD_PCT, np.nan).astype(float)
    df["next_5km_downhill_frac"] = np.where(np.isfinite(g5), g5 < -GRADIENT_THRESHOLD_PCT, np.nan).astype(float)
    df["next_5km_flat_frac"] = 1 - df["next_5km_uphill_frac"] - df["next_5km_downhill_frac"]
    # Nissan-only telemetry stays NaN for Dacia; flags distinguish no sensor from zero output.
    optional = {"speed": "speed_kmh", "motor": "motor_power_kw", "aux": "aux_power_kw", "regen": "regen_power_kw", "temperature": "ambient_temperature_c"}
    for flag, source in optional.items():
        name = "has_speed_data" if flag == "speed" else "has_temperature" if flag == "temperature" else f"has_{flag}_power"
        df[name] = int(df[source].notna().any())
    speed = pd.to_numeric(df.speed_kmh, errors="coerce").to_numpy(float)
    accel = np.divide(np.r_[np.nan, np.diff(speed / 3.6)], dt_s, out=np.full(n, np.nan), where=np.isfinite(dt_s))
    df["current_speed_kmh"], df["acceleration_mps2"] = speed, accel
    for name, li in left.items():
        s_mean = [_stat(_window_values(speed, li, i), np.mean) for i in range(n)]
        df[f"mean_speed_{name}"] = s_mean
        if name != "100m": df[f"speed_std_{name}"] = [_stat(_window_values(speed, li, i), np.std) for i in range(n)]
    li500=left["500m"]
    df["min_speed_recent"]=[_stat(_window_values(speed,li500,i), np.min) for i in range(n)]
    df["max_speed_recent"]=[_stat(_window_values(speed,li500,i), np.max) for i in range(n)]
    df["high_speed_fraction"]=[np.mean(_window_values(speed,li1,i)>80) if len(_window_values(speed,li1,i)) else np.nan for i in range(n)]
    df["stopped_fraction"]=[np.mean(_window_values(speed,li1,i)<1) if len(_window_values(speed,li1,i)) else np.nan for i in range(n)]
    df["stop_count_recent"]=[np.count_nonzero((speed[li1[i]:i+1] < 1) & np.r_[True, speed[li1[i]:i] >= 1]) for i in range(n)]
    df["speed_change_recent"] = speed - np.array([speed[li500[i]] for i in range(n)])
    for metric, values in [("acceleration", accel)]:
        for stat, fun in [("mean",np.nanmean),("std",np.nanstd),("max",np.nanmax),("min",np.nanmin)]:
            df[f"{stat}_{metric}"]=[_stat(_window_values(values,li500,i), fun) for i in range(n)]
    df["hard_acceleration_count"]=[np.sum(_window_values(accel,li500,i)>HARD_ACCELERATION_MPS2) for i in range(n)]
    df["hard_braking_count"]=[np.sum(_window_values(accel,li500,i)<HARD_BRAKING_MPS2) for i in range(n)]
    df["acceleration_variability"] = df.std_acceleration
    motor=pd.to_numeric(df.motor_power_kw,errors="coerce").to_numpy(float); aux=pd.to_numeric(df.aux_power_kw,errors="coerce").to_numpy(float); regen=pd.to_numeric(df.regen_power_kw,errors="coerce").to_numpy(float)
    df["motor_power_kw"],df["torque_nm"],df["motor_rpm"],df["aux_power_kw"],df["regen_power_kw"] = motor,df.motor_torque_nm,df.motor_rpm,aux,regen
    for prefix, values in [("motor_power",motor),("aux_power",aux),("regen_power",regen)]:
        df[f"mean_{prefix}_500m"]=[_stat(_window_values(values,li500,i), np.mean) for i in range(n)]
        df[f"mean_{prefix}_1km"]=[_stat(_window_values(values,li1,i), np.mean) for i in range(n)]
    df["max_motor_power_1km"]=[_stat(_window_values(motor,li1,i), np.max) for i in range(n)]
    df["motor_power_std_1km"]=[_stat(_window_values(motor,li1,i), np.std) for i in range(n)]
    df["positive_motor_power_fraction"]=[np.mean(_window_values(motor,li1,i)>0) if len(_window_values(motor,li1,i)) else np.nan for i in range(n)]
    df["power_variability"]=df.motor_power_std_1km
    df["max_aux_power_1km"]=[_stat(_window_values(aux,li1,i), np.max) for i in range(n)]
    df["aux_power_variability"]=[_stat(_window_values(aux,li1,i), np.std) for i in range(n)]
    df["aux_energy_1km"]=[float(np.nansum(aux[li1[i]:i+1]*dt_s[li1[i]:i+1]/3600)) for i in range(n)]
    df["max_regen_power_1km"]=[_stat(_window_values(regen,li1,i), np.min) for i in range(n)]
    df["regen_event_count_1km"]=[np.count_nonzero(np.diff((regen[li1[i]:i+1]<0).astype(int))==1) for i in range(n)]
    df["regen_duration_estimate"]=[np.nansum(dt_s[li1[i]:i+1][regen[li1[i]:i+1]<0]) for i in range(n)]
    df["regen_energy_recovered_1km"]=[_integrated_positive_energy(regen,dt_s,li1,i) for i in range(n)]
    df["regen_fraction_of_driving_time"]=np.divide(df.regen_duration_estimate,elapsed_s,out=np.full(n,np.nan),where=elapsed_s>0)
    distance_covered_1km = d - d[li1]
    df["regen_intensity"] = np.divide(
        df.regen_energy_recovered_1km.to_numpy(float), distance_covered_1km,
        out=np.full(n, np.nan), where=distance_covered_1km > 0,
    )
    temp=pd.to_numeric(df.ambient_temperature_c,errors="coerce").to_numpy(float)
    df["current_temperature_c"],df["temperature_deviation_from_reference"] = temp,temp-20.0
    df["temperature_recent_mean"]=[_stat(_window_values(temp,li500,i), np.mean) for i in range(n)]
    df["temperature_recent_std"]=[_stat(_window_values(temp,li500,i), np.std) for i in range(n)]
    df["speed_x_gradient"],df["speed_squared"],df["speed_x_temperature"] = speed*grad,speed**2,speed*temp
    # STEP 7.6 P11: speed distribution percentiles + accel aggressiveness (Nissan).
    for q, name in [(10, "p10"), (50, "p50"), (90, "p90")]:
        df[f"speed_{name}"] = np.array([
            np.nanpercentile(speed[max(0, i - 20):i + 1], q) if i > 0 else np.nan
            for i in range(n)])
    df["speed_iqr"] = df.speed_p90 - df.speed_p10
    df["mean_pos_accel"] = np.array([
        _stat(np.clip(_window_values(accel, li500, i), 0, None), np.nanmean) for i in range(n)])
    df["mean_neg_accel"] = np.array([
        _stat(np.clip(_window_values(accel, li500, i), None, 0), np.nanmean) for i in range(n)])
    # STEP 7.6 P12: regen share of traction energy (Nissan).
    traction = np.where(np.isfinite(motor), np.maximum(motor, 0), 0.0) \
        + np.where(np.isfinite(aux), np.maximum(aux, 0), 0.0)
    reg_abs = np.where(np.isfinite(regen), np.maximum(-regen, 0), 0.0)
    df["regen_share_1km"] = np.array([
        (np.nansum(reg_abs[li1[i]:i + 1] * dt_s[li1[i]:i + 1])
         / np.nansum(traction[li1[i]:i + 1] * dt_s[li1[i]:i + 1]))
        if np.nansum(traction[li1[i]:i + 1] * dt_s[li1[i]:i + 1]) > 0 else np.nan
        for i in range(n)])
    df["regen_events_per_km"] = np.divide(
        df.regen_event_count_1km.to_numpy(float),
        np.maximum(d - d[li1], 1e-9))
    # STEP 7.6 P13: temperature bucket (Nissan).
    df["temperature_bucket"] = np.floor(temp / 5.0) * 5.0
    df["hour_of_day"],df["day_of_week"],df["month"] = timestamps.dt.hour,timestamps.dt.dayofweek,timestamps.dt.month
    # STEP 7.6 P9: cyclic time features (raw month was constant).
    df["hour_sin"] = np.sin(2 * np.pi * df.hour_of_day.to_numpy(float) / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df.hour_of_day.to_numpy(float) / 24.0)
    df["is_weekend"] = (df.day_of_week >= 5).astype(float)
    df["trip_phase"] = df.distance_since_trip_start_km / max(float(df.distance_since_trip_start_km.max()), 1e-9)
    df[TARGET] = _target(d, pd.to_numeric(df.soc_pct,errors="coerce").to_numpy(float), pd.to_numeric(df.battery_capacity_kwh,errors="coerce").to_numpy(float))
    step76_features = [
        "hour_sin", "hour_cos", "is_weekend", "trip_phase",
        "next_1km_net_elev_m", "next_1km_gradient_pct", "next_1km_gain_m", "next_1km_loss_m",
        "next_2km_net_elev_m", "next_2km_gradient_pct", "next_2km_gain_m", "next_2km_loss_m",
        "next_5km_net_elev_m", "next_5km_gradient_pct", "next_5km_gain_m", "next_5km_loss_m",
        "next_5km_uphill_frac", "next_5km_downhill_frac", "next_5km_flat_frac",
        "speed_p10", "speed_p50", "speed_p90", "speed_iqr",
        "mean_pos_accel", "mean_neg_accel", "regen_share_1km", "regen_events_per_km",
        "temperature_bucket",
    ]
    metadata=["trip_id","vehicle_id","timestamp","vehicle_model"]
    selected=metadata+COMMON_FEATURES+OPTIONAL_NISSAN_FEATURES+AVAILABILITY_FLAGS+step76_features+["hour_of_day","day_of_week","month",TARGET]
    return df.loc[df[TARGET].notna(), selected]

def main() -> None:
    started=time.perf_counter(); peak=_process_memory_mb(); writer=None; rows=0
    files=sorted(INPUT_DIR.glob("*_standardized.parquet"))
    for number,path in enumerate(files,1):
        frame=pq.read_table(path).to_pandas()
        engineered=engineer_trip(frame)
        if not engineered.empty:
            table=pa.Table.from_pandas(engineered,preserve_index=False)
            if writer is None: writer=pq.ParquetWriter(OUTPUT,table.schema,compression="snappy")
            writer.write_table(table.cast(writer.schema,safe=False)); rows += len(engineered)
        del frame, engineered; gc.collect(); peak=max(peak,_process_memory_mb())
        print(f"{number}/{len(files)} trips processed")
    if writer: writer.close()
    print(f"rows={rows}; peak_process_ram_mb={peak:.1f}; seconds={time.perf_counter()-started:.2f}")

if __name__ == "__main__": main()
