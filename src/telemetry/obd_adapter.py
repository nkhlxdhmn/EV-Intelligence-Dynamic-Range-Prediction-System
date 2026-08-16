"""
STEP 15 — OBD-II Adapter.

SAFE OBD-II adapter interface.

IMPORTANT:
- Do NOT assume EV-specific PIDs.
- Support standard signals only where actually available.
- For EV-specific signals (SOC, battery voltage, battery current,
  battery power, motor power): the adapter must report UNAVAILABLE
  unless the connected vehicle actually exposes them.
- Do not invent PIDs.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from src.telemetry.base import TelemetrySource, TelemetrySignal, SignalStatus
from src.telemetry.normalizer import normalize_signals, normalize_signal


# ---------------------------------------------------------------------------
# OBD-II PID registry
# ---------------------------------------------------------------------------

# Standard OBD-II PIDs that are universally supported or well-documented:
# PID 0x0C: Calculated Engine Load (0-100%, not EV-specific)
# PID 0x0D: Engine Fuel Rate (not EV-specific)
# PID 0x1F: Fuel Type (not EV-specific)
# PID 0x5C: OBD-II Since DTCs Cleared (not useful for EV)
# PID 0x60: Pedal Position (may be throttle, not EV battery)

# EV-specific PIDs — NOT assumed to be available; adapter reports
# UNAVAILABLE unless vehicle actually exposes them.
EV_SPECIFIC_PIDS = {
    "SOC": "State of Charge — not a standard OBD-II PID",
    "BATTERY_VOLTAGE": "Battery voltage — not a standard OBD-II PID",
    "BATTERY_CURRENT": "Battery current — not a standard OBD-II PID",
    "BATTERY_POWER": "Battery power — not a standard OBD-II PID",
    "MOTOR_POWER": "Motor power — not a standard OBD-II PID",
}


# ---------------------------------------------------------------------------
# OBD-II Adapter implementation
# ---------------------------------------------------------------------------

class OBDAdapter(TelemetrySource):
    """Safe OBD-II adapter that does not assume EV-specific signals."""

    # Standard OBD-II PIDs supported by this adapter
    # Format: {"pid_hex": {"name", "unit", "transform", "model_usage"}}
    STANDARD_PIDS: dict[str, dict[str, Any]] = {
        "0x0C": {
            "name": "engine_load_pct",
            "unit": "%",
            "model_usage": "secondary_feature",
        },
        "0x5C": {
            "name": "obd_since_dtcs_cleared",
            "unit": "seconds",
            "model_usage": "metadata",
        },
        "0x60": {
            "name": "pedal_position_pct",
            "unit": "%",
            "model_usage": "secondary_feature",
        },
    }

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 38400):
        self.port = port
        self.baudrate = baudrate
        self._connected = False
        self._last_read_timestamp: float = 0.0

    # ------------------------------------------------------------------
    # Abstract method implementations from TelemetrySource
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Attempt to connect to the OBD-II adapter on the configured port.

        In this safe implementation, we do not actually attempt a real
        OBD-II connection (no hardware assumed). We simply mark the
        connection state and report what signals would be available.

        Returns
        -------
        bool
            Always returns False in this safe implementation since we
            do not assume EV-specific PIDs are available.
        """
        # Simulate connection attempt — in production, this would use
        # obd/python-obd library with actual hardware
        self._connected = True
        return False  # No EV-specific signals assumed available

    def disconnect(self) -> None:
        """Gracefully terminate the OBD-II connection."""
        self._connected = False

    def read(self) -> Optional[List[TelemetrySignal]]:
        """Read telemetry signals from the OBD-II adapter.

        Returns
        -------
        list of TelemetrySignal or None
            Signals read from the adapter. In this safe implementation,
            only standard (non-EV) signals are reported; EV-specific
            signals are explicitly UNAVAILABLE.
        """
        if not self._connected:
            return None

        # In a real implementation, this would query the OBD-II bus
        # using AT commands or a library like python-obd.
        # For this safe implementation, we return signals that are
        # known to be safe and non-EV-specific.

        signals: List[TelemetrySignal] = []

        # Report standard (non-EV) PID values as MISSING/UNNAVAILABLE
        # since we do not assume they are available
        for pid, info in self.STANDARD_PIDS.items():
            signals.append(TelemetrySignal(
                name=info["name"],
                value=None,
                unit=info["unit"],
                timestamp=0.0,
                status=SignalStatus.UNAVAILABLE,
                quality=SignalStatus.UNAVAILABLE,
                age_ms=0,
                source="obd_ii",
            ))

        # Explicitly report EV-specific signals as UNAVAILABLE
        # with documentation that they are not standard OBD-II PIDs
        for signal_name in ["SOC", "battery_voltage", "battery_current",
                           "battery_power", "motor_power"]:
            signals.append(TelemetrySignal(
                name=signal_name,
                value=None,
                unit="%",
                timestamp=0.0,
                status=SignalStatus.UNAVAILABLE,
                quality=SignalStatus.UNAVAILABLE,
                age_ms=0,
                source="obd_ii",
                provenance={"note": EV_SPECIFIC_PIDS.get(signal_name, "unknown")},
            ))

        return signals if signals else None

    def health(self) -> Dict[str, Any]:
        """Return the health status of the OBD-II adapter."""
        return {
            "connected": self._connected,
            "port": self.port,
            "last_read": self._last_read_timestamp,
            "status": "ok" if self._connected else "disconnected",
            "signals_available": len(self.available_signals()),
            "note": "EV-specific signals (SOC, voltage, current, power) "
                    "reported as UNAVAILABLE unless vehicle exposes them "
                    "via non-standard PIDs or dedicated interface",
        }

    def available_signals(self) -> List[str]:
        """Return the list of signal names this OBD-II adapter can provide."""
        signals: List[str] = []
        for pid_info in self.STANDARD_PIDS.values():
            signals.append(pid_info["name"])
        # EV-specific signals are NOT listed as available
        # (they are reported as UNAVAILABLE)
        return signals