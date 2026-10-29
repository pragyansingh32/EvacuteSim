"""Balanced exit assignment (Strategy C's optimization step).

Greedy min-makespan heuristic: process occupants one at a time (grouped by
their zone, in a deterministic order) and give each to the exit whose
*estimated finish time* is lowest:

    finish(exit) = mean_travel_time(zone -> exit) + (assigned_count + 1) / capacity

This water-filling naturally sends more people to high-capacity, nearby exits
and throttles assignment to overloaded ones. It is a heuristic — it does not
solve the assignment problem optimally — and travel times use a single
reference speed because individual speeds are unknown at assignment time.
"""

from __future__ import annotations

from app.simulation.grid import BuildingGrid


def mean_zone_exit_travel_s(
    grid: BuildingGrid,
    zone_cells: list[tuple[int, int]],
    dist_field: dict[tuple[int, int], int],
    cell_size_m: float,
    reference_speed_mps: float,
) -> float | None:
    """Mean modeled walking time from a zone's reachable cells to one exit."""
    times = [
        d * cell_size_m / reference_speed_mps
        for cell, d in ((c, dist_field.get(c)) for c in zone_cells)
        if d is not None
    ]
    if not times:
        return None
    return sum(times) / len(times)


def balanced_zone_assignment(
    grid: BuildingGrid,
    zone_populations: dict[str, int],
    dist_fields: dict[str, dict[tuple[int, int], int]],
    exit_ids: list[str],
    capacities_pps: dict[str, float],
    reference_speed_mps: float,
) -> tuple[dict[str, dict[str, int]], dict[str, str]]:
    """Distribute each zone's population across exits.

    Returns:
        zone_to_exit_counts: {zone_id: {exit_id: number_of_people}}
        zone_primary_exit:   {zone_id: exit_id receiving the most people}
            (used for per-occupant interpolation within a zone)

    Raises nothing; zones with population 0 are simply skipped, and zones with
    no reachable exit get an empty count map (the engine will mark those
    occupants unreachable or fall back individually).
    """
    zone_to_exit_counts: dict[str, dict[str, int]] = {}
    assigned_totals: dict[str, int] = {e: 0 for e in exit_ids}

    # Deterministic zone processing order.
    for zone_id in sorted(zone_populations):
        population = int(zone_populations.get(zone_id, 0))
        if population <= 0:
            continue
        zone_cells = grid.zone_cells(zone_id)
        counts: dict[str, int] = {e: 0 for e in exit_ids}
        travel: dict[str, float] = {}
        for exit_id in exit_ids:
            mean_t = mean_zone_exit_travel_s(
                grid, zone_cells, dist_fields[exit_id], grid.cell_size_m, reference_speed_mps
            )
            if mean_t is not None:
                travel[exit_id] = mean_t
        if not travel:
            zone_to_exit_counts[zone_id] = {}
            continue
        for _ in range(population):
            best_exit = min(
                travel,
                key=lambda e: (
                    travel[e] + (assigned_totals[e] + 1) / max(capacities_pps[e], 1e-9),
                    e,  # deterministic tie-break by exit id
                ),
            )
            counts[best_exit] += 1
            assigned_totals[best_exit] += 1
        zone_to_exit_counts[zone_id] = counts

    zone_primary_exit = {
        zone_id: (max(counts, key=lambda e: (counts[e], e)) if counts else "")
        for zone_id, counts in zone_to_exit_counts.items()
    }
    return zone_to_exit_counts, zone_primary_exit
