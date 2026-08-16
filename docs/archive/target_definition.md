# Primary Target Definition

## Recommended Primary Target: `net_energy_consumption_kwh_per_km`

### Why This Target?

The primary ML target predicts **net energy consumption per kilometer** in kilowatt-hours (kWh/km). This represents the energy drawn from the battery per kilometer of travel, accounting for both consumption and regeneration.

### Derivation from Datasets

#### DEVRT Derivation (RECOMMENDED for initial training)
```
Step 1: Identify trip start and end SOC
  soc_start = soc at first row of trip (earliest timestamp_data_utc)
  soc_end   = soc at last row of trip (latest timestamp_data_utc)

Step 2: Get battery capacity
  DEVRT Dacia Spring: capacity = 33000 Wh (33 kWh)
  DEVRT Nissan Leaf: capacity = 62000 Wh (62 kWh)

Step 3: Calculate energy consumed (Wh)
  energy_wh = (soc_start - soc_end) × capacity_wh / 100
  # Note: soc_start > soc_end for consumption (SOC decreases)
  # If soc_start < soc_end, energy is negative (regen > consumption)

Step 4: Convert to kWh
  energy_kwh = energy_wh / 1000

Step 5: Get total distance
  distance_km = cumul_dist at last row (trip end)

Step 6: Calculate net energy consumption per km
  net_consumption_kwh_per_km = energy_kwh / distance_km
```

**DEVRT Example** (from Nissan Leaf file sampled earlier):
- SOC range: 77-87% (11 unique values)
- Capacity: 62000 Wh
- If soc_start = 85%, soc_end = 78%: 
  - energy_wh = (85 - 78) × 62000 / 100 = 7 × 620 = 4340 Wh
  - energy_kwh = 4.34 kWh
- If cumul_dist final = 34.07 km:
  - net_consumption_kwh_per_km = 4.34 / 34.07 = 0.127 kWh/km = 127 Wh/km

#### TUM Derivation
```
Step 1: Identify track start and end SOC
  soc_start = hv_soc at first sample of track
  soc_end   = hv_soc at last sample of track

Step 2: Get fleet nominal capacity
  TUM fleet: 58 kWh net capacity (108s2p configuration)
  Per-vehicle: may vary (2 ID.3 + 5 Born, all 58 kWh)

Step 3: Calculate energy consumed (Wh)
  energy_wh = (soc_start - soc_end) × 58000 / 100

Step 4: Convert to kWh
  energy_kwh = energy_wh / 1000

Step 5: Get traveled distance
  distance_km = traveled_distance value_id=1299

Step 6: Calculate net energy consumption per km
  net_consumption_kwh_per_km = energy_kwh / distance_km
```

**TUM Note**: The SOC (value_id=900) has 5000ms sampling. The traveled_distance (value_id=1299) is 0-1000 km. May need per-trip filtering.

#### JAC Derivation (NOT RECOMMENDED - limited)
**Cannot reliably derive target** because:
- No SOC column in JAC IEV40 dataset
- No SOH column
- VOL (voltage) and CUR (current) have verification issues
- AIR is a flag, not temperature
- Without SOC, cannot use SOC×capacity/distance method

**Alternative JAC approach (if SOC were available)**:
```
energy_wh = (soc_start - soc_end) × capacity_wh / 100
```
But since SOC is not available, this cannot be computed from JAC data alone.

### Target Consistency Across Datasets

| Dataset | Can Produce `net_energy_consumption_kwh_per_km` | Method | Confidence |
|---------|-----------------------------------------------|--------|------------|
| DEVRT | ✓ | SOC × capacity / distance | High |
| TUM | ✓ | SOC × fleet_capacity / distance | High |
| JAC | ✗ | No SOC column available | Very Low |

### Recommended Training Strategy

Since the target cannot be consistently produced across ALL three datasets:

1. **DEVRT as initial training dataset** (primary training)
   - SOC available in every file
   - Capacity known per vehicle type (33 kWh or 62 kWh)
   - Reference consumption (`ref_consumption`) available as baseline
   - regen data (`regenwh`) available in Nissan Leaf files
   - 2 vehicle models provide some variability

2. **TUM as external validation dataset**
   - SOC available (value_id=900)
   - Different fleet (VW ID.3, CUPRA Born - 58 kWh)
   - Different geography (Germany vs. France for DEVRT)
   - Different driving conditions (validate generalizability)

3. **JAC as additional validation / domain adaptation**
   - Cannot produce target directly
   - May use for feature compatibility analysis only
   - Could derive SOC approximately from other signals (not recommended for target)
   - Useful for: verifying feature pipelines, checking for data leakage, assessing feature generalizability

4. **Secondary approach: Train on DEVRT + validate on TUM**
   - Best practice for multi-dataset projects
   - DEVRT: train model
   - TUM: evaluate model performance (R², MAE, RMSE on kWh/km)
   - JAC: assess feature compatibility, do not train

### Target Definition Document

```
Target Name: net_energy_consumption_kwh_per_km
Target Type: Regression (continuous value)
Target Unit: kWh per kilometer (kWh/km)
Target Description: 
  Net energy consumed from the battery per kilometer of travel.
  Positive values indicate energy consumption (drawn from battery).
  Negative values indicate net energy recovery (more regen than consumption).
  Calculated as: (SOC_start - SOC_end) × Battery_Capacity_Wh / 100 / Traveled_Distance_km

Calculation Formula:
  net_energy_consumption_kwh_per_km = 
    ( (soc_start_pct - soc_end_pct) × battery_capacity_wh / 100 ) / 1000 
    ÷ traveled_distance_km

  = (soc_start_pct - soc_end_pct) × battery_capacity_kwh / traveled_distance_km

Where:
  - soc_start_pct: State of Charge at trip start, in percentage (0-100)
  - soc_end_pct:   State of Charge at trip end,   in percentage (0-100)
  - battery_capacity_wh:  Battery capacity in watt-hours (e.g., 33000, 62000, 58000)
  - traveled_distance_km: Total distance traveled during the trip, in kilometers

Constraints:
  - soc_start_pct must be > soc_end_pfor valid consumption (positive target)
  - If soc_start_pct <= soc_end_pct, target is 0 or negative (regeneration dominant)
  - Requires known battery capacity (per dataset or fleet specification)
  - Distance must be non-zero (denominator constraint)
```

### Why Not Other Potential Targets?

1. **`gross_energy_consumption_kwh_per_km`**: Would include both consumption AND regeneration without subtraction. Less interpretable for range prediction.

2. **`energy_consumed_kwh`**: Absolute energy consumed, but not normalized by distance. Would require separate distance feature for per-km comparison.

3. **`soc_change_pct`**: Not normalized by distance or capacity. Different trips/batteries have different SOC ranges, making comparison difficult.

4. **`regen_energy_kwh_per_km`**: Only regeneration, not net consumption. Not the primary goal (we want to predict range, not just regen).

5. **`battery_power_kw`**: Power, not energy. Different from energy consumption (power is instantaneous, energy is integrated over time).

### Final Recommendation

**Primary target: `net_energy_consumption_kwh_per_km`**

- Derivable from DEVRT and TUM datasets
- Directly relevant to EV range prediction (energy per distance)
- Standard unit in EV literature (kWh/km)
- Enables comparison across datasets (DEVRT + TUM)
- JAC cannot produce this target without SOC (use for feature analysis only)

**Training strategy**:
1. Train initial models on DEVRT dataset
2. Validate on TUM dataset (external validation)
3. Assess JAC feature compatibility (do not train on JAC target)
4. Consider transfer learning or domain adaptation for multi-dataset modeling

**Next step**: Proceed to dataset-specific parsing and data cleaning (Step 4), using DEVRT as the primary dataset for target creation and model training initiation.