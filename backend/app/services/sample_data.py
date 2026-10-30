"""Synthetic sample data: two demonstration buildings and reproducible
sample scenarios.

Everything here is SYNTHETIC. The layouts resemble generic building shapes;
they are not based on any real building and carry no safety claim. Samples are
seeded once at startup (idempotent by name).
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.models import BuildingModel, ScenarioModel
from app.repositories import buildings as building_repo
from app.repositories import scenarios as scenario_repo
from app.simulation.grid import BuildingGrid

logger = logging.getLogger(__name__)

DEFAULT_SPEED = {"distribution": "normal", "mean": 1.2, "sd": 0.25, "min": 0.6, "max": 1.8}
DEFAULT_PRE_MOVEMENT = {"distribution": "uniform", "min": 0.0, "max": 15.0}


def _grid_from_ascii(
    name: str,
    rows: list[str],
    exits: list[dict],
    zones: list[dict],
    cell_size_m: float = 0.5,
) -> BuildingGrid:
    """ASCII helper: '.' floor, '#' wall. Exit/zone dicts match the API form."""
    height, width = len(rows), len(rows[0])
    assert all(len(r) == width for r in rows), f"{name}: rows must be rectangular"
    walls = [[x, y] for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "#"]
    return BuildingGrid.from_dict(
        {
            "name": name,
            "width": width,
            "height": height,
            "cell_size_m": cell_size_m,
            "walls": walls,
            "exits": exits,
            "zones": zones,
        }
    )


def sample_office() -> BuildingGrid:
    """30x20 office floor: two big rooms joined by a central hall, two exits."""
    w, h = 30, 20
    rows = [["#"] * w for _ in range(h)]
    # Open interior
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            rows[y][x] = "."
    # Interior wall between west room and hall (x=10) with a gap at y 9-10
    for y in range(1, h - 1):
        rows[y][10] = "#"
    rows[9][10] = "."
    rows[10][10] = "."
    # Interior wall between hall and east room (x=20) with a gap at y 8-11
    for y in range(1, h - 1):
        rows[y][20] = "#"
    for y in (8, 9, 10, 11):
        rows[y][20] = "."
    # A couple of interior columns in the hall
    rows[5][15] = "#"
    rows[14][15] = "#"
    ascii_rows = ["".join(r) for r in rows]
    west = [[x, y] for x in range(1, 10) for y in range(1, 19)]
    hall = [[x, y] for x in range(11, 20) for y in range(1, 19) if [x, y] not in ([15, 5], [15, 14])]
    east = [[x, y] for x in range(21, 29) for y in range(1, 19)]
    exits = [
        {"id": "EA", "x": 0, "y": 5, "capacity_pps": 1.2},
        {"id": "EB", "x": 29, "y": 14, "capacity_pps": 1.2},
    ]
    zones = [
        {"id": "ZW", "name": "West open office", "cells": west},
        {"id": "ZH", "name": "Central hall", "cells": hall},
        {"id": "ZE", "name": "East open office", "cells": east},
    ]
    return _grid_from_ascii("Sample Office A", ascii_rows, exits, zones)


def sample_hall() -> BuildingGrid:
    """24x12 assembly hall with pillars and three exits of different widths."""
    w, h = 24, 12
    rows = [["#"] * w for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            rows[y][x] = "."
    # Pillars
    for x, y in [(6, 4), (6, 8), (12, 4), (12, 8), (18, 4), (18, 8)]:
        rows[y][x] = "#"
    ascii_rows = ["".join(r) for r in rows]
    north = [[x, y] for x in range(1, w - 1) for y in range(1, 6) if [x, y] not in ([6, 4], [12, 4], [18, 4])]
    south = [[x, y] for x in range(1, w - 1) for y in range(6, h - 1) if [x, y] not in ([6, 8], [12, 8], [18, 8])]
    exits = [
        {"id": "EA", "x": 0, "y": 2, "capacity_pps": 1.0},
        {"id": "EB", "x": 23, "y": 6, "capacity_pps": 1.5},
        {"id": "EC", "x": 12, "y": 11, "capacity_pps": 0.75},
    ]
    zones = [
        {"id": "ZN", "name": "North seating", "cells": north},
        {"id": "ZS", "name": "South seating", "cells": south},
    ]
    return _grid_from_ascii("Sample Hall B", ascii_rows, exits, zones)


def _scenario_config(**overrides) -> dict:
    config = {
        "disaster": {"type": "none", "intensity": 0.0, "origin_x": None, "origin_y": None},
        "zone_populations": {},
        "speed_distribution": dict(DEFAULT_SPEED),
        "pre_movement_distribution": dict(DEFAULT_PRE_MOVEMENT),
        "strategy": "nearest_exit",
        "seed": 42,
        "blocked_exit_ids": [],
        "blocked_cells": [],
        "exit_capacity_overrides": {},
        "max_duration_s": 600.0,
        "dt_s": 0.25,
        "frame_interval_s": 1.0,
        "record_frames": True,
    }
    config.update(overrides)
    return config


SAMPLE_BUILDINGS: list[tuple[BuildingGrid, str]] = [
    (
        sample_office(),
        "Synthetic 15m x 10m office floor: two open-plan rooms joined by a "
        "central hall, one exit on each side. Purely demonstrative.",
    ),
    (
        sample_hall(),
        "Synthetic 12m x 6m assembly hall with pillars and three exits of "
        "different modeled widths. Purely demonstrative.",
    ),
]


def _sample_scenarios(building_id_by_name: dict[str, int]) -> list[dict]:
    office_id = building_id_by_name["Sample Office A"]
    hall_id = building_id_by_name["Sample Hall B"]
    base = {
        "zone_populations": {"ZW": 50, "ZH": 20, "ZE": 50},
    }
    return [
        {
            "building_id": office_id,
            "name": "Sample: Baseline evacuation (nearest exit)",
            "description": (
                "SYNTHETIC demonstration scenario — not based on a real building. "
                "120 occupants, typical walking speeds, short pre-movement delay, "
                "nearest-exit routing. Reproducible with seed 42."
            ),
            "config": _scenario_config(**base),
        },
        {
            "building_id": office_id,
            "name": "Sample: West exit blocked",
            "description": (
                "SYNTHETIC demonstration scenario — same office and population as "
                "the baseline, but exit EA is unavailable; everyone must reroute. "
                "Reproducible with seed 42."
            ),
            "config": _scenario_config(**base, blocked_exit_ids=["EA"]),
        },
        {
            "building_id": office_id,
            "name": "Sample: Balanced exit assignment",
            "description": (
                "SYNTHETIC demonstration scenario — same office and population as "
                "the baseline, but the balanced-assignment strategy distributes "
                "occupants across both exits. Reproducible with seed 42."
            ),
            "config": _scenario_config(**base, strategy="balanced_assignment"),
        },
        {
            "building_id": office_id,
            "name": "Sample: Long pre-movement delay",
            "description": (
                "SYNTHETIC demonstration scenario — occupants take 20-60 s to "
                "start moving, testing the effect of reaction time. "
                "Reproducible with seed 42."
            ),
            "config": _scenario_config(
                **base, pre_movement_distribution={"distribution": "uniform", "min": 20.0, "max": 60.0}
            ),
        },
        {
            "building_id": hall_id,
            "name": "Sample: Hall with slow occupants (capacity-aware)",
            "description": (
                "SYNTHETIC demonstration scenario — assembly hall with 180 "
                "slower occupants and unequal exit capacities, routed "
                "capacity-aware. Reproducible with seed 7."
            ),
            "config": _scenario_config(
                zone_populations={"ZN": 90, "ZS": 90},
                speed_distribution={"distribution": "normal", "mean": 0.9, "sd": 0.2, "min": 0.4, "max": 1.4},
                pre_movement_distribution={"distribution": "uniform", "min": 5.0, "max": 40.0},
                strategy="capacity_aware",
                seed=7,
            ),
        },
        {
            "building_id": office_id,
            "name": "Sample: Fire (severe) — dynamic disaster",
            "description": (
                "SYNTHETIC demonstration scenario — same office as the baseline "
                "but a fire ignites far from the exits and spreads during the "
                "simulation, blocking cells and forcing re-routing. "
                "Reproducible with seed 42."
            ),
            "config": _scenario_config(
                **base,
                disaster={"type": "fire", "intensity": 0.75, "origin_x": None, "origin_y": None},
                max_duration_s=180,
            ),
        },
        {
            "building_id": hall_id,
            "name": "Sample: Earthquake (moderate) — dynamic disaster",
            "description": (
                "SYNTHETIC demonstration scenario — the assembly hall with a "
                "moderate earthquake at ~22 s: debris blocks cells near the "
                "exits and occupants are confused. Reproducible with seed 7."
            ),
            "config": _scenario_config(
                zone_populations={"ZN": 60, "ZS": 60},
                speed_distribution={"distribution": "normal", "mean": 1.2, "sd": 0.25, "min": 0.6, "max": 1.8},
                pre_movement_distribution={"distribution": "uniform", "min": 5.0, "max": 30.0},
                strategy="nearest_exit",
                seed=7,
                disaster={"type": "earthquake", "intensity": 0.5, "origin_x": None, "origin_y": None},
                max_duration_s=300,
            ),
        },
    ]


def ensure_samples(db: Session) -> None:
    """Idempotently create sample buildings and scenarios."""
    existing_names = set(db.scalars(select(BuildingModel.name).where(BuildingModel.is_sample)))
    building_id_by_name: dict[str, int] = {}
    for grid, description in SAMPLE_BUILDINGS:
        if grid.name in existing_names:
            found = db.scalar(
                select(BuildingModel).where(BuildingModel.name == grid.name, BuildingModel.is_sample)
            )
            building_id_by_name[grid.name] = found.id
            continue
        building = building_repo.create_building(db, grid, description, is_sample=True)
        building_id_by_name[grid.name] = building.id
        logger.info("Seeded sample building '%s'", grid.name)

    existing_scenario_names = set(
        db.scalars(select(ScenarioModel.name).where(ScenarioModel.is_sample))
    )
    for spec in _sample_scenarios(building_id_by_name):
        if spec["name"] in existing_scenario_names:
            continue
        scenario_repo.create_scenario(
            db,
            building_id=spec["building_id"],
            name=spec["name"],
            description=spec["description"],
            config=spec["config"],
            is_sample=True,
        )
        logger.info("Seeded sample scenario '%s'", spec["name"])


def seed_samples_once() -> None:
    """Startup hook: create tables if needed and seed samples."""
    from app.db.session import engine
    from app.models import Base

    Base.metadata.create_all(engine)
    with session_scope() as db:
        ensure_samples(db)
