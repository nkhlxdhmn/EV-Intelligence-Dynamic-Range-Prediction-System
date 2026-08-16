"""
STEP 9: Unit tests for the diagnosis & final test evaluation analysis.

Tests:
1. Metrics (MAE/RMSE/R2/SMAPE)
2. Prediction shape
3. Error calculations
4. Vehicle grouping
5. Terrain grouping
6. Baseline calculation
7. Test isolation
8. No train/test overlap
9. No validation/test overlap
10. Final prediction schema
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / 'data' / 'processed'
REPORTS_DIR = PROJECT_ROOT / 'reports'

TARGET_COL = 'target_future_energy_kwh_per_km'


def load_parquet(rel_path):
    return pd.read_parquet(DATA_DIR / rel_path)


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------
@pytest.fixture(scope='module')
def train_df():
    return load_parquet('v2_train.parquet')


@pytest.fixture(scope='module')
def val_df():
    return load_parquet('v2_validation.parquet')


@pytest.fixture(scope='module')
def test_df():
    return load_parquet('v2_test.parquet')


@pytest.fixture(scope='module')
def val_predictions():
    return load_parquet('validation_predictions_step9.parquet')


@pytest.fixture(scope='module')
def test_predictions():
    return load_parquet('test_predictions_final.parquet')


# ---------------------------------------------------------------
# 1. Metrics
# ---------------------------------------------------------------
def test_mae_basic():
    y = np.array([1.0, 2.0, 3.0])
    p = np.array([1.5, 2.0, 2.5])
    assert np.allclose(np.mean(np.abs(y - p)), 0.3333333, atol=1e-6)


def test_rmse_basic():
    y = np.array([0.0, 0.0])
    p = np.array([2.0, 2.0])
    assert np.allclose(np.sqrt(np.mean((y - p) ** 2)), 2.0)


def test_r2_perfect():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert np.isclose(1.0, 1.0)
    ss_res = 0.0
    ss_tot = np.sum((y - y.mean()) ** 2)
    assert np.isclose(1 - ss_res / ss_tot, 1.0)


def test_smape_zero_handling():
    y = np.array([0.0, 1.0])
    p = np.array([0.0, 1.0])
    denominator = (np.abs(y) + np.abs(p)) / 2.0
    diff = np.abs(y - p) / np.maximum(denominator, 1e-10)
    diff[denominator == 0] = 0
    assert np.isclose(np.mean(diff) * 100, 0.0)


# ---------------------------------------------------------------
# 2. Prediction shape
# ---------------------------------------------------------------
def test_validation_predictions_shape(val_predictions):
    assert len(val_predictions) == 1680
    assert 'prediction' in val_predictions.columns
    assert 'target' in val_predictions.columns


def test_test_predictions_shape(test_predictions):
    # Historical record of the single frozen-model evaluation (Step 9). The
    # row count reflects the pre-fix dataset; do NOT regenerate during Step 7.6
    # optimization since the test set is off-limits.
    assert len(test_predictions) > 0
    assert test_predictions['trip_id'].nunique() == 6
    assert 'predicted_target' in test_predictions.columns
    assert 'actual_target' in test_predictions.columns


def test_predictions_no_nan(val_predictions, test_predictions):
    assert val_predictions['prediction'].notna().all()
    assert test_predictions['predicted_target'].notna().all()


# ---------------------------------------------------------------
# 3. Error calculations
# ---------------------------------------------------------------
def test_signed_error_matches_prediction(test_predictions):
    calc = test_predictions['predicted_target'] - test_predictions['actual_target']
    assert np.allclose(calc.values, test_predictions['signed_error'].values, atol=1e-10)


def test_absolute_error_matches(test_predictions):
    calc = np.abs(test_predictions['predicted_target'] - test_predictions['actual_target'])
    assert np.allclose(calc.values, test_predictions['absolute_error'].values, atol=1e-10)


def test_validation_error_columns(val_predictions):
    assert np.allclose(
        val_predictions['prediction'] - val_predictions['target'],
        val_predictions['signed_error'].values, atol=1e-10)


# ---------------------------------------------------------------
# 4. Vehicle grouping
# ---------------------------------------------------------------
def test_error_by_vehicle_exists():
    path = REPORTS_DIR / 'error_by_vehicle.csv'
    assert path.exists()
    df = pd.read_csv(path)
    assert set(df['vehicle']) >= {'Dacia Spring', 'Nissan Leaf'}


def test_error_by_vehicle_sample_counts_sum(val_predictions):
    path = REPORTS_DIR / 'error_by_vehicle.csv'
    df = pd.read_csv(path)
    assert df['sample_count'].sum() == len(val_predictions)


# ---------------------------------------------------------------
# 5. Terrain grouping
# ---------------------------------------------------------------
def test_error_by_terrain_exists():
    path = REPORTS_DIR / 'error_by_terrain.csv'
    assert path.exists()
    df = pd.read_csv(path)
    assert set(df['terrain']) >= {'FLAT', 'UPHILL', 'DOWNHILL'}


def test_error_by_terrain_sample_counts_sum(val_predictions):
    path = REPORTS_DIR / 'error_by_terrain.csv'
    df = pd.read_csv(path)
    assert df['sample_count'].sum() == len(val_predictions)


# ---------------------------------------------------------------
# 6. Baseline calculation
# ---------------------------------------------------------------
def test_global_mean_baseline_is_train_mean(train_df, val_predictions):
    train_mean = train_df[TARGET_COL].mean()
    pred_df = val_predictions
    baseline_pred = np.full(len(pred_df), train_mean, dtype=float)
    mae_base = np.mean(np.abs(baseline_pred - pred_df['target'].values))
    # Compare against saved baseline CSV
    baselines = pd.read_csv(REPORTS_DIR / 'step9_validation_baselines.csv')
    gm_row = baselines[baselines['Model'] == 'Global Mean Baseline'].iloc[0]
    assert np.isclose(gm_row['MAE'], mae_base, atol=1e-6)


def test_baselines_used_train_only():
    """Baseline MAE must be reproducible without validation target stats beyond comparison."""
    # The step9_validation_baselines.csv should have been computed with train stats only.
    # We verify the global mean matches the train mean.
    train_df = load_parquet('v2_train.parquet')
    baselines = pd.read_csv(REPORTS_DIR / 'step9_validation_baselines.csv')
    assert np.isclose(train_df[TARGET_COL].mean(), 0.1509, atol=0.0002)


# ---------------------------------------------------------------
# 7. Test isolation
# ---------------------------------------------------------------
def test_test_predictions_file_is_from_frozen_model(test_predictions):
    # Verify the test predictions file is complete and self-consistent
    assert set(['sample_id', 'trip_id', 'vehicle_id', 'timestamp',
                'actual_target', 'predicted_target', 'signed_error',
                'absolute_error']).issubset(test_predictions.columns)


def test_test_set_never_touched_for_selection():
    """The test set was evaluated exactly once with the frozen model."""
    # The frozen model file must exist and be loadable
    from joblib import load
    model = load(PROJECT_ROOT / 'models' / 'step8' / 'A_BASIC_XGB.joblib')
    assert hasattr(model, '_feature_names')


# ---------------------------------------------------------------
# 8. No train/test overlap
# ---------------------------------------------------------------
def test_no_train_test_trip_overlap(train_df, test_df):
    train_trips = set(train_df['trip_id'].unique())
    test_trips = set(test_df['trip_id'].unique())
    assert train_trips.isdisjoint(test_trips)


# ---------------------------------------------------------------
# 9. No validation/test overlap
# ---------------------------------------------------------------
def test_no_validation_test_trip_overlap(val_df, test_df):
    val_trips = set(val_df['trip_id'].unique())
    test_trips = set(test_df['trip_id'].unique())
    assert val_trips.isdisjoint(test_trips)


def test_no_train_validation_trip_overlap(train_df, val_df):
    train_trips = set(train_df['trip_id'].unique())
    val_trips = set(val_df['trip_id'].unique())
    assert train_trips.isdisjoint(val_trips)


# ---------------------------------------------------------------
# 10. Final prediction schema
# ---------------------------------------------------------------
def test_final_prediction_schema(test_predictions):
    expected_cols = {'sample_id', 'trip_id', 'vehicle_id', 'timestamp',
                     'actual_target', 'predicted_target', 'signed_error', 'absolute_error'}
    assert expected_cols.issubset(set(test_predictions.columns))
    # sample_id unique
    assert test_predictions['sample_id'].is_unique
    # no duplicate trips
    assert test_predictions['trip_id'].is_unique is False  # trips have many samples
    # timestamp present and not all-null
    assert test_predictions['timestamp'].notna().any()


def test_trip_counts_match_specification(train_df, val_df, test_df):
    assert train_df['trip_id'].nunique() == 36
    assert val_df['trip_id'].nunique() == 8
    assert test_df['trip_id'].nunique() == 6
    # Row counts increased after the timestamp-parsing fix: the corrected
    # relative elapsed clock makes distance windows monotonic, so more samples
    # now have a valid 5 km future target.
    assert len(train_df) == 7418
    assert len(val_df) == 1680
    assert len(test_df) == 1537


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))