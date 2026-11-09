"""EvacuateSim API entry point.

Run locally:  uvicorn app.main:app --reload --port 8000  (from backend/)
Interactive API docs: http://127.0.0.1:8000/docs
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import (
    routes_advisor,
    routes_buildings,
    routes_experiments,
    routes_health,
    routes_import,
    routes_runs,
    routes_scenarios,
    routes_snapshots,
    routes_validation,
)
from app.core.config import settings
from app.core.errors import (
    EvacuateSimError,
    evacuatesim_error_handler,
    request_validation_error_handler,
    unhandled_error_handler,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.services.sample_data import seed_samples_once

    seed_samples_once()
    logger.info("EvacuateSim backend ready (db=%s)", settings.database_url)
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "EvacuateSim: an explainable, uncertainty-aware emergency evacuation "
        "simulation and scenario optimization platform. Educational/research "
        "tool - NOT a certified fire-safety system; outputs are model-based "
        "simulations, not safety predictions."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# --- consistent error responses -------------------------------------------
app.add_exception_handler(EvacuateSimError, evacuatesim_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)
from fastapi.exceptions import RequestValidationError  # noqa: E402

app.add_exception_handler(RequestValidationError, request_validation_error_handler)

# --- routers ----------------------------------------------------------------
API = f"/api/{settings.api_version}"
app.include_router(routes_health.router, prefix=API)
app.include_router(routes_buildings.router, prefix=API)
app.include_router(routes_scenarios.router, prefix=API)
app.include_router(routes_runs.router, prefix=API)
app.include_router(routes_experiments.router, prefix=API)
app.include_router(routes_import.router, prefix=API)
app.include_router(routes_validation.router, prefix=API)
app.include_router(routes_advisor.router, prefix=API)
app.include_router(routes_snapshots.router, prefix=API)


# Root: serve the built frontend when present, otherwise a small JSON index.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        """Serve static files and fall back to index.html for SPA routes.

        Registered after the API routers, so /api/*, /docs, and /openapi.json
        keep matching first. Guarded against path traversal.
        """
        if full_path:
            candidate = (_FRONTEND_DIST / full_path).resolve()
            if candidate.is_file() and str(candidate).startswith(str(_FRONTEND_DIST)):
                return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")

    logger.info("Serving frontend from %s", _FRONTEND_DIST)
else:

    @app.get("/")
    def root() -> dict:
        return {
            "name": settings.app_name,
            "api": API,
            "docs": "/docs",
            "disclaimer": (
                "Educational/research simulation tool. Outcomes depend on model "
                "assumptions and are not certified safety predictions."
            ),
        }
