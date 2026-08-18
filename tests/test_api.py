"""
STEP 11K - FastAPI endpoint tests.

Covers /health, /model/info, /predict (valid + invalid), output schema, and
that no filesystem paths or stack traces leak into responses. Never touches
DEVRT test evaluation.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def valid_payload():
    return {
        "telemetry": {
            "vehicle_id": "TEST", "timestamp": "2026-08-16T10:30:00Z",
            "soc_pct": 80.0, "battery_capacity_kwh": 40.0, "speed_kmh": 65.0,
            "altitude_m": 150.0, "ambient_temperature_c": 18.0,
            "distance_since_trip_start_km": 12.0,
            "time_since_trip_start_min": 20.0,
            "motor_power_kw": 12.0, "motor_rpm": 4200.0,
            "motor_torque_nm": 60.0, "aux_power_kw": 0.6,
            "regen_power_kw": -1.0,
        },
        "route_terrain": {
            "points": [{"offset_km": i, "altitude_m": 150 + 20 * i}
                       for i in range(26)],
            "source": "DEM_STATIC",
        },
    }


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["model_version"] == "ev-energy-devrt-v1"


def test_model_info_endpoint(client):
    r = client.get("/model/info")
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "ExtraTreesRegressor"
    assert body["feature_count"] == 102
    assert body["target"] == "target_future_energy_kwh_per_km"
    assert body["horizon_km"] == 5
    assert body["dataset"] == "DEVRT"
    assert body["route_aware"] is True
    assert body["model_version"] == "ev-energy-devrt-v1"


def test_predict_valid(client):
    r = client.post("/predict", json=valid_payload())
    assert r.status_code == 200
    body = r.json()
    for key in ("predicted_energy_kwh_per_km", "usable_energy_kwh",
                "expected_range_km", "conservative_range_km",
                "optimistic_range_km", "model_version"):
        assert key in body
    assert body["predicted_energy_kwh_per_km"] > 0
    assert body["expected_range_km"] > 0
    assert body["model_version"] == "ev-energy-devrt-v1"


def test_predict_output_schema(client):
    r = client.post("/predict", json=valid_payload())
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["predicted_energy_kwh_per_km"], float)
    assert isinstance(body["usable_energy_kwh"], float)
    assert isinstance(body["expected_range_km"], float)
    assert body["conservative_range_km"] <= body["expected_range_km"] + 1e-6
    assert body["expected_range_km"] <= body["optimistic_range_km"] + 1e-6
    # no internal objects / no paths in the response
    raw = r.text
    assert "joblib" not in raw
    assert "C:\\" not in raw and "models/" not in raw


def test_predict_invalid_soc(client):
    p = valid_payload()
    p["telemetry"]["soc_pct"] = 150.0
    r = client.post("/predict", json=p)
    assert r.status_code == 422
    assert "soc_pct" in r.text


def test_predict_missing_route_terrain(client):
    p = valid_payload()
    del p["route_terrain"]
    r = client.post("/predict", json=p)
    assert r.status_code == 422
    assert "route_terrain" in r.text


def test_predict_fabricated_terrain(client):
    p = valid_payload()
    p["route_terrain"]["source"] = "FABRICATED"
    r = client.post("/predict", json=p)
    assert r.status_code == 422


def test_predict_naive_timestamp(client):
    p = valid_payload()
    p["telemetry"]["timestamp"] = "2026-08-16T10:30:00"  # no timezone
    r = client.post("/predict", json=p)
    assert r.status_code == 422


def test_predict_invalid_battery(client):
    p = valid_payload()
    p["telemetry"]["battery_capacity_kwh"] = 0.0
    r = client.post("/predict", json=p)
    assert r.status_code == 422


def test_docs_endpoint(client):
    r = client.get("/docs")
    assert r.status_code == 200


def test_openapi_has_three_endpoints(client):
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"].keys())
    assert {"/health", "/model/info", "/predict"} <= paths


def test_no_stack_trace_on_error(client):
    """Errors must not leak internal tracebacks."""
    p = valid_payload()
    p["telemetry"]["soc_pct"] = -1.0
    r = client.post("/predict", json=p)
    assert r.status_code == 422
    assert "Traceback" not in r.text


# ---- STEP 15 live telemetry endpoints ---------------------------------------

def test_live_status_offline(client):
    """/live/status reports offline when no source is connected."""
    client.post("/live/disconnect")
    r = client.get("/live/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "offline"
    assert body["telemetry_connected"] is False


def test_live_connect_unknown_provider(client):
    """Unknown provider returns HTTP 400 (not 200)."""
    r = client.post("/live/connect", params={"provider": "bogus"})
    assert r.status_code == 400
    assert "Unknown telemetry provider" in r.json()["detail"]


def test_live_connect_then_disconnect(client):
    """Connect to a valid provider then disconnect."""
    r = client.post("/live/connect", params={"provider": "can"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("connected", "connection_failed")
    assert body["provider"] == "can"

    r = client.post("/live/disconnect")
    assert r.status_code == 200
    assert r.json()["status"] == "disconnected"

    r = client.get("/live/status")
    assert r.json()["status"] == "offline"


def test_live_telemetry_returns_bounded_info(client):
    """/live/telemetry returns signal info without raw values."""
    r = client.get("/live/telemetry")
    assert r.status_code == 200
    body = r.json()
    assert "signals" in body
    assert "count" in body


def test_live_connect_disconnect_concurrent(client):
    """Concurrent connect/disconnect must not raise and must end consistent."""
    import asyncio

    async def hammer():
        loop = asyncio.get_event_loop()
        results = await asyncio.gather(
            loop.run_in_executor(
                None, lambda: client.post(
                    "/live/connect", params={"provider": "can"})),
            loop.run_in_executor(
                None, lambda: client.post("/live/disconnect")),
            loop.run_in_executor(
                None, lambda: client.get("/live/status")),
            return_exceptions=True,
        )
        for res in results:
            assert not isinstance(res, Exception), f"unexpected: {res!r}"

    asyncio.run(hammer())

    r = client.get("/live/status")
    assert r.status_code == 200