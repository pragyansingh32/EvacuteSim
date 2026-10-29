"""Building CRUD and validation endpoints."""

from fastapi import APIRouter, Response, status

from app.api.deps import DbSession
from app.repositories import buildings as building_repo
from app.schemas import BuildingCreate, BuildingDetail, BuildingRead, BuildingUpdate
from app.services import building_service

router = APIRouter(prefix="/buildings", tags=["buildings"])


@router.get("", response_model=list[BuildingRead])
def list_buildings(db: DbSession) -> list:
    return building_repo.list_buildings(db)


@router.post("", response_model=BuildingDetail, status_code=status.HTTP_201_CREATED)
def create_building(payload: BuildingCreate, db: DbSession) -> dict:
    building = building_service.create_building(db, payload.model_dump())
    db.commit()
    return building_service.get_building_detail(building)


@router.post("/validate", response_model=dict)
def validate_building(payload: BuildingCreate) -> dict:
    """Validate a layout without saving; returns warnings (raises 422 on errors)."""
    return {"warnings": building_service.validate_only(payload.model_dump())}


@router.get("/{building_id}", response_model=BuildingDetail)
def get_building(building_id: int, db: DbSession) -> dict:
    building = building_repo.get_building(db, building_id)
    return building_service.get_building_detail(building)


@router.put("/{building_id}", response_model=BuildingDetail)
def update_building(building_id: int, payload: BuildingUpdate, db: DbSession) -> dict:
    payload_dict = payload.model_dump(exclude_none=True)
    building = building_service.update_building(db, building_id, payload_dict)
    db.commit()
    return building_service.get_building_detail(building)


@router.delete("/{building_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_building(building_id: int, db: DbSession) -> Response:
    building_repo.delete_building(db, building_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
