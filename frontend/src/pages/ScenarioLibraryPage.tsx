// Scenario library: all saved scenarios with one-click launch. Sample
// scenarios are clearly labeled as synthetic demonstrations.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { DisclaimerBanner, ErrorAlert, strategyLabel } from '../components/ui'
import type { ScenarioSummary } from '../types'

export default function ScenarioLibraryPage() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listScenarios()
      .then((rows) => setScenarios(rows.filter((s) => s.is_sample)))
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      <h1>Scenario Library</h1>
      <p className="page-sub">
        Reproducible demonstration scenarios. Every sample below is{' '}
        <strong>synthetic</strong> — generated from made-up building shapes and populations,
        not from measurements of any real building.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />

      <div className="grid-2">
        {scenarios.map((s) => (
          <div className="card" key={s.id}>
            <h3>{s.name}</h3>
            <p className="muted">{s.description}</p>
            <div className="toolbar">
              <Link to={`/scenarios/${s.id}`}>
                <button className="secondary">Open in editor</button>
              </Link>
              <Link to={`/runs/new?scenario=${s.id}`} style={{ pointerEvents: 'none' }} />
              <LibraryLaunchButton scenarioId={s.id} />
            </div>
          </div>
        ))}
        {scenarios.length === 0 && <div className="empty">No sample scenarios found.</div>}
      </div>
    </div>
  )
}

function LibraryLaunchButton({ scenarioId }: { scenarioId: number }) {
  const [busy, setBusy] = useState(false)
  return (
    <button
      disabled={busy}
      onClick={async () => {
        setBusy(true)
        try {
          const { run } = await api.createRun({ scenario_id: scenarioId })
          window.location.assign(`/runs/${run.id}`)
        } finally {
          setBusy(false)
        }
      }}
    >
      {busy ? 'Starting…' : 'Run now'}
    </button>
  )
}

// Re-exported for the nav label test
export const STRATEGY_LABELS_REF = strategyLabel
