"""Building repository."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import BuildingModel
from app.simulation.grid import BuildingGrid


def get_building(db: Session, building_id: int) -> BuildingModel:
    building = db.get(BuildingModel, building_id)
    if building is None:
        raise NotFoundError(f"Building {building_id} not found.")
    return building


def list_buildings(db: Session) -> list[BuildingModel]:
    return list(db.scalars(select(BuildingModel).order_by(BuildingModel.id)))


def create_building(db: Session, grid: BuildingGrid, description: str, is_sample: bool = False) -> BuildingModel:
    data = grid.to_dict()
    building = BuildingModel(
        name=grid.name,
        description=description,
        width=grid.width,
        height=grid.height,
        cell_size_m=grid.cell_size_m,
        walls_json=BuildingModel.encode(data["walls"]),
        exits_json=BuildingModel.encode(data["exits"]),
        zones_json=BuildingModel.encode(data["zones"]),
        is_sample=is_sample,
    )
    db.add(building)
    db.flush()
    return building


def update_building(db: Session, building: BuildingModel, grid: BuildingGrid, description: str | None) -> BuildingModel:
    data = grid.to_dict()
    building.name = grid.name
    if description is not None:
        building.description = description
    building.width = grid.width
    building.height = grid.height
    building.cell_size_m = grid.cell_size_m
    building.walls_json = BuildingModel.encode(data["walls"])
    building.exits_json = BuildingModel.encode(data["exits"])
    building.zones_json = BuildingModel.encode(data["zones"])
    db.flush()
    return building


def delete_building(db: Session, building_id: int) -> None:
    building = get_building(db, building_id)
    from sqlalchemy import func

    from app.models import ScenarioModel

    in_use = db.scalar(select(func.count()).select_from(ScenarioModel).where(ScenarioModel.building_id == building_id))
    if in_use:
        raise ConflictError(
            f"Building {building_id} is used by {in_use} scenario(s); delete those first."
        )
    db.delete(building)
    db.flush()


def building_to_dict(building: BuildingModel) -> dict:
    return building.to_grid_dict()
