# Model Card: EV Energy Consumption Prediction — v1

## 1. Model Purpose

Predict the **net energy consumption of an electric vehicle over the next 5 km**
of driving, expressed in kWh/km. This is an experimental research model to
investigate the feasibility of ML-based EV range/consumption prediction from
telemetry data. **This is NOT a production-grade range estimator.**

## 2. Target Definition

- **Column:** `target_future_energy_kwh_per_km`
- **Horizon:** future 5 km of driving
- **Meaning:** net energy consumed per km over the upcoming 5 km, where negative
  values indicate net regenerative energy recovery (downhill regeneration).
- Range in data: approx. -0.25 to +0.50 kWh/km
- Negative-target samples: ~3% of validation samples; **0% of test samples**

## 3. Prediction Horizon

5 km of future driving distance.

## 4. Dataset

**DEVRT** (Dacia Spring and Nissan Leaf trips, Basque Country, April 2023),
processed through the project's memory-efficient pipeline.

- Dataset file: `data/processed/devrt_ml_features_v2.parquet`
- Total samples: 9,952
- Total trips: 50

## 5. Number of Trips

- Train: 36 trips (6,900 samples)
- Validation: 8 trips (1,635 samples)
- Test: 6 trips (1,417 samples)

Splits are **trip-disjoint** (no trip appears in more than one split).

## 6. Vehicles

- **Dacia Spring** (small city EV, ~33 kWh battery)
- **Nissan Leaf** (compact EV, ~62 kWh battery)

Dacia Spring files lack speed/motor/regen telemetry (structurally missing);
Nissan Leaf files include full telemetry.

## 7. Feature Groups

Experiment **A_BASIC** (Battery + Terrain):

| Group | Features |
|-------|----------|
| Battery | current_soc_pct, current_soh_pct, battery_capacity_kwh |
| Terrain | current_altitude_m, current_gradient_pct, past_1km_gradient_pct, terrain_class, elevation_gain_1km, elevation_loss_1km |

These 9 features are 100% complete across all samples. Driving/powertrain/
environment features exist in the v2 dataset but were NOT used in the frozen model
because they are structurally missing for Dacia Spring (~43.7% completeness).

## 8. Training Methodology

- Model: XGBoost Regressor
- Hyperparameters: n_estimators=300, learning_rate=0.05, max_depth=5,
  subsample=0.8, colsample_bytree=0.8, tree_method=hist, random_state=42
- Categorical encoding: terrain_class → integer codes
- No feature scaling (tree-based model)
- Rows with missing feature values dropped (none for A_BASIC)
- Random seed: 42
- **No test data used in any training decision**

## 9. Validation Methodology

- Hold-out validation set (8 trips, 1,635 samples)
- Model selection based ONLY on validation MAE (primary) and RMSE/R²/stability
  (secondary)
- Baselines recomputed from train statistics only
- Validation champion: A_BASIC + XGBoost (MAE = 0.063 kWh/km), which beat the
  global-mean baseline (0.072) by ~13% on validation

## 10. Final Test Methodology

- Test set untouched until after model freeze
- Frozen A_BASIC + XGBoost evaluated on test exactly ONCE
- No retraining, no tuning, no feature changes after test evaluation

## 11. Metrics

| Set | Model | MAE | RMSE | R² | SMAPE |
|-----|-------|-----|------|----|-------|
| Validation | Global mean baseline | 0.0722 | 0.1026 | -0.003 | 48.6% |
| Validation | Frozen A_BASIC XGBoost | 0.0629 | 0.0885 | 0.254 | 45.3% |
| Test | Global mean baseline | 0.0572 | 0.0730 | — | — |
| Test | Vehicle mean baseline | 0.0570 | 0.0730 | — | — |
| Test | **Frozen A_BASIC XGBoost** | **0.0642** | **0.0803** | **-0.264** | **44.0%** |

**Result on test:** the frozen ML model was **~12% WORSE than the simple mean
baseline on the test set.** This is reported honestly. The model's validation
advantage did not generalize to the held-out test trips.

## 12. Known Limitations

1. **Poor test generalization:** ML beats baselines on validation but not on test.
2. **Small number of independent trips (50 total):** high variance in trip-level
   performance.
3. **Distribution shift between splits:** test set differs in vehicle mix
   (65% Dacia vs ~53% Nissan in validation) and target distribution.
4. **5 km target horizon** smooths/noisifies the signal; SOC quantization
   (±1% increments) limits target precision.
5. **Baseline difficulty on test:** test target variance is lower (std 0.072 vs
   0.102 validation), making the constant mean a strong reference.

## 13. Missing Telemetry

- Dacia Spring: no speed, motor power, torque, rpm, regen, ambient temperature
  in source files. These signals are **structurally absent**, not zero.
- 43.7% of samples have speed telemetry (Nissan only).
- Driving/powertrain/environment experiments (B–E) operate on the Nissan-only
  subpopulation and are **not directly comparable** to A_BASIC.
- The model does not use optional telemetry features, so it cannot exploit
  regeneration or driving-behavior signals.

## 14. SOC Quantization

- SOC is reported in 1% integer increments.
- The target (energy over 5 km) is derived from SOC differences, so target
  precision is limited by quantization: a ±1% SOC step at 62 kWh ≈ 0.62 kWh,
  which over 5 km ≈ 0.124 kWh/km — comparable to typical target magnitudes.
- This is a fundamental data-quality limit on prediction accuracy.

## 15. Regenerative Braking

- Regeneration can make the net target negative (downhill recovery).
- The frozen model has no regeneration features and **cannot predict negative
  targets** — it systematically overpredicts on the ~53 negative-target
  validation samples (MAE 0.076, mean signed error +0.065).
- Test set contains no negative targets, so test evaluation does not exercise
  this regime.

## 16. Generalization Limitations

- 50 trips from 2 vehicles in one region (Basque Country) over 4 days.
- Results are not generalizable to other vehicles, climates, terrains, or seasons.
- Trip-level distribution differences dominate the error.

## 17. Appropriate Use

- Research and feasibility assessment of ML-based EV consumption prediction.
- Baseline/benchmark for future feature engineering and model iterations.
- Investigating feature-target relationships (predictive importance only).

## 18. Inappropriate Use

- NOT for real-world range estimation or driver guidance.
- NOT for financial, warranty, or safety decisions.
- NOT as a production deployment without major additional validation data.
- NOT to be interpreted as causal claims about what "causes" energy consumption.

---

**Status:** Experimental research model v1.0
**Created:** 2026-08-16
**Model artifact:** `models/step8/A_BASIC_XGB.joblib`