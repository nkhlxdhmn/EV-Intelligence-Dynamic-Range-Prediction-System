# Interview Questions & Answers

STEP 12G — 30 questions with concise, technically accurate answers based
entirely on this project. Read `docs/model_card.md` and
`docs/step8_final_model_report.md` first for depth.

---

### 1. Why ExtraTrees?

ExtraTreesRegressor (Randomized Trees) adds **extra randomization** at split
time (random feature + random threshold per candidate split), which reduces
variance relative to Random Forest at similar bias, especially on
noisy telemetry. It handled mixed feature types without scaling, captured
nonlinearities, and won on our trip-disjoint GroupKFold validation.
Ensembles also gave stable permutation-importance estimates.

### 2. Why not LSTM?

Our 102-feature set is mostly **tabular windowed statistics** (mean speed
over 1 km, elevation gain, SOC). A sequence model would add complexity and
training cost without clear benefit for this short-horizon regression; we
also had missing-telemetry gaps (Dacia) that a table-based imputation
handles more robustly. Feature engineering encoded the temporal structure
explicitly, keeping the model interpretable and memory-safe.

### 3. Why a 5 km horizon?

A 5 km window is long enough to represent a meaningful driving segment
(urban/suburban routes) and short enough to keep the SOC-derived target
accurate (`d_j - d_i >= 4.5 km`) with enough paired samples. It is the
target this dataset supports reliably; longer horizons would reduce valid
samples and increase noise.

### 4. Why an SOC-derived target?

No direct energy meter exists in DEVRT telemetry. Energy is derived from the
**battery state-of-charge change over a distance window**:
`(soc_i - soc_j) * capacity / 100 / (d_j - d_i)`. This is standard for
datasets without high-rate energy signals, but it inherits SOC-reporting
and fleet-capacity uncertainty (capacity is a 58 kWh fleet spec, DERIVED,
not per-vehicle BMS).

### 5. Why GroupKFold?

Samples from the same trip are **not independent**: the 5 km forward target
creates overlapping windows between adjacent samples. GroupKFold grouped by
`trip_id` keeps whole trips together so no trip leaks across folds — a
correct proxy for the held-out trip-level test.

### 6. What is target leakage?

Any information from the prediction window (or the true outcome) that enters
the features at training time, making metrics look better than real-world
performance. Here it would mean feeding future telemetry or the target
itself into the features.

### 7. Why was `trip_phase` removed?

`trip_phase` describes where a sample sits within its trip (start/middle/
end). Its denominator is the **observed total trip distance, known only after
the trip ends** — so at inference time you could not know it. The causal
audit classified it TRIP_END_LEAKAGE and it was removed from both reduced
feature sets.

### 8. Why are the `next_5km` features "conditionally causal"?

They read elevation rows **ahead** of the current position. They are
conditionally causal because road elevation is **static geography** — it is
knowable before you drive there (from a DEM or route plan), so it is not
temporal leakage. They are valid **only if** the system actually has that
route/DEM information.

### 9. Why are they not valid for strict onboard prediction?

Strict onboard prediction has access only to the vehicle's own current/past
signals. Without a planned route or DEM, the system cannot know the upcoming
terrain, so the 15 `next_*` features cannot be computed. The strict onboard
set (87 features) is the honest lower bound: GroupKFold MAE ~0.05518 vs
0.04002 kWh/km for the route-aware set.

### 10. Why did look-ahead terrain improve performance?

Terrain explains a large share of consumption variance (uphill vs downhill,
gradient). Elevation is also **highly predictive and stable** (corr 0.996
across trips of the same route). Adding `next_5km_uphill_frac`,
`next_5km_gradient_pct`, `next_5km_net_elev_m` gave the model the strongest
single source of signal (MAE 0.055 → 0.040).

### 11. Why does impurity importance overestimate terrain?

Impurity-based importance biases toward high-cardinality/continuous features
and correlated splits; terrain features can look more important than they
are because they interact with correlated features (altitude, gradient).
We report **permutation importance** for this reason.

### 12. Why use permutation importance?

Permutation importance measures the **drop in MAE when a feature is
shuffled** under GroupKFold on train+val — a more honest, model-agnostic
estimate of predictive contribution than impurity importance, and robust to
our correlated feature groups.

### 13. Why was SHAP skipped?

`shap` was not installed, and its dependency chain was heavy for this
environment. Permutation importance plus local sample explanations achieved
the explainability goal without it. (Noted in
`reports/step9_shap_status.json`.)

### 14. Why was TUM external validation blocked?

TUM lacks 72/102 frozen-model features: 41 require GPS/altitude route
terrain, 19 require traction-motor signals, 12 require per-timestamp
trip/distance boundaries; the 5 km future target is also unavailable.
Only 30/102 features were reproducible, and we **refuse to fabricate**
signals, so the validation was marked BLOCKED — an honest limitation, not
a success.

### 15. How was memory usage controlled?

Training/data: process **one trip at a time** with streaming aggregation and
PyArrow row-group reads (never whole-dataset copies). Inference: load only
the frozen model + imputer + feature list (~198 MB RSS measured, < 500 MB
budget). See `reports/step10_memory_report.json`,
`reports/step11_memory_report.json`.

### 16. Why Parquet?

Columnar, compressed, typed, schema-enforced, and **memory-mappable** — ideal
for wide telemetry (hundreds of columns × millions of rows) without loading
everything into RAM. Also cross-language (Python/PyArrow/Spark).

### 17. Why PyArrow?

PyArrow gives zero-copy columnar reads, row-group-level streaming for the
98M-row TUM dataset, and native parquet support with strong typing — the
memory-safe backbone of both the TUM extractor and the standardized
interim/processed data.

### 18. Why process one trip at a time?

Trips are the natural independent unit: windowed features and the 5 km target
are computed within a trip, and trips must stay intact for honest splits.
Processing per-trip bounds memory and makes feature/target logic explicit.

### 19. Why not merge all datasets?

DEVRT is the only dataset with all required signals and target support. JAC
lacked SOC confidence, and TUM lacks the route/terrain and motor features
needed (validation blocked). Merging incompatible sources would force
fabricated imputation and weaken the causal story — we kept them separate.

### 20. How was missing telemetry handled?

Missing optional signals (mainly Dacia speed/powertrain gaps) are imputed
with the **median fitted on TRAIN+VALIDATION only** — no test information
enters imputation. Critical features (SOC, altitude, route-aware `next_*`)
are required and never NaN at inference.

### 21. Why wasn't Dacia missing telemetry zero-filled?

Zero is a **meaningful value** (0 speed, 0 power); filling with zero would
bias the model and encode a false "off" state. Median imputation preserves
central tendency, and fitting it on train+val only avoids leakage.

### 22. What does MAE mean here?

Mean Absolute Error between predicted and actual average energy consumption,
in kWh/km: on the held-out test, predictions are off by **0.04112 kWh/km on
average** (~41 Wh per kilometer of driving).

### 23. What does 0.04112 kWh/km mean?

Over a 100 km drive this corresponds to ~4.1 kWh of error in total energy;
for a 40 kWh usable pack that is roughly 10% of usable energy. It is an
average absolute error, so typical trips do much better while extreme ones
(max abs error 0.154) do worse.

### 24. How is predicted consumption converted to range?

`usable_energy_kwh = capacity * max(soc - reserve, 0) / 100`, then
`range_km = usable_energy_kwh / predicted_kwh_per_km`. A default 10% SOC
reserve protects the buffer; an optional q10/q90 band gives conservative and
optimistic ranges. Zero/negative consumption (net regen) yields 0 range.

### 25. Why is MAPE not used?

MAPE is undefined/inflated when targets are near zero, and our target has
**3% of values near zero** plus genuine negatives from regenerative braking.
MAE is scale-consistent (kWh/km) and robust, so it is the headline metric.

### 26. What are the biggest limitations?

1) DEVRT-only training (two vehicles, one region); 2) route-aware features
need upcoming terrain — strict onboard MAE degrades to ~0.055; 3) TUM
external validation blocked (30/102 features); 4) SOC-derived target with
DERIVED 58 kWh fleet capacity; 5) short 5 km horizon; 6) no weather/traffic;
7) Nissan (0.051) weaker than Dacia (0.036); 8) prototype, not OEM-certified.

### 27. How would you improve the model with more data?

Add more vehicles/regions/weather, re-derive per-vehicle battery capacity,
extend horizons with hierarchical models (5/10/20 km), add traffic and
weather inputs, and re-run the causal audit + trip-disjoint split. More trips
would also let a sequence model (LSTM/Transformer) become viable.

### 28. How would you deploy this in a vehicle?

Connect a real DEM/GPS `RouteTerrainProvider` for the `next_*` features,
feed the onboard CAN/bus telemetry to `/predict`, and consume the
range estimate on the HUD. The service already validates inputs, refuses
fabricated terrain, keeps memory ~198 MB, and ships via Docker; a real
deployment adds edge compute, rate limits, and on-vehicle calibration.

### 29. What happens when route information is unavailable?

The service refuses fabricated terrain; the model can only be used with the
**strict onboard feature set** (87 features), which we evaluated as a
separate frozen artifact — MAE ~0.05518 kWh/km in GroupKFold. Honest
behavior: degrade capability, never invent route data.

### 30. How would you validate on a completely new EV?

Collect telemetry with the required signals (GPS/altitude, motor, distance),
run the same standardization and causal feature pipeline, evaluate with a
trip-disjoint split, and compare MAE against our DEVRT baseline (0.04112).
Capacity must come from that vehicle's BMS/fleet spec, and the 5 km target
must be computable from its SOC + distance signals.

---

## Bonus: STAR-style summary for interviews

**Situation:** EV drivers face inaccurate, non-route-aware range estimates;
no per-trip energy model existed for the DEVRT telemetry.
**Task:** predict next-5 km energy consumption and convert it to a dynamic
range estimate, leak-free and reproducible.
**Action:** engineered 102 causal features (87 onboard + 15 route-aware),
ran a causal audit that removed `trip_phase`, used trip-disjoint
GroupKFold + a one-time protected held-out test, tuned to an ExtraTrees
model, added permutation-importance explainability and a range estimator,
then packaged it as a validated FastAPI service with Docker.
**Result:** held-out MAE 0.04112 kWh/km (+33.5% vs baseline), R² 0.5902,
138 passing tests, ~198 MB inference memory; TUM external validation
attempted and honestly reported as blocked.