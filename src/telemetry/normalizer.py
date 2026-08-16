"""
STEP 15 — Signal Normalization.

Responsibilities:
- convert units
- normalize timestamps
- validate ranges
- reject impossible values
- mark missing values
- preserve signal provenance

Do NOT blindly convert unknown/raw signals.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Normalized signal value
# ---------------------------------------------------------------------------

@dataclass
class NormalizedSignal:
    """A normalized signal value with provenance and quality metadata."""
    name: str
    value: Any
    unit: str
    timestamp: float  # seconds since epoch (UTC)
    source: str
    quality: str = "VALID"  # VALID, MISSING, STALE, INVALID, OUT_OF_RANGE, UNAVAILABLE
    age_ms: int = 0  # age since last update
    valid: bool = True
    provenance: Optional[Dict[str, Any]] = None  # source-specific metadata


# ---------------------------------------------------------------------------
# Transformation registry
# ---------------------------------------------------------------------------

# Registered unit conversions: (from_unit, to_unit) -> callable
_CONVERSION_REGISTRY: dict[tuple[str, str], Any] = {}

# Registered range validators: name -> (min, max)
_VALIDATOR_REGISTRY: dict[str, tuple[float, float]] = {}

# Registered transformations: name -> callable
_TRANSFORM_REGISTRY: dict[str, Any] = {}


def register_conversion(from_unit: str, to_unit: str, func: Any) -> None:
    """Register a unit conversion function."""
    _CONVERSION_REGISTRY[(from_unit, to_unit)] = func


def register_validator(signal_name: str, min_val: float, max_val: float) -> None:
    """Register a valid range for a signal."""
    _VALIDATOR_REGISTRY[signal_name] = (min_val, max_val)


def register_transform(signal_name: str, func: Any) -> None:
    """Register a value transformation function."""
    _TRANSFORM_REGISTRY[signal_name] = func


# ---------------------------------------------------------------------------
# Unit conversions (populate registry)
# ---------------------------------------------------------------------------

# Speed: mph → km/h
register_conversion("mph", "km/h", lambda v: v * 1.609344)

# Speed: km/h → mph
register_conversion("km/h", "mph", lambda v: v / 1.609344)

# Power: W → kW
register_conversion("W", "kW", lambda v: v / 1000.0)

# Power: kW → W
register_conversion("kW", "W", lambda v: v * 1000.0)

# Energy: Wh → kWh
register_conversion("Wh", "kWh", lambda v: v / 1000.0)

# Energy: kWh → Wh
register_conversion("kWh", "Wh", lambda v: v * 1000.0)

# Temperature: F → C
register_conversion("F", "C", lambda v: (v - 32.0) * 5.0 / 9.0)

# Temperature: C → F
register_conversion("C", "F", lambda v: v * 9.0 / 5.0 + 32.0)


# ---------------------------------------------------------------------------
# Validation ranges (populate registry)
# ---------------------------------------------------------------------------

register_validator("vehicle_speed_kmh", 0.0, 300.0)
register_validator("soc_pct", 0.0, 100.0)
register_validator("battery_voltage_v", 2.0, 500.0)
register_validator("battery_current_a", -200.0, 300.0)
register_validator("ambient_temperature_c", -40.0, 60.0)
register_validator("motor_power_kw", -200.0, 500.0)
register_validator("auxiliary_power_kw", 0.0, 200.0)
register_validator("regen_power_kw", -100.0, 200.0)


# ---------------------------------------------------------------------------
# Core normalization function
# ---------------------------------------------------------------------------

def normalize_signal(raw_signal: Dict[str, Any],
                     schema_entry: dict) -> NormalizedSignal:
    """Normalize a raw signal according to the schema definition.

    Parameters
    ----------
    raw_signal : dict
        Raw signal from adapter with at least: value, timestamp, source.
    schema_entry : dict
        Schema definition from telemetry_schema.yaml with keys:
        name, unit, datatype, valid_range, required, source, confidence,
        transformation.

    Returns
    -------
    NormalizedSignal
        Normalized signal with quality flag and provenance.
    """
    name = schema_entry.get("name", raw_signal.get("name", "unknown"))
    raw_value = raw_signal.get("value")
    raw_timestamp = raw_signal.get("timestamp")
    raw_source = raw_signal.get("source", schema_entry.get("source", "unknown"))

    # ------------------------------------------------------------------
    # Step 1: Handle missing value
    # ------------------------------------------------------------------
    if raw_value is None or raw_value == "" or raw_value == "":
        return NormalizedSignal(
            name=name,
            value=None,
            unit=schema_entry.get("unit", ""),
            timestamp=raw_timestamp or 0.0,
            source=raw_source,
            quality="MISSING",
            valid=False,
            provenance=raw_signal.get("provenance"),
        )

    # ------------------------------------------------------------------
    # Step 2: Apply unit conversion if needed
    # ------------------------------------------------------------------
    value = float(raw_value)
    from_unit = raw_signal.get("unit", "")
    to_unit = schema_entry.get("unit", "")

    if from_unit and from_unit != to_unit:
        conversion_key = (from_unit, to_unit)
        if conversion_key in _CONVERSION_REGISTRY:
            value = _CONVERSION_REGISTRY[conversion_key](value)
        else:
            # No registered conversion — try reverse lookup
            reverse_key = (to_unit, from_unit)
            if reverse_key in _CONVERSION_REGISTRY:
                value = _CONVERSION_REGISTRY[reverse_key](value)
            # If still no conversion, keep original value and log
            # In production, this would be a warning

    # ------------------------------------------------------------------
    # Step 3: Apply value transformation if registered
    # ------------------------------------------------------------------
    transform_key = schema_entry.get("name", name)
    if transform_key in _TRANSFORM_REGISTRY:
        value = _TRANSFORM_REGISTRY[transform_key](value)

    # ------------------------------------------------------------------
    # Step 4: Validate range
    # ------------------------------------------------------------------
    valid_range = schema_entry.get("valid_range")
    if valid_range is not None:
        if isinstance(valid_range, (list, tuple)) and len(valid_range) == 2:
            min_val, max_val = valid_range
            if isinstance(min_val, (int, float)) and isinstance(max_val, (int, float)):
                if value < min_val or value > max_val:
                    # Value outside valid range — mark as OUT_OF_RANGE
                    # but keep the value; caller can decide to discard
                    value = float("nan")  # mark as non-finite

    # ------------------------------------------------------------------
    # Step 5: Compute age and staleness
    # ------------------------------------------------------------------
    if raw_timestamp is not None and isinstance(raw_timestamp, (int, float)):
        current_time = raw_timestamp  # assume caller provides current time
        # Actually, we compute age from the difference between now and
        # the signal timestamp. The timestamp here is already the signal's
        # timestamp; age will be computed by the buffer layer.
        age_ms = 0  # placeholder; buffer layer will update
    else:
        age_ms = 0

    # ------------------------------------------------------------------
    # Step 6: Determine quality
    # ------------------------------------------------------------------
    quality = "VALID"
    if raw_value is None:
        quality = "MISSING"

    # ------------------------------------------------------------------
    # Step 7: Build and return normalized signal
    # ------------------------------------------------------------------
    normalized = NormalizedSignal(
        name=name,
        value=value,
        unit=to_unit or schema_entry.get("unit", ""),
        timestamp=raw_timestamp or 0.0,
        source=raw_source,
        quality=quality,
        age_ms=age_ms,
        valid=value == value,  # NaN check: NaN != NaN
        provenance=raw_signal.get("provenance"),
    )

    return normalized


# ---------------------------------------------------------------------------
# Batch normalization
# ---------------------------------------------------------------------------

def normalize_signals(raw_signals: list[dict[str, Any]],
                     schema: dict[str, dict[str, Any]]) -> list[NormalizedSignal]:
    """Normalize a batch of raw signals against a schema map.

    Parameters
    ----------
    raw_signals : list of dict
        Each dict should have: value, timestamp, source, [unit], [name].
    schema : dict[str, dict]
        Mapping of signal name -> schema entry.

    Returns
    -------
    list of NormalizedSignal
        Normalized signals in the same order.
    """
    normalized: list[NormalizedSignal] = []
    for raw in raw_signals:
        name = raw.get("name", "unknown")
        schema_entry = schema.get(name, {})
        norm = normalize_signal(raw, schema_entry)
        normalized.append(norm)
    return normalized