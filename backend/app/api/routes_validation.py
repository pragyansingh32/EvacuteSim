"""System accuracy endpoints: the known-answer validation battery."""

from fastapi import APIRouter

from app.services import validation_service

router = APIRouter(prefix="/validation", tags=["validation"])


@router.get("/battery")
def run_validation_battery() -> dict:
    """Run the known-answer battery live and report per-case verdicts.

    Designs with analytically known outcomes (adequate rooms pass; sealed
    rooms, undersized doors, and too-long horizons fail) are executed through
    the real engine, and the system's classification is compared with the
    expected outcome. Runs in well under a second.
    """
    return validation_service.run_battery()
