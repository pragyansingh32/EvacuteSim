# Known limitations

Read together with [SIMULATION_MODEL.md](SIMULATION_MODEL.md).

## Model

- No validation against real buildings, drills or published datasets. The model
  demonstrates mechanisms, not safety.
- Simplified crowd physics: one occupant per 0.5 m cell, no density-speed
  coupling, no pushing or injuries. Head-on encounters resolve by sidestep or
  swap, so opposing flows are optimistic.
- Doors are rate limits in persons per second with a FIFO queue. The values are
  user assumptions, not measured flows.
- Walking speed Normal(1.2, 0.25) m/s and pre-movement Uniform(0, 15) s are
  placeholder defaults, not calibrated populations.
- Occupants follow their assigned exit. Only the capacity-aware strategy
  re-evaluates (every 2 s of simulated time), apart from re-routing around
  blocked cells in disaster scenarios.
- T50/T90/T95 are read from step-resolution data and are coarse.
- Single floor only. No stairwells.

## Features

- Layouts are rectilinear grids. No PDF or IFC import, and no binary DXF.
- Plan import is heuristic. Door gaps narrower than one cell vanish, corridors
  under about three cells wide can be read as chains of doors, and text or
  furniture drawn as solid shapes becomes wall. Exit capacities (width x 1.3
  p/s/m) and populations (area x density) are assumptions. Review the result in
  the editor.
- draw.io import follows fixed conventions: walls are unfilled rectangles or
  lines, obstacles are filled shapes, text is ignored, doors are gaps in walls.
  Only the first page of a multi-page file is read.
- Experiments are full-factorial, capped at 200 planned runs.
- No accounts or authentication. Do not expose the API to an untrusted network.
- SQLite only, with a two-worker run pool.
- Frontend test coverage is thin (the grid renderer and the API client).
