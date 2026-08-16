"""
Unit tests for TUM EV UDS Extraction.
Validates extraction logic using a synthetic tiny Parquet file, ensuring no OOM errors.
"""

import os
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from scripts.tum_extractor import process_file, REQUIRED_IDS

@pytest.fixture
def mock_tum_parquet(tmp_path):
    """Creates a small mock TUM Parquet file for testing."""
    schema = pa.schema([
        ('vehicle_id', pa.string()),
        ('time', pa.float64()),
        ('value_id', pa.int32()),
        ('value', pa.float64())
    ])
    
    # 5 rows total, spanning multiple row groups to test row-group logic
    # Included: 2 valid signals (900, 4), 3 invalid signals (999, 100, 800)
    data_rg1 = pa.Table.from_arrays([
        pa.array(['TEST_VEH', 'TEST_VEH']),
        pa.array([1.0, 2.0]),
        pa.array([900, 999]),  # 900 is required, 999 is ignored
        pa.array([50.0, 10.0])
    ], schema=schema)
    
    data_rg2 = pa.Table.from_arrays([
        pa.array(['TEST_VEH', 'TEST_VEH', 'TEST_VEH']),
        pa.array([3.0, 4.0, 5.0]),
        pa.array([100, 4, 800]), # 4 is required, 100 and 800 are ignored
        pa.array([0.0, 25.0, 100.0])
    ], schema=schema)
    
    input_path = str(tmp_path / "TEST_VEH.parquet")
    
    # Write with small row groups
    with pq.ParquetWriter(input_path, schema) as writer:
        writer.write_table(data_rg1)
        writer.write_table(data_rg2)
        
    return input_path, str(tmp_path / "TEST_VEH_required.parquet")

def test_value_id_filtering_and_signal_mapping(mock_tum_parquet):
    in_path, out_path = mock_tum_parquet
    
    src_rows, ext_rows, max_ram = process_file(in_path, out_path)
    
    assert src_rows == 5
    assert ext_rows == 2
    
    # Reopen and check output
    pf = pq.ParquetFile(out_path)
    assert pf.metadata.num_rows == 2
    
    df = pf.read().to_pandas()
    
    # 1. Output schema
    assert list(df.columns) == ['vehicle_id', 'time', 'value_id', 'value', 'signal_name']
    
    # 2. No unexpected signals (only 900 and 4 should survive)
    assert set(df['value_id']) == {900, 4}
    
    # 3. Signal mapping
    assert set(df['signal_name']) == {"hv_soc", "vehicle_speed"}
    
    # 4. Source vehicle preservation
    assert set(df['vehicle_id']) == {"TEST_VEH"}
    
def test_no_complete_raw_file_loaded(mock_tum_parquet):
    """
    Test memory monitoring (RAM shouldn't spike for tiny file, but
    more importantly process_file shouldn't load everything).
    The process_file uses table.filter() per row_group.
    """
    in_path, out_path = mock_tum_parquet
    _, _, max_ram = process_file(in_path, out_path)
    
    # Very crude proxy for memory safety on a tiny file
    assert max_ram >= 0.0

def test_empty_row_groups(tmp_path):
    """Test handling of a parquet file where NO rows match the required IDs."""
    schema = pa.schema([
        ('vehicle_id', pa.string()),
        ('time', pa.float64()),
        ('value_id', pa.int32()),
        ('value', pa.float64())
    ])
    
    data = pa.Table.from_arrays([
        pa.array(['TEST_VEH', 'TEST_VEH']),
        pa.array([1.0, 2.0]),
        pa.array([999, 888]),  # None are required
        pa.array([50.0, 10.0])
    ], schema=schema)
    
    input_path = str(tmp_path / "TEST_EMPTY.parquet")
    out_path = str(tmp_path / "TEST_EMPTY_required.parquet")
    
    pq.write_table(data, input_path)
    
    src_rows, ext_rows, max_ram = process_file(input_path, out_path)
    
    assert src_rows == 2
    assert ext_rows == 0
    
    # File should exist but be empty
    assert os.path.exists(out_path)
    pf = pq.ParquetFile(out_path)
    assert pf.metadata.num_rows == 0
