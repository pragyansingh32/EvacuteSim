# Algorithms

## Pathfinding

`app/algorithms/pathfinding.py`

**BFS distance fields** over the 4-connected grid. The grid is unweighted and
movement is four-directional, so BFS gives exact shortest step counts. The
engine computes one single-source field per available exit before the run
starts (cost: one BFS per exit over ≤ 14,400 cells). Path extraction is
implicit: an occupant moves to the neighbor with the smallest remaining
distance (deterministic tie-break N, E, S, W), so no per-occupant path
storage is needed. Cells removed by a scenario (blocked exits/cells) are
excluded before the fields are computed - closed routes are structurally
unusable.

Complexity: O(exits × cells) time once per run; O(1) per movement decision.

## Routing strategies

`app/algorithms/strategies.py` - all strategies share the identical movement
machinery; they differ **only** in exit choice, which is what makes
comparisons fair.

### Strategy A - `nearest_exit` (baseline)

Pick the reachable exit with the minimal BFS distance; ties break by exit id
in sorted order. Assigned once at spawn; never revisited.

### Strategy B - `capacity_aware`

Minimize the estimated total time:

```
cost(exit) = dist(exit, cell) × cell_size / speed
           + live_load(exit) / capacity(exit)
```

`live_load` counts occupants currently routed to that exit and still inside -
a deliberately simple, explainable queue proxy, not a calibrated flow model.
Re-evaluated every 8 steps (2 s at default dt) with a 10 % improvement
hysteresis to prevent oscillation between near-equivalent exits. Because
assignments accumulate during spawn processing, the population naturally
spreads across doors as loads build up.

### Strategy C - `balanced_assignment`

A pre-computed greedy **min-makespan assignment** of each zone's population
across exits (`app/algorithms/assignment.py`). Process occupants one at a
time (zones in sorted order) and give each to the exit minimizing:

```
finish(exit) = mean_travel_time(zone → exit) + (assigned_count + 1) / capacity
```

This water-filling favors high-capacity, nearby doors and throttles assignment
to overloaded ones. Per-occupant assignment deals the zone's exit counts to
occupants in a seeded shuffled order. Travel times use a single reference
speed (the distribution mean) because individual speeds are unknown at
assignment time - a documented approximation.

If an occupant's assigned exit is unreachable from its cell (possible for
spilled occupants or zones straddling walls), the occupant **falls back** to
the nearest reachable exit and the fallback is counted in the results
(`fallback_count`), so degraded behavior is visible rather than hidden.

## Occupant placement

For each zone (sorted order): candidate cells are the zone's walkable cells
(sorted, then seeded-shuffled); occupants take cells until the zone is full.
Shortfalls **spill** into the nearest free walkable cells via BFS from the
zone's cells (deterministic frontier expansion). A population exceeding all
walkable space is a hard error.

## Conflict resolution & movement application

See docs/SIMULATION_MODEL.md ("Conflict resolution"). In short: rotated
deterministic order (anti-starvation), application-time occupancy checks
(following), and simultaneous cycle swaps (deadlock-free single-file flow).

## Exit discharge

Rate-limit accumulator per exit: gains `capacity × dt` per step, discharges
the FIFO queue (arrival time, then id) as credit allows, banks at most one
credit while idle. See docs/SIMULATION_MODEL.md.

## Why these choices

- **BFS over A\***: unweighted grid; distance fields serve *all* occupants
  from one computation per exit; A\* would re-plan per occupant for no gain.
- **Heuristic assignment over exact optimization**: the balanced-assignment
  problem is small but the benefit of an exact solver (ILP) is marginal for
  zone-level counts and would add a solver dependency; the greedy is
  explainable in one paragraph and testable in isolation.
- **One movement engine for all strategies**: any observed difference between
  strategies is attributable to routing, not to engine mechanics.
