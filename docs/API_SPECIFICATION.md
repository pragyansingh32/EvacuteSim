# API Specification

Base URL: `http://127.0.0.1:8000/api/v1` — versioned prefix `/api/v1`.
Interactive docs: `http://127.0.0.1:8000/docs` (OpenAPI 3, generated from code).

All errors use one envelope:

```json
{ "error": { "code": "<machine_code>", "message": "<human message>" } }
```

`422 request_validation_error` adds `details[]` with field locations. Internal
failures return opaque `500 internal_error` (details only in server logs).

## Health

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness/readiness: `{status, app, api_version}` |

## Buildings

Layout document shape: `{name, width, height, cell_size_m, walls: [[x,y]…],
exits: [{id, x, y, capacity_pps}…], zones: [{id, name, cells: [[x,y]…]}…]}`.
Grids must be ≥ 4×4 and ≤ 120×120; ≥ 1 exit; zone cells on floor; duplicate
ids rejected. Responses include validation `warnings` (e.g. unreachable
pockets) — warnings do not block saving.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/buildings` | List summaries |
| POST | `/buildings` | Create (validates; 422 on invalid; 201 + detail) |
| POST | `/buildings/validate` | Validate without saving → `{warnings}` |
| GET | `/buildings/{id}` | Full detail incl. walls/exits/zones/warnings |
| PUT | `/buildings/{id}` | Update (merged layout revalidated) |
| DELETE | `/buildings/{id}` | Delete; **409** if scenarios reference it |

## Scenarios

Config shape (see `ScenarioConfigSchema`):

```json
{
  "zone_populations": {"ZW": 50, "ZH": 20, "ZE": 50},
  "speed": {"distribution": "normal", "mean": 1.2, "sd": 0.25, "min": 0.6, "max": 1.8},
  "pre_movement": {"distribution": "uniform", "min": 0.0, "max": 15.0},
  "strategy": "nearest_exit | capacity_aware | balanced_assignment",
  "seed": 42,
  "blocked_exit_ids": ["EA"],
  "blocked_cells": [[3, 4]],
  "exit_capacity_overrides": {"EB": 2.0},
  "max_duration_s": 600, "dt_s": 0.25, "frame_interval_s": 1.0,
  "record_frames": true
}
```

Stored configs use the engine key names `speed_distribution` /
`pre_movement_distribution`; the API translates transparently.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/scenarios?building_id=` | List |
| POST | `/scenarios` | Create; validated against the building (unknown zones/exits, dt bound, all-exits-blocked → 422) |
| GET | `/scenarios/{id}` | Detail with config |
| PUT | `/scenarios/{id}` | Update |
| DELETE | `/scenarios/{id}` | Delete |

## Plan import

| Method | Path | Description |
| --- | --- | --- |
| POST | `/import/preview` | Multipart upload of a floor plan (image or ASCII DXF) + form fields `name`, `target_width` (8–120 cells), `real_width_m`, `threshold` (0–255, image only), `invert` (image only). Returns `{draft: {name, width, height, cell_size_m, walls, exits: [], zones: []}, stats, warnings}`. The draft has **no exits/zones** — it is completed in the editor. 422 with a clear message on unsupported types, oversized files (>10 MB), unreadable images, or geometry with no detected walls. |

## Runs

| Method | Path | Description |
| --- | --- | --- |
| POST | `/runs` | Start a run. Body: `{scenario_id, name?, wait?, overrides?{seed?, strategy?}}`. Default: background execution → `{run: RunDetail(status=pending)}`. `wait: true` executes inline. |
| GET | `/runs?scenario_id=&limit=` | List summaries (newest first) |
| GET | `/runs/recent` | 10 most recent |
| GET | `/runs/{id}?include_frames=&include_building=` | Detail. Pending/running runs return status only. Completed runs include `metrics`, `timeline`, `frames`, and `config`. |
| POST | `/runs/{id}/reproduce` | Re-execute with the run's exact recorded config + seed |

Run status: `pending → running → completed | failed`.
`metrics.engine_status` distinguishes `completed` (all out) from `incomplete`
(horizon reached). Failed runs carry `error {code, message}` and
`metrics: null` — a failure can never look like a successful evacuation.

Metrics document (summary): engine_status, sim_time_s, steps,
total/evacuated/unreachable/remaining counts, t50/t90/t95, mean/max/min
evacuation time, queue total/mean/max, fallback_count, exit_stats[] (per
exit: assigned, evacuated, utilization_pct, discharge times), congestion map
(cell → blocked attempts), warnings[].

`frames`: `[{t, occupants: [[id, x, y, statusCode]…]}]` with statuses
0 waiting, 1 moving, 2 at_exit, 3 evacuated (never in frames), 4 unreachable.
These are the only positions the UI animates.

## Comparison

| Method | Path | Description |
| --- | --- | --- |
| POST | `/compare` | Body `{run_ids: [..]}` (≤ 20). Returns `rows` (per-run headline metrics), `verdicts` (metric → best run name, only when metrics separate), `notes` (methodology disclaimers). Non-completed runs are listed in notes and excluded from verdicts. |

## Experiments

| Method | Path | Description |
| --- | --- | --- |
| GET | `/experiments` | List |
| POST | `/experiments` | Body `{name, base_scenario_id, sweep: {"dot.path": [values…]}, seeds: [..], wait?}`. Sweep paths validated against the real config; cartesian product × seeds ≤ 200 planned runs (else 422). |
| GET | `/experiments/{id}` | Status + error if failed |
| GET | `/experiments/{id}/results` | `{experiment, sweep_definition, rows: [{experiment_run_id, run_id, sweep_values, seed, metrics}]}` |
| GET | `/experiments/{id}/export` | CSV download (one row per run, all headline metrics) |

Experiment statuses: `pending → running → completed | failed`. Individual run
failures are recorded as failed runs with null metrics and do not abort the
experiment.

## HTTP semantics

- 200 read, 201 create, 204 delete, 400/404/409/422/500 as coded.
- CORS restricted to `http://localhost:5173` / `127.0.0.1:5173` (dev origin).
- No authentication: local-first tool; do not expose to untrusted networks.
