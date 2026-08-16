"""Tests for the Step 9 range estimator module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from src.inference.range_estimator import RangeEstimator, estimate_range


@pytest.fixture
def est():
    return RangeEstimator(reserve_soc_pct=10)


def test_normal_range_calculation(est):
    r = est.estimate_range(33, 60, 0.14)
    assert r['usable_energy_kwh'] == pytest.approx(16.5)
    assert r['estimated_range_km'] == pytest.approx(16.5 / 0.14)


def test_soc_validation(est):
    with pytest.raises(ValueError):
        est.estimate_range(33, -1, 0.14)
    with pytest.raises(ValueError):
        est.estimate_range(33, 101, 0.14)


def test_reserve_validation():
    with pytest.raises(ValueError):
        RangeEstimator(reserve_soc_pct=-5)
    with pytest.raises(ValueError):
        RangeEstimator(reserve_soc_pct=100)


def test_zero_consumption_rejection(est):
    with pytest.raises(ValueError):
        est.estimate_range(33, 60, 0.0)


def test_negative_consumption_rejection(est):
    with pytest.raises(ValueError):
        est.estimate_range(33, 60, -0.1)


def test_zero_capacity_rejection(est):
    with pytest.raises(ValueError):
        est.estimate_range(0, 60, 0.14)


def test_soc_below_reserve(est):
    r = est.estimate_range(33, 8, 0.14)
    assert r['usable_energy_kwh'] == 0.0
    assert r['estimated_range_km'] == 0.0


def test_expected_range_calculation(est):
    r = est.estimate_range(33, 60, 0.14)
    assert r['expected_range_km'] == r['estimated_range_km']
    assert r['conservative_range_km'] == r['expected_range_km']
    assert r['optimistic_range_km'] == r['expected_range_km']


def test_conservative_optimistic_ordering(est):
    r = est.estimate_range_band(33, 60, 0.14, -0.05, 0.04)
    assert r['conservative_range_km'] <= r['expected_range_km'] <= r['optimistic_range_km']
    # higher consumption -> lower range; verify band edges differ
    assert r['conservative_range_km'] < r['optimistic_range_km']


def test_band_guard_limits_optimistic_range(est):
    # very low prediction with negative q_low must not explode to absurd range
    r = est.estimate_range_band(62, 80, 0.05, -0.05, 0.04)
    assert r['optimistic_range_km'] <= 2 * r['expected_range_km'] + 1e-9


def test_band_quantile_validation(est):
    with pytest.raises(ValueError):
        est.estimate_range_band(33, 60, 0.14, 0.1, -0.1)  # low > high


def test_convenience_function():
    r = estimate_range(33, 60, 0.14)
    assert r['estimated_range_km'] == pytest.approx(16.5 / 0.14)