"""
STEP 15 — OBD-II Adapter tests.

Tests for the safe OBD-II adapter that does not assume EV-specific PIDs.
"""

import pytest
from src.telemetry.obd_adapter import OBDAdapter, SignalStatus


class TestOBDAdapter:
    """Test the OBDAdapter class."""

    def test_adapter_creation(self):
        """OBDAdapter can be created with default parameters."""
        adapter = OBDAdapter(port="/dev/ttyUSB0", baudrate=38400)
        assert adapter is not None

    def test_connect_returns_false(self):
        """In safe implementation, connect returns False (no EV-specific PIDs assumed)."""
        adapter = OBDAdapter()
        # In safe implementation, we don't assume EV signals are available
        result = adapter.connect()
        # The safe implementation returns False since no EV-specific PIDs are assumed
        assert result is False

    def test_disconnect(self):
        """Disconnect clears the connection state."""
        adapter = OBDAdapter()
        adapter.connect()
        adapter.disconnect()
        # After disconnect, should not be connected
        health = adapter.health()
        assert health["connected"] is False

    def test_read_returns_signals(self):
        """Read returns telemetry signals (all UNAVAILABLE/MISSING in safe mode)."""
        adapter = OBDAdapter()
        adapter.connect()
        signals = adapter.read()
        # In safe mode, all signals are UNAVAILABLE
        assert signals is not None
        assert len(signals) > 0

        # All signals should be UNAVAILABLE or MISSING
        for sig in signals:
            assert sig.status in [SignalStatus.UNAVAILABLE, SignalStatus.MISSING]
            assert sig.quality in [SignalStatus.UNAVAILABLE, SignalStatus.MISSING]

    def test_health(self):
        """Health report includes expected fields."""
        adapter = OBDAdapter()
        health = adapter.health()
        assert "connected" in health
        assert "port" in health
        assert "status" in health
        assert "signals_available" in health

    def test_available_signals(self):
        """Available signals list does not include EV-specific signals."""
        adapter = OBDAdapter()
        signals = adapter.available_signals()
        # EV-specific signals should NOT be listed as available
        # (they are reported as UNAVAILABLE)
        assert "SOC" not in signals
        assert "battery_voltage" not in signals
        assert "battery_current" not in signals
        assert "battery_power" not in signals
        assert "motor_power" not in signals

    def test_ev_specific_signals_reported_unavailable(self):
        """EV-specific signals are explicitly reported as UNAVAILABLE."""
        adapter = OBDAdapter()
        adapter.connect()
        signals = adapter.read()

        # Find SOC signal
        soc_signals = [s for s in signals if s.name == "SOC"]
        if soc_signals:
            assert soc_signals[0].status == SignalStatus.UNAVAILABLE
            assert soc_signals[0].quality == SignalStatus.UNAVAILABLE

        # Find battery voltage signal
        volt_signals = [s for s in signals if "voltage" in s.name.lower()]
        if volt_signals:
            assert volt_signals[0].status == SignalStatus.UNAVAILABLE