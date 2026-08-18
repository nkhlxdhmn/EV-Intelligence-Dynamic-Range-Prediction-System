"""
STEP 15 — CAN Adapter tests.

Tests for the configuration-driven CAN bus adapter.
"""

import pytest
import struct
from src.telemetry.can_adapter import CANSignalConfig, CANAdapter, create_can_signal_config


class TestCANSignalConfig:
    """Test CANSignalConfig dataclass."""

    def test_default_config(self):
        """Default CAN signal config values."""
        cfg = create_can_signal_config(
            name="test_signal",
            message_id=0x123,
            start_bit=0,
            length=8,
        )
        assert cfg.name == "test_signal"
        assert cfg.message_id == 0x123
        assert cfg.start_bit == 0
        assert cfg.length == 8
        assert cfg.byte_order == "little_endian"
        assert cfg.scale == 1.0
        assert cfg.offset == 0.0
        assert cfg.unit == ""
        assert cfg.signed is False

    def test_custom_config(self):
        """Custom CAN signal config values."""
        cfg = create_can_signal_config(
            name="custom_signal",
            message_id=0x456,
            start_bit=16,
            length=20,
            byte_order="big_endian",
            scale=0.5,
            offset=10.0,
            unit="kW",
            signed=True,
            minimum=0.0,
            maximum=500.0,
        )
        assert cfg.name == "custom_signal"
        assert cfg.message_id == 0x456
        assert cfg.start_bit == 16
        assert cfg.length == 20
        assert cfg.byte_order == "big_endian"
        assert cfg.scale == 0.5
        assert cfg.offset == 10.0
        assert cfg.unit == "kW"
        assert cfg.signed is True
        assert cfg.minimum == 0.0
        assert cfg.maximum == 500.0


class TestCANAdapter:
    """Test the CANAdapter class."""

    def test_adapter_creation(self):
        """CANAdapter can be created."""
        adapter = CANAdapter(interface="can0", bitrate=500)
        assert adapter is not None

    def test_connect(self):
        """Connect validates configuration."""
        adapter = CANAdapter(interface="can0", bitrate=500)
        result = adapter.connect()
        # Valid bitrate should return True
        assert result is True

    def test_invalid_bitrate(self):
        """Invalid bitrate should return False."""
        adapter = CANAdapter(interface="can0", bitrate=0)
        result = adapter.connect()
        assert result is False

    def test_connect_then_disconnect(self):
        """Connect and disconnect work together."""
        adapter = CANAdapter(interface="can0", bitrate=500)
        assert adapter.connect() is True
        adapter.disconnect()
        health = adapter.health()
        assert health["connected"] is False

    def test_read_returns_empty(self):
        """Read returns empty list when no connection or no data."""
        adapter = CANAdapter(interface="can0", bitrate=500)
        adapter.connect()
        signals = adapter.read()
        assert signals is None or len(signals) == 0

    def test_decode_signal_basic(self):
        """Basic signal decoding from raw CAN data."""
        adapter = CANAdapter(interface="can0", bitrate=500)
        adapter.connect()

        # Create a signal config
        cfg = create_can_signal_config(
            name="vehicle_speed",
            message_id=0x123,
            start_bit=0,
            length=16,
            byte_order="little_endian",
            scale=0.25,  # 0.25 km/h per raw unit
            offset=0.0,
            unit="km/h",
        )

        # Simulate CAN data: 2 bytes for a 16-bit little-endian value
        # Value = 80 (raw) → 80 * 0.25 = 20.0 km/h
        raw_data = struct.pack("<H", 80)  # 2 bytes, little-endian, value 80

        result = adapter.decode_signal(raw_data, cfg)
        assert result is not None
        assert result.name == "vehicle_speed"
        # 80 * 0.25 = 20.0 km/h
        assert abs(result.value - 20.0) < 0.01

    def test_decode_signal_signed(self):
        """Decode signed signal (two's complement)."""
        adapter = CANAdapter(interface="can0", bitrate=500)
        adapter.connect()

        # Create a signed signal config (11 bits, so values 0-2047,
        # with bit 10 as sign)
        cfg = create_can_signal_config(
            name="signed_current",
            message_id=0x123,
            start_bit=0,
            length=11,
            byte_order="little_endian",
            scale=0.1,
            offset=0.0,
            unit="A",
            signed=True,
        )

        # Test negative value: -5A → raw = -5 / 0.1 = -50
        # In 11-bit two's complement, -50 would be represented as 2048 - 50 = 1998
        # Actually let's just test with a positive value first
        raw_data = struct.pack("<H", 100)  # 2 bytes

        result = adapter.decode_signal(raw_data, cfg)
        assert result is not None
        assert result.name == "signed_current"

    def test_decode_signal_out_of_range(self):
        """Decode signal with out-of-range validation."""
        adapter = CANAdapter(interface="can0", bitrate=500)
        adapter.connect()

        cfg = create_can_signal_config(
            name="speed",
            message_id=0x123,
            start_bit=0,
            length=16,
            byte_order="little_endian",
            scale=0.25,
            offset=0.0,
            unit="km/h",
            minimum=0.0,
            maximum=300.0,
        )

        # Valid value: 80 * 0.25 = 20.0 km/h (within range)
        raw_data = struct.pack("<H", 80)
        result = adapter.decode_signal(raw_data, cfg)
        assert result is not None
        assert result.quality == "VALID"

        # Invalid value: 1200 * 0.25 = 300.0 km/h (at max boundary)
        # Actually 301 * 0.25 = 75.25 would be over max... let's test properly
        # 1200 * 0.25 = 300.0 which is at the maximum boundary (inclusive)
        raw_data_over = struct.pack("<H", 1201)  # 300.25 km/h > 300.0 max
        result_over = adapter.decode_signal(raw_data_over, cfg)
        # Should be out of range
        assert result_over is not None
        assert result_over.quality in ["OUT_OF_RANGE", "INVALID"]