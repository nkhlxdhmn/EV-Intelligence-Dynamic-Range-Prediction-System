# DATA CORRUPTION FINDING & FIX (Step 7.6, Phase 1)

**Date:** 2026-08-16

## Summary

Two latent bugs corrupted the DEVRT data that the ML pipeline (Steps 6–9) was
built on. Both were found during the Step 7.6 optimization and fixed; all
standardized files, the v2 feature matrix, and the train/validation/test splits
were rebuilt from the fixes.

## Bug 1: Dacia relative-timestamp parsing (found in Phase 1 audit)

## Root cause (Bug 1)

Dacia `timestamp_data_utc` values are a **relative elapsed clock** in
`MM:SS.s` (minutes:seconds since trip start) that **wraps every 60 minutes**.
`pd.to_datetime(..., format='mixed')` *succeeded* on values whose minute part
was < 24 (e.g. `00:01.1`), silently attaching **today's date** (2026-08-16)
instead of falling through to the MM:SS branch, which only triggered for
minutes ≥ 24 (e.g. `33:04.6`).

## Bug 2: timestamp-unit conversion (1000x scale error)

Pandas 3.x stores tz-aware datetimes read back from parquet as
`datetime64[us, UTC]` (microseconds) for some files and `datetime64[ns, UTC]`
(nanoseconds) for others, depending on how the file was written. Several
downstream modules used the naive pattern

```python
time_s = timestamps.astype('int64').to_numpy(float) / 1e9
```

which assumes **nanoseconds**. On `datetime64[us]` input this silently
produced epoch seconds **1000x too small**. The parser originally wrote 33 of
58 files (all 29 Nissan + 4 Dacia) as `[us]`, so every **dt-derived feature**
in those trips was scaled by 1000x in the old v2:

- `time_since_trip_start_min` / `trip_elapsed_time_min` → **1000x too small**
  (max 0.03 min instead of ~40 min; some trips showed 1750 min = 29 h);
- `acceleration_mps2`, `mean/std/max/min_acceleration`,
  `acceleration_variability` → **1000x too large** (dividing by dt);
- `elevation_gain_rate` / `elevation_loss_rate` → **1000x too large**;
- `aux_energy_1km`, `regen_duration_estimate`,
  `regen_energy_recovered_1km`, `regen_intensity` → **1000x too small**;

while features that only divide/multiply distances or telemetry powers (speed,
gradient, SOC target) were unaffected. Bug 2 did **not** reorder rows, so the
target itself was not corrupted — but 14 model features were.

## Fix (Bug 2)

1. `src/data/devrt_parser.py` gained `timestamp_to_epoch_seconds(series)`,
   which normalizes the series to `datetime64[ns]` before reading `int64`,
   giving true epoch seconds for both `[ns]` and `[us]` input.
2. `scripts/comprehensive_feature_engineering.py`,
   `scripts/feature_engineering.py`, and
   `src/analysis/optimization_target_comparison.py` now call the helper
   instead of the naive `astype('int64')/1e9`.
3. `parse_timestamps()` normalizes **all** output branches (relative and
   absolute) to `datetime64[ns, UTC]`, so every standardized file is now
   `[ns]` and downstream unit assumptions always hold.
4. All 58 standardized files, v2, and splits were regenerated.

### Cascade

`engineer_trip()` sorts each trip by `["timestamp", "source_row_id"]` before
building distance windows and the target. Garbage 2026 timestamps reordered
rows, so:

- `distance_since_trip_start_km = d - d[0]` became **negative** for rows whose
  true position was earlier than the mis-sorted first row;
- every distance-window feature (gradient, elevation gain/loss, speed windows,
  power windows) was computed over wrongly-ordered rows;
- the target `target_future_energy_kwh_per_km` was derived from
  `np.searchsorted(distance, start + 5.0)` over the mis-ordered array, so
  affected rows got a **wrong target**;
- `hour_of_day` / `day_of_week` features were garbage (2026 dates).

## Scope of corruption (old vs rebuilt v2)

| Metric | OLD (corrupted) | NEW (rebuilt) |
|---|---|---|
| Samples | 9,952 | 10,635 |
| Negative `distance_since_trip_start_km` | 3,141 (31.6%) across 16 trips | 0 |
| Trips affected | 16 (11 train / 2 val / 3 test) | 0 |
| Valid timestamps | 69.0% | 100.0% |
| Garbage 2026 timestamps | 1,508 | 0 |
| Non-monotonic distance trips | 6 | 0 |
| Non-monotonic timestamp trips | 58 (before fix) | 0 |

The additional 683 samples exist because with correct monotonic ordering more
rows have a valid 5 km future horizon.

## Fix (Bug 1)

`src/data/devrt_parser.py`:

1. `parse_timestamps()` now detects the relative `MM:SS.s` / `HH:MM:SS` format
   **before** any absolute parser runs, so values with minutes < 24 can never
   be mis-parsed as today's date.
2. The 60-minute wrap is unwrapped (a drop of > 30 min = +1 lap) so the elapsed
   clock is strictly monotonic.
3. Timestamps are anchored to the **trip date from the filename**
   (e.g. `20230418_...` → 2023-04-18), so `hour_of_day` / `day_of_week` /
   `month` are correct.
4. Lone absolute rows embedded in relative trips (e.g. a single
   `18/04/2023 11:42`) are interpolated from the surrounding relative clock to
   preserve monotonic ordering.

## Impact on results

Because the target itself was corrupted for affected rows, all previously
reported Step 8/9 results (validation baselines, frozen model, feature
importance, and the single test evaluation) were computed on a partially
incorrect target. **The Step 9 frozen model and its test numbers are
superseded.** Step 7.6 re-runs the entire optimization on the clean data.

Step 9 *validation-side* reports (`step9_validation_baselines.csv`,
`validation_predictions_step9.parquet`, error analyses, distribution shift,
feature importance) were regenerated on clean data with the same A_BASIC
models for continuity. The historical test evaluation file
(`test_predictions_final.parquet`) is preserved as the single frozen-model
evaluation and is **not** regenerated during optimization (test set is
off-limits per Step 7.6 rules).

## Verification

- `tests/`: 64 passed (incl. `test_parse_timestamps_relative_wrap_correction`,
  `test_timestamp_to_epoch_seconds_units`, `test_parse_timestamps_returns_ns`).
- All 58 standardized trips: 100% valid timestamps, monotonic, zero 2026 dates.
- All 58 standardized files now `datetime64[ns, UTC]` (consistent unit).
- `reports/optimization_data_audit.csv` / `.json`: regenerated on clean v2.