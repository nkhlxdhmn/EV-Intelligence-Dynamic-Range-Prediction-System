# Telemetry (LIVE)

This document describes the LIVE telemetry layer: how signals are collected,
normalized, quality-assessed, buffered, and used for live predictions. It
consolidates the (removed) live-telemetry documentation.

## 1. Honesty contract

- **No values are fabricated.** A signal a source does not provide is recorded
  as MISSING / UNAVAILABLE and excluded from prediction readiness.
- **Stale data is never treated as current.** Stale samples are flagged and
  rejected by the quality layer.
- **Disconnected state is surfaced honestly.** With no source connected the
  API reports `offline`; it never synthesizes telemetry.

## 2. Components (`src/telemetry/`)

| Module | Responsibility |
|---|---|
| `base.py` | `TelemetrySource` interface + `TelemetrySignal` / `SignalStatus` types. All adapters implement this interface. |
| `obd_adapter.py` | SAFE OBD-II adapter. Does not assume EV-specific PIDs; reports UNAVAILABLE for EV-specific signals the vehicle does not expose. Never invents PIDs. |
| `can_adapter.py` | Vehicle-independent CAN interface: configurable message IDs, start bit, length, byte order, scale, offset, unit. No fake CAN IDs. |
| `telematics_adapter.py` | Generic telematics interface (JSON / MQTT / HTTP normalized input). Not bound to one commercial provider. |
| `normalizer.py` | Unit conversion, timestamp normalization, range validation, impossible-value rejection, missing-value marking, provenance preservation. |
| `quality.py` | Per-signal quality assessment: VALID / MISSING / STALE / INVALID / OUT_OF_RANGE / UNAVAILABLE, with `age_ms`. |
| `reader.py` | Continuous, non-blocking background reader; builds the structured "latest" sample and inserts causal history into the buffer. |
| `buffer.py` | Rolling causal buffer (bounded) used as the `past_window` for windowed features. |
| `recorder.py` | Optional disk-based Parquet recorder (streaming, bounded memory, one file/session). |

## 3. Quality states

| State | Meaning |
|---|---|
| `VALID` | Present, in range, and fresh. |
| `MISSING` | Expected but not reported by the source. |
| `STALE` | Older than the staleness threshold (`STALE_THRESHOLD_MS`); never used as current. |
| `INVALID` | Non-numeric / impossible value rejected by the normalizer. |
| `OUT_OF_RANGE` | Outside the configured valid range. |
| `UNAVAILABLE` | Explicitly unsupported by the source (e.g. EV-specific signal not exposed). |

## 4. Signal mapping for prediction

LIVE prediction builds a `TelemetrySnapshot` from **real VALID signals only**
(see `_LIVE_FIELD_MAP` in `api/main.py`). Operator-supplied (non-telemetry)
fields are `vehicle_id` and `battery_capacity_kwh`, configured via
`EV_LIVE_VEHICLE_ID` / `EV_LIVE_BATTERY_CAPACITY_KWH`.

Required for a live prediction (`REQUIRED_FOR_PREDICTION`):

- `soc_pct` — must be VALID and fresh.
- `vehicle_speed_kmh` — must be VALID and fresh.

Additional snapshot fields used when available: `altitude_m`,
`ambient_temperature_c`, `distance_since_trip_start_km`,
`time_since_trip_start_min`, `motor_power_kw`, `motor_rpm`, `motor_torque_nm`,
`aux_power_kw`, `regen_power_kw`, `battery_voltage_v`,
`battery_temperature_c`, `battery_current_a`. Missing ones are median-imputed
by the frozen preprocessor — never fabricated.

## 5. API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/live/status` | GET | connection + provider + signal availability + prediction readiness + required-signal status. |
| `/live/telemetry` | GET | latest normalized signals with full metadata (value, unit, quality, source, timestamp, age_ms). |
| `/live/health` | GET | live subsystem health (reader, buffer, prediction readiness). |
| `/live/connect` | POST | connect OBD-II / CAN / telematics adapter and start the reader. |
| `/live/reconnect` | POST | explicit recovery of the current source. |
| `/live/disconnect` | POST | stop the reader and disconnect the source. |
| `/live/prediction` | POST | route-aware prediction from the current telemetry (single-flight + 1 s cadence cache). |

`/live/prediction` returns an explicit status instead of fabricating values:

- `OFFLINE` — no connected source.
- `INSUFFICIENT_TELEMETRY` — required signals missing/stale.
- `ROUTE_TERRAIN_UNAVAILABLE` — no real route terrain provider/data.
- `BUSY` — another prediction in flight.

## 6. Staleness

`src/telemetry/quality.py` defines `STALE_THRESHOLD_MS`. The reader records
each signal's `age_ms`; prediction readiness requires required signals to be
VALID and within the staleness threshold. A stale buffer never blocks the
dashboard from showing an honest OFFLINE / DEGRADED state.

## 7. Reference schema

`configs/telemetry_schema.yaml` documents the telemetry signal contract
(signal names, units, and the mapping used by the LIVE layer). It is a
reference document; the runtime mapping lives in `api/main.py`
(`_LIVE_FIELD_MAP`).
