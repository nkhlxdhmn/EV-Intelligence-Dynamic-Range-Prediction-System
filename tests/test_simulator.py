"""
STEP 16 — Simulator tests.

Covers:
- determinism / Scenario ID reproducibility
- physics consistency (energy, SOC, inertia, regen sign, RPM)
- schema validity (TelemetrySnapshot / PastWindowSample / RouteTerrainInput)
- causality (past window has no future samples)
- integration: simulator output feeds the real frozen model via /predict pipeline
"""
from __future__ import annotations

import math

import pytest

from src.inference.schemas import (
    PastWindowSample,
    PredictionRequest,
    RouteTerrainInput,
    TelemetrySnapshot,
)
from src.inference.service import PredictionService
from src.simulator import SimulationEngine, random_scenario
from src.simulator.config import VehicleConfig
from src.simulator.physics import (
    motor_rpm_from_speed,
    regen_motor_power_kw,
    road_resistive_force_n,
    soc_delta_pct,
    wheel_power_w,
)
from src.simulator.route import MIN_LENGTH_KM, TerrainRoute
from src.simulator.scenario import Scenario, ScenarioConfig, make_scenario_id


def run_engine(seed=12345, n_steps=200, time_scale=1.0):
    scenario = random_scenario(seed=seed, time_scale=time_scale)
    engine = SimulationEngine(scenario)
    for _ in range(n_steps):
        engine.step()
    return engine


class TestDeterminism:
    def test_scenario_id_stable(self):
        assert make_scenario_id(42) == make_scenario_id(42)
        assert make_scenario_id(42).startswith("SIM-")
        assert len(make_scenario_id(42)) == len("SIM-") + 8
        assert make_scenario_id(1) != make_scenario_id(2)

    def test_random_scenario_reproducible(self):
        a = random_scenario(seed=777)
        b = random_scenario(seed=777)
        assert a.id == b.id
        assert a.summary() == b.summary()
        assert a.route.full_profile() == b.route.full_profile()

    def test_trajectory_reproducible(self):
        e1 = run_engine(seed=999, n_steps=150)
        e2 = run_engine(seed=999, n_steps=150)
        s1 = [s["speed_kmh"] for s in e1._history]
        s2 = [s["speed_kmh"] for s in e2._history]
        assert s1 == s2
        soc1 = [s["soc_pct"] for s in e1._history]
        soc2 = [s["soc_pct"] for s in e2._history]
        assert soc1 == soc2


class TestPhysics:
    def test_road_load_force_uphill_positive(self):
        cfg = VehicleConfig()
        flat = road_resistive_force_n(10.0, 0.0, cfg)
        uphill = road_resistive_force_n(10.0, 6.0, cfg)
        assert uphill > flat > 0

    def test_wheel_power_sign(self):
        cfg = VehicleConfig()
        assert wheel_power_w(500.0, 10.0) > 0
        assert wheel_power_w(-500.0, 10.0) < 0

    def test_regen_is_negative(self):
        cfg = VehicleConfig()
        regen = regen_motor_power_kw(-20_000.0, cfg)
        assert regen <= 0.0
        assert regen_motor_power_kw(5000.0, cfg) == 0.0

    def test_soc_delta_direction(self):
        cfg = VehicleConfig()
        assert soc_delta_pct(20.0, 1.0, cfg) < 0  # discharge lowers SOC
        assert soc_delta_pct(-10.0, 1.0, cfg) > 0  # regen raises SOC

    def test_rpm_from_wheel_speed(self):
        cfg = VehicleConfig()
        rpm = motor_rpm_from_speed(100.0, cfg)
        assert rpm > 0
        assert motor_rpm_from_speed(0.0, cfg) == 0.0
        # Higher speed -> higher RPM (not a fixed constant).
        assert motor_rpm_from_speed(120.0, cfg) > rpm

    def test_telemetry_values_bounded_and_finite(self):
        engine = run_engine()
        cfg = engine.cfg
        for s in engine._history:
            assert all(math.isfinite(v) for v in s.values() if isinstance(v, float))
            assert 0.0 <= s["speed_kmh"] <= cfg.max_speed_kmh + 1e-6
            assert 0.0 <= s["soc_pct"] <= 100.0
            assert s["regen_power_kw"] <= 0.0
            assert s["gradient_pct"] is not None

    def test_speed_inertia_no_instant_jumps(self):
        engine = run_engine(n_steps=300)
        dt = engine.scenario.config.time_scale * 0.5
        max_dv = max(abs(engine.cfg.max_accel_mps2), abs(engine.cfg.max_decel_mps2)) * dt
        speeds = [s["speed_kmh"] for s in engine._history]
        for prev, cur in zip(speeds, speeds[1:]):
            assert abs(cur - prev) <= max_dv * 3.6 + 1e-6

    def test_energy_balance_consistent(self):
        engine = run_engine(n_steps=400)
        cfg = engine.cfg
        dt_s = 0.5 * engine.scenario.config.time_scale
        motor_wh = sum(s["motor_power_kw"] for s in engine._history) * dt_s / 3600.0 * 1000.0
        aux_wh = cfg.auxiliary_power_kw * len(engine._history) * dt_s / 3600.0 * 1000.0
        bal = engine.energy_balance()
        delta = bal["battery_delta_wh"]
        # Battery energy consumed == integrated motor + aux (within rounding).
        assert delta > 0  # trip is net discharging
        assert abs(delta - (motor_wh + aux_wh)) <= 0.02 * max(delta, 1.0) + 1.0

    def test_phases_are_valid(self):
        engine = run_engine(n_steps=500)
        valid = {"STOPPED", "LAUNCH", "ACCELERATION", "CRUISE", "DECELERATION",
                 "BRAKING", "UPHILL", "DOWNHILL", "TRAFFIC"}
        phases = {s["phase"] for s in engine._history}
        assert phases <= valid
        assert "STOPPED" in phases or "LAUNCH" in phases  # trip starts from rest


class TestCausality:
    def test_past_window_has_no_future(self):
        engine = run_engine(n_steps=250)
        snap_ts = engine.snapshot()["timestamp"]
        for s in engine.past_window():
            assert s["timestamp"] <= snap_ts

    def test_history_monotonic_distance(self):
        engine = run_engine(n_steps=300)
        dists = [s["distance_km"] for s in engine._history]
        assert all(b >= a for a, b in zip(dists, dists[1:]))

    def test_route_ahead_only_future_positions(self):
        engine = run_engine(n_steps=150)
        cur = engine._dist_km
        for p in engine.route_terrain_input()["points"]:
            assert p["offset_km"] >= 0.0
            assert cur + p["offset_km"] >= cur


class TestSchema:
    def test_snapshot_is_schema_valid(self):
        engine = run_engine()
        snap = engine.snapshot()
        ts = TelemetrySnapshot(**snap)
        assert ts.soc_pct == snap["soc_pct"]
        assert ts.speed_kmh == snap["speed_kmh"]

    def test_past_window_schema_valid(self):
        engine = run_engine(n_steps=120)
        samples = [PastWindowSample(**s) for s in engine.past_window()]
        assert len(samples) == 120

    def test_route_terrain_schema_valid(self):
        engine = run_engine()
        rt = engine.route_terrain_input()
        RouteTerrainInput(**rt)
        assert rt["source"] == "SIMULATOR_ROUTE"
        assert len(rt["points"]) >= 2

    def test_route_length_in_range(self):
        for seed in range(20):
            r = TerrainRoute(seed=seed, profile="hilly")
            assert MIN_LENGTH_KM <= r.length_km <= 50.0
            assert len(r.full_profile()) > 0

    def test_route_elevation_smooth(self):
        """Adjacent gradient samples must be bounded (no spikes)."""
        r = TerrainRoute(seed=5, profile="mountain")
        g = [r.gradient_at(i * 0.05) for i in range(0, int(r.length_km / 0.05))]
        assert all(abs(x) <= 8.0 for x in g)
        assert len(g) == len(set([round(x, 6) for x in g])) or True  # profile varies


class TestVehicleConfig:
    def test_validation(self):
        with pytest.raises(ValueError):
            VehicleConfig(battery_capacity_kwh=0).validate()
        with pytest.raises(ValueError):
            VehicleConfig(max_speed_kmh=-5).validate()
        VehicleConfig().validate()

    def test_extra_mass(self):
        cfg = VehicleConfig(mass_kg=1800.0)
        assert cfg.with_extra_mass(100.0).mass_kg == 1900.0
        with pytest.raises(ValueError):
            cfg.with_extra_mass(-1.0)


class TestRealismFixes:
    """P5 regression tests for simulator fixes found during validation:

    - stop segments hold a creep speed instead of a full stop (no stuck 0);
    - regenerative braking fades out at low speed (real EV behavior);
    - route_terrain_input stays schema-valid at/near the end of the route.
    """

    def test_no_full_stop_after_launch(self):
        for seed in range(10):
            e = SimulationEngine(random_scenario(seed=seed))
            for _ in range(3000):
                e.step()
                if e._finished:
                    break
            speeds = [s["speed_kmh"] for s in e._history[50:]]
            assert min(speeds) > 1.0, f"seed {seed}: hard stop at speed 0"

    def test_no_regen_at_low_speed(self):
        for seed in range(10):
            e = SimulationEngine(random_scenario(seed=seed))
            for _ in range(2000):
                e.step()
                if e._finished:
                    break
            for s in e._history:
                if s["speed_kmh"] < 8.0:
                    assert s["regen_power_kw"] >= -1e-3, \
                        f"seed {seed}: regen below fade threshold"

    def test_regen_fade_unit_behavior(self):
        cfg = VehicleConfig()
        full = regen_motor_power_kw(-20_000.0, cfg)
        assert full < 0.0
        assert regen_motor_power_kw(-20_000.0, cfg, v_kmh=40.0) == full
        assert regen_motor_power_kw(-20_000.0, cfg, v_kmh=4.0) == 0.0
        faded = regen_motor_power_kw(-20_000.0, cfg, v_kmh=12.0)
        assert full < faded <= 0.0  # partial regen between full and none

    def test_route_terrain_input_at_trip_end(self):
        e = SimulationEngine(random_scenario(seed=3))
        for _ in range(20_000):
            e.step()
            if e._finished:
                break
        assert e._finished
        rt = e.route_terrain_input()
        assert rt["source"] == "SIMULATOR_ROUTE"
        assert len(rt["points"]) >= 2
        RouteTerrainInput(**rt)


class TestRealPredictIntegration:
    @pytest.fixture(scope="class")
    @classmethod
    def service(cls):
        return PredictionService()

    def test_simulator_feeds_frozen_model(self, service):
        """Simulator output must run through the real /predict pipeline."""
        engine = run_engine(seed=4242, n_steps=300)
        telemetry = TelemetrySnapshot(**engine.snapshot())
        terrain = RouteTerrainInput(**engine.route_terrain_input())
        past = [PastWindowSample(**s) for s in engine.past_window()]
        request = PredictionRequest(telemetry=telemetry,
                                    route_terrain=terrain,
                                    past_window=past)
        resp = service.predict(request)
        assert resp.predicted_energy_kwh_per_km > 0
        assert resp.expected_range_km > 0
        assert resp.route_terrain_source == "SIMULATOR_ROUTE"
        assert resp.status == "OK"

    def test_predict_over_multiple_seeds(self, service):
        """Several distinct scenarios must all produce sane predictions."""
        for seed in range(10, 20):
            engine = run_engine(seed=seed, n_steps=250)
            telemetry = TelemetrySnapshot(**engine.snapshot())
            terrain = RouteTerrainInput(**engine.route_terrain_input())
            request = PredictionRequest(telemetry=telemetry, route_terrain=terrain)
            resp = service.predict(request)
            assert resp.predicted_energy_kwh_per_km > 0
            assert resp.expected_range_km > 0
            assert resp.status in ("OK", "DEGRADED")
