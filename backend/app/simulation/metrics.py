"""Derived metrics helpers."""

from __future__ import annotations


def percentile_of_sorted(sorted_values: list[float], fraction: float) -> float | None:
    """Time by which `fraction` of the sorted values were reached.

    Uses a simple index rule: for n values, T(f) = sorted[min(n-1, floor(f*n))].
    For n=0 returns None. This is intentionally coarse (step-resolution data)
    and deterministic.
    """
    n = len(sorted_values)
    if n == 0:
        return None
    idx = min(n - 1, int(fraction * n))
    return sorted_values[idx]
