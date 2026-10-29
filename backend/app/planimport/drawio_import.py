"""draw.io (.drawio / .xml) diagram import — precise vector conversion.

draw.io stores plans as mxGraph XML: every shape is a vertex with exact
coordinates and every line an edge. This importer converts that vector
geometry DIRECTLY onto the simulation grid — no pixel guessing, so the
result matches the diagram exactly at the chosen grid resolution.

Supported elements and rules (documented in docs/KNOWN_LIMITATIONS.md):

- **Filled shapes** (`fillColor` explicitly set, not "none") become solid
  wall blocks.
- **Unfilled shapes** (rectangles, ellipses, strokes) become wall OUTLINES —
  draw your rooms as unfilled rectangles and the walls are the borders.
- **Edges (lines)** become wall segments along their waypoints; edges
  connected to shapes are routed through the shape centers.
- **Text-only cells** (style ``text;``) are skipped — labels never become
  walls.
- Stroke thickness converts to wall thickness in cells (round(px / cell)).
- Doors/exits/zones/populations are then detected automatically by the same
  semantics pipeline used for images (gap-in-wall geometry + flood tests).

Files: uncompressed ``.drawio`` XML, or draw.io's compressed ``<diagram>``
payload (base64 → raw deflate → URI-encoded), which many exports use.
Only the first page of a multi-page file is imported.
"""

from __future__ import annotations

import base64
import math
import xml.etree.ElementTree as ET
import zlib

from app.planimport.common import ImportParams, ImportResult, finish_grid
from app.planimport.semantics import analyze


class _Shape:
    """One piece of vector geometry mapped to grid space."""

    __slots__ = ("kind", "x", "y", "w", "h", "points", "filled", "stroke_px", "stroke_cells")

    def __init__(
        self,
        kind: str,
        x: float,
        y: float,
        w: float,
        h: float,
        points: list[tuple[float, float]],
        filled: bool,
        stroke_px: float,
    ) -> None:
        self.kind = kind
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.points = points
        self.filled = filled
        self.stroke_px = stroke_px
        self.stroke_cells = 1


def _parse_style(style: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (style or "").split(";"):
        if "=" in part:
            key, _, value = part.partition("=")
            out[key.strip()] = value.strip()
    return out


def _decode_diagram_payload(diagram_el: ET.Element) -> str | None:
    """Return the mxGraphModel XML string of a <diagram> element.

    Handles both plain XML content and draw.io's compressed payload
    (base64 of raw-deflate of a URI-encoded XML string).
    """
    raw = (diagram_el.text or "").strip()
    if not raw:
        model = diagram_el.find(".//mxGraphModel")
        if model is not None:
            return ET.tostring(model, encoding="unicode")
        return None
    if raw.startswith("<"):
        return raw  # uncompressed
    try:
        decoded = base64.b64decode(raw)
        inflated: bytes | None = None
        # draw.io uses RAW deflate (pako.deflateRaw); accept zlib-wrapped
        # streams too for hand-made files.
        for wbits in (-15, 15):
            try:
                inflated = zlib.decompress(decoded, wbits=wbits)
                break
            except zlib.error:
                continue
        if inflated is None:
            raise zlib.error("neither raw-deflate nor zlib")
        from urllib.parse import unquote

        return unquote(inflated.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise ValueError(
            "The diagram payload is neither plain XML nor a valid draw.io "
            f"compressed payload: {exc}"
        ) from exc


def _collect_cells(xml_text: str) -> list[ET.Element]:
    """Parse the mxGraphModel and return all mxCell elements."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML inside the draw.io file: {exc}") from exc
    model = root if root.tag == "mxGraphModel" else root.find(".//mxGraphModel")
    if model is None:
        raise ValueError(
            "No mxGraphModel found — make sure this is a draw.io file "
            "(.drawio / .xml exported from diagrams.net)."
        )
    return list(model.iter("mxCell"))


def _cell_shapes(cells: list[ET.Element]) -> tuple[list[_Shape], int]:
    """Convert mxCell elements into _Shape records (vector-space coords)."""
    vertices: dict[str, tuple[float, float, float, float]] = {}
    shapes: list[_Shape] = []
    text_cells = 0

    for cell in cells:
        style = _parse_style(cell.get("style", ""))
        geometry = cell.find("mxGeometry")

        if cell.get("edge") == "1":
            if geometry is None:
                continue
            # Edge points: ONLY explicit mxPoints (sourcePoint, waypoints,
            # targetPoint). The geometry x/y of an edge is a relative layout
            # hint, not a coordinate — using it corrupts the geometry. Shape
            # references are ignored on purpose: an edge anchored to a room
            # shape is a connection, not a wall through the room.
            source_pt = None
            target_pt = None
            waypoints: list[tuple[float, float]] = []
            for point in geometry.iter("mxPoint"):
                as_attr = point.get("as")
                try:
                    px = float(point.get("x") or 0)
                    py = float(point.get("y") or 0)
                except (TypeError, ValueError):
                    continue
                if as_attr == "sourcePoint":
                    source_pt = (px, py)
                elif as_attr == "targetPoint":
                    target_pt = (px, py)
                else:
                    waypoints.append((px, py))
            pts: list[tuple[float, float]] = []
            if source_pt is not None:
                pts.append(source_pt)
            pts.extend(waypoints)
            if target_pt is not None:
                pts.append(target_pt)
            # Drop consecutive duplicates.
            deduped: list[tuple[float, float]] = []
            for pt in pts:
                if not deduped or pt != deduped[-1]:
                    deduped.append(pt)
            pts = deduped
            if len(pts) >= 2:
                try:
                    stroke_px = float(style.get("strokeWidth", 1))
                except ValueError:
                    stroke_px = 1.0
                for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False):
                    shapes.append(
                        _Shape("line", x1, y1, x2 - x1, y2 - y1, [(x1, y1), (x2, y2)], False, stroke_px)
                    )
            continue

        # vertex
        if geometry is None:
            continue
        try:
            x = float(geometry.get("x") or 0)
            y = float(geometry.get("y") or 0)
            w = float(geometry.get("width") or 0)
            h = float(geometry.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        if style.get("text") == "1" or "text;" in (cell.get("style") or ""):
            text_cells += 1
            continue
        vertices[cell.get("id", "")] = (x, y, w, h)
        fill = style.get("fillColor")
        filled = fill is not None and fill != "none"
        try:
            stroke_px = float(style.get("strokeWidth", 1))
        except ValueError:
            stroke_px = 1.0
        kind = "ellipse" if "ellipse" in style else "rect"
        shapes.append(_Shape(kind, x, y, w, h, [], filled, stroke_px))

    return shapes, text_cells


def _bbox(shapes: list[_Shape]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for s in shapes:
        if s.kind == "line":
            for px, py in s.points:
                xs.append(px)
                ys.append(py)
        else:
            xs.extend([s.x, s.x + s.w])
            ys.extend([s.y, s.y + s.h])
    return min(xs), min(ys), max(xs), max(ys)


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


def _stamp(line: set[tuple[int, int]], thickness: int, grid_w: int, grid_h: int, walls: set[tuple[int, int]]) -> None:
    if thickness <= 1:
        walls |= line
        return
    pad = thickness // 2
    for cx, cy in line:
        for ddx in range(-pad, pad + 1):
            for ddy in range(-pad, pad + 1):
                px, py = cx + ddx, cy + ddy
                if 0 <= px < grid_w and 0 <= py < grid_h:
                    walls.add((px, py))


def _rasterize(shapes: list[_Shape], grid_w: int, grid_h: int, bbox) -> set[tuple[int, int]]:  # noqa: ANN001
    """Map vector geometry onto grid cells (exact at grid resolution)."""
    min_x, min_y, max_x, max_y = bbox
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    scale_x = grid_w / span_x
    scale_y = grid_h / span_y

    def cell(x: float, y: float) -> tuple[int, int]:
        cx = int((x - min_x) * scale_x)
        cy = int((y - min_y) * scale_y)
        return (max(0, min(grid_w - 1, cx)), max(0, min(grid_h - 1, cy)))

    walls: set[tuple[int, int]] = set()
    for s in shapes:
        thickness = max(1, round(s.stroke_cells))
        if s.kind == "line":
            (x1, y1), (x2, y2) = s.points[0], s.points[-1]
            cx1, cy1 = cell(x1, y1)
            cx2, cy2 = cell(x2, y2)
            line: set[tuple[int, int]] = set()
            _bresenham(cx1, cy1, cx2, cy2, line)
            _stamp(line, thickness, grid_w, grid_h, walls)
        elif s.filled:
            gx0, gy0 = cell(s.x, s.y)
            gx1, gy1 = cell(s.x + s.w, s.y + s.h)
            if s.kind == "ellipse":
                ccx = (gx0 + gx1) / 2
                ccy = (gy0 + gy1) / 2
                rx = max((gx1 - gx0) / 2, 0.5)
                ry = max((gy1 - gy0) / 2, 0.5)
                for gy in range(max(0, gy0), min(grid_h, gy1 + 1)):
                    for gx in range(max(0, gx0), min(grid_w, gx1 + 1)):
                        if ((gx - ccx) / rx) ** 2 + ((gy - ccy) / ry) ** 2 <= 1.2:
                            walls.add((gx, gy))
            else:
                for gy in range(max(0, gy0), min(grid_h, gy1 + 1)):
                    for gx in range(max(0, gx0), min(grid_w, gx1 + 1)):
                        walls.add((gx, gy))
        else:
            # Unfilled: wall outline along the shape's border.
            gx0, gy0 = cell(s.x, s.y)
            gx1, gy1 = cell(s.x + s.w, s.y + s.h)
            outline: set[tuple[int, int]] = set()
            if s.kind == "ellipse":
                ccx = (gx0 + gx1) / 2
                ccy = (gy0 + gy1) / 2
                rx = max((gx1 - gx0) / 2, 0.5)
                ry = max((gy1 - gy0) / 2, 0.5)
                steps = 64
                for i in range(steps):
                    a1 = 2 * math.pi * i / steps
                    a2 = 2 * math.pi * (i + 1) / steps
                    p1 = cell(s.x + s.w / 2 + (s.w / 2) * math.cos(a1), s.y + s.h / 2 + (s.h / 2) * math.sin(a1))
                    p2 = cell(s.x + s.w / 2 + (s.w / 2) * math.cos(a2), s.y + s.h / 2 + (s.h / 2) * math.sin(a2))
                    _bresenham(p1[0], p1[1], p2[0], p2[1], outline)
            else:
                _bresenham(gx0, gy0, gx1, gy0, outline)
                _bresenham(gx1, gy0, gx1, gy1, outline)
                _bresenham(gx1, gy1, gx0, gy1, outline)
                _bresenham(gx0, gy1, gx0, gy0, outline)
            _stamp(outline, thickness, grid_w, grid_h, walls)
    return walls


def import_from_drawio(data: bytes, params: ImportParams, name: str) -> ImportResult:
    """Convert draw.io diagram bytes into an ImportResult (raises ValueError)."""
    params.validated()
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"The file is not valid draw.io XML: {exc}") from exc

    diagrams = [root] if root.tag == "mxGraphModel" else root.findall(".//diagram")
    if not diagrams:
        raise ValueError(
            "No diagram page found. Make sure this is a draw.io file "
            "(.drawio / .xml exported from diagrams.net)."
        )
    xml_text = _decode_diagram_payload(diagrams[0])
    if not xml_text:
        raise ValueError("The first diagram page is empty.")

    cells = _collect_cells(xml_text)
    shapes, text_cells = _cell_shapes(cells)
    if not shapes:
        raise ValueError(
            "No shapes or lines found in the diagram. Draw the plan with "
            "rectangles and lines, or export an image instead."
        )

    bbox = _bbox(shapes)
    span_x = max(bbox[2] - bbox[0], 1e-9)
    span_y = max(bbox[3] - bbox[1], 1e-9)
    if span_x >= span_y:
        grid_w = params.target_width
        grid_h = max(8, round(span_y / span_x * params.target_width))
    else:
        grid_h = params.target_width
        grid_w = max(8, round(span_x / span_y * params.target_width))
    grid_w = min(grid_w, 120)
    grid_h = min(grid_h, 120)

    cell_size = round(params.real_width_m / params.target_width, 3)
    px_per_cell = (span_x / grid_w + span_y / grid_h) / 2
    for shape in shapes:
        shape.stroke_cells = max(1, round(shape.stroke_px / px_per_cell))

    walls = _rasterize(shapes, grid_w, grid_h, bbox)

    semantics = None
    if params.interpret:
        semantics = analyze(
            walls, grid_w, grid_h, cell_size_m=cell_size, occupancy_density=params.occupancy_density
        )
        # Keep the draft consistent with the semantics (noise removed).
        walls = semantics.walls

    result = finish_grid(
        walls,
        grid_w,
        grid_h,
        params,
        source_label=name,
        source_stats={
            "source_type": "drawio",
            "shapes": len(shapes),
            "text_cells_skipped": text_cells,
        },
        semantics=semantics,
    )
    result.warnings.insert(
        0,
        "Vector import: filled shapes become solid walls, unfilled shapes and "
        "lines become wall outlines, text labels are ignored. Leave gaps in "
        "your walls where doors should be.",
    )
    return result
