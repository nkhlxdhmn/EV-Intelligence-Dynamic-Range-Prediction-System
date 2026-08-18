# Inference

This document describes the inference pipeline and the frozen feature
contract. It consolidates the (removed) `docs/inference_feature_contract.md`.

## 1. Pipeline

```
POST /predict
  telemetry snapshot + route terrain (+ optional causal past window)
    -> pydantic validation (ranges, types, required fields; payload <= 1 MB)
    -> FeatureBuilder -> 102 causal features
    -> frozen SimpleImputer (median, fit on DEVRT train+val) + ExtraTreesRegressor
    -> predicted energy consumption (kWh/km over the next 5 km)
    -> RangeEstimator -> conservative / expected / optimistic
    -> PredictionResponse + audit log entry (request ID)
```

- The frozen preprocessor and model come from `models/`; their SHA-256 hashes
  are verified against `reports/step13_model_integrity.json` at validation time.
- Predicted consumption may be **non-positive** on net-regen segments (the
  training target is 5 km energy, which can be negative). The pipeline maps
  `consumption <= 0` to `range = 0.0` and `None` consumption/expected/optimistic
  fields; `status` is still returned.

## 2. Request / response contract

The authoritative OpenAPI schema is served by the running API at `/docs`.
Key fields:

| Field | Notes |
|---|---|
| `telemetry` | `vehicle_id`, `battery_capacity_kwh`, `timestamp`, `soc_pct`, `speed_kmh`, `altitude_m`, `ambient_temperature_c`, `distance_since_trip_start_km`, `time_since_trip_start_min`, optional motor/aux/regen/battery signals. |
| `route_terrain` | `source` (real DEM/GPS label; fabricated sources rejected) + `points` (offset_km, altitude_m). |
| `past_window` | optional causal history rows used for windowed features; `null` allowed. |
| `reserve_soc_pct` | driver reserve (default 10 %). |

Response:

- `status` — `ok` / `degraded`.
- `predicted_energy_kwh_per_km` — raw model output (may be <= 0).
- `range_km` — conservative / expected / optimistic bounds.
- `consumption` — normalized view (`conservative` / `expected` / `optimistic`);
  `null` when predicted consumption <= 0.
- `confidence` — reliability score and components (OOD / missing / route /
  width contributions), with `level` (high/medium/low).
- `features_used` — count of features actually used.

## 3. Feature contract

Authoritative feature list: `models/final_feature_list.json`
(102 route-aware causal features). Generated from the frozen feature list +
Step 7.7 causality audit; no feature names are invented.

Total features: **102** · Route-aware (`next_*`): **15** · Onboard: **87**

Legend:

- **required** — must be present and finite at inference; validation fails
  otherwise.
- **optional** — may be NaN pre-imputation; the frozen median imputer fills it.
- **missing-value behavior** — NaN handling at build time.
- **causal** — audited as causally valid at prediction time.

| feature | type | unit | source | required | calculation | causal | class | missing behavior |
|---------|------|------|--------|----------|-------------|--------|-------|------------------|
|---------|------|------|--------|----------|-------------|--------|-------|------------------|
| `current_soc_pct` | float | % | soc_pct | required | direct telemetry field | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `current_altitude_m` | float | m | altitude_m | required | direct telemetry field | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `current_gradient_pct` | float | % | altitude+distance window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `past_1km_gradient_pct` | float | % | altitude+distance window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `elevation_gain_100m` | float | m | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `elevation_gain_500m` | float | m | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `elevation_gain_1km` | float | m | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `elevation_loss_100m` | float | m | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `elevation_loss_500m` | float | m | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `elevation_loss_1km` | float | m | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `net_elevation_change_1km` | float | m | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_gradient_500m` | float | % | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_gradient_1km` | float | % | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `gradient_std_500m` | float | % | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `gradient_std_1km` | float | % | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `max_uphill_gradient` | float | % | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `max_downhill_gradient` | float | % | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `terrain_variability` | float | index | altitude window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `hillyness_score` | float | index | terrain_variability | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `uphill_fraction_1km` | float | ratio | gradient window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `downhill_fraction_1km` | float | ratio | gradient window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `flat_fraction_1km` | float | ratio | gradient window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `terrain_transition_count_1km` | int | count | gradient window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `gradient_direction_changes_1km` | int | count | gradient window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `elevation_gain_rate` | float | m/s | gain+time | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `elevation_loss_rate` | float | m/s | loss+time | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `distance_since_trip_start_km` | float | km | distance_km | required | direct telemetry field | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `time_since_trip_start_min` | float | min | timestamp | required | direct telemetry field | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `trip_distance_so_far_km` | float | km | distance_km | required | cumulative trip distance | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `trip_elapsed_time_min` | float | min | timestamp | required | elapsed time from trip start | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `hour_of_day` | float | h | timestamp | required | from UTC timestamp | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `day_of_week` | float | 0-6 | timestamp | required | from UTC timestamp | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `current_speed_kmh` | float | km/h | speed_kmh | required | direct telemetry field | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `mean_speed_500m` | float | km/h | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_speed_1km` | float | km/h | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `speed_std_500m` | float | km/h | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `speed_std_1km` | float | km/h | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `min_speed_recent` | float | km/h | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `max_speed_recent` | float | km/h | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `high_speed_fraction` | float | ratio | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `stopped_fraction` | float | ratio | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `stop_count_recent` | int | count | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `speed_change_recent` | float | km/h | speed window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `acceleration_mps2` | float | m/s^2 | speed diff | optional | d(speed/3.6)/dt | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_acceleration` | float | m/s^2 | accel window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `std_acceleration` | float | m/s^2 | accel window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `max_acceleration` | float | m/s^2 | accel window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `min_acceleration` | float | m/s^2 | accel window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `motor_power_kw` | float | kW | motor_power_kw | optional | direct telemetry field | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `torque_nm` | float | Nm | motor_torque_nm | optional | direct telemetry field | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `motor_rpm` | float | rpm | motor_rpm | optional | direct telemetry field | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_motor_power_500m` | float | kW | motor window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_motor_power_1km` | float | kW | motor window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `max_motor_power_1km` | float | kW | motor window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `positive_motor_power_fraction` | float | ratio | motor window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `power_variability` | float | kW | motor window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `aux_power_kw` | float | kW | aux_power_kw | optional | direct telemetry field | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_aux_power_500m` | float | kW | aux window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_aux_power_1km` | float | kW | aux window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `max_aux_power_1km` | float | kW | aux window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `aux_power_variability` | float | kW | aux window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `aux_energy_1km` | float | kWh | aux*time | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `regen_power_kw` | float | kW | regen_power_kw | optional | direct telemetry field | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_regen_power_500m` | float | kW | regen window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_regen_power_1km` | float | kW | regen window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `max_regen_power_1km` | float | kW | regen window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `regen_event_count_1km` | int | count | regen window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `regen_duration_estimate` | float | s | regen window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `regen_energy_recovered_1km` | float | kWh | regen*time | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `regen_fraction_of_driving_time` | float | ratio | regen window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `regen_intensity` | float | kWh/km | regen/energy | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `current_temperature_c` | float | degC | ambient_temperature_c | required | direct telemetry field | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `temperature_recent_mean` | float | degC | temp window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `speed_x_gradient` | float | km/h*% | speed*gradient | optional | product of telemetry fields | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `speed_squared` | float | (km/h)^2 | speed | required | product of telemetry fields | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `speed_x_temperature` | float | km/h*C | speed*temp | required | product of telemetry fields | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `hour_sin` | float | -1..1 | timestamp cyclic | required | sin/cos(2*pi*hour/24) | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `hour_cos` | float | -1..1 | timestamp cyclic | required | sin/cos(2*pi*hour/24) | CAUSAL | onboard | never NaN: validation rejects missing telemetry |
| `next_1km_net_elev_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_1km_gradient_pct` | float | % | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_1km_gain_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_1km_loss_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_2km_net_elev_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_2km_gradient_pct` | float | % | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_2km_gain_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_2km_loss_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_5km_net_elev_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_5km_gradient_pct` | float | % | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_5km_gain_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_5km_loss_m` | float | m | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_5km_uphill_frac` | float | ratio | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_5km_downhill_frac` | float | ratio | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `next_5km_flat_frac` | float | ratio | DEM upcoming | required | from upcoming DEM profile (RouteTerrainProvider), never fabricated | CONDITIONALLY_CAUSAL | route-aware | never NaN: build must fail if route terrain absent |
| `speed_p10` | float | km/h | speed recent | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `speed_p50` | float | km/h | speed recent | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `speed_p90` | float | km/h | speed recent | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `speed_iqr` | float | km/h | speed recent | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_pos_accel` | float | m/s^2 | accel window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `mean_neg_accel` | float | m/s^2 | accel window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `regen_share_1km` | float | ratio | regen/traction | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `regen_events_per_km` | float | 1/km | regen window | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |
| `temperature_bucket` | float | degC | temp floor/5 | optional | causal distance/time window statistic (reproduced from engineer_trip) | CAUSAL | onboard | NaN allowed pre-imputation; frozen median imputer fills |

## Missing-value policy

The frozen model was trained with a SimpleImputer (median) fit on DEVRT
train+validation only; the same preprocessor is used at inference. Optional
telemetry-derived features may be NaN before imputation. **Critical features
(route-aware `next_*` and required scalar telemetry) must never be NaN**; the
feature builder raises `FeatureBuildError` rather than silently zero-filling
or imputing them.

## Route/DEM dependency

The 15 `next_*` features require upcoming terrain elevation from a real
DEM/GPS source. The `RouteTerrainProvider` interface supplies this; the build
fails with a clear error if terrain is unavailable. Terrain is **never**
fabricated.
