"""
STEP 15I - Real-time telemetry quality monitor.

Checks each incoming telemetry reading for validity and assigns a quality
rating: good / warning / invalid.

Rules are derived from train+validation data constraints. Does not aggressively
discard data without documenting the rule.
"""

from __future__ import annotations
from typing import Any, Dict, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Quality thresholds (derived from DEVRT train+validation fleet)
# These would normally be loaded from reports/step15_reference_statistics.json
# ---------------------------------------------------------------------------

SOC_VALID_RANGE = (0.0, 100.0)
SOC_WARNING_ZONE_LOW = 10.0
SOC_WARNING_ZONE_HIGH = 95.0

SPEED_VALID_RANGE = (0.0, 200.0)
SPEED_WARNING_THRESHOLD = 150.0  # km/h above which = warning

ALTITUDE_VALID_RANGE = (0.0, 5000.0)
TEMPERATURE_VALID_RANGE = (-40.0, 80.0)

# Timestamp freshness: data older than this (minutes) is stale
STALE_TELEMETRY_MAX_AGE_MIN = 60


# ---------------------------------------------------------------------------
# Sensor quality assessment
# ---------------------------------------------------------------------------


def assess_timestamp_validity(timestamp: Any, current_time: Optional[float] = None) -> dict[str, Any]:
    """Check timestamp validity and freshness.

    Returns dict with:
        - "rating": "good" | "warning" | "invalid"
        - "valid": bool
        - "reason": str | None
        - "stale": bool (data too old)
        - "age_minutes": float | None
    """
    result: dict[str, Any] = {
        "rating": "good",
        "valid": False,
        "reason": None,
        "stale": False,
        "age_minutes": None,
    }

    if timestamp is None:
        result["rating"] = "invalid"
        result["reason"] = "missing timestamp"
        return result

    try:
        from datetime import datetime, timezone

        ts = timestamp
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        # Ensure UTC
        if ts.tzinfo is None:
            result["rating"] = "invalid"
            result["reason"] = "timestamp not timezone-aware (expected UTC)"
            return result
        else:
            ts = ts.astimezone(timezone.utc)

        now = datetime.now(timezone.utc)
        age_seconds = (now - ts).total_seconds()
        age_minutes = age_seconds / 60.0

        result["age_minutes"] = round(age_minutes, 2)

        if age_minutes > STALE_TELEMETRY_MAX_AGE_MIN:
            result["rating"] = "warning"
            result["stale"] = True
            result["reason"] = f"telemetry is {age_minutes:.1f} min old (max {STALE_TELEMETRY_MAX_AGE_MIN} min)"

        if not result["stale"] and not result["reason"]:
            result["rating"] = "good"
            result["valid"] = True
            result["reason"] = "valid"

    except Exception as e:
        result["rating"] = "invalid"
        result["reason"] = f"timestamp parse error: {e}"

    return result


def assess_soc_quality(soc_pct: float) -> dict[str, Any]:
    """Assess SOC quality.

    Returns:
        - "rating": "good" | "warning" | "invalid"
        - "value": the SOC value
        - "reason": human-readable explanation
    """
    result: dict[str, Any] = {
        "rating": "good",
        "value": soc_pct,
        "reason": None,
    }

    if soc_pct is None:
        result["rating"] = "invalid"
        result["reason"] = "SOC missing"
        return result

    if not (SOC_VALID_RANGE[0] <= soc_pct <= SOC_VALID_RANGE[1]):
        result["rating"] = "invalid"
        result["reason"] = f"SOC {soc_pct}% outside valid range {SOC_VALID_RANGE}"
        return result

    # Warning zones
    if soc_pct <= SOC_WARNING_ZONE_LOW:
        result["rating"] = "warning"
        result["reason"] = f"SOC {soc_pct}% very low (below {SOC_WARNING_ZONE_LOW}%)"
    elif soc_pct >= SOC_WARNING_ZONE_HIGH:
        result["rating"] = "warning"
        result["reason"] = f"SOC {soc_pct}% very high (above {SOC_WARNING_ZONE_HIGH}%)"
    else:
        result["rating"] = "good"
        result["reason"] = "SOC within normal operating range"

    return result


def assess_speed_quality(speed_kmh: float) -> dict[str, Any]:
    """Assess speed sensor quality.

    Returns:
        - "rating": "good" | "warning" | "invalid"
        - "value": the speed value
        - "reason": human-readable explanation
    """
    result: dict[str, Any] = {
        "rating": "good",
        "value": speed_kmh,
        "reason": None,
    }

    if speed_kmh is None:
        result["rating"] = "invalid"
        result["reason"] = "speed missing"
        return result

    if not (SPEED_VALID_RANGE[0] <= speed_kmh <= SPEED_VALID_RANGE[1]):
        result["rating"] = "invalid"
        result["reason"] = f"speed {speed_kmh} km/h outside valid range {SPEED_VALID_RANGE}"
        return result

    if speed_kmh > SPEED_WARNING_THRESHOLD:
        result["rating"] = "warning"
        result["reason"] = f"speed {speed_kmh} km/h high (above {SPEED_WARNING_THRESHOLD} km/h)"
    else:
        result["rating"] = "good"
        result["reason"] = "speed within normal range"

    return result


def assess_altitude_quality(altitude_m: float) -> dict[str, Any]:
    """Assess altitude sensor quality.

    Returns:
        - "rating": "good" | "warning" | "invalid"
        - "value": the altitude value
        - "reason": human-readable explanation
    """
    result: dict[str, Any] = {
        "rating": "good",
        "value": altitude_m,
        "reason": None,
    }

    if altitude_m is None:
        result["rating"] = "invalid"
        result["reason"] = "altitude missing"
        return result

    if not (ALTITUDE_VALID_RANGE[0] <= altitude_m <= ALTITUDE_VALID_RANGE[1]):
        result["rating"] = "invalid"
        result["reason"] = f"altitude {altitude_m} m outside valid range {ALTITUDE_VALID_RANGE}"
        return result

    result["rating"] = "good"
    result["reason"] = "altitude within valid range"

    return result


def assess_temperature_quality(temp_c: float) -> dict[str, Any]:
    """Assess ambient temperature sensor quality.

    Returns:
        - "rating": "good" | "warning" | "invalid"
        - "value": the temperature value
        - "reason": human-readable explanation
    """
    result: dict[str, Any] = {
        "rating": "good",
        "value": temp_c,
        "reason": None,
    }

    if temp_c is None:
        result["rating"] = "invalid"
        result["reason"] = "temperature missing"
        return result

    if not (TEMPERATURE_VALID_RANGE[0] <= temp_c <= TEMPERATURE_VALID_RANGE[1]):
        result["rating"] = "invalid"
        result["reason"] = f"temperature {temp_c} C outside valid range {TEMPERATURE_VALID_RANGE}"
        return result

    result["rating"] = "good"
    result["reason"] = "temperature within valid range"

    return result


def assess_complete_telemetry_quality(
    snapshot: dict,
) -> dict[str, Any]:
    """Assess overall telemetry quality from a full snapshot dict.

    Checks all available fields and returns an overall quality rating.
    """
    checks: list[dict[str, Any]] = []

    # SOC
    if "soc_pct" in snapshot:
        checks.append({"field": "soc_pct", **assess_soc_quality(snapshot["soc_pct"])})

    # Speed
    if "speed_kmh" in snapshot:
        checks.append({"field": "speed_kmh", **assess_speed_quality(snapshot["speed_kmh"])})

    # Altitude
    if "altitude_m" in snapshot:
        checks.append({"field": "altitude_m", **assess_altitude_quality(snapshot["altitude_m"])})

    # Temperature
    if "ambient_temperature_c" in snapshot:
        checks.append({"field": "ambient_temperature_c", **assess_temperature_quality(snapshot["ambient_temperature_c"])})

    # Timestamp
    if "timestamp" in snapshot:
        ts_result = assess_timestamp_validity(snapshot["timestamp"])
        checks.append({"field": "timestamp", **ts_result})

    # Determine overall rating
    ratings = [c["rating"] for c in checks]

    if not ratings:
        overall_rating = "unknown"
        overall_message = "No telemetry fields to assess"
    elif any(r == "invalid" for r in ratings):
        overall_rating = "invalid"
        # Find the first invalid field
        invalid_field = next(c["field"] for c in ratings if c == "invalid" or any(r == "invalid" for r in ratings))
        # Actually find first check with invalid rating
        for c in checks:
            if c["rating"] == "invalid":
                invalid_field = c["field"]
                break
        overall_message = f"Telemetry invalid: {invalid_field} is {next(c for c in checks if c['field'] == invalid_field)['reason']}"
    elif any(r == "warning" for r in ratings):
        overall_rating = "warning"
        warning_fields = [c["field"] for c in checks if c["rating"] == "warning"]
        overall_message = f"Telemetry warning: {', '.join(warning_fields)}"
    else:
        overall_rating = "good"
        overall_message = "Telemetry quality: good"

    return {
        "overall_rating": overall_rating,
        "overall_message": overall_message,
        "checks": checks,
        "num_checks": len(checks),
    }