"""
STEP 9H - RANGE ESTIMATOR MODULE

Estimates remaining driving range from predicted energy consumption.

Theoretical formulation (engineering estimate, NOT ground-truth range):

    usable_energy_kwh = battery_capacity_kwh * max(soc_pct - reserve_soc_pct, 0) / 100
    estimated_range_km = usable_energy_kwh / predicted_energy_kwh_per_km

Uncertainty band (optional): the caller supplies residual quantiles of the
model on TRAIN+VALIDATION (q_low < q_high). A positive residual means the
model under-predicted consumption (prediction < actual), so actual
consumption is expected to be HIGHER -> conservative (lower) range.
Conversely a negative residual means over-prediction -> optimistic (higher)
range.

    low_consumption     = predicted + q_high   (higher consumption -> lower range)
    high_consumption    = predicted + q_low    (lower consumption  -> higher range)
    conservative_range  = usable_energy / low_consumption
    expected_range      = usable_energy / predicted
    optimistic_range    = usable_energy / high_consumption

Validation:
    - 0 <= soc_pct <= 100
    - battery_capacity_kwh > 0
    - predicted_energy_kwh_per_km > 0
    - 0 <= reserve_soc_pct < 100
    - reserve_soc_pct < soc_pct for positive usable energy (else usable = 0)
"""
from __future__ import annotations

import math


class RangeEstimator:
    """Estimate remaining driving range from SOC and predicted consumption."""

    DEFAULT_RESERVE_SOC_PCT = 10.0

    def __init__(self, reserve_soc_pct: float = DEFAULT_RESERVE_SOC_PCT):
        self.validate_reserve(reserve_soc_pct)
        self.reserve_soc_pct = float(reserve_soc_pct)

    # -- validation helpers -------------------------------------------------
    @staticmethod
    def validate_soc(soc_pct: float) -> None:
        if soc_pct is None or not math.isfinite(float(soc_pct)):
            raise ValueError('soc_pct must be a finite number')
        if not (0 <= float(soc_pct) <= 100):
            raise ValueError(f'soc_pct must be in [0, 100], got {soc_pct}')

    @staticmethod
    def validate_capacity(battery_capacity_kwh: float) -> None:
        if battery_capacity_kwh is None or not math.isfinite(float(battery_capacity_kwh)):
            raise ValueError('battery_capacity_kwh must be a finite number')
        if float(battery_capacity_kwh) <= 0:
            raise ValueError(f'battery_capacity_kwh must be > 0, got {battery_capacity_kwh}')

    @staticmethod
    def validate_consumption(predicted_energy_kwh_per_km: float) -> None:
        if (predicted_energy_kwh_per_km is None
                or not math.isfinite(float(predicted_energy_kwh_per_km))):
            raise ValueError('predicted_energy_kwh_per_km must be a finite number')
        if float(predicted_energy_kwh_per_km) <= 0:
            raise ValueError(
                f'predicted_energy_kwh_per_km must be > 0, got {predicted_energy_kwh_per_km}')

    @staticmethod
    def validate_reserve(reserve_soc_pct: float) -> None:
        if reserve_soc_pct is None or not math.isfinite(float(reserve_soc_pct)):
            raise ValueError('reserve_soc_pct must be a finite number')
        if not (0 <= float(reserve_soc_pct) < 100):
            raise ValueError(f'reserve_soc_pct must be in [0, 100), got {reserve_soc_pct}')

    # -- core computation ---------------------------------------------------
    def usable_energy_kwh(self, battery_capacity_kwh: float, soc_pct: float) -> float:
        """Available battery energy after applying the SOC reserve."""
        self.validate_capacity(battery_capacity_kwh)
        self.validate_soc(soc_pct)
        return float(battery_capacity_kwh) * max(float(soc_pct) - self.reserve_soc_pct, 0.0) / 100.0

    def estimate_range(self, battery_capacity_kwh: float, soc_pct: float,
                       predicted_energy_kwh_per_km: float) -> dict:
        """Return usable energy and estimated range."""
        usable = self.usable_energy_kwh(battery_capacity_kwh, soc_pct)
        self.validate_consumption(predicted_energy_kwh_per_km)
        if usable <= 0:
            # SOC at/below reserve: no usable energy -> zero range
            return {
                'usable_energy_kwh': 0.0,
                'estimated_range_km': 0.0,
                'conservative_range_km': 0.0,
                'expected_range_km': 0.0,
                'optimistic_range_km': 0.0,
            }
        est = usable / float(predicted_energy_kwh_per_km)
        return {
            'usable_energy_kwh': usable,
            'estimated_range_km': est,
            'conservative_range_km': est,
            'expected_range_km': est,
            'optimistic_range_km': est,
        }

    def estimate_range_band(self, battery_capacity_kwh: float, soc_pct: float,
                            predicted_energy_kwh_per_km: float,
                            residual_q_low: float, residual_q_high: float) -> dict:
        """
        Range estimate with an uncertainty band.

        residual_q_low / residual_q_high are model residual quantiles from
        TRAIN+VALIDATION only (q_low < q_high). residual = prediction - actual.
        Positive residual => model under-predicts consumption => actual
        consumption higher => lower range (conservative).

        Guard: absolute residual quantiles can push the optimistic consumption
        toward zero when a prediction lies far below the residual tail (this
        would produce absurd ranges). The consumption used for the band is
        floored at `0.5 * predicted` so the optimistic range never exceeds
        2x the expected range. Documented engineering safeguard.

        Ordering guarantee: conservative <= expected <= optimistic.
        """
        usable = self.usable_energy_kwh(battery_capacity_kwh, soc_pct)
        self.validate_consumption(predicted_energy_kwh_per_km)
        if not math.isfinite(float(residual_q_low)) or not math.isfinite(float(residual_q_high)):
            raise ValueError('residual quantiles must be finite numbers')
        if float(residual_q_low) > float(residual_q_high):
            raise ValueError('residual_q_low must be <= residual_q_high')
        if usable <= 0:
            return {'usable_energy_kwh': 0.0, 'estimated_range_km': 0.0,
                    'conservative_range_km': 0.0, 'expected_range_km': 0.0,
                    'optimistic_range_km': 0.0}

        p = float(predicted_energy_kwh_per_km)
        floor = 0.5 * p
        # higher consumption (prediction + q_high) -> lower range (conservative)
        low_consumption = max(p + float(residual_q_high), floor)
        # lower consumption (prediction + q_low) -> higher range (optimistic)
        high_consumption = max(p + float(residual_q_low), floor)

        conservative = usable / low_consumption
        expected = usable / p
        optimistic = usable / high_consumption

        conservative, expected, optimistic = sorted(
            (conservative, expected, optimistic))  # ensures conservative <= expected <= optimistic
        return {
            'usable_energy_kwh': usable,
            'estimated_range_km': expected,
            'conservative_range_km': conservative,
            'expected_range_km': expected,
            'optimistic_range_km': optimistic,
            'low_consumption_kwh_per_km': low_consumption,
            'high_consumption_kwh_per_km': high_consumption,
        }


def estimate_range(battery_capacity_kwh: float, soc_pct: float,
                   predicted_energy_kwh_per_km: float,
                   reserve_soc_pct: float = RangeEstimator.DEFAULT_RESERVE_SOC_PCT) -> dict:
    """Convenience function for a single range estimate."""
    est = RangeEstimator(reserve_soc_pct=reserve_soc_pct)
    return est.estimate_range(battery_capacity_kwh, soc_pct, predicted_energy_kwh_per_km)