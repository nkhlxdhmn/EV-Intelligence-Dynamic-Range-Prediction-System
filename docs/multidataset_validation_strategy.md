# STEP 12A — Multi-Dataset Validation Strategy

## Goal
Design a scientifically defensible cross-dataset validation protocol for the frozen Step 8 ExtraTreesRegressor model (102 route-aware features, MAE=0.04112 kWh/km on DEVRT held-out test), without modifying the frozen model or fabricating unavailable features.

## Core Principle
The frozen Step 8 model was trained and validated on DEVRT only. External validation on TUM or JAC is currently blocked by structural data gaps. The validation strategy must make these gaps explicit rather than pretended.

## 1. Validation Path Selection

### PATH A: TUM with sufficient features
- **Status**: BLOCKED
- **Reason**: TUM provides only 30/102 features directly; 41 need GPS/altitude terrain, 19 need traction-motor signals, 12 need per-timestamp distance
- **Additional data required**: GPS/altitude terrain + per-timestamp travelled_distance

### PATH B: Cross-dataset protocol WITHOUT frozen-model pretension
- **Status**: RECOMMENDED
- **Description**: A separate validation framework that documents feature compatibility gaps across datasets, without claiming to validate the frozen model
- **Purpose**: Feature-compatibility analysis, future data acquisition planning, signal-verification prioritization
- **Claim**: "Cross-dataset feature compatibility study, not frozen-model validation"

### PATH C: JAC target investigation
- **Status**: BLOCKED
- **Reason**: SOC unavailable, VOL unverified, CUR unavailable — cannot construct reliable energy target

### PATH D: Combined protocol
- **Status**: RECOMMENDED
- **Description**: PATH B + JAC feature verification pipeline + minimum data acquisition checklist
- **Output**: Documentation of gaps, not model evaluation

## 2. Cross-Dataset Validation Protocol (PATH B)

### Objective
Investigate feature signal availability and compatibility across datasets, NOT to evaluate the frozen Step 8 model. Any model evaluation claiming to use TUM/JAC data for frozen-model validation is scientifically unjustified.

### Protocol Steps

1. **Schema validation**: Use `src/data/unified_schema.py` to classify each feature across datasets (direct/derived/conditional/unavailable/unverified)

2. **Feature compatibility matrix**: Consult `reports/multidataset_feature_compatibility.csv` for per-feature per-dataset availability

3. **Target feasibility**: Consult `reports/tum_target_feasibility.json` and `reports/jac_target_feasibility.json`

4. **Compatibility assessment**: Document which features are directly comparable vs. which require dataset-specific handling

5. **Gap identification**: Explicitly list missing features per dataset (GPS/altitude, per-timestamp distance, verified SOC/VOL/CUR)

6. **Minimum data checklist**: For each dataset, list the minimum additional data required to enable frozen-model-compatible evaluation

### Expected Outcome
- `reports/multiev_validation_matrix.csv` showing dataset compatibility at a high level
- `docs/multidataset_validation_strategy.md` documenting the protocol and conclusions
- No claim of frozen-model validation on TUM/JAC data
- Clear identification of minimum data requirements for future external validation

## 3. Dataset-Specific Limitations

### DEVRT
- ✅ All 102 features available
- ✅ Target construction possible (5-km ahead energy consumption)
- ✅ Held-out test evaluation: MAE=0.04112 kWh/km
- **Role**: Training/validation dataset only; does not need external validation again

### TUM EV UDS (~96M rows)
- ❌ Only 30/102 features directly reproducible
- ❌ 41 features need GPS/altitude route terrain
- ❌ 19 features need traction-motor signals (not in data)
- ❌ 12 features need per-timestamp travelled_distance
- ❌ 5-km energy target cannot be constructed without GPS/altitude and distance
- **Role**: Feature-compatibility investigation only; target construction blocked

### JAC IEV40
- ❌ SOC unavailable
- ❌ VOL (battery voltage) unverified — raw ADC reading
- ❌ CUR (traction current) unverified — raw signal, physical meaning not established
- ❌ AIR (air status flag) ≠ temperature
- ❌ Cannot construct reliable energy consumption target
- **Role**: Signal-verification and future data acquisition priority; model evaluation blocked

## 4. Minimum Additional Data Requirements

### For TUM external validation:
| Required Data Type | Purpose | Priority |
|---|---|---|
| GPS/altitude terrain (route DEM) | Compute route-aware next_* features | CRITICAL |
| Per-timestamp travelled_distance | Demarcate 5-km windows for target | CRITICAL |
| Traction battery current (A) | Compute power, energy consumption | HIGH |
| Traction battery power (kW) | Compute energy consumption | HIGH |
| Verified SOC trajectory | Energy reference for target computation | HIGH |

### For JAC external validation:
| Required Data Type | Purpose | Priority |
|---|---|---|
| Verified SOC (%) | Energy reference for consumption calculation | CRITICAL |
| Verified battery voltage (V) | Power/energy calculations | CRITICAL |
| Verified traction current (A) | Power calculations | CRITICAL |
| Confirmation AIR≠temperature | Semantic disambiguation | MEDIUM |
| Additional signal metadata | Establish VOL/CUR physical meaning | HIGH |

## 5. Path B Summary (Recommended)

The recommended PATH B takes the following approach:

1. **Do not claim** that TUM or JAC data validates the frozen Step 8 model. The feature gaps are too large (72/102 features unavailable in TUM; SOC/VOL/CUR unverified in JAC).

2. **Document** the feature compatibility gaps systematically via `reports/multidataset_feature_compatibility.csv`.

3. **Investigate** target feasibility honestly — TUM target construction is BLOCKED (missing GPS/altitude and distance); JAC target construction is BLOCKED (unverified SOC/VOL/CUR).

4. **Create** a cross-dataset validation protocol that serves as a feature-compatibility study and data-acquisition priority list, NOT as model validation.

5. **Preserve** the frozen Step 8 model unchanged (hash verified: `27a0b7ab8a7fd5bc42ba2ac04d73be772880cdf2a64897108e343a57c6841319`).

6. **Identify** minimum additional data required for future external validation (see Section 4).

### PATH B Outcome
- Cross-dataset feature compatibility documented (no model evaluation claimed)
- Minimum data requirements identified for future external validation
- Frozen Step 8 model preserved unchanged
- Scientifically defensible protocol (no fabrication, no unreliable target construction)
- Ready for future data collection to enable external validation

## 6. Files Created or Updated

- `reports/multidataset_feature_compatibility.csv` — per-concept compatibility across datasets
- `reports/tum_target_feasibility.json` — TUM target feasibility (BLOCKED explanation)
- `reports/jac_target_feasibility.json` — JAC target feasibility (BLOCKED explanation)
- `reports/multiev_validation_matrix.csv` — high-level dataset compatibility matrix
- `docs/multidataset_feature_strategy.md` — detailed feature compatibility strategy
- `docs/multidataset_validation_strategy.md` — this validation strategy overview

## 7. Test Integrity

- Existing test suite unchanged: 138 tests run with `python -m pytest -q`
- Do **not** modify `tests/test_unified_schema.py` to import-related failures
- Do **not** remove or modify the `reports/.step8_test_evaluated` marker
- Do **not** re-evaluate DEVRT test (already evaluated in Step 8)
- Do **not** train or evaluate a new model based on TUM/JAC data

## 8. Stop Condition

**STOP — STEP 12A Complete.**

Do NOT continue to Step 12B.
Do NOT train a new model.
Do NOT tune the frozen model.
Do NOT evaluate DEVRT test again.
Do NOT fabricate data.

The frozen Step 8 model remains valid for DEVRT only. External validation on TUM/JAC is blocked by structural data gaps, not by model hyperparameters or tuning. The recommended PATH B documents these gaps and identifies minimum data requirements for future investigation.