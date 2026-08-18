"""
DEVRT Dataset Parser - Memory Efficient

Processes DEVRT electric vehicle trip CSV files ONE AT A TIME.
Strict memory efficiency: load one file, process, save, delete, gc.collect().

All raw data stays untouched under dataset/.
Output goes to data/interim/devrt/<trip_name>_standardized.parquet
"""


def timestamp_to_epoch_seconds(series) -> np.ndarray:
    """Convert a tz-aware datetime64 series to float epoch seconds (UTC).

    The stored unit may be nanoseconds (datetime64[ns, UTC]) or microseconds
    (datetime64[us, UTC]) depending on how the parquet was written.  The naive
    ``astype('int64') / 1e9`` pattern silently treats microseconds as
    nanoseconds, producing times 1000x too small.  This helper normalizes to
    nanoseconds first.
    """
    naive = pd.Series(pd.to_datetime(series, utc=True)).dt.tz_localize(None)
    return naive.astype('datetime64[ns]').astype('int64').to_numpy(float) / 1e9

import os
import re
import sys
import gc
import json
import csv
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone


def get_memory_info():
    """Get process memory and system memory percent if psutil is available."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        process_mem_mb = process.memory_info().rss / (1024 * 1024)
        system_mem_pct = psutil.virtual_memory().percent
        return process_mem_mb, system_mem_pct
    except ImportError:
        return None, None


def discover_devrt_files(base_path="dataset/DEVRT/DEVRT"):
    """
    Discover all CSV trip files in DEVRT dataset.
    
    Yields one file at a time for memory efficiency.
    """
    vehicle_folders = ["DACIA SPRING", "NISSAN LEAF"]
    
    for vehicle in vehicle_folders:
        vehicle_path = os.path.join(base_path, vehicle)
        if not os.path.exists(vehicle_path):
            continue
        
        for fname in sorted(os.listdir(vehicle_path)):
            if fname.endswith('.csv') and not fname.startswith('.'):
                fpath = os.path.join(vehicle_path, fname)
                rel_trip_name = os.path.splitext(fname)[0]
                yield {
                    'path': fpath,
                    'filename': fname,
                    'trip_name': rel_trip_name,
                    'vehicle': vehicle,
                }


def inspect_single_csv_file(filepath):
    """
    Reads the header and determines the row count of a CSV file efficiently.
    Returns:
        header_cols (list of str): columns in the header
        row_count (int): number of data rows
        file_size_mb (float): size in MB
    """
    file_size_bytes = os.path.getsize(filepath)
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    row_count = 0
    header_cols = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        try:
            header_cols = next(reader)
        except StopIteration:
            return [], 0, file_size_mb
        
        # Count rows safely without loading
        for _ in reader:
            row_count += 1
            
    return header_cols, row_count, file_size_mb


def build_file_inventory(base_path="dataset/DEVRT/DEVRT", output_path="data/interim/devrt/file_inventory.csv"):
    """
    Builds the file inventory CSV file.
    Columns: file, rows, columns, size_mb
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    files = list(discover_devrt_files(base_path))
    
    inventory_data = []
    for f_info in files:
        fpath = f_info['path']
        header_cols, row_count, file_size_mb = inspect_single_csv_file(fpath)
        inventory_data.append({
            'file': f_info['filename'],
            'rows': row_count,
            'columns': len(header_cols),
            'size_mb': round(file_size_mb, 4)
        })
        
    df_inv = pd.DataFrame(inventory_data)
    df_inv.to_csv(output_path, index=False)
    print(f"Inventory saved to {output_path} with {len(df_inv)} entries.")
    return df_inv


_RELATIVE_TS_RE = re.compile(r'^\s*(\d{1,3}):(\d{2})(?::(\d{2}))?(?:\.(\d+))?\s*$')


def _relative_to_seconds(val: str):
    """Parse Dacia relative elapsed clock MM:SS.s / MM:SS / HH:MM:SS(.s) to seconds."""
    m = _RELATIVE_TS_RE.match(str(val).strip())
    if not m:
        return None
    frac = int((m.group(4) or '0')[:6].ljust(6, '0'))
    if m.group(3) is not None:
        hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        hh, mm, ss = 0, int(m.group(1)), int(m.group(2))
    if ss >= 60:
        return None
    return hh * 3600 + mm * 60 + ss + frac / 1e6


def _parse_absolute(val) -> pd.Timestamp:
    """Parse an absolute timestamp (ISO or dd/mm/yyyy hh:mm) to tz-aware UTC."""
    val_str = str(val).strip()
    try:
        return pd.to_datetime(val_str, utc=True, format='mixed')
    except Exception:
        pass
    try:
        return pd.to_datetime(val_str, utc=True, dayfirst=True)
    except Exception:
        return pd.NaT


def parse_timestamps(series, trip_date=None):
    """
    Parse a series of timestamps to timezone-aware UTC.

    Handles three encodings found in DEVRT:
      1. Absolute ISO datetimes (e.g. "2023-04-18 08:02:23.502").
      2. Absolute dd/mm/yyyy hh:mm datetimes (Nissan, some Dacia).
      3. Dacia relative elapsed clock "MM:SS.s" (minutes:seconds since trip
         start). This clock wraps every 60 minutes, so consecutive drops of
         more than 30 minutes indicate a wrap that must be unwrapped. The
         resulting monotonically increasing elapsed time is anchored to the
         trip date (from the filename) for ordering and delta features.

    A previously latent bug routed MM:SS.s values with minutes < 24 through
    pandas' absolute parser, silently attaching today's date (e.g. 2026-08-16).
    That reordered rows in downstream feature engineering and corrupted
    distance windows and targets. This implementation parses relative values
    explicitly BEFORE any absolute parser runs.
    """
    raw = [None if (pd.isna(v) or str(v).strip() == '') else str(v).strip() for v in series]

    # Phase 1: classify every value as relative-seconds or absolute string.
    rel_sec = np.array([_relative_to_seconds(v) if v is not None else np.nan
                        for v in raw], dtype=float)
    is_relative = np.isfinite(rel_sec)

    # Phase 2: unwrap the 60-minute relative clock (only meaningful when the
    # trip is relative-formatted, i.e. at least one relative value exists).
    if is_relative.any():
        # Unwrap in index order: whenever the raw clock drops by >30 min
        # relative to the previous valid raw value, add a full 60-minute lap.
        corr = np.full(len(series), np.nan)
        acc = 0.0
        prev_raw = None
        for i in range(len(series)):
            if not is_relative[i]:
                prev_raw = None
                continue
            if prev_raw is not None and rel_sec[i] < prev_raw - 1800:
                acc += 3600.0
            corr[i] = rel_sec[i] + acc
            prev_raw = rel_sec[i]

        # Absolute rows mixed into a relative trip (e.g. a lone
        # "18/04/2023 11:42" GPS reference) are interpolated from the
        # surrounding relative clock so ordering stays monotonic. Truly
        # invalid strings stay missing.
        non_relative = ~is_relative
        if non_relative.any():
            abs_ok = np.array([
                pd.notna(_parse_absolute(v)) if v is not None else False
                for v in raw], dtype=bool)
            abs_ok = abs_ok & non_relative
            if abs_ok.any():
                idx = np.arange(len(series))
                interp = np.interp(idx, idx[is_relative], corr[is_relative])
                corr = np.where(abs_ok, interp, corr)

        if trip_date is not None:
            base = pd.Timestamp(trip_date, tz='UTC').timestamp()
            wall = pd.Series(pd.to_datetime(base + corr, unit='s', utc=True, errors='coerce'))
            wall = wall.dt.tz_localize(None).astype('datetime64[ns]').dt.tz_localize('UTC')
            result = pd.Series(wall).reset_index(drop=True)
        else:
            # No trip date: express as elapsed seconds since the first row
            # (still monotonic, still suitable for dt/delta features).
            first = np.nanmin(corr)
            rel = pd.Series(pd.to_datetime(corr - first, unit='s', utc=True, errors='coerce'))
            rel = rel.dt.tz_localize(None).astype('datetime64[ns]').dt.tz_localize('UTC')
            result = pd.Series(rel).reset_index(drop=True)
        return result

    # Phase 3: pure absolute series. Normalize to ns so downstream units are stable.
    parsed = pd.Series(pd.to_datetime(series, utc=True, errors='coerce', format='mixed')).reset_index(drop=True)
    if parsed.notna().sum() == series.notna().sum():
        return pd.Series(parsed.dt.tz_localize(None).astype('datetime64[ns]').dt.tz_localize('UTC'),
                         index=parsed.index)
    fallback = pd.Series([_parse_absolute(v) if v is not None else pd.NaT
                          for v in raw], dtype='datetime64[ns, UTC]')
    out = parsed.where(parsed.notna(), fallback)
    return pd.Series(out.dt.tz_localize(None).astype('datetime64[ns]').dt.tz_localize('UTC'),
                     index=parsed.index)


def process_devrt_trip(file_info, output_dir="data/interim/devrt"):
    """
    Process a single DEVRT trip CSV file.
    Loads one file, creates standardized output, saves as Parquet (and CSV),
    then deletes the DataFrame before moving to the next file.
    """
    fpath = file_info['path']
    filename = file_info['filename']
    trip_name = file_info['trip_name']
    vehicle = file_info['vehicle']
    
    # Trip date from the filename prefix (e.g. 20230418_...) anchors Dacia's
    # relative MM:SS.s elapsed clock to a deterministic wall-clock time.
    trip_date = None
    try:
        date_str = os.path.basename(filename)[:8]
        if len(date_str) == 8 and date_str.isdigit():
            trip_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    except Exception:
        trip_date = None
    
    # =========================================================================
    # LOAD ONE CSV FILE ONLY
    # =========================================================================
    raw_df = pd.read_csv(fpath, skip_blank_lines=True)
    n_rows = len(raw_df)
    
    # =========================================================================
    # CREATE STANDARDIZED OUTPUT DataFrame
    # =========================================================================
    std_df = pd.DataFrame({
        'source_dataset': 'DEVRT',
        'source_file': filename,
        'source_row_id': np.arange(n_rows),
        'trip_id': trip_name,
        'vehicle_id': raw_df['car_id'].values if 'car_id' in raw_df.columns else np.full(n_rows, np.nan),
    })
    
    # Parse timestamp_data_utc as timezone-aware UTC
    std_df['timestamp'] = parse_timestamps(raw_df['timestamp_data_utc'], trip_date=trip_date)
    
    # Mappings and conversions
    std_df['soc_pct'] = pd.to_numeric(raw_df['soc'], errors='coerce')
    std_df['soh_pct'] = pd.to_numeric(raw_df['soh'], errors='coerce')
    std_df['speed_kmh'] = pd.to_numeric(raw_df['speed'], errors='coerce')
    std_df['ambient_temperature_c'] = pd.to_numeric(raw_df['amb_temp'], errors='coerce')
    
    # Motor power: W -> kW
    if 'Motor Pwr(w)' in raw_df.columns:
        std_df['motor_power_kw'] = pd.to_numeric(raw_df['Motor Pwr(w)'], errors='coerce') / 1000.0
    else:
        std_df['motor_power_kw'] = np.nan
        
    # Aux power: value * 100 W -> kW
    if 'Aux Pwr(100w)' in raw_df.columns:
        std_df['aux_power_kw'] = (pd.to_numeric(raw_df['Aux Pwr(100w)'], errors='coerce') * 100.0) / 1000.0
    else:
        std_df['aux_power_kw'] = np.nan
        
    std_df['motor_temperature_c'] = pd.to_numeric(raw_df['Motor Temp'], errors='coerce')
    std_df['motor_torque_nm'] = pd.to_numeric(raw_df['Torque Nm'], errors='coerce')
    std_df['motor_rpm'] = pd.to_numeric(raw_df['rpm'], errors='coerce')
    
    # Altitude: altitude or elv_spy
    if 'altitude' in raw_df.columns:
        std_df['altitude_m'] = pd.to_numeric(raw_df['altitude'], errors='coerce')
    elif 'elv_spy' in raw_df.columns:
        std_df['altitude_m'] = pd.to_numeric(raw_df['elv_spy'], errors='coerce')
    else:
        std_df['altitude_m'] = np.nan
        
    std_df['distance_km'] = pd.to_numeric(raw_df['cumul_dist'], errors='coerce')
    std_df['latitude'] = pd.to_numeric(raw_df['latitude'], errors='coerce')
    std_df['longitude'] = pd.to_numeric(raw_df['longitude'], errors='coerce')
    
    # Battery capacity Wh -> kWh
    if 'capacity' in raw_df.columns:
        std_df['battery_capacity_kwh'] = pd.to_numeric(raw_df['capacity'], errors='coerce') / 1000.0
    else:
        std_df['battery_capacity_kwh'] = np.nan
        
    # Regen power: regenwh represents power in Watts. W -> kW. Preserve sign!
    if 'regenwh' in raw_df.columns:
        std_df['regen_power_kw'] = pd.to_numeric(raw_df['regenwh'], errors='coerce') / 1000.0
    else:
        std_df['regen_power_kw'] = np.nan
        
    # Reference baseline consumption
    std_df['reference_consumption_wh_per_km'] = pd.to_numeric(raw_df['ref_consumption'], errors='coerce')
    
    # =========================================================================
    # QUALITY FLAGS (TASK 5)
    # =========================================================================
    std_df['quality_timestamp'] = std_df['timestamp'].notna().astype(int)
    std_df['quality_soc'] = ((std_df['soc_pct'] >= 0) & (std_df['soc_pct'] <= 100)).fillna(False).astype(int)
    std_df['quality_soh'] = ((std_df['soh_pct'] >= 0) & (std_df['soh_pct'] <= 100)).fillna(False).astype(int)
    std_df['quality_speed'] = std_df['speed_kmh'].notna().astype(int)
    std_df['quality_reverse_speed'] = (std_df['speed_kmh'] < 0).fillna(False).astype(int)
    std_df['quality_gps'] = ((std_df['latitude'] >= -90) & (std_df['latitude'] <= 90) &
                             (std_df['longitude'] >= -180) & (std_df['longitude'] <= 180)).fillna(False).astype(int)
    std_df['quality_altitude'] = std_df['altitude_m'].notna().astype(int)
    std_df['quality_distance'] = ((std_df['distance_km'] >= 0)).fillna(False).astype(int)
    
    # Save output
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'{trip_name}_standardized.parquet')
    std_df.to_parquet(output_path, index=False)
    
    # Also save CSV for easy validation/test access
    csv_path = os.path.join(output_dir, f'{trip_name}_standardized.csv')
    std_df.to_csv(csv_path, index=False)
    
    # Record statistics for the cleaning report BEFORE deletion
    quality_summary = {
        'quality_timestamp': int(std_df['quality_timestamp'].sum()),
        'quality_soc': int(std_df['quality_soc'].sum()),
        'quality_soh': int(std_df['quality_soh'].sum()),
        'quality_speed': int(std_df['quality_speed'].sum()),
        'quality_reverse_speed': int(std_df['quality_reverse_speed'].sum()),
        'quality_gps': int(std_df['quality_gps'].sum()),
        'quality_altitude': int(std_df['quality_altitude'].sum()),
        'quality_distance': int(std_df['quality_distance'].sum()),
    }
    
    missing_summary = {col: int(std_df[col].isna().sum()) for col in std_df.columns}
    
    invalid_summary = {
        'soc': int(((std_df['soc_pct'] < 0) | (std_df['soc_pct'] > 100)).sum()),
        'soh': int(((std_df['soh_pct'] < 0) | (std_df['soh_pct'] > 100)).sum()),
        'latitude': int(((std_df['latitude'] < -90) | (std_df['latitude'] > 90)).sum()),
        'longitude': int(((std_df['longitude'] < -180) | (std_df['longitude'] > 180)).sum()),
        'distance': int((std_df['distance_km'] < 0).sum()),
        'timestamp': int(std_df['timestamp'].isna().sum() - raw_df['timestamp_data_utc'].isna().sum()),
    }
    
    # =========================================================================
    # CLEANUP: DELETE DATAFRAME, GC
    # =========================================================================
    del raw_df
    del std_df
    gc.collect()
    
    result = {
        'file': filename,
        'trip_name': trip_name,
        'vehicle': vehicle,
        'rows_processed': n_rows,
        'output_path': output_path,
        'quality_summary': quality_summary,
        'missing_summary': missing_summary,
        'invalid_summary': invalid_summary,
        'success': True,
    }
    
    return result


def process_all_devrt_memory_efficient(base_path="dataset/DEVRT/DEVRT", output_dir="data/interim/devrt"):
    """
    Process all DEVRT trip files one at a time with memory efficiency.
    """
    # Task 1: Build the inventory
    build_file_inventory(base_path, os.path.join(output_dir, "file_inventory.csv"))
    
    files = list(discover_devrt_files(base_path))
    print(f'Found {len(files)} DEVRT trip files')
    print('=' * 60)
    
    results = []
    successful = 0
    failed = 0
    total_rows = 0
    
    max_ram_observed = 0.0
    ram_sum = 0.0
    ram_count = 0
    
    for i, file_info in enumerate(files):
        # Memory monitoring before loading
        mem_before, sys_pct = get_memory_info()
        if mem_before is not None:
            max_ram_observed = max(max_ram_observed, mem_before)
            ram_sum += mem_before
            ram_count += 1
            print(f"[{i+1}/{len(files)}] Before {file_info['filename']}: RAM = {mem_before:.2f} MB (System = {sys_pct:.1f}%)")
            # Safety stop
            if mem_before > 4096.0 or sys_pct > 85.0:
                print("WARNING: Memory usage is dangerously high! Stopping processing gracefully.")
                break
        else:
            print(f"[{i+1}/{len(files)}] Processing {file_info['filename']}")
            
        try:
            result = process_devrt_trip(file_info, output_dir)
            results.append(result)
            successful += 1
            total_rows += result['rows_processed']
        except Exception as e:
            print(f'  ERROR processing {file_info["filename"]}: {e}')
            failed += 1
            results.append({
                'file': file_info['filename'],
                'trip_name': file_info['trip_name'],
                'vehicle': file_info['vehicle'],
                'rows_processed': 0,
                'output_path': None,
                'success': False,
                'error': str(e)
            })
            
        # Memory monitoring after saving and garbage collection
        mem_after, sys_pct_after = get_memory_info()
        if mem_after is not None:
            max_ram_observed = max(max_ram_observed, mem_after)
            ram_sum += mem_after
            ram_count += 1
            print(f"  After cleanup: RAM = {mem_after:.2f} MB")
            
    # Final summary
    print('=' * 60)
    print(f'DEVRT PROCESSING COMPLETE:')
    print(f'  Successful: {successful}/{len(files)} files')
    print(f'  Failed: {failed}/{len(files)} files')
    print(f'  Total rows processed: {total_rows}')
    
    avg_ram = (ram_sum / ram_count) if ram_count > 0 else 0.0
    
    summary = {
        'total_files': len(files),
        'successful': successful,
        'failed': failed,
        'total_rows': total_rows,
        'max_ram_observed_mb': max_ram_observed,
        'avg_ram_observed_mb': avg_ram,
        'results': results,
    }
    
    return summary


def generate_cleaning_report(results, output_path="docs/devrt_cleaning_report.md"):
    """
    Generates a Markdown cleaning report for the DEVRT dataset.
    """
    successful = results['successful']
    failed = results['failed']
    total_rows = results['total_rows']
    total_files = results['total_files']
    max_ram = results.get('max_ram_observed_mb', 0.0)
    avg_ram = results.get('avg_ram_observed_mb', 0.0)
    
    col_missing = {}
    col_quality = {}
    col_invalid = {
        'soc': 0, 'soh': 0, 'latitude': 0, 'longitude': 0, 'distance': 0, 'timestamp': 0
    }
    
    file_rows = []
    
    for r in results['results']:
        if r['success']:
            file_rows.append(f"| {r['file']} | {r['rows_processed']:,} | Success |")
            for col, count in r['missing_summary'].items():
                col_missing[col] = col_missing.get(col, 0) + count
            for flag, count in r['quality_summary'].items():
                col_quality[flag] = col_quality.get(flag, 0) + count
            for key, count in r['invalid_summary'].items():
                col_invalid[key] = col_invalid.get(key, 0) + count
        else:
            file_rows.append(f"| {r['file']} | 0 | Failed ({r.get('error', 'Unknown error')}) |")
            
    report_content = f"""# DEVRT Dataset Data Quality & Cleaning Report

## Overview
- **Total Files Discovered**: {total_files}
- **Successfully Processed**: {successful}
- **Failed**: {failed}
- **Total Rows Processed**: {total_rows:,}

## Memory Observations
- **Maximum RAM Usage Observed**: {max_ram:.2f} MB
- **Average RAM Usage**: {avg_ram:.2f} MB
- **Observation**: Memory remained stable throughout the execution due to the strict one-file-at-a-time loop and explicit garbage collection.

## Quality Flags Summary
| Quality Flag | Valid Rows | Invalid/Missing Rows | Pass Rate |
|--------------|------------|-----------------------|-----------|
"""
    for flag, valid_count in sorted(col_quality.items()):
        invalid_count = total_rows - valid_count
        pass_rate = (valid_count / total_rows * 100) if total_rows > 0 else 0.0
        report_content += f"| `{flag}` | {valid_count:,} | {invalid_count:,} | {pass_rate:.2f}% |\n"
        
    report_content += """
## Missing Values Report
| Standardized Column | Missing Values Count | Percentage |
|---------------------|----------------------|------------|
"""
    for col, missing_count in sorted(col_missing.items()):
        pct = (missing_count / total_rows * 100) if total_rows > 0 else 0.0
        report_content += f"| `{col}` | {missing_count:,} | {pct:.2f}% |\n"
        
    report_content += f"""
## Invalid Values Analysis
Values outside standard physical ranges, excluding missing (NaN) values:
- **SOC out of bounds [0, 100]**: {col_invalid['soc']:,} rows
- **SOH out of bounds [0, 100]**: {col_invalid['soh']:,} rows
- **Latitude out of bounds [-90, 90]**: {col_invalid['latitude']:,} rows
- **Longitude out of bounds [-180, 180]**: {col_invalid['longitude']:,} rows
- **Negative Distance (< 0)**: {col_invalid['distance']:,} rows
- **Timestamp parsing failures**: {col_invalid['timestamp']:,} rows

## Unit Conversions Applied
The following conversions were applied to standard concepts:
1. **Motor Power**: Converted from Watts to kW (`Motor Pwr(w)` / 1000.0).
2. **Auxiliary Power**: Converted from units of 100W to kW (`Aux Pwr(100w)` * 100 / 1000.0).
3. **Battery Capacity**: Converted from Wh to kWh (`capacity` / 1000.0).
4. **Regenerative Power**: Converted from Watts to kW (`regenwh` / 1000.0). Sign was preserved (negative for regenerative braking).

## File-by-File Breakdown
| File Name | Rows Processed | Status |
|-----------|----------------|--------|
"""
    for row in file_rows:
        report_content += row + "\n"
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"Cleaning report saved to {output_path}")


if __name__ == '__main__':
    # Process all DEVRT files memory-efficiently
    results = process_all_devrt_memory_efficient()
    
    # Save processing summary
    summary_path = 'data/interim/devrt/processing_summary.json'
    with open(summary_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f'\nSummary saved to: {summary_path}')
    
    # Generate cleaning report
    generate_cleaning_report(results)
