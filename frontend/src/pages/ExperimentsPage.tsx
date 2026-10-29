// Research experiment runner: sweep scenario parameters across seeds, watch
// progress, inspect the results table, and export CSV for external analysis.

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, ApiRequestError } from '../api/client'
import { DisclaimerBanner, ErrorAlert, StatusBadge, fmt } from '../components/ui'
import type { ExperimentResults, ExperimentSummary, ScenarioSummary } from '../types'

const COMMON_SWEEPS: Record<string, Record<string, unknown[]>> = {
  'Strategy comparison': {
    strategy: ['nearest_exit', 'capacity_aware', 'balanced_assignment'],
  },
  'Reaction delay sweep': {
    'pre_movement.max': [5, 15, 30, 60],
  },
  'Walking speed sweep': {
    'speed.mean': [0.8, 1.0, 1.2, 1.4],
  },
  'Occupancy sweep': {
    'zone_populations.ZW': [30, 60, 90],
  },
}

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([])
  const [scenarioId, setScenarioId] = useState<number | null>(null)
  const [sweepName, setSweepName] = useState('Strategy comparison')
  const [seeds, setSeeds] = useState('0,1,2')
  const [name, setName] = useState('New experiment')
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<ExperimentResults | null>(null)
  const pollRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    const list = await api.listExperiments()
    setExperiments(list)
    return list
  }, [])

  useEffect(() => {
    api
      .listScenarios()
      .then(setScenarios)
      .catch((e) => setError(e.message))
    refresh().catch(() => undefined)
  }, [refresh])

  // Poll while any experiment is running.
  useEffect(() => {
    const anyRunning = experiments.some((e) => e.status === 'pending' || e.status === 'running')
    if (!anyRunning) return
    pollRef.current = window.setTimeout(async () => {
      const list = await refresh()
      setExperiments(list)
    }, 1500)
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current)
    }
  }, [experiments, refresh])

  async function launch() {
    setError(null)
    if (!scenarioId) {
      setError('Select a base scenario first.')
      return
    }
    const sweep = COMMON_SWEEPS[sweepName]
    const seedList = seeds
      .split(',')
      .map((s) => Number(s.trim()))
      .filter((s) => Number.isFinite(s))
    try {
      await api.createExperiment({
        name,
        base_scenario_id: scenarioId,
        sweep,
        seeds: seedList,
      })
      await refresh()
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
    }
  }

  async function openResults(id: number) {
    setError(null)
    try {
      setResults(await api.getExperimentResults(id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const chartRows =
    results?.rows
      .filter((r) => r.metrics)
      .map((r) => {
        const label = Object.entries(r.sweep_values)
          .map(([k, v]) => `${k.split('.').pop()}=${v}`)
          .join(' ')
        return {
          setting: `${label} (seed ${r.seed})`,
          'T90 (s)': (r.metrics?.['t90_s'] as number) ?? 0,
          'Evacuation time (s)': (r.metrics?.['sim_time_s'] as number) ?? 0,
        }
      }) ?? []

  return (
    <div>
      <h1>Experiments</h1>
      <p className="page-sub">
        Controlled parameter sweeps over a base scenario — every combination runs the real
        simulation once per seed and stores the full results.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />

      <div className="card">
        <h3>New experiment</h3>
        <div className="grid-2">
          <label className="field">
            <span className="lbl">Base scenario</span>
            <select value={scenarioId ?? ''} onChange={(e) => setScenarioId(Number(e.target.value))}>
              <option value="">— select —</option>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  #{s.id} {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="lbl">Preset sweep</span>
            <select value={sweepName} onChange={(e) => setSweepName(e.target.value)}>
              {Object.keys(COMMON_SWEEPS).map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="lbl">Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span className="lbl">Seeds (repetitions)</span>
            <input value={seeds} onChange={(e) => setSeeds(e.target.value)} />
          </label>
        </div>
        <div className="muted" style={{ marginBottom: 10 }}>
          Sweep definition: {JSON.stringify(COMMON_SWEEPS[sweepName])}
        </div>
        <button onClick={launch} disabled={!scenarioId}>
          Launch experiment
        </button>
      </div>

      <div className="card">
        <h3>Experiments</h3>
        {experiments.length === 0 ? (
          <div className="empty">No experiments yet.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th className="num">Planned runs</th>
                <th>Status</th>
                <th>Results</th>
              </tr>
            </thead>
            <tbody>
              {experiments.map((e) => (
                <tr key={e.id}>
                  <td>{e.id}</td>
                  <td>{e.name}</td>
                  <td className="num">{e.total_planned}</td>
                  <td>
                    <StatusBadge status={e.status} />
                    {e.error && <span className="muted"> {e.error.message}</span>}
                  </td>
                  <td>
                    <button className="small secondary" onClick={() => openResults(e.id)}>
                      View
                    </button>{' '}
                    <a href={`/api/v1/experiments/${e.id}/export`}>
                      <button className="small secondary">CSV</button>
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {results && (
        <>
          <div className="card">
            <h3>
              Results — {results.experiment.name} <StatusBadge status={results.experiment.status} />
            </h3>
            <table className="data">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Sweep values</th>
                  <th className="num">Seed</th>
                  <th className="num">Evacuated</th>
                  <th className="num">Sim time</th>
                  <th className="num">T90</th>
                  <th className="num">Mean queue</th>
                </tr>
              </thead>
              <tbody>
                {results.rows.map((r) => (
                  <tr key={r.experiment_run_id}>
                    <td>
                      <Link to={`/runs/${r.run_id}`}>#{r.run_id}</Link>
                    </td>
                    <td>{JSON.stringify(r.sweep_values)}</td>
                    <td className="num">{r.seed}</td>
                    <td className="num">
                      {r.metrics
                        ? `${r.metrics['evacuated_count']}/${r.metrics['total_occupants']}`
                        : 'failed'}
                    </td>
                    <td className="num">{fmt(r.metrics?.['sim_time_s'] as number | null)}</td>
                    <td className="num">{fmt(r.metrics?.['t90_s'] as number | null)}</td>
                    <td className="num">{fmt(r.metrics?.['queue_mean_s'] as number | null, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="muted" style={{ marginTop: 8 }}>
              Export for independent analysis: <a href={`/api/v1/experiments/${results.experiment.id}/export`}>Download CSV</a>
            </div>
          </div>

          {chartRows.length > 1 && (
            <div className="card">
              <h3>Outcome spread across sweep settings and seeds</h3>
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={chartRows}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="setting" tick={{ fontSize: 10 }} interval={0} angle={-20} height={60} textAnchor="end" />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="T90 (s)" stroke="#1f6feb" dot />
                  <Line type="monotone" dataKey="Evacuation time (s)" stroke="#b45309" dot />
                </LineChart>
              </ResponsiveContainer>
              <div className="muted">
                Multiple points per setting are different seeds — the spread indicates
                run-to-run variability, not measurement noise.
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
