# Vehicle Integration

This document explains what is needed to integrate a new EV into the EV
Intelligence & Dynamic Range Prediction System. It consolidates the (removed)
`docs/vehicle_integration_guide.md`.

The system is hardware-agnostic: it does **not** claim "Works with every EV."
Instead it depends on the vehicle's actual available signals and
CAN/OBD/telematics interface.

## 1. Integration requirements

### Vehicle identification
- **Make / Model / Year** — identifies the vehicle family and typical signal
  mappings.
- **Vehicle UUID / VIN** — optional, for per-vehicle signal calibration.

### CAN bus documentation
- **CAN interface name** — e.g. `can0`, `can1`, `ttyUSB0`.
- **Bitrate** — typical 250k, 500k, 1 Mbit/s.
- **Message ID map** — hex IDs for each signal.
- **Signal decoding parameters** per message ID:
  - **Start bit** — bit position within the message data
  - **Length** — number of bits (1–64)
  - **Byte order** — `little_endian` or `big_endian`
  - **Scale** — multiplicative factor: `value = raw * scale + offset`
  - **Offset** — additive offset
  - **Unit** — e.g. `km/h`, `V`, `A`, `°C`, `kW`
  - **Signed** — two's complement flag

### OBD-II PIDs (if applicable)
- **PID hex code** — e.g. `0x0C`, `0x1F`.
- **Signal name** — must match entries in `configs/telemetry_schema.yaml`.
- **Unit** — the unit of the PID value.
- **Valid range** — (min, max) for the signal value.

> **Important**: Generic OBD-II adapters typically do NOT expose EV-specific
> signals such as SOC, battery current, or battery power. These must come from
> the vehicle's CAN bus or a dedicated BMS interface.

### BMS signals
- **SOC** — State of Charge (0–100 %) from CAN, SMBus, or manufacturer PID.
- **Battery voltage** — nominal and maximum (V).
- **Battery current** — charge/discharge current (A); negative = regeneration.
- **Battery power** — instantaneous power (kW; can be derived from V × I).
- **Battery temperature** — pack temperature (°C).

### Speed and motion
- **Speed** — km/h from wheel-speed sensors / transmission output / CAN / GPS
  (not OBD fuel-rate PIDs).
- **Accelerator / brake pedal position** — %, if available.

### Environmental
- **Ambient temperature** — °C from external sensor.

### Power and energy
- **Motor power** — kW (positive = driving, negative = regen).
- **Auxiliary power** — kW (climate, accessories).
- **Regen power** — kW (regenerative braking into battery).

### GPS / position
- **Latitude / longitude** — decimal degrees.
- **GPS altitude** — meters above mean sea level.
- **Odometer** — km (total distance).

### Vehicle parameters
- **Vehicle mass** — kg (default 1800 kg in the feature builder).
- **Tire radius** — m (affects speed/SOC estimates).
- **Drivetrain efficiency** — default 85 % in consumption estimates.

## 2. Signal schema mapping

Each signal must map to an entry in `configs/telemetry_schema.yaml`. The
system requires signals by **name** (not by source); the adapter layer
fulfills each name from the available hardware.

Example mapping for a hypothetical "AlphaEV 2024":

| Schema Name | Source | CAN ID | Start Bit | Length | Byte Order | Scale | Offset | Unit |
|-------------|--------|--------|-----------|--------|------------|-------|--------|------|
| `soc_pct` | CAN | `0x246` | 0 | 8 | little_endian | 1.0 | 0.0 | % |
| `battery_voltage_v` | CAN | `0x389` | 0 | 13 | little_endian | 0.01 | 0.0 | V |
| `battery_current_a` | CAN | `0x247` | 0 | 12 | little_endian | 0.1 | -100.0 | A |
| `vehicle_speed_kmh` | CAN | `0x123` | 0 | 16 | little_endian | 0.25 | 0.0 | km/h |
| `motor_power_kw` | CAN | `0x246` | 16 | 16 | little_endian | 0.01 | 0.0 | kW |
| `ambient_temperature_c` | CAN | `0x382` | 0 | 8 | little_endian | 1.0 | -40.0 | °C |

## 3. CAN adapter configuration

The CAN adapter is configured via a `default_signal_config` and/or per-signal
configurations passed to `/live/connect`:

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

The `signals` list overrides `default_signal_config` per signal.

## 4. Schema compliance

Every vehicle signal **must** have an entry in `configs/telemetry_schema.yaml`,
which defines: `name`, `unit`, `valid_range`, `required/optional`, and
`model_usage` (`primary_feature` / `secondary_feature` / `metadata`).

If a `required: true` signal is missing, the system returns
`INSUFFICIENT_DATA` / `INSUFFICIENT_TELEMETRY` rather than an unreliable
prediction.

## 5. What the system does NOT claim

- It does NOT claim to work with every EV.
- Without the mapping information above, the system will:
  1. Report unavailable signals as `UNAVAILABLE` / `MISSING`;
  2. Downgrade prediction status to `DEGRADED` / `INSUFFICIENT_DATA`;
  3. **Not** fabricate or guess signal values;
  4. Produce predictions with reduced confidence when possible.

## 6. Demo / development data

For development and testing the system includes a clearly-labeled simulator
(`src/simulator/`) and a synthetic terrain provider (`EV_DEMO_TERRAIN=1`).
All demo data is labeled `SIMULATOR` / `SIMULATOR_ROUTE` and must never be
presented as real vehicle data.

*The system preserves the frozen Step 8 model and does not retrain or modify
it for any vehicle integration.*