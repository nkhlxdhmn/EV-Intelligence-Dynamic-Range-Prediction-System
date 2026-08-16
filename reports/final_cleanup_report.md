# FINAL REPOSITORY CLEANUP REPORT

- **Date**: 2026-08-16
- **Scope**: Final repository cleanup for GitHub publication. Remove redundant/experimental files,
  keep only the frozen model, inference API, dashboard, tests, final docs, and reproducibility files.
- **Safety rules applied**: every deletion was preceded by a reference check in source, tests,
  README/docs, Docker, compose, pytest.ini, scripts, API, and frontend. Anything uncertain was KEPT.
- **Frozen-model integrity**: verified by SHA-256 before and after cleanup (identical).

## 1. Frozen Model Integrity — PASS

| Artifact | SHA-256 (before = after) | Status |
|---|---|---|
| `models/ev_energy_extratrees_route_aware.joblib` | `27a0b7ab8a7fd5bc42ba2ac04d73be772880cdf2a64897108e343a57c6841319` | PASS |
| `models/final_preprocessor.joblib` | `3587e533e54f37790d8dff4e2025c5bb88a2dc7e219834e20f36cc703456c546` | PASS |
| `models/final_feature_list.json` | `d7a84483332627a01ef81c736ff3faf05d61ee099acaa259d1bf3402fbfb44d0` | PASS |

Identical to the Step 13 record (`reports/step13_model_integrity.json`). No model artifact was modified.

## 2. Tests — PASS

- `pytest -q` → **138 passed** (identical to the pre-cleanup baseline; 14 test files).
- Test fixture reports (`.step8_test_evaluated`, `step8_dataset_verification.json`,
  `step8_feature_importance.csv`, `step8_final_metrics.json`, `error_by_vehicle.csv`,
  `error_by_terrain.csv`, `step9_validation_baselines.csv`) were retained and the
  `.gitignore` was amended so these small fixture CSVs are committed.
- `models/step8/A_BASIC_XGB.joblib` (experiment model required by `test_step9_analysis.py`)
  was kept locally (git-ignored, regenerable).

## 3. API — PASS

- `/health` → 200
- `/model/info` → 200
- `/predict` → 200 with valid prediction
  `{"predicted_energy_kwh_per_km": 0.13959, "expected_range_km": 134.39, ...}`

## 4. Dashboard — PASS

- `/dashboard/` → 200 (title "EV Range Monitor")
- `/dashboard/style.css` → 200
- `/dashboard/app.js` → 200
- Predict flow confirmed working end-to-end.

## 5. Docker — PASS (source-level verification)

- Fixed a latent runtime bug: the Docker image copied `src/inference`, `api`, `models`, `frontend`
  but `src/inference/predictor.py` imports `scripts.comprehensive_feature_engineering` (which in turn
  imports `src/data/devrt_parser`). The `Dockerfile` now also copies:
  - `src/data/devrt_parser.py`
  - `scripts/comprehensive_feature_engineering.py`
- Verified the `/app` layout imports resolve (sys.path logic intact).
- `docker-compose.yml` unchanged (mounts no datasets; correct).

## 6. Files REMOVED

- **From git tracking (kept on disk, now git-ignored)** — raw datasets removed from the repo:
  - `dataset/DEVRT/` — 78 files untracked (`git rm --cached`, files remain locally)
  - `dataset/archive/dataset.csv` — untracked
  - `.gitignore` now ignores the whole `dataset/` directory.
- **Deleted** (duplicate venv + runtime artifacts):
  - `.venv1/` (14 MB duplicate virtual environment)
  - `logs/inference.log`, `logs/`
  - All `__pycache__/`, `*.pyc`, `.pytest_cache/`

## 7. Files ARCHIVED (preserved history, out of the active tree)

- **`docs/archive/` (46 items)**: 41 historical STEP/analysis markdown documents +
  `STEP7_COMPLETION_REPORT.md`, `STEP8_COMPLETION_REPORT.md`, `_run_jac.bat`, 4 exploratory
  notebooks (`01_dataset_inspection.ipynb`, `02a_devrt_processing.ipynb`,
  `02b_jac_processing.ipynb`, `02c_tum_extraction.ipynb`).
- **`reports/archive/` (43 items)**: intermediate/optimization/experiment reports +
  `figures/` (plots). Test fixtures and final reports stay in `reports/`.
- **`src/archive/analysis/` (14 modules)**: `optimization_*` (9), `step9_diagnosis`,
  `step9_test_evaluation`, `step9_figures_test`, `step9_figures_validation`,
  `check_feature_completeness`. (`step7_7_causal_audit.py` and `step9_explainability.py` kept —
  referenced by `model_card.md`/README).
- **`src/archive/models/` (3 modules)**: `dataset.py`, `distribution_analysis.py`,
  `train_experiments.py`. (`baseline.py`, `train_final_model.py` kept.)
- **`src/archive/data/` (3 modules)**: `tum_parser.py`, `verify_v2_dataset.py`,
  `analyze_negative_targets.py`. (`create_split.py`, `create_v2_splits.py`, `devrt_parser.py`,
  `jac_parser.py`, `schemas.py`, `tum_external_validator.py` kept — imported by tests/docs.)
- **`scripts/archive/` (2 modules)**: `run_eda.py`, `tum_metadata_extractor.py`.
  (`comprehensive_feature_engineering.py` [runtime-required], `feature_engineering.py` [documented],
  `generate_feature_reports.py` [documented], `run_inference_demo.py` [documented demo],
  `tum_extractor.py` [test-required] kept.)

## 8. Files RETAINED (active tree)

```
.
├── api/main.py                  # FastAPI app
├── configs/schema.yaml          # unified data schema
├── docs/                        # 13 final docs (architecture, api_usage, data_pipeline,
│                                #   model_card, interview_guide, resume_project_entry,
│                                #   final_project_status, github_release_checklist,
│                                #   inference_feature_contract, step10_external_validation,
│                                #   step7_7_causal_audit, devrt_cleaning_report) + archive/
├── frontend/                    # dashboard (index.html, style.css, app.js)
├── models/                      # 3 frozen artifacts (+ models/step8/ experiment models, ignored)
├── reports/                     # final evidence + test fixtures (+ archive/)
├── scripts/                     # 5 runtime/documented scripts (+ archive/)
├── src/
│   ├── analysis/                # step7_7_causal_audit, step9_explainability
│   ├── data/                    # devrt/jac parsers, splits, schemas, tum_external_validator
│   ├── evaluation/              # leakage_audit, split_audit
│   ├── inference/               # predictor, feature_builder, range_estimator, service, ...
│   └── models/                  # baseline, train_final_model
├── tests/                       # 14 pytest files (138 tests)
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── requirements.txt             # full dev/test env
├── requirements.inference.txt   # minimal API runtime
└── README.md
```

## 9. Configuration changes

- `.gitignore`: `dataset/` now ignored (was: only the TUM subdir + DEVRT tracked);
  added `!reports/*.csv` so test-fixture CSVs are committed despite the `*.csv` rule.
- `pytest.ini`: dropped stale `norecursedirs` entries (`.venv1`, `notebooks`).
- `Dockerfile`: added `src/data/devrt_parser.py` and
  `scripts/comprehensive_feature_engineering.py` to the image copy (runtime requirement).
- `README.md`: updated `src/analysis/` description to "causal audit & explainability analysis".

## 9b. React dashboard migration (post-cleanup)

The vanilla HTML/JS dashboard was converted to a **React + Vite** app in
`frontend/`:

- `frontend/src/` — React source (`App.jsx`, `useDashboard.js` hook, `EnergyChart.jsx`,
  `api.js`, `simulator.js`, `style.css`, `main.jsx`).
- `frontend/dist/` — production bundle (git-ignored; rebuilt via `npm run build`).
- `api/main.py` now serves `frontend/dist/` at `/dashboard/` (falls back to `frontend/`).
- `Dockerfile` is multi-stage: `node:20-alpine` builds the bundle, the python runtime
  copies only `frontend/dist/`.
- `.gitignore` ignores `node_modules/` and `frontend/dist/`; old `frontend/app.js` and
  root `style.css` were removed (superseded by the React sources).
- Behavior preserved: DEMO/LIVE modes, polling interval, Start/Pause/Reset, canvas
  energy chart, and all panels. Verified: 138 tests pass, `/dashboard/` 200,
  `/predict` 200, frozen-model hashes unchanged.

## 10. Remaining manual steps (for the user)

1. Review `git status` / `git diff` (staged dataset removals + README edit), then commit.
2. Initial commit will contain only tracked/whitelisted files; `dataset/`, `data/`, `logs/`,
   `.venv/`, `models/step8/*.joblib` stay local.
3. Optionally run the GitHub release checklist (`docs/github_release_checklist.md`) before pushing.