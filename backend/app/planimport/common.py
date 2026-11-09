"""Shared types for plan import."""

import math
from dataclasses import dataclass, field


@dataclass
class ImportParams:
    """User-controlled conversion parameters.

    target_width  - number of grid cells across the plan's larger dimension
                    (the other dimension follows the aspect ratio).
    real_width_m  - real-world width of the plan in metres; sets cell size.
    threshold     - image only: mean luminance (0-255) below which a cell
                    counts as wall. Lower = fewer walls.
    invert        - image only: for plans drawn light-on-dark.
    """

    target_width: int = 60
    real_width_m: float = 15.0
    threshold: int | None = None  # None = automatic (Otsu)
    invert: bool = False
    interpret: bool = True
    occupancy_density: float = 0.25  # persons per square metre of zone area
    wall_density: float = 0.3  # fraction of a cell's pixels that must be ink

    def validated(self) -> "ImportParams":
        from app.core.config import settings

        if not (8 <= self.target_width <= settings.max_grid_width):
            raise ValueError(
                f"Target width must be between 8 and {settings.max_grid_width} cells."
            )
        if not (1.0 <= self.real_width_m <= 500.0):
            raise ValueError("Real plan width must be between 1 and 500 metres.")
        if self.threshold is not None and not (0 <= self.threshold <= 255):
            raise ValueError("Threshold must be between 0 and 255.")
        if not (0.05 <= self.wall_density <= 0.9):
            raise ValueError("Wall density must be between 0.05 and 0.9.")
        if not (0.02 <= self.occupancy_density <= 2.0):
            raise ValueError("Occupancy density must be between 0.02 and 2.0 persons/m2.")
        return self


@dataclass
class ImportDraft:
    """A converted layout draft: walls plus auto-detected exits and zones."""

    name: str
    width: int
    height: int
    cell_size_m: float
    walls: list[tuple[int, int]] = field(default_factory=list)
    exits: list[dict] = field(default_factory=list)
    zones: list[dict] = field(default_factory=list)

    def to_editor_state(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "cell_size_m": self.cell_size_m,
            "walls": sorted([x, y] for x, y in self.walls),
            "exits": [dict(e) for e in self.exits],
            "zones": [
                {"id": z["id"], "name": z["name"], "cells": sorted([x, y] for x, y in z["cells"])}
                for z in self.zones
            ],
        }


@dataclass
class ImportResult:
    draft: ImportDraft
    stats: dict
    warnings: list[str]
    zone_populations: dict[str, int] = field(default_factory=dict)


def finish_grid(
    walls: set[tuple[int, int]],
    grid_w: int,
    grid_h: int,
    params: ImportParams,
    source_label: str,
    source_stats: dict,
    semantics=None,  # noqa: ANN001 - PlanSemantics | None
) -> ImportResult:
    """Common post-processing: cell-size computation, sanity warnings.

    Raises ValueError when the conversion produced something unusable.
    """
    warnings: list[str] = []
    if semantics is not None:
        warnings.extend(semantics.warnings)
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
            f"Over 60% of the grid converted to walls ({ratio:.0%}) - the result "
            "is probably too dense to walk in. Try a higher threshold or enable "
            "invert if the plan is light-on-dark."
        )
    elif ratio < 0.02:
        warnings.append(
            f"Only {ratio:.1%} of cells became walls - thin or faint lines may "
            "have been missed. Try a lower threshold."
        )

    warnings.append(
        "Auto-detection is a best-effort interpretation: review the draft in "
        "the editor (doors, exits, and zones can be adjusted) before running "
        "a simulation."
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
        exits=list(semantics.exits) if semantics else [],
        zones=list(semantics.zones) if semantics else [],
    )
    stats = {
        "source_type": source_stats.pop("source_type"),
        "wall_cell_count": len(walls),
        "wall_ratio": round(ratio, 4),
        "grid": [grid_w, grid_h],
        "cell_size_m": cell_size,
        **source_stats,
    }
    if semantics is not None:
        stats["semantics"] = {
            "rooms": semantics.rooms,
            "doors": semantics.doors,
            "openings": semantics.openings,
            "exits": len(semantics.exits),
            "zones": len(semantics.zones),
            "noise_removed": semantics.noise_removed,
        }
    return ImportResult(
        draft=draft,
        stats=stats,
        warnings=warnings,
        zone_populations=dict(semantics.zone_populations) if semantics else {},
    )


def suggested_scenario(draft: "ImportDraft", populations: dict[str, int]) -> dict:
    """A ready-to-run scenario configuration for an interpreted draft."""
    total = sum(populations.values())
    total_cap = sum(e.get("capacity_pps", 1.0) for e in draft.exits) or 1.0
    speed_max = 1.8
    # Round DOWN: the suggested dt must always satisfy the engine's
    # dt <= cell_size / max_speed validation.
    dt = math.floor(min(0.25, draft.cell_size_m / speed_max) * 1000) / 1000
    max_duration = min(900.0, max(180.0, round((total / total_cap) * 2.5 + 60)))
    return {
        "name": f"{draft.name} - auto scenario",
        "description": (
            "Suggested by plan import: populations from the occupancy density, "
            "auto-detected exits with width-based capacities. Edit freely."
        ),
        "config": {
            "zone_populations": dict(populations),
            "speed": {"distribution": "normal", "mean": 1.2, "sd": 0.25, "min": 0.6, "max": speed_max},
            "pre_movement": {"distribution": "uniform", "min": 0.0, "max": 15.0},
            "strategy": "nearest_exit",
            "seed": 42,
            "blocked_exit_ids": [],
            "blocked_cells": [],
            "exit_capacity_overrides": {},
            "max_duration_s": float(max_duration),
            "dt_s": dt,
            "frame_interval_s": 1.0,
            "record_frames": True,
        },
    }
