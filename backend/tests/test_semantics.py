"""Automatic plan-interpretation tests: doors, exits, zones, populations."""

from __future__ import annotations

from app.planimport.semantics import analyze, remove_noise


def walls_from_ascii(rows: list[str]) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y, row in enumerate(rows)
        for x, ch in enumerate(row)
        if ch == "#"
    }


class TestAutoDetection:
    def test_detects_exit_interior_door_and_two_rooms(self):
        # 14x6: outer walls with a 3-cell bottom gap (exit), one vertical
        # interior wall with a 2-cell door gap.
        walls = walls_from_ascii(
            [
                "##############",
                "#.....#......#",
                "#.....#......#",
                "#.....+......#",  # '+' marks the door gap cells below
                "#.....#......#",
                "####..########",
            ]
        )
        # Build properly: interior wall with 2-cell gap at y=3; bottom wall gap at x=4..6
        walls = walls_from_ascii(
            [
                "##############",
                "#.....#......#",
                "#.....#......#",
                "#............#",
                "#............#",
                "####..########",
            ]
        )
        # 2-cell interior door gap (1-cell gaps are sealed by the close pass
        # as pinholes, by design).
        walls.discard((6, 3))
        walls.discard((6, 4))
        result = analyze(walls, 14, 6, cell_size_m=0.5, occupancy_density=0.25)
        assert len(result.exits) == 1, f"expected 1 exit, got {result.exits}"
        assert result.exits[0]["y"] == 5  # at the bottom gap
        assert result.doors >= 1  # interior door detected
        assert len(result.zones) == 2, f"expected 2 zones, got {result.zones}"
        pops = result.zone_populations
        assert len(pops) == 2 and all(v > 0 for v in pops.values())

    def test_exit_with_margin_ring_detected(self):
        """Regression: when the plan's envelope is inset from the grid edge
        (auto-crop pad), a door to the outside leads to the floor margin ring,
        NOT out-of-bounds. The exit must still be detected."""
        walls = walls_from_ascii(
            [
                "............",
                "............",
                "############",
                "#..........#",
                "#..........#",
                "#..........#",
                "####..######",  # door gap pierces the envelope
                "............",
                "............",
            ]
        )
        # The gap cells (4,6),(5,6) lead from the interior to the margin ring
        # (floor rows 0-1 and 7-8, touching the grid edge) - the same
        # geometry auto-crop produces for real uploaded plans.
        result = analyze(walls, 12, 9, cell_size_m=0.5, occupancy_density=0.25)
        assert len(result.exits) == 1, f"expected exit through margin ring, got {result.exits}"
        assert len(result.zones) == 1
        assert result.zone_populations and all(v > 0 for v in result.zone_populations.values())

    def test_one_cell_interior_door_detected(self):
        walls = walls_from_ascii(
            [
                "##############",
                "#.....#......#",
                "#.....#......#",
                "#............#",
                "#.....#......#",
                "##############",
            ]
        )
        walls.discard((6, 3))  # 1-cell door gap in the vertical wall
        result = analyze(walls, 14, 6, cell_size_m=0.5)
        assert result.doors >= 1
        assert len(result.zones) == 2

    def test_door_capacity_from_width(self):
        # A 4-cell exterior gap with 0.5 m cells -> 2.0 m -> ~2.6 p/s.
        walls = walls_from_ascii(
            [
                "########",
                "#......#",
                "#......#",
                "#......#",
                "##....##",
            ]
        )
        result = analyze(walls, 8, 5, cell_size_m=0.5, occupancy_density=0.25)
        assert len(result.exits) == 1, result.exits
        assert result.exits[0]["capacity_pps"] >= 2.0

    def test_gap_between_wall_segments_stays_passable(self):
        # Interior wall column 6 exists only at rows 1-2; rows 3-4 are open.
        # The system detects the 2-cell channel as a door - the two areas stay
        # connected for evacuation either way.
        walls = walls_from_ascii(
            [
                "##############",
                "#.....#......#",
                "#.....#......#",
                "#............#",
                "#............#",
                "##############",
            ]
        )
        result = analyze(walls, 14, 6, cell_size_m=0.5)
        assert result.doors >= 1
        assert len(result.exits) == 0
        # No room is stranded: every zone has a path (door) to the others.
        assert not any("no path to any" in w for w in result.warnings)

    def test_sealed_room_produces_warning(self):
        # An outer room with an exterior door, plus a fully sealed interior
        # pocket: the pocket must be flagged as unreachable.
        walls = walls_from_ascii(
            [
                "##########",
                "#........#",
                "#.######.#",
                "#.#....#.#",
                "#.#....#.#",
                "#.######.#",
                "#........#",
                "####..####",
            ]
        )
        result = analyze(walls, 10, 8, cell_size_m=0.5)
        assert len(result.exits) == 1, result.exits
        assert any("no path to any" in w for w in result.warnings), result.warnings


class TestCleanup:
    def test_noise_removal_drops_small_specks(self):
        walls = walls_from_ascii(
            [
                "########",
                "#......#",
                "#..##..#",  # isolated 2-cell speck inside the room
                "#......#",
                "########",
            ]
        )
        cleaned, removed = remove_noise(walls)
        assert removed == 2
        assert (3, 2) not in cleaned and (4, 2) not in cleaned
        assert (0, 0) in cleaned  # the envelope is untouched


class TestEndToEndOnBundledPlan:
    def test_sample_plan_yields_runnable_draft(self):
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / "scripts"))
        try:
            from make_sample_plan import main as make_plan
        finally:
            sys.path.pop(0)
        make_plan()

        from app.planimport import ImportParams, import_from_image

        plan_path = root / "frontend" / "public" / "sample-plan.png"
        result = import_from_image(
            plan_path.read_bytes(),
            ImportParams(target_width=70, real_width_m=24.0, occupancy_density=0.25),
            "Sample",
        )
        draft = result.draft
        assert len(draft.exits) >= 1, f"expected auto exits, got {draft.exits}"
        assert len(draft.zones) >= 2, f"expected auto zones, got {len(draft.zones)}"
        assert sum(result.zone_populations.values()) > 0
        sem = result.stats["semantics"]
        assert sem["rooms"] >= 2 and sem["doors"] >= 1

        # The draft must validate as a building (exits/zones consistent).
        from app.simulation.grid import BuildingGrid

        grid = BuildingGrid.from_dict(draft.to_editor_state())
        warnings = grid.validate()
        assert not any("no exits" in w.lower() for w in warnings)
