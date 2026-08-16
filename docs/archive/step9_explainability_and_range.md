# STEP 9 - Model Explainability + Dynamic Range Estimation

## 1. Feature importance (predictive, not causal)

ExtraTrees impurity-based importance on the frozen model
(`reports/step9_global_feature_importance.csv`). These values describe
**predictive importance** and must NOT be interpreted as causal importance.

Top 20:

| rank | feature | importance | cumulative |
|------|---------|-----------|------------|
| 1 | next_5km_uphill_frac | 0.33995 | 0.33995 |
| 2 | next_5km_net_elev_m | 0.16265 | 0.50260 |
| 3 | next_5km_gradient_pct | 0.15782 | 0.66042 |
| 4 | next_5km_loss_m | 0.05585 | 0.71627 |
| 5 | next_5km_downhill_frac | 0.05200 | 0.76827 |
| 6 | current_altitude_m | 0.01872 | 0.78699 |
| 7 | next_2km_loss_m | 0.01273 | 0.79972 |
| 8 | next_5km_gain_m | 0.01249 | 0.81221 |
| 9 | day_of_week | 0.01121 | 0.82342 |
| 10 | next_2km_net_elev_m | 0.01063 | 0.83405 |
| 11 | current_soc_pct | 0.00885 | 0.84290 |
| 12 | next_2km_gradient_pct | 0.00763 | 0.85054 |
| 13 | hour_sin | 0.00539 | 0.85593 |
| 14 | hour_of_day | 0.00445 | 0.86038 |
| 15 | speed_iqr | 0.00441 | 0.86479 |
| 16 | hour_cos | 0.00422 | 0.86901 |
| 17 | trip_elapsed_time_min | 0.00412 | 0.87313 |
| 18 | time_since_trip_start_min | 0.00406 | 0.87720 |
| 19 | next_2km_gain_m | 0.00393 | 0.88112 |
| 20 | current_temperature_c | 0.00389 | 0.88501 |

## 2. Permutation importance

Permutation importance measures the MAE degradation on TRAIN+VALIDATION only
when each feature is randomly shuffled, using the frozen model configuration
under GroupKFold (grouped by trip_id; no test data).
`reports/step9_permutation_importance.csv`.

OOF base MAE = 0.03852. Top 10:

| rank | feature | importance_mean | importance_std |
|------|---------|-----------------|----------------|
| 1 | next_5km_uphill_frac | 0.01328 | 0.00390 |
| 2 | next_5km_gradient_pct | 0.00503 | 0.00263 |
| 3 | next_5km_net_elev_m | 0.00447 | 0.00260 |
| 4 | next_5km_loss_m | 0.00153 | 0.00124 |
| 5 | next_5km_downhill_frac | 0.00077 | 0.00113 |
| 6 | day_of_week | 0.00047 | 0.00053 |
| 7 | next_5km_gain_m | 0.00029 | 0.00037 |
| 8 | current_altitude_m | 0.00026 | 0.00035 |
| 9 | hour_sin | 0.00018 | 0.00015 |
| 10 | hour_of_day | 0.00012 | 0.00012 |

**Impurity vs permutation discrepancy.** Impurity importance (tree-split gain)
is biased toward high-cardinality/high-frequency features and can over-state
look-ahead terrain. Permutation importance reflects true predictive value via
out-of-fold MAE degradation; it agrees on the top feature
(`next_5km_uphill_frac`) and confirms the look-ahead terrain family dominates,
but ranks it with much smaller magnitude and lets more onboard features
(speed, time-of-day) appear. Impurity importance measures split usage; that is
why the absolute magnitudes differ.

## 3. SHAP status

**SKIPPED.** `shap` is not installed in this environment, and the project rule
avoids installing heavy dependency chains (numba, etc.) for this step.
Permutation importance (Section 2) is used as the model-agnostic explainability
method instead. Status recorded in `reports/step9_shap_status.json`.

## 4. Local explanations

5 representative TRAIN+VALIDATION samples (no test data), selected as
low/medium/high predicted consumption, steep terrain, and high regenerative
braking. Contributions are measured as prediction deltas vs the median-feature
baseline (one-feature-at-a-time) and are PREDICTIVE, not causal.
`reports/step9_local_explanations.md`.

Example (low-predicted sample, Nissan Leaf trip 031): predicted −0.2466 kWh/km
vs baseline 0.1384; the dominant negative contributors are the look-ahead
terrain features (next_5km_net_elev_m, next_5km_gradient_pct) and
current_altitude_m — i.e. the model lowers consumption on downhill upcoming
terrain.

## 5. Energy → range conversion

```
predicted_energy_kwh_per_km   (frozen ExtraTrees over next 5 km)
remaining_energy_kwh = battery_capacity_kwh * soc_pct / 100        (approx)
estimated_range_km  = remaining_energy_kwh / predicted_consumption
```
The capacity·SOC approximation ignores usable-vs-usable buffers, degradation
and reserve; the reserve is added explicitly below.

## 6. SOC reserve

```
usable_energy_kwh = battery_capacity_kwh * max(soc_pct - reserve_soc_pct, 0) / 100
estimated_range_km = usable_energy_kwh / predicted_consumption_kwh_per_km
```
Default reserve 10%. If SOC ≤ reserve, usable energy and range are 0.
Documented as an engineering estimate, NOT ground-truth range.

## 7. Uncertainty / range band

Residual quantiles are computed on TRAIN+VALIDATION only (never test):
`reports/step9_trainval_residual_quantiles.json`.
q10 = −0.04705, q50 = +0.00314, q90 = +0.03628 (residual = predicted − actual).

Method (signs checked carefully):
- Positive residual ⇒ model under-predicts consumption ⇒ actual consumption
  is higher ⇒ lower range (conservative).
- `low_consumption = predicted + q_high`  → `conservative_range = usable / low_consumption`
- `high_consumption = predicted + q_low`  → `optimistic_range = usable / high_consumption`
- `expected_range = usable / predicted`
- Guard: band consumption is floored at 0.5 × predicted so the optimistic
  range never exceeds 2× the expected range (prevents absurd tail results for
  very low predictions).
- Ordering guaranteed: conservative ≤ expected ≤ optimistic.

## 8. Example calculation

Illustrative only — NOT actual vehicle performance.

```
Battery: 33 kWh (Dacia Spring class)
SOC: 60%
Reserve: 10%
Predicted consumption: 0.14 kWh/km

usable energy = 33 × (60 − 10) / 100 = 16.5 kWh
range = 16.5 / 0.14 = 117.9 km
band (q10=−0.047, q90=+0.036):
  conservative = 16.5 / (0.14 + 0.036)  ≈ 93.6 km
  expected     = 16.5 / 0.14            ≈ 117.9 km
  optimistic   = 16.5 / (0.14 − 0.047)  ≈ 177.5 km
```

## 9. Limitations

1. DEVRT is the primary training dataset.
2. Model is route-aware; upcoming terrain must come from route/DEM.
3. Dacia lacks some telemetry available for Nissan (NaN flags/imputation).
4. Target is SOC-derived (may carry SOC-sensor noise).
5. Prediction horizon is 5 km; shorter-horizon behavior is not validated.
6. Test R2 = 0.5902; Nissan weaker than Dacia (MAE 0.051 vs 0.036).
7. Range depends on predicted consumption; it is an estimate, not OEM-certified.
8. Not yet externally validated on TUM; weather/wind and traffic are limited.
9. Driver-behaviour and battery-degradation/SOH generalization is limited.
10. SHAP was skipped; permutation importance is the explainability method.

## 10. Final architecture

```
vehicle telemetry (standardized trip)
        ↓
feature generation (engineer_trip, leakage-safe)
        ↓
102 route-aware features (frozen list)
        ↓
frozen ExtraTreesRegressor (300/10/3, seed 42)
        ↓
predicted energy consumption (kWh/km)
        ↓
RangeEstimator (reserve 10%, residual band q10/q90)
        ↓
usable energy + conservative/expected/optimistic range
```

Implementation:
- `src/inference/range_estimator.py` — range math + validation.
- `src/inference/predictor.py` — end-to-end prediction pipeline.
- `src/analysis/step9_explainability.py` — importance, permutation, local
  explanations, residual quantiles (train+val only).
- Reports: `reports/step9_*`, `reports/figures/` (SHAP figures not produced
  because SHAP was skipped).