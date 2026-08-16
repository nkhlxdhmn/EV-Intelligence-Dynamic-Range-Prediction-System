import numpy as np
import pandas as pd

from scripts.comprehensive_feature_engineering import engineer_trip
from src.evaluation.leakage_audit import audit_dataset_columns


def _trip():
    n = 80
    return pd.DataFrame({
        "source_row_id": range(n), "trip_id": ["NISSAN_TEST"] * n, "vehicle_id": [1] * n,
        "timestamp": pd.date_range("2023-01-01", periods=n, freq="10s", tz="UTC"),
        "soc_pct": 90 - np.arange(n) * .1, "soh_pct": [98.] * n,
        "speed_kmh": [36.] * n, "ambient_temperature_c": [20.] * n,
        "motor_power_kw": [10.] * n, "aux_power_kw": [.2] * n,
        "motor_torque_nm": [10.] * n, "motor_rpm": [1000.] * n,
        "altitude_m": np.arange(n, dtype=float), "distance_km": np.arange(n) * .1,
        "battery_capacity_kwh": [40.] * n, "regen_power_kw": [-1.] * n,
    })


def test_engineered_windows_are_causal():
    original = _trip()
    baseline = engineer_trip(original)
    changed = original.copy()
    changed.loc[50:, "speed_kmh"] = 200
    candidate = engineer_trip(changed)
    # Values before row 50 cannot observe the changed future values.
    assert baseline.loc[baseline.index < 50, "mean_speed_500m"].equals(candidate.loc[candidate.index < 50, "mean_speed_500m"])


def test_expanded_name_audit_allows_causal_features():
    columns = engineer_trip(_trip()).columns
    assert audit_dataset_columns(columns) == []
