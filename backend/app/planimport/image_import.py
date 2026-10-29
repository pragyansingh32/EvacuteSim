"""Raster floor-plan import (PNG/JPEG/...).

Algorithm (deliberately simple and explainable):

1. Decode the image with Pillow, convert to 8-bit grayscale, and pick the
   ink/paper threshold — either the user's value or automatically via Otsu's
   method (maximizes between-class variance in the grayscale histogram).
2. Binarize at FULL resolution (keeps thin wall lines that mean-based
   downscaling would erase), then crop to the drawn content (removes scanner
   margins that would become phantom floor rings).
3. Box-filter the binary image to the target grid: every output pixel is the
   EXACT fraction of ink in that cell's source area.
4. A cell is a wall when at least `wall_density` of its pixels are ink (dark
   for typical plans; inverted for light-on-dark plans).

Fidelity is reported: `ink_captured_pct` says what fraction of the plan's ink
landed inside detected wall cells, and `crop_box` lets the UI overlay the
converted grid on the original image for visual verification.
"""

from __future__ import annotations

import io

from app.core.config import settings
from app.planimport.common import ImportParams, ImportResult, finish_grid


def otsu_threshold(histogram: list[int]) -> int:
    """Otsu 1979: the threshold maximizing between-class variance — the
    standard automatic ink/paper separator for scanned plans."""
    total = sum(histogram)
    if total == 0:
        return 128
    sum_all = sum(i * h for i, h in enumerate(histogram))
    sum_b = 0
    weight_b = 0
    best_threshold = 128
    best_variance = -1.0
    for t in range(256):
        weight_b += histogram[t]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += t * histogram[t]
        mean_b = sum_b / weight_b
        mean_f = (sum_all - sum_b) / weight_f
        variance = weight_b * weight_f * (mean_b - mean_f) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = t
    # `best_threshold` is the last dark-class bin; the binary cut is strict
    # (v < threshold), so advance past it to include the dark class itself.
    return min(255, best_threshold + 1)


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

    # Threshold: user-provided, or automatic via Otsu's method.
    if params.threshold is None:
        threshold = otsu_threshold(grayscale.histogram())
    else:
        threshold = params.threshold

    # Binarize at full resolution first (keeps thin wall lines).
    binary = grayscale.point(lambda v: 0 if v < threshold else 255)

    # Crop to the drawn content: scanner margins would otherwise become a
    # phantom floor ring outside the building envelope.
    content_bbox = binary.point(lambda v: 255 - v).getbbox()
    crop_box = [0, 0, src_w, src_h]
    if content_bbox is not None:
        pad = 2
        left = max(0, content_bbox[0] - pad)
        top = max(0, content_bbox[1] - pad)
        right = min(binary.width, content_bbox[2] + pad)
        bottom = min(binary.height, content_bbox[3] + pad)
        if (right - left) >= 8 and (bottom - top) >= 8:
            binary = binary.crop((left, top, right, bottom))
            crop_box = [left, top, right, bottom]
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

    # Box-filter the binary image: each output pixel is the exact fraction of
    # ink in that cell's source area (0 = empty, 255 = fully inked).
    small = binary.resize((grid_w, grid_h), Image.BOX)
    pixels = small.tobytes()

    dark_cutoff = 255 * (1.0 - params.wall_density)
    bright_cutoff = 255 * params.wall_density
    walls: set[tuple[int, int]] = set()
    total_ink = 0
    captured_ink = 0
    for y in range(grid_h):
        for x in range(grid_w):
            lum = pixels[y * grid_w + x]
            ink = 255 - lum
            total_ink += ink
            if params.invert:
                is_wall = lum >= bright_cutoff  # light walls on dark plan
            else:
                is_wall = lum <= dark_cutoff  # dark walls on light plan
            if is_wall:
                walls.add((x, y))
                captured_ink += ink

    semantics = None
    if params.interpret:
        from app.planimport.semantics import analyze

        cell_size = round(params.real_width_m / params.target_width, 3)
        semantics = analyze(
            walls,
            grid_w,
            grid_h,
            cell_size_m=cell_size,
            occupancy_density=params.occupancy_density,
        )

    return finish_grid(
        walls,
        grid_w,
        grid_h,
        params,
        source_label=name,
        source_stats={
            "source_type": "image",
            "source_pixels": [src_w, src_h],
            "threshold": threshold,
            "threshold_auto": params.threshold is None,
            "wall_density": params.wall_density,
            "invert": params.invert,
            "crop_box": crop_box,
            "ink_captured_pct": round(100.0 * captured_ink / total_ink, 1) if total_ink else 0.0,
        },
        semantics=semantics,
    )
