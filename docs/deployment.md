# Deployment

The project ships a real-time inference API (FastAPI) plus a React telemetry
dashboard. Deployment requires only the frozen model artifacts — no training
data, no processed feature parquet files, and no dataset are needed at runtime.

## Runtime requirements

- Python 3.12+ (runtime deps pinned in `requirements.inference.txt`).
- Frozen artifacts in `models/`:
  - `ev_energy_extratrees_route_aware.joblib`
  - `final_preprocessor.joblib`
  - `final_feature_list.json`
- Dashboard bundle in `dashboard/dist/` (built by `npm run build`).

The runtime does **not** read `data/` or `dataset/`; those are local-only and
never shipped.

## Option A — Docker (recommended)

The multi-stage `Dockerfile` builds the React bundle and the Python runtime in
one image:

```bash
docker compose up --build

# API:        http://localhost:8000
# Docs:       http://localhost:8000/docs
# Dashboard:  http://localhost:8000/dashboard/
```

The container runs as a non-root user (`appuser`) with a `/health` healthcheck.
No dataset is copied into the image.

## Option B — Run from source

```bash
# 1. Install runtime deps
pip install -r requirements.inference.txt

# 2. Build the dashboard (once, after any frontend change)
cd dashboard && npm install && npm run build && cd ..

# 3. Start the API
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `EV_DEMO_TERRAIN` | unset | When `1`, the API attaches the clearly-labeled synthetic terrain provider for local demo only. **Never enable in production.** |
| `EV_LIVE_VEHICLE_ID` | `LIVE-VEHICLE-001` | Operator-supplied vehicle identifier used for LIVE predictions (not telemetry). |
| `EV_LIVE_BATTERY_CAPACITY_KWH` | `60.0` | Operator-supplied battery capacity used for LIVE predictions. |

Production must provide real route/DEM elevation through the `route_terrain`
request body (`source` must be a real DEM/GPS label — fabricated sources are
rejected). See [inference.md](inference.md) for the request contract.

## Production notes

- Route-aware `next_*` features require real planned-route elevation. Without
  it the API never fabricates terrain, so route-aware predictions are
  unavailable.
- The model is trained primarily on DEVRT and is **not** cross-dataset
  validated (TUM validation was blocked). Do not treat predictions as
  universal EV accuracy.
- The dashboard is SIMULATOR-mode by default; LIVE mode requires an explicit
  real telemetry source (`?telemetry=1`).

## Health / observability

- `GET /health` — service health (`{"status":"ok"}`).
- `GET /model/info` — model version, feature count, imputer type.
- `GET /live/status` — telemetry connection, signal quality, prediction
  readiness.
- Inference requests are logged with request IDs; see
  `src/inference/inference_logger.py`.
