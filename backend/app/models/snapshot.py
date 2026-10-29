"""Restore-point persistence model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, utcnow


class SnapshotModel(Base, JSONText):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    counts_json: Mapped[str] = mapped_column(Text, default="{}")
    filename: Mapped[str] = mapped_column(String(260))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False)
