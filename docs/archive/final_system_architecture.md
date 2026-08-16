# Final System Architecture

STEP 12D — end-to-end technical architecture of the EV Intelligence &
Dynamic Range Prediction System (training and inference).

## 1. High-level data flow

```
RAW DATA (DEVRT / TUM / JAC)
        ↓
Dataset-specific parsers
        ↓
Standardized Parquet
        ↓
Memory-safe feature engineering
        ↓
Causal feature audit
        ↓
Train / Validation / Test split (trip-disjoint)
        ↓
ExtraTreesRegressor (frozen model)
        ↓
Explainability (permutation importance)
        ↓
Energy prediction (kWh/km, next 5 km)
        ↓
Range estimation
        ↓
FastAPI inference API
```

## 2. RAW DATA

| Dataset | Content | Role | Parser |
|---|---|---|---|
| DEVRT | Dacia Spring + Nissan Leaf telemetry CSV (58 trips) | Training + test | `src/data/devrt_parser.py` |
| TUM | 98M-row EV UDS parquet (CUP1–5, ID1–2) | External validation (blocked) | `src/data/tum_parser.py`, `scripts/tum_extractor.py` |
| JAC | CSV fleet telemetry | Inspection only | `src/data/jac_parser.py` |

Raw datasets are read once, standardized, and never re-read by later stages.

## 3. Dataset-specific parsers

Each raw format is converted into a **common standardized schema**
(`configs/schema.yaml`): `timestamp`, `soc_pct`, `soh_pct`, `speed_kmh`,
`ambient_temperature_c`, `motor_power_kw`, `aux_power_kw`,
`motor_temperature_c`, `motor_torque_nm`, `motor_rpm`, `altitude_m`,
`distance_km`, `latitude`, `longitude`, `battery_capacity_kwh`,
`regen_power_kw`, `reference_consumption_wh_per_km`, quality flags.

TUM extraction is **streamed row-group by row-group** (PyArrow) to stay
memory-safe over the 98M-row source.

## 4. Standardized Parquet

Outputs:
- `data/interim/devrt/*.parquet` — one standardized file per trip (58 trips).
- `data/interim/jac/jac_standardized.parquet`.
- `data/interim/tum/*.parquet` — required signals per vehicle (CUP/ID).

Parquet is used because it is **columnar, compressed, typed, and
memory-mappable** — ideal for wide telemetry without loading everything into
RAM.

## 5. Memory-safe feature engineering

`scripts/feature_engineering.py` and
`scripts/comprehensive_feature_engineering.py`:

- Process **one trip at a time** (`[t - window, t]` rolling windows).
- Streaming aggregation; no whole-dataset copies in memory.
- Produces `data/processed/devrt_ml_features_v3_route_aware.parquet` (102
  features) and `devrt_ml_features_v3_strict.parquet` (87 features).
- Targets computed with **future windows** (next 5 km) in a leakage-safe way.

## 6. Causal feature audit

`src/analysis/step7_7_causal_audit.py` classifies every feature:
- **87 CAUSAL** — strictly onboard, current/past windows.
- **15 CONDITIONALLY_CAUSAL** — route-aware `next_*` terrain (static
  geography; valid only with route/DEM knowledge).
- **1 TRIP_END_LEAKAGE** — `trip_phase` **removed**.
- 0 future leakage, 0 target leakage.

Result: two frozen reduced feature sets (102 route-aware, 87 strict onboard).

## 7. Train / Validation / Test split

`src/data/create_v2_splits.py`, `src/data/create_split.py`:

- **Trip-disjoint** (trips split, not samples) because the 5 km forward target
  overlaps future windows between adjacent samples.
- Stratified by vehicle: 36/8/6 trips → 7,418 / 1,680 / 1,537 rows.
- Temporal order preserved within trips; seed 42.

## 8. ExtraTrees model

`src/models/train_experiments.py`, `src/models/train_final_model.py`:

```
ExtraTreesRegressor(n_estimators=300, max_depth=10,
                    min_samples_leaf=3, random_state=42, n_jobs=-1)
```

- Trained on TRAIN+VALIDATION (9,098 rows).
- Frozen artifacts: `models/ev_energy_extratrees_route_aware.joblib`,
  `models/final_preprocessor.joblib`, `models/final_feature_list.json`.
- Median imputer fitted on train+val only (handles Dacia missing telemetry).

## 9. Explainability

`src/analysis/step9_explainability.py`:
- Permutation importance under GroupKFold (MAE degradation).
- Top predictors: `next_5km_uphill_frac`, `next_5km_gradient_pct`,
  `next_5km_net_elev_m`, current altitude, day-of-week, time-of-day.
- SHAP skipped (not installed; heavy dependency); local explanations for 5
  representative samples.

## 10. Energy prediction

The frozen model predicts `target_future_energy_kwh_per_km` — average
consumption over the next 5 km. During inference, the FeatureBuilder
(`src/inference/feature_builder.py`) reconstructs the exact 102 features
per-request from validated telemetry + route terrain, validates order/set/
NaN/ranges, then the frozen imputer and model produce the prediction.

## 11. Range estimation

`src/inference/range_estimator.py`:

```
usable_energy_kwh = capacity * max(soc - reserve, 0) / 100
expected_range_km = usable_energy_kwh / predicted_energy_kwh_per_km
```

- Default reserve 10% SOC.
- Uncertainty band from train+val residual quantiles (q10/q90) →
  conservative/optimistic ranges.
- Consumption ≤ 0 (net regen gain) → range 0.

## 12. FastAPI inference

`api/main.py` + `src/inference/service.py`:

- `GET /health`, `GET /model/info`, `POST /predict`, `GET /docs`.
- Pydantic-validated inputs (ranges, timezone-aware timestamps, ≥2 terrain
  points, no fabricated source labels).
- RouteTerrainProvider abstraction; synthetic provider labeled `SYNTHETIC_DEMO`
  (demos only).
- Clean error responses — no stack traces, no filesystem paths.
- Startup loads model once; ~198 MB peak RSS (< 500 MB budget).

## 13. TRAINING vs INFERENCE pipeline

| Aspect | TRAINING pipeline | INFERENCE pipeline |
|---|---|---|
| Raw datasets | Loaded (streamed) | **Never loaded** |
| Feature engineering | Offline, full windows | Per-request builder |
| Model | Trained + frozen | Loaded once from joblib |
| Preprocessor | Fitted on train+val | Frozen transform only |
| Target | Computed (future window) | Not needed |
| Memory | Bounded streaming | ~198 MB |
| Outputs | joblib + parquet | JSON responses |
| Test set | Evaluated once | Never used |

## 14. Why raw datasets are NOT loaded during inference

1. **Memory**: the inference process only needs the frozen model (~15 MB),
   the imputer, and the 102-feature list — not gigabytes of raw telemetry.
2. **Startup speed**: loading the model once at startup (sub-second) instead
   of parsing large datasets.
3. **Isolation / privacy**: no training data crosses into the serving
   boundary, so prediction responses cannot leak dataset content.
4. **Correctness**: inference features are built per-request from validated
   inputs using the same feature contract as training, keeping train/serve
   consistency without re-deriving from raw files.

The architecture keeps data engineering (offline, heavy, streaming) and
serving (online, light, validated) cleanly separated.