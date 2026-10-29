"""Routing strategies.

All strategies answer one question: *which exit should this occupant head to?*
Movement itself (pathfinding, conflicts, queues) is handled identically by the
engine for every strategy, so strategy comparisons isolate only the routing
decision.

Three strategies are implemented:

- ``nearest_exit``    — baseline: closest reachable exit by BFS distance.
- ``capacity_aware``  — balances expected travel time against modeled door
  queues: cost = travel time + (current live load on exit) / capacity.
  Re-evaluated periodically as queues evolve.
- ``balanced_assignment`` — a pre-computed greedy min-makespan assignment of
  each zone's population across exits (see ``assignment.py``). Occupants keep
  their assigned exit; if it is unreachable from their cell they fall back to
  the nearest reachable one (recorded as ``fallback_used``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

STRATEGY_NEAREST = "nearest_exit"
STRATEGY_CAPACITY_AWARE = "capacity_aware"
STRATEGY_BALANCED = "balanced_assignment"

STRATEGY_NAMES = (STRATEGY_NEAREST, STRATEGY_CAPACITY_AWARE, STRATEGY_BALANCED)

# Re-evaluation period for the capacity-aware strategy, in simulation steps.
# 8 steps at the default 0.25 s step = every 2 s of simulated time; frequent
# enough to react to queues, rare enough to keep large runs fast and to avoid
# oscillation between exits.
CAPACITY_REEVALUATE_EVERY = 8

# Relative improvement required before a re-assignment happens (hysteresis,
# prevents thrashing between near-equivalent exits).
CAPACITY_SWITCH_MARGIN = 0.10


class StrategyContext:
    """Everything a strategy may look at when choosing an exit.

    The engine owns and updates this object; strategies only read it.
    """

    def __init__(
        self,
        exit_ids: list[str],
        dist_fields: dict[str, dict[tuple[int, int], int]],
        cell_size_m: float,
        capacities_pps: dict[str, float],
        reference_speed_mps: float,
    ) -> None:
        self.exit_ids = exit_ids
        self.dist_fields = dist_fields  # per-exit BFS distance fields
        self.cell_size_m = cell_size_m
        self.capacities_pps = capacities_pps
        self.reference_speed_mps = reference_speed_mps
        # Live load per exit: number of occupants currently routed to it and
        # still inside. Updated by the engine each step.
        self.live_load: dict[str, int] = {e: 0 for e in exit_ids}

    def travel_time_s(self, exit_id: str, cell: tuple[int, int], speed_mps: float) -> float | None:
        """Modeled walking time from a cell to an exit, or None if unreachable."""
        dist = self.dist_fields[exit_id].get(cell)
        if dist is None:
            return None
        speed = speed_mps if speed_mps > 0 else self.reference_speed_mps
        return dist * self.cell_size_m / speed


class RoutingStrategy(ABC):
    """Interface for exit-choice policies."""

    name: str

    @abstractmethod
    def choose_exit(self, cell: tuple[int, int], speed_mps: float, ctx: StrategyContext) -> str | None:
        """Return the exit id the occupant at `cell` should head to, or None
        if no exit is reachable from that cell."""


class NearestExitStrategy(RoutingStrategy):
    """Strategy A — the baseline: minimize BFS step distance to any reachable exit."""

    name = STRATEGY_NEAREST

    def choose_exit(self, cell: tuple[int, int], speed_mps: float, ctx: StrategyContext) -> str | None:
        best_id: str | None = None
        best_dist = 10**9
        for exit_id in ctx.exit_ids:  # fixed order => deterministic ties
            dist = ctx.dist_fields[exit_id].get(cell)
            if dist is not None and dist < best_dist:
                best_dist = dist
                best_id = exit_id
        return best_id


class CapacityAwareStrategy(RoutingStrategy):
    """Strategy B — minimize estimated total time: walking + expected door queue.

    Expected queue time is approximated as (live load on the exit) / capacity,
    where live load counts occupants currently routed to that exit and still
    inside. This is an intentionally simple, explainable queue model, not a
    calibrated flow model.
    """

    name = STRATEGY_CAPACITY_AWARE

    def choose_exit(self, cell: tuple[int, int], speed_mps: float, ctx: StrategyContext) -> str | None:
        best_id: str | None = None
        best_cost = 10**9
        for exit_id in ctx.exit_ids:
            travel = ctx.travel_time_s(exit_id, cell, speed_mps)
            if travel is None:
                continue
            capacity = max(ctx.capacities_pps[exit_id], 1e-9)
            cost = travel + ctx.live_load[exit_id] / capacity
            if cost < best_cost:
                best_cost = cost
                best_id = exit_id
        return best_id

    def maybe_reassign(
        self,
        cell: tuple[int, int],
        speed_mps: float,
        current_exit: str,
        ctx: StrategyContext,
    ) -> str | None:
        """Re-evaluate with hysteresis: switch only if meaningfully better."""
        candidate = self.choose_exit(cell, speed_mps, ctx)
        if candidate is None or candidate == current_exit:
            return None
        cur_travel = ctx.travel_time_s(current_exit, cell, speed_mps)
        new_travel = ctx.travel_time_s(candidate, cell, speed_mps)
        if cur_travel is None or new_travel is None:
            return candidate
        cur_capacity = max(ctx.capacities_pps[current_exit], 1e-9)
        new_capacity = max(ctx.capacities_pps[candidate], 1e-9)
        cur_cost = cur_travel + ctx.live_load[current_exit] / cur_capacity
        new_cost = new_travel + ctx.live_load[candidate] / new_capacity
        if new_cost < cur_cost * (1.0 - CAPACITY_SWITCH_MARGIN):
            return candidate
        return None


class BalancedAssignmentStrategy(RoutingStrategy):
    """Strategy C — occupants follow a pre-computed zone-to-exit assignment.

    The assignment itself is computed by ``assignment.balanced_zone_assignment``
    before the simulation starts. This class only resolves it per occupant and
    falls back to the nearest reachable exit when the assignment is impossible
    from a particular cell.
    """

    name = STRATEGY_BALANCED

    def __init__(self, occupant_assignments: dict[int, str]) -> None:
        # occupant id -> exit id (may be None for occupants without assignment)
        self.occupant_assignments = occupant_assignments

    def choose_exit(self, cell: tuple[int, int], speed_mps: float, ctx: StrategyContext) -> str | None:  # noqa: ARG002
        raise NotImplementedError("Balanced strategy resolves via assigned_exit_for(), not choose_exit.")

    def assigned_exit_for(self, occupant_id: int, cell: tuple[int, int], speed_mps: float, ctx: StrategyContext) -> str | None:
        assigned = self.occupant_assignments.get(occupant_id)
        if assigned is not None and cell in ctx.dist_fields[assigned]:
            return assigned
        return NearestExitStrategy().choose_exit(cell, speed_mps, ctx)


def get_strategy(name: str) -> RoutingStrategy:
    if name == STRATEGY_NEAREST:
        return NearestExitStrategy()
    if name == STRATEGY_CAPACITY_AWARE:
        return CapacityAwareStrategy()
    if name == STRATEGY_BALANCED:
        raise ValueError(
            "balanced_assignment requires pre-computed occupant assignments; "
            "construct BalancedAssignmentStrategy directly."
        )
    raise ValueError(f"Unknown routing strategy '{name}'.")
