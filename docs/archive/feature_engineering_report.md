# Feature Engineering Report

This report documents the formulas and processing logic applied in `scripts/feature_engineering.py`.

## Target
- **`target_future_energy_kwh_per_km`**
  - **Formula**: `(current_soc_pct - future_5km_soc_pct) * battery_capacity_kwh / 100 / (future_5km_distance - current_distance)`
  - **Past/Current/Future**: Future
  - **Leakage Risk**: NONE (Used exclusively as the target, excluded from inputs).
  - **Missingness**: Missing at the very end of trips (last 5km), and missing when SOC resolution doesn't capture a change.

## Common Features
- **`current_soc_pct`**: Extracted natively at time `t`.
- **`battery_capacity_kwh`**: Extracted natively at time `t`.
- **`current_altitude_m`**: Extracted natively at time `t`.
- **`past_1km_gradient_pct`**: 
  - **Formula**: `(current_altitude_m - past_1km_altitude_m) / (current_distance_m - past_1km_distance_m) * 100`
  - **Leakage Risk**: None (strictly backward-looking).
- **`terrain_class`**:
  - **Formula**: `UPHILL` if gradient > 1.0, `DOWNHILL` if gradient < -1.0, else `FLAT`.

## Nissan Optional Features
- **`current_speed_kmh`**: Extracted natively at time `t`.
- **`past_1km_mean_speed_kmh`**: Rolling mean over distance window.
- **`past_1km_speed_std`**: Rolling standard deviation over distance window.
- **`current_ambient_temperature_c`**: Extracted natively at time `t`.
- **`past_1km_mean_acceleration_mps2`**:
  - **Formula**: `(speed_t - speed_{t-1}) / 3.6 / (time_t - time_{t-1})`. Rolling mean over 1km.
- **`current_motor_power_kw`**: Extracted natively at time `t`.
- **`past_1km_mean_regen_kw`**: Rolling mean over distance window (negative values only).
