# Step 9J: Negative Target Model Analysis

## Purpose

Evaluate how well the A_BASIC + XGBoost model handles samples with **negative targets**
(net regenerative energy recovery over the future 5 km horizon).

Negative targets indicate that, over the prediction horizon, the vehicle recovered more
energy through regeneration than it consumed — a distinctly different regime from normal
driving.

## Results (Validation)

| Metric | Negative Targets | Non-Negative Targets |
|--------|------------------|----------------------|
| Sample count | 53 | 1,582 |
| MAE (kWh/km) | 0.0756 | 0.0625 |
| RMSE (kWh/km) | 0.1084 | 0.0877 |
| Mean signed error | +0.0651 | +0.0010 |
| R² (vs subset mean) | — | -0.016 |

## Key Finding: The Model Cannot Predict Regeneration

- **Mean signed error for negative targets is +0.0651 kWh/km** — the model systematically
  **overpredicts** energy consumption (predicts higher than the negative target).
- This means the model essentially **never predicts a negative target**; it always
  predicts positive consumption.
- The model has **not learned** to recognize regenerative energy recovery cases.

## Why This Happens

1. **Only 53 of 1,635 validation samples (3.2%) have negative targets** — an extreme
   class imbalance that tree models are unlikely to learn from.
2. The A_BASIC feature set contains **no regeneration-related features**:
   - No regen power
   - No speed (to estimate kinetic energy recovery potential)
   - No acceleration (to detect braking events)
3. The negative-target cases are concentrated in **downhill driving**, where elevation
   loss creates the recovery opportunity. Terrain is captured, but the model's smooth
   gradient features may not adequately signal the magnitude of recovery potential.

## Breakdown of Negative Targets

### By Terrain

| Terrain | Count | MAE | Mean Error |
|---------|-------|-----|------------|
| DOWNHILL | 20 (38%) | — | — |
| FLAT | 29 (55%) | — | — |
| UPHILL | 4 (8%) | — | — |

Note: negative targets are NOT exclusively downhill — more than half occur on terrain
classified as FLAT. This suggests the terrain classification threshold may be too coarse
to capture the subtle elevation profiles that trigger net regeneration.

### By Vehicle

Negative targets occur only in **Nissan Leaf** validation samples (which have speed and
regen telemetry available). Dacia Spring samples have no negative targets in validation.

### By Speed (Nissan-only subset)

All negative-target samples belong to the Nissan subset where speed telemetry exists.
The model lacks speed/acceleration features in A_BASIC, so it cannot exploit the braking
signals that precede regeneration.

## Recommendation

- **Do NOT remove negative targets.** They represent a real and physically meaningful
  regime (downhill regeneration).
- **Consider predicting in two stages** (classification: will net energy be negative?
  + regression), OR
- **Add regeneration-related features** (regen_power_kw, mean_regen_power_*, regen_event
  features) to the model, and/or
- **Add speed and acceleration features** which signal braking events.
- **Consider a different target formulation** that separates consumption and recovery.

## Data Quality Note

The negative-target population is small (53 samples). Any conclusions about regeneration
learning must acknowledge the limited sample size and the fact that these samples are
entirely within the Nissan Leaf subset.

---

*Report generated as part of Step 9 (validation-side diagnosis). Test set not used.*