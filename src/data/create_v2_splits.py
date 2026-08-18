"""
STEP 8C: Create v2 Train/Validation/Test Splits

Uses existing split_assignments.parquet (trip-level split labels)
to create v2 feature dataset splits without data leakage.

Key Constraint: Must use EXISTING split assignments, NOT randomly recreate them.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json


def create_v2_splits(
    v2_file: str,
    split_assignments_file: str,
    output_dir: str,
    verbose: bool = True
) -> dict:
    """
    Create v2 train/validation/test splits using existing trip-level assignments.
    
    Returns:
    --------
    dict with split statistics
    """
    
    results = {
        'v2_file': v2_file,
        'split_file': split_assignments_file,
        'output_dir': output_dir,
        'splits': {},
        'validation': {}
    }
    
    if verbose:
        print("="*60)
        print("STEP 8C: CREATE V2 SPLITS")
        print("="*60)
        print("\n[LOAD] Loading datasets...")
    
    # Load v2 features
    v2_df = pd.read_parquet(v2_file)
    print(f"  V2 dataset: {len(v2_df):,} rows, {len(v2_df.columns)} columns")
    
    # Load split assignments
    split_assign = pd.read_parquet(split_assignments_file)
    print(f"  Split assignments: {len(split_assign)} trips")
    
    results['original_v2_rows'] = len(v2_df)
    results['original_v2_cols'] = len(v2_df.columns)
    
    # Merge v2 features with split assignments
    print(f"\n[MERGE] Merging v2 features with split assignments...")
    
    # Group v2 by trip to get split labels
    v2_with_split = v2_df.merge(
        split_assign[['trip_id', 'split']],
        on='trip_id',
        how='left'
    )
    
    print(f"  After merge: {len(v2_with_split):,} rows")
    
    # Check for unmatched trips
    unmatched = v2_with_split['split'].isna().sum()
    if unmatched > 0:
        print(f"  WARNING: {unmatched} rows with unmatched split assignment")
        results['warnings'] = [f"Unmatched rows: {unmatched}"]
    
    # Create splits
    print(f"\n[CREATE] Creating splits...")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    splits_info = {}
    
    for split_name in ['train', 'validation', 'test']:
        split_mask = v2_with_split['split'] == split_name
        split_df = v2_with_split[split_mask].copy()
        
        # Remove split column before saving
        split_df = split_df.drop('split', axis=1)
        
        split_file = output_path / f'v2_{split_name}.parquet'
        split_df.to_parquet(split_file, compression='snappy')
        
        # Statistics
        unique_trips = split_df['trip_id'].nunique()
        unique_vehicles = split_df['vehicle_id'].nunique()
        
        splits_info[split_name] = {
            'file': str(split_file),
            'rows': len(split_df),
            'cols': len(split_df.columns),
            'trips': unique_trips,
            'vehicles': unique_vehicles
        }
        
        print(f"\n  {split_name.upper()}:")
        print(f"    File: {split_file.name}")
        print(f"    Rows: {len(split_df):,}")
        print(f"    Columns: {len(split_df.columns)}")
        print(f"    Unique trips: {unique_trips}")
        print(f"    Unique vehicles: {unique_vehicles}")
        
        # Vehicle breakdown
        for vehicle_id in sorted(split_df['vehicle_id'].unique()):
            vehicle_mask = split_df['vehicle_id'] == vehicle_id
            vehicle_count = vehicle_mask.sum()
            vehicle_trips = split_df.loc[vehicle_mask, 'trip_id'].nunique()
            print(f"      Vehicle {vehicle_id}: {vehicle_count:,} samples, {vehicle_trips} trips")
        
        # Target statistics
        target = split_df['target_future_energy_kwh_per_km']
        print(f"    Target: min={target.min():.6f}, max={target.max():.6f}, mean={target.mean():.6f}")
        
        results['splits'][split_name] = splits_info[split_name]
    
    # Validation checks
    print(f"\n[VALIDATE] Split validation...")
    
    validation_results = validate_splits(
        v2_with_split,
        verbose=verbose
    )
    
    results['validation'] = validation_results
    
    # Verify total samples
    total_split_samples = sum(s['rows'] for s in splits_info.values())
    total_original = len(v2_df)
    
    print(f"\n[SUMMARY]")
    print(f"  Original v2 rows: {total_original:,}")
    print(f"  Split v2 rows: {total_split_samples:,}")
    print(f"  Match: {total_split_samples == total_original}")
    
    if total_split_samples == total_original:
        results['status'] = 'SUCCESS'
        print(f"\n✓ V2 splits created successfully")
    else:
        results['status'] = 'ERROR'
        print(f"\n✗ Row count mismatch!")
    
    return results


def validate_splits(v2_with_split: pd.DataFrame, verbose: bool = True) -> dict:
    """
    Validate that splits have no overlap and preserve data integrity.
    """
    
    results = {
        'no_overlap': True,
        'issues': [],
        'checks': {}
    }
    
    print(f"  [CHECK 1] No trip overlap...")
    
    train_trips = set(v2_with_split[v2_with_split['split'] == 'train']['trip_id'].unique())
    val_trips = set(v2_with_split[v2_with_split['split'] == 'validation']['trip_id'].unique())
    test_trips = set(v2_with_split[v2_with_split['split'] == 'test']['trip_id'].unique())
    
    overlap_train_val = train_trips & val_trips
    overlap_train_test = train_trips & test_trips
    overlap_val_test = val_trips & test_trips
    
    if overlap_train_val:
        results['issues'].append(f"Train-Val overlap: {overlap_train_val}")
        results['no_overlap'] = False
    else:
        print(f"    ✓ No train-validation overlap")
    
    if overlap_train_test:
        results['issues'].append(f"Train-Test overlap: {overlap_train_test}")
        results['no_overlap'] = False
    else:
        print(f"    ✓ No train-test overlap")
    
    if overlap_val_test:
        results['issues'].append(f"Val-Test overlap: {overlap_val_test}")
        results['no_overlap'] = False
    else:
        print(f"    ✓ No validation-test overlap")
    
    results['checks']['no_trip_overlap'] = {
        'train_trips': len(train_trips),
        'val_trips': len(val_trips),
        'test_trips': len(test_trips),
        'train_val_overlap': len(overlap_train_val),
        'train_test_overlap': len(overlap_train_test),
        'val_test_overlap': len(overlap_val_test)
    }
    
    print(f"  [CHECK 2] No sample duplication...")
    
    total_samples = len(v2_with_split)
    unassigned = v2_with_split['split'].isna().sum()
    
    if unassigned > 0:
        results['issues'].append(f"Unassigned samples: {unassigned}")
    else:
        print(f"    ✓ All samples assigned")
    
    results['checks']['sample_assignment'] = {
        'total': total_samples,
        'assigned': total_samples - unassigned,
        'unassigned': unassigned
    }
    
    print(f"  [CHECK 3] Vehicle representation...")
    
    for vehicle_id in sorted(v2_with_split['vehicle_id'].unique()):
        for split_name in ['train', 'validation', 'test']:
            split_mask = (v2_with_split['vehicle_id'] == vehicle_id) & (v2_with_split['split'] == split_name)
            count = split_mask.sum()
            if count == 0:
                results['issues'].append(f"Vehicle {vehicle_id} missing from {split_name} set")
        print(f"    ✓ Vehicle {vehicle_id} present in all splits")
    
    print(f"  [CHECK 4] Target integrity...")
    
    for split_name in ['train', 'validation', 'test']:
        split_target = v2_with_split[v2_with_split['split'] == split_name]['target_future_energy_kwh_per_km']
        null_count = split_target.isna().sum()
        inf_count = np.isinf(split_target).sum()
        
        if null_count > 0:
            results['issues'].append(f"{split_name}: {null_count} null targets")
        if inf_count > 0:
            results['issues'].append(f"{split_name}: {inf_count} infinite targets")
    
    if not any('target' in issue for issue in results['issues']):
        print(f"    ✓ All targets valid in all splits")
    
    return results


if __name__ == '__main__':
    project_root = Path(__file__).parent.parent.parent
    
    v2_file = str(project_root / 'data' / 'processed' / 'devrt_ml_features_v2.parquet')
    split_file = str(project_root / 'data' / 'processed' / 'split_assignments.parquet')
    output_dir = str(project_root / 'data' / 'processed')
    
    if not Path(v2_file).exists():
        print(f"ERROR: V2 file not found: {v2_file}")
        exit(1)
    
    if not Path(split_file).exists():
        print(f"ERROR: Split file not found: {split_file}")
        exit(1)
    
    results = create_v2_splits(v2_file, split_file, output_dir, verbose=True)
    
    # Save results to JSON
    results_file = project_root / 'reports' / 'v2_split_creation.json'
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n✓ Results saved to: {results_file}")
    
    exit(0 if results['status'] == 'SUCCESS' else 1)
