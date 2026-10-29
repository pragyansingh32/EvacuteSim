# EvacuateSim

**An explainable, uncertainty-aware emergency evacuation simulation and
scenario optimization platform.**

EvacuateSim lets you draw a simplified building layout, configure a simulated
population, define emergency scenarios, run a discrete-time evacuation
simulation, and compare routing strategies — with recorded, reproducible
evidence for every number shown.

> **Disclaimer.** EvacuateSim is an educational/research tool. It is **not** a
> certified fire-safety system, and its outputs are **not** safety predictions
> for any real building. Results depend on model assumptions documented in
> [`docs/SIMULATION_MODEL.md`](docs/SIMULATION_MODEL.md).

## Features

- **Building editor** — paint walls/floor, place exits (with modeled door
  capacities), define starting zones; server-side validation with warnings.
- **Plan import** — upload an existing floor plan (image or ASCII DXF CAD
  file) and convert its wall geometry into a simulation grid draft, then
  clean it up, place exits/zones, and evacuate it.
- **Scenario editor** — populations per zone, walking-speed and reaction-time
  distributions, blocked exits/cells, exit capacity overrides, strategy,
  seed, and run limits.
- **Real simulation engine** — discrete-time grid agents with movement-rate
  accumulation, deterministic conflict resolution, door throughput queues,
  and full mass-balance accounting. Pure Python, fully unit-tested.
- **Three routing strategies** — nearest-exit baseline, capacity-aware, and
  balanced exit assignment — comparable on identical conditions.
- **Live run view** — polls real backend status, then plays back the frames
  the engine actually recorded (play/pause/step/speed/congestion heatmap).
- **Analytics & comparison** — evacuation timeline, T50/T90/T95, exit
  utilization, congestion indicator, side-by-side strategy comparison.
- **Experiments** — full-factorial parameter sweeps × seeds, all executed as
  real runs, with a results table and CSV export.
- **Reproducibility** — every run stores its building snapshot, exact config,
  engine version, and seed; one click re-runs it.

No AI API key, no external services: everything runs locally.

## Quick start (Windows PowerShell)

```powershell
# 1. Backend
cd backend
python -m venv ..\.venv
..\.venv\Scripts\python -m pip install -e ".[dev]"
..\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# 2. Frontend (separate terminal) — for development with hot reload
cd frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api to :8000)
```

**Single-process demo (recommended):** build the frontend once
(`npm run build` in `frontend/`), then just run uvicorn — the app is served at
**http://127.0.0.1:8000** with SPA routing.

Linux/macOS: same commands with `python3 -m venv .venv`, `.venv/bin/...`, or
use `scripts/dev.sh`.

First startup seeds two synthetic sample buildings and five clearly-labeled
sample scenarios (SQLite at `backend/data/evacuatesim.db`).

## Try it in 60 seconds

1. Open http://127.0.0.1:8000 → **Scenario Library**.
2. Press **Run now** on *Sample: Baseline evacuation*.
3. Watch the recorded playback; inspect T50/T90 and exit utilization.
4. Run *Sample: West exit blocked* and *Sample: Balanced exit assignment*.
5. **Compare** the runs side by side.
6. **Experiments** → launch the *Strategy comparison* preset with 3 seeds and
   export the CSV.

## Tests and checks

```powershell
cd backend; ..\.venv\Scripts\python -m pytest tests/     # 79 tests
cd backend; ..\.venv\Scripts\ruff check app tests
cd frontend; npm test                                     # vitest
cd frontend; npm run build                                # tsc + bundle
```

## Project layout & documentation

- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) — goals, phased plan
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — modules, data flow
- [`docs/SIMULATION_MODEL.md`](docs/SIMULATION_MODEL.md) — what is modeled, honestly
- [`docs/ALGORITHMS.md`](docs/ALGORITHMS.md) — pathfinding, strategies, assignment
- [`docs/RESEARCH_METHODOLOGY.md`](docs/RESEARCH_METHODOLOGY.md) — experiments, analysis guidance
- [`docs/API_SPECIFICATION.md`](docs/API_SPECIFICATION.md) — REST reference
- [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md) — test matrix incl. spec §12 mapping
- [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) — read before interpreting results
- [`docs/PHASE_STATUS.md`](docs/PHASE_STATUS.md) — delivery log with defect history
- [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) — presentation walkthrough
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — common problems

## Technology

Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2 + SQLite · NumPy ·
pytest · ruff — React 19 · TypeScript · Vite · Recharts.

## Scope boundary (repeated deliberately)

Grid-based educational simulation; no fire/smoke dynamics, no certified
crowd physics, no calibrated door flow rates, no validation against real
buildings. See docs/KNOWN_LIMITATIONS.md before drawing conclusions.
