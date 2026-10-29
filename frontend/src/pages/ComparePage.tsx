// Strategy comparison: select completed runs, see per-metric rows and
// verdicts computed by the backend from recorded results only.

import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import { DisclaimerBanner, ErrorAlert, strategyLabel } from '../components/ui'
import { useTheme } from '../theme'
import type { ComparisonResponse, RunSummary } from '../types'

const METRIC_LABELS: Record<string, string> = {
  sim_time_s: 'Total evacuation time (s)',
  t50_s: 'T50 (s)',
  t90_s: 'T90 (s)',
  t95_s: 'T95 (s)',
  max_evacuation_time_s: 'Last person out (s)',
  queue_mean_s: 'Mean queue time (s)',
  evacuated_count: 'Evacuated (count)',
}

export default function ComparePage() {
  const [params] = useSearchParams()
  const { chart } = useTheme()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [result, setResult] = useState<ComparisonResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const compare = useCallback(async (ids: number[]) => {
    if (ids.length === 0) return
    try {
      setResult(await api.compareRuns(ids))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    api
      .listRuns()
      .then((rows) => {
        const completed = rows.filter((r) => r.status === 'completed')
        setRuns(completed)
        const fromQuery = params.get('run')
        if (fromQuery) {
          const id = Number(fromQuery)
          if (completed.some((r) => r.id === id)) setSelected([id])
        }
      })
      .catch((e) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggle = (id: number) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const chartData =
    result?.rows.map((r) => ({
      name: `#${r.run_id} ${r.strategy.replace('_exit', '').replace('_', ' ')}`,
      'Evacuation time (s)': r.metrics.sim_time_s ?? 0,
      'T90 (s)': r.metrics.t90_s ?? 0,
      'Mean queue (s)': Math.round((r.metrics.queue_mean_s ?? 0) * 10) / 10,
    })) ?? []

  return (
    <div>
      <h1>Compare Runs</h1>
      <p className="page-sub">
        Compare routing strategies on the same building, population, and conditions. For
        statistical confidence across seeds, use <Link to="/experiments">Experiments</Link>.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />

      <div className="card">
        <h3>Completed runs</h3>
        <div className="toolbar">
          {runs.length === 0 && <div className="empty">No completed runs yet.</div>}
          {runs.map((r) => (
            <button
              key={r.id}
              className={selected.includes(r.id) ? 'small' : 'small secondary'}
              onClick={() => toggle(r.id)}
            >
              #{r.id} · {strategyLabel(r.strategy)} · seed {r.seed}
            </button>
          ))}
          <div className="spacer" />
          <button disabled={selected.length < 1} onClick={() => compare(selected)}>
            Compare selected ({selected.length})
          </button>
        </div>
      </div>

      {result && (
        <>
          <div className="card">
            <h3>Metric table</h3>
            <table className="data">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Strategy</th>
                  <th className="num">Evacuated</th>
                  <th className="num">Sim time</th>
                  <th className="num">T50</th>
                  <th className="num">T90</th>
                  <th className="num">T95</th>
                  <th className="num">Max evac</th>
                  <th className="num">Mean queue</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.run_id}>
                    <td>
                      <Link to={`/runs/${r.run_id}`}>#{r.run_id}</Link>
                    </td>
                    <td>{strategyLabel(r.strategy)}</td>
                    <td className="num">
                      {r.metrics.evacuated_count}/{r.metrics.total_occupants}
                    </td>
                    <td className="num">{fmtN(r.metrics.sim_time_s)}</td>
                    <td className="num">{fmtN(r.metrics.t50_s)}</td>
                    <td className="num">{fmtN(r.metrics.t90_s)}</td>
                    <td className="num">{fmtN(r.metrics.t95_s)}</td>
                    <td className="num">{fmtN(r.metrics.max_evacuation_time_s)}</td>
                    <td className="num">{fmtN(r.metrics.queue_mean_s, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {chartData.length > 1 && (
            <div className="card">
              <h3>Headline metrics side by side</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: chart.tick }} />
                  <YAxis tick={{ fontSize: 11, fill: chart.tick }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Evacuation time (s)" fill="#1f6feb" />
                  <Bar dataKey="T90 (s)" fill="#93c5fd" />
                  <Bar dataKey="Mean queue (s)" fill="#b45309" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="card">
            <h3>Verdicts per metric (best run)</h3>
            {Object.keys(result.verdicts).length === 0 ? (
              <div className="muted">No metric separated the runs.</div>
            ) : (
              <table className="data">
                <tbody>
                  {Object.entries(result.verdicts).map(([metric, best]) => (
                    <tr key={metric}>
                      <td>{METRIC_LABELS[metric] ?? metric}</td>
                      <td>
                        <strong>{best}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <ul className="muted" style={{ marginTop: 10 }}>
              {result.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}

function fmtN(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : v.toFixed(digits)
}
