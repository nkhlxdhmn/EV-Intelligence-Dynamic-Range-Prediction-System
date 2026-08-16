# Candidate Features

Based on the EDA findings from DEVRT (and TUM cross-check), here are the feature candidates for predicting dynamic energy consumption. Because the Dacia Spring vehicle lacks speed, motor power, and ambient temperature telemetry, the feature set is split into Common (must-have) and Optional (Nissan-only).

## A. MUST HAVE (Common to All Vehicles)
These features are present for both Dacia and Nissan and form the core ML dataset:
- `current_soc_pct`: State of Charge (%)
- `battery_capacity_kwh`: Physical battery capacity
- `current_altitude_m`: Absolute altitude
- `past_1km_gradient_pct`: The terrain gradient calculated over the trailing 1 km.
- `terrain_class`: Categorical derived from `past_1km_gradient_pct` (DOWNHILL < -1.0%, FLAT ±1.0%, UPHILL > 1.0%).
- `vehicle_model`: Categorical identifier (Dacia Spring vs Nissan Leaf).

## B. HIGH VALUE (Optional / Nissan Only)
These features are highly predictive of energy but are completely missing for Dacia:
- `current_speed_kmh`: Instantaneous speed.
- `past_1km_mean_speed_kmh`: Average speed over the trailing 1 km.
- `past_1km_speed_std`: Speed variability (indicator of traffic or driving style).
- `current_ambient_temperature_c`: External temperature (massive impact on battery efficiency).
- `past_1km_mean_acceleration_mps2`: Average acceleration.

## C. OPTIONAL / SUPPLEMENTARY (Nissan Only)
- `current_motor_power_kw`: Instantaneous motor power.
- `past_1km_mean_regen_kw`: Average regenerative braking power.
- `current_aux_power_kw`: Auxiliary load (AC/heating).

## D. NOT RELIABLE
- `motor_rpm` and `motor_torque_nm`: These are highly volatile and largely redundant if speed and motor power are available.
- `soh_pct`: State of Health is static for almost all trips (e.g. Nissan is flat 99.25% or 98.5%), providing no dynamic predictive power.

## E. LEAKAGE RISK
- `reference_consumption_wh_per_km`: Trip-level aggregate.
- Any future window values (future SOC, distance, etc).
