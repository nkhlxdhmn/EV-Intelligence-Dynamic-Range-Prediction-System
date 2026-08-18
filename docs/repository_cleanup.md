# Repository Cleanup

Production-readiness pass over the repository. Scope: remove historical,
duplicate, generated, and experimental artifacts while preserving everything
required to run the inference API, dashboard, simulator, LIVE telemetry, load
the frozen model, build the production feature vector, validate the inference
contract, deploy, run essential tests, and understand the final architecture.

The frozen model was **not** retrained or modified. The 102-feature contract
was **not** changed. Runtime-required files were **not** removed. Every
deletion was preceded by a reference scan of the remaining tree.

## Removed

| Area | Removed |
|---|---|
| Docs | `docs/archive/` (55 files: notebooks, step reports, catalogs, strategy docs), `api_usage.md`, `data_pipeline.md`, `devrt_cleaning_report.md`, `final_project_status.md`, `interview_guide.md`, `multidataset_validation_strategy.md`, plus previously-deleted `github_release_checklist.md`, `inference_feature_contract.md`, `model_card.md`, `multidataset_feature_strategy.md`, `resume_project_entry.md`, `vehicle_integration_guide.md`. Content consolidated into the final 5 docs. |
| Reports | `reports/archive/` (figures + historical step reports), `final_cleanup_report.md`, `jac_target_feasibility.json`, `tum_target_feasibility.json`, `multidataset_feature_compatibility.csv`, `multiev_validation_matrix.csv`, `step10_*`, `step11_memory_report.json`, `step12_*`, `step13_*` (except `step13_model_integrity.json`), `step14_*`, `step15_memory_report.json`, `step8_error_analysis.csv`. |
| Scripts | `scripts/archive/`, `feature_engineering.py`, `generate_feature_reports.py`, `tum_extractor.py`. |
| Source | `src/archive/`, `src/analysis/` (causal/explainability audits), `src/features/`, `src/terrain/`, `src/route/` (old route subsystem), `src/models/baseline.py`, `src/data/{jac_parser,unified_schema,schemas,tum_external_validator,create_split,create_v2_splits}.py`. |
| Tests | `test_baseline.py`, `test_jac_parser.py`, `test_route_schema.py`, `test_tum_external_validator.py`, `test_tum_extraction.py`, `test_unified_schema.py` (79 tests; suite went 280 → 201, all passing). |
| Root | `add_derivation.py`, `write_schema.py`, `pyproject.toml` (git-ignored stub). |
| Frontend | Unused API client functions (`postLiveConnect`, `postLiveDisconnect`, `postLiveReconnect`, `fetchLiveHealth`) and their API constants. |
| Dev artifacts | `__pycache__/**`, `.pytest_cache/`, `logs/` (git-ignored). |

## Preserved

Everything required to run and validate the system:

- **Runtime**: `api/main.py`, `src/inference/*`, `src/monitoring/*`,
  `src/telemetry/*`, `src/simulator/*`, `src/data/devrt_parser.py`,
  `scripts/comprehensive_feature_engineering.py`.
- **Training reproducibility**: `src/models/train_final_model.py`,
  `src/evaluation/{leakage_audit,split_audit}.py`.
- **Model artifacts**: `models/ev_energy_extratrees_route_aware.joblib`,
  `final_preprocessor.joblib`, `final_feature_list.json` (hashes unchanged,
  see `reports/step13_model_integrity.json` and
  `reports/step16_final_integrity.json`).
- **Configs**: `configs/{schema,telemetry_schema,terrain_schema}.yaml`.
- **Reports** (validation evidence + test fixtures): `step13_model_integrity.json`,
  `step16_final_integrity.{json,md}`, `step16_simulator_validation.{json,md}`,
  `step11_inference_audit.json`, `step7_7_feature_causality_audit.csv`,
  `step9_trainval_residual_quantiles.json` (loaded at runtime),
  `step15_{ood_thresholds,reference_statistics,validation}.json`,
  `step8_{final_metrics,dataset_verification}.json`,
  `step8_feature_importance.csv`, `step9_{permutation_importance,test_summary}.json`,
  `step9_validation_baselines.csv`, `step9_local_explanations.md`,
  `error_by_vehicle.csv`, `error_by_terrain.csv`, `.step8_test_evaluated`.
- **Local fixtures**: `data/`, `dataset/` (git-ignored; required by the
  frozen-model verification tests and training reproducibility).
- **Tests**: 17 files / 201 tests (API, telemetry, simulator, feature
  contract, range estimator, leakage/split audits, frozen-model integrity).
- **Docs**: the final set below.

## Consolidated

- `docs/` reduced from 59 tracked files to exactly 5:
  - `architecture.md` — system design and data-flow guardrails.
  - `inference.md` — inference pipeline + full 102-feature contract
    (consolidates `inference_feature_contract.md`).
  - `telemetry.md` — LIVE telemetry layer (consolidates live docs).
  - `deployment.md` — Docker / local deployment, env config.
  - `vehicle_integration.md` — vehicle signal integration guide
    (consolidates `vehicle_integration_guide.md`).
- README rewritten to a concise production-facing overview (no historical
  narrative).

## Fixed

- `Dockerfile` now copies the full `src/` tree. Previously `src/monitoring`
  (imported by `src/inference/service.py`) and `src/simulator` (used by the
  `/simulator/*` endpoints) were missing from the image, which would have
  broken the Docker build at import time.

## Validation

- Backend: `python -m pytest -q` → **201 passed**.
- Frontend: `npm install` + `npm run build` (regenerates `dashboard/dist`).
- Model: `models/` SHA-256 unchanged; feature count/order unchanged
  (102 features); fixed-prediction sanity check passes.
- Simulator: starts / resets / randomizes / predicts; scenario IDs unique per
  seed; determinism within tolerance.
- LIVE: disconnected state reported honestly; no fabricated telemetry;
  API functional without hardware.
- API: `/health`, `/model/info`, `/predict`, simulator and live endpoints
  respond; Docker image builds and `docker compose config` is valid.

## ML integrity

No training or evaluation was performed during cleanup. The frozen
`models/` artifacts are byte-identical to the Step 13 record
(see `reports/step16_final_integrity.json`).