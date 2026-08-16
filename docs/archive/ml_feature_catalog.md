# ML Feature Catalog

## 1. Battery
| Feature | Status | Notes |
|---------|--------|-------|
| `current_soc_pct` | RELIABLE | Available on Dacia & Nissan. |
| `battery_capacity_kwh` | RELIABLE | Static per vehicle model. |
| `soh_pct` | UNAVAILABLE | Dropped due to lack of variance. |

## 2. Speed
| Feature | Status | Notes |
|---------|--------|-------|
| `current_speed_kmh` | CONDITIONAL | Nissan only. |
| `past_1km_mean_speed_kmh` | CONDITIONAL | Nissan only. |
| `past_1km_speed_std` | CONDITIONAL | Nissan only. |

## 3. Acceleration
| Feature | Status | Notes |
|---------|--------|-------|
| `past_1km_mean_acceleration_mps2` | CONDITIONAL | Nissan only. |

## 4. Terrain
| Feature | Status | Notes |
|---------|--------|-------|
| `current_altitude_m` | RELIABLE | Available on Dacia & Nissan. |
| `past_1km_gradient_pct` | RELIABLE | Calculated dynamically from past altitude/distance. |
| `terrain_class` | RELIABLE | DOWNHILL, FLAT, UPHILL. |

## 5. Driving behavior
| Feature | Status | Notes |
|---------|--------|-------|
| (Derived from Speed) | CONDITIONAL | Nissan only. |

## 6. Environment
| Feature | Status | Notes |
|---------|--------|-------|
| `current_ambient_temperature_c` | CONDITIONAL | Nissan only. |

## 7. Power
| Feature | Status | Notes |
|---------|--------|-------|
| `current_motor_power_kw` | CONDITIONAL | Nissan only. |
| `current_aux_power_kw` | CONDITIONAL | Nissan only. |

## 8. Regeneration
| Feature | Status | Notes |
|---------|--------|-------|
| `past_1km_mean_regen_kw` | CONDITIONAL | Nissan only. |

## 9. Vehicle
| Feature | Status | Notes |
|---------|--------|-------|
| `vehicle_model` | RELIABLE | Categorical. |
