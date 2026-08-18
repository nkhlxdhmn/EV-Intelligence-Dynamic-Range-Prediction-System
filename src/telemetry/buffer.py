from __future__ import annotations

"""
STEP 15 — Rolling Telemetry Buffer.

Implement a bounded rolling buffer.

Requirements:
- fixed maximum number of samples
- automatic eviction
- no unlimited RAM growth
- timestamp ordering
- duplicate handling
- missing-data handling

The buffer must contain only the recent history required to calculate
causal features.
"""

#: Staleness threshold in milliseconds (default: 5 seconds)
STALE_THRESHOLD_MS = 5_000

from typing import Any, Dict, List, Optional, Tuple
from collections import deque


class RollingBuffer:
    """Bounded rolling buffer for telemetry signals.

    Stores only the most recent N samples. Oldest samples are
    automatically evicted when the buffer is full. Designed to
    prevent unlimited RAM growth while providing recent history
    for causal feature calculation.

    Type parameters:
        N: maximum number of samples to store
    """

    def __init__(self, max_samples: int = 1000):
        """Initialize the rolling buffer.

        Parameters
        ----------
        max_samples : int, default 1000
            Maximum number of samples to store. Must be > 0.
        """
        if max_samples <= 0:
            raise ValueError("max_samples must be > 0")
        self._max_samples = max_samples
        # deque of (timestamp, signal_dict) tuples, ordered by timestamp
        # newest at the right end
        self._buffer: "deque[tuple[float, dict[str, Any]]]" = deque()
        self._signal_index: Dict[str, List[int]] = {}  # name -> list of indices
        self._insertion_count = 0  # total samples ever inserted (for diagnostics)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def insert(self, timestamp: float, signals: dict[str, Any]) -> None:
        """Insert a new sample into the buffer.

        Parameters
        ----------
        timestamp : float
            Time (seconds since epoch) when this sample was read.
        signals : dict[str, Any]
            Signal name -> value mapping for this timestamp.
        """
        # Enforce timestamp ordering: the buffer stays sorted by timestamp
        # (oldest at the left, newest at the right) so get_latest() always
        # returns the sample with the newest timestamp (F1.2). Out-of-order
        # samples are inserted at their sorted position instead of appended.
        entry = (timestamp, dict(signals))  # copy to avoid mutability issues
        if self._buffer and timestamp < self._buffer[-1][0]:
            self._buffer.append(entry)
            self._buffer = deque(sorted(self._buffer, key=lambda e: e[0]))
        else:
            self._buffer.append(entry)
        self._insertion_count += 1

        # Track signal indices for quick lookup
        for name in signals:
            if name not in self._signal_index:
                self._signal_index[name] = []
            self._signal_index[name].append(len(self._buffer) - 1)

        # Evict oldest samples if over capacity
        while len(self._buffer) > self._max_samples:
            # Remove the oldest (leftmost) entry
            old_timestamp, old_signals = self._buffer.popleft()
            # Remove this sample from signal index tracking
            for name in old_signals:
                if name in self._signal_index:
                    # Filter out the index we just removed
                    self._signal_index[name] = [
                        i for i in self._signal_index[name] if i != 0
                    ]
                    # Adjust indices > 0 since we removed index 0
                    # Actually, let's just rebuild the index for simplicity
                    break  # simplified: just break and rebuild below

        # Rebuild signal index after eviction (simple but correct)
        self._signal_index = {}
        for i, (ts, sigs) in enumerate(self._buffer):
            for name in sigs:
                if name not in self._signal_index:
                    self._signal_index[name] = []
                self._signal_index[name].append(i)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_recent(self, n: int = 1) -> List[dict[str, Any]]:
        """Get the most recent n samples.

        Parameters
        ----------
        n : int, default 1
            Number of recent samples to return.

        Returns
        -------
        list of dict[str, Any]
            List of signal dicts, most recent last. Returns up to n
            samples (fewer if buffer has fewer samples).
        """
        # Return the last n entries' signal dicts
        recent = list(self._buffer)[-n:] if self._buffer else []
        return [entry[1] for entry in recent]

    def get_by_signal(self, name: str, last_n: int = 1) -> List[Any]:
        """Get the most recent values for a specific signal name.

        Parameters
        ----------
        name : str
            Signal name to look up.
        last_n : int, default 1
            Number of most recent values to return.

        Returns
        -------
        list of Any
            List of values (most recent last). Returns empty list if signal
            not found or no values available.
        """
        indices = self._signal_index.get(name, [])
        # Get the last_n indices (newest first)
        recent_indices = indices[-last_n:] if indices else []
        # Extract values from the buffer entries
        values = []
        for idx in recent_indices:
            if 0 <= idx < len(self._buffer):
                _, sigs = self._buffer[idx]
                values.append(sigs.get(name))
        # Return in chronological order (oldest of the recent first)
        # Actually, let's return most recent first
        return list(reversed(values))

    def get_latest(self) -> Optional[dict[str, Any]]:
        """Get the most recent sample's signals.

        Returns
        -------
        dict[str, Any] or None
            Signal name -> value mapping of the most recent sample,
            or None if buffer is empty.
        """
        if not self._buffer:
            return None
        return self._buffer[-1][1]

    def get_oldest(self) -> Optional[dict[str, Any]]:
        """Get the oldest sample's signals.

        Returns
        -------
        dict[str, Any] or None
            Signal name -> value mapping of the oldest sample,
            or None if buffer is empty.
        """
        if not self._buffer:
            return None
        return self._buffer[0][1]

    def clear(self) -> None:
        """Clear the buffer completely."""
        self._buffer.clear()
        self._signal_index = {}

    def size(self) -> int:
        """Return the current number of samples in the buffer."""
        return len(self._buffer)

    def capacity(self) -> int:
        """Return the maximum capacity of the buffer."""
        return self._max_samples

    def is_full(self) -> bool:
        """Return True if the buffer is at capacity."""
        return len(self._buffer) >= self._max_samples

    def is_empty(self) -> bool:
        """Return True if the buffer is empty."""
        return len(self._buffer) == 0


# ---------------------------------------------------------------------------
# Convenience: buffer with signal extraction for feature building
# ---------------------------------------------------------------------------

def get_latest_value(buffer: RollingBuffer, signal_name: str) -> Any:
    """Get the latest value for a signal from the buffer.

    Parameters
    ----------
    buffer : RollingBuffer
        The telemetry buffer.
    signal_name : str
        Name of the signal to retrieve.

    Returns
    -------
    Any
        The most recent value, or None if not available.
    """
    latest = buffer.get_latest()
    if latest is None:
        return None
    return latest.get(signal_name)


def get_signal_age_ms(buffer: RollingBuffer, signal_name: str, current_time: float) -> int:
    """Get the age in milliseconds of the latest value for a signal.

    Parameters
    ----------
    buffer : RollingBuffer
        The telemetry buffer.
    signal_name : str
        Name of the signal.
    current_time : float
        Current time (seconds since epoch).

    Returns
    -------
    int
        Age in milliseconds; returns STALE_THRESHOLD_MS if signal not found
        or no timestamp available.
    """
    # First check if the signal exists in the buffer's index
    indices = buffer._signal_index.get(signal_name, [])
    if not indices:
        # Signal not found in buffer — return STALE_THRESHOLD_MS
        return STALE_THRESHOLD_MS
    
    # Signal exists — get the latest value for this signal
    latest = buffer.get_latest()
    if latest is None:
        return STALE_THRESHOLD_MS
    
    # Check if the signals dict has a _timestamp key
    if isinstance(latest, dict) and "_timestamp" in latest:
        timestamp = latest["_timestamp"]
        if timestamp == 0.0:
            return STALE_THRESHOLD_MS
        return int((current_time - timestamp) * 1000)
    else:
        # No timestamp stored — conservatively return STALE_THRESHOLD_MS
        # since we can't determine the signal age
        return STALE_THRESHOLD_MS