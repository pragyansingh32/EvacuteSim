# Architecture

EvacuateSim is a **modular monolith** with two applications:

```
evacuate/
├── backend/                 Python 3.12+ / FastAPI
│   ├── app/
│   │   ├── main.py          FastAPI app factory, error handlers, SPA serving
│   │   ├── api/             Routers (thin): health, buildings, scenarios, runs, experiments
│   │   ├── schemas/         Pydantic request/response models
│   │   ├── services/        Orchestration: building/scenario/run/comparison/experiment/sample data
│   │   ├── simulation/      THE ENGINE (pure Python, no HTTP/DB imports)
│   │   │   ├── grid.py      BuildingGrid: walls/exits/zones, validation, serialization
│   │   │   ├── occupant.py  Occupant state machine
│   │   │   ├── engine.py    Discrete-time simulation loop
│   │   │   └── metrics.py   Percentile helper
│   │   ├── algorithms/      pathfinding (BFS fields), strategies, assignment
│   │   ├── planimport/      Floor-plan import: image + ASCII-DXF → grid draft
│   │   ├── models/          SQLAlchemy ORM models (SQLite)
│   │   ├── repositories/    Thin persistence functions per entity
│   │   ├── db/              Engine/session management
│   │   └── core/            Settings, errors, logging
│   └── tests/               Pytest suite (79 tests)
├── frontend/                React 19 + TypeScript + Vite
│   └── src/
│       ├── api/client.ts    Typed fetch client (single source of backend access)
│       ├── components/      GridCanvas (SVG renderer), shared UI
│       └── pages/           Home, BuildingEditor, ScenarioEditor, Library, Runs, RunView,
│                            Compare, Experiments
├── docs/                    The nine required documents
├── scripts/                 PowerShell + bash developer scripts
└── data/                    SQLite database (created at runtime)
```

## Layering rules (enforced by review and tests)

1. `simulation/` and `algorithms/` never import FastAPI, SQLAlchemy, or request
   objects. The engine runs identically inside pytest and inside the API.
2. `api/` routers validate (Pydantic) and delegate; business rules live in
   `services/`; queries live in `repositories/`.
3. The frontend only talks to `/api/v1`. Every number displayed comes from a
   recorded run — there are no hardcoded metrics.

## Request flow for a simulation run

```
POST /api/v1/runs {scenario_id, wait?, overrides?}
  → scenario_service/run_service:
      1. load scenario + building; validate; snapshot building JSON
      2. build EngineConfig (validating dt vs cell size/speed, populations…)
      3. persist RunModel(status=pending, config echo, snapshot)
      4. execute synchronously (wait=true) or submit to ThreadPoolExecutor(2)
  → execute_run (own sessions):
      - status=running
      - EvacuationEngine(BuildingGrid.from_snapshot, EngineConfig).run()
        OUTSIDE any DB transaction
      - success → status=completed + result JSON (metrics, timeline, frames)
      - exception → status=failed + error JSON (never a fabricated success)
```

The run view polls `GET /runs/{id}` while pending/running, then renders the
recorded frames. Playback cannot disagree with the stored result because it IS
the stored result.

## Persistence (SQLite via SQLAlchemy 2)

| Table | Purpose |
| --- | --- |
| `buildings` | Layout: dims, cell size, walls/exits/zones JSON |
| `scenarios` | Full simulation config JSON + building FK |
| `runs` | Building snapshot + full config echo + status + result JSON (metrics, timeline, frames) + error JSON |
| `experiments` / `experiment_runs` | Sweep definitions and per-combination links to real runs with headline metrics |

Reproducibility contract: each run stores its own building snapshot and config
echo, so rerunning the exact configuration works even if the underlying
building/scenario are later edited. Runs reference their scenario when created
from one; experiment runs link through `experiment_runs`.

JSON documents are stored with `sort_keys` for stable serialization. SQLite
runs in WAL mode with foreign keys enforced.

## Plan import pipeline (`app/planimport/`)

Converts an uploaded floor plan into a grid **draft** (walls only):

- **Images** (PNG/JPG/BMP/GIF/TIFF/WebP): decode with Pillow → binarize at full
  resolution at the user threshold (preserves thin lines) → auto-crop to the
  content bounding box (removes scanner margins that would become phantom
  floor rings) → box-filter to the target grid → a cell is wall when ≥ 30% of
  its pixels are wall-colored.
- **ASCII DXF**: parse LINE / LWPOLYLINE / CIRCLE entities from the text
  format → Bresenham-rasterize the segments onto the grid.

The draft is handed to the building editor (router state + sessionStorage
fallback), where the user cleans noise, places exits and zones, and saves
through the normal validated building API. The import never creates a
runnable building by itself — exits and zones are human decisions.

## Computation limits (settings, all overridable via env)

Grid ≤ 120×120, occupants ≤ 2000, duration ≤ 3600 s, blocked cells ≤ 2000,
experiments ≤ 200 planned runs, stored frames ≤ 4000 per run (the engine
raises its frame interval automatically when needed). The time step must
resolve the fastest occupant: `dt ≤ cell_size / max_speed` (0.25 s default at
0.5 m cells and 1.8 m/s max).

## Frontend architecture

- React Router pages; no global state library — server state via typed fetches.
- `GridCanvas` renders walls/zones/exits/blocked overlays/congestion heat and
  occupant dots with status colors from one frame object.
- Recharts renders the evacuation timeline, exit utilization, and experiment
  spread charts.
- The built bundle is served by FastAPI (SPA fallback route) so a single
  process serves the whole application at `http://127.0.0.1:8000`.

## Development vs production mode

- Development: backend `uvicorn app.main:app --reload --port 8000` + frontend
  `npm run dev` (Vite on :5173 proxies `/api`).
- Demo/production: `npm run build`, then just run uvicorn — the built app is
  served from `frontend/dist` with SPA routing support.
