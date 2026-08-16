"""
STEP 15 — Signal Quality Assessment.

Every live signal should have:
- value
- timestamp
- source
- valid
- quality
- age_ms

Quality states:
- VALID
- MISSING
- STALE
- INVALID
- OUT_OF_RANGE
- UNAVAILABLE

Reject stale telemetry from being silently used.

Example:
    If speed has not updated for 5 seconds:
    speed_quality = STALE
    Do not treat it as current speed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass

#: Staleness threshold in milliseconds (default: 5 seconds)
STALE_THRESHOLD_MS = 5_000


# ---------------------------------------------------------------------------
# Quality result
# ---------------------------------------------------------------------------

@dataclass
class QualityResult:
    """Result of quality assessment for a single signal."""
    valid: bool
    quality: str  # One of: VALID, MISSING, STALE, INVALID, OUT_OF_RANGE, UNAVAILABLE
    age_ms: int
    message: str  # Human-readable explanation


# ---------------------------------------------------------------------------
# Per-signal quality assessment
# ---------------------------------------------------------------------------

def assess_signal_quality(
    value: Any,
    timestamp: float,
    current_time: float,
    *,
    stale_threshold_ms: int = STALE_THRESHOLD_MS,
    valid_range: Optional[Tuple[float, float]] = None,
) -> QualityResult:
    """Assess the quality of a single telemetry signal.

    Parameters
    ----------
    value : any
        The signal value; None means missing.
    timestamp : float
        Time (seconds since epoch) when this value was generated/read.
    current_time : float
        Current time (seconds since epoch) for staleness computation.
    stale_threshold_ms : int, default 5_000
        Maximum age in milliseconds before a signal is considered STALE.
    valid_range : tuple of (min, max), optional
        (min, max) valid range for the signal. If value falls outside,
        quality = OUT_OF_RANGE.

    Returns
    -------
    QualityResult
        Structured quality assessment.
    """
    age_ms = int((current_time - timestamp) * 1000)

    # ------------------------------------------------------------------
    # Step 1: Handle missing value (None or NaN)
    # ------------------------------------------------------------------
    if value is None or (isinstance(value, float) and value != value):
        # Value is None or NaN
        return QualityResult(
            valid=False,
            quality="MISSING",
            age_ms=age_ms,
            message="Signal value is missing (None or NaN)",
        )

    # ------------------------------------------------------------------
    # Step 2: Check staleness
    # ------------------------------------------------------------------
    if age_ms > stale_threshold_ms:
        return QualityResult(
            valid=True,
            quality="STALE",
            age_ms=age_ms,
            message=f"Signal is STALE (age={age_ms} ms > {stale_threshold_ms} ms threshold)",
        )

    # ------------------------------------------------------------------
    # Step 3: Check valid range
    # ------------------------------------------------------------------
    if valid_range is not None:
        min_val, max_val = valid_range
        if isinstance(value, (int, float)):
            if value < min_val or value > max_val:
                return QualityResult(
                    valid=False,
                    quality="OUT_OF_RANGE",
                    age_ms=age_ms,
                    message=f"Value {value} outside valid range [{min_val}, {max_val}]",
                )

    # ------------------------------------------------------------------
    # Step 4: All checks passed — signal is VALID
    # ------------------------------------------------------------------
    return QualityResult(
        valid=True,
        quality="VALID",
        age_ms=age_ms,
        message="Signal quality is VALID",
    )


# ---------------------------------------------------------------------------
# Bulk quality assessment
# ---------------------------------------------------------------------------

def assess_signal_quality_batch(
    signals: list[dict[str, Any]],
    current_time: float,
    *,
    stale_threshold_ms: int = STALE_THRESHOLD_MS,
) -> list[QualityResult]:
    """Assess quality for a batch of signals.

    Parameters
    ----------
    signals : list of dict
        Each dict should have: name, value, timestamp, [source], [unit].
    current_time : float
        Current time (seconds since epoch) for staleness computation.
    stale_threshold_ms : int, default 5_000

    Returns
    -------
    list of QualityResult
        Quality assessment for each signal, in the same order.
    """
    results: list[QualityResult] = []
    for sig in signals:
        name = sig.get("name", "unknown")
        value = sig.get("value")
        timestamp = sig.get("timestamp", current_time)
        valid_range = sig.get("valid_range")
        result = assess_signal_quality(
            value=value,
            timestamp=timestamp,
            current_time=current_time,
            stale_threshold_ms=stale_threshold_ms,
            valid_range=valid_range,
        )
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Quality summary
# ---------------------------------------------------------------------------

def quality_summary(results: list[QualityResult]) -> Dict[str, Any]:
    """Produce a summary counts from quality assessment results.

    Parameters
    ----------
    results : list of QualityResult

    Returns
    -------
    dict
        Counts per quality state and overall assessment.
    """
    counts: Dict[str, int] = {
        "VALID": 0,
        "MISSING": 0,
        "STALE": 0,
        "INVALID": 0,
        "OUT_OF_RANGE": 0,
        "UNAVAILABLE": 0,
    }

    for r in results:
        counts[r.quality] = counts.get(r.quality, 0) + 1

    # Determine overall status
    if counts["UNAVAILABLE"] > 0 and counts["VALID"] == 0:
        overall = "offline"
    elif counts["STALE"] > counts["VALID"] and counts["STALE"] > counts["MISSING"]:
        overall = "degraded"
    elif counts["MISSING"] > 0 and counts["VALID"] == 0:
        overall = "insufficient_data"
    else:
        overall = "ok"

    return {
        "counts": counts,
        "overall": overall,
        "total": len(results),
        "valid_fraction": counts["VALID"] / len(results) if results else 0.0,
    }