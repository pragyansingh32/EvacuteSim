"""Advisor endpoints: analyze a run, test a recommended plan."""

from datetime import UTC

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbSession
from app.core.errors import NotFoundError
from app.repositories import buildings as building_repo
from app.repositories import runs as run_repo
from app.repositories import scenarios as scenario_repo
from app.services import advisor_service, run_service
from app.simulation.grid import BuildingGrid

router = APIRouter(prefix="/advisor", tags=["advisor"])


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    recommendation_id: str = Field(min_length=1, max_length=80)


@router.post("/analyze")
def analyze(payload: AnalyzeRequest, db: DbSession) -> dict:
    run = run_repo.get_run(db, payload.run_id)
    if run.status != "completed" or run.result() is None:
        raise HTTPException(
            status_code=409,
            detail="The advisor analyzes completed runs only.",
        )
    report = advisor_service.build_report(run_service.run_metrics(run) or {}, run.config())
    return {"run_id": run.id, **report}


@router.post("/apply")
def apply_recommendation(payload: ApplyRequest, db: DbSession) -> dict:
    """Create a scenario copy with the recommended patch, run the REAL
    simulation, and return before/after metrics for comparison."""
    run = run_repo.get_run(db, payload.run_id)
    if run.status != "completed" or run.result() is None or run.building_id is None:
        raise HTTPException(status_code=409, detail="Only completed runs can be improved.")
    before_metrics = run_service.run_metrics(run) or {}
    report = advisor_service.build_report(before_metrics, run.config())
    recommendation = next(
        (r for r in report["recommendations"] if r["id"] == payload.recommendation_id), None
    )
    if recommendation is None:
        raise NotFoundError(
            f"Recommendation '{payload.recommendation_id}' is not available for run {run.id}."
        )

    new_config = advisor_service.apply_patch(run.config(), recommendation["patch"])

    # Validate against the building before creating anything.
    building = building_repo.get_building(db, run.building_id)
    grid = BuildingGrid.from_dict(building.to_grid_dict())
    from app.services.scenario_service import _validate_config_against_building

    _validate_config_against_building(grid, new_config)

    scenario = scenario_repo.create_scenario(
        db,
        building_id=building.id,
        name=f"Advisor: {recommendation['title']}"[:200],
        description=(
            f"Created by the rule-based advisor from run {run.id} "
            f"({run.name}). Patch: {recommendation['patch_summary']}."
        ),
        config=new_config,
    )

    # Persist + execute the what-if run synchronously (advisor runs are small).
    from datetime import datetime

    engine_cfg = run_service.build_engine_config(new_config)
    new_run = run_repo.create_run(
        db,
        scenario_id=scenario.id,
        building_id=building.id,
        building_snapshot_json=run.building_snapshot_json,
        name=f"Advisor test: {recommendation['title']}"[:200],
        strategy=engine_cfg.strategy,
        seed=engine_cfg.seed,
        status=run_service.RUN_STATUS_PENDING,
        config_json=run_repo.RunModel.encode(run_service.engine_config_to_dict(engine_cfg)),
        started_at=datetime.now(UTC),
    )
    db.commit()
    run_service.execute_run(new_run.id)
    db.expire_all()
    finished = run_repo.get_run(db, new_run.id)

    after_metrics = run_service.run_metrics(finished) or {}
    return {
        "recommendation": recommendation,
        "scenario_id": scenario.id,
        "before": {"run_id": run.id, "metrics": before_metrics},
        "after": {
            "run_id": finished.id,
            "status": finished.status,
            "error": finished.error(),
            "metrics": after_metrics,
        },
    }
