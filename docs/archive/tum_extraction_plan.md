# TUM Dataset Extraction Plan

## 1. Context and Objective
The TUM dataset contains real-world EV operation data for 7 vehicles (2 VW ID.3, 5 CUPRA Born). The raw data is stored in Parquet files in `data/uds_data/`. The goal is to safely extract only the features useful for dynamic range prediction without exhausting the limited RAM (16 GB) on the development machine.

## 2. Extraction Principles
- **Do not use `pd.read_parquet()` on entire files**: Loading the whole `.parquet` for a vehicle directly into a pandas DataFrame will likely cause OOM crashes.
- **Use Parquet Column Projection**: Read only the necessary columns (e.g., `timestamp`, `value_id`, `value`).
- **Use PyArrow filters**: Filter data *on read* by `value_id` using `pyarrow.parquet.read_table(..., filters=[('value_id', 'in', REQUIRED_IDS)])`.
- **Iterate via Row Groups**: If even column projection + filtering is too large, use `ParquetFile.iter_batches()` or `ParquetFile.read_row_group()` to process chunks of rows individually, filtering and saving the chunks out to interim Parquet files before garbage collection.

## 3. Recommended Signals (value_ids)

### A. REQUIRED (Core telemetry for range prediction)
- `900` (`hv_soc`): State of Charge (%)
- `4` (`vehicle_speed`): Vehicle speed (km/h)
- `1299` (`traveled_distance`): Distance traveled (km) - *Wait, this might be trip distance, check sampling*
- `15` (`ambient_air_temp`): Ambient temperature (°C)
- `1200` (`hv_battery_voltage`): Pack voltage (V)

### B. USEFUL (For energy / auxiliary power estimation)
- `56` (`hv_aux_power`): Power HV Aux (W). *Note: This is auxiliary power, NOT traction power.*
- `1205` / `1206` / `1207`: PTC (Heater) Current and Voltage.
- `1288` (`cell_c_rate`): Cell C-rate (1/h). Can be used to estimate battery current (Current = C-rate * Capacity).

### C. IGNORE
- Motor temperatures (`961`, `1265`)
- Battery internal temperatures (`1208`, `1209`, `1272`, `1273`)
- Histograms (JSON files): We need time-series data for dynamic prediction, not histograms.

## 4. Addressing Missing Signals
- **Battery Current**: There is NO direct HV battery current signal in the dataset. `ptc1_current` (1205) is only the heater current.
  - *Mitigation*: We must derive current from `cell_c_rate` (1288) using the known battery capacity (58 kWh).
- **Traction Power**: There is NO direct traction power signal. `hv_aux_power` (56) is auxiliary only.
  - *Mitigation*: Derive total power by integrating SOC changes, or by computing Voltage × (Derived Current).
- **GPS / Altitude**: UDS data does not contain GPS latitude/longitude or altitude.
  - *Mitigation*: We cannot use terrain/elevation features for the TUM dataset unless we synthesize them based on known routes (which aren't provided).

## 5. Chunked Extraction Workflow
1. For each `vehicle_id.parquet`:
2. Open with `pf = pyarrow.parquet.ParquetFile("vehicle.parquet")`.
3. Loop through `range(pf.num_row_groups)`.
4. Read row group: `table = pf.read_row_group(i, columns=['timestamp', 'value_id', 'value'])`.
5. Filter table for `value_id in REQUIRED_IDS`.
6. Convert to pandas: `df = table.to_pandas()`.
7. Pivot to wide format: `df.pivot(index='timestamp', columns='value_id', values='value')`.
8. Append to an interim Parquet file (or write row-group specific file).
9. Delete `table`, `df` and call `gc.collect()`.
10. Combine all small interim files at the end.
