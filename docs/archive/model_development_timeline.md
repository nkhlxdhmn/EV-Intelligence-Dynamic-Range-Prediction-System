# Model Development Timeline

STEP 12E — chronological summary of the project's development steps, their
objectives, key decisions, and results.

---

## Step 1–2: Dataset identification and inspection

- **Objective:** identify suitable EV datasets and verify their quality for
  energy-consumption modeling.
- **Key decision:** select **DEVRT** (Dacia Spring + Nissan Leaf, Basque
  Country routes) as the primary training dataset; keep **TUM** and **JAC**
  as secondary/inspection sources.
- **Result:** DEVRT provides 58 telemetry CSV trips with SOC, speed, altitude,
  temperature, and powertrain signals — sufficient for a route-aware
  consumption model. EDA figures produced in `reports/figures/eda/`.

## Step 3: DEVRT processing

- **Objective:** parse and standardize DEVRT telemetry into a common schema.
- **Key decision:** one standardized parquet per trip; quality flags preserved;
  define a unified schema (`configs/schema.yaml`).
- **Result:** `src/data/devrt_parser.py` + `data/interim/devrt/` (58
  standardized trips). A data-corruption issue was found and fixed (Step 7.6
  report). `docs/devrt_cleaning_report.md`.

## Step 4: JAC processing

- **Objective:** inspect and standardize the JAC dataset for potential use.
- **Key decision:** JAC telemetry quality was insufficient (missing battery
  SOC confidence, signal gaps) → **inspection only, not used for training**.
- **Result:** `src/data/jac_parser.py` + standardized output in
  `data/interim/jac/`. `docs/jac_cleaning_report.md`, `docs/jac_variable_analysis.md`.

## Step 5: TUM metadata inspection

- **Objective:** understand the TUM EV UDS dataset (98M rows, CUP/ID
  vehicles) and its signal catalog for a future external-validation attempt.
- **Key decision:** build a streaming extractor (PyArrow row-group by
  row-group) to stay memory-safe.
- **Result:** `scripts/tum_extractor.py`, signal catalog and value analysis
  (`docs/tum_signal_catalog.md`, `docs/tum_value_analysis.md`).

## Step 6: Initial feature engineering

- **Objective:** define the first feature set and the prediction target.
- **Key decision:** target = average energy consumption over the **next 5 km**
  (`target_future_energy_kwh_per_km`), computed from SOC deltas
  (`(soc_i - soc_j) * capacity / 100 / (d_j - d_i)` with `d_j - d_i >= 4.5 km`).
- **Result:** base feature catalog (SOC, altitude, gradient, terrain class)
  and initial engineering; `docs/feature_engineering_report.md`,
  `docs/target_definition.md`.

## Step 7: Feature expansion and optimization

- **Objective:** expand features (speed, temperature, powertrain, aux load,
  regen, windowed statistics) and validate the v2 feature matrix.
- **Key decision:** 97-feature v2 matrix; median imputation for missing
  telemetry; trip-level data quality verification.
- **Result:** 9,952 samples / 50 trips / 2 vehicles; negative targets (regen)
  analyzed and **kept** as valid signal (1.88% of samples). Feature
  completeness audit passed. `docs/feature_preparation.md`,
  `docs/step8_final_model_report.md`.

## Step 7.6: Model optimization

- **Objective:** optimize the modeling pipeline and confirm data quality after
  the DEVRT data-corruption fix.
- **Key decision:** re-verify the dataset after the corruption fix; establish
  stable baselines and model-selection protocol using the validation split.
- **Result:** optimization experiments and data audit
  (`reports/optimization_*`); baselines documented
  (`reports/baseline_results.md`).

## Step 7.7: Causal feature audit

- **Objective:** eliminate leakage — classify every feature as causal,
  conditionally causal (route-aware), or leakage.
- **Key decision:**
  - 87 CAUSAL (strict onboard),
  - 15 CONDITIONALLY_CAUSAL (`next_1km/2km/5km_*` terrain),
  - 1 TRIP_END_LEAKAGE (`trip_phase`) → **removed**.
  - Two frozen reduced sets: 102 route-aware + 87 strict onboard.
- **Result:** route-aware GroupKFold MAE **0.04002 ± 0.00103**; strict onboard
  MAE **0.05518 ± 0.00158**. `docs/step7_7_causal_audit.md`,
  `reports/step7_7_feature_causality_audit.csv`.

## Step 8: Final model + held-out test

- **Objective:** train the final model on the route-aware causal set and
  evaluate the held-out test set exactly once.
- **Key decision:** `ExtraTreesRegressor(n_estimators=300, max_depth=10,
  min_samples_leaf=3, random_state=42, n_jobs=-1)` on TRAIN+VALIDATION
  (9,098 rows); trip-disjoint test (1,537 rows); test evaluated once,
  marker-protected.
- **Result:**
  - MAE **0.04112** (baseline 0.06187 → **+33.5%**)
  - RMSE **0.05236** (baseline 0.08219 → **+36.3%**)
  - R² **+0.5902**, bias **−0.00618**
  - Dacia MAE 0.03638 (n=1044), Nissan MAE 0.05116 (n=493).
  - Frozen artifacts: `models/ev_energy_extratrees_route_aware.joblib`,
    `models/final_preprocessor.joblib`, `models/final_feature_list.json`.

## Step 9: Explainability + range estimator

- **Objective:** explain predictions and turn consumption into range.
- **Key decision:** permutation importance (GroupKFold) instead of SHAP
  (`shap` not installed); range estimator with SOC reserve + uncertainty band.
- **Result:** route-terrain features dominate importance;
  `src/inference/range_estimator.py` with reserve and q10/q90 band.
  `docs/step9_explainability_and_range.md`, `reports/step9_*`.

## Step 10: TUM external validation attempt

- **Objective:** externally validate the frozen model on the TUM dataset.
- **Key decision:** build a strict feature-compatibility validator that never
  fabricates missing signals.
- **Result:** **BLOCKED** — only **30/102** frozen-model features reproducible
  from TUM signals (41 need GPS/altitude terrain, 19 need traction-motor
  signals, 12 need per-timestamp trip/distance boundaries); 5 km target
  unavailable. Battery capacity derived (58 kWh fleet spec). This is
  **NOT** a successful external validation.
  `docs/step10_external_validation.md`, `reports/step10_*`.

## Step 11: Production inference architecture

- **Objective:** serve the frozen model as a prototype FastAPI inference
  service.
- **Key decision:** per-request feature builder reproducing the exact 102-feature
  contract; RouteTerrainProvider abstraction (no fabricated terrain);
  memory-safe single-model loading; Docker; labeled synthetic demo only.
- **Result:** `/health`, `/model/info`, `/predict`, `/docs`; 138-test suite;
  peak RSS ~198 MB (< 500 MB). `docs/step11_production_architecture.md`,
  `docs/inference_feature_contract.md`, `docs/api_usage.md`.

## Step 12: Finalization

- **Objective:** turn the project into a professional, resume-ready deliverable.
- **Key decisions:** structure audit, final README, model card, architecture
  and timeline docs, resume entry, interview Q&A, final project check, GitHub
  quality check, summary.
- **Result:** this document plus `docs/final_project_summary.md`,
  `docs/project_structure_audit.md`, `docs/resume_project_entry.md`,
  `docs/interview_questions.md`, `docs/final_system_architecture.md`,
  `README.md`, `docs/model_card.md`, `reports/step12_final_project_audit.json`.