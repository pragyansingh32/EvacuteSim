"""Metrics helper tests."""

from app.simulation.metrics import percentile_of_sorted


def test_percentile_empty():
    assert percentile_of_sorted([], 0.5) is None


def test_percentile_single():
    assert percentile_of_sorted([5.0], 0.5) == 5.0


def test_percentile_monotonic():
    values = sorted([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    t50 = percentile_of_sorted(values, 0.5)
    t90 = percentile_of_sorted(values, 0.9)
    t95 = percentile_of_sorted(values, 0.95)
    assert t50 <= t90 <= t95
    # Index rule: T(f) = values[min(n-1, floor(f*n))].
    assert t50 == values[5] == 6.0
    assert t90 == values[9] == 10.0
