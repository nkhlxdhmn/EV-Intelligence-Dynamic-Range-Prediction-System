"""
STEP 7.6 PHASE 1: Complete data audit of devrt_ml_features_v2.parquet.

Quantifies data integrity issues:
- sample/trip/vehicle counts
- target distribution
- missingness, infinities, duplicates
- timestamp validity
- DISTANCE INTEGRITY (negative distance_since_trip_start, non-monotonic)
- feature cardinality / variance
"""
import pandas as pd
import numpy as np
from pathlib import Path
import json
import time
import tracemalloc

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'processed'
REPORTS_DIR = PROJECT_ROOT / 'reports'
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TARGET = 'target_future_energy_kwh_per_km'


def main():
    start = time.time()
    tracemalloc.start()

    print('=' * 70)
    print('PHASE 1: COMPLETE DATA AUDIT (devrt_ml_features_v2.parquet)')
    print('=' * 70)

    df = pd.read_parquet(DATA_DIR / 'devrt_ml_features_v2.parquet')
    print(f'Loaded: {len(df):,} rows x {len(df.columns)} cols')

    audit = {}

    # ---------------------------------------------------------------
    # Counts
    # ---------------------------------------------------------------
    audit['sample_count'] = len(df)
    audit['trip_count'] = df['trip_id'].nunique()
    audit['vehicle_count'] = df['vehicle_id'].nunique()
    audit['vehicle_model_counts'] = df['vehicle_model'].value_counts().to_dict()

    print(f'\nSamples: {len(df):,}')
    print(f'Trips: {df.trip_id.nunique()}')
    print(f'Vehicles: {df.vehicle_model.value_counts().to_dict()}')

    # ---------------------------------------------------------------
    # Target distribution
    # ---------------------------------------------------------------
    t = df[TARGET]
    audit['target'] = {
        'mean': float(t.mean()), 'median': float(t.median()), 'std': float(t.std()),
        'min': float(t.min()), 'max': float(t.max()),
        'zero_pct': float((t == 0).mean() * 100),
        'negative_pct': float((t < 0).mean() * 100),
        'missing': int(t.isna().sum()),
        'unique_values': int(t.nunique()),
    }
    print(f'\nTarget: mean={t.mean():.4f} std={t.std():.4f} min={t.min():.4f} max={t.max():.4f}')
    print(f'  zero_pct={t.eq(0).mean()*100:.2f}% negative_pct={t.lt(0).mean()*100:.2f}%')
    print(f'  unique values (SOC quantization indicator): {t.nunique()}')

    # ---------------------------------------------------------------
    # Missingness / infinities / duplicates
    # ---------------------------------------------------------------
    missing = df.isna().sum()
    missing_pct = df.isna().mean() * 100
    inf_count = int(np.isinf(df.select_dtypes(include=[np.number])).sum().sum())
    dup_rows = int(df.duplicated().sum())
    dup_trip_rows = int(df.duplicated(subset=['trip_id', 'timestamp']).sum())

    audit['missing'] = {
        'total_nan': int(missing.sum()),
        'inf_count': inf_count,
        'duplicate_rows': dup_rows,
        'dup_trip_timestamp': dup_trip_rows,
    }
    print(f'\nMissing (NaN): {missing.sum():,} cells')
    print(f'Infinite values: {inf_count}')
    print(f'Duplicate rows: {dup_rows}')
    print(f'Duplicate (trip,timestamp): {dup_trip_rows}')

    # Columns with >30% missing
    high_missing = missing_pct[missing_pct > 30].sort_values(ascending=False)
    audit['high_missing_cols'] = {k: round(float(v), 1) for k, v in high_missing.items()}
    print(f'\nColumns with >30% missing: {len(high_missing)}')
    for col, pct in high_missing.items():
        print(f'  {col}: {pct:.1f}%')

    # ---------------------------------------------------------------
    # Timestamp validity
    # ---------------------------------------------------------------
    ts_valid = df['timestamp'].notna().mean() * 100
    audit['timestamp_valid_pct'] = float(ts_valid)
    print(f'\nTimestamp valid: {ts_valid:.1f}%')

    # Check timestamps on plausible date (2023-04)
    ts = pd.to_datetime(df['timestamp'], errors='coerce')
    plausible = ts.dt.year.eq(2023).mean() * 100
    audit['timestamp_year2023_pct'] = float(plausible)
    print(f'Timestamp year==2023: {plausible:.1f}%  (remainder are garbage 2026 dates)')

    # ---------------------------------------------------------------
    # DISTANCE INTEGRITY (critical)
    # ---------------------------------------------------------------
    neg_dist = df['distance_since_trip_start_km'] < -0.001
    audit['negative_distance_count'] = int(neg_dist.sum())
    audit['negative_distance_pct'] = float(neg_dist.mean() * 100)
    audit['negative_distance_trips'] = int(df.loc[neg_dist, 'trip_id'].nunique())
    print(f'\n*** NEGATIVE distance_since_trip_start_km: {neg_dist.sum():,} samples '
          f'({neg_dist.mean()*100:.1f}%) across {df.loc[neg_dist,"trip_id"].nunique()} trips ***')

    # Per-trip monotonicity check (distance_since_trip_start should be non-decreasing)
    non_mono_trips = 0
    non_mono_samples = 0
    for trip_id, g in df.groupby('trip_id'):
        d = g['distance_since_trip_start_km'].to_numpy(float)
        if np.any(np.diff(d) < -0.001):
            non_mono_trips += 1
            non_mono_samples += int(np.sum(np.diff(d) < -0.001))
    audit['non_monotonic_distance_trips'] = non_mono_trips
    audit['non_monotonic_distance_samples'] = non_mono_samples
    print(f'Non-monotonic distance in {non_mono_trips} trips ({non_mono_samples} decreases)')

    # Distance range per trip sanity
    trip_dists = df.groupby('trip_id')['distance_since_trip_start_km'].agg(['min', 'max', 'count'])
    trip_neg = trip_dists[trip_dists['min'] < -0.001]
    audit['trips_with_negative_start'] = int(len(trip_neg))
    print(f'Trips with negative min distance: {len(trip_neg)}')

    # ---------------------------------------------------------------
    # Feature cardinality / variance
    # ---------------------------------------------------------------
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    low_var = []
    constant = []
    for col in numeric_cols:
        v = df[col].nunique(dropna=True)
        if v <= 1:
            constant.append(col)
        elif v <= 3:
            low_var.append(col)
    audit['constant_features'] = constant
    audit['low_cardinality_features'] = low_var
    print(f'\nConstant features (nunique<=1): {constant}')
    print(f'Low-cardinality (<=3): {low_var}')

    # ---------------------------------------------------------------
    # Feature dtype summary
    # ---------------------------------------------------------------
    dtype_summary = df.dtypes.astype(str).value_counts().to_dict()
    audit['dtype_summary'] = dtype_summary

    # ---------------------------------------------------------------
    # Save audit CSV
    # ---------------------------------------------------------------
    feature_rows = []
    for col in df.columns:
        if col in ('trip_id', 'vehicle_id', 'timestamp', 'vehicle_model', TARGET):
            continue
        s = df[col]
        feature_rows.append({
            'feature': col,
            'dtype': str(s.dtype),
            'missing_pct': round(float(s.isna().mean() * 100), 2),
            'unique_count': int(s.nunique(dropna=True)),
            'variance': round(float(s.dropna().var()), 6) if pd.api.types.is_numeric_dtype(s) else np.nan,
            'target_corr': round(float(df[col].corr(t)), 4) if pd.api.types.is_numeric_dtype(s) else np.nan,
        })
    feat_audit = pd.DataFrame(feature_rows)
    feat_audit.to_csv(REPORTS_DIR / 'optimization_data_audit.csv', index=False)
    print(f'\nSaved reports/optimization_data_audit.csv ({len(feat_audit)} features)')

    # Save JSON summary
    with open(REPORTS_DIR / 'optimization_data_audit.json', 'w') as f:
        json.dump(audit, f, indent=2, default=str)

    current, peak = tracemalloc.get_traced_memory()
    print(f'\nPeak RAM: {peak/1024/1024:.2f} MB')
    print(f'Runtime: {time.time()-start:.2f}s')
    print('\nPHASE 1 COMPLETE')


if __name__ == '__main__':
    main()