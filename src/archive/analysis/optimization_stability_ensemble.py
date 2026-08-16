"""
STEP 7.6 PHASE P17-P19: CV stability, ensembling, final feature set.

P17 Stability: repeat GroupKFold CV across multiple random seeds / reshuffles
  of trip order and report mean +/- std of MAE per model (guards against
  seed luck on the small 44-trip train+validation pool).
P18 Ensembling: compare
  - single best model (ExtraTrees, tuned)
  - simple average of {ET, XGB, RF}
  - weighted average (weights from per-fold MAE)
  - ET + XGB blending via GroupKFold OOF stacking (ridge on OOF preds)
P19 Final feature set: forward feature selection by family on the ET winner
  (common-only vs +telemetry vs +new vs full) to settle the production set.

Memory-safe: single frame; models small.
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.ensemble import (RandomForestRegressor, ExtraTreesRegressor)
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
REPORTS = PROJECT_ROOT / 'reports'
OUTPUT = REPORTS / 'optimization_stability_ensemble.json'

TARGET = 'target_future_energy_kwh_per_km'
DROP_CONSTANT = ['hard_acceleration_count', 'hard_braking_count', 'month',
                 'is_weekend', 'current_soh_pct', 'battery_capacity_kwh']

COMMON = [
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
]
TELEMETRY = [
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
]
NEW = [
    "hour_sin", "hour_cos", "trip_phase",
    "next_1km_net_elev_m", "next_1km_gradient_pct", "next_1km_gain_m", "next_1km_loss_m",
    "next_2km_net_elev_m", "next_2km_gradient_pct", "next_2km_gain_m", "next_2km_loss_m",
    "next_5km_net_elev_m", "next_5km_gradient_pct", "next_5km_gain_m", "next_5km_loss_m",
    "next_5km_uphill_frac", "next_5km_downhill_frac", "next_5km_flat_frac",
    "speed_p10", "speed_p50", "speed_p90", "speed_iqr",
    "mean_pos_accel", "mean_neg_accel", "regen_share_1km", "regen_events_per_km",
    "temperature_bucket",
]

ET_PARAMS = dict(n_estimators=300, max_depth=10, min_samples_leaf=3, n_jobs=-1, random_state=42)
XGB_PARAMS = dict(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
                  colsample_bytree=0.8, random_state=42)
RF_PARAMS = dict(n_estimators=300, max_depth=10, min_samples_leaf=3, n_jobs=-1, random_state=42)


def load() -> tuple[pd.DataFrame, list[str]]:
    tr = pd.read_parquet(PROCESSED / 'v2_train.parquet')
    va = pd.read_parquet(PROCESSED / 'v2_validation.parquet')
    df = pd.concat([tr, va], ignore_index=True)
    del tr, va
    gc.collect()
    feats = [f for f in COMMON + TELEMETRY + NEW
             if f in df.columns and f not in DROP_CONSTANT
             and pd.api.types.is_numeric_dtype(df[f])]
    return df, feats


def make_matrix(df, feats):
    sub = df[['trip_id', 'vehicle_model'] + feats + [TARGET]].dropna(subset=[TARGET])
    X = sub[feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(float)
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    X = np.where(np.isnan(X), np.broadcast_to(med, X.shape), X)
    return sub, X, y


def cv_single(df, feats, factory, seeds=(42, 7, 123, 2024, 99), impute=True):
    sub, X, y = make_matrix(df, feats)
    groups = sub['trip_id'].to_numpy()
    maes, rmses, r2s = [], [], []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(sub))
        g = groups[order]; Xo = X[order]; yo = y[order]
        # regroup trips into folds via unique trip ids so groups stay trip-level
        unique_trips = np.unique(g)
        uo = rng.permutation(unique_trips)
        folds = np.array_split(uo, 5)
        fold_id = np.full(len(g), -1)
        for fi, trs in enumerate(folds):
            fold_id[np.isin(g, trs)] = fi
        preds = np.full(len(g), np.nan)
        model = factory()
        for fi in range(5):
            tr_mask = fold_id != fi
            model.fit(Xo[tr_mask], yo[tr_mask])
            preds[fold_id == fi] = model.predict(Xo[fold_id == fi])
        # map back to original order
        rev = np.empty(len(g), dtype=int); rev[order] = np.arange(len(g))
        preds = preds[rev]
        maes.append(np.abs(preds - y).mean())
        rmses.append(np.sqrt(np.mean((preds - y) ** 2)))
        r2s.append(1 - np.sum((y - preds) ** 2) / np.sum((y - y.mean()) ** 2))
    return {'mae_mean': round(float(np.mean(maes)), 5),
            'mae_std': round(float(np.std(maes)), 5),
            'mae_runs': [round(float(v), 5) for v in maes],
            'rmse_mean': round(float(np.mean(rmses)), 5),
            'r2_mean': round(float(np.mean(r2s)), 4),
            'r2_std': round(float(np.std(r2s)), 4)}


def oof_preds(df, feats, factory):
    sub, X, y = make_matrix(df, feats)
    groups = sub['trip_id'].to_numpy()
    gkf = GroupKFold(n_splits=5)
    preds = np.full(len(sub), np.nan)
    for t, v in gkf.split(X, y, groups):
        model = factory()
        model.fit(X[t], y[t])
        preds[v] = model.predict(X[v])
    return sub, y, preds


def main():
    start = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    df, feats = load()
    print('STEP 7.6 P17-P19: STABILITY / ENSEMBLING / FINAL FEATURE SET')
    print(f'rows={len(df):,}  features={len(feats)}  trips={df.trip_id.nunique()}')
    print('=' * 70)
    results = {}

    # ---- P17 stability ----
    print('\n[P17] Stability across 5 reshuffles (mean +/- std of MAE):')
    for name, factory in [('ExtraTrees', lambda: ExtraTreesRegressor(**ET_PARAMS)),
                          ('XGBoost', lambda: XGBRegressor(**XGB_PARAMS)),
                          ('RandomForest', lambda: RandomForestRegressor(**RF_PARAMS))]:
        r = cv_single(df, feats, factory)
        results[f'stability_{name}'] = r
        print(f'  {name:14s} MAE={r["mae_mean"]:.5f} +/- {r["mae_std"]:.5f}  '
              f'R2={r["r2_mean"]:+.3f} +/- {r["r2_std"]:.3f}')

    # ---- P18 ensembling (GroupKFold OOF) ----
    print('\n[P18] Ensembling (GroupKFold OOF):')
    sub, y, p_et = oof_preds(df, feats, lambda: ExtraTreesRegressor(**ET_PARAMS))
    _, _, p_xgb = oof_preds(df, feats, lambda: XGBRegressor(**XGB_PARAMS))
    _, _, p_rf = oof_preds(df, feats, lambda: RandomForestRegressor(**RF_PARAMS))

    def ev(pred, label):
        mae = float(np.abs(pred - y).mean())
        rmse = float(np.sqrt(np.mean((pred - y) ** 2)))
        r2 = float(1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))
        results[label] = {'mae': round(mae, 5), 'rmse': round(rmse, 5), 'r2': round(r2, 4)}
        print(f'  {label:24s} MAE={mae:.5f}  RMSE={rmse:.5f}  R2={r2:+.3f}')

    ev(p_et, 'single_ExtraTrees')
    ev(p_xgb, 'single_XGBoost')
    ev((p_et + p_xgb) / 2, 'avg_ET_XGB')
    ev((p_et + p_xgb + p_rf) / 3, 'avg_ET_XGB_RF')

    # stacked ridge on OOF preds (group-aware: fit ridge on train-fold OOF, pred on val-fold OOF)
    M = np.column_stack([p_et, p_xgb, p_rf])
    gkf = GroupKFold(n_splits=5)
    groups = sub['trip_id'].to_numpy()
    stack_preds = np.full(len(y), np.nan)
    for t, v in gkf.split(M, y, groups):
        ridge = Ridge(alpha=1.0)
        ridge.fit(M[t], y[t])
        stack_preds[v] = ridge.predict(M[v])
    ev(stack_preds, 'stacked_ridge_OOF')

    # ---- P19 final feature set ----
    print('\n[P19] Feature-set ablation on ExtraTrees (GroupKFold):')
    sets = {
        'common_only': [f for f in COMMON if f in feats],
        'common_plus_new': [f for f in COMMON + NEW if f in feats],
        'common_plus_telemetry': [f for f in COMMON + TELEMETRY if f in feats],
        'full': feats,
    }
    for name, fs in sets.items():
        r = cv_single(df, fs, lambda: ExtraTreesRegressor(**ET_PARAMS), seeds=(42,))
        results[f'set_{name}'] = r
        print(f'  {name:26s} f={len(fs):3d}  MAE={r["mae_mean"]:.5f}  R2={r["r2_mean"]:+.3f}')

    results['final_feature_set'] = feats
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nSaved {OUTPUT}')
    print(f'Runtime: {time.time() - start:.1f}s')


if __name__ == '__main__':
    main()