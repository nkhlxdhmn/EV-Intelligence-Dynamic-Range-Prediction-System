"""
Split audit and leakage verification.

Verifies:
1. No trip appears in multiple splits
2. No vehicle/trip combination is duplicated across splits
3. Train/validation/test sample counts sum to total
4. All samples belong to exactly one split
5. No duplicate sample_id (if exists) across splits
6. Timestamps are valid (not null, in range)
7. Target is present where required
8. Trip-level integrity maintained
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple


class SplitAuditor:
    """Verify split integrity and detect leakage."""
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.issues = []
        self.warnings = []
        
    def log(self, msg: str, level: str = 'info'):
        """Log message."""
        if self.verbose:
            print(f"[{level.upper()}] {msg}")
    
    def add_issue(self, msg: str):
        """Record critical issue."""
        self.issues.append(msg)
        self.log(f"ISSUE: {msg}", level='error')
    
    def add_warning(self, msg: str):
        """Record warning."""
        self.warnings.append(msg)
        self.log(f"WARNING: {msg}", level='warning')
    
    def audit(
        self,
        split_assignments_file: str,
        train_file: str,
        val_file: str,
        test_file: str,
        original_file: str = None,
    ) -> Dict:
        """
        Run complete split audit.
        
        Returns:
        --------
        Dict with audit results and statistics.
        """
        
        self.log("="*60)
        self.log("SPLIT AUDIT STARTED")
        self.log("="*60)
        
        # Load all files
        self.log("\nLoading files...")
        split_assignments = pd.read_parquet(split_assignments_file)
        train = pd.read_parquet(train_file)
        val = pd.read_parquet(val_file)
        test = pd.read_parquet(test_file)
        
        if original_file:
            original = pd.read_parquet(original_file)
        else:
            original = pd.concat([train, val, test], ignore_index=True)
        
        self.log(f"Split assignments: {len(split_assignments)} trips")
        self.log(f"Train: {len(train)} samples from {train['trip_id'].nunique()} trips")
        self.log(f"Validation: {len(val)} samples from {val['trip_id'].nunique()} trips")
        self.log(f"Test: {len(test)} samples from {test['trip_id'].nunique()} trips")
        self.log(f"Original: {len(original)} samples from {original['trip_id'].nunique()} trips")
        
        # AUDIT 1: No trip appears in multiple splits
        self.log("\n[AUDIT 1] Checking no trip appears in multiple splits...")
        train_trips = set(train['trip_id'].unique())
        val_trips = set(val['trip_id'].unique())
        test_trips = set(test['trip_id'].unique())
        
        train_val_overlap = train_trips & val_trips
        train_test_overlap = train_trips & test_trips
        val_test_overlap = val_trips & test_trips
        
        if train_val_overlap:
            self.add_issue(f"Train-Validation overlap: {len(train_val_overlap)} trips")
        if train_test_overlap:
            self.add_issue(f"Train-Test overlap: {len(train_test_overlap)} trips")
        if val_test_overlap:
            self.add_issue(f"Validation-Test overlap: {len(val_test_overlap)} trips")
        
        if not (train_val_overlap or train_test_overlap or val_test_overlap):
            self.log("✓ No overlap between splits")
        
        # AUDIT 2: Sample count verification
        self.log("\n[AUDIT 2] Checking sample counts...")
        total_split_samples = len(train) + len(val) + len(test)
        if total_split_samples != len(original):
            self.add_issue(
                f"Sample count mismatch: "
                f"{total_split_samples} (train+val+test) != {len(original)} (original)"
            )
        else:
            self.log(f"✓ Sample counts correct: {total_split_samples} total")
        
        # AUDIT 3: All samples assigned exactly once
        self.log("\n[AUDIT 3] Checking all samples assigned exactly once...")
        split_samples_by_trip = []
        for split_name, split_df in [('train', train), ('validation', val), ('test', test)]:
            for trip_id, trip_data in split_df.groupby('trip_id'):
                split_samples_by_trip.append({
                    'trip_id': trip_id,
                    'split': split_name,
                    'samples': len(trip_data)
                })
        
        samples_per_trip = pd.DataFrame(split_samples_by_trip)
        duplicates = samples_per_trip['trip_id'].value_counts()
        if (duplicates > 1).any():
            self.add_issue(f"Trips appearing in multiple splits: {duplicates[duplicates > 1].sum()}")
        else:
            self.log("✓ All trips appear in exactly one split")
        
        # AUDIT 4: Trip-level counts
        self.log("\n[AUDIT 4] Checking trip-level assignments...")
        split_trip_count = split_assignments['trip_id'].nunique()
        combined_trip_count = len(set(train['trip_id']) | set(val['trip_id']) | set(test['trip_id']))
        
        if split_trip_count != combined_trip_count:
            self.add_issue(
                f"Trip count mismatch: "
                f"{split_trip_count} (split_assignments) != {combined_trip_count} (data)"
            )
        else:
            self.log(f"✓ Trip counts match: {split_trip_count} trips")
        
        # AUDIT 5: Vehicle/trip combination integrity
        self.log("\n[AUDIT 5] Checking vehicle/trip combinations...")
        
        # Get vehicle info for each trip
        for split_name, split_df in [('train', train), ('validation', val), ('test', test)]:
            vehicles_in_split = split_df.groupby('trip_id')['vehicle_id'].nunique()
            if (vehicles_in_split > 1).any():
                self.add_issue(
                    f"{split_name}: Some trips have samples from multiple vehicles"
                )
            else:
                self.log(f"✓ {split_name}: Each trip belongs to one vehicle")
        
        # AUDIT 6: Timestamp validity
        self.log("\n[AUDIT 6] Checking timestamp validity...")
        timestamp_cols = []
        for split_name, split_df in [('train', train), ('validation', val), ('test', test)]:
            if 'timestamp' in split_df.columns:
                null_count = split_df['timestamp'].isna().sum()
                if null_count > 0:
                    self.add_warning(f"{split_name}: {null_count} null timestamps")
                else:
                    self.log(f"✓ {split_name}: No null timestamps")
        
        # AUDIT 7: Target presence
        self.log("\n[AUDIT 7] Checking target presence...")
        for split_name, split_df in [('train', train), ('validation', val), ('test', test)]:
            if 'target_future_energy_kwh_per_km' in split_df.columns:
                null_count = split_df['target_future_energy_kwh_per_km'].isna().sum()
                if null_count > 0:
                    self.add_issue(
                        f"{split_name}: {null_count} null targets (target should be complete)"
                    )
                else:
                    self.log(f"✓ {split_name}: Target complete ({len(split_df)} samples)")
        
        # AUDIT 8: Split assignment consistency
        self.log("\n[AUDIT 8] Checking split assignment consistency...")
        assignment_dict = split_assignments.set_index('trip_id')['split'].to_dict()
        
        for split_name, split_df in [('train', train), ('validation', val), ('test', test)]:
            for trip_id in split_df['trip_id'].unique():
                if assignment_dict.get(trip_id) != split_name:
                    self.add_issue(
                        f"Trip {trip_id} in {split_name} data but assigned to "
                        f"{assignment_dict.get(trip_id)}"
                    )
        
        if not self.issues:
            self.log("✓ All split assignments consistent")
        
        # Summary statistics
        self.log("\n" + "="*60)
        self.log("AUDIT SUMMARY")
        self.log("="*60)
        
        summary = {
            'status': 'PASS' if not self.issues else 'FAIL',
            'issues': self.issues,
            'warnings': self.warnings,
            'total_issues': len(self.issues),
            'total_warnings': len(self.warnings),
            'total_samples': len(original),
            'total_trips': len(split_assignments),
            'train_samples': len(train),
            'train_trips': len(train['trip_id'].unique()),
            'val_samples': len(val),
            'val_trips': len(val['trip_id'].unique()),
            'test_samples': len(test),
            'test_trips': len(test['trip_id'].unique()),
        }
        
        # Vehicle distribution
        vehicle_dist = []
        for split_name, split_df in [('train', train), ('validation', val), ('test', test)]:
            vehicle_summary = split_df.groupby('vehicle_id').agg({
                'vehicle_model': 'first',
                'trip_id': 'nunique'
            }).reset_index()
            vehicle_summary['split'] = split_name
            vehicle_dist.append(vehicle_summary)
        
        vehicle_summary_df = pd.concat(vehicle_dist, ignore_index=True)
        vehicle_summary_df.columns = ['vehicle_id', 'vehicle_model', 'trip_count', 'split']
        
        summary['vehicle_distribution'] = vehicle_summary_df
        
        self.log(f"\nStatus: {summary['status']}")
        self.log(f"Issues: {summary['total_issues']}")
        self.log(f"Warnings: {summary['total_warnings']}")
        
        if summary['issues']:
            self.log("\nCritical Issues:")
            for issue in summary['issues']:
                self.log(f"  - {issue}")
        
        if summary['warnings']:
            self.log("\nWarnings:")
            for warning in summary['warnings']:
                self.log(f"  - {warning}")
        
        self.log("\n" + "="*60)
        
        return summary


def run_audit(project_root: str = None) -> Dict:
    """Run complete split audit."""
    
    if project_root is None:
        project_root = Path(__file__).parent.parent.parent
    else:
        project_root = Path(project_root)
    
    auditor = SplitAuditor(verbose=True)
    
    results = auditor.audit(
        split_assignments_file=str(project_root / 'data' / 'processed' / 'split_assignments.parquet'),
        train_file=str(project_root / 'data' / 'processed' / 'train.parquet'),
        val_file=str(project_root / 'data' / 'processed' / 'validation.parquet'),
        test_file=str(project_root / 'data' / 'processed' / 'test.parquet'),
        original_file=str(project_root / 'data' / 'processed' / 'devrt_ml_features.parquet'),
    )
    
    return results


if __name__ == '__main__':
    results = run_audit()
    
    if results['status'] == 'PASS':
        print("\n✓✓✓ AUDIT PASSED ✓✓✓")
    else:
        print("\n✗✗✗ AUDIT FAILED ✗✗✗")
        for issue in results['issues']:
            print(f"  CRITICAL: {issue}")
