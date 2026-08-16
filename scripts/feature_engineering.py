"""
Feature Engineering & Target Construction for EV Intelligence Project.
Memory-safe extraction of DEVRT features and leakage-free future-window targets.
"""

import os
import glob
import gc
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from data.devrt_parser import timestamp_to_epoch_seconds

INPUT_DIR = "data/interim/devrt"
OUTPUT_DIR = "data/processed"
TARGET_DISTANCE_WINDOW_KM = 5.0

os.makedirs(OUTPUT_DIR, exist_ok=True)

def construct_features_and_targets(df):
    """
    Constructs rolling past features and the future 5km target.
    """
    # Sort just in case
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    n_rows = len(df)
    
    # ---------------------------------------------------------
    # 1. COMMON FEATURES (Dacia & Nissan)
    # ---------------------------------------------------------
    df['current_soc_pct'] = df['soc_pct']
    df['battery_capacity_kwh'] = df['battery_capacity_kwh']
    df['current_altitude_m'] = df['altitude_m']
    df['vehicle_model'] = np.where(df['vehicle_id'] == 6, 'Dacia Spring', 'Nissan Leaf')
    
    # Past 1km Gradient
    # We find the row 1km in the past to calculate terrain.
    distances = df['distance_km'].values
    altitudes = df['altitude_m'].values
    
    past_1km_gradient = np.zeros(n_rows)
    terrain_class = np.full(n_rows, 'FLAT', dtype=object)
    
    for i in range(n_rows):
        current_dist = distances[i]
        # Find index in the past where distance is approx current_dist - 1.0
        # If not enough distance has passed, just use the start of the trip
        past_dist_target = max(0, current_dist - 1.0)
        
        # searchsorted finds the first index where distance >= past_dist_target
        past_idx = np.searchsorted(distances, past_dist_target)
        if past_idx > i:
            past_idx = i  # Safeguard
            
        delta_d = (current_dist - distances[past_idx]) * 1000 # meters
        delta_a = altitudes[i] - altitudes[past_idx]
        
        if delta_d >= 50:  # Require at least 50m of movement to calculate a stable gradient
            grad = (delta_a / delta_d) * 100
        else:
            grad = 0.0
            
        past_1km_gradient[i] = grad
        if grad > 1.0:
            terrain_class[i] = 'UPHILL'
        elif grad < -1.0:
            terrain_class[i] = 'DOWNHILL'
            
    df['past_1km_gradient_pct'] = past_1km_gradient
    df['terrain_class'] = terrain_class

    # ---------------------------------------------------------
    # 2. OPTIONAL FEATURES (Nissan)
    # ---------------------------------------------------------
    if 'speed_kmh' in df.columns and not df['speed_kmh'].isna().all():
        df['current_speed_kmh'] = df['speed_kmh']
        df['current_ambient_temperature_c'] = df['ambient_temperature_c']
        df['current_motor_power_kw'] = df['motor_power_kw']
        
        # Use pandas rolling over the last ~10 rows (approx 1-2 km depending on sampling)
        # We must shift(1) to ensure strictly PAST information.
        shifted_speed = df['speed_kmh'].shift(1)
        df['past_mean_speed_kmh'] = shifted_speed.rolling(window=10, min_periods=1).mean()
        df['past_speed_std'] = shifted_speed.rolling(window=10, min_periods=1).std().fillna(0)
        
        # Acceleration (m/s^2)
        time_s = timestamp_to_epoch_seconds(pd.to_datetime(df['timestamp'], utc=True))
        delta_v = df['speed_kmh'].diff() / 3.6
        delta_t = time_s.diff()
        accel = np.where(delta_t > 0, delta_v / delta_t, 0)
        df['past_mean_acceleration_mps2'] = pd.Series(accel).shift(1).rolling(window=10, min_periods=1).mean()
    else:
        # Fill Dacia with NaNs for these features
        df['current_speed_kmh'] = np.nan
        df['current_ambient_temperature_c'] = np.nan
        df['current_motor_power_kw'] = np.nan
        df['past_mean_speed_kmh'] = np.nan
        df['past_speed_std'] = np.nan
        df['past_mean_acceleration_mps2'] = np.nan
        
    # ---------------------------------------------------------
    # 3. TARGET CONSTRUCTION (Future 5km Window)
    # ---------------------------------------------------------
    future_energy_target = np.full(n_rows, np.nan)
    socs = df['soc_pct'].values
    caps = df['battery_capacity_kwh'].values
    
    rejected_boundary = 0
    rejected_soc = 0
    rejected_distance = 0
    
    for i in range(n_rows):
        current_dist = distances[i]
        target_dist = current_dist + TARGET_DISTANCE_WINDOW_KM
        
        # Find the first index where distance >= target_dist
        future_idx = np.searchsorted(distances, target_dist)
        
        if future_idx >= n_rows:
            # We hit the end of the trip before covering 5km.
            rejected_boundary += 1
            continue
            
        actual_future_dist = distances[future_idx]
        delta_d = actual_future_dist - current_dist
        
        if delta_d < 4.5:
            # Did not actually travel far enough (edge case near end of trip)
            rejected_distance += 1
            continue
            
        start_soc = socs[i]
        end_soc = socs[future_idx]
        cap = caps[i]
        
        if pd.isna(start_soc) or pd.isna(end_soc) or pd.isna(cap):
            rejected_soc += 1
            continue
            
        energy_consumed_kwh = (start_soc - end_soc) * cap / 100.0
        kwh_per_km = energy_consumed_kwh / delta_d
        
        future_energy_target[i] = kwh_per_km
        
    df['target_future_energy_kwh_per_km'] = future_energy_target
    
    # Drop rows with NaN target
    initial_rows = n_rows
    df_valid = df.dropna(subset=['target_future_energy_kwh_per_km'])
    valid_rows = len(df_valid)
    
    stats = {
        'trip_id': df['trip_id'].iloc[0],
        'vehicle_id': df['vehicle_id'].iloc[0],
        'candidate_samples': initial_rows,
        'valid_samples': valid_rows,
        'rejected_samples': initial_rows - valid_rows,
        'invalid_soc': rejected_soc,
        'invalid_distance': rejected_distance,
        'cross_boundary': rejected_boundary,
        'other': 0
    }
    
    # Select final columns
    final_cols = [
        'trip_id', 'vehicle_id', 'timestamp', 'vehicle_model',
        'current_soc_pct', 'battery_capacity_kwh', 'current_altitude_m', 
        'past_1km_gradient_pct', 'terrain_class',
        'current_speed_kmh', 'current_ambient_temperature_c', 'current_motor_power_kw',
        'past_mean_speed_kmh', 'past_speed_std', 'past_mean_acceleration_mps2',
        'target_future_energy_kwh_per_km'
    ]
    
    return df_valid[final_cols], stats

def main():
    print("Starting Memory-Safe Feature Engineering...")
    
    files = glob.glob(f"{INPUT_DIR}/*_standardized.parquet")
    print(f"Found {len(files)} trips.")
    
    all_stats = []
    parquet_writer = None
    output_path = f"{OUTPUT_DIR}/devrt_ml_features.parquet"
    
    for i, file in enumerate(files):
        df = pd.read_parquet(file)
        
        df_feat, stats = construct_features_and_targets(df)
        all_stats.append(stats)
        
        if len(df_feat) > 0:
            table = pa.Table.from_pandas(df_feat, preserve_index=False)
            
            if parquet_writer is None:
                # Initialize writer with schema from first valid table
                parquet_writer = pq.ParquetWriter(output_path, table.schema)
            else:
                # Cast table to the established schema (allow unsafe truncation of nanoseconds to microseconds)
                table = table.cast(parquet_writer.schema, safe=False)
                
            parquet_writer.write_table(table)
            
        del df, df_feat
        gc.collect()
        
        print(f"Processed {i+1}/{len(files)} trips...", end='\r')
        
    if parquet_writer:
        parquet_writer.close()
        
    print(f"\nSaved ML dataset to {output_path}")
    
    stats_df = pd.DataFrame(all_stats)
    stats_df.to_csv(f"{OUTPUT_DIR}/devrt_target_statistics.csv", index=False)
    
    print("\n--- Target Statistics ---")
    print(f"Total Candidates: {stats_df['candidate_samples'].sum()}")
    print(f"Total Valid: {stats_df['valid_samples'].sum()}")
    print(f"Rejected (Trip Boundary): {stats_df['cross_boundary'].sum()}")
    print("-------------------------\n")

if __name__ == "__main__":
    main()
