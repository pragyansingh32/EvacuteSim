"""Run repository."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import RunModel


def get_run(db: Session, run_id: int) -> RunModel:
    run = db.get(RunModel, run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} not found.")
    return run


def list_runs(db: Session, scenario_id: int | None = None, limit: int = 200) -> list[RunModel]:
    stmt = select(RunModel).order_by(RunModel.id.desc()).limit(limit)
    if scenario_id is not None:
        stmt = stmt.where(RunModel.scenario_id == scenario_id)
    return list(db.scalars(stmt))


def list_recent_runs(db: Session, limit: int = 10) -> list[RunModel]:
    return list(db.scalars(select(RunModel).order_by(RunModel.id.desc()).limit(limit)))


def create_run(db: Session, **fields) -> RunModel:  # noqa: ANN003
    run = RunModel(**fields)
    db.add(run)
    db.flush()
    return run


def update_run(db: Session, run: RunModel, **fields) -> RunModel:  # noqa: ANN003
    for key, value in fields.items():
        setattr(run, key, value)
    db.flush()
    return run
