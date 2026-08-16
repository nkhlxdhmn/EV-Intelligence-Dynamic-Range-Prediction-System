"""
Tests for split audit using synthetic data.

Creates synthetic split data to verify audit logic.
"""

import pandas as pd
import numpy as np
import pytest
import tempfile
from pathlib import Path
from src.evaluation.split_audit import SplitAuditor


class TestSplitAudit:
    """Test split audit functionality."""
    
    def setup_method(self):
        """Create synthetic data for testing."""
        np.random.seed(42)
        
        # Create synthetic split data
        # Train: trips 0-3 (4 trips)
        # Validation: trips 4-6 (3 trips)
        # Test: trips 7-9 (3 trips)
        
        train_rows = []
        val_rows = []
        test_rows = []
        
        # Train: 4 trips, 25 samples each
        for trip_id in range(0, 4):
            for i in range(25):
                train_rows.append({
                    'trip_id': f'trip_{trip_id}',
                    'vehicle_id': 6 if trip_id % 2 == 0 else 7,
                    'vehicle_model': 'Dacia Spring' if trip_id % 2 == 0 else 'Nissan Leaf',
                    'timestamp': pd.Timestamp(f'2023-01-{(trip_id*25 + i) % 28 + 1:02d}'),
                    'target_future_energy_kwh_per_km': np.random.normal(0.15, 0.08),
                })
        
        # Validation: 3 trips, 20 samples each
        for trip_id in range(4, 7):
            for i in range(20):
                val_rows.append({
                    'trip_id': f'trip_{trip_id}',
                    'vehicle_id': 6 if trip_id % 2 == 0 else 7,
                    'vehicle_model': 'Dacia Spring' if trip_id % 2 == 0 else 'Nissan Leaf',
                    'timestamp': pd.Timestamp(f'2023-02-{(trip_id*20 + i) % 28 + 1:02d}'),
                    'target_future_energy_kwh_per_km': np.random.normal(0.15, 0.08),
                })
        
        # Test: 3 trips, 20 samples each
        for trip_id in range(7, 10):
            for i in range(20):
                test_rows.append({
                    'trip_id': f'trip_{trip_id}',
                    'vehicle_id': 6 if trip_id % 2 == 0 else 7,
                    'vehicle_model': 'Dacia Spring' if trip_id % 2 == 0 else 'Nissan Leaf',
                    'timestamp': pd.Timestamp(f'2023-03-{(trip_id*20 + i) % 28 + 1:02d}'),
                    'target_future_energy_kwh_per_km': np.random.normal(0.15, 0.08),
                })
        
        self.train = pd.DataFrame(train_rows)
        self.val = pd.DataFrame(val_rows)
        self.test = pd.DataFrame(test_rows)
        
        # Create split assignments
        assignments = []
        for trip_id in range(0, 4):
            assignments.append({
                'trip_id': f'trip_{trip_id}',
                'vehicle_id': 6 if trip_id % 2 == 0 else 7,
                'vehicle_model': 'Dacia Spring' if trip_id % 2 == 0 else 'Nissan Leaf',
                'split': 'train'
            })
        for trip_id in range(4, 7):
            assignments.append({
                'trip_id': f'trip_{trip_id}',
                'vehicle_id': 6 if trip_id % 2 == 0 else 7,
                'vehicle_model': 'Dacia Spring' if trip_id % 2 == 0 else 'Nissan Leaf',
                'split': 'validation'
            })
        for trip_id in range(7, 10):
            assignments.append({
                'trip_id': f'trip_{trip_id}',
                'vehicle_id': 6 if trip_id % 2 == 0 else 7,
                'vehicle_model': 'Dacia Spring' if trip_id % 2 == 0 else 'Nissan Leaf',
                'split': 'test'
            })
        
        self.assignments = pd.DataFrame(assignments)
        self.original = pd.concat([self.train, self.val, self.test], ignore_index=True)
    
    def test_split_audit_pass(self):
        """Test that audit passes for valid split."""
        auditor = SplitAuditor(verbose=False)
        
        # Create temp parquet files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            assignments_file = tmpdir / 'assignments.parquet'
            train_file = tmpdir / 'train.parquet'
            val_file = tmpdir / 'validation.parquet'
            test_file = tmpdir / 'test.parquet'
            original_file = tmpdir / 'original.parquet'
            
            self.assignments.to_parquet(assignments_file, index=False)
            self.train.to_parquet(train_file, index=False)
            self.val.to_parquet(val_file, index=False)
            self.test.to_parquet(test_file, index=False)
            self.original.to_parquet(original_file, index=False)
            
            results = auditor.audit(
                str(assignments_file),
                str(train_file),
                str(val_file),
                str(test_file),
                str(original_file)
            )
            
            assert results['status'] == 'PASS'
            assert results['total_issues'] == 0
            assert len(results['issues']) == 0
    
    def test_split_audit_detects_overlap(self):
        """Test that audit detects when a trip appears in multiple splits."""
        auditor = SplitAuditor(verbose=False)
        
        # Corrupt validation data: add a trip that's in train
        corrupted_val = self.val.copy()
        corrupted_val.loc[0, 'trip_id'] = 'trip_0'  # This trip is in train!
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            assignments_file = tmpdir / 'assignments.parquet'
            train_file = tmpdir / 'train.parquet'
            val_file = tmpdir / 'validation.parquet'
            test_file = tmpdir / 'test.parquet'
            original_file = tmpdir / 'original.parquet'
            
            self.assignments.to_parquet(assignments_file, index=False)
            self.train.to_parquet(train_file, index=False)
            corrupted_val.to_parquet(val_file, index=False)
            self.test.to_parquet(test_file, index=False)
            
            # Combine all for original
            corrupted_original = pd.concat([self.train, corrupted_val, self.test], ignore_index=True)
            corrupted_original.to_parquet(original_file, index=False)
            
            results = auditor.audit(
                str(assignments_file),
                str(train_file),
                str(val_file),
                str(test_file),
                str(original_file)
            )
            
            # Should detect overlap
            assert results['total_issues'] > 0
    
    def test_split_audit_detects_sample_count_mismatch(self):
        """Test that audit detects sample count mismatches."""
        auditor = SplitAuditor(verbose=False)
        
        # Remove some samples from test
        corrupted_test = self.test.iloc[:-10].copy()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            assignments_file = tmpdir / 'assignments.parquet'
            train_file = tmpdir / 'train.parquet'
            val_file = tmpdir / 'validation.parquet'
            test_file = tmpdir / 'test.parquet'
            original_file = tmpdir / 'original.parquet'
            
            self.assignments.to_parquet(assignments_file, index=False)
            self.train.to_parquet(train_file, index=False)
            self.val.to_parquet(val_file, index=False)
            corrupted_test.to_parquet(test_file, index=False)
            self.original.to_parquet(original_file, index=False)
            
            results = auditor.audit(
                str(assignments_file),
                str(train_file),
                str(val_file),
                str(test_file),
                str(original_file)
            )
            
            # Should detect sample count mismatch
            assert results['total_issues'] > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
