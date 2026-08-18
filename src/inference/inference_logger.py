"""
STEP 11J - SAFE INFERENCE LOGGING.

Logs only operational metadata:
    timestamp, request ID, model version, prediction latency, success/failure.

NEVER logs: personal information, raw GPS history, full telemetry, or other
sensitive user data. Numerical outcome values (prediction, range) are logged
coarsely and only when configured.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
# Logging must never take the service down: if the logs dir cannot be created
# or written (read-only container filesystem, missing permissions), fall back
# to console-only logging instead of raising at import time.
try:
    LOG_DIR.mkdir(exist_ok=True)
    _LOG_FILE = LOG_DIR / "inference.log"
    with open(_LOG_FILE, "a", encoding="utf-8"):
        pass
except OSError:
    _LOG_FILE = None

_configured = False


def get_logger(name: str = "ev.inference", log_file: Path | None = None,
               level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger writing to both console and a log file.

    No PII/telemetry is logged by any handler added here.
    """
    global _configured
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File logging only when a writable log file is available; otherwise the
    # service logs to stdout/stderr only (never crashes on a read-only FS).
    if log_file is not None or _LOG_FILE is not None:
        fh = logging.FileHandler(log_file or _LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    logger.propagate = False
    _configured = True
    return logger


def make_request_id() -> str:
    """Short unique request identifier (no user data)."""
    return uuid.uuid4().hex[:12]


class InferenceLogger:
    """Request-scoped operational logger."""

    def __init__(self, request_id: str | None = None,
                 model_version: str = "unknown"):
        self.request_id = request_id or make_request_id()
        self.model_version = model_version
        self._logger = get_logger()

    def log_start(self) -> None:
        self._t0 = time.perf_counter()
        self._logger.info(json.dumps({
            "event": "inference_start",
            "request_id": self.request_id,
            "model_version": self.model_version,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }, separators=(",", ":")))

    def log_success(self, latency_ms: float | None = None,
                    prediction: float | None = None,
                    range_km: float | None = None) -> None:
        latency_ms = latency_ms if latency_ms is not None else (
            (time.perf_counter() - self._t0) * 1000.0 if hasattr(self, "_t0") else None)
        rec = {
            "event": "inference_success",
            "request_id": self.request_id,
            "model_version": self.model_version,
            "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }
        if prediction is not None:
            rec["predicted_kwh_per_km"] = round(float(prediction), 4)
        if range_km is not None:
            rec["range_km"] = round(float(range_km), 2)
        self._logger.info(json.dumps(rec, separators=(",", ":")))

    def log_failure(self, error_code: str, message: str,
                    latency_ms: float | None = None) -> None:
        latency_ms = latency_ms if latency_ms is not None else (
            (time.perf_counter() - self._t0) * 1000.0 if hasattr(self, "_t0") else None)
        self._logger.warning(json.dumps({
            "event": "inference_failure",
            "request_id": self.request_id,
            "model_version": self.model_version,
            "error_code": error_code,
            "message": message[:300],  # bounded, no telemetry dump
            "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }, separators=(",", ":")))