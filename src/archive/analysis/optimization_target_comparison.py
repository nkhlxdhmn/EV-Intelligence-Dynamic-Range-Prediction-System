"""
STEP 7.6 PHASE P2-P3: Target optimization & stability analysis.

Compares candidate target definitions on the CLEAN v2 population:
  1. SOC-derived kWh/km at 5 km horizon (current default)
  2. SOC-derived kWh/km at 10 km horizon
  3. SOC-derived kWh/km at 15 km horizon
  4. Power-integrated kWh/km (Nissan only, motor+regen integrated over 5 km)
  5. Hybrid: power-integrated where available, SOC-derived otherwise

For each target we report:
  - coverage (samples with valid target)
  - distribution (mean / std / min / max / zero / negative)
  - implied noise floor (SOC 1% quantization at 62 kWh = 0.124 kWh/km)
  - predictability via a simple Gradient-Boosting baseline on GroupKFold CV
    using the A_BASIC common features (so all targets share the same feature
    population), avoiding the test set entirely.

Memory-safe: one trip at a time.
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from xgboost import XGBRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'src'))
from data.devrt_parser import timestamp_to_epoch_seconds

PROJECT_ROOT = Path(__file__).parent.parent.parent
INTERIM = PROJECT_ROOT / 'data' / 'interim' / 'devrt'
REPORTS = PROJECT_ROOT / 'reports'
OUTPUT = REPORTS / 'optimization_target_comparison.json'

COMMON_FEATURES = [
    "current_soc_pct", "current_soh_pct", "battery_capacity_kwh",
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


def soc_target(distance, soc, capacity, horizon_km, min_frac=0.9):
    """(soc[start] - soc[end]) * capacity / 100 / (distance[end] - distance[start])."""
    n = len(distance)
    result = np.full(n, np.nan)
    for i in range(n):
        j = np.searchsorted(distance, distance[i] + horizon_km, side='left')
        if j < n and (distance[j] - distance[i]) >= horizon_km * min_frac \
                and np.isfinite(soc[i]) and np.isfinite(soc[j]) and np.isfinite(capacity[i]):
            result[i] = (soc[i] - soc[j]) * capacity[i] / 100.0 / (distance[j] - distance[i])
    return result


def power_integrated_target(motor_power_kw, regen_power_kw, dt_s, distance, horizon_km, min_frac=0.9):
    """Integrate net power (motor + regen) over the future horizon / distance."""
    n = len(distance)
    result = np.full(n, np.nan)
    net = np.where(np.isfinite(motor_power_kw), motor_power_kw, 0.0)
    if regen_power_kw is not None and np.isfinite(regen_power_kw).any():
        net = net + np.where(np.isfinite(regen_power_kw), regen_power_kw, 0.0)
    net = np.where(np.isfinite(net), net, 0.0)
    for i in range(n):
        j = np.searchsorted(distance, distance[i] + horizon_km, side='left')
        if j < n and (distance[j] - distance[i]) >= horizon_km * min_frac:
            seg_dt = dt_s[i + 1:j + 1]
            seg_net = net[i + 1:j + 1]
            valid = np.isfinite(seg_dt) & (seg_dt > 0) & (seg_dt <= 300)
            if valid.any():
                energy = np.nansum(seg_net[valid] * seg_dt[valid] / 3600.0)
                result[i] = energy / (distance[j] - distance[i])
    return result


def process_trips(targets_to_compute):
    """One trip at a time; return per-trip target columns as a generator frame."""
    for path in sorted(INTERIM.glob('*_standardized.parquet')):
        frame = pq.read_table(path).to_pandas()
        if 'motor_power_kw' not in frame.columns:
            frame['motor_power_kw'] = np.nan
        if 'regen_power_kw' not in frame.columns:
            frame['regen_power_kw'] = np.nan
        d = np.asarray(frame['distance_km'], dtype=float)
        soc = np.asarray(frame['soc_pct'], dtype=float)
        cap = np.asarray(frame['battery_capacity_kwh'], dtype=float)
        ts = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce')
        time_s = timestamp_to_epoch_seconds(ts)
        dt_s = np.r_[np.nan, np.diff(time_s)]
        dt_s[(dt_s <= 0) | (dt_s > 300)] = np.nan
        motor = np.asarray(frame['motor_power_kw'], dtype=float)
        regen = np.asarray(frame['regen_power_kw'], dtype=float)
        has_motor = frame['motor_power_kw'].notna().any()
        has_regen = frame['regen_power_kw'].notna().any()

        out = pd.DataFrame({'trip_id': frame['trip_id'], 'distance_km': d})
        out['t_soc_5km'] = soc_target(d, soc, cap, 5.0)
        out['t_soc_10km'] = soc_target(d, soc, cap, 10.0)
        out['t_soc_15km'] = soc_target(d, soc, cap, 15.0)
        out['t_pow_5km'] = np.nan
        if has_motor or has_regen:
            out['t_pow_5km'] = power_integrated_target(motor, regen if has_regen else None, dt_s, d, 5.0)
        out['has_power_telemetry'] = bool(has_motor or has_regen)

        # Build the common features for CV evaluation
        frame['_dist'] = d
        frame['_soc'] = soc
        # engineer lightweight versions of common features
        left = {}
        for name, width in [('100m', 0.1), ('500m', 0.5), ('1km', 1.0)]:
            li = np.searchsorted(d, d - width, side='left')
            li = np.minimum(li, np.arange(len(d)))
            left[name] = li
        alt = np.asarray(frame['altitude_m'], dtype=float)
        grad1k = np.divide((alt - alt[left['1km']]) * 100, (d - d[left['1km']]) * 1000,
                           out=np.zeros(len(d)), where=(d - d[left['1km']]) * 1000 >= 50)
        out['current_gradient_pct'] = grad1k
        out['past_1km_gradient_pct'] = grad1k
        out['current_altitude_m'] = alt
        out['current_soc_pct'] = soc
        out['current_soh_pct'] = np.asarray(frame['soh_pct'], dtype=float)
        out['battery_capacity_kwh'] = cap
        out['distance_since_trip_start_km'] = d - (d[0] if np.isfinite(d[0]) else 0.0)
        out['time_since_trip_start_min'] = (time_s - np.nanmin(time_s)) / 60.0
        out['trip_distance_so_far_km'] = out['distance_since_trip_start_km']
        out['trip_elapsed_time_min'] = out['time_since_trip_start_min']
        out['hour_of_day'] = ts.dt.hour.to_numpy()
        out['day_of_week'] = ts.dt.dayofweek.to_numpy()
        out['month'] = ts.dt.month.to_numpy()
        for name in ['100m', '500m', '1km']:
            li = left[name]
            out[f'elevation_gain_{name}'] = np.array([
                np.clip(np.diff(alt[li[i]:i + 1]), 0, None).sum()
                for i in range(len(d))])
            out[f'elevation_loss_{name}'] = np.array([
                -np.clip(np.diff(alt[li[i]:i + 1]), None, 0).sum()
                for i in range(len(d))])
        out['net_elevation_change_1km'] = alt - alt[left['1km']]
        for name in ['500m', '1km']:
            out[f'mean_gradient_{name}'] = np.array([
                np.nanmean(grad1k[left[name][i]:i + 1]) for i in range(len(d))])
            out[f'gradient_std_{name}'] = np.array([
                np.nanstd(grad1k[left[name][i]:i + 1]) for i in range(len(d))])
        out['max_uphill_gradient'] = np.array([
            np.nanmax(grad1k[left['1km'][i]:i + 1]) if np.isfinite(grad1k[left['1km'][i]:i + 1]).any() else np.nan
            for i in range(len(d))])
        out['max_downhill_gradient'] = np.array([
            np.nanmin(grad1k[left['1km'][i]:i + 1]) if np.isfinite(grad1k[left['1km'][i]:i + 1]).any() else np.nan
            for i in range(len(d))])
        out['terrain_variability'] = np.array([
            np.nanstd(grad1k[left['1km'][i]:i + 1]) for i in range(len(d))])
        tc = np.sign(grad1k)
        tc[np.abs(grad1k) <= 1.0] = 0
        out['terrain_transition_count_1km'] = np.array([
            int(np.count_nonzero(np.diff(tc[left['1km'][i]:i + 1]))) for i in range(len(d))])
        out['gradient_direction_changes_1km'] = np.array([
            int(np.count_nonzero(np.diff(tc[left['1km'][i]:i + 1][tc[left['1km'][i]:i + 1] != 0])))
            for i in range(len(d))])
        out['hillyness_score'] = out['terrain_variability'] * (1 + out['gradient_direction_changes_1km'])
        out['uphill_fraction_1km'] = np.array([
            np.mean(grad1k[left['1km'][i]:i + 1] > 1.0) for i in range(len(d))])
        out['downhill_fraction_1km'] = np.array([
            np.mean(grad1k[left['1km'][i]:i + 1] < -1.0) for i in range(len(d))])
        out['flat_fraction_1km'] = 1 - out['uphill_fraction_1km'] - out['downhill_fraction_1km']
        elapsed_s = np.array([np.nansum(dt_s[left['1km'][i]:i + 1]) for i in range(len(d))])
        out['elevation_gain_rate'] = np.divide(out['elevation_gain_1km'].to_numpy(float), elapsed_s,
                                               out=np.full(len(d), np.nan), where=elapsed_s > 0)
        out['elevation_loss_rate'] = np.divide(out['elevation_loss_1km'].to_numpy(float), elapsed_s,
                                               out=np.full(len(d), np.nan), where=elapsed_s > 0)

        yield out
        del frame, out
        gc.collect()


def main():
    start = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)

    print('STEP 7.6 P2-P3: TARGET COMPARISON (clean v2 population)')
    print('=' * 70)

    # ---- Build the target matrix one trip at a time (no concat of raw) ----
    frames = []
    for out in process_trips(None):
        frames.append(out)
        del out
        gc.collect()
    df = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    print(f'Total rows (all trips): {len(df):,}')

    summary = {}
    target_columns = ['t_soc_5km', 't_soc_10km', 't_soc_15km', 't_pow_5km']
    print('\nTarget distributions:')
    for col in target_columns:
        s = df[col]
        summary[col] = {
            'coverage': int(s.notna().sum()),
            'coverage_pct': round(float(s.notna().mean() * 100), 2),
            'mean': round(float(s.mean()), 5),
            'std': round(float(s.std()), 5),
            'min': round(float(s.min()), 5),
            'max': round(float(s.max()), 5),
            'zero_pct': round(float((s == 0).mean() * 100), 2),
            'negative_pct': round(float((s < 0).mean() * 100), 2),
        }
        print(f'  {col:12s} cov={summary[col]["coverage"]:6,} ({summary[col]["coverage_pct"]:5.1f}%)  '
              f'mean={summary[col]["mean"]:.4f} std={summary[col]["std"]:.4f}  '
              f'neg={summary[col]["negative_pct"]:.1f}% zero={summary[col]["zero_pct"]:.1f}%')

    # Noise floor estimate: 1% SOC at the two battery sizes
    summary['noise_floor'] = {
        'nissan_1pct_soc_62kwh': 0.62,   # kWh
        'nissan_per_km_5km': 0.62 / 5.0,
        'dacia_1pct_soc_33kwh': 0.33,
        'dacia_per_km_5km': 0.33 / 5.0,
    }

    # ---- GroupKFold CV predictability of each target ----
    print('\nGroupKFold CV (A_BASIC common features, XGBoost):')
    cv_results = {}
    gkf = GroupKFold(n_splits=5)
    trip_ids = df['trip_id'].values
    for col in ['t_soc_5km', 't_soc_10km', 't_soc_15km']:
        sub = df[['trip_id'] + COMMON_FEATURES + [col]].copy()
        sub = sub.dropna(subset=[col] + COMMON_FEATURES)
        if len(sub) < 2000:
            cv_results[col] = {'n': int(len(sub)), 'mae': None, 'rmse': None, 'r2': None}
            print(f'  {col:12s} n={len(sub):,}  SKIPPED (insufficient)')
            continue
        X = sub[COMMON_FEATURES].values
        y = sub[col].values
        groups = sub['trip_id'].values
        preds = np.full(len(sub), np.nan)
        for tr_idx, va_idx in gkf.split(X, y, groups):
            model = XGBRegressor(n_estimators=150, max_depth=3, learning_rate=0.1,
                                 subsample=0.8, colsample_bytree=0.8, random_state=42)
            model.fit(X[tr_idx], y[tr_idx])
            preds[va_idx] = model.predict(X[va_idx])
        mae = mean_absolute_error(y, preds)
        rmse = np.sqrt(mean_squared_error(y, preds))
        r2 = 1 - np.sum((y - preds) ** 2) / np.sum((y - y.mean()) ** 2)
        cv_results[col] = {'n': int(len(sub)), 'mae': round(float(mae), 5),
                           'rmse': round(float(rmse), 5), 'r2': round(float(r2), 4)}
        print(f'  {col:12s} n={len(sub):,}  MAE={mae:.4f}  RMSE={rmse:.4f}  R2={r2:+.3f}')

    summary['cv'] = cv_results

    # ---- Hybrid target note (power-integrated needs motor/regen, Nissan-only) ----
    pow_cov = df.loc[df['has_power_telemetry'], 't_pow_5km'].notna().sum()
    summary['hybrid_note'] = (
        'Power-integrated target requires motor/regen telemetry (Nissan only, '
        f'{int(pow_cov):,} samples). A hybrid target would use power-integrated '
        'for Nissan and SOC-derived for Dacia, but the two are NOT comparable '
        'across vehicles (different bias/noise), so a single cross-vehicle '
        'target must remain SOC-derived. Power-integrated is evaluated as a '
        'vehicle-specific alternative in P7.'
    )

    with open(OUTPUT, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f'\nSaved {OUTPUT}')
    print(f'Runtime: {time.time() - start:.1f}s')


if __name__ == '__main__':
    main()