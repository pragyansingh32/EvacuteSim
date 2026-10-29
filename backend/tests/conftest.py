"""Shared fixtures and grid builders for simulation tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Test isolation: point the app at a throwaway SQLite file BEFORE any app
# import reads settings. Each pytest session gets a fresh database.
_TEST_DB_DIR = Path(tempfile.gettempdir()) / "evacuatesim-tests"
_TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
_TEST_DB = _TEST_DB_DIR / f"test-{os.getpid()}.db"
os.environ["EVACUATESIM_DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"

import pytest  # noqa: E402
from app.simulation.grid import BuildingGrid  # noqa: E402


def grid_from_rows(
    rows: list[str],
    exits: list[dict],
    zones: list[dict],
    cell_size_m: float = 0.5,
    name: str = "test-grid",
) -> BuildingGrid:
    """Build a grid from ASCII rows ('.' floor, '#' wall).

    Exits/zones use plain dicts matching the API representation so the tests
    also exercise from_dict validation.
    """
    height = len(rows)
    width = len(rows[0])
    assert all(len(r) == width for r in rows), "test grid rows must be rectangular"
    walls = [
        [x, y]
        for y, row in enumerate(rows)
        for x, ch in enumerate(row)
        if ch == "#"
    ]
    data = {
        "name": name,
        "width": width,
        "height": height,
        "cell_size_m": cell_size_m,
        "walls": walls,
        "exits": exits,
        "zones": zones,
    }
    return BuildingGrid.from_dict(data)


@pytest.fixture
def open_room() -> BuildingGrid:
    """6x4 open room, one exit on the right wall, one zone at the left."""
    return grid_from_rows(
        rows=[
            "......",
            "......",
            "......",
            "......",
        ],
        exits=[{"id": "E1", "x": 5, "y": 1, "capacity_pps": 1.0}],
        zones=[{"id": "Z", "name": "West", "cells": [[0, 0], [0, 1], [0, 2], [0, 3]]}],
    )


@pytest.fixture(scope="session")
def client():
    """Shared FastAPI TestClient (lifespan seeds sample data once per session)."""
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
