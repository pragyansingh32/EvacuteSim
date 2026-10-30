// Live simulation view. While the run is pending/running it polls the real
// backend status. When finished, it plays back the frames the engine actually
// recorded — the animation cannot disagree with the stored result.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { AdvisorReport } from '../api/client'
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
import GridCanvas, { STATUS_COLORS, STATUS_NAMES, type ExitPulse } from '../components/GridCanvas'
import { DisclaimerBanner, ErrorAlert, MetricCard, StatusBadge, fmt, strategyLabel } from '../components/ui'
import { DISASTER_LABELS } from '../types'
import { useTheme } from '../theme'
import type { BuildingDetail, RunDetail } from '../types'

export default function RunViewPage() {
  const { id } = useParams()
  const { chart } = useTheme()
  const runId = Number(id)
  const [run, setRun] = useState<RunDetail | null>(null)
  const [building, setBuilding] = useState<BuildingDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [frameIdx, setFrameIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(4) // frames per second multiplier
  const [showCongestion, setShowCongestion] = useState(false)
  const [pulses, setPulses] = useState<ExitPulse[]>([])
  const [advisorReport, setAdvisorReport] = useState<AdvisorReport | null>(null)
  const [advisorBusy, setAdvisorBusy] = useState(false)
  const timerRef = useRef<number | null>(null)
  const lastTRef = useRef(0)

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

  // Smooth glide duration: match the real frame interval at the chosen speed.
  const transitionMs = playing
    ? Math.max(
        45,
        Math.min(
          450,
          (((frames[Math.min(frameIdx + 1, lastFrameIdx)]?.t ?? frame?.t ?? 0) -
            (frames[frameIdx]?.t ?? 0)) *
            1000) /
            Math.max(1, speed),
        ),
      )
    : 130

  // Exit discharge pulses: when a frame shows more discharges than the
  // previous one, pulse the doors that discharged in that interval.
  useEffect(() => {
    if (!run?.metrics || !frame) return
    const prevT = lastTRef.current
    lastTRef.current = frame.t
    if (frame.t <= prevT + 1e-9) {
      setPulses([])
      return
    }
    const events = (run.metrics.exit_stats ?? []).flatMap((e) =>
      e.discharge_times
        .filter((t) => prevT < t && t <= frame.t + 1e-9)
        .map(() => ({ x: e.x, y: e.y, id: e.id })),
    )
    if (events.length === 0 || events.length > 8) {
      setPulses([])
      return
    }
    setPulses(events.map((ev, i) => ({ key: `${ev.id}-${frame.t}-${i}`, x: ev.x, y: ev.y })))
    const timer = window.setTimeout(() => setPulses([]), 750)
    return () => window.clearTimeout(timer)
  }, [frameIdx, run, frame])

  const hasIncapacitated = (run?.timeline ?? []).some((entry) => entry.length > 4 && entry[4] > 0)

  const curveData = useMemo(
    () =>
      (run?.timeline ?? []).map((entry) => {
        const [t, evacuated, inside, atExit] = entry
        const incap = entry.length > 4 ? entry[4] : 0
        return {
          t: Math.round(t * 10) / 10,
          Evacuated: evacuated,
          Inside: inside,
          'At exit door': atExit,
          Incapacitated: incap,
        }
      }),
    [run],
  )

  const liveCounts = useMemo(() => {
    const inside = frame?.occupants.length ?? 0
    const total = run?.metrics?.total_occupants ?? 0
    return { inside, out: Math.max(0, total - inside) }
  }, [frame, run])

  const analyzeRun = useCallback(async () => {
    if (!run || run.status !== 'completed') return
    setAdvisorBusy(true)
    try {
      const resp = await fetch(`/api/v1/advisor/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: run.id }),
      })
      if (resp.ok) setAdvisorReport(await resp.json())
    } catch {
      // ignore
    } finally {
      setAdvisorBusy(false)
    }
  }, [run])

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

      {m && m.disasters && m.disasters.length > 0 && (
        <div className="alert error">
          <strong>Active disasters: </strong>
          {m.disasters.map((d) => `${DISASTER_LABELS[d.type] ?? d.type} @ ${Math.round(d.intensity * 100)}%`).join(', ')}
          {typeof m.incapacitated_count === 'number' && m.incapacitated_count > 0 &&
            ` — ${m.incapacitated_count} incapacitated`}
          {m.disasters.some((d) => typeof d.cells_blocked === 'number') &&
            ` — ${m.disasters.reduce((sum, d) => sum + (typeof d.cells_blocked === 'number' ? d.cells_blocked : 0), 0)} cells blocked`}
          . See the Methodology page for model rules.
        </div>
      )}

      {m && m.warnings.length > 0 && (
        <div className="alert info">
          <strong>Engine notes:</strong> {m.warnings.join(' ')}
        </div>
      )}

      {run.status === 'completed' && frames.length > 0 && (
        <div className="card player-card">
          <div className="player-bar">
            <button className="play-btn" onClick={() => setPlaying((p) => !p)} title={playing ? 'Pause' : 'Play'}>
              {playing ? '❚❚' : '▶'}
            </button>
            <button
              className="small secondary"
              onClick={() => {
                setPlaying(false)
                setFrameIdx((i) => Math.max(0, i - 1))
              }}
              title="Step back one frame"
            >
              ◀
            </button>
            <button
              className="small secondary"
              onClick={() => {
                setPlaying(false)
                setFrameIdx((i) => Math.min(lastFrameIdx, i + 1))
              }}
              title="Step forward one frame"
            >
              ▶
            </button>
            <div className="time-readout">
              <b>{fmt(frame?.t)}</b>
              <span> / {fmt(m?.sim_time_s)} s</span>
            </div>
            <div className="seg" role="group" aria-label="Playback speed">
              {[1, 2, 4, 8, 16].map((s) => (
                <button key={s} className={speed === s ? 'active' : ''} onClick={() => setSpeed(s)}>
                  {s}×
                </button>
              ))}
            </div>
            <div className="live-counters">
              <span className="lc-in">Inside {liveCounts.inside}</span>
              <span className="lc-out">Out {liveCounts.out}</span>
            </div>
            <div className="spacer" />
            <button
              className={`small ${showCongestion ? '' : 'secondary'}`}
              onClick={() => setShowCongestion((v) => !v)}
              title="Overlay blocked-move heatmap"
            >
              Congestion
            </button>
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
            style={{ width: '100%', margin: '10px 0 14px' }}
            aria-label="Frame position"
          />
          <div className="map-wrap" style={{ display: 'flex', justifyContent: 'center' }}>
            <GridCanvas
              building={building}
              cinematic
              blockedExits={(run.config.blocked_exit_ids as string[] | undefined) ?? []}
              blockedCells={(run.config.blocked_cells as [number, number][] | undefined) ?? []}
              congestion={showCongestion ? (m?.congestion ?? {}) : {}}
              frame={frame}
              previousFrame={frameIdx > 0 ? frames[frameIdx - 1] : null}
              transitionMs={transitionMs}
              pulses={pulses}
              cellPx={Math.max(12, Math.min(26, Math.floor(900 / building.width)))}
            />
          </div>
          <div className="legend">
            {STATUS_NAMES.map((name, i) => (
              <span key={name}>
                <span className="swatch" style={{ background: STATUS_COLORS[i] }} />
                {name}
              </span>
            ))}
          </div>
          <div className="kbd-note">
            Occupants glide between the engine's recorded frames; door pulses mark each
            discharge. Playback shows exactly the recorded positions — nothing invented.
          </div>
        </div>
      )}

      {run.status === 'completed' && !advisorReport && (
        <div className="card" style={{ textAlign: 'center', padding: '14px 20px' }}>
          <button onClick={analyzeRun} disabled={advisorBusy}>
            {advisorBusy ? 'Analyzing…' : 'Ask the AI Advisor'}
          </button>
          <span className="muted" style={{ marginLeft: 10 }}>
            Rule-based analysis of this run — identifies issues and suggests improvements.
          </span>
        </div>
      )}

      {advisorReport && (
        <div className="card">
          <h3>AI Advisor — {advisorReport.verdict}</h3>
          {advisorReport.observations.map((o, i) => (
            <div key={i} className="advisor-obs">
              <div className="advisor-obs-head">
                <span
                  className="badge"
                  style={
                    o.severity === 'ok'
                      ? { background: 'var(--ok-soft)', color: 'var(--ok)' }
                      : o.severity === 'warn'
                        ? { background: 'var(--warn-soft)', color: 'var(--warn)' }
                        : o.severity === 'critical'
                          ? { background: 'var(--danger-soft)', color: 'var(--danger)' }
                          : { background: 'var(--accent-soft)', color: 'var(--accent)' }
                  }
                >
                  {o.severity}
                </span>
                <strong>{o.title}</strong>
              </div>
              <div className="muted">{o.detail}</div>
            </div>
          ))}
          {advisorReport.recommendations.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <strong>Recommendations:</strong>
              <ul className="muted" style={{ margin: '4px 0 0 18px' }}>
                {advisorReport.recommendations.map((r, i) => (
                  <li key={i}>{r.title} — {r.patch_summary}</li>
                ))}
              </ul>
              <Link to={`/advisor?run=${run.id}`}>
                <button className="small" style={{ marginTop: 8 }}>Open full advisor</button>
              </Link>
            </div>
          )}
        </div>
      )}

      {run.status === 'completed' && curveData.length > 0 && (
        <div className="grid-2">
          <div className="card">
            <h3>Evacuation timeline</h3>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={curveData} margin={{ top: 5, right: 10, bottom: 20, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: chart.tick }} tickLine={false} axisLine={{ stroke: chart.grid }} />
                <YAxis tick={{ fontSize: 11, fill: chart.tick }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: chart.tooltipBg, border: `1px solid ${chart.grid}`, borderRadius: 8, color: chart.tick }} />
                <Legend iconType="circle" iconSize={8} />
                <Line type="monotone" dataKey="Evacuated" stroke="#10b981" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Inside" stroke="#6366f1" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="'At exit door'" stroke="#f59e0b" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
                {hasIncapacitated && (
                  <Line type="stepAfter" dataKey="Incapacitated" stroke="#e11d48" strokeWidth={2} dot={false} fill="rgba(225,29,72,0.1)" />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <h3>Exit utilization</h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={exitData} margin={{ top: 5, right: 10, bottom: 20, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                <XAxis dataKey="exit" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11, fill: chart.tick }} />
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
            <Link to={`/advisor?run=${run.id}`}>
              <button className="secondary">Ask the AI Advisor</button>
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
