// Methodology & Model Basis: documents exactly how the simulation is built
// and how the evacuation plan works. Static content - kept in sync with
// docs/SIMULATION_MODEL.md.

import { Link } from 'react-router-dom'
import { DisclaimerBanner } from '../components/ui'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <div style={{ fontSize: 14, lineHeight: 1.7 }}>{children}</div>
    </div>
  )
}

export default function MethodologyPage() {
  return (
    <div>
      <h1>Methodology &amp; Model Basis</h1>
      <p className="page-sub">
        Under what basis the system creates the simulation, and how the evacuation plan works -
        the exact rules, formulas, and assumptions.
      </p>
      <DisclaimerBanner />

      <Section title="1. Simulation basis: grid discretization">
        <p>
          Every building is represented as a 2-dimensional grid of cells. Each cell is either
          <strong> wall</strong> (impassable) or <strong>floor</strong> (an occupant can stand
          there). One cell represents <code>cell_size_m</code> metres of real space - 0.5 m by
          default, configurable per building. The grid comes from three sources:
        </p>
        <ul>
          <li>Manual painting in the Building Editor (walls, floor, exits, zones)</li>
          <li>
            Automatic conversion of an uploaded floor plan (draw.io XML for exact vector geometry,
            image files via binarization + per-cell ink density, or ASCII DXF)
          </li>
          <li>Automatic detection of doors, exits, and starting zones from the wall geometry</li>
        </ul>
        <p>
          Validation rejects or warns about: dimensions outside 4×4 to 120×120, missing exits,
          sealed regions with no exit path, occupants exceeding walkable space, and time steps too
          large for the fastest walker.
        </p>
      </Section>

      <Section title="2. How occupants move">
        <p>
          Each occupant has two personal attributes drawn from configurable probability
          distributions:
        </p>
        <ul>
          <li>
            <strong>Walking speed</strong> - default Normal(1.2 m/s, σ = 0.25), clipped to
            [0.6, 1.8] m/s
          </li>
          <li>
            <strong>Pre-movement (reaction) delay</strong> - default Uniform(0, 15) s; the time
            between the alarm and the occupant starting to move
          </li>
        </ul>
        <p>
          Time advances in fixed steps <code>dt</code> (default 0.25 s, must satisfy
          dt ≤ cell_size / max_speed). An occupant accrues <code>dt</code> of eligible movement
          time each step and may advance one cell when its accumulator reaches the cell traversal
          time <code>cell_size / speed</code>. Faster occupants move more often. One cell per
          step, four-directional; diagonal movement is impossible.
        </p>
        <p>
          <strong>Conflict resolution:</strong> when multiple occupants want the same cell, a
          deterministic global order (seeded priority rotated round-robin each step) decides who
          moves; retry passes let a blocked occupant follow a mover into a just-vacated cell;
          head-on cycles are swapped simultaneously to prevent deadlock. Cell capacity is always
          exactly 1 - two occupants never share a cell (tested via recorded frames).
        </p>
      </Section>

      <Section title="3. How the evacuation plan works: routing strategies">
        <p>Three strategies decide which exit each occupant heads toward. Movement mechanics are identical; only the exit choice differs:</p>
        <ul>
          <li>
            <strong>Nearest exit (baseline)</strong> - every occupant routes to the closest
            reachable exit by BFS distance. Ties break by exit id.
          </li>
          <li>
            <strong>Capacity-aware</strong> - minimizes estimated total time:
            walking time + (live door load) / (door capacity). Re-evaluated every 2 s of
            simulated time with a 10 % improvement hysteresis.
          </li>
          <li>
            <strong>Balanced assignment</strong> - a greedy min-makespan heuristic distributes
            each zone's population across exits before the run starts; occupants follow their
            assigned exit.
          </li>
        </ul>
        <p>
          <strong>Exit discharge:</strong> each exit has a throughput capacity in persons/second.
          Occupants standing on an exit cell join a FIFO queue; the exit discharges as many
          queued occupants as its capacity allows each step (fractional credit carries over,
          idle banking capped at 1). This is a rate limit at the door, not a calibrated flow model.
        </p>
        <p>
          <strong>Congestion:</strong> every blocked movement attempt increments a counter on
          the contested cell and adds dt to the occupant's queue time. The heatmap shows where
          occupants lost movement opportunities - an operational bottleneck indicator, not a
          density measurement.
        </p>
      </Section>

      <Section title="4. Disaster scenarios: exact rules and intensity mapping">
        <p>
          Disasters evolve <em>during</em> the simulation - they block cells, incapacitate
          occupants, and force re-routing. Each model's intensity parameter (0–100 %) scales its
          severity. The system reports incapacitated occupants as casualties in the mass balance:
        </p>
        <p><code>total = evacuated + unreachable + incapacitated + remaining</code></p>
        <p><strong>Fire</strong> - ignites at the floor cell farthest from all exits (worst case for early detection). The fire radius grows linearly:</p>
        <p><code>radius(t) = (0.05 + 0.20 × intensity) × t</code> cells per second</p>
        <p>
          Cells within the radius (Chebyshev distance) become impassable smoke/fire. Any
          occupant standing on a newly burning cell is <strong>incapacitated</strong>. Smoke
          permeates the plan (the radius ignores walls - a documented simplification, no CFD).
          Higher intensity → faster spread → more casualties, fewer evacuees.
        </p>
        <p>
          <strong>Earthquake</strong> - a single sudden collapse at{' '}
          <code>t = 30 − 20 × intensity</code> seconds. At collapse,{' '}
          <code>round(intensity² × 0.12 × floor_cells)</code> cells become debris, chosen from
          cells sorted by proximity to the nearest exit (structural damage concentrates at exits
          and doorways). Occupants standing on debris are <strong>incapacitated</strong> (crushed).
          Occupants not yet moving get their reaction delay extended by{' '}
          <code>25 × intensity</code> seconds (post-shock confusion). The route network is
          rebuilt and everyone is re-routed.
        </p>
        <p>
          <strong>Stampede</strong> - the engine tracks blocked movement attempts per cell in a
          rolling 8-second window. When a cell exceeds the trigger threshold (lower at higher
          intensity), it and its 3-cell neighborhood become a permanent <strong>crush
          zone</strong>: occupants have fallen and the cells become impassable obstacles. The
          engine shoves occupants standing there to a free neighbor (pushed aside by the crowd -
          they are not lost). Crush zones at the door reduce effective corridor width → fewer
          people escape within the horizon. Trampling casualties are out of scope.
        </p>
      </Section>

      <Section title="5. Mass balance and recorded evidence">
        <p>
          The engine enforces a mass-balance invariant at the end of every run. If it fails, the
          engine refuses to emit results rather than fabricating them:
        </p>
        <p><code>total = evacuated + unreachable + incapacitated + remaining</code></p>
        <p>
          Every run records: timeline (per-step evacuated/inside/at-exit/incapacitated), exit
          utilization with discharge times, congestion heatmap, queue statistics, and sampled
          frames. All are stored with the run's exact configuration and seed - one click
          reproduces any result.
        </p>
      </Section>

      <Section title="6. Validation and accuracy">
        <p>
          The System Accuracy page runs a 14-case known-answer battery against the real engine:
          adequate designs must evacuate, flawed designs (sealed rooms, undersized doors,
          impossible horizons) must fail with the analytically expected outcome, and physics
          bounds (door throughput, travel time, population monotonicity) must be respected.
          The battery is regression-gated in the test suite (132+ tests).
        </p>
      </Section>

      <Section title="7. Known limitations">
        <p>
          The full list is in <code>docs/KNOWN_LIMITATIONS.md</code>. Key items: no fire/smoke
          physics (the fire model is a growing radius, not CFD); no structural collapse physics
          (debris placement is a heuristic); populations and speeds are configurable assumptions,
          not calibrated measurements; door capacities are user-set rate limits; no validation
          against real evacuation drills. The tool demonstrates evacuation <em>mechanisms</em>,
          not real-building safety.
        </p>
      </Section>

      <div className="card">
        <h3>Related pages</h3>
        <div className="toolbar">
          <Link to="/accuracy"><button className="small secondary">System Accuracy</button></Link>
          <Link to="/advisor"><button className="small secondary">Advisor</button></Link>
          <Link to="/experiments"><button className="small secondary">Experiments</button></Link>
          <Link to="/library"><button className="small secondary">Scenario Library</button></Link>
        </div>
      </div>
    </div>
  )
}
