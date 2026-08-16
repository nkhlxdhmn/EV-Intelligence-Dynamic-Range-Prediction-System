# Baseline Model Results

## Overview

Baseline models establish minimum performance expectations. They provide a reference point for comparing more complex ML models.

Two simple baseline approaches are evaluated on **validation and test sets** using **training set statistics only**.

**Critical:** Test set remains untouched during baseline development and hyperparameter selection.

## Dataset Information

| Metric | Value |
|--------|-------|
| Training Samples | 6,900 |
| Training Trips | 36 |
| Validation Samples | 1,635 |
| Validation Trips | 8 |
| Test Samples | 1,417 |
| Test Trips | 6 |
| **Total Samples** | **9,952** |
| **Total Trips** | **50** |

## Baseline 1: Mean Baseline

### Description

**Strategy:** Predict the **mean of the training set** for all validation and test samples.

**Formula:**
```
ŷ_validation = mean(y_train)
ŷ_test = mean(y_train)
```

**Rationale:** This is the null model. Any ML model should significantly outperform this to justify its complexity.

### Training Statistics

```
Training Mean (prediction value): 0.151504 kWh/km
```

### Validation Results

| Metric | Value | Interpretation |
|--------|-------|-----------------|
| **MAE** | 0.0715 kWh/km | Average prediction error magnitude |
| **RMSE** | 0.1001 kWh/km | Penalizes large errors more |
| **R²** | -0.0064 | Model explains 0% of variance (as expected) |
| **MAPE** | 42.29% | Mean absolute % error (42% on average) |
| **SMAPE** | 48.10% | Symmetric MAPE (more robust) |

### Test Results

| Metric | Value | Interpretation |
|--------|-------|-----------------|
| **MAE** | 0.0566 kWh/km | Test MAE is better than validation |
| **RMSE** | 0.0711 kWh/km | More consistent test performance |
| **R²** | -0.0452 | Slight negative (variance in test greater than train mean) |
| **MAPE** | 34.60% | Test MAPE is lower (~34% vs 42%) |
| **SMAPE** | 35.89% | Reasonable symmetric error |

### Observations

1. **R² is negative:** The model performs worse than predicting zero deviation from mean. This is expected for a constant predictor.

2. **Test outperforms validation:** Test MAE (0.0566) is better than validation (0.0715). This is **not unusual** for random splits - just means test set has slightly lower variance.

3. **MAPE interpretation:** With target values near zero (mean=0.15), MAPE of ~35-42% is not unreasonable.

## Baseline 2: Vehicle Mean Baseline

### Description

**Strategy:** Predict the **vehicle-specific training mean** for validation/test samples.

**Formula:**
```
If vehicle_id in training_vehicles:
    ŷ = mean(y_train | vehicle_id)
Else:
    ŷ = mean(y_train)  # Fallback to global mean
```

**Rationale:** Energy consumption may differ by vehicle type. This model captures per-vehicle differences observed in training.

### Training Statistics

```
Vehicle 6 (Dacia Spring):  Mean = 0.144442 kWh/km (from 18 trips)
Vehicle 7 (Nissan Leaf):   Mean = 0.159335 kWh/km (from 18 trips)
Global Mean (fallback):    0.151504 kWh/km

Difference: Nissan Leaf uses ~1.03% more energy than Dacia Spring on average
```

### Fallback Usage

| Split | Samples Using Fallback | Total Samples | % |
|-------|------------------------|----|-------|
| Validation | 0 | 1,635 | 0% |
| Test | 0 | 1,417 | 0% |

**Note:** Both vehicles present in both validation and test, so no fallback needed.

### Validation Results

| Metric | Value | Difference from Mean Baseline | Interpretation |
|--------|-------|---------|-----------------|
| **MAE** | 0.0708 kWh/km | -0.0007 ✓ | Slightly better (-1.0%) |
| **RMSE** | 0.0999 kWh/km | -0.0002 ✓ | Marginally better |
| **R²** | -0.0032 | +0.0032 ✓ | Captures ~0% variance (still poor) |
| **MAPE** | 41.17% | -1.12 ✓ | Modest improvement |
| **SMAPE** | 47.63% | -0.47 ✓ | Very similar |

### Test Results

| Metric | Value | Difference from Mean Baseline | Interpretation |
|--------|-------|---------|-----------------|
| **MAE** | 0.0560 kWh/km | -0.0006 ✓ | Slightly better (-1.1%) |
| **RMSE** | 0.0710 kWh/km | -0.0001 ✓ | Marginally better |
| **R²** | -0.0418 | +0.0034 ✓ | Tiny improvement |
| **MAPE** | 33.69% | -0.91 ✓ | Small improvement |
| **SMAPE** | 35.49% | -0.40 ✓ | Similar |

### Observations

1. **Marginal improvement:** Vehicle-specific mean is ~1% better than global mean across metrics.

2. **Not dramatic:** The difference between vehicles (~1.03%) is small relative to target variance (std = 0.088).

3. **Negative R²:** Still cannot explain meaningful variance with this approach.

4. **Both vehicles represented:** No fallback usage shows good split balance.

## Comparison Summary

| Model | Validation MAE | Validation RMSE | Test MAE | Test RMSE | Interpretation |
|-------|---------|--------|----------|----------|-----------------|
| Mean Baseline | 0.0715 | 0.1001 | 0.0566 | 0.0711 | Null model |
| Vehicle Mean | 0.0708 | 0.0999 | 0.0560 | 0.0710 | ~1% better |
| **Improvement** | **-1.0%** | **-0.2%** | **-1.1%** | **-0.1%** | Marginal |

## Metric Explanations

### MAE (Mean Absolute Error)
- **Range:** 0 to ∞
- **Better:** Smaller
- **Interpretation:** Average magnitude of prediction errors
- **Example:** MAE=0.0566 means predictions are off by ~0.0566 kWh/km on average

### RMSE (Root Mean Squared Error)
- **Range:** 0 to ∞
- **Better:** Smaller
- **Property:** Penalizes large errors more heavily than MAE
- **Interpretation:** Larger errors hurt more

### R² (Coefficient of Determination)
- **Range:** -∞ to 1.0
- **Better:** Higher (1.0 = perfect)
- **Interpretation:** Proportion of variance explained by model
- **Negative:** Model worse than predicting mean (constant predictor)

### MAPE (Mean Absolute Percentage Error)
- **Range:** 0 to ∞ (unbounded, can be very large)
- **Better:** Smaller
- **Limitation:** Unstable when actual values are zero or near zero
- **Our case:** Target has values from -0.248 to +0.496, with ~20% of samples ≤ 0
- **Note:** MAPE is unreliable here; prefer SMAPE

### SMAPE (Symmetric Mean Absolute Percentage Error)
- **Range:** 0 to 200 (100 = reasonable baseline)
- **Better:** Smaller
- **Formula:** 2×|actual-pred| / (|actual|+|pred|)
- **Advantage:** Handles zero/negative values better than MAPE
- **Our results:** SMAPE ~35-48, indicating ~35-48% average relative error

## Data Leakage Check

✓ **No leakage detected**

- Baselines trained ONLY on training data
- Evaluated on validation and test sets
- Test set used for final reporting only
- No hyperparameter tuning performed

## Expected ML Model Performance

### Realistic Goals

Based on baseline results:

**Validation Set Expectations:**
- Good model MAE: 0.045-0.055 kWh/km (25-35% better than mean baseline)
- Good model RMSE: 0.080-0.090 kWh/km
- Good model R²: 0.15-0.35 (explaining 15-35% of variance)

**Test Set Expectations:**
- Test MAE: 0.050-0.060 kWh/km
- Test RMSE: 0.080-0.095 kWh/km
- Test R²: 0.10-0.30

### Interpretation

- Energy consumption has high variability (std = 0.088)
- Mean baseline achieves ~0.0715 MAE
- Room for ~1.5x improvement (down to ~0.05 MAE) with better features/model
- Beyond 0.04 MAE may require non-linear models (tree-based or neural)

## Feature Importance Insights

From baseline comparisons:

1. **Battery capacity matters:** Vehicle-specific difference of ~1%
2. **Current SOC may matter:** Baseline doesn't capture this
3. **Terrain/altitude likely important:** Baseline ignores these
4. **Time-of-day/speed likely important:** Baseline ignores these
5. **Non-linear relationships likely exist:** Linear mean baseline limited

**Prediction:** Including current_soc_pct, altitude, and gradient in a simple linear model could achieve:
- Validation R² ~ 0.20-0.30
- Test R² ~ 0.15-0.25

## Recommendations for Next Steps

### Model Selection (STEP 8)

1. ✓ Start with linear regression on base features
   - current_soc_pct
   - battery_capacity_kwh
   - current_altitude_m
   - past_1km_gradient_pct
   - terrain_class (one-hot)

2. → Try tree-based models (Random Forest, XGBoost) for non-linearity

3. → Consider ensemble methods

4. → Only explore vehicle-specific models if base model plateaus

### Feature Engineering (STEP 8+)

1. Interactions: SOC × Altitude, Gradient × Speed
2. Lagged features: Previous sample energy usage
3. Rolling statistics: 5-sample moving average
4. Domain features: "Regeneration potential", efficiency ratio

### Validation Strategy

1. ✓ Splits are clean (no leakage)
2. ✓ Use validation set for hyperparameter tuning
3. ✓ Use test set ONLY for final evaluation (after model selection complete)
4. → Consider cross-validation on training set

### Data Quality

1. ⚠️ Address timestamp missing values if using time-series features
2. ⚠️ Understand why vehicle-specific features are missing (44% incomplete)
3. ✓ Current set of 5 base features is complete and high-quality

## Conclusion

- **Mean baseline MAE:** 0.0715 (validation), 0.0566 (test)
- **Vehicle baseline MAE:** 0.0708 (validation), 0.0560 (test)
- **Improvement:** ~1% better with vehicle-specific means
- **Interpretation:** Basic vehicle differences captured, but larger potential improvements from features
- **Status:** Ready for ML model development

---

**Report Version:** 1.0  
**Created:** 2026-08-16  
**Status:** COMPLETE
