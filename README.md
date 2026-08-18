# EV Intelligence & Dynamic Range Prediction System

Route-aware EV energy-consumption and dynamic range prediction, served through
a FastAPI inference API and a real-time React dashboard.

The system predicts an electric vehicle's average energy consumption
(`kWh/km`) over the next 5 km of a planned route using a frozen, leakage-audited
ExtraTrees model, then converts it into conservative / expected / optimistic
remaining-range estimates.

> **Prototype status** — validated on the DEVRT dataset only. Not a
> safety-critical vehicle control system; do not treat predictions as universal
> EV accuracy.

---

## Features

- **Frozen ML pipeline** — 102 causal route-aware features, `ExtraTreesRegressor`
  (saved in `models/`, never retrained).
- **FastAPI inference service** — validated `POST /predict`, model health/info,
  payload-size limits, clean error responses, audited inference logging.
- **Physics simulator (demo)** — backend `src/simulator/` drives the dashboard
  SIMULATOR mode; every sample is honestly labeled `SIMULATOR` /
  `SIMULATOR_ROUTE`. No client-side telemetry.
- **LIVE telemetry layer** — continuous reader with per-signal quality
  assessment (VALID / STALE / MISSING / …), rolling causal buffer, and
  OBD-II / CAN / telematics adapters. Never fabricates a value; disconnected
  state is surfaced honestly.
- **Monitoring** — OOD detection, PSI drift monitoring, sensor-quality rules
  derived from train+validation statistics.
- **React dashboard** — engineering console served at `/dashboard/` (SIMULATOR
  demo by default; LIVE only behind `?telemetry=1` with a real source).

## Architecture

```
Telemetry (SIMULATOR or LIVE) + route terrain
        ↓
FastAPI (/predict, /live/*, /simulator/*)
        ↓
Feature Builder (102 causal features, configs/schema.yaml)
        ↓
Frozen preprocessor (median imputation) + ExtraTrees model
        ↓
Energy consumption prediction (kWh/km @ 5 km)
        ↓
Range estimator (usable energy / consumption, reserve, band)
        ↓
Dashboard (SIMULATOR + optional LIVE) / inference audit log
```

Detailed diagrams: [docs/architecture.md](docs/architecture.md).

## Project structure

```
├── api/                 # FastAPI app (health, model, predict, live, simulator)
├── src/
│   ├── inference/       # feature builder, predictor, range estimator, service, schemas
│   ├── telemetry/       # readers, adapters, quality, normalizer, buffer, recorder
│   ├── monitoring/      # OOD, drift, sensor-quality monitoring
│   ├── simulator/       # physics-based demo simulator (scenario, route, physics)
│   ├── data/            # devrt_parser (training-data tooling)
│   ├── evaluation/      # leakage & split audits
│   └── models/          # train_final_model (reproducibility only)
├── dashboard/           # React/Vite dashboard (served from dist/)
├── scripts/             # feature engineering + simulator validation
├── configs/             # schema, telemetry-schema, terrain-schema YAML
├── models/              # frozen artifacts (model, preprocessor, feature list)
├── reports/             # validation evidence, integrity reports, audit fixtures
├── tests/               # pytest suite (201 tests)
├── docs/                # architecture, inference, telemetry, deployment, vehicle integration
├── Dockerfile
├── docker-compose.yml
├── requirements.txt            # full dev/test environment
├── requirements.inference.txt  # minimal API runtime
└── pytest.ini
```

## ML model

- **Input**: 102 route-aware causal features (87 onboard + 15 `next_*` route
  terrain). Authoritative list: `models/final_feature_list.json`.
- **Task**: regression of average consumption over the next 5 km.
- **Artifacts** (frozen, SHA-256 recorded in `reports/step13_model_integrity.json`):
  `ev_energy_extratrees_route_aware.joblib`, `final_preprocessor.joblib`,
  `final_feature_list.json`.
- **Verified metrics** (DEVRT held-out test):

  | Metric | Value |
  |---|---|
  | MAE | 0.04112 kWh/km |
  | RMSE | 0.05236 kWh/km |
  | R²   | 0.5902 |

- **Route-aware dependency**: the best model needs planned-route/DEM elevation
  **before driving**. Without route terrain the API does not fabricate it; in
  SIMULATOR mode terrain is synthetic and clearly labeled.

## Installation

Requires Python 3.12+ and Node 18+.

```bash
# 1. Python dependencies
pip install -r requirements.txt          # dev/test
pip install -r requirements.inference.txt  # runtime only

# 2. Dashboard
cd dashboard && npm install && npm run build && cd ..
```

## Running

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
# API:        http://localhost:8000
# Docs:       http://localhost:8000/docs
# Dashboard:  http://localhost:8000/dashboard/
```

or Docker:

```bash
docker compose up --build
```

## Dashboard

Open `/dashboard/` and press **Start**.

- **SIMULATOR mode (default)** — the backend physics simulator
  (`src/simulator/`) drives telemetry and route terrain via
  `/simulator/reset` and `/simulator/step`; predictions come from the real
  frozen model through `/predict`. All demo data is labeled `SIMULATOR`.
- **LIVE mode** — append `?telemetry=1` to the dashboard URL. It reads
  `/live/status`, `/live/telemetry`, and `/live/prediction` from a connected
  telemetry source. With no source connected the dashboard shows an honest
  OFFLINE state; nothing is fabricated.

Rebuild after frontend changes: `cd dashboard && npm run build` (the API serves
`dashboard/dist`). For development, `npm run dev` starts Vite on :5173 proxying
to a local backend.

## Simulator

The physics simulator (`src/simulator/`) produces causally-correct telemetry:
realistic speed/acceleration profiles, a low-speed regen fade (no regen below
8 km/h), energy balance checks, and deterministic seeded scenarios. Each sample
is labeled `SIMULATOR` and never presented as real vehicle data. Validation:
`scripts/step16_simulator_validation.py`, evidence in
`reports/step16_simulator_validation.md`.

## LIVE telemetry

LIVE sources connect through `/live/connect` (OBD-II, CAN, or telematics
adapters). Signals are normalized, quality-assessed, and fed into a rolling
causal buffer. Prediction requires `soc_pct` + `vehicle_speed_kmh` VALID and
fresh, plus route terrain; otherwise the API returns an explicit
`INSUFFICIENT_TELEMETRY` / `ROUTE_TERRAIN_UNAVAILABLE` status. See
[docs/telemetry.md](docs/telemetry.md) and
[docs/vehicle_integration.md](docs/vehicle_integration.md).

## Testing

```bash
pytest -q        # 201 passed
```

Covers API endpoints (including live-telemetry and simulator endpoints),
inference service, feature-builder contract, range estimator, leakage/split
audits, frozen-model integrity, telemetry reader quality/staleness/reconnect,
and the physics simulator (determinism, energy balance, causality).

## Limitations

- Metrics measured on the DEVRT dataset only.
- Route-aware features require route/DEM data before driving.
- TUM cross-dataset validation was blocked by feature/target incompatibility.
- LIVE requires a real telemetry source; nothing is fabricated when offline.
- Estimation tool — not a safety-critical vehicle control system.

## License / data

Raw datasets (DEVRT, the third-party TUM dataset) stay local under `dataset/`
and `data/` and are **not** committed. Runtime images contain only the frozen
model artifacts, API, and dashboard.
