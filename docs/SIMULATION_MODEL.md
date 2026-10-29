# Simulation Model

This document defines exactly what the engine does and does not model. Read it
before interpreting any result.

## Scope statement

EvacuateSim's engine is a **discrete-time, grid-based agent simulation** for
teaching and research. It is **not** a validated pedestrian-dynamics model and
**not** a fire model: no smoke, heat, toxicity, structural failure, or
behavioral panic modeling. Outcomes depend on the assumptions below.

## Building representation

- A 2D grid of cells; every cell is **wall** or **walkable**.
- Cell size defaults to **0.5 m** (configurable 0.05–5 m); all speeds are
  interpreted through this scale.
- **Exits** are special walkable cells with a modeled throughput capacity in
  persons/second (default 1.0 p/s ≈ one person per second through a ~0.5 m
  door — a deliberately conservative simplification, not a calibrated value).
  An exit placed *inside* a wall line is a doorway: exit cells are walkable by
  definition.
- **Zones** are named sets of walkable cells used as occupant starting areas.
- Scenarios may additionally mark exits as blocked (the cell becomes
  impassable) and add blocked cells (temporary walls).

## Occupants

Each occupant carries:

| Property | Default | Meaning |
| --- | --- | --- |
| speed | Normal(1.2, 0.25) clipped to [0.6, 1.8] m/s | walking speed |
| reaction delay | Uniform(0, 15) s | pre-movement time before walking may start |
| priority | Uniform(0,1), seeded | fixed tie-break weight for movement contests |
| status | waiting → moving → at_exit → evacuated (or unreachable) | lifecycle |

Statuses and the mass-balance identity (an engine invariant):

```
total = evacuated + unreachable + (waiting + moving + at_exit)
```

`unreachable` occupants had no path to any exit at spawn; they are counted and
never disappear. The engine refuses to emit results if the identity breaks.

## Movement model

Time advances in fixed steps `dt` (default 0.25 s). Movement uses
**rate accumulation**: an occupant accrues `dt` of eligible time each step
(after its reaction delay has elapsed) and may advance one cell whenever the
accumulator reaches the cell traversal time `cell_size / speed`. Faster
occupants therefore move more often. `dt` must satisfy
`dt ≤ cell_size / max_speed` so that one step never under-samples the fastest
walker (validated; a clear error explains the bound).

One cell per step, four-directional movement; diagonal moves (including
corner-cutting between two diagonal walls) are impossible.

## Routing

Routes come from precomputed **BFS distance fields** (one per available exit),
computed once per run over the walkable set minus scenario-blocked cells. An
occupant's next cell is the neighbor with the smallest distance value in its
assigned exit's field; ties break in the fixed order N, E, S, W. Occupants
walking toward exit A may pass through exit B's cell (doors are floor); if
they *stop* on any exit cell they will leave through that exit.

## Conflict resolution (per step, deterministic)

1. Waiting occupants whose reaction delay has elapsed activate.
2. Active occupants with a full movement accumulator request their next cell.
3. All requests are attempted **in a deterministic global order**: sorted by
   the occupant's seeded priority, rotated round-robin by step index. The
   rotation prevents starvation (a fixed winner blocked by a standing
   occupant cannot starve everyone behind it forever).
4. A request succeeds when its destination is free **at application time**,
   so an occupant may follow a leader into a cell vacated earlier in the
   same step (platoons advance naturally). Multi-pass retry realizes this.
5. Remaining blocked requesters whose destinations are held by other blocked
   requesters form head-on cycles; each cycle is applied **simultaneously**
   (a permutation — no cell is ever shared). This is a documented
   simplification: occupants may pass each other by sidestepping at
   sub-cell resolution, which prevents permanent deadlock in single-file
   corridors. Opposing flows in narrow corridors are therefore represented
   more favorably than reality.
6. Cell capacity is 1: at no point do two occupants share a cell (enforced
   and tested via recorded frames).

## Congestion representation

Congestion is **operational, not physical**: every blocked movement attempt
increments a counter on the contested cell and adds `dt` to the occupant's
queue time. The congestion heatmap therefore shows where occupants lost
movement opportunities — a useful bottleneck indicator, not a density or
pressure measurement, and not a safety threshold.

## Exits and discharge

Occupants standing on an exit cell join that exit's **FIFO door queue**
(ordered by arrival time, then id). Each exit has a throughput accumulator:
per step it gains `capacity × dt` credit, discharges as many queued occupants
as credits allow (fractional credit carries over), and banks **at most one**
credit while idle so long idle periods cannot produce bursts. Occupants
spawning on an exit cell join the door queue but may not discharge before
their reaction delay has elapsed. Discharged occupants are `evacuated` at the
step's end time; their cell frees for the next step.

This is a **simplified throughput model** (a rate limit at the door), not a
calibrated flow model of specific door geometries.

## Termination

The run ends when `evacuated + unreachable == total` (engine status
`completed`) or when the configured maximum duration (or the 40,000-step
safety cap) is reached (engine status `incomplete`, occupants remaining are
reported honestly). Both cases are stored as *successfully executed* runs;
`failed` is reserved for execution errors.

## Reproducibility

One `numpy.random.Generator` seeded from the scenario seed drives all
randomness (spawn placement, attribute sampling, conflict priorities, balanced
assignment dealing). Given the same layout snapshot, config, seed, and engine
version, results are identical — verified by tests comparing full result
documents. The engine version string is stored with each run.

## What is approximated or omitted (summary)

| Behavior | Status |
| --- | --- |
| Walking speeds, reaction delays | Modeled (distributions) |
| Path choice | Shortest (BFS) to assigned exit |
| Cell capacity, queues, door throughput | Modeled (simplified) |
| Overtaking / counter-flow | Not modeled; head-on swaps allowed (see above) |
| Crowd pressure, densities, injuries | Not modeled |
| Fire/smoke/route degradation during the run | Not modeled (blockages are fixed at start) |
| Group behavior, family cohesion, herding | Not modeled |
| Route re-planning when queues form | Only strategy B reassigns exits periodically |
| Calibrated door flow rates | Not calibrated — user-configured assumptions |
