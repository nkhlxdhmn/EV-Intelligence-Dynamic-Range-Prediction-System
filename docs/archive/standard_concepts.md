# Standard Concepts Vocabulary

## Definition
This section defines the conceptual standard vocabulary for the EV Intelligence project. 
**IMPORTANT**: This does NOT rename raw columns. It defines common concepts that can be obtained from one or more datasets.

### Core Vehicle Concepts

| Concept | Description | Available in Datasets | Confidence |
|---------|-------------|----------------------|------------|
| `timestamp` | UTC timestamp representing the data point | DEVRT (timestamp_data_utc), JAC (reconstruct from Y/M/D/H/MIN/SEC), TUM (value timestamps) | High |
| `vehicle_id` | Unique identifier for the vehicle | DEVRT (car_id), JAC (implicit single vehicle), TUM (vehicle_id in JSON/parquet) | High |
| `trip_id` | Identifier for a driving trip/journey | DEVRT (route_id, start/end timestamps), JAC (implicit per row), TUM (trip-level in JSON) | High |
| `driver_id` | Identifier for the driver | DEVRT (driver column), JAC (not available), TUM (not available) | Medium (DEVRT only) |

### Battery Concepts

| Concept | Description | Available in Datasets | Derivation |
|---------|-------------|----------------------|------------|
| `soc_pct` | State of Charge, percentage of remaining battery capacity | DEVRT (soc column, %), TUM (hv_soc, value_id=900, %) | JAC: NOT available |
| `soh_pct` | State of Health, percentage of remaining battery health | DEVRT (soh column, %), TUM: NOT in 29 value_ids | JAC: NOT available. TUM: derive from aging data |
| `battery_voltage_v` | Battery pack voltage in Volts | DEVRT (implied via Motor Pwr/w observations), TUM (hv_battery_voltage, value_id=1200, V), JAC (VOL, V but unverified) | Medium for JAC |
| `battery_current_a` | Battery current in Amperes | DEVRT (implied via Motor Pwr/w / voltage), TUM (ptc1_current, value_id=1205, A), JAC (CUR, A but unverified) | Medium for JAC |
| `battery_temperature_c` | Battery temperature in Celsius | DEVRT (Motor Temp, amb_temp), TUM (multiple temp value_ids: hv_temp_min/max, interior_temp, etc.), JAC (ALT may include temp) | High |
| `battery_capacity_kwh` | Battery energy capacity in kWh | DEVRT (capacity: 33000 Wh = 33 kWh Dacia, 62000 Wh = 62 kWh Nissan), TUM (58 kWh fleet spec), JAC (not explicit) | High |
| `available_energy_kwh` | Available energy remaining in kWh | Derived: soc_pct × battery_capacity_kwh | Derived concept |

### Driving Concepts

| Concept | Description | Available in Datasets | Derivation |
|---------|-------------|----------------------|------------|
| `speed_kmh` | Vehicle speed in km/h | DEVRT (speed, km/h), JAC (SPD, km/h), TUM (vehicle_speed, value_id=4, km/h) | High |
| `acceleration_ms2` | Acceleration in m/s² | DEVRT (Motor Pwr/w + speed diff, derived), TUM (derived from speed differences), JAC (AX/AY/AZ accelerometer, /192 scaling) | Derived in all |
| `distance_km` | Distance traveled in km | DEVRT (cumul_dist), JAC (ODO), TUM (traveled_distance, value_id=1299) | High |
| `motor_power_kw` | Motor power in kW | DEVRT (Motor Pwr(w) / 1000), TUM (hv_aux_power/ptc_power, W), JAC (implied) | Derived |
| `motor_torque_nm` | Motor torque in Nm | DEVRT (Torque Nm column), JAC (GX/GY/GZ gyroscope, derived), TUM (not in 29 value_ids) | Medium (DEVRT) |
| `brake_intensity` | Brake pedal intensity | DEVRT (regenwh sign + Motor Pwr), JAC (BRK column, unverified 0-28), TUM (hv_aux_power sign) | Low for JAC |
| `accelerator_position` | Accelerator pedal position | DEVRT (Aux Pwr(100w) indirect), JAC (ACC column, unverified 0-90), TUM (not in 29 value_ids) | Low for JAC |
| `regen_active` | Regenerative braking active flag | DEVRT (regenwh < 0), JAC (derived from BRK + CUR signs), TUM (hv_aux_power < 0) | Derived |

### Terrain Concepts

| Concept | Description | Available in Datasets | Derivation |
|---------|-------------|----------------------|------------|
| `altitude_m` | Altitude in meters above reference | DEVRT (altitude, elv_spy, m), JAC (ALT, m), TUM (in JSON/histograms, not value_overview) | Medium |
| `gradient_pct` | Road gradient in percent | Derived: Δaltitude_m / Δdistance_km × 100 | Derived concept (requires altitude + distance) |
| `uphill_flag` | Uphill driving indicator | Derived: gradient_pct > 0 | Derived |
| `downhill_flag` | Downhill driving indicator | Derived: gradient_pct < 0 | Derived |
| `flat_flag` | Flat road driving indicator | Derived: |gradient_pct| < threshold | Derived |
| `hilly_flag` | Hilly road indicator | Derived: |gradient_pct| > threshold | Derived |
| `latitude` | GPS latitude in decimal degrees | DEVRT (latitude), JAC (LAT, deg), TUM (in JSON/histograms) | High |
| `longitude` | GPS longitude in decimal degrees | DEVRT (longitude), JAC (LON, deg), TUM (in JSON/histograms) | High (JAC lon needs investigation) |

### Environment Concepts

| Concept | Description | Available in Datasets | Derivation |
|---------|-------------|----------------------|------------|
| `ambient_temperature_c` | Ambient air temperature in °C | DEVRT (amb_temp, °C), TUM (ambient_air_temp, value_id=15, °C), JAC (AIR, but FLAG not temp) | High (DEVRT/TUM), Low (JAC - is flag) |
| `humidity_pct` | Relative humidity in percent | NOT available in any dataset (3 datasets) | None |
| `wind_speed_kmh` | Wind speed in km/h | DEVRT (wind_kph, wind_mph), JAC (not available), TUM (not in 29 value_ids) | Medium (DEVRT only) |
| `wind_direction` | Wind direction | DEVRT (wind_dir, cardinal), JAC (not available), TUM (not available) | Medium (DEVRT only) |

### Energy Concepts

| Concept | Description | Available in Datasets | Derivation |
|---------|-------------|----------------------|------------|
| `net_energy_consumption_kwh_per_km` | Net energy consumption per km | DEVRT (derivable: SOC×cap/dist), TUM (derivable: SOC×cap/dist/J), JAC (derivable: limited) | Derivable from SOC+cap+dist |
| `energy_consumed_kwh` | Total energy consumed in kWh | DEVRT (derivable: SOC×cap/100), TUM (same), JAC (limited: no SOC) | Derivable where SOC available |
| `recovered_energy_kwh` | Recovered energy from regen in kWh | DEVRT (derivable: Σregenwh×time/3600), TUM (derivable: Σnegative_power×time/3600), JAC (limited) | Derivable where regen data available |
| `gross_energy_consumption_kwh` | Gross energy consumed (before regen subtraction) | DEVRT (power integration), TUM (same), JAC (limited) | Derivable |

### Vehicle Concepts

| Concept | Description | Available in Datasets | Confidence |
|---------|-------------|----------------------|------------|
| `vehicle_model` | Vehicle model identifier | DEVRT (car_description: Dacia Spring/Nissan Leaf), JAC (IEV40 implied), TUM (VW ID.3, CUPRA Born) | High |
| `vehicle_mass_kg` | Vehicle mass in kg | NOT available in any dataset (3 datasets) | None |
| `battery_pack_configuration` | Battery pack string config | DEVRT (capacity implies: 33 kWh = ~330 cells?, 62 kWh = different), TUM (108s2p, 58 kWh), JAC (not explicit) | Medium (TUM) |

### Derived/Composite Concepts

| Concept | Description | Derivation Formula | Available |
|---------|-------------|-------------------|-----------|
| `soc_change_pct` | SOC change during observation period | soc_end - soc_start | Where SOC available |
| `energy_wh` | Energy in watt-hours | (soc_start - soc_end) × capacity_wh / 100 | Where SOC + capacity available |
| `energy_kwh` | Energy in kilowatt-hours | energy_wh / 1000 | Where energy_wh available |
| `speed_variability` | Speed standard deviation | STD(speed_kmh) over window | Where speed data across window |
| `avg_speed_kmh` | Average speed over period | mean(speed_kmh) | Where speed data available |
| `deceleration_ms2` | Deceleration (negative acceleration) | -acceleration_ms2 when acceleration < 0 | Where acceleration available |
| `uphill_distance_pct` | Percentage of trip uphill | (uphill_distance_km / total_distance_km) × 100 | Where gradient derivable |
| `regen_energy_kwh` | Regenerated energy in kWh | Σ(regenwh × time_diff_s) / 3600 (DEVRT) or Σ(negative_power × time/3600) | Where regen data available |
| `average_acceleration_ms2` | Mean acceleration over period | mean(acceleration_ms2) | Where acceleration available |