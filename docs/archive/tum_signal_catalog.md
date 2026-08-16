# TUM Dataset Signal Catalog

This catalog documents the available signals in the TUM dataset, based on `data/value_overview.csv`.

## 1. Required Signals Analysis

| Value ID | Signal Name | Unit | Sampling (ms) | Range | Notes |
|----------|-------------|------|---------------|-------|-------|
| `900` | `hv_soc` | % | 5000 | 0.0 - 100.0 | High Voltage State of Charge. Required. |
| `4` | `vehicle_speed` | km/h | 200 | 0.0 - 254.0 | Vehicle Speed. Required. |
| `1200` | `hv_battery_voltage` | V | 200 | 0.0 - 1000.0 | Pack Voltage. Required. |
| `1205` | `ptc1_current` | A | 1000 | 0.0 - 100.0 | **NOT battery current.** This is current for PTC Heater 1. Do not use as total current. |
| `15` | `ambient_air_temp` | °C | 10000 | -40.0 - 215.0 | Ambient air temperature. Required. |
| `56` | `hv_aux_power` | W | 1000 | -20000 - 20000 | Power HV Aux. **NOT total traction power.** Useful for auxiliary consumption tracking. |
| `1290` | `hv_dod` | % | N/A | 0.0 - 100.0 | Depth-Of-Discharge. Complementary to SOC. |
| `1299` | `traveled_distance` | km | N/A | 0.0 - 1000.0 | Distance traveled. Likely trip-level (no sampling interval given in metadata). |
| `1288` | `cell_c_rate` | 1/h | N/A | -100.0 - 100.0 | Cell C-Rate. Can be multiplied by pack capacity to estimate current. |

## 2. Battery Energy Signals Search

Searching the catalog for energy/power concepts:

| Concept | Value ID | Variable Name | Unit | Verified? | Usable for Target? | Reason |
|---------|----------|---------------|------|-----------|--------------------|--------|
| **Battery Voltage** | `1200` | `hv_battery_voltage` | V | Yes | Yes | Direct pack voltage measurement |
| **Battery Current** | **NONE** | **N/A** | **N/A** | **NO** | **NO** | **HV battery current not verified in the inspected signal catalog.** `ptc1_current` is heater current only. |
| **Battery Power** | **NONE** | **N/A** | **N/A** | **NO** | **NO** | No direct traction power signal. `hv_aux_power` is auxiliary. |
| **SOC** | `900` | `hv_soc` | % | Yes | Yes | Direct SOC measurement |
| **C-Rate** | `1288` | `cell_c_rate` | 1/h | Yes | Yes | Proxy for battery current (Current = C-Rate × 58Ah or similar depending on capacity definition). |

## 3. Important Semantic Rules
- `value_id 1205` is **`ptc1_current`**. It must **NOT** be renamed to `battery_current_a`. It is not HV battery current.
- **HV battery current not verified in the inspected signal catalog.**
- `value_id 56` is **`hv_aux_power`**. It is auxiliary power only, not total vehicle/traction battery power.

## 4. GPS & Terrain Availability
- **Latitude / Longitude**: Not present in `value_overview.csv`.
- **Altitude**: Not present in `value_overview.csv`.
- UDS data natively lacks GPS data unless explicitly logged from a navigation module, which is not included here.
