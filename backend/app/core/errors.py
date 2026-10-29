"""Consistent application errors and error responses.

The API layer converts these into HTTP responses; the simulation layer raises
them directly. Stack traces are never exposed to clients.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class EvacuateSimError(Exception):
    """Base class for expected, user-facing errors."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(EvacuateSimError):
    status_code = 422
    code = "validation_error"


class NotFoundError(EvacuateSimError):
    status_code = 404
    code = "not_found"


class ConflictError(EvacuateSimError):
    status_code = 409
    code = "conflict"


class SimulationError(EvacuateSimError):
    status_code = 422
    code = "simulation_error"


async def evacuatesim_error_handler(_request: Request, exc: EvacuateSimError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def request_validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "request_validation_error",
                "message": "The request body failed validation.",
                "details": [
                    {"loc": list(err.get("loc", [])), "msg": err.get("msg")}
                    for err in exc.errors()[:10]
                ],
            }
        },
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    # Deliberately opaque: internal details go to the server log, not the client.
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected internal error occurred. See server logs.",
            }
        },
    )
