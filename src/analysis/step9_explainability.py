"""
STEP 9 - MODEL EXPLAINABILITY ANALYSIS

9A  Global (impurity) feature importance       -> reports/step9_global_feature_importance.csv
9B  Permutation importance (TRAIN+VAL only)    -> reports/step9_permutation_importance.csv
9C  SHAP (<=500 samples) or documented skip    -> reports/figures/step9_shap_*.png
9D  Local explanations (5 samples)             -> reports/step9_local_explanations.md
9G  Residual quantiles (TRAIN+VAL only)        -> reports/step9_trainval_residual_quantiles.json

The frozen model is loaded read-only. No test data is touched. No retraining.
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
MODELS = PROJECT_ROOT / 'models'
REPORTS = PROJECT_ROOT / 'reports'
FIGURES = REPORTS / 'figures'
TARGET = 'target_future_energy_kwh_per_km'
SEED = 42
np.random.seed(SEED)


def load_data():
    tr = pd.read_parquet(PROCESSED / 'v2_train.parquet')
    va = pd.read_parquet(PROCESSED / 'v2_validation.parquet')
    df = pd.concat([tr, va], ignore_index=True)
    del tr, va
    gc.collect()
    feats = json.loads((MODELS / 'final_feature_list.json').read_text(encoding='utf-8'))
    model = joblib.load(MODELS / 'ev_energy_extratrees_route_aware.joblib')
    imputer = joblib.load(MODELS / 'final_preprocessor.joblib')
    return df, feats, model, imputer


def step9a(df, feats, model):
    imp = model.feature_importances_
    out = pd.DataFrame({'feature': feats, 'importance': imp}).sort_values(
        'importance', ascending=False).reset_index(drop=True)
    out.insert(0, 'rank', range(1, len(out) + 1))
    out['cumulative_importance'] = out['importance'].cumsum()
    p = REPORTS / 'step9_global_feature_importance.csv'
    out.to_csv(p, index=False)
    print(f'[9A] global (impurity) importance -> {p.name}; top: {out.iloc[0].feature}')
    print('     NOTE: this is PREDICTIVE importance, not causal importance.')
    return out


def step9b(df, feats, model, imputer):
    """Grouped permutation importance on TRAIN+VALIDATION only (no test).

    ExtraTrees is strongly in-sample memorizing, so permutation on the same
    rows the model was trained on is meaningless (flat ~0). Instead we fit
    clones with the EXACT frozen hyperparameters under GroupKFold (grouped by
    trip_id) and measure MAE degradation on each held-out fold. The frozen
    production artifact is never modified.
    """
    from sklearn.ensemble import ExtraTreesRegressor

    sub = df[['trip_id'] + feats + [TARGET]].dropna(subset=[TARGET])
    X = sub[feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(float)
    groups = sub['trip_id'].to_numpy()
    del sub
    gc.collect()

    params = {k: getattr(model, k) for k in
              ('n_estimators', 'max_depth', 'min_samples_leaf', 'random_state')}
    params['n_jobs'] = -1
    gkf = GroupKFold(n_splits=5)
    rng = np.random.default_rng(SEED)
    n_repeats = 3

    imp_acc = np.zeros(len(feats))
    imp_acc2 = np.zeros(len(feats))
    fold_scores = []
    for t, v in gkf.split(X, y, groups):
        clone = ExtraTreesRegressor(**params)
        clone.fit(X[t], y[t])
        yv = y[v]
        base = float(np.mean(np.abs(clone.predict(X[v]) - yv)))
        fold_scores.append(base)
        for k in range(len(feats)):
            for _ in range(n_repeats):
                Xp = X[v].copy()
                Xp[:, k] = rng.permutation(Xp[:, k])
                d = float(np.mean(np.abs(clone.predict(Xp) - yv))) - base
                imp_acc[k] += d
                imp_acc2[k] += d * d
        del clone
        gc.collect()
    n_obs = 5 * n_repeats
    imp_mean = imp_acc / n_obs
    imp_std = np.sqrt(np.maximum(imp_acc2 / n_obs - imp_mean ** 2, 0.0))
    base_mae = float(np.mean(fold_scores))

    out = pd.DataFrame({'feature': feats, 'importance_mean': imp_mean,
                        'importance_std': imp_std}).sort_values(
        'importance_mean', ascending=False).reset_index(drop=True)
    out.insert(0, 'rank', range(1, len(out) + 1))
    p = REPORTS / 'step9_permutation_importance.csv'
    out.to_csv(p, index=False)
    print(f'[9B] grouped permutation importance (GroupKFold, MAE degradation, '
          f'train+val) -> {p.name}')
    print(f'     OOF base MAE = {base_mae:.5f}; top: {out.iloc[0].feature}')
    return out, base_mae


def step9c_shap():
    """SHAP: skipped because `shap` is not installed and we avoid heavy deps."""
    report = {
        'shap_status': 'SKIPPED',
        'reason': ('`shap` is not installed in this environment. Installing it '
                   'would add a heavy dependency chain (numba, etc.) that the '
                   'project rules avoid. Permutation importance (step9b) is '
                   'used as the model-agnostic explainability method instead.'),
        'max_samples_allowed': 500,
    }
    p = REPORTS / 'step9_shap_status.json'
    p.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'[9C] SHAP SKIPPED (not installed; no heavy deps added). -> {p.name}')


def sample_selection(df, feats, model, imputer):
    """Select 5 representative TRAIN+VALIDATION samples for local explanation."""
    meta = ['trip_id', 'vehicle_model', 'current_soc_pct', 'current_altitude_m',
            'current_gradient_pct', 'next_5km_gradient_pct', 'regen_power_kw',
            'mean_regen_power_1km']
    sub = df[list(dict.fromkeys(meta + feats)) + [TARGET]].dropna(subset=[TARGET])
    X = sub[feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(float)
    med = np.nanmedian(X, axis=0); med = np.where(np.isfinite(med), med, 0.0)
    X = np.where(np.isnan(X), np.broadcast_to(med, X.shape), X)
    pred = model.predict(X)
    # choose by criteria
    picks = {}
    low = int(np.argmin(pred)); picks['low_predicted_consumption'] = low
    med_p = int(np.argsort(np.abs(pred - np.median(pred)))[0]); picks['medium_predicted_consumption'] = med_p
    high = int(np.argmax(pred)); picks['high_predicted_consumption'] = high
    steep = int(np.argsort(-np.abs(sub['next_5km_gradient_pct'].to_numpy()))[0]); picks['steep_terrain'] = steep
    regen = int(np.argsort(-sub['mean_regen_power_1km'].to_numpy(float))[0]); picks['high_regen'] = regen

    result = {}
    for name, idx in picks.items():
        result[name] = {
            'index_in_subset': int(idx),
            'trip_id': str(sub.iloc[idx]['trip_id']),
            'vehicle_model': str(sub.iloc[idx]['vehicle_model']),
            'predicted_kwh_per_km': float(pred[idx]),
            'actual_kwh_per_km': float(y[idx]),
            'soc_pct': float(sub.iloc[idx]['current_soc_pct']),
            'altitude_m': float(sub.iloc[idx]['current_altitude_m']),
            'next_5km_gradient_pct': float(sub.iloc[idx]['next_5km_gradient_pct']),
            'mean_regen_power_1km': float(sub.iloc[idx]['mean_regen_power_1km']),
        }
    return result, X, y, pred, feats, model


def step9d_local(df, feats, model, imputer):
    """Local explanations: contributions estimated via prediction deltas."""
    sel, X, y, pred, feats, model = sample_selection(df, feats, model, imputer)
    # baseline prediction at feature medians
    base = float(model.predict(np.median(X, axis=0, keepdims=True))[0])
    rows = []
    for name, info in sel.items():
        idx = info['index_in_subset']
        x = X[idx]
        contribs = []
        for k, f in enumerate(feats):
            xp = x.copy(); xp[k] = np.median(X[:, k])
            contribs.append((f, float(model.predict(xp.reshape(1, -1))[0]) - base))
        contribs.sort(key=lambda t: -abs(t[1]))
        pos = [(f, round(v, 5)) for f, v in contribs[:6] if v > 0]
        neg = [(f, round(v, 5)) for f, v in contribs[-6:][::-1] if v < 0]
        rows.append({
            'case': name, 'prediction_kwh_per_km': round(info['predicted_kwh_per_km'], 5),
            'actual_kwh_per_km': round(info['actual_kwh_per_km'], 5),
            'baseline_median_prediction': round(base, 5),
            'trip_id': info['trip_id'], 'vehicle': info['vehicle_model'],
            'positive_contributors': pos, 'negative_contributors': neg,
        })
    md = ['# Step 9D - Local Explanations (representative TRAIN+VAL samples)\n',
          'Contributions are measured as prediction deltas vs the median-feature '
          'baseline (one-feature-at-a-time). This is PREDICTIVE attribution, '
          'NOT causal attribution.\n']
    for r in rows:
        md.append(f'## {r["case"]}')
        md.append(f'- Trip: `{r["trip_id"]}` ({r["vehicle"]})')
        md.append(f'- Predicted consumption: {r["prediction_kwh_per_km"]} kWh/km'
                  f' (actual: {r["actual_kwh_per_km"]})')
        md.append(f'- Baseline (median features) prediction: {r["baseline_median_prediction"]}')
        md.append('- Positive contributors (push prediction up):')
        for f, v in r['positive_contributors']:
            md.append(f'  - {f}: +{v}')
        if not r['positive_contributors']:
            md.append('  - (none)')
        md.append('- Negative contributors (push prediction down):')
        for f, v in r['negative_contributors']:
            md.append(f'  - {f}: {v}')
        if not r['negative_contributors']:
            md.append('  - (none)')
        md.append('')
    (REPORTS / 'step9_local_explanations.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'[9D] local explanations -> step9_local_explanations.md ({len(rows)} cases)')


def step9g_residuals(df, feats, model, imputer):
    """Residual quantiles on TRAIN+VALIDATION only (for range band)."""
    sub = df[['trip_id'] + feats + [TARGET]].dropna(subset=[TARGET])
    X = sub[feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(float)
    med = np.nanmedian(X, axis=0); med = np.where(np.isfinite(med), med, 0.0)
    X = np.where(np.isnan(X), np.broadcast_to(med, X.shape), X)
    pred = model.predict(X)
    resid = pred - y
    qs = {f'q{i}': float(np.quantile(resid, i / 100)) for i in (5, 10, 25, 50, 75, 90, 95)}
    qs['n'] = int(len(resid))
    qs['source'] = 'TRAIN+VALIDATION ONLY (test excluded)'
    p = REPORTS / 'step9_trainval_residual_quantiles.json'
    p.write_text(json.dumps(qs, indent=2), encoding='utf-8')
    print(f'[9G] residual quantiles (train+val) -> {p.name}: q10={qs["q10"]:.5f}, '
          f'q50={qs["q50"]:.5f}, q90={qs["q90"]:.5f}')
    return qs


def main():
    t0 = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    print('STEP 9 - MODEL EXPLAINABILITY')
    print('=' * 72)
    df, feats, model, imputer = load_data()
    print(f'rows={len(df):,} trips={df.trip_id.nunique()} features={len(feats)}')

    step9a(df, feats, model)
    step9b(df, feats, model, imputer)
    step9c_shap()
    step9d_local(df, feats, model, imputer)
    qs = step9g_residuals(df, feats, model, imputer)
    del df
    gc.collect()
    print(f'\nSTEP 9 analysis complete in {time.time() - t0:.1f}s')


if __name__ == '__main__':
    main()