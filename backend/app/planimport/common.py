"""Shared types for plan import."""

from dataclasses import dataclass, field


@dataclass
class ImportParams:
    """User-controlled conversion parameters.

    target_width  — number of grid cells across the plan's larger dimension
                    (the other dimension follows the aspect ratio).
    real_width_m  — real-world width of the plan in metres; sets cell size.
    threshold     — image only: mean luminance (0-255) below which a cell
                    counts as wall. Lower = fewer walls.
    invert        — image only: for plans drawn light-on-dark.
    """

    target_width: int = 60
    real_width_m: float = 15.0
    threshold: int = 128
    invert: bool = False

    def validated(self) -> "ImportParams":
        from app.core.config import settings

        if not (8 <= self.target_width <= settings.max_grid_width):
            raise ValueError(
                f"Target width must be between 8 and {settings.max_grid_width} cells."
            )
        if not (1.0 <= self.real_width_m <= 500.0):
            raise ValueError("Real plan width must be between 1 and 500 metres.")
        if not (0 <= self.threshold <= 255):
            raise ValueError("Threshold must be between 0 and 255.")
        return self


@dataclass
class ImportDraft:
    """A converted layout draft: walls only, no exits/zones yet."""

    name: str
    width: int
    height: int
    cell_size_m: float
    walls: list[tuple[int, int]] = field(default_factory=list)

    def to_editor_state(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "cell_size_m": self.cell_size_m,
            "walls": sorted([x, y] for x, y in self.walls),
            "exits": [],
            "zones": [],
        }


@dataclass
class ImportResult:
    draft: ImportDraft
    stats: dict
    warnings: list[str]


def finish_grid(
    walls: set[tuple[int, int]],
    grid_w: int,
    grid_h: int,
    params: ImportParams,
    source_label: str,
    source_stats: dict,
) -> ImportResult:
    """Common post-processing: cell-size computation, sanity warnings.

    Raises ValueError when the conversion produced something unusable.
    """
    warnings: list[str] = []
    total_cells = grid_w * grid_h
    ratio = len(walls) / total_cells if total_cells else 1.0

    if not walls:
        raise ValueError(
            "No walls were detected in the plan. Try a lower threshold (darker "
            "cutoff), check the invert option, or make sure the file contains "
            "visible wall lines."
        )
    if ratio > 0.6:
        warnings.append(
            f"Over 60% of the grid converted to walls ({ratio:.0%}) — the result "
            "is probably too dense to walk in. Try a higher threshold or enable "
            "invert if the plan is light-on-dark."
        )
    elif ratio < 0.02:
        warnings.append(
            f"Only {ratio:.1%} of cells became walls — thin or faint lines may "
            "have been missed. Try a lower threshold."
        )

    warnings.append(
        "Import produces walls only: review the draft in the editor, clean up "
        "noise (text, furniture, hatching), then place exits and starting "
        "zones before running a simulation."
    )
    warnings.append(
        "Imported geometry is an approximation at grid resolution; walls may be "
        "thicker/thinner than drawn and curved shapes become stepped."
    )

    cell_size = round(params.real_width_m / params.target_width, 3)
    draft = ImportDraft(
        name=source_label,
        width=grid_w,
        height=grid_h,
        cell_size_m=cell_size,
        walls=walls,
    )
    stats = {
        "source_type": source_stats.pop("source_type"),
        "wall_cell_count": len(walls),
        "wall_ratio": round(ratio, 4),
        "grid": [grid_w, grid_h],
        "cell_size_m": cell_size,
        **source_stats,
    }
    return ImportResult(draft=draft, stats=stats, warnings=warnings)
