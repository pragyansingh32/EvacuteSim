"""Experiment API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    base_scenario_id: int
    # {dot.path into scenario config -> list of values}; combinations are the
    # cartesian product. Example: {"strategy": ["nearest_exit",
    # "capacity_aware"], "pre_movement.max": [5.0, 30.0]}
    sweep: dict[str, list] = Field(min_length=1)
    seeds: list[int] = Field(
        default_factory=lambda: [0],
        min_length=1,
        max_length=20,
        description="One repetition per seed per parameter combination.",
    )
    wait: bool = Field(default=False, description="Execute synchronously (small experiments).")


class ExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    base_scenario_id: int
    status: str
    total_planned: int
    created_at: datetime
    finished_at: datetime | None
    error: dict | None = None


class ExperimentResultRow(BaseModel):
    experiment_run_id: int
    run_id: int
    sweep_values: dict
    seed: int
    metrics: dict | None = None


class ExperimentResults(BaseModel):
    experiment: ExperimentRead
    sweep_definition: dict
    rows: list[ExperimentResultRow]
