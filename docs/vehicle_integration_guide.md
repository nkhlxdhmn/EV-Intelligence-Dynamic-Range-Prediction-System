# Vehicle Integration Guide

## Overview

This document explains what information is needed to integrate a new EV vehicle
into the EV Energy Intelligence & Dynamic Range Prediction System. The system
is hardware-agnostic: it does not claim "Works with every EV." Instead, it
depends on the vehicle's actual available signals and CAN/OBD/telematics
interface.

## Integration Requirements

To integrate a new vehicle, the following information is needed:

### 1. Vehicle Identification
- **Make / Model / Year** — Required to identify the vehicle family and
  its typical signal mappings.
- **Vehicle UUID or VIN** — Optional, for per-vehicle signal calibration.

### 2. CAN Bus Documentation
If the vehicle uses a CAN bus for communication, provide:

- **CAN interface name** — e.g. `can0`, `can1`, `ttyUSB0`
- **Bitrate** — typical values: 250k, 500k, 1Mbit/s (common for automotive)
- **Message ID map** — hex IDs for each signal, e.g.:
  - `0x123` → vehicle_speed (11-bit, little-endian)
  - `0x246` → motor_power (11-bit, big-endian)
  - `0x389` → battery_voltage (13-bit, little-endian)
- **Signal decoding parameters** per message ID:
  - **Start bit** — bit position within the message data
  - **Length** — number of bits (1-64)
  - **Byte order** — `little_endian` or `big_endian`
  - **Scale** — multiplicative factor to apply to raw integer value
  - **Offset** — additive offset: `value = raw * scale + offset`
  - **Unit** — e.g. `km/h`, `V`, `A`, `°C`, `kW`
  - **Signed** — whether the value uses two's complement (boolean)

### 3. OBD-II PIDs (if applicable)

If the vehicle exposes signals via standard OBD-II, provide the PID mappings:

- **PID hex code** — e.g. `0x0C` (Calculated Engine Load), `0x1F` (Fuel Type)
- **Signal name** — must match entries in `configs/telemetry_schema.yaml`
- **Unit** — the unit of the PID value
- **Valid range** — (min, max) for the signal value

> **Important**: Generic OBD-II adapters typically do NOT expose EV-specific
> signals such as SOC, battery current, or battery power. These must be
> provided via the vehicle's CAN bus or a dedicated battery management system
> interface.

### 4. Battery Management System (BMS) Signals

If the vehicle has a dedicated BMS interface (not via OBD-II/CAN), provide:

- **SOC signal** — State of Charge in percent (0-100). Source could be:
  - CAN bus message ID
  - Dedicated SMBus interface
  - Manufacturer-specific OBD PID
- **Battery voltage** — Nominal and maximum voltage (V)
- **Battery current** — Charging/discharging current (A). Negative = regeneration
- **Battery power** — instantaneous power (kW). Can be derived from V * I
- **Temperature** — Battery pack temperature (°C)

### 5. Speed and Motion Signals

- **Speed** — vehicle speed (km/h). Sources:
  - OBD-II PID `0x0D` (Engine Fuel Rate) is not suitable; use vehicle speed
    from wheel speed sensors or transmission output
  - CAN bus signal
  - GPS-derived speed (if GPS available)
- **Accelerator pedal position** — % (0-100), if available
- **Brake pedal position** — % (0-100), if available

### 6. Environmental Signals

- **Ambient temperature** — °C from external sensor
- **Inside cabin temperature** — °C, if available

### 7. Power and Energy Signals

- **Motor power** — kW (positive = driving, negative = regeneration)
- **Auxiliary power** — kW (climate control, accessories, etc.)
- **Regen power** — kW (regenerative braking power into battery)

### 8. GPS and Position

- **GPS latitude** — decimal degrees
- **GPS longitude** — decimal degrees
- **GPS altitude** — meters above mean sea level
- **Odometer** — km (total distance traveled)

### 9. Vehicle-Specific Parameters

These may be needed for accurate feature computation:

- **Vehicle mass** — kg (default: 1800 kg used in feature builder; update if
  significantly different for the vehicle family)
- **Tire radius** — m (affects speed/SOC estimates)
- **Drivetrain efficiency** — (default: 85% used in consumption estimates)

## Signal Schema Mapping

Each signal must map to an entry in `configs/telemetry_schema.yaml`. The
system requires signals by **name** (not by source), and the adapter layer
will attempt to fulfill each name from the available hardware.

Example mapping for a hypothetical "AlphaEV 2024":

| Schema Name | Source | CAN ID | Start Bit | Length | Byte Order | Scale | Offset | Unit |
|-------------|--------|--------|-----------|--------|------------|-------|--------|------|
| `soc_pct` | CAN | `0x246` | 0 | 8 | little_endian | 1.0 | 0.0 | % |
| `battery_voltage_v` | CAN | `0x389` | 0 | 13 | little_endian | 0.01 | 0.0 | V |
| `battery_current_a` | CAN | `0x247` | 0 | 12 | little_endian | 0.1 | -100.0 | A |
| `vehicle_speed_kmh` | CAN | `0x123` | 0 | 16 | little_endian | 0.25 | 0.0 | km/h |
| `motor_power_kw` | CAN | `0x246` | 16 | 16 | little_endian | 0.01 | 0.0 | kW |
| `ambient_temperature_c` | CAN | `0x382` | 0 | 8 | little_endian | 1.0 | -40.0 | °C |

## Adapter Configuration Example

The CAN adapter can be configured with a `default_signal_config` and/or
per-signal configurations. Example JSON configuration:

```json
{
  "interface": "can0",
  "bitrate": 500,
  "default_signal_config": {
    "name": "vehicle_speed_kmh",
    "message_id": 0x123,
    "start_bit": 0,
    "length": 16,
    "byte_order": "little_endian",
    "scale": 0.25,
    "offset": 0.0,
    "unit": "km/h",
    "signed": false
  },
  "signals": [
    {
      "name": "soc_pct",
      "message_id": 0x246,
      "start_bit": 0,
      "length": 8,
      "byte_order": "little_endian",
      "scale": 1.0,
      "offset": 0.0,
      "unit": "%",
      "signed": false
    },
    {
      "name": "battery_voltage_v",
      "message_id": 0x389,
      "start_bit": 0,
      "length": 13,
      "byte_order": "little_endian",
      "scale": 0.01,
      "offset": 0.0,
      "unit": "V",
      "signed": false
    }
  ]
}
```

The `signals` list overrides the `default_signal_config` for each listed signal.

## Telemetry Schema Compliance

Every signal provided by the vehicle **must** have an entry in
`configs/telemetry_schema.yaml`. The schema defines:

- **name** — used by the feature builder and model
- **unit** — unit of measurement
- **valid_range** — (min, max) for range validation
- **required/optional** — whether the signal is needed for prediction
- **model_usage** — `primary_feature` (used in 102-feature model) or
  `secondary_feature` (additional context) or `metadata` (not a model feature)

If a signal is marked as `required: true` in the schema and the vehicle
does not provide it, the system will return
`prediction_status = INSUFFICIENT_DATA` rather than producing an
unreliable prediction.

## What the System Does NOT Claim

The system does NOT claim:

> "Works with every EV."

Instead:

> "The telemetry adapter depends on the vehicle's actual available signals
> and CAN/OBD/telematics interface. Integration requires vehicle-specific
> documentation of signal mappings."

Without the above information, the system will:

1. Report unavailable signals as `UNAVAILABLE` or `MISSING`
2. Downgrade the prediction status to `DEGRADED` or `INSUFFICIENT_DATA`
3. Not fabricate or guess signal values
4. Produce a prediction with reduced confidence (reflected in the
   confidence score)

## Development / Testing Integration

For development and testing purposes, the system includes a
`SyntheticRouteTerrainProvider` and a demo simulator that generates
clearly-labeled synthetic telemetry. This **must** be explicitly labeled:

- **Dashboard**: `SIMULATOR — DEVELOPMENT ONLY`
- **API**: `?telemetry=1` URL parameter enables live mode; default is demo
- **Feature builder**: `build_demo_snapshot()` returns labeled DEMO data
- **All demo/simulator data** is explicitly marked with source = `DEMO` or
  `SYNTHETIC` and must never be presented as real vehicle data

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-08-17 | 1.0.0 | Initial release (STEP 15) |

## Contact / Support

If you are integrating a new vehicle and need assistance with signal mapping
or CAN documentation, please refer to the vehicle's technical documentation
or contact the vehicle manufacturer for CAN bus signal definitions.

---

*This document is part of the EV Intelligence & Dynamic Range Prediction System
(STEP 15 - Live Telemetry Integration). The system preserves the frozen Step 8
model and does not retrain or modify it for any vehicle integration.*