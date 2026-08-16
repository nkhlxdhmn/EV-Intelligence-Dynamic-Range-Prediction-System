"""
Exploratory Data Analysis (EDA) Script for EV Intelligence Project
Performs memory-safe aggregation and visualization of DEVRT dataset.
"""

import os
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

warnings.filterwarnings('ignore')

INPUT_DIR = "data/interim/devrt"
OUTPUT_DIR = "reports/figures/eda"
STATS_DIR = "reports"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(STATS_DIR, exist_ok=True)

# Selected features for aggregation
FEATURES = [
    'soc_pct', 'soh_pct', 'speed_kmh', 'altitude_m', 'distance_km',
    'ambient_temperature_c', 'motor_power_kw', 'aux_power_kw', 
    'regen_power_kw', 'motor_temperature_c', 'motor_torque_nm', 
    'motor_rpm', 'battery_capacity_kwh'
]

def calculate_trip_energy(df):
    """Calculate trip-level energy consumption per km."""
    if df.empty or len(df) < 2:
        return np.nan
        
    start_soc = df['soc_pct'].iloc[0]
    end_soc = df['soc_pct'].iloc[-1]
    capacity = df['battery_capacity_kwh'].iloc[0]
    distance = df['distance_km'].max() - df['distance_km'].min()
    
    if pd.isna(start_soc) or pd.isna(end_soc) or pd.isna(capacity) or distance <= 0:
        return np.nan
        
    energy_kwh = (start_soc - end_soc) * capacity / 100.0
    return energy_kwh / distance

def extract_trip_features(df):
    """Extract trip-level aggregated features."""
    if df.empty:
        return {}
        
    # Calculate gradients
    df['delta_alt'] = df['altitude_m'].diff()
    df['delta_dist'] = df['distance_km'].diff() * 1000  # in meters
    
    # Safe gradient calculation
    df['gradient_pct'] = np.where(
        (df['delta_dist'] > 0) & (df['delta_dist'] >= 5),  # Min 5m movement to avoid noise
        (df['delta_alt'] / df['delta_dist']) * 100,
        0
    )
    
    # Acceleration
    # time is in seconds if we cast datetime to int64 / 1e9, but we can just use timestamp diff
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['delta_time_s'] = df['timestamp'].diff().dt.total_seconds()
    
    df['acceleration'] = np.where(
        df['delta_time_s'] > 0,
        df['speed_kmh'].diff() / 3.6 / df['delta_time_s'], # m/s^2
        0
    )
    
    return {
        'vehicle': df['vehicle_id'].iloc[0],
        'energy_kwh_per_km': calculate_trip_energy(df),
        'avg_speed': df['speed_kmh'].mean(),
        'avg_temp': df['ambient_temperature_c'].mean(),
        'avg_gradient': df['gradient_pct'].mean(),
        'avg_regen': df['regen_power_kw'].mean() if 'regen_power_kw' in df.columns else np.nan,
        'elevation_gain': df.loc[df['delta_alt'] > 0, 'delta_alt'].sum(),
        'elevation_loss': df.loc[df['delta_alt'] < 0, 'delta_alt'].sum()
    }

def main():
    print("Starting Memory-Safe EDA...")
    
    files = glob.glob(f"{INPUT_DIR}/*_standardized.parquet")
    print(f"Found {len(files)} DEVRT files to process.")
    
    trip_summaries = []
    global_stats = []
    
    dacia_sample = None
    nissan_sample = None

    # Step 1: Memory-Safe Aggregation & Trip Summaries
    for i, file in enumerate(files):
        df = pd.read_parquet(file)
        
        # Save sample dataframes for plotting
        if dacia_sample is None and 'DACIA' in file:
            dacia_sample = df.copy()
            dacia_sample['timestamp'] = pd.to_datetime(dacia_sample['timestamp'])
        if nissan_sample is None and 'NISSAN' in file:
            nissan_sample = df.copy()
            nissan_sample['timestamp'] = pd.to_datetime(nissan_sample['timestamp'])
            
        trip_summaries.append(extract_trip_features(df))
        
        # Global variable stats (min, max, mean, count)
        for feat in FEATURES:
            if feat in df.columns:
                valid_data = df[feat].dropna()
                if len(valid_data) > 0:
                    global_stats.append({
                        'feature': feat,
                        'count': len(valid_data),
                        'sum': valid_data.sum(),
                        'min': valid_data.min(),
                        'max': valid_data.max()
                    })
                    
        print(f"Processed {i+1}/{len(files)}", end='\r')

    print("\n\n--- Global Stats ---")
    stats_df = pd.DataFrame(global_stats)
    agg_stats = stats_df.groupby('feature').agg({
        'count': 'sum',
        'sum': 'sum',
        'min': 'min',
        'max': 'max'
    }).reset_index()
    agg_stats['mean'] = agg_stats['sum'] / agg_stats['count']
    agg_stats.to_csv(f"{STATS_DIR}/devrt_global_stats.csv", index=False)
    print(agg_stats[['feature', 'count', 'min', 'max', 'mean']])
    
    print("\n--- Trip Summaries (First 5) ---")
    trips_df = pd.DataFrame(trip_summaries)
    trips_df.dropna(subset=['energy_kwh_per_km'], inplace=True)
    trips_df.to_csv(f"{STATS_DIR}/devrt_trip_summaries.csv", index=False)
    print(trips_df.head())
    
    # Step 2: Visualization
    print("\nGenerating Plots...")
    sns.set_theme(style="whitegrid")
    
    # Plot 1: SOC Distribution across trips (using the two samples)
    plt.figure(figsize=(10, 5))
    if dacia_sample is not None:
        sns.kdeplot(dacia_sample['soc_pct'], label="Dacia Sample", fill=True)
    if nissan_sample is not None:
        sns.kdeplot(nissan_sample['soc_pct'], label="Nissan Sample", fill=True)
    plt.title("01 - Sample SOC Distribution")
    plt.legend()
    plt.savefig(f"{OUTPUT_DIR}/01_soc_distribution.png")
    plt.close()
    
    # Plot 2: Speed Distribution
    plt.figure(figsize=(10, 5))
    if dacia_sample is not None and not dacia_sample['speed_kmh'].isna().all():
        sns.kdeplot(dacia_sample['speed_kmh'].dropna(), label="Dacia Sample", fill=True)
    if nissan_sample is not None and not nissan_sample['speed_kmh'].isna().all():
        sns.kdeplot(nissan_sample['speed_kmh'].dropna(), label="Nissan Sample", fill=True)
    plt.title("02 - Sample Speed Distribution")
    plt.legend()
    plt.savefig(f"{OUTPUT_DIR}/02_speed_distribution.png")
    plt.close()
    
    # Plot 3: Energy Consumption Distribution (Trip Level)
    plt.figure(figsize=(10, 5))
    sns.histplot(trips_df['energy_kwh_per_km'], bins=20, kde=True, color='teal')
    plt.title("03 - Trip Energy Consumption Distribution (kWh/km)")
    plt.savefig(f"{OUTPUT_DIR}/03_energy_consumption_distribution.png")
    plt.close()
    
    # Plot 4: Altitude Profile (Sample Trips)
    plt.figure(figsize=(12, 5))
    if dacia_sample is not None:
        plt.plot(dacia_sample['distance_km'], dacia_sample['altitude_m'], label='Dacia')
    if nissan_sample is not None:
        plt.plot(nissan_sample['distance_km'], nissan_sample['altitude_m'], label='Nissan')
    plt.title("04 - Altitude vs Distance")
    plt.xlabel("Distance (km)")
    plt.ylabel("Altitude (m)")
    plt.legend()
    plt.savefig(f"{OUTPUT_DIR}/04_altitude_profile.png")
    plt.close()
    
    # Plot 5: Speed vs Energy (Trip Level)
    plt.figure(figsize=(8, 6))
    sns.scatterplot(data=trips_df, x='avg_speed', y='energy_kwh_per_km', hue='vehicle')
    plt.title("05 - Average Speed vs Energy Consumption")
    plt.savefig(f"{OUTPUT_DIR}/05_speed_vs_energy.png")
    plt.close()
    
    # Plot 6: Gradient vs Energy (Trip Level)
    plt.figure(figsize=(8, 6))
    sns.scatterplot(data=trips_df, x='avg_gradient', y='energy_kwh_per_km', hue='vehicle')
    plt.title("06 - Average Gradient vs Energy Consumption")
    plt.savefig(f"{OUTPUT_DIR}/06_gradient_vs_energy.png")
    plt.close()
    
    # Plot 7: Temperature vs Energy (Trip Level)
    plt.figure(figsize=(8, 6))
    sns.scatterplot(data=trips_df, x='avg_temp', y='energy_kwh_per_km', hue='vehicle')
    plt.title("07 - Temperature vs Energy Consumption")
    plt.savefig(f"{OUTPUT_DIR}/07_temperature_vs_energy.png")
    plt.close()
    
    # Plot 8: Regen Analysis (Histogram of regen power for Nissan)
    plt.figure(figsize=(10, 5))
    if nissan_sample is not None and not nissan_sample['regen_power_kw'].isna().all():
        regen_data = nissan_sample['regen_power_kw'].dropna()
        sns.histplot(regen_data, bins=30, color='green', kde=True)
        plt.title("08 - Regen Power Distribution (Nissan Sample)")
        plt.xlabel("Regen Power (kW) (Negative means generating)")
    else:
        plt.text(0.5, 0.5, "Regen data unavailable", ha='center')
    plt.savefig(f"{OUTPUT_DIR}/08_regen_analysis.png")
    plt.close()

    print("\nEDA Script Complete! Plots saved to reports/figures/eda/.")

if __name__ == "__main__":
    main()
