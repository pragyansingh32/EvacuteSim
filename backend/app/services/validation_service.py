"""Known-answer validation battery.

A set of building designs whose correct evacuation outcome is KNOWN in advance
by construction (sealed rooms, blocked exits, doors too small for the crowd,
distances longer than the horizon, adequate designs). The battery runs every
case through the real engine and checks whether the system classifies it
correctly - this is the project's own accuracy measurement, surfaced in the UI
on the Accuracy page.

Expectations are derived analytically:
- travel lower bound:  distance_cells * cell_size / speed
- door lower bound:    population / capacity (persons per second)
A design PASSes only if everyone evacuates within the horizon; it FAILs when
geometry or capacity makes that impossible. The battery asserts the system
reports exactly that - no more, no less.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.simulation.engine import ENGINE_VERSION, EngineConfig, EvacuationEngine
from app.simulation.grid import BuildingGrid


def grid_from_ascii(rows: list[str], exits: list[dict], zones: list[dict]) -> BuildingGrid:
    height, width = len(rows), len(rows[0])
    assert all(len(r) == width for r in rows), "battery grid rows must be rectangular"
    walls = [[x, y] for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "#"]
    return BuildingGrid.from_dict(
        {
            "name": "battery",
            "width": width,
            "height": height,
            "cell_size_m": 0.5,
            "walls": walls,
            "exits": exits,
            "zones": zones,
        }
    )


def config(**overrides) -> EngineConfig:
    base: dict = {
        "strategy": "nearest_exit",
        "zone_populations": {"Z": 10},
        "speed_distribution": {"distribution": "uniform", "min": 1.0, "max": 1.0},
        "pre_movement_distribution": {"distribution": "uniform", "min": 0.0, "max": 0.0},
        "seed": 7,
        "max_duration_s": 120.0,
        "dt_s": 0.25,
        "frame_interval_s": 5.0,
        "record_frames": False,
    }
    base.update(overrides)
    return EngineConfig(**base)


@dataclass
class CaseResult:
    name: str
    category: str  # pass | fail | accuracy
    description: str
    expected: str
    passed: bool
    actual: str
    evidence: dict = field(default_factory=dict)


def _summarize(result) -> dict:  # noqa: ANN001
    return {
        "engine_status": result.status,
        "evacuated": result.evacuated_count,
        "remaining": result.remaining_count,
        "unreachable": result.unreachable_count,
        "total": result.total_occupants,
        "sim_time_s": result.sim_time_s,
        "t90_s": result.t90_s,
        "queue_mean_s": result.queue_mean_s,
        "exit_evacuated": {e["id"]: e["evacuated"] for e in result.exit_stats},
    }


# ---------------------------------------------------------------------------
# PASS cases: adequate designs must evacuate everyone within the horizon.
# ---------------------------------------------------------------------------

def case_single_exit_room() -> CaseResult:
    grid = grid_from_ascii(
        [
            "########",
            "#......#",
            "#......#",
            "#......E",
            "#......#",
            "########",
        ],
        [{"id": "E", "x": 7, "y": 3, "capacity_pps": 1.0}],
        [{"id": "Z", "name": "Room", "cells": [[1, 1], [1, 2], [1, 3], [1, 4], [2, 2], [2, 3]]}],
    )
    result = EvacuationEngine(grid, config(zone_populations={"Z": 8}, max_duration_s=90)).run()
    passed = result.status == "completed" and result.evacuated_count == result.total_occupants
    return CaseResult(
        "Adequate room, single exit",
        "pass",
        "8 occupants, one 1.0 p/s door, plenty of time.",
        "Everyone evacuates; status completed.",
        passed,
        f"engine={result.status}, evacuated {result.evacuated_count}/{result.total_occupants}",
        _summarize(result),
    )


def case_two_exits_crowd() -> CaseResult:
    grid = grid_from_ascii(
        [
            "##############",
            "#............#",
            "#............#",
            "E............E",
            "#............#",
            "#............#",
            "#............#",
            "##############",
        ],
        [
            {"id": "EA", "x": 0, "y": 3, "capacity_pps": 1.0},
            {"id": "EB", "x": 13, "y": 3, "capacity_pps": 1.0},
        ],
        [{"id": "Z", "name": "Hall", "cells": [[x, y] for x in range(2, 12) for y in range(1, 7)]}],
    )
    result = EvacuationEngine(
        grid, config(zone_populations={"Z": 40}, max_duration_s=180, strategy="capacity_aware")
    ).run()
    passed = result.status == "completed" and result.evacuated_count == 40
    both_used = sum(1 for e in result.exit_stats if e["evacuated"] > 0) >= 2
    return CaseResult(
        "Two exits, 40 occupants",
        "pass",
        "Crowd of 40 with two doors and capacity-aware routing.",
        "Everyone evacuates; both doors carry people.",
        passed and both_used,
        f"engine={result.status}, evacuated {result.evacuated_count}/40, doors used: "
        + ", ".join(f"{e['id']}={e['evacuated']}" for e in result.exit_stats),
        _summarize(result),
    )


def case_corridor_adequate() -> CaseResult:
    grid = grid_from_ascii(
        [
            "####################",
            "#..................E",
            "####################",
            "####################",
        ],
        [{"id": "E", "x": 19, "y": 1, "capacity_pps": 1.0}],
        [{"id": "Z", "name": "Far end", "cells": [[1, 1], [2, 1], [3, 1]]}],
    )
    result = EvacuationEngine(grid, config(zone_populations={"Z": 6}, max_duration_s=60)).run()
    passed = result.status == "completed" and result.evacuated_count == 6
    return CaseResult(
        "Corridor with adequate door",
        "pass",
        "6 people, 18-cell corridor, 1.0 p/s door (needs ~9 s travel + 6 s door).",
        "Everyone evacuates within 60 s.",
        passed,
        f"engine={result.status}, evacuated {result.evacuated_count}/6 in {result.sim_time_s} s",
        _summarize(result),
    )


def case_blocked_exit_alternative() -> CaseResult:
    grid = grid_from_ascii(
        [
            "##############",
            "#............#",
            "#............#",
            "E............E",
            "#............#",
            "##############",
        ],
        [
            {"id": "EA", "x": 0, "y": 3, "capacity_pps": 1.0},
            {"id": "EB", "x": 13, "y": 3, "capacity_pps": 1.0},
        ],
        [{"id": "Z", "name": "Hall", "cells": [[x, y] for x in range(2, 12) for y in range(1, 5)]}],
    )
    result = EvacuationEngine(
        grid, config(zone_populations={"Z": 20}, blocked_exit_ids={"EA"}, max_duration_s=180)
    ).run()
    stats = {e["id"]: e["evacuated"] for e in result.exit_stats}
    passed = (
        result.status == "completed"
        and result.evacuated_count == 20
        and "EA" not in stats
        and stats.get("EB", 0) == 20
    )
    return CaseResult(
        "Blocked exit, alternative exists",
        "pass",
        "Exit EA unavailable; everyone must use EB.",
        "Everyone evacuates through EB; EA never used.",
        passed,
        f"engine={result.status}, discharged per exit: {stats}",
        _summarize(result),
    )


def case_slow_occupants_generous() -> CaseResult:
    grid = grid_from_ascii(
        [
            "########",
            "#......#",
            "#......E",
            "#......#",
            "########",
        ],
        [{"id": "E", "x": 7, "y": 2, "capacity_pps": 1.0}],
        [{"id": "Z", "name": "Room", "cells": [[1, 1], [1, 2], [1, 3], [2, 2]]}],
    )
    result = EvacuationEngine(
        grid,
        config(
            zone_populations={"Z": 4},
            speed_distribution={"distribution": "uniform", "min": 0.4, "max": 0.6},
            max_duration_s=120,
        ),
    ).run()
    passed = result.status == "completed" and result.evacuated_count == 4
    return CaseResult(
        "Slow occupants, sufficient horizon",
        "pass",
        "4 slow occupants (0.4-0.6 m/s); horizon is generous.",
        "Everyone evacuates; slow speed affects timing, not the outcome.",
        passed,
        f"engine={result.status}, evacuated {result.evacuated_count}/4 in {result.sim_time_s} s",
        _summarize(result),
    )


# ---------------------------------------------------------------------------
# FAIL cases: the system must report these designs do NOT evacuate.
# ---------------------------------------------------------------------------

def case_sealed_zone() -> CaseResult:
    grid = grid_from_ascii(
        [
            "########",
            "#......#",
            "#......#",
            "#.####.#",
            "#.#..#.E",
            "#.####.#",
            "#......#",
            "########",
        ],
        [{"id": "E", "x": 7, "y": 4, "capacity_pps": 1.0}],
        [{"id": "Z", "name": "Sealed pocket", "cells": [[3, 4], [4, 4]]}],
    )
    result = EvacuationEngine(grid, config(zone_populations={"Z": 2}, max_duration_s=60)).run()
    passed = (
        result.unreachable_count == 2
        and result.evacuated_count == 0
        and result.total_occupants == 2
    )
    return CaseResult(
        "Sealed room (no path out)",
        "fail",
        "Two occupants are walled in with no route to any exit.",
        "System marks both unreachable and loses nobody.",
        passed,
        f"unreachable={result.unreachable_count}, evacuated={result.evacuated_count}, "
        f"total={result.total_occupants}",
        _summarize(result),
    )


def case_all_exits_blocked() -> CaseResult:
    grid = grid_from_ascii(
        [
            "########",
            "E......#",
            "#......#",
            "########",
        ],
        [{"id": "E", "x": 0, "y": 1, "capacity_pps": 1.0}],
        [{"id": "Z", "name": "Room", "cells": [[2, 1], [3, 1], [2, 2], [3, 2]]}],
    )
    try:
        result = EvacuationEngine(
            grid, config(zone_populations={"Z": 2}, blocked_exit_ids={"E"})
        ).run()
        passed = False
        actual = f"engine ran and returned {result.status} - it should have refused"
        evidence = _summarize(result)
    except Exception as exc:  # noqa: BLE001 - any refusal counts, message checked
        message = str(exc).lower()
        passed = "exit" in message
        actual = f"refused to run: {exc}"
        evidence = {"error": str(exc)}
    return CaseResult(
        "Every exit blocked",
        "fail",
        "Scenario blocks the only exit.",
        "System refuses to simulate with a clear error (no fake success).",
        passed,
        actual,
        evidence,
    )


def case_insufficient_door_capacity() -> CaseResult:
    grid = grid_from_ascii(
        [
            "##############################",
            "#............................#",
            "#............................#",
            "#............................E",
            "#............................#",
            "#............................#",
            "##############################",
        ],
        [{"id": "E", "x": 29, "y": 3, "capacity_pps": 0.25}],
        [{"id": "Z", "name": "Dense hall", "cells": [[x, y] for x in range(2, 28) for y in range(1, 6)]}],
    )
    result = EvacuationEngine(
        grid, config(zone_populations={"Z": 120}, max_duration_s=60)
    ).run()
    # 60 s at 0.25 p/s discharges at most ~16 people; the rest remain inside.
    passed = (
        result.status == "incomplete"
        and result.remaining_count >= 90
        and result.evacuated_count <= 20
    )
    return CaseResult(
        "Door too small for the crowd",
        "fail",
        "120 occupants, one 0.25 p/s door, 60 s horizon. Physics: at most ~16 can leave.",
        "Simulation ends incomplete with 90+ people still inside.",
        passed,
        f"engine={result.status}, evacuated {result.evacuated_count}, "
        f"remaining {result.remaining_count}",
        _summarize(result),
    )


def case_distance_exceeds_horizon() -> CaseResult:
    grid = grid_from_ascii(
        [
            "##################################################",
            "#................................................E",
            "#................................................#",
            "##################################################",
        ],
        [{"id": "E", "x": 49, "y": 1, "capacity_pps": 1.0}],
        [{"id": "Z", "name": "Far end", "cells": [[1, 1]]}],
    )
    result = EvacuationEngine(grid, config(zone_populations={"Z": 1}, max_duration_s=20)).run()
    # 48 cells * 0.5 m at 1 m/s = 24 s of walking; the horizon is only 20 s.
    passed = (
        result.status == "incomplete"
        and result.remaining_count == 1
        and result.evacuated_count == 0
    )
    return CaseResult(
        "Exit unreachable within the horizon",
        "fail",
        "Single occupant 24 walking-s away; simulation horizon is 20 s.",
        "Simulation ends incomplete; the occupant is still inside.",
        passed,
        f"engine={result.status}, remaining={result.remaining_count}, sim_time={result.sim_time_s} s",
        _summarize(result),
    )


def case_crowd_crush_queue() -> CaseResult:
    grid = grid_from_ascii(
        [
            "####################",
            "#..................#",
            "#..................#",
            "#..................E",
            "#..................#",
            "####################",
        ],
        [{"id": "E", "x": 19, "y": 3, "capacity_pps": 0.5}],
        [{"id": "Z", "name": "Crowd", "cells": [[x, y] for x in range(1, 19) for y in range(1, 5)]}],
    )
    result = EvacuationEngine(
        grid, config(zone_populations={"Z": 60}, max_duration_s=40)
    ).run()
    # 40 s at 0.5 p/s = ~21 discharges; heavy queueing must be visible.
    queue_visible = (result.queue_mean_s or 0) > 5.0
    passed = (
        result.status == "incomplete"
        and result.remaining_count >= 35
        and queue_visible
    )
    return CaseResult(
        "Crowd crush at a narrow door",
        "fail",
        "60 occupants through one 0.5 p/s door in 40 s; only ~20 can leave.",
        "Incomplete outcome AND reported queueing (mean blocked time > 5 s).",
        passed,
        f"engine={result.status}, remaining {result.remaining_count}, "
        f"mean queue {result.queue_mean_s and round(result.queue_mean_s, 1)} s",
        _summarize(result),
    )


# ---------------------------------------------------------------------------
# ACCURACY cases: quantitative checks against analytical bounds.
# ---------------------------------------------------------------------------

def case_throughput_lower_bound() -> CaseResult:
    grid = grid_from_ascii(
        [
            "###############",
            "#.............#",
            "#.............E",
            "#.............#",
            "###############",
        ],
        [{"id": "E", "x": 14, "y": 2, "capacity_pps": 0.5}],
        [{"id": "Z", "name": "Room", "cells": [[x, y] for x in range(1, 14) for y in range(1, 4)]}],
    )
    result = EvacuationEngine(
        grid, config(zone_populations={"Z": 20}, max_duration_s=300)
    ).run()
    first = min(e["first_discharge_s"] for e in result.exit_stats if e["discharge_times"])
    last = max(e["last_discharge_s"] for e in result.exit_stats if e["discharge_times"])
    # 20 people at 0.5 p/s need >= 19 intervals of 2 s between first and last.
    bound = (20 - 1) / 0.5
    spread = last - first
    passed = result.evacuated_count == 20 and spread >= bound - 0.25
    return CaseResult(
        "Door throughput lower bound",
        "accuracy",
        "20 occupants through one 0.5 p/s door: last-first discharge must be >= 38 s.",
        "Measured discharge spread respects the analytic throughput bound.",
        passed,
        f"discharge spread {spread:.2f} s vs bound {bound:.2f} s",
        {"spread_s": spread, "bound_s": bound, **_summarize(result)},
    )


def case_travel_lower_bound() -> CaseResult:
    grid = grid_from_ascii(
        [
            "############",
            "#..........E",
            "#..........#",
            "############",
        ],
        [{"id": "E", "x": 11, "y": 1, "capacity_pps": 5.0}],
        [{"id": "Z", "name": "Start", "cells": [[1, 1]]}],
    )
    result = EvacuationEngine(grid, config(zone_populations={"Z": 1}, max_duration_s=60)).run()
    distance_cells = 10  # (1,1) -> (11,1)
    bound = distance_cells * 0.5 / 1.0
    evac_t = result.max_evacuation_time_s or 0.0
    passed = result.evacuated_count == 1 and evac_t >= bound - 0.25
    return CaseResult(
        "Travel-time lower bound",
        "accuracy",
        "One occupant 10 cells away at 1 m/s on 0.5 m cells: needs >= 5.0 s.",
        "Recorded evacuation time is never faster than physics allows.",
        passed,
        f"evacuated at {evac_t:.2f} s vs bound {bound:.2f} s",
        {"evacuation_time_s": evac_t, "bound_s": bound, **_summarize(result)},
    )


def case_population_monotonicity() -> CaseResult:
    grid = grid_from_ascii(
        [
            "##############################",
            "#............................E",
            "#............................#",
            "##############################",
        ],
        [{"id": "E", "x": 29, "y": 1, "capacity_pps": 1.0}],
        [{"id": "Z", "name": "Room", "cells": [[x, y] for x in range(1, 29) for y in (1, 2)]}],
    )
    times = []
    for population in (10, 20, 40):
        result = EvacuationEngine(
            grid, config(zone_populations={"Z": population}, max_duration_s=600)
        ).run()
        times.append(round(result.sim_time_s, 3))
    passed = times[0] < times[1] < times[2]
    return CaseResult(
        "More people -> longer evacuation",
        "accuracy",
        "Same room with 10 / 20 / 40 occupants, one 1.0 p/s door.",
        "Evacuation time strictly increases with population.",
        passed,
        f"times for 10/20/40: {times}",
        {"times_s": times},
    )


def case_reproducibility() -> CaseResult:
    grid = grid_from_ascii(
        [
            "##############",
            "#............#",
            "E............E",
            "#............#",
            "##############",
        ],
        [
            {"id": "EA", "x": 0, "y": 2, "capacity_pps": 1.0},
            {"id": "EB", "x": 13, "y": 2, "capacity_pps": 1.0},
        ],
        [{"id": "Z", "name": "Hall", "cells": [[x, y] for x in range(2, 12) for y in range(1, 4)]}],
    )
    cfg = config(
        zone_populations={"Z": 24}, strategy="balanced_assignment", seed=42, max_duration_s=300
    )
    r1 = EvacuationEngine(grid, cfg).run().to_dict()
    r2 = EvacuationEngine(grid, cfg).run().to_dict()
    r1.pop("wall_time_ms")
    r2.pop("wall_time_ms")
    passed = r1 == r2
    return CaseResult(
        "Same seed -> identical result",
        "accuracy",
        "Run the same 24-occupant balanced-assignment scenario twice with seed 42.",
        "Both runs produce identical results documents.",
        passed,
        "identical" if passed else "results differ between runs",
        {"t90_s": r1.get("t90_s"), "evacuated": r1.get("evacuated_count")},
    )


def run_battery() -> dict:
    """Execute every case and return verdicts plus overall accuracy."""
    cases: list[CaseResult] = []
    builders: list[tuple[str, Callable[[], CaseResult]]] = [
        ("Adequate room, single exit", case_single_exit_room),
        ("Two exits, 40 occupants", case_two_exits_crowd),
        ("Corridor with adequate door", case_corridor_adequate),
        ("Blocked exit, alternative exists", case_blocked_exit_alternative),
        ("Slow occupants, sufficient horizon", case_slow_occupants_generous),
        ("Sealed room (no path out)", case_sealed_zone),
        ("Every exit blocked", case_all_exits_blocked),
        ("Door too small for the crowd", case_insufficient_door_capacity),
        ("Exit unreachable within the horizon", case_distance_exceeds_horizon),
        ("Crowd crush at a narrow door", case_crowd_crush_queue),
        ("Door throughput lower bound", case_throughput_lower_bound),
        ("Travel-time lower bound", case_travel_lower_bound),
        ("More people -> longer evacuation", case_population_monotonicity),
        ("Same seed -> identical result", case_reproducibility),
    ]
    for name, fn in builders:
        try:
            cases.append(fn())
        except Exception as exc:  # noqa: BLE001 - a crashing case is itself a finding
            cases.append(
                CaseResult(
                    name=name,
                    category="accuracy",
                    description="Case raised an unexpected exception.",
                    expected="clean execution",
                    passed=False,
                    actual=f"exception: {exc}",
                    evidence={"error": str(exc)},
                )
            )
    passed = sum(1 for c in cases if c.passed)
    total = len(cases)
    return {
        "engine_version": ENGINE_VERSION,
        "ran_cases": total,
        "passed": passed,
        "failed": total - passed,
        "accuracy_pct": round(100.0 * passed / total, 1) if total else 0.0,
        "cases": [
            {
                "name": c.name,
                "category": c.category,
                "description": c.description,
                "expected": c.expected,
                "passed": c.passed,
                "actual": c.actual,
                "evidence": c.evidence,
            }
            for c in cases
        ],
        "notes": [
            "Expected outcomes are derived analytically from geometry and door "
            "capacity, then compared with what the system reported.",
            "This battery validates the SYSTEM's classification of designs, not "
            "real-world safety.",
        ],
    }
