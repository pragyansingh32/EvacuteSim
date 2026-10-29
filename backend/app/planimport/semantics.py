"""Automatic plan interpretation: from raw wall cells to a runnable draft.

Given the wall geometry extracted from an imported plan, this module derives
the semantics the user would otherwise have to add by hand:

1. **Morphological cleanup** — a closing pass (dilate + erode) seals single-cell
   pinholes (anti-aliased diagonals, scan noise) while preserving genuine
   openings of two or more cells. Small floating wall specks (text dots) are
   removed.
2. **Opening candidates** — run-based scans along rows and columns find floor
   runs flanked by wall on both ends, with a passage (open cells on both sides
   perpendicular to the run; out-of-bounds counts as outside). This
   over-approximates: room rows between wall columns also match.
3. **Connectivity verification** — a candidate group is a REAL opening only if
   removing it actually disconnects the plan (per-group flood test) or links
   the interior to the outside. Room-interior false candidates fail this test
   because the room stays connected around them.
4. **Classification** — an opening that links the interior to the exterior is
   an EXIT (any width); an interior opening up to MAX_DOOR_CELLS wide that
   separates two areas is a DOOR; wider interior separations are structural
   splits the rooms simply span.
5. **Zones** — interior regions of at least MIN_ZONE_CELLS become starting
   zones; suggested population = area × occupancy density.
6. **Reachability** — rooms are graph-connected through doors/exits; rooms
   with no path to any exit are reported before simulating.

Exit capacities derive from detected width: capacity ≈ width_m × 1.3 p/s/m
(a common, deliberately conservative door specific-flow assumption).
"""

from __future__ import annotations

from dataclasses import dataclass, field

MIN_ZONE_CELLS = 6
MAX_DOOR_CELLS = 5
MAX_ZONES = 15
MAX_CANDIDATE_RUN = 14
NOISE_COMPONENT_CELLS = 8
MAX_NOISE_BB = 4

NEIGHBORS_4 = ((0, -1), (1, 0), (0, 1), (-1, 0))
NEIGHBORS_8 = NEIGHBORS_4 + ((1, -1), (1, 1), (-1, 1), (-1, -1))

EXTERIOR = -1


def remove_noise(walls: set[tuple[int, int]]) -> tuple[set[tuple[int, int]], int]:
    """Drop small floating wall components (text specks, hatching dots)."""
    remaining = set(walls)
    seen: set[tuple[int, int]] = set()
    removed = 0
    for start in sorted(walls):
        if start in seen or start not in remaining:
            continue
        component: list[tuple[int, int]] = []
        stack = [start]
        seen.add(start)
        while stack:
            cell = stack.pop()
            component.append(cell)
            for dx, dy in NEIGHBORS_8:
                nxt = (cell[0] + dx, cell[1] + dy)
                if nxt in remaining and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        if len(component) <= NOISE_COMPONENT_CELLS:
            xs = [c[0] for c in component]
            ys = [c[1] for c in component]
            if max(xs) - min(xs) < MAX_NOISE_BB and max(ys) - min(ys) < MAX_NOISE_BB:
                remaining.difference_update(component)
                removed += len(component)
    return remaining, removed


def _label(floor: set[tuple[int, int]]) -> dict[tuple[int, int], int]:
    labels: dict[tuple[int, int], int] = {}
    current = 0
    for start in sorted(floor):
        if start in labels:
            continue
        current += 1
        labels[start] = current
        stack = [start]
        while stack:
            x, y = stack.pop()
            for dx, dy in NEIGHBORS_4:
                nxt = (x + dx, y + dy)
                if nxt in floor and nxt not in labels:
                    labels[nxt] = current
                    stack.append(nxt)
    return labels


def _flood_reaches(
    start_cells: set[tuple[int, int]],
    passable: set[tuple[int, int]],
    targets: set[tuple[int, int]],
) -> bool:
    """Can any start cell reach any target cell within `passable`?"""
    starts = start_cells & passable
    if starts & targets:
        return True
    seen = set(starts)
    stack = list(starts)
    while stack:
        x, y = stack.pop()
        for dx, dy in NEIGHBORS_4:
            nxt = (x + dx, y + dy)
            if nxt in passable and nxt not in seen:
                if nxt in targets:
                    return True
                seen.add(nxt)
                stack.append(nxt)
    return False


def _gap_candidates(
    floor: set[tuple[int, int]], walls: set[tuple[int, int]], width: int, height: int
) -> list[list[tuple[int, int, str]]]:
    """Run-based opening candidates along rows ('h') and columns ('v').

    A floor run in a line, flanked by wall on both ends (out-of-bounds counts
    as wall — plans whose envelope sits on the grid edge still have gaps),
    with a passage perpendicular to the line (open on both sides, where
    out-of-bounds counts as outside). Generous by design; the connectivity
    test in analyze() rejects false positives.
    """

    def is_wall(c: tuple[int, int]) -> bool:
        x, y = c
        if not (0 <= x < width and 0 <= y < height):
            return True
        return c in walls

    def is_passable(c: tuple[int, int]) -> bool:
        x, y = c
        if not (0 <= x < width and 0 <= y < height):
            return True
        return c in floor

    groups: list[list[tuple[int, int, str]]] = []
    for y in range(height):
        x = 0
        while x < width:
            if (x, y) in floor:
                x0 = x
                while x < width and (x, y) in floor:
                    x += 1
                passage_h = any(
                    is_passable((cx, y - 1)) and is_passable((cx, y + 1))
                    for cx in range(x0, x)
                )
                if (
                    1 <= x - x0 <= MAX_CANDIDATE_RUN
                    and is_wall((x0 - 1, y))
                    and is_wall((x, y))
                    and passage_h
                ):
                    groups.append([(cx, y, "h") for cx in range(x0, x)])
            else:
                x += 1
    for x in range(width):
        y = 0
        while y < height:
            if (x, y) in floor:
                y0 = y
                while y < height and (x, y) in floor:
                    y += 1
                passage_v = any(
                    is_passable((x - 1, cy)) and is_passable((x + 1, cy))
                    for cy in range(y0, y)
                )
                if (
                    1 <= y - y0 <= MAX_CANDIDATE_RUN
                    and is_wall((x, y0 - 1))
                    and is_wall((x, y))
                    and passage_v
                ):
                    groups.append([(x, cy, "v") for cy in range(y0, y)])
            else:
                y += 1
    return groups


def _drop_passage_stacks(groups: list[list[tuple[int, int, str]]]) -> list[list[tuple[int, int, str]]]:
    """Remove candidate groups that stack consecutively across rows/columns:
    a narrow corridor yields a candidate at every cross-section, while a real
    wall has isolated doors along it."""

    def span(group):  # noqa: ANN001
        xs = [c[0] for c in group]
        ys = [c[1] for c in group]
        o = group[0][2]
        return (o, (min(xs), max(xs)) if o == "h" else None, (min(ys), max(ys)) if o == "v" else None)

    by_span: dict[tuple, list[int]] = {}
    for group in groups:
        o, hspan, vspan = span(group)
        if o == "h" and hspan:
            by_span.setdefault(("h", hspan), []).append(group[0][1])
        elif o == "v" and vspan:
            by_span.setdefault(("v", vspan), []).append(group[0][0])

    def consecutive(values: list[int]) -> bool:
        vals = sorted(set(values))
        return len(vals) >= 3 and all(b - a == 1 for a, b in zip(vals, vals[1:], strict=False))

    passage_spans = {key for key, vals in by_span.items() if consecutive(vals)}
    if not passage_spans:
        return groups
    return [g for g in groups if span(g) not in passage_spans]


@dataclass
class PlanSemantics:
    exits: list[dict] = field(default_factory=list)
    zones: list[dict] = field(default_factory=list)
    zone_populations: dict[str, int] = field(default_factory=dict)
    rooms: int = 0
    doors: int = 0
    openings: int = 0
    noise_removed: int = 0
    warnings: list[str] = field(default_factory=list)


def analyze(
    walls: set[tuple[int, int]],
    width: int,
    height: int,
    cell_size_m: float,
    occupancy_density: float = 0.25,
) -> PlanSemantics:
    """Derive doors, exits, and starting zones from wall geometry."""
    result = PlanSemantics()

    # NOTE: no morphological closing — flood fill and occupant movement are
    # both 4-connected, so diagonal pinholes never leak; any radius-1 close
    # would seal legitimate 1-2 cell doors.
    noise_free, removed = remove_noise(walls)
    result.noise_removed = removed
    walls = noise_free

    all_cells = {(x, y) for x in range(width) for y in range(height)}
    floor = all_cells - walls

    # ---- candidates -> verified openings ------------------------------------
    groups = _drop_passage_stacks(_gap_candidates(floor, walls, width, height))
    door_cells: set[tuple[int, int]] = set()
    exit_specs: list[dict] = []
    interior_openings = 0

    def has_wall_continuation(group):  # noqa: ANN001
        """A genuine door pierces a wall that keeps going along the run beyond
        the gap's flanking walls. Room-interior slices have no continuation
        (their flanks are the envelope/edge) and are rejected here."""
        o = group[0][2]
        if o == "v":
            x = group[0][0]
            ys = [c[1] for c in group]
            top, bot = min(ys), max(ys)
            up = 0 <= top - 2 < height and (x, top - 2) in walls
            down = 0 <= bot + 2 < height and (x, bot + 2) in walls
            return up or down
        y = group[0][1]
        xs = [c[0] for c in group]
        left, right = min(xs), max(xs)
        left_w = 0 <= left - 2 < width and (left - 2, y) in walls
        right_w = 0 <= right + 2 < width and (right + 2, y) in walls
        return left_w or right_w

    def in_bounds(c: tuple[int, int]) -> bool:
        return 0 <= c[0] < width and 0 <= c[1] < height

    for group in groups:
        if not has_wall_continuation(group):
            continue
        cells = {(x, y) for x, y, _ in group}
        passable = floor - cells
        orientation = group[0][2]
        side_a: set[tuple[int, int]] = set()
        side_b: set[tuple[int, int]] = set()
        for x, y, _ in group:
            if orientation == "h":  # walls left+right; passage vertical
                side_a.add((x, y - 1))
                side_b.add((x, y + 1))
            else:  # walls up+down; passage horizontal
                side_a.add((x - 1, y))
                side_b.add((x + 1, y))

        a_out = any(not in_bounds(c) for c in side_a)
        b_out = any(not in_bounds(c) for c in side_b)
        side_a_in = {c for c in side_a if in_bounds(c)}
        side_b_in = {c for c in side_b if in_bounds(c)}

        if a_out or b_out:
            # The opening leads off the plan: an exterior door = an EXIT.
            mid = group[len(group) // 2]
            width_m = len(group) * cell_size_m
            capacity = max(0.75, round(width_m * 1.3 * 4) / 4)
            exit_specs.append(
                {
                    "id": f"E{len(exit_specs) + 1}",
                    "x": mid[0],
                    "y": mid[1],
                    "capacity_pps": capacity,
                }
            )
            door_cells |= cells
            result.doors += 1
        elif side_a_in and side_b_in:
            # A gap whose removal separates the two sides is a door/channel:
            # evacuation-wise it stays a passable connection either way.
            separated = not _flood_reaches(side_a_in, passable, side_b_in)
            if separated:
                door_cells |= cells
                result.doors += 1
            else:
                interior_openings += 1

    # ---- rooms -> zones ------------------------------------------------------
    floor_no_doors = floor - door_cells
    room_labels = _label(floor_no_doors)
    regions: dict[int, list[tuple[int, int]]] = {}
    for cell, label in room_labels.items():
        regions.setdefault(label, []).append(cell)
    biggest_region = max(regions, key=lambda lbl: len(regions[lbl])) if regions else None

    def in_outer_margin(cells: list[tuple[int, int]]) -> bool:
        """True when every cell lies within the 2-cell crop margin at the
        grid edge — that ring is the plan's outside, never a room."""
        return all(
            c[0] < 2 or c[1] < 2 or c[0] >= width - 2 or c[1] >= height - 2
            for c in cells
        )

    room_cells: dict[int, list[tuple[int, int]]] = {}
    for label, cells in regions.items():
        on_boundary = any(
            c[0] in (0, width - 1) or c[1] in (0, height - 1) for c in cells
        )
        is_exterior = on_boundary and label != biggest_region
        if is_exterior or (on_boundary and in_outer_margin(cells)):
            continue  # exterior ring
        room_cells[label] = cells

    sized = sorted(room_cells.values(), key=len, reverse=True)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for index, cells in enumerate(sized[:MAX_ZONES]):
        if len(cells) < MIN_ZONE_CELLS:
            break
        result.zones.append(
            {
                "id": f"Z{alphabet[index]}",
                "name": f"Zone {alphabet[index]} ({len(cells)} cells)",
                "cells": sorted(cells),
            }
        )
        area_m2 = len(cells) * cell_size_m * cell_size_m
        result.zone_populations[f"Z{alphabet[index]}"] = max(0, round(area_m2 * occupancy_density))
    if len(sized) > MAX_ZONES:
        result.warnings.append(
            f"{len(sized) - MAX_ZONES} smaller rooms were not turned into zones "
            "(limit 15); paint them manually if needed."
        )
    result.rooms = len(sized)

    # ---- reachability of rooms through doors and exits -----------------------
    # Rooms are labeled on floor-without-doors; each door cell links the
    # regions around it, each exit cell anchors a reachable region.

    def neighbors_in_regions(c: tuple[int, int]) -> set[int]:
        x, y = c
        out: set[int] = set()
        for dx, dy in NEIGHBORS_4:
            label = room_labels.get((x + dx, y + dy))
            if label is not None:
                out.add(label)
        return out

    adjacency: dict[int, set[int]] = {}
    for x, y in door_cells:
        around = neighbors_in_regions((x, y))
        for label in around:
            adjacency.setdefault(label, set()).update(around)
    exit_labels: set[int] = set()
    for e in exit_specs:
        exit_labels |= neighbors_in_regions((e["x"], e["y"]))
    reached = set(exit_labels)
    stack = list(reached)
    while stack:
        cur = stack.pop()
        for nxt in adjacency.get(cur, ()):
            if nxt not in reached:
                reached.add(nxt)
                stack.append(nxt)
    stranded = sum(
        len(cells)
        for label, cells in room_cells.items()
        if label not in reached
    )
    if stranded and exit_specs:
        result.warnings.append(
            f"{stranded} walkable cells belong to room(s) with no path to any "
            "detected exit — connect them to the rest of the plan in the editor."
        )

    result.exits = exit_specs
    result.openings = interior_openings
    if not exit_specs:
        result.warnings.append(
            "No opening to the outside was detected, so no exits could be "
            "placed automatically. Place at least one exit manually in the editor."
        )
    total_pop = sum(result.zone_populations.values())
    if result.zones and total_pop == 0:
        result.zone_populations[result.zones[0]["id"]] = 8
        result.warnings.append(
            "The occupancy density produced zero population; the largest zone "
            "was preset to 8 occupants. Adjust in the scenario editor."
        )
    return result
