"""Tests for STEP 8 final model training & one-time held-out evaluation."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import ExtraTreesRegressor

PROJECT_ROOT = Path(__file__).parent.parent
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
REPORTS = PROJECT_ROOT / 'reports'
MODELS = PROJECT_ROOT / 'models'
TARGET = 'target_future_energy_kwh_per_km'


def load_feature_list():
    return json.loads((MODELS / 'final_feature_list.json').read_text(encoding='utf-8'))


def test_exact_feature_count_is_102():
    assert len(load_feature_list()) == 102


def test_trip_phase_absent():
    assert 'trip_phase' not in load_feature_list()


def test_target_absent_from_features():
    assert TARGET not in load_feature_list()


def test_trip_id_absent_from_features():
    assert 'trip_id' not in load_feature_list()


def test_timestamp_absent_from_features():
    assert 'timestamp' not in load_feature_list()


def test_train_test_trip_disjointness():
    tr = pd.read_parquet(PROCESSED / 'v2_train.parquet')
    va = pd.read_parquet(PROCESSED / 'v2_validation.parquet')
    te = pd.read_parquet(PROCESSED / 'v2_test.parquet')
    s = {k: set(v.trip_id.unique()) for k, v in [('t', tr), ('v', va), ('e', te)]}
    assert not (s['t'] & s['v'])
    assert not (s['t'] & s['e'])
    assert not (s['v'] & s['e'])


def test_model_hyperparameters_frozen():
    model = joblib.load(MODELS / 'ev_energy_extratrees_route_aware.joblib')
    assert isinstance(model, ExtraTreesRegressor)
    assert model.n_estimators == 300
    assert model.max_depth == 10
    assert model.min_samples_leaf == 3
    assert model.random_state == 42
    assert model.n_jobs == -1


def test_saved_feature_list_matches_training_order():
    feats = load_feature_list()
    model = joblib.load(MODELS / 'ev_energy_extratrees_route_aware.joblib')
    assert len(model.feature_importances_) == len(feats)
    # saved list must match the route-aware dataset column order (minus metadata)
    cols = pd.read_parquet(PROCESSED / 'devrt_ml_features_v3_route_aware.parquet').columns
    meta = {'trip_id', 'vehicle_id', 'timestamp', 'vehicle_model'}
    expected = [c for c in cols if c not in meta and c != TARGET]
    assert feats == expected
    # importance CSV has rank + cumulative and covers the same feature set
    imp = pd.read_csv(REPORTS / 'step8_feature_importance.csv')
    assert set(imp['feature']) == set(feats)
    assert list(imp['rank']) == list(range(1, len(feats) + 1))
    assert imp['cumulative_importance'].iloc[-1] > 0


def test_prediction_output_columns():
    pred = pd.read_parquet(PROCESSED / 'step8_test_predictions.parquet')
    assert list(pred.columns) == ['trip_id', 'vehicle_model', 'timestamp',
                                  'actual_target', 'predicted_target',
                                  'residual', 'absolute_error']
    te = pd.read_parquet(PROCESSED / 'v2_test.parquet')
    assert len(pred) == len(te)
    np.testing.assert_allclose(pred['actual_target'].to_numpy(),
                               te[TARGET].to_numpy(), rtol=1e-12)
    assert pred['absolute_error'].to_numpy().min() >= 0


def test_evaluation_marker_exists_and_guards():
    marker = REPORTS / '.step8_test_evaluated'
    assert marker.exists()
    data = json.loads(marker.read_text(encoding='utf-8'))
    assert data['test_evaluated_once'] is True
    # predictions already on disk -> re-evaluation would need marker removal
    assert marker.exists()


def test_final_metrics_no_nan():
    m = json.loads((REPORTS / 'step8_final_metrics.json').read_text(encoding='utf-8'))
    assert m['test_evaluated_once'] is True
    for k, v in m.items():
        if isinstance(v, float):
            assert not np.isnan(v), f'{k} is NaN'
    assert m['feature_count'] == 102
    assert m['test_mae'] > 0


def test_verification_json_overlap_passed():
    v = json.loads((REPORTS / 'step8_dataset_verification.json').read_text(encoding='utf-8'))
    assert v['trip_overlap_passed'] is True
    for c in ['train_intersection_validation', 'train_intersection_test',
              'validation_intersection_test']:
        assert v['trip_overlap_checks'][c] == []


def test_preprocessor_fitted_on_train_val():
    imputer = joblib.load(MODELS / 'final_preprocessor.joblib')
    assert hasattr(imputer, 'statistics_')
    assert imputer.statistics_.shape == (102,)


def test_predictions_cover_test_trips():
    pred = pd.read_parquet(PROCESSED / 'step8_test_predictions.parquet')
    te = pd.read_parquet(PROCESSED / 'v2_test.parquet')
    assert set(pred.trip_id.unique()) == set(te.trip_id.unique())