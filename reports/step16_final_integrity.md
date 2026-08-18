# STEP 16F — Final ML Integrity Report (6-prompt engineering batch)

- **Date**: 2026-08-18
- **Scope**: Confirm the frozen model was never modified during the 6-prompt batch
  (repo audit, physics simulator, LIVE telemetry, dashboard redesign, 50-scenario
  validation, final cleanup). No training, evaluation, model reload, or re-split
  was performed.

## 1. Frozen model integrity — PASS

| Artifact | SHA-256 | Matches Step 13 |
|---|---|---|
| `models/ev_energy_extratrees_route_aware.joblib` | `27a0b7ab…c6841319` | yes |
| `models/final_preprocessor.joblib` | `3587e533…c703456c546` | yes |
| `models/final_feature_list.json` | `d7a84483…fbfb44d0` | yes |

The 102-feature inference contract is unchanged.

## 2. Test suite — PASS

`python -m pytest -q` → **280 passed** (simulator 28, live reader 14, API 23,
plus 4 new P5 realism regression tests).

## 3. P5 validation — PASS

- `reports/step16_simulator_validation.json`: **300/300** predictions through the
  real `/predict` pipeline (50 scenarios x 6 checkpoints).
- Model hash unchanged; determinism same-seed within 1e-9 (ULP jitter from
  `n_jobs=-1` tree aggregation; physics deterministic).
- 11/300 (3.7%) predictions had non-positive consumption (regen-dominated /
  boundary operating points); all safely mapped to range 0.0 with None band per
  the documented pipeline contract. Never overstates range.

## 4. Simulator fixes (model untouched)

- Stop segments hold a 6 km/h creep floor instead of a full stop (brake-zone bug
  kept the vehicle pinned at speed 0).
- Low-speed regen fade: 0 below 8 km/h, full at 25 km/h.
- `route_terrain_input` stays schema-valid (>= 2 points, `SIMULATOR_ROUTE`) at
  route end.

## 5. Cleanup

- Removed orphaned `src/inference/live_feature_builder.py` (0 references; F8.4).
- Removed temporary `probe_neg.py`.

## 6. Honesty rules verified

- Simulated data labeled `SIMULATOR` / `SIMULATOR_ROUTE` everywhere.
- LIVE endpoints only surface real connected sources; no fabricated telemetry or
  terrain; terrain source validator rejects FABRICATED / FAKE / SYNTHETIC_DEMO.

**Status: PASS** — artifacts bit-identical to Step 13, suite green, 300/300
validation through the real frozen model.