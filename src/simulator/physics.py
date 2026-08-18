"""
Pure physics helpers for the EV simulator.

Longitudinal vehicle model (engineering approximation):

    F_resist = F_roll + F_aero + F_grade
    F_roll   = m * g * Crr * cos(theta)
    F_aero   = 0.5 * rho * Cd * A * v^2
    F_grade  = m * g * sin(theta)
    theta    = atan(gradient_pct / 100)

    traction force demand  = F_resist + m * a
    wheel power            = F * v
    motor electrical power = P_wheel / combined_efficiency  (traction)
    regen power            = P_wheel * regen_efficiency     (negative, energy back)

All functions are pure and deterministic.
"""
from __future__ import annotations

import math

from src.simulator.config import VehicleConfig

GRAVITY_MPS2 = 9.80665
AIR_DENSITY_KG_M3 = 1.225


def gradient_to_angle_rad(gradient_pct: float) -> float:
    """Convert a road gradient in percent to an angle in radians."""
    return math.atan(float(gradient_pct) / 100.0)


def road_resistive_force_n(v_mps: float, gradient_pct: float, cfg: VehicleConfig) -> float:
    """Total resistive force (rolling + aero + grade) in Newtons.

    Positive = opposes motion (uphill, drag, rolling). Downhill grades can
    make this negative (assisting motion).
    """
    theta = gradient_to_angle_rad(gradient_pct)
    f_roll = cfg.mass_kg * GRAVITY_MPS2 * cfg.rolling_resistance_coeff * math.cos(theta)
    f_aero = 0.5 * AIR_DENSITY_KG_M3 * cfg.drag_coefficient_cd * cfg.frontal_area_m2 * v_mps * v_mps
    f_grade = cfg.mass_kg * GRAVITY_MPS2 * math.sin(theta)
    return f_roll + f_aero + f_grade


def traction_force_n(
    v_mps: float,
    gradient_pct: float,
    accel_mps2: float,
    cfg: VehicleConfig,
) -> float:
    """Net tractive force required at the wheels (Newtons)."""
    f_resist = road_resistive_force_n(v_mps, gradient_pct, cfg)
    return f_resist + cfg.mass_kg * accel_mps2


def wheel_power_w(f_force_n: float, v_mps: float) -> float:
    """Power at the wheels (Watts). Negative = regenerative/assisting."""
    return f_force_n * v_mps


def traction_motor_power_kw(p_wheel_w: float, cfg: VehicleConfig) -> float:
    """Motor electrical power draw (positive traction demand) in kW."""
    return p_wheel_w / 1000.0 / cfg.combined_drivetrain_efficiency


def regen_motor_power_kw(
    p_wheel_w: float, cfg: VehicleConfig, v_kmh: float | None = None
) -> float:
    """Regenerative electrical power recovered (kW, negative by convention).

    Returns a value in [-max_regen, 0]. The codebase convention is that
    regen_power_kw is <= 0 (energy flowing back into the battery).

    When ``v_kmh`` is given, regen fades toward zero at low speed (real EVs
    recover little/nothing near standstill); this keeps the simulated drive in
    the domain the frozen model was trained on.
    """
    if p_wheel_w >= 0:
        return 0.0
    regen = -p_wheel_w / 1000.0 * cfg.regen_efficiency
    if v_kmh is not None:
        # Linear fade: ~0 below 8 km/h, full from ~25 km/h up.
        fade = clamp((v_kmh - 8.0) / 17.0, 0.0, 1.0)
        regen *= fade
    return max(-cfg.max_power_kw * 0.8, -abs(regen))


def motor_power_kw(
    p_wheel_w: float, cfg: VehicleConfig, v_kmh: float | None = None
) -> float:
    """Net motor electrical power (kW).

    Positive = discharging to drive; negative = motoring/regen.
    """
    if p_wheel_w >= 0:
        return min(traction_motor_power_kw(p_wheel_w, cfg), cfg.max_power_kw)
    return regen_motor_power_kw(p_wheel_w, cfg, v_kmh=v_kmh)


def motor_rpm_from_speed(v_kmh: float, cfg: VehicleConfig) -> float:
    """Motor RPM derived from wheel speed and fixed gear ratio."""
    wheel_rpm = (v_kmh / 3.6) / (2.0 * math.pi * cfg.wheel_radius_m) * 60.0
    return wheel_rpm * cfg.gear_ratio


def motor_torque_nm(p_motor_kw: float, motor_rpm: float) -> float:
    """Motor torque (Nm) from electrical power and RPM."""
    if motor_rpm <= 1e-6:
        return 0.0
    omega = motor_rpm * 2.0 * math.pi / 60.0
    return (p_motor_kw * 1000.0) / omega


def battery_power_kw(motor_power_kw_val: float, aux_power_kw: float) -> float:
    """Total battery power (kW). Positive = discharge, negative = charge."""
    return motor_power_kw_val + aux_power_kw


def battery_current_a(battery_power_kw_val: float, cfg: VehicleConfig) -> float:
    """Pack current (A) from power and nominal voltage."""
    if cfg.nominal_voltage_v <= 0:
        return 0.0
    return battery_power_kw_val * 1000.0 / cfg.nominal_voltage_v


def soc_delta_pct(p_battery_kw_val: float, dt_s: float, cfg: VehicleConfig) -> float:
    """SOC change over dt seconds (percentage points).

    Discharging (positive power) decreases SOC; charging (negative power)
    increases it.
    """
    energy_kwh = p_battery_kw_val * dt_s / 3600.0
    return -energy_kwh / cfg.battery_capacity_kwh * 100.0


def battery_temp_delta(
    p_battery_kw_val: float,
    batt_temp_c: float,
    ambient_temp_c: float,
    dt_s: float,
    cfg: VehicleConfig,
) -> float:
    """Battery temperature change over dt (deg C).

    Heating is proportional to the magnitude of battery power (ohmic loss);
    cooling is proportional to the temperature difference to ambient.
    """
    heating = cfg.battery_heating_coeff * abs(p_battery_kw_val)
    cooling = cfg.battery_cooling_coeff * (batt_temp_c - ambient_temp_c)
    return (heating - cooling) * dt_s


def clamp(val: float, lo: float, hi: float) -> float:
    """Clamp val into [lo, hi]."""
    return max(lo, min(hi, val))
