"""Raster floor-plan import (PNG/JPEG/...).

Algorithm (deliberately simple and explainable):

1. Decode the image with Pillow, convert to 8-bit grayscale, and binarize at
   FULL resolution (dark vs light at the threshold) — binarizing first
   preserves thin wall lines that mean-based downscaling would erase.
2. Downscale the binary image to the target grid with a BOX filter, so every
   output pixel is the fraction of dark pixels in that cell's area.
3. A cell becomes a wall when at least WALL_PIXEL_DENSITY of its pixels are
   wall-colored (dark for typical plans, bright when `invert` is set for
   light-on-dark plans).

This is a raster approximation: text, hatching, furniture, and scan noise
convert to wall cells too. The result is a draft for manual cleanup, not a
verified model. See docs/KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import io

from app.core.config import settings
from app.planimport.common import ImportParams, ImportResult, finish_grid

# Fraction of a cell's pixels that must be wall-colored to count as wall.
# Lower values keep thinner lines but admit more noise; the editor is the
# place to clean the remainder.
WALL_PIXEL_DENSITY = 0.3


def import_from_image(data: bytes, params: ImportParams, name: str) -> ImportResult:
    """Convert plan image bytes into an ImportResult (raises ValueError)."""
    params.validated()
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow is a hard dependency
        raise ValueError("Image support is unavailable (Pillow not installed).") from exc

    # Decompression guard: refuse absurdly large images before decoding.
    Image.MAX_IMAGE_PIXELS = settings.import_max_pixels

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise ValueError(f"Could not decode the image file: {exc}") from exc

    src_w, src_h = image.size
    if src_w < 16 or src_h < 16:
        raise ValueError("Image is too small to be a floor plan (minimum 16x16 pixels).")

    grayscale = image.convert("L")

    # Binarize at full resolution first (keeps thin wall lines that mean-based
    # downscaling would erase).
    binary = grayscale.point(lambda v: 0 if v < params.threshold else 255)

    # Crop to the drawn content: plans scanned with white margins would
    # otherwise convert the margin into a phantom floor ring OUTSIDE the
    # building envelope, detaching any exit placed there from the interior.
    content_bbox = binary.point(lambda v: 255 - v).getbbox()
    if content_bbox is not None:
        pad = 2
        left = max(0, content_bbox[0] - pad)
        top = max(0, content_bbox[1] - pad)
        right = min(binary.width, content_bbox[2] + pad)
        bottom = min(binary.height, content_bbox[3] + pad)
        if (right - left) >= 8 and (bottom - top) >= 8:
            binary = binary.crop((left, top, right, bottom))
            src_w, src_h = binary.size

    # Fit the plan into the grid: the larger dimension maps to target_width
    # cells; the other follows the aspect ratio (>= 8 cells).
    if src_w >= src_h:
        grid_w = params.target_width
        grid_h = max(8, round(src_h / src_w * params.target_width))
    else:
        grid_h = params.target_width
        grid_w = max(8, round(src_w / src_h * params.target_width))
    grid_w = min(grid_w, settings.max_grid_width)
    grid_h = min(grid_h, settings.max_grid_height)

    # Box-filter the binary image: each output pixel is the fraction of dark
    # pixels in that cell's area.
    small = binary.resize((grid_w, grid_h), Image.BOX)
    pixels = small.tobytes()  # 0 = fully dark cell, 255 = fully light cell

    dark_cutoff = 255 * (1.0 - WALL_PIXEL_DENSITY)
    bright_cutoff = 255 * WALL_PIXEL_DENSITY
    walls: set[tuple[int, int]] = set()
    for y in range(grid_h):
        for x in range(grid_w):
            lum = pixels[y * grid_w + x]
            if params.invert:
                is_wall = lum >= bright_cutoff  # light walls on dark plan
            else:
                is_wall = lum <= dark_cutoff  # dark walls on light plan
            if is_wall:
                walls.add((x, y))

    semantics = None
    if params.interpret:
        from app.planimport.semantics import analyze

        semantics = analyze(walls, grid_w, grid_h, cell_size_m=round(
            params.real_width_m / params.target_width, 3), occupancy_density=params.occupancy_density)

    return finish_grid(
        walls,
        grid_w,
        grid_h,
        params,
        source_label=name,
        source_stats={
            "source_type": "image",
            "source_pixels": [src_w, src_h],
            "threshold": params.threshold,
            "invert": params.invert,
        },
        semantics=semantics,
    )
