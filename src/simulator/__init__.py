"""
STEP 16 — Physics-inspired EV driving simulator.

Deterministic, physics-based simulation of an electric vehicle driving a
generated route. Produces clearly-labeled SIMULATOR telemetry that can feed
the same causal feature builder and frozen model as live telemetry.

Honesty contract:
- Simulator output is always labeled with source "SIMULATOR".
- The simulator is deterministic for a given scenario seed (Scenario ID).
- Simulated data is NEVER presented as real vehicle data.
"""
from __future__ import annotations

from src.simulator.config import VehicleConfig
from src.simulator.route import TerrainRoute
from src.simulator.scenario import Scenario, ScenarioConfig, random_scenario
from src.simulator.simulator import SimulationEngine

__all__ = [
    "VehicleConfig",
    "TerrainRoute",
    "Scenario",
    "ScenarioConfig",
    "random_scenario",
    "SimulationEngine",
]
