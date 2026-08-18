"""
Deterministic continuous route terrain generator.

Produces a smooth elevation profile over 20-50 km. The gradient profile is a
seeded sum of harmonic components, so elevation is a C1 continuous curve --
never a sequence of independent random altitude points (which would be
physically implausible and break the smoothness requirement).

All randomness is derived from a fixed seed, so a given seed always yields
the identical route (reproducibility / Scenario ID replay).
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Tuple

from src.simulator.physics import clamp

SAMPLE_INTERVAL_KM = 0.05
DEFAULT_LENGTH_KM = 35.0
MIN_LENGTH_KM = 20.0
MAX_LENGTH_KM = 50.0
MAX_GRADIENT_PCT = 8.0

# Route profile styles -> harmonic amplitude envelopes
PROFILE_STYLES = {
    "highway": {"amps": (0.15, 0.35, 0.55, 0.25), "base": 0.3},
    "hilly": {"amps": (0.5, 1.2, 1.6, 0.9), "base": 0.8},
    "mountain": {"amps": (1.2, 2.4, 3.0, 1.6), "base": 1.8},
    "flat": {"amps": (0.05, 0.12, 0.25, 0.1), "base": 0.1},
}


class TerrainRoute:
    """A smooth, deterministic elevation profile for a fixed route length."""

    def __init__(
        self,
        seed: int,
        length_km: float = DEFAULT_LENGTH_KM,
        base_altitude_m: float = 120.0,
        profile: str = "hilly",
    ):
        if not (MIN_LENGTH_KM <= length_km <= MAX_LENGTH_KM):
            raise ValueError(
                f"route length must be in [{MIN_LENGTH_KM}, {MAX_LENGTH_KM}] km, got {length_km}")
        style = PROFILE_STYLES.get(profile)
        if style is None:
            raise ValueError(f"unknown route profile {profile!r}; "
                             f"expected one of {sorted(PROFILE_STYLES)}")
        self.seed = int(seed)
        self.length_km = float(length_km)
        self.base_altitude_m = float(base_altitude_m)
        self.profile = profile
        self._rng = random.Random(self.seed)
        self._build(style)

    # ------------------------------------------------------------------ build
    def _build(self, style: Dict[str, Any]) -> None:
        """Generate the gradient samples and integrate them into elevation."""
        n = int(math.ceil(self.length_km / SAMPLE_INTERVAL_KM)) + 1
        length = self.length_km

        # Deterministic harmonic coefficients from the seed.
        amps = [self._rng.uniform(a * 0.6, a * 1.4) for a in style["amps"]]
        phases = [self._rng.uniform(0.0, 2.0 * math.pi) for _ in style["amps"]]
        freqs = [2.0 * math.pi * (k + 1) / length for k in range(len(amps))]

        base = style["base"]

        # Gentle seeded baseline ramp keeps the profile interesting but bounded.
        ramp = self._rng.uniform(-1.2, 1.2)

        gradients: List[float] = []
        for i in range(n):
            x = i * SAMPLE_INTERVAL_KM
            g = base * sum(a * math.sin(f * x + p) for a, f, p in zip(amps, freqs, phases))
            g += ramp * math.sin(math.pi * x / length)
            gradients.append(clamp(g, -MAX_GRADIENT_PCT, MAX_GRADIENT_PCT))

        # Integrate gradient -> smooth elevation (m). delta_alt = g% * dx * 1000.
        altitudes: List[float] = []
        alt = self.base_altitude_m
        for g in gradients:
            altitudes.append(alt)
            alt += g / 100.0 * SAMPLE_INTERVAL_KM * 1000.0
            if alt < 0.0:
                alt = 0.0  # stay above sea level

        self._gradients = gradients
        self._altitudes = altitudes
        self._offsets = [i * SAMPLE_INTERVAL_KM for i in range(n)]
        self._n = n

    # ------------------------------------------------------------------ query
    def elevation_at(self, distance_km: float) -> float:
        """Elevation (m) at a traveled distance, by linear interpolation."""
        d = clamp(float(distance_km), 0.0, self.length_km)
        i = int(d / SAMPLE_INTERVAL_KM)
        i = min(i, self._n - 2)
        frac = (d - self._offsets[i]) / SAMPLE_INTERVAL_KM
        return self._altitudes[i] * (1.0 - frac) + self._altitudes[i + 1] * frac

    def gradient_at(self, distance_km: float) -> float:
        """Gradient (%) at a traveled distance (from the gradient profile)."""
        d = clamp(float(distance_km), 0.0, self.length_km)
        i = int(d / SAMPLE_INTERVAL_KM)
        i = min(i, self._n - 1)
        return self._gradients[i]

    def full_profile(self) -> List[Tuple[float, float]]:
        """Return [(distance_km, altitude_m), ...] for the whole route."""
        return list(zip(self._offsets, self._altitudes))

    def ahead_terrain(
        self,
        from_distance_km: float,
        horizon_km: float = 5.0,
        step_km: float = 0.25,
    ) -> List[Dict[str, float]]:
        """Return upcoming terrain points ahead of a traveled position.

        Each point has offset_km (distance ahead of the current point) and
        absolute altitude_m -- the format the RouteTerrainInput schema expects.
        offset 0 == current position. Only terrain at >= from_distance_km is
        returned (causal: no information about where the vehicle hasn't been).
        """
        if horizon_km <= 0:
            raise ValueError("horizon_km must be > 0")
        points: List[Dict[str, float]] = []
        offset = 0.0
        while offset <= horizon_km + 1e-9:
            d = from_distance_km + offset
            if d > self.length_km:
                break
            points.append({
                "offset_km": round(offset, 3),
                "altitude_m": round(self.elevation_at(d), 2),
            })
            offset += step_km
        if len(points) < 2:
            raise ValueError("route is too short to provide upcoming terrain")
        return points

    def summary(self) -> Dict[str, Any]:
        """Compact route description for display/audit."""
        return {
            "seed": self.seed,
            "profile": self.profile,
            "length_km": round(self.length_km, 2),
            "base_altitude_m": round(self.base_altitude_m, 1),
            "min_altitude_m": round(min(self._altitudes), 1),
            "max_altitude_m": round(max(self._altitudes), 1),
            "total_gain_m": round(
                sum(max(self._altitudes[i] - self._altitudes[i - 1], 0.0)
                    for i in range(1, self._n)), 1),
            "max_gradient_pct": round(max(self._gradients), 2),
            "min_gradient_pct": round(min(self._gradients), 2),
        }
