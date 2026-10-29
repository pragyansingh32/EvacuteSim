# Known Limitations

Honest accounting of what EvacuateSim does **not** do. Read together with
docs/SIMULATION_MODEL.md.

## Model-level limitations

1. **No validation against reality.** No real-building data, evacuation
   drills, or published datasets were used. Nothing here predicts real
   outcomes; the model demonstrates mechanisms, not safety.
2. **No fire or smoke.** Route unavailability is fixed at scenario start; no
   mid-run degradation, no hazard fields, no toxicity.
3. **Simplified crowd physics.** One occupant per 0.5 m cell; no continuous
   space, no density–speed coupling, no pushing/pressure, no injuries, no
   counter-flow friction (head-on encounters resolve by mutual sidestep).
4. **Simplified door throughput.** Exits are rate limits in persons/second
   with one-person FIFO queues. Real doors' flow depends on width, geometry,
   approach density, and behavior; values here are user assumptions.
5. **Behavioral distributions are assumptions.** Walking speed
   Normal(1.2, 0.25) m/s and pre-movement Uniform(0, 15) s are typical
   literature-ish placeholders, not calibrated populations. All parameters
   are configurable and should be treated as scenario inputs.
6. **No dynamic re-routing by default.** Occupants follow their assigned
   exit; only the capacity-aware strategy re-evaluates (every 2 s of sim
   time). Humans visibly re-decide in queues; the model mostly does not.
7. **T50/T90/T95 are index-based.** Step-resolution data plus a simple index
   rule; treat them as coarse quantiles.
8. **Counter-flow favorability.** The cycle-swap rule lets occupants pass in
   single-file corridors; real opposing flows congest far worse. Results with
   opposing flows are optimistic.

## Feature-level limitations

9. **Grid-only layouts.** No CAD/PDF/IFC import. Rectilinear 0.5 m cells only;
   curved geometry is an approximation.
10. **Plan import auto-interpretation is heuristic.** Doors, exits, zones,
    and populations are detected automatically (gap-in-wall-line geometry,
    flood-fill room segmentation, area × density populations), but heuristics
    have failure modes: door gaps narrower than one grid cell vanish;
    corridors narrower than ~3 cells can be misread as chains of doors;
    text/furniture drawn as solid shapes become wall cells; exit capacities
    are width × 1.3 p/s/m (an assumption, not a measured flow); populations
    are area × density (an assumption). Warnings list unreachable rooms; the
    editor remains the review step. Binary DXF, PDF, and INSERT blocks are
    not imported. Scale relies on the stated plan width.
11. **draw.io import conventions.** Vector import follows explicit drawing
    conventions: walls = unfilled rectangles/lines (fillColor=none), solid
    obstacles = filled shapes, labels = text shapes (ignored). Doors must be
    gaps in the wall geometry. Edges anchored to shapes are treated as
    connections, not walls. Multi-page files import the first page only.
12. **Static scenarios.** Blocked exits/cells cannot change mid-run; no
    scheduled events, no occupant re-spawning.
11. **Experiments are full-factorial only.** No Latin hypercube/optimization
    search; sweeps are bounded at 200 planned runs per experiment.
12. **No user accounts / multi-tenancy.** Local-first single-user tool; the
    API has no authentication — it must not be exposed to untrusted networks.
13. **SQLite only.** Single-writer database; concurrent heavy experiments are
    serialized through a 2-worker pool. Adequate locally, not a server backend.
14. **Frontend tests are thin.** Vitest covers the renderer and formatting;
    interaction flows are verified by recorded browser E2E sessions rather
    than automated CI.

## Environment-specific notes

15. **Smart App Control (Windows).** This development machine blocks
    unsigned compiled wheels by cloud reputation. `pydantic` is pinned to
    2.12.5 (its `pydantic_core` binary has reputation); upgrading pydantic may
    reintroduce DLL blocks (`ImportError: DLL load failed … Application
    Control policy`). If that happens, pin the previous working version
    rather than disabling the security policy.
16. **Windows-first packaging.** Developer scripts ship as PowerShell plus
    bash; paths in examples use Windows conventions.

## Deliberate non-goals (first release)

- Multi-floor stairwell routing (single-level model).
- Calibration tooling against drill data.
- User management, deployment hardening, horizontal scaling.
- ML surrogate models (the spec allows them only if trained on real
  simulation outputs and evaluated on held-out scenarios; none is shipped).
