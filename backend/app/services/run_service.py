"""Run service: create, execute (sync or background), and serialize runs.

Execution model: POST /runs persists a `pending` run, then either executes it
synchronously (small runs, tests) or submits it to a small thread pool. The
engine runs *outside* any open transaction; only the final result write happens
in a short transaction. A failed engine execution records status=failed with
the error message — it can never fabricate a successful result.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.db.session import session_scope
from app.models import RunModel
from app.repositories import buildings as building_repo
from app.repositories import runs as run_repo
from app.repositories import scenarios as scenario_repo
from app.simulation.disasters import DisasterSpec
from app.simulation.engine import EngineConfig, EvacuationEngine
from app.simulation.grid import BuildingGrid

logger = logging.getLogger(__name__)

EXECUTOR = ThreadPoolExecutor(
    max_workers=settings.run_workers, thread_name_prefix="evacuatesim-run"
)

RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"


def _read_disasters(config: dict) -> list[dict]:
    """Read disaster specs from any config format into a normalized list."""
    # New format: disasters is a list of dicts
    if "disasters" in config and isinstance(config["disasters"], list):
        return [
            {
                "type": d.get("type", "none"),
                "intensity": float(d.get("intensity", 0.0)),
                "origin": tuple(d["origin"]) if d.get("origin") else None,
            }
            for d in config["disasters"]
            if d.get("type", "none") != "none"
        ]
    # Engine round-trip: disaster_type at top level
    if config.get("disaster_type", "none") != "none":
        origin = config.get("disaster_origin")
        return [{
            "type": config["disaster_type"],
            "intensity": float(config.get("disaster_intensity", 0.0)),
            "origin": tuple(origin) if origin else None,
        }]
    # Old scenario format: single disaster object
    disaster = config.get("disaster") or {}
    if isinstance(disaster, dict) and disaster.get("type", "none") != "none":
        origin = disaster.get("origin")
        return [{
            "type": disaster["type"],
            "intensity": float(disaster.get("intensity", 0.0)),
            "origin": tuple(origin) if origin else None,
        }]
    return []


def build_engine_config(config: dict) -> EngineConfig:
    """Stored/plain scenario config dict -> engine EngineConfig (validating)."""
    try:
        return EngineConfig(
            strategy=config["strategy"],
            zone_populations=dict(config["zone_populations"]),
            speed_distribution=dict(config["speed_distribution"]),
            pre_movement_distribution=dict(config["pre_movement_distribution"]),
            blocked_cells={tuple(c) for c in config.get("blocked_cells", [])},
            blocked_exit_ids=set(config.get("blocked_exit_ids", [])),
            exit_capacity_overrides=dict(config.get("exit_capacity_overrides", {})),
            disasters=[
                DisasterSpec(type=d["type"], intensity=d["intensity"], origin=d["origin"])
                for d in _read_disasters(config)
            ],
            seed=int(config["seed"]),
            max_duration_s=float(config["max_duration_s"]),
            dt_s=float(config["dt_s"]),
            frame_interval_s=float(config.get("frame_interval_s", settings.default_frame_interval_s)),
            record_frames=bool(config.get("record_frames", True)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"Malformed scenario configuration: {exc}") from exc


def engine_config_to_dict(cfg: EngineConfig) -> dict:
    data = asdict(cfg)
    data["blocked_cells"] = sorted([list(c) for c in cfg.blocked_cells])
    data["blocked_exit_ids"] = sorted(cfg.blocked_exit_ids)
    data["disasters"] = [
        {
            "type": d.type,
            "intensity": d.intensity,
            "origin": list(d.origin) if d.origin else None,
        }
        for d in cfg.disasters
    ]
    return data


def apply_overrides(config: dict, overrides) -> dict:  # noqa: ANN001
    merged = dict(config)
    if overrides is None:
        return merged
    if getattr(overrides, "seed", None) is not None:
        merged["seed"] = int(overrides.seed)
    if getattr(overrides, "strategy", None):
        merged["strategy"] = overrides.strategy
    return merged


def create_run(
    db: Session,
    scenario_id: int,
    name: str | None,
    overrides=None,  # noqa: ANN001
) -> RunModel:
    scenario = scenario_repo.get_scenario(db, scenario_id)
    building = building_repo.get_building(db, scenario.building_id)
    snapshot = building.to_grid_dict()
    # Validate the building still loads before scheduling the run.
    BuildingGrid.from_dict(snapshot)

    config = apply_overrides(scenario.config(), overrides)
    engine_cfg = build_engine_config(config)  # raises ValidationError early
    run = run_repo.create_run(
        db,
        scenario_id=scenario.id,
        building_id=building.id,
        building_snapshot_json=RunModel.encode(snapshot),
        name=name or scenario.name,
        strategy=engine_cfg.strategy,
        seed=engine_cfg.seed,
        status=RUN_STATUS_PENDING,
        config_json=RunModel.encode(engine_config_to_dict(engine_cfg)),
    )
    return run


def execute_run(run_id: int) -> None:
    """Execute one run in its own sessions; safe to call from a thread."""
    from datetime import datetime

    with session_scope() as db:
        run = run_repo.get_run(db, run_id)
        if run.status != RUN_STATUS_PENDING:
            return
        run_repo.update_run(
            db, run, status=RUN_STATUS_RUNNING, started_at=datetime.now(UTC)
        )
        snapshot = run.decode(run.building_snapshot_json)
        config = run.config()

    try:
        grid = BuildingGrid.from_dict(snapshot)
        engine_cfg = build_engine_config(config)
        result = EvacuationEngine(grid, engine_cfg).run()
        result_dict = result.to_dict()
    except Exception as exc:  # noqa: BLE001 - record honestly, re-raise nothing
        logger.exception("Run %s failed", run_id)
        with session_scope() as db:
            failed = run_repo.get_run(db, run_id)
            run_repo.update_run(
                db,
                failed,
                status=RUN_STATUS_FAILED,
                finished_at=datetime.now(UTC),
                error_json=RunModel.encode({"code": type(exc).__name__, "message": str(exc)}),
            )
        return

    with session_scope() as db:
        done = run_repo.get_run(db, run_id)
        run_repo.update_run(
            db,
            done,
            status=RUN_STATUS_COMPLETED,
            finished_at=datetime.now(UTC),
            result_json=RunModel.encode(result_dict),
        )


def submit_run(run_id: int) -> None:
    EXECUTOR.submit(execute_run, run_id)


def run_metrics(run: RunModel) -> dict | None:
    """Extract the headline metrics document from a stored result."""
    result = run.result()
    if result is None:
        return None
    queue = result.get("queue", {})
    return {
        "engine_status": result.get("status"),
        "sim_time_s": result.get("sim_time_s"),
        "steps": result.get("steps"),
        "total_occupants": result.get("total_occupants"),
        "evacuated_count": result.get("evacuated_count"),
        "unreachable_count": result.get("unreachable_count"),
        "incapacitated_count": result.get("incapacitated_count"),
        "disasters": result.get("disasters") or [],
        "remaining_count": result.get("remaining_count"),
        "t50_s": result.get("t50_s"),
        "t90_s": result.get("t90_s"),
        "t95_s": result.get("t95_s"),
        "mean_evacuation_time_s": result.get("mean_evacuation_time_s"),
        "max_evacuation_time_s": result.get("max_evacuation_time_s"),
        "queue_total_s": queue.get("total_s"),
        "queue_mean_s": queue.get("mean_s"),
        "queue_max_s": queue.get("max_s"),
        "fallback_count": result.get("fallback_count"),
        "exit_stats": result.get("exit_stats", []),
        "congestion": result.get("congestion", {}),
        "warnings": result.get("warnings", []),
    }


def run_detail(run: RunModel, include_building: bool = False, include_frames: bool = True) -> dict:
    result = run.result()
    detail = {
        "id": run.id,
        "scenario_id": run.scenario_id,
        "building_id": run.building_id,
        "name": run.name,
        "strategy": run.strategy,
        "seed": run.seed,
        "status": run.status,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "config": run.config(),
        "metrics": run_metrics(run),
        "error": run.error(),
        "building_snapshot": run.decode(run.building_snapshot_json) if include_building else None,
        "timeline": (result or {}).get("timeline", []) if include_frames else [],
        "frames": (result or {}).get("frames", []) if include_frames else [],
    }
    return detail


def wait_for_run(run_id: int, timeout_s: float = 120.0) -> RunModel:
    """Block until a run leaves pending/running (used by tests and wait=true)."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with session_scope() as db:
            run = run_repo.get_run(db, run_id)
            if run.status not in (RUN_STATUS_PENDING, RUN_STATUS_RUNNING):
                return run
        time.sleep(0.05)
    raise TimeoutError(f"Run {run_id} did not finish within {timeout_s}s.")
