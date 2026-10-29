// Live simulation view. While the run is pending/running it polls the real
// backend status. When finished, it plays back the frames the engine actually
// recorded — the animation cannot disagree with the stored result.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import GridCanvas, { STATUS_NAMES } from '../components/GridCanvas'
import { DisclaimerBanner, ErrorAlert, MetricCard, StatusBadge, fmt, strategyLabel } from '../components/ui'
import type { BuildingDetail, RunDetail } from '../types'

export default function RunViewPage() {
  const { id } = useParams()
  const runId = Number(id)
  const [run, setRun] = useState<RunDetail | null>(null)
  const [building, setBuilding] = useState<BuildingDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [frameIdx, setFrameIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(4) // frames per second multiplier
  const [showCongestion, setShowCongestion] = useState(false)
  const timerRef = useRef<number | null>(null)

  // Initial + polling load.
  const load = useCallback(async () => {
    try {
      const detail = await api.getRun(runId, true)
      setRun(detail)
      if (detail.building_id) {
        setBuilding(await api.getBuilding(detail.building_id))
      }
      return detail
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return null
    }
  }, [runId])

  useEffect(() => {
    let cancelled = false
    async function poll() {
      const detail = await load()
      if (cancelled) return
      if (detail && (detail.status === 'pending' || detail.status === 'running')) {
        setTimeout(poll, 1000)
      }
    }
    poll()
    return () => {
      cancelled = true
    }
  }, [load])

  // Playback loop over recorded frames.
  useEffect(() => {
    if (!playing || !run?.frames?.length) return
    const intervalMs = Math.max(30, 1000 / speed)
    timerRef.current = window.setInterval(() => {
      setFrameIdx((i) => {
        if (i >= (run.frames.length ?? 0) - 1) {
          setPlaying(false)
          return i
        }
        return i + 1
      })
    }, intervalMs)
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [playing, speed, run])

  const frame = run?.frames?.[frameIdx] ?? null
  const frames = run?.frames ?? []
  const lastFrameIdx = Math.max(0, frames.length - 1)

  const curveData = useMemo(
    () =>
      (run?.timeline ?? []).map(([t, evacuated, inside, atExit]) => ({
        t: Math.round(t * 10) / 10,
        Evacuated: evacuated,
        Inside: inside,
        'At exit door': atExit,
      })),
    [run],
  )

  const exitData = useMemo(
    () =>
      (run?.metrics?.exit_stats ?? []).map((e) => ({
        exit: e.id,
        Evacuated: e.evacuated,
        'Capacity (p/s)': e.capacity_pps,
      })),
    [run],
  )

  if (error) {
    return (
      <div>
        <h1>Run #{runId}</h1>
        <ErrorAlert message={error} />
      </div>
    )
  }

  if (!run || !building) return <div className="muted">Loading run…</div>

  const m = run.metrics

  return (
    <div>
      <h1>
        Run #{run.id} — {run.name}
      </h1>
      <p className="page-sub">
        Strategy: <strong>{strategyLabel(run.strategy)}</strong> · Seed: <strong>{run.seed}</strong> ·{' '}
        <StatusBadge status={run.status} />
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={run.error ? `Run failed: ${run.error.message}` : null} />

      {run.status === 'pending' || run.status === 'running' ? (
        <div className="card">
          <h3>Simulation in progress…</h3>
          <div className="progressbar">
            <div style={{ width: '50%' }} />
          </div>
          <div className="muted">This view updates automatically from the backend.</div>
        </div>
      ) : null}

      {run.status === 'failed' && (
        <div className="card">
          <h3>Run failed</h3>
          <p className="muted">{run.error?.message}</p>
        </div>
      )}

      {m && (
        <div className="grid-4">
          <MetricCard
            label="Evacuated"
            value={`${m.evacuated_count}/${m.total_occupants}`}
            tone={
              m.remaining_count === 0 && m.unreachable_count === 0
                ? 'ok'
                : m.evacuated_count === 0
                  ? 'danger'
                  : 'warn'
            }
            hint={
              m.unreachable_count
                ? `${m.unreachable_count} could not reach any exit`
                : `${m.remaining_count} still inside at end`
            }
          />
          <MetricCard label="Simulated time" value={`${fmt(m.sim_time_s)} s`} hint={`${m.steps} steps`} />
          <MetricCard label="T90" value={`${fmt(m.t90_s)} s`} hint="90% evacuated by this time" />
          <MetricCard
            label="Mean queue time"
            value={`${fmt(m.queue_mean_s)} s`}
            hint={m.fallback_count ? `${m.fallback_count} strategy fallbacks` : undefined}
          />
        </div>
      )}

      {m && m.warnings.length > 0 && (
        <div className="alert info">
          <strong>Engine notes:</strong> {m.warnings.join(' ')}
        </div>
      )}

      {run.status === 'completed' && frames.length > 0 && (
        <div className="card">
          <h3>Playback of recorded simulation frames</h3>
          <div className="toolbar">
            <button onClick={() => setPlaying((p) => !p)}>{playing ? 'Pause' : 'Play'}</button>
            <button
              className="secondary"
              onClick={() => {
                setPlaying(false)
                setFrameIdx((i) => Math.max(0, i - 1))
              }}
            >
              ◀ Step
            </button>
            <button
              className="secondary"
              onClick={() => {
                setPlaying(false)
                setFrameIdx((i) => Math.min(lastFrameIdx, i + 1))
              }}
            >
              Step ▶
            </button>
            <span className="muted">
              t = {fmt(frame?.t)} s · frame {frameIdx + 1}/{frames.length} ·{' '}
              {frame ? frame.occupants.length : 0} occupants inside
            </span>
            <div className="spacer" />
            <label className="muted" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              Speed
              <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} style={{ width: 90 }}>
                <option value={1}>1×</option>
                <option value={2}>2×</option>
                <option value={4}>4×</option>
                <option value={8}>8×</option>
                <option value={16}>16×</option>
              </select>
            </label>
            <label className="muted" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={showCongestion}
                onChange={(e) => setShowCongestion(e.target.checked)}
                style={{ width: 'auto' }}
              />
              Congestion heat
            </label>
          </div>
          <input
            type="range"
            min={0}
            max={lastFrameIdx}
            value={frameIdx}
            onChange={(e) => {
              setPlaying(false)
              setFrameIdx(Number(e.target.value))
            }}
            style={{ width: '100%', marginBottom: 10 }}
            aria-label="Frame position"
          />
          <div className="map-wrap" style={{ display: 'flex', justifyContent: 'center' }}>
            <GridCanvas
              building={building}
              blockedExits={run.config.blocked_exit_ids as string[] | undefined ?? []}
              blockedCells={(run.config.blocked_cells as [number, number][] | undefined) ?? []}
              congestion={showCongestion ? (m?.congestion ?? {}) : {}}
              frame={frame}
              cellPx={Math.max(12, Math.min(26, Math.floor(900 / building.width)))}
            />
          </div>
          <div className="legend">
            {STATUS_NAMES.map((name, i) => (
              <span key={name}>
                <span
                  className="swatch"
                  style={{
                    background: ['#94a3b8', '#1f6feb', '#b45309', '#15803d', '#7c3aed'][i],
                  }}
                />
                {name}
              </span>
            ))}
          </div>
          <div className="kbd-note">
            Frames are recorded by the engine at the configured interval; playback shows exactly
            those positions.
          </div>
        </div>
      )}

      {run.status === 'completed' && curveData.length > 0 && (
        <div className="grid-2">
          <div className="card">
            <h3>Evacuation timeline</h3>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={curveData} margin={{ top: 5, right: 10, bottom: 20, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="t" tick={{ fontSize: 11 }} label={{ value: 't (s)', position: 'insideBottom', offset: -10 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="Evacuated" stroke="#15803d" dot={false} />
                <Line type="monotone" dataKey="Inside" stroke="#1f6feb" dot={false} />
                <Line type="monotone" dataKey="At exit door" stroke="#b45309" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <h3>Exit utilization</h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={exitData} margin={{ top: 5, right: 10, bottom: 20, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="exit" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="Evacuated" fill="#1f6feb" />
                <Bar dataKey="Capacity (p/s)" fill="#94a3b8" />
              </BarChart>
            </ResponsiveContainer>
            <table className="data" style={{ marginTop: 10 }}>
              <thead>
                <tr>
                  <th>Exit</th>
                  <th className="num">Capacity</th>
                  <th className="num">Evacuated</th>
                  <th className="num">Share</th>
                </tr>
              </thead>
              <tbody>
                {(m?.exit_stats ?? []).map((e) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td className="num">{e.capacity_pps} p/s</td>
                    <td className="num">{e.evacuated}</td>
                    <td className="num">{fmt(e.utilization_pct)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {run.status === 'completed' && (
        <div className="card">
          <h3>Actions</h3>
          <div className="toolbar">
            <button
              className="secondary"
              onClick={async () => {
                const { run: repro } = await api.reproduceRun(run.id)
                window.location.assign(`/runs/${repro.id}`)
              }}
            >
              Reproduce with recorded seed
            </button>
            <Link to={`/compare?run=${run.id}`}>
              <button className="secondary">Add to comparison</button>
            </Link>
            <Link to={`/scenarios/${run.scenario_id}`}>
              <button className="secondary">Open source scenario</button>
            </Link>
          </div>
          <details style={{ marginTop: 10 }}>
            <summary className="muted">Run configuration (exact values used)</summary>
            <pre style={{ fontSize: 12, overflow: 'auto' }}>{JSON.stringify(run.config, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  )
}
