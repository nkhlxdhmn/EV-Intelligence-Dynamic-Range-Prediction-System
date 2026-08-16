# Missing-Feature Analysis

Optional Nissan telemetry is structurally unavailable for Dacia and is never zero-imputed. Timestamp-derived and power-integration features are null where timestamps are missing or intervals are invalid.

| Feature | Overall missing | Missing by vehicle | Structural? | Treatment |
|---|---:|---|---|---|
| `current_soc_pct` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `current_soh_pct` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `battery_capacity_kwh` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `current_altitude_m` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `current_gradient_pct` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `past_1km_gradient_pct` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `terrain_class` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `elevation_gain_100m` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `elevation_gain_500m` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `elevation_gain_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `elevation_loss_100m` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `elevation_loss_500m` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `elevation_loss_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `net_elevation_change_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `mean_gradient_500m` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `mean_gradient_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `gradient_std_500m` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `gradient_std_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `max_uphill_gradient` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `max_downhill_gradient` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `terrain_variability` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `hillyness_score` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `uphill_fraction_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `downhill_fraction_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `flat_fraction_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `terrain_transition_count_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `gradient_direction_changes_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `elevation_gain_rate` | 30.537% | {'Dacia Spring': 42.8, 'Nissan Leaf': 14.9} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `elevation_loss_rate` | 30.537% | {'Dacia Spring': 42.8, 'Nissan Leaf': 14.9} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `distance_since_trip_start_km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `time_since_trip_start_min` | 30.979% | {'Dacia Spring': 55.3, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `trip_distance_so_far_km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `trip_elapsed_time_min` | 30.979% | {'Dacia Spring': 55.3, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `current_speed_kmh` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_speed_100m` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_speed_500m` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_speed_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `speed_std_500m` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `speed_std_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `min_speed_recent` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `max_speed_recent` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `high_speed_fraction` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `stopped_fraction` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `stop_count_recent` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `speed_change_recent` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `acceleration_mps2` | 93.69% | {'Dacia Spring': 100.0, 'Nissan Leaf': 85.6} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_acceleration` | 72.347% | {'Dacia Spring': 100.0, 'Nissan Leaf': 37.1} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `std_acceleration` | 72.347% | {'Dacia Spring': 100.0, 'Nissan Leaf': 37.1} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `max_acceleration` | 72.347% | {'Dacia Spring': 100.0, 'Nissan Leaf': 37.1} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `min_acceleration` | 72.347% | {'Dacia Spring': 100.0, 'Nissan Leaf': 37.1} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `hard_acceleration_count` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `hard_braking_count` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `acceleration_variability` | 72.347% | {'Dacia Spring': 100.0, 'Nissan Leaf': 37.1} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `motor_power_kw` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `torque_nm` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `motor_rpm` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_motor_power_500m` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_motor_power_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `max_motor_power_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `motor_power_std_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `positive_motor_power_fraction` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `power_variability` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `aux_power_kw` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_aux_power_500m` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_aux_power_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `max_aux_power_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `aux_power_variability` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `aux_energy_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `regen_power_kw` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_regen_power_500m` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `mean_regen_power_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `max_regen_power_1km` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `regen_event_count_1km` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `regen_duration_estimate` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `regen_energy_recovered_1km` | 62.932% | {'Dacia Spring': 100.0, 'Nissan Leaf': 15.6} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `regen_fraction_of_driving_time` | 30.537% | {'Dacia Spring': 42.8, 'Nissan Leaf': 14.9} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `regen_intensity` | 62.972% | {'Dacia Spring': 100.0, 'Nissan Leaf': 15.7} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `current_temperature_c` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `temperature_deviation_from_reference` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `temperature_recent_mean` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `temperature_recent_std` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `speed_x_gradient` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `speed_squared` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `speed_x_temperature` | 56.059% | {'Dacia Spring': 100.0, 'Nissan Leaf': 0.0} | Yes: Dacia has no verified telemetry signal. | Keep null; use an availability flag where supplied. |
| `has_speed_data` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `has_motor_power` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `has_aux_power` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `has_regen_power` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
| `has_temperature` | 0.0% | {'Dacia Spring': 0.0, 'Nissan Leaf': 0.0} | No for the common feature definition. | Keep null; use an availability flag where supplied. |
