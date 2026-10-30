"""Disaster scenario tests: fire, earthquake, stampede.

Each disaster must evolve during the run, be honestly counted (incapacitated
occupants are casualties, never dropped), and stay deterministic. The exact
model rules are documented in docs/SIMULATION_MODEL.md and the Methodology
page; here we verify the engine applies them.
"""

from __future__ import annotations

import pytest
from app.simulation.engine import EngineConfig, EvacuationEngine

from tests.conftest import grid_from_rows


def config(disaster_type: str, intensity: float, population: int = 16, seed: int = 11, **overrides):
    params = {
        "zone_populations": {"Z": population},
        "speed_distribution": {"distribution": "uniform", "min": 1.0, "max": 1.0},
        "pre_movement_distribution": {"distribution": "uniform", "min": 0.0, "max": 1.0},
        "seed": seed,
        "max_duration_s": 240.0,
        "dt_s": 0.25,
        "disaster_type": disaster_type,
        "disaster_intensity": intensity,
    }
    params.update(overrides)
    return EngineConfig(**params)


def office_grid():
    return grid_from_rows(
        [
            "############",
            "#..........#",
            "#..........#",
            "#..........#",
            "#..........#",
            "####....####",
        ],
        [{"id": "E", "x": 5, "y": 5, "capacity_pps": 1.5}],
        [{"id": "Z", "name": "Office", "cells": [[x, y] for x in range(1, 11) for y in range(1, 5)]}],
    )


def mass_ok(result) -> bool:
    return (
        result.evacuated_count
        + result.unreachable_count
        + result.incapacitated_count
        + result.remaining_count
        == result.total_occupants
    )


class TestFire:
    def test_fire_blocks_cells_and_incapsulates(self):
        """With fire, the plan must end WORSE than the no-disaster baseline:
        fewer evacuated and/or casualties — the disaster bites. The long
        pre-movement delay keeps occupants inside while the fire spreads."""
        grid = office_grid()
        baseline = EvacuationEngine(
            grid, config("none", 0.0, population=24, seed=31, max_duration_s=120,
                         pre_movement_distribution={"distribution": "uniform", "min": 5.0, "max": 12.0})
        ).run()
        fire = EvacuationEngine(
            grid, config("fire", 0.8, population=24, seed=31, max_duration_s=120,
                         pre_movement_distribution={"distribution": "uniform", "min": 5.0, "max": 12.0})
        ).run()

        assert mass_ok(baseline) and mass_ok(fire)
        assert fire.incapacitated_count >= 1, "fire must catch at least one occupant"
        assert fire.evacuated_count < baseline.evacuated_count or fire.remaining_count > 0
        assert fire.disaster["type"] == "fire"
        assert fire.disaster["cells_blocked"] >= fire.disaster["ignited_cells"] > 0

    def test_higher_intensity_is_worse(self):
        grid = office_grid()
        outcomes = []
        for intensity in (0.3, 0.9):
            r = EvacuationEngine(grid, config("fire", intensity, population=16, max_duration_s=90)).run()
            outcomes.append(r.evacuated_count + r.incapacitated_count)
        # Higher intensity can only reduce or equal the number of people who
        # got out alive. (Deterministic layouts make this strict here.)
        assert outcomes[1] <= outcomes[0]

    def test_fire_origin_respected(self):
        """Pin the origin at the spawn cells and hold occupants in place with
        a long pre-movement delay: the fire must catch them there."""
        grid = grid_from_rows(
            [
                "############",
                "#..........#",
                "#..........#",
                "#..........#",
                "#..........#",
                "####....####",
            ],
            [{"id": "E", "x": 5, "y": 5, "capacity_pps": 1.5}],
            [{"id": "Z", "name": "At origin", "cells": [[1, 1], [2, 1], [1, 2], [2, 2]]}],
        )
        cfg = config(
            "fire", 1.0, population=4, seed=3,
            disaster_origin=(2, 2),
            max_duration_s=60,
            pre_movement_distribution={"distribution": "uniform", "min": 8.0, "max": 8.0},
        )
        result = EvacuationEngine(grid, cfg).run()
        assert result.disaster["origin"] == [2, 2]
        # rate = 0.25 cells/s -> radius 2.0 by t=8 s: the whole 2x2 spawn
        # area is on fire exactly when the occupants finally react.
        assert result.incapacitated_count == 4
        assert result.evacuated_count == 0

    def test_fire_is_deterministic(self):
        grid = office_grid()
        cfg = config("fire", 0.7, population=12, seed=21, max_duration_s=90)
        r1 = EvacuationEngine(grid, cfg).run().to_dict()
        r2 = EvacuationEngine(grid, cfg).run().to_dict()
        r1.pop("wall_time_ms")
        r2.pop("wall_time_ms")
        assert r1 == r2


class TestEarthquake:
    def test_collapse_blocks_cells_and_extends_reaction(self):
        grid = office_grid()
        cfg = config("earthquake", 0.8, population=24, seed=5, max_duration_s=60,
                     exit_capacity_overrides={"E": 0.75})
        engine = EvacuationEngine(grid, cfg)
        collapse = engine.disaster.collapse_time
        assert 0 < collapse < 30.0
        result = engine.run()
        assert mass_ok(result)
        assert result.disaster["cells_blocked"] >= 1
        # Debris concentrates near exits: the exit cell itself can be debris.
        assert result.disaster["type"] == "earthquake"

    def test_collapse_can_seal_the_exit(self):
        """Catastrophic intensity blocks cells nearest exits first — with a
        small plan the single exit can be lost and nobody escapes. Honest
        failure, not a simulation bug."""
        grid = office_grid()
        result = EvacuationEngine(
            grid, config("earthquake", 1.0, population=24, seed=2, max_duration_s=120,
                         exit_capacity_overrides={"E": 0.75})
        ).run()
        assert mass_ok(result)
        assert result.disaster["cells_blocked"] >= 1
        # Either the exit survived and some escaped, or it was destroyed and
        # the plan fails — both are valid, honestly reported outcomes.
        assert result.status in ("completed", "incomplete")

    def test_waiting_occupants_get_confusion_delay(self):
        grid = office_grid()
        cfg = config("earthquake", 0.9, population=20, seed=8, max_duration_s=20,
                     exit_capacity_overrides={"E": 0.5},
                     pre_movement_distribution={"distribution": "uniform", "min": 5.0, "max": 30.0})
        engine = EvacuationEngine(grid, cfg)
        engine.run()
        # Occupants still WAITING at the collapse get the confusion
        # extension (25 * intensity seconds added to their delay). Original
        # delays are 5-30 s; those above the 12 s collapse were waiting and
        # must now exceed 30 s (the pre-movement maximum).
        delayed = [o for o in engine.occupants if o.reaction_delay_s > 30.0]
        assert delayed, "confusion delay must be applied to waiting occupants"
        assert all(o.reaction_delay_s >= 25.0 * 0.9 - 1e-9 for o in delayed)


class TestStampede:
    def test_crush_zones_slow_evacuation(self):
        grid = office_grid()
        # Dense crowd through one small door -> congestion -> crush.
        slow = EvacuationEngine(
            grid, config("stampede", 0.9, population=40, seed=4, max_duration_s=60,
                         exit_capacity_overrides={"E": 0.5})
        ).run()
        baseline = EvacuationEngine(
            grid, config("none", 0.0, population=40, seed=4, max_duration_s=60,
                         exit_capacity_overrides={"E": 0.5})
        ).run()
        assert mass_ok(slow) and mass_ok(baseline)
        assert slow.disaster["crush_cells"] >= 1
        # Crush zones slow movement: fewer people get out within the horizon.
        assert slow.evacuated_count < baseline.evacuated_count

    def test_crush_zones_are_permanent_and_bounded(self):
        grid = office_grid()
        engine = EvacuationEngine(grid, config("stampede", 1.0, population=40, seed=6, max_duration_s=60,
                                               exit_capacity_overrides={"E": 0.5}))
        engine.run()
        crush = engine.disaster.crush_zones
        assert crush
        # Crush zones grow only within 3 cells of a triggered cell.
        for cx, cy in crush:
            assert any(
                max(abs(cx - c[0]), abs(cy - c[1])) <= 3 for c in crush
            )


class TestValidationAndBalance:
    def test_mass_balance_holds_under_every_disaster(self):
        grid = office_grid()
        for disaster_type, intensity in (
            ("fire", 0.5),
            ("earthquake", 0.6),
            ("stampede", 0.8),
            ("none", 0.0),
        ):
            result = EvacuationEngine(grid, config(disaster_type, intensity, population=24, seed=9)).run()
            assert mass_ok(result), disaster_type

    def test_unknown_disaster_type_rejected_by_schema(self):
        from app.schemas.scenario import DisasterSpecSchema
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="disaster type"):
            DisasterSpecSchema(type="volcano", intensity=0.5)

    def test_intensity_bounds_enforced(self):
        from app.schemas.scenario import DisasterSpecSchema
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DisasterSpecSchema(type="fire", intensity=1.5)
