"""Declarative base and JSON column helpers."""

import json
from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def dumps(data) -> str:  # noqa: ANN001
    """Stable JSON serialization for stored documents."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def loads(raw: str | None) -> dict | list | None:
    if raw is None or raw == "":
        return None
    return json.loads(raw)


class JSONText:
    """Mixin providing JSON (de)serialization over a TEXT column."""

    @staticmethod
    def encode(data) -> str:  # noqa: ANN001
        return dumps(data)

    @staticmethod
    def decode(raw: str | None):  # noqa: ANN001
        return loads(raw)
