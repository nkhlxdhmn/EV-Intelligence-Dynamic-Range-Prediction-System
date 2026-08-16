"""
Feature Completeness Analysis for STEP 8D Models
"""

import pandas as pd
from pathlib import Path

project_root = Path(".")
train_file = 'data/processed/v2_train.parquet'

df = pd.read_parquet(train_file)

# Experiment features (from train_experiments.py)
experiments = {
    'A_BASIC': [
        'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',
        'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',
        'terrain_class', 'elevation_gain_1km', 'elevation_loss_1km'
    ],
    'B_DRIVING': [
        'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',
        'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',
        'terrain_class', 'elevation_gain_1km', 'elevation_loss_1km',
        'current_speed_kmh', 'mean_speed_500m', 'mean_speed_1km',
        'speed_variance_500m', 'speed_variance_1km',
        'mean_acceleration_500m', 'acceleration_variance_500m'
    ]
}

print("="*70)
print("FEATURE COMPLETENESS ANALYSIS")
print("="*70)

for exp_name, features in experiments.items():
    print(f"\n{exp_name}:")
    print("-" * 70)
    
    # Filter to available features
    available_features = [f for f in features if f in df.columns]
    
    subset = df[available_features]
    
    null_counts = subset.isna().sum()
    null_pct = (subset.isna().sum() / len(subset)) * 100
    
    for feature in available_features:
        count = df[feature].isna().sum()
        pct = (count / len(df)) * 100
        print(f"  {feature:40s}: {count:5,} null ({pct:5.1f}%)")
    
    # Total complete rows
    complete_rows = subset.notna().all(axis=1).sum()
    print(f"\nComplete rows (all {len(available_features)} features): {complete_rows:,} / {len(df):,} ({complete_rows/len(df)*100:.1f}%)")
