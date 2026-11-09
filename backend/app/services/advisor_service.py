"""Advisor: observes a completed run and proposes a better plan.

This is a **deterministic, rule-based expert system** - not a language model
and not an external API. Every observation cites recorded evidence (exit
utilization, queue times, congestion counts, mass balance), and every
recommendation carries a concrete, appliable configuration patch. The
"apply" step creates a scenario copy with the patch, runs the REAL simulation,
and reports before/after metrics - so a proposed plan is only ever claimed
better once the engine has actually demonstrated it.

Analysis rules (see docs/ALGORITHMS.md):
- door bottleneck:      queue time dominates → raise the loaded door's capacity
- exit imbalance:       one door saturated while a similar one idles → reroute
- horizon too short:    occupants remain with low queueing → extend horizon
- crowd oversubscribed: remaining people AND saturated doors → bigger door
- sealed areas:         unreachable occupants → layout repair (manual)
- congestion clusters:  blocked attempts concentrate near a door → widen it
- slow start:           pre-movement delay dominates → tighten it (drills)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SEVERITY_OK = "ok"
SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_CRITICAL = "critical"


@dataclass
class Observation:
    severity: str
    title: str
    detail: str
    evidence: dict = field(default_factory=dict)


@dataclass
class Recommendation:
    id: str
    title: str
    rationale: str
    patch: dict  # dot-path -> value, applied onto a copy of the run config
    patch_summary: str
    estimate: str


def _fmt(v: float | None, digits: int = 1) -> str:
    return "-" if v is None else f"{v:.{digits}f}"


def build_report(metrics: dict, config: dict) -> dict:
    """Pure analysis over recorded run metrics + scenario config.

    `metrics` is the run_metrics document; `config` uses the engine key names
    (speed_distribution / pre_movement_distribution). Returns observations and
    appliable recommendations.
    """
    observations: list[Observation] = []
    recommendations: list[Recommendation] = []

    total = int(metrics.get("total_occupants") or 0)
    evacuated = int(metrics.get("evacuated_count") or 0)
    remaining = int(metrics.get("remaining_count") or 0)
    unreachable = int(metrics.get("unreachable_count") or 0)
    sim_time = float(metrics.get("sim_time_s") or 0.0)
    queue_mean = float(metrics.get("queue_mean_s") or 0.0)
    queue_max = float(metrics.get("queue_max_s") or 0.0)
    exit_stats: list[dict] = metrics.get("exit_stats") or []
    congestion: dict[str, int] = metrics.get("congestion") or {}
    engine_status = metrics.get("engine_status")

    # ---- mass balance sanity (the advisor refuses to guess without it) ------
    if evacuated + remaining + unreachable != total:
        observations.append(
            Observation(
                SEVERITY_CRITICAL,
                "Mass balance violated",
                "Evacuated + remaining + unreachable does not equal the spawned "
                "population; this run's bookkeeping is inconsistent and no "
                "recommendation is made.",
                {"total": total, "evacuated": evacuated, "remaining": remaining,
                 "unreachable": unreachable},
            )
        )
        return _finalize(observations, recommendations)

    # ---- overall verdict ----------------------------------------------------
    if engine_status == "completed" and unreachable == 0:
        observations.append(
            Observation(
                SEVERITY_OK,
                "Full evacuation achieved",
                f"All {total} occupants evacuated in {_fmt(sim_time)} s "
                "(within the horizon).",
                {"sim_time_s": sim_time, "t90_s": metrics.get("t90_s")},
            )
        )
    elif unreachable > 0:
        observations.append(
            Observation(
                SEVERITY_CRITICAL,
                f"{unreachable} occupant(s) cannot reach any exit",
                "These occupants are walled or blocked off from every exit. No "
                "routing or capacity change can help them - the layout itself "
                "must be repaired in the editor (connect the area to a door or "
                "remove the blocking walls).",
                {"unreachable": unreachable},
            )
        )
    if remaining > 0:
        observations.append(
            Observation(
                SEVERITY_WARN,
                f"{remaining} occupant(s) still inside at the horizon",
                f"The simulation ended at {_fmt(sim_time)} s with people still "
                "inside: the design cannot clear the population within the "
                "configured time.",
                {"remaining": remaining, "horizon_s": config.get("max_duration_s")},
            )
        )

    # ---- exit utilization ---------------------------------------------------
    used = [e for e in exit_stats if e["evacuated"] > 0]
    if len(exit_stats) >= 2 and used:
        shares = {e["id"]: e["evacuated"] / evacuated for e in used}
        caps = {e["id"]: e["capacity_pps"] for e in exit_stats}
        busiest = max(shares, key=lambda k: shares[k])
        idlest = min(shares, key=lambda k: shares[k])
        total_cap = sum(caps.values())
        imbalance = shares[busiest] - caps[busiest] / total_cap
        if imbalance > 0.12:
            observations.append(
                Observation(
                    SEVERITY_WARN,
                    f"Exit '{busiest}' carries more than its capacity share",
                    f"'{busiest}' handled {shares[busiest]:.0%} of all evacuees "
                    f"but represents only {caps[busiest] / total_cap:.0%} of "
                    "total door capacity.",
                    {"shares": {k: round(v, 3) for k, v in shares.items()}},
                )
            )
            if shares[idlest] < 0.35 and shares[busiest] > 0.5:
                next_strategy = (
                    "capacity_aware" if config.get("strategy") == "nearest_exit"
                    else "balanced_assignment"
                )
                recommendations.append(
                    Recommendation(
                        "strategy",
                        f"Switch routing to '{next_strategy}'",
                        f"'{busiest}' is overloaded while '{idlest}' is barely "
                        "used. A routing strategy that weighs door load should "
                        "push latecomers to the quieter exit.",
                        {"strategy": next_strategy},
                        f"strategy → {next_strategy}",
                        f"expected: better door balance; less queueing at '{busiest}'",
                    )
                )

    # ---- door bottleneck (queue dominance) ----------------------------------
    if sim_time > 0 and queue_mean > 0.2 * sim_time and used:
        busiest = max(exit_stats, key=lambda e: e["evacuated"])
        cap = busiest["capacity_pps"]
        # Capacity needed so the busiest door clears its share in 75% of the
        # current total time.
        target_time = sim_time * 0.75
        needed = (busiest["evacuated"] / target_time) if target_time > 0 else cap
        new_cap = max(cap, math.ceil(needed * 4) / 4)  # 0.25 granularity
        if new_cap > cap * 1.05:
            recommendations.append(
                Recommendation(
                    f"capacity_{busiest['id']}",
                    f"Widen exit '{busiest['id']}': {cap} → {new_cap} p/s",
                    f"Mean queue time is {_fmt(queue_mean)} s (max {_fmt(queue_max)} s) "
                    f"- occupants spend most of the evacuation standing in line at "
                    f"'{busiest['id']}'. More door capacity converts queue time "
                    "into walking time.",
                    {"exit_capacity_overrides": {busiest["id"]: new_cap}},
                    f"exit {busiest['id']}: {cap} → {new_cap} p/s",
                    f"estimate: total time could drop toward ~{total / new_cap + 2:.0f} s "
                    "(travel + discharge); the test-run below measures it precisely",
                )
            )

    # ---- horizon too short (incomplete with low queueing) -------------------
    if remaining > 0 and sim_time > 0 and queue_mean <= 0.2 * sim_time:
        new_horizon = math.ceil(sim_time * 1.75 / 5) * 5
        recommendations.append(
            Recommendation(
                "horizon",
                f"Extend the horizon to {new_horizon} s",
                f"{remaining} occupant(s) were still walking when the horizon "
                f"ended (queueing is not the bottleneck: mean queue "
                f"{_fmt(queue_mean)} s). A longer simulated window lets them "
                "finish; check whether that horizon is acceptable for the "
                "building's use case.",
                {"max_duration_s": float(new_horizon)},
                f"max_duration_s → {new_horizon}",
                "expected: everyone out if travel time is the only limit",
            )
        )

    # ---- crowd oversubscribed (incomplete AND saturated door) ---------------
    if remaining > 0 and sim_time > 0 and queue_mean > 0.2 * sim_time and exit_stats:
        total_cap = sum(e["capacity_pps"] for e in exit_stats)
        needed_total = total / (0.9 * config.get("max_duration_s", sim_time))
        if needed_total > total_cap:
            recommendations.append(
                Recommendation(
                    "capacity_all",
                    f"Raise total door capacity: {total_cap} → "
                    f"{math.ceil(needed_total * 4) / 4} p/s",
                    f"{total} people cannot clear through {total_cap} p/s in "
                    f"{_fmt(config.get('max_duration_s'))} s. The scenario needs "
                    "physically more egress (wider doors, additional exits) - "
                    "or a longer acceptable evacuation time.",
                    {
                        "exit_capacity_overrides": {
                            e["id"]: math.ceil(e["capacity_pps"] * needed_total / total_cap * 4) / 4
                            for e in exit_stats
                        }
                    },
                    f"all doors scaled ×{needed_total / total_cap:.2f}",
                    "estimate: near-full evacuation within the horizon; verified by test run",
                )
            )

    # ---- congestion clusters ------------------------------------------------
    if congestion:
        top_cells = sorted(congestion.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top_cell, top_count = top_cells[0]
        if total and top_count > 0.25 * total and exit_stats:
            x, y = (int(v) for v in top_cell.split(","))
            nearest = min(
                exit_stats,
                key=lambda e: abs(e["x"] - x) + abs(e["y"] - y),
            )
            dist = abs(nearest["x"] - x) + abs(nearest["y"] - y)
            if dist <= 4:
                cap = nearest["capacity_pps"]
                new_cap = math.ceil(cap * 1.5 * 4) / 4
                recommendations.append(
                    Recommendation(
                        f"capacity_hotspot_{nearest['id']}",
                        f"Widen exit '{nearest['id']}': {cap} → {new_cap} p/s",
                        f"The worst congestion cluster ({top_count} blocked "
                        f"attempts at cell ({x}, {y})) sits within {dist} cells "
                        f"of '{nearest['id']}' - that door is the local "
                        "bottleneck.",
                        {"exit_capacity_overrides": {nearest["id"]: new_cap}},
                        f"exit {nearest['id']}: {cap} → {new_cap} p/s",
                        "expected: less blocking around the hotspot",
                    )
                )
            else:
                observations.append(
                    Observation(
                        SEVERITY_INFO,
                        "Congestion cluster away from any door",
                        f"The worst cluster ({top_count} blocked attempts at "
                        f"({x}, {y})) is not near an exit - likely a narrow "
                        "corridor or junction. Consider widening that passage "
                        "in the editor.",
                        {"cell": top_cell, "blocked_attempts": top_count},
                    )
                )
        observations.append(
            Observation(
                SEVERITY_INFO,
                "Congestion hotspots",
                "Cells with the most blocked movement attempts (operational "
                "queueing indicator, not a density measure): "
                + ", ".join(f"({c}) ×{n}" for c, n in top_cells),
                {"top": top_cells},
            )
        )

    # ---- pre-movement dominance ---------------------------------------------
    pre = config.get("pre_movement_distribution") or {}
    pre_max = float(pre.get("max") or 0)
    t50 = metrics.get("t50_s")
    if pre_max >= 20 and t50 and t50 > 0.6 * pre_max:
        recommendations.append(
            Recommendation(
                "pre_movement",
                f"Tighten pre-movement delay: max {pre_max} → {max(5.0, pre_max * 0.5)} s",
                "Occupants spend a large share of the evacuation simply reacting. "
                "Half the maximum delay models better drill readiness or "
                "notification systems - a behavior assumption, not a building "
                "change, so treat the effect as a sensitivity result.",
                {"pre_movement_distribution": {**pre, "max": max(5.0, pre_max * 0.5)}},
                f"pre-movement max → {max(5.0, pre_max * 0.5)} s",
                "expected: earlier movement start; T50/T90 shift down",
            )
        )

    # ---- all-clear ----------------------------------------------------------
    if not recommendations:
        observations.append(
            Observation(
                SEVERITY_OK,
                "No clear weakness detected",
                "Exit loads are balanced relative to capacity, queueing is not "
                "dominant, and everyone (reachable) got out within the horizon. "
                "Use Experiments to explore sensitivities instead of chasing a "
                "single-metric improvement.",
                {},
            )
        )

    return _finalize(observations, recommendations)


def _finalize(observations: list[Observation], recommendations: list[Recommendation]) -> dict:
    worst = SEVERITY_OK
    for sev in (SEVERITY_CRITICAL, SEVERITY_WARN, SEVERITY_INFO):
        if any(o.severity == sev for o in observations):
            worst = sev
            break
    verdict = {
        SEVERITY_OK: "Efficient evacuation - no design change indicated.",
        SEVERITY_INFO: "Evacuation works; some characteristics worth reviewing.",
        SEVERITY_WARN: "Measurable inefficiencies found - recommendations below.",
        SEVERITY_CRITICAL: "Serious problems found - occupants could not evacuate.",
    }[worst]
    return {
        "verdict": verdict,
        "severity": worst,
        "observations": [
            {
                "severity": o.severity,
                "title": o.title,
                "detail": o.detail,
                "evidence": o.evidence,
            }
            for o in observations
        ],
        "recommendations": [
            {
                "id": r.id,
                "title": r.title,
                "rationale": r.rationale,
                "patch": r.patch,
                "patch_summary": r.patch_summary,
                "estimate": r.estimate,
            }
            for r in recommendations
        ],
        "disclaimer": (
            "Rule-based analysis of the recorded run - deterministic and "
            "explainable, no language model. Recommendations are model-level "
            "suggestions; each must be validated by a test run before you rely "
            "on it, and none of this is certified safety guidance."
        ),
    }


def apply_patch(config: dict, patch: dict) -> dict:
    """Apply a recommendation patch (dot-paths) onto a deep copy of a config."""
    import copy

    merged = copy.deepcopy(config)

    def set_path(node: dict, path: str, value) -> None:  # noqa: ANN001
        parts = path.split(".")
        target = node
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value

    for path, value in patch.items():
        if path == "exit_capacity_overrides":
            node = merged.setdefault("exit_capacity_overrides", {})
            for exit_id, cap in value.items():
                node[exit_id] = cap
        else:
            set_path(merged, path, value)
    return merged
