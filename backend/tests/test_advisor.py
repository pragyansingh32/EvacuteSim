"""Advisor rule tests: the expert system must flag the right problems and
produce appliable patches."""

from __future__ import annotations

from app.services.advisor_service import apply_patch, build_report


def base_metrics(**overrides):
    metrics = {
        "engine_status": "completed",
        "sim_time_s": 60.0,
        "total_occupants": 100,
        "evacuated_count": 100,
        "unreachable_count": 0,
        "remaining_count": 0,
        "t50_s": 30.0,
        "t90_s": 52.0,
        "queue_mean_s": 4.0,
        "queue_max_s": 12.0,
        "exit_stats": [
            {"id": "EA", "x": 0, "y": 3, "capacity_pps": 1.0, "evacuated": 50,
             "first_discharge_s": 5.0, "last_discharge_s": 55.0, "discharge_times": []},
            {"id": "EB", "x": 13, "y": 3, "capacity_pps": 1.0, "evacuated": 50,
             "first_discharge_s": 5.0, "last_discharge_s": 55.0, "discharge_times": []},
        ],
        "congestion": {},
        "warnings": [],
    }
    metrics.update(overrides)
    return metrics


def base_config(**overrides):
    config = {
        "strategy": "nearest_exit",
        "zone_populations": {"Z": 100},
        "speed_distribution": {"distribution": "uniform", "min": 1.0, "max": 1.0},
        "pre_movement_distribution": {"distribution": "uniform", "min": 0.0, "max": 5.0},
        "max_duration_s": 120.0,
        "seed": 1,
        "dt_s": 0.25,
    }
    config.update(overrides)
    return config


class TestRules:
    def test_healthy_run_gets_no_recommendation(self):
        report = build_report(base_metrics(), base_config())
        assert report["severity"] == "ok"
        assert report["recommendations"] == []
        assert any("Full evacuation" in o["title"] for o in report["observations"])

    def test_door_bottleneck_recommends_capacity(self):
        # Queue dominance: mean queue 30 s of a 60 s evacuation.
        metrics = base_metrics(
            queue_mean_s=30.0,
            queue_max_s=55.0,
            exit_stats=[
                {"id": "EA", "x": 0, "y": 3, "capacity_pps": 1.0, "evacuated": 100,
                 "discharge_times": []},
                {"id": "EB", "x": 13, "y": 3, "capacity_pps": 1.0, "evacuated": 0,
                 "discharge_times": []},
            ],
        )
        report = build_report(metrics, base_config())
        recs = {r["id"]: r for r in report["recommendations"]}
        assert "capacity_EA" in recs
        patch_cap = recs["capacity_EA"]["patch"]["exit_capacity_overrides"]["EA"]
        assert patch_cap > 1.0  # widened

    def test_exit_imbalance_recommends_strategy_switch(self):
        metrics = base_metrics(
            queue_mean_s=8.0,  # below the bottleneck trigger
            exit_stats=[
                {"id": "EA", "x": 0, "y": 3, "capacity_pps": 1.0, "evacuated": 95,
                 "discharge_times": []},
                {"id": "EB", "x": 13, "y": 3, "capacity_pps": 1.0, "evacuated": 5,
                 "discharge_times": []},
            ],
        )
        report = build_report(metrics, base_config())
        recs = {r["id"]: r for r in report["recommendations"]}
        assert recs["strategy"]["patch"]["strategy"] == "capacity_aware"

    def test_incomplete_low_queue_recommends_longer_horizon(self):
        metrics = base_metrics(
            engine_status="incomplete",
            evacuated_count=60,
            remaining_count=40,
            queue_mean_s=2.0,
        )
        report = build_report(metrics, base_config(max_duration_s=60.0))
        recs = {r["id"]: r for r in report["recommendations"]}
        assert "horizon" in recs
        assert recs["horizon"]["patch"]["max_duration_s"] > 60.0

    def test_incomplete_saturated_doors_recommends_total_capacity(self):
        metrics = base_metrics(
            engine_status="incomplete",
            evacuated_count=20,
            remaining_count=80,
            queue_mean_s=35.0,
            exit_stats=[
                {"id": "EA", "x": 0, "y": 3, "capacity_pps": 0.5, "evacuated": 15,
                 "discharge_times": []},
                {"id": "EB", "x": 13, "y": 3, "capacity_pps": 0.5, "evacuated": 5,
                 "discharge_times": []},
            ],
        )
        report = build_report(metrics, base_config(max_duration_s=60.0))
        recs = {r["id"]: r for r in report["recommendations"]}
        assert "capacity_all" in recs

    def test_unreachable_is_critical_with_no_capacity_fix(self):
        metrics = base_metrics(
            evacuated_count=90,
            unreachable_count=10,
            remaining_count=0,
        )
        report = build_report(metrics, base_config())
        assert report["severity"] == "critical"
        assert any("cannot reach any exit" in o["title"] for o in report["observations"])

    def test_long_pre_movement_recommends_tightening(self):
        metrics = base_metrics(t50_s=40.0)
        config = base_config(
            pre_movement_distribution={"distribution": "uniform", "min": 0.0, "max": 50.0}
        )
        report = build_report(metrics, config)
        recs = {r["id"]: r for r in report["recommendations"]}
        assert "pre_movement" in recs
        assert recs["pre_movement"]["patch"]["pre_movement_distribution"]["max"] == 25.0

    def test_congestion_near_door_recommends_widening(self):
        metrics = base_metrics(
            congestion={"6,3": 40},
            exit_stats=[
                {"id": "EA", "x": 5, "y": 3, "capacity_pps": 1.0, "evacuated": 100,
                 "discharge_times": []},
                {"id": "EB", "x": 13, "y": 3, "capacity_pps": 1.0, "evacuated": 0,
                 "discharge_times": []},
            ],
        )
        report = build_report(metrics, base_config())
        recs = {r["id"]: r for r in report["recommendations"]}
        assert "capacity_hotspot_EA" in recs


class TestApplyPatch:
    def test_capacity_merge(self):
        merged = apply_patch(
            base_config(exit_capacity_overrides={"EB": 2.0}),
            {"exit_capacity_overrides": {"EA": 1.5}},
        )
        assert merged["exit_capacity_overrides"] == {"EB": 2.0, "EA": 1.5}

    def test_nested_path_and_immutability(self):
        original = base_config()
        merged = apply_patch(original, {"pre_movement_distribution.max": 12.0})
        assert merged["pre_movement_distribution"]["max"] == 12.0
        assert original["pre_movement_distribution"]["max"] == 5.0  # source untouched
