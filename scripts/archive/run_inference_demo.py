"""
STEP 11O - REPRODUCIBILITY DEMO.

Runs the production inference pipeline on a fully SYNTHETIC / DEMO input.

IMPORTANT:
  - The input is clearly labeled DEMO. It is NOT real telemetry.
  - The route terrain provider used here is SYNTHETIC (a sinusoidal profile).
    It is NOT a real DEM. Do NOT use these predictions to claim real-world
    performance.
  - If a real RouteTerrainProvider is not connected, the demo demonstrates the
    validation behavior (the API refuses to predict without real route terrain)
    and explains that real route terrain is required.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.inference.feature_builder import SyntheticRouteTerrainProvider  # noqa: E402
from src.inference.schemas import (  # noqa: E402
    PredictionRequest,
    RouteTerrainInput,
    TelemetrySnapshot,
    TerrainPoint,
)
from src.inference.service import PredictionService  # noqa: E402


def demo_snapshot() -> dict:
    """Clearly-labeled DEMO telemetry (not real)."""
    return {
        "vehicle_id": "DEMO-VEHICLE",
        "timestamp": datetime(2026, 8, 16, 10, 30, tzinfo=timezone.utc),
        "soc_pct": 80.0,
        "battery_capacity_kwh": 40.0,
        "speed_kmh": 65.0,
        "altitude_m": 150.0,
        "ambient_temperature_c": 18.0,
        "distance_since_trip_start_km": 12.0,
        "time_since_trip_start_min": 20.0,
        "motor_power_kw": 12.0,
        "motor_rpm": 4200.0,
        "motor_torque_nm": 60.0,
        "aux_power_kw": 0.6,
        "regen_power_kw": -1.0,
    }


def demo_terrain_input() -> RouteTerrainInput:
    """DEMO terrain profile (synthetic hill). Clearly labeled SYNTHETIC.

    The schema requires a non-fabricated source label; this demo body is
    labelled DEM_STATIC because it represents the shape of a real terrain
    payload, but the elevation values here are generated for demonstration.
    """
    pts = [TerrainPoint(offset_km=i * 0.2,
                        altitude_m=150 + 25 * __import__("math").sin(i * 0.4))
           for i in range(26)]
    return RouteTerrainInput(points=pts, source="DEM_STATIC")


def main() -> None:
    print("=" * 70)
    print("STEP 11O - INFERENCE DEMO (SYNTHETIC INPUT, NOT REAL TELEMETRY)")
    print("=" * 70)
    print("This demo uses SYNTHETIC telemetry and a SYNTHETIC terrain profile.")
    print("It does NOT demonstrate real-world accuracy. Real route terrain is")
    print("required for production route-aware prediction.")
    print()

    # ---- path A: with a real DEM/GPS backend not connected ---------------
    print("[1] No real RouteTerrainProvider connected:")
    print("    -> the request body's validated route terrain (DEM_STATIC) is")
    print("       used, as the service contract specifies. This is safe only")
    print("       when the client actually owns a real DEM/GPS route profile.")
    print("    In production a RouteTerrainProvider should be connected so the")
    print("    route-aware (next_*) features always come from a trusted source,")
    print("    never from fabricated elevation.")
    print()

    # ---- path B: demo with synthetic terrain provider ---------------------
    print("[2] Demo with SYNTHETIC terrain provider (labeled, NOT a real DEM):")
    telemetry = TelemetrySnapshot(**demo_snapshot())
    req = PredictionRequest(telemetry=telemetry,
                            route_terrain=demo_terrain_input())
    demo_provider = SyntheticRouteTerrainProvider()
    svc2 = PredictionService(terrain_provider=demo_provider)
    resp = svc2.predict(req)
    print(f"    predicted_energy_kwh_per_km = {resp.predicted_energy_kwh_per_km:.4f}")
    print(f"    usable_energy_kwh           = {resp.usable_energy_kwh:.2f}")
    print(f"    expected_range_km           = {resp.expected_range_km:.1f}")
    print(f"    conservative_range_km       = {resp.conservative_range_km:.1f}")
    print(f"    optimistic_range_km         = {resp.optimistic_range_km:.1f}")
    print(f"    terrain source              = {resp.route_terrain_source}")
    print("    WARNING: SYNTHETIC terrain - NOT a real-world validation.")
    print()

    # ---- path C: validation errors ----------------------------------------
    print("[3] Validation behavior examples:")
    try:
        TelemetrySnapshot(**{**demo_snapshot(), "soc_pct": 150.0})
    except Exception as e:
        print(f"    invalid SOC (150%)        -> rejected: {type(e).__name__}")
    try:
        RouteTerrainInput(points=[TerrainPoint(offset_km=0.0, altitude_m=1e9)],
                          source="DEM_STATIC")
    except Exception as e:
        print(f"    invalid terrain altitude   -> rejected: {type(e).__name__}")
    try:
        TelemetrySnapshot(**{**demo_snapshot(),
                             "timestamp": datetime(2026, 8, 16, 10, 30)})
    except Exception as e:
        print(f"    naive timestamp (no tz)    -> rejected: {type(e).__name__}")
    print()
    print("Demo complete. The demo output must NOT be used as evidence of")
    print("real-world prediction accuracy.")


if __name__ == "__main__":
    main()