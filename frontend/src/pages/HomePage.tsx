import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { DisclaimerBanner, StatusBadge, strategyLabel } from '../components/ui'
import type { BuildingSummary, RunSummary, ScenarioSummary } from '../types'

export default function HomePage() {
  const [buildings, setBuildings] = useState<BuildingSummary[]>([])
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([])
  const [recentRuns, setRecentRuns] = useState<RunSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.listBuildings(), api.listScenarios(), api.recentRuns()])
      .then(([b, s, r]) => {
        setBuildings(b)
        setScenarios(s)
        setRecentRuns(r)
      })
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      <h1>EvacuateSim</h1>
      <p className="page-sub">
        An explainable, uncertainty-aware emergency evacuation simulation and scenario
        optimization platform.
      </p>
      <DisclaimerBanner />

      {error && <div className="alert error">{error}</div>}

      <div className="card">
        <h3>What you can do</h3>
        <p>
          Draw a simplified building layout, configure a simulated population, define emergency
          scenarios (blocked exits, slower occupants, longer reaction times), run a discrete-time
          evacuation simulation, and compare routing strategies with recorded, reproducible
          evidence.
        </p>
        <div className="toolbar">
          <Link to="/buildings">
            <button>Create a building</button>
          </Link>
          <Link to="/library">
            <button className="secondary">Launch a sample scenario</button>
          </Link>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h3>Buildings ({buildings.length})</h3>
          {buildings.length === 0 && <div className="empty">No buildings yet.</div>}
          <table className="data">
            <tbody>
              {buildings.map((b) => (
                <tr key={b.id}>
                  <td>
                    <Link to={`/buildings/${b.id}`}>{b.name}</Link>
                    {b.is_sample && <span className="muted"> (sample)</span>}
                  </td>
                  <td className="muted num">
                    {b.width}×{b.height} cells · {b.cell_size_m} m/cell
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3>Scenarios ({scenarios.length})</h3>
          <table className="data">
            <tbody>
              {scenarios.slice(0, 8).map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link to={`/scenarios/${s.id}`}>{s.name}</Link>
                  </td>
                  <td className="muted">{s.is_sample ? 'sample' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Recent simulation runs</h3>
        {recentRuns.length === 0 && <div className="empty">No runs yet — start one from a scenario.</div>}
        {recentRuns.length > 0 && (
          <table className="data">
            <thead>
              <tr>
                <th>Run</th>
                <th>Strategy</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recentRuns.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/runs/${r.id}`}>#{r.id} {r.name}</Link>
                  </td>
                  <td>{strategyLabel(r.strategy)}</td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
