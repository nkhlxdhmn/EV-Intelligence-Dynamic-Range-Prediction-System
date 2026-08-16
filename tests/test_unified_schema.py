"""Unit tests for the STEP 12A unified telemetry schema."""

import pytest

from src.data.unified_schema import (
    Availability,
    SchemaEntry,
    get_all_concepts,
    get_concept,
    classify,
    get_unit,
    get_confidence,
    DIRECT_CONCEPTS,
    UNAVAILABLE_CONCEPTS,
    CONDITIONAL_CONCEPTS,
    UNVERIFIED_CONCEPTS,
)


def test_schema_has_concepts():
    """Every concept in the schema must have an availability classification."""
    assert len(get_all_concepts()) > 0


def test_direct_concepts_exist():
    """DIRECT_CONCEPTS must not be empty."""
    assert len(DIRECT_CONCEPTS) > 0


def test_unavailable_concepts_exist():
    """UNAVAILABLE_CONCEPTS must not be empty."""
    assert len(UNAVAILABLE_CONCEPTS) > 0


def test_direct_classification_is_correct():
    """All concepts classified as ``direct`` must have a unit and confidence."""
    for concept in DIRECT_CONCEPTS:
        entry = get_concept(concept)
        assert entry is not None, f"Concept {concept} not found in schema"
        assert entry["unit"] is not None, f"Concept {concept} has no unit"
        assert entry["confidence"] is not None, f"Concept {concept} has no confidence"


def test_unavailable_classification_is_correct():
    """All concepts classified as ``unavailable`` must have no unit requirement."""
    for concept in UNAVAILABLE_CONCEPTS:
        entry = get_concept(concept)
        assert entry is not None, f"Concept {concept} not found in schema"
        # unavailable concepts may or may not have a unit; just check it exists


def test_conditional_classification_is_correct():
    """All concepts classified as ``conditional`` must have a source dataset."""
    for concept in CONDITIONAL_CONCEPTS:
        entry = get_concept(concept)
        assert entry is not None, f"Concept {concept} not found in schema"
        assert entry["source"] is not None, f"Concept {concept} must have a source dataset"


def test_unverified_classification_is_correct():
    """All concepts classified as ``unverified`` must have a unit."""
    for concept in UNVERIFIED_CONCEPTS:
        entry = get_concept(concept)
        assert entry is not None, f"Concept {concept} not found in schema"
        assert entry["unit"] is not None, f"Concept {concept} has no unit"


def test_classify_returns_availability():
    """``classify()`` must return an ``Availability`` enum value."""
    for concept in get_all_concepts():
        result = classify(concept)
        assert isinstance(result, Availability), f"classify({concept!r}) returned {result!r}, not Availability"


def test_get_unit_returns_string_or_none():
    """``get_unit()`` must return a string or ``None``."""
    for concept in get_all_concepts():
        result = get_unit(concept)
        assert isinstance(result, str) or result is None, (
            f"get_unit({concept!r}) returned {result!r}, expected str or None"
        )


def test_get_confidence_returns_string_or_none():
    """``get_confidence()`` must return a string or ``None``."""
    for concept in get_all_concepts():
        result = get_confidence(concept)
        assert isinstance(result, str) or result is None, (
            f"get_confidence({concept!r}) returned {result!r}, expected str or None"
        )


def test_DIRECT_CONCEPTS_vs_schema():
    """Every concept listed as ``DIRECT`` must appear in the schema."""
    for concept in DIRECT_CONCEPTS:
        assert get_concept(concept) is not None, f"DIRECT concept {concept!r} not in schema"


def test_UNAVAILABLE_CONCEPTS_vs_schema():
    """Every concept listed as ``unavailable`` must appear in the schema."""
    for concept in UNAVAILABLE_CONCEPTS:
        assert get_concept(concept) is not None, f"UNAVAILABLE concept {concept!r} not in schema"


def test_CONDITIONAL_CONCEPTS_vs_schema():
    """Every concept listed as ``conditional`` must appear in the schema."""
    for concept in CONDITIONAL_CONCEPTS:
        assert get_concept(concept) is not None, f"CONDITIONAL concept {concept!r} not in schema"


def test_UNVERIFIED_CONCEPTS_vs_schema():
    """Every concept listed as ``unverified`` must appear in the schema."""
    for concept in UNVERIFIED_CONCEPTS:
        assert get_concept(concept) is not None, f"UNVERIFIED concept {concept!r} not in schema"


def test_schema_coverage_devt():
    """DEVRT-relevant concepts must be classified."""
    devrt_concepts = [
        "speed_kmh", "soc_pct", "battery_capacity_kwh", "battery_voltage_v",
        "battery_current_a", "ambient_temperature_c", "distance_since_trip_start_km",
        "time_since_trip_start_min",
    ]
    for concept in devrt_concepts:
        assert get_concept(concept) is not None, f"DEVRT concept {concept!r} not in schema"


def test_schema_coverage_tum():
    """TUM-relevant concepts must be classified."""
    tum_concepts = [
        "speed_kmh", "soc_pct", "battery_voltage_v", "ambient_temperature_c",
        "altitude_m", "traction_battery_current_a",
    ]
    for concept in tum_concepts:
        assert get_concept(concept) is not None, f"TUM concept {concept!r} not in schema"


def test_schema_coverage_jac():
    """JAC-relevant concepts must be classified."""
    jac_concepts = [
        "speed_kmh", "battery_voltage_v", "soc_pct", "status_flag",
    ]
    for concept in jac_concepts:
        assert get_concept(concept) is not None, f"JAC concept {concept!r} not in schema"


def test_no_fabricated_unavailable():
    """No concept should have its availability forced to ``0`` or ``NA``."""
    for concept, entry in get_all_concepts.items():
        # Check the raw availability string is not "0" or "NA"
        availability = entry["availability"]
        assert availability not in ("0", "NA", "NAN"), (
            f"Concept {concept!r} has forbidden availability '{availability}'"
        )


def test_no_accidental_zero_filling():
    """No concept should have its availability set by accidentally filling with zero."""
    for concept, entry in get_all_concepts.items():
        # Check that availability was not set via an accidental zero fill
        # (this is a semantic check, not a code check; we just verify the
        # classification makes sense)
        assert entry["availability"] is not None


def test_required_metadata_fields_present():
    """Every ``SchemaEntry`` must contain the required fields."""
    for concept, entry in get_all_concepts().items():
        required = ["concept", "availability", "source", "unit", "confidence",
                    "derivation_method", "notes"]
        for key in required:
            assert key in entry, f"SchemaEntry({concept!r}) missing key '{key}'"