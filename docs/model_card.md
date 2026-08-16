# Model Card - EV Energy Consumption & Range Prediction

## 1. Model purpose
Predict the average future energy consumption of an electric vehicle over the
next 5 km of driving (kWh/km), and use that prediction to estimate the
remaining usable driving range given the current battery state of charge.

## 2. Intended use
- Route-aware energy-consumption prediction for the Dacia Spring and Nissan
  Leaf on the DEVRT dataset (urban/suburban Basque Country routes).
- Input to a dynamic remaining-range estimator (usable energy / predicted
  consumption) with a configurable SOC reserve and uncertainty band.
- Scientific/analytical usage: understanding which features carry predictive
  signal and how they affect the consumption estimate.
- Serving as a prototype inference API (Step 11) for demonstration.

## 3. Non-intended use
- Not a certified OEM range estimator; ranges are engineering estimates.
- Not validated on other EV models, routes, or countries.
- Not for autonomous driving control loops.
- Not to be used without upcoming route elevation/terrain data (the model is
  route-aware).
- Not for predicting battery degradation, cell health, or charging behavior.
- **Not externally validated**: the TUM external validation attempt was
  BLOCKED (see §13); do not treat the model as cross-dataset validated.

## 4. Training data
- Source: DEVRT telemetry (Dacia Spring and Nissan Leaf).
- Processed parquet features: `data/processed/v2_{train,validation,test}.parquet`.
- Rows: train 7,418; validation 1,680; test 1,537 (test evaluated once).
- Trips: train 36, validation 8, test 6 (trip-disjoint splits).

## 5. Target
`target_future_energy_kwh_per_km`: average future energy consumption over the
next 5 km, computed as `(soc_i - soc_j) * capacity / 100 / (d_j - d_i)` with
`d_j - d_i >= 4.5 km`. SOC-derived; negative values occur (regenerative gain
over a 5 km window) and are treated as real signal.

## 6. Feature set
Exactly 102 route-aware causal features (frozen in Step 7.7):
- 87 strictly causal onboard features (current/past windows).
- 15 conditionally causal route/terrain features (`next_1km/2km/5km_*`,
  static-geography look-ahead).
- `trip_phase` removed (trip-end leakage).
- Median imputation fitted on TRAIN+VALIDATION only.

## 7. Route-aware dependency
The 15 `next_*` route-aware features require upcoming route/DEM knowledge.
**Without route/DEM data the model degrades to the strict onboard set**
(GroupKFold MAE ≈ 0.05518 vs 0.04002 kWh/km route-aware). This is the single
most important operational constraint.

## 8. Model architecture
`ExtraTreesRegressor(n_estimators=300, max_depth=10, min_samples_leaf=3,
random_state=42, n_jobs=-1)` trained on TRAIN+VALIDATION (9,098 rows).

## 9. Validation methodology
- Trip-disjoint GroupKFold (grouped by trip_id) used for model selection in
  Step 7.6/7.7.
- Causal feature audit in Step 7.7 (0 future/target leakage; `trip_phase`
  trip-end leakage removed).
- One-time held-out test evaluation in Step 8 (marker-protected by
  `reports/.step8_test_evaluated`).

## 10. Final test performance
Held-out test, 1,537 samples, evaluated exactly once:

| Metric | Value | Baseline (global mean) | Improvement |
|---|---|---|---|
| MAE (kWh/km) | **0.04112** | 0.06187 | **+33.5%** |
| RMSE (kWh/km) | **0.05236** | 0.08219 | **+36.3%** |
| R² | **+0.5902** | −0.0096 | — |
| Bias (mean error) | **−0.00618** | — | — |
| Median absolute error | 0.03270 | — | — |
| Max absolute error | 0.15361 | — | — |

Vehicle-level:
- Dacia Spring: MAE 0.03638 (n = 1,044)
- Nissan Leaf: MAE 0.05116 (n = 493)

GroupKFold CV (Step 7.7 route-aware): MAE = 0.04002 ± 0.00103.

## 11. Known unavailable telemetry

The feature engineering and the model handle missing signals by design, but
several signals are not available in parts of the training data or in the
frozen schema:

- **Dacia Spring (DEVRT)**: speed, acceleration, motor power/torque/RPM,
  auxiliary power, regenerative power, and temperature columns are
  **UNAVAILABLE**; the model relies on the remaining signals and the
  imputation preprocessor for these rows.
- **Wind components**: unavailable in all datasets (no verified wind heading
  source); not part of the 102-feature set.
- **Traffic / weather / road conditions**: not present in any dataset.
- **JAC**: no SOC/SOH columns (not used for training).
- **TUM**: only 30/102 features reproducible; 72 require signals TUM does not
  expose (GPS/altitude route terrain, traction-motor, per-trip distance).

The inference API accepts optional telemetry fields and the feature builder
substitutes `NaN` for missing optional signals, which the median-imputation
preprocessor handles at runtime.

## 12. Explainability
- **Predictive importance** (not causal): top features are look-ahead terrain
  (`next_5km_uphill_frac`, `next_5km_gradient_pct`, `next_5km_net_elev_m`),
  current altitude, day-of-week, and time-of-day.
- Permutation importance (GroupKFold, MAE degradation on train+val) agrees:
  `next_5km_uphill_frac` first, then `next_5km_gradient_pct` and
  `next_5km_net_elev_m`.
- SHAP skipped: `shap` not installed; heavy dependency chain avoided.
  Permutation importance used instead.
- Local explanations: 5 representative train+val samples documented in
  `reports/step9_local_explanations.md`.

## 13. Range estimation
`src/inference/range_estimator.py`:
- `usable_energy_kwh = capacity * max(soc - reserve, 0) / 100` (default reserve 10%)
- `estimated_range_km = usable_energy_kwh / predicted_kwh_per_km`
- Uncertainty band from TRAIN+VAL residual quantiles (q10/q90): conservative
  and optimistic ranges (higher consumption → lower range).
- Rows with predicted consumption ≤ 0 (regen gain) are excluded from range.
- Validated: 0 ≤ SOC ≤ 100, capacity > 0, consumption > 0, 0 ≤ reserve < 100.

## 14. External validation status (TUM)
- Attempted in Step 10 against the third-party TUM EV UDS dataset.
- **BLOCKED**: only **30/102** frozen-model features are reproducible from TUM
  signals. Missing: 41 need GPS/altitude route terrain, 19 need traction-motor
  signals, 12 need per-timestamp trip/distance boundaries. The 5 km future
  target is also unavailable in TUM.
- Battery capacity used for target interpretation is a **derived fleet
  specification** (58 kWh from the dataset README), not a per-vehicle BMS
  readout.
- This is **not** a successful external validation. See
  `docs/step10_external_validation.md`.

## 15. Limitations
1. DEVRT is the primary training dataset.
2. Model is route-aware.
3. Upcoming terrain must be available from route/DEM information.
4. Dacia lacks some telemetry available for Nissan.
5. Target is SOC-derived.
6. Prediction horizon is 5 km.
7. Test R2 is 0.5902.
8. Nissan performance is weaker than Dacia.
9. Range estimate depends on predicted consumption.
10. Range is an estimate, not an OEM-certified value.
11. **TUM external validation BLOCKED** (30/102 features reproducible) — no
    cross-dataset validation.
12. Weather/wind information is limited.
13. Traffic information is not included.
14. Driver behaviour generalization may be limited.
15. Battery degradation/general SOH effects may require additional validation.
16. This is a prototype inference system, not a certified product.
17. **This system is an estimation tool and should not be treated as a
    safety-critical vehicle control system.**

## 16. Reproducibility
- `src/models/train_final_model.py`: full frozen training + one-time test eval.
- `src/analysis/step7_7_causal_audit.py`: feature causality audit.
- `src/analysis/step9_explainability.py`: importance + local explanations.
- `src/inference/range_estimator.py`, `src/inference/predictor.py`: inference.
- `src/inference/service.py` + `api/main.py`: production inference API.
- `random_state=42` everywhere; artifacts in `models/`.
- Tests: full suite **138 tests passing** (`python -m pytest -q`), including
  parsers, leakage/split audits, final model, TUM validator, feature builder,
  inference service, and API. Test set never re-evaluated.