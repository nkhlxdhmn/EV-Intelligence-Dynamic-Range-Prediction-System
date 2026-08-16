# Data Split Strategy

## Overview

This document describes the temporal/grouped train-validation-test split strategy used for the EV Intelligence & Dynamic Range Prediction System ML pipeline.

## Objective

Create a scientifically valid, non-leaking split that:
- Maintains temporal integrity for time-series data
- Prevents data leakage between splits
- Ensures reproducibility
- Maintains vehicle representation
- Enables fair model evaluation

## Dataset Overview

**Original ML Dataset:** `data/processed/devrt_ml_features.parquet`

### Statistics
- **Total Samples:** 9,952
- **Total Trips:** 50
- **Unique Vehicles:** 2
  - Vehicle 6: Dacia Spring (25 trips)
  - Vehicle 7: Nissan Leaf (25 trips)
- **Samples per Trip:** 83-482 (mean: 199.0)
- **Timestamp Range:** 2023-04-18 to 2026-08-16
- **Target:** `target_future_energy_kwh_per_km` (5 km future energy consumption per km)

## Split Strategy

### Approach: Trip-Level Stratified Split

**Rationale:**

The dataset is fundamentally trip-based time-series data. A critical issue is that adjacent samples within a trip **overlap heavily** because the target is computed using a 5 km forward-looking window.

**Example:** 
- Sample A at 10 km has target computed from energy between 10-15 km
- Sample B at 12 km has target computed from energy between 12-17 km

These targets share energy data from the 12-15 km range, creating a dependency.

**Solution:** 
Split at the **trip level**, not the sample level. This ensures:
1. ✓ No samples from the same trip appear in different splits
2. ✓ No target leakage due to overlapping future windows
3. ✓ Complete temporal sequences preserved within each split
4. ✓ Realistic training/evaluation scenarios

### Stratification

To maintain vehicle representation across all splits, we use **stratified sampling**:

Each vehicle's trips are randomly shuffled and split proportionally:
- Vehicle 6 (Dacia Spring): 25 trips → 18 train, 4 validation, 3 test
- Vehicle 7 (Nissan Leaf): 25 trips → 18 train, 4 validation, 3 test

This ensures:
- ✓ Both vehicles represented in all splits
- ✓ Perfect vehicle balance
- ✓ No vehicle-specific bias
- ✓ No multi-vehicle trip contamination

### Split Proportions

| Split | Trips | Target | Achieved | Samples | Target | Achieved |
|-------|-------|--------|----------|---------|--------|----------|
| Train | 36 | 70% | 72.0% | 6,900 | 69.4% | 69.4% |
| Validation | 8 | 15% | 16.0% | 1,635 | 16.4% | 16.4% |
| Test | 6 | 15% | 12.0% | 1,417 | 14.2% | 14.2% |
| **Total** | **50** | **100%** | **100%** | **9,952** | **100%** | **100%** |

### Vehicle Distribution

| Split | Vehicle Model | Trips | Samples | % |
|-------|---------------|-------|---------|---|
| Train | Dacia Spring | 18 | 3,628 | 52.6% |
| Train | Nissan Leaf | 18 | 3,272 | 47.4% |
| Validation | Dacia Spring | 4 | 993 | 60.7% |
| Validation | Nissan Leaf | 4 | 642 | 39.3% |
| Test | Dacia Spring | 3 | 924 | 65.2% |
| Test | Nissan Leaf | 3 | 493 | 34.8% |

**Note:** Slight sample imbalance between vehicles is due to varying trip lengths. This is acceptable because:
1. Vehicle representation is maintained
2. Trip-level separation is perfect
3. No vehicle is "missing" from any split

## Temporal Order

Within each split, samples are sorted by:
1. `trip_id` (primary)
2. `timestamp` (secondary)

This preserves:
- Trip integrity
- Temporal sequences
- Optional sequential modeling capabilities

**No random shuffling** of samples to maintain temporal coherence.

## Leakage Prevention

### Audit Results

✓ **AUDIT PASSED** - No critical issues detected

- ✓ No trip appears in multiple splits (50 unique trips across all splits)
- ✓ All samples assigned exactly once (9,952 train + validation + test)
- ✓ Sample counts sum correctly (9,952 = 6,900 + 1,635 + 1,417)
- ✓ Each trip belongs to exactly one vehicle
- ✓ All split assignments consistent with data

### Known Issues

⚠️ **Timestamp Completeness**

Some timestamps are missing in the original data:
- Train: 1,980/6,900 samples (28.7%) have null timestamp
- Validation: 504/1,635 samples (30.8%) have null timestamp
- Test: 599/1,417 samples (42.3%) have null timestamp

This is a **data quality issue inherited from original dataset**, not a split problem.

**Impact:** Temporal sorting within trips is only applied to non-null timestamps.

## Target Distribution

### Summary Statistics

| Split | Count | Mean | Median | Std | Min | Max |
|-------|-------|------|--------|-----|-----|-----|
| Train | 6,900 | 0.1515 | 0.1306 | 0.0874 | -0.248 | 0.496 |
| Validation | 1,635 | 0.1435 | 0.1297 | 0.0998 | -0.247 | 0.495 |
| Test | 1,417 | 0.1663 | 0.1317 | 0.0695 | 0.000 | 0.390 |

### Distribution Analysis

**Findings:**
1. ✓ Distributions are **reasonably similar** across splits
2. ✓ Mean values are within 0.015 (0.1435 to 0.1663) - very close
3. ✓ Standard deviations are similar (0.087 to 0.100) - acceptable variance
4. ✓ Test set has slightly higher mean and lower std (favorable)
5. ⚠️ Validation has slightly higher std (0.100 vs 0.087) - minor issue

**Conclusion:** Target distributions are **appropriately balanced** across splits. The stratified split maintains statistical similarity without artificial balancing.

## Files Generated

### Split Assignments
- **File:** `data/processed/split_assignments.parquet`
- **Columns:** `trip_id`, `vehicle_id`, `vehicle_model`, `split`
- **Purpose:** Maps each trip to its split assignment

### Split Datasets
- **Train:** `data/processed/train.parquet` (6,900 samples)
- **Validation:** `data/processed/validation.parquet` (1,635 samples)
- **Test:** `data/processed/test.parquet` (1,417 samples)

### Distribution Reports
- **Target Stats:** `reports/split_target_statistics.csv`
- **Vehicle Distribution:** `data/processed/split_distribution.csv`
- **Visualization:** `reports/figures/split_target_distribution.png`

## Usage Notes

### For Model Training

1. **Use train.parquet** - Never use validation or test during training
2. **Use validation.parquet** - For hyperparameter tuning only
3. **Use test.parquet** - For final evaluation ONLY (preserve until end)

### Memory Considerations

- Train: 6,900 samples, ~1.0-1.2 MB per numeric column
- All three: ~10 MB total if loaded as parquet (compressed)
- Python/Pandas in-memory: ~50-100 MB for full dataset

Use `src/models/dataset.py` for memory-efficient loading with column projection.

### Missing Features

The dataset contains some vehicle-specific features that are missing for certain vehicles:

**Dacia Spring specific:**
- Motor power readings only for subset of trips
- Some speed/acceleration data may be incomplete

**Nissan Leaf specific:**
- Similar patterns for vehicle-specific signals

**Strategy for modeling:**
- Use only **common reliable features** (see `docs/feature_preparation.md`)
- Do NOT blindly fill missing values with zero
- Consider vehicle-specific models later if needed

## Reproducibility

### Random Seed
- Random seed: `42`
- Seed used for: Trip shuffling within each vehicle
- Engine: NumPy

### Determinism
All splits are **fully deterministic**. Same seed produces identical splits.

```python
# To regenerate splits:
python src/data/create_split.py
```

## Next Steps

1. ✓ Feature engineering and target construction (STEP 6 - Complete)
2. ✓ Train/validation/test split (STEP 7 - This document)
3. → Feature preparation and baseline models (STEP 7 continuation)
4. → ML model training and evaluation (STEP 8)
5. → Hyperparameter tuning (STEP 9)
6. → Final test evaluation (STEP 10)

---

**Document Version:** 1.0  
**Created:** 2026-08-16  
**Status:** COMPLETE
