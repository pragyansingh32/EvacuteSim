"""Run API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RunOverrides(BaseModel):
    """Optional per-run adjustments on top of the scenario configuration.

    Overrides let the same saved scenario be re-run with a different seed or
    strategy without editing it - the mechanism the comparison views use.
    """

    model_config = ConfigDict(extra="forbid")

    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    strategy: str | None = None

    @property
    def has_any(self) -> bool:
        return self.seed is not None or self.strategy is not None


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: int
    name: str | None = Field(default=None, max_length=200)
    wait: bool = Field(
        default=False,
        description="Execute synchronously and return the full result (small runs).",
    )
    overrides: RunOverrides = Field(default_factory=RunOverrides)


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int | None
    building_id: int | None
    name: str
    strategy: str
    seed: int
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunMetrics(BaseModel):
    """Headline metrics extracted from the stored engine result."""

    engine_status: str | None = None
    sim_time_s: float | None = None
    steps: int | None = None
    total_occupants: int | None = None
    evacuated_count: int | None = None
    unreachable_count: int | None = None
    incapacitated_count: int | None = None
    disasters: list = Field(default_factory=list)
    remaining_count: int | None = None
    t50_s: float | None = None
    t90_s: float | None = None
    t95_s: float | None = None
    mean_evacuation_time_s: float | None = None
    max_evacuation_time_s: float | None = None
    queue_total_s: float | None = None
    queue_mean_s: float | None = None
    queue_max_s: float | None = None
    fallback_count: int | None = None
    exit_stats: list[dict] = Field(default_factory=list)
    congestion: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RunError(BaseModel):
    code: str
    message: str


class RunDetail(RunSummary):
    config: dict
    metrics: RunMetrics | None = None
    error: RunError | None = None
    building_snapshot: dict | None = Field(
        default=None, description="Included only when ?include_building=true"
    )
    timeline: list = Field(default_factory=list)
    frames: list = Field(default_factory=list)
