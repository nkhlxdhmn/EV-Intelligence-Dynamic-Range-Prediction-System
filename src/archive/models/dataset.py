"""
Memory-efficient dataset loading for ML models.

Provides functions to load train/validation/test data selectively,
with column projection and filtering to avoid loading unnecessary data into RAM.

Designed for 16 GB RAM machine - loads only required splits and columns.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple, Union


# Default columns to use in ML models
# These are confirmed to exist and be reasonably complete
FEATURE_COLUMNS = [
    'current_soc_pct',
    'battery_capacity_kwh',
    'current_altitude_m',
    'past_1km_gradient_pct',
    'terrain_class',
]

# These are vehicle-specific and may not exist in all samples
OPTIONAL_FEATURE_COLUMNS = [
    'current_speed_kmh',
    'current_ambient_temperature_c',
    'current_motor_power_kw',
    'past_mean_speed_kmh',
    'past_speed_std',
    'past_mean_acceleration_mps2',
]

TARGET_COLUMN = 'target_future_energy_kwh_per_km'

# ID columns for reference
ID_COLUMNS = ['trip_id', 'vehicle_id', 'vehicle_model', 'timestamp']


class DatasetLoader:
    """Memory-efficient dataset loader."""
    
    def __init__(
        self,
        data_dir: Union[str, Path] = None,
        feature_columns: List[str] = None,
        target_column: str = TARGET_COLUMN,
        include_ids: bool = False,
        verbose: bool = False
    ):
        """
        Initialize dataset loader.
        
        Parameters:
        -----------
        data_dir : str or Path
            Directory containing train/validation/test parquet files
        feature_columns : list of str
            Feature columns to load (if None, use FEATURE_COLUMNS)
        target_column : str
            Name of target column
        include_ids : bool
            Whether to include ID columns (trip_id, vehicle_id, etc.)
        verbose : bool
            Print debug information
        """
        
        if data_dir is None:
            # Try to infer from this file location
            data_dir = Path(__file__).parent.parent.parent / 'data' / 'processed'
        
        self.data_dir = Path(data_dir)
        self.feature_columns = feature_columns or FEATURE_COLUMNS
        self.target_column = target_column
        self.include_ids = include_ids
        self.verbose = verbose
        
        # Check that data files exist
        self.train_file = self.data_dir / 'train.parquet'
        self.val_file = self.data_dir / 'validation.parquet'
        self.test_file = self.data_dir / 'test.parquet'
        
        if not self.train_file.exists():
            raise FileNotFoundError(f"Train file not found: {self.train_file}")
    
    def log(self, msg: str):
        """Log message if verbose."""
        if self.verbose:
            print(f"[DatasetLoader] {msg}")
    
    def _get_columns_to_load(self, include_target: bool = True) -> List[str]:
        """Get list of columns to load."""
        columns = []
        
        if self.include_ids:
            columns.extend(ID_COLUMNS)
        
        columns.extend(self.feature_columns)
        
        if include_target:
            columns.append(self.target_column)
        
        return columns
    
    def load_split(
        self,
        split: str = 'train',
        include_target: bool = True,
        reset_index: bool = True
    ) -> pd.DataFrame:
        """
        Load a single split efficiently.
        
        Parameters:
        -----------
        split : str
            'train', 'validation', or 'test'
        include_target : bool
            Whether to include target column
        reset_index : bool
            Whether to reset DataFrame index
            
        Returns:
        --------
        DataFrame with only the required columns
        """
        
        if split == 'train':
            filepath = self.train_file
        elif split == 'validation':
            filepath = self.val_file
        elif split == 'test':
            filepath = self.test_file
        else:
            raise ValueError(f"Invalid split: {split}")
        
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        # Load with column projection
        columns = self._get_columns_to_load(include_target=include_target)
        
        self.log(f"Loading {split} from {filepath.name}")
        self.log(f"  Columns: {len(columns)} ({', '.join(columns[:3])}...)")
        
        df = pd.read_parquet(filepath, columns=columns)
        
        if reset_index:
            df = df.reset_index(drop=True)
        
        self.log(f"  Loaded: {len(df)} samples, {len(df.columns)} columns")
        
        return df
    
    def load_train(self, include_target: bool = True) -> pd.DataFrame:
        """Load training data."""
        return self.load_split('train', include_target=include_target)
    
    def load_validation(self, include_target: bool = True) -> pd.DataFrame:
        """Load validation data."""
        return self.load_split('validation', include_target=include_target)
    
    def load_test(self, include_target: bool = True) -> pd.DataFrame:
        """Load test data (usually without target for final evaluation)."""
        return self.load_split('test', include_target=include_target)
    
    def load_train_val(
        self,
        include_target: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load both train and validation."""
        train = self.load_train(include_target=include_target)
        val = self.load_validation(include_target=include_target)
        return train, val
    
    def load_all(self, include_target: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load all three splits."""
        train = self.load_train(include_target=include_target)
        val = self.load_validation(include_target=include_target)
        test = self.load_test(include_target=include_target)
        return train, val, test
    
    def get_feature_columns(self) -> List[str]:
        """Get list of feature columns."""
        return self.feature_columns
    
    def get_target_column(self) -> str:
        """Get target column name."""
        return self.target_column


def get_dataset_info(data_dir: Union[str, Path] = None) -> dict:
    """
    Get basic information about the splits without loading all data.
    
    Uses PyArrow to read metadata only.
    """
    
    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent / 'data' / 'processed'
    
    data_dir = Path(data_dir)
    
    import pyarrow.parquet as pq
    
    info = {}
    
    for split_name, filename in [
        ('train', 'train.parquet'),
        ('validation', 'validation.parquet'),
        ('test', 'test.parquet')
    ]:
        filepath = data_dir / filename
        
        if filepath.exists():
            table = pq.read_table(filepath)
            info[split_name] = {
                'samples': table.num_rows,
                'columns': table.column_names,
                'trips': None  # Would need to load data to compute
            }
    
    return info


if __name__ == '__main__':
    # Example usage
    loader = DatasetLoader(verbose=True)
    
    print("="*60)
    print("DATASET LOADER EXAMPLE")
    print("="*60)
    
    # Get info
    info = get_dataset_info()
    print("\nDataset Info:")
    for split, data in info.items():
        print(f"  {split}: {data['samples']} samples, {len(data['columns'])} columns")
    
    # Load train only
    print("\nLoading train...")
    train = loader.load_train()
    print(f"Train shape: {train.shape}")
    print(f"Train columns: {list(train.columns)}")
    print(f"Train dtypes:\n{train.dtypes}")
    
    # Load all
    print("\nLoading all splits...")
    train, val, test = loader.load_all()
    print(f"Train: {len(train)} samples")
    print(f"Validation: {len(val)} samples")
    print(f"Test: {len(test)} samples")
    print(f"Total: {len(train) + len(val) + len(test)} samples")
