# Phase Status

Live development log. Updated as phases complete. Last updated: end of Phase 4.

| Phase | Scope | Status | Validation performed |
| --- | --- | --- | --- |
| 0 | Workspace inspection | DONE | Empty workspace confirmed; Python 3.14.7, Node 24.20, npm 11.19 verified; venv created |
| 1 | Project foundation | DONE | Backend config/db/errors modules; pyproject with ruff+pytest config; .gitignore; docs scaffold |
| 2 | Building representation | DONE (backend) | `BuildingGrid` with validation: dims, exits, zones, reachability warnings; 11 grid tests pass |
| 3 | Simulation engine | DONE | Discrete-time engine: movement accumulation, conflicts, following, cycle swaps, exit throughput, frames, timeline; engine tests pass |
| 4 | Routing strategies | DONE | nearest_exit / capacity_aware / balanced_assignment + fallback; strategy tests pass |
| 5 | Persistence + samples | IN PROGRESS | SQLAlchemy models next |
| 6 | Backend API | PENDING | |
| 7 | Visualization | PENDING | |
| 8 | Analytics/comparison | PENDING | |
| 9 | Experiment runner | PENDING | |
| 10 | Full testing + E2E | PENDING | |
| 11 | Packaging/docs | PENDING | |

## Environment constraints discovered

- **Smart App Control is ON** on this machine. It blocked `pydantic_core 2.50.2`
  (too new, no cloud reputation). Fixed by pinning `pydantic==2.12.5` whose
  compiled core is allow-listed. numpy and ruff binaries pass. If a dependency
  update reintroduces DLL blocks, pin older versions (see `KNOWN_LIMITATIONS.md`).

## Bugs found and fixed during Phase 3/4 (for the record)

1. Stale occupancy set: `_step` copied `self.occupied` but never wrote back —
   occupants haunted their spawn cells; fixed by making `self.occupied` the
   single live source of truth (discharge also frees door cells now).
2. Starvation deadlock in contests: fixed-priority contest winners blocked by
   standing occupants starved everyone behind them. Fixed with a rotated
   deterministic global request order (round-robin by step).
3. Cycle (swap) application could remove a cell already claimed by an earlier
   cycle member (double discard) — could produce two occupants in one cell.
   Fixed: vacate all origins first, then move with discard suppressed.
4. Exit accumulator could under-use high-capacity exits (cap applied before
   discharge). Fixed: accumulate uncapped, discharge multiple per step, cap
   residual credit at 1.0.
5. Occupants spawning on an exit cell could discharge before reacting — fixed
   with a `reacted` flag required for discharge.
6. `fallback_count` was zeroed by init order after being computed.

Next action: implement persistence models + repositories + sample data (Phase 5), then API layer (Phase 6).
