"""
STEP 7: Create temporal/grouped train-validation-test split.

Split strategy:
- Trip-level splitting (not random sample shuffling)
- 70% train, 15% validation, 15% test
- Stratified by vehicle to maintain representation
- Sorted by timestamp within each split
- No leakage between splits
"""

import pandas as pd
import numpy as np
from pathlib import Path

def create_split(
    input_parquet: str,
    output_split_file: str,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42,
    verbose: bool = True
) -> tuple:
    """
    Create a stratified trip-level train/val/test split.
    
    Parameters:
    -----------
    input_parquet : str
        Path to input ML features parquet file
    output_split_file : str
        Path to save split_assignments.parquet
    train_ratio : float
        Proportion of trips for training (default 0.70)
    val_ratio : float
        Proportion of trips for validation (default 0.15)
    test_ratio : float
        Proportion of trips for testing (default 0.15)
    random_state : int
        Random seed for reproducibility
    verbose : bool
        Print debug information
        
    Returns:
    --------
    tuple : (split_df, stats_dict)
        split_df: DataFrame with columns [trip_id, vehicle_id, vehicle_model, split]
        stats_dict: Dictionary with split statistics
    """
    
    np.random.seed(random_state)
    
    # Load full dataset
    if verbose:
        print(f"Loading dataset from {input_parquet}...")
    df = pd.read_parquet(input_parquet)
    
    # Get unique trips with vehicle info
    trip_info = df.groupby('trip_id').agg({
        'vehicle_id': 'first',
        'vehicle_model': 'first'
    }).reset_index()
    
    if verbose:
        print(f"Total trips: {len(trip_info)}")
        print(f"Total samples: {len(df)}")
    
    # Get unique trips per vehicle
    vehicles = trip_info['vehicle_id'].unique()
    if verbose:
        print(f"Vehicles: {vehicles}")
        for vid in sorted(vehicles):
            vehicle_name = trip_info[trip_info['vehicle_id'] == vid]['vehicle_model'].iloc[0]
            trip_count = len(trip_info[trip_info['vehicle_id'] == vid])
            print(f"  {vehicle_name} (ID {vid}): {trip_count} trips")
    
    # Stratified split: split each vehicle's trips separately, then combine
    split_assignments = []
    
    for vehicle_id in sorted(vehicles):
        vehicle_trips = trip_info[trip_info['vehicle_id'] == vehicle_id].copy()
        vehicle_name = vehicle_trips['vehicle_model'].iloc[0]
        n_trips = len(vehicle_trips)
        
        # Shuffle trips within vehicle
        vehicle_trips_shuffled = vehicle_trips.sample(
            n=n_trips, random_state=random_state + vehicle_id
        ).reset_index(drop=True)
        
        # Calculate split boundaries
        n_train = int(np.ceil(n_trips * train_ratio))
        n_val = int(np.ceil(n_trips * val_ratio))
        # n_test = n_trips - n_train - n_val
        
        # Assign splits
        vehicle_trips_shuffled['split'] = 'train'
        vehicle_trips_shuffled.loc[n_train:n_train+n_val-1, 'split'] = 'validation'
        vehicle_trips_shuffled.loc[n_train+n_val:, 'split'] = 'test'
        
        split_assignments.append(vehicle_trips_shuffled)
        
        if verbose:
            train_count = len(vehicle_trips_shuffled[vehicle_trips_shuffled['split'] == 'train'])
            val_count = len(vehicle_trips_shuffled[vehicle_trips_shuffled['split'] == 'validation'])
            test_count = len(vehicle_trips_shuffled[vehicle_trips_shuffled['split'] == 'test'])
            print(f"  {vehicle_name}: Train={train_count}, Val={val_count}, Test={test_count}")
    
    # Combine all splits
    split_df = pd.concat(split_assignments, ignore_index=True)
    
    # Verify no duplicates
    assert split_df['trip_id'].nunique() == len(split_df), "Duplicate trip_id in split"
    assert split_df['trip_id'].nunique() == len(trip_info), "Missing trips in split"
    
    # Save split assignments
    if verbose:
        print(f"\nSaving split assignments to {output_split_file}...")
    split_df.to_parquet(output_split_file, index=False)
    
    # Create statistics
    stats = {
        'total_trips': len(split_df),
        'total_samples': len(df),
        'train_trips': len(split_df[split_df['split'] == 'train']),
        'validation_trips': len(split_df[split_df['split'] == 'validation']),
        'test_trips': len(split_df[split_df['split'] == 'test']),
    }
    
    if verbose:
        print(f"\n=== SPLIT SUMMARY ===")
        print(f"Train trips:      {stats['train_trips']} ({stats['train_trips']/stats['total_trips']*100:.1f}%)")
        print(f"Validation trips: {stats['validation_trips']} ({stats['validation_trips']/stats['total_trips']*100:.1f}%)")
        print(f"Test trips:       {stats['test_trips']} ({stats['test_trips']/stats['total_trips']*100:.1f}%)")
    
    return split_df, stats, df


def create_split_datasets(
    input_parquet: str,
    split_assignments: pd.DataFrame,
    output_train: str,
    output_val: str,
    output_test: str,
    verbose: bool = True
) -> dict:
    """
    Create separate train, validation, and test parquet files.
    
    Each split is sorted by trip_id and timestamp (for time-series integrity).
    """
    
    df = pd.read_parquet(input_parquet)
    
    # Merge split assignments with data
    df_with_splits = df.merge(
        split_assignments[['trip_id', 'split']],
        on='trip_id',
        how='left'
    )
    
    assert df_with_splits['split'].isna().sum() == 0, "Some samples missing split assignment"
    
    # Create separate datasets, sorted by trip_id and timestamp
    datasets = {}
    split_files = {
        'train': output_train,
        'validation': output_val,
        'test': output_test
    }
    
    for split_name, output_file in split_files.items():
        split_data = df_with_splits[df_with_splits['split'] == split_name].copy()
        split_data = split_data.sort_values(['trip_id', 'timestamp'])
        split_data = split_data.drop('split', axis=1)  # Remove split column from data
        
        if verbose:
            print(f"Saving {split_name}: {len(split_data)} samples to {output_file}")
        
        split_data.to_parquet(output_file, index=False)
        
        datasets[split_name] = {
            'file': output_file,
            'samples': len(split_data),
            'trips': split_data['trip_id'].nunique()
        }
    
    return datasets


if __name__ == '__main__':
    # Configuration
    project_root = Path(__file__).parent.parent.parent  # Go up to project root
    input_file = project_root / 'data' / 'processed' / 'devrt_ml_features.parquet'
    output_split_file = project_root / 'data' / 'processed' / 'split_assignments.parquet'
    
    output_train = project_root / 'data' / 'processed' / 'train.parquet'
    output_val = project_root / 'data' / 'processed' / 'validation.parquet'
    output_test = project_root / 'data' / 'processed' / 'test.parquet'
    
    # Create splits
    split_df, stats, full_df = create_split(
        str(input_file),
        str(output_split_file),
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        random_state=42,
        verbose=True
    )
    
    print("\n" + "="*60)
    print("Creating separate split datasets...")
    print("="*60)
    
    # Create split datasets
    datasets = create_split_datasets(
        str(input_file),
        split_df,
        str(output_train),
        str(output_val),
        str(output_test),
        verbose=True
    )
    
    print("\n" + "="*60)
    print("FINAL STATISTICS")
    print("="*60)
    print(f"Total samples: {stats['total_samples']}")
    print(f"Total trips: {stats['total_trips']}")
    print(f"\nTrain:")
    print(f"  Trips: {stats['train_trips']}")
    print(f"  Samples: {datasets['train']['samples']}")
    print(f"\nValidation:")
    print(f"  Trips: {stats['validation_trips']}")
    print(f"  Samples: {datasets['validation']['samples']}")
    print(f"\nTest:")
    print(f"  Trips: {stats['test_trips']}")
    print(f"  Samples: {datasets['test']['samples']}")
    
    # Verify totals
    total_samples = sum(d['samples'] for d in datasets.values())
    total_trips = sum(d['trips'] for d in datasets.values())
    assert total_samples == stats['total_samples'], "Sample count mismatch"
    assert total_trips == stats['total_trips'], "Trip count mismatch"
    print(f"\n✓ Verification passed: {total_samples} samples, {total_trips} trips")
