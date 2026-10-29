// Runs list: all simulation runs with status, strategy, and links to results.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorAlert, StatusBadge, strategyLabel } from '../components/ui'
import type { RunSummary } from '../types'

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listRuns()
      .then(setRuns)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      <h1>Simulation Runs</h1>
      <p className="page-sub">Every run is stored with its full configuration and seed.</p>
      <ErrorAlert message={error} />
      <div className="card">
        {runs.length === 0 ? (
          <div className="empty">
            No runs yet. Launch one from the <Link to="/library">scenario library</Link>.
          </div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Run</th>
                <th>Name</th>
                <th>Strategy</th>
                <th className="num">Seed</th>
                <th>Status</th>
                <th>Finished</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/runs/${r.id}`}>#{r.id}</Link>
                  </td>
                  <td>{r.name}</td>
                  <td>{strategyLabel(r.strategy)}</td>
                  <td className="num">{r.seed}</td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="muted">{r.finished_at ? new Date(r.finished_at).toLocaleTimeString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
