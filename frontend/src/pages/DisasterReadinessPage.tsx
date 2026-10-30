// Disaster Readiness: tests a scenario against all 6 disaster types at
// multiple intensities and reports a clear PASS/FAIL verdict for each.

import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { api } from "../api/client"
import { DisclaimerBanner, ErrorAlert, MetricCard } from "../components/ui"
import type { ScenarioSummary } from "../types"

interface ReadinessRow {
  disaster_type: string
  intensity: number
  run_id: number
  status: string
  outcome: "PASSED" | "FAILED"
  evacuated: number
  total: number
  incapacitated: number
  remaining: number
  sim_time_s: number | null
}

interface ReadinessReport {
  scenario_id: number
  scenario_name: string
  rows: ReadinessRow[]
  passed: number
  failed: number
  total: number
  readiness_pct: number
  notes: string[]
}

const DISASTER_NAMES: Record<string, string> = {
  fire: "Fire",
  earthquake: "Earthquake",
  stampede: "Stampede",
  gas_leak: "Gas Leak",
  flood: "Flood",
  power_outage: "Power Outage",
}

export default function DisasterReadinessPage() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [report, setReport] = useState<ReadinessReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .listScenarios()
      .then((rows) => {
        setScenarios(rows)
        if (rows.length > 0) setSelectedId((prev) => prev ?? rows[0].id)
      })
      .catch((e) => setError(e.message))
  }, [])

  async function run() {
    if (!selectedId) return
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      const resp = await fetch("/api/v1/validation/disaster-readiness", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_id: selectedId }),
      })
      if (!resp.ok) {
        const body = await resp.json()
        throw new Error(body?.error?.message ?? `Server returned ${resp.status}`)
      }
      setReport(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const grouped = report
    ? [...new Set(report.rows.map((r) => r.disaster_type))].map((dtype) => ({
        type: dtype,
        rows: report.rows.filter((r) => r.disaster_type === dtype),
        allPassed: report.rows
          .filter((r) => r.disaster_type === dtype)
          .every((r) => r.outcome === "PASSED"),
        anyFailed: report.rows
          .filter((r) => r.disaster_type === dtype)
          .some((r) => r.outcome === "FAILED"),
      }))
    : []

  return (
    <div>
      <h1>Disaster Readiness</h1>
      <p className="page-sub">
        Tests a scenario against all 6 disaster types at 3 intensity levels (18 real simulation
        runs) and reports a clear PASSED/FAILED verdict for each — whether the plan successfully
        evacuated all reachable occupants under each condition.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />

      <div className="card">
        <h3>Select a scenario</h3>
        <div className="toolbar">
          <select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(Number(e.target.value))}
            style={{ maxWidth: 480 }}
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                #{s.id} {s.name}
              </option>
            ))}
          </select>
          <button onClick={run} disabled={!selectedId || busy}>
            {busy ? "Running 18 simulations…" : "Test disaster readiness"}
          </button>
        </div>
      </div>

      {report && (
        <>
          <div className="grid-3">
            <MetricCard
              label="Readiness score"
              value={`${report.readiness_pct}%`}
              tone={report.readiness_pct >= 80 ? "ok" : report.readiness_pct >= 50 ? "warn" : "danger"}
              hint={`${report.passed} of ${report.total} conditions passed`}
            />
            <MetricCard
              label="Conditions passed"
              value={`${report.passed}`}
              tone="ok"
              hint="all reachable occupants evacuated"
            />
            <MetricCard
              label="Conditions failed"
              value={`${report.failed}`}
              tone={report.failed > 0 ? "danger" : "ok"}
              hint="occupants trapped or incapacitated"
            />
          </div>

          {grouped.map((g) => (
            <div className="card" key={g.type}>
              <h3>
                {DISASTER_NAMES[g.type] ?? g.type}{" "}
                {g.allPassed && <span className="badge completed">All intensities passed</span>}
                {g.anyFailed && <span className="badge failed">Failed at some intensities</span>}
              </h3>
              <table className="data">
                <thead>
                  <tr>
                    <th>Intensity</th>
                    <th>Verdict</th>
                    <th className="num">Evacuated</th>
                    <th className="num">Incapacitated</th>
                    <th className="num">Remaining</th>
                    <th className="num">Sim time</th>
                    <th>Run</th>
                  </tr>
                </thead>
                <tbody>
                  {g.rows.map((r) => (
                    <tr key={r.run_id}>
                      <td>{Math.round(r.intensity * 100)}%</td>
                      <td>
                        <span
                          className="badge"
                          style={
                            r.outcome === "PASSED"
                              ? { background: "var(--ok-soft)", color: "var(--ok)" }
                              : { background: "var(--danger-soft)", color: "var(--danger)" }
                          }
                        >
                          {r.outcome}
                        </span>
                      </td>
                      <td className="num">{r.evacuated}/{r.total}</td>
                      <td className="num">{r.incapacitated}</td>
                      <td className="num">{r.remaining}</td>
                      <td className="num">{r.sim_time_s?.toFixed(1)}s</td>
                      <td>
                        <Link to={`/runs/${r.run_id}`}>#{r.run_id}</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          <div className="card">
            <h3>How to read this</h3>
            <ul className="muted" style={{ margin: "4px 0 0 18px" }}>
              {report.notes.map((n, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  {n}
                </li>
              ))}
              <li>
                Each row is a real simulation run stored with its exact configuration — click the
                run ID to replay the animation.
              </li>
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
