# ML Interview Guide — EV Energy Consumption & Range Prediction

Concise, technically honest answers grounded in the actual project. Each
answer states what was done, why, and the caveat. These are talking points,
not scripts.

---

### 1. Why ExtraTrees?

ExtraTreesRegressor randomizes both the feature subset AND the split threshold
per node, which reduces variance further than Random Forest at the same
ensemble size. It fit our dataset well: ~9,000 rows, 102 features, mostly
tabular with non-linear interactions between speed, altitude, SOC, and
look-ahead terrain. It trains fast, needs no heavy GPU, and gives comparable
or better accuracy to XGBoost on this size of tabular data with far fewer
tuning knobs. We froze it with `random_state=42` for reproducibility.

### 2. Why not Random Forest?

We benchmarked a basic RF as a Step 8 baseline. Random Forest's split
thresholds are learned per feature, which is more prone to variance and
overfitting on correlated tabular telemetry. ExtraTrees' random thresholds
act as an extra regularizer and produced a lower held-out MAE in our model
comparison. The difference was meaningful on the strict-onboard set but modest
on the full route-aware set — we kept ExtraTrees because it won on the
marker-protected test.

### 3. Why not XGBoost?

We did evaluate an XGB baseline. On ~9k rows XGBoost needed more
hyperparameter tuning and was more sensitive to leakage-adjacent artifacts
(when features were correlated with the trip), while ExtraTrees was more robust
out of the box. Boosting can overfit small structured datasets; ExtraTrees'
bagging-style averaging is better behaved here. Nothing about XGBoost was
wrong — it was a modeling choice that ExtraTrees won on cross-validation and
the final test.

### 4. Why 5 km prediction horizon?

Measured from the data. DEVRT average consumption is ~0.15 kWh/km and a 1% SOC
change on a 33–62 kWh battery is ~0.33–0.62 kWh, so SOC ticks over every
2–4 km. A 1 km horizon produced many degenerate ~0 kWh targets from integer
SOC quantization. A 5 km window gives stable SOC-delta targets without
smoothing over terrain features too heavily. The target is
`(soc_i - soc_j) * capacity / 100 / (d_j - d_i)` with `d_j - d_i >= 4.5 km`,
never crossing a trip boundary.

### 5. How did you prevent leakage?

Four layers:
1. **Trip-level splitting** — a trip never spans train and validation/test.
2. **GroupKFold** grouped by `trip_id` for model selection.
3. **Future target separation** — the 5 km target window stops at trip ends.
4. **Causal feature audit** — every feature was checked for causality and
   prediction-time availability. This is how we caught and removed
   `trip_phase`, and how we separated 87 strictly causal onboard features from
   15 conditionally causal `next_*` route features.

### 6. What is GroupKFold?

K-Fold cross-validation where the grouping key (here `trip_id`) is never split
across folds. Standard K-Fold would put rows of the same trip in both train and
validation, letting the model memorize trip-level speed/altitude patterns and
inflate CV scores. GroupKFold gives honest, trip-disjoint estimates.

### 7. Why split by trip?

Telemetry is not independent samples — rows within a trip are highly
autocorrelated (same driver, road, battery, weather). Random row splits leak
temporal context between folds, so CV becomes optimistic. Splitting by trip
mimics the real deployment: the model must predict for trips it has never seen.

### 8. Why is trip_phase leakage?

`trip_phase` encoded the position within the trip (start / middle / end).
Because the target is the *future* 5 km consumption window, a trip near its end
has a different (or missing) future window than a trip at its start —
`trip_phase` was therefore informative about the target in a way that is
neither causal nor available at prediction time. The causal audit flagged it,
and we removed it.

### 9. Why are next_5km features conditionally causal?

The `next_1km/2km/5km_*` elevation features are computed from the *future*
route geometry (static geography), not from future vehicle behavior. They are
causal **only if** the route/DEM is known before driving — which is true in a
route-aware deployment (GPS + elevation map) but not in a strict onboard
setting. We labeled them "conditionally causal" and documented the dependency.

### 10. Why did strict onboard performance decrease?

The strict onboard model uses only the 87 non-route features (no look-ahead
terrain). GroupKFold MAE rose from 0.04002 to 0.05518 (±0.00158) and R² dropped
to 0.3724. Most predictive signal comes from upcoming elevation: gradient and
uphill fraction ahead are the strongest features. Without route knowledge the
model cannot anticipate climbs, so it under-predicts consumption before
ascents and over-predicts before descents.

### 11. Why is route-aware terrain useful?

Uphill fraction, gradient, and net elevation change over the next 1/2/5 km
dominate feature importance and permutation importance. A vehicle's energy
consumption over the next 5 km is largely determined by how much elevation it
must gain — that is exactly what look-ahead terrain encodes. It converts a
reactive (current-state) model into a predictive (route-aware) model.

### 12. Why is TUM validation blocked?

The frozen model needs 102 features; only 30 are reproducible from TUM signals.
41 require GPS/altitude route terrain, 19 require traction-motor signals, 12
require per-trip distance boundaries. The 5 km distance-based target is also
unavailable in TUM. Without those features the frozen model cannot run, so any
"validation" would be meaningless. We used TUM for memory-safety engineering
instead and documented the block explicitly. We do not claim cross-dataset
validation.

### 13. Why not merge all datasets?

DEVRT (Dacia Spring + Nissan Leaf) has aligned, trip-bounded telemetry and
GPS-derived terrain. JAC lacks SOC; TUM lacks route/terrain and motor features
and has a different target structure. Merging would create feature matrices
with most columns missing and a target that cannot be computed consistently —
that introduces imputation bias and invalid cross-dataset comparisons. We kept
DEVRT as the training corpus and used TUM only as a memory-safety engineering
target.

### 14. How did you handle missing telemetry?

The feature builder returns `NaN` for missing optional signals, and the frozen
preprocessor applies median imputation fit on TRAIN+VALIDATION **only** (never
the test set). Dacia lacks speed/motor/temp columns, so those rows are handled
by imputation at training time and at runtime the API substitutes `NaN` for
unavailable optional telemetry. Missingness is part of the schema contract, not
a silent failure.

### 15. Why wasn't MAPE used?

About 3% of test targets are near zero (<0.05 kWh/km) because regenerative
driving can yield near-zero window consumption. MAPE is unstable or undefined
with near-zero denominators and would misrepresent model quality. MAE is
interpretable in the physical unit (kWh/km) and RMSE penalizes large errors,
which matters for range estimation. We reported MAE, RMSE, R², and bias.

### 16. How is range calculated?

`usable_energy_kwh = capacity * max(soc - reserve, 0) / 100`, then
`expected_range_km = usable_energy / predicted_kwh_per_km`. A configurable SOC
reserve (default 10%) prevents discharging to zero. Predicted consumption ≤ 0
(net regen) yields no range. Conservative/optimistic bounds come from model
residual quantiles (TRAIN+VAL): a positive residual means under-prediction →
higher actual consumption → lower (conservative) range. The served API band is
currently collapsed to the expected value because residual quantiles are not
wired into the running service; `estimate_range_band` implements the full band
and is unit-tested.

### 17. How is uncertainty estimated?

From residual quantiles computed on TRAIN+VALIDATION only
(`reports/step9_trainval_residual_quantiles.json`), e.g. q10 = −0.047 and
q90 = +0.036 kWh/km. `estimate_range_band` shifts the predicted consumption by
those quantiles to produce conservative (high consumption) and optimistic (low
consumption) ranges, with an engineering floor so optimistic range never
exceeds 2× expected. It is honest uncertainty: derived from held-out residuals,
not a fabricated confidence interval.

### 18. How did you handle Dacia vs Nissan?

Both vehicles live in the same feature space; vehicle-model differences are
captured by the vehicle model's telemetry (capacity, power, weight proxies)
and the model is trained on both. Test performance differs: Dacia MAE 0.03638
(n=1,044), Nissan MAE 0.05116 (n=493). Nissan is harder to predict — richer
telemetry but wider operating envelope and heavier/less efficient drive. We did
not build per-vehicle models because the dataset is small; a production system
could add vehicle ID as a grouped feature or train per-vehicle calibrators.

### 19. How did you handle memory constraints?

Streaming, not batch-loading. Parsers process one trip/file at a time and write
standardized parquet via PyArrow. Feature engineering streams row groups and
uses a `pq.ParquetWriter`. Explicit `gc` + `tracemalloc` bound peak memory. The
~96 M-row TUM dataset is never loaded fully; peak processing RAM was ~79–197 MB
(see `reports/step11_memory_report.json`). No dataset is held in RAM wholesale.

### 20. Why PyArrow instead of loading everything with pandas?

pandas `read_csv` materializes the whole file into Python objects — hundreds of
MB to GBs for 96 M rows. PyArrow reads parquet columnar data in bounded row
groups, streams directly, and has predictable memory behavior. It also keeps
types efficient (timestamps, floats) and writes compact parquet. For a
pipeline that must scale to corpus-sized telemetry, bounded-memory columnar I/O
is the difference between running on a laptop and OOM-killing a server.

### 21. What happens if route information is unavailable?

The API accepts route terrain in the request body. With no connected route
provider, it uses the validated request-body terrain. The dashboard DEMO mode
uses a clearly-labeled synthetic route provider; LIVE mode requires a real
source. Without any terrain the model degrades to the strict onboard set,
whose GroupKFold MAE is 0.05518 vs 0.04002 route-aware — so the range estimate
is less accurate but the system still runs and reports that it used a degraded
or synthetic route source.

### 22. What are the biggest weaknesses?

1. **External validation blocked** — metrics are DEVRT-only; no cross-dataset
   proof.
2. **Route-aware dependency** — accuracy drops sharply without planned-route
   elevation.
3. **SOC-derived target** — target quality depends on battery capacity
   assumptions (fleet spec 58 kWh, not per-vehicle BMS).
4. **Small, single-region corpus** — Basque Country urban/suburban routes;
   generalization is unproven.
5. **No weather/wind/traffic** features.
6. **Range band not wired into the running API** (only in unit-tested code).

### 23. How would you improve it with more real vehicle data?

- Per-vehicle battery capacity/SOH from BMS instead of fleet spec.
- Weather (temp, wind) and traffic ingestion as live context features.
- Per-vehicle calibrators or a small per-vehicle fine-tune layer.
- Multi-region trips to test generalization honestly.
- Ground-truth energy meter (actual kWh pulled) instead of SOC-derived target.
- High-frequency regen/coasting events to sharpen near-zero consumption cases.

### 24. How would you deploy it?

Exactly as implemented: FastAPI served by uvicorn in a non-root Docker
container with a healthcheck (`docker compose up --build`). The image copies
only `src/`, `api/`, `models/`, `frontend/` and pinned
`requirements.inference.txt`; raw datasets are not in the image. For scale I'd
add: request tracing/request IDs (already present via `InferenceLogger`),
metric export (prometheus), horizontal replicas behind a load balancer, and
model/feature contract versioning via `/model/info`.

### 25. What would you change for production?

- Wire the residual-quantile range band into the served response.
- Strict pydantic version pinning and a migration path when the frozen model
  is replaced.
- Real route provider (route + DEM lookup) replacing the synthetic provider.
- Live telemetry ingestion with a schema registry and back-pressure.
- Per-request latency SLOs and load tests.
- A/B behind feature flags between the current frozen model and any future
  model, with the DEVRT test evaluated once per candidate and never reused.