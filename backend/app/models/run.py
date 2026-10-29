"""Simulation run persistence.

A run stores its own building snapshot and full configuration so it can be
reproduced even if the underlying building/scenario later change. `status` is
pending -> running -> completed|failed; `result_json.status` distinguishes
"completed" (everyone out) from "incomplete" (horizon reached) engine outcomes.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, utcnow


class RunModel(Base, JSONText):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenarios.id"), nullable=True, index=True
    )
    building_id: Mapped[int | None] = mapped_column(
        ForeignKey("buildings.id"), nullable=True, index=True
    )
    building_snapshot_json: Mapped[str] = mapped_column(Text)  # layout used, for reproducibility
    name: Mapped[str] = mapped_column(String(200), default="")
    strategy: Mapped[str] = mapped_column(String(40))
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    config_json: Mapped[str] = mapped_column(Text)  # full engine config echo
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def result(self) -> dict | None:
        return self.decode(self.result_json)

    def error(self) -> dict | None:
        return self.decode(self.error_json)

    def config(self) -> dict:
        return self.decode(self.config_json)
