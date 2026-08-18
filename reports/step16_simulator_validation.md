# STEP 16 — 50-scenario simulator validation (real /predict)

- Date: 2026-08-18T13:42:15
- Scenarios: 50 seeds x 6 checkpoints = 300 predictions
- Passed: 300 / 300
- Status counts: {'OK': 300}
- Non-positive consumption (kWh/km <= 0, range 0.0): 11 (3.7% of predictions)
- Energy kWh/km: min=-0.191966, max=0.378674, mean=0.149277
- Expected range km: min=0.0, max=78340.26, mean=534.9
- Deterministic rerun (seed 0): {'same_seed_within_1e-9': True, 'seed_0_trials_kwh_per_km': [0.15324164847958222, 0.15324164847958222]}
- HTTP /predict subset: True (10 checks)
- Model hash unchanged: True

## Invariants validated

- No crashes; every checkpoint produced a structured response.
- predicted_energy_kwh_per_km finite (may be <= 0;
  the training target is 5-km energy and legitimately goes negative during
  regen-dominated segments, and the pipeline maps those to range 0.0).
- expected_range_km finite and >= 0 (0.0 exactly when predicted energy <= 0,
  with conservative/optimistic None per the pipeline contract).
- conservative <= expected <= optimistic when range > 0.
- status in {OK, DEGRADED}.
- route_terrain_source == SIMULATOR_ROUTE (honest labeling).
- usable_energy_kwh > 0.
- non-positive-consumption instants are a small minority (< 20%).

## Per-scenario summary

| seed | checkpoints | min kWh/km | max kWh/km | statuses |
|------|-------------|------------|------------|----------|
| 0 | 6 | 0.0432 | 0.3131 | {'OK': 6} |
| 1 | 6 | 0.1331 | 0.1475 | {'OK': 6} |
| 2 | 6 | 0.1491 | 0.1546 | {'OK': 6} |
| 3 | 6 | 0.1379 | 0.1520 | {'OK': 6} |
| 4 | 6 | 0.1439 | 0.1752 | {'OK': 6} |
| 5 | 6 | 0.1301 | 0.2658 | {'OK': 6} |
| 6 | 6 | 0.1420 | 0.1481 | {'OK': 6} |
| 7 | 6 | 0.0828 | 0.1470 | {'OK': 6} |
| 8 | 6 | 0.1478 | 0.1660 | {'OK': 6} |
| 9 | 6 | -0.1920 | 0.2837 | {'OK': 6} |
| 10 | 6 | 0.1430 | 0.1474 | {'OK': 6} |
| 11 | 6 | -0.0309 | 0.3787 | {'OK': 6} |
| 12 | 6 | -0.0903 | 0.2499 | {'OK': 6} |
| 13 | 6 | 0.1281 | 0.2096 | {'OK': 6} |
| 14 | 6 | 0.1331 | 0.1467 | {'OK': 6} |
| 15 | 6 | 0.1535 | 0.1975 | {'OK': 6} |
| 16 | 6 | 0.1150 | 0.1572 | {'OK': 6} |
| 17 | 6 | -0.0535 | 0.3516 | {'OK': 6} |
| 18 | 6 | 0.1321 | 0.1453 | {'OK': 6} |
| 19 | 6 | 0.1307 | 0.1475 | {'OK': 6} |
| 20 | 6 | 0.1460 | 0.1609 | {'OK': 6} |
| 21 | 6 | 0.1415 | 0.1539 | {'OK': 6} |
| 22 | 6 | 0.1520 | 0.2344 | {'OK': 6} |
| 23 | 6 | 0.0479 | 0.1666 | {'OK': 6} |
| 24 | 6 | -0.0835 | 0.3146 | {'OK': 6} |
| 25 | 6 | -0.1681 | 0.3699 | {'OK': 6} |
| 26 | 6 | 0.1508 | 0.1635 | {'OK': 6} |
| 27 | 6 | -0.1297 | 0.3663 | {'OK': 6} |
| 28 | 6 | 0.1439 | 0.1488 | {'OK': 6} |
| 29 | 6 | 0.1330 | 0.1463 | {'OK': 6} |
| 30 | 6 | 0.1277 | 0.2423 | {'OK': 6} |
| 31 | 6 | 0.1326 | 0.1458 | {'OK': 6} |
| 32 | 6 | 0.1451 | 0.1830 | {'OK': 6} |
| 33 | 6 | 0.1507 | 0.1633 | {'OK': 6} |
| 34 | 6 | 0.0782 | 0.2380 | {'OK': 6} |
| 35 | 6 | 0.1080 | 0.2606 | {'OK': 6} |
| 36 | 6 | 0.0783 | 0.2465 | {'OK': 6} |
| 37 | 6 | 0.1443 | 0.1486 | {'OK': 6} |
| 38 | 6 | 0.0665 | 0.2986 | {'OK': 6} |
| 39 | 6 | 0.1359 | 0.1441 | {'OK': 6} |
| 40 | 6 | -0.1086 | 0.3314 | {'OK': 6} |
| 41 | 6 | 0.0688 | 0.3129 | {'OK': 6} |
| 42 | 6 | 0.1433 | 0.1469 | {'OK': 6} |
| 43 | 6 | 0.1222 | 0.1515 | {'OK': 6} |
| 44 | 6 | -0.0063 | 0.3671 | {'OK': 6} |
| 45 | 6 | 0.1204 | 0.1840 | {'OK': 6} |
| 46 | 6 | 0.1308 | 0.1494 | {'OK': 6} |
| 47 | 6 | 0.0809 | 0.1485 | {'OK': 6} |
| 48 | 6 | 0.1332 | 0.2538 | {'OK': 6} |
| 49 | 6 | 0.1277 | 0.1455 | {'OK': 6} |
