"""Building API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    capacity_pps: float = Field(default=1.0, gt=0, description="Modeled throughput, persons/second")


class ZoneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=100)
    cells: list[tuple[int, int]] = Field(min_length=1)


class BuildingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    width: int = Field(ge=4, le=120)
    height: int = Field(ge=4, le=120)
    cell_size_m: float = Field(default=0.5, gt=0.05, le=5.0)
    walls: list[tuple[int, int]] = Field(default_factory=list)
    exits: list[ExitSpec] = Field(min_length=1, max_length=20)
    zones: list[ZoneSpec] = Field(default_factory=list, max_length=30)


class BuildingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    width: int | None = Field(default=None, ge=4, le=120)
    height: int | None = Field(default=None, ge=4, le=120)
    cell_size_m: float | None = Field(default=None, gt=0.05, le=5.0)
    walls: list[tuple[int, int]] | None = None
    exits: list[ExitSpec] | None = Field(default=None, min_length=1, max_length=20)
    zones: list[ZoneSpec] | None = Field(default=None, max_length=30)


class BuildingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    width: int
    height: int
    cell_size_m: float
    is_sample: bool
    created_at: datetime
    updated_at: datetime


class BuildingDetail(BuildingRead):
    walls: list[tuple[int, int]]
    exits: list[ExitSpec]
    zones: list[ZoneSpec]
    warnings: list[str] = Field(default_factory=list)
