# EV Energy Consumption & Dynamic Range Prediction System

A leakage-controlled, route-aware machine-learning system that predicts an
electric vehicle's future energy consumption (kWh/km) over a 5 km horizon and
converts it into a dynamic remaining-range estimate. The model and inference
pipeline are served through a production-style FastAPI API with a real-time
telemetry dashboard.

---

## 1. Overview

The system predicts future EV energy consumption and estimates remaining
driving range using:

- **battery state** — State of Charge, usable capacity, power draw
- **driving behavior** — speed, acceleration, regenerative braking
- **vehicle telemetry** — motor power/torque/RPM, auxiliary loads
- **terrain** — elevation, gradient, road conditions
- **route-aware elevation information** — elevation ahead of the vehicle
- **environmental/context features** — ambient temperature, trip context

The output is an expected energy consumption rate (`kWh/km`) over the next
5 km of a planned route, which is converted into conservative / expected /
optimistic range estimates.

## 2. Architecture

```
Raw telemetry (DEVRT / TUM / JAC)
    → memory-safe processing (PyArrow, one file/vehicle at a time)
    → standardized data (configs/schema.yaml)
    → feature engineering (102 features)
    → causal/leakage audit (trip_phase removed)
    → ExtraTrees model (frozen)
    → energy prediction (kWh/km over 5 km)
    → range estimator (usable energy ÷ predicted consumption)
    → FastAPI (/health, /model/info, /predict)
    → dashboard (dashboard/, DEMO + optional LIVE)
```

See [docs/architecture.md](docs/architecture.md) for the detailed diagram and
the strict onboard-only alternative.

## 3. ML Problem

- **Target**: `target_future_energy_kwh_per_km` — average energy consumption
  over the next **5 km** of the trip.
- **Task**: regression (continuous value).
- **Why 5 km?** DEVRT average consumption is ~0.15 kWh/km. A 1% SOC change on
  a 33–62 kWh battery is ~0.33–0.62 kWh, so SOC ticks over roughly every
  2–4 km. A 1 km horizon therefore produces many degenerate "0 kWh" targets
  from integer SOC quantization, while a 5 km window yields stable SOC-delta
  readings without smoothing over terrain features too heavily.

## 4. Model

`ExtraTreesRegressor` (scikit-learn), frozen at STEP 8:

```
n_estimators = 300
max_depth    = 10
min_samples_leaf = 3
random_state = 42
n_jobs       = -1
```

Input: **102 route-aware causal features** (15 `next_*` route-aware elevation
features + 87 onboard/contextual features). `trip_phase` was removed after the
causal audit.

## 5. Results

Verified metrics only (frozen evaluation artifacts):

| Metric | DEVRT held-out test |
|---|---|
| MAE | **0.04112 kWh/km** |
| RMSE | **0.05236 kWh/km** |
| R² | **0.5902** |

Route-aware GroupKFold cross-validation (trip-level groups):

| Metric | Value |
|---|---|
| MAE | **0.04002 ± 0.00103** |

These are measured on the DEVRT held-out test set. They are **not** claimed as
real-world, universal EV accuracy numbers — see Limitations.

## 6. Leakage Prevention

- **Trip-level splitting** — no trip appears in both train and validation.
- **GroupKFold** — folds grouped by trip to prevent temporal leakage.
- **Future target separation** — target is computed from a 5 km future window
  that never crosses a trip boundary.
- **Causal feature audit** — each feature was audited for causality and
  availability at prediction time (docs/step7_7_causal_audit.md).
- **`trip_phase` removal** — `trip_phase` encoded the position within the
  trip, which is correlated with the future-window target (leakage); removed.
- **Route-aware vs strict onboard distinction** — route-aware features use
  upcoming elevation (valid when the route is known); the strict onboard set
  uses only signals available without route knowledge.

## 7. Route-aware Limitation

The best model uses **future terrain information** (route-aware features).
This is valid **only when route / DEM elevation information is available
before driving**. A strict onboard-only model (no route knowledge) performed
worse on the held-out test.

This limitation is deliberate and documented, not hidden: the system assumes
a planned route with elevation data is available. Without it, the API falls
back to a synthetic route provider in DEMO mode (labeled) and accuracy
degrades.

## 8. External Validation

External validation on the **TUM** dataset (A2/ID1/ID2, ~96 M rows) was
**BLOCKED**, not performed: only **30 of 102** frozen-model features could be
reproduced from TUM signals (41 require GPS/terrain, 19 require traction-motor
signals, 12 require distance/trip context), and the 5 km distance-based target
could not be constructed. TUM is therefore used for memory-safety engineering
only, not for cross-dataset model validation.

No successful cross-dataset validation is claimed. See
[docs/step10_external_validation.md](docs/step10_external_validation.md).

## 9. Memory Safety

- **PyArrow** for columnar/streaming I/O instead of loading whole CSVs into
  memory.
- **Row-group processing** — parquet files processed in bounded row groups.
- **One file / one vehicle at a time** — trips streamed independently.
- **Garbage collection** — `gc` + tracemalloc used to bound peak memory.
- **No full TUM load** — the ~96 M-row TUM dataset was never fully loaded into
  RAM; processing peak was ~197 MB (see `reports/step11_memory_report.json`).

## 10. API

FastAPI application in `api/main.py` (src/inference modules).

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | liveness + service status |
| `/model/info` | GET | model version, 102-feature contract |
| `/predict` | POST | telemetry + route terrain → energy & range estimate |

Full schema and examples: [docs/api_usage.md](docs/api_usage.md).

## 11. Dashboard

A real-time telemetry dashboard (React/Vite) is served at `/dashboard/` from
`dashboard/dist` (build output). It polls `/health`, `/model/info`, and
`/predict` and displays primary telemetry, battery, energy, range, route, and
driving conditions.

- **DEMO MODE** — built-in telemetry simulator (speed, SOC, temperature,
  altitude, consumption). Clearly labeled "DEMO MODE — SIMULATED TELEMETRY".
  Never presented as real vehicle data.
- **LIVE mode** — only activated when an actual telemetry source is connected
  (`?live=1&telemetry=...`); no live source is bundled, so LIVE is not shown
  by default.

Rebuild the dashboard after changing the React source (the API serves the
pre-built `dashboard/dist`):

```bash
cd dashboard
npm install
npm run build     # writes dashboard/dist
```

For development, `npm run dev` starts a Vite dev server on :5173 that proxies
API calls to a locally running backend (http://127.0.0.1:8000).

## 12. Docker

Local deployment via Docker:

```bash
docker compose up --build
# API:  http://localhost:8000
# Docs: http://localhost:8000/docs
# Dashboard: http://localhost:8000/dashboard/
```

The image runs as a non-root user with a healthcheck. Runtime dependencies are
pinned in `requirements.inference.txt`; the full dev/test environment is in
`requirements.txt`.

## 13. Testing

`pytest -q` (config: `pytest.ini`, `testpaths = tests`):

```
138 passed
```

Covers: API endpoints, inference service, feature builder (102-feature
contract), range estimator, leakage/split audits, baseline comparison, frozen
model integrity, parsers, and TUM extraction/validator. The STEP 8 test set
is evaluated once and never re-evaluated.

## 14. Limitations

- Metrics are from the DEVRT dataset only; not universal EV accuracy.
- Route-aware features require route/DEM data before driving.
- TUM external validation was blocked (feature/target incompatibility).
- No live CAN/OBD integration — the dashboard DEMO uses a simulator; LIVE
  requires a future telemetry feed.
- This system is an **estimation tool and should not be treated as a
  safety-critical vehicle control system**.

---

## Project Structure

```
├── api/                 # FastAPI app (main.py)
├── src/
│   ├── data/            # parsers, split creation, TUM extraction
│   ├── analysis/        # causal audit & explainability analysis
│   ├── evaluation/      # leakage & split audits
│   ├── models/          # training & baseline experiments
│   └── inference/       # frozen-model inference, features, range, API layer
├── dashboard/            # React/Vite telemetry dashboard (served from dist/)
├── configs/schema.yaml  # unified data schema
├── docs/                # model card, architecture, interview guide, API docs
├── models/              # frozen artifacts (ev_energy_extratrees_route_aware.joblib, ...)
├── reports/             # evaluation evidence, audits, memory reports
├── tests/               # pytest suite (138 tests)
├── scripts/             # demos, EDA, feature reports, TUM extractors
├── Dockerfile
├── docker-compose.yml
├── requirements.txt            # full dev/test environment
├── requirements.inference.txt  # minimal API runtime
└── pytest.ini
```

## Getting Started

```bash
# 1. Install (Python 3.12+)
pip install -r requirements.txt

# 2. Start the API
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 3. Build the dashboard (React)
cd dashboard && npm install && npm run build && cd ..

# 4. Open the dashboard
open http://localhost:8000/dashboard/   # press Start (DEMO MODE)

# 5. Run tests
pytest -q
```

## License / Data

- Raw datasets (DEVRT under `dataset/DEVRT/`, the third-party TUM dataset
  `dataset/electric-vehicle-uds-dataset-main/`) are kept locally only and are
  **not** committed (large, own licenses). See `dataset/` for the source.