"""
STEP 8 - FINAL MODEL TRAINING & ONE-TIME HELD-OUT TEST EVALUATION

Frozen route-aware model:
    ExtraTreesRegressor(n_estimators=300, max_depth=10, min_samples_leaf=3,
                        random_state=42, n_jobs=-1)
Feature set: the exact 102 route-aware causal features from Step 7.7
    (data/processed/devrt_ml_features_v3_route_aware.parquet, minus metadata).
Target:     target_future_energy_kwh_per_km (already present; never recreated).

Test protection (Step 8O): the test set is evaluated exactly once. After the
first evaluation a marker file reports/.step8_test_evaluated is written and
any further run refuses to re-evaluate the test set. Remove the marker file
explicitly to force a re-run (discouraged for scientific reproducibility).

Determinism: random_state=42 everywhere; feature order is fixed from the
route-aware dataset column order; median imputation fitted on TRAIN+VAL ONLY.
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (mean_absolute_error, mean_squared_error, r2_score,
                             median_absolute_error, explained_variance_score)

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
MODELS = PROJECT_ROOT / 'models'
REPORTS = PROJECT_ROOT / 'reports'
DOCS = PROJECT_ROOT / 'docs'
FIGURES = REPORTS / 'figures'

TARGET = 'target_future_energy_kwh_per_km'
META = {'trip_id', 'vehicle_id', 'timestamp', 'vehicle_model'}
ROUTE_PARQUET = PROCESSED / 'devrt_ml_features_v3_route_aware.parquet'
MARKER = REPORTS / '.step8_test_evaluated'
MODEL_FILE = MODELS / 'ev_energy_extratrees_route_aware.joblib'
PREPROCESSOR_FILE = MODELS / 'final_preprocessor.joblib'
FEATURE_LIST_FILE = MODELS / 'final_feature_list.json'

ET_PARAMS = dict(n_estimators=300, max_depth=10, min_samples_leaf=3,
                 n_jobs=-1, random_state=42)
SEED = 42

np.random.seed(SEED)

# ---------------------------------------------------------------------------
# 8A - dataset verification
# ---------------------------------------------------------------------------
def load_split(name: str) -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / f'v2_{name}.parquet')
    return df


def feature_list() -> list[str]:
    cols = pd.read_parquet(ROUTE_PARQUET, columns=None).columns.tolist()
    feats = [c for c in cols if c not in META and c != TARGET]
    if len(feats) != 102:
        raise ValueError(f'expected 102 route-aware features, got {len(feats)}')
    return feats


def step8a() -> dict:
    tr, va, te = load_split('train'), load_split('validation'), load_split('test')
    tr_t = set(tr.trip_id.unique()); va_t = set(va.trip_id.unique()); te_t = set(te.trip_id.unique())
    overlaps = {
        'train_intersection_validation': sorted(tr_t & va_t),
        'train_intersection_test': sorted(tr_t & te_t),
        'validation_intersection_test': sorted(va_t & te_t),
    }
    if any(overlaps.values()):
        raise RuntimeError(f'trip overlap detected: {overlaps}')
    feats = feature_list()
    res = {
        'train_rows': int(len(tr)), 'validation_rows': int(len(va)),
        'test_rows': int(len(te)),
        'train_plus_validation_rows': int(len(tr) + len(va)),
        'number_of_features': len(feats),
        'target_name': TARGET,
        'feature_names': feats,
        'missing_value_counts_train': {c: int(tr[c].isna().sum()) for c in feats},
        'missing_value_counts_validation': {c: int(va[c].isna().sum()) for c in feats},
        'missing_value_counts_test': {c: int(te[c].isna().sum()) for c in feats},
        'trip_counts': {'train': int(tr.trip_id.nunique()),
                        'validation': int(va.trip_id.nunique()),
                        'test': int(te.trip_id.nunique())},
        'vehicle_counts': {'train': tr.vehicle_model.value_counts().to_dict(),
                           'validation': va.vehicle_model.value_counts().to_dict(),
                           'test': te.vehicle_model.value_counts().to_dict()},
        'trip_overlap_checks': overlaps,
        'trip_overlap_passed': True,
    }
    out = REPORTS / 'step8_dataset_verification.json'
    out.write_text(json.dumps(res, indent=2), encoding='utf-8')
    del tr, va, te
    gc.collect()
    print(f'[8A] verified: train={res["train_rows"]} val={res["validation_rows"]} '
          f'test={res["test_rows"]} trips, no overlap. -> {out.name}')
    return res


# ---------------------------------------------------------------------------
# 8B/8C - combine train+val, fit median imputer (train+val only)
# ---------------------------------------------------------------------------
def step8bc(feats: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    tr = load_split('train')
    va = load_split('validation')
    tr_trips = tr['trip_id'].to_numpy()
    va_trips = va['trip_id'].to_numpy()
    X_tr = tr[feats].to_numpy(dtype=float)
    y_tr = tr[TARGET].to_numpy(float)
    X_va = va[feats].to_numpy(dtype=float)
    y_va = va[TARGET].to_numpy(float)
    del tr, va
    gc.collect()

    X_all = np.vstack([X_tr, X_va])
    y_all = np.concatenate([y_tr, y_va])
    trips_all = np.concatenate([tr_trips, va_trips])
    del X_tr, y_tr, X_va, y_va, tr_trips, va_trips
    gc.collect()

    imputer = SimpleImputer(strategy='median')
    imputer.fit(X_all)
    joblib.dump(imputer, PREPROCESSOR_FILE)
    X_imp = imputer.transform(X_all)
    print(f'[8B/8C] combined train+val: {X_imp.shape[0]} rows x {X_imp.shape[1]} feats; '
          f'median imputer fitted on train+val only -> {PREPROCESSOR_FILE.name}')
    return X_imp, y_all, trips_all, imputer


# ---------------------------------------------------------------------------
# 8D - train frozen model
# ---------------------------------------------------------------------------
def step8d(X: np.ndarray, y: np.ndarray, feats: list[str]) -> ExtraTreesRegressor:
    model = ExtraTreesRegressor(**ET_PARAMS)
    model.fit(X, y)
    joblib.dump(model, MODEL_FILE)
    FEATURE_LIST_FILE.write_text(json.dumps(feats, indent=2), encoding='utf-8')
    print(f'[8D] trained ExtraTrees on {len(y):,} rows x {len(feats)} feats '
          f'-> {MODEL_FILE.name}')
    return model


# ---------------------------------------------------------------------------
# 8E - one-time test evaluation
# ---------------------------------------------------------------------------
def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = float(r2_score(y_true, y_pred))
    bias = float(np.mean(y_pred - y_true))
    med_ae = float(median_absolute_error(y_true, y_pred))
    max_ae = float(np.max(np.abs(y_pred - y_true)))
    ev = float(explained_variance_score(y_true, y_pred))
    return {'mae': mae, 'rmse': rmse, 'r2': r2, 'bias': bias,
            'median_absolute_error': med_ae, 'max_absolute_error': max_ae,
            'explained_variance': ev}


def step8e(model, imputer, feats: list[str]) -> tuple[dict, pd.DataFrame]:
    te = load_split('test')
    trips = te['trip_id'].to_numpy()
    vehicles = te['vehicle_model'].to_numpy()
    timestamps = te['timestamp'].to_numpy()
    y = te[TARGET].to_numpy(float)
    X = te[feats].to_numpy(dtype=float)
    del te
    gc.collect()
    X = imputer.transform(X)
    pred = model.predict(X)
    m = metrics(y, pred)
    print(f'[8E] TEST evaluated once: n={len(y)} '
          f'MAE={m["mae"]:.5f} RMSE={m["rmse"]:.5f} R2={m["r2"]:+.4f} '
          f'bias={m["bias"]:+.5f}')

    # MAPE decision (near-zero targets make it unstable)
    near_zero = float(np.mean(np.abs(y) < 0.05))
    m['mape_used'] = False
    m['mape_reason'] = (f'{near_zero:.1%} of test targets are near zero '
                        f'(<0.05 kWh/km); MAPE is unstable/undefined with '
                        f'near-zero denominators.')

    pred_df = pd.DataFrame({
        'trip_id': trips, 'vehicle_model': vehicles, 'timestamp': timestamps,
        'actual_target': y, 'predicted_target': pred,
        'residual': pred - y, 'absolute_error': np.abs(pred - y),
    })
    pred_out = PROCESSED / 'step8_test_predictions.parquet'
    pred_df.to_parquet(pred_out, index=False)
    print(f'[8I] predictions -> {pred_out.name}')
    MARKER.write_text(
        json.dumps({'test_evaluated_once': True, 'n': int(len(y)),
                    'mae': m['mae'], 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')},
                   indent=2), encoding='utf-8')
    print(f'[8O] marker written -> {MARKER.name}')
    return m, pred_df


# ---------------------------------------------------------------------------
# 8F - baseline (train+val mean), 8G - vehicle-wise, 8H - error analysis
# ---------------------------------------------------------------------------
def step8fg(y_train: np.ndarray, test_metrics: dict, pred_df: pd.DataFrame,
            y_test: np.ndarray) -> dict:
    baseline = float(np.mean(y_train))
    pred = pred_df['predicted_target'].to_numpy()
    y = y_test
    base_mae = float(np.mean(np.abs(y - baseline)))
    base_rmse = float(np.sqrt(np.mean((y - baseline) ** 2)))
    base_r2 = float(1 - np.sum((y - baseline) ** 2) / np.sum((y - np.mean(y)) ** 2))
    mae_imp = (base_mae - test_metrics['mae']) / base_mae * 100
    rmse_imp = (base_rmse - test_metrics['rmse']) / base_rmse * 100
    base = {'baseline_value': baseline,
            'baseline_mae': base_mae, 'baseline_rmse': base_rmse, 'baseline_r2': base_r2,
            'mae_improvement_percent': mae_imp, 'rmse_improvement_percent': rmse_imp}
    print(f'[8F] baseline(train+val mean={baseline:.4f}): MAE={base_mae:.5f} '
          f'RMSE={base_rmse:.5f}; model MAE improvement {mae_imp:.1f}%')

    veh = {}
    for v in ['Dacia Spring', 'Nissan Leaf']:
        sub = pred_df[pred_df.vehicle_model == v]
        if len(sub):
            veh[v] = metrics(sub['actual_target'].to_numpy(),
                             sub['predicted_target'].to_numpy())
            veh[v]['samples'] = int(len(sub))
            print(f'[8G] {v}: n={veh[v]["samples"]} MAE={veh[v]["mae"]:.5f} '
                  f'RMSE={veh[v]["rmse"]:.5f} R2={veh[v]["r2"]:+.3f} '
                  f'bias={veh[v]["bias"]:+.5f}')
    return {'baseline': base, 'vehicle_wise': veh}


def step8h(pred_df: pd.DataFrame) -> None:
    te = load_split('test')
    feats = ['current_altitude_m', 'current_gradient_pct', 'next_5km_gradient_pct',
             'distance_since_trip_start_km', 'trip_elapsed_time_min']
    for c in feats:
        pred_df[c] = te[c].to_numpy()
    del te
    gc.collect()

    def bin_stats(sub: pd.DataFrame, label: str) -> dict:
        y = sub['actual_target'].to_numpy(); p = sub['predicted_target'].to_numpy()
        return {'bin': label, 'sample_count': int(len(sub)),
                'mae': round(float(np.mean(np.abs(p - y))), 5),
                'rmse': round(float(np.sqrt(np.mean((p - y) ** 2))), 5),
                'bias': round(float(np.mean(p - y)), 5)}

    rows = []
    y = pred_df['actual_target']
    rows.append(bin_stats(pred_df, 'all'))
    for lo, hi in [(-0.5, 0.0), (0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 1.0)]:
        s = pred_df[(y >= lo) & (y < hi)]
        if len(s): rows.append(bin_stats(s, f'target_{lo:.1f}_to_{hi:.1f}'))
    for lo, hi in [(0, 200), (200, 400), (400, 600), (600, 1000)]:
        s = pred_df[(pred_df['current_altitude_m'] >= lo) & (pred_df['current_altitude_m'] < hi)]
        if len(s): rows.append(bin_stats(s, f'altitude_{lo}_to_{hi}'))
    for lo, hi in [(-99, -3), (-3, -1), (-1, 1), (1, 3), (3, 99)]:
        s = pred_df[(pred_df['next_5km_gradient_pct'] >= lo) & (pred_df['next_5km_gradient_pct'] < hi)]
        if len(s): rows.append(bin_stats(s, f'next5km_grad_{lo}_to_{hi}'))
    for lo, hi in [(0, 5), (5, 15), (15, 30), (30, 100)]:
        s = pred_df[(pred_df['distance_since_trip_start_km'] >= lo) & (pred_df['distance_since_trip_start_km'] < hi)]
        if len(s): rows.append(bin_stats(s, f'dist_{lo}_to_{hi}'))
    for lo, hi in [(0, 10), (10, 20), (20, 40), (40, 100)]:
        s = pred_df[(pred_df['trip_elapsed_time_min'] >= lo) & (pred_df['trip_elapsed_time_min'] < hi)]
        if len(s): rows.append(bin_stats(s, f'time_{lo}_to_{hi}'))
    for v in ['Dacia Spring', 'Nissan Leaf']:
        s = pred_df[pred_df.vehicle_model == v]
        if len(s): rows.append(bin_stats(s, f'vehicle_{v}'))
    out = REPORTS / 'step8_error_analysis.csv'
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f'[8H] error analysis -> {out.name}')


# ---------------------------------------------------------------------------
# 8J - figures, 8K - feature importance
# ---------------------------------------------------------------------------
def step8jk(model, feats: list[str], pred_df: pd.DataFrame,
            veh: dict) -> pd.DataFrame:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    FIGURES.mkdir(parents=True, exist_ok=True)
    y = pred_df['actual_target'].to_numpy(); p = pred_df['predicted_target'].to_numpy()

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y, p, s=8, alpha=0.4)
    lims = [min(y.min(), p.min()), max(y.max(), p.max())]
    ax.plot(lims, lims, 'r--', lw=1.2, label='y=x')
    ax.set_xlabel('Actual (kWh/km)'); ax.set_ylabel('Predicted (kWh/km)')
    ax.set_title('Step 8: Actual vs Predicted'); ax.legend()
    fig.tight_layout(); fig.savefig(FIGURES / 'step8_actual_vs_predicted.png', dpi=120)
    plt.close(fig)

    resid = p - y
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(resid, bins=60, alpha=0.7)
    ax.axvline(0, color='r', lw=1.2)
    ax.set_xlabel('Residual = predicted - actual'); ax.set_ylabel('Count')
    ax.set_title('Step 8: Residual Distribution')
    fig.tight_layout(); fig.savefig(FIGURES / 'step8_residual_distribution.png', dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y, np.abs(resid), s=8, alpha=0.4)
    ax.set_xlabel('Actual target (kWh/km)'); ax.set_ylabel('Absolute error')
    ax.set_title('Step 8: Error vs Target')
    fig.tight_layout(); fig.savefig(FIGURES / 'step8_error_vs_target.png', dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    labels = ['Dacia Spring', 'Nissan Leaf']
    mae = [veh[v]['mae'] for v in labels if v in veh]
    l = [v for v in labels if v in veh]
    ax.bar(l, mae, color=['#1f77b4', '#ff7f0e'])
    for i, v in enumerate(mae):
        ax.text(i, v + 0.001, f'{v:.4f}', ha='center')
    ax.set_ylabel('MAE (kWh/km)'); ax.set_title('Step 8: Vehicle-wise MAE')
    fig.tight_layout(); fig.savefig(FIGURES / 'step8_vehicle_performance.png', dpi=120)
    plt.close(fig)

    imp = model.feature_importances_
    order = np.argsort(-imp)
    top20 = order[:20]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh([feats[i] for i in top20][::-1], [imp[i] for i in top20][::-1])
    ax.set_xlabel('Feature importance (predictive, not causal)')
    ax.set_title('Step 8: Top 20 Feature Importance')
    fig.tight_layout(); fig.savefig(FIGURES / 'step8_feature_importance.png', dpi=120)
    plt.close(fig)
    print('[8J] figures saved to reports/figures/')

    imp_df = pd.DataFrame({'feature': feats, 'importance': imp}).sort_values(
        'importance', ascending=False).reset_index(drop=True)
    imp_df.insert(0, 'rank', range(1, len(imp_df) + 1))
    imp_df['cumulative_importance'] = imp_df['importance'].cumsum()
    imp_df.to_csv(REPORTS / 'step8_feature_importance.csv', index=False)
    print(f'[8K] feature importance -> step8_feature_importance.csv '
          f'(top: {imp_df.iloc[0]["feature"]})')
    return imp_df


# ---------------------------------------------------------------------------
# 8L/8M - final report + metrics JSON
# ---------------------------------------------------------------------------
def step8lm(ver: dict, feats: list[str], cv: dict, test_m: dict, base: dict,
            veh: dict, imp_df: pd.DataFrame) -> dict:
    final = {
        'model': 'ExtraTreesRegressor',
        'target': TARGET,
        'feature_count': len(feats),
        'train_rows': ver['train_rows'],
        'validation_rows': ver['validation_rows'],
        'test_rows': ver['test_rows'],
        'cv_mae': cv.get('mae_mean'), 'cv_mae_std': cv.get('mae_std'),
        'cv_rmse': cv.get('rmse_mean'), 'cv_r2': cv.get('r2_mean'),
        'test_mae': test_m['mae'], 'test_rmse': test_m['rmse'],
        'test_r2': test_m['r2'], 'test_bias': test_m['bias'],
        'test_median_absolute_error': test_m['median_absolute_error'],
        'test_max_absolute_error': test_m['max_absolute_error'],
        'test_explained_variance': test_m['explained_variance'],
        'baseline_mae': base['baseline_mae'], 'baseline_rmse': base['baseline_rmse'],
        'baseline_r2': base['baseline_r2'],
        'mae_improvement_percent': base['mae_improvement_percent'],
        'rmse_improvement_percent': base['rmse_improvement_percent'],
        'dacia_mae': veh.get('Dacia Spring', {}).get('mae'),
        'nissan_mae': veh.get('Nissan Leaf', {}).get('mae'),
        'test_evaluated_once': True,
    }
    (REPORTS / 'step8_final_metrics.json').write_text(
        json.dumps(final, indent=2), encoding='utf-8')
    print(f'[8M] final metrics -> step8_final_metrics.json')
    write_report(final, ver, feats, cv, test_m, base, veh, imp_df)
    return final


def write_report(final, ver, feats, cv, test_m, base, veh, imp_df) -> None:
    top20 = imp_df.head(20)
    t20 = '\n'.join(f'{r.rank}. {r.feature}: {r.importance:.5f}' for r in top20.itertuples())
    veh_rows = '\n'.join(
        f'- {v}: n={veh[v]["samples"]}, MAE={veh[v]["mae"]:.5f}, '
        f'RMSE={veh[v]["rmse"]:.5f}, R2={veh[v]["r2"]:+.3f}, bias={veh[v]["bias"]:+.5f}'
        for v in veh)
    md = f"""# STEP 8 - Final Model Report

## 1. Executive summary
The frozen route-aware model achieves a held-out test MAE of **{test_m['mae']:.5f} kWh/km**
(RMSE {test_m['rmse']:.5f}, R2 {test_m['r2']:+.4f}), a **{base['mae_improvement_percent']:.1f}%**
improvement over the global-mean baseline (MAE {base['baseline_mae']:.5f}).

## 2. Dataset
- Train rows: {ver['train_rows']:,}
- Validation rows: {ver['validation_rows']:,}
- Test rows (held-out, evaluated once): {ver['test_rows']:,}
- Train+validation rows used for final fit: {ver['train_plus_validation_rows']:,}
- Trips: train {ver['trip_counts']['train']}, validation {ver['trip_counts']['validation']}, test {ver['trip_counts']['test']}

## 3. Target definition
`{TARGET}` = average future energy consumption over the next 5 km (kWh/km).
Used exactly as present in the processed datasets; never recreated.

## 4. Feature set
Exactly **{len(feats)} route-aware causal features** (frozen in Step 7.7):
- 87 strictly causal onboard features
- 15 conditionally causal route/terrain (look-ahead `next_*`) features
- `trip_phase` REMOVED (trip-end leakage)
Feature order and list: `models/final_feature_list.json`.

## 5. Route-aware assumption
"This model is route-aware and assumes access to upcoming route elevation /
terrain information."
"The strict onboard-only model achieved MAE ≈ 0.05518 kWh/km in GroupKFold
CV, while the route-aware model achieved MAE ≈ 0.04002 kWh/km."

## 6. Data splitting strategy
Trip-disjoint split at the trip level (no trip appears in two splits):
train ∩ validation = ∅, train ∩ test = ∅, validation ∩ test = ∅
(verified, see `reports/step8_dataset_verification.json`).

## 7. Leakage prevention
- Median imputation fitted on TRAIN+VAL ONLY; test never contributes statistics.
- Feature set audited in Step 7.7 (no target leakage, no trip-end leakage, no
  future SOC/speed/power telemetry; look-ahead terrain is static geography).
- Test evaluated exactly once; marker `reports/.step8_test_evaluated` guards
  against accidental re-evaluation.

## 8. Model architecture
ExtraTreesRegressor (ensemble of regression trees).

## 9. Hyperparameters
- n_estimators = 300
- max_depth = 10
- min_samples_leaf = 3
- random_state = 42
- n_jobs = -1
Frozen; no tuning, no comparison, no ensembles.

## 10. Training procedure
1. Load v2_train + v2_validation.
2. Select the exact 102 route-aware features.
3. Fit `SimpleImputer(strategy='median')` on train+val only.
4. Train ExtraTreesRegressor on the combined matrix.
5. Save model + preprocessor + feature list.

## 11. Final test results
- MAE: **{test_m['mae']:.5f}**
- RMSE: **{test_m['rmse']:.5f}**
- R2: **{test_m['r2']:+.4f}**
- Bias (mean error): **{test_m['bias']:+.5f}**
- Median absolute error: **{test_m['median_absolute_error']:.5f}**
- Max absolute error: **{test_m['max_absolute_error']:.5f}**
- Explained variance: **{test_m['explained_variance']:.5f}**
- MAPE: not reported — {test_m['mape_reason']}

## 12. Baseline comparison
Baseline = global mean of the train+val target ({base['baseline_value']:.5f}):
- Baseline MAE: {base['baseline_mae']:.5f} | Model MAE: {test_m['mae']:.5f}
- MAE improvement: **{base['mae_improvement_percent']:.1f}%**
- RMSE improvement: **{base['rmse_improvement_percent']:.1f}%**
- Baseline R2: {base['baseline_r2']:+.4f} | Model R2: {test_m['r2']:+.4f}

## 13. Vehicle-wise performance
{veh_rows}

## 14. Error analysis
Binned MAE/RMSE/bias by target range, altitude, look-ahead 5km gradient,
trip distance, elapsed time, and vehicle -> `reports/step8_error_analysis.csv`.
(Descriptive only; does not influence the model.)

## 15. Feature importance
Top 20 (predictive importance from ExtraTrees `feature_importances_`; this is
NOT causal importance):
{t20}
Full ranking: `reports/step8_feature_importance.csv`.

## 16. Limitations
- Route-aware assumption: requires planned route elevation/terrain (nav/DEM);
  a bare onboard model without route info degrades to strict onboard (~0.05518).
- Cross-vehicle generalization tested on only two vehicle models (Dacia, Nissan).
- Small per-vehicle test samples (n ≈ {veh.get('Dacia Spring', {}).get('samples', '?')} /
{veh.get('Nissan Leaf', {}).get('samples', '?')}).
- DEVRT telemetry gaps (e.g. no regen/motor data on Dacia) are handled via NaN
  flags/median imputation.
- Negative target values exist (regen gain over a 5km window); treated as real signal.

## 17. Reproducibility
- `src/models/train_final_model.py` reproduces the entire pipeline
  (random_state=42 everywhere, fixed feature order).
- Model: `models/ev_energy_extratrees_route_aware.joblib`
- Preprocessor: `models/final_preprocessor.joblib`
- Feature list: `models/final_feature_list.json`

## 18. Final conclusion
The route-aware ExtraTrees model generalizes to the untouched held-out test set
with MAE **{test_m['mae']:.5f} kWh/km** ({base['mae_improvement_percent']:.1f}% better than
baseline), evaluated exactly once with no test-driven tuning.
"""
    (DOCS / 'step8_final_model_report.md').write_text(md, encoding='utf-8')
    print('[8L] final model report -> docs/step8_final_model_report.md')


def load_cv_metrics() -> dict:
    p = REPORTS / 'step7_7_causal_audit.md'
    # CV values are fixed from Step 7.7 route-aware result (documented).
    return {'mae_mean': 0.04002, 'mae_std': 0.00103, 'rmse_mean': 0.05256,
            'r2_mean': 0.657}


def main() -> None:
    t0 = time.time()
    for d in (MODELS, REPORTS, FIGURES, DOCS):
        d.mkdir(parents=True, exist_ok=True)
    print('STEP 8 - FINAL MODEL TRAINING & ONE-TIME TEST EVALUATION')
    print('=' * 72)

    feats = feature_list()
    print(f'frozen feature count: {len(feats)} | trip_phase present: '
          f'{"trip_phase" in feats}')

    ver = step8a()
    X, y, trips, imputer = step8bc(feats)
    model = step8d(X, y, feats)
    del X, y, trips
    gc.collect()

    # ---- test protection (8O) ----
    if MARKER.exists():
        raise SystemExit(
            f'REFUSING to evaluate test set: marker {MARKER} already exists.\n'
            f'The test set was already evaluated once. Remove the marker file '
            f'explicitly only if you intend to override this protection.')

    test_m, pred_df = step8e(model, imputer, feats)
    base_res = step8fg(y_train_mean(), test_m, pred_df, y_test())
    step8h(pred_df)
    imp_df = step8jk(model, feats, pred_df, base_res['vehicle_wise'])
    final = step8lm(ver, feats, load_cv_metrics(), test_m,
                    base_res['baseline'], base_res['vehicle_wise'], imp_df)
    print(f'\nSTEP 8 COMPLETE in {time.time() - t0:.1f}s')


def y_train_mean() -> np.ndarray:
    tr = load_split('train')
    va = load_split('validation')
    y = np.concatenate([tr[TARGET].to_numpy(float), va[TARGET].to_numpy(float)])
    del tr, va
    gc.collect()
    return y


def y_test() -> np.ndarray:
    te = load_split('test')
    y = te[TARGET].to_numpy(float)
    del te
    gc.collect()
    return y


if __name__ == '__main__':
    main()