"""Core engine tests: movement, occupancy, throughput, integrity, reproducibility."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.simulation.engine import EngineConfig, EvacuationEngine
from tests.conftest import grid_from_rows


def fast_config(zone: str = "Z", population: int = 4, seed: int = 42, **overrides) -> EngineConfig:
    """Zero reaction delay, uniform speed: predictable movement for tests."""
    params = {
        "strategy": "nearest_exit",
        "zone_populations": {zone: population},
        "speed_distribution": {"distribution": "uniform", "min": 1.0, "max": 1.0},
        "pre_movement_distribution": {"distribution": "uniform", "min": 0.0, "max": 0.0},
        "seed": seed,
        "max_duration_s": 120.0,
        "dt_s": 0.25,
        "frame_interval_s": 1.0,
    }
    params.update(overrides)
    return EngineConfig(**params)


class TestBasicEvacuation:
    def test_single_occupant_evacuates(self, open_room):
        engine = EvacuationEngine(open_room, fast_config(population=1))
        result = engine.run()
        assert result.status == "completed"
        assert result.evacuated_count == 1
        assert result.total_occupants == 1
        assert result.sim_time_s <= 4.0

    def test_open_room_all_evacuate(self, open_room):
        engine = EvacuationEngine(open_room, fast_config(population=4, seed=7))
        result = engine.run()
        assert result.status == "completed"
        assert result.evacuated_count == 4
        assert result.unreachable_count == 0
        assert result.remaining_count == 0

    def test_mass_balance(self, open_room):
        engine = EvacuationEngine(open_room, fast_config(population=4, seed=3))
        result = engine.run()
        assert (
            result.evacuated_count + result.unreachable_count + result.remaining_count
            == result.total_occupants
        )


class TestMovementConstraints:
    def test_walls_are_never_traversed(self):
        # Corridor with a wall; the only route goes around it.
        grid = grid_from_rows(
            rows=[
                "....",
                ".##.",
                "....",
                "....",
            ],
            exits=[{"id": "E", "x": 3, "y": 1}],
            zones=[{"id": "Z", "cells": [[0, 1]]}],
        )
        engine = EvacuationEngine(grid, fast_config(population=1))
        result = engine.run()
        assert result.status == "completed"
        walked = set()
        for frame in result.frames:
            for _id, x, y, _status in frame["occupants"]:
                walked.add((x, y))
        assert (1, 1) not in walked and (2, 1) not in walked  # wall cells never used

    def test_two_occupants_never_share_a_cell(self, open_room):
        engine = EvacuationEngine(open_room, fast_config(population=4, seed=11))
        result = engine.run()
        for frame in result.frames:
            positions = [(x, y) for _id, x, y, _s in frame["occupants"]]
            assert len(positions) == len(set(positions)), "two occupants shared a cell"

    def test_conflicting_requests_resolve_and_everyone_still_exits(self):
        # Four occupants squeezed into adjacent cells heading for one exit:
        # contests must occur and resolve without losing anyone.
        grid = grid_from_rows(
            rows=[
                ".....",
                ".....",
                ".....",
                ".....",
            ],
            exits=[{"id": "E", "x": 4, "y": 1}],
            zones=[{"id": "Z", "cells": [[1, 0], [1, 1], [1, 2], [2, 1]]}],
        )
        engine = EvacuationEngine(grid, fast_config(population=4, seed=5))
        result = engine.run()
        assert result.status == "completed"
        assert result.evacuated_count == 4
        assert result.queue_total_s > 0  # someone was actually delayed

    def test_head_on_swap_resolves_without_collision(self, open_room):
        """Direct unit test of the cycle/swap resolution in _apply_moves.

        Two occupants facing each other in a 1-wide corridor, each assigned to
        the exit behind the other. The simultaneous-swap rule must move both
        without ever sharing a cell, and must not lose anyone.
        """
        engine = EvacuationEngine(open_room, fast_config(population=2, seed=1))
        a = engine.occupants[0]
        b = engine.occupants[1]
        # Force positions and goals: a at x=2 wants to go right; b at x=3
        # wants to go left (a head-on swap situation).
        a.x, a.y = 2, 1
        b.x, b.y = 3, 1
        engine.occupied = {(2, 1), (3, 1)}
        winners = [(a, (3, 1)), (b, (2, 1))]
        engine._apply_moves(winners, engine.occupied, t_end=0.25)
        assert (a.x, a.y) == (3, 1)
        assert (b.x, b.y) == (2, 1)
        assert engine.occupied == {(2, 1), (3, 1)}
        assert len({a.pos, b.pos}) == 2

    def test_following_platoon_advances(self):
        # Four occupants in single file in a 1-wide corridor: the follower
        # must advance into the leader's vacated cell; all must evacuate.
        grid = grid_from_rows(
            rows=[
                "....E",
                "#####",
                "#####",
                "#####",
            ],
            exits=[{"id": "E", "x": 4, "y": 0}],
            zones=[{"id": "Z", "cells": [[0, 0]]}],
        )
        result = EvacuationEngine(grid, fast_config(population=4, seed=2)).run()
        assert result.status == "completed"
        assert result.evacuated_count == 4
        # Identical speeds at 1-cell spacing move in lockstep (no blocking),
        # but the shared door throttles the platoon: 1 pps means the last
        # person leaves roughly 3 s after the first.
        times = result.exit_stats[0]["discharge_times"]
        assert len(times) == 4
        assert times[-1] - times[0] >= 3.0 - 0.25


class TestTiming:
    def test_reaction_delay_delays_movement(self, open_room):
        config_now = fast_config(population=1, seed=9)
        config_late = fast_config(
            population=1,
            seed=9,
            pre_movement_distribution={"distribution": "uniform", "min": 10.0, "max": 10.0},
        )
        now = EvacuationEngine(open_room, config_now).run()
        late = EvacuationEngine(open_room, config_late).run()
        assert now.evacuated_count == 1 and late.evacuated_count == 1
        assert late.max_evacuation_time_s - now.max_evacuation_time_s == pytest.approx(10.0, abs=0.6)

    def test_speed_affects_arrival_time(self, open_room):
        # Zone at (0,0), exit at (5,1): 6 cells of travel.
        slow = EvacuationEngine(
            open_room,
            fast_config(population=1, seed=4, speed_distribution={"distribution": "uniform", "min": 0.5, "max": 0.5}),
        ).run()
        fast = EvacuationEngine(
            open_room,
            fast_config(population=1, seed=4, speed_distribution={"distribution": "uniform", "min": 2.0, "max": 2.0}),
        ).run()
        assert slow.max_evacuation_time_s > fast.max_evacuation_time_s
        # 6 cells * 0.5 m at 0.5 m/s = 6 s; at 2 m/s = 1.5 s (+ step quantization).
        assert slow.max_evacuation_time_s == pytest.approx(6.0, abs=1.0)
        assert fast.max_evacuation_time_s == pytest.approx(1.5, abs=1.0)

    def test_too_large_dt_rejected(self, open_room):
        with pytest.raises(ValidationError, match="too large"):
            EvacuationEngine(
                open_room,
                fast_config(speed_distribution={"distribution": "uniform", "min": 2.0, "max": 2.0}, dt_s=1.0),
            )

    def test_max_duration_respected(self):
        # 21 m corridor at ~1 m/s takes ~21+ s; cap at 5 s.
        grid = grid_from_rows(
            rows=[
                "....................E",
                "#####################",
                "#####################",
                "#####################",
            ],
            exits=[{"id": "E", "x": 20, "y": 0}],
            zones=[{"id": "Z", "cells": [[0, 0]]}],
        )
        config = fast_config(population=1, max_duration_s=5.0)
        engine = EvacuationEngine(grid, config)
        result = engine.run()
        assert result.status == "incomplete"
        assert result.evacuated_count == 0
        assert result.remaining_count == 1
        assert result.sim_time_s == pytest.approx(5.0)
        assert any("maximum duration" in w for w in result.warnings)


class TestExitThroughput:
    def test_throughput_is_respected(self):
        # One door with capacity 0.5 persons/s: two occupants queue at it.
        # The second may not leave before 1/0.5 = 2 s after the first.
        grid = grid_from_rows(
            rows=[
                "..E.",
                "....",
                "....",
                "....",
            ],
            exits=[{"id": "E", "x": 2, "y": 0, "capacity_pps": 0.5}],
            zones=[{"id": "Z", "cells": [[0, 0]]}],
        )
        config = fast_config(population=2, seed=13)
        engine = EvacuationEngine(grid, config)
        result = engine.run()
        assert result.evacuated_count == 2
        times = sorted(t for e in result.exit_stats for t in e["discharge_times"])
        assert len(times) == 2
        assert times[1] - times[0] >= 2.0 - 0.25  # one step tolerance

    def test_exit_credit_does_not_bank_into_bursts(self):
        # Capacity 0.5 pps: after a long idle period with nobody at the door,
        # at most a small burst may discharge immediately.
        grid = grid_from_rows(
            rows=[
                "..E.",
                "....",
                "....",
                "....",
            ],
            exits=[{"id": "E", "x": 2, "y": 0, "capacity_pps": 0.5}],
            zones=[{"id": "Z", "cells": [[0, 0]]}],
        )
        config = fast_config(
            population=3,
            seed=17,
            pre_movement_distribution={"distribution": "uniform", "min": 60.0, "max": 60.0},
        )
        result = EvacuationEngine(grid, config).run()
        times = sorted(t for e in result.exit_stats for t in e["discharge_times"])
        # Everyone reacts at t=60; with capacity 0.5 pps the third person
        # cannot leave before ~64 s regardless of idle banking.
        assert times[2] >= 60.0 + 2 * (1 / 0.5) - 0.5

    def test_high_capacity_exits_multiple_per_step(self):
        grid = grid_from_rows(
            rows=[
                "..E.",
                "....",
                "....",
                "....",
            ],
            exits=[{"id": "E", "x": 2, "y": 0, "capacity_pps": 8.0}],
            zones=[{"id": "Z", "cells": [[0, 0], [1, 0], [3, 0]]}],
        )
        # Three occupants reach the door quickly; 8 pps allows several
        # discharges within one 0.25 s step.
        result = EvacuationEngine(grid, fast_config(population=3, seed=19)).run()
        assert result.evacuated_count == 3
        first_step_discharges = sum(
            1 for e in result.exit_stats for t in e["discharge_times"] if t <= 0.75 + 1e-9
        )
        assert first_step_discharges >= 2


class TestUnreachableAndBlocking:
    def test_unreachable_occupant_is_marked(self):
        grid = grid_from_rows(
            rows=[
                "....",
                ".##.",
                "#..#",
                "####",
            ],
            exits=[{"id": "E", "x": 3, "y": 0}],
            zones=[{"id": "Z", "cells": [[1, 2]]}],
        )
        result = EvacuationEngine(grid, fast_config(population=1)).run()
        assert result.status == "completed"  # nothing left to simulate
        assert result.unreachable_count == 1
        assert result.evacuated_count == 0
        assert result.total_occupants == 1

    def test_blocked_exit_causes_rerouting(self):
        grid = grid_from_rows(
            rows=[
                "E....E",
                "......",
                "......",
                "......",
            ],
            exits=[
                {"id": "EA", "x": 0, "y": 0},
                {"id": "EB", "x": 5, "y": 0},
            ],
            zones=[{"id": "Z", "cells": [[2, 1], [2, 2]]}],
        )
        # Without blocking: both exits usable. With EA blocked: EB carries all.
        open_result = EvacuationEngine(grid, fast_config(population=2, seed=21)).run()
        blocked_cfg = fast_config(
            population=2, seed=21, blocked_exit_ids={"EA"}, max_duration_s=300
        )
        blocked_result = EvacuationEngine(grid, blocked_cfg).run()
        assert open_result.evacuated_count == 2
        assert blocked_result.evacuated_count == 2
        blocked_stats = {e["id"]: e for e in blocked_result.exit_stats}
        assert "EA" not in blocked_stats  # blocked exit is not part of the run
        assert blocked_stats["EB"]["evacuated"] == 2

    def test_blocked_cells_close_routes(self):
        grid = grid_from_rows(
            rows=[
                "E...E",
                ".....",
                ".....",
                ".....",
            ],
            exits=[
                {"id": "EA", "x": 0, "y": 0},
                {"id": "EB", "x": 4, "y": 0},
            ],
            zones=[{"id": "Z", "cells": [[2, 1]]}],
        )
        # Blocking the top row between the exits and EA forces the route
        # through the lower rows to EB.
        config = fast_config(
            population=1,
            seed=23,
            blocked_exit_ids={"EA"},
            blocked_cells={(1, 0), (2, 0), (3, 0)},
        )
        result = EvacuationEngine(grid, config).run()
        assert result.evacuated_count == 1
        walked = set()
        for frame in result.frames:
            for _id, x, y, _s in frame["occupants"]:
                walked.add((x, y))
        assert all(cell not in walked for cell in [(1, 0), (2, 0), (3, 0)])

    def test_scenario_with_unknown_zone_rejected(self, open_room):
        with pytest.raises(ValidationError, match="unknown zone"):
            EvacuationEngine(open_room, fast_config(zone="NOPE"))

    def test_all_exits_blocked_rejected(self, open_room):
        from app.core.errors import SimulationError

        with pytest.raises(SimulationError, match="All exits are blocked"):
            EvacuationEngine(open_room, fast_config(blocked_exit_ids={"E1"}))


class TestReproducibility:
    def test_same_seed_same_result(self, open_room):
        config = fast_config(population=12, seed=77, max_duration_s=300)
        r1 = EvacuationEngine(open_room, config).run().to_dict()
        r2 = EvacuationEngine(open_room, config).run().to_dict()
        r1.pop("wall_time_ms")
        r2.pop("wall_time_ms")
        assert r1 == r2

    def test_different_seed_uses_different_randomness(self, open_room):
        config_a = fast_config(population=12, seed=1)
        config_b = fast_config(population=12, seed=2)
        ra = EvacuationEngine(open_room, config_a).run()
        rb = EvacuationEngine(open_room, config_b).run()
        # With 12 occupants and 4 zone cells, spawn layouts differ between seeds.
        assert ra.frames[0]["occupants"] != rb.frames[0]["occupants"]


class TestCongestionRecording:
    def test_congestion_heatmap_records_blocked_attempts(self):
        result = EvacuationEngine(
            grid_from_rows(*_contest_grid()), fast_config(population=8, seed=5)
        ).run()
        assert result.evacuated_count == 8
        # Contested narrow flow: at least one blocked attempt must be recorded.
        assert sum(result.congestion.values()) > 0
        assert result.queue_total_s > 0

    def test_frames_sampled_at_interval(self, open_room):
        result = EvacuationEngine(
            open_room, fast_config(population=4, seed=5, frame_interval_s=2.0)
        ).run()
        times = [f["t"] for f in result.frames]
        assert times[0] == 0.0
        assert all(b - a >= 2.0 - 1e-6 for a, b in zip(times, times[1:]))
        # Final frame shows the end state.
        assert result.frames[-1]["t"] >= result.sim_time_s - 2.0


def _contest_grid():
    """Wide room, one small door: forces queueing and blocked attempts."""
    return (
        [
            ".......",
            ".......",
            ".......",
            ".......",
        ],
        [{"id": "E", "x": 3, "y": 0, "capacity_pps": 1.0}],
        [{"id": "Z", "cells": [[0, 1], [1, 1], [0, 2], [1, 2], [2, 1], [2, 2], [1, 3], [2, 3]]}],
    )
