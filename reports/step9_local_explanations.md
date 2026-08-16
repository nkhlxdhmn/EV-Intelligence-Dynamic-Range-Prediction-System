# Step 9D - Local Explanations (representative TRAIN+VAL samples)

Contributions are measured as prediction deltas vs the median-feature baseline (one-feature-at-a-time). This is PREDICTIVE attribution, NOT causal attribution.

## low_predicted_consumption
- Trip: `20230419_NISSAN_ANDOAIN_AZPEITIA_031` (Nissan Leaf)
- Predicted consumption: -0.24664 kWh/km (actual: -0.24799)
- Baseline (median features) prediction: 0.13838
- Positive contributors (push prediction up):
  - (none)
- Negative contributors (push prediction down):
  - next_5km_net_elev_m: -0.2499
  - next_5km_gradient_pct: -0.27089
  - next_5km_loss_m: -0.33418
  - current_altitude_m: -0.35828
  - mean_regen_power_500m: -0.36219
  - mean_speed_1km: -0.36416

## medium_predicted_consumption
- Trip: `20230419_DACIA_DONOSTIA_IRUN_025` (Dacia Spring)
- Predicted consumption: 0.13872 kWh/km (actual: 0.25318)
- Baseline (median features) prediction: 0.13838
- Positive contributors (push prediction up):
  - next_5km_gradient_pct: +0.00138
  - next_5km_net_elev_m: +0.00111
  - hour_cos: +0.00078
  - hour_of_day: +0.00072
  - trip_elapsed_time_min: +0.00052
- Negative contributors (push prediction down):
  - current_altitude_m: -0.00016

## high_predicted_consumption
- Trip: `20230419_NISSAN_ANDOAIN_AZPEITIA_031` (Nissan Leaf)
- Predicted consumption: 0.49153 kWh/km (actual: 0.49555)
- Baseline (median features) prediction: 0.13838
- Positive contributors (push prediction up):
  - max_speed_recent: +0.35319
  - positive_motor_power_fraction: +0.35318
  - mean_acceleration: +0.35314
  - speed_x_gradient: +0.35314
  - elevation_gain_1km: +0.35314
  - max_downhill_gradient: +0.35314
- Negative contributors (push prediction down):
  - (none)

## steep_terrain
- Trip: `20230419_NISSAN_ANDOAIN_AZPEITIA_031` (Nissan Leaf)
- Predicted consumption: 0.47609 kWh/km (actual: 0.49325)
- Baseline (median features) prediction: 0.13838
- Positive contributors (push prediction up):
  - mean_motor_power_500m: +0.34153
  - mean_neg_accel: +0.33844
  - max_motor_power_1km: +0.33837
  - max_acceleration: +0.33828
  - mean_motor_power_1km: +0.33806
  - mean_acceleration: +0.33806
- Negative contributors (push prediction down):
  - (none)

## high_regen
- Trip: `20230418_NISSAN_AZPEITIA_DONOSTIA_016` (Nissan Leaf)
- Predicted consumption: 0.1452 kWh/km (actual: 0.24087)
- Baseline (median features) prediction: 0.13838
- Positive contributors (push prediction up):
  - next_5km_gradient_pct: +0.01097
  - next_5km_net_elev_m: +0.00958
  - next_2km_loss_m: +0.00728
  - hour_cos: +0.00721
  - hour_of_day: +0.0072
  - hillyness_score: +0.0071
- Negative contributors (push prediction down):
  - (none)
