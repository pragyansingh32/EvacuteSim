# EvacuateSim

A grid-based evacuation simulator. Draw (or import) a building layout, set up a
population and a scenario, run a discrete-time simulation, and compare routing
strategies across runs.

It is an educational tool. It is not a certified fire-safety system and its
results say nothing about any real building. See
[docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## What it does

- Building editor: paint walls, place exits with door capacities, define start zones.
- Plan import: draw.io diagrams, images and ASCII DXF files are converted to a
  grid, with doors, exits and zones detected automatically.
- Scenario editor: population per zone, walking speed and reaction time
  distributions, blocked exits, strategy, seed and run limits.
- Simulation engine: discrete-time agents on a grid, door throughput queues,
  fire, earthquake, stampede, gas leak, flood and power outage disasters.
- Three routing strategies: nearest exit, capacity-aware, balanced assignment.
- Run view with playback, evacuation timeline, T50/T90/T95 and exit utilization.
- Compare runs side by side, and run parameter sweeps over several seeds with CSV export.
- Advisor: a rule-based analysis of a finished run that proposes changes and
  checks each one with a real test run.
- Restore points for the whole workspace.

Every run stores its building snapshot, configuration, engine version and seed,
so it can be repeated exactly.

## Setup

Requires Python 3.12+ and Node 20+.

```bash
python -m venv .venv
.venv/bin/pip install -e "backend[dev]"      # Windows: .venv\Scripts\pip
cd frontend && npm install
```

Run the backend and the frontend dev server in two terminals:

```bash
cd backend && ../.venv/bin/python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend && npm run dev     # http://localhost:5173, proxies /api to :8000
```

For a single process, run `npm run build` in `frontend/` and start only the
backend. It serves the built app at http://127.0.0.1:8000.

`scripts/dev.sh` and `scripts/dev.ps1` do the setup and start both servers.
On first start the database (`backend/data/evacuatesim.db`) is seeded with two
sample buildings and a few sample scenarios.

## Checks

```bash
cd backend && ../.venv/bin/python -m pytest tests/
cd backend && ../.venv/bin/ruff check app tests
cd frontend && npm test
cd frontend && npm run build      # type-check and bundle
```

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Simulation model](docs/SIMULATION_MODEL.md)
- [Algorithms](docs/ALGORITHMS.md)
- [API reference](docs/API_SPECIFICATION.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Stack

Python, FastAPI, Pydantic, SQLAlchemy with SQLite, NumPy. React, TypeScript, Vite, Recharts.
