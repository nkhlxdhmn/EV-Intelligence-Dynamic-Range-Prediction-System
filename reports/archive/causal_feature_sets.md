# Causal Feature Sets (Step 7.7C)

- **FEATURE_SET_CAUSAL (route-aware):** 102 features. Current + past + static-geography look-ahead terrain. Requires the system to know the planned route / a digital elevation map.

- **FEATURE_SET_STRICT_ONBOARD:** 87 features. Only current sensor data, historical data, and past-derived features. No future rows, no trip-end information.


## Excluded from strict onboard

- `next_1km_gain_m`
- `next_1km_gradient_pct`
- `next_1km_loss_m`
- `next_1km_net_elev_m`
- `next_2km_gain_m`
- `next_2km_gradient_pct`
- `next_2km_loss_m`
- `next_2km_net_elev_m`
- `next_5km_downhill_frac`
- `next_5km_flat_frac`
- `next_5km_gain_m`
- `next_5km_gradient_pct`
- `next_5km_loss_m`
- `next_5km_net_elev_m`
- `next_5km_uphill_frac`
- `trip_phase`

## Excluded from route-aware

- `trip_phase`
