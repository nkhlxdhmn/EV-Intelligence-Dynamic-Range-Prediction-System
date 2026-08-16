"""
Target Leakage Audit Module.
Scans the final ML dataset for potential data leakage.

Updated for STEP 9: inspects ALL expanded features and flags suspicious
future/end/remaining/total-trip indicators and mathematical leakage.
"""

import pandas as pd

FORBIDDEN_KEYWORDS = [
    'future', 'end', 'next', 'target', 'total_trip', 'remaining',
    'trip_total', 'future_soc', 'future_speed', 'future_altitude', 'future_energy',
    'total_energy', 'trip_end', 'trip_final', 'arrival'
]

# Features that represent trip-end or total-trip information (leakage)
FORBIDDEN_PATTERNS = [
    'remaining_trip', 'total_trip', 'trip_total', 'trip_end_soc',
    'trip_total_energy', 'remaining_distance', 'remaining_time',
    'future_', 'target_'
]

# Derived evaluation outputs (legitimately depend on the target)
DERIVED_OUTPUT_COLUMNS = {
    'prediction', 'predicted_target', 'signed_error', 'absolute_error',
    'prediction_xgb'
}

TARGET_COL = 'target_future_energy_kwh_per_km'

# Aliases used in prediction/evaluation files (they contain the true target)
KNOWN_TARGET_COLUMNS = {
    'target_future_energy_kwh_per_km',
    'target',
    'actual_target',
}

# Allowed features that contain 'total' or 'trip' but are PAST-only (safe)
ALLOWED_EXCEPTIONS = {
    'trip_distance_so_far_km', 'trip_elapsed_time_min',
    'distance_since_trip_start_km', 'time_since_trip_start_min',
    # STEP 7.6 P9-P13: 'is_weekend' is a calendar attribute (the 'end' substring
    # is a false positive), and all next_* look-ahead TERRAIN columns are
    # derived from static altitude (map geography), which is known before the
    # trip begins -- NOT from future sensor/telemetry readings. These are
    # legitimate predictive features for a route-aware range estimator.
    'is_weekend', 'hour_sin', 'hour_cos', 'trip_phase',
    'next_1km_net_elev_m', 'next_1km_gradient_pct', 'next_1km_gain_m', 'next_1km_loss_m',
    'next_2km_net_elev_m', 'next_2km_gradient_pct', 'next_2km_gain_m', 'next_2km_loss_m',
    'next_5km_net_elev_m', 'next_5km_gradient_pct', 'next_5km_gain_m', 'next_5km_loss_m',
    'next_5km_uphill_frac', 'next_5km_downhill_frac', 'next_5km_flat_frac',
}


def audit_dataset_columns(columns):
    """
    Check if any column names contain forbidden keywords (except the target).
    """
    violations = []

    for col in columns:
        if col in KNOWN_TARGET_COLUMNS:
            continue
        if col.lower() in DERIVED_OUTPUT_COLUMNS:
            continue

        col_lower = col.lower()

        # Skip safe past-only trip context columns
        if col_lower in {x.lower() for x in ALLOWED_EXCEPTIONS}:
            continue

        # 1) Forbidden keyword substring check (backwards-compatible)
        keyword_hit = None
        for keyword in FORBIDDEN_KEYWORDS:
            if keyword in col_lower:
                keyword_hit = keyword
                break

        # 2) Forbidden structured pattern check
        pattern_hit = None
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in col_lower:
                pattern_hit = pattern
                break

        if keyword_hit is not None:
            violations.append(
                f"Column '{col}' contains forbidden keyword '{keyword_hit}'"
            )
        elif pattern_hit is not None:
            violations.append(
                f"Column '{col}' matches forbidden leakage pattern '{pattern_hit}'"
            )

    return violations


def check_mathematical_leakage(df, corr_threshold=0.99):
    """
    Check if any feature is (near-)perfectly correlated with the target.
    In prediction files, skip prediction/error columns which are derived outputs.
    """
    violations = []

    target_col = None
    for candidate in ['target_future_energy_kwh_per_km', 'actual_target', 'target']:
        if candidate in df.columns:
            target_col = candidate
            break
    if target_col is None:
        return ["Target column missing"]

    # Columns that legitimately depend on the target (evaluation outputs)
    derived_outputs = {'prediction', 'predicted_target', 'signed_error',
                       'absolute_error', 'prediction_xgb'}

    numeric_df = df.select_dtypes(include=['float64', 'int64', 'float32', 'int32', 'uint8', 'bool'])

    correlations = numeric_df.corr(method='pearson')[target_col]

    for col, corr in correlations.items():
        if col == target_col:
            continue
        if col.lower() in derived_outputs:
            continue
        if pd.isna(corr):
            continue
        if abs(corr) > corr_threshold:
            violations.append(
                f"Column '{col}' is mathematically near-identical to target "
                f"(corr={corr:.3f})"
            )

    return violations


def check_constant_features(df):
    """Flag features with zero variance (likely non-informative)."""
    flags = []
    numeric_df = df.select_dtypes(include=['float64', 'int64', 'float32', 'int32', 'uint8', 'bool'])
    for col in numeric_df.columns:
        if numeric_df[col].nunique(dropna=False) <= 1:
            flags.append(f"Column '{col}' is constant (nunique <= 1)")
    return flags


def run_full_audit(parquet_path):
    """Run full audit on a parquet dataset."""
    df = pd.read_parquet(parquet_path)

    violations = []
    violations.extend(audit_dataset_columns(df.columns))
    violations.extend(check_mathematical_leakage(df))
    violations.extend(check_constant_features(df))

    return violations


if __name__ == '__main__':
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / 'data' / 'processed'

    datasets = [
        'v2_train.parquet',
        'v2_validation.parquet',
        'v2_test.parquet',
        'devrt_ml_features_v2.parquet',
        'validation_predictions_step9.parquet',
        'test_predictions_final.parquet',
    ]

    print('=' * 70)
    print('LEAKAGE AUDIT (STEP 9)')
    print('=' * 70)

    all_pass = True
    for ds in datasets:
        path = data_dir / ds
        if not path.exists():
            print(f'\n  {ds}: FILE NOT FOUND (skipped)')
            continue
        print(f'\n  Auditing: {ds}')
        violations = run_full_audit(str(path))
        if violations:
            all_pass = False
            print(f'    FAIL: {len(violations)} violation(s)')
            for v in violations:
                print(f'      - {v}')
        else:
            print(f'    PASS')

    print('\n' + '=' * 70)
    if all_pass:
        print('LEAKAGE AUDIT: PASS')
    else:
        print('LEAKAGE AUDIT: FAIL')
    print('=' * 70)
    sys.exit(0 if all_pass else 1)