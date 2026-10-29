"""Restore points: full-workspace snapshots with safe, transactional restore.

A snapshot captures every data table (buildings, scenarios, runs, experiments,
experiment_runs) as a JSON document on disk plus a row in `snapshots`.
Restoring wipes the data tables and re-inserts the snapshot rows with their
original ids inside one transaction. Safety net: **every restore first
auto-snapshots the current state**, so a restore can always be undone.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT
from app.core.errors import NotFoundError
from app.models import (
    BuildingModel,
    ExperimentModel,
    ExperimentRunModel,
    RunModel,
    ScenarioModel,
    SnapshotModel,
)

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = BACKEND_ROOT / "data" / "snapshots"

# Order matters: parents before children for insert, reversed for delete.
TABLES: list[type] = [
    BuildingModel,
    ScenarioModel,
    RunModel,
    ExperimentModel,
    ExperimentRunModel,
]


def _snapshot_dir() -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SNAPSHOT_DIR


def _row_to_dict(row) -> dict:  # noqa: ANN001
    out = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        out[column.name] = value
    return out


def _rows_from_json(model, rows: list[dict]) -> list:  # noqa: ANN001
    columns = {c.name for c in model.__table__.columns}
    objects = []
    for raw in rows:
        filtered = {}
        for key, value in raw.items():
            if key not in columns:
                continue
            column = model.__table__.columns[key]
            if isinstance(value, str) and column.type.python_type is datetime:
                try:
                    value = datetime.fromisoformat(value)
                except ValueError:
                    pass
            filtered[key] = value
        objects.append(model(**filtered))
    return objects


def create_snapshot(db: Session, name: str, is_auto: bool = False) -> SnapshotModel:
    """Capture all data tables into a JSON file + a snapshots row."""
    tables: dict[str, list] = {}
    counts: dict[str, int] = {}
    for model in TABLES:
        rows = db.execute(text(f"SELECT * FROM {model.__tablename__}")).mappings().all()
        # Use model-aware serialization for datetime safety.
        keys = rows[0].keys() if rows else [c.name for c in model.__table__.columns]
        serialized = []
        for row_mapping in rows:
            obj = model(**{k: row_mapping[k] for k in keys})
            serialized.append(_row_to_dict(obj))
        tables[model.__tablename__] = serialized
        counts[model.__tablename__] = len(serialized)

    document = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "tables": tables,
    }
    payload = json.dumps(document, default=str, sort_keys=True)

    _snapshot_dir()
    # Peek at the next id so the filename matches the row (safe: single-user).
    next_id = db.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM snapshots")).scalar()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name)[:60]
    filename = f"snapshot-{next_id:04d}-{stamp}-{safe_name.replace(' ', '_')}.json"
    path = _snapshot_dir() / filename
    path.write_text(payload, encoding="utf-8")

    snapshot = SnapshotModel(
        name=name,
        created_at=datetime.now(UTC),
        counts_json=SnapshotModel.encode(counts),
        filename=filename,
        size_bytes=len(payload.encode("utf-8")),
        is_auto=is_auto,
    )
    db.add(snapshot)
    db.flush()
    logger.info("Snapshot %s '%s' created (%d bytes)", snapshot.id, name, snapshot.size_bytes)
    return snapshot


def _read_document(snapshot: SnapshotModel) -> dict:  # noqa: ANN001
    path = _snapshot_dir() / snapshot.filename
    if not path.is_file():
        raise NotFoundError(f"Snapshot file '{snapshot.filename}' is missing on disk.")
    return json.loads(path.read_text(encoding="utf-8"))


def restore_snapshot(db: Session, snapshot_id: int) -> dict:
    """Restore all data tables from a snapshot (auto-backups first)."""
    snapshot = db.get(SnapshotModel, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Restore point {snapshot_id} not found.")
    document = _read_document(snapshot)

    # Safety net: capture the current state before overwriting anything.
    create_snapshot(db, f"Auto-backup before restoring '{snapshot.name}'", is_auto=True)
    db.commit()  # the safety net must be durable before we start wiping

    for model in reversed(TABLES):
        db.execute(text(f"DELETE FROM {model.__tablename__}"))
    db.flush()

    restored: dict[str, int] = {}
    has_sequence_table = db.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'")
    ).scalar()
    for model in TABLES:
        rows = document["tables"].get(model.__tablename__, [])
        for obj in _rows_from_json(model, rows):
            db.add(obj)
        db.flush()
        restored[model.__tablename__] = len(rows)
        # Keep autoincrement counters above the restored ids (the sequence
        # table only exists after the first AUTOINCREMENT insert).
        if has_sequence_table:
            db.execute(
                text(
                    f"UPDATE sqlite_sequence SET seq = (SELECT COALESCE(MAX(id), 0) "
                    f"FROM {model.__tablename__}) WHERE name = '{model.__tablename__}'"
                )
            )
            db.execute(
                text(
                    f"INSERT INTO sqlite_sequence (name, seq) "
                    f"SELECT '{model.__tablename__}', COALESCE(MAX(id), 0) "
                    f"FROM {model.__tablename__} "
                    f"WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = '{model.__tablename__}')"
                )
            )
    db.flush()
    logger.info("Restored snapshot %s: %s", snapshot_id, restored)
    return {"restored": restored, "snapshot": snapshot.name}


def list_snapshots(db: Session) -> list[SnapshotModel]:  # noqa: ANN001
    return list(
        db.query(SnapshotModel).order_by(SnapshotModel.id.desc()).all()  # type: ignore[attr-defined]
    )


def get_snapshot(db: Session, snapshot_id: int) -> SnapshotModel:  # noqa: ANN001
    snapshot = db.get(SnapshotModel, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Restore point {snapshot_id} not found.")
    return snapshot


def delete_snapshot(db: Session, snapshot_id: int) -> None:  # noqa: ANN001
    snapshot = get_snapshot(db, snapshot_id)
    path = _snapshot_dir() / snapshot.filename
    if path.is_file():
        path.unlink()
    db.delete(snapshot)
    db.flush()


def snapshot_detail(snapshot: SnapshotModel) -> dict:  # noqa: ANN001
    return {
        "id": snapshot.id,
        "name": snapshot.name,
        "created_at": snapshot.created_at,
        "counts": snapshot.decode(snapshot.counts_json) or {},
        "size_bytes": snapshot.size_bytes,
        "is_auto": snapshot.is_auto,
    }
