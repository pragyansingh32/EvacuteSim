"""Research experiment persistence: a sweep of scenario parameter values."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, utcnow


class ExperimentModel(Base, JSONText):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    base_scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"))
    sweep_json: Mapped[str] = mapped_column(Text)  # {dot.path: [values...]}
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    total_planned: Mapped[int] = mapped_column(Integer, default=0)
    error_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentRunModel(Base, JSONText):
    __tablename__ = "experiment_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    sweep_values_json: Mapped[str] = mapped_column(Text)  # {dot.path: value}
    seed: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
