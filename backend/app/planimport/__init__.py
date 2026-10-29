"""Plan import: convert existing building plans (raster images or ASCII DXF)
into an EvacuateSim grid draft.

The conversion produces WALLS ONLY. It cannot know where doors, exits, or
functional zones are — that semantics is added by the user in the editor.
Every import result therefore carries explicit warnings stating this.
"""

from app.planimport.common import ImportDraft, ImportParams, ImportResult
from app.planimport.dxf_import import import_from_dxf
from app.planimport.drawio_import import import_from_drawio
from app.planimport.image_import import import_from_image

__all__ = [
    "ImportParams",
    "ImportDraft",
    "ImportResult",
    "import_from_image",
    "import_from_dxf",
    "import_from_drawio",
]
