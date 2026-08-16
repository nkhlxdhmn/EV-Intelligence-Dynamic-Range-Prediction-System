# DEVRT Data Quality Summary

## Processing Overview

- **Total Files Discovered**: 58 CSV trip files
- **Successfully Processed**: 58/58 (100%)
- **Failed**: 0/58 (0%)
- **Total Rows Processed**: 14,266
- **Memory Peak**: 98.92 MB (well within 16 GB limit)
- **Average RAM per File**: 96.57 MB

## Processing Method

- **Strategy**: One file at a time with explicit `gc.collect()` between files
- **Never**: `pd.concat(all_files)` or loading all CSVs into one DataFrame
- **Output**: One parquet file per trip + CSV backup in `data/interim/devrt/`

## Quality Flags

| Quality Flag | Valid Rows | Invalid/Missing | Pass Rate |
|--------------|------------|-----------------|-----------|
| `quality_altitude` | 14,266 | 0 | 100.00% |
| `quality_distance` | 14,266 | 0 | 100.00% |
| `quality_gps` | 14,266 | 0 | 100.00% |
| `quality_reverse_speed` | 7 | 14,259 | 0.05% |
| `quality_soc` | 14,266 | 0 | 100.00% |
| `quality_soh` | 14,266 | 0 | 100.00% |
| `quality_speed` | 5,843 | 8,423 | 40.96% |
| `quality_timestamp` | 10,013 | 4,253 | 70.19% |

## Missing Values Report

| Standardized Column | Missing Values Count | Percentage |
|---------------------|----------------------|------------|
| `altitude_m` | 0 | 0.00% |
| `ambient_temperature_c` | 8,423 | 59.04% |
| `aux_power_kw` | 8,423 | 59.04% |
| `battery_capacity_kwh` | 0 | 0.00% |
| `distance_km` | 0 | 0.00% |
| `latitude` | 0 | 0.00% |
| `longitude` | 0 | 0.00% |
| `motor_power_kw` | 8,423 | 59.04% |
| `motor_rpm` | 8,423 | 59.04% |
| `motor_temperature_c` | 8,423 | 59.04% |
| `motor_torque_nm` | 8,423 | 59.04% |
| `quality_altitude` | 0 | 0.00% |
| `quality_distance` | 0 | 0.00% |
| `quality_gps` | 0 | 0.00% |
| `quality_reverse_speed` | 0 | 0.00% |
| `quality_soc` | 0 | 0.00% |
| `quality_soh` | 0 | 0.00% |
| `quality_speed` | 0 | 0.00% |
| `quality_timestamp` | 0 | 0.00% |
| `reference_consumption_wh_per_km` | 0 | 0.00% |
| `regen_power_kw` | 8,423 | 59.04% |
| `soc_pct` | 0 | 0.00% |
| `soh_pct` | 0 | 0.00% |
| `source_dataset` | 0 | 0.00% |
| `source_file` | 0 | 0.00% |
| `source_row_id` | 0 | 0.00% |
| `speed_kmh` | 8,423 | 59.04% |
| `timestamp` | 4,253 | 29.81% |
| `trip_id` | 0 | 0.00% |
| `vehicle_id` | 0 | 0.00% |

## Invalid Values Analysis

- **SOC out of bounds [0, 100]**: 0 rows
- **SOH out of bounds [0, 100]**: 0 rows
- **Latitude out of bounds [-90, 90]**: 0 rows
- **Longitude out of bounds [-180, 180]**: 0 rows
- **Negative Distance (< 0)**: 0 rows
- **Timestamp parsing failures**: 4,253 rows (30% of total)

Note: 7 rows had negative speed values (reverse driving), flagged via `quality_reverse_speed`.

## Unit Conversions Applied

1. **Motor Power**: W → kW (`Motor Pwr(w)` / 1000.0)
   - Available only for Nissan Leaf files (29/58 trips)
   - Dacia Spring: all NaN

2. **Auxiliary Power**: units of 100W → kW (`Aux Pwr(100w)` × 100 / 1000.0)
   - Constant 0.2 kW for all rows where available

3. **Battery Capacity**: Wh → kWh (`capacity` / 1000.0)
   - Dacia Spring: 33 kWh constant
   - Nissan Leaf: 62 kWh constant

4. **Regenerative Power**: W → kW (`regenwh` / 1000.0)
   - Sign preserved: negative = regenerative braking
   - Dacia Spring: all NaN (no regen column)
   - Nissan Leaf: 279/279 rows with negative values

## Timestamp Quality

- **10,013/14,266 (70.19%)** timestamps parsed successfully
- **4,253/14,266 (29.81%)** failed to parse
- Failed timestamps predominantly from Dacia Spring files
- Dacia Spring timestamps format: `HH:MMSS` (e.g., `33:04.6`)
- Nissan Leaf timestamps format: ISO 8601 (e.g., `18/04/2023 11:33`)
- The parser attempted both formats; Dacia Spring's format was recognized but many values still failed

## Key Statistics by Dataset Subset

### Dacia Spring (30 files, 6,889 rows)
- SOC: 64-81%, mean 71.57%
- SOH: 98.5% constant
- Speed: all NaN (not available in Dacia files)
- Regen power: all NaN (not available in Dacia files)
- Ambient temperature: all NaN
- Motor power: all NaN
- Reference consumption: 139 Wh/km constant
- Battery capacity: 33 kWh constant

### Nissan Leaf (28 files, 7,377 rows)
- SOC: 77-87%, mean 80.97%
- SOH: 99.27% constant
- Speed: 0-116.2 km/h, mean 51.90 km/h
- Regen power: -2.97 to -0.62 kW (negative = regenerative braking), mean -1.25 kW
- Ambient temperature: 13.5-19.0°C, mean 16.27°C
- Motor power: 0-33.76 kW, mean 6.57 kW
- Aux power: 0.2 kW constant
- Reference consumption: 174 Wh/km constant
- Battery capacity: 62 kWh constant

## Files Created

- `data/interim/devrt/` - 58 standardized parquet files + 58 CSV backups
- `data/interim/devrt/processing_summary.json` - processing metadata
- `docs/devrt_cleaning_report.md` - comprehensive quality report

## Unresolved Issues / Limitations

1. **Dacia Spring missing data**: SOC, speed, regen, ambient temp, motor power all NaN
   - Only: SOC, SOH, capacity, cumul_dist available
   - Consider whether Dacia Spring should be excluded from certain feature groups

2. **Timestamp parsing**: 29.81% failure rate due to format differences between Dacia Spring and Nissan Leaf
   - Consider improved format detection or separate temporal features per vehicle type

3. **Ambient temperature**: Available only for Nissan Leaf (29/58 files)
   - Dacia Spring lacks ambient temperature data

4. **Motor power**: Available only for Nissan Leaf (29/58 files)
   - Dacia Spring lacks motor power data

5. **Regen power**: Available only for Nissan Leaf (29/58 files)
   - Dacia Spring lacks regen data

6. **Speed**: Available only for Nissan Leaf (29/58 files)
   - Dacia Spring lacks speed data

## Recommendations

1. **DEVRT is viable for initial model training** using Nissan Leaf files (29/58 trips)
2. **Dacia Spring can provide SOC and capacity information** but lacks driving dynamics
3. **Consider modeling approach**: Train on Nissan Leaf subset, validate on full dataset with imputation
4. **Future work**: Improve timestamp parsing for Dacia Spring format; investigate why ambient temp, speed, and regen are absent in Dacia Spring files