# STEP 8B: Negative Target Analysis

## Overview

- Total samples: 9,952
- Negative targets: 187 (1.88%)
- Negative range: [-0.247994, -0.063121]

## Interpretation

- Negative targets are RARE (<2% of data) - likely edge case or measurement artifact
- Terrain 'DOWNHILL': Higher negative % - may favor downhill regeneration
- Negative targets are SUBSTANTIAL (mean < -0.05) - meaningful energy recovery

## Recommendations

1. REMOVE or FLAG negative samples - decide based on domain knowledge
2. Use robust loss functions (Huber, quantile) if keeping negatives
3. Recalculate baselines using full target distribution (including negatives)
4. Report negative target treatment transparently in final model comparison
