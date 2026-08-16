# Step 9O: Validation Distribution Shift Analysis

Comparison of TRAIN vs VALIDATION distributions.
Test set NOT used.

| Feature | Train mean | Val mean | Train std | Val std | Shift (val-train)/train_std |
|---------|-----------|----------|-----------|---------|---------------------------|
| target_future_energy_kwh_per_km | 0.1509 | 0.1428 | 0.0866 | 0.1023 | -0.093 |
| current_soc_pct | 77.4214 | 82.3952 | 12.7082 | 6.6801 | 0.391 |
| current_altitude_m | 130.5524 | 154.1281 | 98.5540 | 124.4181 | 0.239 |
| current_gradient_pct | -0.2352 | -0.0870 | 3.9330 | 5.0006 | 0.038 |
| battery_capacity_kwh | 44.7869 | 47.9315 | 14.2449 | 14.4979 | 0.221 |

## Categorical Distribution

### Terrain class
| Terrain | Train % | Validation % |
|---------|---------|--------------|
| FLAT | 68.9 | 70.1 |
| UPHILL | 13.9 | 14.5 |
| DOWNHILL | 17.2 | 15.5 |

### Vehicle
| Vehicle | Train % | Validation % |
|---------|---------|--------------|
| Dacia Spring | 59.4 | 48.5 |
| Nissan Leaf | 40.6 | 51.5 |

## Interpretation

A normalized shift magnitude > 0.5 indicates a notable distribution difference.
