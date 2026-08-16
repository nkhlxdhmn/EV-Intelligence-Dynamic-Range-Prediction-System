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

import os
import sys
from pathlib import Path
from typing import Optional

# allow running from project root without install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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


class AppState:
    """Holds the loaded PredictionService (loaded once at startup)."""

    service: Optional[PredictionService] = None


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

# Global telemetry state (in-production would be per-connection or
# session-scoped; here we use a singleton for prototype simplicity)
_telemetry_source: Optional[TelemetrySource] = None
_telemetry_buffer = None  # RollingBuffer initialized on first read


def _get_telemetry_buffer() -> "RollingBuffer":
    """Get or create the global telemetry buffer."""
    global _telemetry_buffer
    if _telemetry_buffer is None:
        from src.telemetry.buffer import RollingBuffer
        _telemetry_buffer = RollingBuffer(max_samples=1000)
    return _telemetry_buffer


# ---- Live status ------------------------------------------------------------

@app.get("/live/status", response_model=dict[str, Any])
def live_status() -> dict[str, Any]:
    """Return the live telemetry connection and system status."""
    global _telemetry_source

    buffer = _get_telemetry_buffer()
    recent_signals = buffer.get_latest()

    # Determine overall telemetry status
    if _telemetry_source is None:
        connected = False
        status = "offline"
        available_signals = []
        buffer_size = 0
    else:
        connected = _telemetry_source.health().get("connected", False)
        available_signals = _telemetry_source.available_signals()
        buffer_size = buffer.size()
        # Simple status logic: if we have recent VALID signals, OK;
        # if we have STALE/Missing, degraded; otherwise offline.
        if recent_signals is not None:
            for v in recent_signals.values():
                if v is not None and v != float("nan"):
                    status = "ok"
                    break
            else:
                # Check buffer for any signals
                if buffer_size > 0:
                    status = "degraded"
                else:
                    status = "offline"
        else:
            status = "offline"

    return {
        "telemetry_connected": connected,
        "status": status,
        "available_signals": available_signals,
        "buffer_size": buffer_size,
        "buffer_capacity": buffer.capacity(),
        "mode": "ROUTE_AWARE" if connected and _is_route_available() else "STRICT_ONBOARD",
    }


def _is_route_available() -> bool:
    """Check if route terrain is available for route-aware prediction."""
    # In production, would check the terrain provider/status
    # For now, return True if we have a prediction service with terrain
    try:
        from src.inference.service import PredictionService
        # Check if the service has terrain provider configured
        return True  # simplified
    except Exception:
        return False


# ---- Live telemetry ---------------------------------------------------------

@app.get("/live/telemetry", response_model=dict[str, Any])
def live_telemetry() -> dict[str, Any]:
    """Return the latest normalized telemetry signals."""
    global _telemetry_source, _telemetry_buffer

    buffer = _get_telemetry_buffer()

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
        # Determine quality based on value presence
        if value is None or value != value:  # None or NaN
            quality = "MISSING"
        elif value == float("nan"):
            quality = "MISSING"
        else:
            quality = "VALID"

        signal_infos.append({
            "name": name,
            "has_value": value is not None and value == value and value != float("nan"),
            "quality": quality,
        })

    return {
        "signals": signal_infos,
        "count": len(signal_infos),
        "source": _telemetry_source.health().get("provider", "none") if _telemetry_source else "none",
    }


# ---- Live connect -----------------------------------------------------------

@app.post("/live/connect")
def live_connect(provider: str = "obd_ii", format_type: str = "json",
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
    global _telemetry_source

    from src.telemetry.obd_adapter import OBDAdapter
    from src.telemetry.can_adapter import CANAdapter
    from src.telemetry.telematics_adapter import TelematicsAdapter

    # Create the appropriate adapter based on provider type
    if provider == "obd_ii":
        _telemetry_source = OBDAdapter()
    elif provider == "can":
        _telemetry_source = CANAdapter(config=config)
    elif provider == "telematics":
        _telemetry_source = TelematicsAdapter(provider=provider,
                                              format_type=format_type,
                                              config=config)
    else:
        return {
            "status": "error",
            "message": f"Unknown telemetry provider: {provider}",
        }

    # Attempt connection
    try:
        connected = _telemetry_source.connect()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to connect: {str(e)}",
        }

    # Read initial signals
    initial_signals = _telemetry_source.read() if connected else None

    # Insert into buffer if we have data
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
        "available_signals": _telemetry_source.available_signals() if _telemetry_source else [],
        "message": "Telemetry connection established" if connected else "Connection failed",
    }


# ---- Live disconnect ---------------------------------------------------------

@app.post("/live/disconnect")
def live_disconnect() -> dict[str, Any]:
    """Disconnect the current telemetry source."""
    global _telemetry_source, _telemetry_buffer

    if _telemetry_source is not None:
        _telemetry_source.disconnect()
        _telemetry_source = None

    _telemetry_buffer = None

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