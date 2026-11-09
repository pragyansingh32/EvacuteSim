// System Accuracy page: runs the known-answer validation battery live and
// shows whether the simulation classifies each design correctly (pass vs
// fail) against analytically derived expectations.

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type ValidationReport } from '../api/client'
import { DisclaimerBanner, ErrorAlert, MetricCard } from '../components/ui'

type Filter = 'all' | 'pass' | 'fail' | 'accuracy'

const CATEGORY_LABELS: Record<Filter, string> = {
  all: 'All cases',
  pass: 'Designs that should evacuate',
  fail: 'Designs that should fail',
  accuracy: 'Quantitative bounds',
}

export default function AccuracyPage() {
  const [report, setReport] = useState<ValidationReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState<Filter>('all')
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      setReport(await api.validationBattery())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const cases = useMemo(() => {
    if (!report) return []
    return report.cases.filter((c) => filter === 'all' || c.category === filter)
  }, [report, filter])

  const passDesigns = report?.cases.filter((c) => c.category === 'pass' && c.passed).length ?? 0
  const failDesigns = report?.cases.filter((c) => c.category === 'fail' && c.passed).length ?? 0
  const bounds = report?.cases.filter((c) => c.category === 'accuracy' && c.passed).length ?? 0

  return (
    <div>
      <h1>System Accuracy</h1>
      <p className="page-sub">
        Fourteen building designs whose correct outcome is known in advance - adequate layouts
        that must evacuate, and flawed layouts (sealed rooms, undersized doors, impossible
        horizons) that must be reported as failing. Each is run through the real engine right
        now, and the system's verdict is compared with the analytical expectation.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />

      <div className="toolbar">
        <button onClick={load} disabled={busy}>
          {busy ? 'Running battery…' : 'Re-run validation battery'}
        </button>
        {report && (
          <span className="muted">
            engine v{report.engine_version} · {report.ran_cases} cases · ran live just now
          </span>
        )}
      </div>

      {report && (
        <>
          <div className="grid-4">
            <MetricCard
              label="Classification accuracy"
              value={`${report.accuracy_pct}%`}
              tone={report.accuracy_pct === 100 ? 'ok' : 'warn'}
              hint={`${report.passed} of ${report.ran_cases} known-answer cases correct`}
            />
            <MetricCard
              label="Pass designs identified"
              value={`${passDesigns}/5`}
              tone="ok"
              hint="adequate layouts correctly evacuated"
            />
            <MetricCard
              label="Failure modes identified"
              value={`${failDesigns}/5`}
              tone="danger"
              hint="sealed rooms, undersized doors, impossible horizons"
            />
            <MetricCard
              label="Physics bounds respected"
              value={`${bounds}/4`}
              hint="throughput, travel time, monotonicity, reproducibility"
            />
          </div>

          <div className="card">
            <div className="toolbar" style={{ marginBottom: 4 }}>
              {(['all', 'pass', 'fail', 'accuracy'] as Filter[]).map((f) => (
                <button
                  key={f}
                  className={filter === f ? 'small' : 'small secondary'}
                  onClick={() => setFilter(f)}
                >
                  {CATEGORY_LABELS[f]}
                </button>
              ))}
            </div>
            <table className="data">
              <thead>
                <tr>
                  <th>Verdict</th>
                  <th>Design / check</th>
                  <th>What the system must report</th>
                  <th>What the system reported</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr
                    key={c.name}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setExpanded(expanded === c.name ? null : c.name)}
                  >
                    <td>
                      <span
                        className="badge"
                        style={
                          c.passed
                            ? { background: 'var(--ok-soft)', color: 'var(--ok)' }
                            : { background: 'var(--danger-soft)', color: 'var(--danger)' }
                        }
                      >
                        {c.passed ? 'Correct' : 'Mismatch'}
                      </span>
                    </td>
                    <td>
                      <strong>{c.name}</strong>
                      <div className="muted">{c.description}</div>
                    </td>
                    <td style={{ maxWidth: 260 }}>{c.expected}</td>
                    <td style={{ maxWidth: 300 }}>
                      {c.actual}
                      {expanded === c.name && (
                        <pre style={{ marginTop: 8 }}>
                          {JSON.stringify(c.evidence, null, 2)}
                        </pre>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="kbd-note">Click a row to inspect the recorded evidence.</div>
          </div>

          <div className="card">
            <h3>How to read this</h3>
            <ul className="muted" style={{ margin: '4px 0 0 18px' }}>
              {report.notes.map((n, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  {n}
                </li>
              ))}
              <li>
                "Correct" means the engine's outcome matches the analytical expectation - for
                example a 0.25 p/s door with 120 people inside a 60 s horizon <em>must</em>{' '}
                end with 90+ people still inside, and the system reports exactly that.
              </li>
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
