# Data Pipeline

This document describes how raw EV telemetry becomes the frozen model's
training data and how raw datasets remain untouched end-to-end.

## 1. Pipeline overview

```
DEVRT raw CSV (Dacia Spring + Nissan Leaf)
    ↓ 1. Parsing (src/data/devrt_parser.py)
Standardized parquet (data/interim/devrt/)
    ↓ 2. Timestamp normalization (UTC epoch seconds)
    ↓ 3. Standardization (configs/schema.yaml)
Standardized feature matrix (data/processed/devrt_ml_features*.parquet)
    ↓ 4. Feature engineering (scripts/feature_engineering.py)
        → 102 route-aware features + target
    ↓ 5. Target generation (5 km future window)
    ↓ 6. Leakage audit (trip_phase removed; trip-level splits)
Train / validation / test splits (trip-disjoint)
    ↓ 7. Model (frozen ExtraTreesRegressor)
```

## 2. Step 1 — Parsing

`src/data/devrt_parser.py` reads the raw DEVRT CSV files:

- Discovers trips from `dataset/DEVRT/DEVRT/{DACIA SPRING,NISSAN LEAF}/**`.
- Parses raw signal columns and normalizes units (m/s → km/h, W → kW, etc.).
- Processes **one trip/file at a time** and writes standardized parquet via
  PyArrow to `data/interim/devrt/`.
- Generates a cleaning report (`docs/devrt_cleaning_report.md`) and a file
  inventory (`data/interim/devrt/file_inventory.csv`).

## 3. Step 2 — Timestamp normalization

Raw DEVRT timestamps are heterogeneous (relative elapsed values and absolute
formats). `timestamp_to_epoch_seconds` / `parse_timestamps` convert every
timestamp to **timezone-aware UTC epoch seconds**, so downstream windows,
deltas, and the 5 km future target are computed on a consistent axis.

## 4. Step 3 — Standardization

`configs/schema.yaml` defines the canonical signal set (SOC, capacity, speed,
altitude, motor power/torque/RPM, aux power, regen power, ambient temperature,
distance, time, vehicle model). Standardized columns are stored in
`data/interim/devrt/*_standardized.parquet` with transformation metadata
(`*_transformations.json`).

## 5. Step 4 — Feature engineering

`scripts/feature_engineering.py` (training) and
`src/inference/feature_builder.py` (runtime, shared) construct the **102
route-aware causal features**:

- 87 strictly onboard features: current values plus past-window aggregates
  (100 m / 500 m / 1 km / 2 km) of speed, altitude, motor, SOC deltas.
- 15 conditionally causal route/terrain features (`next_1km/2km/5km_*`):
  static-geography look-ahead (uphill fraction, gradient, net elevation).
- `trip_phase` was removed (trip-end leakage).

## 6. Step 5 — Target generation

`target_future_energy_kwh_per_km` = average consumption over the next 5 km:

```
target = (soc_i - soc_j) * capacity / 100 / (d_j - d_i),  d_j - d_i >= 4.5 km
```

The future window never crosses a trip boundary. Negative targets (regenerative
gain over the window) are kept as real signal. Rows without a valid 5 km
future window are dropped.

## 7. Step 6 — Leakage audit & splits

- Trip-level splitting (`src/data/create_split.py`): no trip appears in more
  than one split; rows sorted by timestamp within each split.
- GroupKFold (grouped by `trip_id`) for model selection; a fixed train /
  validation / test holdout for the final evaluation.
- Causal audit (`src/analysis/step7_7_causal_audit.py`) verified zero
  future/target leakage and removed `trip_phase`.
- Result: `data/processed/{train,validation,test}.parquet`
  (7,418 / 1,680 / 1,537 rows; 36 / 8 / 6 trips).

## 8. Step 7 — Model

`src/models/train_final_model.py` trains the frozen
`ExtraTreesRegressor(n_estimators=300, max_depth=10, min_samples_leaf=3,
random_state=42, n_jobs=-1)` with median imputation fit on TRAIN+VALIDATION
only, then evaluates the held-out test **exactly once** (marker-protected by
`reports/.step8_test_evaluated`).

## 9. Why raw datasets remain untouched

The raw files under `dataset/` are never modified:

- Parsers read them read-only and write standardized parquet to `data/interim/`.
- Raw CSV/parquet source files are the canonical, immutable input; every
  downstream stage is regenerable from them.
- `data/` is git-ignored (generated artifacts) while `dataset/DEVRT/` is
  tracked for reproducibility. The large third-party TUM dataset is
  git-ignored (own license, ~96 M rows).

## 10. Memory-safety during the pipeline

- PyArrow columnar I/O with row-group streaming (see `scripts/feature_engineering.py`).
- One file/trip at a time (never the whole corpus in memory).
- Explicit `gc` + `tracemalloc` for peak-memory bounding (TUM processing
  peaked at ~79–197 MB; see `reports/step11_memory_report.json`).

## 11. Reproducibility

Every stage is script-driven with `random_state=42`:

| Stage | Script |
|---|---|
| Parse DEVRT | `src/data/devrt_parser.py` |
| Standardize | `configs/schema.yaml` + parsers |
| Feature engineering | `scripts/feature_engineering.py` |
| Splits | `src/data/create_split.py`, `create_v2_splits.py` |
| Causal audit | `src/analysis/step7_7_causal_audit.py` |
| Train + freeze | `src/models/train_final_model.py` |
| Runtime features | `src/inference/feature_builder.py` |