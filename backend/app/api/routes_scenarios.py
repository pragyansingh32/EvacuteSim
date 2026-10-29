"""Scenario CRUD endpoints."""

from fastapi import APIRouter, Response, status
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.repositories import scenarios as scenario_repo
from app.schemas import ScenarioCreate, ScenarioDetail, ScenarioRead, ScenarioUpdate
from app.services import scenario_service

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioRead])
def list_scenarios(db: DbSession, building_id: int | None = None) -> list:
    return scenario_repo.list_scenarios(db, building_id=building_id)


@router.post("", response_model=ScenarioDetail, status_code=status.HTTP_201_CREATED)
def create_scenario(payload: ScenarioCreate, db: DbSession) -> dict:
    scenario = scenario_service.create_scenario(db, payload.model_dump())
    db.commit()
    return _detail(scenario)


@router.get("/{scenario_id}", response_model=ScenarioDetail)
def get_scenario(scenario_id: int, db: DbSession) -> dict:
    return _detail(scenario_repo.get_scenario(db, scenario_id))


@router.put("/{scenario_id}", response_model=ScenarioDetail)
def update_scenario(scenario_id: int, payload: ScenarioUpdate, db: DbSession) -> dict:
    scenario = scenario_service.update_scenario(db, scenario_id, payload.model_dump(exclude_none=True))
    db.commit()
    return _detail(scenario)


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(scenario_id: int, db: DbSession) -> Response:
    scenario_repo.delete_scenario(db, scenario_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _detail(scenario: Session) -> dict:  # noqa: ANN001 - actually ScenarioModel
    data = {
        "id": scenario.id,
        "building_id": scenario.building_id,
        "name": scenario.name,
        "description": scenario.description,
        "is_sample": scenario.is_sample,
        "created_at": scenario.created_at,
        "updated_at": scenario.updated_at,
        "config": _api_config(scenario.config()),
    }
    return data


def _api_config(config: dict) -> dict:
    """Stored config -> API shape (engine key names back to schema names)."""
    cfg = dict(config)
    if "speed_distribution" in cfg:
        cfg["speed"] = cfg.pop("speed_distribution")
    if "pre_movement_distribution" in cfg:
        cfg["pre_movement"] = cfg.pop("pre_movement_distribution")
    return cfg
