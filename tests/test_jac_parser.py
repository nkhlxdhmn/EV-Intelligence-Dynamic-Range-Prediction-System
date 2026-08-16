"""
Unit tests for JAC IEV40 Parser.

Tests use small mock data — the full JAC dataset is NOT loaded during testing.
"""

import os
import pytest
import pandas as pd
import numpy as np
from src.data.jac_parser import reconstruct_timestamps, process_jac


def _make_mock_df(rows):
    """Create a minimal mock DataFrame mimicking JAC CSV structure."""
    return pd.DataFrame(rows)


class TestTimestampReconstruction:
    """Test timestamp reconstruction from Y/M/D/H/MIN/SEC."""
    
    def test_valid_timestamp(self):
        df = _make_mock_df([
            {'Y': 23, 'M': 10, 'D': 23, 'H': 12, 'MIN': 55, 'SEC': 10},
        ])
        ts = reconstruct_timestamps(df)
        assert ts.iloc[0] == pd.Timestamp(2023, 10, 23, 12, 55, 10)
    
    def test_zero_date_is_nat(self):
        df = _make_mock_df([
            {'Y': 0, 'M': 0, 'D': 0, 'H': 0, 'MIN': 0, 'SEC': 0},
        ])
        ts = reconstruct_timestamps(df)
        assert pd.isna(ts.iloc[0])
    
    def test_partial_zero_date_is_nat(self):
        df = _make_mock_df([
            {'Y': 0, 'M': 0, 'D': 0, 'H': 12, 'MIN': 30, 'SEC': 5},
        ])
        ts = reconstruct_timestamps(df)
        assert pd.isna(ts.iloc[0])
    
    def test_invalid_month_is_nat(self):
        df = _make_mock_df([
            {'Y': 23, 'M': 13, 'D': 1, 'H': 0, 'MIN': 0, 'SEC': 0},
        ])
        ts = reconstruct_timestamps(df)
        assert pd.isna(ts.iloc[0])
    
    def test_seconds_preserved(self):
        """SEC column must be included in the timestamp, not ignored."""
        df = _make_mock_df([
            {'Y': 23, 'M': 10, 'D': 23, 'H': 12, 'MIN': 55, 'SEC': 42},
        ])
        ts = reconstruct_timestamps(df)
        assert ts.iloc[0].second == 42
    
    def test_mixed_valid_invalid(self):
        df = _make_mock_df([
            {'Y': 23, 'M': 10, 'D': 23, 'H': 12, 'MIN': 55, 'SEC': 10},
            {'Y': 0, 'M': 0, 'D': 0, 'H': 0, 'MIN': 0, 'SEC': 0},
            {'Y': 23, 'M': 10, 'D': 26, 'H': 20, 'MIN': 14, 'SEC': 5},
        ])
        ts = reconstruct_timestamps(df)
        assert ts.iloc[0] == pd.Timestamp(2023, 10, 23, 12, 55, 10)
        assert pd.isna(ts.iloc[1])
        assert ts.iloc[2] == pd.Timestamp(2023, 10, 26, 20, 14, 5)


class TestSpeedConversion:
    """Test that SPD is mapped to speed_kmh without modification."""
    
    def test_speed_passthrough(self, tmp_path):
        mock_data = pd.DataFrame({
            'id': [1, 2, 3],
            'COND': [9, 9, 9],
            'LAT': [-21.8, -21.8, -21.8],
            'LON': [-46.5, -46.5, -46.5],
            'ALT': [1329.0, 1329.0, 1329.0],
            'AX': [0, 0, 0], 'AY': [0, 0, 0], 'AZ': [0, 0, 0],
            'GX': [0, 0, 0], 'GY': [0, 0, 0], 'GZ': [0, 0, 0],
            'Y': [23, 23, 23], 'M': [10, 10, 10], 'D': [23, 23, 23],
            'H': [12, 12, 12], 'MIN': [55, 55, 55], 'SEC': [10, 12, 14],
            'CH': [94, 94, 94],
            'VOL': [2, 2, 2], 'CUR': [-1, -1, -1],
            'SPD': [0, 54, 133],
            'ODO': [25656.0, 25656.1, 25656.5],
            'BRK': [0, 0, 0], 'ACC': [0, 16, 30],
            'AUT': [251, 251, 251], 'ECO': [0, 0, 0], 'AIR': [0, 2, 2],
        })
        csv_path = tmp_path / "dataset.csv"
        mock_data.to_csv(csv_path, index=False)
        
        summary = process_jac(base_path=str(tmp_path), output_dir=str(tmp_path / "output"))
        df = pd.read_parquet(tmp_path / "output" / "jac_standardized.parquet")
        
        assert list(df['speed_kmh']) == [0, 54, 133]


class TestGPSValidation:
    """Test GPS quality flag logic."""
    
    def test_valid_gps(self, tmp_path):
        mock_data = pd.DataFrame({
            'id': [1, 2, 3],
            'COND': [9, 9, 9],
            'LAT': [-21.8, 95.0, -21.8],  # Row 2: invalid lat
            'LON': [-46.5, -46.5, 263.0],  # Row 3: invalid lon
            'ALT': [0, 0, 0],
            'AX': [0, 0, 0], 'AY': [0, 0, 0], 'AZ': [0, 0, 0],
            'GX': [0, 0, 0], 'GY': [0, 0, 0], 'GZ': [0, 0, 0],
            'Y': [23, 23, 23], 'M': [10, 10, 10], 'D': [23, 23, 23],
            'H': [12, 12, 12], 'MIN': [55, 55, 55], 'SEC': [10, 12, 14],
            'CH': [0, 0, 0],
            'VOL': [0, 0, 0], 'CUR': [0, 0, 0],
            'SPD': [0, 0, 0], 'ODO': [25656, 25656, 25656],
            'BRK': [0, 0, 0], 'ACC': [0, 0, 0],
            'AUT': [0, 0, 0], 'ECO': [0, 0, 0], 'AIR': [0, 0, 0],
        })
        csv_path = tmp_path / "dataset.csv"
        mock_data.to_csv(csv_path, index=False)
        
        summary = process_jac(base_path=str(tmp_path), output_dir=str(tmp_path / "output"))
        df = pd.read_parquet(tmp_path / "output" / "jac_standardized.parquet")
        
        assert df['quality_gps'].iloc[0] == 1  # Valid
        assert df['quality_gps'].iloc[1] == 0  # Lat > 90
        assert df['quality_gps'].iloc[2] == 0  # Lon > 180


class TestOdometerPreservation:
    """Test odometer values are preserved as-is."""
    
    def test_odo_passthrough(self, tmp_path):
        mock_data = pd.DataFrame({
            'id': [1, 2],
            'COND': [9, 9],
            'LAT': [-21.8, -21.8], 'LON': [-46.5, -46.5], 'ALT': [0, 0],
            'AX': [0, 0], 'AY': [0, 0], 'AZ': [0, 0],
            'GX': [0, 0], 'GY': [0, 0], 'GZ': [0, 0],
            'Y': [23, 23], 'M': [10, 10], 'D': [23, 23],
            'H': [12, 12], 'MIN': [55, 56], 'SEC': [10, 10],
            'CH': [0, 0],
            'VOL': [0, 0], 'CUR': [0, 0],
            'SPD': [0, 0],
            'ODO': [25656.4, 25660.1],
            'BRK': [0, 0], 'ACC': [0, 0],
            'AUT': [0, 0], 'ECO': [0, 0], 'AIR': [0, 0],
        })
        csv_path = tmp_path / "dataset.csv"
        mock_data.to_csv(csv_path, index=False)
        
        process_jac(base_path=str(tmp_path), output_dir=str(tmp_path / "output"))
        df = pd.read_parquet(tmp_path / "output" / "jac_standardized.parquet")
        
        assert df['odometer_km'].iloc[0] == pytest.approx(25656.4)
        assert df['odometer_km'].iloc[1] == pytest.approx(25660.1)


class TestSourceLineage:
    """Test that source traceability fields are always present."""
    
    def test_source_fields_exist(self, tmp_path):
        mock_data = pd.DataFrame({
            'id': [1],
            'COND': [9],
            'LAT': [0], 'LON': [0], 'ALT': [0],
            'AX': [0], 'AY': [0], 'AZ': [0],
            'GX': [0], 'GY': [0], 'GZ': [0],
            'Y': [23], 'M': [10], 'D': [23],
            'H': [12], 'MIN': [55], 'SEC': [10],
            'CH': [0],
            'VOL': [0], 'CUR': [0],
            'SPD': [0], 'ODO': [25656],
            'BRK': [0], 'ACC': [0],
            'AUT': [0], 'ECO': [0], 'AIR': [0],
        })
        csv_path = tmp_path / "dataset.csv"
        mock_data.to_csv(csv_path, index=False)
        
        process_jac(base_path=str(tmp_path), output_dir=str(tmp_path / "output"))
        df = pd.read_parquet(tmp_path / "output" / "jac_standardized.parquet")
        
        assert df['source_dataset'].iloc[0] == 'JAC_IEV40'
        assert df['source_file'].iloc[0] == 'dataset.csv'
        assert df['source_row_id'].iloc[0] == 0


class TestSensorGuardrails:
    """Test that forbidden columns are NOT created."""
    
    def test_no_ambient_temperature(self, tmp_path):
        mock_data = pd.DataFrame({
            'id': [1],
            'COND': [9],
            'LAT': [0], 'LON': [0], 'ALT': [0],
            'AX': [0], 'AY': [0], 'AZ': [0],
            'GX': [0], 'GY': [0], 'GZ': [0],
            'Y': [23], 'M': [10], 'D': [23],
            'H': [12], 'MIN': [55], 'SEC': [10],
            'CH': [0],
            'VOL': [350], 'CUR': [100],
            'SPD': [0], 'ODO': [25656],
            'BRK': [0], 'ACC': [0],
            'AUT': [0], 'ECO': [0], 'AIR': [2],
        })
        csv_path = tmp_path / "dataset.csv"
        mock_data.to_csv(csv_path, index=False)
        
        process_jac(base_path=str(tmp_path), output_dir=str(tmp_path / "output"))
        df = pd.read_parquet(tmp_path / "output" / "jac_standardized.parquet")
        
        # AIR must NOT be treated as temperature
        assert 'ambient_temperature_c' not in df.columns
        assert 'air_sensor_flag' in df.columns
        assert df['air_sensor_flag'].iloc[0] == 2
    
    def test_no_battery_voltage(self, tmp_path):
        mock_data = pd.DataFrame({
            'id': [1],
            'COND': [9],
            'LAT': [0], 'LON': [0], 'ALT': [0],
            'AX': [0], 'AY': [0], 'AZ': [0],
            'GX': [0], 'GY': [0], 'GZ': [0],
            'Y': [23], 'M': [10], 'D': [23],
            'H': [12], 'MIN': [55], 'SEC': [10],
            'CH': [0],
            'VOL': [379], 'CUR': [263],
            'SPD': [0], 'ODO': [25656],
            'BRK': [0], 'ACC': [0],
            'AUT': [0], 'ECO': [0], 'AIR': [0],
        })
        csv_path = tmp_path / "dataset.csv"
        mock_data.to_csv(csv_path, index=False)
        
        process_jac(base_path=str(tmp_path), output_dir=str(tmp_path / "output"))
        df = pd.read_parquet(tmp_path / "output" / "jac_standardized.parquet")
        
        # VOL must NOT be treated as battery voltage
        assert 'battery_voltage_v' not in df.columns
        assert 'vol_raw' in df.columns
        assert df['vol_raw'].iloc[0] == 379
    
    def test_no_battery_current(self, tmp_path):
        mock_data = pd.DataFrame({
            'id': [1],
            'COND': [9],
            'LAT': [0], 'LON': [0], 'ALT': [0],
            'AX': [0], 'AY': [0], 'AZ': [0],
            'GX': [0], 'GY': [0], 'GZ': [0],
            'Y': [23], 'M': [10], 'D': [23],
            'H': [12], 'MIN': [55], 'SEC': [10],
            'CH': [0],
            'VOL': [350], 'CUR': [200],
            'SPD': [0], 'ODO': [25656],
            'BRK': [0], 'ACC': [0],
            'AUT': [0], 'ECO': [0], 'AIR': [0],
        })
        csv_path = tmp_path / "dataset.csv"
        mock_data.to_csv(csv_path, index=False)
        
        process_jac(base_path=str(tmp_path), output_dir=str(tmp_path / "output"))
        df = pd.read_parquet(tmp_path / "output" / "jac_standardized.parquet")
        
        # CUR must NOT be treated as HV battery current
        assert 'battery_current_a' not in df.columns
        assert 'current_raw' in df.columns
        assert df['current_raw'].iloc[0] == 200


class TestNoRawModification:
    """Test that the raw file is not modified."""
    
    def test_raw_file_unchanged(self, tmp_path):
        mock_data = pd.DataFrame({
            'id': [1],
            'COND': [9],
            'LAT': [0], 'LON': [0], 'ALT': [0],
            'AX': [0], 'AY': [0], 'AZ': [0],
            'GX': [0], 'GY': [0], 'GZ': [0],
            'Y': [23], 'M': [10], 'D': [23],
            'H': [12], 'MIN': [55], 'SEC': [10],
            'CH': [0],
            'VOL': [0], 'CUR': [0],
            'SPD': [0], 'ODO': [25656],
            'BRK': [0], 'ACC': [0],
            'AUT': [0], 'ECO': [0], 'AIR': [0],
        })
        csv_path = tmp_path / "dataset.csv"
        mock_data.to_csv(csv_path, index=False)
        
        # Read content before processing
        with open(csv_path, 'r') as f:
            content_before = f.read()
        
        process_jac(base_path=str(tmp_path), output_dir=str(tmp_path / "output"))
        
        # Read content after processing
        with open(csv_path, 'r') as f:
            content_after = f.read()
        
        assert content_before == content_after
