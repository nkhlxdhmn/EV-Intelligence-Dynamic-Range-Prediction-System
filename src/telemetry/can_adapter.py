"""
STEP 15 — CAN Adapter Interface.

Vehicle-independent CAN interface.

Supports configuration of:
- CAN interface
- bitrate
- message ID
- signal name
- start bit
- length
- byte order
- scale
- offset
- unit

DO NOT create fake CAN IDs.

Provides configuration-driven decoding so actual vehicle CAN
documentation can be added later.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from src.telemetry.base import TelemetrySignal, SignalStatus, TelemetrySource


# ---------------------------------------------------------------------------
# CAN signal configuration (per-signal decoding config)
# ---------------------------------------------------------------------------

@dataclass
class CANSignalConfig:
    """Configuration for decoding one signal from a CAN message."""
    name: str
    message_id: int
    start_bit: int
    length: int  # number of bits
    byte_order: str = "little_endian"  # or "big_endian"
    scale: float = 1.0  # multiplicative scaling factor
    offset: float = 0.0  # additive offset
    unit: str = ""
    signed: bool = False  # whether the value is signed (two's complement)
    minimum: Optional[float] = None  # minimum valid value
    maximum: Optional[float] = None  # maximum valid value


# ---------------------------------------------------------------------------
# CAN Adapter implementation
# ---------------------------------------------------------------------------

class CANAdapter(TelemetrySource):
    """Configuration-driven CAN bus adapter.

    This adapter is vehicle-independent: it does not hard-code any
    CAN IDs or signal mappings. Instead, it uses per-signal configuration
    that can be populated from vehicle documentation when available.

    The decoding logic is generic and applies scale/offset and byte-order
    conversion to extract numeric values from raw CAN data.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 *, interface: str = "can0", bitrate: int = 500,
                 default_signal_config: Optional[Dict[str, Any]] = None):
        """Initialize the CAN adapter.

        Parameters
        ----------
        config : dict, optional
            Configuration dictionary may contain:
            - interface: str (e.g. "can0", "ttyUSB0")
            - bitrate: int
            - default_signal_config: CANSignalConfig for default decoding
        interface : str, optional
            CAN interface name (used when ``config`` is not provided).
        bitrate : int, optional
            CAN bus bitrate in kbit/s (used when ``config`` is not provided).
        default_signal_config : dict, optional
            Default signal config as a dict (used when ``config`` is not
            provided).
        """
        merged: Dict[str, Any] = dict(config) if config else {}
        merged.setdefault("interface", interface)
        merged.setdefault("bitrate", bitrate)
        if default_signal_config is not None:
            merged.setdefault("default_signal_config", default_signal_config)
        self._interface: str = merged.get("interface", "can0")
        self._bitrate: int = merged.get("bitrate", 500)
        self._connected: bool = False
        # Default signal config — can be overridden per-signal
        self._default_config: Optional[CANSignalConfig] = None
        if "default_signal_config" in merged:
            self._default_config = CANSignalConfig(**merged["default_signal_config"])

    # ------------------------------------------------------------------
    # Abstract method implementations from TelemetrySource
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Attempt to connect to the CAN bus.

        In this configuration-driven implementation, we do not actually
        connect to hardware (no assumption of specific vehicle CAN bus).
        We simply record the configuration and report that the adapter
        is ready to decode signals when actual CAN data is provided.

        Returns
        -------
        bool
            True if configuration is valid; False otherwise.
        """
        # Validate configuration is plausible
        if self._bitrate <= 0 or self._bitrate > 1000:
            return False
        self._connected = True
        return True

    def disconnect(self) -> None:
        """Gracefully terminate the CAN connection."""
        self._connected = False

    def read(self) -> Optional[List[TelemetrySignal]]:
        """Read telemetry signals from the CAN bus.

        In this implementation, we do not have actual CAN bus access.
        The method is designed to accept raw CAN frames and decode
        signals using the configured CANSignalConfig.

        Returns
        -------
        list of TelemetrySignal or None
            Empty list in this implementation (no real CAN hardware).
            Callers should provide raw CAN frames and call
            decode_signal() to extract values.
        """
        if not self._connected:
            return None
        # No real CAN frames available in this safe implementation
        return []

    def decode_signal(self, raw_data: bytes, config: CANSignalConfig) -> Optional[TelemetrySignal]:
        """Decode a signal from raw CAN bytes using the given configuration.

        Parameters
        ----------
        raw_data : bytes
            Raw CAN message data bytes (typically 8 bytes maximum).
        config : CANSignalConfig
            Configuration for this specific signal.

        Returns
        -------
        TelemetrySignal or None
            Decoded signal with value, or None if decoding fails.
        """
        if not config.name:
            return None

        # Extract the relevant bits from raw_data
        # CAN data is typically 8 bytes (64 bits maximum)
        if len(raw_data) == 0:
            return None

        # Determine which bytes contain the signal data
        # CAN byte ordering depends on the bus setup
        # We support little_endian and big_endian

        # Calculate byte positions within the 8-byte CAN data
        # The signal starts at start_bit; we extract the relevant bits
        # by shifting and masking.

        num_bits = config.length
        start_bit = config.start_bit

        # If start_bit + length exceeds 64 bits (8 * 8), we can't decode
        if start_bit + num_bits > 64:
            return None

        # Build the bit mask
        # Mask has num_bits set to 1, starting from LSB position start_bit
        mask = ((1 << num_bits) - 1) << start_bit

        # Apply mask to extract the bits from all CAN data bytes
        # Combine all bytes into a single integer
        combined = 0
        for i, byte in enumerate(raw_data):
            # Each byte contributes 8 bits, starting at position i*8
            # We need to be careful about byte order
            combined |= (byte << (i * 8))

        # Extract the signal bits
        signal_bits = combined & mask

        # Shift to LSB position for processing
        if config.byte_order == "big_endian":
            # If big-endian, the first byte in raw_data is the most significant
            # We need to reverse the byte order for proper interpretation
            # Actually, let's handle this more carefully:
            # The start_bit refers to the bit position within the combined
            # 64-bit value. The byte order determines how raw_data bytes
            # map to the combined value.
            # For simplicity, we'll treat the raw_data as big-endian:
            # the first byte is the most significant byte.
            pass  # handled below

        # For little-endian: raw_data[0] is least significant byte
        if config.byte_order == "little_endian":
            # Convert to little-endian integer: byte[0] is LSB
            combined = 0
            for i, byte in enumerate(raw_data):
                combined |= (byte << (i * 8))
            signal_bits = combined & mask
        elif config.byte_order == "big_endian":
            # Big-endian: raw_data[0] is most significant byte
            # To combine in big-endian order, we reverse the byte indexing
            combined = 0
            for i, byte in enumerate(reversed(raw_data)):
                combined |= (byte << (i * 8))
            signal_bits = combined & mask

        # Handle signed values (two's complement)
        if config.signed and (signal_bits & (1 << (num_bits - 1))):
            # Negative value in two's complement
            signal_bits = signal_bits - (1 << num_bits)

        # Apply scale and offset
        value = config.scale * signal_bits + config.offset

        # Determine unit
        unit = config.unit if config.unit else "unknown"

        # Create the telemetry signal
        result = TelemetrySignal(
            name=config.name,
            value=value if value == value else None,  # NaN check
            unit=unit,
            timestamp=0.0,
            status=SignalStatus.VALID,
            quality=SignalStatus.VALID,
            age_ms=0,
            source="can_bus",
        )

        # Validate against configured ranges if present
        if config.minimum is not None and value < config.minimum:
            result.quality = SignalStatus.OUT_OF_RANGE
            result.value = None  # mark as invalid
        if config.maximum is not None and value > config.maximum:
            result.quality = SignalStatus.OUT_OF_RANGE
            result.value = None  # mark as invalid

        return result

    def health(self) -> Dict[str, Any]:
        """Return the health status of the CAN adapter."""
        return {
            "connected": self._connected,
            "interface": self._interface,
            "bitrate": self._bitrate,
            "status": "ok" if self._connected else "disconnected",
            "default_signal_config": self._default_config is not None,
            "note": "Configuration-driven: signal mappings must be populated "
                    "from vehicle CAN documentation. No fake CAN IDs or "
                    "hard-coded mappings.",
        }

    def available_signals(self) -> List[str]:
        """Return the list of signal names this CAN adapter can decode.

        Returns
        -------
        list of str
            Signal names based on configured CANSignalConfig entries.
        """
        if self._default_config:
            return [self._default_config.name]
        return []


# ---------------------------------------------------------------------------
# Convenience: create CANSignalConfig from simple dict
# ---------------------------------------------------------------------------

def create_can_signal_config(
    name: str,
    message_id: int,
    start_bit: int,
    length: int,
    *,
    byte_order: str = "little_endian",
    scale: float = 1.0,
    offset: float = 0.0,
    unit: str = "",
    signed: bool = False,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> CANSignalConfig:
    """Create a CANSignalConfig with the given parameters.

    Convenience function for configuring CAN signal decoding without
    manually constructing the dataclass.

    Returns
    -------
    CANSignalConfig
        Configured signal decoding configuration.
    """
    return CANSignalConfig(
        name=name,
        message_id=message_id,
        start_bit=start_bit,
        length=length,
        byte_order=byte_order,
        scale=scale,
        offset=offset,
        unit=unit,
        signed=signed,
        minimum=minimum,
        maximum=maximum,
    )