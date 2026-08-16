# Data Leakage Strategy

## Design Principles
- **Time-series data must be split chronologically**, not randomly
- **Future data must never enter lag/rolling features** for current prediction
- **Target-derived variables must not be used as input features**
- **Same trip/vehicle must appear in either training OR testing, not both**
- **Vehicle-aware splits for multi-vehicle evaluation**

## Important Examples of Leakage to Avoid

### 1. Random Time-Series Split
❌ **Wrong**: `train_test_split(X, y, test_size=0.2)` (shuffles time order)
✅ **Correct**: Split by time cutoff: `train = data[:cutoff], test = data[cutoff:]`

### 2. Future Observations in Lag Features
❌ **Wrong**: Using `speed[t+1:]` to predict `speed[t]` or `energy_consumption[t]`
✅ **Correct**: Only use `speed[:t]`, `speed[:t-1]`, etc. (past observations only)

### 3. Trip-Level Information Using Future Data
❌ **Wrong**: Calculating `mean_speed` using data from after the prediction point
✅ **Correct**: Calculate trip-level stats from trip start to current point only

### 4. Target-Derived Variables as Features
❌ **Wrong**: Using `net_energy_consumption_kwh_per_km` (the target itself) as a feature
✅ **Correct**: Use raw variables only (SOC, speed, power, etc.)

### 5. Same Trip in Train and Test
❌ **Wrong**: Random split where some rows from trip X are in train, others in test
✅ **Correct**: Whole trips assigned to either train OR test, never both

### 6. Vehicle-Specific Information Leakage
❌ **Wrong**: Training on Vehicle A and testing on Vehicle B, but using Vehicle A's calibration parameters
✅ **Correct**: Either vehicle-aware split, or train on all vehicles with regularization

## Data Leakage Rules by Phase

### Phase 1: Raw Data Parsing
- ✅ Parse raw files without any feature engineering
- ✅ Map raw columns to standard concepts
- ✅ Verify units and ranges
- ❌ Do NOT create lag/rolling features
- ❌ Do NOT calculate derived features
- ❌ Do NOT split data for modeling

### Phase 2: Data Cleaning & Verification
- ✅ Verify units, fix obvious errors (e.g., JAC AIR flag)
- ✅ Handle missing values with imputation strategy (documented)
- ✅ Remove obvious outliers with documented thresholds
- ❌ Do NOT create features using future data
- ❌ Do NOT normalize features for modeling yet

### Phase 3: Feature Engineering
- ✅ Create lag features using ONLY past data (t-1, t-2, etc.)
- ✅ Create rolling statistics using only past window
- ✅ Create trip-level aggregates from historical data only
- ✅ Create interaction features from non-future variables
- ❌ Do NOT use target variable in any feature
- ❌ Do NOT use data from after prediction point

### Phase 4: Model Training
- ✅ Temporal train/test split (e.g., 80% earliest data, 20% latest)
- ✅ Vehicle-aware split if evaluating across vehicles
- ✅ Cross-validation with time-series splitter (TimeSeriesSplit)
- ✅ Features validated for no leakage
- ❌ Do NOT train on future data
- ❌ Do NOT include target as feature

### Phase 5: Evaluation
- ✅ Evaluate on chronologically last data
- ✅ Report metrics (MAE, RMSE, R²) on test set only
- ✅ Compare model performance across datasets
- ❌ Do NOT report performance on training data only
- ❌ Do NOT use test data to influence model retraining

## Specific Leakage Checks for Each Dataset

### DEVRT Checks
- [ ] SOC used only from start/end of trip, not intermediate values as features
- [ ] `regenwh` integrated only up to current prediction point
- [ ] `cumul_dist` used as cumulative from trip start, not future distance
- [ ] `Motor Pwr(w)` used only from past samples
- [ ] `amb_temp` used only from current/past, not forecasted

### JAC Checks
- [ ] AIR flag used only as flag (not temperature conversion)
- [ ] VOL used only after scaling verification (not assumed)
- [ ] SPD used as-is (no future speed assumptions)
- [ ] ODO used as cumulative from trip start
- [ ] ECO mode (0/192) used as binary flag

### TUM Checks
- [ ] hv_soc (value_id=900) used only from start/end of trip
- [ ] hv_battery_voltage × ptc1_current power calculated only from past samples
- [ ] hv_aux_power (can be negative) integrated only to current point
- [ ] traveled_distance accumulative from trip start
- [ ] C-rate values used only from past data
- [ ] Battery temperatures used only from past data

## Validation Procedure

### 1. Leakage Audit Script
Create a validation script that checks:
```python
def check_no_leakage(features, target, timestamps, trip_ids):
    """
    Verify that no future data leakage is present.
    """
    errors = []
    
    # Check 1: Features should not contain target values
    if np.any(np.isclose(features, target, atol=1e-10)):
        errors.append("Features contain target values")
    
    # Check 2: No future timestamps in training features
    # (timestamps in train set should all be before test set timestamps)
    train_timestamps = timestamps[trip_ids == 'train']
    test_timestamps = timestamps[trip_ids == 'test']
    if np.any(train_timestamps > np.max(test_timestamps)):
        errors.append("Train set contains future timestamps relative to test set")
    
    # Check 3: Same trip not in both train and test
    train_trips = set(trip_ids[trip_ids == 'train'])
    test_trips = set(trip_ids[trip_ids == 'test'])
    overlap = train_trips & test_trips
    if overlap:
        errors.append(f"Trips in both train and test: {overlap}")
    
    return errors
```

### 2. Documentation Requirements
All features must be documented with:
- Source raw variables
- Calculation method
- Time direction (past-only)
- Leakage check passed/failed

### 3. Version Control
- Record all feature engineering dates
- Document any changes to leakage rules
- Maintain feature lineage (which raw vars → which features)

## Multi-Dataset Leakage Considerations

### When Combining DEVRT + TUM + JAC
- **Different sampling rates**: 200ms (DEVRT speed), 5s (TUM SOC), minute-level (JAC timestamps)
- **Different time bases**: Align by trip start, not by clock time
- **Vehicle heterogeneity**: 7 DEVRT vehicles (2 models), 7 TUM vehicles (2 models + 5 Born), 1 JAC vehicle
- **Split by dataset first**, then by time within each dataset
- **Never mix train from one dataset with test from another** without proper domain adaptation

### Dataset-Specific Splits
- **DEVRT**: Split by trip (28 trips total) - 80/20 by trip order
- **TUM**: Split by track/trip (per vehicle track segments) - chronological split
- **JAC**: Split by row order (decomposed timestamps) - challenging; may need to bin into trip segments

### Recommended Split Procedure
1. **Within each dataset**: Chronological split (earliest data → train, latest data → test)
2. **Across datasets**: Evaluate separately, then compare performance
3. **Do NOT** randomly combine all datasets and split
4. **Do NOT** use data from dataset A to predict dataset B's pattern

## Leakage Checklist (Before Model Training)

- [ ] All features derive from past or current data only (no future forecasts)
- [ ] No feature uses the target variable (directly or indirectly)
- [ ] Train/test split is temporal, not random
- [ ] Same trip/vehicle appears in only one split (train OR test)
- [ ] Lag/rolling features use fixed windows from past data
- [ ] Imputation values (mean/std) calculated from training data only
- [ ] Normalization parameters (min/max, mean/std) calculated from training data only
- [ ] No geographic/route information from test trips used in training features
- [ ] Vehicle-specific parameters not leaked across splits

## Leakage Avoidance Summary

| Leakage Type | Prevention Method |
|-------------|------------------|
| Random time split | Chronological split by time cutoff |
| Future data in features | Only use t-, t-1, t-2... lag features |
| Target as feature | Exclude target from feature matrix entirely |
| Same trip in both splits | Assign whole trips to one split |
| Imputation with global stats | Calculate stats from training data only |
| Normalization with global params | Fit on train data, transform test data |
| Vehicle-specific leakage | Vehicle-aware splits or regularization |
| Cross-dataset leakage | Evaluate datasets separately first |
| Route/geography leakage | Remove route-specific features if leaking |

## Next Steps (Step 4: Dataset-Specific Parsing)
When proceeding to data cleaning:
1. Implement the leakage checks above before any feature engineering
2. Document all feature calculations with time direction
3. Create the leakage audit script in `src/data/leakage_check.py`
4. Record all imputation/normalization parameters derived from training data only
5. Begin DEVRT dataset parsing (primary training dataset)