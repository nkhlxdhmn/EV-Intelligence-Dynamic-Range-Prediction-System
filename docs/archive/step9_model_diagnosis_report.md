# Step 9: Model Diagnosis Report

## Executive Summary

The frozen A_BASIC + XGBoost model **beats the baseline on validation** (MAE 0.063 vs
0.072, ~13% better) but **fails to generalize to the test set** (MAE 0.064 vs baseline
0.057, ~12% worse). The ML model's validation advantage does not survive contact with
the held-out test trips. This report explains why, based on evidence.

**This is an honest negative result.** The model is not currently suitable as a range
estimator. The diagnosis identifies the structural causes and what Step 10 should change.

---

## 1. Why Did ML Fail to Beat the Baseline?

**Evidence-based answer:** It did beat the baseline on validation but lost on test. The
reversal is explained by **trip-level distribution shift between splits**, not by a
defect in any single model.

Supporting evidence:

- **Validation:** XGBoost MAE 0.063 vs global-mean baseline 0.072 (XGBoost ~13% better),
  R² = 0.254.
- **Test:** XGBoost MAE 0.064 vs global-mean baseline 0.057 (XGBoost ~12% worse),
  R² = -0.264.
- The test set has a different composition: 65% Dacia (vs 47% in validation), target
  std 0.072 (vs 0.102 in validation), and **zero negative targets** (vs 53 in validation).
- The test set's lower target variance makes the constant-mean baseline unusually strong:
  a model must predict well on a narrower distribution to beat the mean, and the frozen
  model overfitted the broader validation distribution.

## 2. Is the Problem Feature Quality?

**Partially.** The A_BASIC features (battery + terrain) are 100% complete and show
meaningful predictive signal on validation (R² 0.254). Feature importance is dominated
by terrain (gradient, altitude), which is physically sensible.

However, the feature set **omits the signals most relevant to the target**:
- Regeneration features (regen power) — absent from A_BASIC, and structurally missing
  for Dacia.
- Speed and acceleration — absent from A_BASIC, and structurally missing for Dacia.
- These features could help distinguish the driving regimes that produce high/low
  consumption, but they cannot be used without either excluding Dacia or imputing.

## 3. Is the Problem Target Quality?

**Yes — substantially.** The target is derived from SOC differences (SOC reported in 1%
integer increments). At 62 kWh (Nissan), a ±1% SOC step is ~0.62 kWh; over the 5 km
horizon this is ~0.124 kWh/km of quantization error — of the same magnitude as the
target itself (typical values 0.10–0.25 kWh/km). This places a hard floor on achievable
MAE that no feature engineering can fully overcome.

Additionally, the 5 km forward horizon averages over varied terrain/driving, smoothing
the signal but also introducing noise when the future trip segment differs from the
current context that the features describe.

## 4. Is Missing Telemetry Responsible?

**Yes, in part — and it makes experiments B–E non-comparable to A_BASIC.**

- 43.7% of samples (train) have speed telemetry; the rest (Dacia) have none.
- Experiments B–E run only on the Nissan subpopulation (3,015 train samples), so their
  superior R² (0.32–0.39) reflects both extra features AND a different population.
- It is **not valid** to conclude from Step 8 that driving/powertrain/environment
  features are useless. They were never evaluated on a comparable population.
- The frozen A_BASIC model cannot exploit regeneration or braking signals at all.

## 5. Does Vehicle-Specific Behavior Matter?

**Yes, but it is secondary to trip-level variance.**

- Vehicle-mean baseline (0.072 validation / 0.057 test) is only ~1% better than the
  global mean, so simple per-vehicle constants add little.
- Validation per-vehicle R²: Nissan 0.324 (good), Dacia -0.263 (negative). The negative
  Dacia R² is driven by low target variance on Dacia samples; the model's predictions
  have more spread than the near-constant Dacia targets.
- On test, Dacia MAE (0.059) is better than Nissan MAE (0.074) — the model is less
  accurate on the vehicle with telemetry, which is counter-intuitive and suggests the
  A_BASIC features (especially battery capacity, which separates the two vehicles) do
  not fully capture the differences.

## 6. Does Terrain Matter?

**Yes — terrain is the dominant signal.**

- Terrain group accounts for 63% (XGB) / 73% (RF) of feature importance.
- Validation R² by terrain: DOWNHILL 0.421, FLAT 0.208, UPHILL 0.198.
- The model captures terrain-driven consumption reasonably on validation but **fails on
  test terrain segments** (test R²: DOWNHILL -0.63, FLAT -0.33, UPHILL -0.99). The
  negative test R² on every terrain class again reflects test distribution shift more
  than terrain per se.

## 7. Does Regenerative Braking Matter?

**Yes, and the model ignores it.**

- 53 validation samples (3.2%) have negative targets (net recovery).
- The model systematically overpredicts them (MAE 0.076, mean signed error +0.065) —
  it never predicts a negative value.
- Regeneration features exist in the v2 dataset (regen_power_kw, regen_energy_*,
  regen_event_*) but are Nissan-only and were excluded from A_BASIC.
- The test set contains **no negative targets**, so the test evaluation does not
  exercise the regeneration regime at all.

## 8. Which Features Are Most Predictive?

Top features by XGBoost gain (predictive importance, NOT causality):

| Rank | Feature | XGB importance | RF importance |
|------|---------|----------------|---------------|
| 1 | past_1km_gradient_pct | 0.196 | 0.159 |
| 2 | current_altitude_m | 0.192 | 0.366 |
| 3 | battery_capacity_kwh | 0.143 | 0.014 |
| 4 | current_soh_pct | 0.125 | 0.055 |
| 5 | current_soc_pct | 0.103 | 0.200 |
| 6 | elevation_gain_1km | 0.092 | 0.079 |
| 7 | elevation_loss_1km | 0.089 | 0.112 |
| 8 | current_gradient_pct | 0.033 | 0.013 |
| 9 | terrain_class | 0.027 | 0.001 |

Group importance: Terrain 63% (XGB) / 73% (RF); Battery 37% / 27%.

## 9. Where Does the Model Fail?

- **Regenerative/low-consumption cases:** negative targets (MAE 0.076, systematic
  overprediction) and 0–0.05 kWh/km targets (MAE 0.109 on validation, 0.124 on test).
- **High-consumption cases:** >0.30 kWh/km targets have MAE 0.222 on validation and
  0.166 on test (systematic underprediction).
- **Trip 20230418_NISSAN_ANDOAIN_AZPEITIA_015** (validation): worst trip, MAE 0.112,
  24% negative targets, target std 0.214 — the trip with the most regeneration.
- **Low-SOC validation range:** SOC 60–80% has higher MAE (0.055) than 80–100% (0.070);
  on test the order flips (60–80: 0.075 vs 80–100: 0.054), again showing split instability.
- **Low-speed segments** (0–20, 20–40 km/h) show the largest errors on both splits.

## 10. Does the Model Generalize to Unseen Trips?

**No.** The test trips are unseen, and the model's validation performance (MAE 0.063,
R² 0.254) degrades to test MAE 0.064, R² -0.264. On 5 of 6 test trips the model has
negative R². The model does not generalize across trip distributions.

The fundamental issue: **50 trips is far too few for reliable ML.** Trip-level
differences dominate; the model memorizes validation-trip structure rather than
learning transferable consumption dynamics.

## 11. What Should Step 10 Improve?

Priority order:

1. **Reconsider the target.** SOC-quantization noise (~0.124 kWh/km at Nissan capacity)
   is comparable to the target magnitude. Options:
   - Longer horizon (10 km) to dilute quantization error.
   - Alternative energy sources (regen integration, cumulative distance-based) if any
     are reliable.
   - Two-stage modeling: first predict sign (regen vs consumption), then magnitude.
2. **Add regeneration and driving features** for the Nissan subpopulation — evaluate
   them on a comparable population (Nissan-only or speed-complete samples), not mixed.
3. **Consider per-vehicle models or at least per-vehicle feature handling**, since
   Dacia and Nissan have different available telemetry and different target behavior.
4. **Investigate SOC resolution**: confirm whether SOC is truly 1%-quantized and
   whether any higher-resolution state variable exists.
5. **Expand the dataset** — more trips are the single highest-leverage change. 50 trips
   cannot support robust ML.
6. **Use trip-aware evaluation** (leave-one-trip-out / grouped CV) for all model
   comparisons to reflect the actual generalization task.
7. **Report the baseline honestly in every comparison** — the mean baseline is a strong
   opponent given the target noise.

## Data Quality Limitations (recap)

- SOC 1% quantization → target noise floor.
- Dacia lacks speed/motor/regen/temperature telemetry (structural missingness).
- Timestamps: ~30% of raw DEVRT rows had parsing issues (mitigated during processing).
- Small number of independent trips; 4 days of data; 2 vehicle models; one region.

## Bottom Line

The ML model does not yet beat the simple baseline on the test set. The reasons are
structural (target noise from SOC quantization, small trip count, split distribution
shift, missing regeneration/telemetry) rather than a single fixable bug. **Step 10
should focus on target redesign and data expansion, not on squeezing the current
feature/model combination.**

---

*Generated as part of Step 9. Test set was used exactly once, with the frozen model.*