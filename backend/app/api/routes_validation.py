"""System accuracy endpoints: the known-answer validation battery."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.api.deps import DbSession
from app.services import validation_service

router = APIRouter(prefix="/validation", tags=["validation"])


class DisasterReadinessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: int


@router.post("/disaster-readiness")
def disaster_readiness(payload: DisasterReadinessRequest, db: DbSession) -> dict:
    """Test a scenario against all 6 disaster types at 3 intensity levels
    (18 runs) and report a clear PASS/FAIL verdict for each."""
    from app.repositories import buildings as building_repo
    from app.repositories import runs as run_repo
    from app.repositories import scenarios as scenario_repo
    from app.services import run_service

    scenario = scenario_repo.get_scenario(db, payload.scenario_id)
    building = building_repo.get_building(db, scenario.building_id)
    snapshot = building.to_grid_dict()
    base_config = scenario.config()
    if not base_config.get("zone_populations"):
        raise HTTPException(status_code=422, detail="Scenario has no population.")

    disaster_types = ["fire", "earthquake", "stampede", "gas_leak", "flood", "power_outage"]
    intensities = [0.3, 0.6, 0.9]
    rows = []
    passed = 0
    total = 0

    import copy

    for dtype in disaster_types:
        for intensity in intensities:
            config = copy.deepcopy(base_config)
            config["disaster"] = {"type": dtype, "intensity": intensity, "origin": None}
            config["scenario_id"] = scenario.id
            engine_cfg = run_service.build_engine_config(config)
            run = run_repo.create_run(
                db,
                scenario_id=scenario.id,
                building_id=scenario.building_id,
                building_snapshot_json=run_repo.RunModel.encode(snapshot),
                name=f"Readiness: {dtype} @ {intensity:.0%}",
                strategy=engine_cfg.strategy,
                seed=42,
                status=run_service.RUN_STATUS_PENDING,
                config_json=run_repo.RunModel.encode(
                    run_service.engine_config_to_dict(engine_cfg)
                ),
            )
            db.commit()
            run_service.execute_run(run.id)
            db.expire_all()
            finished = run_repo.get_run(db, run.id)
            metrics = run_service.run_metrics(finished) or {}
            total_pop = metrics.get("total_occupants", 0) or 0
            evac = metrics.get("evacuated_count", 0) or 0
            incap = metrics.get("incapacitated_count", 0) or 0
            reachable = total_pop - (metrics.get("unreachable_count", 0) or 0)
            outcome = "PASSED" if evac >= reachable else "FAILED"
            passed += 1 if outcome == "PASSED" else 0
            total += 1
            rows.append({
                "disaster_type": dtype,
                "intensity": intensity,
                "run_id": run.id,
                "status": finished.status,
                "outcome": outcome,
                "evacuated": evac,
                "total": total_pop,
                "incapacitated": incap,
                "remaining": metrics.get("remaining_count", 0),
                "sim_time_s": metrics.get("sim_time_s"),
            })

    return {
        "scenario_id": payload.scenario_id,
        "scenario_name": scenario.name,
        "rows": rows,
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "readiness_pct": round(100.0 * passed / total, 1) if total else 0.0,
        "notes": [
            "PASSED = all reachable occupants evacuated within the horizon.",
            "FAILED = occupants remained inside or became casualties.",
            "Each cell is a real simulation run; results are stored and reproducible.",
        ],
    }


@router.get("/battery")
def run_validation_battery() -> dict:
    """Run the known-answer battery live and report per-case verdicts.

    Designs with analytically known outcomes (adequate rooms pass; sealed
    rooms, undersized doors, and too-long horizons fail) are executed through
    the real engine, and the system's classification is compared with the
    expected outcome. Runs in well under a second.
    """
    return validation_service.run_battery()
