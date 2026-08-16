"""
STEP 15 — Telematics Adapter.

Generic interface for external telematics systems.

Support normalized input such as:
- JSON telemetry
- MQTT telemetry
- HTTP telemetry

Do not bind the project to one commercial provider.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from src.telemetry.base import TelemetrySignal, SignalStatus, TelemetrySource


# ---------------------------------------------------------------------------
# Telematics message types
# ---------------------------------------------------------------------------

@dataclass
class TelematicsMessage:
    """A telematics message received from an external system."""
    source: str  # e.g. "mqtt", "http", "json_file"
    topic: Optional[str] = None  # MQTT topic or HTTP endpoint
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[float] = None  # when received (seconds since epoch)
    qos: int = 0  # MQTT QoS level


# ---------------------------------------------------------------------------
# Telematics Adapter implementation
# ---------------------------------------------------------------------------

class TelematicsAdapter(TelemetrySource):
    """Generic telematics adapter supporting multiple input formats.

    This adapter is provider-agnostic: it does not bind the project to
    one commercial telematics vendor. It supports common input formats
    and normalizes them to the internal TelemetrySignal format.

    Supported input formats:
    - JSON: dict with signal name/value pairs
    - MQTT: messages on a topic with JSON payload
    - HTTP: GET/POST responses with JSON payload
    - File: JSON files containing telemetry data
    """

    def __init__(self, provider: str = "generic",
                 format_type: str = "json",
                 config: Optional[Dict[str, Any]] = None):
        """Initialize the telematics adapter.

        Parameters
        ----------
        provider : str
            Name of the telematics provider (for logging/identification).
        format_type : str
            Input format: "json", "mqtt", "http", or "file".
        config : dict, optional
            Provider-specific configuration:
            - For JSON: signal mapping dict {schema_name: raw_key}
            - For MQTT: broker address, topic subscription
            - For HTTP: endpoint URL, authentication
            - For file: file path or stream
        """
        self._provider = provider
        self._format_type = format_type
        self._config = config or {}
        self._connected = False
        self._last_message: Optional[TelematicsMessage] = None

        # Signal mapping: maps normalized signal names to raw payload keys
        # Populated from config depending on provider/format
        self._signal_mapping: Dict[str, str] = self._build_signal_mapping()

    # ------------------------------------------------------------------
    # Abstract method implementations from TelemetrySource
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to the telematics provider.

        Returns
        -------
        bool
            True if connection/initialization succeeded.
        """
        # Connection depends on format_type
        if self._format_type == "mqtt":
            # Would connect to MQTT broker
            self._connected = True  # placeholder
        elif self._format_type == "http":
            # Would verify HTTP endpoint
            self._connected = True  # placeholder
        elif self._format_type == "file":
            # Would verify file existence/readability
            self._connected = True  # placeholder
        else:  # json
            self._connected = True  # no connection needed for JSON input

        return self._connected

    def disconnect(self) -> None:
        """Disconnect from the telematics provider."""
        self._connected = False

    def read(self) -> Optional[List[TelemetrySignal]]:
        """Read the latest telemetry signals from the telematics source.

        Returns
        -------
        list of TelemetrySignal or None
            Normalized signals from the telematics source, or None
            if no data is available.
        """
        if not self._connected:
            return None

        # Generate sample signals based on format and config
        # In a real implementation, this would read from the actual
        # provider (MQTT broker, HTTP endpoint, file, etc.)

        signals: List[TelemetrySignal] = []

        if self._format_type == "json":
            signals = self._read_json_signals()
        elif self._format_type == "mqtt":
            signals = self._read_mqtt_signals()
        elif self._format_type == "http":
            signals = self._read_http_signals()
        elif self._format_type == "file":
            signals = self._read_file_signals()
        else:
            # Unknown format — return empty
            signals = []

        self._last_message = TelematicsMessage(
            source=self._provider,
            topic=getattr(self, '_last_topic', None),
            payload={},
            timestamp=None,
        )

        return signals if signals else None

    def _read_json_signals(self) -> List[TelemetrySignal]:
        """Read signals from a JSON payload.

        Uses _signal_mapping to map raw keys to normalized signal names.
        """
        payload = self._config.get("payload", {})
        if not isinstance(payload, dict):
            return []

        signals: List[TelemetrySignal] = []

        # Process each mapped signal
        for norm_name, raw_key in self._signal_mapping.items():
            if raw_key in payload:
                raw_value = payload[raw_key]
                # Determine unit from config or default
                unit = self._config.get("units", {}).get(norm_name, "")
                signals.append(TelemetrySignal(
                    name=norm_name,
                    value=raw_value,
                    unit=unit,
                    timestamp=self._last_message.timestamp or 0.0,
                    status=SignalStatus.VALID,
                    quality=SignalStatus.VALID,
                    age_ms=0,
                    source=self._provider,
                ))
            else:
                # Raw key not in payload — signal missing
                signals.append(TelemetrySignal(
                    name=norm_name,
                    value=None,
                    unit="",
                    timestamp=self._last_message.timestamp or 0.0,
                    status=SignalStatus.MISSING,
                    quality=SignalStatus.MISSING,
                    age_ms=0,
                    source=self._provider,
                ))

        return signals

    def _read_mqtt_signals(self) -> List[TelemetrySignal]:
        """Read signals from MQTT payload.

        In a real implementation, this would subscribe to a topic
        and read messages. For this implementation, returns empty.
        """
        return []

    def _read_http_signals(self) -> List[TelemetrySignal]:
        """Read signals from HTTP response.

        In a real implementation, this would make an HTTP request
        and parse the response. For this implementation, returns empty.
        """
        return []

    def _read_file_signals(self) -> List[TelemetrySignal]:
        """Read signals from a JSON file.

        In a real implementation, this would read from a file path
        configured in self._config. For this implementation, returns empty.
        """
        return []

    def health(self) -> Dict[str, Any]:
        """Return the health status of the telematics adapter."""
        return {
            "connected": self._connected,
            "provider": self._provider,
            "format_type": self._format_type,
            "signal_mapping_size": len(self._signal_mapping),
            "status": "ok" if self._connected else "disconnected",
            "note": f"Provider-agnostic telematics adapter supporting "
                    f"json/mqtt/http/file formats. Provider: {self._provider}",
        }

    def available_signals(self) -> List[str]:
        """Return the list of signal names this telematics adapter can provide.

        Returns
        -------
        list of str
            Signal names based on the signal mapping configuration.
        """
        return list(self._signal_mapping.keys())

    def _build_signal_mapping(self) -> Dict[str, str]:
        """Build the signal mapping from config.

        Returns
        -------
        dict[str, str]
            Mapping of normalized signal names to raw payload keys.
        """
        mapping: Dict[str, str] = {}
        # Default: no mapping; caller must configure
        # Example format would be provided per provider
        return mapping