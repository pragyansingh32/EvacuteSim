# Test Strategy

## Test pyramid in this project

| Level | Tooling | What it covers |
| --- | --- | --- |
| Unit (simulation layer) | pytest | Grid validation, BFS fields, engine mechanics, strategies, metrics helpers |
| Integration (API) | pytest + FastAPI TestClient (httpx) | Schema validation, CRUD, run lifecycle, persistence across "restart", comparison |
| Frontend unit | Vitest + Testing Library | SVG renderer (frame fidelity, blocked exits), API row formatting |
| End-to-end (manual-assisted) | ZCode browser automation (recorded in PHASE_STATUS) | Real backend + built frontend: editor painting, run launch, playback, compare, experiments, CSV export |

Run everything from `backend/` / `frontend/`:

```bash
# backend
.venv/Scripts/python -m pytest tests/          # Windows
.venv/bin/python -m pytest tests/              # Linux/macOS
.venv/Scripts/ruff check app tests

# frontend
npm test          # vitest
npm run build     # type-checks (tsc -b) and bundles
```

## Required test cases (spec §12) → where they live

### Building and routing
1. Valid map with one exit permits evacuation → `test_engine.py::TestBasicEvacuation::test_single_occupant_evacuates`
2. Walls cannot be traversed → `TestMovementConstraints::test_walls_are_never_traversed`
3. A closed route is never used → `TestUnreachableAndBlocking::test_blocked_cells_close_routes`
4. Blocked exit causes rerouting when an alternative exists → `test_blocked_exit_causes_rerouting`
5. Occupant without a reachable exit is marked → `test_unreachable_occupant_is_marked`, `test_unreachable_region_marked_for_all_strategies`
6. Invalid map dimensions rejected → `test_grid.py::TestGridValidation` (too small, too large, out-of-bounds, malformed)

### Agent movement
7. Two occupants cannot share a single-capacity cell → `TestMovementConstraints::test_two_occupants_never_share_a_cell` (asserted over all recorded frames)
8. Conflicts resolved per documented algorithm → `test_conflicting_requests_resolve_and_everyone_still_exits`, `test_head_on_swap_resolves_without_collision` (direct unit test of the swap rule)
9. Reaction delays affect movement start → `TestTiming::test_reaction_delay_delays_movement` (exact 10 s shift)
10. Speeds influence movement timing → `test_speed_affects_arrival_time` (quantized 6 s vs 1.5 s)
11. Exit throughput respected → `TestExitThroughput` (spacing ≥ 1/capacity, no idle banking bursts, multi-discharge at high capacity)
12. All occupants accounted for → mass-balance tests + engine invariant

### Simulation integrity
13. Spawned = evacuated + remaining (+unreachable) → `test_mass_balance`, API-level balance assertion in `test_synchronous_run`
14. Reproducibility → `TestReproducibility::test_same_seed_same_result` (full result-document equality), `test_reproducibility_via_api`
15. Max duration respected → `test_max_duration_respected` (incomplete status, honest warning)
16. Empty/invalid maps produce clear errors → grid validation tests + `test_all_exits_blocked_rejected`, `test_scenario_with_unknown_zone_rejected`
17. An exception cannot fabricate success → `TestRunEndpoints::test_failed_run_recorded_honestly` (zone fully blocked → run failed with error, `metrics: null`)

### API and persistence
18. Invalid requests rejected → `TestBuildingEndpoints::test_invalid_building_rejected`, `test_malformed_body_rejected`, scenario validation tests
19. Saved buildings retrievable → `test_create_and_get_building`
20. Scenarios/results persist across restart → `TestPersistenceAcrossRestart::test_data_survives_backend_restart` (fresh app instance, same DB; also asserts samples are not duplicated)
21. Failed DB writes handled explicitly → referential guard: deleting a building in use by a scenario returns 409 (`test_delete_building_in_use_conflicts`)
22. API results agree with the engine → `test_api_result_matches_engine` (API run vs direct engine run on the same config+seed: equal evacuated count and T90)

### Frontend and integration
23–27. Covered end-to-end in the recorded browser session (see PHASE_STATUS): sample scenario loads, run starts from the UI, progress and final results visible, comparison over selected runs, understandable errors.
28. No hardcoded metrics → structural: the frontend has no metric constants; `GridCanvas.test.tsx` and `client.test.ts` verify rendering/formatting only. The disclaimer test guards honest framing.

## The PUT lesson (why endpoint coverage matters end to end)

Manual editing shipped broken: every `PUT /buildings/{id}` returned 500 (a
stray keyword argument in the service layer) while all 95 existing tests were
green — because no test exercised the update path. Three regression tests now
cover update success, invalid-update rejection, and 404. Rule of thumb applied
since: every endpoint shape (GET/POST/PUT/DELETE × success/error) gets at
least one test even when the UI appears to work.

## Known-answer accuracy battery

`app/services/validation_service.py` (surfaced live on the **System Accuracy**
page, `GET /api/v1/validation/battery`) encodes 14 designs with analytically
derived outcomes and asserts the engine classifies each correctly:

- **Pass designs (5):** adequate rooms/corridors, blocked exit with
  alternative, slow occupants with sufficient horizon → everyone out.
- **Failure designs (5):** sealed room (occupants marked unreachable, never
  lost), every exit blocked (refused with clear error), door throughput below
  population demand (incomplete with the analytically expected remaining
  count), horizon shorter than travel time, crowd crush with visible queueing.
- **Quantitative bounds (4):** door-throughput lower bound
  (last−first discharge ≥ (n−1)/capacity), travel-time lower bound
  (evacuation ≥ distance×cell/speed), population monotonicity (10 → 20 → 40
  occupants strictly increases time), seed reproducibility (identical result
  documents).

The battery is a **pytest regression gate** (`tests/test_validation_battery.py`):
any engine change that breaks one of these classifications fails CI. It
measured **100 % (14/14)** at delivery, stable across repeated runs.

Heavy-load verification executed during delivery: 800-occupant / 100×70-cell
stress run completes in ~2 s wall time with full mass balance; mass balance
re-verified across every stored run in the database.

## Regression discipline

Every engine bug found during development has a named regression test
(exit-in-wall doors, stale occupancy set, contest starvation, cycle double
discard, accumulator capping, spawn-on-exit reaction gating, fallback count
reset). The list lives in docs/PHASE_STATUS.md.

## What is NOT automated

- Browser E2E is executed via automation during development but not wired into
  CI (no display in typical CI runners); the vitest suite plus API integration
  tests approximate the contract.
- Performance/load testing is manual; a 300-occupant, 40×30-cell reference run
  completes in ~0.2 s wall time (checked during development).
