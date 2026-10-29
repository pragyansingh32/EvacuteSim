// AI Advisor: observes a completed run's recorded data and proposes a better
// plan. Rule-based and deterministic — every observation cites evidence and
// every recommendation carries a concrete patch that is TESTED by running the
// real simulation before/after, so a plan is only called better once the
// engine has demonstrated it.

import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ApiRequestError, type AdvisorApplyResult, type AdvisorReport } from '../api/client'
import { DisclaimerBanner, ErrorAlert, fmt } from '../components/ui'
import type { RunSummary } from '../types'

const SEVERITY_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  ok: { bg: 'var(--ok-soft)', color: 'var(--ok)', label: 'Healthy' },
  info: { bg: 'var(--accent-soft)', color: 'var(--accent)', label: 'Note' },
  warn: { bg: 'var(--warn-soft)', color: 'var(--warn)', label: 'Warning' },
  critical: { bg: 'var(--danger-soft)', color: 'var(--danger)', label: 'Critical' },
}

function delta(before: number | null, after: number | null, lowerIsBetter = true): string {
  if (before == null || after == null) return '—'
  if (before === 0) return '—'
  const pct = ((after - before) / before) * 100
  if (Math.abs(pct) < 0.5) return 'no change'
  const better = lowerIsBetter ? pct < 0 : pct > 0
  return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}% ${better ? '(better)' : '(worse)'}`
}

export default function AdvisorPage() {
  const [params] = useSearchParams()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [runId, setRunId] = useState<number | null>(
    params.get('run') ? Number(params.get('run')) : null,
  )
  const [report, setReport] = useState<AdvisorReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, AdvisorApplyResult>>({})

  useEffect(() => {
    api
      .listRuns()
      .then((rows) => {
        const completed = rows.filter((r) => r.status === 'completed')
        setRuns(completed)
        if (!runId && completed.length > 0) setRunId(completed[0].id)
      })
      .catch((e) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const analyze = useCallback(async () => {
    if (!runId) return
    setBusy(true)
    setError(null)
    setReport(null)
    setResults({})
    try {
      setReport(await api.advisorAnalyze(runId))
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [runId])

  async function testPlan(recId: string) {
    if (!runId) return
    setTesting(recId)
    setError(null)
    try {
      const result = await api.advisorApply(runId, recId)
      setResults((prev) => ({ ...prev, [recId]: result }))
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
    } finally {
      setTesting(null)
    }
  }

  return (
    <div>
      <h1>AI Advisor</h1>
      <p className="page-sub">
        A rule-based expert system observes a completed run — exit utilization, queue times,
        congestion clusters, mass balance — and proposes a better plan. Every recommendation is
        applied to a scenario copy and <strong>tested with the real simulation</strong>, so you
        see measured before/after evidence, not promises.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />

      <div className="card">
        <h3>Choose a completed run</h3>
        <div className="toolbar">
          <select
            value={runId ?? ''}
            onChange={(e) => setRunId(Number(e.target.value))}
            style={{ maxWidth: 480 }}
          >
            {runs.length === 0 && <option value="">— no completed runs yet —</option>}
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                #{r.id} {r.name} · {r.strategy} · seed {r.seed}
              </option>
            ))}
          </select>
          <button onClick={analyze} disabled={!runId || busy}>
            {busy ? 'Analyzing…' : 'Analyze run'}
          </button>
        </div>
      </div>

      {report && (
        <>
          <div className="card">
            <h3>Advisor verdict</h3>
            <p style={{ margin: '4px 0 0', fontSize: 15 }}>
              <span
                className="badge"
                style={{
                  background: SEVERITY_STYLE[report.severity]?.bg,
                  color: SEVERITY_STYLE[report.severity]?.color,
                  marginRight: 10,
                }}
              >
                {SEVERITY_STYLE[report.severity]?.label}
              </span>
              {report.verdict}
            </p>
          </div>

          <div className="grid-2">
            <div className="card">
              <h3>Observations ({report.observations.length})</h3>
              {report.observations.map((o, i) => (
                <div key={i} className="advisor-obs">
                  <div className="advisor-obs-head">
                    <span
                      className="badge"
                      style={{
                        background: SEVERITY_STYLE[o.severity]?.bg,
                        color: SEVERITY_STYLE[o.severity]?.color,
                      }}
                    >
                      {SEVERITY_STYLE[o.severity]?.label}
                    </span>
                    <strong>{o.title}</strong>
                  </div>
                  <div className="muted">{o.detail}</div>
                </div>
              ))}
            </div>

            <div className="card">
              <h3>Recommended plans ({report.recommendations.length})</h3>
              {report.recommendations.length === 0 && (
                <div className="empty">
                  No weakness detected. Try Experiments to explore sensitivities across seeds.
                </div>
              )}
              {report.recommendations.map((r) => {
                const result = results[r.id]
                return (
                  <div key={r.id} className="advisor-rec">
                    <strong>{r.title}</strong>
                    <div className="muted" style={{ margin: '4px 0' }}>
                      {r.rationale}
                    </div>
                    <div className="kbd-note">Patch: {r.patch_summary}</div>
                    <div className="kbd-note">{r.estimate}</div>
                    <div className="toolbar" style={{ margin: '10px 0 0' }}>
                      <button className="small" onClick={() => testPlan(r.id)} disabled={testing !== null}>
                        {testing === r.id ? 'Testing with real simulation…' : 'Test this plan'}
                      </button>
                      {result && (
                        <Link to={`/runs/${result.after.run_id}`}>
                          <button className="small secondary">Open test run</button>
                        </Link>
                      )}
                    </div>
                    {result && (
                      <div className="advisor-result">
                        <table className="data">
                          <thead>
                            <tr>
                              <th>Metric</th>
                              <th className="num">Before</th>
                              <th className="num">After</th>
                              <th>Change</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr>
                              <td>Evacuation time</td>
                              <td className="num">{fmt(result.before.metrics.sim_time_s)} s</td>
                              <td className="num">{fmt(result.after.metrics.sim_time_s)} s</td>
                              <td>{delta(result.before.metrics.sim_time_s, result.after.metrics.sim_time_s)}</td>
                            </tr>
                            <tr>
                              <td>T90</td>
                              <td className="num">{fmt(result.before.metrics.t90_s)} s</td>
                              <td className="num">{fmt(result.after.metrics.t90_s)} s</td>
                              <td>{delta(result.before.metrics.t90_s, result.after.metrics.t90_s)}</td>
                            </tr>
                            <tr>
                              <td>Mean queue</td>
                              <td className="num">{fmt(result.before.metrics.queue_mean_s, 2)} s</td>
                              <td className="num">{fmt(result.after.metrics.queue_mean_s, 2)} s</td>
                              <td>{delta(result.before.metrics.queue_mean_s, result.after.metrics.queue_mean_s)}</td>
                            </tr>
                            <tr>
                              <td>Evacuated</td>
                              <td className="num">
                                {result.before.metrics.evacuated_count}/{result.before.metrics.total_occupants}
                              </td>
                              <td className="num">
                                {result.after.metrics.evacuated_count}/{result.after.metrics.total_occupants}
                              </td>
                              <td>{delta(result.before.metrics.evacuated_count, result.after.metrics.evacuated_count, false)}</td>
                            </tr>
                          </tbody>
                        </table>
                        <div className="kbd-note">
                          Saved as scenario #{result.scenario_id} — the plan is preserved and
                          re-runnable.
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card">
            <h3>About this advisor</h3>
            <p className="muted" style={{ margin: 0 }}>
              {report.disclaimer}
            </p>
          </div>
        </>
      )}
    </div>
  )
}
