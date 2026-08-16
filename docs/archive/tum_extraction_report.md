# TUM EV UDS Extraction Report

## 1. Overview
- **Source Rows**: 98,061,214
- **Extracted Rows**: 91,612,113 (93.4%)
- **Max RAM Observed**: 419.1 MB
- **Processing Time**: 20.5 seconds

## 2. Selected Signals
Only the following `value_id`s were extracted:
- `4`: `vehicle_speed`
- `15`: `ambient_air_temp`
- `56`: `hv_aux_power`
- `900`: `hv_soc`
- `1200`: `hv_battery_voltage`
- `1205`: `ptc1_current`
- `1288`: `cell_c_rate`
- `1299`: `traveled_distance`

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
| vehicle_id | value_id | signal_name | row_count |
| --- | --- | --- | --- |
| CUP1 | 4 | vehicle_speed | 2150504 |
| CUP1 | 15 | ambient_air_temp | 51637 |
| CUP1 | 56 | hv_aux_power | 512018 |
| CUP1 | 900 | hv_soc | 126742 |
| CUP1 | 1200 | hv_battery_voltage | 5282082 |
| CUP2 | 4 | vehicle_speed | 756739 |
| CUP2 | 15 | ambient_air_temp | 25437 |
| CUP2 | 56 | hv_aux_power | 251621 |
| CUP2 | 900 | hv_soc | 53088 |
| CUP2 | 1200 | hv_battery_voltage | 2386969 |
| CUP3 | 4 | vehicle_speed | 217344 |
| CUP3 | 15 | ambient_air_temp | 6434 |
| CUP3 | 56 | hv_aux_power | 64713 |
| CUP3 | 900 | hv_soc | 13764 |
| CUP3 | 1200 | hv_battery_voltage | 619997 |
| CUP4 | 4 | vehicle_speed | 1079914 |
| CUP4 | 15 | ambient_air_temp | 32869 |
| CUP4 | 56 | hv_aux_power | 324957 |
| CUP4 | 900 | hv_soc | 68326 |
| CUP4 | 1200 | hv_battery_voltage | 3085181 |
| CUP5 | 4 | vehicle_speed | 841741 |
| CUP5 | 15 | ambient_air_temp | 20288 |
| CUP5 | 56 | hv_aux_power | 200807 |
| CUP5 | 900 | hv_soc | 45145 |
| CUP5 | 1200 | hv_battery_voltage | 1978897 |
| ID1 | 4 | vehicle_speed | 4537006 |
| ID1 | 15 | ambient_air_temp | 283059 |
| ID1 | 56 | hv_aux_power | 2548507 |
| ID1 | 900 | hv_soc | 821873 |
| ID1 | 1200 | hv_battery_voltage | 29383790 |
| ID1 | 1205 | ptc1_current | 273222 |
| ID2 | 4 | vehicle_speed | 7689927 |
| ID2 | 15 | ambient_air_temp | 197214 |
| ID2 | 56 | hv_aux_power | 1821868 |
| ID2 | 900 | hv_soc | 539521 |
| ID2 | 1200 | hv_battery_voltage | 23318912 |


## 7. Global Signal Statistics
| signal_name | value_id | count | min | max | mean | null_count |
| --- | --- | --- | --- | --- | --- | --- |
| vehicle_speed | 4 | 17273175 | 0.0 | 428.68 | 37.26206018117688 | 0 |
| ambient_air_temp | 15 | 616938 | -11.0 | 39.5 | 9.446746674706372 | 0 |
| hv_aux_power | 56 | 5724491 | 0.0 | 25400.0 | 778.5214852115236 | 0 |
| hv_soc | 900 | 1668459 | 0.0 | 101.6 | 68.42653682230127 | 0 |
| hv_battery_voltage | 1200 | 66055828 | 0.0 | 8642.5 | 419.9695609462346 | 0 |
| ptc1_current | 1205 | 273222 | 0.0 | 63.5 | 1.2212312698098982 | 0 |
