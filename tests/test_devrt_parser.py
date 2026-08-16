import os
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from src.data.devrt_parser import parse_timestamps, process_devrt_trip, timestamp_to_epoch_seconds


def test_timestamp_to_epoch_seconds_units():
    # Regression: pandas may store tz-aware timestamps as datetime64[us, UTC]
    # or datetime64[ns, UTC]; the helper must return TRUE epoch seconds in both
    # cases (the old naive "astype('int64')/1e9" was 1000x too small on [us]).
    ns = pd.Series(pd.to_datetime(["2023-04-18 11:33:00+00:00", "2023-04-18 12:05:00+00:00"], utc=True))
    ns = pd.Series(ns.dt.tz_localize(None).astype("datetime64[ns]")).dt.tz_localize("UTC")
    us = pd.Series(ns.dt.tz_localize(None).astype("datetime64[us]")).dt.tz_localize("UTC")
    assert str(ns.dtype) == "datetime64[ns, UTC]"
    assert str(us.dtype) == "datetime64[us, UTC]"

    for series in (ns, us):
        secs = timestamp_to_epoch_seconds(series)
        assert secs[0] == pytest.approx(1681817580.0, abs=1e-3)
        assert secs[1] == pytest.approx(1681819500.0, abs=1e-3)
        assert np.diff(secs)[0] == pytest.approx(1920.0, abs=1e-3)


def test_parse_timestamps_returns_ns():
    # parse_timestamps must normalize to datetime64[ns, UTC] so downstream
    # "astype('int64')/1e9" unit assumptions hold everywhere.
    iso = parse_timestamps(pd.Series(["2023-04-18 08:02:23.502"]))
    assert str(iso.dtype) == "datetime64[ns, UTC]"
    rel = parse_timestamps(pd.Series(["33:04.6"]), trip_date="2023-04-18")
    assert str(rel.dtype) == "datetime64[ns, UTC]"


def test_parse_timestamps_standard():
    # Test ISO standard format
    series = pd.Series(["2023-04-18 08:02:23.502", "2023-04-19 12:00:00"])
    parsed = parse_timestamps(series)
    
    assert parsed.iloc[0].year == 2023
    assert parsed.iloc[0].month == 4
    assert parsed.iloc[0].day == 18
    assert parsed.iloc[0].hour == 8
    assert parsed.iloc[0].tzinfo == timezone.utc
    assert parsed.iloc[1].day == 19
    assert parsed.iloc[1].hour == 12


def test_parse_timestamps_relative():
    # Test relative format (MM:SS and HH:MM:SS) anchored to the trip date
    series = pd.Series(["33:04.6", "02:15:30.5", "invalid", None])
    parsed = parse_timestamps(series, trip_date="2023-04-18")

    # 33:04.6 should parse as 33 minutes, 4.6 seconds after trip date midnight
    assert parsed.iloc[0].year == 2023
    assert parsed.iloc[0].month == 4
    assert parsed.iloc[0].day == 18
    assert parsed.iloc[0].minute == 33
    assert parsed.iloc[0].second == 4
    assert abs(parsed.iloc[0].microsecond - 600000) <= 1
    assert parsed.iloc[0].tzinfo == timezone.utc

    # 02:15:30.5 should parse as 2 hours, 15 minutes, 30.5 seconds after midnight
    assert parsed.iloc[1].hour == 2
    assert parsed.iloc[1].minute == 15
    assert parsed.iloc[1].second == 30
    assert parsed.iloc[1].tzinfo == timezone.utc

    # Invalid formats should return NaT
    assert pd.isna(parsed.iloc[2])
    assert pd.isna(parsed.iloc[3])


def test_parse_timestamps_relative_wrap_correction():
    # The Dacia relative clock wraps every 60 minutes. Values that fall below
    # 24 minutes (e.g. 00:01.1) must NOT be parsed as absolute today-dates;
    # they continue the elapsed clock after a full 60-minute lap.
    series = pd.Series(["59:55.6", "00:01.1", "00:12.1", "13:51.5"])
    parsed = parse_timestamps(series, trip_date="2023-04-18")

    assert pd.api.types.is_datetime64_any_dtype(parsed.dtype)
    assert parsed.is_monotonic_increasing
    # No garbage 2026 dates (the latent bug routed these to today's date)
    assert (parsed.dt.year == 2026).sum() == 0
    assert parsed.iloc[0].minute == 59
    assert parsed.iloc[1].minute == 0  # wrapped into the next 60-minute lap
    # Elapsed deltas stay ~seconds apart across the wrap
    dt = (parsed.iloc[1] - parsed.iloc[0]).total_seconds()
    assert 5.0 < dt < 7.0


def test_devrt_processing_validation(tmp_path):
    # Create a small mock dataset
    mock_data = pd.DataFrame({
        'timestamp_data_utc': ["2023-04-18 08:02:23.502", "2023-04-18 08:02:24.502", "2023-04-18 08:02:25.502"],
        'car_id': [1, 1, 1],
        'soc': [85.5, -5.0, 105.0],      # Valid, invalid low, invalid high
        'soh': [98.0, 100.0, 102.0],     # Valid, valid, invalid high
        'speed': [45.0, -10.0, np.nan],  # Normal speed, reverse driving, missing speed
        'amb_temp': [15.5, 16.0, 16.5],
        'Motor Pwr(w)': [25000.0, -5000.0, 0.0],
        'Aux Pwr(100w)': [2, 3, 0],
        'Motor Temp': [45.0, 47.0, 48.0],
        'Torque Nm': [120.0, -30.0, 0.0],
        'rpm': [2500.0, -500.0, 0.0],
        'altitude': [120.0, np.nan, 122.0],
        'elv_spy': [119.5, 120.0, 121.5],
        'cumul_dist': [0.0, 0.1, -0.2],   # Valid, valid, invalid negative
        'latitude': [43.1, 95.0, np.nan], # Valid, invalid latitude, missing
        'longitude': [-2.3, 190.0, -2.3], # Valid, invalid longitude, valid
        'capacity': [33000, 33000, 33000],
        'ref_consumption': [139, 139, 139],
        'regenwh': [-5000.0, 0.0, np.nan] # regen power (Watts)
    })
    
    csv_file = tmp_path / "20230418_DACIA_TEST_TRIP_001.csv"
    mock_data.to_csv(csv_file, index=False)
    
    file_info = {
        'path': str(csv_file),
        'filename': csv_file.name,
        'trip_name': "20230418_DACIA_TEST_TRIP_001",
        'vehicle': "DACIA SPRING"
    }
    
    # Process mock file
    output_dir = tmp_path / "output"
    result = process_devrt_trip(file_info, output_dir=str(output_dir))
    
    # Verify processing return state
    assert result['success'] is True
    assert result['rows_processed'] == 3
    
    # Read the output Parquet file
    output_parquet = output_dir / "20230418_DACIA_TEST_TRIP_001_standardized.parquet"
    assert os.path.exists(output_parquet)
    
    df_out = pd.read_parquet(output_parquet)
    
    # 7. source_file preservation
    assert df_out['source_file'].iloc[0] == csv_file.name
    
    # 8. trip_id creation
    assert df_out['trip_id'].iloc[0] == "20230418_DACIA_TEST_TRIP_001"
    
    # Mapped vehicle ID
    assert df_out['vehicle_id'].iloc[0] == 1
    
    # 1. Timestamp validation (timezone aware UTC)
    assert df_out['timestamp'].dt.tz is not None
    assert df_out['quality_timestamp'].iloc[0] == 1
    
    # 2. SOC range validation quality flagging
    assert df_out['quality_soc'].iloc[0] == 1 # 85.5
    assert df_out['quality_soc'].iloc[1] == 0 # -5.0
    assert df_out['quality_soc'].iloc[2] == 0 # 105.0
    
    # SOH validation quality flagging
    assert df_out['quality_soh'].iloc[0] == 1 # 98.0
    assert df_out['quality_soh'].iloc[1] == 1 # 100.0
    assert df_out['quality_soh'].iloc[2] == 0 # 102.0
    
    # 3. GPS validation
    assert df_out['quality_gps'].iloc[0] == 1 # (43.1, -2.3)
    assert df_out['quality_gps'].iloc[1] == 0 # (95.0, 190.0)
    assert df_out['quality_gps'].iloc[2] == 0 # Missing GPS
    
    # 4. Power conversions
    # Motor power: W -> kW
    assert df_out['motor_power_kw'].iloc[0] == 25.0
    assert df_out['motor_power_kw'].iloc[1] == -5.0
    # Aux power: value * 100 W -> kW
    assert df_out['aux_power_kw'].iloc[0] == 0.2
    assert df_out['aux_power_kw'].iloc[1] == 0.3
    
    # 5. Capacity conversion: Wh -> kWh
    assert df_out['battery_capacity_kwh'].iloc[0] == 33.0
    
    # 6. Regen conversion: W -> kW (sign preserved)
    assert df_out['regen_power_kw'].iloc[0] == -5.0
    assert df_out['regen_power_kw'].iloc[1] == 0.0
    assert pd.isna(df_out['regen_power_kw'].iloc[2])
    
    # Speed and reverse speed flags
    assert df_out['quality_speed'].iloc[0] == 1
    assert df_out['quality_speed'].iloc[2] == 0  # NaN
    assert df_out['quality_reverse_speed'].iloc[0] == 0  # 45.0
    assert df_out['quality_reverse_speed'].iloc[1] == 1  # -10.0 (reverse)
    
    # Distance validation
    assert df_out['quality_distance'].iloc[0] == 1 # 0.0
    assert df_out['quality_distance'].iloc[2] == 0 # -0.2 (negative is invalid)
