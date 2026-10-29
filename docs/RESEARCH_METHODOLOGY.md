# Research Methodology

## Central research question

**Can capacity-aware and balanced-exit routing improve simulated evacuation
outcomes compared with nearest-exit routing across different building layouts,
occupancy levels, and route-availability conditions?**

## Baselines and treatments

- **Baseline (control):** `nearest_exit` — every occupant routes to the
  closest reachable exit.
- **Treatment 1:** `capacity_aware` — exit choice weighs walking time against
  modeled door queues (live load / capacity), re-evaluated periodically.
- **Treatment 2:** `balanced_assignment` — a greedy min-makespan assignment of
  each zone's population across exits, computed before the run.

All strategies run on the identical engine, layout snapshot, population
distribution, and seed set. Only exit choice differs.

## Experimental design

The experiment runner (`POST /api/v1/experiments`) performs full-factorial
sweeps: a dictionary of dot-path parameter values is expanded into the
cartesian product of combinations, each executed **once per configured seed**.
Every combination produces a real simulation run stored with its exact
configuration; `experiment_runs` links each to its sweep values, seed, and
headline metrics. CSV export allows independent analysis.

Standard sweeps shipped with the UI:

| Preset | Varied parameter |
| --- | --- |
| Strategy comparison | strategy ∈ {nearest, capacity-aware, balanced} |
| Reaction delay sweep | pre-movement max ∈ {5, 15, 30, 60} s |
| Walking speed sweep | speed mean ∈ {0.8, 1.0, 1.2, 1.4} m/s |
| Occupancy sweep | west-zone population ∈ {30, 60, 90} |

Seeds: each combination is repeated per seed (default 0, 1, 2 in the UI).
Repeated seeds quantify **run-to-run variability**; the spread of outcomes at
one setting is model randomness, not measurement noise, and must be reported
alongside means.

## Metrics recorded per run

- Total evacuation time (last discharge), T50 / T90 / T95 (index rule — see
  docs note below), mean/max/min individual evacuation time.
- Evacuated / unreachable / remaining counts and the evacuated share.
- Per-exit: assigned, evacuated, utilization share, first/last/mean discharge.
- Queueing: total, mean, max blocked time; occupants who queued.
- Congestion: blocked-attempt counts per cell (operational indicator).
- Strategy fallbacks (balanced assignment degradations).
- Full timeline (per-step evacuated/inside/at-exit) and sampled frames.

T50/T90/T95 use the index rule `sorted_times[min(n-1, floor(f · n))]` on
step-resolution data — coarse by design, deterministic, and monotone.

## Analysis guidance

1. **Never conclude from a single run.** Compare strategies only with repeated
   seeds; report the spread (min–max or per-seed values).
2. **Look for trade-offs, not winners.** A strategy may reduce total time but
   raise queueing at one door, or help slow occupants while delaying fast
   ones. The comparison view shows each metric separately; the experiment
   table exposes per-seed outcomes.
3. **Context matters.** On a symmetric building with one zone per exit,
   nearest-exit routing is already balanced — an "improved" strategy cannot
   beat it on total time and may match it. Asymmetries (a single crowded
   zone, unequal door capacities, a blocked exit) are where routing strategies
   differentiate.
4. **Verify the sanity envelope.** Evacuation time is bounded below by
   (distance × cell size / speed) + capacity effects; a result outside
   plausible bounds indicates a misconfiguration, not a finding.

## Limits on generalizing results

- All results describe **the model**, not any real building or population.
- Speed/reaction distributions are configurable assumptions, not calibrated
  empirical distributions.
- Door capacities are user-set rate limits, not measured flow rates.
- Counter-flow, group behavior, and route degradation during a run are not
  modeled (see docs/SIMULATION_MODEL.md).
- No validation against real drills or published datasets has been performed;
  none is claimed. Any use beyond teaching/demonstration requires independent
  validation.

## Reproducibility statement

Every run stores its building snapshot, full configuration, engine version,
and seed. Re-running the same configuration (button: "Reproduce with recorded
seed", or `POST /runs/{id}/reproduce`) must reproduce the stored result
byte-identically except for wall-clock metadata — enforced by tests.
Experiments record the engine-produced runs they depend on, so an experiment
can be re-derived from its stored configuration and seeds.
