# DEVRT Target Variable Analysis

## ref_consumption

### Exact Meaning
According to the DEVRT README:
> `ref_consumption (Wh/km): Reference consumption of the vehicle.`

### Exact Unit
- **Wh/km** (watt-hours per kilometer)
- Confirmed from README column description

### Whether Measured or Calculated
- **Reference/calculated value** - not directly measured per-sample
- The README describes it as "Reference consumption of the vehicle"
- It is constant per trip/file (does not vary row-by-row)
- Value is specific to each vehicle type:
  - Dacia Spring: 139 Wh/km
  - Nissan Leaf: 174 Wh/km

### Whether Instantaneous or Trip-Level
- **Trip-level** - constant across all rows within a CSV file/trip
- Does not vary with speed, power, SOC, or other per-sample measurements
- Appears to be a baseline/expected consumption for the specific route

### Suitable as ML Target
- **Partially suitable** as a baseline reference, but NOT as a measured actual consumption target
- Represents the *expected* or *reference* consumption, not the *actual* energy consumed
- Could be used as:
  - A baseline/reference target for model comparison
  - A normalization factor
  - NOT for predicting actual energy consumption (it's a constant, not variable data)

### Unit Interpretation (Wh/km)
- **Watt-hours per kilometer** = energy consumed per unit distance
- If actual consumption were tracked: Wh traveled / km driven
- But since ref_consumption is constant, it represents a *reference* or *baseline* value, not measured actuals

### Derivation from Other Variables
Can calculate actual energy consumption from:
```
energy_consumed_wh = (soc_initial - soc_final) × capacity_wh / 100
energy_consumed_kwh_per_km = energy_consumed_wh / cumul_dist_km
```
Or from power integration:
```
energy_consumed_wh = Σ (Motor Pwr(w) × time_diff_s) / 3600  # convert W·s to Wh
energy_consumed_kwh_per_km = energy_consumed_wh / cumul_dist_km
```

### Conclusion
- **ref_consumption = reference baseline consumption in Wh/km**
- Constant per trip, specific to vehicle type (139 for Dacia Spring, 174 for Nissan Leaf)
- NOT suitable as the primary ML target for actual energy consumption prediction
- CAN be used as a reference/baseline for model evaluation
- Actual energy consumption should be derived from SOC × capacity / distance or power × time / distance

## regenwh

### Exact Meaning
According to the DEVRT README:
> `regenwh (W): Regeneration power.`

### Exact Unit
- **W** (Watts) - instantaneous power, NOT energy (Wh)
- The column name "regenwh" is misleading (suggests "regenerative Wh") but the unit is W

### Whether Cumulative or Instantaneous
- **Instantaneous** - varies per row/sample
- Different from what the name "wh" might suggest

### Whether It Resets at Trip Start
- Yes - each CSV file/trip has its own regenwh values
- Not cumulative across trips

### Whether Represents Regenerative Energy
- **Partially** - represents regenerative *power* (W), not *energy* (Wh)
- Negative values indicate energy flowing back to the battery during regenerative braking
- The actual *recovered energy* would require: Σ(regenwh × time_diff) / 3600 = Wh

### Can Be Used to Derive Regenerative Energy Per km
- **Yes**, with proper unit conversion:
  ```
  recovered_energy_wh = Σ (regenwh × time_diff_s) / 3600
  recovered_energy_kwh_per_km = recovered_energy_wh / cumul_dist_km
  ```
- Note: time_diff column exists in DEVRT data (difference between vehicle timestamp and GPS timestamp in ms)

### Whether Measured Directly or Calculated
- The README says "Regeneration power" in W
- Likely calculated from motor power sign changes or battery current direction during braking
- Not a direct energy meter but a power signal that can be integrated to energy

### Summary
- `regenwh` = instantaneous regenerative power in **Watts (W)**
- Negative values = regenerative braking (energy returning to battery)
- Name "regenwh" is misleading - suggests Wh but unit is W
- Can be integrated to recover energy: Σ(regenwh × time_diff) / 3600 = Wh
- Can derive regen energy per km: Σ(regenwh × time_diff) / 3600 / cumul_dist = kWh/km
- Available in Nissan Leaf DEVRT files but ALL NaN in Dacia Spring files (variable availability)

## DEVRT Energy Variables Analysis

### Motor Pwr(w)
- **Unit**: W (Watts) - instantaneous motor power
- **Availability**: Present in Nissan Leaf files, ALL NaN in Dacia Spring files
- **Range**: 0-33760 W (33.76 kW) in Nissan Leaf
- **Sign**: 
  - Positive = motoring (energy consumed from battery)
  - Negative potential for regeneration (observed in regenwh, but Motor Pwr(w) was all ≥0 in Nissan Leaf sample)
- **Energy calculation**:
  ```
  motor_energy_wh = Σ (Motor Pwr(w) × time_diff_s) / 3600
  motor_energy_kwh = motor_energy_wh / 1000
  motor_energy_kwh_per_km = motor_energy_wh / cumul_dist_km / 1000
  ```

### Aux Pwr(100w)
- **Unit**: The column name suggests "Auxiliary Power in units of 100W"
- **Values**: Constant 2 across all observed rows
- **Actual power**: 2 × 100 = 200 W auxiliary power
- **Purpose**: Powers vehicle accessories (lights, climate control, electronics)
- **Energy calculation**:
  ```
  aux_energy_wh = 200W × total_trip_time_s / 3600 × 1000... 
  # Actually: 200W × time_s / 3600 = Wh (but 200/3600 × time_s)
  ```

### Capacity
- **Unit**: Wh (watt-hours)
- **Dacia Spring**: 33000 Wh = 33 kWh
- **Nissan Leaf**: 62000 Wh = 62 kWh
- **Usage**: SOC calculation: `energy_from_soc = (soc_initial - soc_final) × capacity / 100` = Wh

### SOC (State of Charge)
- **Unit**: %
- **Range**: 
  - Dacia Spring: 64-81% (one file sample), multiple unique values across files
  - Nissan Leaf: 77-87% (one file sample), 11 unique values
- **Per-file variation**: SOC changes across a trip, indicating energy consumption
- **Energy calculation**:
  ```
  energy_from_soc_change_wh = (soc_start - soc_end) × capacity_wh / 100
  energy_from_soc_change_kwh = energy_from_soc_change_wh / 1000
  net_energy_consumption_kwh_per_km = energy_from_soc_change_kwh / cumul_dist_km
  ```
- **High reliability** for energy consumption calculation when combined with capacity

### Cumul_dist
- **Unit**: km (kilometers)
- **Range**: 0 to trip-end distance (e.g., 34.29 km for Dacia, 34.07 km for Nissan Leaf)
- **Behavior**: Cumulative - starts at 0, increases monotonically per row
- **Usage**: Distance denominator for per-km calculations
- **Energy per km**: `energy_wh / cumul_dist_km` or `power_w × time_s / cumul_dist_km`

### Target Derivation Summary
**Net energy consumption per km can be calculated from DEVRT as:**

**Method 1 - SOC-based (higher reliability):**
```
energy_wh = (soc_start - soc_end) × capacity_wh / 100
energy_kwh = energy_wh / 1000
net_consumption_kwh_per_km = energy_kwh / cumul_dist_km
```

**Method 2 - Power-based (medium reliability):**
```
energy_wh = Σ (Motor Pwr(w) × time_diff_s) / 3600
energy_kwh = energy_wh / 1000
net_consumption_kwh_per_km = energy_kwh / cumul_dist_km
```

**Method 3 - Reference-based (baseline only):**
- Use ref_consumption as baseline/reference, not actual measurement
- 139 Wh/km (Dacia Spring) or 174 Wh/km (Nissan Leaf)

**Recommended target**: `net_energy_consumption_kwh_per_km` derived from SOC × capacity / distance