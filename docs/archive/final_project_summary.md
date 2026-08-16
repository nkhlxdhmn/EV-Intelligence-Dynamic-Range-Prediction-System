# Final Project Summary

STEP 12J — definitive summary of the EV Intelligence & Dynamic Range
Prediction System at project completion (2026-08-16).

---

## PROJECT
**EV Intelligence & Dynamic Range Prediction System** — a leakage-controlled,
route-aware machine-learning system that predicts an EV's average energy
consumption over the next 5 km and converts it into a dynamic remaining-range
estimate, served through a memory-safe FastAPI inference API.

## FINAL MODEL
`ExtraTreesRegressor(n_estimators=300, max_depth=10, min_samples_leaf=3,
random_state=42, n_jobs=-1)` — version `ev-energy-devrt-v1`, trained on
TRAIN+VALIDATION (9,098 rows; Dacia Spring + Nissan Leaf, DEVRT).

## FINAL TEST
Held-out test, 1,537 samples, evaluated **exactly once**:

| Metric | Value |
|---|---|
| MAE | **0.04112 kWh/km** |
| RMSE | **0.05236 kWh/km** |
| R² | **0.5902** |
| Bias (mean error) | **−0.00618** |
| Median abs. error | 0.03270 |
| Max abs. error | 0.15361 |

## BASELINE
Global-mean baseline: MAE **0.06187** kWh/km, RMSE **0.08219**, R² −0.0096.

## IMPROVEMENT
- **+33.5%** MAE (0.04112 vs 0.06187)
- **+36.3%** RMSE (0.05236 vs 0.08219)
- Vehicle-level held-out: Dacia MAE 0.03638 (n=1044); Nissan MAE 0.05116
  (n=493).

## FEATURES
- **102** route-aware causal features (frozen contract,
  `models/final_feature_list.json`)
- **87** strict onboard causal features (current/past windows)
- **15** route-aware terrain/look-ahead features (`next_1km/2km/5km_*`)
- `trip_phase` removed (TRIP_END_LEAKAGE)
- 0 future leakage, 0 target leakage (Step 7.7 causal audit)

## EXPLAINABILITY
**Permutation importance** (GroupKFold, MAE degradation). Top predictors:
`next_5km_uphill_frac`, `next_5km_gradient_pct`, `next_5km_net_elev_m`,
current altitude, day-of-week, time-of-day. SHAP skipped (dependency
weight); local explanations documented.

## RANGE ESTIMATION
`src/inference/range_estimator.py`:
```
usable_energy_kwh = capacity * max(soc - reserve, 0) / 100   # reserve default 10%
expected_range_km  = usable_energy_kwh / predicted_kwh_per_km
```
Plus an optional uncertainty band from train+val residual quantiles
(conservative/optimistic). Consumption ≤ 0 → 0 range.

## API
FastAPI inference service (`api/main.py`): `GET /health`, `GET /model/info`,
`POST /predict`, `GET /docs`. Pydantic-validated inputs; rejects fabricated
route terrain; clean error responses; Docker deployment. RouteTerrainProvider
abstraction (synthetic provider DEMO-only).

## TESTS
**138 tests passing** (`python -m pytest -q`) — parsers, leakage/split
audits, baselines, final model (without re-evaluating the test set), TUM
validator, range estimator, feature builder, inference service, API.

## MEMORY
**~198 MB** peak RSS for the production inference process
(`reports/step11_memory_report.json`; target < 500 MB). Training/data
pipeline is memory-safe: one trip at a time, streaming via PyArrow.

## EXTERNAL VALIDATION
**TUM — BLOCKED.** Only 30/102 frozen-model features reproducible from TUM
signals (41 need GPS/altitude terrain, 19 need traction-motor signals, 12
need per-timestamp trip/distance boundaries); 5 km future target unavailable.
Battery capacity derived (58 kWh fleet spec). This is **not** a successful
external validation — see `docs/step10_external_validation.md`.

## LIMITATIONS
1. DEVRT-only training (two vehicles, one region).
2. Route-aware: requires upcoming route/DEM terrain; strict onboard MAE
   degrades to ~0.055 kWh/km.
3. TUM external validation blocked (30/102 features).
4. SOC-derived target with derived 58 kWh fleet capacity.
5. 5 km horizon (short-horizon).
6. Weather/traffic not included.
7. Nissan weaker than Dacia.
8. Prototype inference system — not OEM-certified, no live vehicle
   integration, no real-world deployment claims.

## KEY DOCUMENTATION
- `README.md` — full project overview (24 sections).
- `docs/model_card.md` — model facts, assumptions, limitations.
- `docs/final_system_architecture.md` — end-to-end architecture.
- `docs/model_development_timeline.md` — steps 1–12.
- `docs/resume_project_entry.md` — 1-line / 2-bullet / 4-bullet versions.
- `docs/interview_questions.md` — 30 Q&A.
- `docs/project_structure_audit.md` — structure + cleanup.
- `docs/step10_external_validation.md`, `docs/step11_production_architecture.md`,
  `docs/inference_feature_contract.md`, `docs/api_usage.md`.
- `reports/step12_final_project_audit.json` — final verification.
- `reports/.step8_test_evaluated` — one-time test marker (preserved).