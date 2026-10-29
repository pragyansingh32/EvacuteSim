# EvacuateSim — Project Plan

**EvacuateSim: An Explainable, Uncertainty-Aware Emergency Evacuation Simulation and Scenario Optimization Platform**

## Purpose

EvacuateSim is a local-first, educational/research-oriented decision-support tool that lets a user
build a simplified grid-based building layout, configure an occupant population, define emergency
scenarios, run a discrete-time evacuation simulation, and compare routing strategies with recorded,
reproducible evidence.

**Scope boundary (repeated everywhere it matters):** EvacuateSim is *not* a certified fire-safety
system. It does not simulate fire/smoke dynamics, structural failure, or professional-grade crowd
physics. Outcomes depend on model assumptions and are not safety predictions for real buildings.

## Environment findings (Phase 0)

| Item | Finding |
| --- | --- |
| Workspace | `D:\projects\evacuate` — empty at session start |
| OS | Windows 10/11 (win32), Git Bash shell |
| Python | 3.14.7 (system) + project venv at `.venv\` |
| Node.js | v24.20.0, npm 11.19.0 |
| Backend deps | fastapi 0.162, pydantic **2.12.5** (pinned — Smart App Control blocks newer pydantic_core builds), sqlalchemy 2.1, numpy 2.5, pytest 9.2, httpx, ruff |
| Frontend deps | React 19 + TypeScript + Vite + Recharts |
| AI API key | Not required — no LLM is used anywhere in the runtime |

**Delivery note:** all 12 phases completed. Final validation: 79 backend tests
+ 4 frontend tests green, ruff clean, production build succeeds, and the full
user workflow verified in a real browser (see `docs/PHASE_STATUS.md`).

## Architecture summary

Modular monolith:

- `backend/` — Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2 + SQLite, NumPy.
  - `simulation/` — pure-Python discrete-time grid engine (no HTTP concepts).
  - `algorithms/` — BFS pathfinding, routing strategies, exit assignment.
  - `services/` — orchestration, run execution, comparison, experiments.
  - `api/` + `schemas/` — versioned REST API under `/api/v1`.
  - `models/` + `repositories/` + `db/` — persistence.
- `frontend/` — React 19 + TypeScript + Vite, SVG visualizations, Recharts for metric charts.
- `docs/` — the nine required documents.
- `scripts/` — PowerShell + bash developer scripts.

## Phased delivery

See `docs/PHASE_STATUS.md` for live status. Phases are executed sequentially with a validation
gate at each checkpoint:

0. Workspace inspection and execution planning.
1. Project foundation: backend + frontend scaffolding, health endpoint, tooling.
2. Building representation + validation + floor-plan editor (frontend + API).
3. Simulation engine (pure Python, tested before API integration).
4. Routing strategies (nearest-exit, capacity-aware, balanced assignment) + tests.
5. Scenario management and persistence (SQLite; restart-safe).
6. Backend API integration (runs, status, results, comparison).
7. Simulation visualization (live view driven by real backend frames).
8. Analytics, comparison, optimization views.
9. Research experiment runner (parameter sweeps, reproducible records, export).
10. Full test suite + failure correction (+ browser-based end-to-end check).
11. Packaging and final delivery (verified setup instructions, docs, scripts).

## Non-negotiable engineering rules

1. Every result shown in the UI comes from a recorded simulation run — no hardcoded metrics.
2. Same layout + scenario + seed + algorithm version ⇒ identical results (enforced by tests).
3. Mass balance: spawned = evacuated + unreachable + remaining, always (enforced by tests).
4. Failed runs are recorded as failed; an exception can never fabricate a successful result.
5. Simulation layer never imports FastAPI/HTTP objects.
6. Honest limitations are documented in-app and in `docs/KNOWN_LIMITATIONS.md`.
