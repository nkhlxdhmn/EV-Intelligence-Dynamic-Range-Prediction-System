# Inference API Usage Guide

STEP 11N - documentation for the route-aware EV energy & range inference API.

> **IMPORTANT**: this is a **prototype inference system**. The model has only
> been validated on the DEVRT dataset; TUM external validation was **blocked**
> by feature incompatibility. **Real-time accurate range prediction is NOT
> claimed.** Results are estimates for route-aware EV energy consumption and
> range, valid only in the DEVRT domain until further validation.

## 1. Start the service

```bash
# run directly (dev)
uvicorn api.main:app --host 0.0.0.0 --port 8000

# or via Docker
docker compose up --build
```

Interactive docs: http://localhost:8000/docs

### Environment variables

| Variable           | Default | Meaning                                                        |
|--------------------|---------|----------------------------------------------------------------|
| `EV_DEMO_TERRAIN`  | `0`     | `1` enables the clearly-labeled **SYNTHETIC** terrain provider (demo only). NEVER in production. |

## 2. Endpoints

### `GET /health`

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok", "model_loaded": true, "model_version": "ev-energy-devrt-v1"}
```

### `GET /model/info`

```bash
curl http://localhost:8000/model/info
```

Returns the frozen model identity, feature count (102), target, horizon (5 km),
dataset (DEVRT), route-awareness flag, and version. No internal paths or model
objects are exposed.

### `POST /predict`

Body (all fields required unless noted):

```json
{
  "telemetry": {
    "vehicle_id": "VEH-001",
    "timestamp": "2026-08-16T10:30:00Z",
    "soc_pct": 80.0,
    "battery_capacity_kwh": 40.0,
    "speed_kmh": 65.0,
    "altitude_m": 150.0,
    "ambient_temperature_c": 18.0,
    "distance_since_trip_start_km": 12.0,
    "time_since_trip_start_min": 20.0,
    "motor_power_kw": 12.0,
    "motor_rpm": 4200.0,
    "motor_torque_nm": 60.0,
    "aux_power_kw": 0.6,
    "regen_power_kw": -1.0
  },
  "route_terrain": {
    "points": [
      {"offset_km": 0.0, "altitude_m": 150.0},
      {"offset_km": 1.0, "altitude_m": 160.0}
    ],
    "source": "DEM_STATIC"
  },
  "reserve_soc_pct": 10.0,
  "past_window": []
}
```

Field notes:

- `timestamp` must be **timezone-aware** (trailing `Z` or `+00:00`).
- `soc_pct` in `[0, 100]`, `battery_capacity_kwh` in `(0, 300]`,
  `speed_kmh` in `[0, 400]`, `ambient_temperature_c` in `[-60, 80]`.
- `route_terrain.points` requires **>= 2 points**; source must be a real
  DEM/GPS label (`FABRICATED`, `FAKE`, `SYNTHETIC_DEMO` are rejected).
  Offsets ascending, altitudes finite.
- `past_window` (optional) is a list of historical samples used to compute
  windowed speed/elevation features (e.g. `mean_speed_1km`,
  `elevation_gain_1km`, `gradient_std_1km`).
- `reserve_soc_pct` (optional, default 10) is subtracted from `soc_pct` to
  compute usable energy.

Response:

```json
{
  "predicted_energy_kwh_per_km": 0.1266,
  "usable_energy_kwh": 28.0,
  "expected_range_km": 221.1,
  "conservative_range_km": 221.1,
  "optimistic_range_km": 221.1,
  "model_version": "ev-energy-devrt-v1",
  "route_terrain_source": "DEM_STATIC"
}
```

Note: this build uses the deterministic `estimate_range` path, so
`conservative_range_km` and `optimistic_range_km` currently equal
`expected_range_km`. The `RangeEstimator` supports an uncertainty band
(`estimate_range_band`) driven by model residual quantiles from
train+validation; it is exposed but not yet configured with quantiles, so the
band collapses to the expected range.

## 3. Error handling

- **400**: `InferenceError` from the service (e.g. `TerrainUnavailableError`,
  `FEATURE_BUILD_FAILED`, `NON_FINITE_FEATURES`) with a clean JSON detail.
- **422**: Pydantic request validation (wrong types, out-of-range values,
  missing fields, naive timestamp, fabricated terrain source).
- **500**: unhandled internal error. The client receives only
  `{"detail": "internal server error", "error_code": "INTERNAL"}` — never a
  stack trace or filesystem path.

## 4. Route terrain provider

When a `RouteTerrainProvider` is connected, the service uses it to obtain the
upcoming route profile (used for the `next_*` route-aware features). When no
provider is connected, the **validated request-body terrain** is used — safe
only if the client owns a real DEM/GPS route profile. The abstract provider
raises `NotImplementedError`; a `SyntheticRouteTerrainProvider`
(source `SYNTHETIC_DEMO`) exists for demos only and must not be used in
production.

## 5. Security hygiene

- Inputs validated by Pydantic (types, ranges, required fields).
- No stack traces, filesystem paths, or internal model objects in responses.
- No telemetry or PII is logged (see `src/inference/inference_logger.py`).
- Container runs as a non-root user; no training data is shipped in the image.

## 6. Limits / caveats

- Prototype only; validated exclusively on DEVRT. TUM external validation was
  blocked (30/102 features reproducible; route terrain unavailable externally;
  battery capacity DERIVED from fleet spec 58 kWh).
- Battery capacity is a *capacity* input, not derived from telemetry.
- Range bands are derived from the model prediction with a fixed ±factor.