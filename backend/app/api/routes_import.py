"""Plan import endpoint: convert an uploaded floor plan into a grid draft.

The response is a DRAFT (walls only). The frontend hands it to the building
editor, where the user adds exits and zones and saves through the normal
building API — so layout validation (≥ 1 exit etc.) stays enforced exactly
where it belongs.
"""

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import DbSession  # noqa: F401 - reserved for future persistence
from app.core.config import settings
from app.core.errors import ValidationError
from app.planimport import ImportParams, import_from_drawio, import_from_dxf, import_from_image

router = APIRouter(prefix="/import", tags=["import"])

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}


def _suffix(filename: str | None) -> str:
    import os

    return os.path.splitext(filename or "")[1].lower()


@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    name: str = Form(default="Imported plan"),
    target_width: int = Form(default=60),
    real_width_m: float = Form(default=15.0),
    threshold: int | None = Form(default=None),
    invert: bool = Form(default=False),
    interpret: bool = Form(default=True),
    occupancy_density: float = Form(default=0.25),
    wall_density: float = Form(default=0.3),
) -> dict:
    """Convert an uploaded plan (image or ASCII DXF) into a grid draft.

    Returns `{draft, stats, warnings}`. Raises 422 with a clear message when
    the file cannot be converted.
    """
    max_bytes = settings.max_upload_mb * 1024 * 1024
    suffix = _suffix(file.filename)
    if not suffix:
        raise ValidationError(
            "Could not determine the file type from the filename; use an image "
            "extension (.png/.jpg/...) or .dxf."
        )

    data = await file.read()
    if len(data) == 0:
        raise ValidationError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise ValidationError(
            f"The file is {len(data) / 1024 / 1024:.1f} MB; the limit is "
            f"{settings.max_upload_mb} MB."
        )

    params = ImportParams(
        target_width=target_width,
        real_width_m=real_width_m,
        threshold=threshold,
        invert=invert,
        interpret=interpret,
        occupancy_density=occupancy_density,
        wall_density=wall_density,
    )

    safe_name = (name or "Imported plan").strip()[:200]
    try:
        if suffix == ".dxf":
            result = import_from_dxf(data, params, safe_name)
        elif suffix in (".drawio", ".xml"):
            result = import_from_drawio(data, params, safe_name)
        elif suffix in _IMAGE_EXTENSIONS:
            result = import_from_image(data, params, safe_name)
        else:
            raise ValidationError(
                f"Unsupported file type '{suffix}'. Upload a draw.io diagram "
                "(.drawio/.xml), an image (.png/.jpg/.bmp/.tif/.webp), or an "
                "ASCII DXF (.dxf)."
            )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    suggested = None
    if result.draft.exits and result.draft.zones:
        from app.planimport.common import suggested_scenario

        suggested = suggested_scenario(result.draft, result.zone_populations)
    return {
        "draft": result.draft.to_editor_state(),
        "stats": result.stats,
        "suggested_scenario": suggested,
        "warnings": result.warnings,
    }
