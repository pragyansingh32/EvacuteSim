"""ASCII DXF (CAD) floor-plan import.

Parses LINE, LWPOLYLINE, and CIRCLE entities from an ASCII DXF file (the
format AutoCAD-compatible tools export by default when saving ASCII DXF),
converts the geometry into line segments, and rasterizes them onto the grid
with Bresenham's line algorithm — wall lines become 1-cell-thick walls.

Scope and limits (documented in KNOWN_LIMITATIONS.md):

- ASCII DXF only; binary DXF is not supported.
- Only LINE / LWPOLYLINE / CIRCLE entities are read. POLYLINE/VERTEX chains,
  INSERTs (block references), HATCH, TEXT, arcs and splines are skipped.
- Layers are ignored (everything visible in the entity list is imported);
  the editor is the place to erase furniture/annotation layers manually.
- Real-world scale cannot be trusted from DXF headers in practice, so the
  caller supplies the plan's real width in metres, as with images.
"""

from __future__ import annotations

from contextlib import suppress

from app.core.config import settings
from app.planimport.common import ImportParams, ImportResult, finish_grid

_MAX_SEGMENTS = 200_000


def _parse_pairs(text: str):
    """Yield (group_code:int, value:str) pairs from an ASCII DXF document."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) - 1:  # noqa: SIM105
        code_line = lines[i].strip()
        value_line = lines[i + 1]
        i += 2
        try:
            code = int(code_line)
        except ValueError:
            continue  # noise (e.g. binary DXF or corrupted section)
        yield code, value_line.strip()


def _extract_segments(data: bytes) -> tuple[list[tuple[float, float, float, float]], int]:
    """Return (segments, entities_seen). Segments are (x1, y1, x2, y2)."""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - decode with replace rarely fails
        raise ValueError(f"Could not read the DXF file: {exc}") from exc

    pairs = list(_parse_pairs(text))
    segments: list[tuple[float, float, float, float]] = []
    entities_seen = 0
    i = 0
    n = len(pairs)

    while i < n:
        code, value = pairs[i]
        if code != 0:
            i += 1
            continue
        etype = value.upper()
        if etype not in ("LINE", "LWPOLYLINE", "CIRCLE"):
            i += 1
            continue
        entities_seen += 1
        props: dict[int, list[float]] = {}
        j = i + 1
        while j < n and pairs[j][0] != 0:
            c, v = pairs[j]
            if c in (10, 11, 20, 21, 40, 70):
                with suppress(ValueError):
                    props.setdefault(c, []).append(float(v))
            j += 1

        if etype == "LINE":
            try:
                x1, y1 = props[10][0], props[20][0]
                x2, y2 = props[11][0], props[21][0]
                segments.append((x1, y1, x2, y2))
            except (KeyError, IndexError):
                pass
        elif etype == "LWPOLYLINE":
            xs = props.get(10, [])
            ys = props.get(20, [])
            pts = list(zip(xs, ys, strict=False))
            for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False):
                segments.append((x1, y1, x2, y2))
            if len(pts) >= 3 and int(props.get(70, [0])[0]) & 1:
                # Closed polyline: connect back to the first vertex.
                segments.append((pts[-1][0], pts[-1][1], pts[0][0], pts[0][1]))
        elif etype == "CIRCLE":
            try:
                cx, cy, r = props[10][0], props[20][0], props[40][0]
            except (KeyError, IndexError):
                cx = cy = r = None
            if r and r > 0:
                # Approximate with a 16-gon; circles are rare as walls.
                import math

                k = 16
                for s in range(k):
                    a1 = 2 * math.pi * s / k
                    a2 = 2 * math.pi * (s + 1) / k
                    segments.append(
                        (
                            cx + r * math.cos(a1),
                            cy + r * math.sin(a1),
                            cx + r * math.cos(a2),
                            cy + r * math.sin(a2),
                        )
                    )
        if len(segments) > _MAX_SEGMENTS:
            raise ValueError(
                f"The DXF contains more than {_MAX_SEGMENTS} line segments; "
                "simplify the drawing or purge unused layers first."
            )
        i = j

    return segments, entities_seen


def _rasterize(segments, grid_w: int, grid_h: int, bounds) -> set[tuple[int, int]]:  # noqa: ANN001
    """Bresenham-rasterize scaled segments into wall cells.

    The scale fills the whole grid (border-to-border); out-of-range cells are
    clamped, so the plan's far edges land on the last grid column/row.
    """
    min_x, min_y, max_x, max_y = bounds
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    scale = min(grid_w / span_x, grid_h / span_y)

    def to_cell(x: float, y: float) -> tuple[int, int]:
        cx = round((x - min_x) * scale)
        cy = round((y - min_y) * scale)
        return (max(0, min(grid_w - 1, cx)), max(0, min(grid_h - 1, cy)))

    walls: set[tuple[int, int]] = set()
    for x1, y1, x2, y2 in segments:
        cx1, cy1 = to_cell(x1, y1)
        cx2, cy2 = to_cell(x2, y2)
        _bresenham(cx1, cy1, cx2, cy2, walls)
    return walls


def _bresenham(x0: int, y0: int, x1: int, y1: int, out: set[tuple[int, int]]) -> None:
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        out.add((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def import_from_dxf(data: bytes, params: ImportParams, name: str) -> ImportResult:
    """Convert ASCII DXF bytes into an ImportResult (raises ValueError)."""
    params.validated()
    segments, entities_seen = _extract_segments(data)
    if not segments:
        raise ValueError(
            "No LINE / LWPOLYLINE / CIRCLE geometry found in the DXF. "
            "This converter reads ASCII DXF only — make sure the file is a "
            "plain-text DXF and contains model-space wall lines."
        )

    xs = [v for s in segments for v in (s[0], s[2])]
    ys = [v for s in segments for v in (s[1], s[3])]
    bounds = (min(xs), min(ys), max(xs), max(ys))
    span_x = max(bounds[2] - bounds[0], 1e-9)
    span_y = max(bounds[3] - bounds[1], 1e-9)

    # Grid size from the aspect ratio, capped at the platform limits.
    if span_x >= span_y:
        grid_w = params.target_width
        grid_h = max(8, round(span_y / span_x * params.target_width))
    else:
        grid_h = params.target_width
        grid_w = max(8, round(span_x / span_y * params.target_width))
    grid_w = min(grid_w, settings.max_grid_width)
    grid_h = min(grid_h, settings.max_grid_height)

    walls = _rasterize(segments, grid_w, grid_h, bounds)
    semantics = None
    if params.interpret:
        from app.planimport.semantics import analyze

        cell_size = round(params.real_width_m / params.target_width, 3)
        semantics = analyze(walls, grid_w, grid_h, cell_size_m=cell_size, occupancy_density=params.occupancy_density)

    return finish_grid(
        walls,
        grid_w,
        grid_h,
        params,
        source_label=name,
        source_stats={
            "source_type": "dxf",
            "entities_seen": entities_seen,
            "segments_imported": len(segments),
        },
        semantics=semantics,
    )
