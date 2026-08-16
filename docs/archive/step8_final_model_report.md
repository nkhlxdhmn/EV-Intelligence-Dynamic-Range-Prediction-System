# STEP 8 - Final Model Report

## 1. Executive summary
The frozen route-aware model achieves a held-out test MAE of **0.04112 kWh/km**
(RMSE 0.05236, R2 +0.5902), a **33.5%**
improvement over the global-mean baseline (MAE 0.06187).

## 2. Dataset
- Train rows: 7,418
- Validation rows: 1,680
- Test rows (held-out, evaluated once): 1,537
- Train+validation rows used for final fit: 9,098
- Trips: train 36, validation 8, test 6

## 3. Target definition
`target_future_energy_kwh_per_km` = average future energy consumption over the next 5 km (kWh/km).
Used exactly as present in the processed datasets; never recreated.

## 4. Feature set
Exactly **102 route-aware causal features** (frozen in Step 7.7):
- 87 strictly causal onboard features
- 15 conditionally causal route/terrain (look-ahead `next_*`) features
- `trip_phase` REMOVED (trip-end leakage)
Feature order and list: `models/final_feature_list.json`.

## 5. Route-aware assumption
"This model is route-aware and assumes access to upcoming route elevation /
terrain information."
"The strict onboard-only model achieved MAE ≈ 0.05518 kWh/km in GroupKFold
CV, while the route-aware model achieved MAE ≈ 0.04002 kWh/km."

## 6. Data splitting strategy
Trip-disjoint split at the trip level (no trip appears in two splits):
train ∩ validation = ∅, train ∩ test = ∅, validation ∩ test = ∅
(verified, see `reports/step8_dataset_verification.json`).

## 7. Leakage prevention
- Median imputation fitted on TRAIN+VAL ONLY; test never contributes statistics.
- Feature set audited in Step 7.7 (no target leakage, no trip-end leakage, no
  future SOC/speed/power telemetry; look-ahead terrain is static geography).
- Test evaluated exactly once; marker `reports/.step8_test_evaluated` guards
  against accidental re-evaluation.

## 8. Model architecture
ExtraTreesRegressor (ensemble of regression trees).

## 9. Hyperparameters
- n_estimators = 300
- max_depth = 10
- min_samples_leaf = 3
- random_state = 42
- n_jobs = -1
Frozen; no tuning, no comparison, no ensembles.

## 10. Training procedure
1. Load v2_train + v2_validation.
2. Select the exact 102 route-aware features.
3. Fit `SimpleImputer(strategy='median')` on train+val only.
4. Train ExtraTreesRegressor on the combined matrix.
5. Save model + preprocessor + feature list.

## 11. Final test results
- MAE: **0.04112**
- RMSE: **0.05236**
- R2: **+0.5902**
- Bias (mean error): **-0.00618**
- Median absolute error: **0.03270**
- Max absolute error: **0.15361**
- Explained variance: **0.59590**
- MAPE: not reported — 3.0% of test targets are near zero (<0.05 kWh/km); MAPE is unstable/undefined near-zero denominators.

## 12. Baseline comparison
Baseline = global mean of the train+val target (0.14939):
- Baseline MAE: 0.06187 | Model MAE: 0.04112
- MAE improvement: **33.5%**
- RMSE improvement: **36.3%**
- Baseline R2: -0.0096 | Model R2: +0.5902

## 13. Vehicle-wise performance
- Dacia Spring: n=1044, MAE=0.03638, RMSE=0.04543, R2=+0.663, bias=+0.00034
- Nissan Leaf: n=493, MAE=0.05116, RMSE=0.06463, R2=+0.436, bias=-0.02000

## 14. Error analysis
Binned MAE/RMSE/bias by target range, altitude, look-ahead 5km gradient,
trip distance, elapsed time, and vehicle -> `reports/step8_error_analysis.csv`.
(Descriptive only; does not influence the model.)

## 15. Feature importance
Top 20 (predictive importance from ExtraTrees `feature_importances_`; this is
NOT causal importance):
1. next_5km_uphill_frac: 0.33995
2. next_5km_net_elev_m: 0.16265
3. next_5km_gradient_pct: 0.15782
4. next_5km_loss_m: 0.05585
5. next_5km_downhill_frac: 0.05200
6. current_altitude_m: 0.01872
7. next_2km_loss_m: 0.01273
8. next_5km_gain_m: 0.01249
9. day_of_week: 0.01121
10. next_2km_net_elev_m: 0.01063
11. current_soc_pct: 0.00885
12. next_2km_gradient_pct: 0.00763
13. hour_sin: 0.00539
14. hour_of_day: 0.00445
15. speed_iqr: 0.00441
16. hour_cos: 0.00422
17. trip_elapsed_time_min: 0.00412
18. time_since_trip_start_min: 0.00406
19. next_2km_gain_m: 0.00393
20. current_temperature_c: 0.00389
Full ranking: `reports/step8_feature_importance.csv`.

## 16. Limitations
- Route-aware assumption: requires planned route elevation/terrain (nav/DEM);
  a bare onboard model without route info degrades to strict onboard (~0.05518).
- Cross-vehicle generalization tested on only two vehicle models (Dacia, Nissan).
- Small per-vehicle test samples (n ≈ 1044 /
493).
- DEVRT telemetry gaps (e.g. no regen/motor data on Dacia) are handled via NaN
  flags/median imputation.
- Negative target values exist (regen gain over a 5km window); treated as real signal.

## 17. Reproducibility
- `src/models/train_final_model.py` reproduces the entire pipeline
  (random_state=42 everywhere, fixed feature order).
- Model: `models/ev_energy_extratrees_route_aware.joblib`
- Preprocessor: `models/final_preprocessor.joblib`
- Feature list: `models/final_feature_list.json`

## 18. Final conclusion
The route-aware ExtraTrees model generalizes to the untouched held-out test set
with MAE **0.04112 kWh/km** (33.5% better than
baseline), evaluated exactly once with no test-driven tuning.
