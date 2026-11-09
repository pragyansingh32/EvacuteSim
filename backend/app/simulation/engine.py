"""The discrete-time evacuation engine.

Model summary (see docs/SIMULATION_MODEL.md for the full write-up):

- The building is a grid; each cell holds at most one occupant. Movement is
  four-directional; diagonal moves are impossible.
- Each occupant has a walking speed (m/s) and a pre-movement reaction delay (s).
- Time advances in fixed steps of `dt_s`. An occupant may advance one cell per
  step once its movement accumulator has collected at least one cell traversal
  time (`cell_size_m / speed`). This makes walking speed directly control
  movement frequency.
- Every step: (1) waiting occupants whose reaction delay has elapsed activate;
  (2) active occupants request their next cell; (3) contests for the same cell
  are resolved deterministically by a seeded per-occupant priority; (4) moves
  are applied (including following into just-vacated cells and, as a documented
  simplification, head-on swaps/cycles so single-file flows cannot deadlock);
  (5) occupants standing on an exit cell are discharged subject to that exit's
  throughput accumulator; (6) metrics are recorded.

Determinism: a single numpy Generator seeded from the scenario seed drives all
randomness (spawn placement, attribute sampling, conflict priorities). The same
layout + config + seed + code version produces identical results.
"""

from __future__ import annotations

import time as wallclock
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from app.algorithms.assignment import balanced_zone_assignment
from app.algorithms.pathfinding import NEIGHBOR_OFFSETS, bfs_distance_field
from app.algorithms.strategies import (
    CAPACITY_REEVALUATE_EVERY,
    STRATEGY_BALANCED,
    STRATEGY_CAPACITY_AWARE,
    STRATEGY_NEAREST,
    BalancedAssignmentStrategy,
    CapacityAwareStrategy,
    NearestExitStrategy,
    RoutingStrategy,
    StrategyContext,
)
from app.core.config import settings
from app.core.errors import SimulationError, ValidationError
from app.simulation.disasters import DisasterSpec, create_disaster
from app.simulation.grid import BuildingGrid, cells_to_key
from app.simulation.metrics import percentile_of_sorted
from app.simulation.occupant import (
    INSIDE_STATUSES,
    STATUS_AT_EXIT,
    STATUS_CODES,
    STATUS_EVACUATED,
    STATUS_INCAPACITATED,
    STATUS_MOVING,
    STATUS_UNREACHABLE,
    STATUS_WAITING,
    Occupant,
)

ENGINE_VERSION = "1.0.0"


@dataclass
class EngineConfig:
    """Plain configuration for one engine run (converted from API schemas)."""

    strategy: str = STRATEGY_NEAREST
    zone_populations: dict[str, int] = field(default_factory=dict)
    speed_distribution: dict = field(
        default_factory=lambda: {"distribution": "normal", "mean": 1.2, "sd": 0.25, "min": 0.6, "max": 1.8}
    )
    pre_movement_distribution: dict = field(
        default_factory=lambda: {"distribution": "uniform", "min": 0.0, "max": 15.0}
    )
    blocked_cells: set[tuple[int, int]] = field(default_factory=set)
    blocked_exit_ids: set[str] = field(default_factory=set)
    exit_capacity_overrides: dict[str, float] = field(default_factory=dict)
    disasters: list[DisasterSpec] = field(default_factory=list)
    seed: int = 0
    max_duration_s: float = 600.0
    dt_s: float = settings.default_dt_s
    frame_interval_s: float = settings.default_frame_interval_s
    record_frames: bool = True


@dataclass
class RunResult:
    """Everything recorded from one engine run."""

    status: str  # "completed" | "incomplete"
    engine_version: str = ENGINE_VERSION
    sim_time_s: float = 0.0
    steps: int = 0
    wall_time_ms: int = 0
    total_occupants: int = 0
    evacuated_count: int = 0
    unreachable_count: int = 0
    incapacitated_count: int = 0
    remaining_count: int = 0
    remaining_breakdown: dict = field(default_factory=dict)
    disasters: list[dict] = field(default_factory=list)
    t50_s: float | None = None
    t90_s: float | None = None
    t95_s: float | None = None
    mean_evacuation_time_s: float | None = None
    max_evacuation_time_s: float | None = None
    min_evacuation_time_s: float | None = None
    exit_stats: list = field(default_factory=list)
    queue_total_s: float = 0.0
    queue_mean_s: float | None = None
    queue_max_s: float | None = None
    occupants_who_queued: int = 0
    congestion: dict = field(default_factory=dict)  # "x,y" -> blocked-move count
    fallback_count: int = 0
    timeline: list = field(default_factory=list)  # per-step [t, evacuated, inside, at_exit, incapacitated]
    frames: list = field(default_factory=list)  # sampled snapshots
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "engine_version": self.engine_version,
            "sim_time_s": self.sim_time_s,
            "steps": self.steps,
            "wall_time_ms": self.wall_time_ms,
            "total_occupants": self.total_occupants,
            "evacuated_count": self.evacuated_count,
            "unreachable_count": self.unreachable_count,
            "incapacitated_count": self.incapacitated_count,
            "remaining_count": self.remaining_count,
            "remaining_breakdown": self.remaining_breakdown,
            "disasters": self.disasters,
            "t50_s": self.t50_s,
            "t90_s": self.t90_s,
            "t95_s": self.t95_s,
            "mean_evacuation_time_s": self.mean_evacuation_time_s,
            "max_evacuation_time_s": self.max_evacuation_time_s,
            "min_evacuation_time_s": self.min_evacuation_time_s,
            "exit_stats": self.exit_stats,
            "queue": {
                "total_s": self.queue_total_s,
                "mean_s": self.queue_mean_s,
                "max_s": self.queue_max_s,
                "occupants_who_queued": self.occupants_who_queued,
            },
            "congestion": self.congestion,
            "fallback_count": self.fallback_count,
            "timeline": self.timeline,
            "frames": self.frames,
            "warnings": self.warnings,
        }


class _ExitRuntime:
    """Per-exit mutable state during a run."""

    __slots__ = ("defn", "capacity", "accumulator", "discharge_times")

    def __init__(self, exit_def, capacity: float) -> None:  # noqa: ANN001
        self.defn = exit_def
        self.capacity = capacity
        self.accumulator = 0.0
        self.discharge_times: list[float] = []


class EvacuationEngine:
    """Runs one evacuation simulation. Deterministic for a given seed/config."""

    def __init__(self, grid: BuildingGrid, config: EngineConfig) -> None:
        self.grid = grid
        self.config = config
        self.warnings: list[str] = []

        self._validate_config()

        self.rng = np.random.default_rng(config.seed)
        self.dt = config.dt_s
        self.blocked = grid.effective_blocked(config.blocked_cells, config.blocked_exit_ids)
        self.walkable = grid.walkable_with(self.blocked)

        # Available exits: scenario-blocked exits are removed entirely.
        self.exits_runtime: dict[str, _ExitRuntime] = {}
        for exit_id in sorted(grid.exits):
            if exit_id in config.blocked_exit_ids:
                continue
            exit_def = grid.exits[exit_id]
            capacity = config.exit_capacity_overrides.get(exit_id, exit_def.capacity_pps)
            if capacity <= 0:
                raise ValidationError(f"Exit '{exit_id}' capacity override must be positive.")
            self.exits_runtime[exit_id] = _ExitRuntime(exit_def, capacity)
        if not self.exits_runtime:
            raise SimulationError("All exits are blocked; evacuation is impossible in this scenario.")

        self.exit_cells: dict[tuple[int, int], str] = {
            rt.defn.key(): eid for eid, rt in self.exits_runtime.items()
        }

        # Distance fields (one BFS per available exit), recomputed whenever
        # the dynamic blocked set of a disaster grows.
        self.dynamic_blocked: set[tuple[int, int]] = set()
        self.dist_fields: dict[str, dict[tuple[int, int], int]] = {}
        self._recompute_fields()

        self._spawn_occupants()

        # Disaster models (fire / earthquake / stampede / etc.) - multiple
        # disasters can be active simultaneously. Each evolves during the
        # run: blocks cells dynamically, incapacitates occupants caught in
        # the event, and forces live re-routing.
        self.disasters: list = []
        for spec in config.disasters:
            model = create_disaster(
                spec,
                self.walkable,
                self.rng,
                self.dist_fields,
                {rt.defn.key() for rt in self.exits_runtime.values()},
                grid.width,
                grid.height,
            )
            if model is not None:
                self.disasters.append(model)
        if self.disasters:
            for d in self.disasters:
                if d.dynamic_blocked:
                    self.dynamic_blocked |= d.dynamic_blocked
            if self.dynamic_blocked:
                self._recompute_fields()
                self._incapacitate_on(self.dynamic_blocked)

        # Adaptive frame interval: cap the number of stored frames for very
        # long runs so result payloads stay bounded.
        est_frames = (self.dt * self._max_steps()) / max(config.frame_interval_s, 1e-9)
        if est_frames > settings.max_frames_per_run:
            config.frame_interval_s = round(
                (self.dt * self._max_steps()) / settings.max_frames_per_run, 3
            )
            self.warnings.append(
                f"Frame interval increased to {config.frame_interval_s}s to cap stored frames."
            )

        reference_speed = self._reference_speed()
        self.strategy_ctx = StrategyContext(
            exit_ids=sorted(self.exits_runtime),
            dist_fields=self.dist_fields,
            cell_size_m=grid.cell_size_m,
            capacities_pps={eid: rt.capacity for eid, rt in self.exits_runtime.items()},
            reference_speed_mps=reference_speed,
        )
        self.strategy: RoutingStrategy = self._build_strategy(reference_speed)

        self._assign_exits()

        # Counters and recording (fallback_count is set by _assign_exits).
        self.step_index = 0
        self.congestion: dict[str, int] = {}
        self.timeline: list[list[float]] = []
        self.frames: list[dict] = []
        self._next_frame_t = 0.0
        self.status = "incomplete"

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _validate_config(self) -> None:
        cfg = self.config
        if cfg.dt_s <= 0:
            raise ValidationError("Simulation time step must be positive.")
        if cfg.max_duration_s <= 0 or cfg.max_duration_s > settings.max_sim_duration_s:
            raise ValidationError(
                f"Maximum simulation duration must be between 0 and {settings.max_sim_duration_s} s."
            )
        speed_max = float(cfg.speed_distribution.get("max", 1.8))
        if speed_max <= 0:
            raise ValidationError("Maximum walking speed must be positive.")
        # One-cell-per-step resolution: the step must not exceed the fastest
        # occupant's traversal time, otherwise movement is under-sampled.
        max_dt = self.grid.cell_size_m / speed_max
        if cfg.dt_s > max_dt + 1e-9:
            raise ValidationError(
                f"Time step {cfg.dt_s}s is too large for a {self.grid.cell_size_m}m cell and "
                f"{speed_max}m/s maximum speed; use dt <= {max_dt:.3f}s."
            )
        total_population = sum(int(v) for v in cfg.zone_populations.values())
        if total_population <= 0:
            raise ValidationError("Scenario has no occupants; at least one zone needs a population.")
        if total_population > settings.max_occupants:
            raise ValidationError(
                f"Total population {total_population} exceeds the limit of {settings.max_occupants}."
            )
        if len(cfg.blocked_cells) > settings.max_blocked_cells:
            raise ValidationError("Too many blocked cells in scenario.")
        unknown_zones = set(cfg.zone_populations) - set(self.grid.zones)
        if unknown_zones:
            raise ValidationError(f"Scenario references unknown zone(s): {sorted(unknown_zones)}.")

    def _sample_speed(self) -> float:
        dist = self.config.speed_distribution
        kind = dist.get("distribution", "normal")
        lo = float(dist.get("min", 0.5))
        hi = float(dist.get("max", 2.0))
        if lo <= 0 or hi < lo:
            raise ValidationError("Walking-speed distribution bounds are invalid.")
        if kind == "uniform":
            value = float(self.rng.uniform(lo, hi))
        elif kind == "normal":
            mean = float(dist.get("mean", 1.2))
            sd = float(dist.get("sd", 0.25))
            if sd < 0:
                raise ValidationError("Walking-speed standard deviation must be >= 0.")
            value = float(np.clip(self.rng.normal(mean, sd), lo, hi))
        else:
            raise ValidationError(f"Unknown speed distribution '{kind}' (use 'normal' or 'uniform').")
        return value

    def _sample_reaction(self) -> float:
        dist = self.config.pre_movement_distribution
        kind = dist.get("distribution", "uniform")
        lo = float(dist.get("min", 0.0))
        hi = float(dist.get("max", 15.0))
        if lo < 0 or hi < lo:
            raise ValidationError("Pre-movement distribution bounds are invalid.")
        if kind == "uniform":
            value = float(self.rng.uniform(lo, hi))
        elif kind == "normal":
            mean = float(dist.get("mean", (lo + hi) / 2))
            sd = float(dist.get("sd", (hi - lo) / 6))
            if sd < 0:
                raise ValidationError("Pre-movement standard deviation must be >= 0.")
            value = float(np.clip(self.rng.normal(mean, sd), lo, hi))
        else:
            raise ValidationError(f"Unknown pre-movement distribution '{kind}' (use 'normal' or 'uniform').")
        return value

    def _spawn_occupants(self) -> None:
        """Place occupants in zones (with deterministic spill into nearby cells)."""
        placement: list[tuple[int, int]] = []
        self.zone_of_placement: list[str] = []
        for zone_id in sorted(self.config.zone_populations):
            population = int(self.config.zone_populations[zone_id])
            if population <= 0:
                continue
            zone = self.grid.zones[zone_id]
            candidates = [c for c in zone.cells if c in self.walkable]
            if not candidates:
                raise SimulationError(
                    f"Zone '{zone_id}' has no walkable cells in this scenario (blocked or walled)."
                )
            candidates.sort()  # deterministic base order before shuffling
            self.rng.shuffle(candidates)
            chosen = list(candidates[:population])
            shortfall = population - len(chosen)
            if shortfall > 0:
                spill = self._spill_cells(set(candidates), shortfall)
                chosen.extend(spill)
                self.warnings.append(
                    f"Zone '{zone_id}' holds {len(candidates)} cells but {population} occupants; "
                    f"{shortfall} spilled into nearby walkable cells."
                )
            placement.extend(chosen)
            self.zone_of_placement.extend([zone_id] * len(chosen))

        total = len(placement)
        if total > len(self.walkable):
            raise SimulationError(
                f"Population {total} exceeds available walkable cells {len(self.walkable)} "
                "in this scenario."
            )
        occupants: list[Occupant] = []
        for i, (x, y) in enumerate(placement):
            occupants.append(
                Occupant(
                    id=i,
                    x=x,
                    y=y,
                    speed_mps=self._sample_speed(),
                    reaction_delay_s=self._sample_reaction(),
                    priority=float(self.rng.random()),
                )
            )
        self.occupants = occupants
        self.occupied: set[tuple[int, int]] = {o.pos for o in occupants}
        # Occupants spawning on an exit cell are already at a door: they join
        # that door's queue but only become dischargeable once they react.
        for occ in occupants:
            exit_id = self.exit_cells.get(occ.pos)
            if exit_id is not None:
                occ.status = STATUS_AT_EXIT
                occ.exit_id = exit_id
                occ.exit_entered_t = 0.0
                occ.assigned_exit = exit_id

    def _spill_cells(self, already_used: set[tuple[int, int]], count: int) -> list[tuple[int, int]]:
        """Nearest free walkable cells via BFS from the used set (deterministic)."""
        found: list[tuple[int, int]] = []
        visited = set(already_used)
        queue = deque(sorted(already_used))
        while queue and len(found) < count:
            x, y = queue.popleft()
            for dx, dy in NEIGHBOR_OFFSETS:
                nxt = (x + dx, y + dy)
                if nxt in self.walkable and nxt not in visited:
                    visited.add(nxt)
                    if nxt not in already_used:
                        found.append(nxt)
                        if len(found) >= count:
                            break
                    queue.append(nxt)
        if len(found) < count:
            raise SimulationError("Not enough walkable space to place all occupants.")
        return found

    def _reference_speed(self) -> float:
        mean = self.config.speed_distribution.get("mean")
        if isinstance(mean, (int, float)) and float(mean) > 0:
            return float(mean)
        return 1.2

    def _build_strategy(self, reference_speed: float) -> RoutingStrategy:
        name = self.config.strategy
        if name == STRATEGY_NEAREST:
            return NearestExitStrategy()
        if name == STRATEGY_CAPACITY_AWARE:
            return CapacityAwareStrategy()
        if name == STRATEGY_BALANCED:
            zone_counts, _ = balanced_zone_assignment(
                grid=self.grid,
                zone_populations=self.config.zone_populations,
                dist_fields=self.dist_fields,
                exit_ids=sorted(self.exits_runtime),
                capacities_pps={eid: rt.capacity for eid, rt in self.exits_runtime.items()},
                reference_speed_mps=reference_speed,
            )
            return BalancedAssignmentStrategy(self._expand_zone_assignment(zone_counts))
        raise ValidationError(f"Unknown routing strategy '{name}'.")

    def _expand_zone_assignment(self, zone_counts: dict[str, dict[str, int]]) -> dict[int, str]:
        """Expand per-zone exit counts to per-occupant assignments, deterministic.

        Occupants are grouped by the zone they spawned in (spawn order is
        recorded in `zone_of_placement`), then dealt exit ids according to the
        counts in a seeded shuffled order.
        """
        by_zone: dict[str, list[int]] = {}
        for occ, zone_id in zip(self.occupants, self.zone_of_placement, strict=False):
            by_zone.setdefault(zone_id, []).append(occ.id)

        assignments: dict[int, str] = {}
        for zone_id, occ_ids in by_zone.items():
            counts = zone_counts.get(zone_id, {})
            exit_pool: list[str] = []
            for exit_id in sorted(counts):
                exit_pool.extend([exit_id] * counts[exit_id])
            if not exit_pool:
                continue  # occupants will fall back at resolve time
            exit_pool = list(exit_pool)
            self.rng.shuffle(exit_pool)
            for occ_id, exit_id in zip(sorted(occ_ids), exit_pool, strict=False):
                assignments[occ_id] = exit_id
        return assignments

    def _assign_exits(self) -> None:
        """Initial exit assignment and immediate unreachable detection."""
        for occ in self.occupants:
            if occ.status == STATUS_AT_EXIT and occ.exit_id is not None:
                # Spawned on a door: committed to that exit, no re-routing.
                self.strategy_ctx.live_load[occ.assigned_exit] += 1
                continue
            if isinstance(self.strategy, BalancedAssignmentStrategy):
                strategy: BalancedAssignmentStrategy = self.strategy
                pre_assigned = strategy.occupant_assignments.get(occ.id)
                exit_id = strategy.assigned_exit_for(
                    occ.id, occ.pos, occ.speed_mps, self.strategy_ctx
                )
                if exit_id != pre_assigned:
                    occ.fallback_used = True
            else:
                exit_id = self.strategy.choose_exit(occ.pos, occ.speed_mps, self.strategy_ctx)
            if exit_id is None:
                occ.status = STATUS_UNREACHABLE
                continue
            occ.assigned_exit = exit_id
            self.strategy_ctx.live_load[exit_id] += 1
        self.fallback_count = sum(1 for o in self.occupants if o.fallback_used)

    # ------------------------------------------------------------------
    # Simulation loop
    # ------------------------------------------------------------------

    def run(self) -> RunResult:
        started = wallclock.perf_counter()
        self._record_frame(0.0)
        max_steps = self._max_steps()
        while (
            self.evacuated_count + self.unreachable_count + self.incapacitated_count
            < self.total
        ):
            if self.step_index >= max_steps:
                self.status = "incomplete"
                self.warnings.append(
                    "Simulation stopped at the configured maximum duration; "
                    "not all occupants evacuated."
                )
                break
            self._step()
        else:
            self.status = "completed"
        if self.config.record_frames:
            final_t = self.step_index * self.dt
            if not self.frames or self.frames[-1]["t"] < final_t - 1e-9:
                # Record the true end state, bypassing the interval guard.
                self._next_frame_t = 0.0
                self._record_frame(final_t)
        return self._finalize(int((wallclock.perf_counter() - started) * 1000))

    def _recompute_fields(self) -> None:
        """Rebuild every exit's BFS distance field over the walkable set
        minus dynamically blocked cells (disaster effects). The dict object
        is updated in place so the strategy context stays valid."""
        effective = self.walkable - self.dynamic_blocked
        new_fields = {
            eid: bfs_distance_field(self.grid.width, self.grid.height, effective, {rt.defn.key()})
            for eid, rt in self.exits_runtime.items()
        }
        self.dist_fields.clear()
        self.dist_fields.update(new_fields)

    def _incapacitate_on(self, cells: set[tuple[int, int]]) -> None:
        """Occupants standing on cells destroyed by the disaster become
        incapacitated - a casualty count, never silently dropped."""
        for occ in self.occupants:
            if occ.status in INSIDE_STATUSES and occ.pos in cells:
                occ.status = STATUS_INCAPACITATED

    def _shove_from(self, cells: set[tuple[int, int]]) -> None:
        """Push occupants standing on newly crush-zoned cells to a free
        4-neighbor (the crowd shoves them aside); they are never lost."""
        for occ in self.occupants:
            if occ.status not in INSIDE_STATUSES or occ.pos not in cells:
                continue
            for dx, dy in NEIGHBOR_OFFSETS:
                nxt = (occ.x + dx, occ.y + dy)
                if (
                    nxt in self.walkable
                    and nxt not in self.dynamic_blocked
                    and nxt not in self.occupied
                ):
                    self.occupied.discard(occ.pos)
                    occ.x, occ.y = nxt
                    self.occupied.add(occ.pos)
                    break

    def _reroute_all(self) -> None:
        """After the route network changes, re-assign every active occupant
        whose assigned exit is no longer reachable from their position to the
        nearest reachable exit. Occupants with no reachable exit stay put
        (they remain inside and are reported as remaining)."""
        for occ in self.occupants:
            if occ.status not in (STATUS_MOVING, STATUS_WAITING):
                continue
            if occ.pos in self.dist_fields.get(occ.assigned_exit, {}):
                continue
            best = None
            best_dist = None
            for eid, fmap in self.dist_fields.items():
                d = fmap.get(occ.pos)
                if d is not None and (best_dist is None or d < best_dist):
                    best, best_dist = eid, d
            if best is not None and best != occ.assigned_exit:
                old = occ.assigned_exit
                if old in self.strategy_ctx.live_load:
                    self.strategy_ctx.live_load[old] -= 1
                occ.assigned_exit = best
                self.strategy_ctx.live_load[best] += 1
                occ.fallback_used = True

    def _max_steps(self) -> int:
        by_duration = int(self.config.max_duration_s / self.dt)
        return min(by_duration, settings.max_total_steps)

    @property
    def total(self) -> int:
        return len(self.occupants)

    @property
    def evacuated_count(self) -> int:
        return sum(1 for o in self.occupants if o.status == STATUS_EVACUATED)

    @property
    def unreachable_count(self) -> int:
        return sum(1 for o in self.occupants if o.status == STATUS_UNREACHABLE)

    @property
    def incapacitated_count(self) -> int:
        return sum(
            1 for o in self.occupants if o.status == STATUS_INCAPACITATED
        )

    def _step(self) -> None:
        t_start = self.step_index * self.dt
        t_end = t_start + self.dt

        # 0) Disaster evolution: multiple disasters can be active at once.
        #    Each blocks new cells (fire spread, earthquake collapse, stampede
        #    crush) and may incapacitate occupants standing there. Route
        #    fields are recomputed and everyone re-routed when the network
        #    changes. Stampede crush zones SHOVE occupants to free neighbors;
        #    fire/earthquake/gas/flood INCAPACITATE occupants on newly
        #    blocked cells.
        if self.disasters:
            newly = set()
            any_dirty = False
            has_stampede = False
            for d in self.disasters:
                step_new = d.step(t_end, self.dt, self.occupants)
                newly |= step_new
                if d.fields_dirty:
                    any_dirty = True
                if d.type == "stampede":
                    has_stampede = True
            if newly:
                self.dynamic_blocked |= newly
                if has_stampede:
                    self._shove_from(newly)
                else:
                    self._incapacitate_on(newly)
            if any_dirty and self.step_index % 8 == 0:
                self._recompute_fields()
                self._reroute_all()

        # 1) Activate occupants whose pre-movement delay has elapsed.
        # (Occupants spawned on an exit cell are AT_EXIT from spawn, so only
        # walkers are transitioned here.)
        for occ in self.occupants:
            if occ.status == STATUS_WAITING and t_end >= occ.reaction_delay_s - 1e-9:
                occ.status = STATUS_MOVING
                occ.reacted = True

        # 2) Periodic re-evaluation for the capacity-aware strategy.
        if (
            isinstance(self.strategy, CapacityAwareStrategy)
            and self.step_index % CAPACITY_REEVALUATE_EVERY == 0
        ):
            self._reevaluate_capacity_assignments()

        # 3) Movement requests (one cell per eligible occupant per step).
        # In stampede crush zones movement accrues at a reduced rate.
        requests: list[tuple[Occupant, tuple[int, int]]] = []
        for occ in self.occupants:
            if occ.status != STATUS_MOVING:
                continue
            factor = 1.0
            for d in self.disasters:
                factor *= d.speed_factor(occ.pos)
            occ.move_accumulator_s += self.dt * factor
            cell_time = self.grid.cell_size_m / occ.speed_mps
            if occ.move_accumulator_s + 1e-9 < cell_time:
                continue
            dest = self._next_cell(occ)
            if dest is not None:
                requests.append((occ, dest))

        # 4) Movement application. Every requester attempts its move in a
        # deterministic global order (seeded priority, rotated round-robin by
        # step so no one starves). Retry passes let a blocked requester follow
        # a mover out of the cell it wants; remaining head-on cycles are
        # swapped simultaneously (see _apply_moves).
        requests.sort(key=lambda od: (od[0].priority, od[0].id))
        if requests:
            rotation = self.step_index % len(requests)
            requests = requests[rotation:] + requests[:rotation]
        unmoved = self._apply_moves(requests, self.occupied, t_end)
        for occ, dest in unmoved:
            self._record_blocked([occ], dest)

        # 5) Discharge through exits (deterministic exit order, FIFO door queue).
        self._discharge(t_end, self.occupied)

        # 6) Record and advance.
        inside = sum(1 for o in self.occupants if o.status in INSIDE_STATUSES)
        at_exit = sum(1 for o in self.occupants if o.status == STATUS_AT_EXIT)
        self.timeline.append(
            [t_end, self.evacuated_count, inside, at_exit, self.incapacitated_count]
        )
        self._record_frame(t_end)
        self.step_index += 1

    def _next_cell(self, occ: Occupant) -> tuple[int, int] | None:
        """Best next cell toward the assigned exit (descending its distance
        field). Dynamically blocked cells (disaster) are never entered, and an
        occupant whose assigned exit became unreachable is re-routed on the
        spot to the nearest exit still reachable from here."""
        if occ.assigned_exit not in self.dist_fields:
            return None
        field_map = self.dist_fields[occ.assigned_exit]
        if occ.pos not in field_map or field_map.get(occ.pos) is None:
            # Assigned exit unreachable from here: try re-routing once.
            best_exit = None
            best_dist = None
            for eid, fmap in self.dist_fields.items():
                d = fmap.get(occ.pos)
                if d is not None and (best_dist is None or d < best_dist):
                    best_exit, best_dist = eid, d
            if best_exit is None:
                return None  # trapped: no exit reachable from this position
            old = occ.assigned_exit
            if old in self.strategy_ctx.live_load:
                self.strategy_ctx.live_load[old] -= 1
            occ.assigned_exit = best_exit
            self.strategy_ctx.live_load[best_exit] += 1
            occ.fallback_used = True
            field_map = self.dist_fields[best_exit]
        current = field_map.get(occ.pos)
        if current is None:
            return None
        best: tuple[int, int] | None = None
        best_dist = current
        for dx, dy in NEIGHBOR_OFFSETS:
            nxt = (occ.x + dx, occ.y + dy)
            if nxt in self.dynamic_blocked:
                continue
            d = field_map.get(nxt)
            if d is not None and d < best_dist:
                best_dist = d
                best = nxt
        return best

    def _record_blocked(self, occupants: list[Occupant], dest: tuple[int, int]) -> None:
        if not occupants:
            return
        key = cells_to_key(*dest)
        self.congestion[key] = self.congestion.get(key, 0) + len(occupants)
        for d in self.disasters:
            d.record_attempt(dest)
        for occ in occupants:
            occ.queue_time_s += self.dt

    def _apply_moves(
        self,
        requests: list[tuple[Occupant, tuple[int, int]]],
        occupied: set[tuple[int, int]],
        t_end: float,
    ) -> list[tuple[Occupant, tuple[int, int]]]:
        """Apply movement requests: sequential attempts, following, cycle swaps.

        Each requester tries its move in the given (already rotated) order.
        Retry passes let a blocked requester follow a mover out of the cell it
        wants, so platoons advance naturally. Remaining blocked requesters
        whose destinations are held by other blocked requesters form head-on
        cycles; these are applied simultaneously as a documented simplification
        for passing in narrow space (this prevents permanent deadlock in
        single-file corridors).

        Returns the requesters that could not move this step (still queued).
        """
        cell_time_of = {occ.id: self.grid.cell_size_m / occ.speed_mps for occ, _ in requests}
        pending = list(requests)
        guard = len(pending) + 1
        while pending and guard > 0:
            guard -= 1
            progressed = False
            still_pending: list[tuple[Occupant, tuple[int, int]]] = []
            for occ, dest in pending:
                if dest in occupied:
                    still_pending.append((occ, dest))
                    continue
                self._move_one(occ, dest, cell_time_of[occ.id], occupied, t_end)
                progressed = True
            pending = still_pending
            if not progressed:
                break
        if pending:
            self._apply_cycles(pending, cell_time_of, occupied, t_end)
            # Anything still pending after cycle resolution is blocked by a
            # non-moving occupant; report it as queued this step.
            return [
                (occ, dest)
                for occ, dest in pending
                if (occ.x, occ.y) != dest  # not moved by cycle resolution
            ]
        return []

    def _move_one(
        self,
        occ: Occupant,
        dest: tuple[int, int],
        cell_time: float,
        occupied: set[tuple[int, int]],
        t_end: float,
        discard_old: bool = True,
    ) -> None:
        if discard_old:
            occupied.discard(occ.pos)
        occ.x, occ.y = dest
        occ.move_accumulator_s = max(0.0, occ.move_accumulator_s - cell_time)
        occ.moves += 1
        occupied.add(dest)
        exit_id = self.exit_cells.get(dest)
        if exit_id is not None:
            occ.status = STATUS_AT_EXIT
            occ.exit_id = exit_id
            occ.exit_entered_t = t_end
            if occ.assigned_exit != exit_id:
                self.strategy_ctx.live_load[occ.assigned_exit] -= 1
                self.strategy_ctx.live_load[exit_id] += 1
                occ.assigned_exit = exit_id

    def _apply_cycles(
        self,
        pending: list[tuple[Occupant, tuple[int, int]]],
        cell_time_of: dict[int, float],
        occupied: set[tuple[int, int]],
        t_end: float,
    ) -> None:
        """Simultaneously apply remaining winners that form rotation cycles.

        A cycle is a chain of winners where each one's destination is held by
        the next (A wants B's cell, B wants C's cell, ..., last wants A's cell).
        Applying the permutation moves each occupant exactly once, so no cell
        is ever shared. Winners whose destination is held by a non-moving
        occupant simply wait until the next step.
        """
        holder: dict[tuple[int, int], Occupant] = {occ.pos: occ for occ, _ in pending}
        dest_of: dict[int, tuple[int, int]] = {occ.id: dest for occ, dest in pending}
        resolved: set[int] = set()
        for start, _ in pending:
            if start.id in resolved:
                continue
            chain: list[Occupant] = []
            seen_ids: set[int] = set()
            cur: Occupant | None = start
            cycle_found = False
            while cur is not None:
                if cur.id in seen_ids:
                    cycle_found = True
                    break
                seen_ids.add(cur.id)
                chain.append(cur)
                cur = holder.get(dest_of[cur.id])
            if not cycle_found:
                continue
            cycle = chain[chain.index(cur):]
            # Simultaneous permutation: vacate every original cell first, then
            # move each occupant WITHOUT discarding its (already vacated)
            # origin -- sequential discards would remove cells that earlier
            # cycle members have just claimed.
            for o in cycle:
                occupied.discard(o.pos)
            for o in cycle:
                self._move_one(
                    o, dest_of[o.id], cell_time_of[o.id], occupied, t_end, discard_old=False
                )
                resolved.add(o.id)

    def _reevaluate_capacity_assignments(self) -> None:
        strategy: CapacityAwareStrategy = self.strategy  # type: ignore[assignment]
        for occ in self.occupants:
            if occ.status not in (STATUS_WAITING, STATUS_MOVING):
                continue
            new_exit = strategy.maybe_reassign(
                occ.pos, occ.speed_mps, occ.assigned_exit, self.strategy_ctx
            )
            if new_exit is not None and new_exit != occ.assigned_exit:
                self.strategy_ctx.live_load[occ.assigned_exit] -= 1
                self.strategy_ctx.live_load[new_exit] += 1
                occ.assigned_exit = new_exit

    def _discharge(self, t_end: float, occupied: set[tuple[int, int]]) -> None:
        for exit_id in sorted(self.exits_runtime):
            rt = self.exits_runtime[exit_id]
            rt.accumulator += rt.capacity * self.dt
            queue = sorted(
                (
                    o
                    for o in self.occupants
                    if o.status == STATUS_AT_EXIT and o.exit_id == exit_id and o.reacted
                ),
                key=lambda o: (o.exit_entered_t, o.id),
            )
            while rt.accumulator >= 1.0 - 1e-9 and queue:
                occ = queue.pop(0)
                occ.status = STATUS_EVACUATED
                occ.evacuated_t = t_end
                rt.discharge_times.append(t_end)
                rt.accumulator -= 1.0
                self.strategy_ctx.live_load[exit_id] -= 1
                # The occupant has left the building; the door cell frees up
                # for the next step.
                occupied.discard(occ.pos)
            # Idle exits bank at most one discharge credit, so a long idle
            # period cannot produce an unrealistic burst later.
            rt.accumulator = min(rt.accumulator, 1.0)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _record_frame(self, t: float) -> None:
        if not self.config.record_frames:
            return
        if t + 1e-9 < self._next_frame_t and self.frames:
            return
        occupants_payload = [
            [o.id, o.x, o.y, STATUS_CODES[o.status]]
            for o in self.occupants
            if o.status != STATUS_EVACUATED
        ]
        self.frames.append({"t": round(t, 6), "occupants": occupants_payload})
        self._next_frame_t = t + self.config.frame_interval_s

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def _finalize(self, wall_time_ms: int) -> RunResult:
        # Mass balance is an invariant, not a statistic: if it fails the engine
        # is wrong and must refuse to emit results rather than fabricate them.
        # total = evacuated + unreachable + incapacitated + remaining
        evacuated = self.evacuated_count
        unreachable = self.unreachable_count
        incapacitated = self.incapacitated_count
        inside = self.total - evacuated - unreachable - incapacitated
        if inside < 0:  # pragma: no cover
            raise SimulationError("Mass balance invariant violated; refusing to emit results.")

        evac_times = sorted(o.evacuated_t for o in self.occupants if o.evacuated_t is not None)
        sim_time = self.step_index * self.dt

        exit_stats = []
        for exit_id in sorted(self.exits_runtime):
            rt = self.exits_runtime[exit_id]
            assigned = sum(1 for o in self.occupants if o.assigned_exit == exit_id)
            discharged = len(rt.discharge_times)
            exit_stats.append(
                {
                    "id": exit_id,
                    "x": rt.defn.x,
                    "y": rt.defn.y,
                    "capacity_pps": rt.capacity,
                    "assigned": assigned,
                    "evacuated": discharged,
                    "utilization_pct": round(100.0 * discharged / self.total, 2) if self.total else 0.0,
                    "first_discharge_s": rt.discharge_times[0] if discharged else None,
                    "last_discharge_s": rt.discharge_times[-1] if discharged else None,
                    "mean_discharge_s": float(np.mean(rt.discharge_times)) if discharged else None,
                    "discharge_times": [round(t, 6) for t in rt.discharge_times],
                }
            )

        queued_times = [o.queue_time_s for o in self.occupants if o.queue_time_s > 0]
        remaining_breakdown = {
            STATUS_WAITING: sum(1 for o in self.occupants if o.status == STATUS_WAITING),
            STATUS_MOVING: sum(1 for o in self.occupants if o.status == STATUS_MOVING),
            STATUS_AT_EXIT: sum(1 for o in self.occupants if o.status == STATUS_AT_EXIT),
        }

        return RunResult(
            status=self.status,
            sim_time_s=round(sim_time, 6),
            steps=self.step_index,
            wall_time_ms=wall_time_ms,
            total_occupants=self.total,
            evacuated_count=evacuated,
            unreachable_count=unreachable,
            incapacitated_count=incapacitated,
            remaining_count=inside,
            remaining_breakdown=remaining_breakdown,
            disasters=[d.summary() for d in self.disasters],
            t50_s=percentile_of_sorted(evac_times, 0.50),
            t90_s=percentile_of_sorted(evac_times, 0.90),
            t95_s=percentile_of_sorted(evac_times, 0.95),
            mean_evacuation_time_s=float(np.mean(evac_times)) if evac_times else None,
            max_evacuation_time_s=evac_times[-1] if evac_times else None,
            min_evacuation_time_s=evac_times[0] if evac_times else None,
            exit_stats=exit_stats,
            queue_total_s=round(sum(o.queue_time_s for o in self.occupants), 6),
            queue_mean_s=float(np.mean(queued_times)) if queued_times else None,
            queue_max_s=float(np.max(queued_times)) if queued_times else None,
            occupants_who_queued=len(queued_times),
            congestion=self.congestion,
            fallback_count=self.fallback_count,
            timeline=self.timeline,
            frames=self.frames,
            warnings=self.warnings,
        )
