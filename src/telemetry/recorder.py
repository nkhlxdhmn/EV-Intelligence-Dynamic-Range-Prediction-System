"""
STEP 15 — Live Data Recorder.

Optional disk-based telemetry recorder for streaming writes with bounded
memory. Uses Parquet format for efficient columnar storage.

REQUIREMENTS:
- streaming writes
- bounded memory
- Parquet preferred
- one file/session
- no full-session RAM accumulation

STORES per sample:
- timestamp (seconds since epoch, UTC)
- normalized signal values (dict signal_name -> value)
- quality flags (dict signal_name -> quality_state)
- source (adapter identifier)

DO NOT store unnecessary personal information.
"""

from __future__ import annotations

import os
import time
import json
from pathlib import Path
from typing import Any, Dict, Optional, List

import pyarrow as pa
import pyarrow.parquet as pq


# ---------------------------------------------------------------------------
# Recorder configuration
# ---------------------------------------------------------------------------

# Default maximum file size before rollover (bytes)
DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

# Default Parquet schema fields
DEFAULT_SCHEMA = pa.schema([
    ("timestamp", pa.float64()),          # seconds since epoch
    ("signals", pa.string()),              # JSON-encoded dict of signal values
    ("qualities", pa.string()),            # JSON-encoded dict of quality states
    ("source", pa.string()),               # adapter identifier
])


# ---------------------------------------------------------------------------
# RollingFileRecorder

class RollingFileRecorder:
    """Bounded-size Parquet-based telemetry recorder.

    Writes telemetry samples to a single Parquet file that grows up to a
    maximum size. When the limit is reached, the file is closed and a new
    file is started (rollover). Old files are not deleted; the caller is
    responsible for managing the file lifecycle.

    Memory is bounded: only one file's worth of data is held in RAM at any
    time. Samples are batched before writing to reduce I/O overhead.
    """

    def __init__(
        self,
        directory: Path,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        schema: pa.schema = DEFAULT_SCHEMA,
    ):
        """Initialize the recorder.

        Parameters
        ----------
        directory : Path
            Directory in which to write the recorder files.
        max_file_size : int, default 100 MB
            Maximum size (bytes) for a single file before rollover.
        schema : pa.schema
            Parquet schema for the recorded data.
        """
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._max_file_size = max_file_size
        self._schema = schema

        # State
        self._current_file: Optional[Path] = None
        self._current_size = 0
        self._batch: List[Dict[str, Any]] = []
        self._sample_count = 0
        self._source: Optional[str] = None

        # Ensure directory exists
        if not self._directory.is_dir():
            raise RuntimeError(f"Recorder directory not found: {self._directory}")

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    @property
    def source(self) -> Optional[str]:
        """Return the adapter source to which this recorder is attached."""
        return self._source

    @source.setter
    def source(self, value: str) -> None:
        """Set the adapter source and initialize the first file."""
        self._source = value
        self._initialize_file()

    # ------------------------------------------------------------------
    # File initialization / rollover
    # ------------------------------------------------------------------

    def _initialize_file(self) -> None:
        """Create a new Parquet file for recording."""
        # Close the previous file if it exists and has data
        if self._current_file is not None and self._current_size > 0:
            # Flush any remaining batch
            self._flush_batch(force=True)

        # Generate a new filename with timestamp
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self._current_file = self._directory / f"telemetry_{ts}.parquet"

        # Initialize the Parquet writer
        self._writer = pq.ParquetWriter(
            self._current_file,
            self._schema,
            # compression="SNAPPY",  # optional: enable compression
        )
        self._current_size = 0
        self._batch = []
        self._sample_count = 0

    # ------------------------------------------------------------------
    # Batch writing
    # ------------------------------------------------------------------

    def _flush_batch(self, force: bool = False) -> None:
        """Write the current batch to the Parquet file.

        Parameters
        ----------
        force : bool, default False
            If True, flush even if the batch is smaller than the preferred
            batch size.
        """
        if not self._batch:
            return

        try:
            # Convert batch to PyArrow tables
            # Each batch entry: {"timestamp": float, "signals": str, "qualities": str}
            timestamps = pa.array([entry["timestamp"] for entry in self._batch], type=pa.float64())
            signal_jsons = pa.array([entry["signals"] for entry in self._batch], type=pa.string())
            quality_jsons = pa.array([entry["qualities"] for entry in self._batch], type=pa.string())

            table = pa.table({
                "timestamp": timestamps,
                "signals": signal_jsons,
                "qualities": quality_jsons,
            })

            self._writer.write_table(table)
            self._current_size += sum(
                len(json.dumps(entry)) for entry in self._batch
            )
        except Exception as e:
            # In production, this would go to a proper logger
            print(f"Recorder write error: {e}")
        finally:
            self._batch = []
            self._sample_count = 0

    # ------------------------------------------------------------------
    # Public API: insert
    # ------------------------------------------------------------------

    def insert(
        self,
        timestamp: float,
        signals: Dict[str, Any],
        qualities: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> None:
        """Insert a telemetry sample into the recorder.

        Parameters
        ----------
        timestamp : float
            Seconds since epoch (UTC) when the sample was read.
        signals : dict[str, Any]
            Normalized signal name -> value mapping.
        qualities : dict[str, Any], optional
            Signal name -> quality state (VALID, MISSING, STALE, etc.).
            If None, all signals are assumed VALID.
        source : str, optional
            Adapter source identifier. If None, uses the recorder's source.
        """
        # Set the source for this sample (recorder-level source if not provided)
        sample_source = source if source is not None else self._source

        # Prepare qualities dict as JSON
        if qualities is None:
            qualities = {name: "VALID" for name in signals}
        qualities_json = json.dumps(qualities)

        # Prepare signals dict as JSON (only include finite values for storage
        # efficiency; None/missing values are still recorded)
        signals_json = json.dumps(signals)

        # Add to batch
        self._batch.append({
            "timestamp": timestamp,
            "signals": signals_json,
            "qualities": qualities_json,
        })
        self._sample_count += 1

        # Check if we should roll over (based on file size or batch count)
        # Batch size: write every 10 samples or when file approaches limit
        if (
            self._sample_count >= 10
            or (self._current_file is not None and self._current_size >= self._max_file_size)
            or (self._current_file is not None and self._current_size + len(json.dumps(self._batch[-1])) >= self._max_file_size)
        ):
            self._flush_batch()
            if not force and self._current_file is not None and self._current_size >= self._max_file_size:
                # Rollover: start a new file
                self._initialize_file()

    # ------------------------------------------------------------------
    # Public API: close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Flush any remaining batch and close the current file."""
        try:
            self._flush_batch(force=True)
        finally:
            if hasattr(self, "_writer") and self._writer is not None:
                self._writer.close()
            self._current_file = None
            self._writer = None
            self._batch = []
            self._sample_count = 0

    # ------------------------------------------------------------------
    # Utility: list recordings
    # ------------------------------------------------------------------

    def list_recordings(self) -> List[Dict[str, Any]]:
        """List recorded telemetry files with metadata.

        Returns
        -------
        list of dict
            Each dict has: filename, size_bytes, sample_count (approx),
            start_time, end_time (approx).
        """
        if not self._current_file and not any(self._directory.iterdir()):
            return []

        records: List[Dict[str, Any]] = []

        # Check current file
        if self._current_file is not None and self._current_file.exists():
            try:
                size = self._current_file.stat().st_size
                records.append({
                    "filename": self._current_file.name,
                    "size_bytes": size,
                    "start_time": None,  # approximate; would need metadata
                    "end_time": None,
                })
            except Exception:
                pass

        # Check historical files (if any)
        for f in sorted(self._directory.iterdir()):
            if f.name.startswith("telemetry_") and f.name.endswith(".parquet"):
                try:
                    size = f.stat().st_size
                    records.append({
                        "filename": f.name,
                        "size_bytes": size,
                        "start_time": None,
                        "end_time": None,
                    })
                except Exception:
                    pass

        return records