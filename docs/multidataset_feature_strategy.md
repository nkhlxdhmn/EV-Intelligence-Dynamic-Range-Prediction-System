# STEP 12A — Multidataset Feature Strategy

## Goal
Design a scientifically defensible feature compatibility framework across DEVRT, TUM EV UDS, and JAC IEV40 datasets, without fabricating unavailable features or forcing incompatible signals into the frozen 102-feature model.

The frozen Step 8 model (ExtraTreesRegressor, 102 route-aware features, MAE=0.04112 kWh/km on DEVRT held-out test) is **not** to be retrained or modified. This step only designs the compatibility framework and investigates external validation feasibility.

--------------------------------------------------
## 1.  Dataset-by-Dataset Feature Availability
--------------------------------------------------

### DEVRT (Training Dataset)
- **58 trips** from Dacia Spring and Nissan Leaf
- **All 102 frozen features** are directly observable
- Every feature has a verified meaning from the DEVRT data dictionary
- No features are "unavailable" or "unverified" in the DEVRT context
- **Conclusion**: DEVRT is the full-compatibility dataset; the frozen model was trained and evaluated here

### TUM EV UDS (~96M rows, CUP1-CUP5, ID1-ID2)
- **30/102 features** directly reproducible from TUM signals
- **41 features** require GPS/altitude route terrain (not available in TUM)
- **19 features** require traction-motor signals (not available in TUM)
- **12 features** require per-timestamp travelled-distance (unavailable in TUM)
- **Available features** include: SOC, speed, battery voltage, ambient temperature, basic battery info
- **Cannot evaluate**: TUM cannot provide the 5-km ahead energy consumption target without GPS/altitude terrain and per-timestamp distance
- **Conclusion**: TUM cannot support the frozen 102-feature model directly; only a reduced feature set is possible

### JAC IEV40
- SOC **unavailable** (no SOC field in the dataset)
- VOL (battery voltage) **unverified** — raw ADC reading, not verified as battery voltage
- CUR (traction current) **unverified** — raw signal, physical meaning not established
- AIR (air status flag) is **not** temperature
- No reliable energy target can be constructed from unverified signals
- ODOmeter available, speed available, GPS available, altitude available
- **Conclusion**: JAC features are largely incompatible with the frozen 102-feature model without signal verification

--------------------------------------------------
## 2.  Compatibility Classifications
--------------------------------------------------

Each feature is classified into one of five categories:

| Classification | Meaning |
|---|---|
| **direct** | Signal directly available and semantically verified in the dataset |
| **derived** | Mathematically derivable from direct signals |
| **conditional** | Available only when supplementary data (e.g., route DEM) is provided |
| **unavailable** | Cannot be reconstructed reliably from dataset signals |
| **unverified** | Raw signal exists but physical meaning is not sufficiently established |

### DEVRT Mappings (excerpt)
| Feature | Classification | Source Column | Unit | Confidence |
|---|---|---|---|---|
| speed_kmh | direct | speed | km/h | HIGH |
| soc_pct | direct | soc_pct | % | HIGH |
| battery_capacity_kwh | direct | battery_capacity_kwh | kWh | HIGH |
| next_5km_uphill_frac | conditional | next_5km_uphill_frac | frac | HIGH |
| altitude_m | unavailable | N/A | — | — |
| battery_current_a | verified | battery_current_a | A | HIGH |

### TUM Mappings (excerpt)
| Feature | Classification | Source Column | Unit | Confidence |
|---|---|---|---|---|
| speed_kmh | direct | value_id=4 | km/h | HIGH |
| soc_pct | direct | SOC field | % | HIGH |
| altitude_m | unavailable | N/A | — | — |
| battery_voltage_v | direct | value_id=13 | V | HIGH |
| battery_temperature_c | unverified | value_id‑14 | °C | LOW |
| travelled_distance_km | unavailable | N/A | — | — |

### JAC Mappings (excerpt)
| Feature | Classification | Source Column | Unit | Confidence |
|---|---|---|---|---|
| speed_kmh | direct | SPD | km/h | HIGH |
| battery_voltage_v | unverified | VOL | V? | LOW |
| soc_pct | unavailable | N/A | — | — |
| status_flag | unverified | AIR | bool | LOW |

--------------------------------------------------
## 3.  Common Feature Set Analysis
--------------------------------------------------

### Common Verified Features (intersection of DEVRT + TUM)
Only 30 features are directly available in both DEVRT and TUM:
- speed_kmh, soc_pct, battery_voltage_v, ambient_temperature_c
- Basic battery properties (battery_capacity_kwh, battery current where available)
- These can be used for a reduced/compatibility model but **do not include** the route-aware next_* features

### Dataset-Specific Features
- **DEVRT-only**: All 102 route-aware features (next_*_gradient_pct, elevation_gain_*, terrain_class, etc.)
- **TUM-only**: Features relying on GPS/altitude that are simply unavailable
- **JAC-only**: Features relying on unverified signals (VOL, CUR) or missing SOC

### Unavailable Features
Features that cannot be reconstructed from TUM/JAC signals:
- Any feature requiring GPS coordinates (latitude, longitude)
- Any feature requiring altitude measurements from TUM
- Any feature requiring traction battery current (TUM, JAC)
- Any feature requiring per-timestamp travelled distance (TUM: 12 features)
- Any feature requiring traction battery power (TUM: 19 features)

--------------------------------------------------
## 4.  TUM Target Feasibility Investigation
--------------------------------------------------

### The Core Problem
The frozen model predicts `target_future_energy_kwh_per_km` over the next 5 km.
TUM provides:
- ✅ SOC, speed, battery voltage, ambient temperature
- ❌ GPS/altitude (unavailable)
- ❌ per-timestamp travelled_distance (unavailable)
- ❌ traction battery current/power (unavailable)

### Investigation — PyArrow Only (no pandas, no full-load loading)

Using PyArrow `ParquetFile` metadata inspection and row-group iteration:

1. **Timestamp/value relationships**: TUM uses `(value_id, value)` pairs. The `value_id` encodes the signal type. Validation of timestamp formats shows reconstruction of `travelled_distance` is **not** possible from the available `value_id`/`value` pairs alone.

2. **SOC samples**: SOC is available in TUM, but without per-timestamp distance, the 5-km energy consumption target cannot be properly computed. SOC change alone does not account for distance travelled.

3. **Target derivation attempt**: 
   - The DEVRT target is `target_future_energy_kwh_per_km` over a 5 km window
   - TUM lacks: GPS, altitude, and per-timestamp distance
   - Without distance, the 5-km window cannot be reliably demarcated
   - Without altitude, gradient features (next_*_gradient_pct, etc.) cannot be computed

### Conclusion: TUM TARGET STATUS = BLOCKED
**Reason**: The 5-km ahead energy consumption target requires (a) GPS/altitude for route-aware features and (b) per-timestamp travelled distance for the 5 km window. Neither is available in TUM. Without these, any target constructed would be based on unreliable assumptions and cannot be scientifically defended.

**Conclusion**: TUM cannot serve as an external validation dataset for the frozen 102-feature model in its current form. The limitation is structural (missing signals), not a matter of model tuning.

--------------------------------------------------
## 5.  JAC Target Feasibility Investigation
--------------------------------------------------

### Signal Verification Status
- **SOC**: Unavailable — no SOC field in JAC dataset
- **VOL (battery voltage)**: Unverified — raw ADC reading; not verified as battery voltage
- **CUR (traction current)**: Unverified — raw signal; physical meaning not established
- **AIR (air status flag)**: Not temperature; a status flag only
- **Available**: speed_kmh, GPS, altitude, odometer

### Target Feasibility
Since the three key signals (SOC, VOL, CUR) are either unavailable or unverified, **no scientifically defensible energy target can be derived from JAC signals alone**.

**JAC TARGET STATUS**: BLOCKED
**Reason**: The three fundamental signals required for energy consumption calculation (SOC, voltage, current) are either unavailable or unverified. Without these, any target construction would rely on unverified assumptions.

--------------------------------------------------
## 6.  Multi-EV Validation Matrix
--------------------------------------------------

| Vehicle | Dataset | Target Available | Core Features Available | Terrain Available | Energy Target Confidence | Frozen Model Compatible | Valid External Evaluation |
|---|---|---|---|---|---|---|---|
| Dacia Spring | DEVRT | ✅ (DEVRT test) | 102 features | ✅ route-aware | HIGH | ✅ (frozen model) | ✅ (held-out test) |
| Nissan Leaf | DEVRT | ✅ (DEVRT test) | 102 features | ✅ route-aware | HIGH | ✅ (frozen model) | ✅ (held-out test) |
| VW ID.3 | TUM | ❌ BLOCKED | 30/102 features | ❌ GPS/altitude unavailable | BLOCKED | ❌ | ❌ |
| CUPRA Born | TUM | ❌ BLOCKED | 30/102 features | ❌ GPS/altitude unavailable | BLOCKED | ❌ | ❌ |
| JAC IEV40 | JAC | ❌ BLOCKED | limited (speed, voltage odometer) | ⚠️ unverified signals | BLOCKED | ❌ | ❌ |

--------------------------------------------------
## 7.  Decision Path
--------------------------------------------------

### PATH A: TUM target + sufficient features available
→ Prepare an external validation dataset (not possible with current data)

### PATH B: TUM target unavailable
→ Build a separate cross-dataset validation protocol **without** pretending it is validation of the frozen model. Document the feature gaps explicitly.

### PATH C: JAC target unavailable
→ Keep JAC as feature compatibility / future data acquisition only. Do not train or evaluate on JAC.

### PATH D: Both external targets unavailable
→ Explicitly document that the limitation cannot currently be fixed from the downloaded datasets and identify the minimum additional data required:
  - TUM: GPS/altitude terrain + per-timestamp distance
  - JAC: Verified SOC, verified VOL, verified CUR

--------------------------------------------------
## 8.  Final Recommendation
--------------------------------------------------

**Do not train or evaluate a new model based on TUM or JAC data.**

The scientifically correct path is:

1. **Preserve the frozen Step 8 model** (MAE=0.04112 kWh/km on DEVRT held-out test)
2. **Document the feature compatibility matrix** (created in `reports/multidataset_feature_compatibility.csv`)
3. **Investigate TUM/TUM target feasibility** (concluded: BLOCKED — missing GPS/altitude and per-timestamp distance)
4. **Investigate JAC target feasibility** (concluded: BLOCKED — unverified SOC, VOL, CUR)
5. **Investigate a cross-dataset validation protocol** that does not claim validation of the frozen model, but documents feature compatibility gaps
6. **Identify minimum additional data required**:
   - TUM: GPS/altitude terrain + per-timestamp distance measurements
   - JAC: Verified SOC, verified VOL, verified traction current

The frozen model remains valid for DEVRT only. External validation on TUM/JAC is not currently possible without additional data collection.

--------------------------------------------------
## 9.  Files Created
--------------------------------------------------

- `reports/multidataset_feature_compatibility.csv` — per-concept compatibility across datasets
- `docs/multidataset_feature_strategy.md` — this strategy document
- `reports/tum_target_feasibility.json` — TUM target feasibility report
- `reports/jac_target_feasibility.json` — JAC target feasibility report
- `reports/multiev_validation_matrix.csv` — multi-EV validation matrix
- `docs/multidataset_validation_strategy.md` — strategy overview

--------------------------------------------------
## 10.  Test Suite
--------------------------------------------------

Run: `python -m pytest -q`
**Expected**: 138 passed (existing suite unchanged)

Do **not** remove existing tests.  Do **not** modify the DEVRT test-evaluated marker.

--------------------------------------------------
STOP AFTER STEP 12A.

Do NOT continue to Step 12B.

Do NOT train a new model.

Do NOT tune the frozen model.

Do NOT evaluate DEVRT test again.

Do NOT fabricate data.

STOP.