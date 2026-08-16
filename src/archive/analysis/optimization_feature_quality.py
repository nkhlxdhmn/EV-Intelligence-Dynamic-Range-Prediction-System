"""
STEP 7.6 PHASE P4-P6: Feature quality audit, redundancy removal, importance.

Runs on the CLEAN corrected v2 (train + validation only; the test set stays
off-limits). Reports:

  P4 Quality:
    - missingness per feature (structural vs accidental)
    - constant / near-constant / low-cardinality features
    - per-vehicle missingness split (Dacia vs Nissan telemetry)

  P5 Redundancy:
    - pairwise |Pearson| >= 0.95 correlation clusters (greedy)
    - per-cluster proposed drop: keep the feature with highest absolute
      correlation to the target (or most complete), drop the rest
    - recommends a redundancy-trimmed feature list

  P6 Importance:
    - GroupKFold CV variable importance (permutation) for the A_BASIC and
      A_FULL candidate feature sets using the 5 km SOC target
    - XGBoost + RandomForest feature importance agreement

Memory-safe: loads only v2 train/validation frames (11k rows, ~9 MB).
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
REPORTS = PROJECT_ROOT / 'reports'
OUTPUT = REPORTS / 'optimization_feature_quality.json'

TARGET = 'target_future_energy_kwh_per_km'
ID_COLS = ['trip_id', 'vehicle_id', 'timestamp', 'vehicle_model']

DROP_ALWAYS = [
    # constant or pure metadata / leakage-adjacent columns
    'hard_acceleration_count', 'hard_braking_count', 'month',
    'vehicle_id', 'battery_capacity_kwh', 'current_soh_pct',
    # boolean has_* markers are redundancy of missingness, not signal
    'has_speed_data', 'has_motor_power', 'has_aux_power', 'has_regen_power',
    'has_temperature',
]

# Low-signal telemetry flags (structural missingness carriers)
QUALITY_ONLY = ['acceleration_mps2', 'current_speed_kmh']


def load_analysis_frame() -> pd.DataFrame:
    tr = pd.read_parquet(PROCESSED / 'v2_train.parquet')
    va = pd.read_parquet(PROCESSED / 'v2_validation.parquet')
    df = pd.concat([tr, va], ignore_index=True)
    del tr, va
    gc.collect()
    return df


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in ID_COLS and c != TARGET]


def p4_quality(df: pd.DataFrame, feats: list[str]) -> dict:
    report = {'missing_pct': {}, 'constant': [], 'near_constant': [],
              'low_cardinality': [], 'per_vehicle_missing': {}}
    n = len(df)
    for c in feats:
        miss = float(df[c].isna().mean() * 100)
        report['missing_pct'][c] = round(miss, 2)
        if df[c].nunique(dropna=True) <= 1:
            report['constant'].append(c)
        elif df[c].nunique(dropna=True) <= 3:
            report['low_cardinality'].append(c)
        elif df[c].nunique(dropna=True) <= 10:
            report['near_constant'].append(c)
    for veh in sorted(df['vehicle_model'].unique()):
        sub = df[df['vehicle_model'] == veh]
        report['per_vehicle_missing'][veh] = {
            c: round(float(sub[c].isna().mean() * 100), 2)
            for c in feats if sub[c].isna().any()
        }
    return report


def p5_redundancy(df: pd.DataFrame, feats: list[str], corr_thresh=0.95) -> dict:
    num = df[feats].select_dtypes(include=[np.number]).columns.tolist()
    X = df[num].to_numpy(dtype=float)
    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0)
    Xc = np.where(np.isnan(X), np.broadcast_to(mu, X.shape), X)
    keep_mask = sd > 1e-12
    sd_safe = np.where(keep_mask, sd, 1.0)
    Z = (Xc - mu) / sd_safe
    Z[:, ~keep_mask] = 0.0
    C = np.corrcoef(Z.T)
    target_corr = {}
    tgt = df[TARGET].to_numpy(float)
    for i, c in enumerate(num):
        m = np.isfinite(X[:, i]) & np.isfinite(tgt)
        if m.sum() > 10:
            target_corr[c] = float(np.corrcoef(X[m, i], tgt[m])[0, 1])
        else:
            target_corr[c] = 0.0

    # greedy clustering by |corr| >= thresh
    clusters = []
    assigned = set()
    for i, a in enumerate(num):
        if a in assigned or not keep_mask[i]:
            continue
        members = [a]
        assigned.add(a)
        for j, b in enumerate(num):
            if i != j and b not in assigned and not np.isnan(C[i, j]) \
                    and abs(C[i, j]) >= corr_thresh and keep_mask[j]:
                members.append(b)
                assigned.add(b)
        if len(members) > 1:
            clusters.append(members)

    picks = []
    dropped = []
    for members in clusters:
        scores = [(abs(target_corr[m]) if np.isfinite(target_corr[m]) else 0.0, m)
                  for m in members]
        keep = max(scores)[1]
        picks.append(keep)
        dropped.extend(m for m in members if m != keep)

    # correlation summary pairs (top 40)
    pairs = []
    idx = {c: i for i, c in enumerate(num)}
    for i, a in enumerate(num):
        for j in range(i + 1, len(num)):
            v = C[i, j]
            if not np.isnan(v) and abs(v) >= corr_thresh:
                pairs.append({'a': a, 'b': num[j],
                              'corr': round(float(v), 4),
                              'abs_target_a': round(abs(target_corr[a]), 4),
                              'abs_target_b': round(abs(target_corr[num[j]]), 4)})
    pairs.sort(key=lambda p: -abs(p['corr']))

    return {
        'corr_threshold': corr_thresh,
        'clusters': [{ 'members': m, 'keep': picks[i] }
                     for i, m in enumerate(clusters)],
        'dropped_redundant': sorted(set(dropped)),
        'kept_in_clusters': sorted(set(picks)),
        'top_pairs': pairs[:40],
        'feature_count_before': len(feats),
        'feature_count_after_clusters': len(feats) - len(set(dropped)),
    }


def run_cv_importance(df: pd.DataFrame, feats: list[str],
                      model_cls, params, n_outer=5, seed=42) -> dict:
    num_feats = [f for f in feats if pd.api.types.is_numeric_dtype(df[f])]
    # Keep NaN in features (XGBoost / sklearn handle it); only require a target.
    sub = df[['trip_id'] + num_feats + [TARGET]].dropna(subset=[TARGET])
    X = sub[num_feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(float)
    groups = sub['trip_id'].to_numpy()
    gkf = GroupKFold(n_splits=n_outer)
    model = model_cls(**params)
    importances = np.zeros(len(num_feats))
    oof = np.full(len(sub), np.nan)
    for tr_idx, va_idx in gkf.split(X, y, groups):
        model.fit(X[tr_idx], y[tr_idx])
        oof[va_idx] = model.predict(X[va_idx])
        # permutation importance on the validation fold
        base = np.abs(oof[va_idx] - y[va_idx]).mean()
        perm = np.zeros(len(num_feats))
        rng = np.random.default_rng(seed)
        for k in range(len(num_feats)):
            Xp = X[va_idx].copy()
            Xp[:, k] = rng.permutation(Xp[:, k])
            perm[k] = np.abs(model.predict(Xp) - y[va_idx]).mean() - base
        importances += perm
    importances /= n_outer
    mae = float(np.abs(oof - y).mean())
    return {
        'n': int(len(sub)),
        'mae': round(mae, 5),
        'importances': {num_feats[i]: round(float(importances[i]), 6)
                        for i in np.argsort(-importances)},
    }


def main():
    start = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)
    df = load_analysis_frame()
    feats = feature_columns(df)
    feats = [f for f in feats if f not in DROP_ALWAYS]
    print(f'STEP 7.6 P4-P6: FEATURE QUALITY / REDUNDANCY / IMPORTANCE')
    print(f'rows={len(df):,}  features(analysis)={len(feats)}')
    print('=' * 70)

    report = {'n_rows': int(len(df))}

    # ---- P4 quality ----
    report['p4_quality'] = p4_quality(df, feats)
    q = report['p4_quality']
    print('\n[P4] Quality')
    print(f'  constant ({len(q["constant"])}): {q["constant"]}')
    print(f'  low-cardinality ({len(q["low_cardinality"])}): {q["low_cardinality"]}')
    high_miss = sorted([(k, v) for k, v in q['missing_pct'].items() if v >= 40],
                       key=lambda kv: -kv[1])
    print(f'  >=40% missing ({len(high_miss)}):')
    for k, v in high_miss:
        print(f'    {k:34s} {v:5.1f}%')
    print('  Dacia-only missing cols:',
          sorted(q['per_vehicle_missing'].get('Dacia Spring', {})))
    print('  Nissan-only missing cols:',
          sorted(q['per_vehicle_missing'].get('Nissan Leaf', {})))

    # ---- P5 redundancy ----
    report['p5_redundancy'] = p5_redundancy(df, feats)
    r5 = report['p5_redundancy']
    print(f'\n[P5] Redundancy (|r|>={r5["corr_threshold"]})')
    print(f'  clusters: {len(r5["clusters"])}')
    for cl in r5['clusters']:
        print(f'    keep {cl["keep"]:26s} from {cl["members"]}')
    print(f'  dropped ({len(r5["dropped_redundant"])}): {r5["dropped_redundant"]}')
    print(f'  features after cluster-trim: {r5["feature_count_after_clusters"]}')

    # ---- P6 importance on two candidate sets ----
    redundant_set = set(r5['dropped_redundant'])
    base_feats = [f for f in feats if f not in redundant_set]
    print(f'\n[P6] Importance (GroupKFold CV, permutation)')
    print(f'  analysis set: {len(base_feats)} features (after redundancy trim)')

    xgb_params = dict(n_estimators=200, max_depth=3, learning_rate=0.1,
                      subsample=0.8, colsample_bytree=0.8, random_state=42)
    rf_params = dict(n_estimators=200, max_depth=8, min_samples_leaf=5,
                     n_jobs=-1, random_state=42)

    imp_xgb = run_cv_importance(df, base_feats, XGBRegressor, xgb_params)
    print(f'  XGB MAE={imp_xgb["mae"]:.5f}  n={imp_xgb["n"]:,}')
    top_xgb = list(imp_xgb['importances'].items())[:20]
    for name, v in top_xgb:
        print(f'    {name:34s} {v:.6f}')

    imp_rf = run_cv_importance(df, base_feats, RandomForestRegressor, rf_params)
    print(f'  RF  MAE={imp_rf["mae"]:.5f}')
    top_rf = list(imp_rf['importances'].items())[:20]
    for name, v in top_rf:
        print(f'    {name:34s} {v:.6f}')

    report['p6_importance'] = {'xgb': imp_xgb, 'random_forest': imp_rf}
    report['redundancy_trimmed_features'] = base_feats

    with open(OUTPUT, 'w') as f:
        json.dump(report, f, indent=2)
    print(f'\nSaved {OUTPUT}')
    print(f'Runtime: {time.time() - start:.1f}s')


if __name__ == '__main__':
    main()