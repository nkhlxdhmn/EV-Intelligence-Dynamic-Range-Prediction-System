"""
STEP 7.6 PHASE P9-P13: New feature families & their marginal value.

Adds new feature families to the CLEAN v2 (train+validation, test off-limits):

  P9  Temporal:
    - hour_sin / hour_cos cyclic encoding
    - is_weekend, trip_phase (progress along route: early/mid/late)
  P10 Terrain (look-ahead, static geography -> legitimate for prediction):
    - next_1km/2km/5km net elevation change and mean gradient
    - next_1km/2km/5km elevation gain/loss
    - next_5km uphill/downhill/flat fractions
  P11 Driving (Nissan only, NaN for Dacia):
    - speed percentiles (p10/p50/p90), speed_iqr
    - mean positive / negative accel (drive aggressiveness)
  P12 Regen (Nissan only):
    - regen_share = regen_energy / |motor_energy + aux| over 1 km
    - regen_events_per_km (existing count normalized by distance)
  P13 Environment:
    - temperature_bucket (binned temp, Nissan only)

Evaluates marginal value: GroupKFold CV of XGBoost with
  - baseline A: common features only (P4-P6 trimmed set)
  - baseline B: A + existing telemetry (gated, P7-P8 winner)
  - NEW:        B + new feature families

Memory-safe: one standardized trip at a time.
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
OUTPUT = REPORTS / 'optimization_new_features.json'

TARGET = 'target_future_energy_kwh_per_km'

BASE_FEATURES = [
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
    "hour_of_day", "day_of_week",
]

# telemetry set with new features removed where they'd be duplicated
TELEMETRY = [
    "current_speed_kmh", "mean_speed_500m", "mean_speed_1km",
    "speed_std_500m", "speed_std_1km", "min_speed_recent", "max_speed_recent",
    "high_speed_fraction", "stopped_fraction", "stop_count_recent",
    "speed_change_recent", "acceleration_mps2", "mean_acceleration",
    "std_acceleration", "max_acceleration", "min_acceleration",
    "motor_power_kw", "torque_nm", "motor_rpm",
    "mean_motor_power_500m", "mean_motor_power_1km", "max_motor_power_1km",
    "positive_motor_power_fraction", "power_variability",
    "aux_power_kw", "mean_aux_power_500m", "mean_aux_power_1km",
    "max_aux_power_1km", "aux_power_variability", "aux_energy_1km",
    "regen_power_kw", "mean_regen_power_500m", "mean_regen_power_1km",
    "max_regen_power_1km", "regen_event_count_1km", "regen_duration_estimate",
    "regen_energy_recovered_1km", "regen_fraction_of_driving_time",
    "regen_intensity", "current_temperature_c", "temperature_recent_mean",
    "speed_x_gradient", "speed_squared", "speed_x_temperature",
]


def main():
    start = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    print('STEP 7.6 P9-P13: NEW FEATURE FAMILIES (marginal value)')
    print('=' * 70)

    # New features are now integrated into v2 directly (one trip at a time).
    tr = pd.read_parquet(PROCESSED / 'v2_train.parquet')
    va = pd.read_parquet(PROCESSED / 'v2_validation.parquet')
    merged = pd.concat([tr, va], ignore_index=True)
    del tr, va
    gc.collect()

    NEW_FEATURES = [
        "hour_sin", "hour_cos", "is_weekend", "trip_phase",
        "next_1km_net_elev_m", "next_1km_gradient_pct", "next_1km_gain_m", "next_1km_loss_m",
        "next_2km_net_elev_m", "next_2km_gradient_pct", "next_2km_gain_m", "next_2km_loss_m",
        "next_5km_net_elev_m", "next_5km_gradient_pct", "next_5km_gain_m", "next_5km_loss_m",
        "next_5km_uphill_frac", "next_5km_downhill_frac", "next_5km_flat_frac",
        "speed_p10", "speed_p50", "speed_p90", "speed_iqr",
        "mean_pos_accel", "mean_neg_accel", "regen_share_1km", "regen_events_per_km",
        "temperature_bucket",
    ]
    print(f'new features in v2 ({len(NEW_FEATURES)}): {NEW_FEATURES}')
    print(f'rows={len(merged):,}')
    print('\ncoverage in train+validation:')
    for c in NEW_FEATURES:
        print(f'  {c:28s} {merged[c].notna().mean()*100:5.1f}%')

    # ---- GroupKFold CV comparison ----
    print('\nGroupKFold CV (XGBoost):')
    gkf = GroupKFold(n_splits=5)
    results = {}
    for name, feats in [
        ('A_common_only', BASE_FEATURES),
        ('B_common_plus_telemetry', BASE_FEATURES + TELEMETRY),
        ('C_plus_new_features', BASE_FEATURES + TELEMETRY + NEW_FEATURES),
    ]:
        feats = [f for f in feats if f in merged.columns]
        sub = merged[['trip_id', 'vehicle_model'] + feats + [TARGET]].dropna(subset=[TARGET])
        X = sub[feats].to_numpy(dtype=float)
        y = sub[TARGET].to_numpy(float)
        groups = sub['trip_id'].to_numpy()
        model = XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.1,
                             subsample=0.8, colsample_bytree=0.8, random_state=42)
        preds = np.full(len(sub), np.nan)
        for t, v in gkf.split(X, y, groups):
            model.fit(X[t], y[t])
            preds[v] = model.predict(X[v])
        mae = float(np.abs(preds - y).mean())
        rmse = float(np.sqrt(np.mean((preds - y) ** 2)))
        r2 = float(1 - np.sum((y - preds) ** 2) / np.sum((y - y.mean()) ** 2))
        dacia = sub['vehicle_model'] == 'Dacia Spring'
        mae_d = float(np.abs(preds[dacia] - y[dacia]).mean()) if dacia.any() else None
        mae_n = float(np.abs(preds[~dacia] - y[~dacia]).mean()) if (~dacia).any() else None
        results[name] = {'n_features': len(feats), 'n': int(len(sub)),
                         'mae': round(mae, 5), 'rmse': round(rmse, 5), 'r2': round(r2, 4),
                         'mae_dacia': round(mae_d, 5) if mae_d is not None else None,
                         'mae_nissan': round(mae_n, 5) if mae_n is not None else None}
        md = f'{mae_d:.5f}' if mae_d is not None else '  nan  '
        mn = f'{mae_n:.5f}' if mae_n is not None else '  nan  '
        print(f'  {name:26s} f={len(feats):3d}  MAE={mae:.5f}  RMSE={rmse:.5f}  R2={r2:+.3f}  '
              f'MAE_D={md}  MAE_N={mn}')

    merged.drop(columns=['distance_km'], inplace=True, errors='ignore')
    with open(OUTPUT, 'w') as f:
        json.dump({'new_features': NEW_FEATURES, 'cv': results}, f, indent=2)
    print(f'\nSaved {OUTPUT}')
    print(f'Runtime: {time.time() - start:.1f}s')


if __name__ == '__main__':
    main()