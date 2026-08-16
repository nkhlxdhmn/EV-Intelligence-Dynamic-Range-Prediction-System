# DEVRT Dataset Data Quality & Cleaning Report

## Overview
- **Total Files Discovered**: 58
- **Successfully Processed**: 58
- **Failed**: 0
- **Total Rows Processed**: 14,266

## Memory Observations
- **Maximum RAM Usage Observed**: 98.16 MB
- **Average RAM Usage**: 95.45 MB
- **Observation**: Memory remained stable throughout the execution due to the strict one-file-at-a-time loop and explicit garbage collection.

## Quality Flags Summary
| Quality Flag | Valid Rows | Invalid/Missing Rows | Pass Rate |
|--------------|------------|-----------------------|-----------|
| `quality_altitude` | 14,266 | 0 | 100.00% |
| `quality_distance` | 14,266 | 0 | 100.00% |
| `quality_gps` | 14,266 | 0 | 100.00% |
| `quality_reverse_speed` | 7 | 14,259 | 0.05% |
| `quality_soc` | 14,266 | 0 | 100.00% |
| `quality_soh` | 14,266 | 0 | 100.00% |
| `quality_speed` | 5,843 | 8,423 | 40.96% |
| `quality_timestamp` | 14,266 | 0 | 100.00% |

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
| `timestamp` | 0 | 0.00% |
| `trip_id` | 0 | 0.00% |
| `vehicle_id` | 0 | 0.00% |

## Invalid Values Analysis
Values outside standard physical ranges, excluding missing (NaN) values:
- **SOC out of bounds [0, 100]**: 0 rows
- **SOH out of bounds [0, 100]**: 0 rows
- **Latitude out of bounds [-90, 90]**: 0 rows
- **Longitude out of bounds [-180, 180]**: 0 rows
- **Negative Distance (< 0)**: 0 rows
- **Timestamp parsing failures**: 0 rows

## Unit Conversions Applied
The following conversions were applied to standard concepts:
1. **Motor Power**: Converted from Watts to kW (`Motor Pwr(w)` / 1000.0).
2. **Auxiliary Power**: Converted from units of 100W to kW (`Aux Pwr(100w)` * 100 / 1000.0).
3. **Battery Capacity**: Converted from Wh to kWh (`capacity` / 1000.0).
4. **Regenerative Power**: Converted from Watts to kW (`regenwh` / 1000.0). Sign was preserved (negative for regenerative braking).

## File-by-File Breakdown
| File Name | Rows Processed | Status |
|-----------|----------------|--------|
| 20230418_DACIA_ANDOAIN_AZPEITIA_011.csv | 347 | Success |
| 20230418_DACIA_AZPEITIA_DONOSTIA_012.csv | 414 | Success |
| 20230418_DACIA_DONOSTIA_HERNANI_001.csv | 74 | Success |
| 20230418_DACIA_DONOSTIA_IRUN_009.csv | 370 | Success |
| 20230418_DACIA_HERNANI_TOLOSA_002.csv | 210 | Success |
| 20230418_DACIA_IRUN_ANDOAIN_010.csv | 174 | Success |
| 20230418_DACIA_TOLOSA_ZARAUTZ_003.csv | 312 | Success |
| 20230418_DACIA_ZARAUTZ_DONOSTIA_004.csv | 176 | Success |
| 20230419_DACIA_ANDOAIN_AZPEITIA_027.csv | 411 | Success |
| 20230419_DACIA_AZPEITIA_DONOSTIA_028.csv | 403 | Success |
| 20230419_DACIA_DONOSTIA_HERNANI_017.csv | 85 | Success |
| 20230419_DACIA_DONOSTIA_IRUN_025.csv | 184 | Success |
| 20230419_DACIA_DONOSTIA_TOLOSA_033.csv | 256 | Success |
| 20230419_DACIA_HERNANI_TOLOSA_018.csv | 205 | Success |
| 20230419_DACIA_IRUN_ANDOAIN_026.csv | 212 | Success |
| 20230419_DACIA_TOLOSA_DONOSTIA_034.csv | 236 | Success |
| 20230419_DACIA_TOLOSA_ZARAUTZ_019.csv | 310 | Success |
| 20230419_DACIA_ZARAUTZ_DONOSTIA_020.csv | 163 | Success |
| 20230420_DACIA_BILBAO_EIBAR_051.csv | 337 | Success |
| 20230420_DACIA_DONOSTIA_HERNANI_037.csv | 82 | Success |
| 20230420_DACIA_DONOSTIA_HERNANI_045.csv | 76 | Success |
| 20230420_DACIA_EIBAR_BILBAO_049.csv | 486 | Success |
| 20230420_DACIA_EIBAR_DONOSTIA_053.csv | 462 | Success |
| 20230420_DACIA_HERNANI_EIBAR_047.csv | 597 | Success |
| 20230420_DACIA_HERNANI_TOLOSA_038.csv | 230 | Success |
| 20230420_DACIA_TOLOSA_ZARAUTZ_039.csv | 312 | Success |
| 20230420_DACIA_ZARAUTZ_DONOSTIA_040.csv | 194 | Success |
| 20230421_DACIA_DONOSTIA_ULIA_055.csv | 680 | Success |
| 20230421_DACIA_ULIA_HERNANI_057.csv | 425 | Success |
| 20230418_NISSAN_ANDOAIN_AZPEITIA_015.csv | 279 | Success |
| 20230418_NISSAN_AZPEITIA_DONOSTIA_016.csv | 274 | Success |
| 20230418_NISSAN_DONOSTIA_HERNANI_005.csv | 49 | Success |
| 20230418_NISSAN_DONOSTIA_IRUN_013.csv | 252 | Success |
| 20230418_NISSAN_HERNANI_TOLOSA_006.csv | 136 | Success |
| 20230418_NISSAN_IRUN_ANDOAIN_014.csv | 118 | Success |
| 20230418_NISSAN_TOLOSA_ZARAUTZ_007.csv | 207 | Success |
| 20230418_NISSAN_ZARAUTZ_DONOSTIA_008.csv | 121 | Success |
| 20230419_NISSAN_ANDOAIN_AZPEITIA_031.csv | 309 | Success |
| 20230419_NISSAN_AZPEITIA_DONOSTIA_032.csv | 267 | Success |
| 20230419_NISSAN_DONOSTIA_HERNANI_021.csv | 59 | Success |
| 20230419_NISSAN_DONOSTIA_IRUN_029.csv | 272 | Success |
| 20230419_NISSAN_DONOSTIA_TOLOSA_035.csv | 169 | Success |
| 20230419_NISSAN_HERNANI_TOLOSA_022.csv | 129 | Success |
| 20230419_NISSAN_IRUN_ANDOAIN_030.csv | 139 | Success |
| 20230419_NISSAN_TOLOSA_DONOSTIA_036.csv | 172 | Success |
| 20230419_NISSAN_TOLOSA_ZARAUTZ_023.csv | 219 | Success |
| 20230419_NISSAN_ZARAUTZ_DONOSTIA_024.csv | 122 | Success |
| 20230420_NISSAN_BILBAO_EIBAR_052.csv | 216 | Success |
| 20230420_NISSAN_DONOSTIA_HERNANI_041.csv | 59 | Success |
| 20230420_NISSAN_DONOSTIA_HERNANI_046.csv | 49 | Success |
| 20230420_NISSAN_EIBAR_BILBAO_050.csv | 304 | Success |
| 20230420_NISSAN_EIBAR_DONOSTIA_054.csv | 311 | Success |
| 20230420_NISSAN_HERNANI_EIBAR_048.csv | 386 | Success |
| 20230420_NISSAN_HERNANI_TOLOSA_042.csv | 144 | Success |
| 20230420_NISSAN_TOLOSA_ZARAUTZ_043.csv | 201 | Success |
| 20230420_NISSAN_ZARAUTZ_DONOSTIA_044.csv | 126 | Success |
| 20230421_NISSAN_DONOSTIA_ULIA_056.csv | 462 | Success |
| 20230421_NISSAN_ULIA_HERNANI_058.csv | 292 | Success |
