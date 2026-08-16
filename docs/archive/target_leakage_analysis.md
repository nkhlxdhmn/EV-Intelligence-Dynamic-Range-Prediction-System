# Target Leakage Analysis

## Concept
Target leakage occurs when a model is trained with features that will not be available at inference time (i.e., in production when predicting the future), or features that are mathematically derived from the target itself. In our case, the target is the `future_energy_consumption_kwh_per_km` over a 5 km window starting from time `t`.

## Forbidden Features (High Leakage Risk)
The following variables must **NEVER** be used as model inputs at time `t`:

1. **Future SOC (`soc_pct_at_t_plus_5km`)**: Directly reveals the target energy consumed.
2. **Trip-end SOC (`soc_end`)**: Implies the total energy consumed on the trip.
3. **Future Distance (`distance_km_at_t_plus_5km`)**: Implies the span of the target.
4. **Future Altitude (`altitude_m_at_t_plus_5km`)**: You cannot know the exact altitude 5 km ahead unless you have a pre-programmed navigation route. Since we don't, using future altitude leaks terrain foresight that a simple real-time predictor lacks.
5. **Future Speed / Acceleration**: Impossible to know in real-time what the traffic or speed will be in 3 kilometers.
6. **Reference Consumption (`reference_consumption_wh_per_km`)**: This is a trip-level aggregate baseline value that is only known after the trip or represents an overall static average.
7. **Future Ambient Temperature**: Temperature changes in the future cannot be used.
8. **Future Auxiliary / Regen Power**: Unknown until the driving actually happens.

## Safe Features (Information available at time `t`)
The following variables are safe to use:

1. **Current Status**: `current_soc_pct`, `current_speed_kmh`, `current_altitude_m`, `battery_capacity_kwh`, `ambient_temperature_c`.
2. **Historical Rolling Windows (Past-Only)**: `past_1km_mean_speed`, `past_1km_gradient_pct`, `terrain_class`.
    - *CRITICAL*: These must be calculated strictly from rows `t-n` to `t`. Using `shift(1)` ensures we don't accidentally leak `t+1`.

## Evaluation Strategy
To guarantee no leakage, `src/evaluation/leakage_audit.py` will audit the final ML parquet dataset to ensure no column names contain forbidden keywords (like "future", "end", "total") except the `target` column itself, and mathematically verify that no input column is highly correlated (>0.99) with the target (which often indicates mathematical leakage).
