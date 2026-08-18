"""
Recorder regression tests (audit F1.1 / F1.1b).

F1.1  : insert() raised NameError ('force' undefined) on first file rollover.
F1.1b : _initialize_file() replaced the Parquet writer without closing the
        previous one (handle leak, no Parquet footer on rolled files).
"""

import pyarrow.parquet as pq

from src.telemetry.recorder import RollingFileRecorder


def test_rollover_no_nameerror(tmp_path):
    """Inserting past the file-size limit must not raise NameError."""
    rec = RollingFileRecorder(tmp_path, max_file_size=1)
    rec.source = "TEST"
    for i in range(25):
        rec.insert(1000.0 + i, {"speed": 50.0 + i}, {"speed": "VALID"})
    rec.close()

    files = list(tmp_path.glob("telemetry_*.parquet"))
    assert len(files) >= 1


def test_rollover_files_are_valid_parquet(tmp_path):
    """Rolled files must be closed properly, readable, and lose no data."""
    rec = RollingFileRecorder(tmp_path, max_file_size=1)
    rec.source = "TEST"
    for i in range(25):
        rec.insert(1000.0 + i, {"speed": 50.0 + i}, {"speed": "VALID"})
    rec.close()

    files = sorted(tmp_path.glob("telemetry_*.parquet"))
    assert len(files) >= 2
    total_rows = 0
    for f in files:
        table = pq.read_table(f)
        assert table.num_rows >= 0  # valid, closed, footer written
        total_rows += table.num_rows
    # No telemetry may be lost across rollovers (F1.1c)
    assert total_rows == 25


def test_batch_flush_without_rollover(tmp_path):
    """A normal session under the size limit writes and closes cleanly."""
    rec = RollingFileRecorder(tmp_path, max_file_size=1024 * 1024)
    rec.source = "TEST"
    for i in range(15):
        rec.insert(1000.0 + i, {"speed": 50.0 + i}, {"speed": "VALID"})
    rec.close()

    files = list(tmp_path.glob("telemetry_*.parquet"))
    assert len(files) == 1
    assert pq.read_table(files[0]).num_rows == 15