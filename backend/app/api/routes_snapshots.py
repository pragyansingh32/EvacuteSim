"""Restore-point endpoints."""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbSession
from app.services import snapshot_service

router = APIRouter(prefix="/restore-points", tags=["restore-points"])


class SnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


@router.get("")
def list_restore_points(db: DbSession) -> list[dict]:
    return [snapshot_service.snapshot_detail(s) for s in snapshot_service.list_snapshots(db)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_restore_point(payload: SnapshotCreate, db: DbSession) -> dict:
    snapshot = snapshot_service.create_snapshot(db, payload.name)
    db.commit()
    return snapshot_service.snapshot_detail(snapshot)


@router.get("/{snapshot_id}")
def get_restore_point(snapshot_id: int, db: DbSession) -> dict:
    return snapshot_service.snapshot_detail(snapshot_service.get_snapshot(db, snapshot_id))


@router.post("/{snapshot_id}/restore")
def restore(snapshot_id: int, db: DbSession) -> dict:
    result = snapshot_service.restore_snapshot(db, snapshot_id)
    db.commit()
    return result


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(snapshot_id: int, db: DbSession) -> Response:
    snapshot_service.delete_snapshot(db, snapshot_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
