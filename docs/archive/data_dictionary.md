# Data Dictionary - Verified Column Mappings

## Definition
This data dictionary documents verified columns and standard concepts across the three datasets (DEVRT, JAC IEV40, TUM EV UDS).
**IMPORTANT**: This does NOT rename raw columns. It documents what each raw column represents based on inspection evidence.

### DEVRT Data Dictionary

| Dataset | Raw Column | Data Type | Unit | Standard Concept | Meaning | Direct/Derived | Confidence |
|---------|-----------|-----------|------|-----------------|---------|----------------|------------|
| DEVRT | `timestamp_data_utc` | datetime | UTC | `timestamp` | Primary trip timestamp (UTC) | Direct | High |
| DEVRT | `car_id` | int | — | `vehicle_id` | Vehicle identifier | Direct | High |
| DEVRT | `driver` | string | — | `driver_id` | Route driver name/ID | Direct | Medium |
| DEVRT | `soc` | float | % | `soc_pct` | State of Charge percentage | Direct | High |
| DEVRT | `soh` | float | % | `soh_pct` | State of Health percentage | Direct | High |
| DEVRT | `speed` | float | km/h | `speed_kmh` | Vehicle speed | Direct | High |
| DEVRT | `cumul_dist` | float | km | `distance_km` | Cumulative distance from trip start | Direct | High |
| DEVRT | `altitude` | float | m | `altitude_m` | Elevation (elv_spy sensor) | Direct | High |
| DEVRT | `elv_spy` | float | m | `altitude_m` (alt) | Elevation (Spy application) | Direct | High |
| DEVRT | `latitude` | float | deg | `latitude` | GPS latitude | Direct | High |
| DEVRT | `longitude` | float | deg | `longitude` | GPS longitude | Direct | High |
| DEVRT | `amb_temp` | float | °C | `ambient_temperature_c` | Ambient air temperature | Direct | High |
| DEVRT | `regenwh` | float | W | `regen_energy_kwh` (derived) | Regeneration power (instantaneous) | Derived | Medium |
| DEVRT | `Motor Pwr(w)` | float | W | `motor_power_kw` (derived) | Motor power | Derived | Medium (Nissan Leaf only) |
| DEVRT | `Aux Pwr(100w)` | int | (×100W) | `aux_power_kw` (derived) | Auxiliary power (2×100=200W) | Derived | Medium |
| DEVRT | `capacity` | int | Wh | `battery_capacity_kwh` | Battery capacity (33000=33kWh, 62000=62kWh) | Direct | High |
| DEVRT | `ref_consumption` | int | Wh/km | (baseline reference) | Reference consumption (not as target) | — | Medium |
| DEVRT | `Torque Nm` | float | Nm | `motor_torque_nm` | Motor torque | Direct | Medium |
| DEVRT | `rpm` | float | rpm | (engine speed) | Engine revolutions per minute | Direct | Medium |
| DEVRT | `amb_temp` | float | °C | `ambient_temperature_c` | Ambient temperature | Direct | High |
| DEVRT | `soc` | float | % | `soc_pct` | State of Charge | Direct | High |
| DEVRT | `soh` | float | % | `soh_pct` | State of Health | Direct | High |

### JAC IEV40 Data Dictionary

| Dataset | Raw Column | Data Type | Unit | Standard Concept | Meaning | Direct/Derived | Confidence |
|---------|-----------|-----------|------|-----------------|---------|----------------|------------|
| JAC | `VOL` | float | V | `battery_voltage_v` | Battery voltage (UNVERIFIED, likely raw ADC) | Derived/UNVERIFIED | Low |
| JAC | `CUR` | float | A | `battery_current_a` | Battery current (raw) | Direct (raw) | Medium |
| JAC | `SPD` | float | km/h | `speed_kmh` | Vehicle speed | Direct | High |
| JAC | `ODO` | float | km | `distance_km` | Odometer distance | Direct | High |
| JAC | `LAT` | float | deg | `latitude` | GPS latitude | Direct (valid range) | Medium |
| JAC | `LON` | float | deg | `longitude` | GPS longitude | Direct (investigate 263 max) | Medium |
| JAC | `ALT` | float | m | `altitude_m` | Altitude (reference frame unknown) | Direct | Medium |
| JAC | `AIR` | int (0/2) | — | (NOT ambient_temperature) | **Sensor status flag**: 0=invalid, 2=valid | **Processed flag** | **High (as flag)** |
| JAC | `BRK` | float | — | `brake_intensity` (UNVERIFIED) | Brake status (0-28 range, not %%) | Derived/UNVERIFIED | Low |
| JAC | `ACC` | float | — | `accelerator_position` (UNVERIFIED) | Accelerator position (0-90 range, not %%) | Derived/UNVERIFIED | Low |
| JAC | `AUT` | float | — | `automatic_mode` (UNVERIFIED) | Automatic transmission mode code | Derived/UNVERIFIED | Low |
| JAC | `ECO` | int | Binary (0/192) | `eeco_mode` | ECO mode indicator (0=off, 192=on) | Direct (binary flag) | High |
| JAC | `Y, M, D, H, MIN, SEC` | int | — | `timestamp` (derived) | Date/time (reconstruct from 6 cols) | Derived | Medium |
| JAC | `AX, AY, AZ` | float | raw counts | `acceleration_m_s2` (after /192) | After scaling: acceleration in m/s² | Derived | Medium (after scaling) |
| JAC | `GX, GY, GZ` | float | raw counts | `gyro_rad_s` (requires sensor spec) | Gyroscope angular rates | Derived (UNVERIFIED) | Low |
| JAC | `soc` | N/A | — | **NOT AVAILABLE** | No SOC column in dataset | Very Low | Very Low |
| JAC | `soh` | N/A | — | **NOT AVAILABLE** | No SOH column in dataset | Very Low | Very Low |

### TUM EV UDS Data Dictionary (from value_overview.csv)

| Dataset | value_id | Raw Column (variable_name) | Data Type | Unit | Standard Concept | Meaning | Direct/Derived | Confidence |
|---------|----------|---------------------------|-----------|------|-----------------|---------|----------------|------------|
| TUM | 900 | `hv_soc` | float | % | `soc_pct` | State of Charge | Direct | High |
| TUM | 4 | `vehicle_speed` | float | km/h | `speed_kmh` | Vehicle speed | Direct | High |
| TUM | 1200 | `hv_battery_voltage` | float | V | `battery_voltage_v` | Pack voltage | Direct | High |
| TUM | 1205 | `ptc1_current` | float | A | `battery_current_a` | PTC1 current | Direct | High |
| TUM | 15 | `ambient_air_temp` | float | °C | `ambient_temperature_c` | Ambient air temperature | Direct | High |
| TUM | 56 | `hv_aux_power` | float | W | `aux_power_kw` (derived) | HV auxiliary power | Direct (W→kW/1000) | High |
| TUM | 1299 | `traveled_distance` | float | km | `distance_km` | Traveled distance per segment | Direct | High |
| TUM | 1291 | `track_duration` | float | min | `trip_duration_min` | Driving track duration | Direct | High |
| TUM | 1290 | `hv_dod` | float | % | `dod_pct` | Depth of Discharge ( = 100 - SOC) | Direct | High |
| TUM | 1288 | `cell_c_rate` | float | 1/h | `cell_c_rate_1_per_h` | Cell C-rate (negative=charge, positive=discharge) | Direct | High |
| TUM | 1293 | `cell_voltage_max` | float | V | `cell_voltage_v` | Max cell voltage (0-5V per cell) | Direct | High |
| TUM | 1294 | `cell_voltage_min` | float | V | `cell_voltage_v` (min) | Min cell voltage (0-5V per cell) | Direct | High |
| TUM | 1295 | `cell_voltage_delta` | float | V | `cell_voltage_delta` | Max cell voltage difference | Direct | High |
| TUM | 1208 | `hv_temp_min` | float | °C | `battery_temp_c` | HV battery temp min | Direct | High |
| TUM | 1209 | `hv_temp_max` | float | °C | `battery_temp_c` (max) | HV battery temp max | Direct | High |
| TUM | 43 | `interior_temp` | float | °C | `cabin_temp_c` | Interior/cabin temperature | Direct | High |
| TUM | 961 | `temp_rear_motor_stator` | float | °C | `motor_temp_c` | Rear motor stator temperature | Direct | High |
| TUM | 1265 | `rear_motor_rotor_temp` | float | °C | `motor_temp_c` (rotor) | Rear motor rotor temperature | Direct | High |
| TUM | 1269 | `coolant_temp_inverter_inlet` | float | °C | `coolant_temp_c` (inverter inlet) | Inverter coolant inlet temperature | Direct | High |
| TUM | 1272 | `hv_battery_temp_inlet` | float | °C | `battery_temp_c` (inlet) | HV battery pack inlet temperature | Direct | High |
| TUM | 1273 | `hv_battery_temp_outlet` | float | °C | `battery_temp_c` (outlet) | HV battery pack outlet temperature | Direct | High |
| TUM | 1289 | `hv_temp_delta` | float | °C | `pack_temp_delta_c` | Max temperature difference in pack | Direct | High |
| TUM | 1300 | `ptc1_power` | float | W | `ptc_power_kw` (derived) | PTC1 heater power | Derived (W→kW/1000) | Medium |
| TUM | 1301 | `ptc2_power` | float | W | `ptc_power_kw` (derived) | PTC2 heater power | Derived (W→kW/1000) | Medium |
| TUM | 1303 | `cell_c_rate_peak_freq` | float | Hz | `c_rate_peak_freq_hz` | Frequency of C-rate peaks | Direct | Medium |
| TUM | 1302 | `cell_c_rate_peak_ampl` | float | 1/C | `c_rate_peak_ampl_1_per_C` | Amplitude of C-rate peaks | Direct | Medium |

## Unmappable Columns (Not Documented as Standard Concepts)

| Dataset | Raw Column | Reason Not Documented |
|---------|-----------|----------------------|
| DEVRT | `wind_mph`, `wind_kph`, `wind_degree`, `wind_dir`, `Frontal_Wind` | Available but not core to energy consumption target |
| DEVRT | `point_geom`, `route_code`, `route_description`, `driver`, `start_timestamp`, `end_timestamp`, `car_code`, `car_description`, `totalVehicles`, `speedAvg`, `cars_by_speed_interval_*`, `max_speed`, `radius` | Non-essential for target calculation |
| JAC | `Y, M, D, H, MIN, SEC` | Documented as "timestamp (derived)" in dictionary |
| JAC | `AX, AY, AZ` | Documented as "acceleration after /192 scaling" |
| JAC | `GX, GY, GZ` | Documented as "gyro (UNVERIFIED, needs sensor spec)" |
| TUM | All 100+ value_ids NOT in the 29 inspected | Only 29 of ~100+ value_ids inspected; remainder documented if relevant |
| TUM | JSON histogram data (x_values, y_values) | Processed histograms, not raw data; separate from value_overview |

## Confidence Legend

| Confidence Level | Description |
|-----------------|-------------|
| **High** | Column meaning well-established from documentation and data inspection |
| **Medium** | Meaning reasonably established but may require scaling or verification |
| **Low** | Meaning uncertain; requires documentation review or data analysis |
| **Very Low** | Not available in dataset; column does not exist or has entirely different meaning |
| **UNVERIFIED** | Meaning could not be confirmed from inspected data/documentation |
| **Flag** | Column is a status flag, not a continuous measurement (e.g., JAC AIR) |

## Usage Notes

1. **This dictionary does NOT rename raw columns** in the source datasets. It documents what each column represents for planning purposes.

2. **Confidence levels indicate how reliably the standard concept can be obtained** from the raw column. Use high-confidence mappings for model features; treat low-confidence mappings as needing further investigation.

3. **For JAC AIR**: Documented as "NOT ambient_temperature" with "High confidence as sensor flag". Do NOT use value as temperature °C.

4. **For JAC VOL**: Documented as "UNVERIFIED, likely raw ADC". Do NOT use for power calculations without scaling factor confirmation.

5. **For TUM value_ids**: Only the 29 inspected value_ids are documented. The full dataset contains ~100+ value_ids; future work may inspect additional ones.

6. **For derived concepts** (e.g., `gradient_pct`, `regen_energy_kwh`): These are defined in separate documentation (derived_features.md, dataset_mapping.md) and not repeated here.

7. **When merging datasets**: Use the "Standard Concept" column as the key, NOT the raw column names. Different datasets use different column names for the same physical quantity.