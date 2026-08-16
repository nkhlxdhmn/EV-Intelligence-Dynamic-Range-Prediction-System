"""
Baseline models for predicting target.

Two simple baselines:
1. Mean baseline: Predict training-set mean for all validation/test samples
2. Vehicle mean baseline: Predict vehicle-specific mean if enough training trips exist

Metrics:
- MAE: Mean Absolute Error
- RMSE: Root Mean Squared Error
- R²: Coefficient of determination
- MAPE: Mean Absolute Percentage Error (with handling for zero/negative values)
- SMAPE: Symmetric Mean Absolute Percentage Error (more robust)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Tuple


def safe_mape(y_true, y_pred):
    """
    Calculate MAPE safely, handling zero/negative actual values.
    
    Returns np.nan if majority of actual values are ≤ 0 (indicating instability).
    """
    # Check if most values are <= 0
    zero_or_negative = (y_true <= 0).sum()
    if zero_or_negative > len(y_true) * 0.2:  # >20% are zero/negative
        return np.nan
    
    # Use only values where y_true > 0
    mask = y_true > 0
    if mask.sum() == 0:
        return np.nan
    
    y_true_safe = y_true[mask]
    y_pred_safe = y_pred[mask]
    
    return np.mean(np.abs((y_true_safe - y_pred_safe) / y_true_safe)) * 100


def smape(y_true, y_pred):
    """
    Symmetric Mean Absolute Percentage Error.
    
    More robust than MAPE for handling zeros and small values.
    Range: 0 to 200 (where 100 is reasonable)
    """
    denominator = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    diff = np.abs(y_true - y_pred) / denominator
    diff[denominator == 0] = 0  # Handle zero division
    return np.mean(diff) * 100


def mae(y_true, y_pred):
    """Mean Absolute Error."""
    return np.mean(np.abs(y_true - y_pred))


def rmse(y_true, y_pred):
    """Root Mean Squared Error."""
    return np.sqrt(np.mean((y_true - y_pred) ** 2))


def r_squared(y_true, y_pred):
    """Coefficient of determination (R²)."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return np.nan
    return 1 - (ss_res / ss_tot)


def mean_baseline(
    train_data: pd.DataFrame,
    val_data: pd.DataFrame,
    test_data: pd.DataFrame,
    target_column: str = 'target_future_energy_kwh_per_km'
) -> Dict:
    """
    Simple mean baseline: predict training-set mean for all samples.
    
    Parameters:
    -----------
    train_data : DataFrame
        Training data
    val_data : DataFrame
        Validation data
    test_data : DataFrame
        Test data
    target_column : str
        Name of target column
        
    Returns:
    --------
    Dict with results and metrics
    """
    
    # Calculate training mean
    y_train = train_data[target_column].values
    train_mean = np.mean(y_train)
    
    # Predictions: constant value for all samples
    y_val_true = val_data[target_column].values
    y_val_pred = np.full_like(y_val_true, train_mean, dtype=float)
    
    y_test_true = test_data[target_column].values
    y_test_pred = np.full_like(y_test_true, train_mean, dtype=float)
    
    # Calculate metrics
    results = {
        'model': 'Mean Baseline',
        'train_mean': train_mean,
        'validation': {
            'MAE': mae(y_val_true, y_val_pred),
            'RMSE': rmse(y_val_true, y_val_pred),
            'R2': r_squared(y_val_true, y_val_pred),
            'MAPE': safe_mape(y_val_true, y_val_pred),
            'SMAPE': smape(y_val_true, y_val_pred),
            'samples': len(y_val_true),
        },
        'test': {
            'MAE': mae(y_test_true, y_test_pred),
            'RMSE': rmse(y_test_true, y_test_pred),
            'R2': r_squared(y_test_true, y_test_pred),
            'MAPE': safe_mape(y_test_true, y_test_pred),
            'SMAPE': smape(y_test_true, y_test_pred),
            'samples': len(y_test_true),
        }
    }
    
    return results


def vehicle_mean_baseline(
    train_data: pd.DataFrame,
    val_data: pd.DataFrame,
    test_data: pd.DataFrame,
    target_column: str = 'target_future_energy_kwh_per_km',
    vehicle_column: str = 'vehicle_id',
    min_training_trips: int = 2
) -> Dict:
    """
    Vehicle-specific mean baseline.
    
    For each vehicle in val/test, predict the mean of that vehicle's training samples.
    If a vehicle doesn't have enough training samples, fall back to global mean.
    
    Parameters:
    -----------
    train_data : DataFrame
        Training data
    val_data : DataFrame
        Validation data
    test_data : DataFrame
        Test data
    target_column : str
        Name of target column
    vehicle_column : str
        Name of vehicle ID column
    min_training_trips : int
        Minimum number of training trips to consider a vehicle
        
    Returns:
    --------
    Dict with results and metrics
    """
    
    # Calculate per-vehicle means in training
    vehicle_means = train_data.groupby(vehicle_column)[target_column].mean().to_dict()
    vehicle_trip_counts = train_data.groupby(vehicle_column)['trip_id'].nunique().to_dict()
    
    # Global mean fallback
    global_mean = train_data[target_column].mean()
    
    def predict_vehicle_mean(row):
        """Predict using vehicle mean or global mean."""
        vehicle_id = row[vehicle_column]
        trip_count = vehicle_trip_counts.get(vehicle_id, 0)
        
        if trip_count >= min_training_trips and vehicle_id in vehicle_means:
            return vehicle_means[vehicle_id]
        else:
            return global_mean
    
    # Make predictions
    y_val_true = val_data[target_column].values
    y_val_pred = val_data.apply(predict_vehicle_mean, axis=1).values
    
    y_test_true = test_data[target_column].values
    y_test_pred = test_data.apply(predict_vehicle_mean, axis=1).values
    
    # Count fallback usage
    val_fallback = (~val_data[vehicle_column].isin(vehicle_means.keys())).sum()
    test_fallback = (~test_data[vehicle_column].isin(vehicle_means.keys())).sum()
    
    results = {
        'model': 'Vehicle Mean Baseline',
        'vehicle_means': vehicle_means,
        'vehicle_trip_counts': vehicle_trip_counts,
        'global_mean': global_mean,
        'validation_fallback_samples': val_fallback,
        'test_fallback_samples': test_fallback,
        'validation': {
            'MAE': mae(y_val_true, y_val_pred),
            'RMSE': rmse(y_val_true, y_val_pred),
            'R2': r_squared(y_val_true, y_val_pred),
            'MAPE': safe_mape(y_val_true, y_val_pred),
            'SMAPE': smape(y_val_true, y_val_pred),
            'samples': len(y_val_true),
        },
        'test': {
            'MAE': mae(y_test_true, y_test_pred),
            'RMSE': rmse(y_test_true, y_test_pred),
            'R2': r_squared(y_test_true, y_test_pred),
            'MAPE': safe_mape(y_test_true, y_test_pred),
            'SMAPE': smape(y_test_true, y_test_pred),
            'samples': len(y_test_true),
        }
    }
    
    return results


if __name__ == '__main__':
    project_root = Path(__file__).parent.parent.parent
    
    train_file = project_root / 'data' / 'processed' / 'train.parquet'
    val_file = project_root / 'data' / 'processed' / 'validation.parquet'
    test_file = project_root / 'data' / 'processed' / 'test.parquet'
    
    # Load data
    print("Loading data...")
    train = pd.read_parquet(train_file)
    val = pd.read_parquet(val_file)
    test = pd.read_parquet(test_file)
    
    print(f"Train: {len(train)} samples")
    print(f"Validation: {len(val)} samples")
    print(f"Test: {len(test)} samples")
    
    # Test 1: Mean Baseline
    print("\n" + "="*60)
    print("MEAN BASELINE")
    print("="*60)
    
    results_mean = mean_baseline(train, val, test)
    
    print(f"\nModel: {results_mean['model']}")
    print(f"Training mean (will be predicted): {results_mean['train_mean']:.6f}")
    
    print("\nValidation Metrics:")
    for metric, value in results_mean['validation'].items():
        if metric != 'samples':
            if isinstance(value, float):
                print(f"  {metric}: {value:.6f}")
            else:
                print(f"  {metric}: {value}")
    
    print("\nTest Metrics:")
    for metric, value in results_mean['test'].items():
        if metric != 'samples':
            if isinstance(value, float):
                print(f"  {metric}: {value:.6f}")
            else:
                print(f"  {metric}: {value}")
    
    # Test 2: Vehicle Mean Baseline
    print("\n" + "="*60)
    print("VEHICLE MEAN BASELINE")
    print("="*60)
    
    results_vehicle = vehicle_mean_baseline(train, val, test)
    
    print(f"\nModel: {results_vehicle['model']}")
    print(f"Global mean (fallback): {results_vehicle['global_mean']:.6f}")
    print(f"\nVehicle-specific means:")
    for vehicle_id, mean_val in results_vehicle['vehicle_means'].items():
        trip_count = results_vehicle['vehicle_trip_counts'][vehicle_id]
        print(f"  Vehicle {vehicle_id}: {mean_val:.6f} (from {trip_count} trips)")
    
    print(f"\nValidation fallback samples: {results_vehicle['validation_fallback_samples']}")
    print(f"Test fallback samples: {results_vehicle['test_fallback_samples']}")
    
    print("\nValidation Metrics:")
    for metric, value in results_vehicle['validation'].items():
        if metric != 'samples':
            if isinstance(value, float):
                print(f"  {metric}: {value:.6f}")
            else:
                print(f"  {metric}: {value}")
    
    print("\nTest Metrics:")
    for metric, value in results_vehicle['test'].items():
        if metric != 'samples':
            if isinstance(value, float):
                print(f"  {metric}: {value:.6f}")
            else:
                print(f"  {metric}: {value}")
