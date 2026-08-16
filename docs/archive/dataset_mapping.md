# Dataset Standard Concept Mapping

## Mapping Table: Standard Concept ↔ Raw Columns

This table maps standard concepts to raw dataset columns. 
**IMPORTANT**: This does NOT rename raw columns. It shows which raw columns map to which standard concepts.

| Standard Concept | DEVRT Raw Column | JAC Raw Column | TUM value_id | Unit | Direct/Derived | Reliability | Evidence/Notes |
|-----------------|-----------------|----------------|--------------|------|----------------|-------------|----------------|
| `speed_kmh` | `speed` | `SPD` | `value_id=4` | km/h | Direct | High | All three have speed column; DEVRT: observed 0-116 km/h; JAC: 0-133 km/h; TUM: 0-254 km/h |
| `distance_km` | `cumul_dist` | `ODO` | `value_id=1299` | km | Direct | High | DEVRT: cumulative per row; JAC: odometer readings; TUM: traveled_distance |
| `battery_voltage_v` | (implied: Motor Pwr/w) | `VOL` | `value_id=1200` | V | Derived/UNVERIFIED | Medium (DEVRT)/Low (JAC)/High (TUM) | DEVRT: indirect; JAC: 0-379V likely raw ADC; TUM: 0-1000V direct pack voltage |
| `battery_current_a` | (implied) | `CUR` | `value_id=1205` | A | Derived/UNVERIFIED | Medium (DEVRT)/Medium (JAC)/High (TUM) | DEVRT: via Motor Pwr/w/V; JAC: -40 to 263A; TUM: 0-100A PTC current |
| `soc_pct` | `soc` | **NOT AVAILABLE** | `value_id=900` | % | Direct | High (DEVRT/TUM)/Very Low (JAC) | DEVRT: soc column %; TUM: hv_soc %; JAC: no SOC column |
| `soh_pct` | `soh` | **NOT AVAILABLE** | **NOT in 29** | % | Direct | High (DEVRT)/Very Low (TUM/JAC) | DEVRT: soh column %; TUM/JAC: not in inspected value_ids |
| `ambient_temperature_c` | `amb_temp` | **NOT temperature** (see AIR analysis) | `value_id=15` | °C | Direct (DEVRT/TUM)/Flag (JAC) | High (DEVRT/TUM)/High (JAC-as-flag) | DEVRT: amb_temp °C; TUM: value_id=15 °C; JAC: AIR is flag 0/2, not temp |
| `altitude_m` | `altitude`, `elv_spy` | `ALT` | (in JSON/histograms) | m | Direct (DEVRT)/Maybe (JAC) | High (DEVRT)/Medium (JAC) | DEVRT: altitude + elv_spy; JAC: ALT 0-1333m; TUM: in JSON data, not value_overview |
| `gradient_pct` | Derived (altitude/dist) | Derived (ALT/ODO) | Derived | % | Derived | Medium | Δalt/Δdistance × 100; requires altitude + distance from same dataset |
| `net_energy_consumption_kwh_per_km` | (SOC×cap)/cumul_dist | (SOC×cap)/ODO | (SOC×cap)/traveled_distance | kWh/km | Derived | Medium | See target derivation in respective analyses |
| `regen_energy_kwh` | Σ(regenwh × time_diff)/3600 | Derived from BRK+CUR | Derived from negative power | kWh | Derived | Medium (DEVRT)/Low (TUM)/Low (JAC) | DEVRT: regenwh column; TUM: negative hv_aux_power; JAC: BRK+CUR sign analysis |
| `timestamp` | `timestamp_data_utc` | Y/M/D/H/MIN/SEC | (from value timestamps) | UTC | Direct/Derived | High | DEVRT: ISO 8601; JAC: reconstruct from 6 int cols; TUM: from data timestamps |
| `vehicle_model` | `car_description` | (IEV40 implied) | (vehicle_id in data) | — | Direct | High | DEVRT: Dacia Spring/Nissan Leaf; JAC: IEV40; TUM: VW ID.3/CUPRA Born |
| `brake_intensity` | (regenwh sign) | `BRK` (unverified) | `hv_aux_power` sign | — | Derived/UNVERIFIED | Medium (DEVRT)/Low (JAC)/Medium (TUM) | DEVRT: regenwh < 0; JAC: BRK 0-28 unverified; TUM: aux_power sign |
| `accelerator_position` | (indirect) | `ACC` (unverified) | Not in 29 value_ids | — | UNVERIFIED | Low (DEVRT indirect)/Low (JAC) | DEVRT: no direct column; JAC: ACC 0-90 unverified |
| `eeco_mode` | (implicit) | `ECO` | Not explicitly mapped | Binary | Direct (JAC)/— | High (JAC)/— | JAC: ECO = 0 or 192 only |

## Key Mapping Decisions

### 1. SOC (State of Charge)
- **DEVRT**: `soc` column → `soc_pct` (direct, %)
- **TUM**: `value_id=900` (`hv_soc`) → `soc_pct` (direct, %)
- **JAC**: No SOC column → **UNVERIFIED / Not available**
- **Decision**: SOC available in DEVRT and TUM; JAC cannot provide SOC

### 2. Ambient Temperature
- **DEVRT**: `amb_temp` → `ambient_temperature_c` (direct, °C)
- **TUM**: `value_id=15` (`ambient_air_temp`) → `ambient_temperature_c` (direct, °C)
- **JAC**: `AIR` column → **NOT ambient temperature** (it's a flag 0/2)
- **Decision**: JAC AIR should be documented as sensor flag, not temperature. Either exclude or use as flag only.

### 3. Battery Voltage
- **DEVRT**: Indirect (via power observations, not direct voltage column)
- **TUM**: `value_id=1200` (`hv_battery_voltage`) → `battery_voltage_v` (direct, V)
- **JAC**: `VOL` → `battery_voltage_v` (UNVERIFIED, likely raw ADC, 0-379V)
- **Decision**: 
  - TUM: use `value_id=1200` directly
  - JAC: VOL should be treated as raw/unverified until scaling factor confirmed
  - DEVRT: no direct voltage column; infer from Motor Pwr/w observations

### 3. Speed
- **DEVRT**: `speed` → `speed_kmh` (direct, km/h)
- **JAC**: `SPD` → `speed_kmh` (direct, km/h)
- **TUM**: `value_id=4` (`vehicle_speed`) → `speed_kmh` (direct, km/h)
- **Decision**: All three have workable speed columns; use as-is

### 4. Distance/Odometer
- **DEVRT**: `cumul_dist` → `distance_km` (direct, km, cumulative per row)
- **JAC**: `ODO` → `distance_km` (direct, km, cumulative odometer)
- **TUM**: `value_id=1299` (`traveled_distance`) → `distance_km` (direct, km per segment)
- **Decision**: All three provide distance; use dataset-specific column names

### 5. Gradient
- **DEVRT**: Derive from `altitude` + `cumul_dist`: `gradient_pct = Δaltitude / Δcumul_dist × 100`
- **JAC**: Derive from `ALT` + `ODO`: `gradient_pct = ΔALT / ΔODO × 100` (but ODO may not be travel distance)
- **TUM**: Derive from JSON/histogram altitude + traveled_distance
- **Decision**: Gradient can be derived from altitude + distance, but requires same-dataset altitude and distance. Cross-dataset gradient comparison requires normalization.

### 6. Target Variable: net_energy_consumption_kwh_per_km
- **DEVRT**: Derive from `(soc_start - soc_end) × capacity_wh / 100 / cumul_dist_km`
- **TUM**: Derive from `(soc_start - soc_end) × 58000 / 100 / traveled_distance_km` (58 kWh fleet capacity)
- **JAC**: NOT reliably derivable (no SOC column)
- **Decision**: DEVRT and TUM can produce target; JAC cannot without SOC. DEVRT recommended for initial model training.

## Raw-to-Standard Mapping by Dataset

### DEVRT Raw Columns → Standard Concepts
| Raw Column | Standard Concept | Unit | Direct/Derived |
|------------|-----------------|------|----------------|
| `timestamp_data_utc` | `timestamp` | UTC | Direct |
| `car_id` | `vehicle_id` | — | Direct |
| `driver` | `driver_id` | — | Direct |
| `soc` | `soc_pct` | % | Direct |
| `soh` | `soh_pct` | % | Direct |
| `speed` | `speed_kmh` | km/h | Direct |
| `cumul_dist` | `distance_km` | km | Direct |
| `altitude` | `altitude_m` | m | Direct |
| `latitude` | `latitude` | deg | Direct |
| `longitude` | `longitude` | deg | Direct |
| `amb_temp` | `ambient_temperature_c` | °C | Direct |
| `regenwh` | `regen_energy_kwh` (derived) | kWh | Derived (Σ×time/3600) |
| `Motor Pwr(w)` | `motor_power_kw` (derived) | kW | Derived (W/1000) |
| `capacity` | `battery_capacity_kwh` | kWh | Direct (33000/62000 Wh) |
| `ref_consumption` | (baseline reference) | Wh/km | Not as target, use as reference |
| `regenwh` | `recovered_energy_kwh` (derived) | kWh | Derived |
| `Torque Nm` | `motor_torque_nm` | Nm | Direct |
| `rpm` | (engine speed) | RPM | Not in standard concept set |

### JAC Raw Columns → Standard Concepts
| Raw Column | Standard Concept | Unit | Direct/Derived | Confidence |
|------------|-----------------|------|----------------|------------|
| `SPD` | `speed_kmh` | km/h | Direct | High |
| `ODO` | `distance_km` | km | Direct | High |
| `LAT` | `latitude` | deg | Direct (valid range) | Medium |
| `LON` | `longitude` | deg | Direct (investigate 263 max) | Medium |
| `ALT` | `altitude_m` | m | Direct (reference frame?) | Medium |
| `CUR` | `battery_current_a` | A | Direct (raw) | Medium |
| `VOL` | `battery_voltage_v` | V | **UNVERIFIED** (likely raw ADC) | Low |
| `BRK` | `brake_intensity` | — | **UNVERIFIED** (not 0-100%) | Low |
| `ACC` | `accelerator_position` | — | **UNVERIFIED** (not 0-100%) | Low |
| `ECO` | `eeco_mode` | Binary | Direct (0/192) | High |
| `AIR` | (NOT ambient_temperature) | — | **Sensor flag** | High (as flag) |
| `AUT` | `automatic_mode` | — | **UNVERIFIED** | Low |
| `Y/M/D/H/MIN/SEC` | `timestamp` | UTC | **Derived** (reconstruct) | Medium |
| `AX/AY/AZ` | `acceleration_m/s2` (after /192) | m/s² | **Derived** (after scaling) | Medium |
| `GX/GY/GZ` | `gyro_rad/s` | raw | **UNVERIFIED** (needs sensor spec) | Low |
| `soc` | **NOT AVAILABLE** | — | Very Low | Very Low |
| `soh` | **NOT AVAILABLE** | — | Very Low | Very Low |

### TUM Raw Columns → Standard Concepts (from value_overview)
| value_id | Raw Concept | Standard Concept | Unit | Direct/Derived |
|----------|-------------|-----------------|------|----------------|
| `900` | `hv_soc` | `soc_pct` | % | Direct |
| `4` | `vehicle_speed` | `speed_kmh` | km/h | Direct |
| `1200` | `hv_battery_voltage` | `battery_voltage_v` | V | Direct |
| `1205` | `ptc1_current` | `battery_current_a` | A | Direct |
| `15` | `ambient_air_temp` | `ambient_temperature_c` | °C | Direct |
| `56` | `hv_aux_power` | `aux_power_kw` (derived) | kW | Direct (W/1000) |
| `1299` | `traveled_distance` | `distance_km` | km | Direct |
| `1291` | `track_duration` | `trip_duration_min` | min | Direct |
| `1290` | `hv_dod` | `dod_pct` | % | Direct (DOD = 100-SOC) |
| `1288` | `cell_c_rate` | `cell_c_rate_1_per_h` | 1/h | Direct |
| `1293-1295` | cell voltages | `cell_voltage_v` | V | Direct (0-5V per cell) |
| `1208-1209` | hv_temp_min/max | `battery_temp_c` | °C | Direct |
| `43` | `interior_temp` | `cabin_temp_c` | °C | Direct |
| `961/1265` | motor temps | `motor_temp_c` | °C | Direct |
| `1269/1272/1273` | coolant/battery temps | various | Direct |
| `1300/1301` | PTC power | `ptc_power_kw` (derived) | kW | Direct (W/1000) |
| `1289` | hv_temp_delta | `pack_temp_delta_c` | °C | Direct |
| `1302/1303` | c-rate peaks | `c_rate_peak_amps`, `c_rate_peak_freq` | 1/C, Hz | Direct |

## Unmappable Concepts (Not Available in Dataset)

| Concept | Reason | Dataset(s) Affected |
|---------|--------|--------------------|
| `soc_pct` | No SOC column | JAC |
| `soh_pct` | No SOH column | All three (DEVRT has it, TUM/JAC don't) |
| `humidity_pct` | No humidity sensor | All three |
| `wind_speed_kmh` | No wind speed in TUM/JAC | TUM/JAC (DEVRT has wind_kph/mph) |
| `vehicle_mass_kg` | No mass data | All three |
| `brake_pct` | BRK not 0-100% in JAC | JAC |
| `accelerator_pct` | ACC not 0-100% in JAC | JAC |
| `vehicle_mass_kg` | Nowhere available | All three |
| `gps_altitude_msl` | Altitude reference frame unknown | DEVRT/JAC (TUM in JSON only) |
| `drivetrain_type` | Not in data | All three |
| `tire_type` | Not in data | All three |

## Mapping Confidence Summary

| Concept | DEVRT | JAC | TUM | Overall |
|---------|-------|-----|-----|---------|
| `speed_kmh` | High | High | High | **High** |
| `distance_km` | High | High | High | **High** |
| `battery_voltage_v` | Medium | Low (UNVERIFIED) | High | **Medium** |
| `battery_current_a` | Medium | Medium | High | **Medium** |
| `soc_pct` | High | Very Low | High | **Medium** (2 of 3) |
| `soh_pct` | High | Very Low | Very Low | **Low** (1 of 3) |
| `ambient_temperature_c` | High | Low (is flag) | High | **Medium** (JAC needs reclassification) |
| `altitude_m` | High | Medium | Medium (JSON only) | **Medium** |
| `gradient_pct` | Derivable | Derivable | Derivable (JSON) | **Derivable** |
| `net_energy_consumption_kwh_per_km` | Derivable | Not derivable (no SOC) | Derivable | **Derivable (DEVRT/TUM)** |
| `timestamp` | High | Derived (6 cols) | High | **High** |
| `vehicle_model` | High | Implied | High | **High** |
| `eeco_mode` | (implicit) | High (0/192) | — | **High (JAC only)** |