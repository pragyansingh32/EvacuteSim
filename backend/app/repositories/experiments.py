"""Experiment repository."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import ExperimentModel, ExperimentRunModel


def get_experiment(db: Session, experiment_id: int) -> ExperimentModel:
    experiment = db.get(ExperimentModel, experiment_id)
    if experiment is None:
        raise NotFoundError(f"Experiment {experiment_id} not found.")
    return experiment


def list_experiments(db: Session, limit: int = 50) -> list[ExperimentModel]:
    return list(db.scalars(select(ExperimentModel).order_by(ExperimentModel.id.desc()).limit(limit)))


def create_experiment(db: Session, **fields) -> ExperimentModel:  # noqa: ANN003
    experiment = ExperimentModel(**fields)
    db.add(experiment)
    db.flush()
    return experiment


def update_experiment(db: Session, experiment: ExperimentModel, **fields) -> ExperimentModel:  # noqa: ANN003
    for key, value in fields.items():
        setattr(experiment, key, value)
    db.flush()
    return experiment


def create_experiment_run(db: Session, **fields) -> ExperimentRunModel:  # noqa: ANN003
    row = ExperimentRunModel(**fields)
    db.add(row)
    db.flush()
    return row


def list_experiment_runs(db: Session, experiment_id: int) -> list[ExperimentRunModel]:
    return list(
        db.scalars(
            select(ExperimentRunModel)
            .where(ExperimentRunModel.experiment_id == experiment_id)
            .order_by(ExperimentRunModel.id)
        )
    )


def get_experiment_run(db: Session, experiment_run_id: int) -> ExperimentRunModel:
    row = db.get(ExperimentRunModel, experiment_run_id)
    if row is None:
        raise NotFoundError(f"Experiment run {experiment_run_id} not found.")
    return row
