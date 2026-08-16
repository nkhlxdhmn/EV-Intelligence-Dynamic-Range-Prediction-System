"""Create Step 7.5 reports from the engineered DEVRT v2 matrix (no modelling)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import pandas as pd
import numpy as np
from scripts.comprehensive_feature_engineering import COMMON_FEATURES, OPTIONAL_NISSAN_FEATURES, AVAILABILITY_FLAGS, EXPERIMENT_GROUPS, TARGET
from src.evaluation.leakage_audit import run_full_audit

DATA=Path('data/processed/devrt_ml_features_v2.parquet')

def main():
    df=pd.read_parquet(DATA); Path('reports').mkdir(exist_ok=True); Path('docs').mkdir(exist_ok=True)
    records=[]
    for c in df.columns:
        s=df[c]; numeric=pd.api.types.is_numeric_dtype(s)
        records.append({'feature':c,'dtype':str(s.dtype),'unit':_unit(c),'source':_source(c),'missing_count':int(s.isna().sum()),'missing_percentage':round(s.isna().mean()*100,3),'min':s.min() if numeric else '', 'max':s.max() if numeric else '', 'mean':s.mean() if numeric else '', 'median':s.median() if numeric else '', 'std':s.std() if numeric else ''})
    quality=pd.DataFrame(records); quality.to_csv('data/processed/feature_quality_report.csv',index=False)
    numeric=df.select_dtypes(include='number').drop(columns=['vehicle_id'],errors='ignore')
    pearson=numeric.corr(method='pearson')[TARGET].drop(TARGET).sort_values(key=lambda x:x.abs(),ascending=False)
    spearman=numeric.corr(method='spearman')[TARGET].drop(TARGET).sort_values(key=lambda x:x.abs(),ascending=False)
    cols=numeric.drop(columns=[TARGET]).columns; corr=numeric[cols].corr(); mask=np.triu(np.ones(corr.shape,dtype=bool),1)
    pairs=corr.where(mask).stack().reset_index(); pairs.columns=['feature_a','feature_b','pearson_correlation']; pairs=pairs[pairs.pearson_correlation.abs()>=.95].sort_values('pearson_correlation',key=lambda s:s.abs(),ascending=False)
    pairs.to_csv('data/processed/high_correlation_features.csv',index=False)
    violations=run_full_audit(str(DATA))
    Path('reports/feature_target_analysis.md').write_text('# Feature-Target Analysis\n\nNo features were removed based on these associations.\n\n## Pearson correlation\n\n'+_markdown_series(pearson)+'\n\n## Spearman correlation\n\n'+_markdown_series(spearman)+'\n\n## Leakage audit\n\n'+('PASS: no forbidden feature names or |Pearson r| > 0.99 feature-target relationships.' if not violations else '\n'.join('- '+v for v in violations))+'\n',encoding='utf-8')
    miss=[]
    for c in COMMON_FEATURES+OPTIONAL_NISSAN_FEATURES+AVAILABILITY_FLAGS:
        if c in df:
            by_vehicle=df.groupby('vehicle_model')[c].apply(lambda s: round(s.isna().mean()*100,1)).to_dict()
            structural='Yes: Dacia has no verified telemetry signal.' if c in OPTIONAL_NISSAN_FEATURES else 'No for the common feature definition.'
            miss.append(f'| `{c}` | {quality.loc[quality.feature.eq(c),"missing_percentage"].iloc[0]}% | {by_vehicle} | {structural} | Keep null; use an availability flag where supplied. |')
    Path('reports/missing_feature_analysis.md').write_text('# Missing-Feature Analysis\n\nOptional Nissan telemetry is structurally unavailable for Dacia and is never zero-imputed. Timestamp-derived and power-integration features are null where timestamps are missing or intervals are invalid.\n\n| Feature | Overall missing | Missing by vehicle | Structural? | Treatment |\n|---|---:|---|---|---|\n'+'\n'.join(miss)+'\n',encoding='utf-8')
    matrix=['# Feature Availability Matrix','','| Feature family | DEVRT Dacia | DEVRT Nissan | JAC | TUM | Status |','|---|---|---|---|---|---|','| Battery SOC/SOH, capacity | yes | yes | CONDITIONAL | NOT_VERIFIED | RELIABLE for DEVRT |','| GPS altitude and derived terrain | yes | yes | CONDITIONAL | NOT_VERIFIED | RELIABLE for DEVRT |','| Speed, acceleration | UNAVAILABLE | yes | CONDITIONAL | NOT_VERIFIED | CONDITIONAL |','| Motor, torque, RPM | UNAVAILABLE | yes | NOT_VERIFIED | NOT_VERIFIED | CONDITIONAL |','| Auxiliary power | UNAVAILABLE | yes | NOT_VERIFIED | NOT_VERIFIED | CONDITIONAL |','| Regenerative power | UNAVAILABLE | yes | NOT_VERIFIED | NOT_VERIFIED | CONDITIONAL |','| Temperature | UNAVAILABLE | yes | CONDITIONAL | NOT_VERIFIED | CONDITIONAL |','| Wind components | UNAVAILABLE | UNAVAILABLE | NOT_VERIFIED | NOT_VERIFIED | UNAVAILABLE (no verified heading) |']
    Path('docs/feature_availability_matrix.md').write_text('\n'.join(matrix)+'\n',encoding='utf-8')
    groups='\n'.join(f'- `{n}`: {len(v)} candidate features' for n,v in EXPERIMENT_GROUPS.items())
    Path('docs/comprehensive_feature_engineering.md').write_text(f'''# Comprehensive EV Feature Engineering\n\nThe v2 DEVRT matrix has {len(df):,} samples and {len(df.columns)-1} predictor/metadata columns plus the future target. It is produced one standardized trip at a time with PyArrow output and explicit garbage collection.\n\n## Causality\n\nAll distance windows are trailing windows ending at the current observation. No centered rolling windows, end-of-trip fields, remaining-distance fields, or future signals are present. The 5 km target preserves the established Step 6 construction order.\n\n## Definitions\n\n- Terrain is FLAT for absolute 100 m gradient at or below 1%; otherwise UPHILL or DOWNHILL.\n- Hillyness is 1 km gradient standard deviation multiplied by one plus the number of non-flat gradient direction changes.\n- Hard acceleration/braking thresholds are +2.0 / -2.0 m/s2.\n- Regeneration recovery integrates negative regenerative power over valid 0-120 second intervals.\n- Temperature deviation is relative to 20 C.\n\n## Feature groups\n\n- COMMON: {len(COMMON_FEATURES)} terrain, battery, and trip-context features.\n- OPTIONAL_NISSAN: {len(OPTIONAL_NISSAN_FEATURES)} verified telemetry-derived features, structurally null for Dacia.\n- Availability flags: {', '.join(AVAILABILITY_FLAGS)}.\n\n## Future ablations\n\n{groups}\n\nWind is retained as unavailable: direction alone cannot produce headwind components without verified vehicle heading. JAC is compatibility-only and TUM remains external validation; neither is merged into DEVRT.\n''',encoding='utf-8')
    print(f'quality={len(quality)} high_pairs={len(pairs)} leakage_violations={len(violations)}')

def _unit(c):
    if 'speed' in c: return 'km/h'
    if 'power' in c: return 'kW'
    if 'energy' in c: return 'kWh'
    if 'altitude' in c or 'elevation' in c: return 'm'
    if 'gradient' in c: return '%'
    if 'temperature' in c: return 'C'
    if 'time' in c: return 'min'
    if 'distance' in c: return 'km'
    return 'unitless'

def _source(c):
    if c in COMMON_FEATURES: return 'DEVRT SOC/capacity/GPS altitude, causal derivation'
    if c in OPTIONAL_NISSAN_FEATURES: return 'Verified Nissan DEVRT telemetry, causal derivation'
    return 'Metadata or target'

def _markdown_series(series):
    lines = ['| Feature | Correlation |', '|---|---:|']
    lines.extend(f'| `{name}` | {value:.6f} |' for name, value in series.items())
    return '\n'.join(lines)

if __name__=='__main__': main()
