"""
Deterministic EV driving simulation engine.

Longitudinal simulation with:
- speed inertia (bounded acceleration, no instant speed jumps)
- physical road load + inertial force -> wheel power -> motor/regen power
- torque from force assumptions, RPM from wheel speed (not a fixed constant)
- regenerative braking during deceleration and downhill driving
- SOC coupled to battery energy (with regen recovery)
- battery temperature responding to load
- driving phases (stopped/launch/accel/cruise/decel/brake/uphill/downhill/traffic)

Outputs:
- snapshot(): current telemetry (schema-ready, source labeled SIMULATOR)
- past_window(): causal history (past samples only, never future)
- route_terrain_input(): upcoming smooth terrain for the current position
- step(): advance simulated time by BASE_DT_S * time_scale per call

Determinism: all state evolves from the scenario seed; timestamps derive from
a fixed epoch + simulated elapsed time, so replaying a Scenario ID reproduces
the identical trajectory.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.simulator.config import VehicleConfig
from src.simulator.physics import (
    battery_current_a,
    battery_power_kw,
    battery_temp_delta,
    clamp,
    motor_power_kw,
    motor_rpm_from_speed,
    motor_torque_nm,
    regen_motor_power_kw,
    soc_delta_pct,
    traction_force_n,
    wheel_power_w,
)
from src.simulator.scenario import Scenario

BASE_DT_S = 0.5          # simulated seconds advanced per physics step
MIN_SOC_PCT = 5.0        # trip ends below this
CREEP_SPEED_KMH = 6.0    # queue-crawl floor so per-km energy stays well-defined
EPOCH_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def classify_phase(
    v_kmh: float,
    accel_mps2: float,
    gradient_pct: float,
    segment_kind: str,
) -> str:
    """Classify the current driving phase (deterministic, label only)."""
    if v_kmh < 0.5:
        return "STOPPED"
    if segment_kind == "stop":
        return "STOPPED"
    # Gradient is most meaningful during steady driving.
    if v_kmh >= 20.0:
        if gradient_pct > 1.5 and accel_mps2 >= -0.1:
            return "UPHILL"
        if gradient_pct < -1.5 and accel_mps2 <= 0.1:
            return "DOWNHILL"
    if segment_kind == "traffic" and v_kmh <= 35.0:
        return "TRAFFIC"
    if v_kmh < 25.0 and accel_mps2 > 0.3:
        return "LAUNCH"
    if accel_mps2 > 0.15:
        return "ACCELERATION"
    if accel_mps2 < -1.2:
        return "BRAKING"
    if accel_mps2 < -0.05:
        return "DECELERATION"
    return "CRUISE"


class SimulationEngine:
    """Drives a Scenario forward deterministically and produces telemetry."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.cfg: VehicleConfig = scenario.vehicle
        self.reset()

    # ------------------------------------------------------------------ reset
    def reset(self) -> None:
        """Restart the trip from scratch (deterministic from scenario seed)."""
        self._t_s = 0.0
        self._dist_km = 0.0
        self._v_kmh = 0.0
        self._soc_pct = float(self.scenario.config.initial_soc_pct)
        self._batt_temp_c = float(self.scenario.config.ambient_temperature_c)
        self._history: List[Dict[str, Any]] = []
        self._step_index = 0
        self._finished = False

    @property
    def finished(self) -> bool:
        return self._finished

    # ---------------------------------------------------------------- stepping
    def step(self, n_steps: int = 1) -> None:
        """Advance the simulation by n_steps physics ticks.

        Each tick advances BASE_DT_S * time_scale simulated seconds.
        """
        dt = BASE_DT_S * self.scenario.config.time_scale
        for _ in range(int(n_steps)):
            if self._finished:
                return
            self._advance(dt)

    def _advance(self, dt: float) -> None:
        # ---- target speed from the drive schedule ------------------------
        seg = self.scenario.segment_at(self._dist_km)
        target = self._gradient_adjusted_target(seg["cruise_kmh"], seg["kind"])
        accel_mps2 = self._desired_accel(target, dt)

        # ---- integrate speed & distance (inertia: bounded accel) ---------
        v_mps = self._v_kmh / 3.6
        v_mps_new = clamp(v_mps + accel_mps2 * dt, 0.0, self.cfg.max_speed_kmh / 3.6)
        actual_accel = (v_mps_new - v_mps) / dt if dt > 0 else 0.0
        dist_new_km = self._dist_km + v_mps_new * dt / 1000.0
        self._v_kmh = v_mps_new * 3.6
        self._dist_km = dist_new_km
        self._t_s += dt

        # ---- physics ------------------------------------------------------
        grad = self.scenario.route.gradient_at(self._dist_km)
        alt = self.scenario.route.elevation_at(self._dist_km)
        f_trac = traction_force_n(v_mps_new, grad, actual_accel, self.cfg)
        p_wheel_w = wheel_power_w(f_trac, v_mps_new)
        motor_kw = motor_power_kw(p_wheel_w, self.cfg, v_kmh=self._v_kmh)
        regen_kw = regen_motor_power_kw(p_wheel_w, self.cfg, v_kmh=self._v_kmh)
        aux_kw = float(self.cfg.auxiliary_power_kw)
        batt_kw = battery_power_kw(motor_kw, aux_kw)

        rpm = motor_rpm_from_speed(self._v_kmh, self.cfg)
        torque = motor_torque_nm(motor_kw, rpm)
        current_a = battery_current_a(batt_kw, self.cfg)

        # ---- SOC + battery temperature ------------------------------------
        self._soc_pct = clamp(
            self._soc_pct + soc_delta_pct(batt_kw, dt, self.cfg), 0.0, 100.0)
        self._batt_temp_c += battery_temp_delta(
            batt_kw, self._batt_temp_c,
            float(self.scenario.config.ambient_temperature_c), dt, self.cfg)

        # ---- phase label ----------------------------------------------------
        phase = classify_phase(self._v_kmh, actual_accel, grad, seg["kind"])

        # ---- record (causal history: only samples at/before this instant) --
        self._history.append(self._make_sample(
            phase=phase, gradient_pct=grad, altitude_m=alt,
            motor_kw=motor_kw, regen_kw=regen_kw, aux_kw=aux_kw,
            batt_kw=batt_kw, rpm=rpm, torque=torque, current_a=current_a))
        self._step_index += 1

        # ---- stop conditions ------------------------------------------------
        if self._dist_km >= self.scenario.route.length_km:
            self._finished = True
        elif self._soc_pct <= MIN_SOC_PCT:
            self._finished = True

    # ------------------------------------------------------------ sub-models
    def _gradient_adjusted_target(self, base_kmh: float, kind: str) -> float:
        """Adjust the cruise target speed for the road gradient."""
        if kind == "stop":
            # Queue-crawl instead of a full stop: per-km energy stays defined
            # and the vehicle never idles at 0 km/h.
            return CREEP_SPEED_KMH
        grad = self.scenario.route.gradient_at(self._dist_km)
        target = float(base_kmh)
        if grad > 0:
            target *= clamp(1.0 - 0.018 * grad, 0.55, 1.0)
        elif grad < 0:
            target *= clamp(1.0 - 0.008 * grad, 1.0, 1.3)
        return clamp(target, CREEP_SPEED_KMH, self.cfg.max_speed_kmh)

    def _desired_accel(self, target_kmh: float, dt: float) -> float:
        """P-controller toward the target speed with comfort + physics limits.

        Also prepares for the next scheduled stop so the vehicle decelerates
        smoothly into the queue-crawl zone instead of jumping from cruise to
        stopped.
        """
        # Look ahead to the next stop event.
        next_stop = self._next_stop_km()
        if next_stop is not None:
            brake_zone = 0.09  # km
            if 0.0 <= (next_stop - self._dist_km) <= brake_zone:
                if self._v_kmh <= CREEP_SPEED_KMH:
                    # At/below creep: hold creep speed (never a full stop).
                    a = clamp((CREEP_SPEED_KMH - self._v_kmh) / 3.6 * 1.0,
                              -0.5, 0.5)
                    return a
                # Above creep: decelerate to reach ~CREEP_SPEED_KMH at the
                # stop point: v_f^2 = v_i^2 + 2*a*d => a = (v_f^2 - v_i^2)/(2*d).
                d_m = max((next_stop - self._dist_km) * 1000.0, 1e-6)
                v_mps = self._v_kmh / 3.6
                v_c_mps = CREEP_SPEED_KMH / 3.6
                a_stop = (v_c_mps * v_c_mps - v_mps * v_mps) / (2.0 * d_m)
                a_stop = clamp(a_stop, self.cfg.max_decel_mps2, -0.2)
                return a_stop

        dv = (target_kmh - self._v_kmh) / 3.6
        a = clamp(dv * 0.4, -1.2, self.cfg.max_accel_mps2)

        # Motor power / torque limits bound achievable acceleration.
        if self._v_kmh > 1.0:
            v_mps = self._v_kmh / 3.6
            grad = self.scenario.route.gradient_at(self._dist_km)
            f_resist = traction_force_n(v_mps, grad, 0.0, self.cfg)
            f_max_power = self.cfg.max_power_kw * 1000.0 / v_mps
            f_max_torque = (self.cfg.max_torque_nm * self.cfg.gear_ratio
                            / self.cfg.wheel_radius_m)
            f_max = min(f_max_power, f_max_torque)
            a_max_by_force = (f_max - f_resist) / self.cfg.mass_kg
            a = clamp(a, -abs(self.cfg.max_decel_mps2), a_max_by_force)
        return a

    def _next_stop_km(self) -> Optional[float]:
        """Distance of the next scheduled stop (or None if none ahead)."""
        for seg in self.scenario._segments:
            if seg["kind"] == "stop" and seg["start_km"] >= self._dist_km - 1e-9:
                return seg["start_km"]
        return None

    # --------------------------------------------------------------- outputs
    def _make_sample(
        self,
        *,
        phase: str,
        gradient_pct: float,
        altitude_m: float,
        motor_kw: float,
        regen_kw: float,
        aux_kw: float,
        batt_kw: float,
        rpm: float,
        torque: float,
        current_a: float,
    ) -> Dict[str, Any]:
        """Build a raw history sample (internal format, causal)."""
        ts = EPOCH_START + timedelta(seconds=self._t_s)
        return {
            "timestamp": ts,
            "elapsed_s": round(self._t_s, 3),
            "distance_km": round(self._dist_km, 5),
            "altitude_m": round(altitude_m, 2),
            "speed_kmh": round(self._v_kmh, 3),
            "ambient_temperature_c": float(self.scenario.config.ambient_temperature_c),
            "soc_pct": round(self._soc_pct, 4),
            "motor_power_kw": round(motor_kw, 4),
            "motor_rpm": round(rpm, 1),
            "motor_torque_nm": round(torque, 2),
            "aux_power_kw": round(aux_kw, 4),
            "regen_power_kw": round(regen_kw, 4),
            "battery_power_kw": round(batt_kw, 4),
            "battery_voltage_v": round(self.cfg.nominal_voltage_v, 1),
            "battery_temperature_c": round(self._batt_temp_c, 3),
            "battery_current_a": round(current_a, 2),
            "gradient_pct": round(gradient_pct, 3),
            "phase": phase,
        }

    def snapshot(self) -> Dict[str, Any]:
        """Current telemetry snapshot (schema-ready field names + labels)."""
        if not self._history:
            self._advance(BASE_DT_S * self.scenario.config.time_scale)
        s = self._history[-1]
        return {
            "vehicle_id": f"SIM-{self.scenario.id}",
            "timestamp": s["timestamp"],
            "soc_pct": s["soc_pct"],
            "battery_capacity_kwh": self.cfg.battery_capacity_kwh,
            "speed_kmh": s["speed_kmh"],
            "altitude_m": s["altitude_m"],
            "ambient_temperature_c": s["ambient_temperature_c"],
            "distance_since_trip_start_km": s["distance_km"],
            "time_since_trip_start_min": round(s["elapsed_s"] / 60.0, 3),
            "motor_power_kw": s["motor_power_kw"],
            "motor_rpm": s["motor_rpm"],
            "motor_torque_nm": s["motor_torque_nm"],
            "aux_power_kw": s["aux_power_kw"],
            "regen_power_kw": s["regen_power_kw"],
            "battery_voltage_v": s["battery_voltage_v"],
            "battery_temperature_c": s["battery_temperature_c"],
            "battery_current_a": s["battery_current_a"],
            "current_gradient_pct": s["gradient_pct"],
            "phase": s["phase"],
            "scenario_id": self.scenario.id,
            "_source": "SIMULATOR",
        }

    def past_window(self, max_samples: int = 120) -> List[Dict[str, Any]]:
        """Return causal history samples (never any future samples)."""
        win = self._history[-max_samples:] if self._history else []
        return [
            {
                "timestamp": s["timestamp"],
                "distance_km": s["distance_km"],
                "altitude_m": s["altitude_m"],
                "speed_kmh": s["speed_kmh"],
                "ambient_temperature_c": s["ambient_temperature_c"],
                "motor_power_kw": s["motor_power_kw"],
                "motor_torque_nm": s["motor_torque_nm"],
                "motor_rpm": s["motor_rpm"],
                "aux_power_kw": s["aux_power_kw"],
                "regen_power_kw": s["regen_power_kw"],
            }
            for s in win
        ]

    def route_terrain_input(self, horizon_km: float = 5.0) -> Dict[str, Any]:
        """Upcoming terrain for the current position (causal, labeled).

        The horizon is clamped to the remaining route so the schema (>= 2
        points) always holds; near the trip end a short 2-point profile is
        emitted instead of failing.
        """
        remaining = self.scenario.route.length_km - self._dist_km
        if remaining < 0.25:
            d = min(self._dist_km, self.scenario.route.length_km)
            try:
                pts = self.scenario.route.ahead_terrain(
                    d, horizon_km=max(remaining, 0.1), step_km=0.05)
            except ValueError:
                pts = []
            if len(pts) < 2:
                pts = [
                    {"offset_km": 0.0,
                     "altitude_m": round(self.scenario.route.elevation_at(d), 2)},
                    {"offset_km": 0.05,
                     "altitude_m": round(
                         self.scenario.route.elevation_at(
                             self.scenario.route.length_km), 2)},
                ]
            return {"points": pts, "source": "SIMULATOR_ROUTE"}
        horizon = min(horizon_km, remaining)
        return {
            "points": self.scenario.route.ahead_terrain(
                self._dist_km, horizon_km=horizon, step_km=0.25),
            "source": "SIMULATOR_ROUTE",
        }

    def state(self) -> Dict[str, Any]:
        """Full engine state for display/audit."""
        return {
            "scenario_id": self.scenario.id,
            "finished": self._finished,
            "elapsed_s": round(self._t_s, 2),
            "distance_km": round(self._dist_km, 3),
            "speed_kmh": round(self._v_kmh, 2),
            "soc_pct": round(self._soc_pct, 2),
            "battery_temperature_c": round(self._batt_temp_c, 2),
            "n_samples": len(self._history),
            "time_scale": self.scenario.config.time_scale,
        }

    def energy_balance(self) -> Dict[str, float]:
        """Energy audit over the trip so far (kWh) for physics-consistency tests."""
        motor_wh = 0.0
        regen_wh = 0.0
        prev_wh = self.cfg.battery_capacity_kwh * 1000.0 * (
            self.scenario.config.initial_soc_pct / 100.0)
        cur_wh = self.cfg.battery_capacity_kwh * 1000.0 * (self._soc_pct / 100.0)
        dt_s = BASE_DT_S * self.scenario.config.time_scale
        for s in self._history:
            motor_wh += s["motor_power_kw"] * 1000.0 * dt_s / 3600.0
            regen_wh += s["regen_power_kw"] * 1000.0 * dt_s / 3600.0
        delta_wh = prev_wh - cur_wh
        return {
            "initial_battery_wh": round(prev_wh, 1),
            "current_battery_wh": round(cur_wh, 1),
            "battery_delta_wh": round(delta_wh, 1),
            "integrated_motor_wh": round(motor_wh, 1),
            "integrated_regen_wh": round(regen_wh, 1),
        }
