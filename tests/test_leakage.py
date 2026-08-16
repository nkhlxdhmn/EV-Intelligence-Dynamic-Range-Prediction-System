"""
Tests for target leakage in feature engineering.
"""

import pandas as pd
import numpy as np
from src.evaluation.leakage_audit import audit_dataset_columns, check_mathematical_leakage

def test_column_names_audit():
    bad_columns = [
        'current_soc_pct',
        'future_soc_pct',
        'past_mean_speed',
        'target_future_energy_kwh_per_km',
        'trip_end_distance'
    ]
    
    violations = audit_dataset_columns(bad_columns)
    assert len(violations) == 2
    assert any('future_soc_pct' in v for v in violations)
    assert any('trip_end_distance' in v for v in violations)

def test_mathematical_leakage():
    df = pd.DataFrame({
        'safe_feature': np.random.rand(100),
        'target_future_energy_kwh_per_km': np.linspace(0, 10, 100),
        'leaky_feature': np.linspace(0, 10, 100) * 2.5 + 1.0  # Perfect linear correlation
    })
    
    violations = check_mathematical_leakage(df)
    assert len(violations) == 1
    assert 'leaky_feature' in violations[0]
