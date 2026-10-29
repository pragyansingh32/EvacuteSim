"""Experiment endpoints: parameter sweeps for controlled research."""

import csv
import io

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession
from app.repositories import experiments as experiment_repo
from app.schemas import ExperimentCreate, ExperimentRead, ExperimentResults
from app.services import experiment_service

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentRead])
def list_experiments(db: DbSession) -> list:
    return experiment_repo.list_experiments(db)


@router.post("", response_model=ExperimentRead, status_code=201)
def create_experiment(payload: ExperimentCreate, db: DbSession) -> dict:
    planned = experiment_service.create_experiment(db, payload.model_dump())
    experiment = planned["experiment"]
    db.commit()
    if payload.wait:
        experiment_service.execute_experiment(
            experiment.id, planned["combinations"], planned["seeds"]
        )
        db.expire_all()
        return _read(experiment_repo.get_experiment(db, experiment.id))
    experiment_service.submit_experiment(
        experiment.id, planned["combinations"], planned["seeds"]
    )
    return _read(experiment)


@router.get("/{experiment_id}", response_model=ExperimentRead)
def get_experiment(experiment_id: int, db: DbSession) -> dict:
    return _read(experiment_repo.get_experiment(db, experiment_id))


@router.get("/{experiment_id}/results", response_model=ExperimentResults)
def get_results(experiment_id: int, db: DbSession) -> dict:
    experiment = experiment_repo.get_experiment(db, experiment_id)
    rows = []
    for exp_run in experiment_repo.list_experiment_runs(db, experiment.id):
        rows.append(
            {
                "experiment_run_id": exp_run.id,
                "run_id": exp_run.run_id,
                "sweep_values": exp_run.decode(exp_run.sweep_values_json),
                "seed": exp_run.seed,
                "metrics": exp_run.decode(exp_run.metrics_json),
            }
        )
    return {
        "experiment": _read(experiment),
        "sweep_definition": experiment.decode(experiment.sweep_json),
        "rows": rows,
    }


@router.get("/{experiment_id}/export")
def export_csv(experiment_id: int, db: DbSession) -> Response:
    """Export the experiment's result table as CSV for external analysis."""
    experiment = experiment_repo.get_experiment(db, experiment_id)
    exp_runs = experiment_repo.list_experiment_runs(db, experiment.id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    metric_keys = [
        "engine_status",
        "sim_time_s",
        "evacuated_count",
        "total_occupants",
        "remaining_count",
        "unreachable_count",
        "t50_s",
        "t90_s",
        "t95_s",
        "max_evacuation_time_s",
        "queue_mean_s",
        "evacuated_pct",
    ]
    header = ["experiment_run_id", "run_id", "seed", "sweep_values"] + metric_keys
    writer.writerow(header)
    for exp_run in exp_runs:
        metrics = exp_run.decode(exp_run.metrics_json) or {}
        sweep = exp_run.decode(exp_run.sweep_values_json) or {}
        writer.writerow(
            [exp_run.id, exp_run.run_id, exp_run.seed, _csv_safe(sweep)]
            + [metrics.get(k, "") for k in metric_keys]
        )
    buffer.seek(0)
    filename = f"experiment_{experiment.id}_results.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _csv_safe(value: dict) -> str:  # noqa: ANN001
    import json

    return json.dumps(value, sort_keys=True)


def _read(experiment) -> dict:  # noqa: ANN001
    data = {
        "id": experiment.id,
        "name": experiment.name,
        "description": experiment.description,
        "base_scenario_id": experiment.base_scenario_id,
        "status": experiment.status,
        "total_planned": experiment.total_planned,
        "created_at": experiment.created_at,
        "finished_at": experiment.finished_at,
        "error": experiment.error_json and experiment.decode(experiment.error_json),
    }
    return data
