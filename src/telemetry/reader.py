"""
STEP 15 — Continuous Telemetry Reader.

Reads live signals from a TelemetrySource in the background, assesses each
signal's quality (stale / out-of-range / missing), records a structured
"latest" sample, and inserts causal history into the rolling buffer for
feature building.

Honesty contract:
- No values are fabricated. Signals a source does not provide are recorded
  as MISSING / UNAVAILABLE and are excluded from prediction readiness.
- Stale data is never treated as current.
- The reader is non-blocking: reads are short and scheduled on a timer.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from src.telemetry.base import SignalStatus, TelemetrySignal, TelemetrySource
from src.telemetry.buffer import RollingBuffer
from src.telemetry.quality import (
    STALE_THRESHOLD_MS,
    assess_signal_quality,
)

DEFAULT_INTERVAL_S = 0.5


class TelemetryReader:
    """Continuously read + normalize telemetry from a source into a buffer."""

    def __init__(
        self,
        source: TelemetrySource,
        buffer: RollingBuffer,
        interval_s: float = DEFAULT_INTERVAL_S,
        stale_threshold_ms: int = STALE_THRESHOLD_MS,
        valid_ranges: Optional[Dict[str, tuple[float, float]]] = None,
    ):
        self.source = source
        self.buffer = buffer
        self.interval_s = float(interval_s)
        self.stale_threshold_ms = int(stale_threshold_ms)
        self.valid_ranges = valid_ranges or {}

        # runtime state
        self._latest: Dict[str, Dict[str, Any]] = {}
        self._last_read: Optional[float] = None
        self._last_data_time: Optional[float] = None
        self._last_error: Optional[str] = None
        self._consecutive_failures = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ read
    def read_once(self, current_time: Optional[float] = None) -> int:
        """Read one sample from the source, assess quality, update state.

        Returns the number of signals read (0 if no data / failure).
        """
        now = current_time if current_time is not None else time.time()
        self._last_read = now
        try:
            signals = self.source.read()
        except Exception as e:  # adapter error -> failure, no fabricated data
            self._consecutive_failures += 1
            self._last_error = f"adapter read failed: {str(e)[:200]}"
            return 0

        if not signals:
            # Connected but no data yet (or empty read): not a hard failure,
            # but there is nothing new to record.
            return 0

        latest: Dict[str, Dict[str, Any]] = {}
        flat: Dict[str, Any] = {}
        count = 0
        for sig in signals:
            if not isinstance(sig, TelemetrySignal):
                continue
            # Respect source-declared unavailability (never invent a value).
            if sig.status in (SignalStatus.UNAVAILABLE, "UNAVAILABLE"):
                entry = self._entry(sig, "UNAVAILABLE", now)
                latest[sig.name] = entry
                continue
            q = assess_signal_quality(
                value=sig.value,
                timestamp=sig.timestamp or now,
                current_time=now,
                stale_threshold_ms=self.stale_threshold_ms,
                valid_range=self.valid_ranges.get(sig.name),
            )
            latest[sig.name] = self._entry(sig, q.quality, now, age_ms=q.age_ms)
            if q.quality == "VALID":
                flat[sig.name] = sig.value
                count += 1

        self._latest = latest
        if flat:
            flat["_timestamp"] = now
            self.buffer.insert(now, flat)
            self._last_data_time = now
            self._consecutive_failures = 0
            self._last_error = None
        return count

    def _entry(self, sig: TelemetrySignal, quality: str,
               now: float, age_ms: Optional[int] = None) -> Dict[str, Any]:
        """Build the structured latest entry for one signal."""
        age = age_ms if age_ms is not None else int((now - (sig.timestamp or now)) * 1000)
        return {
            "timestamp": sig.timestamp or now,
            "name": sig.name,
            "value": sig.value,
            "unit": sig.unit,
            "quality": quality,
            "source": sig.source or "unknown",
            "age_ms": max(age, 0),
        }

    # ---------------------------------------------------------------- health
    def health(self) -> Dict[str, Any]:
        now = time.time()
        latest_age_ms = (
            int((now - self._last_data_time) * 1000)
            if self._last_data_time is not None else None)
        return {
            "running": self._running,
            "connected": bool(self.source.health().get("connected", False)),
            "provider": self.source.health().get("provider",
                                                  type(self.source).__name__),
            "last_read": self._last_read,
            "last_data_time": self._last_data_time,
            "latest_age_ms": latest_age_ms,
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
            "buffer_size": self.buffer.size(),
            "n_signals": len(self._latest),
        }

    def latest(self) -> Dict[str, Dict[str, Any]]:
        """Structured latest sample: name -> {value, unit, quality, source, ...}."""
        return dict(self._latest)

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Start the background read loop (idempotent)."""
        if self._running:
            return
        self._running = True
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the background read loop (idempotent)."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            try:
                self.read_once()
            except Exception as e:
                self._consecutive_failures += 1
                self._last_error = f"reader error: {str(e)[:200]}"
            await asyncio.sleep(self.interval_s)

    # -------------------------------------------------------------- reconnect
    def reconnect(self) -> bool:
        """Disconnect and reconnect the underlying source. Returns success."""
        try:
            self.source.disconnect()
            ok = self.source.connect()
            if not ok:
                self._last_error = ("reconnect: source.connect() returned False "
                                    "(no hardware assumed / unavailable)")
            else:
                self._last_error = None
                self._consecutive_failures = 0
            return bool(ok)
        except Exception as e:
            self._last_error = f"reconnect failed: {str(e)[:200]}"
            return False