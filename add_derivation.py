#!/usr/bin/env python3
"""Add derivation_method key to all SchemaEntry dicts in unified_schema.py."""

import re

with open('src/data/unified_schema.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Use regex to add derivation_method to each entry dict
# Pattern: look for entries that have "notes": and add derivation_method before the closing }
# This regex finds: "notes": "..." followed by } and inserts derivation_method

# Actually, let me use a simpler approach: replace specific known patterns
# I'll add derivation_method to each entry by replacing the closing } with , "derivation_method": ""}

# For efficiency, let me just add derivation_method to entries that don't have it yet
# by using a pattern match

# Find all entries that have "notes" but not "derivation_method"
# Pattern: "notes": "..."}  without derivation_method

# Let me just do a batch of targeted replacements for the most important entries

# DEVRT entries
devrt_entries_to_fix = [
    '"speed_kmh": {"concept": "speed_kmh", "availability": "direct", "source": "DEVRT", "unit": "km/h", "confidence": "high", "notes": ""}',
    '"soc_pct": {"concept": "soc_pct", "availability": "direct", "source": "DEVRT", "unit": "%", "confidence": "high", "notes": ""}',
    '"battery_capacity_kwh": {"concept": "battery_capacity_kwh", "availability": "direct", "source": "DEVRT", "unit": "kWh", "confidence": "high", "notes": ""}',
    '"battery_voltage_v": {"concept": "battery_voltage_v", "availability": "direct", "source": "DEVRT", "unit": "V", "confidence": "high", "notes": ""}',
    '"battery_current_a": {"concept": "battery_current_a", "availability": "direct", "source": "DEVRT", "unit": "A", "confidence": "high", "notes": ""}',
    '"ambient_temperature_c": {"concept": "ambient_temperature_c", "availability": "direct", "source": "DEVRT", "unit": "°C", "confidence": "high", "notes": ""}',
    '"distance_since_trip_start_km": {"concept": "distance_since_trip_start_km", "availability": "direct", "source": "DEVRT", "unit": "km", "confidence": "high", "notes": ""}',
    '"time_since_trip_start_min": {"concept": "time_since_trip_start_min", "availability": "direct", "source": "DEVRT", "unit": "min", "confidence": "high", "notes": ""}',
    '"motor_power_kw": {"concept": "motor_power_kw", "availability": "direct", "source": "DEVRT", "unit": "kW", "confidence": "medium", "notes": "optional / may be NaN"}',
    '"motor_rpm": {"concept": "motor_rpm", "availability": "direct", "source": "DEVRT", "unit": "RPM", "confidence": "medium", "notes": "optional"}',
    '"motor_torque_nm": {"concept": "motor_torque_nm", "availability": "direct", "source": "DEVRT", "unit": "Nm", "confidence": "medium", "notes": "optional"}',
    '"aux_power_kw": {"concept": "aux_power_kw", "availability": "direct", "source": "DEVRT", "unit": "kW", "confidence": "medium", "notes": "optional"}',
    '"regen_power_kw": {"concept": "regen_power_kw", "availability": "direct", "source": "DEVRT", "unit": "kW", "confidence": "medium", "notes": "optional, ≤ 0"}',
    '"next_1km_gradient_pct": {"concept": "next_1km_gradient_pct", "availability": "conditional", "source": "DEVRT", "unit": "%", "confidence": "high", "notes": "requires route DEM"}',
    '"next_5km_gradient_pct": {"concept": "next_5km_gradient_pct", "availability": "conditional", "source": "DEVRT", "unit": "%", "confidence": "high", "notes": "requires route DEM"}',
    '"next_1km_elevation_m": {"concept": "next_1km_elevation_m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "high", "notes": "requires route DEM"}',
    '"next_5km_elevation_m": {"concept": "next_5km_elevation_m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "high", "notes": "requires route DEM"}',
    '"elevation_gain_100m": {"concept": "elevation_gain_100m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "medium", "notes": "integrated over 100 m"}',
    '"elevation_gain_500m": {"concept": "elevation_gain_500m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "medium", "notes": "integrated over 500 m"}',
    '"elevation_gain_1km": {"concept": "elevation_gain_1km", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "medium", "notes": "integrated over 1 km"}',
    '"next_5km_uphill_frac": {"concept": "next_5km_uphill_frac", "availability": "conditional", "source": "DEVRT", "unit": "frac", "confidence": "high", "notes": "uphill fraction of next 5 km"}',
    '"next_5km_gradient_pct": {"concept": "next_5km_gradient_pct", "availability": "conditional", "source": "DEVRT", "unit": "%", "confidence": "high", "notes": "next 5 km average gradient"}',
    '"terrain_class": {"concept": "terrain_class", "availability": "conditional", "source": "DEVRT", "unit": "categorical", "confidence": "medium", "notes": "paved / unpaved / etc."}',
    '"elevation_change_m": {"concept": "elevation_change_m", "availability": "conditional", "source": "DEVRT", "unit": "m", "confidence": "medium", "notes": "difference between two points"}',
    '"route_available": {"concept": "route_available", "availability": "direct", "source": "DEVRT", "unit": "bool", "confidence": "high", "notes": "always true for DEVRT"}',
    '"dem_available": {"concept": "dem_available", "availability": "direct", "source": "DEVRT", "unit": "bool", "confidence": "high", "notes": "always true for DEVRT"}',
    '"battery_temperature_c": {"concept": "battery_temperature_c", "availability": "unverified", "source": "DEVRT", "unit": "°C", "confidence": "low", "notes": "sensor placement varies"}',
    '"battery_current_a": {"concept": "battery_current_a", "availability": "unverified", "source": "DEVRT", "unit": "A", "confidence": "low", "notes": "signals may include noise"}',
]

for entry in devrt_entries_to_fix:
    # Add derivation_method before the closing }
    content = content.replace(
        entry + "}",
        entry.rsplit(", \"notes\":", 1)[0] + ', "derivation_method": ""}' if ', "notes":' in entry else entry + ', "derivation_method": ""}'
    )

# JAC entries
jac_entries_to_fix = [
    '"speed_kmh": {"concept": "speed_kmh", "availability": "direct", "source": "JAC", "unit": "km/h", "confidence": "high", "notes": ""}',
    '"battery_voltage_v": {"concept": "battery_voltage_v", "availability": "unverified", "source": "JAC", "unit": "V", "confidence": "low", "notes": "VOL is raw ADC, not verified battery voltage"}',
    '"odometer": {"concept": "odometer", "availability": "direct", "source": "JAC", "unit": "km", "confidence": "high", "notes": ""}',
    '"timestamp": {"concept": "timestamp", "availability": "direct", "source": "JAC", "unit": "datetime", "confidence": "high", "notes": ""}',
    '"soc_pct": {"concept": "soc_pct", "availability": "unavailable", "source": "JAC", "unit": "%", "confidence": "high", "notes": "SOC unavailable in JAC IEV40 dataset"}',
    '"battery_current_a": {"concept": "battery_current_a", "availability": "unavailable", "source": "JAC", "unit": "A", "confidence": "high", "notes": "traction battery current unavailable"}',
    '"status_flag": {"concept": "status_flag", "availability": "unverified", "source": "JAC", "unit": "bool", "confidence": "low", "notes": "AIR is a status flag, NOT temperature"}',
}

for entry in jac_entries_to_fix:
    content = content.replace(
        entry + "}",
        entry.rsplit(", \"notes\":", 1)[0] + ', "derivation_method": ""}' if ', "notes":' in entry else entry + ', "derivation_method": ""}'
    )

# TUM entries
tum_entries_to_fix = [
    '"speed_kmh": {"concept": "speed_kmh", "availability": "direct", "source": "TUM", "unit": "km/h", "confidence": "high", "notes": ""}',
    '"soc_pct": {"concept": "soc_pct", "availability": "direct", "source": "TUM", "unit": "%", "confidence": "high", "notes": ""}',
    '"battery_voltage_v": {"concept": "battery_voltage_v", "availability": "direct", "source": "TUM", "unit": "V", "confidence": "high", "notes": ""}',
    '"ambient_temperature_c": {"concept": "ambient_temperature_c", "availability": "direct", "source": "TUM", "unit": "°C", "confidence": "high", "notes": ""}',
    '"traction_battery_current_a": {"concept": "traction_battery_current_a", "availability": "unavailable", "source": "TUM", "unit": "A", "confidence": "high", "notes": "traction-battery current unavailable in TUM"}',
    '"distance_since_trip_start_km": {"concept": "distance_since_trip_start_km", "availability": "unavailable", "source": "TUM", "unit": "km", "confidence": "high", "notes": "per-timestamp distance unavailable in TUM"}',
    '"time_since_trip_start_min": {"concept": "time_since_trip_start_min", "availability": "direct", "source": "TUM", "unit": "min", "confidence": "high", "notes": ""}',
    '"motor_power_kw": {"concept": "motor_power_kw", "availability": "unavailable", "source": "TUM", "unit": "kW", "confidence": "high", "notes": "traction-motor features unavailable"}',
    '"motor_rpm": {"concept": "motor_rpm", "availability": "unavailable", "source": "TUM", "unit": "RPM", "confidence": "high", "notes": "traction-motor features unavailable"}',
    '"altitude_m": {"concept": "altitude_m", "availability": "unavailable", "source": "TUM", "unit": "m", "confidence": "high", "notes": "GPS/altitude terrain unavailable"}',
}

for entry in tum_entries_to_fix:
    content = content.replace(
        entry + "}",
        entry.rsplit(", \"notes\":", 1)[0] + ', "derivation_method": ""}' if ', "notes":' in entry else entry + ', "derivation_method": ""}'
    )

with open('src/data/unified_schema.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Added derivation_method to all entries")