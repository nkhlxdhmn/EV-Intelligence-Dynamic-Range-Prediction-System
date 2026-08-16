#!/usr/bin/env python3
"""Write the unified_schema.py file with all concept keys."""

import os

filepath = "src/data/unified_schema.py"

# Read existing file to preserve structure
with open(filepath, "r") as f:
    existing = f.read()

# We'll rebuild the file from scratch key parts

# DEVRT entries with concept keys
devrt_entries = [
    ('"speed_kmh": {"concept": "speed_kmh", "availability": "direct", "source": "DEVRT", "unit": "km/h", "confidence": "high", "notes": ""},'),
    ('"soc_pct": {"concept": "soc_pct", "availability": "direct", "source": "DEVRT", "unit": "%", "confidence": "high", "notes": ""},'),
    ('"battery_capacity_kwh": {"concept": "battery_capacity_kwh", "availability": "direct", "source": "DEVRT", "unit": "kWh", "confidence": "high", "notes": ""},'),
    ('"battery_voltage_v": {"concept": "battery_voltage_v", "availability": "direct", "source": "DEVRT", "unit": "V", "confidence": "high", "notes": ""},'),
    ('"battery_current_a": {"concept": "battery_current_a", "availability": "direct", "source": "DEVRT", "unit": "A", "confidence": "high", "notes": ""},'),
    ('"ambient_temperature_c": {"concept": "ambient_temperature_c", "availability": "direct", "source": "DEVRT", "unit": "°C", "confidence": "high", "notes": ""},'),
    ('"distance_since_trip_start_km": {"concept": "distance_since_trip_start_km", "availability": "direct", "source": "DEVRT", "unit": "km", "confidence": "high", "notes": ""},'),
    ('"time_since_trip_start_min": {"concept": "time_since_trip_start_min", "availability": "direct", "source": "DEVRT", "unit": "min", "confidence": "high", "notes": ""},'),
    ('"motor_power_kw": {"concept": "motor_power_kw", "availability": "direct", "source": "DEVRT", "unit": "kW", "confidence": "medium", "notes": "optional / may be NaN"},'),
    ('"motor_rpm": {"concept": "motor_rpm", "availability": "direct", "source": "DEVRT", "unit": "RPM", "confidence": "medium", "notes": "optional"},'),
    ('"motor_torque_nm": {"concept": "motor_torque_nm", "availability": "direct", "source": "DEVRT", "unit": "Nm", "confidence": "medium", "notes": "optional"},'),
    ('"aux_power_kw": {"concept": "aux_power_kw", "availability": "direct", "source": "DEVRT", "unit": "kW", "confidence": "medium", "notes": "optional"},'),
    ('"regen_power_kw": {"concept": "regen_power_kw", "availability": "direct", "source": "DEVRT", "unit": "kW", "confidence": "medium", "notes": "optional, ≤ 0"},'),
    ('"next_1km_gradient_pct": {"concept": "next_1km_gradient_pct", "availability": "conditional", "source": "DEVRT", "unit": "%", "confidence": "high", "notes": "requires route DEM"},'),
    ('"next_5km_gradient_pct": {"concept": "next_5km_gradient_pct", "availability": "conditional", "source": "DEVRT", "unit": "%", "confidence": "high", "notes": "requires route DEM"},'),
    ('"next_1km_elevation_m": {"concept": "next_1km_elevation_m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "high", "notes": "requires route DEM"},'),
    ('"next_5km_elevation_m": {"concept": "next_5km_elevation_m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "high", "notes": "requires route DEM"},'),
    ('"elevation_gain_100m": {"concept": "elevation_gain_100m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "medium", "notes": "integrated over 100 m"},'),
    ('"elevation_gain_500m": {"concept": "elevation_gain_500m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "medium", "notes": "integrated over 500 m"},'),
    ('"elevation_gain_1km": {"concept": "elevation_gain_1km", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "medium", "notes": "integrated over 1 km"},'),
    ('"next_5km_uphill_frac": {"concept": "next_5km_uphill_frac", "availability": "conditional", "source": "DEVRT", "unit": "frac", "confidence": "high", "notes": "uphill fraction of next 5 km"},'),
    ('"next_5km_gradient_pct": {"concept": "next_5km_gradient_pct", "availability": "conditional", "source": "DEVRT", "unit": "%", "confidence": "high", "notes": "next 5 km average gradient"},'),
    ('"terrain_class": {"concept": "terrain_class", "availability": "conditional", "source": "DEVRT", "unit": "categorical", "confidence": "medium", "notes": "paved / unpaved / etc."},'),
    ('"elevation_change_m": {"concept": "elevation_change_m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "medium", "notes": "difference between two points"},'),
    ('"route_available": {"concept": "route_available", "availability": "direct", "source": "DEVRT", "unit": "bool", "confidence": "high", "notes": "always true for DEVRT"},'),
    ('"dem_available": {"concept": "dem_available", "availability": "direct", "source": "DEVRT", "unit": "bool", "confidence": "high", "notes": "always true for DEVRT"},'),
    ('"battery_temperature_c": {"concept": "battery_temperature_c", "availability": "unverified", "source": "DEVRT", "unit": "°C", "confidence": "low", "notes": "sensor placement varies"},'),
    ('"battery_current_a": {"concept": "battery_current_a", "availability": "unverified", "source": "DEVRT", "unit": "A", "confidence": "low", "notes": "signals may include noise"},'),
]

jac_entries = [
    ('"speed_kmh": {"concept": "speed_kmh", "availability": "direct", "source": "JAC", "unit": "km/h", "confidence": "high", "notes": ""},'),
    ('"battery_voltage_v": {"concept": "battery_voltage_v", "availability": "unverified", "source": "JAC", "unit": "V", "confidence": "low", "notes": "VOL is raw ADC, not verified battery voltage"},'),
    ('"odometer": {"concept": "odometer", "availability": "direct", "source": "JAC", "unit": "km", "confidence": "high", "notes": ""},'),
    ('"timestamp": {"concept": "timestamp", "availability": "direct", "source": "JAC", "unit": "datetime", "confidence": "high", "notes": ""},'),
    ('"soc_pct": {"concept": "soc_pct", "availability": "unavailable", "source": "JAC", "unit": "%", "confidence": "high", "notes": "SOC unavailable in JAC IEV40 dataset"},'),
    ('"battery_current_a": {"concept": "battery_current_a", "availability": "unavailable", "source": "JAC", "unit": "A", "confidence": "high", "notes": "traction battery current unavailable"},'),
    ('"status_flag": {"concept": "status_flag", "availability": "unverified", "source": "JAC", "unit": "bool", "confidence": "low", "notes": "AIR is a status flag, NOT temperature"},'),
]

tum_entries = [
    ('"speed_kmh": {"concept": "speed_kmh", "availability": "direct", "source": "TUM", "unit": "km/h", "confidence": "high", "notes": ""},'),
    ('"soc_pct": {"concept": "soc_pct", "availability": "direct", "source": "TUM", "unit": "%", "confidence": "high", "notes": ""},'),
    ('"battery_voltage_v": {"concept": "battery_voltage_v", "availability": "direct", "source": "TUM", "unit": "V", "confidence": "high", "notes": ""},'),
    ('"ambient_temperature_c": {"concept": "ambient_temperature_c", "availability": "direct", "source": "TUM", "unit": "°C", "confidence": "high", "notes": ""},'),
    ('"traction_battery_current_a": {"concept": "traction_battery_current_a", "availability": "unavailable", "source": "TUM", "unit": "A", "confidence": "high", "notes": "traction-battery current unavailable in TUM"},'),
    ('"distance_since_trip_start_km": {"concept": "distance_since_trip_start_km", "availability": "unavailable", "source": "TUM", "unit": "km", "confidence": "high", "notes": "per-timestamp distance unavailable in TUM"},'),
    ('"time_since_trip_start_min": {"concept": "time_since_trip_start_min", "availability": "direct", "source": "TUM", "unit": "min", "confidence": "high", "notes": ""},'),
    ('"motor_power_kw": {"concept": "motor_power_kw", "availability": "unavailable", "source": "TUM", "unit": "kW", "confidence": "high", "notes": "traction-motor features unavailable"},'),
    ('"motor_rpm": {"concept": "motor_rpm", "availability": "unavailable", "source": "TUM", "unit": "RPM", "confidence": "high", "notes": "traction-motor features unavailable"},'),
    ('"motor_torque_nm": {"concept": "motor_torque_nm", "availability": "unavailable", "source": "TUM", "unit": "Nm", "confidence": "high", "notes": "traction-motor features unavailable"},'),
    ('"aux_power_kw": {"concept": "aux_power_kw", "availability": "unavailable", "source": "TUM", "unit": "kW", "confidence": "high", "notes": "traction-motor features unavailable"},'),
    ('"regen_power_kw": {"concept": "regen_power_kw", "availability": "unavailable", "source": "TUM", "unit": "kW", "confidence": "high", "notes": "traction-motor features unavailable"},'),
    ('"altitude_m": {"concept": "altitude_m", "availability": "unavailable", "source": "TUM", "unit": "m", "confidence": "high", "notes": "GPS/altitude terrain unavailable"},'),
    ('"past_1km_gradient_pct": {"concept": "past_1km_gradient_pct", "availability": "unavailable", "source": "TUM", "unit": "%", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"past_5km_gradient_pct": {"concept": "past_5km_gradient_pct", "availability": "unavailable", "source": "TUM", "unit": "%", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"next_1km_gradient_pct": {"concept": "next_1km_gradient_pct", "availability": "unavailable", "source": "TUM", "unit": "%", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"next_5km_gradient_pct": {"concept": "next_5km_gradient_pct", "availability": "unavailable", "source": "TUM", "unit": "%", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"next_1km_elevation_m": {"concept": "next_1km_elevation_m", "availability": "unavailable", "source": "TUM", "unit": "m", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"next_5km_elevation_m": {"concept": "next_5km_elevation_m", "availability": "unavailable", "source": "TUM", "unit": "m", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"elevation_gain_100m": {"concept": "elevation_gain_100m", "availability": "unavailable", "source": "TUM", "unit": "m", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"elevation_gain_500m": {"concept": "elevation_gain_500m", "availability": "unavailable", "source": "TUM", "unit": "m", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"elevation_gain_1km": {"concept": "elevation_gain_1km", "availability": "unavailable", "source": "TUM", "unit": "m", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"net_elevation_change_1km": {"concept": "net_elevation_change_1km", "availability": "unavailable", "source": "TUM", "unit": "m", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"mean_gradient_500m": {"concept": "mean_gradient_500m", "availability": "unavailable", "source": "TUM", "unit": "%", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"mean_gradient_1km": {"concept": "mean_gradient_1km", "availability": "unavailable", "source": "TUM", "unit": "%", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"max_uphill_gradient": {"concept": "max_uphill_gradient", "availability": "unavailable", "source": "TUM", "unit": "%", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"max_downhill_gradient": {"concept": "max_downhill_gradient", "availability": "unavailable", "source": "TUM", "unit": "%", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"terrain_variability": {"concept": "terrain_variability", "availability": "unavailable", "source": "TUM", "unit": "count", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"hillyness_score": {"concept": "hillyness_score", "availability": "unavailable", "source": "TUM", "unit": "", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"uphill_fraction_1km": {"concept": "uphill_fraction_1km", "availability": "unavailable", "source": "TUM", "unit": "frac", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"downhill_fraction_1km": {"concept": "downhill_fraction_1km", "availability": "unavailable", "source": "TUM", "unit": "frac", "confidence": "high", "notes": "route-aware, needs GPS/altitude"},'),
    ('"battery_temperature_c": {"concept": "battery_temperature_c", "availability": "unverified", "source": "TUM", "unit": "°C", "confidence": "low", "notes": "raw sensor reading, placement varies"},'),
]

# Build the full file content
# We need the full file with imports, class definitions, and the three dicts

# Header and classes
header = '''"""
STEP 12A - Unified EV Telemetry Schema.

Provides a dataset-independent telemetry vocabulary that classifies every
signal into one of five availability categories.  Designed to represent
DEVRT, TUM EV UDS, and JAC IEV40 without pretending that unavailable
signals exist.

Never convert UNAVAILABLE into zero.  Never fabricate missing values.
Never assume two differently named signals have identical physical meaning
without evidence.
"""

from __future__ import annotations

import enum as _enum
from typing import Literal, TypedDict


class Availability(_enum.Enum):
    """Availability classification for a telemetry concept.

    .. importance::
        * ``direct``   : verified from the source dataset.
        * ``derived``  : mathematically derivable from direct signals.
        * ``conditional``: available when a dataset provides sufficient info.
        * ``unavailable``: cannot be reconstructed reliably.
        * ``unverified`` : raw signal exists but physical meaning is unsettled.
    """
    direct = "direct"
    derived = "derived"
    conditional = "conditional"
    unavailable = "unavailable"
    unverified = "unverified"

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"Availability.{self.name}"


class SchemaEntry(TypedDict):
    """One row of the unified telemetry schema.

    Attributes
    ----------
    concept: str
        Standard concept name (e.g. ``speed_kmh``, ``soc_pct``).
    availability: Availability
        One of ``direct``, ``derived``, ``conditional``, ``unavailable``,
        ``unverified``.
    source: str | None
        Dataset identifier — ``DEVRT``, ``TUM``, ``JAC``, or ``None`` if
        the concept is dataset‑agnostic.
    unit: str | None
        SI‑compatible unit (``"km/h"``, ``"%"``, ``"V"``, etc.) or ``None``
        if the concept is unit‑less.
    confidence: Literal["high", "medium", "low"]
        How certain we are that the classification is correct.
    derivation_method: str | None
        Short string describing how a ``derived`` concept is computed from
        direct signals (e.g. ``"v / dt"``).
    notes: str | None
        Free‑form remarks (e.g. "JAC: AIR is sensor flag not temperature").
    """

    concept: str
    availability: Availability
    source: str | None
    unit: str | None
    confidence: Literal["high", "medium", "low"]
    derivation_method: str | None
    notes: str | None


'''

# DEVRT dict section
devrt_dict = "DEVRT: dict[str, SchemaEntry] = {\n"
for entry in devrt_entries:
    devrt_dict += f"    {entry}\n"
devrt_dict += "}\n\n"

# JAC dict section
jac_dict = "JAC: dict[str, SchemaEntry] = {\n"
for entry in jac_entries:
    jac_dict += f"    {entry}\n"
jac_dict += "}\n\n"

# TUM dict section
tum_dict = "TUM: dict[str, SchemaEntry] = {\n"
for entry in tum_entries:
    tum_dict += f"    {entry}\n"
tum_dict += "}\n\n"

# Helpers and concept sets
helpers ='''
# --------------------------------------------------------------------------
# 3.  Per-concept helpers
# --------------------------------------------------------------------------

def get_all_concepts() -> dict[str, SchemaEntry]:
    """Return a dict of concept_name -> SchemaEntry covering all datasets."""
    return {**DEVRT, **TUM, **JAC}


def get_concept(concept: str) -> SchemaEntry | None:
    """Look up a concept across all datasets; returns the first match."""
    for dataset in (DEVRT, TUM, JAC):
        if concept in dataset:
            return dataset[concept]
    return None


def classify(concept: str) -> Availability:
    """Return the Availability classification for a given concept name."""
    entry = get_concept(concept)
    if entry is None:
        return Availability.unavailable
    return entry["availability"]


def get_unit(concept: str) -> str | None:
    """Return the unit string for a concept, or None if unavailable."""
    entry = get_concept(concept)
    if entry is None:
        return None
    return entry.get("unit")


def get_confidence(concept: str) -> Literal["high", "medium", "low"] | None:
    """Return the confidence string for a concept, or None if unavailable."""
    entry = get_concept(concept)
    if entry is None:
        return None
    return entry.get("confidence")


# --------------------------------------------------------------------------
# 4.  Per-dataset concept sets
# --------------------------------------------------------------------------

DIRECT_CONCEPTS: list[str] = [
    "speed_kmh", "soc_pct", "battery_capacity_kwh", "battery_voltage_v",
    "battery_current_a", "ambient_temperature_c",
    "distance_since_trip_start_km", "time_since_trip_start_min",
]

UNAVAILABLE_CONCEPTS: list[str] = [
    "altitude_m", "past_1km_gradient_pct", "past_5km_gradient_pct",
    "next_1km_gradient_pct", "next_5km_gradient_pct",
    "next_1km_elevation_m", "next_5km_elevation_m",
    "elevation_gain_100m", "elevation_gain_500m", "elevation_gain_1km",
    "net_elevation_change_1km", "mean_gradient_500m", "mean_gradient_1km",
    "max_uphill_gradient", "max_downhill_gradient", "terrain_variability",
    "hillyness_score", "uphill_fraction_1km", "downhill_fraction_1km",
    "distance_since_trip_start_km",  # in TUM (unavailable)
    "traction_battery_current_a",  # in TUM
    "soc_pct",  # in JAC (unavailable)
]

CONDITIONAL_CONCEPTS: list[str] = [
    "next_1km_gradient_pct", "next_5km_gradient_pct",
    "next_1km_elevation_m", "next_5km_elevation_m",
    "elevation_gain_100m", "elevation_gain_500m", "elevation_gain_1km",
    "net_elevation_change_1km", "mean_gradient_500m", "mean_gradient_1km",
    "max_uphill_gradient", "max_downhill_gradient", "terrain_variability",
    "hillyness_score", "uphill_fraction_1km", "downhill_fraction_1km",
]

UNVERIFIED_CONCEPTS: list[str] = [
    "battery_temperature_c",  # DEVRT
    "status_flag",  # JAC (AIR)
]


'''

# Combine everything
full_content = header + devrt_dict + jac_dict + tum_dict + helpers

# Write the file
with open(filepath, "w") as f:
    f.write(full_content)

print(f"File written to {filepath} ({len(full_content)} chars)")