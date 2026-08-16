# Step 10F: TUM Battery Capacity Analysis

## Status: DERIVED (58 kWh net, fleet specification)

The TUM EV UDS dataset README.MD "Fleet Specifications" table documents a net
energy capacity of **58 kWh** for both vehicle families:

| Vehicle Model           | Manufacturer | Year | Number | Pack Config | Net Energy Capacity |
|-------------------------|--------------|------|--------|-------------|---------------------|
| ID.3 Pro Performance    | Volkswagen   | 2020 | 2      | 108s2p (216 cells) | 58 kWh |
| CUPRA Born              | CUPRA        | 2022 | 5      | 108s2p (216 cells) | 58 kWh |

## Why not VERIFIED?

- The 58 kWh figure is a **fleet specification** published in the dataset
  documentation; it is not a per-vehicle BMS readout.
- No `value_id` in the raw UDS parquet files maps to battery capacity
  (verified by a full value_id census of all 7 vehicle files).
- A per-vehicle verified capacity would require either a dedicated capacity
  diagnostic or recorded capacity in the raw signal stream; neither is exposed.

## Why not UNKNOWN?

- The capacity is explicitly and consistently documented for both models in
  the authoritative dataset README, so treating it as unknown would discard
  reliable metadata.

## Usage rules (Step 10)

- The 58 kWh figure is used **only** to interpret SOC deltas when constructing
  an energy target — it is **never** used to fabricate model features.
- Because external validation of the frozen 102-feature model is BLOCKED
  (see `docs/step10_external_validation.md`), no SOC-delta target was
  constructed; the capacity figure is reported for completeness.

## Files

- `reports/step10_battery_capacity.json` — machine-readable record.