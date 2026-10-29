# Phase Status

Final status after the complete development session (Phase 0 → 11).

| Phase | Scope | Status | Validation |
| --- | --- | --- | --- |
| 0 | Workspace inspection | **DONE** | Empty workspace; Python 3.14.7, Node 24.20, npm 11.19 verified; venv created; plan written |
| 1 | Project foundation | **DONE** | Backend scaffold + health endpoint tested; frontend scaffold built |
| 2 | Building representation + editor | **DONE** | `BuildingGrid` validation (11 grid tests); SVG editor with paint/undo/zones/exits/save verified in browser |
| 3 | Simulation engine | **DONE** | 28 engine tests: movement, conflicts, throughput, mass balance, reproducibility, limits |
| 4 | Routing strategies | **DONE** | 11 strategy tests: baseline, capacity-aware, balanced + fallback, unreachable handling |
| 5 | Persistence + samples | **DONE** | SQLite models/repos; restart-persistence test; 2 sample buildings + 5 synthetic sample scenarios seeded idempotently |
| 6 | Backend API | **DONE** | 23 API integration tests (validation, run lifecycle, comparison, reproduction, error honesty) |
| 7 | Visualization | **DONE** | Live polling + recorded-frame playback (play/pause/step/speed/congestion) verified in browser |
| 8 | Analytics & comparison | **DONE** | Timeline/exit-utilization charts, compare table + verdicts, honest notes |
| 9 | Experiment runner | **DONE** | Full-factorial sweeps × seeds; results table; CSV export verified |
| 10 | Full testing + E2E | **DONE** | 79 backend tests + 4 frontend tests green; browser E2E of the complete workflow (see below) |
| 11 | Packaging + docs | **DONE** | This document set, README, scripts, verified setup instructions |

## Test totals at delivery

- Backend: **79 passed** (`pytest tests/`), ruff clean.
- Frontend: **4 passed** (vitest), `tsc -b` clean, production build succeeds.
- Browser E2E (recorded during development, ZCode in-app browser):
  1. Home renders with real seeded data.
  2. Scenario library lists 5 synthetic samples with honest labels.
  3. "Run now" starts a run; live view polls, then shows 120/120 evacuated.
  4. Frame playback advances (t=0 → 62.3 s), step/speed/congestion controls work.
  5. Compare page: 3 runs side by side with per-metric verdicts and notes.
  6. Experiments: strategy sweep × 3 seeds = 9 runs completed; results table + CSV export verified.
  7. Building editor: painted walls, placed 2 exits, painted a zone, saved; the painted building then ran a successful 8/8 scenario through the API.
  8. Reproduce-with-seed and failed-run honesty verified via API tests.

## Notable defects found and fixed (regression-tested)

1. **Exits in wall lines were impassable** (sample buildings' doors sat on the
   border) → exit cells are walkable by definition + regression test.
2. **Stale occupancy set** — movements updated a per-step copy, never the
   canonical state → single live source of truth.
3. **Contest starvation deadlock** — fixed-priority winners blocked forever →
   rotated deterministic order (round-robin by step).
4. **Cycle swap double-discard** could put two occupants in one cell → vacate
   all origins, then move with discard suppressed.
5. **Exit accumulator under-used high-capacity doors** → accumulate, discharge
   multiple, bank ≤ 1 credit when idle.
6. **Spawn-on-exit occupants could discharge before reacting** → `reacted`
   flag gates discharge.
7. **`fallback_count` zeroed by init order** after computation.
8. **SPA routes 404'd** behind the static mount → guarded SPA fallback route.
9. **Final playback frame could lag the end state** → true end-state frame
   recorded (bypassing the interval guard).

## Environment constraints

- Windows Smart App Control blocked `pydantic_core 2.50.2` (unproven cloud
  reputation) → pinned `pydantic==2.12.5`. numpy/ruff binaries pass.
- Recorded in KNOWN_LIMITATIONS.md with recovery guidance.

## Outstanding work

None blocking delivery. Future ideas (not promised): multi-floor routing,
dynamic mid-run events, automated browser E2E in CI, calibration tooling.
