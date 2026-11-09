"""Experiment service: parameter sweeps over a base scenario.

An experiment is a cartesian product of sweep values applied to dot-paths of
the scenario config, repeated once per configured seed. Every combination
produces a real simulation run stored in `runs`, linked from `experiment_runs`
with its sweep values and headline metrics. Individual run failures are
recorded; they do not abort the whole experiment.
"""

import copy
import itertools
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.db.session import session_scope
from app.repositories import buildings as building_repo
from app.repositories import experiments as experiment_repo
from app.repositories import runs as run_repo
from app.repositories import scenarios as scenario_repo
from app.services import run_service

logger = logging.getLogger(__name__)

EXPERIMENT_STATUS_PENDING = "pending"
EXPERIMENT_STATUS_RUNNING = "running"
EXPERIMENT_STATUS_COMPLETED = "completed"
EXPERIMENT_STATUS_FAILED = "failed"

EXPERIMENT_METRICS = (
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
)


def _set_by_path(config: dict, path: str, value) -> None:  # noqa: ANN001
    """Set a nested config value by dot-path, e.g. 'pre_movement.max'."""
    parts = path.split(".")
    node = config
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            raise ValidationError(f"Unknown sweep path '{path}'.")
        node = node[part]
    leaf = parts[-1]
    if not isinstance(node, dict) or leaf not in node:
        raise ValidationError(f"Unknown sweep path '{path}'.")
    # Coerce scalars to the existing value's type where sensible.
    current = node[leaf]
    if isinstance(current, bool) and isinstance(value, str):
        node[leaf] = value.lower() == "true"
    elif isinstance(current, int) and not isinstance(current, bool) and isinstance(value, (int, float)):
        node[leaf] = int(value)
    elif isinstance(current, float) and isinstance(value, (int, float)):
        node[leaf] = float(value)
    else:
        node[leaf] = value


def plan_experiment(sweep: dict, seeds: list[int]) -> tuple[list[dict], int]:
    """Expand the sweep into (combinations, total_runs).

    Each combination is {dot.path: value}. Enforces the planned-run cap.
    """
    if not sweep:
        raise ValidationError("Experiment sweep must define at least one parameter.")
    paths = sorted(sweep)
    value_lists = []
    for path in paths:
        values = sweep[path]
        if not isinstance(values, list) or not values:
            raise ValidationError(f"Sweep values for '{path}' must be a non-empty list.")
        value_lists.append(values)
    combos = [dict(zip(paths, values, strict=False)) for values in itertools.product(*value_lists)]
    total = len(combos) * len(seeds)
    if total > settings.max_experiment_runs:
        raise ValidationError(
            f"Experiment would run {total} simulations; the limit is "
            f"{settings.max_experiment_runs}. Reduce the sweep or seeds."
        )
    return combos, total


def create_experiment(db: Session, payload: dict) -> dict:
    scenario = scenario_repo.get_scenario(db, payload["base_scenario_id"])
    combos, total = plan_experiment(payload["sweep"], payload["seeds"])
    # Validate every sweep path against the actual config before persisting.
    for combo in combos:
        probe = copy.deepcopy(scenario.config())
        for path, value in combo.items():
            _set_by_path(probe, path, value)
    experiment = experiment_repo.create_experiment(
        db,
        name=payload["name"],
        description=payload.get("description", ""),
        base_scenario_id=scenario.id,
        sweep_json=scenario_repo.ScenarioModel.encode(payload["sweep"]),
        status=EXPERIMENT_STATUS_PENDING,
        total_planned=total,
    )
    return {"experiment": experiment, "combinations": combos, "seeds": list(payload["seeds"])}


def execute_experiment(experiment_id: int, combinations: list[dict], seeds: list[int]) -> None:
    """Run all combinations; safe to call from a worker thread."""
    with session_scope() as db:
        experiment = experiment_repo.get_experiment(db, experiment_id)
        scenario = scenario_repo.get_scenario(db, experiment.base_scenario_id)
        building = building_repo.get_building(db, scenario.building_id)
        base_config = copy.deepcopy(scenario.config())
        base_config["scenario_id"] = scenario.id  # used by _register_run
        snapshot = building.to_grid_dict()
        experiment_repo.update_experiment(db, experiment, status=EXPERIMENT_STATUS_RUNNING)
        experiment_name = experiment.name

    try:
        for combo in combinations:
            config = copy.deepcopy(base_config)
            for path, value in combo.items():
                _set_by_path(config, path, value)
            for seed in seeds:
                config["seed"] = int(seed)
                label = f"{experiment_name} [{_combo_label(combo)} seed={seed}]"
                run_id = _register_run(config, snapshot, label)
                run_service.execute_run(run_id)
                metrics = _headline_metrics(run_id)
                with session_scope() as db:
                    experiment_repo.create_experiment_run(
                        db,
                        experiment_id=experiment_id,
                        run_id=run_id,
                        sweep_values_json=run_repo.RunModel.encode(combo),
                        seed=int(seed),
                        metrics_json=run_repo.RunModel.encode(metrics),
                    )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Experiment %s failed", experiment_id)
        with session_scope() as db:
            experiment_repo.update_experiment(
                db,
                experiment_repo.get_experiment(db, experiment_id),
                status=EXPERIMENT_STATUS_FAILED,
                finished_at=datetime.now(UTC),
                error_json=run_repo.RunModel.encode(
                    {"code": type(exc).__name__, "message": str(exc)}
                ),
            )
        return

    with session_scope() as db:
        experiment_repo.update_experiment(
            db,
            experiment_repo.get_experiment(db, experiment_id),
            status=EXPERIMENT_STATUS_COMPLETED,
            finished_at=datetime.now(UTC),
        )


def _register_run(config: dict, snapshot: dict, name: str) -> int:
    """Persist a pending run row for one experiment combination."""
    engine_cfg = run_service.build_engine_config(config)
    with session_scope() as db:
        scenario = scenario_repo.get_scenario(db, config["scenario_id"])
        run = run_repo.create_run(
            db,
            scenario_id=scenario.id,
            building_id=scenario.building_id,
            building_snapshot_json=run_repo.RunModel.encode(snapshot),
            name=name,
            strategy=engine_cfg.strategy,
            seed=engine_cfg.seed,
            status=run_service.RUN_STATUS_PENDING,
            config_json=run_repo.RunModel.encode(run_service.engine_config_to_dict(engine_cfg)),
        )
        return run.id


def _headline_metrics(run_id: int) -> dict:
    with session_scope() as db:
        run = run_repo.get_run(db, run_id)
        metrics = run_service.run_metrics(run) or {}
    out = {key: metrics.get(key) for key in EXPERIMENT_METRICS}
    if out.get("total_occupants") and out.get("evacuated_count") is not None:
        out["evacuated_pct"] = round(
            100.0 * out["evacuated_count"] / out["total_occupants"], 2
        )
    return out


def _combo_label(combo: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(combo.items()))


def submit_experiment(experiment_id: int, combinations: list[dict], seeds: list[int]) -> None:
    run_service.EXECUTOR.submit(execute_experiment, experiment_id, combinations, seeds)
