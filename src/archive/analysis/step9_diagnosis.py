"""
STEP 9: Model Diagnosis, Error Analysis & Final Test Evaluation.

This module performs the VALIDATION-side diagnosis (9B-9O):
- Baseline recheck using TRAIN-only statistics
- Best-model validation predictions and error analysis
- Error breakdowns by vehicle / terrain / speed / SOC / target range
- Negative-target analysis
- Feature importance (RF + XGB)
- Model vs baseline diagnosis
- Trip-level performance
- Distribution shift (train vs validation)

CRITICAL: The TEST set is NOT touched by this module.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
import joblib
import time
import warnings
import tracemalloc
from typing import Dict, Tuple, List

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'processed'
MODELS_DIR = PROJECT_ROOT / 'models' / 'step8'
REPORTS_DIR = PROJECT_ROOT / 'reports'
FIGURES_DIR = REPORTS_DIR / 'figures' / 'step9'
DOCS_DIR = PROJECT_ROOT / 'docs'

TARGET_COL = 'target_future_energy_kwh_per_km'
RANDOM_SEED = 42

A_BASIC_FEATURES = [
    'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',
    'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',
    'terrain_class', 'elevation_gain_1km', 'elevation_loss_1km'
]


def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return np.nan
    return float(1 - ss_res / ss_tot)


def smape(y_true, y_pred):
    denominator = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    diff = np.abs(y_true - y_pred) / denominator
    diff[denominator == 0] = 0
    return float(np.mean(diff) * 100)


def metrics_dict(y_true, y_pred) -> Dict:
    return {
        'MAE': mae(y_true, y_pred),
        'RMSE': rmse(y_true, y_pred),
        'R2': r2(y_true, y_pred),
        'SMAPE': smape(y_true, y_pred),
        'samples': int(len(y_true)),
        'mean_signed_error': float(np.mean(y_pred - y_true)),
        'median_signed_error': float(np.median(y_pred - y_true)),
        'std_signed_error': float(np.std(y_pred - y_true)),
        'p90_abs_error': float(np.percentile(np.abs(y_true - y_pred), 90)),
        'p95_abs_error': float(np.percentile(np.abs(y_true - y_pred), 95)),
    }


def encode_categorical(X: pd.DataFrame, categorical_cols: List[str]) -> pd.DataFrame:
    """Encode categorical columns using the same approach as training (codes)."""
    X_enc = X.copy()
    for col in categorical_cols:
        X_enc[col] = pd.Categorical(X_enc[col]).codes
    return X_enc


def predict_model(model, X: pd.DataFrame) -> np.ndarray:
    """Predict using a step8 model, handling categorical encoding."""
    if hasattr(model, '_categorical_cols'):
        cat_cols = model._categorical_cols
        X_enc = encode_categorical(X, cat_cols)
        return model.predict(X_enc)
    return model.predict(X)


def global_mean_baseline(train_df: pd.DataFrame, eval_df: pd.DataFrame) -> np.ndarray:
    """Predict train-set global mean for all eval samples."""
    mean = train_df[TARGET_COL].mean()
    return np.full(len(eval_df), mean, dtype=float)


def vehicle_mean_baseline(train_df: pd.DataFrame, eval_df: pd.DataFrame) -> np.ndarray:
    """Predict per-vehicle training mean; fallback to global mean."""
    means = train_df.groupby('vehicle_id')[TARGET_COL].mean()
    counts = train_df.groupby('vehicle_id')['trip_id'].nunique()
    global_mean = train_df[TARGET_COL].mean()
    preds = np.empty(len(eval_df), dtype=float)
    for i, vid in enumerate(eval_df['vehicle_id'].values):
        if vid in means.index and counts.get(vid, 0) >= 2:
            preds[i] = means[vid]
        else:
            preds[i] = global_mean
    return preds


def main():
    start = time.time()
    tracemalloc.start()

    print('=' * 70)
    print('STEP 9: MODEL DIAGNOSIS & ERROR ANALYSIS (VALIDATION SIDE)')
    print('=' * 70)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------
    # Load data (train + validation ONLY)
    # ---------------------------------------------------------------
    print('\n[9A] Loading train + validation...')
    train_df = pd.read_parquet(DATA_DIR / 'v2_train.parquet')
    val_df = pd.read_parquet(DATA_DIR / 'v2_validation.parquet')
    print(f'  Train: {len(train_df)} samples, {train_df.trip_id.nunique()} trips')
    print(f'  Validation: {len(val_df)} samples, {val_df.trip_id.nunique()} trips')

    # ---------------------------------------------------------------
    # 9B - Validation baseline recheck (TRAIN stats only)
    # ---------------------------------------------------------------
    print('\n[9B] Validation baseline recheck...')
    y_val = val_df[TARGET_COL].values

    global_mean_pred = global_mean_baseline(train_df, val_df)
    vehicle_mean_pred = vehicle_mean_baseline(train_df, val_df)

    baseline_rows = []
    baseline_rows.append({'Model': 'Global Mean Baseline', **metrics_dict(y_val, global_mean_pred)})
    baseline_rows.append({'Model': 'Vehicle Mean Baseline', **metrics_dict(y_val, vehicle_mean_pred)})

    # Load A_BASIC models for comparison
    ridge_model = joblib.load(MODELS_DIR / 'A_BASIC_Ridge.joblib')
    rf_model = joblib.load(MODELS_DIR / 'A_BASIC_RF.joblib')
    xgb_model = joblib.load(MODELS_DIR / 'A_BASIC_XGB.joblib')

    X_val_a = val_df[A_BASIC_FEATURES].copy()
    X_train_a = train_df[A_BASIC_FEATURES].copy()

    # Models trained on the FULL train population (A_BASIC is 100% complete)
    for name, model in [('A_BASIC Ridge', ridge_model),
                        ('A_BASIC RandomForest', rf_model),
                        ('A_BASIC XGBoost', xgb_model)]:
        pred = predict_model(model, X_val_a)
        baseline_rows.append({'Model': name, **metrics_dict(y_val, pred)})

    baselines_df = pd.DataFrame(baseline_rows)
    baselines_df.to_csv(REPORTS_DIR / 'step9_validation_baselines.csv', index=False)
    print(f'  Saved reports/step9_validation_baselines.csv')
    print(baselines_df[['Model', 'MAE', 'RMSE', 'R2', 'SMAPE']].to_string(index=False))

    # ---------------------------------------------------------------
    # 9C - Best model validation predictions (A_BASIC + XGBoost)
    # ---------------------------------------------------------------
    print('\n[9C] Generating validation predictions with A_BASIC + XGBoost...')
    xgb_pred = predict_model(xgb_model, X_val_a)

    pred_df = val_df[['trip_id', 'vehicle_id', 'timestamp', 'vehicle_model',
                      'current_soc_pct', 'current_altitude_m', 'current_gradient_pct',
                      'terrain_class', 'current_speed_kmh', 'has_speed_data']].copy()
    pred_df['sample_id'] = np.arange(len(pred_df))
    pred_df['target'] = y_val
    pred_df['prediction'] = xgb_pred
    pred_df['signed_error'] = xgb_pred - y_val
    pred_df['absolute_error'] = np.abs(xgb_pred - y_val)

    # Save with index for stable sample_id
    pred_df.to_parquet(DATA_DIR / 'validation_predictions_step9.parquet', index=False)
    print(f'  Saved data/processed/validation_predictions_step9.parquet ({len(pred_df)} rows)')

    # ---------------------------------------------------------------
    # 9D - Error distribution
    # ---------------------------------------------------------------
    print('\n[9D] Error distribution...')
    err_metrics = metrics_dict(y_val, xgb_pred)
    print(f'  MAE: {err_metrics["MAE"]:.6f}')
    print(f'  RMSE: {err_metrics["RMSE"]:.6f}')
    print(f'  R2: {err_metrics["R2"]:.4f}')
    print(f'  SMAPE: {err_metrics["SMAPE"]:.2f}%')
    print(f'  mean signed error: {err_metrics["mean_signed_error"]:.6f}')
    print(f'  median signed error: {err_metrics["median_signed_error"]:.6f}')
    print(f'  std signed error: {err_metrics["std_signed_error"]:.6f}')
    print(f'  P90 abs error: {err_metrics["p90_abs_error"]:.6f}')
    print(f'  P95 abs error: {err_metrics["p95_abs_error"]:.6f}')

    # ---------------------------------------------------------------
    # 9E - Error by vehicle
    # ---------------------------------------------------------------
    print('\n[9E] Error by vehicle...')
    vehicle_rows = []
    for vid, group in pred_df.groupby('vehicle_model'):
        m = metrics_dict(group['target'].values, group['prediction'].values)
        vehicle_rows.append({
            'vehicle': vid,
            'sample_count': len(group),
            'MAE': m['MAE'], 'RMSE': m['RMSE'], 'R2': m['R2'],
            'mean_error': m['mean_signed_error'],
            'median_error': m['median_signed_error'],
        })
    vehicle_err_df = pd.DataFrame(vehicle_rows)
    vehicle_err_df.to_csv(REPORTS_DIR / 'error_by_vehicle.csv', index=False)
    print(vehicle_err_df.to_string(index=False))

    # ---------------------------------------------------------------
    # 9F - Error by terrain
    # ---------------------------------------------------------------
    print('\n[9F] Error by terrain...')
    terrain_rows = []
    for terrain, group in pred_df.groupby('terrain_class'):
        t = group['target'].values
        p = group['prediction'].values
        m = metrics_dict(t, p)
        terrain_rows.append({
            'terrain': terrain,
            'sample_count': len(group),
            'MAE': m['MAE'], 'RMSE': m['RMSE'], 'R2': m['R2'],
            'mean_signed_error': m['mean_signed_error'],
            'negative_target_pct': float((t < 0).mean() * 100),
        })
    terrain_err_df = pd.DataFrame(terrain_rows)
    terrain_err_df.to_csv(REPORTS_DIR / 'error_by_terrain.csv', index=False)
    print(terrain_err_df.to_string(index=False))

    # ---------------------------------------------------------------
    # 9G - Error by speed (reliable speed subset only)
    # ---------------------------------------------------------------
    print('\n[9G] Error by speed...')
    speed_df = pred_df[pred_df['has_speed_data'] == True].copy()
    print(f'  Population: {len(speed_df)}/{len(pred_df)} samples with reliable speed')
    bins = [0, 20, 40, 60, np.inf]
    labels = ['0-20', '20-40', '40-60', '60+']
    speed_df['speed_bin'] = pd.cut(speed_df['current_speed_kmh'], bins=bins, labels=labels, right=False)
    speed_rows = []
    for bin_label, group in speed_df.groupby('speed_bin', observed=True):
        if len(group) == 0:
            continue
        m = metrics_dict(group['target'].values, group['prediction'].values)
        speed_rows.append({
            'speed_bin': str(bin_label),
            'sample_count': len(group),
            'MAE': m['MAE'], 'RMSE': m['RMSE'],
            'mean_error': m['mean_signed_error'],
        })
    speed_err_df = pd.DataFrame(speed_rows)
    speed_err_df.to_csv(REPORTS_DIR / 'error_by_speed.csv', index=False)
    print(f'  Saved reports/error_by_speed.csv (population: samples with reliable speed)')
    print(speed_err_df.to_string(index=False))

    # ---------------------------------------------------------------
    # 9H - Error by SOC
    # ---------------------------------------------------------------
    print('\n[9H] Error by SOC...')
    soc_bins = [0, 20, 40, 60, 80, 100]
    soc_labels = ['0-20', '20-40', '40-60', '60-80', '80-100']
    pred_df['soc_bin'] = pd.cut(pred_df['current_soc_pct'], bins=soc_bins, labels=soc_labels, right=False)
    soc_rows = []
    for bin_label, group in pred_df.groupby('soc_bin', observed=True):
        m = metrics_dict(group['target'].values, group['prediction'].values)
        soc_rows.append({
            'soc_bin': str(bin_label),
            'sample_count': len(group),
            'MAE': m['MAE'], 'RMSE': m['RMSE'],
            'mean_error': m['mean_signed_error'],
        })
    soc_err_df = pd.DataFrame(soc_rows)
    soc_err_df.to_csv(REPORTS_DIR / 'error_by_soc.csv', index=False)
    print(soc_err_df.to_string(index=False))

    # ---------------------------------------------------------------
    # 9I - Error by target range
    # ---------------------------------------------------------------
    print('\n[9I] Error by target range...')
    target_bins = [-np.inf, 0, 0.05, 0.10, 0.15, 0.20, 0.30, np.inf]
    target_labels = ['negative', '0-0.05', '0.05-0.10', '0.10-0.15', '0.15-0.20', '0.20-0.30', '>0.30']
    pred_df['target_bin'] = pd.cut(pred_df['target'], bins=target_bins, labels=target_labels, right=False)
    target_rows = []
    for bin_label, group in pred_df.groupby('target_bin', observed=True):
        m = metrics_dict(group['target'].values, group['prediction'].values)
        target_rows.append({
            'target_bin': str(bin_label),
            'sample_count': len(group),
            'MAE': m['MAE'], 'RMSE': m['RMSE'],
            'mean_error': m['mean_signed_error'],
        })
    target_err_df = pd.DataFrame(target_rows)
    target_err_df.to_csv(REPORTS_DIR / 'error_by_target_range.csv', index=False)
    print(target_err_df.to_string(index=False))

    # ---------------------------------------------------------------
    # 9J - Negative target analysis
    # ---------------------------------------------------------------
    print('\n[9J] Negative target analysis...')
    neg_df = pred_df[pred_df['target'] < 0]
    pos_df = pred_df[pred_df['target'] >= 0]
    print(f'  Negative targets: {len(neg_df)} samples')
    print(f'  Non-negative targets: {len(pos_df)} samples')

    neg_metrics = metrics_dict(neg_df['target'].values, neg_df['prediction'].values)
    pos_metrics = metrics_dict(pos_df['target'].values, pos_df['prediction'].values)
    print(f'  Negative targets - MAE: {neg_metrics["MAE"]:.6f}, mean error: {neg_metrics["mean_signed_error"]:.6f}')
    print(f'  Non-negative targets - MAE: {pos_metrics["MAE"]:.6f}, mean error: {pos_metrics["mean_signed_error"]:.6f}')

    neg_breakdown = {'negative_target_count': len(neg_df), 'non_negative_count': len(pos_df)}
    if len(neg_df) > 0:
        for key, group in neg_df.groupby('terrain_class'):
            m = metrics_dict(group['target'].values, group['prediction'].values)
            neg_breakdown[f'neg_{key}_MAE'] = m['MAE']
            neg_breakdown[f'neg_{key}_mean_err'] = m['mean_signed_error']
            neg_breakdown[f'neg_{key}_count'] = len(group)
        neg_speed = neg_df[neg_df['has_speed_data'] == True]
        if len(neg_speed) > 0:
            m = metrics_dict(neg_speed['target'].values, neg_speed['prediction'].values)
            neg_breakdown['neg_speed_subset_MAE'] = m['MAE']
            neg_breakdown['neg_speed_subset_count'] = len(neg_speed)
        for vid, group in neg_df.groupby('vehicle_model'):
            m = metrics_dict(group['target'].values, group['prediction'].values)
            neg_breakdown[f'neg_{vid}_MAE'] = m['MAE']
            neg_breakdown[f'neg_{vid}_count'] = len(group)

    with open(DOCS_DIR / 'step9_negative_target_data.json', 'w') as f:
        json.dump(neg_breakdown, f, indent=2)

    # ---------------------------------------------------------------
    # 9K - Feature importance
    # ---------------------------------------------------------------
    print('\n[9K] Feature importance...')
    importance_rows = []
    for feature in A_BASIC_FEATURES:
        row = {'feature': feature}
        if feature in rf_model.feature_importances_.__dir__() or True:
            try:
                fi_idx = list(rf_model._feature_names).index(feature)
                row['random_forest_importance'] = rf_model.feature_importances_[fi_idx]
            except (ValueError, AttributeError):
                row['random_forest_importance'] = np.nan
            try:
                fi_idx = list(xgb_model._feature_names).index(feature)
                row['xgboost_importance'] = xgb_model.feature_importances_[fi_idx]
            except (ValueError, AttributeError):
                row['xgboost_importance'] = np.nan
        importance_rows.append(row)

    imp_df = pd.DataFrame(importance_rows)
    imp_df = imp_df.sort_values('xgboost_importance', ascending=False)
    imp_df.to_csv(REPORTS_DIR / 'step9_feature_importance.csv', index=False)
    print(imp_df.to_string(index=False))

    # ---------------------------------------------------------------
    # 9L - Feature group importance
    # ---------------------------------------------------------------
    print('\n[9L] Feature group importance...')
    group_map = {
        'current_soc_pct': 'Battery', 'current_soh_pct': 'Battery', 'battery_capacity_kwh': 'Battery',
        'current_altitude_m': 'Terrain', 'current_gradient_pct': 'Terrain', 'past_1km_gradient_pct': 'Terrain',
        'terrain_class': 'Terrain', 'elevation_gain_1km': 'Terrain', 'elevation_loss_1km': 'Terrain',
    }
    imp_df['group'] = imp_df['feature'].map(group_map)
    group_imp = imp_df.groupby('group')[['random_forest_importance', 'xgboost_importance']].sum().reset_index()
    group_imp = group_imp.sort_values('xgboost_importance', ascending=False)
    group_imp.to_csv(REPORTS_DIR / 'step9_feature_group_importance.csv', index=False)
    print(group_imp.to_string(index=False))

    # ---------------------------------------------------------------
    # 9N - Trip-level performance
    # ---------------------------------------------------------------
    print('\n[9N] Trip-level performance...')
    trip_rows = []
    for trip_id, group in pred_df.groupby('trip_id'):
        t = group['target'].values
        p = group['prediction'].values
        m = metrics_dict(t, p)
        trip_rows.append({
            'trip_id': trip_id,
            'vehicle': group['vehicle_model'].iloc[0],
            'sample_count': len(group),
            'MAE': m['MAE'], 'RMSE': m['RMSE'],
            'mean_target': float(t.mean()),
            'target_std': float(t.std()),
            'negative_target_pct': float((t < 0).mean() * 100),
        })
    trip_perf = pd.DataFrame(trip_rows).sort_values('MAE', ascending=False)
    trip_perf.to_csv(REPORTS_DIR / 'step9_trip_performance.csv', index=False)
    print(f'  Saved reports/step9_trip_performance.csv ({len(trip_perf)} trips)')
    print(trip_perf.to_string(index=False))

    # ---------------------------------------------------------------
    # 9O - Distribution shift (train vs validation)
    # ---------------------------------------------------------------
    print('\n[9O] Distribution shift (train vs validation)...')
    shift_lines = []
    shift_lines.append('# Step 9O: Validation Distribution Shift Analysis')
    shift_lines.append('')
    shift_lines.append('Comparison of TRAIN vs VALIDATION distributions.')
    shift_lines.append('Test set NOT used.')
    shift_lines.append('')

    shift_cols = ['target_future_energy_kwh_per_km', 'current_soc_pct', 'current_altitude_m',
                  'current_gradient_pct', 'battery_capacity_kwh']
    shift_lines.append('| Feature | Train mean | Val mean | Train std | Val std | Shift (val-train)/train_std |')
    shift_lines.append('|---------|-----------|----------|-----------|---------|---------------------------|')
    for col in shift_cols:
        tm, ts = train_df[col].mean(), train_df[col].std()
        vm, vs = val_df[col].mean(), val_df[col].std()
        if ts != 0:
            norm_shift = (vm - tm) / ts
        else:
            norm_shift = np.nan
        shift_lines.append(f'| {col} | {tm:.4f} | {vm:.4f} | {ts:.4f} | {vs:.4f} | {norm_shift:.3f} |')

    shift_lines.append('')
    shift_lines.append('## Categorical Distribution')
    shift_lines.append('')
    shift_lines.append('### Terrain class')
    shift_lines.append('| Terrain | Train % | Validation % |')
    shift_lines.append('|---------|---------|--------------|')
    train_terrain = train_df['terrain_class'].value_counts(normalize=True) * 100
    val_terrain = val_df['terrain_class'].value_counts(normalize=True) * 100
    for terrain in ['FLAT', 'UPHILL', 'DOWNHILL']:
        shift_lines.append(f'| {terrain} | {train_terrain.get(terrain, 0):.1f} | {val_terrain.get(terrain, 0):.1f} |')

    shift_lines.append('')
    shift_lines.append('### Vehicle')
    shift_lines.append('| Vehicle | Train % | Validation % |')
    shift_lines.append('|---------|---------|--------------|')
    for vid in ['Dacia Spring', 'Nissan Leaf']:
        train_pct = (train_df['vehicle_model'] == vid).mean() * 100
        val_pct = (val_df['vehicle_model'] == vid).mean() * 100
        shift_lines.append(f'| {vid} | {train_pct:.1f} | {val_pct:.1f} |')

    shift_lines.append('')
    shift_lines.append('## Interpretation')
    shift_lines.append('')
    shift_lines.append('A normalized shift magnitude > 0.5 indicates a notable distribution difference.')
    shift_lines.append('')

    with open(REPORTS_DIR / 'step9_distribution_shift.md', 'w') as f:
        f.write('\n'.join(shift_lines))
    print('  Saved reports/step9_distribution_shift.md')

    # ---------------------------------------------------------------
    # 9M - Model vs baseline diagnosis summary
    # ---------------------------------------------------------------
    print('\n[9M] Model vs baseline diagnosis...')
    xgb_mae = metrics_dict(y_val, xgb_pred)['MAE']
    mean_base_mae = metrics_dict(y_val, global_mean_pred)['MAE']
    veh_base_mae = metrics_dict(y_val, vehicle_mean_pred)['MAE']
    print(f'  XGBoost MAE: {xgb_mae:.6f}')
    print(f'  Global mean baseline MAE: {mean_base_mae:.6f}')
    print(f'  Vehicle mean baseline MAE: {veh_base_mae:.6f}')
    print(f'  XGBoost vs global mean: {100 * (xgb_mae - mean_base_mae) / mean_base_mae:+.1f}%')

    # Peak memory & time
    current, peak = tracemalloc.get_traced_memory()
    elapsed = time.time() - start
    print(f'\n  Peak RAM: {peak / 1024 / 1024:.2f} MB')
    print(f'  Runtime: {elapsed:.2f}s')

    # Save a small summary JSON
    summary = {
        'validation_global_mean_baseline_MAE': mean_base_mae,
        'validation_vehicle_mean_baseline_MAE': veh_base_mae,
        'validation_xgboost_MAE': xgb_mae,
        'validation_xgboost_R2': metrics_dict(y_val, xgb_pred)['R2'],
        'validation_negative_target_count': int((y_val < 0).sum()),
        'peak_ram_mb': peak / 1024 / 1024,
        'runtime_s': elapsed,
    }
    with open(REPORTS_DIR / 'step9_validation_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    print('\n' + '=' * 70)
    print('STEP 9 VALIDATION-SIDE DIAGNOSIS COMPLETE')
    print('=' * 70)

    return summary


if __name__ == '__main__':
    summary = main()