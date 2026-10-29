"""Routing strategy tests (Phase 4)."""

from __future__ import annotations

from app.simulation.engine import EngineConfig, EvacuationEngine
from tests.conftest import grid_from_rows


def config(strategy: str, population: int = 10, seed: int = 42, **overrides) -> EngineConfig:
    params = {
        "strategy": strategy,
        "zone_populations": {"Z": population},
        "speed_distribution": {"distribution": "uniform", "min": 1.0, "max": 1.0},
        "pre_movement_distribution": {"distribution": "uniform", "min": 0.0, "max": 0.0},
        "seed": seed,
        "max_duration_s": 600.0,
        "dt_s": 0.25,
    }
    params.update(overrides)
    return EngineConfig(**params)


TWO_EXITS_ROOM = (
    [
        "E.....E",
        ".......",
        ".......",
        ".......",
    ],
    [
        {"id": "EA", "x": 0, "y": 0, "capacity_pps": 1.0},
        {"id": "EB", "x": 6, "y": 0, "capacity_pps": 1.0},
    ],
    [{"id": "Z", "name": "Middle", "cells": [[3, 1], [3, 2], [2, 1], [2, 2]]}],
)


class TestNearestExit:
    def test_all_take_the_closest_exit(self):
        grid = grid_from_rows(*TWO_EXITS_ROOM)
        # Population exactly fills the 4 zone cells (no spill): all zone cells
        # are equidistant (4 steps) from both exits, and the deterministic
        # nearest rule consistently picks the first exit id on ties.
        result = EvacuationEngine(grid, config("nearest_exit", population=4)).run()
        assert result.evacuated_count == 4
        stats = {e["id"]: e for e in result.exit_stats}
        assert stats["EA"]["evacuated"] == 4
        assert stats["EB"]["evacuated"] == 0

    def test_spilled_occupants_pick_their_own_nearest_exit(self):
        grid = grid_from_rows(*TWO_EXITS_ROOM)
        # With 10 occupants and 4 zone cells, 6 spill to nearby cells; those
        # occupants legitimately route to their own nearest exit.
        result = EvacuationEngine(grid, config("nearest_exit", population=10)).run()
        assert result.evacuated_count == 10
        stats = {e["id"]: e for e in result.exit_stats}
        # Zone cells lean toward EA, but spilled cells on the right reach EB.
        assert stats["EA"]["evacuated"] > 0
        assert stats["EB"]["evacuated"] > 0
        assert stats["EA"]["evacuated"] > stats["EB"]["evacuated"]

    def test_nearest_by_distance_not_id(self):
        grid = grid_from_rows(
            ["E....E", "......", "......", "......"],
            [
                {"id": "EA", "x": 0, "y": 0},
                {"id": "EB", "x": 5, "y": 0},
            ],
            [{"id": "Z", "cells": [[5, 1]]}],
        )
        result = EvacuationEngine(grid, config("nearest_exit", population=1)).run()
        stats = {e["id"]: e for e in result.exit_stats}
        assert stats["EB"]["evacuated"] == 1


class TestCapacityAware:
    def test_diverts_from_overloaded_exit(self):
        grid = grid_from_rows(*TWO_EXITS_ROOM)
        result = EvacuationEngine(grid, config("capacity_aware")).run()
        stats = {e["id"]: e for e in result.exit_stats}
        # Equidistant exits with live-load-aware routing must use both doors.
        assert stats["EA"]["evacuated"] > 0
        assert stats["EB"]["evacuated"] > 0
        assert result.evacuated_count == 10

    def test_respects_capacity_override(self):
        grid = grid_from_rows(*TWO_EXITS_ROOM)
        # EB becomes a wide door: capacity-aware routing should favor it.
        result = EvacuationEngine(
            grid,
            config("capacity_aware", exit_capacity_overrides={"EB": 5.0}),
        ).run()
        stats = {e["id"]: e for e in result.exit_stats}
        assert stats["EB"]["evacuated"] > stats["EA"]["evacuated"]
        assert result.evacuated_count == 10


class TestBalancedAssignment:
    def test_balances_equidistant_exits(self):
        grid = grid_from_rows(*TWO_EXITS_ROOM)
        result = EvacuationEngine(grid, config("balanced_assignment")).run()
        stats = {e["id"]: e for e in result.exit_stats}
        assert result.evacuated_count == 10
        # Equal capacities and distances: roughly even split (heuristic,
        # so assert both are used and neither starves).
        assert stats["EA"]["evacuated"] >= 3
        assert stats["EB"]["evacuated"] >= 3

    def test_low_capacity_exit_receives_fewer(self):
        grid = grid_from_rows(*TWO_EXITS_ROOM)
        result = EvacuationEngine(
            grid,
            config("balanced_assignment", exit_capacity_overrides={"EA": 0.2, "EB": 2.0}),
        ).run()
        stats = {e["id"]: e for e in result.exit_stats}
        assert stats["EB"]["evacuated"] > stats["EA"]["evacuated"]

    def test_fallback_when_assigned_exit_unreachable(self):
        # The zone straddles a full-height wall: two cells can only reach EA,
        # two only EB. The balanced assignment deals exits across the whole
        # zone, so some occupants must fall back to their nearest reachable
        # exit instead of being stranded.
        grid = grid_from_rows(
            [
                "E..#..E",
                "...#...",
                "...#...",
                "...#...",
            ],
            [
                {"id": "EA", "x": 0, "y": 0},
                {"id": "EB", "x": 6, "y": 0},
            ],
            [{"id": "Z", "cells": [[1, 1], [5, 1], [1, 2], [5, 2]]}],
        )
        result = EvacuationEngine(grid, config("balanced_assignment", population=4, seed=1)).run()
        assert result.evacuated_count == 4
        assert result.fallback_count >= 1
        stats = {e["id"]: e for e in result.exit_stats}
        # Both exits carry people (2 assigned each side, with fallbacks).
        assert stats["EA"]["evacuated"] >= 2
        assert stats["EB"]["evacuated"] >= 2

    def test_unreachable_region_marked_for_all_strategies(self):
        # Cell (2,0) is sealed: walls on every side.
        grid = grid_from_rows(
            [
                "E#.#.E",
                "######",
                "......",
                "......",
            ],
            [
                {"id": "EA", "x": 0, "y": 0},
                {"id": "EB", "x": 4, "y": 0},
            ],
            [{"id": "Z", "cells": [[2, 0]]}],
        )
        for strategy in ("nearest_exit", "capacity_aware", "balanced_assignment"):
            result = EvacuationEngine(grid, config(strategy, population=1)).run()
            assert result.unreachable_count == 1, strategy
            assert result.evacuated_count == 0, strategy


class TestFairComparison:
    def test_strategies_run_on_identical_conditions(self):
        """All three strategies complete the same layout/population/seed."""
        grid = grid_from_rows(*TWO_EXITS_ROOM)
        totals = []
        for strategy in ("nearest_exit", "capacity_aware", "balanced_assignment"):
            result = EvacuationEngine(grid, config(strategy, population=20, seed=99)).run()
            assert result.total_occupants == 20
            assert result.evacuated_count == 20
            totals.append(result.t95_s)
        # Sanity: results exist for every strategy (no fairness bias in setup).
        assert all(t is not None for t in totals)
