"""Building layout persistence."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, utcnow


class BuildingModel(Base, JSONText):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    cell_size_m: Mapped[float] = mapped_column(Float)
    walls_json: Mapped[str] = mapped_column(Text, default="[]")
    exits_json: Mapped[str] = mapped_column(Text, default="[]")
    zones_json: Mapped[str] = mapped_column(Text, default="[]")
    is_sample: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_grid_dict(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "cell_size_m": self.cell_size_m,
            "walls": self.decode(self.walls_json),
            "exits": self.decode(self.exits_json),
            "zones": self.decode(self.zones_json),
        }
