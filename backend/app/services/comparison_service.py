"""Comparison service: compare completed runs on identical conditions."""

from app.repositories import runs as run_repo

# metric -> ("min"|"max") direction of "better"; None = informational only
METRIC_DIRECTIONS: dict[str, str | None] = {
    "sim_time_s": "min",
    "t50_s": "min",
    "t90_s": "min",
    "t95_s": "min",
    "max_evacuation_time_s": "min",
    "queue_mean_s": "min",
    "queue_max_s": "min",
    "evacuated_count": "max",
    "evacuated_pct": "max",
}

COMPARISON_NOTES = [
    "Comparisons reflect the simulation model's assumptions only, not certified "
    "safety guidance.",
    "Single-seed comparisons can differ from run to run; use an experiment with "
    "repeated seeds before drawing conclusions.",
    "All compared runs should share the same building snapshot and population; "
    "strategy differences are only meaningful under otherwise equal conditions.",
    "Runs are compared under the documented model simplifications (see "
    "docs/SIMULATION_MODEL.md).",
]


def compare_runs(db, run_ids: list[int]) -> dict:  # noqa: ANN001
    rows: list[dict] = []
    notes: list[str] = []
    for run_id in run_ids:
        run = run_repo.get_run(db, run_id)
        if run.status != "completed":
            notes.append(f"Run {run_id} ({run.name}) is {run.status} and excluded from verdicts.")
            continue
        metrics = _headline(run)
        rows.append(
            {
                "run_id": run.id,
                "name": run.name,
                "strategy": run.strategy,
                "seed": run.seed,
                "metrics": metrics,
            }
        )

    verdicts: dict[str, str] = {}
    for metric, direction in METRIC_DIRECTIONS.items():
        candidates = [(r["name"], r["metrics"].get(metric)) for r in rows]
        candidates = [(n, v) for n, v in candidates if v is not None]
        if not candidates:
            continue
        best_name, _ = (
            min(candidates, key=lambda p: p[1])
            if direction == "min"
            else max(candidates, key=lambda p: p[1])
        )
        # Only claim a verdict when the best is uniquely meaningful.
        values = [v for _, v in candidates]
        if len(set(values)) > 1:
            verdicts[metric] = best_name

    return {"rows": rows, "verdicts": verdicts, "notes": notes + COMPARISON_NOTES}


def _headline(run) -> dict:  # noqa: ANN001
    from app.services.run_service import run_metrics

    metrics = run_metrics(run) or {}
    out = dict(metrics)
    total = metrics.get("total_occupants")
    evac = metrics.get("evacuated_count")
    if total and evac is not None:
        out["evacuated_pct"] = round(100.0 * evac / total, 2)
    return out
