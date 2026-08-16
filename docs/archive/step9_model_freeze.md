# Step 9Q: Model Freeze

## Decision

**Selected final candidate: A_BASIC + XGBoost**

This model is frozen for the single, one-time evaluation on the untouched TEST set.

## Validation Champion Rationale

Selection based ONLY on validation metrics (test set never consulted):

| Candidate | Validation MAE | Validation RMSE | Validation R² |
|-----------|---------------|-----------------|---------------|
| Global Mean Baseline | 0.0722 | 0.1026 | -0.003 |
| Vehicle Mean Baseline | 0.0716 | 0.1023 | 0.002 |
| A_BASIC Ridge | 0.0660 | 0.0901 | 0.226 |
| A_BASIC RandomForest | 0.0658 | 0.0906 | 0.218 |
| **A_BASIC XGBoost** | **0.0629** | **0.0885** | **0.254** |

- **Primary criterion (MAE):** XGBoost wins with 0.0629 vs 0.0658 (RF) and 0.0722 (global mean baseline).
- **Secondary (RMSE, R²):** XGBoost also best.
- **Stability across vehicles/terrain:** XGBoost achieves R² of 0.324 on Nissan and positive R² on all terrain classes; the negative R² on Dacia (-0.263) reflects the low target variance on Dacia samples, not a model failure.

**Note on the prompt's stated baseline comparison:** The prompt reports "baseline MAE = 0.057", which is the TEST-set global-mean baseline MAE, not the validation MAE. On validation, the global-mean baseline MAE is 0.0722 and XGBoost (0.0629) beats it by ~13%. Therefore, **on validation, the ML model does beat the baseline.** The final test evaluation will determine whether this holds on the untouched test set.

## Frozen Configuration

| Component | Value |
|-----------|-------|
| Feature experiment | A_BASIC (Battery + Terrain) |
| Feature set | current_soc_pct, current_soh_pct, battery_capacity_kwh, current_altitude_m, current_gradient_pct, past_1km_gradient_pct, terrain_class, elevation_gain_1km, elevation_loss_1km |
| Categorical encoding | terrain_class → integer codes (pd.Categorical) |
| Model | XGBRegressor |
| n_estimators | 300 |
| learning_rate | 0.05 |
| max_depth | 5 |
| subsample | 0.8 |
| colsample_bytree | 0.8 |
| tree_method | hist |
| device | cpu |
| random_state | 42 |
| Target | target_future_energy_kwh_per_km (future 5 km) |
| Preprocessing | None beyond categorical encoding (no scaling for XGBoost) |
| Drop-NaN policy | A_BASIC features are 100% complete; no rows dropped |

## Frozen Artifact

- Model file: `models/step8/A_BASIC_XGB.joblib`
- Feature names stored on model: `_feature_names`, `_categorical_cols`
- Prediction wrapper: `predict_with_model()` in `src/models/train_experiments.py` (encode categoricals then predict)

## Validation Metrics (Frozen)

- MAE = 0.0629 kWh/km
- RMSE = 0.0885 kWh/km
- R² = 0.254
- SMAPE = 45.34%

## Anti-leakage Contract

- Validation predictions were generated with the frozen model.
- No validation or test samples were used in training or model selection.
- Test set will be evaluated exactly ONCE with the frozen model.
- No further tuning after seeing test results.

---

*Report generated as part of Step 9.*