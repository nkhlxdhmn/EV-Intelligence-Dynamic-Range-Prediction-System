# Feature Preparation Guide

## Overview

This document describes feature preparation strategies for ML modeling, including:
- Feature overview and completeness
- Missing value analysis
- Vehicle-specific feature handling
- Recommended feature sets
- Feature types (numeric vs categorical)

## Dataset Information

**Source:** `data/processed/{train|validation|test}.parquet`

**Total Features:** 15 (excluding sample identifiers)

**Loaded by:** `src/models/dataset.py` (DatasetLoader class)

## Feature Catalog

### Core Features (Always Available)

These features are **100% complete** and present in all splits.

#### 1. `current_soc_pct` (State of Charge)
- **Type:** Numeric (integer)
- **Range:** 0-100 %
- **Unit:** Percentage
- **Completeness:** 100% (9,952/9,952)
- **Description:** Battery state of charge at sample time
- **Quality:** ✓ High - no missing values
- **Recommendation:** ✓ Include in base model

#### 2. `battery_capacity_kwh` (Battery Capacity)
- **Type:** Numeric (float)
- **Range:** ~40-60 kWh
- **Unit:** Kilowatt-hours
- **Completeness:** 100% (9,952/9,952)
- **Description:** Battery capacity specific to vehicle model
- **Quality:** ✓ High - constant per vehicle
- **Note:** This is vehicle-specific, not time-varying
- **Recommendation:** ✓ Include (captures vehicle differences)

#### 3. `current_altitude_m` (Altitude)
- **Type:** Numeric (float)
- **Range:** -50 to 1200+ m
- **Unit:** Meters
- **Completeness:** 100% (9,952/9,952)
- **Description:** GPS altitude at current position
- **Quality:** ✓ High
- **Recommendation:** ✓ Include in base model

#### 4. `past_1km_gradient_pct` (Average Gradient)
- **Type:** Numeric (float)
- **Range:** -20 to +30 %
- **Unit:** Percentage
- **Completeness:** 100% (9,952/9,952)
- **Description:** Average road gradient over past 1 km
- **Quality:** ✓ High
- **Interpretation:** Positive = uphill (high energy), Negative = downhill (regeneration)
- **Recommendation:** ✓ Include in base model

#### 5. `terrain_class` (Terrain Classification)
- **Type:** Categorical (string)
- **Values:** 'urban', 'suburban', 'motorway', etc.
- **Completeness:** 100% (9,952/9,952)
- **Description:** Road type classification
- **Quality:** ✓ High
- **Recommendation:** ✓ Include (one-hot encode)

#### 6. `vehicle_model` (Vehicle Model)
- **Type:** Categorical (string)
- **Values:** 'Dacia Spring', 'Nissan Leaf'
- **Completeness:** 100% (9,952/9,952)
- **Description:** Vehicle model identifier
- **Quality:** ✓ High
- **Recommendation:** → Do NOT use in base model (already stratified)
- **Use Case:** Vehicle-specific model training only

### Vehicle-Specific Features (Partially Available)

These features are **only available for certain vehicles** or subsets of data.

#### 7. `current_speed_kmh` (Current Speed)
- **Type:** Numeric (float)
- **Unit:** km/h
- **Completeness:** 4,373/9,952 (44%)
- **Missing by:** Dacia Spring: ~100%, Nissan Leaf: ~12%
- **Description:** GPS-based current speed
- **Quality:** ⚠️ Medium - highly vehicle-specific missing
- **Note:** Dacia Spring essentially missing this feature
- **Recommendation:** 
  - ❌ Do NOT use in base model (too incomplete)
  - → Consider for vehicle-specific models
  - → Use missing indicator if including

#### 8. `current_ambient_temperature_c` (Ambient Temperature)
- **Type:** Numeric (float)
- **Unit:** °C
- **Completeness:** 4,373/9,952 (44%)
- **Missing by:** Same pattern as `current_speed_kmh`
- **Description:** Ambient air temperature at sample time
- **Quality:** ⚠️ Medium - vehicle-specific missing
- **Note:** May be correlated with Nissan Leaf data collection setup
- **Recommendation:**
  - ❌ Do NOT use in base model
  - → Vehicle-specific model only
  - → Likely correlated with time-of-day

#### 9. `current_motor_power_kw` (Motor Power)
- **Type:** Numeric (float)
- **Unit:** Kilowatts
- **Completeness:** 4,373/9,952 (44%)
- **Missing by:** Same pattern as above
- **Description:** Real-time motor power output (positive) or regeneration (negative)
- **Quality:** ⚠️ Medium - vehicle-specific missing
- **Note:** **CRITICAL:** Missing does NOT mean power = 0. It means data not available.
- **Warning:** ⚠️ **DO NOT FILL ZERO** - this is a measurement missing, not actual zero power
- **Recommendation:**
  - ❌ Do NOT use in base model
  - → Vehicle-specific model only
  - → Use missing indicator if needed

#### 10. `past_mean_speed_kmh` (Mean Speed Last 1 km)
- **Type:** Numeric (float)
- **Unit:** km/h
- **Completeness:** 4,348/9,952 (43.7%)
- **Missing by:** Same pattern as other speed-related features
- **Description:** Average speed over past 1 km
- **Quality:** ⚠️ Medium
- **Recommendation:**
  - ❌ Do NOT use in base model
  - → Vehicle-specific model only

#### 11. `past_speed_std` (Speed Std Dev Last 1 km)
- **Type:** Numeric (float)
- **Unit:** km/h
- **Completeness:** 4,373/9,952 (44%)
- **Description:** Standard deviation of speed over past 1 km
- **Quality:** ⚠️ Medium
- **Interpretation:** High std = variable driving, Low std = consistent speed
- **Recommendation:**
  - ❌ Do NOT use in base model
  - → Vehicle-specific model only

#### 12. `past_mean_acceleration_mps2` (Mean Acceleration)
- **Type:** Numeric (float)
- **Unit:** m/s²
- **Completeness:** 4,348/9,952 (43.7%)
- **Description:** Average acceleration over past 1 km
- **Quality:** ⚠️ Medium
- **Interpretation:** Positive = acceleration, Negative = braking/deceleration
- **Recommendation:**
  - ❌ Do NOT use in base model
  - → Vehicle-specific model only

### Target Variable

#### `target_future_energy_kwh_per_km` (Energy Consumption Target)
- **Type:** Numeric (float)
- **Unit:** kWh/km
- **Range:** -0.248 to 0.496
- **Completeness:** 100% (9,952/9,952)
- **Mean:** 0.151 kWh/km
- **Std:** 0.088 kWh/km
- **Description:** Energy consumption over next 5 km of trip
- **Quality:** ✓ High - no missing values
- **Note:** Negative values indicate net regeneration exceeding consumption

## Feature Completeness Summary

| Feature | Type | Complete | Vehicle Specific | Recommendation |
|---------|------|----------|------------------|-----------------|
| current_soc_pct | Numeric | 100% | No | ✓ Base model |
| battery_capacity_kwh | Numeric | 100% | Yes | ✓ Base model |
| current_altitude_m | Numeric | 100% | No | ✓ Base model |
| past_1km_gradient_pct | Numeric | 100% | No | ✓ Base model |
| terrain_class | Categorical | 100% | No | ✓ Base model |
| current_speed_kmh | Numeric | 44% | Yes | Vehicle-specific |
| current_ambient_temperature_c | Numeric | 44% | Yes | Vehicle-specific |
| current_motor_power_kw | Numeric | 44% | Yes | Vehicle-specific |
| past_mean_speed_kmh | Numeric | 44% | Yes | Vehicle-specific |
| past_speed_std | Numeric | 44% | Yes | Vehicle-specific |
| past_mean_acceleration_mps2 | Numeric | 44% | Yes | Vehicle-specific |

## Recommended Feature Sets

### Option 1: Base Model (Common Features) - RECOMMENDED

**Use Case:** First ML model, general EV energy prediction

**Features:**
- `current_soc_pct`
- `battery_capacity_kwh`
- `current_altitude_m`
- `past_1km_gradient_pct`
- `terrain_class` (one-hot encoded)

**Advantages:**
- ✓ 100% complete
- ✓ No missing value imputation needed
- ✓ Applicable to both vehicles
- ✓ Represents key energy consumption factors

**Expected Coverage:** 100% of samples

**Implementation:**
```python
from src.models.dataset import DatasetLoader, FEATURE_COLUMNS

loader = DatasetLoader(feature_columns=FEATURE_COLUMNS)
train = loader.load_train()  # Will have 5 features + target
```

### Option 2: Vehicle-Specific Features (Advanced)

**Use Case:** After base model, if exploring vehicle differences

**Strategy:**
- Train separate models for Dacia Spring and Nissan Leaf
- Include vehicle-specific features for each

**Dacia Spring Features:**
- Base model features
- Battery capacity (specific to Dacia)
- Any Dacia-specific features with >80% completeness

**Nissan Leaf Features:**
- Base model features
- All vehicle-specific features (speed, temperature, power, etc.)

**Note:** Requires significant feature engineering and missing value strategies.

### Option 3: Extended Model with Missing Indicators

**Use Case:** Single model with all data, using missingness as signal

**Strategy:**
- Include vehicle-specific features
- Create binary "is_missing" indicators
- Impute missing values with mean/median (NOT zero for power)

**Features:**
```
# Base features
current_soc_pct
battery_capacity_kwh
current_altitude_m
past_1km_gradient_pct
terrain_class

# Vehicle-specific with imputation
current_speed_kmh (median imputed)
current_ambient_temperature_c (median imputed)
current_motor_power_kw (median imputed)
past_mean_speed_kmh (median imputed)
past_speed_std (median imputed)
past_mean_acceleration_mps2 (median imputed)

# Missing indicators
is_speed_missing
is_temperature_missing
is_power_missing
...
```

**Challenges:**
- Loses real missingness information
- Assumes missing is random (it's not - vehicle-specific)
- May confuse model learning

**Not recommended for first iteration.**

## Missing Value Strategy

### DON'T DO THIS ❌

```python
# WRONG: Filling motor power with zero
df['current_motor_power_kw'] = df['current_motor_power_kw'].fillna(0)

# WRONG: This assumes no power = 0 kW, but missing means data not collected
# In reality, the vehicle WAS accelerating/consuming, but we don't know how much
```

### Options for Missing Values

**Option A: Drop Features (RECOMMENDED for base model)**
- Simply exclude vehicle-specific features
- Clean, no assumptions
- Works well for base model

**Option B: Drop Samples**
- Remove rows with missing values
- Reduces dataset size significantly
- Not recommended (44% data loss)

**Option C: Imputation with Domain Knowledge**
- Use vehicle-specific median/mean
- Works only if missingness is random (it's not)
- Consider tree-based models that handle missing naturally

**Option D: Missing Indicators**
- Include binary "is_missing" flag
- Let model learn from pattern
- Only if using Option C imputation

## Feature Engineering Opportunities

### Not to be done in this STEP

These are for future consideration:

1. **Interactions**
   - SOC × Altitude (battery state interacts with terrain)
   - Gradient × Speed (aggressive driving uphill)

2. **Time-based features**
   - Hour of day (captured in timestamp, but mostly missing)
   - Day of week
   - Season

3. **Trip aggregates**
   - Total trip distance so far
   - Average consumption so far
   - Trip start time characteristics

4. **Lagged features**
   - Previous sample's speed
   - Rolling averages
   - Momentum indicators

5. **Domain features**
   - "Is regeneration possible" (downhill + speed)
   - Efficiency potential
   - Battery thermal state

These should be considered in STEP 8+ after baseline models.

## Feature Implementation

### Loading with DatasetLoader

```python
from src.models.dataset import DatasetLoader

# Create loader with default features
loader = DatasetLoader(
    data_dir='data/processed',
    feature_columns=[
        'current_soc_pct',
        'battery_capacity_kwh', 
        'current_altitude_m',
        'past_1km_gradient_pct',
        'terrain_class'
    ],
    target_column='target_future_energy_kwh_per_km',
    include_ids=False,  # Don't load trip_id, vehicle_id, etc.
    verbose=True
)

# Load training data
train_X = loader.load_train(include_target=False)  # Features only
train_y = loader.load_train(include_target=True)['target_future_energy_kwh_per_km']

# Or load with target
train = loader.load_train(include_target=True)
X = train.drop('target_future_energy_kwh_per_km', axis=1)
y = train['target_future_energy_kwh_per_km']
```

### Categorical Encoding

For `terrain_class` and `vehicle_model`:

```python
import pandas as pd

# One-hot encoding
X = pd.get_dummies(X, columns=['terrain_class'], drop_first=True)

# Now X contains:
# - current_soc_pct
# - battery_capacity_kwh
# - current_altitude_m
# - past_1km_gradient_pct
# - terrain_class_motorway
# - terrain_class_suburban
# - terrain_class_urban (or dropped if drop_first=True)
```

### Memory Efficiency

The DatasetLoader already applies column projection:

```python
# Loads ONLY these 5 columns + target (not all 16)
# Memory efficient - no unnecessary data in RAM
train = loader.load_train()  # ~0.5 MB instead of 1.7 MB
```

## Next Steps

1. ✓ Inspect and understand features (This document)
2. → Baseline model training with base features (STEP 7 - Baseline)
3. → Evaluate baseline performance
4. → Train more complex models
5. → Consider vehicle-specific features if needed (STEP 8+)
6. → Feature engineering and selection
7. → Hyperparameter tuning
8. → Final test evaluation

## Summary Table

| Aspect | Status | Notes |
|--------|--------|-------|
| Base features ready | ✓ | 5 complete features identified |
| Target variable | ✓ | 100% complete, ready for modeling |
| Vehicle-specific features | ⚠️ | Incomplete, for vehicle-specific models |
| Missing values | ✓ | Understood and documented |
| Strategy | ✓ | Use base features for first iteration |
| Memory efficient loading | ✓ | DatasetLoader implemented |
| Feature encoding | → | Ready for implementation in ML pipeline |

---

**Document Version:** 1.0  
**Created:** 2026-08-16  
**Status:** COMPLETE
