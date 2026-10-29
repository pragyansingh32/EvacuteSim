"""Scenario repository."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import ScenarioModel


def get_scenario(db: Session, scenario_id: int) -> ScenarioModel:
    scenario = db.get(ScenarioModel, scenario_id)
    if scenario is None:
        raise NotFoundError(f"Scenario {scenario_id} not found.")
    return scenario


def list_scenarios(db: Session, building_id: int | None = None) -> list[ScenarioModel]:
    stmt = select(ScenarioModel).order_by(ScenarioModel.id)
    if building_id is not None:
        stmt = stmt.where(ScenarioModel.building_id == building_id)
    return list(db.scalars(stmt))


def create_scenario(
    db: Session,
    building_id: int,
    name: str,
    description: str,
    config: dict,
    is_sample: bool = False,
) -> ScenarioModel:
    scenario = ScenarioModel(
        building_id=building_id,
        name=name,
        description=description,
        config_json=ScenarioModel.encode(config),
        is_sample=is_sample,
    )
    db.add(scenario)
    db.flush()
    return scenario


def update_scenario(
    db: Session,
    scenario: ScenarioModel,
    name: str | None,
    description: str | None,
    config: dict | None,
) -> ScenarioModel:
    if name is not None:
        scenario.name = name
    if description is not None:
        scenario.description = description
    if config is not None:
        scenario.config_json = ScenarioModel.encode(config)
    db.flush()
    return scenario


def delete_scenario(db: Session, scenario_id: int) -> None:
    scenario = get_scenario(db, scenario_id)
    db.delete(scenario)
    db.flush()
