# Final Project Status

## PROJECT
EV Energy Consumption & Dynamic Range Prediction System

## ML
ExtraTrees Regression

## TARGET
5 km future energy consumption (target_future_energy_kwh_per_km)

## FEATURES
102 route-aware causal features (87 strictly onboard + 15 route-aware
look-ahead); `trip_phase` removed

## TEST (DEVRT held-out, 1,537 samples, evaluated once)
MAE 0.04112 kWh/km
RMSE 0.05236 kWh/km
R² 0.5902

## CV (Route-aware GroupKFold, trip-disjoint)
MAE 0.04002 ± 0.00103

## EXTERNAL VALIDATION
TUM blocked due feature/target incompatibility (30/102 features reproducible;
41 need GPS/terrain, 19 need traction-motor, 12 need per-trip distance; 5 km
target unavailable). No cross-dataset validation claimed.

## DEPLOYMENT
FastAPI + Docker + telemetry dashboard (DEMO simulator + optional LIVE)

## MEMORY
Memory-safe PyArrow processing — one file/vehicle at a time, row-group
streaming, explicit gc; peak ~79–197 MB, no full TUM (~96 M rows) load

## TESTS
138 passed (pytest -q, 2026-08-16) — API, inference service, feature contract,
range estimator, parsers, leakage/split audits, TUM extractor/validator

## MODEL
Frozen — artifacts verified unmodified (sha256 recorded in
reports/step13_model_integrity.json); DEVRT test set never re-evaluated
(reports/.step8_test_evaluated intact)

## Integrity
- Model artifacts frozen: `models/ev_energy_extratrees_route_aware.joblib`,
  `models/final_preprocessor.joblib`, `models/final_feature_list.json`
- Hashes recorded: reports/step13_model_integrity.json
- Security scan: no secrets found (reports/step13_security_audit.json)
- Repository audit: duplicates/temp removed (reports/step13_repository_audit.json)

## Honesty constraints
- Metrics are DEVRT-only, not universal EV accuracy.
- Route-aware dependency: best accuracy requires route/DEM elevation before
  driving; strict onboard set is worse (GroupKFold MAE ~0.05518).
- DEMO telemetry is simulated; no live CAN/OBD integration exists.
- This system is an estimation tool and should not be treated as a
  safety-critical vehicle control system.