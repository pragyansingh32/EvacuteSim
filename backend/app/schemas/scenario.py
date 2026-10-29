"""Scenario API schemas.

A scenario pins down everything the engine needs except the building itself:
populations per zone, behavior distributions, route availability, strategy,
seed, and run limits.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings

STRATEGIES = ("nearest_exit", "capacity_aware", "balanced_assignment")


class DistributionSpec(BaseModel):
    """Walking-speed or pre-movement delay distribution."""

    model_config = ConfigDict(extra="forbid")

    distribution: str = Field(default="uniform", pattern="^(normal|uniform)$")
    mean: float | None = Field(default=None, description="required for 'normal'")
    sd: float | None = Field(default=None, ge=0, description="required for 'normal'")
    min: float
    max: float

    @field_validator("max")
    @classmethod
    def _max_ge_min(cls, v: float, info) -> float:  # noqa: ANN001
        min_v = info.data.get("min")
        if min_v is not None and v < min_v:
            raise ValueError("max must be >= min")
        return v


class ScenarioConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_populations: dict[str, int]
    speed: DistributionSpec
    pre_movement: DistributionSpec
    strategy: str = Field(default="nearest_exit")
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    blocked_exit_ids: list[str] = Field(default_factory=list)
    blocked_cells: list[tuple[int, int]] = Field(default_factory=list)
    exit_capacity_overrides: dict[str, float] = Field(default_factory=dict)
    max_duration_s: float = Field(default=600.0, gt=0, le=settings.max_sim_duration_s)
    dt_s: float = Field(default=settings.default_dt_s, gt=0, le=2.0)
    frame_interval_s: float = Field(default=settings.default_frame_interval_s, gt=0, le=60.0)
    record_frames: bool = True

    @field_validator("zone_populations")
    @classmethod
    def _population_within_limits(cls, v: dict[str, int]) -> dict[str, int]:
        total = sum(v.values())
        if total <= 0:
            raise ValueError("Total population must be positive")
        if total > settings.max_occupants:
            raise ValueError(f"Total population {total} exceeds limit {settings.max_occupants}")
        for zone_id, count in v.items():
            if count < 0:
                raise ValueError(f"Population for zone '{zone_id}' must be >= 0")
        return v

    @field_validator("strategy")
    @classmethod
    def _known_strategy(cls, v: str) -> str:
        if v not in STRATEGIES:
            raise ValueError(f"strategy must be one of {STRATEGIES}")
        return v

    @field_validator("blocked_cells")
    @classmethod
    def _blocked_within_limits(cls, v: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if len(v) > settings.max_blocked_cells:
            raise ValueError(f"Too many blocked cells (limit {settings.max_blocked_cells})")
        return v

    @field_validator("exit_capacity_overrides")
    @classmethod
    def _positive_capacities(cls, v: dict[str, float]) -> dict[str, float]:
        for exit_id, cap in v.items():
            if cap <= 0:
                raise ValueError(f"Capacity override for '{exit_id}' must be positive")
        return v


class ScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    building_id: int
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    config: ScenarioConfigSchema


class ScenarioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    config: ScenarioConfigSchema | None = None


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    building_id: int
    name: str
    description: str
    is_sample: bool
    created_at: datetime
    updated_at: datetime


class ScenarioDetail(ScenarioRead):
    config: ScenarioConfigSchema
