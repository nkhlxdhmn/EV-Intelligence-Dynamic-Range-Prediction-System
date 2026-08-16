# TUM EV UDS Dataset Value Overview Analysis

## Dataset Overview
- **Source**: Technische Universität München (TUM) - Institute of Automotive Technology
- **Fleet**: 7 vehicles (2 VW ID.3 Pro Performance 2020, 5 CUPRA Born 2022)
- **Battery**: 58 kWh net capacity, 108s2p configuration (9 modules, 216 cells)
- **Data Collection**: Unified Diagnostic Services (UDS) over OBD-II interface
- **License**: CC BY-NC 4.0
- **Total Distance**: >72,000 km across fleet
- **Value Overview**: 29 variables in value_overview.csv

## Key Variables Identified

### 1. SOC (State of Charge) - value_id=900
- **Original Name**: `Ladezustand`
- **Standard Concept**: `hv_soc` (State of Charge)
- **English Name**: State of Charge
- **Unit**: %
- **Range**: 0.0 - 100.0%
- **Sampling Interval**: 5000 ms (5 seconds)
- **Vehicle(s)**: All 7 fleet vehicles (CUP1-CUP5, ID1-ID2)
- **Notes**: The ONLY SOC variable in the 29-value overview. Critical for energy consumption calculation. DOD (value_id=1290) is also available as 100-SOC.

### 2. Vehicle Speed - value_id=4
- **Original Name**: `Geschwindigkeit`
- **Standard Concept**: `vehicle_speed`
- **English Name**: Vehicle speed
- **Unit**: km/h
- **Range**: 0.0 - 254.0 km/h
- **Sampling Interval**: 200 ms (very high frequency - 5 Hz)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Highest frequency signal in the overview. Most frequently sampled measurement. Direct speed measurement. Used for speed profiles and acceleration calculation.

### 3. Battery Pack Voltage - value_id=1200
- **Original Name**: `Packspannung`
- **Standard Concept**: `hv_battery_voltage`
- **English Name**: Pack voltage
- **Unit**: V (Volts)
- **Range**: 0.0 - 1000.0 V
- **Sampling Interval**: 200 ms (same high frequency as speed)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: High voltage battery pack voltage. 200ms sampling enables power calculation (P = V × I). Range 0-1000V is consistent with 400-800V EV battery packs.

### 4. PTC1 Current - value_id=1205
- **Original Name**: `PTC1 Strom`
- **Standard Concept**: `ptc1_current`
- **English Name**: PTC1 current
- **Unit**: A (Amperes)
- **Range**: 0.0 - 100.0 A
- **Sampling Interval**: 1000 ms (1 second)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: PTC (Positive Temperature Coefficient) heater circuit 1 current. Used for auxiliary power analysis. Current limited to 100A in measurement range.

### 5. PTC2 Current - value_id=1206
- **Original Name**: `PTC2 Strom`
- **Standard Concept**: `ptc2_current`
- **English Name**: PTC2 current
- **Unit**: A (Amperes)
- **Range**: 0.0 - 100.0 A
- **Sampling Interval**: 1000 ms (1 second)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: PTC heater circuit 2 current. Same as PTC1 but for second circuit.

### 6. Ambient Air Temperature - value_id=15
- **Original Name**: `Umgebungslufttemperatur`
- **Standard Concept**: `ambient_air_temp`
- **English Name**: Ambient air temperature
- **Unit**: °C (Celsius)
- **Range**: -40.0 - 215.0 °C
- **Sampling Interval**: 10000 ms (10 seconds - lowest frequency)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Widest range of any temperature sensor (-40 to 215°C). -40°C is extreme cold threshold. 215°C is very high (possibly includes sensor error margin or hot climate). 10s sampling is lowest frequency in overview.

### 7. HV Aux Power - value_id=56
- **Original Name**: `Leistung HV Nebenverbraucher`
- **Standard Concept**: `hv_aux_power`
- **English Name**: High voltage auxiliary power
- **Unit**: W (Watts)
- **Range**: -20000.0 - 20000.0 W (can be negative)
- **Sampling Interval**: 1000 ms (1 second)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Can be negative (regenerative mode or power feedback). Range ±20kW covers typical auxiliary loads. Important for net energy consumption calculation.

### 8. PTC1 Power - value_id=1300
- **Original Name**: `PTC1 Leistung`
- **Standard Concept**: `ptc1_power`
- **English Name**: PTC1 power
- **Unit**: W (Watts)
- **Range**: 0.0 - 10000.0 W
- **Sampling Interval**: NaN (not specified in value_overview)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: PTC heater power. Non-negative (0 to 10kW). Sampling interval not documented in value_overview.

### 9. PTC2 Power - value_id=1301
- **Original Name**: `PTC2 Leistung`
- **Standard Concept**: `ptc2_power`
- **English Name**: PTC2 power
- **Unit**: W (Watts)
- **Range**: 0.0 - 10000.0 W
- **Sampling Interval**: NaN (not specified in value_overview)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Same as PTC1 but for second circuit.

### 10. DOD (Depth of Discharge) - value_id=1290
- **Original Name**: `Entladetiefe (DOD)`
- **Standard Concept**: `hv_dod`
- **English Name**: Depth of Discharge
- **Unit**: %
- **Range**: 0.0 - 100.0%
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: DOD = 100 - SOC. Alternative way to represent battery state. Can be used interchangeably with SOC for energy consumption calculation.

### 11. Track Duration - value_id=1291
- **Original Name**: `Fahrtdauer`
- **Standard Concept**: `track_duration`
- **English Name**: Track/trip duration
- **Unit**: min (minutes)
- **Range**: 0.0 - 720.0 min (0 to 12 hours)
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Duration of driving track/trip. Can be used with speed to calculate distance: `distance = speed × duration`.

### 12. Idle Period Duration - value_id=1292
- **Original Name**: `Ruhezeit`
- **Standard Concept**: `idle_period_duration`
- **English Name**: Idle period duration
- **Unit**: min (minutes)
- **Range**: 0.0 - 525600.0 min (0 to 364 days!)
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Very wide range suggests this may include parking periods, not just driving idle. 525600 min = 365 days. May need filtering for driving-only analysis.

### 13. Traveled Distance - value_id=1299
- **Original Name**: `Zurückgelegte Strecke`
- **Standard Concept**: `traveled_distance`
- **English Name**: Traveled distance
- **Unit**: km (kilometers)
- **Range**: 0.0 - 1000.0 km
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Distance traveled per trip/segment. Can be used with speed and duration: `distance = average_speed × duration`.

### 14. Cell C-Rate - value_id=1288
- **Original Name**: `Zell C-Rate`
- **Standard Concept**: `cell_c_rate`
- **English Name**: Cell C-rate
- **Unit**: 1/h (per hour)
- **Range**: -100.0 - 100.0 1/h
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: 
  - Negative values = charging (energy going into battery)
  - Positive values = discharging (energy going out of battery)
  - C-rate = current / nominal capacity. 1C = full capacity in 1 hour.
  - Critical for understanding charge/discharge rates.

### 15. C-Rate Peak Frequency - value_id=1303
- **Original Name**: `Frequenz der Zell-C-Raten-Peaks`
- **Standard Concept**: `cell_c_rate_peak_freq`
- **English Name**: Frequency of cell C-rate peaks
- **Unit**: Hz (Hertz)
- **Range**: 0.0 - 5.0 Hz
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Peaks in C-rate signal. May indicate rapid charge/discharge events. 5Hz = 5 peaks per second.

### 16. C-Rate Peak Amplitude - value_id=1302
- **Original Name**: `Amplitude der Zell-C-Raten-Peaks`
- **Standard Concept**: `cell_c_rate_peak_ampl`
- **English Name**: Amplitude of cell C-rate peaks
- **Unit**: 1/C (inverse capacity)
- **Range**: 0.0 - 10.0 1/C
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Magnitude of C-rate peaks. Related to fast charge/discharge events.

### 17. Cell Voltage Max - value_id=1293
- **Original Name**: `Zellspannung max`
- **Standard Concept**: `cell_voltage_max`
- **English Name**: Cell voltage maximum
- **Unit**: V (Volts)
- **Range**: 0.0 - 5.0 V
- **Sampling Interval**: 1000 ms
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Maximum cell voltage in the pack. 0-5V suggests individual cell voltage (cells in series increase pack voltage, but individual cells are ~3.6-3.8V each). 5V max may indicate 2-cell series or ADC reference.

### 18. Cell Voltage Min - value_id=1294
- **Original Name**: `Zellspannung min`
- **Standard Concept**: `cell_voltage_min`
- **English Name**: Cell voltage minimum
- **Unit**: V (Volts)
- **Range**: 0.0 - 5.0 V
- **Sampling Interval**: 1000 ms
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Minimum cell voltage. Same range as cell_voltage_max. Used for cell balance monitoring: `cell_voltage_delta = cell_voltage_max - cell_voltage_min`.

### 19. Cell Voltage Delta - value_id=1295
- **Original Name**: `Max. Zellspannungsdifferenz`
- **Standard Concept**: `cell_voltage_delta`
- **English Name**: Cell voltage difference maximum
- **Unit**: V (Volts)
- **Range**: 0.0 - 5.0 V
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: `delta = max - min`. Indicates cell voltage imbalance. Large delta suggests need for cell balancing.

### 20. HV Temperature Min - value_id=1208
- **Original Name**: `Pack Temp. Min.`
- **Standard Concept**: `hv_temp_min`
- **English Name**: HV battery temperature min
- **Unit**: °C (Celsius)
- **Range**: -40.0 - 100.0 °C
- **Sampling Interval**: 10000 ms (10 seconds)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Minimum battery pack temperature over sampling period. -40°C extreme cold, 100°C overheard threshold.

### 21. HV Temperature Max - value_id=1209
- **Original Name**: `Pack Temp. Max.`
- **Standard Concept**: `hv_temp_max`
- **English Name**: HV battery temperature max
- **Unit**: °C (Celsius)
- **Range**: -40.0 - 100.0 °C
- **Sampling Interval**: 10000 ms (10 seconds)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Maximum battery pack temperature. Same range as temp min. Used for thermal management monitoring.

### 22. Interior Temperature - value_id=43
- **Original Name**: `Innenraumtemperatur`
- **Standard Concept**: `interior_temp`
- **English Name**: Interior/cabin temperature
- **Unit**: °C (Celsius)
- **Range**: -100.0 - 100.0 °C (unusual range)
- **Sampling Interval**: 10000 ms (10 seconds)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Unusual range (-100 to 100°C). -100°C is physically impossible for cabin. May include error codes or sensor fault states along with real temperatures.

### 23. Rear Motor Stator Temp - value_id=961
- **Original Name**: `Temp. Stator (Hinterachse)`
- **Standard Concept**: `temp_rear_motor_stator`
- **English Name**: Rear motor stator temperature
- **Unit**: °C (Celsius)
- **Range**: -20.0 - 250.0 °C
- **Sampling Interval**: 5000 ms (5 seconds)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Motor winding temperature. 250°C is very high (near overheating threshold). 5s sampling more frequent than battery temps (10s).

### 24. Rear Motor Rotor Temp - value_id=1265
- **Original Name**: `Rotortemperatur Hinten`
- **Standard Concept**: `rear_motor_rotor_temp`
- **English Name**: Rear motor rotor temperature
- **Unit**: °C (Celsius)
- **Range**: -40.0 - 250.0 °C
- **Sampling Interval**: 5000 ms (5 seconds)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Rotor temperature. Same range as stator temp (-20 to 250°C). Both indicate high-temperature monitoring capability.

### 25. Coolant Temperature Inverter Inlet - value_id=1269
- **Original Name**: `Kühlmitteltemperatur Inverter Einlass`
- **Standard Concept**: `coolant_temp_inverter_inlet`
- **English Name**: Coolant temperature inverter inlet
- **Unit**: °C (Celsius)
- **Range**: -40.0 - 200.0 °C
- **Sampling Interval**: 5000 ms (5 seconds)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Inverter coolant inlet temperature. Critical for inverter thermal management. 200°C max indicates high-power operation.

### 26. Battery Pack Inlet Temp - value_id=1272
- **Original Name**: `Temperatur HV Pack Einlass`
- **Standard Concept**: `hv_battery_temp_inlet`
- **English Name**: HV battery pack inlet temperature
- **Unit**: °C (Celsius)
- **Range**: -40.0 - 200.0 °C
- **Sampling Interval**: 5000 ms (5 seconds)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Battery pack cooling inlet temperature. Same range as inverter coolant. Used for pack thermal management.

### 27. Battery Pack Outlet Temp - value_id=1273
- **Original Name**: `Temperatur HV Pack Auslass`
- **Standard Concept**: `hv_battery_temp_outlet`
- **English Name**: HV battery pack outlet temperature
- **Unit**: °C (Celsius)
- **Range**: -40.0 - 200.0 °C
- **Sampling Interval**: 5000 ms (5 seconds)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Battery pack cooling outlet temperature. Delta between inlet and outlet indicates heat extraction capacity.

### 28. Temperature Delta - value_id=1289
- **Original Name**: `Pack Max. Temperaturdifferenz`
- **Standard Concept**: `hv_temp_delta`
- **English Name**: HV temperature difference maximum
- **Unit**: °C (Celsius)
- **Range**: 0.0 - 100.0 °C
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Maximum temperature difference within pack. Used for thermal gradient monitoring and balance assessment.

### 29. Cell C-Rate Peak Amplitude - value_id=1302
- **Original Name**: `Amplitude der Zell-C-Raten-Peaks`
- **Standard Concept**: `cell_c_rate_peak_ampl`
- **English Name**: Amplitude of cell C-rate peaks
- **Unit**: 1/C (inverse capacity)
- **Range**: 0.0 - 10.0 1/C
- **Sampling Interval**: NaN (not specified)
- **Vehicle(s)**: All fleet vehicles
- **Notes**: Peak magnitude of C-rate events. Related to 1303 (frequency).

## TUM Energy Signals Analysis

### Battery Power Signals
1. **hv_battery_voltage (value_id=1200) × ptc1_current (value_id=1205)**:
   - Power = V × I = battery instantaneous power
   - Voltage range: 0-1000V, Current range: 0-100A
   - Power range: 0-100,000 W (0-100 kW)
   - Sampling: both at 200ms/1000ms
   - **Formula**: `battery_power_w = hv_battery_voltage × ptc1_current`

2. **hv_aux_power (value_id=56)**:
   - Direct power measurement: -20kW to 20kW
   - Already in Watts
   - Can be negative (regenerative or feedback)
   - **Formula**: Direct use as `aux_power_w = hv_aux_power`

3. **PTC1/PTC2 Power (value_ids 1300, 1301)**:
   - PTC heater power: 0-10kW each
   - Likely always non-negative (heater power consumption)
   - **Formula**: Direct use as `ptc_power_w = ptc1_power` or `ptc2_power`

### Battery Energy Consumption
**From SOC change (most reliable)**:
```
energy_wh = (soc_start - soc_end) × capacity_wh / 100
energy_kwh = energy_wh / 1000
```
- SOC available at 5s sampling (value_id=900)
- Capacity: 58 kWh net (fleet specification)
- More precise: per-vehicle capacity from fleet data

From power integration:
```
energy_wh = Σ (battery_power_w × sample_interval_s) 
energy_kwh = energy_wh / 1000
```
- Battery power = hv_battery_voltage × ptc1_current
- Sample interval varies (200ms, 1000ms, 5000ms, 10000ms)
- Must weight by actual sampling interval

From DOD change (alternative):
```
energy_wh = (dod_start - dod_end) × capacity_wh / 100
```
- DOD available (value_id=1290)
- Same formula as SOC method

### Regenerative Energy
**From power sign analysis**:
```
# Negative battery power = regenerative energy
# hv_aux_power can be negative (range: -20000 to 20000W)
regen_energy_wh = Σ (hv_aux_power × sample_interval_s) for hv_aux_power < 0
regen_energy_kwh = regen_energy_wh / 1000
```

**From C-rate analysis**:
```
# Negative cell_c_rate (value_id=1288) = charging/discharging
# Energy from C-rate: E = capacity × ΔSOC = capacity × (C_rate × Δt)
# More complex: requires integration over time
```

**From cell voltage delta analysis**:
- Not direct regeneration indicator
- Cell voltage delta indicates imbalance, not energy flow direction

### Net Energy Consumption
**Primary formula (SOC-based, most reliable)**:
```
net_energy_consumption_wh = (soc_start - soc_end) × capacity_wh / 100
net_energy_consumption_kwh = net_energy_consumption_wh / 1000
net_energy_consumption_kwh_per_km = net_energy_consumption_kwh / traveled_distance_km
```

**Alternative formula (power-based)**:
```
# Sum all power signals × their sampling intervals
# Include: battery power, aux power, motor power (if available)
# Subtract regen (negative power periods)
# Divide by distance traveled

net_energy_kwh = Σ (power_w × interval_s) / 3600  # Wh to kWh
net_energy_kwh_per_km = net_energy_kwh / distance_km
```

### Distance Signals
1. **traveled_distance (value_id=1299)**: 0-1000 km, direct distance
2. **track_duration (value_id=1291)**: in minutes, combine with speed for distance
3. **ODOMETER equivalent**: Not explicitly in 29 value_ids, but traveled_distance serves same purpose

### GPS/Terrain Signals
**NOT in the 29 value_overview variables**. GPS coordinates, altitude, and terrain data would be in:
- JSON track histograms (separate data structure)
- Parquet UDS data files (full raw measurements)
- May require accessing the raw UDS data files rather than the summary value_overview

### Environment Signals
1. **ambient_air_temp (value_id=15)**: -40 to 215°C, 10s sampling
2. **No humidity variable** in the 29 value_ids
3. **No weather condition variable** in the 29 value_ids

### TUM Summary Table: Available Signals for Energy Calculation

| Signal Type | Available | value_id | Unit | Sampling | Formula/Usage |
|-------------|-----------|----------|------|----------|---------------|
| Battery voltage | ✓ | 1200 | V | 200ms | P = V × I |
| Battery current | ✓ | 1205 | A | 1000ms | P = V × I |
| SOC | ✓ | 900 | % | 5000ms | E = ΔSOC × capacity |
| DOD | ✓ | 1290 | % | NaN | E = ΔDOD × capacity |
| Aux power | ✓ | 56 | W | 1000ms | Direct, can be negative |
| PTC power | ✓ | 1300/1301 | W | NaN/10000ms | Heater power only |
| Ambient temp | ✓ | 15 | °C | 10000ms | Environmental factor |
| Traveled distance | ✓ | 1299 | km | NaN | Denominator for kWh/km |
| Track duration | ✓ | 1291 | min | NaN | Duration for integration |
| C-rate | ✓ | 1288 | 1/h | NaN | Charge/discharge rate |
| Cell voltages | ✓ | 1293-1295 | V | 1000ms | Cell-level monitoring |
| Battery temp min/max | ✓ | 1208-1209 | °C | 10000ms | Thermal management |
| Interior temp | ✓ | 43 | °C | 10000ms | Cabin environment |

### TUM Energy Calculation Formulas

**Formula 1: SOC-based energy consumption (RECOMMENDED)**
```
1. Extract SOC start/end: soc_start = hv_soc at trip start, soc_end = hv_soc at trip end
2. Get capacity: 58 kWh = 58000 Wh (fleet nominal), or per-vehicle from documentation
3. Calculate: energy_wh = (soc_start - soc_end) × 58000 / 100
4. Calculate: energy_kwh = energy_wh / 1000
5. Get distance: traveled_distance_km
6. Calculate: net_consumption_kwh_per_km = energy_kwh / traveled_distance_km
```

**Formula 2: Power integration (alternative)**
```
1. Get battery power: battery_power_w = hv_battery_voltage × ptc1_current
2. For each sample: energy_wh_sample = battery_power_w × (sampling_interval_ms / 1000) / 3600
   # Wait: W × s = J, not Wh. Correct:
   # W × s = J (Joules), Wh = W × h = W × s / 3600
   # So: energy_wh = Σ (battery_power_w × sampling_interval_s) / 3600
3. Sum across all samples in trip
4. Get distance: traveled_distance_km
5. Calculate: net_consumption_kwh_per_km = net_energy_kwh / traveled_distance_km
```

**Formula 3: Aux power integration**
```
1. Get aux power: aux_power_w = hv_aux_power (can be negative for regen)
2. For each sample: energy_wh = aux_power_w × (sampling_interval_s / 3600)
3. Sum across all samples (positive = consumption, negative = regen)
4. Get distance: traveled_distance_km
5. Calculate: net_consumption_kwh_per_km = net_energy_kwh / traveled_distance_km
   # This will include both consumption and regeneration
   # To get NET: positive net = consumption, negative net = regen overall
```