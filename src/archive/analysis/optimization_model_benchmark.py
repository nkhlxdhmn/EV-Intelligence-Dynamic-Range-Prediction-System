"""
STEP 7.6 PHASE P14-P16: Model benchmark & hyperparameter tuning.

Benchmarks candidate algorithms on the enriched v2 (train+validation only,
test off-limits) with the winning feature set from P9-P13 (common + telemetry
+ look-ahead/new features). GroupKFold CV at the trip level.

P14 benchmark (default params):
  - XGBoost, RandomForest, ExtraTrees, LightGBM, GradientBoosting
  - plus a Global-Mean and trip-level baseline for reference
P15 tuning (per model, small grid, GroupKFold):
  - XGBoost: n_estimators, max_depth, learning_rate, subsample, colsample
  - RandomForest/ExtraTrees: n_estimators, max_depth, min_samples_leaf
P16 selection:
  - best config per family; report MAE/RMSE/R2 + per-vehicle MAE

Memory-safe: single ~11k-row frame; models are small.
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.ensemble import (RandomForestRegressor, ExtraTreesRegressor,
                              GradientBoostingRegressor)
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

try:
    from lightgbm import LGBMRegressor
    HAS_LGBM = True
except Exception:
    HAS_LGBM = False

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
REPORTS = PROJECT_ROOT / 'reports'
OUTPUT = REPORTS / 'optimization_model_benchmark.json'

TARGET = 'target_future_energy_kwh_per_km'
ID_COLS = ['trip_id', 'vehicle_id', 'timestamp', 'vehicle_model', 'terrain_class']

DROP_CONSTANT = ['hard_acceleration_count', 'hard_braking_count', 'month',
                 'is_weekend', 'current_soh_pct', 'battery_capacity_kwh']

FEATURE_BASE = [
    # common
    "current_soc_pct", "current_altitude_m", "current_gradient_pct", "past_1km_gradient_pct",
    "elevation_gain_100m", "elevation_gain_500m", "elevation_gain_1km",
    "elevation_loss_100m", "elevation_loss_500m", "elevation_loss_1km",
    "net_elevation_change_1km", "mean_gradient_500m", "mean_gradient_1km",
    "gradient_std_500m", "gradient_std_1km", "max_uphill_gradient", "max_downhill_gradient",
    "terrain_variability", "hillyness_score", "uphill_fraction_1km", "downhill_fraction_1km",
    "flat_fraction_1km", "terrain_transition_count_1km", "gradient_direction_changes_1km",
    "elevation_gain_rate", "elevation_loss_rate", "distance_since_trip_start_km",
    "time_since_trip_start_min", "trip_distance_so_far_km", "trip_elapsed_time_min",
    "hour_of_day", "day_of_week",
    # telemetry
    "current_speed_kmh", "mean_speed_500m", "mean_speed_1km", "speed_std_500m", "speed_std_1km",
    "min_speed_recent", "max_speed_recent", "high_speed_fraction", "stopped_fraction",
    "stop_count_recent", "speed_change_recent", "acceleration_mps2", "mean_acceleration",
    "std_acceleration", "max_acceleration", "min_acceleration", "motor_power_kw", "torque_nm",
    "motor_rpm", "mean_motor_power_500m", "mean_motor_power_1km", "max_motor_power_1km",
    "positive_motor_power_fraction", "power_variability", "aux_power_kw",
    "mean_aux_power_500m", "mean_aux_power_1km", "max_aux_power_1km", "aux_power_variability",
    "aux_energy_1km", "regen_power_kw", "mean_regen_power_500m", "mean_regen_power_1km",
    "max_regen_power_1km", "regen_event_count_1km", "regen_duration_estimate",
    "regen_energy_recovered_1km", "regen_fraction_of_driving_time", "regen_intensity",
    "current_temperature_c", "temperature_recent_mean", "speed_x_gradient", "speed_squared",
    "speed_x_temperature",
    # new (P9-P13)
    "hour_sin", "hour_cos", "trip_phase",
    "next_1km_net_elev_m", "next_1km_gradient_pct", "next_1km_gain_m", "next_1km_loss_m",
    "next_2km_net_elev_m", "next_2km_gradient_pct", "next_2km_gain_m", "next_2km_loss_m",
    "next_5km_net_elev_m", "next_5km_gradient_pct", "next_5km_gain_m", "next_5km_loss_m",
    "next_5km_uphill_frac", "next_5km_downhill_frac", "next_5km_flat_frac",
    "speed_p10", "speed_p50", "speed_p90", "speed_iqr",
    "mean_pos_accel", "mean_neg_accel", "regen_share_1km", "regen_events_per_km",
    "temperature_bucket",
]


def load() -> pd.DataFrame:
    tr = pd.read_parquet(PROCESSED / 'v2_train.parquet')
    va = pd.read_parquet(PROCESSED / 'v2_validation.parquet')
    df = pd.concat([tr, va], ignore_index=True)
    del tr, va
    gc.collect()
    feats = [f for f in FEATURE_BASE
             if f in df.columns and f not in DROP_CONSTANT
             and pd.api.types.is_numeric_dtype(df[f])]
    return df, feats


def run_cv(df, feats, model_factory, name, results, impute=False):
    sub = df[['trip_id', 'vehicle_model'] + feats + [TARGET]].dropna(subset=[TARGET])
    X = sub[feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(float)
    if impute:
        med = np.nanmedian(X, axis=0)
        med = np.where(np.isfinite(med), med, 0.0)
        X = np.where(np.isnan(X), np.broadcast_to(med, X.shape), X)
    groups = sub['trip_id'].to_numpy()
    gkf = GroupKFold(n_splits=5)
    preds = np.full(len(sub), np.nan)
    model = model_factory()
    for t, v in gkf.split(X, y, groups):
        model.fit(X[t], y[t])
        preds[v] = model.predict(X[v])
    mae = float(np.abs(preds - y).mean())
    rmse = float(np.sqrt(np.mean((preds - y) ** 2)))
    r2 = float(1 - np.sum((y - preds) ** 2) / np.sum((y - y.mean()) ** 2))
    dacia = sub['vehicle_model'] == 'Dacia Spring'
    mae_d = float(np.abs(preds[dacia] - y[dacia]).mean()) if dacia.any() else None
    mae_n = float(np.abs(preds[~dacia] - y[~dacia]).mean()) if (~dacia).any() else None
    results[name] = {'n': int(len(sub)), 'mae': round(mae, 5), 'rmse': round(rmse, 5),
                     'r2': round(r2, 4),
                     'mae_dacia': round(mae_d, 5) if mae_d is not None else None,
                     'mae_nissan': round(mae_n, 5) if mae_n is not None else None}
    md = f'{mae_d:.5f}' if mae_d is not None else '  nan  '
    mn = f'{mae_n:.5f}' if mae_n is not None else '  nan  '
    print(f'  {name:34s} MAE={mae:.5f}  RMSE={rmse:.5f}  R2={r2:+.3f}  '
          f'MAE_D={md}  MAE_N={mn}')
    return results[name]


def main():
    start = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    df, feats = load()
    print('STEP 7.6 P14-P16: MODEL BENCHMARK & TUNING')
    print(f'rows={len(df):,}  features={len(feats)}  trips={df.trip_id.nunique()}')
    print('=' * 70)
    results = {}

    # ---- baselines ----
    sub = df[['trip_id', 'vehicle_model', TARGET]].dropna()
    y = sub[TARGET].to_numpy(float)
    gm = float(y.mean())
    results['baseline_global_mean'] = {
        'n': int(len(y)), 'mae': round(float(np.abs(y - gm).mean()), 5),
        'rmse': round(float(np.sqrt(np.mean((y - gm) ** 2))), 5), 'r2': 0.0}
    print(f'  baseline_global_mean               MAE={results["baseline_global_mean"]["mae"]:.5f}')

    # ---- P14 default-param benchmark ----
    print('\n[P14] Default-parameter benchmark:')
    default = {
        'xgb': lambda: XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.1,
                                    subsample=0.8, colsample_bytree=0.8, random_state=42),
        'rf': lambda: RandomForestRegressor(n_estimators=200, max_depth=8, min_samples_leaf=5,
                                            n_jobs=-1, random_state=42),
        'et': lambda: ExtraTreesRegressor(n_estimators=200, max_depth=8, min_samples_leaf=5,
                                          n_jobs=-1, random_state=42),
        'gbrt': lambda: GradientBoostingRegressor(n_estimators=200, max_depth=3,
                                                  learning_rate=0.1, random_state=42),
    }
    if HAS_LGBM:
        default['lgbm'] = lambda: LGBMRegressor(n_estimators=200, max_depth=3, learning_rate=0.1,
                                                subsample=0.8, colsample_bytree=0.8,
                                                random_state=42, verbose=-1)
    for name, factory in default.items():
        run_cv(df, feats, factory, f'bench_{name}', results, impute=(name in ('rf', 'et', 'gbrt')))

    # ---- P15 tuning (small grid) ----
    print('\n[P15] Tuning grid (GroupKFold CV):')
    grids = {
        'xgb': [
            dict(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
                 colsample_bytree=0.8, random_state=42),
            dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.7,
                 colsample_bytree=0.7, random_state=42),
            dict(n_estimators=400, max_depth=5, learning_rate=0.03, subsample=0.8,
                 colsample_bytree=0.8, random_state=42),
        ],
        'rf': [
            dict(n_estimators=300, max_depth=6, min_samples_leaf=5, n_jobs=-1, random_state=42),
            dict(n_estimators=300, max_depth=10, min_samples_leaf=3, n_jobs=-1, random_state=42),
            dict(n_estimators=500, max_depth=None, min_samples_leaf=2, n_jobs=-1, random_state=42),
        ],
        'et': [
            dict(n_estimators=300, max_depth=6, min_samples_leaf=5, n_jobs=-1, random_state=42),
            dict(n_estimators=300, max_depth=10, min_samples_leaf=3, n_jobs=-1, random_state=42),
            dict(n_estimators=500, max_depth=None, min_samples_leaf=2, n_jobs=-1, random_state=42),
        ],
    }
    best_per_family = {}
    for fam, params_list in grids.items():
        best = None
        for p in params_list:
            tag = f"tune_{fam}_" + "_".join(f"{k}{v}" for k, v in p.items()
                                            if k not in ('random_state', 'n_jobs'))
            res = run_cv(df, feats, lambda pp=p: _mk(fam, pp), f'tune_{fam}', results,
                         impute=(fam in ('rf', 'et')))
            if best is None or res['mae'] < best['mae']:
                best = res
        best_per_family[fam] = best

    # ---- P16 selection ----
    print('\n[P16] Selection (best per family):')
    for fam, res in best_per_family.items():
        print(f'  {fam:10s} MAE={res["mae"]:.5f}  RMSE={res["rmse"]:.5f}  R2={res["r2"]:+.3f}')

    with open(OUTPUT, 'w') as f:
        json.dump({'features': feats, 'results': results, 'best_per_family': best_per_family},
                  f, indent=2)
    print(f'\nSaved {OUTPUT}')
    print(f'Runtime: {time.time() - start:.1f}s')


def _mk(fam, p):
    if fam == 'xgb':
        return XGBRegressor(**p)
    if fam == 'rf':
        return RandomForestRegressor(**p)
    return ExtraTreesRegressor(**p)


if __name__ == '__main__':
    main()