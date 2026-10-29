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
      <div className="hero card">
        <div className="hero-text">
          <h1>EvacuateSim</h1>
          <p>
            An explainable, uncertainty-aware emergency evacuation simulation and scenario
            optimization platform. Draw or import a building, simulate the crowd, and compare
            routing strategies with reproducible evidence.
          </p>
          <div className="toolbar">
            <Link to="/buildings">
              <button>Create a building</button>
            </Link>
            <Link to="/import">
              <button>Import an existing plan</button>
            </Link>
            <Link to="/library">
              <button className="secondary">Launch a sample scenario</button>
            </Link>
          </div>
        </div>
        <div className="hero-stats">
          <div className="stat">
            <b>{buildings.length}</b>
            <span>Buildings</span>
          </div>
          <div className="stat">
            <b>{scenarios.length}</b>
            <span>Scenarios</span>
          </div>
          <div className="stat">
            <b>{recentRuns.length}</b>
            <span>Recent runs</span>
          </div>
        </div>
      </div>
      <DisclaimerBanner />

      {error && <div className="alert error">{error}</div>}

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
