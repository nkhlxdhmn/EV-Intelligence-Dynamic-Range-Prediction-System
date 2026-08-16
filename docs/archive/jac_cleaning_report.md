# JAC IEV40 Data Quality & Cleaning Report

## 1. Source File
- **File**: `dataset.csv`
- **Location**: `dataset/archive/`
- **Size**: 2.7775 MB

## 2. Row Counts
- **Raw row count**: 24,277
- **Processed row count**: 24,277
- **Rows removed**: 0 (no rows removed — all preserved with quality flags)

## 3. Flagged Rows Summary
| Quality Flag | Valid | Invalid/Flagged |
|-------------|-------|-----------------|
| `quality_timestamp` | 24,206 | 71 |
| `quality_speed` | 24,277 | 0 |
| `quality_gps` | 24,275 | 2 |
| `quality_odometer` | 24,277 | 0 |
| `quality_altitude` | 24,277 | 0 |
| `quality_reverse_speed` | 0 rows with negative speed | — |

## 4. Missing Values
| Column | Missing Count | Percentage |
|--------|---------------|------------|
| `accelerator_raw` | 0 | 0.00% |
| `air_sensor_flag` | 0 | 0.00% |
| `altitude_m` | 0 | 0.00% |
| `brake_raw` | 0 | 0.00% |
| `current_raw` | 0 | 0.00% |
| `eco_mode` | 0 | 0.00% |
| `latitude` | 0 | 0.00% |
| `longitude` | 0 | 0.00% |
| `odometer_km` | 0 | 0.00% |
| `quality_altitude` | 0 | 0.00% |
| `quality_gps` | 0 | 0.00% |
| `quality_odometer` | 0 | 0.00% |
| `quality_reverse_speed` | 0 | 0.00% |
| `quality_speed` | 0 | 0.00% |
| `quality_timestamp` | 0 | 0.00% |
| `source_dataset` | 24,277 | 100.00% |
| `source_file` | 24,277 | 100.00% |
| `source_row_id` | 0 | 0.00% |
| `speed_kmh` | 0 | 0.00% |
| `timestamp` | 71 | 0.29% |
| `vehicle_id` | 0 | 0.00% |
| `vol_raw` | 0 | 0.00% |

## 5. Timestamp Analysis
- **Reconstruction**: Built from Y/M/D/H/MIN/SEC columns
- **Valid timestamps**: 24,206 / 24,277 (99.7%)
- **Invalid timestamps**: 71 (Y=0, M=0, D=0 or out-of-range values)
- **Earliest**: 2023-10-23 01:00:00
- **Latest**: 2023-10-26 20:14:12
- **Duplicate timestamps**: 17
- **Chronologically sorted**: True
- **Sampling interval (median)**: 2.0s
- **Sampling interval (min)**: 0.0s
- **Sampling interval (max)**: 92060.0s
- **Gaps > 60s**: 16

> **Note**: The data is NOT pre-sorted by timestamp. Many rows have invalid (all-zero) date fields and are interspersed throughout the file. The actual sampling rate appears to be approximately every 1–2 seconds when timestamps are valid.

## 6. GPS Validation
- **Valid GPS coordinates**: 24,275
- **Invalid GPS coordinates**: 2
- **Latitude range**: [-21.97695541, 21.96396065]
- **Longitude range**: [-46.75, 637.0]

> **Warning**: Longitude values up to 637.0 were observed, which exceeds the valid [-180, 180] range. This may indicate coordinate wrapping (modulo 360) or data corruption. These rows are flagged via `quality_gps = 0`.

## 7. Speed Analysis
- **Range**: [0.0, 134.0] km/h
- **Mean**: 56.64 km/h
- **Negative speed values**: 0
- **Zero speed (stopped)**: 1,498
- **Unit**: Verified as km/h (direct measurement, no scaling needed)

## 8. Odometer Analysis
- **Range**: [25656.0, 26352.4] km
- **Total distance covered**: 696.4 km
- **Unit**: Verified as km (cumulative odometer reading)
- **Note**: ODO is the cumulative vehicle odometer, NOT trip-level distance.

## 9. Altitude Analysis
- **Range**: [0.0, 1352.4] m
- **Mean**: 1077.5 m
- **Zero values**: 97
- **Unit**: Listed as meters (m) in column name; reference frame (ASL vs relative) uncertain.

## 10. BRK (Brake) Analysis
- **Range**: [0.0, 38.0]
- **Unique values**: 19
- **Interpretation**: Raw sensor signal. NOT a 0–100% pedal position. Do not normalize.

## 11. ACC (Accelerator) Analysis
- **Range**: [0.0, 94.0]
- **Unique values**: 48
- **Interpretation**: Raw sensor signal. NOT a 0–100% throttle position. Do not normalize.

## 12. ECO Mode Analysis
- **Unique values**: [0, 192]
- **ECO off (0)**: 23,175
- **ECO on (192)**: 1,102
- **Interpretation**: Binary flag. 0 = ECO off, 192 = ECO on.

## 13. AIR Handling
- **Unique values**: [0, 2]
- **Count of 0**: 12,979
- **Count of 2**: 11,298
- **Interpretation**: Sensor/status flag. NOT ambient temperature. Stored as `air_sensor_flag`.
- **`ambient_temperature_c` NOT created** — AIR is not a temperature measurement.

## 14. VOL Handling
- **Range**: [0.0, 381.0]
- **Mean**: 98.68
- **Interpretation**: Likely raw ADC values. NOT verified as battery voltage.
- **`battery_voltage_v` NOT created** — semantics unverified.
- **Stored as**: `vol_raw`

## 15. CUR Handling
- **Range**: [-52.0, 301.0]
- **Mean**: 28.09
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
7. **Invalid timestamps**: 71 rows have Y=0/M=0/D=0 or otherwise un-parseable timestamps.

## 17. Standardized Columns Created
- `source_dataset`
- `source_file`
- `source_row_id`
- `vehicle_id`
- `timestamp`
- `speed_kmh`
- `odometer_km`
- `latitude`
- `longitude`
- `altitude_m`
- `brake_raw`
- `accelerator_raw`
- `eco_mode`
- `vol_raw`
- `current_raw`
- `air_sensor_flag`
- `quality_timestamp`
- `quality_speed`
- `quality_reverse_speed`
- `quality_gps`
- `quality_odometer`
- `quality_altitude`

## 18. Files Created
- `data/interim/jac/jac_standardized.parquet`
- `data/interim/jac/jac_standardized.csv`
- `data/interim/jac/jac_quality_flags.parquet`
- `data/interim/jac/processing_summary.json`
- `docs/jac_cleaning_report.md` (this file)
