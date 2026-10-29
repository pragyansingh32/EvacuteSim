"""Strategy comparison API schemas."""

from pydantic import BaseModel, ConfigDict, Field


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_ids: list[int] = Field(min_length=1, max_length=20)


class CompareRow(BaseModel):
    run_id: int
    name: str
    strategy: str
    seed: int
    metrics: dict
    scenario_name: str | None = None


class ComparisonResponse(BaseModel):
    rows: list[CompareRow]
    # Per-metric winner (lower is better for time metrics; higher for evacuated)
    verdicts: dict[str, str] = Field(
        default_factory=dict,
        description="metric -> run name with the best value, given each metric's direction",
    )
    notes: list[str] = Field(default_factory=list)
