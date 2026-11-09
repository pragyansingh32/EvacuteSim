"""API integration tests (Phases 5-6): buildings, scenarios, runs, comparison.

Uses the FastAPI TestClient against a throwaway SQLite database. The lifespan
hook seeds sample data, which the tests also verify.
"""

from __future__ import annotations

import pytest
from app.main import app
from fastapi.testclient import TestClient

BUILDING_A = {
    "name": "API Test Building",
    "description": "test",
    "width": 6,
    "height": 4,
    "cell_size_m": 0.5,
    "walls": [],
    "exits": [{"id": "E1", "x": 5, "y": 1, "capacity_pps": 1.0}],
    "zones": [{"id": "Z1", "name": "Left", "cells": [[0, 0], [0, 1], [0, 2], [0, 3]]}],
}

SCENARIO_BASE = {
    "zone_populations": {"Z1": 6},
    "speed": {"distribution": "uniform", "min": 1.0, "max": 1.0},
    "pre_movement": {"distribution": "uniform", "min": 0.0, "max": 2.0},
    "strategy": "nearest_exit",
    "seed": 5,
    "max_duration_s": 120.0,
    "dt_s": 0.25,
}


@pytest.fixture(scope="module")
def building_id(client) -> int:
    resp = client.post("/api/v1/buildings", json=BUILDING_A)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture(scope="module")
def scenario_id(client, building_id) -> int:
    resp = client.post(
        "/api/v1/scenarios",
        json={
            "building_id": building_id,
            "name": "API Test Scenario",
            "config": SCENARIO_BASE,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    def test_api_documentation_carries_disclaimer(self, client):
        """The disclaimer must be part of the API description regardless of
        whether the built frontend is being served at /."""
        openapi = client.get("/openapi.json").json()
        assert "certified fire-safety system" in openapi["info"]["description"].lower()


class TestBuildingEndpoints:
    def test_samples_are_seeded(self, client):
        resp = client.get("/api/v1/buildings")
        names = [b["name"] for b in resp.json()]
        assert "Sample Office A" in names
        assert "Sample Hall B" in names

    def test_create_and_get_building(self, client, building_id):
        resp = client.get(f"/api/v1/buildings/{building_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "API Test Building"
        assert body["exits"][0]["id"] == "E1"
        assert body["walls"] == []

    def test_invalid_building_rejected(self, client):
        bad = dict(BUILDING_A)
        bad["name"] = "No Exits"
        bad["exits"] = []
        resp = client.post("/api/v1/buildings", json=bad)
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_out_of_bounds_exit_rejected(self, client):
        bad = dict(BUILDING_A)
        bad["name"] = "Bad Exit"
        bad["exits"] = [{"id": "E1", "x": 99, "y": 99}]
        resp = client.post("/api/v1/buildings", json=bad)
        assert resp.status_code == 422
        assert "outside" in resp.json()["error"]["message"].lower()

    def test_malformed_body_rejected(self, client):
        resp = client.post("/api/v1/buildings", json={"width": "abc"})
        assert resp.status_code == 422
        error = resp.json()["error"]
        assert error["code"] == "request_validation_error"

    def test_validate_endpoint(self, client):
        resp = client.post("/api/v1/buildings/validate", json=BUILDING_A)
        assert resp.status_code == 200
        assert resp.json() == {"warnings": []}

    def test_404_for_missing_building(self, client):
        resp = client.get("/api/v1/buildings/99999")
        assert resp.status_code == 404

    def test_delete_building_in_use_conflicts(self, client, scenario_id):
        # The scenario references a building; deletion must be refused.
        resp = client.get("/api/v1/scenarios")
        scenario = next(s for s in resp.json() if s["id"] == scenario_id)
        resp = client.delete(f"/api/v1/buildings/{scenario['building_id']}")
        assert resp.status_code == 409


class TestScenarioEndpoints:
    def test_create_and_get(self, client, scenario_id):
        resp = client.get(f"/api/v1/scenarios/{scenario_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["config"]["strategy"] == "nearest_exit"
        assert body["config"]["speed"]["distribution"] == "uniform"

    def test_unknown_zone_rejected(self, client, building_id):
        bad = {"building_id": building_id, "name": "bad", "config": dict(SCENARIO_BASE, zone_populations={"NOPE": 5})}
        resp = client.post("/api/v1/scenarios", json=bad)
        assert resp.status_code == 422
        assert "unknown zone" in resp.json()["error"]["message"].lower()

    def test_unknown_strategy_rejected(self, client, building_id):
        bad = {"building_id": building_id, "name": "bad", "config": dict(SCENARIO_BASE, strategy="magic")}
        resp = client.post("/api/v1/scenarios", json=bad)
        assert resp.status_code == 422

    def test_all_exits_blocked_rejected(self, client, building_id):
        bad = {"building_id": building_id, "name": "bad", "config": dict(SCENARIO_BASE, blocked_exit_ids=["E1"])}
        resp = client.post("/api/v1/scenarios", json=bad)
        assert resp.status_code == 422
        assert "block every exit" in resp.json()["error"]["message"].lower()

    def test_dt_too_large_rejected(self, client, building_id):
        bad = {
            "building_id": building_id,
            "name": "bad",
            "config": dict(SCENARIO_BASE, dt_s=2.0),
        }
        resp = client.post("/api/v1/scenarios", json=bad)
        assert resp.status_code == 422
        assert "time step" in resp.json()["error"]["message"].lower()

    def test_sample_scenarios_seeded(self, client):
        resp = client.get("/api/v1/scenarios")
        names = [s["name"] for s in resp.json()]
        assert any("Sample: Baseline" in n for n in names)
        assert any("Sample: West exit blocked" in n for n in names)


class TestRunEndpoints:
    def test_synchronous_run(self, client, scenario_id):
        resp = client.post("/api/v1/runs", json={"scenario_id": scenario_id, "wait": True})
        assert resp.status_code == 201, resp.text
        run = resp.json()["run"]
        assert run["status"] == "completed"
        metrics = run["metrics"]
        assert metrics["total_occupants"] == 6
        assert metrics["evacuated_count"] == 6
        assert metrics["engine_status"] == "completed"
        # Mass balance via API
        assert (
            metrics["evacuated_count"]
            + metrics["unreachable_count"]
            + (metrics["incapacitated_count"] or 0)
            + metrics["remaining_count"]
            == metrics["total_occupants"]
        )
        # Frames are present for the live view
        assert len(run["frames"]) >= 2
        assert len(run["timeline"]) >= 2

    def test_async_run_lifecycle(self, client, scenario_id):
        resp = client.post("/api/v1/runs", json={"scenario_id": scenario_id})
        assert resp.status_code == 201
        run = resp.json()["run"]
        run_id = run["id"]
        assert run["status"] in ("pending", "running", "completed")
        # Poll until finished
        import time

        for _ in range(200):
            body = client.get(f"/api/v1/runs/{run_id}").json()
            if body["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert body["status"] == "completed"
        assert body["metrics"]["evacuated_count"] == 6

    def test_reproducibility_via_api(self, client, scenario_id):
        runs = []
        for _ in range(2):
            resp = client.post("/api/v1/runs", json={"scenario_id": scenario_id, "wait": True})
            runs.append(resp.json()["run"]["metrics"])
        assert runs[0]["t90_s"] == runs[1]["t90_s"]
        assert runs[0]["max_evacuation_time_s"] == runs[1]["max_evacuation_time_s"]

    def test_seed_override_changes_outcome_seed_only(self, client, scenario_id):
        resp = client.post(
            "/api/v1/runs",
            json={"scenario_id": scenario_id, "wait": True, "overrides": {"seed": 999}},
        )
        assert resp.status_code == 201
        assert resp.json()["run"]["seed"] == 999

    def test_api_result_matches_engine(self, client, scenario_id):
        """API results must agree with a direct engine run of the same config."""
        scenario = client.get(f"/api/v1/scenarios/{scenario_id}").json()
        resp = client.post("/api/v1/runs", json={"scenario_id": scenario_id, "wait": True})
        api_metrics = resp.json()["run"]["metrics"]

        from app.services.run_service import build_engine_config
        from app.simulation.engine import EvacuationEngine

        from tests.conftest import grid_from_rows

        cfg = build_engine_config(
            {
                **scenario["config"],
                "speed_distribution": scenario["config"]["speed"],
                "pre_movement_distribution": scenario["config"]["pre_movement"],
            }
        )
        building = client.get(f"/api/v1/buildings/{scenario['building_id']}").json()
        grid = grid_from_rows(
            rows=["." * building["width"] for _ in range(building["height"])],
            exits=building["exits"],
            zones=building["zones"],
        )
        direct = EvacuationEngine(grid, cfg).run()
        assert api_metrics["evacuated_count"] == direct.evacuated_count
        assert api_metrics["t90_s"] == direct.t90_s

    def test_failed_run_is_recorded(self, client, building_id):
        # Zone fully covered by blocked cells -> engine raises -> run failed.
        scenario = client.post(
            "/api/v1/scenarios",
            json={
                "building_id": building_id,
                "name": "Doomed",
                "config": dict(SCENARIO_BASE, blocked_cells=[[0, 0], [0, 1], [0, 2], [0, 3]]),
            },
        )
        assert scenario.status_code == 201
        sid = scenario.json()["id"]
        resp = client.post("/api/v1/runs", json={"scenario_id": sid, "wait": True})
        assert resp.status_code == 201  # run registered...
        run = resp.json()["run"]
        assert run["status"] == "failed"
        assert run["error"] is not None
        assert run["metrics"] is None

    def test_compare_runs(self, client, building_id, scenario_id):
        ids = []
        for strategy in ("nearest_exit", "balanced_assignment"):
            resp = client.post(
                "/api/v1/runs",
                json={
                    "scenario_id": scenario_id,
                    "wait": True,
                    "overrides": {"strategy": strategy},
                },
            )
            assert resp.status_code == 201, resp.text
            ids.append(resp.json()["run"]["id"])
        resp = client.post("/api/v1/compare", json={"run_ids": ids})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rows"]) == 2
        assert {r["strategy"] for r in body["rows"]} == {"nearest_exit", "balanced_assignment"}
        assert any("not certified" in n for n in body["notes"])

    def test_reproduce_run(self, client, scenario_id):
        first = client.post("/api/v1/runs", json={"scenario_id": scenario_id, "wait": True}).json()["run"]
        resp = client.post(f"/api/v1/runs/{first['id']}/reproduce")
        assert resp.status_code == 200, resp.text
        repro = resp.json()["run"]
        assert repro["status"] == "completed"
        assert repro["metrics"]["evacuated_count"] == first["metrics"]["evacuated_count"]


class TestPersistenceAcrossRestart:
    def test_data_survives_backend_restart(self, client, scenario_id):
        """Saved buildings, scenarios, and run results must survive a restart."""
        run = client.post("/api/v1/runs", json={"scenario_id": scenario_id, "wait": True}).json()["run"]
        first_scenario = client.get('/api/v1/scenarios').json()[0]
        before_building = client.get(f"/api/v1/buildings/{first_scenario['building_id']}").json()
        before_scenario = client.get(f"/api/v1/scenarios/{scenario_id}").json()

        # Simulate a backend restart: a fresh app instance with its lifespan,
        # against the same database file.
        with TestClient(app) as restarted:
            after_building = restarted.get(f"/api/v1/buildings/{before_building['id']}").json()
            after_scenario = restarted.get(f"/api/v1/scenarios/{scenario_id}").json()
            after_run = restarted.get(f"/api/v1/runs/{run['id']}").json()
            assert after_building["walls"] == before_building["walls"]
            assert after_scenario["config"] == before_scenario["config"]
            assert after_run["status"] == "completed"
            assert after_run["metrics"]["evacuated_count"] == run["metrics"]["evacuated_count"]
            # Samples must not be duplicated by re-seeding.
            names = [b["name"] for b in restarted.get("/api/v1/buildings").json()]
            assert names.count("Sample Office A") == 1


class TestBuildingUpdate:
    def test_update_walls_and_name(self, client, building_id):
        """Regression: PUT /buildings/{id} used to 500 (stray kwarg) - manual
        editing in the editor was impossible. Editing must work end to end."""
        detail = client.get(f"/api/v1/buildings/{building_id}").json()
        walls = [list(w) for w in detail["walls"]]
        walls.append([3, 1])
        resp = client.put(
            f"/api/v1/buildings/{building_id}",
            json={"name": "Edited Building", "walls": walls},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Edited Building"
        assert [3, 1] in [list(w) for w in body["walls"]]
        assert client.get(f"/api/v1/buildings/{building_id}").json()["walls"] == body["walls"]

    def test_update_rejects_invalid_layout(self, client, building_id):
        resp = client.put(
            f"/api/v1/buildings/{building_id}",
            json={"exits": []},  # a building cannot lose all exits
        )
        assert resp.status_code == 422

    def test_update_404_for_missing(self, client):
        resp = client.put("/api/v1/buildings/99999", json={"name": "nope"})
        assert resp.status_code == 404
