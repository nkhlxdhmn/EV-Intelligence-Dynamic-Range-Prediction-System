"""
STEP 7.6 PHASE P7-P8: Missing telemetry strategies + vehicle-specific models.

Question: Dacia lacks speed/motor/regen/temperature telemetry (structural
missingness); Nissan has it all. Should the final model be:
  (a) one cross-vehicle model on common features only,
  (b) one model with NaN-handling for telemetry features (XGBoost-native),
  (c) vehicle-specific models (one per vehicle),
  (d) per-vehicle models sharing a common-feature backbone?

Strategy (b) risks the model over-relying on telemetry that is structurally
absent for Dacia. Strategy (c) splits the tiny dataset (50 trips). This phase
measures the tradeoff with GroupKFold CV on train+validation ONLY (test set
off-limits):

  - Model A: common features only (no telemetry)  -> the cross-vehicle baseline
  - Model B: common + telemetry features with XGBoost NaN handling
  - Model C: Dacia-only model (common features)
  - Model D: Nissan-only model (common + telemetry features)

We also test a "telemetry-gated" variant: common + telemetry, but telemetry
features are masked (set to NaN) for Dacia rows so XGBoost's missing-value
handling naturally routes Dacia rows through common-only splits.

Memory-safe: loads only v2 train/validation (~11k rows).
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
REPORTS = PROJECT_ROOT / 'reports'
OUTPUT = REPORTS / 'optimization_vehicle_strategy.json'

TARGET = 'target_future_energy_kwh_per_km'
ID_COLS = ['trip_id', 'vehicle_id', 'timestamp', 'vehicle_model']

COMMON_FEATURES = [
    "current_soc_pct", "current_soh_pct",
    "current_altitude_m", "current_gradient_pct", "past_1km_gradient_pct",
    "elevation_gain_100m", "elevation_gain_500m", "elevation_gain_1km",
    "elevation_loss_100m", "elevation_loss_500m", "elevation_loss_1km",
    "net_elevation_change_1km", "mean_gradient_500m", "mean_gradient_1km",
    "gradient_std_500m", "gradient_std_1km",
    "max_uphill_gradient", "max_downhill_gradient", "terrain_variability",
    "hillyness_score", "uphill_fraction_1km", "downhill_fraction_1km",
    "flat_fraction_1km", "terrain_transition_count_1km",
    "gradient_direction_changes_1km", "elevation_gain_rate",
    "elevation_loss_rate", "distance_since_trip_start_km",
    "time_since_trip_start_min", "trip_distance_so_far_km", "trip_elapsed_time_min",
    "hour_of_day", "day_of_week", "month",
]

TELEMETRY_FEATURES = [
    "current_speed_kmh", "mean_speed_100m", "mean_speed_500m", "mean_speed_1km",
    "speed_std_500m", "speed_std_1km", "min_speed_recent", "max_speed_recent",
    "high_speed_fraction", "stopped_fraction", "stop_count_recent",
    "speed_change_recent", "acceleration_mps2", "mean_acceleration",
    "std_acceleration", "max_acceleration", "min_acceleration",
    "acceleration_variability", "motor_power_kw", "torque_nm", "motor_rpm",
    "mean_motor_power_500m", "mean_motor_power_1km", "max_motor_power_1km",
    "motor_power_std_1km", "positive_motor_power_fraction", "power_variability",
    "aux_power_kw", "mean_aux_power_500m", "mean_aux_power_1km",
    "max_aux_power_1km", "aux_power_variability", "aux_energy_1km",
    "regen_power_kw", "mean_regen_power_500m", "mean_regen_power_1km",
    "max_regen_power_1km", "regen_event_count_1km", "regen_duration_estimate",
    "regen_energy_recovered_1km", "regen_fraction_of_driving_time",
    "regen_intensity", "current_temperature_c",
    "temperature_deviation_from_reference", "temperature_recent_mean",
    "temperature_recent_std", "speed_x_gradient", "speed_squared",
    "speed_x_temperature",
]


def load_frame() -> pd.DataFrame:
    tr = pd.read_parquet(PROCESSED / 'v2_train.parquet')
    va = pd.read_parquet(PROCESSED / 'v2_validation.parquet')
    df = pd.concat([tr, va], ignore_index=True)
    del tr, va
    gc.collect()
    return df


def run_cv(df: pd.DataFrame, feats: list[str], name: str, results: dict):
    sub = df[['trip_id', 'vehicle_model'] + feats + [TARGET]].dropna(subset=[TARGET])
    X = sub[feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(float)
    groups = sub['trip_id'].to_numpy()
    gkf = GroupKFold(n_splits=5)
    model = XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.1,
                         subsample=0.8, colsample_bytree=0.8, random_state=42)
    preds = np.full(len(sub), np.nan)
    for tr_idx, va_idx in gkf.split(X, y, groups):
        model.fit(X[tr_idx], y[tr_idx])
        preds[va_idx] = model.predict(X[va_idx])
    mae = float(np.abs(preds - y).mean())
    rmse = float(np.sqrt(np.mean((preds - y) ** 2)))
    r2 = float(1 - np.sum((y - preds) ** 2) / np.sum((y - y.mean()) ** 2))
    n_dacia = int((sub['vehicle_model'] == 'Dacia Spring').sum())
    n_nissan = int((sub['vehicle_model'] == 'Nissan Leaf').sum())
    mae_dacia = float(np.abs(preds[sub['vehicle_model'] == 'Dacia Spring']
                             - y[sub['vehicle_model'] == 'Dacia Spring']).mean()) \
        if n_dacia else None
    mae_nissan = float(np.abs(preds[sub['vehicle_model'] == 'Nissan Leaf']
                              - y[sub['vehicle_model'] == 'Nissan Leaf']).mean()) \
        if n_nissan else None
    results[name] = {
        'features': len(feats), 'n': int(len(sub)),
        'n_dacia': n_dacia, 'n_nissan': n_nissan,
        'mae': round(mae, 5), 'rmse': round(rmse, 5), 'r2': round(r2, 4),
        'mae_dacia': round(mae_dacia, 5) if mae_dacia is not None else None,
        'mae_nissan': round(mae_nissan, 5) if mae_nissan is not None else None,
    }
    md = f'{mae_dacia:.5f}' if mae_dacia is not None else '  nan  '
    mn = f'{mae_nissan:.5f}' if mae_nissan is not None else '  nan  '
    print(f'  {name:18s} n={len(sub):5,} (D:{n_dacia:4,}/N:{n_nissan:4,})  '
          f'MAE={mae:.5f}  RMSE={rmse:.5f}  R2={r2:+.3f}  '
          f'MAE_D={md}  MAE_N={mn}')


def main():
    start = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    df = load_frame()
    print('STEP 7.6 P7-P8: MISSING-TELEMETRY STRATEGY & VEHICLE-SPECIFIC MODELS')
    print(f'rows={len(df):,}  trips={df.trip_id.nunique()}  '
          f'Dacia={int((df.vehicle_model=="Dacia Spring").sum()):,}  '
          f'Nissan={int((df.vehicle_model=="Nissan Leaf").sum()):,}')
    print('=' * 70)

    results = {}

    print('\n[A] Cross-vehicle, common features only (baseline):')
    run_cv(df, COMMON_FEATURES, 'A_common_only', results)

    print('\n[B] Cross-vehicle, common + telemetry (XGBoost NaN handling):')
    run_cv(df, COMMON_FEATURES + TELEMETRY_FEATURES, 'B_common_plus_telemetry', results)

    print('\n[C] Dacia-only model (common features):')
    dacia = df[df['vehicle_model'] == 'Dacia Spring'].copy()
    run_cv(dacia, COMMON_FEATURES, 'C_dacia_only', results)

    print('\n[D] Nissan-only model (common + telemetry):')
    nissan = df[df['vehicle_model'] == 'Nissan Leaf'].copy()
    run_cv(nissan, COMMON_FEATURES + TELEMETRY_FEATURES, 'D_nissan_only', results)

    # ---- Gated telemetry (mask telemetry to NaN for Dacia) ----
    print('\n[E] Gated telemetry (telemetry NaN for Dacia, full for Nissan):')
    gated = df.copy()
    tele = [c for c in TELEMETRY_FEATURES if c in gated.columns]
    gated.loc[gated['vehicle_model'] == 'Dacia Spring', tele] = np.nan
    run_cv(gated, COMMON_FEATURES + tele, 'E_gated_telemetry', results)

    with open(OUTPUT, 'w') as f:
        json.dump({'models': results}, f, indent=2)
    print(f'\nSaved {OUTPUT}')
    print(f'Runtime: {time.time() - start:.1f}s')


if __name__ == '__main__':
    main()