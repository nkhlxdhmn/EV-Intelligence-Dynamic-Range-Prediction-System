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


def test_live_prediction_end_to_end(client, monkeypatch):
    """/live/prediction builds a real prediction from real (sim) telemetry.

    The provider is honestly labeled SIMULATOR; the endpoint must consume the
    reader's latest signals (no fabrication) and produce a real model output.
    """
    import time

    import numpy as np

    from api.main import AppState
    from src.inference.feature_builder import RouteTerrain, RouteTerrainProvider
    from src.inference.service import PredictionService
    from src.simulator.scenario import random_scenario
    from src.simulator.simulator import SimulationEngine
    from src.telemetry.base import TelemetrySignal
    from src.telemetry.buffer import RollingBuffer
    from src.telemetry.reader import TelemetryReader

    class _SimSource:
        """Adapters a SimulationEngine as a (honestly labeled) telemetry source."""

        def __init__(self, sim):
            self.sim = sim
            self._connected = False

        def connect(self):
            self._connected = True
            return True

        def disconnect(self):
            self._connected = False

        def read(self):
            if not self._connected:
                return None
            snap = self.sim.snapshot()
            self.sim.step()
            now = time.time()
            return [
                TelemetrySignal("soc_pct", snap["soc_pct"], "%", now),
                TelemetrySignal("vehicle_speed_kmh", snap["speed_kmh"], "km/h", now),
                TelemetrySignal("altitude_m", snap["altitude_m"], "m", now),
                TelemetrySignal("ambient_temperature_c",
                                snap["ambient_temperature_c"], "C", now),
                TelemetrySignal("distance_since_trip_start_km",
                                snap["distance_since_trip_start_km"], "km", now),
                TelemetrySignal("time_since_trip_start_min",
                                snap["time_since_trip_start_min"], "min", now),
            ]

        def health(self):
            return {"connected": self._connected, "provider": "SIMULATOR"}

        def available_signals(self):
            return ["soc_pct", "vehicle_speed_kmh", "altitude_m",
                    "ambient_temperature_c", "distance_since_trip_start_km",
                    "time_since_trip_start_min"]

    class FakeTerrain(RouteTerrainProvider):
        def get_upcoming_terrain(self, d, a, lookahead_km=5.0):
            offs = np.linspace(0, lookahead_km, 51)
            alts = np.full(51, float(a)) + 5.0 * np.sin(offs * 3.0)
            return RouteTerrain(offs, alts, source="DEM_TEST")

    # Provider-backed service so the endpoint is route-aware.
    svc = PredictionService(terrain_provider=FakeTerrain())
    monkeypatch.setattr(AppState, "service", svc)

    scenario = random_scenario(seed=7)
    sim = SimulationEngine(scenario)
    sim.step()

    buffer = RollingBuffer(max_samples=200)
    reader = TelemetryReader(_SimSource(sim), buffer, interval_s=60.0)
    reader.source.connect()
    reader.read_once()
    reader.read_once()  # two real samples -> latest + causal history

    client.post("/live/disconnect")
    AppState.telemetry_reader = reader
    AppState.telemetry_source = reader.source
    AppState.telemetry_buffer = buffer

    r = client.post("/live/prediction")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True, body
    pred = body["prediction"]
    assert pred["predicted_energy_kwh_per_km"] > 0
    assert pred["expected_range_km"] > 0
    assert body["provenance"]["source"] == "LIVE"
    assert body["provenance"]["provider"] == "SIMULATOR"
    assert body["status"] in ("OK", "DEGRADED")


def test_live_prediction_after_disconnect(client, monkeypatch):
    """/live/prediction is OFFLINE (not fabricated) after disconnect."""
    client.post("/live/disconnect")
    r = client.post("/live/prediction")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["status"] == "OFFLINE"


# ---- STEP 16 simulator demo endpoints ---------------------------------------

def test_simulator_reset_and_step(client):
    """Simulator reset returns a labeled SIMULATOR payload; step advances."""
    from api.main import AppState

    AppState.simulator_engine = None
    AppState.simulator_seed = None

    r = client.post("/simulator/reset", params={"seed": 42})
    assert r.status_code == 200
    body = r.json()
    assert body["simulator"] is True
    assert body["source"] == "SIMULATOR"
    assert body["telemetry"]["soc_pct"] > 0
    assert body["route_terrain"]["source"] == "SIMULATOR_ROUTE"
    d0 = body["telemetry"]["distance_since_trip_start_km"]

    r = client.post("/simulator/step", params={"n_steps": 10})
    assert r.status_code == 200
    d1 = r.json()["telemetry"]["distance_since_trip_start_km"]
    assert d1 > d0


def test_simulator_deterministic_same_seed(client):
    """Same seed -> same scenario_id and identical initial state."""
    from api.main import AppState

    AppState.simulator_engine = None
    AppState.simulator_seed = None
    a = client.post("/simulator/reset", params={"seed": 7}).json()
    AppState.simulator_engine = None
    AppState.simulator_seed = None
    b = client.post("/simulator/reset", params={"seed": 7}).json()
    assert a["scenario_id"] == b["scenario_id"]
    assert a["telemetry"]["distance_since_trip_start_km"] == \
        b["telemetry"]["distance_since_trip_start_km"]


def test_simulator_predict_roundtrip(client):
    """A simulator snapshot + terrain predicts through /predict (demo path)."""
    from api.main import AppState

    AppState.simulator_engine = None
    AppState.simulator_seed = None
    s = client.post("/simulator/reset", params={"seed": 3, "n_steps": 4}).json()
    payload = {
        "telemetry": s["telemetry"],
        "route_terrain": s["route_terrain"],
        "reserve_soc_pct": 10.0,
    }
    r = client.post("/predict", json=payload)
    assert r.status_code == 200
    pred = r.json()
    assert pred["predicted_energy_kwh_per_km"] > 0
    assert pred["expected_range_km"] > 0
    assert pred["status"] in ("OK", "DEGRADED")


def test_simulator_invalid_params(client):
    """Invalid simulator parameters return HTTP 400."""
    r = client.post("/simulator/reset", params={"seed": -1})
    assert r.status_code == 400
    r = client.post("/simulator/step", params={"n_steps": 0})
    assert r.status_code == 400
    r = client.post("/simulator/step", params={"n_steps": 500})
    assert r.status_code == 400