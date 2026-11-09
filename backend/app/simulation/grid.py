"""Grid-based building representation shared by the engine and the API layer.

A building is a 2D grid. Each cell is either a wall or walkable floor.
Exits are special walkable cells with an explicit throughput capacity.
Zones are named groups of floor cells used as occupant starting areas.

Coordinates are (x, y) with x = column (0..width-1), y = row (0..height-1).
A documented physical scale (`cell_size_m`, default 0.5 m) maps grid steps to
metres; all movement speeds and distances in the engine are expressed through
this scale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.algorithms.pathfinding import bfs_distance_field
from app.core.config import settings
from app.core.errors import ValidationError

WALL = "#"
FLOOR = "."

# Directions in fixed order for deterministic tie-breaking.
NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))


@dataclass
class ExitDef:
    """An exit cell. Capacity is a modeled throughput in persons/second."""

    id: str
    x: int
    y: int
    capacity_pps: float = 1.0

    def key(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass
class ZoneDef:
    """A named starting area: a set of walkable cells."""

    id: str
    name: str
    cells: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class BuildingGrid:
    """In-memory building layout used by the simulation engine."""

    width: int
    height: int
    cell_size_m: float
    walls: set[tuple[int, int]]
    exits: dict[str, ExitDef]
    zones: dict[str, ZoneDef]
    name: str = "Untitled"

    # ---------- basic queries ----------

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_wall(self, x: int, y: int) -> bool:
        return (x, y) in self.walls

    def walkable_cells(self) -> set[tuple[int, int]]:
        """All cells occupants may stand on: floor plus exit cells.

        Exit cells are walkable by definition - an exit placed in a wall line
        is a doorway. Without this, doors on the building envelope would be
        unreachable and no evacuation could start.
        """
        cells: set[tuple[int, int]] = set()
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) not in self.walls:
                    cells.add((x, y))
        cells.update(e.key() for e in self.exits.values())
        return cells

    def zone_cells(self, zone_id: str) -> list[tuple[int, int]]:
        zone = self.zones.get(zone_id)
        return list(zone.cells) if zone else []

    def exit_at(self, x: int, y: int) -> ExitDef | None:
        for e in self.exits.values():
            if e.x == x and e.y == y:
                return e
        return None

    # ---------- scenario-aware walkability ----------

    def effective_blocked(
        self, blocked_cells: set[tuple[int, int]], blocked_exit_ids: set[str]
    ) -> set[tuple[int, int]]:
        """Cells removed from the walkable set by a scenario.

        Blocked exits become impassable walls; extra blocked cells are added walls.
        """
        blocked = set(blocked_cells)
        for exit_id in blocked_exit_ids:
            e = self.exits.get(exit_id)
            if e is not None:
                blocked.add(e.key())
        return blocked

    def walkable_with(self, blocked: set[tuple[int, int]]) -> set[tuple[int, int]]:
        return self.walkable_cells() - blocked

    # ---------- validation ----------

    def validate(self) -> list[str]:
        """Raise ValidationError for hard errors; return a list of human-readable warnings.

        Hard errors make the layout unusable for simulation. Warnings describe
        suspicious but technically runnable layouts.
        """
        warnings: list[str] = []
        self._validate_dimensions()
        self._validate_exits()
        self._validate_zones()
        warnings.extend(self._validate_reachability())
        return warnings

    def _validate_dimensions(self) -> None:
        if self.width < settings.min_grid_size or self.height < settings.min_grid_size:
            raise ValidationError(
                f"Grid is too small: minimum {settings.min_grid_size}x{settings.min_grid_size} cells."
            )
        if self.width > settings.max_grid_width or self.height > settings.max_grid_height:
            raise ValidationError(
                f"Grid is too large: maximum {settings.max_grid_width}x{settings.max_grid_height} cells."
            )
        if not (0.05 <= self.cell_size_m <= 5.0):
            raise ValidationError("Cell size must be between 0.05 and 5.0 metres.")

    def _validate_exits(self) -> None:
        if not self.exits:
            raise ValidationError("The layout has no exits. Add at least one exit.")
        if len(self.exits) > settings.max_exits:
            raise ValidationError(f"Too many exits (maximum {settings.max_exits}).")
        seen: set[tuple[int, int]] = set()
        for exit_def in self.exits.values():
            if not self.in_bounds(exit_def.x, exit_def.y):
                raise ValidationError(f"Exit '{exit_def.id}' is outside the grid bounds.")
            if exit_def.key() in seen:
                raise ValidationError("Two exits cannot occupy the same cell.")
            seen.add(exit_def.key())
            if exit_def.capacity_pps <= 0:
                raise ValidationError(f"Exit '{exit_def.id}' must have a positive throughput capacity.")

    def _validate_zones(self) -> None:
        if len(self.zones) > settings.max_zones:
            raise ValidationError(f"Too many zones (maximum {settings.max_zones}).")
        for zone in self.zones.values():
            if not zone.cells:
                raise ValidationError(f"Zone '{zone.id}' has no cells. Paint at least one cell.")
            for x, y in zone.cells:
                if not self.in_bounds(x, y):
                    raise ValidationError(f"Zone '{zone.id}' contains a cell outside the grid bounds.")
                if (x, y) in self.walls:
                    raise ValidationError(f"Zone '{zone.id}' contains a wall cell at ({x}, {y}).")

    def _validate_reachability(self) -> list[str]:
        warnings: list[str] = []
        walkable = self.walkable_cells()
        exit_cells = {e.key() for e in self.exits.values()}
        dist = bfs_distance_field(self.width, self.height, walkable, exit_cells)
        reachable = set(dist)
        # An exit with no walkable neighbor can never be used.
        for exit_def in self.exits.values():
            neighbors = [(exit_def.x + dx, exit_def.y + dy) for dx, dy in NEIGHBOR_OFFSETS]
            if not any(n in walkable and n not in exit_cells for n in neighbors):
                warnings.append(
                    f"Exit '{exit_def.id}' has no adjacent walkable cell and can never be used."
                )
        unreachable_floor = walkable - reachable
        if unreachable_floor:
            warnings.append(
                f"{len(unreachable_floor)} walkable cell(s) cannot reach any exit "
                "(occupants spawning there will be marked unreachable)."
            )
        for zone in self.zones.values():
            if all(cell not in reachable for cell in zone.cells):
                warnings.append(
                    f"Zone '{zone.id}' has no path to any exit; occupants spawning there cannot evacuate."
                )
        return warnings

    # ---------- serialization ----------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "cell_size_m": self.cell_size_m,
            "walls": sorted([x, y] for x, y in self.walls),
            "exits": [
                {"id": e.id, "x": e.x, "y": e.y, "capacity_pps": e.capacity_pps}
                for e in self.exits.values()
            ],
            "zones": [
                {"id": z.id, "name": z.name, "cells": sorted([x, y] for x, y in z.cells)}
                for z in self.zones.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BuildingGrid:
        """Build a grid from plain dictionaries, validating structure.

        Raises ValidationError on malformed input (wrong types, out-of-range
        coordinates, duplicate ids).
        """
        try:
            width = int(data["width"])
            height = int(data["height"])
            cell_size = float(data.get("cell_size_m", settings.default_cell_size_m))
            name = str(data.get("name", "Untitled"))
            raw_walls = data.get("walls", [])
            raw_exits = data.get("exits", [])
            raw_zones = data.get("zones", [])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"Malformed layout data: {exc}") from exc

        walls: set[tuple[int, int]] = set()
        for cell in raw_walls:
            try:
                x, y = int(cell[0]), int(cell[1])
            except (TypeError, ValueError, IndexError) as exc:
                raise ValidationError("Wall cells must be [x, y] integer pairs.") from exc
            if not (0 <= x < width and 0 <= y < height):
                raise ValidationError(f"Wall cell ({x}, {y}) is outside the grid bounds.")
            walls.add((x, y))

        exits: dict[str, ExitDef] = {}
        for raw in raw_exits:
            try:
                exit_id = str(raw["id"])
                x, y = int(raw["x"]), int(raw["y"])
                capacity = float(raw.get("capacity_pps", 1.0))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValidationError(f"Malformed exit definition: {raw!r}") from exc
            if exit_id in exits:
                raise ValidationError(f"Duplicate exit id '{exit_id}'.")
            if not (0 <= x < width and 0 <= y < height):
                raise ValidationError(f"Exit '{exit_id}' is outside the grid bounds.")
            exits[exit_id] = ExitDef(id=exit_id, x=x, y=y, capacity_pps=capacity)

        zones: dict[str, ZoneDef] = {}
        for raw in raw_zones:
            try:
                zone_id = str(raw["id"])
                zone_name = str(raw.get("name", zone_id))
                cells = [(int(c[0]), int(c[1])) for c in raw.get("cells", [])]
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise ValidationError(f"Malformed zone definition: {raw!r}") from exc
            if zone_id in zones:
                raise ValidationError(f"Duplicate zone id '{zone_id}'.")
            zones[zone_id] = ZoneDef(id=zone_id, name=zone_name, cells=cells)

        grid = cls(
            width=width,
            height=height,
            cell_size_m=cell_size,
            walls=walls,
            exits=exits,
            zones=zones,
            name=name,
        )
        grid.validate()
        return grid


def cells_to_key(x: int, y: int) -> str:
    """Canonical string key for a cell (used in congestion maps and JSON)."""
    return f"{x},{y}"


def key_to_cells(key: str) -> tuple[int, int]:
    x_s, y_s = key.split(",")
    return int(x_s), int(y_s)
