# Resume-Ready Project Description

Two versions of the project description for a resume / LinkedIn / portfolio.
All claims are supported by the repository. **Do not** claim 90% accuracy,
successful TUM validation, real-world production deployment, or live vehicle
integration.

Facts backing every version:

- Model: ExtraTreesRegressor (300 trees, max_depth 10, min_samples_leaf 3),
  102 route-aware causal features (87 strictly onboard + 15 route-aware
  look-ahead), `trip_phase` removed.
- Held-out test (1,537 samples, evaluated exactly once): MAE 0.04112 kWh/km,
  RMSE 0.05236, R² 0.5902; +33.5% MAE / +36.3% RMSE vs global-mean baseline
  (MAE 0.06187). Route-aware GroupKFold CV: MAE 0.04002 ± 0.00103.
- Trip-disjoint train/val/test split + GroupKFold + causal/leakage audit.
- FastAPI inference service (`/health`, `/model/info`, `/predict`),
  memory-safe PyArrow pipeline (~198 MB peak), Docker, 138 automated tests,
  telemetry dashboard (DEMO + optional LIVE).
- TUM external validation attempted and **blocked** (30/102 features
  reproducible) — described as a limitation, never as a success.

---

## Version 1 — 2-bullet resume version (ML + engineering)

- **ML (EV energy-consumption prediction):** Built a leakage-controlled
  model predicting 5 km-ahead EV energy consumption from 102 causal features
  (87 onboard + 15 route-aware terrain) extracted from real Dacia Spring /
  Nissan Leaf telemetry; ExtraTreesRegressor reached MAE 0.04112 kWh/km,
  RMSE 0.05236, R² 0.5902 on a trip-disjoint held-out test (baseline
  0.06187), using GroupKFold CV and a feature-causality audit that removed
  trip-end leakage.
- **Engineering (FastAPI + PyArrow):** Shipped the frozen model in a
  memory-safe FastAPI inference service (`/predict`, `/health`, `/model/info`)
  with Pydantic validation, feature-contract enforcement, a ~198 MB-peak
  PyArrow streaming pipeline, Docker packaging, a real-time telemetry
  dashboard, and 138 passing tests.

## Version 2 — 3-bullet strong version

- **ExtraTrees + 102 route-aware causal features:** Engineered 102
  leakage-safe features from real EV telemetry — 87 strictly onboard (speed,
  motor, SOC deltas, altitude) plus 15 look-ahead terrain features
  (`next_1km/2km/5km_*`) — and trained an ExtraTreesRegressor that predicts
  5 km-ahead consumption at MAE 0.04112 kWh/km, RMSE 0.05236, R² 0.5902 on a
  one-time trip-level held-out test.
- **Leakage prevention with GroupKFold:** Enforced trip-disjoint
  train/validation/test splits and GroupKFold CV (grouped by trip), and ran a
  causal feature audit that removed trip-end leakage (`trip_phase`) and
  separated onboard vs route-dependent features; route-aware CV MAE
  0.04002 ± 0.00103.
- **FastAPI + memory-safe PyArrow pipeline:** Delivered the frozen model via
  a FastAPI inference API (`/predict`, `/health`, `/model/info`) with
  Pydantic validation and feature-contract enforcement, a memory-safe PyArrow
  streaming pipeline (peak ~198 MB, no full-corpus load), Docker packaging, a
  telemetry dashboard, and 138 automated tests.

## Guidance for interviews

- Use "prototype inference system" rather than "production deployment".
- If asked "did you validate on TUM?", answer honestly: attempted, blocked by
  feature incompatibility (30/102 reproducible); the model is DEVRT-only.
- The 33.5% improvement is over the **global-mean baseline**, not over another
  model — say this explicitly.
- R² 0.59 is on a held-out trip-level test of 1,537 samples; the strict
  onboard (no route data) variant is GroupKFold MAE ~0.05518 kWh/km.
- State the route-aware dependency: best accuracy requires route/DEM elevation
  before driving; without it the system degrades to the onboard-only set.