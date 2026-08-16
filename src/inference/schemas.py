"""
STEP 11B - PRODUCTION INPUT SCHEMAS (Pydantic).

Defines the minimum validated input required by the route-aware model and the
standardized prediction response.

Rules:
  - Inputs are strictly validated (ranges, types, required fields).
  - No values are invented. If a required field (including route terrain) is
    missing, validation fails with a clear error.
  - Route-aware (next_*) features are never silently zero-filled.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from src.inference.model_metadata import (
    MODEL_VERSION,
    TRAINING_DATASET,
    TARGET,
    HORIZON_KM,
    ROUTE_AWARE,
)


# --------------------------------------------------------------------------
# Route terrain input (STEP 11E). The client supplies upcoming elevation data
# produced by a real DEM/GPS pipeline. It is NEVER fabricated server-side.
# --------------------------------------------------------------------------
class TerrainPoint(BaseModel):
    """One sample of the upcoming elevation profile."""

    offset_km: float = Field(ge=0.0, description="Distance ahead of the prediction point (km). 0 == current point.")
    altitude_m: float = Field(description="Elevation at this offset (metres).")

    @field_validator("offset_km")
    @classmethod
    def _finite_offset(cls, v):
        if v != v:  # NaN
            raise ValueError("offset_km must be a finite number")
        return v

    @field_validator("altitude_m")
    @classmethod
    def _finite_alt(cls, v):
        if v != v:
            raise ValueError("altitude_m must be a finite number")
        if abs(v) > 9000:
            raise ValueError(f"altitude_m out of plausible range: {v}")
        return v


class RouteTerrainInput(BaseModel):
    """Upcoming route terrain required for route-aware prediction."""

    points: List[TerrainPoint] = Field(
        min_length=2,
        description="Elevation samples covering at least the next 5 km.",
    )
    source: str = Field(
        description="Label of the terrain source (e.g. DEM_STATIC). Never 'FABRICATED'.")

    @field_validator("source")
    @classmethod
    def _not_fabricated(cls, v):
        if v.strip().upper() in {"FABRICATED", "FAKE", "SYNTHETIC_DEMO"}:
            raise ValueError(
                "terrain source must be a real DEM/GPS label, not fabricated")
        return v.strip()


# --------------------------------------------------------------------------
# Telemetry snapshot at the prediction point.
# --------------------------------------------------------------------------
class TelemetrySnapshot(BaseModel):
    """Minimum telemetry required at the prediction point."""

    vehicle_id: str = Field(min_length=1, max_length=64)
    timestamp: datetime = Field(description="Prediction timestamp (UTC).")
    soc_pct: float = Field(ge=0.0, le=100.0, description="State of charge (%).")
    battery_capacity_kwh: float = Field(gt=0.0, le=300.0, description="Usable battery capacity (kWh).")
    speed_kmh: float = Field(ge=0.0, le=400.0, description="Vehicle speed (km/h).")
    altitude_m: float = Field(description="Current altitude (m).")
    ambient_temperature_c: float = Field(ge=-60.0, le=80.0, description="Ambient temperature (deg C).")
    distance_since_trip_start_km: float = Field(
        ge=0.0, description="Distance driven since trip start (km).")
    time_since_trip_start_min: float = Field(
        ge=0.0, description="Time elapsed since trip start (minutes).")

    # Optional powertrain telemetry (missing -> NaN -> frozen imputer median).
    motor_power_kw: Optional[float] = Field(default=None, ge=-500.0, le=500.0)
    motor_rpm: Optional[float] = Field(default=None, ge=-20000.0, le=20000.0)
    motor_torque_nm: Optional[float] = Field(default=None, ge=-1000.0, le=1000.0)
    aux_power_kw: Optional[float] = Field(default=None, ge=-50.0, le=50.0)
    regen_power_kw: Optional[float] = Field(default=None, ge=-500.0, le=0.0)

    # Optional battery telemetry (display-only; not used by the frozen model).
    battery_voltage_v: Optional[float] = Field(default=None, ge=0.0, le=1500.0)
    battery_temperature_c: Optional[float] = Field(default=None, ge=-60.0, le=120.0)
    battery_current_a: Optional[float] = Field(default=None, ge=-1000.0, le=1000.0)

    @field_validator("timestamp")
    @classmethod
    def _timezone_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
        return v.astimezone(timezone.utc)

    @field_validator("soc_pct")
    @classmethod
    def _soc_finite(cls, v):
        if v != v:
            raise ValueError("soc_pct must be a finite number")
        return v

    @field_validator("battery_capacity_kwh")
    @classmethod
    def _capacity_finite(cls, v):
        if v != v:
            raise ValueError("battery_capacity_kwh must be a finite number")
        return v


class PastWindowSample(BaseModel):
    """One row of recent trip history used to compute causal past-window features."""

    timestamp: datetime
    distance_km: float = Field(ge=0.0)
    altitude_m: float
    speed_kmh: float = Field(ge=0.0, le=400.0)
    ambient_temperature_c: Optional[float] = None
    motor_power_kw: Optional[float] = None
    motor_torque_nm: Optional[float] = None
    motor_rpm: Optional[float] = None
    aux_power_kw: Optional[float] = None
    regen_power_kw: Optional[float] = None


class PredictionRequest(BaseModel):
    """Production inference request."""

    telemetry: TelemetrySnapshot
    route_terrain: RouteTerrainInput = Field(
        description="Required: upcoming route terrain (real DEM/GPS).")
    past_window: Optional[List[PastWindowSample]] = Field(
        default=None,
        description="Optional recent history (<= ~2 km) to enable causal "
                    "past-window features; if omitted those features are "
                    "median-imputed by the frozen preprocessor.")
    reserve_soc_pct: float = Field(default=10.0, ge=0.0, lt=100.0,
                                   description="Reserve SOC to exclude from range.")


# --------------------------------------------------------------------------
# Responses
# --------------------------------------------------------------------------
class PredictionResponse(BaseModel):
    """Standardized prediction response (no internal model objects)."""

    predicted_energy_kwh_per_km: float
    usable_energy_kwh: float
    expected_range_km: float
    conservative_range_km: Optional[float] = None
    optimistic_range_km: Optional[float] = None
    uncertainty: Optional[dict] = None
    confidence: Optional[dict] = None
    ood: Optional[dict] = None
    route: Optional[dict] = None
    sensor_quality: str = "good"
    model_version: str = MODEL_VERSION
    route_terrain_source: str


class ModelInfoResponse(BaseModel):
    model: str
    feature_count: int
    target: str = TARGET
    horizon_km: int = HORIZON_KM
    dataset: str = TRAINING_DATASET
    route_aware: bool = ROUTE_AWARE
    model_version: str = MODEL_VERSION


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str = MODEL_VERSION


class ErrorResponse(BaseModel):
    detail: str
    error_code: str