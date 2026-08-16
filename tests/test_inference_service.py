"""
STEP 11K - Prediction Service tests.

Tests the full service pipeline: valid prediction, invalid inputs, model
loading, range calculation, terrain requirement. Never touches DEVRT test
evaluation and never loads raw DEVRT data.
"""

from datetime import datetime, timezone

import pytest

from src.inference.feature_builder import SyntheticRouteTerrainProvider
from src.inference.range_estimator import RangeEstimator
from src.inference.schemas import (
    PastWindowSample,
    PredictionRequest,
    RouteTerrainInput,
    TelemetrySnapshot,
    TerrainPoint,
)
from src.inference.service import (
    InferenceError,
    ModelLoadError,
    PredictionService,
    TerrainUnavailableError,
)

CAPACITY = 40.0


def make_terrain():
    pts = [TerrainPoint(offset_km=i, altitude_m=150 + 20 * i) for i in range(26)]
    return RouteTerrainInput(points=pts, source="DEM_STATIC")


def make_snapshot(**over):
    base = dict(
        vehicle_id="TEST", timestamp=datetime(2026, 8, 16, 10, 30, tzinfo=timezone.utc),
        soc_pct=80.0, battery_capacity_kwh=CAPACITY, speed_kmh=65.0,
        altitude_m=150.0, ambient_temperature_c=18.0,
        distance_since_trip_start_km=12.0, time_since_trip_start_min=20.0,
        motor_power_kw=12.0, motor_rpm=4200.0, motor_torque_nm=60.0,
        aux_power_kw=0.6, regen_power_kw=-1.0,
    )
    base.update(over)
    return TelemetrySnapshot(**base)


def make_request(**over):
    base = dict(telemetry=make_snapshot(), route_terrain=make_terrain())
    base.update(over)
    return PredictionRequest(**base)


@pytest.fixture(scope="module")
def service():
    return PredictionService(terrain_provider=SyntheticRouteTerrainProvider())


def test_model_loading():
    """Model + preprocessor + metadata load once at startup."""
    svc = PredictionService()
    assert svc.model is not None
    assert svc.preprocessor is not None
    assert svc.metadata.model_version == "ev-energy-devrt-v1"
    assert svc.metadata.feature_count() == 102


def test_valid_prediction(service):
    """End-to-end valid prediction returns all required fields."""
    resp = service.predict(make_request())
    assert resp.predicted_energy_kwh_per_km > 0
    assert resp.usable_energy_kwh == pytest.approx(CAPACITY * 0.7)  # 80% - 10% reserve
    assert resp.expected_range_km > 0
    assert resp.conservative_range_km is not None
    assert resp.optimistic_range_km is not None
    assert resp.model_version == "ev-energy-devrt-v1"
    assert resp.route_terrain_source == "SYNTHETIC_DEMO"


def test_prediction_with_terrain_body(service):
    """Without a provider, the validated request terrain is used."""
    svc = PredictionService()  # no provider -> request terrain path
    resp = svc.predict(make_request())
    assert resp.predicted_energy_kwh_per_km > 0
    assert resp.route_terrain_source == "DEM_STATIC"


def test_invalid_soc():
    """Invalid SOC is rejected at schema level with a clean ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_snapshot(soc_pct=150.0)
    with pytest.raises(ValidationError):
        make_snapshot(soc_pct=-5.0)
    with pytest.raises(ValidationError):
        make_snapshot(soc_pct=float("nan"))


def test_invalid_battery_capacity():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_snapshot(battery_capacity_kwh=0.0)
    with pytest.raises(ValidationError):
        make_snapshot(battery_capacity_kwh=-1.0)


def test_invalid_speed():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_snapshot(speed_kmh=99999.0)


def test_invalid_timestamp_naive():
    """Timestamp must be timezone-aware."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_snapshot(timestamp=datetime(2026, 8, 16, 10, 30))


def test_missing_route_terrain():
    svc = PredictionService()
    req = make_request()
    req.route_terrain.points = []
    with pytest.raises(TerrainUnavailableError):
        svc.predict(req)


def test_invalid_terrain():
    """Out-of-range / non-finite terrain is rejected at schema level."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RouteTerrainInput(
            points=[TerrainPoint(offset_km=0.0, altitude_m=1e9),
                    TerrainPoint(offset_km=1.0, altitude_m=2e9)],
            source="DEM_STATIC")
    with pytest.raises(ValidationError):
        RouteTerrainInput(points=[TerrainPoint(offset_km=0.0, altitude_m=float("nan"))],
                          source="DEM_STATIC")


def test_fabricated_terrain_source_rejected():
    """Source labeled fabricated/synthetic must be rejected by schema."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RouteTerrainInput(
            points=[TerrainPoint(offset_km=0.0, altitude_m=100.0),
                    TerrainPoint(offset_km=1.0, altitude_m=110.0)],
            source="FABRICATED")


def test_range_calculation_consistency(service):
    """Range values must be consistent: conservative <= expected <= optimistic."""
    resp = service.predict(make_request())
    assert resp.conservative_range_km <= resp.expected_range_km + 1e-6
    assert resp.expected_range_km <= resp.optimistic_range_km + 1e-6


def test_range_estimator_unit():
    est = RangeEstimator(reserve_soc_pct=10.0)
    r = est.estimate_range(40.0, 80.0, 0.20)
    assert r["usable_energy_kwh"] == pytest.approx(28.0)
    assert r["expected_range_km"] == pytest.approx(140.0)
    band = est.estimate_range_band(40.0, 80.0, 0.20, -0.03, 0.03)
    assert band["conservative_range_km"] <= band["expected_range_km"] <= band["optimistic_range_km"]


def test_past_window_used(service):
    """Providing a past window still yields a valid prediction."""
    from datetime import timedelta
    t0 = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
    past = [
        PastWindowSample(
            timestamp=t0 + timedelta(minutes=i),
            distance_km=10.0 + 0.1 * i, altitude_m=120.0 + 1.5 * i,
            speed_kmh=60.0, ambient_temperature_c=18.0,
            motor_power_kw=10.0, aux_power_kw=0.5, regen_power_kw=0.0)
        for i in range(20)
    ]
    resp = service.predict(make_request(past_window=past))
    assert resp.predicted_energy_kwh_per_km > 0


def test_model_load_failure(tmp_path, monkeypatch):
    """Model loading failure raises ModelLoadError."""
    from src.inference import service as svc_mod
    monkeypatch.setattr(svc_mod.joblib, "load", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(ModelLoadError):
        PredictionService(models_dir=tmp_path)