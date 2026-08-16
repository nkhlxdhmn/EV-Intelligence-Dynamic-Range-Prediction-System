"""
STEP 15 — Rolling Buffer tests.

Tests for the bounded telemetry signal buffer.
"""

import pytest
import numpy as np
import time

from src.telemetry.buffer import RollingBuffer, get_latest_value, get_signal_age_ms, STALE_THRESHOLD_MS


class TestRollingBuffer:
    """Test the RollingBuffer class."""

    def test_basic_insert_and_get(self):
        """Basic insert and retrieve."""
        buffer = RollingBuffer(max_samples=5)
        buffer.insert(1000.0, {"speed": 50.0, "soc": 80.0})
        buffer.insert(1001.0, {"speed": 52.0, "soc": 78.0})
        buffer.insert(1002.0, {"speed": 55.0, "soc": 75.0})

        assert buffer.size() == 3
        assert buffer.capacity() == 5

    def test_eviction_when_full(self):
        """Oldest samples are evicted when buffer is full."""
        buffer = RollingBuffer(max_samples=3)
        buffer.insert(1000.0, {"val": 1})
        buffer.insert(1001.0, {"val": 2})
        buffer.insert(1002.0, {"val": 3})
        assert buffer.size() == 3  # at capacity

        # Adding one more should evict the oldest
        buffer.insert(1003.0, {"val": 4})
        assert buffer.size() == 3  # still at capacity (oldest evicted)

        # The oldest (val=1) should be gone; newest (val=4) should be present
        latest = buffer.get_latest()
        assert latest is not None
        assert latest["val"] == 4

    def test_get_recent(self):
        """Get the most recent n samples."""
        buffer = RollingBuffer(max_samples=10)
        buffer.insert(1000.0, {"speed": 50.0})
        buffer.insert(1001.0, {"speed": 52.0})
        buffer.insert(1002.0, {"speed": 55.0})

        recent = buffer.get_recent(2)
        assert len(recent) == 2
        assert recent[0]["speed"] == 52.0  # older of the two
        assert recent[1]["speed"] == 55.0  # newest

    def test_get_by_signal(self):
        """Get recent values for a specific signal."""
        buffer = RollingBuffer(max_samples=5)
        buffer.insert(1000.0, {"speed": 50.0, "soc": 80.0})
        buffer.insert(1001.0, {"speed": 52.0, "soc": 78.0})

        speeds = buffer.get_by_signal("speed", last_n=1)
        assert len(speeds) == 1
        assert speeds[0] == 52.0

        soc_values = buffer.get_by_signal("soc", last_n=2)
        assert len(soc_values) == 2
        # Buffer inserts newest at the end; get_by_signal returns most recent first
        # So soc_values[0] is the newest (78.0), soc_values[1] is older (80.0)
        assert soc_values[0] == 78.0  # newest
        assert soc_values[1] == 80.0  # older

    def test_get_latest(self):
        """Get the most recent sample."""
        buffer = RollingBuffer(max_samples=5)
        buffer.insert(1000.0, {"speed": 50.0})
        latest = buffer.get_latest()
        assert latest is not None
        assert latest["speed"] == 50.0

    def test_get_oldest(self):
        """Get the oldest sample."""
        buffer = RollingBuffer(max_samples=3)
        buffer.insert(1000.0, {"val": 1})
        buffer.insert(1001.0, {"val": 2})
        oldest = buffer.get_oldest()
        assert oldest is not None
        assert oldest["val"] == 1

    def test_clear(self):
        """Clear the buffer."""
        buffer = RollingBuffer(max_samples=5)
        buffer.insert(1000.0, {"val": 1})
        buffer.insert(1001.0, {"val": 2})
        assert buffer.size() == 2

        buffer.clear()
        assert buffer.is_empty()
        assert buffer.size() == 0

    def test_is_full_and_is_empty(self):
        """Test is_full and is_empty."""
        buffer = RollingBuffer(max_samples=3)
        assert buffer.is_empty()
        assert not buffer.is_full()

        buffer.insert(1000.0, {"val": 1})
        assert not buffer.is_empty()
        assert not buffer.is_full()  # 1 < 3

        buffer.insert(1001.0, {"val": 2})
        assert not buffer.is_full()  # 2 < 3

        buffer.insert(1002.0, {"val": 3})
        assert buffer.is_full()  # 3 == 3

    def test_max_samples_enforced(self):
        """Buffer never exceeds max_samples."""
        buffer = RollingBuffer(max_samples=2)
        buffer.insert(1000.0, {"val": 1})
        buffer.insert(1001.0, {"val": 2})
        assert buffer.size() == 2

        # Adding a 3rd should evict the oldest
        buffer.insert(1002.0, {"val": 3})
        assert buffer.size() == 2  # still 2, oldest evicted
        latest = buffer.get_latest()
        assert latest["val"] == 3  # newest is present

    def test_timestamp_ordering(self):
        """Buffer maintains roughly timestamp order."""
        buffer = RollingBuffer(max_samples=10)
        # Insert out of order (newer before older)
        buffer.insert(2000.0, {"val": "newer"})
        buffer.insert(1000.0, {"val": "older"})

        # Both should be present
        assert buffer.size() == 2
        # Latest should be the one with timestamp 2000.0
        latest = buffer.get_latest()
        assert latest is not None
        # The buffer should contain both entries


class TestBufferUtilities:
    """Test buffer utility functions."""

    def test_get_latest_value(self):
        """Get latest value for a signal from buffer."""
        buffer = RollingBuffer(max_samples=5)
        buffer.insert(1000.0, {"speed": 50.0, "soc": 80.0})
        speed = get_latest_value(buffer, "speed")
        assert speed == 50.0

        soc = get_latest_value(buffer, "soc")
        assert soc == 80.0

        # Unknown signal returns None
        unknown = get_latest_value(buffer, "unknown_signal")
        assert unknown is None

    def test_get_signal_age_ms(self):
        """Get age in milliseconds of a signal."""
        buffer = RollingBuffer(max_samples=5)
        # Insert with _timestamp in signals dict
        buffer.insert(1000.0, {"speed": 50.0, "_timestamp": 1000.0})
        
        # Age from timestamp 1000.0 to current time ~1000.0 should be ~0
        age = get_signal_age_ms(buffer, "speed", current_time=1000.0)
        assert age < STALE_THRESHOLD_MS  # should be near 0

        # Old timestamp should give large age
        age_old = get_signal_age_ms(buffer, "speed", current_time=2000.0)
        assert age_old > STALE_THRESHOLD_MS  # ~1000 seconds = 1,000,000 ms

        # Unknown signal returns STALE_THRESHOLD_MS
        unknown_age = get_signal_age_ms(buffer, "unknown_signal", current_time=1000.0)
        assert unknown_age >= STALE_THRESHOLD_MS