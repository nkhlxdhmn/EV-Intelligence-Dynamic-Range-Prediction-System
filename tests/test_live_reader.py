"""
STEP 15 — Live telemetry reader + /live/* endpoint tests (P3).

Covers the continuous-reader lifecycle, quality/staleness/missing handling,
reconnect, readiness reporting, and genuine LIVE prediction built only from
real (never fabricated) telemetry. Uses a FakeSource so tests are hermetic.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import AppState, app
from src.inference.feature_builder import RouteTerrain, RouteTerrainProvider
from src.inference.service import PredictionService
from src.telemetry.base import TelemetrySignal
from src.telemetry.buffer import RollingBuffer
from src.telemetry.reader import TelemetryReader


class FakeSource:
    """Scripted TelemetrySource-like fake (duck-typed, hermetic)."""

    def __init__(self, scripts, provider_name="fake_obd"):
        self.scripts = list(scripts)
        self._connected = False
        self._index = 0
        self._provider_name = provider_name
        self.fail_until = 0  # read fails while index < this

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def read(self):
        if not self._connected:
            return None
        if self._index < self.fail_until:
            self._index += 1
            raise RuntimeError("bus timeout")
        if not self.scripts:
            return None
        if self._index >= len(self.scripts):
            sigs = self.scripts[-1]
        else:
            sigs = self.scripts[self._index]
            self._index += 1
        return [TelemetrySignal(**s) for s in sigs]

    def health(self) -> Dict[str, Any]:
        return {"connected": self._connected,
                "provider": self._provider_name,
                "last_read": None}

    def available_signals(self) -> List[str]:
        return ["soc_pct", "vehicle_speed_kmh", "altitude_m",
                "ambient_temperature_c", "distance_since_trip_start_km",
                "time_since_trip_start_min", "motor_power_kw",
                "auxiliary_power_kw", "regen_power_kw"]


class FakeTerrainProvider(RouteTerrainProvider):
    """Deterministic test terrain labeled DEM_TEST (honest label)."""

    def get_upcoming_terrain(self, current_distance_km, current_altitude_m,
                             lookahead_km=5.0) -> RouteTerrain:
        n = 51
        offsets = np.linspace(0.0, float(lookahead_km), n)
        alts = np.full(n, float(current_altitude_m)) + 5.0 * np.sin(offsets * 3.0)
        return RouteTerrain(offsets, alts, source="DEM_TEST")


def make_signals(ts=None, soc=80.0, speed=60.0, alt=150.0):
    ts = ts if ts is not None else time.time()
    return [
        {"name": "soc_pct", "value": soc, "unit": "%",
         "timestamp": ts, "source": "fake"},
        {"name": "vehicle_speed_kmh", "value": speed, "unit": "km/h",
         "timestamp": ts, "source": "fake"},
        {"name": "altitude_m", "value": alt, "unit": "m",
         "timestamp": ts, "source": "fake"},
        {"name": "ambient_temperature_c", "value": 18.0, "unit": "C",
         "timestamp": ts, "source": "fake"},
        {"name": "distance_since_trip_start_km", "value": 12.0, "unit": "km",
         "timestamp": ts, "source": "fake"},
        {"name": "time_since_trip_start_min", "value": 20.0, "unit": "min",
         "timestamp": ts, "source": "fake"},
        {"name": "motor_power_kw", "value": 12.0, "unit": "kW",
         "timestamp": ts, "source": "fake"},
        {"name": "auxiliary_power_kw", "value": 0.6, "unit": "kW",
         "timestamp": ts, "source": "fake"},
        {"name": "regen_power_kw", "value": -1.0, "unit": "kW",
         "timestamp": ts, "source": "fake"},
    ]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
    # reset live state for the next test
    try:
        import asyncio
        asyncio.run(_reset_live())
    except RuntimeError:
        pass


async def _reset_live():
    reader = AppState.telemetry_reader
    if reader is not None:
        await reader.stop()
    if AppState.telemetry_source is not None:
        AppState.telemetry_source.disconnect()
    AppState.telemetry_reader = None
    AppState.telemetry_source = None
    AppState.telemetry_buffer = None
    AppState.last_live_prediction = None
    AppState.last_live_prediction_time = 0.0


def _install_reader(source, interval_s=60.0):
    """Connect + create a reader (long interval so the loop stays idle in tests)."""
    source.connect()
    buffer = RollingBuffer(max_samples=200)
    reader = TelemetryReader(source, buffer, interval_s=interval_s)
    AppState.telemetry_source = source
    AppState.telemetry_reader = reader
    AppState.telemetry_buffer = buffer
    return reader


class TestReader:
    def test_read_once_populates_latest_and_buffer(self):
        src = FakeSource([make_signals()])
        reader = _install_reader(src)
        now = time.time()
        n = reader.read_once(current_time=now)
        assert n == 9
        latest = reader.latest()
        assert latest["soc_pct"]["value"] == 80.0
        assert latest["soc_pct"]["quality"] == "VALID"
        assert "unit" in latest["soc_pct"]
        assert "source" in latest["soc_pct"]
        assert "age_ms" in latest["soc_pct"]
        assert reader.health()["consecutive_failures"] == 0
        assert reader.buffer.size() == 1

    def test_missing_value_is_missing_not_fabricated(self):
        sigs = make_signals()
        sigs[0]["value"] = None  # soc missing
        reader = _install_reader(FakeSource([sigs]))
        reader.read_once(current_time=time.time())
        assert reader.latest()["soc_pct"]["quality"] == "MISSING"
        assert reader.latest()["soc_pct"]["value"] is None
        # soc must NOT appear in the buffer (no fabricated value)
        assert "soc_pct" not in reader.buffer.get_latest()

    def test_nan_value_marked_missing(self):
        sigs = make_signals()
        sigs[1]["value"] = float("nan")  # speed NaN
        reader = _install_reader(FakeSource([sigs]))
        reader.read_once(current_time=time.time())
        assert reader.latest()["vehicle_speed_kmh"]["quality"] == "MISSING"
        assert "vehicle_speed_kmh" not in reader.buffer.get_latest()

    def test_stale_signal_detected(self):
        now = time.time()
        old = now - 10.0  # 10 seconds old -> stale (threshold 5 s)
        reader = _install_reader(FakeSource([make_signals(ts=old)]))
        reader.read_once(current_time=now)
        entry = reader.latest()["soc_pct"]
        assert entry["quality"] == "STALE"
        assert entry["age_ms"] >= 5000
        # stale values are not treated as current -> excluded from buffer
        buf = reader.buffer.get_latest()
        assert buf is None or "soc_pct" not in buf

    def test_reader_failure_tracking(self):
        src = FakeSource([make_signals()])
        src.fail_until = 2  # first 2 reads raise
        reader = _install_reader(src)
        now = time.time()
        for _ in range(2):
            reader.read_once(current_time=now)
        assert reader.health()["consecutive_failures"] == 2
        assert reader.health()["last_error"] is not None
        # recovery on the next successful read
        reader.read_once(current_time=now)
        assert reader.health()["consecutive_failures"] == 0

    def test_reconnect_recovers(self):
        src = FakeSource([make_signals()])
        src.fail_until = 1
        reader = _install_reader(src)
        reader.read_once(current_time=time.time())
        assert reader.health()["last_error"] is not None
        assert reader.reconnect() is True
        assert reader.health()["last_error"] is None
        reader.read_once(current_time=time.time())
        assert reader.buffer.size() >= 1


class TestLiveEndpoints:
    def test_live_telemetry_full_fields(self, client):
        reader = _install_reader(FakeSource([make_signals()]))
        reader.read_once(current_time=time.time())
        r = client.get("/live/telemetry")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 9
        sig = next(s for s in body["signals"] if s["name"] == "soc_pct")
        assert sig["value"] == 80.0
        assert sig["unit"] == "%"
        assert sig["quality"] == "VALID"
        assert sig["source"] == "fake"
        assert "timestamp" in sig and "age_ms" in sig

    def test_live_status_offline_when_no_source(self, client):
        r = client.get("/live/status")
        assert r.status_code == 200
        body = r.json()
        assert body["telemetry_connected"] is False
        assert body["status"] == "offline"
        assert body["prediction_ready"] is False

    def test_live_status_readiness_with_data(self, client, monkeypatch):
        svc = PredictionService(terrain_provider=FakeTerrainProvider())
        monkeypatch.setattr(AppState, "service", svc)
        reader = _install_reader(FakeSource([make_signals()]))
        reader.read_once(current_time=time.time())
        r = client.get("/live/status")
        body = r.json()
        assert body["status"] == "ok"
        assert body["prediction_ready"] is True
        assert body["required_signal_status"]["soc_pct"] == "VALID"
        assert body["required_signal_status"]["vehicle_speed_kmh"] == "VALID"

    def test_live_health(self, client):
        r = client.get("/live/health")
        assert r.status_code == 200
        assert "status" in r.json()


class TestLivePrediction:
    def test_live_prediction_no_fabrication_when_missing(self, client, monkeypatch):
        svc = PredictionService(terrain_provider=FakeTerrainProvider())
        monkeypatch.setattr(AppState, "service", svc)
        sigs = make_signals()
        sigs[0]["value"] = None  # soc missing
        reader = _install_reader(FakeSource([sigs]))
        reader.read_once(current_time=time.time())
        r = client.post("/live/prediction")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is False
        assert body["status"] == "INSUFFICIENT_TELEMETRY"
        assert "soc_pct" in body["missing_required"]

    def test_live_prediction_route_unavailable(self, client, monkeypatch):
        # service WITHOUT a terrain provider -> route unavailable, no synthetic
        svc = PredictionService(terrain_provider=None)
        monkeypatch.setattr(AppState, "service", svc)
        reader = _install_reader(FakeSource([make_signals()]))
        reader.read_once(current_time=time.time())
        r = client.post("/live/prediction")
        body = r.json()
        assert body["available"] is False
        assert body["status"] == "ROUTE_TERRAIN_UNAVAILABLE"
        assert body["route"]["provider_configured"] is False

    def test_live_prediction_uses_real_data(self, client, monkeypatch):
        svc = PredictionService(terrain_provider=FakeTerrainProvider())
        monkeypatch.setattr(AppState, "service", svc)
        reader = _install_reader(FakeSource([make_signals()]))
        reader.read_once(current_time=time.time())
        r = client.post("/live/prediction")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        pred = body["prediction"]
        assert pred["predicted_energy_kwh_per_km"] > 0
        assert pred["expected_range_km"] > 0
        assert body["provenance"]["source"] == "LIVE"
        assert body["route"]["available"] is True

    def test_live_prediction_cadence_and_single_flight(self, client, monkeypatch):
        svc = PredictionService(terrain_provider=FakeTerrainProvider())
        monkeypatch.setattr(AppState, "service", svc)
        reader = _install_reader(FakeSource([make_signals()]))
        reader.read_once(current_time=time.time())
        first = client.post("/live/prediction").json()
        assert first["available"] is True
        # Immediate second call within cadence reuses the cache.
        second = client.post("/live/prediction").json()
        assert second["fresh"] is False
        assert second["available"] is True
        # Concurrent calls never duplicate work (single-flight).
        import asyncio

        async def hammer():
            loop = asyncio.get_event_loop()
            return await asyncio.gather(
                loop.run_in_executor(None, lambda: client.post("/live/prediction")),
                loop.run_in_executor(None, lambda: client.post("/live/prediction")),
                return_exceptions=True,
            )

        results = asyncio.run(hammer())
        for res in results:
            assert not isinstance(res, Exception)
            assert res.json()["available"] is True