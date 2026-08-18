"""
Simulator vehicle configuration.

A validated, immutable vehicle parameter set. These are engineering constants
that drive the physics model; they are never taken from the frozen model and
never modify model artifacts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class VehicleConfig:
    """Physical parameters of the simulated vehicle."""

    battery_capacity_kwh: float = 60.0
    mass_kg: float = 1800.0
    frontal_area_m2: float = 2.5
    drag_coefficient_cd: float = 0.28
    rolling_resistance_coeff: float = 0.011
    drivetrain_efficiency: float = 0.90
    motor_efficiency: float = 0.92
    auxiliary_power_kw: float = 0.6
    wheel_radius_m: float = 0.34
    gear_ratio: float = 9.0
    nominal_voltage_v: float = 350.0
    regen_efficiency: float = 0.70
    max_power_kw: float = 150.0
    max_torque_nm: float = 350.0
    max_speed_kmh: float = 150.0
    max_accel_mps2: float = 2.6
    max_decel_mps2: float = -3.4
    battery_heating_coeff: float = 0.004
    battery_cooling_coeff: float = 0.008

    # ------------------------------------------------------------------ mass
    @property
    def combined_drivetrain_efficiency(self) -> float:
        """Combined drivetrain x motor efficiency used for traction power."""
        return self.drivetrain_efficiency * self.motor_efficiency

    def with_extra_mass(self, extra_mass_kg: float) -> "VehicleConfig":
        """Return a copy with additional payload mass (load factor)."""
        if extra_mass_kg < 0:
            raise ValueError("extra_mass_kg must be >= 0")
        return VehicleConfig(**{**self.__dict__, "mass_kg": self.mass_kg + extra_mass_kg})

    # ------------------------------------------------------------------ valid
    def validate(self) -> None:
        """Raise ValueError if any parameter is physically invalid."""
        errors = []
        if self.battery_capacity_kwh <= 0 or not math.isfinite(self.battery_capacity_kwh):
            errors.append("battery_capacity_kwh must be > 0")
        if self.mass_kg <= 0 or not math.isfinite(self.mass_kg):
            errors.append("mass_kg must be > 0")
        if not (0 < self.drag_coefficient_cd <= 2.0):
            errors.append("drag_coefficient_cd must be in (0, 2]")
        if not (0 < self.rolling_resistance_coeff <= 0.05):
            errors.append("rolling_resistance_coeff must be in (0, 0.05]")
        if not (0 < self.combined_drivetrain_efficiency <= 1.0):
            errors.append("combined drivetrain efficiency must be in (0, 1]")
        if not (0 < self.regen_efficiency <= 1.0):
            errors.append("regen_efficiency must be in (0, 1]")
        if self.wheel_radius_m <= 0:
            errors.append("wheel_radius_m must be > 0")
        if self.gear_ratio <= 0:
            errors.append("gear_ratio must be > 0")
        if self.nominal_voltage_v <= 0:
            errors.append("nominal_voltage_v must be > 0")
        if self.max_power_kw <= 0:
            errors.append("max_power_kw must be > 0")
        if self.max_speed_kmh <= 0:
            errors.append("max_speed_kmh must be > 0")
        if self.max_accel_mps2 <= 0:
            errors.append("max_accel_mps2 must be > 0")
        if self.max_decel_mps2 >= 0:
            errors.append("max_decel_mps2 must be < 0")
        if self.frontal_area_m2 <= 0:
            errors.append("frontal_area_m2 must be > 0")
        if errors:
            raise ValueError("invalid VehicleConfig: " + "; ".join(errors))

    def to_dict(self) -> Dict[str, Any]:
        """Serializable description (no model artifacts involved)."""
        return {
            "battery_capacity_kwh": self.battery_capacity_kwh,
            "mass_kg": self.mass_kg,
            "frontal_area_m2": self.frontal_area_m2,
            "drag_coefficient_cd": self.drag_coefficient_cd,
            "rolling_resistance_coeff": self.rolling_resistance_coeff,
            "combined_drivetrain_efficiency": round(self.combined_drivetrain_efficiency, 4),
            "auxiliary_power_kw": self.auxiliary_power_kw,
            "wheel_radius_m": self.wheel_radius_m,
            "gear_ratio": self.gear_ratio,
            "nominal_voltage_v": self.nominal_voltage_v,
            "regen_efficiency": self.regen_efficiency,
            "max_power_kw": self.max_power_kw,
            "max_torque_nm": self.max_torque_nm,
            "max_speed_kmh": self.max_speed_kmh,
        }
