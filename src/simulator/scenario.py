"""
Scenario model: RANDOMIZE SCENARIO + Scenario ID + deterministic replay.

A Scenario bundles a seed-derived route profile, driving style, traffic level,
initial SOC, ambient temperature, load factor and time scale. Everything is
derived from a single integer seed, so:

    s1 = random_scenario(seed=123)
    s2 = random_scenario(seed=123)   # identical scenario (reproducible)

    Scenario ID = SIM-XXXXXXXX  (derived from the seed)

Replay a scenario by re-instantiating with the recorded seed.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.simulator.config import VehicleConfig
from src.simulator.route import PROFILE_STYLES, TerrainRoute

ID_PREFIX = "SIM-"
ID_LEN = 8

DRIVING_STYLES = ("eco", "balanced", "sporty")
TRAFFIC_LEVELS = ("light", "moderate", "heavy")
ROUTE_PROFILES = tuple(sorted(PROFILE_STYLES))

# cruise speed (km/h) lower/upper by driving style
STYLE_SPEED_RANGE = {
    "eco": (45.0, 62.0),
    "balanced": (52.0, 76.0),
    "sporty": (62.0, 90.0),
}
# stop frequency (per km) by traffic level
TRAFFIC_STOP_FREQ = {"light": 0.12, "moderate": 0.28, "heavy": 0.45}
# traffic segment speed (km/h)
TRAFFIC_SPEED = {"light": 40.0, "moderate": 25.0, "heavy": 15.0}


def make_scenario_id(seed: int) -> str:
    """Derive a stable Scenario ID from the seed: SIM-XXXXXXXX."""
    digest = hashlib.sha256(str(int(seed)).encode("utf-8")).hexdigest().upper()
    return f"{ID_PREFIX}{digest[:ID_LEN]}"


@dataclass
class ScenarioConfig:
    """A single coherent driving scenario (deterministic from seed)."""

    seed: int
    route_profile: str = "hilly"
    driving_style: str = "balanced"
    traffic_level: str = "light"
    ambient_temperature_c: float = 18.0
    initial_soc_pct: float = 80.0
    load_factor: float = 1.0  # 1.0 = driver only; >1 adds payload mass
    time_scale: float = 1.0
    vehicle: VehicleConfig = field(default_factory=VehicleConfig)

    def validate(self) -> None:
        if self.route_profile not in ROUTE_PROFILES:
            raise ValueError(f"route_profile must be one of {ROUTE_PROFILES}")
        if self.driving_style not in DRIVING_STYLES:
            raise ValueError(f"driving_style must be one of {DRIVING_STYLES}")
        if self.traffic_level not in TRAFFIC_LEVELS:
            raise ValueError(f"traffic_level must be one of {TRAFFIC_LEVELS}")
        if not (0.0 <= self.initial_soc_pct <= 100.0):
            raise ValueError("initial_soc_pct must be in [0, 100]")
        if not (0.5 <= self.load_factor <= 2.0):
            raise ValueError("load_factor must be in [0.5, 2.0]")
        if not (0.5 <= self.time_scale <= 10.0):
            raise ValueError("time_scale must be in [0.5, 10.0]")
        if not (-60.0 <= self.ambient_temperature_c <= 60.0):
            raise ValueError("ambient_temperature_c out of range")
        self.vehicle.validate()


class Scenario:
    """A seeded, replayable driving scenario."""

    def __init__(self, config: ScenarioConfig):
        config.validate()
        self.config = config
        self.id = make_scenario_id(config.seed)

        rng = random.Random(config.seed)
        # Route length deterministic from the seed, in [20, 50] km.
        length_km = round(rng.uniform(20.0, 50.0), 2)
        base_alt = round(rng.uniform(80.0, 250.0), 1)
        self.route = TerrainRoute(
            seed=config.seed,
            length_km=length_km,
            base_altitude_m=base_alt,
            profile=config.route_profile,
        )

        # Vehicle mass includes the payload implied by load_factor.
        extra_mass = (config.load_factor - 1.0) * 70.0  # 70 kg per extra passenger-ish
        self.vehicle = config.vehicle.with_extra_mass(extra_mass)

        self._segments = self._build_segments(rng)

    # ------------------------------------------------------------------ cycles
    def _build_segments(self, rng: random.Random) -> List[Dict[str, Any]]:
        """Build the deterministic cruise/stop/traffic schedule for the route."""
        length = self.route.length_km
        lo, hi = STYLE_SPEED_RANGE[self.config.driving_style]
        stop_freq = TRAFFIC_STOP_FREQ[self.config.traffic_level]
        traffic_speed = TRAFFIC_SPEED[self.config.traffic_level]

        segments: List[Dict[str, Any]] = []
        pos = 0.0
        while pos < length:
            seg_len = rng.uniform(1.2, 3.0)
            kind = "cruise"
            cruise = rng.uniform(lo, hi)
            # Heavy/moderate traffic occasionally converts a cruise into a
            # slow traffic segment.
            if rng.random() < TRAFFIC_STOP_FREQ[self.config.traffic_level] * 0.5:
                kind = "traffic"
                cruise = traffic_speed
            segments.append({
                "start_km": round(pos, 3),
                "end_km": round(min(pos + seg_len, length), 3),
                "cruise_kmh": round(cruise, 1),
                "kind": kind,
            })
            pos += seg_len
            # Traffic light stop (zero-length event) between segments.
            if rng.random() < stop_freq:
                segments.append({
                    "start_km": round(pos, 3),
                    "end_km": round(pos, 3),
                    "cruise_kmh": 0.0,
                    "kind": "stop",
                })
        return segments

    def segment_at(self, distance_km: float) -> Dict[str, Any]:
        """Return the driving segment active at a distance (last stop wins)."""
        active = None
        for seg in self._segments:
            if seg["start_km"] <= distance_km <= seg["end_km"]:
                active = seg
            elif seg["start_km"] <= distance_km < seg["start_km"] + 0.01:
                active = seg  # exact stop position
            elif distance_km >= seg["end_km"]:
                continue
        if active is None:
            active = self._segments[-1]
        return active

    # ------------------------------------------------------------------ info
    def summary(self) -> Dict[str, Any]:
        """Scenario description for the dashboard / validation report."""
        return {
            "scenario_id": self.id,
            "seed": self.config.seed,
            "driving_style": self.config.driving_style,
            "traffic_level": self.config.traffic_level,
            "route_profile": self.config.route_profile,
            "ambient_temperature_c": self.config.ambient_temperature_c,
            "initial_soc_pct": self.config.initial_soc_pct,
            "load_factor": self.config.load_factor,
            "time_scale": self.config.time_scale,
            "vehicle_mass_kg": round(self.vehicle.mass_kg, 1),
            "route": self.route.summary(),
            "n_segments": len(self._segments),
        }


def random_scenario(
    seed: int | None = None,
    time_scale: float = 1.0,
) -> Scenario:
    """RANDOMIZE SCENARIO: build a coherent scenario from a seed.

    If seed is None, one is drawn from the system RNG (a single source of
    entropy); everything else is derived deterministically from it.
    """
    if seed is None:
        seed = random.SystemRandom().randint(0, 2**31 - 1)
    rng = random.Random(seed)

    config = ScenarioConfig(
        seed=int(seed),
        route_profile=rng.choice(ROUTE_PROFILES),
        driving_style=rng.choice(DRIVING_STYLES),
        traffic_level=rng.choice(TRAFFIC_LEVELS),
        ambient_temperature_c=round(rng.uniform(-10.0, 40.0), 1),
        initial_soc_pct=round(rng.uniform(60.0, 100.0), 1),
        load_factor=round(rng.uniform(1.0, 1.5), 2),
        time_scale=time_scale,
        vehicle=VehicleConfig(),
    )
    return Scenario(config)
