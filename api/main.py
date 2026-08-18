"""
STEP 11G - PRODUCTION INFERENCE API (FastAPI).

Endpoints:
    GET  /health        - service + model load status
    GET  /model/info    - frozen model identity (no internals, no paths)
    POST /predict       - validated inference
    GET  /docs          - OpenAPI docs (FastAPI auto)

Security hygiene (STEP 11P):
    - request bodies validated by Pydantic (ranges, types, required fields)
    - payload size limit via Starlette max_request_size config
    - responses never expose filesystem paths or internal model objects
    - exceptions are converted to clean errors (no stack traces in responses)
    - no sensitive telemetry is logged (see inference_logger)
    - numerical ranges validated (schemas)

To start:  uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# allow running from project root without install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.inference.feature_builder import SyntheticRouteTerrainProvider
from src.inference.inference_logger import InferenceLogger, make_request_id
from src.inference.model_metadata import MODEL_VERSION
from src.inference.schemas import (
    HealthResponse,
    ModelInfoResponse,
    PastWindowSample,
    PredictionRequest,
    PredictionResponse,
    RouteTerrainInput,
    TelemetrySnapshot,
    TerrainPoint,
)
from src.inference.service import (
    InferenceError,
    PredictionService,
    TerrainUnavailableError,
)
from src.telemetry.base import TelemetrySignal, SignalStatus
from src.telemetry.quality import STALE_THRESHOLD_MS, assess_signal_quality, quality_summary
from src.telemetry.reader import TelemetryReader

# --------------------------------------------------------------------------
# Configuration (environment-driven, no secrets)
# --------------------------------------------------------------------------
DEMO_TERRAIN = os.getenv("EV_DEMO_TERRAIN", "0") == "1"

# Maximum accepted request body size (payload size limit, see docstring).
MAX_BODY_BYTES = 1_000_000  # 1 MB

# Operator-supplied vehicle parameters for LIVE prediction (NOT telemetry;
# they configure the target vehicle). Override via environment variables.
LIVE_VEHICLE_ID = os.getenv("EV_LIVE_VEHICLE_ID", "LIVE-VEHICLE-001")
LIVE_BATTERY_CAPACITY_KWH = float(os.getenv("EV_LIVE_BATTERY_CAPACITY_KWH", "60.0"))

# Minimum interval between live predictions (cadence, seconds).
LIVE_PREDICTION_CADENCE_S = 1.0

# Signals required (VALID and fresh) before a live prediction is attempted.
# soc_pct + vehicle_speed_kmh are the minimum the route-aware model needs
# beyond operator config and GPS; everything else can be median-imputed.
REQUIRED_FOR_PREDICTION = ("soc_pct", "vehicle_speed_kmh")


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject request bodies larger than MAX_BODY_BYTES with HTTP 413."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            return JSONResponse(status_code=413,
                                content={"detail": "payload too large"})
        return await call_next(request)


class AppState:
    """Shared application state (service + live telemetry, lock-guarded).

    ``telemetry_lock`` guards the telemetry connection/buffer so concurrent
    connect/disconnect/read operations do not race.
    """

    service: Optional[PredictionService] = None
    telemetry_source: Optional["TelemetrySource"] = None
    telemetry_reader: Optional[TelemetryReader] = None
    telemetry_buffer = None  # RollingBuffer initialized on first read
    telemetry_lock: asyncio.Lock = asyncio.Lock()

    # Live prediction single-flight + cadence cache (see /live/prediction).
    live_prediction_lock: asyncio.Lock = asyncio.Lock()
    last_live_prediction: Optional[dict] = None
    last_live_prediction_time: float = 0.0

    # Backend physics simulator session (demo mode, STEP 16).
    simulator_engine: Optional["SimulationEngine"] = None
    simulator_seed: Optional[int] = None


app = FastAPI(
    title="EV Intelligence - Route-Aware Energy & Range Inference API",
    description=(
        "Prototype inference system for route-aware EV energy-consumption and "
        "range estimation. Serves the frozen DEVRT ExtraTrees model "
        f"(version {MODEL_VERSION}). This is a PROTOTYPE: the model has only "
        "been validated on DEVRT; TUM external validation was blocked by "
        "feature incompatibility. Real-time accurate range prediction is NOT "
        "claimed."
    ),
    version=MODEL_VERSION,
)

app.add_middleware(MaxBodySizeMiddleware)


@app.on_event("startup")
def _startup() -> None:
    """Load the frozen model once (memory-safe, single process)."""
    terrain_provider = SyntheticRouteTerrainProvider() if DEMO_TERRAIN else None
    AppState.service = PredictionService(terrain_provider=terrain_provider)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    svc = AppState.service
    if svc is None:
        raise HTTPException(status_code=503, detail="service not initialized")
    return HealthResponse(**svc.health())


@app.get("/model/info", response_model=ModelInfoResponse)
def model_info() -> ModelInfoResponse:
    svc = AppState.service
    if svc is None:
        raise HTTPException(status_code=503, detail="service not initialized")
    return ModelInfoResponse(**svc.model_info())


@app.post("/predict", response_model=PredictionResponse)
def predict(req: PredictionRequest, request: Request) -> PredictionResponse:
    svc = AppState.service
    if svc is None:
        raise HTTPException(status_code=503, detail="service not initialized")
    request_id = make_request_id()
    try:
        return svc.predict(req, request_id=request_id)
    except InferenceError as e:
        raise HTTPException(status_code=400, detail=e.message)


@app.exception_handler(Exception)
def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    """Convert unhandled errors into clean JSON (no stack traces)."""
    # log a bounded message; do NOT echo traceback to the client
    InferenceLogger().log_failure("UNHANDLED", str(exc)[:300])
    return JSONResponse(status_code=500,
                        content={"detail": "internal server error",
                                 "error_code": "INTERNAL"})


# ---------------------------------------------------------------------------
# Simulator demo endpoints (STEP 16)
# ---------------------------------------------------------------------------

# The dashboard SIMULATOR mode is driven by the physics-based backend simulator
# (src/simulator). All outputs are honestly labeled "SIMULATOR" and are never
# presented as real vehicle data.


def _simulator_payload(engine: "SimulationEngine") -> dict[str, Any]:
    """Serialize one simulator snapshot + route + energy balance."""
    snap = dict(engine.snapshot())
    snap.pop("_source", None)
    return {
        "simulator": True,
        "source": "SIMULATOR",
        "scenario_id": snap.get("scenario_id"),
        "scenario": engine.scenario.summary(),
        "telemetry": snap,
        "route_terrain": engine.route_terrain_input(),
        "past_window": engine.past_window(),
        "energy_balance": engine.energy_balance(),
        "finished": engine.finished,
    }


def _simulator_engine(seed: int) -> "SimulationEngine":
    """Get the shared simulator engine, creating it if needed."""
    from src.simulator.scenario import random_scenario
    from src.simulator.simulator import SimulationEngine
    engine = AppState.simulator_engine
    if engine is None or AppState.simulator_seed != seed:
        scenario = random_scenario(seed=seed)
        engine = SimulationEngine(scenario)
        AppState.simulator_engine = engine
        AppState.simulator_seed = seed
    return engine


@app.post("/simulator/reset", response_model=dict[str, Any])
async def simulator_reset(seed: int = 1, n_steps: int = 1) -> dict[str, Any]:
    """Start a fresh backend simulator session for the given seed."""
    if seed < 0:
        raise HTTPException(status_code=400, detail="seed must be >= 0")
    async with AppState.telemetry_lock:
        engine = _simulator_engine(seed)
        engine.reset()
        engine.step(max(1, n_steps))
    return _simulator_payload(engine)


@app.post("/simulator/step", response_model=dict[str, Any])
async def simulator_step(n_steps: int = 1) -> dict[str, Any]:
    """Advance the backend simulator by n_steps (0.5 sim-seconds each)."""
    if n_steps < 1 or n_steps > 100:
        raise HTTPException(status_code=400,
                            detail="n_steps must be in [1, 100]")
    async with AppState.telemetry_lock:
        engine = AppState.simulator_engine
        if engine is None:
            engine = _simulator_engine(1)
        engine.step(n_steps)
    return _simulator_payload(engine)


# ---------------------------------------------------------------------------
# Live telemetry endpoints (STEP 15)
# ---------------------------------------------------------------------------

# Telemetry state lives on AppState (lock-guarded); see class AppState above.


def _is_valid_signal(v) -> bool:
    """True when a value is a non-None finite number (not NaN)."""
    return v is not None and isinstance(v, (int, float)) and not math.isnan(v)


def _get_telemetry_buffer():
    """Get or create the telemetry buffer (lock held by caller)."""
    if AppState.telemetry_buffer is None:
        from src.telemetry.buffer import RollingBuffer
        AppState.telemetry_buffer = RollingBuffer(max_samples=1000)
    return AppState.telemetry_buffer


def _get_reader() -> Optional[TelemetryReader]:
    """Current reader (None if no connected live source). Lock not required."""
    return AppState.telemetry_reader


# ---- Live health -------------------------------------------------------------

@app.get("/live/health", response_model=dict[str, Any])
async def live_health() -> dict[str, Any]:
    """Live subsystem health (reader, buffer, prediction readiness)."""
    async with AppState.telemetry_lock:
        reader = _get_reader()
        buffer = _get_telemetry_buffer()
        if reader is None:
            return {
                "status": "offline",
                "reader": None,
                "buffer_size": buffer.size(),
                "prediction_ready": False,
            }
        h = reader.health()
        return {
            "status": h["connected"] and h["running"] and "ok" or
                     (h["connected"] and "degraded" or "offline"),
            "reader": h,
            "buffer_size": buffer.size(),
            "prediction_ready": _live_prediction_ready(h),
        }


def _live_prediction_ready(health: dict[str, Any]) -> bool:
    """Prediction readiness: connected, fresh data, no hard failures."""
    if not health.get("connected"):
        return False
    age = health.get("latest_age_ms")
    if age is None or age > STALE_THRESHOLD_MS:
        return False
    return True


# ---- Live status ------------------------------------------------------------

@app.get("/live/status", response_model=dict[str, Any])
async def live_status() -> dict[str, Any]:
    """Return the live telemetry connection, health and readiness status."""
    async with AppState.telemetry_lock:
        buffer = _get_telemetry_buffer()
        reader = _get_reader()
        source = reader.source if reader else AppState.telemetry_source
        now = time.time()

        if source is None or reader is None:
            return {
                "telemetry_connected": False,
                "status": "offline",
                "provider": None,
                "available_signals": [],
                "buffer_size": buffer.size(),
                "buffer_capacity": buffer.capacity(),
                "required_signal_status": {},
                "prediction_ready": False,
                "prediction_ready_reason": "no telemetry source connected",
                "route_ready": _is_route_available(),
                "mode": "STRICT_ONBOARD",
            }

        health = reader.health()
        connected = bool(health.get("connected", False))
        available_signals = source.available_signals()
        latest = reader.latest()
        buffer_size = buffer.size()

        # Required-signal availability (VALID + fresh) for live prediction.
        required_status = {
            name: latest[name]["quality"] if name in latest else "MISSING"
            for name in REQUIRED_FOR_PREDICTION
        }
        age = health.get("latest_age_ms")
        fresh = age is not None and age <= STALE_THRESHOLD_MS
        missing_required = [
            name for name, q in required_status.items() if q != "VALID"
        ]
        prediction_ready = (
            connected and fresh and not missing_required
            and _live_prediction_ready(health)
        )
        if not connected:
            reason = "telemetry source not connected"
        elif not fresh:
            reason = f"telemetry stale (age {age} ms)"
        elif missing_required:
            reason = f"missing required signals: {missing_required}"
        else:
            reason = "ready"

        if connected and fresh and not missing_required:
            status = "ok"
        elif connected and buffer_size > 0:
            status = "degraded"
        elif connected:
            status = "waiting_for_telemetry"
        else:
            status = "offline"

        return {
            "telemetry_connected": connected,
            "status": status,
            "provider": health.get("provider"),
            "health": health,
            "available_signals": available_signals,
            "buffer_size": buffer_size,
            "buffer_capacity": buffer.capacity(),
            "required_signal_status": required_status,
            "prediction_ready": prediction_ready,
            "prediction_ready_reason": reason,
            "route_ready": _is_route_available(),
            "mode": "ROUTE_AWARE" if connected and _is_route_available()
                    else "STRICT_ONBOARD",
        }


def _is_route_available() -> bool:
    """Check if the running service has a terrain provider configured."""
    svc = AppState.service
    return svc is not None and getattr(svc, "terrain_provider", None) is not None


# ---- Live telemetry ---------------------------------------------------------

@app.get("/live/telemetry", response_model=dict[str, Any])
async def live_telemetry() -> dict[str, Any]:
    """Return the latest normalized telemetry signals with full metadata.

    Each signal entry includes: name, value, unit, quality, source,
    timestamp and age_ms. Raw values are exposed ONLY for signals the source
    actually provides; nothing is fabricated.
    """
    async with AppState.telemetry_lock:
        reader = _get_reader()
        if reader is None:
            return {"signals": [], "count": 0,
                    "message": "No telemetry source connected"}

        latest = reader.latest()
        if not latest:
            return {"signals": [], "count": 0,
                    "message": "No telemetry data available yet"}

        signals = list(latest.values())
        return {
            "signals": signals,
            "count": len(signals),
            "source": reader.health().get("provider", "none"),
            "timestamp": latest.get("_timestamp"),
        }


# ---- Live connect -----------------------------------------------------------

@app.post("/live/connect")
async def live_connect(provider: str = "obd_ii", format_type: str = "json",
                       config: Optional[dict] = None,
                       reconnect: bool = True,
                       interval_s: float = 0.5) -> dict[str, Any]:
    """Connect to a telemetry provider and start the continuous reader.

    Parameters
    ----------
    provider : str
        Identifier for the telemetry source (obd_ii, can, telematics, etc.).
    format_type : str
        Input format (json, mqtt, http, file).
    config : dict, optional
        Provider-specific configuration for signal mapping, etc.
    reconnect : bool, default True
        If already connected, disconnect first then reconnect.
    interval_s : float
        Reader sampling interval in seconds.
    """
    from src.telemetry.obd_adapter import OBDAdapter
    from src.telemetry.can_adapter import CANAdapter
    from src.telemetry.telematics_adapter import TelematicsAdapter

    async with AppState.telemetry_lock:
        if AppState.telemetry_reader is not None:
            if not reconnect:
                return {
                    "status": "already_connected",
                    "provider": provider,
                    "message": "already connected (reconnect=false)",
                }
            await AppState.telemetry_reader.stop()
            if AppState.telemetry_source is not None:
                AppState.telemetry_source.disconnect()
            AppState.telemetry_source = None
            AppState.telemetry_reader = None

        # Create the appropriate adapter based on provider type
        if provider == "obd_ii":
            adapter = OBDAdapter()
        elif provider == "can":
            adapter = CANAdapter(config=config)
        elif provider == "telematics":
            adapter = TelematicsAdapter(provider=provider,
                                        format_type=format_type,
                                        config=config)
        else:
            raise HTTPException(status_code=400,
                                detail=f"Unknown telemetry provider: {provider}")

        # Attempt connection (under lock so connect/disconnect do not race)
        try:
            connected = adapter.connect()
        except Exception as e:
            raise HTTPException(status_code=502,
                                detail=f"Failed to connect to {provider}: {str(e)[:200]}")

        buffer = _get_telemetry_buffer()
        reader = TelemetryReader(adapter, buffer, interval_s=interval_s)
        AppState.telemetry_source = adapter
        AppState.telemetry_reader = reader
        if connected:
            reader.start()
            reader.read_once()  # immediate first sample

    return {
        "status": "connected" if connected else "connection_failed",
        "provider": provider,
        "format_type": format_type,
        "available_signals": adapter.available_signals() if adapter else [],
        "message": ("Telemetry connection established" if connected
                    else "Connected adapter reported no usable signals; "
                          "waiting for data"),
    }


# ---- Live reconnect ---------------------------------------------------------

@app.post("/live/reconnect")
async def live_reconnect() -> dict[str, Any]:
    """Reconnect the current telemetry source (explicit recovery)."""
    async with AppState.telemetry_lock:
        reader = _get_reader()
        if reader is None:
            raise HTTPException(status_code=409,
                                detail="no telemetry source connected")
        ok = reader.reconnect()
        if ok:
            reader.read_once()
        return {"status": "reconnected" if ok else "reconnect_failed",
                "message": reader.health().get("last_error") or "reconnected"}


# ---- Live disconnect ---------------------------------------------------------

@app.post("/live/disconnect")
async def live_disconnect() -> dict[str, Any]:
    """Stop the reader and disconnect the current telemetry source."""
    async with AppState.telemetry_lock:
        reader = _get_reader()
        if reader is not None:
            await reader.stop()
        if AppState.telemetry_source is not None:
            AppState.telemetry_source.disconnect()
        AppState.telemetry_reader = None
        AppState.telemetry_source = None
        AppState.telemetry_buffer = None
        AppState.last_live_prediction = None
        AppState.last_live_prediction_time = 0.0

    return {
        "status": "disconnected",
        "message": "Telemetry source disconnected",
    }


# ---- Live prediction --------------------------------------------------------

# Mapping from adapter signal names (telemetry_schema.yaml) to the
# TelemetrySnapshot fields the frozen model expects.
_LIVE_FIELD_MAP = {
    "soc_pct": "soc_pct",
    "vehicle_speed_kmh": "speed_kmh",
    "speed_kmh": "speed_kmh",
    "altitude_m": "altitude_m",
    "ambient_temperature_c": "ambient_temperature_c",
    "distance_since_trip_start_km": "distance_since_trip_start_km",
    "time_since_trip_start_min": "time_since_trip_start_min",
    "motor_power_kw": "motor_power_kw",
    "motor_rpm": "motor_rpm",
    "motor_torque_nm": "motor_torque_nm",
    "auxiliary_power_kw": "aux_power_kw",
    "regen_power_kw": "regen_power_kw",
    "battery_voltage_v": "battery_voltage_v",
    "battery_temperature_c": "battery_temperature_c",
    "battery_current_a": "battery_current_a",
}


def _live_telemetry_fields(reader: TelemetryReader) -> tuple[dict, list[str]]:
    """Build the TelemetrySnapshot field dict from real VALID signals only.

    Never fabricates a value: any required field without a VALID signal is
    reported missing. Returns (fields, missing_required).
    """
    latest = reader.latest()
    fields: dict[str, Any] = {
        "vehicle_id": LIVE_VEHICLE_ID,
        "battery_capacity_kwh": LIVE_BATTERY_CAPACITY_KWH,
        "timestamp": datetime.now(timezone.utc),
    }
    for sig_name, field_name in _LIVE_FIELD_MAP.items():
        entry = latest.get(sig_name)
        if entry and entry["quality"] == "VALID" and entry["value"] is not None:
            fields[field_name] = entry["value"]

    required = ("soc_pct", "speed_kmh", "altitude_m", "ambient_temperature_c",
                "distance_since_trip_start_km", "time_since_trip_start_min")
    missing = [f for f in required if fields.get(f) is None]
    return fields, missing


def _live_past_window(buffer) -> list[PastWindowSample]:
    """Causal past window from the rolling buffer (no future samples)."""
    samples: list[PastWindowSample] = []
    for s in buffer.get_recent(min(buffer.size(), 120)):
        ts = s.get("_timestamp")
        dist = s.get("distance_since_trip_start_km") or s.get("odometer_km")
        alt = s.get("altitude_m")
        speed = s.get("vehicle_speed_kmh") or s.get("speed_kmh")
        if ts is None or dist is None or alt is None or speed is None:
            continue  # cannot build a schema-valid causal row; skip
        samples.append(PastWindowSample(
            timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
            distance_km=float(dist),
            altitude_m=float(alt),
            speed_kmh=float(speed),
            ambient_temperature_c=(float(s["ambient_temperature_c"])
                                   if s.get("ambient_temperature_c") is not None else None),
            motor_power_kw=(float(s["motor_power_kw"])
                            if s.get("motor_power_kw") is not None else None),
            motor_torque_nm=(float(s["motor_torque_nm"])
                             if s.get("motor_torque_nm") is not None else None),
            motor_rpm=(float(s["motor_rpm"])
                       if s.get("motor_rpm") is not None else None),
            aux_power_kw=(float(s["aux_power_kw"])
                          if s.get("aux_power_kw") is not None else None),
            regen_power_kw=(float(s["regen_power_kw"])
                            if s.get("regen_power_kw") is not None else None),
        ))
    return samples


def _live_route_input(svc: PredictionService, dist_km: float, alt_m: float):
    """Resolve route terrain for live prediction from the real provider.

    Never fabricates terrain: if no provider or no data, returns None.
    """
    if svc is None or getattr(svc, "terrain_provider", None) is None:
        return None
    provider = svc.terrain_provider
    try:
        t = provider.get_upcoming_terrain(dist_km, alt_m)
        if t is None or len(t.offsets_km) == 0:
            return None
        return RouteTerrainInput(
            points=[TerrainPoint(offset_km=float(o), altitude_m=float(a))
                    for o, a in zip(t.offsets_km, t.altitudes_m)],
            source=str(t.source),
        )
    except (NotImplementedError, TerrainUnavailableError, Exception):
        return None


@app.post("/live/prediction", response_model=dict[str, Any])
async def live_prediction() -> dict[str, Any]:
    """Live route-aware prediction from the actual latest telemetry.

    Single-flight + cadence: requests within LIVE_PREDICTION_CADENCE_S reuse
    the cached result; a second concurrent request never starts a duplicate
    model call. If required live data is missing, the response is
    INSUFFICIENT_TELEMETRY (no fabricated values).
    """
    now = time.time()

    # Cadence cache: reuse a fresh-enough result instead of re-running the model.
    if (AppState.last_live_prediction is not None
            and now - AppState.last_live_prediction_time < LIVE_PREDICTION_CADENCE_S):
        cached = dict(AppState.last_live_prediction)
        cached["fresh"] = False
        cached["cached_age_s"] = round(now - AppState.last_live_prediction_time, 2)
        return cached

    # Single-flight: never start a second prediction while one is in flight.
    if AppState.live_prediction_lock.locked():
        if AppState.last_live_prediction is not None:
            cached = dict(AppState.last_live_prediction)
            cached["fresh"] = False
            cached["in_flight"] = True
            return cached
        return {"available": False, "status": "BUSY",
                "message": "prediction already in progress"}

    async with AppState.live_prediction_lock:
        async with AppState.telemetry_lock:
            reader = _get_reader()
            buffer = _get_telemetry_buffer()
            if reader is None:
                return {"available": False, "status": "OFFLINE",
                        "message": "no connected telemetry source"}
            health = reader.health()

        if not health.get("connected"):
            result = {"available": False, "status": "OFFLINE",
                      "message": "telemetry source not connected"}
            AppState.last_live_prediction = result
            AppState.last_live_prediction_time = now
            return result

        # Required signals must be VALID and fresh (never fabricated).
        fields, missing = _live_telemetry_fields(reader)
        if missing:
            result = {
                "available": False,
                "status": "INSUFFICIENT_TELEMETRY",
                "missing_required": missing,
                "message": "insufficient live telemetry for prediction "
                           "(no fabricated values)",
            }
            AppState.last_live_prediction = result
            AppState.last_live_prediction_time = now
            return result

        svc = AppState.service
        route_input = _live_route_input(
            svc, fields["distance_since_trip_start_km"], fields["altitude_m"])
        route_status = {
            "available": route_input is not None,
            "terrain_features_available": route_input is not None,
            "provider_configured": svc is not None
            and getattr(svc, "terrain_provider", None) is not None,
        }
        if route_input is None:
            result = {
                "available": False,
                "status": "ROUTE_TERRAIN_UNAVAILABLE",
                "route": route_status,
                "message": "route terrain unavailable for live prediction; "
                           "no synthetic terrain is substituted",
            }
            AppState.last_live_prediction = result
            AppState.last_live_prediction_time = now
            return result

        past = _live_past_window(buffer)
        request = PredictionRequest(
            telemetry=TelemetrySnapshot(**fields),
            route_terrain=route_input,
            past_window=past or None,
        )
        try:
            resp = svc.predict(request)
        except (TerrainUnavailableError, InferenceError) as e:
            result = {"available": False,
                      "status": "ROUTE_TERRAIN_UNAVAILABLE"
                      if isinstance(e, TerrainUnavailableError) else "PREDICTION_FAILED",
                      "message": e.message}
            AppState.last_live_prediction = result
            AppState.last_live_prediction_time = now
            return result

        result = {
            "available": True,
            "fresh": True,
            "prediction": resp.model_dump(),
            "route": route_status,
            "telemetry_age_ms": health.get("latest_age_ms"),
            "provenance": {
                "source": "LIVE",
                "provider": health.get("provider"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "cadence_ms": int(LIVE_PREDICTION_CADENCE_S * 1000),
            },
            "status": resp.status,
        }
        AppState.last_live_prediction = result
        AppState.last_live_prediction_time = now
        return result


# Serve the telemetry dashboard (Step 12.1 / React). Mounted AFTER the API
# routes so /health, /model/info, /predict and /docs keep precedence. The
# React bundle lives in dashboard/dist (built via `npm run build`).
_FRONTEND = Path(__file__).resolve().parent.parent / "dashboard" / "dist"
if not _FRONTEND.is_dir():
    _FRONTEND = Path(__file__).resolve().parent.parent / "dashboard"
if _FRONTEND.is_dir():
    app.mount("/dashboard",
              StaticFiles(directory=str(_FRONTEND), html=True),
              name="dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)