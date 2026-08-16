"""
Tests for baseline models using synthetic data.

Tests are created with synthetic data to verify logic without requiring
real parquet files to be present.
"""

import pandas as pd
import numpy as np
import pytest
from src.models.baseline import (
    mean_baseline,
    vehicle_mean_baseline,
    mae,
    rmse,
    r_squared,
    safe_mape,
    smape
)


class TestMetrics:
    """Test metric calculation functions."""
    
    def test_mae(self):
        """Test Mean Absolute Error."""
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.1, 2.1, 3.1])
        expected = 0.1
        assert np.isclose(mae(y_true, y_pred), expected)
    
    def test_rmse(self):
        """Test Root Mean Squared Error."""
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.5, 2.5, 3.5])
        expected = np.sqrt(0.25)
        assert np.isclose(rmse(y_true, y_pred), expected)
    
    def test_r_squared_perfect(self):
        """Test R² for perfect predictions."""
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.0, 2.0, 3.0])
        expected = 1.0
        assert np.isclose(r_squared(y_true, y_pred), expected)
    
    def test_r_squared_mean_baseline(self):
        """Test R² for mean baseline (should be ~0)."""
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([2.0, 2.0, 2.0])  # Mean
        expected = 0.0
        assert np.isclose(r_squared(y_true, y_pred), expected, atol=1e-10)
    
    def test_smape(self):
        """Test Symmetric MAPE."""
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 210.0, 310.0])
        # SMAPE should handle these reasonably
        result = smape(y_true, y_pred)
        assert 0 <= result <= 200  # Valid range
        assert result > 0  # Should be non-zero for different values
    
    def test_safe_mape_with_zeros(self):
        """Test MAPE handling for zero values."""
        y_true = np.array([0.0, 1.0, 2.0])
        y_pred = np.array([0.1, 1.1, 2.1])
        # Should return nan or handle gracefully due to zero
        result = safe_mape(y_true, y_pred)
        # If majority are zero, will return nan
        assert result is np.nan or isinstance(result, float)


class TestMeanBaseline:
    """Test mean baseline model."""
    
    def setup_method(self):
        """Create synthetic data for testing."""
        np.random.seed(42)
        
        self.train = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.15, 0.08, 100),
            'vehicle_id': np.random.randint(6, 8, 100),
            'trip_id': [f'trip_{i}' for i in range(100)]
        })
        
        self.val = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.15, 0.08, 30),
            'vehicle_id': np.random.randint(6, 8, 30),
            'trip_id': [f'trip_{i}' for i in range(100, 130)]
        })
        
        self.test = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.15, 0.08, 20),
            'vehicle_id': np.random.randint(6, 8, 20),
            'trip_id': [f'trip_{i}' for i in range(130, 150)]
        })
    
    def test_mean_baseline_structure(self):
        """Test that mean baseline returns correct structure."""
        results = mean_baseline(self.train, self.val, self.test)
        
        assert 'model' in results
        assert 'train_mean' in results
        assert 'validation' in results
        assert 'test' in results
        
        val_metrics = results['validation']
        test_metrics = results['test']
        
        for metric in ['MAE', 'RMSE', 'R2', 'MAPE', 'SMAPE', 'samples']:
            assert metric in val_metrics
            assert metric in test_metrics
    
    def test_mean_baseline_constant_prediction(self):
        """Test that mean baseline predicts constant value."""
        results = mean_baseline(self.train, self.val, self.test)
        train_mean = results['train_mean']
        
        # For constant predictions, R² should be ~0
        r2_val = results['validation']['R2']
        assert -0.1 <= r2_val <= 0.1  # Very close to 0
        
        # MAE should be roughly std/2 for random normal data
        mae_val = results['validation']['MAE']
        assert mae_val > 0


class TestVehicleBaseline:
    """Test vehicle mean baseline model."""
    
    def setup_method(self):
        """Create synthetic data with vehicle structure."""
        np.random.seed(42)
        
        # Train: two vehicles with different means
        train_data_6 = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.10, 0.05, 50),
            'vehicle_id': 6,
            'trip_id': [f'trip_train_6_{i}' for i in range(50)]
        })
        
        train_data_7 = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.20, 0.05, 50),
            'vehicle_id': 7,
            'trip_id': [f'trip_train_7_{i}' for i in range(50)]
        })
        
        self.train = pd.concat([train_data_6, train_data_7], ignore_index=True)
        
        # Validation and test: mix of both vehicles
        val_data_6 = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.10, 0.05, 15),
            'vehicle_id': 6,
            'trip_id': [f'trip_val_6_{i}' for i in range(15)]
        })
        
        val_data_7 = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.20, 0.05, 15),
            'vehicle_id': 7,
            'trip_id': [f'trip_val_7_{i}' for i in range(15)]
        })
        
        self.val = pd.concat([val_data_6, val_data_7], ignore_index=True)
        
        test_data_6 = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.10, 0.05, 10),
            'vehicle_id': 6,
            'trip_id': [f'trip_test_6_{i}' for i in range(10)]
        })
        
        test_data_7 = pd.DataFrame({
            'target_future_energy_kwh_per_km': np.random.normal(0.20, 0.05, 10),
            'vehicle_id': 7,
            'trip_id': [f'trip_test_7_{i}' for i in range(10)]
        })
        
        self.test = pd.concat([test_data_6, test_data_7], ignore_index=True)
    
    def test_vehicle_baseline_structure(self):
        """Test that vehicle baseline returns correct structure."""
        results = vehicle_mean_baseline(self.train, self.val, self.test)
        
        assert 'model' in results
        assert 'vehicle_means' in results
        assert 'global_mean' in results
        assert 'validation' in results
        assert 'test' in results
        
        # Should have means for both vehicles
        assert len(results['vehicle_means']) == 2
        assert 6 in results['vehicle_means']
        assert 7 in results['vehicle_means']
    
    def test_vehicle_baseline_fallback(self):
        """Test that vehicle baseline doesn't use fallback when vehicles are known."""
        results = vehicle_mean_baseline(self.train, self.val, self.test)
        
        # Both vehicles appear in training, so fallback should be 0
        assert results['validation_fallback_samples'] == 0
        assert results['test_fallback_samples'] == 0


class TestSplitAudit:
    """Tests for split audit would go here."""
    
    def test_placeholder(self):
        """Placeholder test."""
        assert True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
