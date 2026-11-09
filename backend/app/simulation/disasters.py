"""Disaster scenario models: fire, earthquake, stampede.

Each disaster is a documented, deliberately simplified process that evolves
DURING the simulation - unlike the static route blocking of a basic scenario.
All models share the same interface so the engine treats them uniformly:

- ``step(t, dt, occupants)`` advances the disaster and returns the set of
  cells NEWLY blocked this step (the engine turns those into impassable
  cells and incapacitates any occupant standing there).
- ``speed_factor(cell)`` multiplies an occupant's movement accrual when
  standing on a cell (stampede crush zones slow movement).
- ``fields_dirty`` tells the engine to recompute the exit distance fields
  (the blocked set grew).

All processes are deterministic given the engine's seeded RNG and are
abstract approximations, not physics: they exist to stress-test evacuation
plans under time-dependent disruption. Exact rules and intensity mappings
are documented in docs/SIMULATION_MODEL.md and the in-app Methodology page.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DISASTER_TYPES = ("none", "fire", "earthquake", "stampede", "gas_leak", "flood", "power_outage")

NEIGHBORS_4 = ((0, -1), (1, 0), (0, 1), (-1, 0))


def chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass
class DisasterSpec:
    """User-facing disaster configuration (from the scenario)."""

    type: str = "none"
    intensity: float = 0.0  # 0..1
    origin: tuple[int, int] | None = None  # None = automatic (fire)


class BaseDisaster:
    type = "none"

    def __init__(self, spec: DisasterSpec, floor: set[tuple[int, int]], rng) -> None:  # noqa: ANN001
        self.spec = spec
        self.intensity = spec.intensity
        self.floor = floor
        self.rng = rng
        self.dynamic_blocked: set[tuple[int, int]] = set()
        self.fields_dirty = False
        self.cells_blocked_total = 0

    def step(self, t: float, dt: float, occupants) -> set[tuple[int, int]]:  # noqa: ANN001
        return set()

    def speed_factor(self, cell: tuple[int, int]) -> float:  # noqa: ARG002
        return 1.0

    def record_attempt(self, cell: tuple[int, int]) -> None:  # noqa: ARG002
        """Stampede only: the engine reports blocked movement attempts.
        Other disasters ignore them."""

    def summary(self) -> dict:
        return {
            "type": self.type,
            "intensity": round(self.intensity, 3),
            "cells_blocked": self.cells_blocked_total,
        }


class FireDisaster(BaseDisaster):
    """Fire ignites at an origin and spreads as a growing radius of smoke/fire.

    - radius(t) = spread_rate * t,  spread_rate = 0.05 + 0.20 * intensity (cells/s)
    - cells within the radius (Chebyshev) become impassable; occupants standing
      on a newly burning cell are incapacitated (the engine applies this).
    - the origin is automatic: the floor cell FARTHEST from every exit (the
      worst case for early detection) unless the scenario pins one.
    - smoke permeates the plan: the radius ignores walls (documented
      simplification - no CFD, no doors slowing smoke).
    """

    type = "fire"

    def __init__(self, spec, floor, rng, dist_fields, width, height) -> None:  # noqa: ANN001
        super().__init__(spec, floor, rng)
        self.width = width
        self.height = height
        if spec.origin is not None and spec.origin in floor:
            self.origin = spec.origin
        else:
            self.origin = self._worst_case_origin(floor, dist_fields)
        self.fired: set[tuple[int, int]] = set()
        self.rate = 0.05 + 0.20 * self.intensity

    def _worst_case_origin(self, floor, dist_fields) -> tuple[int, int]:  # noqa: ANN001
        def min_exit_dist(cell):  # noqa: ANN001
            dists = [f[cell] for f in dist_fields.values() if cell in f]
            return min(dists) if dists else 10**9

        return max(sorted(floor), key=min_exit_dist)

    def step(self, t: float, dt: float, occupants) -> set[tuple[int, int]]:  # noqa: ANN001
        del dt, occupants
        radius = self.rate * t
        newly: set[tuple[int, int]] = set()
        ox, oy = self.origin
        # Only scan the bounding square of the current radius.
        reach = int(math.ceil(radius))
        for y in range(max(0, oy - reach), min(self.height, oy + reach + 1)):
            for x in range(max(0, ox - reach), min(self.width, ox + reach + 1)):
                cell = (x, y)
                if cell in self.fired or cell not in self.floor:
                    continue
                if chebyshev(cell, self.origin) <= radius:
                    newly.add(cell)
        if newly:
            self.fired |= newly
            self.dynamic_blocked |= newly
            self.cells_blocked_total = len(self.dynamic_blocked)
            self.fields_dirty = True
        return newly

    def summary(self) -> dict:
        return {
            **super().summary(),
            "origin": list(self.origin),
            "ignited_cells": len(self.fired),
            "spread_rate_cells_per_s": round(self.rate, 3),
        }


class EarthquakeDisaster(BaseDisaster):
    """A single sudden collapse event.

    - collapse_time = 30 - 20 * intensity seconds (higher intensity -> earlier).
    - At collapse, N floor cells become debris: N = round(intensity^2 * 0.12 *
      floor_count), chosen from cells sorted by proximity to the nearest exit
      (structural damage concentrates at exits and doorways first - a
      documented simplification). Exit cells themselves can be debris.
    - Occupants standing on debris are incapacitated (crushed); occupants not
      yet moving get their reaction delay extended by 25 * intensity seconds
      (post-shock confusion).
    """

    type = "earthquake"

    def __init__(self, spec, floor, rng, dist_fields, exits) -> None:  # noqa: ANN001
        super().__init__(spec, floor, rng)
        self.collapse_time = 30.0 - 20.0 * self.intensity
        self.exits = exits
        self.floor_list = sorted(floor)
        self.collapsed = False
        self.exit_cells = sorted(exits)

    def _min_exit_dist(self, cell: tuple[int, int]) -> int:
        return min((chebyshev(cell, e) for e in self.exit_cells), default=10**9)

    def step(self, t: float, dt: float, occupants) -> set[tuple[int, int]]:  # noqa: ANN001
        del dt
        if self.collapsed or t < self.collapse_time:
            return set()
        self.collapsed = True
        n_debris = int(round(self.intensity**2 * 0.12 * len(self.floor_list)))
        n_debris = max(1, min(n_debris, len(self.floor_list)))
        ranked = sorted(self.floor_list, key=lambda c: (self._min_exit_dist(c), c))
        chosen = set(ranked[:n_debris])
        self.dynamic_blocked |= chosen
        self.cells_blocked_total = len(self.dynamic_blocked)
        self.fields_dirty = True
        # Post-shock confusion extends reaction times of occupants not yet moving.
        from app.simulation.occupant import STATUS_WAITING

        for occ in occupants:
            if occ.status == STATUS_WAITING:
                occ.reaction_delay_s += 25.0 * self.intensity
        return chosen

    def summary(self) -> dict:
        return {
            **super().summary(),
            "collapse_time_s": round(self.collapse_time, 2),
        }


class StampedeDisaster(BaseDisaster):
    """Crowd-crush dynamics at chokepoints.

    The engine reports each blocked movement attempt; when a cell accumulates
    more than ``trigger`` attempts within the 8 s window, it and its 3-cell
    neighborhood become a permanent CRUSH ZONE: people have fallen and the
    cells become impassable obstacles (the standard representation in crowd
    dynamics). Occupants standing in a new crush zone are pushed to a
    neighboring free cell by the engine (they are not lost). Trampling
    casualties are out of scope; the model captures crush-induced capacity
    loss at the chokepoint.
    """

    type = "stampede"

    WINDOW_S = 8.0

    def __init__(self, spec, floor, rng) -> None:  # noqa: ANN001
        super().__init__(spec, floor, rng)
        self.trigger = max(3, round(10 * (1 - self.intensity)) + 2)
        self.window_start = 0.0
        self.window_counts: dict[tuple[int, int], int] = {}
        self.crush_zones: set[tuple[int, int]] = set()

    def record_attempt(self, cell: tuple[int, int]) -> None:
        self.window_counts[cell] = self.window_counts.get(cell, 0) + 1

    def step(self, t: float, dt: float, occupants) -> set[tuple[int, int]]:  # noqa: ANN001
        del dt, occupants
        newly: set[tuple[int, int]] = set()
        if t - self.window_start >= self.WINDOW_S:
            triggered = [
                cell
                for cell, count in self.window_counts.items()
                if count >= self.trigger and cell not in self.crush_zones
            ]
            newly = set()
            for cell in triggered:
                for ddx in range(-3, 4):
                    for ddy in range(-3, 4):
                        nxt = (cell[0] + ddx, cell[1] + ddy)
                        if nxt in self.floor and nxt not in self.crush_zones:
                            self.crush_zones.add(nxt)
                            newly.add(nxt)
            self.window_counts = {}
            self.window_start = t
            if newly:
                self.dynamic_blocked |= newly
                self.cells_blocked_total = len(self.crush_zones)
                self.fields_dirty = True
        return newly

    def summary(self) -> dict:
        return {
            **super().summary(),
            "crush_cells": len(self.crush_zones),
        }


class GasLeakDisaster(BaseDisaster):
    """Toxic gas leak: spreads through walls (gas permeates everything) and
    is invisible - occupants don't re-route until the gas reaches their area."""

    type = "gas_leak"

    def __init__(self, spec, floor, rng, dist_fields, width, height) -> None:  # noqa: ANN001
        super().__init__(spec, floor, rng)
        self.width = width
        self.height = height
        if spec.origin is not None and spec.origin in floor:
            self.origin = spec.origin
        else:
            cells = sorted(floor)
            self.origin = cells[len(cells) // 2]
        self.affected: set[tuple[int, int]] = set()
        self.rate = 0.03 + 0.12 * self.intensity

    def step(self, t: float, dt: float, occupants) -> set[tuple[int, int]]:  # noqa: ANN001
        del dt, occupants
        radius = self.rate * t
        newly: set[tuple[int, int]] = set()
        ox, oy = self.origin
        reach = int(math.ceil(radius))
        for y in range(max(0, oy - reach), min(self.height, oy + reach + 1)):
            for x in range(max(0, ox - reach), min(self.width, ox + reach + 1)):
                cell = (x, y)
                if cell in self.affected or cell not in self.floor:
                    continue
                if chebyshev(cell, self.origin) <= radius:
                    newly.add(cell)
        if newly:
            self.affected |= newly
            self.dynamic_blocked |= newly
            self.cells_blocked_total = len(self.dynamic_blocked)
            self.fields_dirty = True
        return newly

    def summary(self) -> dict:
        return {**super().summary(), "origin": list(self.origin), "affected_cells": len(self.affected)}


class FloodDisaster(BaseDisaster):
    """Flood: water rises from the lowest cells upward over time."""

    type = "flood"

    def __init__(self, spec, floor, rng, width, height) -> None:  # noqa: ANN001
        super().__init__(spec, floor, rng)
        self.width = width
        self.height = height
        self.flooded: set[tuple[int, int]] = set()

    def step(self, t: float, dt: float, occupants) -> set[tuple[int, int]]:  # noqa: ANN001
        del dt, occupants
        level = t * (0.08 + 0.25 * self.intensity)
        cutoff_y = (self.height - 1) - int(level)
        newly: set[tuple[int, int]] = set()
        for cell in self.floor:
            if cell[1] >= cutoff_y and cell not in self.flooded:
                newly.add(cell)
        if newly:
            self.flooded |= newly
            self.dynamic_blocked |= newly
            self.cells_blocked_total = len(self.dynamic_blocked)
            self.fields_dirty = True
        return newly

    def summary(self) -> dict:
        return {**super().summary(), "flooded_cells": len(self.flooded)}


class PowerOutageDisaster(BaseDisaster):
    """Power outage: movement slows globally, reaction times increase."""

    type = "power_outage"

    def __init__(self, spec, floor, rng) -> None:  # noqa: ANN001
        super().__init__(spec, floor, rng)
        self.speed_multiplier = 1.0 / (1.0 + 0.8 * self.intensity)
        self.delay_extension = 10.0 * self.intensity
        self._applied = False

    def step(self, t: float, dt: float, occupants) -> set[tuple[int, int]]:  # noqa: ANN001
        del dt
        if not self._applied and t >= 1.0:
            from app.simulation.occupant import STATUS_WAITING

            for occ in occupants:
                if occ.status == STATUS_WAITING:
                    occ.reaction_delay_s += self.delay_extension
            self._applied = True
        return set()

    def speed_factor(self, cell: tuple[int, int]) -> float:  # noqa: ARG002
        return self.speed_multiplier

    def summary(self) -> dict:
        return {
            **super().summary(),
            "speed_multiplier": round(self.speed_multiplier, 3),
            "delay_extension_s": round(self.delay_extension, 1),
        }


def create_disaster(spec: DisasterSpec, floor, rng, dist_fields, exits, width, height):  # noqa: ANN001
    """Factory: build the disaster model for a scenario spec (or None)."""
    if spec.type == "fire":
        return FireDisaster(spec, floor, rng, dist_fields, width, height)
    if spec.type == "earthquake":
        return EarthquakeDisaster(spec, floor, rng, dist_fields, exits)
    if spec.type == "stampede":
        return StampedeDisaster(spec, floor, rng)
    if spec.type == "gas_leak":
        return GasLeakDisaster(spec, floor, rng, dist_fields, width, height)
    if spec.type == "flood":
        return FloodDisaster(spec, floor, rng, width, height)
    if spec.type == "power_outage":
        return PowerOutageDisaster(spec, floor, rng)
    return None
