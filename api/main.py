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
    PredictionRequest,
    PredictionResponse,
)
from src.inference.service import (
    InferenceError,
    PredictionService,
)
from src.telemetry.base import TelemetrySignal, SignalStatus
from src.telemetry.quality import assess_signal_quality, quality_summary

# --------------------------------------------------------------------------
# Configuration (environment-driven, no secrets)
# --------------------------------------------------------------------------
DEMO_TERRAIN = os.getenv("EV_DEMO_TERRAIN", "0") == "1"

# Maximum accepted request body size (payload size limit, see docstring).
MAX_BODY_BYTES = 1_000_000  # 1 MB


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
    telemetry_buffer = None  # RollingBuffer initialized on first read
    telemetry_lock: asyncio.Lock = asyncio.Lock()


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


# ---- Live status ------------------------------------------------------------

@app.get("/live/status", response_model=dict[str, Any])
async def live_status() -> dict[str, Any]:
    """Return the live telemetry connection and system status."""
    async with AppState.telemetry_lock:
        buffer = _get_telemetry_buffer()
        recent_signals = buffer.get_latest()
        source = AppState.telemetry_source

        # Determine overall telemetry status
        if source is None:
            connected = False
            status = "offline"
            available_signals = []
            buffer_size = 0
        else:
            connected = source.health().get("connected", False)
            available_signals = source.available_signals()
            buffer_size = buffer.size()
            # Simple status logic: if we have recent VALID signals, OK;
            # if we have STALE/Missing, degraded; otherwise offline.
            if recent_signals and any(_is_valid_signal(v)
                                      for v in recent_signals.values()):
                status = "ok"
            elif buffer_size > 0:
                status = "degraded"
            else:
                status = "offline"

        return {
            "telemetry_connected": connected,
            "status": status,
            "available_signals": available_signals,
            "buffer_size": buffer_size,
            "buffer_capacity": buffer.capacity(),
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
    """Return the latest normalized telemetry signals."""
    async with AppState.telemetry_lock:
        buffer = _get_telemetry_buffer()
        source = AppState.telemetry_source

        # Get latest sample
        latest = buffer.get_latest()

        if latest is None:
            return {
                "signals": [],
                "count": 0,
                "message": "No telemetry data available",
            }

        # Convert to signal info (without exposing raw values that could be
        # sensitive; only show names, quality, and staleness info)
        signal_infos: list[dict[str, Any]] = []
        for name, value in latest.items():
            is_valid = _is_valid_signal(value)
            signal_infos.append({
                "name": name,
                "has_value": is_valid,
                "quality": "VALID" if is_valid else "MISSING",
            })

        return {
            "signals": signal_infos,
            "count": len(signal_infos),
            "source": source.health().get("provider", "none") if source else "none",
        }


# ---- Live connect -----------------------------------------------------------

@app.post("/live/connect")
async def live_connect(provider: str = "obd_ii", format_type: str = "json",
                       config: Optional[dict] = None) -> dict[str, Any]:
    """Connect to a telemetry provider.

    Parameters
    ----------
    provider : str
        Identifier for the telemetry source (obd_ii, can, telematics, etc.).
    format_type : str
        Input format (json, mqtt, http, file).
    config : dict, optional
        Provider-specific configuration for signal mapping, etc.
    """
    from src.telemetry.obd_adapter import OBDAdapter
    from src.telemetry.can_adapter import CANAdapter
    from src.telemetry.telematics_adapter import TelematicsAdapter

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
        async with AppState.telemetry_lock:
            connected = adapter.connect()
            AppState.telemetry_source = adapter
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"Failed to connect to {provider}: {str(e)[:200]}")

    # Read initial signals
    initial_signals = adapter.read() if connected else None

    # Insert into buffer if we have data
    async with AppState.telemetry_lock:
        buffer = _get_telemetry_buffer()
        if initial_signals is not None:
            # Extract timestamps and normalize
            import time
            timestamp = time.time()
            buffer.insert(timestamp, {sig.name: sig.value for sig in initial_signals})

    return {
        "status": "connected" if connected else "connection_failed",
        "provider": provider,
        "format_type": format_type,
        "available_signals": adapter.available_signals() if adapter else [],
        "message": "Telemetry connection established" if connected else "Connection failed",
    }


# ---- Live disconnect ---------------------------------------------------------

@app.post("/live/disconnect")
async def live_disconnect() -> dict[str, Any]:
    """Disconnect the current telemetry source."""
    async with AppState.telemetry_lock:
        if AppState.telemetry_source is not None:
            AppState.telemetry_source.disconnect()
            AppState.telemetry_source = None
        AppState.telemetry_buffer = None

    return {
        "status": "disconnected",
        "message": "Telemetry source disconnected",
    }


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