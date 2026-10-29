"""Run endpoints: start simulations, poll status, fetch results, compare."""

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession
from app.repositories import runs as run_repo
from app.schemas import CompareRequest, ComparisonResponse, RunCreate, RunDetail, RunSummary
from app.services import comparison_service, run_service

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=dict, status_code=201)
def create_run(payload: RunCreate, db: DbSession) -> dict:
    run = run_service.create_run(db, payload.scenario_id, payload.name, payload.overrides)
    db.commit()
    if payload.wait:
        run_service.execute_run(run.id)
        db.expire_all()
        run = run_repo.get_run(db, run.id)
        return {"run": run_service.run_detail(run, include_frames=True)}
    run_service.submit_run(run.id)
    detail = run_service.run_detail(run, include_frames=False)
    return {"run": detail}


@router.get("/runs", response_model=list[RunSummary])
def list_runs(db: DbSession, scenario_id: int | None = None, limit: int = Query(50, le=200)) -> list:
    return run_repo.list_runs(db, scenario_id=scenario_id, limit=limit)


@router.get("/runs/recent", response_model=list[RunSummary])
def recent_runs(db: DbSession, limit: int = Query(10, le=50)) -> list:
    return run_repo.list_recent_runs(db, limit=limit)


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(
    run_id: int,
    db: DbSession,
    include_building: bool = False,
    include_frames: bool = Query(True, description="Include timeline/frames in the response."),
) -> dict:
    run = run_repo.get_run(db, run_id)
    if run.status in ("pending", "running"):
        # Report the live status; details come when the run finishes.
        return run_service.run_detail(run, include_building=include_building, include_frames=False)
    return run_service.run_detail(
        run, include_building=include_building, include_frames=include_frames
    )


@router.post("/runs/{run_id}/reproduce", response_model=dict)
def reproduce_run(run_id: int, db: DbSession) -> dict:
    """Re-run a stored run with its exact recorded configuration and seed."""
    run = run_repo.get_run(db, run_id)
    if run.status == "failed" and not run.config():
        raise HTTPException(status_code=409, detail="Failed run has no stored configuration.")

    config = dict(run.config())
    config["scenario_id"] = run.scenario_id
    engine_cfg = run_service.build_engine_config(config)
    new_run = run_repo.create_run(
        db,
        scenario_id=run.scenario_id,
        building_id=run.building_id,
        building_snapshot_json=run.building_snapshot_json,
        name=f"Reproduction of run {run.id}",
        strategy=engine_cfg.strategy,
        seed=engine_cfg.seed,
        status="pending",
        config_json=run.config_json,
    )
    db.commit()
    run_service.execute_run(new_run.id)
    db.expire_all()
    return {"run": run_service.run_detail(run_repo.get_run(db, new_run.id), include_frames=False)}


@router.post("/compare", response_model=ComparisonResponse)
def compare(payload: CompareRequest, db: DbSession) -> dict:
    return comparison_service.compare_runs(db, payload.run_ids)
