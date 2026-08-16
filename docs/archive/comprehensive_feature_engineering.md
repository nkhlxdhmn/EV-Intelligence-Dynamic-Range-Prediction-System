# Comprehensive EV Feature Engineering

The v2 DEVRT matrix has 9,952 samples and 96 predictor/metadata columns plus the future target. It is produced one standardized trip at a time with PyArrow output and explicit garbage collection.

## Causality

All distance windows are trailing windows ending at the current observation. No centered rolling windows, end-of-trip fields, remaining-distance fields, or future signals are present. The 5 km target preserves the established Step 6 construction order.

## Definitions

- Terrain is FLAT for absolute 100 m gradient at or below 1%; otherwise UPHILL or DOWNHILL.
- Hillyness is 1 km gradient standard deviation multiplied by one plus the number of non-flat gradient direction changes.
- Hard acceleration/braking thresholds are +2.0 / -2.0 m/s2.
- Regeneration recovery integrates negative regenerative power over valid 0-120 second intervals.
- Temperature deviation is relative to 20 C.

## Feature groups

- COMMON: 33 terrain, battery, and trip-context features.
- OPTIONAL_NISSAN: 51 verified telemetry-derived features, structurally null for Dacia.
- Availability flags: has_speed_data, has_motor_power, has_aux_power, has_regen_power, has_temperature.

## Future ablations

- `EXPERIMENT_A_BASIC`: 5 candidate features
- `EXPERIMENT_B_DRIVING`: 55 candidate features
- `EXPERIMENT_C_POWERTRAIN`: 78 candidate features
- `EXPERIMENT_D_ENVIRONMENT`: 84 candidate features
- `EXPERIMENT_E_FULL`: 89 candidate features

Wind is retained as unavailable: direction alone cannot produce headwind components without verified vehicle heading. JAC is compatibility-only and TUM remains external validation; neither is merged into DEVRT.
