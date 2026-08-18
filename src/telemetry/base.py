"""
STEP 15 — Telemetry Source Base Interface.

Defines the abstract interface for all telemetry adapters.
Do not hard-code a specific vehicle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Signal status enumeration
# ---------------------------------------------------------------------------

class SignalStatus:
    """Status of a telemetry signal."""
    VALID = "VALID"
    MISSING = "MISSING"
    STALE = "STALE"
    INVALID = "INVALID"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Normalized signal representation
# ---------------------------------------------------------------------------

@dataclass
class TelemetrySignal:
    """Normalized telemetry signal with quality metadata."""
    name: str
    value: Any
    unit: str
    timestamp: float  # seconds since epoch (UTC)
    status: str = SignalStatus.VALID
    quality: str = "VALID"  # alias for status; maintained for compatibility
    age_ms: int = 0
    source: str = ""
    provenance: Optional[Dict[str, Any]] = None  # source-specific metadata


# ---------------------------------------------------------------------------
# TelemetrySource abstract base class
# ---------------------------------------------------------------------------

class TelemetrySource(ABC):
    """Abstract base class for all telemetry sources.

    Subclasses must implement the core methods: connect, disconnect, read,
    health check, and available signals reporting.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Attempt to establish a connection to the vehicle adapter.

        Returns
        -------
        bool
            True if connection succeeded, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully terminate the connection to the vehicle adapter."""
        raise NotImplementedError

    @abstractmethod
    def read(self) -> Optional[List[TelemetrySignal]]:
        """Read the latest telemetry signals from the adapter.

        Returns
        -------
        list of TelemetrySignal or None
            List of normalized signals, or None if no data available.
            Must not return unlimited accumulation; bounded output only.
        """
        raise NotImplementedError

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return the health status of the telemetry source.

        Returns
        -------
        dict
            Health information including connection status, last read
            timestamp, error messages, etc.
        """
        raise NotImplementedError

    @abstractmethod
    def available_signals(self) -> List[str]:
        """Return the list of signal names this source can provide.

        Returns
        -------
        list of str
            Signal names (must match entries in telemetry_schema.yaml).
        """
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        """Return a summary status of the source.

        Convenience method that calls health() and extracts key fields.
        Subclasses may override for more detailed status reporting.

        Returns
        -------
        dict
            Summary status dictionary.
        """
        h = self.health()
        return {
            "connected": h.get("connected", False),
            "last_read": h.get("last_read"),
            "available_signals": self.available_signals(),
        }