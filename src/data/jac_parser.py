"""
JAC IEV40 Dataset Parser — Memory Efficient

Parses the JAC IEV40 telemetry CSV dataset from dataset/archive/dataset.csv.
Original raw files are NEVER modified. Output goes to data/interim/jac/.

CRITICAL RULES:
- AIR: NOT ambient temperature — sensor/status flag (values 0 and 2 only)
- VOL: NOT assumed to be battery voltage (range 0-379, likely raw ADC)
- CUR: Keep as current_raw — NOT assumed HV battery current
- BRK: Keep as brake_raw (range 0-28, NOT percentage)
- ACC: Keep as accelerator_raw (range 0-90, NOT percentage)
- SPD: Verified km/h → speed_kmh
- ODO: Verified km → odometer_km
- ECO: Binary indicator (0=off, 192=on) → eco_mode
- Timestamps: Reconstructed from Y/M/D/H/MIN/SEC with second-level resolution
- DO NOT create: battery_voltage_v, battery_current_a, ambient_temperature_c,
                 battery_power_kw, energy_consumption_kwh_per_km, regen_energy_kwh
"""

import os
import gc
import json
import csv
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime


def discover_jac_file(base_path="dataset/archive"):
    """Discover the JAC IEV40 CSV file."""
    csv_path = os.path.join(base_path, "dataset.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"JAC dataset.csv not found at {csv_path}")
    file_size = os.path.getsize(csv_path)
    # Count rows without loading
    row_count = 0
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for _ in reader:
            row_count += 1
    return {
        'path': csv_path,
        'filename': 'dataset.csv',
        'file_size_bytes': file_size,
        'file_size_mb': round(file_size / (1024 * 1024), 4),
        'rows': row_count,
        'columns': len(header),
        'column_names': header,
    }


def reconstruct_timestamps(df):
    """
    Reconstruct timestamps from Y/M/D/H/MIN/SEC columns.
    
    Year values observed: 0 (invalid) and 23 (=2023).
    When Y < 100 and Y > 0, we add 2000 to get a full year.
    When Y=0 AND M=0 AND D=0, the timestamp is treated as invalid (NaT).
    
    Returns a Series of timezone-naive datetime values (or NaT).
    """
    y = df['Y'].values
    m = df['M'].values
    d = df['D'].values
    h = df['H'].values
    mn = df['MIN'].values
    s = df['SEC'].values
    
    timestamps = []
    for i in range(len(df)):
        yi, mi, di, hi, mni, si = int(y[i]), int(m[i]), int(d[i]), int(h[i]), int(mn[i]), int(s[i])
        
        # Invalid: all-zero date fields
        if yi == 0 and mi == 0 and di == 0:
            timestamps.append(pd.NaT)
            continue
        
        # Apply 2-digit year offset
        if 0 < yi < 100:
            yi += 2000
        elif yi == 0:
            timestamps.append(pd.NaT)
            continue
        
        # Validate ranges
        if not (1 <= mi <= 12 and 1 <= di <= 31 and 0 <= hi <= 23 and 0 <= mni <= 59 and 0 <= si <= 59):
            timestamps.append(pd.NaT)
            continue
        
        try:
            timestamps.append(pd.Timestamp(yi, mi, di, hi, mni, si))
        except (ValueError, OverflowError):
            timestamps.append(pd.NaT)
    
    return pd.Series(timestamps, dtype='datetime64[ns]')


def process_jac(base_path="dataset/archive", output_dir="data/interim/jac"):
    """
    Process the JAC IEV40 dataset.
    
    Returns a dict with processing results and statistics.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # =========================================================================
    # TASK 1: Identify the file
    # =========================================================================
    file_info = discover_jac_file(base_path)
    print(f"JAC source file: {file_info['filename']}")
    print(f"  Size: {file_info['file_size_mb']} MB")
    print(f"  Rows: {file_info['rows']}")
    print(f"  Columns: {file_info['columns']}")
    print(f"  Column names: {file_info['column_names']}")
    
    # =========================================================================
    # TASK 2: Load the data
    # =========================================================================
    raw_df = pd.read_csv(file_info['path'])
    n_rows = len(raw_df)
    print(f"\nLoaded {n_rows} rows x {len(raw_df.columns)} columns")
    
    # =========================================================================
    # TASK 3: Reconstruct timestamp
    # =========================================================================
    print("\nReconstructing timestamps from Y/M/D/H/MIN/SEC...")
    timestamps = reconstruct_timestamps(raw_df)
    
    valid_ts_mask = timestamps.notna()
    n_valid_ts = valid_ts_mask.sum()
    n_invalid_ts = n_rows - n_valid_ts
    
    ts_stats = {}
    if n_valid_ts > 0:
        valid_ts = timestamps[valid_ts_mask]
        ts_stats['earliest'] = str(valid_ts.min())
        ts_stats['latest'] = str(valid_ts.max())
        ts_stats['n_duplicates'] = int(valid_ts.duplicated().sum())
        ts_stats['is_sorted'] = bool(valid_ts.is_monotonic_increasing)
        
        # Sampling interval distribution (on sorted valid timestamps)
        sorted_ts = valid_ts.sort_values()
        diffs = sorted_ts.diff().dropna()
        if len(diffs) > 0:
            ts_stats['interval_min_s'] = diffs.dt.total_seconds().min()
            ts_stats['interval_max_s'] = diffs.dt.total_seconds().max()
            ts_stats['interval_median_s'] = diffs.dt.total_seconds().median()
            ts_stats['interval_mean_s'] = diffs.dt.total_seconds().mean()
        
        # Gaps > 60 seconds
        if len(diffs) > 0:
            gaps_gt_60 = (diffs.dt.total_seconds() > 60).sum()
            ts_stats['gaps_gt_60s'] = int(gaps_gt_60)
    
    print(f"  Valid timestamps: {n_valid_ts}/{n_rows} ({100*n_valid_ts/n_rows:.1f}%)")
    print(f"  Invalid timestamps: {n_invalid_ts}")
    if ts_stats:
        print(f"  Earliest: {ts_stats.get('earliest')}")
        print(f"  Latest:   {ts_stats.get('latest')}")
        print(f"  Duplicates: {ts_stats.get('n_duplicates')}")
        print(f"  Is sorted: {ts_stats.get('is_sorted')}")
        if 'interval_median_s' in ts_stats:
            print(f"  Sampling interval median: {ts_stats['interval_median_s']:.1f}s")
    
    # =========================================================================
    # TASK 4+15: Create standardized DataFrame with data lineage
    # =========================================================================
    std_df = pd.DataFrame(index=range(n_rows))
    std_df['source_dataset'] = 'JAC_IEV40'
    std_df['source_file'] = file_info['filename']
    std_df['source_row_id'] = np.arange(n_rows)
    std_df['vehicle_id'] = 'JAC_IEV40'  # Single vehicle dataset
    std_df['timestamp'] = timestamps
    
    # TASK 6: Speed
    std_df['speed_kmh'] = pd.to_numeric(raw_df['SPD'], errors='coerce')
    
    # TASK 7: Odometer
    std_df['odometer_km'] = pd.to_numeric(raw_df['ODO'], errors='coerce')
    
    # TASK 8: GPS
    std_df['latitude'] = pd.to_numeric(raw_df['LAT'], errors='coerce')
    std_df['longitude'] = pd.to_numeric(raw_df['LON'], errors='coerce')
    
    # TASK 9: Altitude — docs say ALT is in meters; reference frame uncertain
    std_df['altitude_m'] = pd.to_numeric(raw_df['ALT'], errors='coerce')
    
    # TASK 12: Driver control variables (raw, no conversions)
    std_df['brake_raw'] = pd.to_numeric(raw_df['BRK'], errors='coerce')
    std_df['accelerator_raw'] = pd.to_numeric(raw_df['ACC'], errors='coerce')
    std_df['eco_mode'] = pd.to_numeric(raw_df['ECO'], errors='coerce')
    
    # TASK 5: Keep unverified sensor variables as raw (NOT creating standard names)
    std_df['vol_raw'] = pd.to_numeric(raw_df['VOL'], errors='coerce')
    std_df['current_raw'] = pd.to_numeric(raw_df['CUR'], errors='coerce')
    std_df['air_sensor_flag'] = pd.to_numeric(raw_df['AIR'], errors='coerce')
    
    # =========================================================================
    # TASK 10: Quality flags
    # =========================================================================
    std_df['quality_timestamp'] = valid_ts_mask.astype(int).values
    std_df['quality_speed'] = std_df['speed_kmh'].notna().astype(int)
    std_df['quality_reverse_speed'] = (std_df['speed_kmh'] < 0).fillna(False).astype(int)
    std_df['quality_gps'] = (
        (std_df['latitude'] >= -90) & (std_df['latitude'] <= 90) &
        (std_df['longitude'] >= -180) & (std_df['longitude'] <= 180)
    ).fillna(False).astype(int)
    std_df['quality_odometer'] = std_df['odometer_km'].notna().astype(int)
    std_df['quality_altitude'] = std_df['altitude_m'].notna().astype(int)
    
    # =========================================================================
    # TASK 11: Missing values analysis (report only, no filling)
    # =========================================================================
    missing_counts = {col: int(std_df[col].isna().sum()) for col in std_df.columns}
    
    # =========================================================================
    # Compute statistics for the report
    # =========================================================================
    speed_stats = {}
    spd = std_df['speed_kmh'].dropna()
    if len(spd) > 0:
        speed_stats['min'] = float(spd.min())
        speed_stats['max'] = float(spd.max())
        speed_stats['mean'] = float(spd.mean())
        speed_stats['n_negative'] = int((spd < 0).sum())
        speed_stats['n_zero'] = int((spd == 0).sum())
    
    odo_stats = {}
    odo = std_df['odometer_km'].dropna()
    if len(odo) > 0:
        odo_stats['min'] = float(odo.min())
        odo_stats['max'] = float(odo.max())
        odo_stats['total_range'] = float(odo.max() - odo.min())
    
    gps_stats = {
        'valid': int(std_df['quality_gps'].sum()),
        'invalid': int((std_df['quality_gps'] == 0).sum()),
        'lat_min': float(std_df['latitude'].min()) if std_df['latitude'].notna().any() else None,
        'lat_max': float(std_df['latitude'].max()) if std_df['latitude'].notna().any() else None,
        'lon_min': float(std_df['longitude'].min()) if std_df['longitude'].notna().any() else None,
        'lon_max': float(std_df['longitude'].max()) if std_df['longitude'].notna().any() else None,
    }
    
    alt_stats = {}
    alt = std_df['altitude_m'].dropna()
    if len(alt) > 0:
        alt_stats['min'] = float(alt.min())
        alt_stats['max'] = float(alt.max())
        alt_stats['mean'] = float(alt.mean())
        alt_stats['n_zero'] = int((alt == 0).sum())
    
    brk_stats = {}
    brk = std_df['brake_raw'].dropna()
    if len(brk) > 0:
        brk_stats['min'] = float(brk.min())
        brk_stats['max'] = float(brk.max())
        brk_stats['n_unique'] = int(brk.nunique())
    
    acc_stats = {}
    acc = std_df['accelerator_raw'].dropna()
    if len(acc) > 0:
        acc_stats['min'] = float(acc.min())
        acc_stats['max'] = float(acc.max())
        acc_stats['n_unique'] = int(acc.nunique())
    
    eco_stats = {}
    eco = std_df['eco_mode'].dropna()
    if len(eco) > 0:
        eco_stats['values'] = sorted([int(v) for v in eco.unique()])
        eco_stats['n_off'] = int((eco == 0).sum())
        eco_stats['n_on'] = int((eco == 192).sum())
    
    air_stats = {}
    air = std_df['air_sensor_flag'].dropna()
    if len(air) > 0:
        air_stats['values'] = sorted([int(v) for v in air.unique()])
        air_stats['n_zero'] = int((air == 0).sum())
        air_stats['n_two'] = int((air == 2).sum())
    
    vol_stats = {}
    vol = std_df['vol_raw'].dropna()
    if len(vol) > 0:
        vol_stats['min'] = float(vol.min())
        vol_stats['max'] = float(vol.max())
        vol_stats['mean'] = float(vol.mean())
    
    cur_stats = {}
    cur = std_df['current_raw'].dropna()
    if len(cur) > 0:
        cur_stats['min'] = float(cur.min())
        cur_stats['max'] = float(cur.max())
        cur_stats['mean'] = float(cur.mean())
    
    # =========================================================================
    # TASK 14: Save outputs
    # =========================================================================
    # Main standardized parquet
    parquet_path = os.path.join(output_dir, 'jac_standardized.parquet')
    std_df.to_parquet(parquet_path, index=False)
    print(f"\nSaved: {parquet_path} ({len(std_df)} rows)")
    
    # Also CSV for inspection
    csv_out_path = os.path.join(output_dir, 'jac_standardized.csv')
    std_df.to_csv(csv_out_path, index=False)
    print(f"Saved: {csv_out_path}")
    
    # Quality flags parquet (same data, but explicitly named)
    qf_cols = [c for c in std_df.columns if c.startswith('quality_')]
    qf_df = std_df[['source_row_id'] + qf_cols].copy()
    qf_path = os.path.join(output_dir, 'jac_quality_flags.parquet')
    qf_df.to_parquet(qf_path, index=False)
    del qf_df
    print(f"Saved: {qf_path}")
    
    # Processing summary JSON
    summary = {
        'source_file': file_info['filename'],
        'file_size_mb': file_info['file_size_mb'],
        'raw_rows': n_rows,
        'processed_rows': len(std_df),
        'rows_removed': 0,  # We do NOT remove rows
        'timestamp_stats': ts_stats,
        'n_valid_timestamps': int(n_valid_ts),
        'n_invalid_timestamps': int(n_invalid_ts),
        'speed_stats': speed_stats,
        'odometer_stats': odo_stats,
        'gps_stats': gps_stats,
        'altitude_stats': alt_stats,
        'brake_stats': brk_stats,
        'accelerator_stats': acc_stats,
        'eco_stats': eco_stats,
        'air_stats': air_stats,
        'vol_stats': vol_stats,
        'cur_stats': cur_stats,
        'missing_counts': missing_counts,
        'standardized_columns': list(std_df.columns),
        'quality_flag_columns': qf_cols,
    }
    
    summary_path = os.path.join(output_dir, 'processing_summary.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Saved: {summary_path}")
    
    # Clean up
    del raw_df
    del std_df
    gc.collect()
    
    return summary


def generate_jac_cleaning_report(summary, output_path="docs/jac_cleaning_report.md"):
    """Generate the JAC data quality & cleaning report as a Markdown file."""
    
    ts = summary.get('timestamp_stats', {})
    spd = summary.get('speed_stats', {})
    odo = summary.get('odometer_stats', {})
    gps = summary.get('gps_stats', {})
    alt = summary.get('altitude_stats', {})
    brk = summary.get('brake_stats', {})
    acc = summary.get('accelerator_stats', {})
    eco = summary.get('eco_stats', {})
    air = summary.get('air_stats', {})
    vol = summary.get('vol_stats', {})
    cur = summary.get('cur_stats', {})
    missing = summary.get('missing_counts', {})
    
    report = f"""# JAC IEV40 Data Quality & Cleaning Report

## 1. Source File
- **File**: `{summary['source_file']}`
- **Location**: `dataset/archive/`
- **Size**: {summary['file_size_mb']} MB

## 2. Row Counts
- **Raw row count**: {summary['raw_rows']:,}
- **Processed row count**: {summary['processed_rows']:,}
- **Rows removed**: {summary['rows_removed']} (no rows removed — all preserved with quality flags)

## 3. Flagged Rows Summary
| Quality Flag | Valid | Invalid/Flagged |
|-------------|-------|-----------------|
| `quality_timestamp` | {summary['n_valid_timestamps']:,} | {summary['n_invalid_timestamps']:,} |
| `quality_speed` | {summary['processed_rows'] - missing.get('speed_kmh', 0):,} | {missing.get('speed_kmh', 0):,} |
| `quality_gps` | {gps.get('valid', 0):,} | {gps.get('invalid', 0):,} |
| `quality_odometer` | {summary['processed_rows'] - missing.get('odometer_km', 0):,} | {missing.get('odometer_km', 0):,} |
| `quality_altitude` | {summary['processed_rows'] - missing.get('altitude_m', 0):,} | {missing.get('altitude_m', 0):,} |
| `quality_reverse_speed` | {spd.get('n_negative', 0)} rows with negative speed | — |

## 4. Missing Values
| Column | Missing Count | Percentage |
|--------|---------------|------------|
"""
    for col, count in sorted(missing.items()):
        pct = (count / summary['processed_rows'] * 100) if summary['processed_rows'] > 0 else 0
        report += f"| `{col}` | {count:,} | {pct:.2f}% |\n"

    report += f"""
## 5. Timestamp Analysis
- **Reconstruction**: Built from Y/M/D/H/MIN/SEC columns
- **Valid timestamps**: {summary['n_valid_timestamps']:,} / {summary['processed_rows']:,} ({100 * summary['n_valid_timestamps'] / summary['processed_rows']:.1f}%)
- **Invalid timestamps**: {summary['n_invalid_timestamps']:,} (Y=0, M=0, D=0 or out-of-range values)
- **Earliest**: {ts.get('earliest', 'N/A')}
- **Latest**: {ts.get('latest', 'N/A')}
- **Duplicate timestamps**: {ts.get('n_duplicates', 'N/A')}
- **Chronologically sorted**: {ts.get('is_sorted', 'N/A')}
- **Sampling interval (median)**: {ts.get('interval_median_s', 'N/A')}s
- **Sampling interval (min)**: {ts.get('interval_min_s', 'N/A')}s
- **Sampling interval (max)**: {ts.get('interval_max_s', 'N/A')}s
- **Gaps > 60s**: {ts.get('gaps_gt_60s', 'N/A')}

> **Note**: The data is NOT pre-sorted by timestamp. Many rows have invalid (all-zero) date fields and are interspersed throughout the file. The actual sampling rate appears to be approximately every 1–2 seconds when timestamps are valid.

## 6. GPS Validation
- **Valid GPS coordinates**: {gps.get('valid', 0):,}
- **Invalid GPS coordinates**: {gps.get('invalid', 0):,}
- **Latitude range**: [{gps.get('lat_min', 'N/A')}, {gps.get('lat_max', 'N/A')}]
- **Longitude range**: [{gps.get('lon_min', 'N/A')}, {gps.get('lon_max', 'N/A')}]

> **Warning**: Longitude values up to {gps.get('lon_max', 'N/A')} were observed, which exceeds the valid [-180, 180] range. This may indicate coordinate wrapping (modulo 360) or data corruption. These rows are flagged via `quality_gps = 0`.

## 7. Speed Analysis
- **Range**: [{spd.get('min', 'N/A')}, {spd.get('max', 'N/A')}] km/h
- **Mean**: {spd.get('mean', 'N/A'):.2f} km/h
- **Negative speed values**: {spd.get('n_negative', 0)}
- **Zero speed (stopped)**: {spd.get('n_zero', 0):,}
- **Unit**: Verified as km/h (direct measurement, no scaling needed)

## 8. Odometer Analysis
- **Range**: [{odo.get('min', 'N/A')}, {odo.get('max', 'N/A')}] km
- **Total distance covered**: {odo.get('total_range', 'N/A'):.1f} km
- **Unit**: Verified as km (cumulative odometer reading)
- **Note**: ODO is the cumulative vehicle odometer, NOT trip-level distance.

## 9. Altitude Analysis
- **Range**: [{alt.get('min', 'N/A')}, {alt.get('max', 'N/A')}] m
- **Mean**: {alt.get('mean', 'N/A'):.1f} m
- **Zero values**: {alt.get('n_zero', 0):,}
- **Unit**: Listed as meters (m) in column name; reference frame (ASL vs relative) uncertain.

## 10. BRK (Brake) Analysis
- **Range**: [{brk.get('min', 'N/A')}, {brk.get('max', 'N/A')}]
- **Unique values**: {brk.get('n_unique', 'N/A')}
- **Interpretation**: Raw sensor signal. NOT a 0–100% pedal position. Do not normalize.

## 11. ACC (Accelerator) Analysis
- **Range**: [{acc.get('min', 'N/A')}, {acc.get('max', 'N/A')}]
- **Unique values**: {acc.get('n_unique', 'N/A')}
- **Interpretation**: Raw sensor signal. NOT a 0–100% throttle position. Do not normalize.

## 12. ECO Mode Analysis
- **Unique values**: {eco.get('values', 'N/A')}
- **ECO off (0)**: {eco.get('n_off', 'N/A'):,}
- **ECO on (192)**: {eco.get('n_on', 'N/A'):,}
- **Interpretation**: Binary flag. 0 = ECO off, 192 = ECO on.

## 13. AIR Handling
- **Unique values**: {air.get('values', 'N/A')}
- **Count of 0**: {air.get('n_zero', 'N/A'):,}
- **Count of 2**: {air.get('n_two', 'N/A'):,}
- **Interpretation**: Sensor/status flag. NOT ambient temperature. Stored as `air_sensor_flag`.
- **`ambient_temperature_c` NOT created** — AIR is not a temperature measurement.

## 14. VOL Handling
- **Range**: [{vol.get('min', 'N/A')}, {vol.get('max', 'N/A')}]
- **Mean**: {vol.get('mean', 'N/A'):.2f}
- **Interpretation**: Likely raw ADC values. NOT verified as battery voltage.
- **`battery_voltage_v` NOT created** — semantics unverified.
- **Stored as**: `vol_raw`

## 15. CUR Handling
- **Range**: [{cur.get('min', 'N/A')}, {cur.get('max', 'N/A')}]
- **Mean**: {cur.get('mean', 'N/A'):.2f}
- **Interpretation**: Raw current values. NOT assumed to be HV battery current.
- **`battery_current_a` NOT created** — semantics unverified.
- **Stored as**: `current_raw`
- **No power calculation (VOL × CUR) performed.**

## 16. Limitations
1. **No SOC/SOH data**: The JAC dataset does not contain State of Charge or State of Health fields.
2. **No energy target**: Cannot derive `energy_consumption_kwh_per_km` or similar ML targets from this dataset alone.
3. **Unverified sensor variables**: VOL, CUR, BRK, ACC have uncertain semantics and should not be used for physical calculations without documentation confirmation.
4. **Longitude anomalies**: Some longitude values exceed 180°, requiring investigation (possible modulo-360 wrapping or data corruption).
5. **Altitude reference frame**: Whether ALT is above sea level or relative is unknown.
6. **Shuffled data**: The raw file is not sorted chronologically.
7. **Invalid timestamps**: {summary['n_invalid_timestamps']:,} rows have Y=0/M=0/D=0 or otherwise un-parseable timestamps.

## 17. Standardized Columns Created
"""
    for col in summary.get('standardized_columns', []):
        report += f"- `{col}`\n"
    
    report += f"""
## 18. Files Created
- `data/interim/jac/jac_standardized.parquet`
- `data/interim/jac/jac_standardized.csv`
- `data/interim/jac/jac_quality_flags.parquet`
- `data/interim/jac/processing_summary.json`
- `docs/jac_cleaning_report.md` (this file)
"""
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Cleaning report saved to {output_path}")


if __name__ == '__main__':
    summary = process_jac()
    generate_jac_cleaning_report(summary)
    
    print("\n=== JAC IEV40 PROCESSING COMPLETE ===")
    print(f"  Source: {summary['source_file']}")
    print(f"  Raw rows: {summary['raw_rows']:,}")
    print(f"  Processed rows: {summary['processed_rows']:,}")
    print(f"  Rows removed: {summary['rows_removed']}")
    print(f"  Valid timestamps: {summary['n_valid_timestamps']:,}")
    print(f"  Standardized columns: {len(summary['standardized_columns'])}")