"""
TUM EV UDS Dataset Memory-Safe Signal Extractor

Extracts specific signals from the raw 98M-row TUM dataset using PyArrow.
Processes files strictly by row group to prevent RAM exhaustion.
"""

import os
import gc
import json
import time
import psutil
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

# =========================================================================
# CONFIGURATION & SEMANTIC GUARDRAILS
# =========================================================================

RAW_DATA_DIR = r"dataset/electric-vehicle-uds-dataset-main/data/uds_data"
OUTPUT_DIR = r"data/interim/tum"

# Verified value_ids to extract
# DO NOT ADD 1205 AS BATTERY CURRENT. It is ptc1_current.
# DO NOT ADD 56 AS TRACTION POWER. It is hv_aux_power.
REQUIRED_IDS = {
    4: "vehicle_speed",
    15: "ambient_air_temp",
    56: "hv_aux_power",
    900: "hv_soc",
    1200: "hv_battery_voltage",
    1205: "ptc1_current",
    1288: "cell_c_rate",
    1299: "traveled_distance"
}

def get_memory_usage_mb():
    """Return current process memory usage in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def process_file(parquet_path, output_path):
    """
    Process a single Parquet file row-group by row-group.
    Filters to REQUIRED_IDS and writes to output_path.
    """
    filename = os.path.basename(parquet_path)
    print(f"\n[{filename}] Starting extraction...")
    
    pf = pq.ParquetFile(parquet_path)
    n_row_groups = pf.num_row_groups
    total_source_rows = pf.metadata.num_rows
    
    print(f"[{filename}] Row groups: {n_row_groups}, Total rows: {total_source_rows:,}")
    
    # Read the exact data type of the time column from the source
    orig_schema = pf.schema_arrow
    time_type = orig_schema.field('time').type
    
    output_schema = pa.schema([
        ('vehicle_id', pa.string()),
        ('time', time_type),
        ('value_id', pa.int32()),
        ('value', pa.float64()),
        ('signal_name', pa.string())
    ])
    
    writer = None
    extracted_rows = 0
    max_ram = 0.0
    
    for rg_idx in range(n_row_groups):
        ram_before = get_memory_usage_mb()
        
        # Read only the needed columns for this row group
        table = pf.read_row_group(rg_idx, columns=['vehicle_id', 'time', 'value_id', 'value'])
        source_rg_rows = table.num_rows
        
        # Filter for required value_ids
        filtered_table = table.filter(
            pa.compute.is_in(table['value_id'], value_set=pa.array(list(REQUIRED_IDS.keys())))
        )
        
        extracted_rg_rows = filtered_table.num_rows
        extracted_rows += extracted_rg_rows
        
        # Create signal_name column
        if extracted_rg_rows > 0:
            df = filtered_table.to_pandas()
            df['signal_name'] = df['value_id'].map(REQUIRED_IDS)
            
            # Ensure correct types
            df['vehicle_id'] = df['vehicle_id'].astype(str)
            # time remains its original type (datetime)
            df['value_id'] = df['value_id'].astype(int)
            df['value'] = df['value'].astype(float)
            df['signal_name'] = df['signal_name'].astype(str)
            
            final_table = pa.Table.from_pandas(df, schema=output_schema, preserve_index=False)
            
            if writer is None:
                writer = pq.ParquetWriter(output_path, output_schema)
            
            writer.write_table(final_table)
            
            del df
            del final_table
        
        # Release memory
        del table
        del filtered_table
        gc.collect()
        
        ram_after = get_memory_usage_mb()
        max_ram = max(max_ram, ram_after)
        
        print(f"  RG {rg_idx+1}/{n_row_groups} | Rows: {source_rg_rows:,} -> {extracted_rg_rows:,} | RAM: {ram_after:.1f} MB")

    if writer:
        writer.close()
    else:
        # If no rows were extracted, write an empty file with the schema
        empty_table = pa.Table.from_arrays(
            [pa.array([], type=t) for t in output_schema.types], 
            schema=output_schema
        )
        pq.write_table(empty_table, output_path)
        
    print(f"[{filename}] Finished. Extracted {extracted_rows:,} / {total_source_rows:,} rows.")
    return total_source_rows, extracted_rows, max_ram


def aggregate_statistics():
    """
    Calculate statistics over the extracted files using PyArrow.
    Does NOT load entire datasets into memory.
    """
    print("\nCalculating signal statistics and counts...")
    
    extracted_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('_required.parquet')]
    
    signal_counts = []
    signal_stats_acc = {}
    
    # Initialize accumulators
    for sig in REQUIRED_IDS.values():
        signal_stats_acc[sig] = {
            'count': 0, 'min': float('inf'), 'max': float('-inf'), 
            'sum': 0.0, 'null_count': 0
        }
        
    global_min_time = None
    global_max_time = None

    for file in extracted_files:
        vehicle_id = file.split('_')[0]
        filepath = os.path.join(OUTPUT_DIR, file)
        
        pf = pq.ParquetFile(filepath)
        
        # Dictionary to hold counts for this vehicle
        veh_counts = {sig: 0 for sig in REQUIRED_IDS.values()}
        
        for rg_idx in range(pf.num_row_groups):
            table = pf.read_row_group(rg_idx)
            
            if table.num_rows == 0:
                continue
                
            times = table['time'].to_numpy()
            if len(times) > 0:
                rg_min = np.min(times)
                rg_max = np.max(times)
                global_min_time = rg_min if global_min_time is None else min(global_min_time, rg_min)
                global_max_time = rg_max if global_max_time is None else max(global_max_time, rg_max)
            
            signal_names = table['signal_name'].to_numpy()
            values = table['value'].to_numpy()
            
            for sig in REQUIRED_IDS.values():
                mask = (signal_names == sig)
                count = np.sum(mask)
                if count > 0:
                    veh_counts[sig] += count
                    sig_vals = values[mask]
                    valid_mask = ~np.isnan(sig_vals)
                    valid_vals = sig_vals[valid_mask]
                    
                    signal_stats_acc[sig]['count'] += len(valid_vals)
                    signal_stats_acc[sig]['null_count'] += np.sum(~valid_mask)
                    if len(valid_vals) > 0:
                        signal_stats_acc[sig]['min'] = min(signal_stats_acc[sig]['min'], np.min(valid_vals))
                        signal_stats_acc[sig]['max'] = max(signal_stats_acc[sig]['max'], np.max(valid_vals))
                        signal_stats_acc[sig]['sum'] += np.sum(valid_vals)
            
            del table
            gc.collect()
            
        for sig, count in veh_counts.items():
            if count > 0:
                signal_counts.append({
                    'vehicle_id': vehicle_id,
                    'value_id': [k for k, v in REQUIRED_IDS.items() if v == sig][0],
                    'signal_name': sig,
                    'row_count': count
                })
                
    # Save signal counts
    counts_df = pd.DataFrame(signal_counts)
    counts_path = os.path.join(OUTPUT_DIR, 'tum_signal_counts.csv')
    counts_df.to_csv(counts_path, index=False)
    
    # Save signal statistics
    stats_list = []
    for sig, acc in signal_stats_acc.items():
        if acc['count'] > 0:
            stats_list.append({
                'signal_name': sig,
                'value_id': [k for k, v in REQUIRED_IDS.items() if v == sig][0],
                'count': acc['count'],
                'min': acc['min'],
                'max': acc['max'],
                'mean': acc['sum'] / acc['count'],
                'null_count': acc['null_count']
            })
    
    stats_df = pd.DataFrame(stats_list)
    stats_path = os.path.join(OUTPUT_DIR, 'tum_signal_statistics.csv')
    stats_df.to_csv(stats_path, index=False)
    
    return counts_df, stats_df, global_min_time, global_max_time


def _df_to_md_table(df):
    """Convert a DataFrame to a markdown table string (no tabulate needed)."""
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join([header, separator] + rows) + "\n"


def generate_report(total_source, total_ext, max_ram, elapsed_time, counts_df, stats_df, min_time, max_time):
    """Generate Markdown report for extraction."""
    
    report = f"""# TUM EV UDS Extraction Report

## 1. Overview
- **Source Rows**: {total_source:,}
- **Extracted Rows**: {total_ext:,} ({100*total_ext/total_source:.1f}%)
- **Max RAM Observed**: {max_ram:.1f} MB
- **Processing Time**: {elapsed_time:.1f} seconds

## 2. Selected Signals
Only the following `value_id`s were extracted:
"""
    for vid, name in REQUIRED_IDS.items():
        report += f"- `{vid}`: `{name}`\n"
        
    report += """
## 3. Semantic Limitations Enforced
- `ptc1_current` (1205) was retained as heater current, NOT assumed to be battery current.
- `hv_aux_power` (56) was retained as auxiliary power, NOT assumed to be traction power.
- `cell_c_rate` (1288) was retained natively without deriving current.

## 4. Output Files
Generated one Parquet file per vehicle in `data/interim/tum/`.
The data is strictly in **long format** (`vehicle_id`, `time`, `value_id`, `value`, `signal_name`). No pivoting was performed to prevent memory bloat and misalignment.

## 5. Timestamp Representation
- **Data Type**: Float (seconds)
- **Minimum Value**: {min_time}
- **Maximum Value**: {max_time}
- **Note**: The UDS time column is a relative or epoch float. It has NOT been converted to pandas datetime yet to save memory.

## 6. Signal Counts per Vehicle
"""
    if not counts_df.empty:
        report += _df_to_md_table(counts_df)
        
    report += "\n\n## 7. Global Signal Statistics\n"
    if not stats_df.empty:
        report += _df_to_md_table(stats_df)
        
    report_path = "docs/tum_extraction_report.md"
    os.makedirs("docs", exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")


def main():
    print("WARNING:")
    print("TUM contains ~98 million raw rows. Extraction will use row-group processing and value_id filtering.")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    files = [f for f in os.listdir(RAW_DATA_DIR) if f.endswith('.parquet')]
    
    total_source = 0
    total_ext = 0
    global_max_ram = 0.0
    
    start_time = time.time()
    
    for f in files:
        in_path = os.path.join(RAW_DATA_DIR, f)
        vid = f.replace('.parquet', '')
        out_path = os.path.join(OUTPUT_DIR, f"{vid}_required.parquet")
        
        src, ext, mx_ram = process_file(in_path, out_path)
        
        total_source += src
        total_ext += ext
        global_max_ram = max(global_max_ram, mx_ram)
        
    elapsed = time.time() - start_time
    
    counts_df, stats_df, min_time, max_time = aggregate_statistics()
    
    generate_report(total_source, total_ext, global_max_ram, elapsed, counts_df, stats_df, min_time, max_time)
    
    print("\n=== EXTRACTION COMPLETE ===")
    print(f"Total Source Rows: {total_source:,}")
    print(f"Total Extracted Rows: {total_ext:,}")
    print(f"Max RAM used: {global_max_ram:.1f} MB")
    print(f"Time elapsed: {elapsed:.1f} s")

if __name__ == "__main__":
    main()
