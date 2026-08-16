"""
STEP 9R-9U: FINAL TEST EVALUATION.

The FIRST and ONLY use of the test set.
Applies the frozen A_BASIC + XGBoost candidate to v2_test.parquet.

- 9R: Overall test metrics (MAE, RMSE, R², SMAPE, signed error, P90/P95)
- 9S: Test baselines from TRAIN stats only (global mean, vehicle mean)
- 9T: Test breakdown by vehicle / terrain / SOC / target range / speed
- 9U: Final prediction file
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
import joblib
import time
import tracemalloc
import warnings

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'processed'
MODELS_DIR = PROJECT_ROOT / 'models' / 'step8'
REPORTS_DIR = PROJECT_ROOT / 'reports'
FIGURES_DIR = REPORTS_DIR / 'figures' / 'step9'

TARGET_COL = 'target_future_energy_kwh_per_km'
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


def metrics_dict(y_true, y_pred) -> dict:
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


def encode_categorical(X, categorical_cols):
    X_enc = X.copy()
    for col in categorical_cols:
        X_enc[col] = pd.Categorical(X_enc[col]).codes
    return X_enc


def predict_model(model, X):
    if hasattr(model, '_categorical_cols'):
        return model.predict(encode_categorical(X, model._categorical_cols))
    return model.predict(X)


def main():
    start = time.time()
    tracemalloc.start()

    print('=' * 70)
    print('STEP 9R-9U: FINAL TEST EVALUATION')
    print('This is the FIRST use of the test set.')
    print('=' * 70)

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------
    # Load frozen model + train (for baseline stats) + test
    # ---------------------------------------------------------------
    print('\nLoading frozen model and data...')
    xgb_model = joblib.load(MODELS_DIR / 'A_BASIC_XGB.joblib')
    train_df = pd.read_parquet(DATA_DIR / 'v2_train.parquet')
    test_df = pd.read_parquet(DATA_DIR / 'v2_test.parquet')

    print(f'  Test: {len(test_df)} samples, {test_df.trip_id.nunique()} trips')
    print(f'  Test vehicles: {dict(test_df.groupby("vehicle_model").size())}')

    y_test = test_df[TARGET_COL].values
    X_test = test_df[A_BASIC_FEATURES].copy()

    # ---------------------------------------------------------------
    # 9R - Final test metrics (frozen candidate)
    # ---------------------------------------------------------------
    print('\n[9R] Final test evaluation (frozen A_BASIC + XGBoost)...')
    pred = predict_model(xgb_model, X_test)
    test_metrics = metrics_dict(y_test, pred)
    print(f'  MAE: {test_metrics["MAE"]:.6f}')
    print(f'  RMSE: {test_metrics["RMSE"]:.6f}')
    print(f'  R2: {test_metrics["R2"]:.4f}')
    print(f'  SMAPE: {test_metrics["SMAPE"]:.2f}%')
    print(f'  mean signed error: {test_metrics["mean_signed_error"]:.6f}')
    print(f'  median signed error: {test_metrics["median_signed_error"]:.6f}')
    print(f'  P90 abs error: {test_metrics["p90_abs_error"]:.6f}')
    print(f'  P95 abs error: {test_metrics["p95_abs_error"]:.6f}')

    # ---------------------------------------------------------------
    # 9S - Test baselines from TRAIN stats only
    # ---------------------------------------------------------------
    print('\n[9S] Test baselines (TRAIN stats only)...')

    # Global mean baseline
    global_mean = train_df[TARGET_COL].mean()
    gm_pred = np.full(len(test_df), global_mean, dtype=float)
    gm_metrics = metrics_dict(y_test, gm_pred)

    # Vehicle mean baseline
    means = train_df.groupby('vehicle_id')[TARGET_COL].mean()
    counts = train_df.groupby('vehicle_id')['trip_id'].nunique()
    vm_pred = np.empty(len(test_df), dtype=float)
    for i, vid in enumerate(test_df['vehicle_id'].values):
        if vid in means.index and counts.get(vid, 0) >= 2:
            vm_pred[i] = means[vid]
        else:
            vm_pred[i] = global_mean
    vm_metrics = metrics_dict(y_test, vm_pred)

    print(f'  Global mean baseline MAE: {gm_metrics["MAE"]:.6f}, RMSE: {gm_metrics["RMSE"]:.6f}')
    print(f'  Vehicle mean baseline MAE: {vm_metrics["MAE"]:.6f}, RMSE: {vm_metrics["RMSE"]:.6f}')
    print(f'  Frozen model MAE: {test_metrics["MAE"]:.6f}')
    print(f'  Improvement vs global mean: {100 * (gm_metrics["MAE"] - test_metrics["MAE"]) / gm_metrics["MAE"]:+.1f}%')
    print(f'  Improvement vs vehicle mean: {100 * (vm_metrics["MAE"] - test_metrics["MAE"]) / vm_metrics["MAE"]:+.1f}%')

    baseline_comparison = pd.DataFrame([
        {'Model': 'Global Mean Baseline', **{k: v for k, v in gm_metrics.items()}},
        {'Model': 'Vehicle Mean Baseline', **{k: v for k, v in vm_metrics.items()}},
        {'Model': 'Frozen A_BASIC XGBoost', **{k: v for k, v in test_metrics.items()}},
    ])
    baseline_comparison.to_csv(REPORTS_DIR / 'step9_test_baseline_comparison.csv', index=False)
    print('  Saved reports/step9_test_baseline_comparison.csv')

    # ---------------------------------------------------------------
    # 9T - Final test breakdowns
    # ---------------------------------------------------------------
    print('\n[9T] Final test breakdowns...')

    # Build prediction frame
    test_pred_df = test_df[['trip_id', 'vehicle_id', 'timestamp', 'vehicle_model',
                            'current_soc_pct', 'current_altitude_m', 'current_gradient_pct',
                            'terrain_class', 'current_speed_kmh', 'has_speed_data']].copy()
    test_pred_df['sample_id'] = np.arange(len(test_pred_df))
    test_pred_df['actual_target'] = y_test
    test_pred_df['predicted_target'] = pred
    test_pred_df['signed_error'] = pred - y_test
    test_pred_df['absolute_error'] = np.abs(pred - y_test)

    # Overall results file
    final_results = pd.DataFrame([{
        'metric': k, 'value': v, 'model': 'A_BASIC_XGBoost'
    } for k, v in test_metrics.items()])
    final_results.to_csv(REPORTS_DIR / 'final_test_results.csv', index=False)
    print('  Saved reports/final_test_results.csv')

    # By vehicle
    vehicle_rows = []
    for vid, group in test_pred_df.groupby('vehicle_model'):
        m = metrics_dict(group['actual_target'].values, group['predicted_target'].values)
        vehicle_rows.append({'vehicle': vid, 'sample_count': len(group),
                             'MAE': m['MAE'], 'RMSE': m['RMSE'], 'R2': m['R2'],
                             'mean_error': m['mean_signed_error']})
    by_vehicle = pd.DataFrame(vehicle_rows)
    by_vehicle.to_csv(REPORTS_DIR / 'final_test_by_vehicle.csv', index=False)
    print('  Saved reports/final_test_by_vehicle.csv')

    # By terrain
    terrain_rows = []
    for terrain, group in test_pred_df.groupby('terrain_class'):
        m = metrics_dict(group['actual_target'].values, group['predicted_target'].values)
        terrain_rows.append({'terrain': terrain, 'sample_count': len(group),
                             'MAE': m['MAE'], 'RMSE': m['RMSE'], 'R2': m['R2'],
                             'mean_error': m['mean_signed_error']})
    by_terrain = pd.DataFrame(terrain_rows)
    by_terrain.to_csv(REPORTS_DIR / 'final_test_by_terrain.csv', index=False)
    print('  Saved reports/final_test_by_terrain.csv')

    # By SOC
    test_pred_df['soc_bin'] = pd.cut(test_pred_df['current_soc_pct'],
                                     bins=[0, 20, 40, 60, 80, 100],
                                     labels=['0-20', '20-40', '40-60', '60-80', '80-100'],
                                     right=False)
    soc_rows = []
    for bin_label, group in test_pred_df.groupby('soc_bin', observed=True):
        m = metrics_dict(group['actual_target'].values, group['predicted_target'].values)
        soc_rows.append({'soc_bin': str(bin_label), 'sample_count': len(group),
                         'MAE': m['MAE'], 'RMSE': m['RMSE'], 'mean_error': m['mean_signed_error']})
    by_soc = pd.DataFrame(soc_rows)
    by_soc.to_csv(REPORTS_DIR / 'final_test_by_soc.csv', index=False)
    print('  Saved reports/final_test_by_soc.csv')

    # By target range
    test_pred_df['target_bin'] = pd.cut(test_pred_df['actual_target'],
                                        bins=[-np.inf, 0, 0.05, 0.10, 0.15, 0.20, 0.30, np.inf],
                                        labels=['negative', '0-0.05', '0.05-0.10', '0.10-0.15',
                                                '0.15-0.20', '0.20-0.30', '>0.30'], right=False)
    target_rows = []
    for bin_label, group in test_pred_df.groupby('target_bin', observed=True):
        m = metrics_dict(group['actual_target'].values, group['predicted_target'].values)
        target_rows.append({'target_bin': str(bin_label), 'sample_count': len(group),
                            'MAE': m['MAE'], 'RMSE': m['RMSE'], 'mean_error': m['mean_signed_error']})
    by_target = pd.DataFrame(target_rows)
    by_target.to_csv(REPORTS_DIR / 'final_test_by_target_range.csv', index=False)
    print('  Saved reports/final_test_by_target_range.csv')

    # By speed (reliable speed subset)
    speed_df = test_pred_df[test_pred_df['has_speed_data'] == True].copy()
    speed_df['speed_bin'] = pd.cut(speed_df['current_speed_kmh'],
                                   bins=[0, 20, 40, 60, np.inf],
                                   labels=['0-20', '20-40', '40-60', '60+'], right=False)
    speed_rows = []
    for bin_label, group in speed_df.groupby('speed_bin', observed=True):
        m = metrics_dict(group['actual_target'].values, group['predicted_target'].values)
        speed_rows.append({'speed_bin': str(bin_label), 'sample_count': len(group),
                           'MAE': m['MAE'], 'RMSE': m['RMSE'], 'mean_error': m['mean_signed_error']})
    by_speed = pd.DataFrame(speed_rows)
    by_speed.to_csv(REPORTS_DIR / 'final_test_by_speed.csv', index=False)
    print(f'  Saved reports/final_test_by_speed.csv (population: {len(speed_df)} samples with reliable speed)')

    # ---------------------------------------------------------------
    # 9U - Final prediction file
    # ---------------------------------------------------------------
    print('\n[9U] Saving final prediction file...')
    final_pred_file = test_pred_df[['sample_id', 'trip_id', 'vehicle_id', 'timestamp',
                                    'actual_target', 'predicted_target',
                                    'signed_error', 'absolute_error']].copy()
    final_pred_file.to_parquet(DATA_DIR / 'test_predictions_final.parquet', index=False)
    print(f'  Saved data/processed/test_predictions_final.parquet ({len(final_pred_file)} rows)')

    # Peak memory & time
    current, peak = tracemalloc.get_traced_memory()
    elapsed = time.time() - start
    print(f'\n  Peak RAM: {peak / 1024 / 1024:.2f} MB')
    print(f'  Runtime: {elapsed:.2f}s')

    # Save summary
    summary = {
        'test_global_mean_baseline_MAE': gm_metrics['MAE'],
        'test_vehicle_mean_baseline_MAE': vm_metrics['MAE'],
        'test_frozen_model_MAE': test_metrics['MAE'],
        'test_frozen_model_RMSE': test_metrics['RMSE'],
        'test_frozen_model_R2': test_metrics['R2'],
        'test_frozen_model_SMAPE': test_metrics['SMAPE'],
        'test_improvement_vs_global_mean_pct': 100 * (gm_metrics['MAE'] - test_metrics['MAE']) / gm_metrics['MAE'],
        'test_improvement_vs_vehicle_mean_pct': 100 * (vm_metrics['MAE'] - test_metrics['MAE']) / vm_metrics['MAE'],
        'peak_ram_mb': peak / 1024 / 1024,
        'runtime_s': elapsed,
    }
    with open(REPORTS_DIR / 'step9_test_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    print('\n  Saved reports/step9_test_summary.json')

    print('\n' + '=' * 70)
    print('STEP 9 FINAL TEST EVALUATION COMPLETE')
    print('=' * 70)

    return summary


if __name__ == '__main__':
    summary = main()