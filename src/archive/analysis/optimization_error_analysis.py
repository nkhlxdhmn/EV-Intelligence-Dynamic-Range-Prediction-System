"""
STEP 7.6 PHASE P20-P21: Error analysis + final target decision.

On the winning model (ExtraTrees, full feature set, GroupKFold OOF on
train+validation only; test off-limits):

P20 Error analysis:
  - residuals vs target (bias, heteroscedasticity)
  - errors by vehicle, by SOC band, by gradient band, by speed band
  - errors by trip_phase (early/mid/late) and by look-ahead 5km gradient
  - worst-trip analysis (which trips are hardest)
  - bias check (mean signed error near 0?)

P21 Target decision:
  - summarize evidence from P2-P3 (target comparison), P9-P13 (look-ahead
    terrain matches the 5km horizon), P17-P19 (feature ablation).
  - final decision: keep 5km SOC target (coverage 74.5%, R2 +0.67 with
    look-ahead features) OR switch to 10km (better MAE but lower coverage)
    OR hybrid. Report recommendation + rationale.

Memory-safe: single frame.
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
REPORTS = PROJECT_ROOT / 'reports'
OUTPUT = REPORTS / 'optimization_error_analysis.json'

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


def oof(df, feats, with_features=None):
    keep = list(dict.fromkeys(['trip_id', 'vehicle_model'] + feats + [TARGET]
                              + (with_features or [])))
    sub = df[keep].dropna(subset=[TARGET])
    X = sub[feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(float)
    med = np.nanmedian(X, axis=0); med = np.where(np.isfinite(med), med, 0.0)
    X = np.where(np.isnan(X), np.broadcast_to(med, X.shape), X)
    groups = sub['trip_id'].to_numpy()
    gkf = GroupKFold(n_splits=5)
    preds = np.full(len(sub), np.nan)
    for t, v in gkf.split(X, y, groups):
        model = ExtraTreesRegressor(**ET_PARAMS)
        model.fit(X[t], y[t])
        preds[v] = model.predict(X[v])
    sub['pred'] = preds
    sub['resid'] = y - preds
    sub['abs_err'] = np.abs(sub['resid'])
    return sub


def bucket_stats(sub, col, bins):
    col_vals = sub[col].to_numpy(dtype=float)
    cats = pd.cut(col_vals, bins)
    s = pd.Series(np.abs(sub['resid'].to_numpy(dtype=float)), index=sub.index)
    out = {}
    for iv in cats.categories:
        mask = np.asarray(cats == iv, dtype=bool)
        vals = s[mask]
        out[str(iv)] = {'mae': round(float(vals.mean()), 5) if len(vals) else None,
                        'n': int(len(vals))}
    return out


def main():
    start = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    df, feats = load()
    print('STEP 7.6 P20-P21: ERROR ANALYSIS & TARGET DECISION')
    print(f'rows={len(df):,}  features={len(feats)}  trips={df.trip_id.nunique()}')
    print('=' * 70)

    with_feats = ['trip_phase', 'current_soc_pct', 'current_gradient_pct',
                  'next_5km_gradient_pct', 'current_speed_kmh']
    sub = oof(df, feats, with_feats)
    y = sub[TARGET].to_numpy(float)
    preds = sub['pred'].to_numpy(float)
    resid = sub['resid'].to_numpy(float)

    report = {}
    report['overall'] = {
        'mae': round(float(np.abs(resid).mean()), 5),
        'rmse': round(float(np.sqrt(np.mean(resid ** 2))), 5),
        'bias': round(float(resid.mean()), 5),
        'r2': round(float(1 - np.sum(resid ** 2) / np.sum((y - y.mean()) ** 2)), 4),
        'n': int(len(sub)),
    }
    print(f'\n[P20] Overall: MAE={report["overall"]["mae"]:.5f}  '
          f'RMSE={report["overall"]["rmse"]:.5f}  bias={report["overall"]["bias"]:+.5f}')

    # bias check by vehicle
    print('\n  errors by vehicle:')
    veh = {}
    for v in sorted(sub['vehicle_model'].unique()):
        m = sub['vehicle_model'] == v
        veh[v] = {'mae': round(float(np.abs(resid[m]).mean()), 5),
                  'bias': round(float(resid[m].mean()), 5),
                  'n': int(m.sum())}
        print(f'    {v:14s} MAE={veh[v]["mae"]:.5f}  bias={veh[v]["bias"]:+.5f}  n={veh[v]["n"]}')
    report['by_vehicle'] = veh

    # residual distribution quantiles
    qs = {f'p{q}': round(float(np.percentile(resid, q)), 5) for q in (5, 25, 50, 75, 95)}
    report['residual_quantiles'] = qs
    print(f'  residual p5/p50/p95: {qs["p5"]} / {qs["p50"]} / {qs["p95"]}')

    # buckets
    print('\n  MAE by gradient band (current):')
    gb = bucket_stats(sub, 'current_gradient_pct', [-99, -3, -1, 1, 3, 99])
    report['by_gradient_band'] = gb
    for k, v in gb.items(): print(f'    {k}  {v}')

    print('\n  MAE by look-ahead 5km gradient:')
    g5 = bucket_stats(sub, 'next_5km_gradient_pct', [-99, -3, -1, 1, 3, 99])
    report['by_next5km_gradient'] = g5
    for k, v in g5.items(): print(f'    {k}  {v}')

    print('\n  MAE by trip phase:')
    tp = bucket_stats(sub, 'trip_phase', [-0.1, 0.33, 0.66, 1.1])
    report['by_trip_phase'] = tp
    for k, v in tp.items(): print(f'    {k}  {v}')

    print('\n  MAE by SOC band:')
    soc = bucket_stats(sub, 'current_soc_pct', [-1, 30, 50, 70, 100])
    report['by_soc_band'] = soc
    for k, v in soc.items(): print(f'    {k}  {v}')

    # worst trips
    print('\n  worst trips (highest trip-level MAE):')
    trip_mae = sub.groupby('trip_id').apply(
        lambda g: np.abs(g['resid']).mean(), include_groups=False).sort_values(ascending=False)
    worst = trip_mae.head(6)
    report['worst_trips'] = {str(k): round(float(v), 5) for k, v in worst.items()}
    for k, v in worst.items(): print(f'    {k}  {v:.5f}')

    # ---- P21 target decision ----
    print('\n[P21] Target decision')
    decision = {
        'recommendation': 'KEEP 5km SOC target',
        'rationale': (
            'P2-P3: 10km target has lower MAE (0.0336 vs 0.0545) but at '
            'substantially lower coverage (61% vs 74.5%) and R2 is higher '
            '(+0.44 vs +0.38) under common features. With the P9-P13 '
            'look-ahead terrain features matched to the 5km horizon, the 5km '
            'target reaches R2=+0.67 on GroupKFold CV. Switching horizons '
            'would invalidate the carefully constructed look-ahead feature '
            'family (next_1/2/5km) and reduce coverage by 13 points. The '
            'power-integrated target (P2-P3) is Nissan-only and not '
            'comparable across vehicles. Therefore the production target '
            'remains target_future_energy_kwh_per_km (5km SOC-derived).'
        ),
        'soc_5km_evidence': 'R2 +0.67 with look-ahead terrain; coverage 74.5%',
        'soc_10km_evidence': 'R2 +0.44 common-only, higher MAE std; coverage 61%',
        'power_integrated': 'Nissan-only, not cross-vehicle comparable',
    }
    report['target_decision'] = decision
    print(f'  Recommendation: {decision["recommendation"]}')

    with open(OUTPUT, 'w') as f:
        json.dump(report, f, indent=2)
    print(f'\nSaved {OUTPUT}')
    print(f'Runtime: {time.time() - start:.1f}s')


if __name__ == '__main__':
    main()