"""Building service: validation and CRUD."""

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models import BuildingModel
from app.repositories import buildings as building_repo
from app.simulation.grid import BuildingGrid


def _grid_from_parts(
    *,
    name: str,
    width: int,
    height: int,
    cell_size_m: float,
    walls: list,
    exits: list,
    zones: list,
) -> BuildingGrid:
    data = {
        "name": name,
        "width": width,
        "height": height,
        "cell_size_m": cell_size_m,
        "walls": [list(w) for w in walls],
        "exits": [dict(e) for e in exits],
        "zones": [
            {"id": z["id"], "name": z["name"], "cells": [list(c) for c in z["cells"]]}
            for z in zones
        ],
    }
    return BuildingGrid.from_dict(data)  # raises ValidationError on bad input


def create_building(db: Session, payload: dict) -> BuildingModel:
    grid = _grid_from_parts(
        name=payload["name"],
        width=payload["width"],
        height=payload["height"],
        cell_size_m=payload["cell_size_m"],
        walls=payload.get("walls", []),
        exits=[e.model_dump() if hasattr(e, "model_dump") else e for e in payload.get("exits", [])],
        zones=[
            z.model_dump() if hasattr(z, "model_dump") else z for z in payload.get("zones", [])
        ],
    )
    warnings = grid.validate()
    building = building_repo.create_building(db, grid, payload.get("description", ""))
    building.warnings = warnings  # transient, surfaced by the API layer
    return building


def update_building(db: Session, building_id: int, payload: dict) -> BuildingModel:
    building = building_repo.get_building(db, building_id)
    current = building.to_grid_dict()
    merged = {
        "name": payload.get("name", current["name"]),
        "width": payload.get("width", current["width"]),
        "height": payload.get("height", current["height"]),
        "cell_size_m": payload.get("cell_size_m", current["cell_size_m"]),
        "walls": payload.get("walls", current["walls"]),
        "exits": payload.get("exits", current["exits"]),
        "zones": payload.get("zones", current["zones"]),
    }
    grid = _grid_from_parts(**merged)
    warnings = grid.validate()
    building = building_repo.update_building(db, building, grid, payload.get("description"))
    building.warnings = warnings
    return building


def validate_only(payload: dict) -> list[str]:
    """Validate a layout without persisting; returns warnings."""
    grid = _grid_from_parts(
        name=payload.get("name", "validation"),
        width=payload["width"],
        height=payload["height"],
        cell_size_m=payload.get("cell_size_m", 0.5),
        walls=payload.get("walls", []),
        exits=[dict(e) for e in payload.get("exits", [])],
        zones=[
            {"id": z["id"], "name": z.get("name", z["id"]), "cells": [list(c) for c in z["cells"]]}
            for z in payload.get("zones", [])
        ],
    )
    return grid.validate()


def get_building_detail(building: BuildingModel) -> dict:
    data = building.to_grid_dict()
    warnings: list[str] = []
    try:
        grid = BuildingGrid.from_dict(data)
        warnings = grid.validate()
    except ValidationError:
        # Stored layout no longer validates (should not happen; be honest).
        warnings = ["Stored layout failed validation; it may be unusable for simulation."]
    return {
        "id": building.id,
        "name": building.name,
        "description": building.description,
        "width": building.width,
        "height": building.height,
        "cell_size_m": building.cell_size_m,
        "is_sample": building.is_sample,
        "created_at": building.created_at,
        "updated_at": building.updated_at,
        "walls": data["walls"],
        "exits": data["exits"],
        "zones": data["zones"],
        "warnings": warnings,
    }
