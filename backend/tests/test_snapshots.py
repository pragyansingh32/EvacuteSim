"""Restore-point tests: snapshot, drift, restore, auto-backup."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.db.session import session_scope
from app.repositories import buildings as building_repo
from app.services import snapshot_service


@pytest.fixture(scope="module", autouse=True)
def _db_ready():
    """Standalone runs need tables + samples before touching the DB."""
    from app.services.sample_data import seed_samples_once

    seed_samples_once()


def test_create_snapshot_counts_everything():
    with session_scope() as db:
        snap = snapshot_service.create_snapshot(db, "test point A")
        detail = snapshot_service.snapshot_detail(snap)
    assert detail["counts"]["buildings"] >= 2
    assert detail["counts"]["scenarios"] >= 5
    assert (Path(snapshot_service.SNAPSHOT_DIR) / snap.filename).is_file()


def test_restore_returns_workspace_to_snapshot_state():
    # 1. Snapshot the current state.
    with session_scope() as db:
        snap = snapshot_service.create_snapshot(db, "pre-drift")
        snap_id = snap.id
        before_names = [b.name for b in building_repo.list_buildings(db)]
        before_count = len(before_names)

    # 2. Drift: add a building.
    from app.simulation.grid import BuildingGrid

    with session_scope() as db:
        grid = BuildingGrid.from_dict(
            {
                "name": "Drift Building",
                "width": 8,
                "height": 4,
                "cell_size_m": 0.5,
                "walls": [[0, 0]],
                "exits": [{"id": "E", "x": 7, "y": 1, "capacity_pps": 1.0}],
                "zones": [],
            }
        )
        building_repo.create_building(db, grid, "drift")
    with session_scope() as db:
        assert "Drift Building" in [b.name for b in building_repo.list_buildings(db)]

    # 3. Restore.
    with session_scope() as db:
        snapshot_service.restore_snapshot(db, snap_id)
        db.commit()
    with session_scope() as db:
        after_restore = [b.name for b in building_repo.list_buildings(db)]
        assert "Drift Building" not in after_restore
        assert after_restore == before_names
        assert len(after_restore) == before_count

    # 4. The auto-backup captured the drifted state (nothing was lost).
    with session_scope() as db:
        autos = [s for s in snapshot_service.list_snapshots(db) if s.is_auto]
    assert autos, "restore must create an auto-backup first"
    with session_scope() as db:
        detail = snapshot_service.snapshot_detail(autos[0])
    assert detail["counts"]["buildings"] == before_count + 1


def test_cleanup_test_snapshots():
    with session_scope() as db:
        for s in snapshot_service.list_snapshots(db):
            snapshot_service.delete_snapshot(db, s.id)
        db.commit()
    # Also remove orphan files left by earlier failed runs (file written
    # before a rollback has no row).
    for orphan in Path(snapshot_service.SNAPSHOT_DIR).glob("snapshot-*.json"):
        orphan.unlink()
    assert list(Path(snapshot_service.SNAPSHOT_DIR).glob("snapshot-*.json")) == []
