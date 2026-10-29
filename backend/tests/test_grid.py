"""Grid model and validation tests."""

import pytest
from app.core.errors import ValidationError
from app.simulation.grid import BuildingGrid, cells_to_key, key_to_cells

from tests.conftest import grid_from_rows


class TestGridValidation:
    def test_valid_grid_loads(self, open_room) -> None:
        assert open_room.width == 6
        assert open_room.exits["E1"].capacity_pps == 1.0
        assert open_room.zones["Z"].cells == [(0, 0), (0, 1), (0, 2), (0, 3)]

    def test_too_small_grid_rejected(self) -> None:
        with pytest.raises(ValidationError, match="too small"):
            grid_from_rows(rows=[".."], exits=[], zones=[])

    def test_too_large_grid_rejected(self) -> None:
        with pytest.raises(ValidationError, match="too large"):
            BuildingGrid.from_dict(
                {
                    "width": 500,
                    "height": 500,
                    "cell_size_m": 0.5,
                    "walls": [],
                    "exits": [{"id": "E", "x": 0, "y": 0}],
                    "zones": [],
                }
            )

    def test_grid_without_exits_rejected(self) -> None:
        with pytest.raises(ValidationError, match="no exits"):
            grid_from_rows(
                rows=["....", "....", "....", "...."],
                exits=[],
                zones=[{"id": "Z", "name": "z", "cells": [[0, 0]]}],
            )

    def test_exit_out_of_bounds_rejected(self) -> None:
        with pytest.raises(ValidationError, match="outside the grid"):
            grid_from_rows(
                rows=["....", "....", "....", "...."],
                exits=[{"id": "E", "x": 9, "y": 9}],
                zones=[],
            )

    def test_zone_on_wall_rejected(self) -> None:
        with pytest.raises(ValidationError, match="wall"):
            grid_from_rows(
                rows=["..#.", "....", "....", "...."],
                exits=[{"id": "E", "x": 3, "y": 1}],
                zones=[{"id": "Z", "name": "z", "cells": [[2, 0]]}],
            )

    def test_zone_out_of_bounds_rejected(self) -> None:
        with pytest.raises(ValidationError, match="outside the grid"):
            grid_from_rows(
                rows=["....", "....", "....", "...."],
                exits=[{"id": "E", "x": 3, "y": 1}],
                zones=[{"id": "Z", "name": "z", "cells": [[10, 10]]}],
            )

    def test_duplicate_exit_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate exit"):
            grid_from_rows(
                rows=["....", "....", "....", "...."],
                exits=[
                    {"id": "E", "x": 3, "y": 1},
                    {"id": "E", "x": 0, "y": 0},
                ],
                zones=[],
            )

    def test_negative_capacity_rejected(self) -> None:
        with pytest.raises(ValidationError, match="positive"):
            grid_from_rows(
                rows=["....", "....", "....", "...."],
                exits=[{"id": "E", "x": 3, "y": 1, "capacity_pps": -1.0}],
                zones=[],
            )

    def test_malformed_wall_cell_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Wall cells"):
            BuildingGrid.from_dict(
                {
                    "width": 4,
                    "height": 4,
                    "walls": [[0]],
                    "exits": [{"id": "E", "x": 3, "y": 1}],
                    "zones": [],
                }
            )

    def test_unreachable_cells_warn_but_load(self) -> None:
        # A sealed pocket must not crash loading; it produces a warning.
        grid = grid_from_rows(
            rows=[
                "....",
                ".##.",
                "#..#",
                "####",
            ],
            exits=[{"id": "E", "x": 3, "y": 0}],
            zones=[{"id": "Z", "name": "sealed", "cells": [[1, 2]]}],
        )
        assert any("cannot reach any exit" in w for w in grid._validate_reachability())

    def test_cell_key_roundtrip(self) -> None:
        assert key_to_cells(cells_to_key(3, 7)) == (3, 7)
